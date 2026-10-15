import io
import unittest

from src.http_body import RequestBodyError, read_chunked_body


class ChunkedBodyTests(unittest.TestCase):
    def test_extensions_zero_padding_and_trailers(self):
        stream = io.BytesIO(b'0003 ; flag; hash="a\\\"b"\r\nabc\r\n00\r\nX-Note: value\r\n\r\nNEXT')
        self.assertEqual(read_chunked_body(stream, 3), b'abc')
        self.assertEqual(stream.read(), b'NEXT')

    def test_limits_chunk_lines_and_total_framing(self):
        cases = [
            (b'1;name=' + b'x' * 8192 + b'\r\n', {}),
            (b'0\r\nX-Note: abcdef\r\n\r\n', {'max_framing_size': 10}),
            (b'1\r\nx\r\n' * 10 + b'0\r\n\r\n', {'max_framing_size': 20}),
        ]
        for body, limits in cases:
            with self.subTest(limits=limits), self.assertRaises(RequestBodyError) as error:
                read_chunked_body(io.BytesIO(body), 100, **limits)
            self.assertEqual(error.exception.status, 413)

    def test_invalid_extensions_and_trailers(self):
        for body in [b'1;\r\nx\r\n0\r\n\r\n', b'1;name="unterminated\r\n',
                     b'0\r\nNo-colon\r\n\r\n', b'0\r\nX-Note: a\x00b\r\n\r\n',
                     b'0\r\n', b'0\r\n\n']:
            with self.subTest(body=body), self.assertRaises(RequestBodyError) as error:
                read_chunked_body(io.BytesIO(body), 100)
            self.assertEqual(error.exception.status, 400)


if __name__ == '__main__':
    unittest.main()
