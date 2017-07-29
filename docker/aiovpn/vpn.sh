#!/bin/sh

vpn_log=/tmp/aiovpn.log


iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
[ $? != 0 ] && \
    echo "add iptables rule failed inside container." > $vpn_log && \
    exit 1


nohup stdbuf -i0 -o0 -e0 python3 /opt/aiovpn/main.py > $vpn_log 2>&1 &
tailf $vpn_log
# python3 /opt/aiovpn/main.py
[ $? != 0 ] && \
    echo "start aiovpn failed inside container." > $vpn_log && \
    exit 1

