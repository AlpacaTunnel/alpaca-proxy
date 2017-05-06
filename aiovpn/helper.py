#!/usr/bin/env python3

import platform
import subprocess
import ipaddress
import re
import time
import os
import socket
import threading
import multiprocessing
import struct
import fcntl


def byte2int(b):
    return int.from_bytes(b, byteorder='big')


def int2byte(i):
    return i.to_bytes(4, 'big')


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


class Command():
    """
    Run a cmd and wait it to terminate by itself or be terminated by a thread.
    """

    def __init__(self, cmd=None):
        self.child = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, shell=False)
    
    def wait(self, split=False, realtime_print=True, collect_output=True):
        stream = ''

        while self.child.poll() is None:
            line = self.child.stdout.readline()

            if realtime_print:
                print(line)
                sys.stdout.flush()
            
            if collect_output:
                stream += line
    
        stream += self.child.communicate()[0]
    
        rc = self.child.returncode
    
        if split:
            data = (stream.split('\n'))
        else:
            data = stream
    
        return (rc, data)

    def terminate(self):
        self.child.send_signal(signal.SIGTERM)


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

    def _cmd(self, c, split=False):
        cmd = Command(c)
        return cmd.wait(split=split, realtime_print=False, collect_output=True)
    
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


class TunSocketForwarder(multiprocessing.Process):
    """
    Forward packets between the tuntap and unix socket.
    Both multiprocessing.Process and threading.Thread are OK here.

    Tuntap reading is blocking-file-IO, and asyncio can not handle this IO.
    One way is to await in a ThreadPoolExecutor, this is how aiofiles works.
    But for each packet, there is a ThreadPoolExecutor call, and it's really slow.
    Asyncio can handle unix socket, so I use a Thread/Process to read tuntap,
    and forward packets to unix socket, it's 10 times fatster than aiofiles.
    """

    def __init__(self, unix_path, tun_name):
        super(TunSocketForwarder, self).__init__()
        self.unix_path = unix_path
        self.tun_name = tun_name

    def run(self):
        tun = self.tun_open()
        socket = self.stream_accept()

        s2t = Socket2Tun(socket, tun)
        t2s = Tun2Socket(socket, tun)

        s2t.start()
        t2s.start()

        while True:
            time.sleep(1000)

    def tun_open(self):
        name = self.tun_name
        mode = 'tap'

        if mode == 'tap':
            ifr = struct.pack('16sH', str.encode(name), Arch.IFF_TAP | Arch.IFF_NO_PI)
        elif mode == 'tun':
            ifr = struct.pack('16sH', str.encode(name), Arch.IFF_TUN | Arch.IFF_NO_PI)
        else:
            raise Exception('mode not supported: %s' % mode)

        tun = open('/dev/net/tun', mode='r+b', buffering=0)

        fcntl.ioctl(tun, Arch.TUNSETIFF, ifr)
        print('tun_open: open %s %s' % (mode, name))
        return tun

    def stream_accept(self):
        path = self.unix_path
        if os.path.exists(path):
            os.remove(path)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)

        server.listen()
        print("stream_accept: listening unix socket...")

        client, client_address = server.accept()

        print("stream_accept: accepted unix socket")

        return client


class Socket2Tun(threading.Thread):
    """
    get packets from unix socket and write to tuntap
    """

    def __init__(self, socket, tun):
        threading.Thread.__init__(self)
        self.socket = socket
        self.tun = tun

    def run(self):
        print ("started thread Socket2Tun")

        while True:

            packet = self.recv_pkt()
            self.tun.write(packet)

    def recv_pkt(self):
        len_mark = self.recvexactly(4)
        pkt_len = byte2int(len_mark)
        pkt = self.recvexactly(pkt_len)
        return pkt

    def recvexactly(self, n):
        total = b''
        left = n
        while True:

            current = self.socket.recv(left)

            if not current:
                raise Exception('IncompleteReadError')
            else:
                total += current

            if len(total) == n:
                break
            else:
                left -= len(current)

        return total


class Tun2Socket(threading.Thread):
    """
    read packets from tuntap and send to unix socket
    """

    def __init__(self, socket, tun):
        threading.Thread.__init__(self)
        self.socket = socket
        self.tun = tun

    def run(self):
        print ("started thread Tun2Socket")

        while True:

            packet = self.tun.read(2048)
            pkt_len = len(packet)
            self.socket.send(int2byte(pkt_len))
            self.socket.send(packet)

