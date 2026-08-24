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
    def _write_artifacts(
        dist: Path,
        *,
        include_secret: bool = False,
        sdist_requirement: str = "pathspec>=0.12,<1",
    ) -> tuple[Path, Path]:
        wheel = dist / "nolane_habitat-0.1.0a20-py3-none-any.whl"
        sdist = dist / "nolane_habitat-0.1.0a20.tar.gz"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("habitat/__init__.py", '__version__ = "0.1.0-alpha.20"\n')
            archive.writestr(
                "nolane_habitat-0.1.0a20.dist-info/METADATA",
                "Metadata-Version: 2.3\n"
                "Name: nolane-habitat\n"
                "Version: 0.1.0a20\n"
                "Requires-Dist: pathspec>=0.12,<1\n",
            )
            if include_secret:
                archive.writestr(".env", "TOKEN=not-for-release\n")
        with tarfile.open(sdist, "w:gz") as archive:
            for name, payload in {
                "nolane_habitat-0.1.0a20/README.md": b"# Nolane Habitat\n",
                "nolane_habitat-0.1.0a20/PKG-INFO": (
                    "Metadata-Version: 2.3\n"
                    "Name: nolane-habitat\n"
                    "Version: 0.1.0a20\n"
                    f"Requires-Dist: {sdist_requirement}\n"
                ).encode("utf-8"),
            }.items():
                member = tarfile.TarInfo(name)
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
            self.assertEqual(["pathspec>=0.12,<1"], report["dependency_inventory"]["wheel"])
            self.assertEqual(report["dependency_inventory"]["wheel"], report["dependency_inventory"]["sdist"])
            self.assertRegex(report["dependency_inventory_sha256"], r"^[0-9a-f]{64}$")
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

    def test_report_rejects_mismatched_dependency_inventory(self):
        with TemporaryDirectory() as td:
            dist = Path(td)
            self._write_artifacts(dist, sdist_requirement="pathspec>=0.13,<1")

            report = verify_distribution(
                source_commit="a" * 40,
                version="0.1.0-alpha.20",
                dist=dist,
                smoke_import=lambda *_: True,
            )

            self.assertEqual("failed", report["status"])
            self.assertIn("dependencies:mismatch", report["failures"])


if __name__ == "__main__":
    unittest.main()
