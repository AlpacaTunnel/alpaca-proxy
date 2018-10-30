#!/usr/bin/env python3

# Control message over websocks text stream, in json format.

# Author: twitter.com/alpacatunnel


import json


class CtrlMsgError(Exception):
    pass


class CtrlMsg():
    """
    A json str.

    request_dict = {
        'msg_type': 'request',
        'stream_id': stream_id,
        'address_type': address_type,
        'dst_addr': dst_addr,
        'dst_port': dst_port
    }

    response_dict = {
        'msg_type': 'response',
        'stream_id': stream_id,
        'result': result,
    }

    """

    TYPE_REQUEST = 'request'  # socks5 request
    TYPE_RESPONSE = 'response'  # socks5 response
    TYPE_CHARGE = 'cryptocoin'  # crypto pay method and charge
    TYPE_SIGNATURE = 'signature'  # sign a message to prove client_account ownership
    TYPE_BALANCE = 'balance'

    REASON_ACCOUNT_NOT_VERIFIED = 'crypto coin client_account not verified'
    REASON_NEGATIVE_BALANCE = 'negative balance'

    def __init__(self, msg_type=None, stream_id=None,
            address_type=None, dst_addr=None, dst_port=None,
            result=None, reason=None,
            coin=None, server_account=None, price_kilo_requests=None, price_gigabytes=None,
            client_account=None, timestamped_msg=None, signature=None,
            balance=None, total_pay=None, total_spend=None, total_requests=None, total_bytes=None,
            padding=None):

        self.msg_type       = msg_type
        self.stream_id      = stream_id

        self.address_type   = address_type
        self.dst_addr       = dst_addr
        self.dst_port       = dst_port

        self.result     = result  # True or False for response
        self.reason     = reason  # if result == False, return socks5 fail reason

        self.coin                   = coin
        self.server_account         = server_account
        self.price_kilo_requests    = price_kilo_requests
        self.price_gigabytes        = price_gigabytes

        self.client_account     = client_account
        self.timestamped_msg    = timestamped_msg
        self.signature          = signature

        self.balance            = balance
        self.total_pay          = total_pay
        self.total_spend        = total_spend
        self.total_requests     = total_requests
        self.total_bytes        = total_bytes

        self.padding = padding # may used to change the string length

    def __str__(self):
        return self.to_str()

    def __repr__(self):
        return self.to_str()

    def _validate(self):
        if self.msg_type not in (
                self.TYPE_REQUEST, self.TYPE_RESPONSE,
                self.TYPE_CHARGE, self.TYPE_SIGNATURE, self.TYPE_BALANCE):
            raise CtrlMsgError(
                'msg_type must be one of request/response/cryptocoin: {}'.format(self.msg_type))

        if not isinstance(self.stream_id, int) or self.stream_id < 1:
            raise CtrlMsgError('stream_id must be a positive integer: {}'.format(self.stream_id))

        if self.msg_type == self.TYPE_REQUEST:
            if None in (self.address_type, self.dst_addr, self.dst_port):
                raise CtrlMsgError('request must have address_type/dst_addr/dst_port')

        if self.msg_type == self.TYPE_RESPONSE:
            if self.result not in (True, False):
                raise CtrlMsgError('response must have a result of True or False')

        if self.msg_type == self.TYPE_CHARGE:
            if None in (self.coin, self.price_kilo_requests, self.price_gigabytes):
                raise CtrlMsgError(
                    'cryptocoin must have coin/server_account/price_kilo_requests/price_gigabytes')

        if self.msg_type == self.TYPE_SIGNATURE:
            if None in (self.client_account, self.timestamped_msg, self.signature):
                raise CtrlMsgError('signature must have client_account/timestamped_msg/signature')

        if self.msg_type == self.TYPE_BALANCE:
            if None in (self.balance, self.total_pay,
                    self.total_spend, self.total_requests, self.total_bytes):
                raise CtrlMsgError('balance message must have balance')

    def to_str(self):
        self._validate()

        if self.msg_type == self.TYPE_REQUEST:
            ctrl_dict = {
                'address_type'  : self.address_type,
                'dst_addr'      : self.dst_addr,
                'dst_port'      : self.dst_port,
            }

        elif self.msg_type == self.TYPE_RESPONSE:
            ctrl_dict = {
                'result'    : self.result,
                'reason'    : self.reason,
            }

        elif self.msg_type == self.TYPE_CHARGE:
            ctrl_dict = {
                'coin'                  : self.coin,
                'server_account'        : self.server_account,
                'price_kilo_requests'   : self.price_kilo_requests,
                'price_gigabytes'       : self.price_gigabytes,
            }

        elif self.msg_type == self.TYPE_SIGNATURE:
            ctrl_dict = {
                'client_account'    : self.client_account,
                'timestamped_msg'   : self.timestamped_msg,
                'signature'         : self.signature,
            }

        elif self.msg_type == self.TYPE_BALANCE:
            ctrl_dict = {
                'balance'           : self.balance,
                'total_pay'         : self.total_pay,
                'total_spend'       : self.total_spend,
                'total_requests'    : self.total_requests,
                'total_bytes'       : self.total_bytes,
            }

        ctrl_dict['msg_type']   = self.msg_type
        ctrl_dict['stream_id']  = self.stream_id
        ctrl_dict['padding']    = self.padding

        return json.dumps(ctrl_dict)

    def from_str(self, ctrl_str):
        ctrl_dict = json.loads(ctrl_str)

        self.msg_type       = ctrl_dict.get('msg_type')
        self.stream_id      = ctrl_dict.get('stream_id')

        self.address_type   = ctrl_dict.get('address_type')
        self.dst_addr       = ctrl_dict.get('dst_addr')
        self.dst_port       = ctrl_dict.get('dst_port')

        self.result     = ctrl_dict.get('result')
        self.reason     = ctrl_dict.get('reason')

        self.coin                   = ctrl_dict.get('coin')
        self.server_account         = ctrl_dict.get('server_account')
        self.price_kilo_requests    = ctrl_dict.get('price_kilo_requests')
        self.price_gigabytes        = ctrl_dict.get('price_gigabytes')

        self.client_account     = ctrl_dict.get('client_account')
        self.timestamped_msg    = ctrl_dict.get('timestamped_msg')
        self.signature          = ctrl_dict.get('signature')

        self.balance            = ctrl_dict.get('balance')
        self.total_pay          = ctrl_dict.get('total_pay')
        self.total_spend        = ctrl_dict.get('total_spend')
        self.total_requests     = ctrl_dict.get('total_requests')
        self.total_bytes        = ctrl_dict.get('total_bytes')

        self._validate()
