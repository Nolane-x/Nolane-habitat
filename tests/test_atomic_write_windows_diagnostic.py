from __future__ import annotations

import os
import tempfile
import threading
import traceback
import unittest
from pathlib import Path

from habitat.source_bridge import atomic_write


@unittest.skipUnless(os.name == "nt", "Windows sharing-race diagnostic")
class AtomicWriteWindowsDiagnosticTests(unittest.TestCase):
    def test_concurrent_replace_failure_reports_exact_windows_origin(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.txt"
            path.write_bytes(b"seed")

            for round_index in range(12):
                payloads = [f"round-{round_index}-writer-{i}".encode() for i in range(24)]
                barrier = threading.Barrier(len(payloads))
                errors: list[dict] = []
                errors_lock = threading.Lock()

                def writer(data: bytes) -> None:
                    try:
                        barrier.wait(timeout=5)
                        atomic_write(path, data)
                    except Exception as exc:
                        detail = {
                            "type": type(exc).__name__,
                            "repr": repr(exc),
                            "errno": getattr(exc, "errno", None),
                            "winerror": getattr(exc, "winerror", None),
                            "filename": getattr(exc, "filename", None),
                            "filename2": getattr(exc, "filename2", None),
                            "traceback": traceback.format_exc(),
                        }
                        with errors_lock:
                            errors.append(detail)

                threads = [threading.Thread(target=writer, args=(data,)) for data in payloads]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=8)

                self.assertTrue(all(not thread.is_alive() for thread in threads), round_index)
                self.assertFalse(errors, {"round": round_index, "errors": errors})
                self.assertIn(path.read_bytes(), payloads)
                self.assertFalse(list(path.parent.glob(f".{path.name}.habitat-*.tmp")))


if __name__ == "__main__":
    unittest.main()
