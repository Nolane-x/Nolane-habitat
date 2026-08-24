import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.verify_reproducible_build import verify_reproducible_build


class ReproducibleBuildTests(unittest.TestCase):
    @staticmethod
    def _write_build(directory: Path, *, wheel: bytes = b"wheel", sdist: bytes = b"sdist") -> None:
        directory.mkdir()
        (directory / "nolane_habitat-0.1.0a20-py3-none-any.whl").write_bytes(wheel)
        (directory / "nolane_habitat-0.1.0a20.tar.gz").write_bytes(sdist)

    def test_report_binds_two_identical_builds_to_one_candidate(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            first = root / "first"
            second = root / "second"
            self._write_build(first)
            self._write_build(second)

            report = verify_reproducible_build(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                first=first,
                second=second,
            )

            self.assertEqual("passed", report["status"])
            self.assertEqual([], report["failures"])
            self.assertEqual(report["builds"]["first"], report["builds"]["second"])
            self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_a_nonreproducible_artifact_hash(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            first = root / "first"
            second = root / "second"
            self._write_build(first)
            self._write_build(second, wheel=b"different-wheel")

            report = verify_reproducible_build(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                first=first,
                second=second,
            )

            self.assertEqual("failed", report["status"])
            self.assertIn("wheel:sha256-mismatch", report["failures"])


if __name__ == "__main__":
    unittest.main()
