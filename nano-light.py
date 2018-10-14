#!/usr/bin/env python3

# Author: twitter.com/alpacatunnel

import os
import asyncio

from alpaca_proxy.nano_client import NanoLightClient
from alpaca_proxy.nano_account import Account

my_test_private_key = '8dbb56813c5c22a900867ab13a4d54c6aafdd2c60053d9c56d910da379bba989'
my_test_account = 'xrb_3nxa8yf5zd7w3dbpnrraoif1ndxfgxox1ca9c6ybwescyt7ryt8r8wn8dfik'


async def test_nano_client():
    client = NanoLightClient()
    await client.connect(verify_ssl=False)

    print(await client.price_data())

    # print(await client.work_generate(os.urandom(32).hex()))

    print(await client.account_balance('xrb_3t6k35gi95xu6tergt6p69ck76ogmitsa8mnijtpxm9fkcm736xtoncuohr3'))

    print(await client.account_info('xrb_3t6k35gi95xu6tergt6p69ck76ogmitsa8mnijtpxm9fkcm736xtoncuohr3'))

    print(await client.block('991CF190094C00F0B68E2E5F75F6BEE95A2E0BD93CEAA4A6734DB9F19B728948'))

    print(await client.block_hash(
        account='xrb_1kdsjauuxw3gjcgjts6m5bbi6b1fda3dc46gkeu7fkkh14dawyp6frpmxytx',
        previous='A2AFE3F19ED352F47C60FA3D9222DF15F7C7B103A5973C2D017FC97007B7FD2A',
        representative='xrb_17wmwpg65neuh8u84f99e6nxcf48znusb437efwaafta7rtpy4n9h6io79xj',
        balance='21932669000000000000000000000000',
        link='950D2A44B0D5F9A8ED784C7ED77355D427724325560E49EACBC4D9A4B45D6245'
        ))

    print(await client.price_data())

    await client.close()


async def nano_light():
    client = NanoLightClient()
    await client.connect(verify_ssl=False)

    account = Account(private_key=my_test_private_key)
    print(account.xrb_account)

    xrb_account = account.xrb_account
    previous = None
    representative = 'xrb_17wmwpg65neuh8u84f99e6nxcf48znusb437efwaafta7rtpy4n9h6io79xj'
    balance = 1688145320856373314709356544
    link = '30B131D6D421DA2A27F5BC079B790887BD7DD3C0A3068BB0F0F2420672CEEC6A'

    hash_dict = await client.block_hash(xrb_account, previous, representative, balance, link)
    print(hash_dict)

    signature = account.sign(hash_dict['hash']).hex()
    print(signature)

    # if previous:
    #     work_dict = await client.work_generate(previous)
    # else:
    #     work_dict = await client.work_generate(account.public_key.hex())
    work_dict = {'work': 'b2cc447f2f1ccdf6'}
    print(work_dict)

    await client.process(xrb_account, previous, representative, balance, link, signature, work_dict['work'])


def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(nano_light())


if __name__ == '__main__':
    
    main()
