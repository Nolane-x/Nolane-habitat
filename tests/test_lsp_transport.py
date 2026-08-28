from __future__ import annotations

import unittest


class LspTransportTests(unittest.TestCase):
    def test_decoder_handles_fragmented_header_and_body(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, encode_lsp_message

        payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        wire = encode_lsp_message(payload)
        decoder = LspFrameDecoder()
        out = []
        for chunk in (wire[:7], wire[7:19], wire[19:31], wire[31:]):
            out.extend(decoder.feed(chunk))
        self.assertEqual(out, [payload])

    def test_decoder_handles_multiple_frames_in_one_feed(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, encode_lsp_message

        first = {"jsonrpc": "2.0", "id": 1, "result": 1}
        second = {
            "jsonrpc": "2.0",
            "method": "window/logMessage",
            "params": {"type": 3},
        }
        decoder = LspFrameDecoder()
        self.assertEqual(
            decoder.feed(encode_lsp_message(first) + encode_lsp_message(second)),
            [first, second],
        )

    def test_encode_rejects_non_object_message(self):
        from habitat.semantic.lsp_transport import encode_lsp_message

        with self.assertRaises(TypeError):
            encode_lsp_message([])

    def test_decoder_rejects_missing_content_length(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError

        with self.assertRaises(LspProtocolError):
            LspFrameDecoder().feed(b"Content-Type: application/json\r\n\r\n{}")

    def test_decoder_rejects_duplicate_content_length(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError

        with self.assertRaises(LspProtocolError):
            LspFrameDecoder().feed(
                b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}"
            )

    def test_decoder_rejects_oversized_body_before_body_arrives(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError

        with self.assertRaises(LspProtocolError):
            LspFrameDecoder(max_body_bytes=32).feed(b"Content-Length: 100\r\n\r\n")

    def test_decoder_rejects_invalid_utf8(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError

        with self.assertRaises(LspProtocolError):
            LspFrameDecoder().feed(b"Content-Length: 1\r\n\r\n\xff")

    def test_decoder_rejects_non_object_json(self):
        from habitat.semantic.lsp_transport import LspFrameDecoder, LspProtocolError

        with self.assertRaises(LspProtocolError):
            LspFrameDecoder().feed(b"Content-Length: 2\r\n\r\n[]")


if __name__ == "__main__":
    unittest.main()
