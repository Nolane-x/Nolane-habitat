import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.verify_distribution import verify_distribution


class DistributionVerifierTests(unittest.TestCase):
    def test_report_binds_matching_wheel_and_sdist_to_candidate(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            dist = root / "dist"
            dist.mkdir()
            wheel = dist / "nolane_habitat-0.1.0a20-py3-none-any.whl"
            sdist = dist / "nolane_habitat-0.1.0a20.tar.gz"
            wheel.write_bytes(b"wheel")
            sdist.write_bytes(b"sdist")

            report = verify_distribution(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                dist=dist,
                smoke_import=lambda path, expected: path == wheel and expected == "0.1.0-alpha.20",
            )

            self.assertEqual("passed", report["status"])
            self.assertEqual("a" * 40, report["source_commit"])
            self.assertEqual(
                hashlib.sha256(b"wheel").hexdigest(), report["artifacts"][0]["sha256"]
            )
            self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_fails_closed_when_the_expected_sdist_is_missing(self):
        with TemporaryDirectory() as td:
            dist = Path(td)
            (dist / "nolane_habitat-0.1.0a20-py3-none-any.whl").write_bytes(b"wheel")

            report = verify_distribution(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                dist=dist,
                smoke_import=lambda *_: True,
            )

            self.assertEqual("failed", report["status"])
            self.assertIn("sdist:missing", report["failures"])


if __name__ == "__main__":
    unittest.main()
