import io
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from habitat.semantic import ts_language_service


class _StuckInput:
    def write(self, _value):
        return 0

    def flush(self):
        return None

    def close(self):
        return None


class _DelayedEmptyOutput:
    def __init__(self, delay: float):
        self.delay = delay
        self.closed = False

    def readline(self):
        time.sleep(self.delay)
        return ""

    def close(self):
        self.closed = True


class _StuckProcess:
    def __init__(self, delay: float):
        self.stdin = _StuckInput()
        self.stdout = _DelayedEmptyOutput(delay)
        self.stderr = io.StringIO()
        self.pid = 12345
        self.killed = False

    def poll(self):
        return 1 if self.killed else None

    def wait(self, timeout):
        if not self.killed:
            raise subprocess.TimeoutExpired("node", timeout)
        return 1

    def kill(self):
        self.killed = True


class TypeScriptLanguageServiceTests(unittest.TestCase):
    def test_unresponsive_service_times_out_and_is_closed(self):
        process = _StuckProcess(delay=0.15)
        service = ts_language_service.TypeScriptLanguageServiceProcess.__new__(
            ts_language_service.TypeScriptLanguageServiceProcess
        )
        service.root = Path.cwd()
        service._lock = threading.Lock()
        service._closed = False
        service.proc = process
        service.last_result = {}

        with patch.object(ts_language_service, "TS_SERVICE_RESPONSE_TIMEOUT_S", 0.02, create=True):
            started = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                service.analyze([], [], [])

        self.assertLess(time.monotonic() - started, 0.1)
        self.assertTrue(service._closed)
        self.assertTrue(process.killed)


if __name__ == "__main__":
    unittest.main()
