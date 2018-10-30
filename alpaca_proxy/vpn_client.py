#!/usr/bin/env python3

import aiohttp
import asyncio
import ipaddress
import traceback
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from .log import print_log
from .tunnel import Tunnel
from .ws_helper import ws_connect, ws_recv, ws_send


MAX_MTU = 9000


async def ws_client_handler(tun, send_q, url, username=None, password=None, verify_ssl=True):

    ws, session = await ws_connect(url, username, password, verify_ssl)
    if not ws:
        return

    task_recv = asyncio.ensure_future(ws_recv_to_tun(ws, tun))
    task_send = asyncio.ensure_future(ws_send_from_q(send_q, ws))
    print_log('started task: ws_recv/ws_send')

    while True:
        if ws.closed:
            await session.close()
            await ws.close()
            print_log('closed session to %s' % url)
            task_recv.cancel()
            task_send.cancel()
            print_log('stopped task: ws_recv/ws_send')
            break
        else:
            await asyncio.sleep(1)


async def ws_client_auto_connect(tun, send_q, url, username=None, password=None, verify_ssl=True):
    while True:
        await ws_client_handler(tun, send_q, url, username, password, verify_ssl)


async def ws_recv_to_tun(ws, tun):
    while True:
        msg = await ws_recv(ws)
        if not msg:
            break

        if msg.type == aiohttp.WSMsgType.BINARY:
            tun.write(msg.data)

        elif msg.type == aiohttp.WSMsgType.TEXT:
            print_log('=====>>> ws_recv message from server: %s' % msg.data)


async def ws_send_from_q(send_q, ws):
    while True:
        packet = await send_q.get()
        await ws_send(ws, packet, aiohttp.WSMsgType.BINARY)


def tun_read(tun, send_q):
    # Do NOT put while loop here! It will block other coroutines.
    packet = tun.read(MAX_MTU)
    send_q.put_nowait(packet)


def start_vpn_client(conf):
    send_q = asyncio.Queue()
    if 'verify_ssl' in conf and conf['verify_ssl'] is True:
        verify_ssl = True
    else:
        verify_ssl = False

    tunif = Tunnel(conf['name'], 'tap')
    tunif.IPv4 = ipaddress.IPv4Interface(conf['client_private_ip'])
    tunif.delete()
    tunif.add()
    tun = tunif.open()

    loop = asyncio.get_event_loop()
    loop.add_reader(tun.fileno(), tun_read, tun, send_q)
    loop.run_until_complete(
        ws_client_auto_connect(tun, send_q, conf['server_url'], conf['username'], conf['password'], verify_ssl)
        )
    loop.close()

