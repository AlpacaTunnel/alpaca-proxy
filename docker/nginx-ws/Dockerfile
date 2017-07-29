FROM steveltn/https-portal

MAINTAINER alpaca.tunnel@gmail.com

ADD ./nginx-conf/ /var/lib/nginx-conf
ADD ./htpasswd /etc/nginx/
COPY vpn.sh /usr/bin/

ENTRYPOINT ["/bin/bash", "/usr/bin/vpn.sh"]
