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
    TYPE_CHARGE = 'cryptopay'  # crypto pay method and charge
    TYPE_SIGNATURE = 'signature'  # sign a message to prove account ownership

    def __init__(self, msg_type=None, stream_id=None,
            address_type=None, dst_addr=None, dst_port=None,
            result=None, reason=None,
            coin=None, cost_per_request=None, cost_per_byte=None,
            account=None, timestamped_msg=None, signature=None,
            padding=None):

        self.msg_type           = msg_type
        self.stream_id          = stream_id

        self.address_type       = address_type
        self.dst_addr           = dst_addr
        self.dst_port           = dst_port

        self.result             = result  # True or False for response
        self.reason             = reason  # if result == False, return socks5 fail reason

        self.coin               = coin
        self.cost_per_request   = cost_per_request
        self.cost_per_byte      = cost_per_byte

        self.account            = account
        self.timestamped_msg    = timestamped_msg
        self.signature          = signature

        self.account            = account
        self.padding            = padding # may used to change the string length

    def __str__(self):
        return self.to_str()

    def __repr__(self):
        return self.to_str()

    def _validate(self):
        if self.msg_type not in (self.TYPE_REQUEST, self.TYPE_RESPONSE, self.TYPE_CHARGE, self.TYPE_SIGNATURE):
            raise CtrlMsgError('msg_type must be one of request/response/cryptopay: {}'.format(self.msg_type))

        if not isinstance(self.stream_id, int) or self.stream_id < 1:
            raise CtrlMsgError('stream_id must be a positive integer: {}'.format(self.stream_id))

        if self.msg_type == self.TYPE_REQUEST:
            if None in (self.address_type, self.dst_addr, self.dst_port):
                raise CtrlMsgError('request must have address_type/dst_addr/dst_port')

        if self.msg_type == self.TYPE_RESPONSE:
            if self.result not in (True, False):
                raise CtrlMsgError('response must have a result of True or False')

        if self.msg_type == self.TYPE_CHARGE:
            if None in (self.coin, self.cost_per_request, self.cost_per_byte):
                raise CtrlMsgError('cryptopay must have cost_per_request/cost_per_byte')

        if self.msg_type == self.TYPE_SIGNATURE:
            if None in (self.account, self.timestamped_msg, self.signature):
                raise CtrlMsgError('signature must have account/timestamped_msg/signature')

    def to_str(self):
        self._validate()

        if self.msg_type == self.TYPE_REQUEST:
            ctrl_dict = {
                'msg_type'      : self.msg_type,
                'stream_id'     : self.stream_id,
                'address_type'  : self.address_type,
                'dst_addr'      : self.dst_addr,
                'dst_port'      : self.dst_port,
                'padding'       : self.padding,
            }

        elif self.msg_type == self.TYPE_RESPONSE:
            ctrl_dict = {
                'msg_type'      : self.msg_type,
                'stream_id'     : self.stream_id,
                'result'        : self.result,
                'reason'        : self.reason,
                'padding'       : self.padding,
            }

        elif self.msg_type == self.TYPE_CHARGE:
            ctrl_dict = {
                'msg_type'          : self.msg_type,
                'stream_id'         : self.stream_id,
                'coin'              : self.coin,
                'cost_per_request'  : self.cost_per_request,
                'cost_per_byte'     : self.cost_per_byte,
                'padding'           : self.padding,
            }

        elif self.msg_type == self.TYPE_SIGNATURE:
            ctrl_dict = {
                'msg_type'          : self.msg_type,
                'stream_id'         : self.stream_id,
                'account'           : self.account,
                'timestamped_msg'   : self.timestamped_msg,
                'signature'         : self.signature,
                'padding'           : self.padding,
            }

        return json.dumps(ctrl_dict)

    def from_str(self, ctrl_str):
        ctrl_dict = json.loads(ctrl_str)

        self.msg_type           = ctrl_dict.get('msg_type')
        self.stream_id          = ctrl_dict.get('stream_id')

        self.address_type       = ctrl_dict.get('address_type')
        self.dst_addr           = ctrl_dict.get('dst_addr')
        self.dst_port           = ctrl_dict.get('dst_port')

        self.result             = ctrl_dict.get('result')
        self.reason             = ctrl_dict.get('reason')

        self.coin               = ctrl_dict.get('coin')
        self.cost_per_request   = ctrl_dict.get('cost_per_request')
        self.cost_per_byte      = ctrl_dict.get('cost_per_byte')

        self.account            = ctrl_dict.get('account')
        self.timestamped_msg    = ctrl_dict.get('timestamped_msg')
        self.signature          = ctrl_dict.get('signature')

        self._validate()
