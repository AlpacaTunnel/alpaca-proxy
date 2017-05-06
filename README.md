aiovpn
======

aiovpn is a VPN implementation build on aiohttp. It uses websockets to
wrap the ethernet packets. This implementation is compatible with vpn-ws.

Python >= 3.5 and aiohttp >= 2.0 is required.

Edit `aiovpn.json` to configure. For client, use 'wss://' to enable ssl.

The server does NOT support ssl, use nginx to offload ssl.


License
-------

Copyright (C) 2017 aiovpn

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
