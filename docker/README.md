Deploy a aiovpn server and a nginx server within Docker.
========================================================================================

Requirements
============

The `deploy.sh` is tested only on Ubuntu 16.04, it depends on Docker and docker-compose.

The nginx image is based on steveltn/https-portal, it will auto request certificate from Let's Encrypt and auto renew it.

The nginx configuration I used here requires a domain name. Raw IP address is forbidden.


Configuration
=============

Everything can be configured by editing the environments in `docker-compose.yml`. Don't change any other files, otherwise the deploy script may fail.

* Change the VPN URI location: `VPN_URL`.

* Change the private IP on server side: `PRIVATE_IP`.

* Add a new user: `VPN_USERNAME` and `VPN_PASSWORD`.

* If you have multiple users, put them in the file `./nginx-ws/htpasswd`, and set `USE_HTPASSWD_FILE: 'true'`. This will obsolete `VPN_USERNAME` and `VPN_PASSWORD`.

* Set `STAGE: 'local'` to use self-signed certificate, set `STAGE: 'staging'` to request a fake certificate from Let's Encrypt.

* After everything is tested, set `STAGE: 'production'` for a production environment. (visit https://github.com/SteveLTN/https-portal for details)


Deploying
=========

After configuration, deploy with this cmd:

```sh
sudo ./deploy.sh
```

It will install Docker on the system, build the image, start a nginx server with only HTTPS, and start a aiovpn server with the private IP.

After the script finished, you can test the URI `https://username:password@server_domain/vpn_url`.

If anything goes wrong, you can check the logs with `docker logs instance-name`.

That's it, thanks.
