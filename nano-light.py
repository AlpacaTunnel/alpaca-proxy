#!/usr/bin/env python3

# Author: twitter.com/alpacatunnel

import os
import asyncio
import argparse
from pprint import pprint

from alpaca_proxy.nano_client import NanoLightClient
from alpaca_proxy.nano_account import Account


def main():
    parser = argparse.ArgumentParser(description='Send or receive Nano via the Light server')

    parser.add_argument('--seed', required=True, help='The seed to generate private key and Nano account/address')
    parser.add_argument('--index', default=0, help='The index of account generated with the seed, default 0')
    parser.add_argument('--state', action="store_true", help='Get the state of the account')
    parser.add_argument('--history', action="store_true", help='Get the history of the account')
    parser.add_argument('--receive', help="Pairing send block's hash, or 'all'")
    parser.add_argument('--open', help="Pairing send block's hash")
    parser.add_argument('--send', help='Destination account')
    parser.add_argument('--amount', help='The amount to send, unit is Mnano/NANO (10^30 raw)')
    args = parser.parse_args()

    account = Account(seed=args.seed, index=args.index)
    # account = Account(xrb_account='xrb_1ipx847tk8o46pwxt5qjdbncjqcbwcc1rrmqnkztrfjy5k7z4imsrata9est')
    print('Your account is {}'.format(account.xrb_account))

    loop = asyncio.get_event_loop()
    client = NanoLightClient(account)
    asyncio.ensure_future(client.connect())

    if args.state:
        state = loop.run_until_complete(client.state())
        pprint(state)

    if args.history:
        history = loop.run_until_complete(client.history())
        pprint(history)

    elif args.receive:
        if args.receive == 'all':
            loop.run_until_complete(client.receive_all())
        else:
            loop.run_until_complete(client.receive(args.receive))

    elif args.open:
        loop.run_until_complete(client.open(args.open))

    elif args.send:
        assert args.amount != None
        loop.run_until_complete(client.send(args.send, args.amount))

    print('done')


if __name__ == '__main__':

    main()
