#!/usr/bin/env python3

import asyncio
import socket
import struct
import time
from aiohttp import WSMsgType

from .log import print_log
from .socks5 import Socks5Parser
from .multiplexing import Multiplexing
from .ws_helper import ws_connect, ws_recv, ws_send
from .ctrl_msg import CtrlMsg
from .nano_account import Account


async def s5_prepare(s5_conn, s5_reader, s5_writer):

    s5_buffer = b''
    for _x in range(20):
        s5_buffer += await s5_reader.readexactly(1)
        greeting = s5_conn.receive_greeting(s5_buffer)
        if greeting == Socks5Parser.PARSE_DONE:
            break
    else:
        raise Exception('wrong socks5 greeting message')

    greeting_reply = s5_conn.send_greeting()
    s5_writer.write(greeting_reply)

    s5_buffer = b''
    for _x in range(100):
        s5_buffer += await s5_reader.readexactly(1)
        request = s5_conn.receive_request(s5_buffer)
        if request == Socks5Parser.PARSE_DONE:
            break
    else:
        raise Exception('wrong socks5 request message')

    # after s5_conn.receive_request(), should save the addr/port in s5_conn
    address_type, dst_addr, dst_port = s5_conn.address_type[0], s5_conn.dst_addr, s5_conn.dst_port

    if address_type == Socks5Parser.ADDRESS_TYPE_IPV4:
        dst_addr = socket.inet_ntop(socket.AF_INET, dst_addr)
    elif address_type == Socks5Parser.ADDRESS_TYPE_IPV6:
        dst_addr = socket.inet_ntop(socket.AF_INET6, dst_addr)
    elif address_type == Socks5Parser.ADDRESS_TYPE_DOMAIN:
        dst_addr = dst_addr.decode()
    dst_port = struct.unpack('!H', dst_port)[0]

    return address_type, dst_addr, dst_port


async def s5_server(s5_reader, s5_writer, send_q, mp_session, s5_dict):

    s5_conn = Socks5Parser()

    address_type, dst_addr, dst_port = await s5_prepare(s5_conn, s5_reader, s5_writer)

    stream_id = mp_session.new_stream()
    s5_q = asyncio.Queue()
    s5_dict[stream_id] = s5_q

    ctrl = CtrlMsg(
        msg_type=CtrlMsg.TYPE_REQUEST,
        stream_id=stream_id,
        address_type=address_type,
        dst_addr=dst_addr,
        dst_port=dst_port
    )

    ctrl_str = ctrl.to_str()
    send_q.put_nowait((WSMsgType.TEXT, ctrl_str))
    print_log(ctrl_str)

    # first msg is socks5 response
    response = await s5_q.get()
    # print_log(response)

    if response.result:
        server_data = s5_conn.send_success_response()
        s5_writer.write(server_data)
    else:
        print_log('request failed, reason: {}'.format(response.reason))
        server_data = s5_conn.send_failed_response(1)
        s5_writer.write(server_data)
        s5_writer.close()
        return

    task = asyncio.ensure_future(ws_to_s5(stream_id, s5_q, s5_writer))

    # s5_to_ws
    while True:
        try:
            s5_data = await s5_reader.read(8192)
        except Exception as e:
            print_log('stream_id:', stream_id, e)
            task.cancel()
            break

        ws_data = mp_session.send(stream_id, s5_data)
        send_q.put_nowait((WSMsgType.BINARY, ws_data))

        # EOF
        if not s5_data:
            break


async def ws_to_s5(stream_id, s5_q, s5_writer):
    while True:
        s5_data = await s5_q.get()

        try:
            s5_writer.write(s5_data)
        except Exception as e:
            print_log('stream_id:', stream_id, e)
            break

        # EOF
        if not s5_data:
            break

    try:
        s5_writer.close()
    except Exception as _e:
        pass


async def ws_multiplexing_decode(ws, mp_session, s5_dict, send_q, nano_seed):
    account = Account(seed=nano_seed)
    while True:
        ws_msg = await ws_recv(ws)
        if not ws_msg:
            break

        if ws_msg.type == WSMsgType.TEXT:
            ctrl = CtrlMsg()
            ctrl.from_str(ws_msg.data)

            if ctrl.msg_type == CtrlMsg.TYPE_CHARGE:
                print_log(ctrl)
                if not nano_seed:
                    print_log('nano_seed is null, skip sign.')
                    continue

                timestamped_msg = '{}-message-to-sign'.format(time.time())
                signature = account.sign(bytes(timestamped_msg, 'utf-8')).hex()

                sign_msg = CtrlMsg(
                    msg_type=CtrlMsg.TYPE_SIGNATURE,
                    stream_id=mp_session.new_stream(),
                    account=account.xrb_account,
                    timestamped_msg=timestamped_msg,
                    signature=signature
                )
                print_log(sign_msg)

                ctrl_str = sign_msg.to_str()
                send_q.put_nowait((WSMsgType.TEXT, ctrl_str))

                continue

            if ctrl.msg_type == CtrlMsg.TYPE_RESPONSE:
                stream_id, s5_data = ctrl.stream_id, ctrl

        elif ws_msg.type == WSMsgType.BINARY:
            stream_id, s5_data = mp_session.receive(ws_msg.data)

        if stream_id not in s5_dict:
            print_log('got unkown stream_id', stream_id)
            continue

        s5_q = s5_dict[stream_id]
        s5_q.put_nowait(s5_data)

        if not s5_data:
            s5_dict.pop(stream_id)


async def ws_send_from_q(send_q, ws):
    """
    Use a q to receive and send to ws, because ws may be interrupted and re-connect.
    """
    while True:
        msg_type, ws_data = await send_q.get()
        await ws_send(ws, ws_data, msg_type)


async def ws_client_handler(mp_session, s5_dict, send_q, url, username, password, verify_ssl, nano_seed):

    ws, session = await ws_connect(url, username, password, verify_ssl)
    if not ws:
        return

    task_recv = asyncio.ensure_future(ws_multiplexing_decode(ws, mp_session, s5_dict, send_q, nano_seed))
    task_send = asyncio.ensure_future(ws_send_from_q(send_q, ws))
    print_log('started task: ws_recv/ws_send')

    while True:
        if ws.closed:
            session.close()
            await ws.close()
            print_log('closed session to {}'.format(url))
            task_recv.cancel()
            task_send.cancel()
            print_log('stopped task: ws_recv/ws_send')
            break
        else:
            await asyncio.sleep(1)


async def ws_client_auto_connect(mp_session, s5_dict, send_q, url, username=None, password=None, verify_ssl=True, nano_seed=None):
    while True:
        await ws_client_handler(mp_session, s5_dict, send_q, url, username, password, verify_ssl, nano_seed)


def start_proxy_client(conf):
    send_q = asyncio.Queue()
    s5_dict = {'stream_id': 's5_q'}

    mp_session = Multiplexing(role='client')

    verify_ssl = conf.get('verify_ssl', True)
    nano_seed = conf.get('nano_seed')

    loop = asyncio.get_event_loop()
    # loop.set_debug(True)

    asyncio.ensure_future(
        ws_client_auto_connect(mp_session, s5_dict, send_q, conf['server_url'], conf['username'], conf['password'], verify_ssl, nano_seed)
    )

    s5_task = asyncio.start_server(
        lambda r, w: s5_server(r, w, send_q, mp_session, s5_dict),
        conf['socks5_address'],
        conf['socks5_port'],
    )

    asyncio.ensure_future(s5_task)
    loop.run_forever()


if __name__ == '__main__':
    conf = {
        'server_url': 'ws://127.0.0.1:8080',
        'username': 'username',
        'password': 'password',
        'verify_ssl': False,
        'socks5_address': '0.0.0.0',
        'socks5_port': 1080
    }

    start_proxy_client(conf)
