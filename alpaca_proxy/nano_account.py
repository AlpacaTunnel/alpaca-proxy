#!/usr/bin/env python3


# This file was mainly copied from https://github.com/dourvaris/nano-python/tree/master/nano
# Because pip installed version does not include generate_account yet, so I copy them here.
# The code of nano-python is licensed under MIT License.


import struct
from pyblake2 import blake2b
from base64 import b32encode, b32decode

from .ed25519_blake2 import publickey_unsafe, signature_unsafe, checkvalid


maketrans = hasattr(bytes, 'maketrans') and bytes.maketrans or string.maketrans
B32_ALPHABET = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
XRB_ALPHABET = b'13456789abcdefghijkmnopqrstuwxyz'
XRB_ENCODE_TRANS = maketrans(B32_ALPHABET, XRB_ALPHABET)
XRB_DECODE_TRANS = maketrans(XRB_ALPHABET, B32_ALPHABET)


def address_checksum(address):
    """
    Returns the checksum in bytes for an address in bytes
    """
    address_bytes = address
    h = blake2b(digest_size=5)
    h.update(address_bytes)
    checksum = bytearray(h.digest())
    checksum.reverse()
    return checksum


def b32xrb_encode(value):
    """
    Encodes bytes to xrb encoding which uses the base32 algorithm
    with a custom alphabet: '13456789abcdefghijkmnopqrstuwxyz'
    :param value: the value to encode
    :type: bytes
    :return: encoded value
    :rtype: bytes
    >>> b32xrb_encode(b'deadbeef')
    b'ejkp4s54eokpe==='
    """
    return b32encode(value).translate(XRB_ENCODE_TRANS)


def b32xrb_decode(value):
    """
    Decodes a value in xrb encoding to bytes using base32 algorithm
    with a custom alphabet: '13456789abcdefghijkmnopqrstuwxyz'
    :param value: the value to decode
    :type: bytes
    :return: decoded value
    :rtype: bytes
    >>> b32xrb_decode(b'fxop4ya=')
    b'okay'
    """
    return b32decode(value.translate(XRB_DECODE_TRANS))


def public_key_to_xrb_address(public_key):
    """
    Convert `public_key` (bytes) to an xrb address
    >>> public_key_to_xrb_address(b'00000000000000000000000000000000')
    'xrb_1e3i81r51e3i81r51e3i81r51e3i81r51e3i81r51e3i81r51e3imxssakuq'
    :param public_key: public key in bytes
    :type public_key: bytes
    :return: xrb address
    :rtype: str
    """

    if not len(public_key) == 32:
        raise ValueError('public key must be 32 chars')

    padded = b'000' + public_key
    address = b32xrb_encode(padded)[4:]
    checksum = b32xrb_encode(address_checksum(public_key))
    return 'xrb_' + address.decode('ascii') + checksum.decode('ascii')


def xrb_address_to_public_key(address):
    """
    Convert an xrb address to public key in bytes
    >>> xrb_address_to_public_key('xrb_1e3i81r51e3i81r51e3i81r51e3i'\
                                  '81r51e3i81r51e3i81r51e3imxssakuq')
    b'00000000000000000000000000000000'
    :param address: xrb address
    :type address: bytes
    :return: public key in bytes
    :rtype: bytes
    :raises ValueError:
    """

    address = bytearray(address, 'ascii')

    if not address.startswith(b'xrb_'):
        raise ValueError('address does not start with xrb_: %s' % address)

    if len(address) != 64:
        raise ValueError('address must be 64 chars long: %s' % address)

    address = bytes(address)
    key_b32xrb = b'1111' + address[4:56]
    key_bytes = b32xrb_decode(key_b32xrb)[3:]
    checksum = address[56:]

    if b32xrb_encode(address_checksum(key_bytes)) != checksum:
        raise ValueError('invalid address, invalid checksum: %s' % address)

    return key_bytes


def seed_to_keypair(seed, index=0):
    """
    Generates a deterministic keypair from `seed` based on `index`
    :param seed: bytes value of seed
    :type seed: bytes
    :param index: offset from seed
    :type index: int
    :return: (private_key, public_key)
    """

    h = blake2b(digest_size=32)
    h.update(seed + struct.pack(">L", index))
    private_key = h.digest()
    public_key = publickey_unsafe(private_key)
    return (private_key, public_key)


class NanoAccountError(Exception):
    pass


class Account():

    def __init__(self, seed=None, index=0, private_key=None, public_key=None, xrb_account=None):
        """
        All parameters should be hex strings.

        priority: seed > private_key > public_key > xrb_account
        meaning: if given seed, use seed to generate all other properties.
                 if no seed, but given private_key, use private_key to generate public_key and xrb_account.
                 etc.
        """
        self.seed = seed
        self.private_key = private_key
        self.public_key = public_key
        self.xrb_account = xrb_account

        if seed:
            assert len(seed) == 64
            self.seed = bytes.fromhex(seed)
            self.private_key, self.public_key = seed_to_keypair(self.seed, index)
            self.xrb_account = public_key_to_xrb_address(self.public_key)
        elif private_key:
            self.private_key = bytes.fromhex(private_key)
            self.public_key = publickey_unsafe(self.private_key)
            self.xrb_account = public_key_to_xrb_address(self.public_key)
        elif public_key:
            self.public_key = bytes.fromhex(public_key)
            self.xrb_account = public_key_to_xrb_address(self.public_key)
        elif xrb_account:
            self.public_key = xrb_address_to_public_key(xrb_account)

    def sign(self, data):
        """
        sign binary data with private key.
        """
        if not self.private_key:
            raise NanoAccountError('can not sign without private_key')

        if not isinstance(data, bytes):
            raise NanoAccountError('can only sign binary data')

        return signature_unsafe(data, self.private_key, self.public_key)

    def verify(self, data, signature):
        """
        verify binary data and signature with public key.
        """
        if not isinstance(data, bytes):
            raise NanoAccountError('can only verify binary data')

        try:
            signature = bytes.fromhex(signature)
            checkvalid(signature, data, self.public_key)
            return True
        except Exception as _e:
            return False
