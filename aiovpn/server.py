#!/usr/bin/env python

import aiohttp
import asyncio
import ipaddress
import os
import traceback
from aiohttp import web

from .helper import Arch, Command, Tunnel, TunSocketForwarder, byte2int, int2byte


UNIX_SOCKET_PATH = '/tmp/aiovpn_server.socket'
BROADCAST_MAC = bytes.fromhex('ffffffffffff')
ALLOW_P2P = True

US_READER, US_WRITER = None, None
CLIENT_DICT = {}
RECV_PKT_Q = asyncio.Queue()


async def us_connext(loop, unix_path):
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    while True:
        try:
            await asyncio.sleep(0.1)
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

        dst_mac = packet[0:6]

        if dst_mac == BROADCAST_MAC:
            await send_broad(packet)

        elif dst_mac in CLIENT_DICT:
            ws, task = CLIENT_DICT[dst_mac]
            if ws.closed:
                continue

            await ws.send_bytes(packet)


async def send_broad(packet):
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    for mac in list(CLIENT_DICT.keys()):
        # the dict may change during await
        if mac in CLIENT_DICT:
            ws, task = CLIENT_DICT[mac]
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


async def ws_recv_pkt(ws):

    if ws.closed:
        print('ws_recv_pkt: session closed')
        return None

    while True:
        msg = await ws.receive()

        if msg.type == aiohttp.WSMsgType.BINARY:
            return msg.data

        elif msg.type == aiohttp.WSMsgType.TEXT:
            print(msg.data)
            continue

        elif msg.type == aiohttp.WSMsgType.CLOSED:
            break

        elif msg.type == aiohttp.WSMsgType.ERROR:
            break

        else:
            print('ws_recv_pkt: message type unkown: %s' % msg.type)
            break

    return None


async def websocket_handler(request):
    global US_READER, US_WRITER, CLIENT_DICT, RECV_PKT_Q

    ws = web.WebSocketResponse(heartbeat=45)
    await ws.prepare(request)
    task = asyncio.Task.current_task()
    print('websocket_handler: new session connected')

    first_pkt = await ws_recv_pkt(ws)
    if first_pkt is None:
        print('websocket_handler: no packet received, close session')
        await ws.close()
        return ws

    # if one user knows others' MAC address, he can kick off others.
    # but if not allow kick off, one can not kick off himself when session lost.
    client_mac = first_pkt[6:12]
    if client_mac in CLIENT_DICT:
        (old_ws, old_task) = CLIENT_DICT.pop(client_mac)
        old_task.cancel()
        msg = 'websocket_handler: peer MAC=%s already connected, kick off the old session' % client_mac.hex()
        print(msg)
        await ws.send_str(msg)

    CLIENT_DICT[client_mac] = (ws, task)
    print('websocket_handler: add peer, MAC=%s' % client_mac.hex())

    await RECV_PKT_Q.put(first_pkt)

    try:
        while True:

            packet = await ws_recv_pkt(ws)
            if packet is None:
                break

            dst_mac, src_mac = packet[0:6], packet[6:12]

            if client_mac == src_mac:
                if dst_mac == BROADCAST_MAC:
                    await RECV_PKT_Q.put(packet)
                    await send_broad(packet)
                elif dst_mac in CLIENT_DICT and ALLOW_P2P:
                    dst_ws, dst_task = CLIENT_DICT[dst_mac]
                    await dst_ws.send_bytes(packet)
                else:
                    await RECV_PKT_Q.put(packet)

            else:
                msg = 'websocket_handler: client MAC changed from %s to %s, cancel the session' % (client_mac.hex(), src_mac.hex())
                print(msg)
                await ws.send_str(msg)
                break

    except asyncio.CancelledError:
        print('websocket_handler: websocket cancelled')

    await ws.close()

    # if CLIENT_DICT[client_mac] is not closed, it's a new session
    if client_mac in CLIENT_DICT:
        ws, task = CLIENT_DICT[client_mac]
        if ws.closed:
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

    if 'unix_path' in conf:
        unix_path = conf['unix_path']
    else:
        unix_path = None

    if unix_path:
        web.run_app(app, loop=loop, path=unix_path)
    else:
        web.run_app(app, loop=loop, host=server_host, port=server_port)

