#!/bin/bash
export PATH="/bin:/sbin:/usr/sbin:/usr/bin:/usr/local/bin"


vpn_log=/tmp/vpn-ws/vpn-ws.log


[ ! "$(docker -v)" ] && \
    echo "Installing docker..." && \
    curl -sSL https://get.docker.com/ | sh

[ ! "$(docker -v)" ] && \
    echo "install docker failed" && \
    exit 1


[ ! "$(docker-compose -v)" ] && \
    echo "Installing docker-compose..." && \
    apt-get install docker-compose -y

[ ! "$(docker-compose -v)" ] && \
    echo "install docker-compose failed" && \
    exit 1

docker-compose build
[ $? != 0 ] && echo "build images failed" && \
    exit 1


echo "Starting vpn..."
docker-compose up -d
[ $? != 0 ] && echo "start images failed" && \
    exit 1


echo "Done."

