# encoding: utf-8
#
#    Copyright (c) 2011-2013 Anton Tyurin <noxiouz@yandex.ru>
#    Copyright (c) 2011-2013 Other contributors as noted in the AUTHORS file.
#
#    This file is part of Cocaine.
#
#    Cocaine is free software; you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    Cocaine is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>. 
#

import array
from threading import Lock

import msgpack

MAX_BUFF_SIZE = 104857600
START_CHUNK_SIZE = 10240

def encode_dec(f):
    def wrapper(self, data):
        encode = msgpack.packb(data)
        return f(self, encode, len(encode))
    return wrapper

class Decoder(object):

    def __init__(self):
        self.callback = None

    def bind(self, callback):
        assert callable(callback)
        self.callback = callback

    def decode(self, buffer):
        """
         buffer is msgpack.Unpacker (stream unpacker)
        """
        try:
            for res in buffer: # if not enough data - 0 iterations
                self.callback(res)
        except Exception as err:
            pass # hook - view later


class ReadableStream(object):

    def __init__(self, loop, pipe):
        self.loop = loop
        self.pipe = pipe

        self.callback = None
        self.is_attached = False

        self.buffer = msgpack.Unpacker()
        self.tmp_buff = array.array('c','\0' * START_CHUNK_SIZE)
        self.mutex = Lock()

    def bind(self, callback):
        assert callable(callback)
        self.callback = callback
        self.is_attached = self.loop.register_read_event(self._on_event, self.pipe.fileno())

    def unbind(self):
        self.callback = None
        if self.is_attached:
            self.loop.unregister_read_event(self.pipe.fileno())

    def _on_event(self):
        with self.mutex:
            # Bad solution. On python 2.7 and higher - use memoryview and bytearray
            length = self.pipe.read(self.tmp_buff, self.tmp_buff.buffer_info()[1])

            if length <= 0:
                if length == 0: #Remote side has closed connection
                    self.loop.unregister_read_event(self.pipe.fileno())
                return

            self.buffer.feed(self.tmp_buff[:length])
            self.callback(self.buffer)

            # Enlarge buffer if messages are big
            if self.tmp_buff.buffer_info()[1] == length:
                self.tmp_buff *= 2


class WritableStream(object):

    def __init__(self, loop, pipe):
        self.loop = loop
        self.pipe = pipe
        self.is_attached = False

        self.mutex = Lock()

        self.ring = bytearray()
        self.wr_offset = 0
        self.tx_offset = 0

    def _on_event(self):
        with self.mutex:

            if self.wr_offset == self.tx_offset and self.is_attached:
                self.loop.unregister_write_event(self.pipe.fileno())
                self.is_attached = False
                return

            unsent = self.wr_offset - self.tx_offset

            sent = self.pipe.write(self.ring[self.tx_offset : self.tx_offset + unsent])

            if sent > 0:
                self.tx_offset += sent

    @encode_dec
    def write(self, data, size):
        with self.mutex:
            if self.wr_offset == self.tx_offset:
                sent = self.pipe.write(data)

                if sent >= 0:
                    if sent == size:
                        return

                    size -= sent


            if len(self.ring) > MAX_BUFF_SIZE:
                unsent = self.wr_offset - self.tx_offset
                self.ring = self.ring[self.tx_offset : self.tx_offset + unsent]
                self.rd_offset = unsent
                self.rx_offset = 0


            self.wr_offset += size
            self.ring.extend(data[sent:])


            if not self.is_attached:
                self.loop.register_write_event(self._on_event, self.pipe.fileno())
                self.is_attached = True
