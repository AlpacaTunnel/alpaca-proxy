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

    def __init__(self, msg_type=None, stream_id=None, address_type=None, dst_addr=None, dst_port=None, result=None, padding=None):
        self.msg_type       = msg_type
        self.stream_id      = stream_id
        self.address_type   = address_type
        self.dst_addr       = dst_addr
        self.dst_port       = dst_port
        self.result         = result  # True or False for response
        self.padding        = padding # may used to change the string length

    def __str__(self):
        return self.to_str()

    def __repr__(self):
        return self.to_str()

    def _validate(self):
        if self.msg_type not in ('request', 'response'):
            raise CtrlMsgError('msg_type must be one of request/response: {}'.format(self.msg_type))

        if not isinstance(self.stream_id, int) or self.stream_id < 1:
            raise CtrlMsgError('stream_id must be a positive integer: {}'.format(self.stream_id))

        if self.msg_type == 'request':
            if None in (self.address_type, self.dst_addr, self.dst_port):
                raise CtrlMsgError('request must have address_type/dst_addr/dst_port')

        if self.msg_type == 'response':
            if self.result not in (True, False):
                raise CtrlMsgError('response must have a result of True or False')

    def to_str(self):
        self._validate()

        if self.msg_type == 'request':
            ctrl_dict = {
                'msg_type'      : self.msg_type,
                'stream_id'     : self.stream_id,
                'address_type'  : self.address_type,
                'dst_addr'      : self.dst_addr,
                'dst_port'      : self.dst_port,
                'padding'       : self.padding,
            }

        elif self.msg_type == 'response':
            ctrl_dict = {
                'msg_type'      : self.msg_type,
                'stream_id'     : self.stream_id,
                'result'        : self.result,
                'padding'       : self.padding,
            }

        return json.dumps(ctrl_dict)

    def from_str(self, ctrl_str):
        ctrl_dict = json.loads(ctrl_str)

        self.msg_type       = ctrl_dict.get('msg_type')
        self.stream_id      = ctrl_dict.get('stream_id')
        self.address_type   = ctrl_dict.get('address_type')
        self.dst_addr       = ctrl_dict.get('dst_addr')
        self.dst_port       = ctrl_dict.get('dst_port')
        self.result         = ctrl_dict.get('result')

        self._validate()
