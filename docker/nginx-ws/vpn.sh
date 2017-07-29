#!/bin/bash


# if space in url, ignore the url
echo "$VPN_URL" | grep -q "\s"
[ $? != 0 ] || VPN_URL="/aiovpn_url"
VPN_URL="${VPN_URL///}"

sed -i s#aiovpn_url#$VPN_URL#g /var/lib/nginx-conf/default.ssl.conf.erb
cat /var/lib/nginx-conf/default.ssl.conf.erb | grep location


if [ "xtrue" == "x$USE_HTPASSWD_FILE" ]; then
    echo "use password file /etc/nginx/htpasswd"
else
    echo -n "$VPN_USERNAME:" > /etc/nginx/htpasswd
    openssl passwd -apr1 $VPN_PASSWORD >> /etc/nginx/htpasswd
fi

cat /etc/nginx/htpasswd

/init
