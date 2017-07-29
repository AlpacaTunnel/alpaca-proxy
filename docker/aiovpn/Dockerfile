FROM python:3.6.2

MAINTAINER alpaca.tunnel@gmail.com

RUN apt-get update && \
    apt-get install iproute2 iptables -y && \
    apt-get clean && \
    pip3 install aiohttp && \
    git clone https://github.com/AlpacaTunnel/aiovpn.git /opt/aiovpn

COPY aiovpn.json /opt/aiovpn/
COPY vpn.sh /usr/bin/

CMD ["sh", "/usr/bin/vpn.sh"]

