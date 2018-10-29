alpaca-proxy
============

alpaca-proxy is a VPN/proxy implementation build on aiohttp. It uses websockets
to wrap the ethernet/socks5 packets.

Python 3.5+, uvloop 0.8+ and aiohttp 2.0+ are required.

Edit `alpaca-proxy.json` to configure. For client, use 'wss://' to enable ssl.

Two roles, `client` and `server`.

Two modes, `proxy` and `vpn`.

The server does NOT support ssl, use nginx to offload ssl.


## Pay via Nano

Proxy servers offer free Internet access. The clients can buy this service via
[Nano](https://nano.org/).

The server and client each need a Nano account. Try one of the Nano wallets.
You will need a `seed` to generate your Nano account. After opened your account,
copy your seed to the `alpaca-proxy.json` config.

For server, add these into your config

```json
{
    "cryptocoin": "nano",
    "database": "/home/user/proxy.db",
    "nano_seed": "390b9fc5efb2be3154579ea3e152f26226d5ab746dd9cf7b34ce11eadb635d31",
    "price_kilo_requests": "0.01",
    "price_gigabytes": "0.1"
}
```

The server will automatically search all Nano sent to its account, and receive them.
The balance and bill is stored in the database file. Backup it often.

The price unit here is USA dollar, not Nano, since Nano price is not stable.
The `price_kilo_requests` is how much you charge for 1,000 TCP connections,
and `price_gigabytes` is the price of 1GB data.

For client, you'll need to add the seed to your config

```json
{
    "nano_seed": "8dbb56813c5c22a900867ab13a4d54c6aafdd2c60053d9c56d910da379bba989",
    "auto_pay": 0
}
```

The client will use your seed (private key) to sign a message and send to the
server to prove that you own the account.

Not implemented yet:
You can manually send Nano to the server's address, or let the client do it.
For example, you set `auto_pay` to 0.1, the client will send 0.1 Nano to the
server when your balance reaches 0. (Server will push its Nano account to client.)
So you won't worry you spent money but got bad service.


License
-------

Copyright (C) 2018 alpaca-proxy

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.


For vpn-ws, please refer to <https://github.com/unbit/vpn-ws>.
