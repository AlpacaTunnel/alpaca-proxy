#!/usr/bin/env python3

# Author: twitter.com/alpacatunnel

import os
import asyncio
import argparse

from alpaca_proxy.nano_client import NanoLightClient
from alpaca_proxy.nano_account import Account


def main():
    parser = argparse.ArgumentParser(description='Send or receive Nano via the Light server')

    parser.add_argument('--seed', required=True, help='The seed to generate private key and Nano account/address')
    parser.add_argument('--index', default=0, help='The index of account generated with the seed, default 0')
    parser.add_argument('--state', action="store_true", help='Get the state of the account')
    parser.add_argument('--receive', help="Pairing send block's hash")
    parser.add_argument('--open', help="Pairing send block's hash")
    parser.add_argument('--send', help='Destination account')
    parser.add_argument('--amount', help='The amount to send, unit is Mnano/NANO (10^30 raw)')
    args = parser.parse_args()

    account = Account(seed=args.seed, index=args.index)
    print('Your account is {}'.format(account.xrb_account))

    loop = asyncio.get_event_loop()
    client = NanoLightClient()

    if args.state:
        loop.run_until_complete(client.connect())
        loop.run_until_complete(client.nano_state(account))

    elif args.receive:
        loop.run_until_complete(client.connect())
        loop.run_until_complete(client.nano_receive(account, args.receive))

    elif args.open:
        loop.run_until_complete(client.connect())
        loop.run_until_complete(client.nano_open(account, args.open))

    elif args.send:
        assert args.amount != None
        loop.run_until_complete(client.connect())
        loop.run_until_complete(client.nano_send(account, args.send, float(args.amount)))


if __name__ == '__main__':

    main()
