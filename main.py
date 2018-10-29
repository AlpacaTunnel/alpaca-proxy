#!/usr/bin/env python3

# Author: twitter.com/alpacatunnel


import os
import json
import argparse

from alpaca_proxy.proxy_client import start_proxy_client
from alpaca_proxy.proxy_server import start_proxy_server
from alpaca_proxy.vpn_client import start_vpn_client
from alpaca_proxy.vpn_server import start_vpn_server


VERSION = '1.0'
CONF_NAME = 'alpaca-proxy.json'


def get_conf(conf_file=None):

    if not conf_file:

        cur_dir = os.path.dirname(os.path.realpath(__file__))

        if cur_dir == '/usr/local/bin':
            conf_path = '/usr/local/etc'
        elif cur_dir == '/usr/bin':
            conf_path = '/etc'
        else:
            conf_path = cur_dir

        conf_file = os.path.join(conf_path, CONF_NAME)

    with open(conf_file) as data_file:
        conf = json.load(data_file)

    return conf


def main(conf):

    if   conf['role'] == 'client' and conf['mode'] == 'proxy':
        start_proxy_client(conf)
    elif conf['role'] == 'server' and conf['mode'] == 'proxy':
        start_proxy_server(conf)
    elif conf['role'] == 'client' and conf['mode'] == 'vpn':
        start_vpn_client(conf)
    elif conf['role'] == 'server' and conf['mode'] == 'vpn':
        start_vpn_server(conf)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--conf', default=None, help='path to the configure file')
    args = parser.parse_args()

    conf = get_conf(args.conf)
    main(conf)
