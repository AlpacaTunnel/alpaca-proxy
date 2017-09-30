#!/usr/bin/env python3

import aiohttp
import asyncio
import ipaddress
import os
import sys
import time
import traceback
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from .helper import Arch, Command, Tunnel, TunSocketForwarder, byte2int, int2byte


WS_RECV_SET, WS_SEND_SET, GLOBAL_WS = 0, 0, None
TUN_READER, TUN_WRITER = None, None
RECV_PKT_Q = asyncio.Queue()


async def ws_connect(loop, url, username=None, password=None, verify_ssl=True):
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, TUN_READER, TUN_WRITER

    while True:

        retry_timeout = 1

        while True:
            retry_timeout += 1

            try:
                if username and password:
                    auth = aiohttp.BasicAuth(username, password)
                else:
                    auth = None

                connector = aiohttp.TCPConnector(verify_ssl=verify_ssl, force_close=True)
                session = aiohttp.ClientSession(loop=loop, connector=connector)

                fut = session.ws_connect(url, auth=auth, heartbeat=30)

                ws = await asyncio.wait_for(fut, timeout=retry_timeout, loop=loop)

                WS_RECV_SET, WS_SEND_SET, GLOBAL_WS = 1, 1, ws
                print('ws_connect: connected to %s' % url)

                break

            except asyncio.TimeoutError:
                print('ws_connect: connect to %s timeout, retry...' % url)
                continue

            except Exception as e:
                err = traceback.format_exc()
                print('ws_connect: connect to %s exception: %s' % (url, err))
                print('ws_connect: retry after %s second...' % retry_timeout)
                await asyncio.sleep(retry_timeout)
                continue

        while True:
            if ws.closed:
                await ws.close()
                print('ws_connect: session to %s closed' % url)
                break
            else:
                await asyncio.sleep(1)


async def ws_recv():
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, TUN_READER, TUN_WRITER

    while TUN_WRITER is None:
        await asyncio.sleep(0.1)

    while True:

        if WS_RECV_SET == 1:
            WS_RECV_SET = 0
        else:
            await asyncio.sleep(0.1)
            continue

        print('ws_recv: start to recv websockets messages')

        async for msg in GLOBAL_WS:
            if WS_RECV_SET == 1:
                break

            if GLOBAL_WS.closed:
                break

            if msg.type == aiohttp.WSMsgType.BINARY:
                
                packet = msg.data
                TUN_WRITER.write(packet)

            elif msg.type == aiohttp.WSMsgType.TEXT:
                pass
                print('=====>>> message from server: %s' % msg.data)

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                break


async def ws_send():
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, TUN_READER, TUN_WRITER, RECV_PKT_Q
    while True:

        if WS_SEND_SET == 1:
            WS_SEND_SET = 0
        else:
            await asyncio.sleep(0.1)
            continue

        print('ws_send: start to send packets to websockets')

        while True:
            if WS_SEND_SET == 1:
                break

            if GLOBAL_WS.closed:
                break

            packet = await RECV_PKT_Q.get()
            await GLOBAL_WS.send_bytes(packet)


def tun_read():
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, TUN_READER, TUN_WRITER, RECV_PKT_Q

    packet = TUN_READER.read(2048)
    # asyncio.async(RECV_PKT_Q.put(packet))
    RECV_PKT_Q.put_nowait(packet)


def start_client(conf):
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, TUN_READER, TUN_WRITER

    tunif = Tunnel(conf['name'], 'tap')
    tunif.IPv4 = ipaddress.IPv4Interface(conf['client_private_ip'])
    tunif.delete()
    tunif.add()
    tunfd = tunif.open()
    TUN_READER = tunfd
    TUN_WRITER = tunfd

    if 'verify_ssl' in conf and conf['verify_ssl'] is True:
        verify_ssl = True
    else:
        verify_ssl = False

    loop = asyncio.get_event_loop()

    loop.add_reader(TUN_READER.fileno(), tun_read)


    tasks = [loop.create_task(ws_connect(loop, conf['server_url'], conf['username'], conf['password'], verify_ssl)),
            loop.create_task(ws_recv()),
            loop.create_task(ws_send()),
            ]

    wait_tasks = asyncio.wait(tasks)
    loop.run_until_complete(wait_tasks)
    loop.close()

