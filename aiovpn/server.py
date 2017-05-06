#!/usr/bin/env python

import aiohttp
import asyncio
import ipaddress
import os
import traceback
from aiohttp import web

from .helper import Arch, Command, Tunnel, TunSocketForwarder, byte2int, int2byte


UNIX_SOCKET_PATH = '/tmp/ws_vpn_server.socket'
BROADCAST_MAC = bytes.fromhex('ffffffffffff')

US_READER, US_WRITER = None, None
CLIENT_DICT = {}
RECV_PKT_Q = asyncio.Queue()


async def us_connext(loop, unix_path):
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    while True:
        try:
            fut = asyncio.open_unix_connection(unix_path, loop=loop)
            reader, writer = await asyncio.wait_for(fut, timeout=0.1, loop=loop)

            US_READER, US_WRITER = reader, writer
            print('us_connext: connected to %s' % unix_path)
            os.remove(unix_path)

            break

        except asyncio.TimeoutError:
            print('us_connect: connect to %s timeout, retry...' % unix_path)
            continue

        except ConnectionRefusedError:
            print('us_connect: connect to %s ConnectionRefusedError, retry...' % unix_path)
            await asyncio.sleep(0.1)
            continue

        except Exception as e:
            err = traceback.format_exc()
            print('us_connect: connect to %s exception: %s' % (unix_path, err))
            raise(e)

    while True:
        await asyncio.sleep(1000)


async def us_read():
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    while US_READER is None:
        await asyncio.sleep(0.1)

    print('us_read: start to read unix socket packet')

    while True:

        len_mark = await US_READER.readexactly(4)
        pkt_len = byte2int(len_mark)
        packet = await US_READER.readexactly(pkt_len)

        client_mac = packet[0:6]

        if client_mac == BROADCAST_MAC:
            for mac in list(CLIENT_DICT.keys()):
                # the dict may change during await
                if mac in CLIENT_DICT:
                    ws = CLIENT_DICT[mac]
                    if ws.closed:
                        continue
                    await ws.send_bytes(packet)

        elif client_mac in CLIENT_DICT:
            ws = CLIENT_DICT[client_mac]
            if ws.closed:
                continue

            await ws.send_bytes(packet)


async def us_write():
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    while US_WRITER is None:
        await asyncio.sleep(0.1)

    print('us_write: start to recv websockets packet')

    while True:

        packet = await RECV_PKT_Q.get()
        pkt_len = len(packet)

        US_WRITER.write(int2byte(pkt_len))
        US_WRITER.write(packet)


async def websocket_handler(request):
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    print('websocket_handler: new session connected')
    client_mac = None

    async for msg in ws:
        if ws.closed:
            break

        if msg.type == aiohttp.WSMsgType.BINARY:
            packet = msg.data
            mac = packet[6:12]

            if client_mac is None:
                client_mac = mac

                if client_mac in CLIENT_DICT:
                    msg = 'websocket_handler: peer MAC=%s already connected, reject the session' % client_mac.hex()
                    print(msg)
                    await ws.send_str(msg)
                    await ws.close()
                    return ws

                CLIENT_DICT[client_mac] = ws
                print('websocket_handler: add peer, MAC=%s' % client_mac.hex())

            if client_mac == mac:
                await RECV_PKT_Q.put(packet)
            else:
                msg = 'websocket_handler: client MAC changed, close the session'
                print(msg)
                await ws.send_str(msg)
                break

        elif msg.type == aiohttp.WSMsgType.TEXT:
            print(msg.data)
            pass

        elif msg.type == aiohttp.WSMsgType.CLOSED:
            break

        elif msg.type == aiohttp.WSMsgType.ERROR:
            break

    await ws.close()

    if client_mac in CLIENT_DICT:
        CLIENT_DICT.pop(client_mac)
    print('websocket_handler: removed peer, MAC=%s' % client_mac.hex())

    return ws


def start_server(conf):

    tun = Tunnel(conf['name'], 'tap')
    tun.IPv4 = ipaddress.IPv4Interface(conf['server_private_ip'])
    tun.delete()
    tun.add()

    ts = TunSocketForwarder(UNIX_SOCKET_PATH, conf['name'])
    ts.start()

    loop = asyncio.get_event_loop()
    loop.create_task(us_connext(loop, UNIX_SOCKET_PATH))
    loop.create_task(us_read())
    loop.create_task(us_write())

    app = web.Application()
    app.router.add_get('/', websocket_handler)
    app.router.add_get('/{name}', websocket_handler)

    if 'server_host' in conf:
        server_host = conf['server_host']
    else:
        server_host = None

    if 'server_port' in conf:
        server_port = conf['server_port']
    else:
        server_port = None

    web.run_app(app, loop=loop, host=server_host, port=server_port)

