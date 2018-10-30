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
from .nano_client import NanoLightClient, EMPTY_PREVIOUS, to_raw
from .db import DB

# cost unit is dollar
NANO_PRICE_USD = 2.718281828
COST_PER_REQUEST = 0.0001
COST_PER_BYTE = 0.000001

RAW_PER_REQUEST = to_raw(COST_PER_REQUEST * NANO_PRICE_USD)
RAW_PER_BYTE = to_raw(COST_PER_BYTE * NANO_PRICE_USD)

# warn on last 100 requests or 10,000 bytes
BALANCE_WARN_THRESHOLD = RAW_PER_REQUEST * 100 + RAW_PER_BYTE * 10**4


async def send_s5_response(ws, stream_id, result=False, reason=None):
    ctrl = CtrlMsg(
        msg_type=CtrlMsg.TYPE_RESPONSE,
        stream_id=stream_id,
        result=result,
        reason=reason
        )
    ctrl_str = ctrl.to_str()

    await ws_send(ws, ctrl_str, WSMsgType.TEXT)


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


def charge_bytes(db, xrb_account, size):
    # return balance
    if not xrb_account:
        return 1

    balance = db.get_bill_balance(xrb_account)

    spend = RAW_PER_BYTE * size
    db.increase_total_bytes(xrb_account, size)
    db.increase_total_spend(xrb_account, spend)
    db.update_bill_balance(xrb_account)

    return balance


def charge_requests(db, xrb_account):
    # return balance
    if not xrb_account:
        return 1

    balance = db.get_bill_balance(xrb_account)

    db.increase_total_requests(xrb_account, 1)
    db.increase_total_spend(xrb_account, RAW_PER_REQUEST)
    db.update_bill_balance(xrb_account)

    return balance


async def s5_to_ws(ws, mp_session, stream_id, s5_reader, db, xrb_account):
    while True:
        try:
            s5_data = await s5_reader.read(8192)
        except Exception as e:
            print_log('stream_id:', stream_id, e)
            break

        balance = charge_bytes(db, xrb_account, len(s5_data))
        if balance < 0:
            s5_data = b''

        ws_data = mp_session.send(stream_id, s5_data)
        await ws_send(ws, ws_data, WSMsgType.BINARY)

        # EOF
        if not s5_data:
            break


async def ws_signature_handler(ctrl, db):
    client_account = Account(xrb_account=ctrl.client_account)
    is_valid = client_account.verify(bytes(ctrl.timestamped_msg, 'utf-8'), ctrl.signature)
    if not is_valid:
        print_log('signature not valid for account: {}'.format(ctrl.client_account))
        return False

    db.update_account(ctrl.client_account, DB.ROLE_CLIENT)
    await update_db_bill(db)
    print_log('added account to database: {}'.format(ctrl.client_account))

    return True


async def ws_request_handler(ws, mp_session, s5_dict, ctrl, db, xrb_account, account_verified):
    stream_id = ctrl.stream_id

    if stream_id in s5_dict:
        print_log('conflict stream_id: {}'.format(stream_id))
        return

    if not account_verified:
        await send_s5_response(ws, ctrl.stream_id, False, CtrlMsg.REASON_ACCOUNT_NOT_VERIFIED)
        return

    balance = charge_requests(db, xrb_account)
    if balance < 0:
        await send_s5_response(ws, ctrl.stream_id, False, CtrlMsg.REASON_NEGATIVE_BALANCE)
        return

    s5_reader, s5_writer = await s5_connect(ctrl.dst_addr, ctrl.dst_port)
    if not s5_reader or not s5_writer:
        await send_s5_response(ws, stream_id, False)
        return

    await send_s5_response(ws, stream_id, True)

    asyncio.ensure_future(s5_to_ws(ws, mp_session, stream_id, s5_reader, db, xrb_account))
    s5_dict[stream_id] = s5_writer


async def ws_binary_handler(mp_session, s5_dict, ws_data, db, xrb_account):
    stream_id, s5_data = mp_session.receive(ws_data)
    if stream_id not in s5_dict:
        print_log('unkown stream_id: {}'.format(stream_id))
        return

    balance = charge_bytes(db, xrb_account, len(s5_data))
    if balance < 0:
        s5_data = b''

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


async def ws_send_bill(ws, mp_session, db, xrb_account):
    bill = db.get_bill(xrb_account)

    ctrl = CtrlMsg(
        msg_type=CtrlMsg.TYPE_BALANCE,
        stream_id=mp_session.new_stream(),
        balance=bill.get('balance'),
        total_pay=bill.get('total_pay'),
        total_spend=bill.get('total_spend'),
        total_requests=bill.get('total_requests'),
        total_bytes=bill.get('total_bytes'),
    )
    ctrl_str = ctrl.to_str()
    print_log(ctrl_str)
    await ws_send(ws, ctrl_str, WSMsgType.TEXT)


async def ws_server(ws, db, cryptocoin):
    mp_session = Multiplexing(role='server')
    s5_dict = {'stream_id': 's5_writer'}

    if cryptocoin:
        ctrl = CtrlMsg(
            msg_type=CtrlMsg.TYPE_CHARGE,
            stream_id=mp_session.new_stream(),
            coin=cryptocoin.get('coin'),
            server_account=cryptocoin.get('server_account'),
            price_kilo_requests=cryptocoin.get('price_kilo_requests'),
            price_gigabytes=cryptocoin.get('price_gigabytes'),
        )
        ctrl_str = ctrl.to_str()
        await ws_send(ws, ctrl_str, WSMsgType.TEXT)

        account_verified = False

    else:
        account_verified = True

    xrb_account = None

    while True:
        ws_msg = await ws_recv(ws)
        if not ws_msg:
            break

        if ws_msg.type == WSMsgType.TEXT:
            ctrl = CtrlMsg()
            ctrl.from_str(ws_msg.data)

            if ctrl.msg_type == CtrlMsg.TYPE_SIGNATURE:
                account_verified = await ws_signature_handler(ctrl, db)
                if not account_verified:
                    break

                xrb_account = ctrl.client_account
                await ws_send_bill(ws, mp_session, db, xrb_account)

            if ctrl.msg_type == CtrlMsg.TYPE_REQUEST:
                await ws_request_handler(ws, mp_session, s5_dict, ctrl, db, xrb_account, account_verified)

                if xrb_account and db.get_bill_balance(xrb_account) < BALANCE_WARN_THRESHOLD:
                    await ws_send_bill(ws, mp_session, db, xrb_account)

        elif ws_msg.type == WSMsgType.BINARY:
            await ws_binary_handler(mp_session, s5_dict, ws_msg.data, db, xrb_account)

    await ws.close()
    print_log('session closed')
    return ws


async def http_server_handler(request):
    try:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        print_log('new session connected from {}'.format(request.protocol))

        db = request.app['db']
        cryptocoin = request.app['cryptocoin']
        await ws_server(ws, db, cryptocoin)

    except Exception as e:
        print_log('Error: got Exception: ({})' .format(e))

    return web.WebSocketResponse(heartbeat=3)


async def update_db_history(db, account):
    """
    Update block_chain history of a account from network, order blocks by block chain.
    """
    client = NanoLightClient(account)
    await client.connect()

    global NANO_PRICE_USD, COST_PER_REQUEST, COST_PER_BYTE, RAW_PER_REQUEST, RAW_PER_BYTE, BALANCE_WARN_THRESHOLD
    NANO_PRICE_USD = await client.get_price()
    print_log('current price {} USD'.format(NANO_PRICE_USD))

    cost_per_request = NANO_PRICE_USD * COST_PER_REQUEST
    cost_per_byte = NANO_PRICE_USD * COST_PER_BYTE
    RAW_PER_REQUEST = to_raw(cost_per_request)
    RAW_PER_BYTE = to_raw(cost_per_byte)
    BALANCE_WARN_THRESHOLD = RAW_PER_REQUEST * 100 + RAW_PER_BYTE * 10**4
    print_log('cost per request: {} NANO, or {} raw'.format(cost_per_request, RAW_PER_REQUEST))
    print_log('cost per byte: {} NANO, or {} raw'.format(cost_per_byte, RAW_PER_BYTE))

    try:
        await client.receive_all()
    except Exception as e:
        print_log('Error receive all pending: {}'.format(e))

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
    db.update_account(account.xrb_account, DB.ROLE_SERVER)

    await update_db_history(db, account)

    # create or update all the client accounts in db.
    for client in db.get_client_accounts():
        db.update_account(client, DB.ROLE_CLIENT)

    await update_db_bill(db)


async def update_db_periodically(db, account):
    while True:
        try:
            await update_db(db, account)
        except Exception as e:
            print_log('Error update_db: {}'.format(e))
        db.commit()
        print_log('Sleep 60s and update the database.')
        await asyncio.sleep(60)


def start_proxy_server(conf):
    print_log(conf)

    app = web.Application()
    app.router.add_get('/', http_server_handler)
    app.router.add_get('/{tail:.*}', http_server_handler)

    server_host = conf.get('server_host')
    server_port = conf.get('server_port')
    unix_path = conf.get('unix_path')

    cryptocoin = conf.get('cryptocoin')
    database = conf.get('database', '/tmp/proxy.db')
    nano_seed = conf.get('nano_seed')
    price_kilo_requests = conf.get('price_kilo_requests', 0.01)
    price_gigabytes = conf.get('price_gigabytes', 0.01)

    cost_per_request = float(price_kilo_requests) / 1000
    cost_per_byte = float(price_gigabytes) / 10**9

    global COST_PER_REQUEST, COST_PER_BYTE
    COST_PER_REQUEST, COST_PER_BYTE = cost_per_request, cost_per_byte

    if cryptocoin:
        account = Account(seed=nano_seed)
        print_log('Your Nano account is: {}'.format(account.xrb_account))

        db = DB(database)
        asyncio.ensure_future(update_db_periodically(db, account))

        app['db'] = db
        app['cryptocoin'] = {
            'coin': cryptocoin,
            'server_account': account.xrb_account,
            'price_gigabytes': price_gigabytes,
            'price_kilo_requests': price_kilo_requests,
        }

    else:
        app['cryptocoin'] = {}
        app['db'] = None

    if unix_path:
        web.run_app(app, path=unix_path)
    else:
        web.run_app(app, host=server_host, port=server_port)

    loop = asyncio.get_event_loop()
    loop.run_forever()


def _test_main():
    conf = {
        "server_host": "127.0.0.1",
        "server_port": 8081,
    }

    start_proxy_server(conf)


if __name__ == '__main__':
    _test_main()
