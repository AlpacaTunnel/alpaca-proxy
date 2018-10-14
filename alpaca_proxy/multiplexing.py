#!/usr/bin/env python3

# Bidirectional multiplexing channel/stream over websocks.

# Author: twitter.com/alpacatunnel


def byte2int(b):
    return int.from_bytes(b, byteorder='big')


def int2byte(i):
    return i.to_bytes(4, 'big')


class Multiplexing():
    """
    No io involved. Only parse binary data.

    Because websocks already handles payload length, so there's no need to add length field here.
    Only insert 4 bytes stream ID. Format is: 4-bytes-stream-id + data.

    Like HTTP2, client-initiated streams have odd-numbered stream IDs.
    """

    def __init__(self, role='client'):
        if role == 'client':
            self._max_id = 1
        else:
            self._max_id = 2
        self._alive_ids = set()

    def new_stream(self):
        # TODO: recycle id when reach max 4 bytes
        new_id = self._max_id
        self._alive_ids.add(new_id)
        self._max_id += 2
        return new_id

    def del_stream(self, stream_id):
        self._alive_ids.discard(stream_id)

    def send(self, stream_id, data):
        if not data:
            data = b''
        id_bytes = int2byte(stream_id)
        return id_bytes + data

    def receive(self, data):
        stream_id = byte2int(data[0:4])
        return stream_id, data[4:]


def _test_main():
    pass


if __name__ == '__main__':
    _test_main()
