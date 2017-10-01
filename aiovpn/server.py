#!/usr/bin/env python

import aiohttp
import asyncio
import ipaddress
from aiohttp import web
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from .helper import Tunnel


BROADCAST_MAC = bytes.fromhex('ffffffffffff')
ALLOW_P2P = True

CLIENT_DICT = {}
TUNFD = None


async def ws_send(send_q):
    global CLIENT_DICT

    print('ws_send: start to send packet')

    while True:
        packet = await send_q.get()

        dst_mac = packet[0:6]

        if dst_mac == BROADCAST_MAC:
            await send_broad(packet)

        elif dst_mac in CLIENT_DICT:
            ws, task = CLIENT_DICT[dst_mac]
            if ws.closed:
                continue

            await ws.send_bytes(packet)


async def send_broad(packet):
    global CLIENT_DICT

    for mac in list(CLIENT_DICT.keys()):
        # the dict may change during await
        if mac in CLIENT_DICT:
            ws, task = CLIENT_DICT[mac]
            if ws.closed:
                continue
            await ws.send_bytes(packet)


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
    global CLIENT_DICT, TUNFD
    tun = TUNFD

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

    tun.write(first_pkt)

    try:
        while True:

            packet = await ws_recv_pkt(ws)
            if packet is None:
                break

            dst_mac, src_mac = packet[0:6], packet[6:12]

            if client_mac == src_mac:
                if dst_mac == BROADCAST_MAC:
                    tun.write(packet)
                    await send_broad(packet)
                elif dst_mac in CLIENT_DICT and ALLOW_P2P:
                    dst_ws, dst_task = CLIENT_DICT[dst_mac]
                    await dst_ws.send_bytes(packet)
                else:
                    tun.write(packet)

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


def tun_read(tun, send_q):
    # Do NOT put while loop here! It will block other coroutines.
    packet = tun.read(2048)
    send_q.put_nowait(packet)


def start_server(conf):
    global TUNFD

    send_q = asyncio.Queue()

    tunif = Tunnel(conf['name'], 'tap')
    tunif.IPv4 = ipaddress.IPv4Interface(conf['server_private_ip'])
    tunif.delete()
    tunif.add()
    tun = tunif.open()
    TUNFD = tun

    loop = asyncio.get_event_loop()
    loop.add_reader(tun.fileno(), tun_read, tun, send_q)
    loop.create_task(ws_send(send_q))

    app = web.Application()
    app.router.add_get('/', websocket_handler)
    app.router.add_get('/{tail:.*}', websocket_handler)

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

