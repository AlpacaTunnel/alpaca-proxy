Deploy a alpaca server and a nginx server within Docker
=======================================================

## Requirements

Please install Docker and docker-compose first.

The nginx image is based on
[steveltn/https-portal](https://github.com/SteveLTN/https-portal),
it will auto request certificate from Let's Encrypt and auto renew it.
The nginx configuration used here requires a domain name.
Raw IP address is forbidden.


## Alpaca Proxy/VPN

You can config the alpaca server to be proxy or vpn mode by editing
`alpaca/alpaca-proxy.json`. You don't need to change the host/port.

The Nginx and Alpaca docker instance communicate by the docker bridge network.
The Nginx instance can access the Alpaca server by domain name `alpaca`,
because it's the Alpaca server's name in `docker-compose.yml`.


## Nginx

Edit the Nginx config in `nginx-ws/default.ssl.conf.erb`.

In the default config, I added basic username/password authentication.
Edit user in `nginx-ws/htpasswd`, the format is `username:password_hash`.
You can generate the hash with this cmd:

```sh
openssl passwd -apr1 YOUR_PASSWORD
```

Change the proxy/vpn URI location if needed, default is `/alpaca_url/`. The
Nginx server will pass all HTTP requests to the URI to the alpaca proxy server.

Set `STAGE: 'local'` to use self-signed certificate, set `STAGE: 'staging'` to
request a fake certificate from Let's Encrypt. After everything is tested, set
`STAGE: 'production'` for a production environment.


## Deploy

After configuration, deploy with this cmd:

```sh
docker-compose up --build -d
```

It will build the image, start a nginx server with only HTTPS, and start a
alpaca server. After the cmd finished, you can test with the URI
`https://username:password@server_domain/alpaca_url/`. If anything goes wrong,
you can check the logs with `docker logs instance-name`.

That's it, thanks.
