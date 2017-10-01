Deploy a aiovpn server and a nginx server within Docker.
========================================================================================

Requirements
============

The `deploy.sh` is tested only on Ubuntu 16.04, it depends on Docker and docker-compose.

The nginx image is based on steveltn/https-portal, it will auto request certificate from Let's Encrypt and auto renew it.


Configuration
=============

Everything can be configured by editing the environments in `docker-compose.yml`.

Change the VPN URI location: `VPN_URL`.

Change the private IP on server side: `PRIVATE_IP`.

Add a new user: `VPN_USERNAME` and `VPN_PASSWORD`.

If you have multiple users, put them in the file `./nginx-ws/htpasswd`, and set `USE_HTPASSWD_FILE: 'true'`.

Set `STAGE: 'local'` to use self-signed certificate, set `STAGE: 'staging'` to request a fake certificate from Let's Encrypt.

After everything is tested, set `STAGE: 'production'` for a production environment. (visit https://github.com/SteveLTN/https-portal for details)


Deploying
=========

After configuration, deploy with this cmd:

```sh
sudo ./deploy.sh
```

It will install Docker on the system, build the image, start a nginx server with only HTTPS, and a aiovpn server with the private IP.

then you can test the URI `https://username:password@server_domain/vpn_url`.

That's it, thanks.