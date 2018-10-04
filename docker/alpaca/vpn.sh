#!/bin/sh

set -e

alpaca_log=/tmp/alpaca.log
alpaca_bin=/opt/alpaca-proxy/main.py
alpaca_conf=/opt/alpaca-proxy/alpaca-proxy.json

is_vpn=false
cat $alpaca_conf | grep mode | grep vpn 2>&1 > /dev/null && is_vpn=true

if $is_vpn; then
    iptables -t mangle -A POSTROUTING -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1300
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
fi

echo > $alpaca_log
nohup stdbuf -oL -eL python3 $alpaca_bin >> $alpaca_log 2>&1 &

tail -f $alpaca_log

