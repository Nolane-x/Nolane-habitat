import hashlib
import io
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from tools.verify_distribution import verify_distribution


class DistributionVerifierTests(unittest.TestCase):
    @staticmethod
    def _write_artifacts(dist: Path, *, include_secret: bool = False) -> tuple[Path, Path]:
        wheel = dist / "nolane_habitat-0.1.0a20-py3-none-any.whl"
        sdist = dist / "nolane_habitat-0.1.0a20.tar.gz"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("habitat/__init__.py", '__version__ = "0.1.0-alpha.20"\n')
            if include_secret:
                archive.writestr(".env", "TOKEN=not-for-release\n")
        with tarfile.open(sdist, "w:gz") as archive:
            payload = b"# Nolane Habitat\n"
            member = tarfile.TarInfo("nolane_habitat-0.1.0a20/README.md")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        return wheel, sdist

    def test_report_binds_matching_wheel_and_sdist_to_candidate(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            dist = root / "dist"
            dist.mkdir()
            wheel, sdist = self._write_artifacts(dist)

            report = verify_distribution(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                dist=dist,
                smoke_import=lambda path, expected: path == wheel and expected == "0.1.0-alpha.20",
            )

            self.assertEqual("passed", report["status"])
            self.assertEqual("a" * 40, report["source_commit"])
            self.assertEqual(
                hashlib.sha256(wheel.read_bytes()).hexdigest(), report["artifacts"][0]["sha256"]
            )
            self.assertRegex(report["member_manifest_sha256"], r"^[0-9a-f]{64}$")
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

    def test_report_rejects_secret_bearing_package_members(self):
        with TemporaryDirectory() as td:
            dist = Path(td)
            self._write_artifacts(dist, include_secret=True)

            report = verify_distribution(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                dist=dist,
                smoke_import=lambda *_: True,
            )

            self.assertEqual("failed", report["status"])
            self.assertIn("wheel:forbidden-member:.env", report["failures"])


if __name__ == "__main__":
    unittest.main()
