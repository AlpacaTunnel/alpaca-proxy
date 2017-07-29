Deploy a aiovpn server and a nginx server within Docker.
========================================================================================

Requirements
============

Docker and docker-compose.


Certification
=============

The nginx image is based on steveltn/https-portal, it will auto request certificate from Let's Encrypt and renew it.
Uncomment `STAGE: 'production'` in `docker-compose.yml` after your testing.


Password Authentication
=======================

Add a new user

```sh
echo -n 'tom:' >> htpasswd
openssl passwd -apr1 >> htpasswd
```

and replace `./nginx-ws/htpasswd` with your new file.


Change URI
==========

The default URI location is `/aiovpn/`, you can change it in the file `./nginx-ws/nginx-conf/default.ssl.conf.erb`


Change Private IP
=================

Change the private IP on server side in the file `./aiovpn/aiovpn.json`


Deploying
=========

After replace the certificate and htpasswd, deploy with this cmd:

```sh
sudo ./deploy.sh
```

It will install Docker on the system, build the image, start a nginx server with only HTTPS, and a aiovpn server with the private IP.


then you can test the URI `wss://tom:password@server_ip:443/vpn`.

That's it, thanks.
