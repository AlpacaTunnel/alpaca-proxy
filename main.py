#!/usr/bin/env python3

# Author: twitter.com/alpacatunnel
# TBD: monitor route/tunnel, chnroute

import os
import json

from aiovpn.client import start_client
from aiovpn.server import start_server


VERSION = '0.1'
CONF_NAME = 'aiovpn.json'


def get_conf():

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


def main():

    conf = get_conf()
    if conf['mode'] == 'client':
        start_client(conf)
    elif conf['mode'] == 'server':
        start_server(conf)


if __name__ == '__main__':
    main()

