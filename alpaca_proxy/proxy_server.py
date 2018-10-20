#!/usr/bin/env python3

import asyncio
from aiohttp import web
from aiohttp import WSMsgType

from .log import print_log
from .socks5 import Socks5Parser
from .multiplexing import Multiplexing
from .ws_helper import ws_recv, ws_send
from .ctrl_msg import CtrlMsg
from .nano_account import Account
from .nano_client import NanoLightClient, EMPTY_PREVIOUS
from .db import DB


async def send_s5_response(ws, stream_id, result=False):
    ctrl = CtrlMsg(
        msg_type='response',
        stream_id=stream_id,
        result=result
        )
    result_str = ctrl.to_str()

    await ws_send(ws, result_str, WSMsgType.TEXT)


async def s5_connect(dst_addr, dst_port):
    try:
        future = asyncio.open_connection(dst_addr, dst_port)
        s5_reader, s5_writer = await asyncio.wait_for(future, timeout=10)
        print_log('connect success to', dst_addr, dst_port)
        return s5_reader, s5_writer

    # except (asyncio.TimeoutError, ConnectionRefusedError) as e:
    except Exception as e:
        print_log('error connect to', dst_addr, dst_port, str(e))
        return None, None


async def s5_to_ws(ws, mp_session, stream_id, s5_reader):
    while True:
        try:
            s5_data = await s5_reader.read(8192)
        except Exception as e:
            print_log('stream_id:', stream_id, e)
            break

        ws_data = mp_session.send(stream_id, s5_data)
        await ws_send(ws, ws_data, WSMsgType.BINARY)

        # EOF
        if not s5_data:
            break


async def ws_text_handler(ws, mp_session, s5_dict, ws_data):
    ctrl = CtrlMsg()
    ctrl.from_str(ws_data)
    # print_log(ctrl)

    if ctrl.msg_type == 'request':
        stream_id = ctrl.stream_id

        if stream_id in s5_dict:
            print_log('conflict stream_id: {}'.format(stream_id))
            return

        s5_reader, s5_writer = await s5_connect(ctrl.dst_addr, ctrl.dst_port)
        if not s5_reader or not s5_writer:
            await send_s5_response(ws, stream_id, False)
            return

        await send_s5_response(ws, stream_id, True)

        asyncio.ensure_future(s5_to_ws(ws, mp_session, stream_id, s5_reader))
        s5_dict[stream_id] = s5_writer


async def ws_binary_handler(mp_session, s5_dict, ws_data):
    stream_id, s5_data = mp_session.receive(ws_data)
    if stream_id not in s5_dict:
        print_log('unkown stream_id: {}'.format(stream_id))
        return

    # ws_to_s5
    s5_writer = s5_dict[stream_id]
    try:
        s5_writer.write(s5_data)
    except Exception as e:
        print_log('stream_id:', stream_id, e)
        s5_dict.pop(stream_id)
        return

    # EOF
    if not s5_data:
        s5_dict.pop(stream_id)


async def ws_server(request):

    mp_session = Multiplexing(role='server')
    s5_dict = {'stream_id': 's5_writer'}

    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    print_log('new session connected')

    while True:
        ws_msg = await ws_recv(ws)
        if not ws_msg:
            break

        if ws_msg.type == WSMsgType.TEXT:
            await ws_text_handler(ws, mp_session, s5_dict, ws_msg.data)

        elif ws_msg.type == WSMsgType.BINARY:
            await ws_binary_handler(mp_session, s5_dict, ws_msg.data)

    await ws.close()
    print_log('session closed')


async def update_db_history(db, account):
    """
    Update block_chain history of a account from network, order blocks by block chain.
    """
    client = NanoLightClient(account)
    await client.connect()
    await client.receive_all()

    history_blocks = []
    head = None
    count = 2

    # retrieve all blocks that not in the db
    while True:
        history_blocks += await client.history(count=count, head=head)
        head_block = history_blocks[-1]
        head = head_block['hash']
        count = 20

        # found one in the db
        if db.get_block(head):
            break

        # legacy open block
        if head_block.get('type') == 'open':
            break

        # state open block
        if head_block.get('previous') == EMPTY_PREVIOUS:
            break

    history_blocks.reverse()
    for block in history_blocks:
        db.update_block(account.xrb_account, block)


async def update_db_bill(db):
    """
    Get all client accounts and their pay to all server accounts.
    """
    for client_account in db.get_client_accounts():
        total_pay = 0
        for server_account in db.get_server_accounts():
            for block in db.get_receive_blocks(server_account, client_account):
                total_pay += int(block['amount'])
        db.update_total_pay(client_account, str(total_pay))


async def update_db(db, account):
    # create or update the server account in db
    db.update_account(account.xrb_account, db.ROLE_SERVER)

    await update_db_history(db, account)

    # create or update all the client accounts in db.
    for client in db.get_client_accounts():
        db.update_account(client, db.ROLE_CLIENT)

    await update_db_bill(db)


async def update_db_periodically(db, account):
    while True:
        try:
            await update_db(db, account)
        except Exception as e:
            print_log('Error update_db: {}'.format(e))
        print_log('Sleep 60s and update the database.')
        await asyncio.sleep(60)


def start_proxy_server(conf):

    loop = asyncio.get_event_loop()

    app = web.Application()
    app.router.add_get('/', ws_server)
    app.router.add_get('/{tail:.*}', ws_server)

    server_host = conf.get('server_host')
    server_port = conf.get('server_port')
    unix_path = conf.get('unix_path')
    nano_seed = conf.get('nano_seed')

    if nano_seed:
        account = Account(seed=nano_seed)
        print_log('Your Nano account is: {}'.format(account.xrb_account))
        db = DB('/tmp/proxy.db')
        asyncio.ensure_future(update_db_periodically(db, account))

    if unix_path:
        web.run_app(app, loop=loop, path=unix_path)
    else:
        web.run_app(app, loop=loop, host=server_host, port=server_port)

    loop.run_forever()


def _test_main():
    conf = {
        "server_host": "127.0.0.1",
        "server_port": 8081,
    }

    start_proxy_server(conf)


if __name__ == '__main__':
    _test_main()
