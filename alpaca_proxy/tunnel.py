#!/usr/bin/env python3

# Add and delete tuntap interface on Linux.

# Author: twitter.com/alpacatunnel


import re
import platform
import ipaddress
import struct
import fcntl

from .command import exec_cmd


class Arch():
    ARCH = platform.machine()

    if ARCH in ('ppc64', 'ppc64le'):
        # From linux/include/linux/if_tun.h
        TUNSETIFF = 0x800454ca
        TUNGETIFF = 0x400454d2
        IFF_TUN = 0x1
        IFF_TAP = 0x2
        IFF_NO_PI = 0x1000
        # From linux/include/linux/if.h
        IFF_UP = 0x1
        # From linux/netlink.h
        NETLINK_ROUTE = 0
        NLM_F_REQUEST = 1
        NLM_F_ACK = 4
        RTM_DELLINK = 17
        NLMSG_ERROR = 2

    else:
        # From linux/include/linux/if_tun.h
        TUNSETIFF = 0x400454ca
        TUNGETIFF = 0x800454d2
        IFF_TUN = 0x0001
        IFF_TAP = 0x0002
        IFF_NO_PI = 0x1000
        # From linux/include/linux/if.h
        IFF_UP = 0x1
        # From linux/netlink.h
        NETLINK_ROUTE = 0
        NLM_F_REQUEST = 1
        NLM_F_ACK = 4
        RTM_DELLINK = 17
        NLMSG_ERROR = 2


class Tunnel():
    """
    A class to manage the tuntap interface.
    """

    MIN_MTU = 68
    MAX_MTU = 9000
    DEFAULT_MTU = 1500
    DEFAULT_MODE = 'tun'

    def __init__(self, name, mode=None, mtu=None, IPv4=None, IPv6=None):
        """
        :param str name:
            name of the tunnel

        :param str mode:
            mode of the tunnel, tun or tap

        :param int mtu:
            mtu of the tunnel, must less than 1408

        :param ipaddress.IPv4Interface IPv4:
            IPv4 address and mask, the mask better be 16

        :param ipaddress.IPv6Interface IPv6:
            IPv6 address and mask
        """

        self.name  = str(name)
        self._mode = mode
        self._mtu  = mtu
        self._IPv4 = IPv4
        self._IPv6 = IPv6

    @property
    def mode(self):
        if self._mode:
            return self._mode
        else:
            return self.__class__.DEFAULT_MODE

    @mode.setter
    def mode(self, mode):
        mode = str(mode)
        if mode.lower() not in ['tun', 'tap']:
            raise ValueError('mode must be tun or tap')
        self._mode = mode

    @property
    def mtu(self):
        if self._mtu:
            return self._mtu
        else:
            return self.__class__.DEFAULT_MTU

    @mtu.setter
    def mtu(self, mtu):
        mtu = int(mtu)
        if mtu > self.__class__.MAX_MTU or mtu < self.__class__.MIN_MTU:
            raise ValueError('mtu must be between %d and %d' % (self.__class__.MIN_MTU, self.__class__.MAX_MTU))
        self._mtu = mtu

    @property
    def IPv4(self):
        return self._IPv4

    @IPv4.setter
    def IPv4(self, ip):
        if not isinstance(ip, ipaddress.IPv4Interface):
            raise ValueError('%s is not instance of ipaddress.IPv4Interface' % ip)
        self._IPv4 = ip

    @property
    def IPv6(self):
        return self._IPv6

    @IPv6.setter
    def IPv6(self, ip):
        if not isinstance(ip, ipaddress.IPv6Interface):
            raise ValueError('%s is not instance of ipaddress.IPv6Interface' % ip)
        self._IPv6 = ip

    def _cmd(self, c, split=False, strict=False):
        rc, output = exec_cmd(c, realtime_print=False)

        if strict and int(rc) != 0:
            raise Exception('cmd ({}) error: {}'.format(c, output))

        if split:
            return rc, output.split('\n')
        else:
            return rc, output
    
    def _exists(self):
        '''
        return True if tunif exists
        '''
        rc, interfaces = self._cmd('ip link', True)
        if rc != 0:
            raise Exception('cmd `ip link` error: %s' % interfaces)
        for line in interfaces:
            re_obj = re.match(r'^[0-9]+:\s+(.*?):\s+<', line)
            if re_obj:
                interface = re_obj.group(1)
                if interface == self.name:
                    return True
        return False

    def _ipv4_overlaps(self):
        rc, ip_addrs = self._cmd('ip -4 addr', True)
        if rc != 0:
            raise Exception('cmd `ip -4 addr` error: %s' % ip_addrs)
        for line in ip_addrs:
            line = line.lstrip()
            if line.startswith('inet'):
                re_obj = re.match(r'^inet\s+(.*?)\s', line)
                if re_obj:
                    inet4 = ipaddress.IPv4Network(re_obj.group(1), False)
                    if self.IPv4:
                        inet4_self = ipaddress.IPv4Network(self.IPv4, False)
                        if inet4.overlaps(inet4_self):
                            return True
        return False

    def _ipv6_overlaps(self):
        rc, ip_addrs = self._cmd('ip -6 addr', True)
        if rc != 0:
            raise Exception('cmd `ip -6 addr` error: %s' % ip_addrs)
        for line in ip_addrs:
            line = line.lstrip()
            if line.startswith('inet6'):
                re_obj = re.match(r'^inet6\s+(.*?)\s', line)
                if re_obj:
                    inet6 = ipaddress.IPv6Network(re_obj.group(1), False)
                    if self.IPv6:
                        inet6_self = ipaddress.IPv6Network(self.IPv6, False)
                        if inet6.overlaps(inet6_self):
                            return True
        return False

    def _add_ipv4(self):
        if self._ipv4_overlaps():
            raise Exception('tunnel %s: IPv4 overlaps with other interface, cannot add IP' % self.name)
        c = 'ip -4 addr add %s dev %s' % (self.IPv4, self.name)
        rc, output = self._cmd(c)
        if rc != 0:
            raise Exception('cmd `%s` error: %s' % (c, output))

    def _add_ipv6(self):
        if self._ipv6_overlaps():
            raise Exception('tunnel %s: IPv6 overlaps with other interface, cannot add IP' % self.name)
        c = 'ip -6 addr add %s dev %s' % (self.IPv6, self.name)
        rc, output = self._cmd(c)
        if rc != 0:
            raise Exception('cmd `%s` error: %s' % (c, output))

    def _add_dev(self):
        if self._exists():
            raise Exception('tunnel %s already exists, nothing to do!' % self.name)
        c = 'ip tuntap add dev %s mode %s' % (self.name, self.mode)
        rc, output = self._cmd(c)
        if rc != 0:
            raise Exception('cmd `%s` error: %s' % (c, output))
        self._cmd('ip link set %s up' % self.name)
        if not self._exists():
            raise Exception('add tunnel %s failed: %s'% (self.name, output))

    def _set_mtu(self):
        c = 'ip link set %s mtu %d' % (self.name, self.mtu)
        rc, output = self._cmd(c)
        if rc != 0:
            raise Exception('cmd `%s` error: %s' % (c, output))

    def _del_dev(self):
        if self._exists():
            c = 'ip tuntap del dev %s mode %s' % (self.name, self.mode)
            rc, output = self._cmd(c)
            if rc != 0:
                raise Exception('cmd `%s` error: %s' % (c, output))

    def add(self):
        self._add_dev()
        self._set_mtu()
        if self.IPv4:
            self._add_ipv4()
        if self.IPv6:
            self._add_ipv6()

    def delete(self):
        self._del_dev()

    def open(self):
        if not self._exists():
            raise Exception('device not exists %s' % self.name)

        if self.mode == 'tap':
            ifr = struct.pack('16sH', str.encode(self.name), Arch.IFF_TAP | Arch.IFF_NO_PI)
        elif self.mode == 'tun':
            ifr = struct.pack('16sH', str.encode(self.name), Arch.IFF_TUN | Arch.IFF_NO_PI)
        else:
            raise Exception('mode not supported: %s' % self.mode)

        tun_fd = open('/dev/net/tun', mode='r+b', buffering=0)

        fcntl.ioctl(tun_fd, Arch.TUNSETIFF, ifr)
        print('tun_open: open %s %s' % (self.mode, self.name))
        return tun_fd


def _test_main():
    pass


if __name__ == '__main__':
    _test_main()
