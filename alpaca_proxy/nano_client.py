#!/usr/bin/env python3

# A Websockets client talks to nanocast server
# https://github.com/nano-wallet-company/nano-wallet-server

# Author: twitter.com/alpacatunnel


import os
import json
import asyncio
from aiohttp import WSMsgType
from typing import List, Dict

from .ws_helper import ws_connect, ws_recv, ws_send
from .log import print_log

EMPTY_PREVIOUS = '0000000000000000000000000000000000000000000000000000000000000000'
LIGHT_SERVER = 'https://light.nano.org/'
# LIGHT_SERVER = 'https://10.1.1.31'


class NanoClientError(Exception):
    pass


class NanoLightClient():

    def __init__(self, server=LIGHT_SERVER):
        self.server = server
        self.ws = None

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

    async def close(self):
        await self._ws_session.close()
        await self.ws.close()

    def __del__(self):
        asyncio.ensure_future(self.close())

    async def _ws_send(self, request_dict):
        data = json.dumps(request_dict)
        return await ws_send(self.ws, data, WSMsgType.TEXT)

    async def _ws_recv(self):
        msg = await ws_recv(self.ws)
        if msg.type == WSMsgType.TEXT:
            try:
                return json.loads(msg.data)
            except:
                print_log('Load json string failed: {}'.format(msg.data))
                return {}
        else:
            print_log('Got unexpected message type: {}'.format(msg.type))
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
                error = 'Timeout receiving websockets message'
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
                continue

            # return a fully expected dict
            return response_dict

        print_log(error)
        raise NanoClientError(error)

    async def _ws_request(self, request_dict, excepted_keys):
        await self._ws_send(request_dict)
        await asyncio.sleep(0.03)
        response_dict = await self._ws_recv_until_success(excepted_keys)
        return response_dict

    async def price_data(self):
        request_dict = {
            'action': 'price_data',
            'currency': 'usd'
        }
        excepted_keys = ['currency', 'price']
        return await self._ws_request(request_dict, excepted_keys)

    async def work_generate(self, hash):
        request_dict = {
            'action': 'work_generate',
            'hash': hash
        }
        excepted_keys = ['work']
        return await self._ws_request(request_dict, excepted_keys)

    async def account_get(self, public_key):
        request_dict = {
            'action': 'account_get',
            'key': public_key
        }
        excepted_keys = ['account']
        return await self._ws_request(request_dict, excepted_keys)

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
            'pending': True,
            'account': account
        }
        excepted_keys = ['balance', 'pending', 'frontier']
        return await self._ws_request(request_dict, excepted_keys)

    async def block(self, hash):
        request_dict = {
            'action': 'block',
            'hash': hash
        }
        excepted_keys = ['contents']
        response_dict = await self._ws_request(request_dict, excepted_keys)
        contents = response_dict['contents']
        return json.loads(contents)

    async def block_hash(self, account, previous, representative, balance, link):
        """
        Only support "state" block, because other block types are obsoleted.
        """

        if not previous:
            previous = EMPTY_PREVIOUS

        block_dict = {
            'type': 'state',
            'account': account,
            'previous': previous,
            'representative': representative,
            'balance': balance,
            'link': link,
        }
        block_json = json.dumps(block_dict)

        request_dict = {
            'action': 'block_hash',
            'block': block_json
        }
        excepted_keys = ['hash']
        return await self._ws_request(request_dict, excepted_keys)

    async def process(self, account, previous, representative, balance, link, signature, work):
        """
        Only support "state" block, because other block types are obsoleted.
        """

        if not previous:
            previous = EMPTY_PREVIOUS

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


async def get_price():
    client = NanoLightClient()
    await client.connect(verify_ssl=False)

    price = await client.price_data()
    print_log(price)

    await client.close()


def main_test():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_price())


if __name__ == '__main__':
    main_test()
