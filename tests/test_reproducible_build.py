import unittest
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from tools.verify_reproducible_build import verify_reproducible_build


class ReproducibleBuildTests(unittest.TestCase):
    @staticmethod
    def _write_build(directory: Path, *, wheel: bytes = b"wheel", sdist: bytes = b"sdist") -> None:
        directory.mkdir()
        (directory / "nolane_habitat-0.1.0a20-py3-none-any.whl").write_bytes(wheel)
        (directory / "nolane_habitat-0.1.0a20.tar.gz").write_bytes(sdist)

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()

    def _clean_source_copies(self, root: Path) -> tuple[str, Path, Path]:
        repository = root / "repository"
        repository.mkdir()
        (repository / "tracked.py").write_text("value = 1\n", encoding="utf-8")
        self._git(repository, "init", "--quiet")
        self._git(repository, "config", "user.email", "tests@example.invalid")
        self._git(repository, "config", "user.name", "Habitat tests")
        self._git(repository, "add", "tracked.py")
        self._git(repository, "commit", "--quiet", "-m", "fixture")
        commit = self._git(repository, "rev-parse", "HEAD")
        first = root / "source-first"
        second = root / "source-second"
        self._git(root, "clone", "--quiet", str(repository), str(first))
        self._git(root, "clone", "--quiet", str(repository), str(second))
        return commit, first, second

    def test_report_binds_two_identical_builds_to_one_candidate(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source_commit, first_source, second_source = self._clean_source_copies(root)
            first = root / "first-build"
            second = root / "second-build"
            self._write_build(first)
            self._write_build(second)

            report = verify_reproducible_build(
                source_commit=source_commit,
                version="0.1.0-alpha.20",
                first=first,
                second=second,
                first_source=first_source,
                second_source=second_source,
            )

            self.assertEqual("passed", report["status"])
            self.assertEqual([], report["failures"])
            self.assertEqual(report["builds"]["first"], report["builds"]["second"])
            self.assertEqual(source_commit, report["sources"]["first"]["head"])
            self.assertNotEqual(report["sources"]["first"]["checkout_id"], report["sources"]["second"]["checkout_id"])
            self.assertEqual("cpython", report["environment"]["implementation"])
            self.assertRegex(report["environment"]["python"], r"^\d+\.\d+\.\d+$")
            self.assertRegex(report["report_sha256"], r"^[0-9a-f]{64}$")

    def test_report_rejects_a_nonreproducible_artifact_hash(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source_commit, first_source, second_source = self._clean_source_copies(root)
            first = root / "first-build"
            second = root / "second-build"
            self._write_build(first)
            self._write_build(second, wheel=b"different-wheel")

            report = verify_reproducible_build(
                source_commit=source_commit,
                version="0.1.0-alpha.20",
                first=first,
                second=second,
                first_source=first_source,
                second_source=second_source,
            )

            self.assertEqual("failed", report["status"])
            self.assertIn("wheel:sha256-mismatch", report["failures"])

    def test_report_rejects_one_checkout_presented_as_two_clean_sources(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source_commit, source, _ = self._clean_source_copies(root)
            first = root / "first-build"
            second = root / "second-build"
            self._write_build(first)
            self._write_build(second)

            with self.assertRaisesRegex(ValueError, "distinct clean checkouts"):
                verify_reproducible_build(
                    source_commit=source_commit,
                    version="0.1.0-alpha.20",
                    first=first,
                    second=second,
                    first_source=source,
                    second_source=source,
                )

    def test_report_rejects_a_dirty_source_checkout(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source_commit, first_source, second_source = self._clean_source_copies(root)
            first = root / "first-build"
            second = root / "second-build"
            self._write_build(first)
            self._write_build(second)
            (second_source / "untracked.txt").write_text("dirty\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "clean checkout"):
                verify_reproducible_build(
                    source_commit=source_commit,
                    version="0.1.0-alpha.20",
                    first=first,
                    second=second,
                    first_source=first_source,
                    second_source=second_source,
                )


if __name__ == "__main__":
    unittest.main()
