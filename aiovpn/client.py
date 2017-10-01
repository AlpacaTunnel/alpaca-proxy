#!/usr/bin/env python3

import aiohttp
import asyncio
import ipaddress
import traceback
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

from .helper import Tunnel


async def ws_connect(loop, tun, send_q, url, username=None, password=None, verify_ssl=True):
    while True:
        retry_timeout = 2
        while True:
            retry_timeout += 2

            try:
                if username and password:
                    auth = aiohttp.BasicAuth(username, password)
                else:
                    auth = None

                connector = aiohttp.TCPConnector(verify_ssl=verify_ssl, force_close=True)
                session = aiohttp.ClientSession(loop=loop, connector=connector)
                future = session.ws_connect(url, auth=auth, heartbeat=30)
                ws = await asyncio.wait_for(future, timeout=retry_timeout, loop=loop)
                print('ws_connect: connected to %s' % url)
                break

            except asyncio.TimeoutError:
                print('ws_connect: connect to %s timeout, retry after %s second...' % (url, retry_timeout))
                continue

            except Exception as e:
                print('ws_connect: connect to %s exception: %s' % (url, traceback.format_exc()))
                print('ws_connect: retry after %s second...' % retry_timeout)
                await asyncio.sleep(retry_timeout)
                continue

        task_recv = asyncio.ensure_future(ws_recv(ws, tun))
        task_send = asyncio.ensure_future(ws_send(send_q, ws))
        print('ws_connect: started task: ws_recv/ws_send')

        while True:
            if ws.closed:
                await ws.close()
                print('ws_connect: closed session to %s' % url)
                task_recv.cancel()
                task_send.cancel()
                print('ws_connect: stopped task: ws_recv/ws_send')
                break
            else:
                await asyncio.sleep(1)


async def ws_recv(ws, tun):
    while True:
        if ws.closed:
            break
        else:
            msg = await ws.receive()

        if msg.type == aiohttp.WSMsgType.BINARY:
            packet = msg.data
            tun.write(packet)

        elif msg.type == aiohttp.WSMsgType.TEXT:
            print('=====>>> message from server: %s' % msg.data)


async def ws_send(send_q, ws):
    while True:
        packet = await send_q.get()
        # If not break here, the send_bytes() will block all coroutines.
        if ws.closed:
            break
        else:
            await ws.send_bytes(packet)


def tun_read(tun, send_q):
    # Do NOT put while loop here! It will block other coroutines.
    packet = tun.read(2048)
    send_q.put_nowait(packet)


def start_client(conf):
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
        ws_connect(loop, tun, send_q, conf['server_url'], conf['username'], conf['password'], verify_ssl)
        )
    loop.close()

