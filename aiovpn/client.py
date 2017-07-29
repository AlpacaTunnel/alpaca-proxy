#!/usr/bin/env python3

import aiohttp
import asyncio
import ipaddress
import os
import traceback

from .helper import Arch, Command, Tunnel, TunSocketForwarder, byte2int, int2byte


UNIX_SOCKET_PATH = '/tmp/aiovpn_client.socket'

WS_RECV_SET, WS_SEND_SET, GLOBAL_WS = 0, 0, None
US_READER, US_WRITER = None, None


async def ws_connect(loop, url, username=None, password=None, verify_ssl=True):
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, US_READER, US_WRITER

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


async def us_connext(loop, unix_path):
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, US_READER, US_WRITER

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
        await asyncio.sleep(10000)


async def ws_recv():
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, US_READER, US_WRITER

    while US_WRITER is None:
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
                pkt_len = len(packet)

                US_WRITER.write(int2byte(pkt_len))
                US_WRITER.write(packet)

            elif msg.type == aiohttp.WSMsgType.TEXT:
                pass
                print('=====>>> message from server: %s' % msg.data)

            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                break


async def us_read():
    global WS_RECV_SET, WS_SEND_SET, GLOBAL_WS, US_READER, US_WRITER

    while US_READER is None:
        await asyncio.sleep(0.1)

    while True:

        if WS_SEND_SET == 1:
            WS_SEND_SET = 0
        else:
            await asyncio.sleep(0.1)
            continue

        print('us_read: start to read unix socket packets')

        while True:
            if WS_SEND_SET == 1:
                break

            if GLOBAL_WS.closed:
                break

            len_mark = await US_READER.readexactly(4)
            pkt_len = byte2int(len_mark)

            packet = await US_READER.readexactly(pkt_len)
            await GLOBAL_WS.send_bytes(packet)


def start_client(conf):

    tunif = Tunnel(conf['name'], 'tap')
    tunif.IPv4 = ipaddress.IPv4Interface(conf['client_private_ip'])
    tunif.delete()
    tunif.add()

    ts = TunSocketForwarder(UNIX_SOCKET_PATH, conf['name'])
    ts.start()

    if 'verify_ssl' in conf and conf['verify_ssl'] is True:
        verify_ssl = True
    else:
        verify_ssl = False

    loop = asyncio.get_event_loop()

    tasks = [loop.create_task(ws_connect(loop, conf['server_url'], conf['username'], conf['password'], verify_ssl)),
            loop.create_task(us_connext(loop, UNIX_SOCKET_PATH)),
            loop.create_task(ws_recv()),
            loop.create_task(us_read())]

    wait_tasks = asyncio.wait(tasks)
    loop.run_until_complete(wait_tasks)
    loop.close()

