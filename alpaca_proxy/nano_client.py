#!/usr/bin/env python3

# A Websockets client talks to nanocast server
# https://github.com/nano-wallet-company/nano-wallet-server

# Author: twitter.com/alpacatunnel


import os
import time
import json
import decimal
from pyblake2 import blake2b
import asyncio
from concurrent.futures import ProcessPoolExecutor
from aiohttp import WSMsgType
from typing import List, Dict

from .ws_helper import ws_connect, ws_recv, ws_send
from .log import print_log
from .nano_account import Account

EMPTY_PREVIOUS = '0000000000000000000000000000000000000000000000000000000000000000'
LIGHT_SERVER = 'https://light.nano.org/'
# LIGHT_SERVER = 'https://10.1.1.31'


def _float_to_str(f):
    """
    Convert the given float to a string, without resorting to scientific notation.
    https://stackoverflow.com/questions/38847690/convert-float-to-string-without-scientific-notation-and-false-precision
    """
    # create a new context for this task
    ctx = decimal.Context()
    # 20 digits should be enough for everyone :D
    ctx.prec = 20
    d1 = ctx.create_decimal(repr(f))
    return format(d1, 'f')


def to_raw(amount):
    """
    Convert NANO (str/float/int) to raw.
    1 NANO = 10^30 raw
    """

    # convert to str first. For float, this will be rounded up and lost precision
    if isinstance(amount, float):
        amount = _float_to_str(amount)
    else:
        amount = str(amount)

    if '.' not in amount:
        amount += '.0'
    a, b = amount.split('.')
    b = b[0:30]
    b += '0' * (30 - len(b))

    return int(a) * 10**30 + int(b)


def _work_valid(work: bytes, data: bytes):
    work = bytearray(work)
    work.reverse()
    work = bytes(work)

    h = blake2b(digest_size=8)
    h.update(work+data)

    h = bytearray(h.digest())
    h.reverse()

    return h >= bytes.fromhex('FFFFFFC000000000')


def _generate_work(hash):
    print_log('start to generate work for hash: {}'.format(hash))

    hash = bytes.fromhex(hash)
    start = time.time()

    work = os.urandom(8)
    while _work_valid(work, hash) is False:
        work = os.urandom(8)

    end = time.time()
    print_log('cost {} seconds to generate work: {}'.format(int(end-start), work.hex()))
    return work.hex()


class NanoClientError(Exception):
    pass


class NanocastClient():

    def __init__(self, server=LIGHT_SERVER):
        self.server = server
        self.ws = None
        self._ws_session = None
        self._maintain_task_started = False

    async def connect(self, verify_ssl=True):
        # header of Android and iOS
        headers = {
            'X-Client-Version': '30',
            'User-Agent': 'SwiftWebSocket'
        }
        ws, session = await ws_connect(self.server, verify_ssl=verify_ssl, headers=headers)
        if not ws:
            raise NanoClientError('connect to server failed: {}'.format(self.server))
        self.ws = ws
        self._ws_session = session  # keep the session, otherwise it will be closed
        self._maintain_conn()

    async def close(self):
        if self.ws:
            await self._ws_session.close()
            await self.ws.close()

    def __del__(self):
        asyncio.ensure_future(self.close())

    async def _wait_ws_alive(self):
        while self.ws is None:
            await asyncio.sleep(0.01)

    async def _reconnect(self):
        await self._wait_ws_alive()
        while True:
            if self.ws.closed:
                await self.close()
                await self.connect()
            await asyncio.sleep(1)

    def _maintain_conn(self):
        """
        Local work generator may take too long time, ws connection may lost.
        """
        if self._maintain_task_started:
            return
        asyncio.ensure_future(self._reconnect())
        self._maintain_task_started = True

    async def _ws_send(self, request_dict):
        await self._wait_ws_alive()
        data = json.dumps(request_dict)
        return await ws_send(self.ws, data, WSMsgType.TEXT)

    async def _ws_recv(self):
        await self._wait_ws_alive()
        msg = await ws_recv(self.ws)
        if msg.type == WSMsgType.TEXT:
            try:
                return json.loads(msg.data)
            except Exception as e:
                print_log(e.__class__.__name__, e)
                print_log('Load json string failed: ({})'.format(msg.data))
                return {}
        else:
            print_log('Got unexpected message type: ({})'.format(msg.type))
            return {}

    async def _ws_recv_until_success(self, excepted_keys: List[str]) -> Dict:
        """
        Receive until get the excepted_keys in the response dict.

        The nanocast server has these features:
        1) did not implement multiplexing channels over websockets,
        2) handle requests and send responses asynchronously,
        3) broadcast price data periodically.

        So if a client sends requests too quickly, it's difficult to find out
        which response belongs to which request.
        (Client sends request A, then B, but server may response B, then A.)

        To solve this, we must slow down the requests, and don't send a request until
        a previous response is received. And we must specially handle price messages.
        """

        if 'currency' in excepted_keys and 'price' in excepted_keys:
            ignore_price = False
        else:
            ignore_price = True

        # price data broadcast interval is 60s, so work acturally timeout after 90 * 10
        retry_times = 10
        if 'work' in excepted_keys:
            timeout = 90
        else:
            timeout = 30

        error = 'Failed to get the expect data from server'
        for _x in range(retry_times):
            future = self._ws_recv()
            try:
                response_dict = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                error = 'Timeout receiving websockets message, expect {}'.format(excepted_keys)
                break

            # may be binary data or malformed json
            if not response_dict:
                continue

            # If ignore broadcasted price message here,
            # must send a separate price_data request to fetch it.
            if ignore_price and 'currency' in response_dict and 'price' in response_dict:
                print_log('Got periodically data message')
                continue

            if 'error' in response_dict:
                error = 'Got error from server: {}'.format(response_dict['error'])
                break

            expected = True
            for key in excepted_keys:
                if key not in response_dict:
                    expected = False
                    break

            if not expected:
                print_log('Warning: got message but not expected: {}'.format(response_dict))
                continue

            # return a fully expected dict
            return response_dict

        print_log(error)
        raise NanoClientError(error)

    async def _ws_request(self, request_dict, excepted_keys):
        await self._ws_send(request_dict)
        await asyncio.sleep(0.03)
        response_dict = await self._ws_recv_until_success(excepted_keys)
        print_log(response_dict)
        return response_dict

    async def price_data(self):
        request_dict = {
            'action': 'price_data',
            'currency': 'usd'
        }
        excepted_keys = ['currency', 'price']
        return await self._ws_request(request_dict, excepted_keys)

    async def work_generate_local(self, hash):
        executor = ProcessPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        work = await loop.run_in_executor(executor, _generate_work, hash)
        return work

    async def work_generate(self, hash):
        request_dict = {
            'action': 'work_generate',
            'hash': hash
        }
        excepted_keys = ['work']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        return response_dict['work']

    async def account_balance(self, account):
        request_dict = {
            'action': 'account_balance',
            'account': account
        }
        excepted_keys = ['balance', 'pending']
        return await self._ws_request(request_dict, excepted_keys)

    async def account_info(self, account):
        request_dict = {
            'action': 'account_info',
            'representative': True,
            'pending': True,
            'account': account
        }
        excepted_keys = ['balance', 'pending', 'frontier']
        return await self._ws_request(request_dict, excepted_keys)

    async def pending(self, account):
        request_dict = {
            'action': 'pending',
            'count': 10,
            'account': account
        }
        excepted_keys = ['blocks']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        return response_dict['blocks']

    async def pending2(self, account):
        request_dict = {
            'action': 'accounts_pending',
            'count': 10,
            'accounts': [account, ]
        }
        excepted_keys = ['blocks']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        return response_dict['blocks'][account]

    async def account_history(self, account, count=10, head=None):
        if head:
            request_dict = {
                'action': 'account_history',
                'raw': True,
                'account': account,
                'count': count,
                'head': head
            }
        else:
            request_dict = {
                'action': 'account_history',
                'raw': True,
                'account': account,
                'count': count
            }
        excepted_keys = ['account', 'history']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        return response_dict['history']

    async def block(self, hash):
        """
        Use self.block_info() instead, it returns the amount.
        """
        request_dict = {
            'action': 'block',
            'hash': hash
        }
        excepted_keys = ['contents']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        contents = response_dict['contents']
        return json.loads(contents)

    async def block_info(self, hash):
        request_dict = {
            'action': 'blocks_info',
            'hashes': [hash]
        }
        excepted_keys = ['blocks']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        _block_info = response_dict['blocks'][hash]
        amount = _block_info.get('amount')
        contents = json.loads(_block_info['contents'])
        contents['amount'] = amount
        return contents

    async def block_hash(self, account, previous, representative, balance, link):
        """
        Only support "state" block, because other block types are obsoleted.
        """

        if not previous:
            previous = EMPTY_PREVIOUS
        if not representative:
            representative = 'nano_1nanode8ngaakzbck8smq6ru9bethqwyehomf79sae1k7xd47dkidjqzffeg' # Nanode Rep

        block_dict = {
            'type': 'state',
            'account': account,
            'previous': previous,
            'representative': representative,
            'balance': balance,
            'link': link,
            'signature': '',
            'work': '0000000000000000',
        }

        request_dict = {
            'action': 'block_hash',
            'json_block': True,
            'block': block_dict
        }
        excepted_keys = ['hash']
        return await self._ws_request(request_dict, excepted_keys)

    async def process(self, account, previous, representative, balance, link, signature, work):
        """
        Only support "state" block, because other block types are obsoleted.
        """

        if not previous:
            previous = EMPTY_PREVIOUS
        if not representative:
            representative = 'nano_1nanode8ngaakzbck8smq6ru9bethqwyehomf79sae1k7xd47dkidjqzffeg' # Nanode Rep

        block_dict = {
            'type': 'state',
            'account': account,
            'previous': previous,
            'representative': representative,
            'balance': balance,
            'link': link,
            'signature': signature,
            'work': work
        }
        block_json = json.dumps(block_dict)

        request_dict = {
            'action': 'process',
            'block': block_json
        }
        excepted_keys = ['hash']
        return await self._ws_request(request_dict, excepted_keys)


class NanoLightClient():

    def __init__(self, account: Account):
        self.account = account
        self.cast = NanocastClient()

    async def connect(self):
        await self.cast.connect()

    async def _process_state_block(self, previous, representative, amount, link):
        hash_dict = await self.cast.block_hash(
            account=self.account.xrb_account,
            previous=previous,
            representative=representative,
            balance=amount,
            link=link
        )

        hash_data = bytes.fromhex(hash_dict['hash'])
        signature = self.account.sign(hash_data).hex()

        if previous:
            work_data = previous
        else: # for open block
            work_data = self.account.public_key.hex()

        try:
            work = await self.cast.work_generate(work_data)
        except Exception as e:
            print_log('get work from online server failed: {} {}'.format(e.__class__.__name__, e))
            work = await self.cast.work_generate_local(work_data)

        response_dict = await self.cast.process(
            account=self.account.xrb_account,
            previous=previous,
            representative=representative,
            balance=amount,
            link=link,
            signature=signature,
            work=work
        )

        return response_dict['hash']

    async def _get_sent_amount(self, source_hash):
        source_block = await self.cast.block_info(source_hash)
        amount = source_block['amount']
        if not amount:
            raise Exception('Did not get the amount from source block hash')
        return int(amount)

    async def get_price(self):
        price = await self.cast.price_data()
        return float(price['price'])

    async def state(self):
        return await self.cast.account_info(self.account.xrb_account)

    async def history(self, count=10, head=None):
        return await self.cast.account_history(self.account.xrb_account, count=count, head=head)

    async def open(self, source_hash):
        """
        source_hash: Pairing Send Block's Hash, the 'link'
        """

        previous, representative = None, None
        amount = await self._get_sent_amount(source_hash)

        frontier_hash = await self._process_state_block(
            previous, representative, amount, source_hash)

        print_log('Received Nano: {} raw'.format(amount))
        print_log('Frontier block hash is: {}'.format(frontier_hash))

        return frontier_hash

    async def receive(self, source_hash):
        """
        source_hash: Pairing Send Block's Hash, the 'link'
        """

        try:
            info = await self.cast.account_info(self.account.xrb_account)
        except NanoClientError as e:
            if 'Account not found' in str(e):
                print_log('Account not opened yet, receive with a open block.')
                return await self.open(source_hash)
            else:
                raise

        balance_before = int(info['balance'])
        previous = info['frontier']
        representative = info['representative']

        if int(info['pending']) == 0:
            print_log('No pending Nano to receive.')
            return

        amount = await self._get_sent_amount(source_hash)
        balance_after = balance_before + amount

        print_log('Balance before    : {} raw'.format(balance_before))
        print_log('Amount from source: {} raw'.format(amount))
        print_log('Total pending Nano: {} raw'.format(info['pending']))

        frontier_hash = await self._process_state_block(
            previous, representative, balance_after, source_hash)

        print_log('Received Nano     : {} raw'.format(amount))
        print_log('Balance after     : {} raw'.format(balance_after))
        print_log('Frontier block hash is: {}'.format(frontier_hash))

        return frontier_hash

    async def receive_all(self):
        """
        Receive all pending block.
        """
        try:
            pending_blocks = await self.cast.pending2(self.account.xrb_account)
        except Exception as e:
            print_log(e.__class__.__name__, e)
            print_log('get pending with accounts_pending RPC failed, try another.')
            pending_blocks = await self.cast.pending(self.account.xrb_account)

        if not pending_blocks:
            print_log('No pending block found.')
            return

        print_log('pending_blocks: {}.'.format(pending_blocks))

        for block in pending_blocks:
            await self.receive(block)

    async def send(self, dest_account, amount):
        amount = to_raw(amount)
        info = await self.cast.account_info(self.account.xrb_account)
        balance_before = int(info['balance'])
        previous = info['frontier']
        representative = info['representative']

        print_log('Balance before : {} raw'.format(balance_before))
        print_log('Amount to send : {} raw'.format(amount))

        if amount > balance_before:
            print_log('Can not send amount more than balance')
            return

        balance_after = balance_before - amount

        frontier_hash = await self._process_state_block(
            previous, representative, balance_after, dest_account)

        print_log('Balance after  : {} raw'.format(balance_after))
        print_log('Frontier block hash is: {}'.format(frontier_hash))

        return frontier_hash


async def test_get_price():
    client = NanocastClient()
    await client.connect(verify_ssl=False)

    price = await client.price_data()
    print_log(price)

    await client.close()


def main_test():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_get_price())


if __name__ == '__main__':
    main_test()
