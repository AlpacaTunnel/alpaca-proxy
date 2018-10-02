# Parse socks5 protocol, only support NO AUTHENTICATION and CONNECT CMD.

# Author: twitter.com/alpacatunnel


import struct


def socks5_request_encode(address_type, dst_addr, dst_port):
    # 1 bytes, 2 bytes, left are IPv4/IPv6/domain
    request_data = address_type + dst_port + dst_addr
    return request_data


def socks5_request_decode(data):
    # 1 bytes, 2 bytes, left are IPv4/IPv6/domain
    address_type, dst_port, dst_addr = data[0], data[1:3], data[3:]
    return address_type, dst_port, dst_addr


class Socks5Parser():
    """
    No io involved. Only parse binary data.
    """

    SOCKS_VERSION = 5

    AUTH_METHOD_NO_AUTH = 0
    AUTH_METHOD_GSSAPI = 1
    AUTH_METHOD_USERNAME_PASSWORD = 2

    CMD_CONNECT = 1
    CMD_BIND = 2
    CMD_UDP_ASSOCIATE = 3

    ADDRESS_TYPE_IPV4 = 1
    ADDRESS_TYPE_IPV6 = 4
    ADDRESS_TYPE_DOMAIN = 3

    IncompleteReadError = 0
    PARSE_DONE = 1

    def __init__(self):
        self.auth_methods = None
        self.address_type = None
        self.dst_addr = None
        self.dst_port = None

    def receive_greeting(self, data):
        if len(data) < 2:
            return self.IncompleteReadError

        version, nmethods = data[0], data[1]

        assert version == self.SOCKS_VERSION
        assert nmethods > 0

        if nmethods + 2 != len(data):
            return self.IncompleteReadError

        auth_methods = []
        for i in range(nmethods):
            auth_methods.append(data[2+i])

        self.auth_methods = auth_methods

        if (self.AUTH_METHOD_NO_AUTH not in auth_methods and
            self.AUTH_METHOD_USERNAME_PASSWORD not in auth_methods):
            raise Exception('auth methods not supported')

        return self.PARSE_DONE

    def send_greeting(self):
        return struct.pack("!BB", self.SOCKS_VERSION, self.AUTH_METHOD_NO_AUTH)

    def receive_request(self, data):
        if len(data) < 4:
            return self.IncompleteReadError

        version, cmd, _reserved, address_type = struct.unpack("!BBBB", data[0:4])
        assert version == self.SOCKS_VERSION
        assert cmd == self.CMD_CONNECT

        if address_type == self.ADDRESS_TYPE_IPV4:
            if len(data) < 4+4+2:
                return self.IncompleteReadError

            dst_addr = data[4:8]
            dst_port = data[8:10]

        elif address_type == self.ADDRESS_TYPE_IPV6:
            if len(data) < 4+16+2:
                return self.IncompleteReadError

            dst_addr = data[4:20]
            dst_port = data[20:22]

        elif address_type == self.ADDRESS_TYPE_DOMAIN:
            if len(data) < 4+1:
                return self.IncompleteReadError

            domain_length = data[4]
            if len(data) < 4+1+domain_length+2:
                return self.IncompleteReadError

            dst_addr = data[4+1:4+1+domain_length]
            dst_port = data[4+1+domain_length:4+1+domain_length+2]

        else:
            raise Exception('address_type not supported')

        # print(address_type, dst_addr, dst_port)
        self.address_type = struct.pack("!B", address_type)
        self.dst_addr = dst_addr
        self.dst_port = dst_port

        return self.PARSE_DONE

    def send_success_response(self):
        return struct.pack("!BBBBIH", self.SOCKS_VERSION, 0, 0, self.ADDRESS_TYPE_IPV4, 0, 0)

    def send_failed_response(self, error_number=9):
        return struct.pack("!BBBBIH", self.SOCKS_VERSION, error_number, 0, self.ADDRESS_TYPE_IPV4, 0, 0)


def _test_main():
    pass


if __name__ == '__main__':
    _test_main()
