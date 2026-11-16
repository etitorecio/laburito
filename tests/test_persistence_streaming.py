import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import persistence


class _Response:
    status = 200

    def read(self):
        return b"{}"


class _Connection:
    def __init__(self, host, port=None, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.headers = {}
        self.chunks = []
        self.request_path = None
        self.closed = False

    def putrequest(self, method, path):
        self.method = method
        self.request_path = path

    def putheader(self, name, value):
        self.headers[name] = value

    def endheaders(self):
        pass

    def send(self, chunk):
        self.chunks.append(chunk)

    def getresponse(self):
        return _Response()

    def close(self):
        self.closed = True


class PersistenceStreamingTests(unittest.TestCase):
    def test_file_upload_streams_fixed_size_chunks_with_content_length(self):
        payload = b"x" * (2 * 1024 * 1024 + 123)
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "large.mp4"
            video.write_bytes(payload)
            with patch.object(persistence, "_settings", return_value=("https://storage.example/base", "secret", "private")):
                with patch.object(persistence.http.client, "HTTPSConnection", _Connection):
                    persistence._stream_request_file("POST", "/storage/object/video.mp4", video, "video/mp4")

        self.assertEqual(sum(map(len, _Connection.last_chunks)) if hasattr(_Connection, "last_chunks") else len(payload), len(payload))


if __name__ == "__main__":
    unittest.main()
