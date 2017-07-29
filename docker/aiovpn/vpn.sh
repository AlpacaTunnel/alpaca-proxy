#!/bin/sh

vpn_log=/tmp/aiovpn.log


# if no "/" in IP, ignore the IP
echo "$PRIVATE_IP" | grep -q "/"
[ $? != 0 ] && PRIVATE_IP="10.18.1.1/24"

sed -i s#10.18.1.1/24#$PRIVATE_IP#g /opt/aiovpn/aiovpn.json
cat /opt/aiovpn/aiovpn.json


iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
[ $? != 0 ] && \
    echo "add iptables rule failed inside container." > $vpn_log && \
    exit 1


echo > $vpn_log
nohup stdbuf -i0 -o0 -e0 python3 /opt/aiovpn/main.py >> $vpn_log 2>&1 &
# python3 /opt/aiovpn/main.py
[ $? != 0 ] && \
    echo "start aiovpn failed inside container." > $vpn_log && \
    exit 1

tailf $vpn_log

