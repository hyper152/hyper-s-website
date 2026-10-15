"""Bounded decoding of HTTP/1.1 chunked request bodies."""

import re


class RequestBodyError(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


_TOKEN = rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
_QUOTED = rb'"(?:[\x09\x20\x21\x23-\x5b\x5d-\x7e\x80-\xff]|\\[\x09\x20-\x7e\x80-\xff])*"'
_CHUNK_HEADER = re.compile(
    rb'([0-9A-Fa-f]+)(?:[ \t]*;[ \t]*' + _TOKEN +
    rb'(?:[ \t]*=[ \t]*(?:' + _TOKEN + rb'|' + _QUOTED + rb'))?)*'
)
_TRAILER = re.compile(_TOKEN + rb':[\x09\x20-\x7e\x80-\xff]*')


def read_chunked_body(stream, max_size, *, max_line_size=8192, max_framing_size=65536):
    """Decode one body, validating framing and discarding untrusted trailers."""
    body = bytearray()
    framing_size = 0

    def read_line():
        nonlocal framing_size
        line = stream.readline(max_line_size + 1)
        framing_size += len(line)
        if len(line) > max_line_size or framing_size > max_framing_size:
            raise RequestBodyError(413, '分块请求的附加信息超过大小限制')
        if not line.endswith(b'\r\n'):
            raise RequestBodyError(400, '分块请求不完整或行结束符无效')
        return line[:-2]

    while True:
        header = _CHUNK_HEADER.fullmatch(read_line())
        if header is None:
            raise RequestBodyError(400, '分块请求的长度或扩展格式无效')
        size_text = header[1].lstrip(b'0') or b'0'
        remaining = max_size - len(body)
        if len(size_text) > len(format(remaining, 'x')):
            raise RequestBodyError(413, '请求体超过大小限制')
        size = int(size_text, 16)
        if size > remaining:
            raise RequestBodyError(413, '请求体超过大小限制')
        if size == 0:
            while True:
                trailer = read_line()
                if not trailer:
                    return bytes(body)
                if _TRAILER.fullmatch(trailer) is None:
                    raise RequestBodyError(400, '分块请求的尾部字段格式无效')
                # Never merge trailers into headers, particularly auth or length fields.
        chunk = stream.read(size)
        if len(chunk) != size or stream.read(2) != b'\r\n':
            raise RequestBodyError(400, '分块请求不完整或数据结束符无效')
        body.extend(chunk)
        framing_size += 2
        if framing_size > max_framing_size:
            raise RequestBodyError(413, '分块请求的附加信息超过大小限制')
