import gzip
from io import BytesIO
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest

from tools.normalize_sdist import normalize_sdist


class NormalizeSdistTests(unittest.TestCase):
    @staticmethod
    def _write_sdist(path: Path, *, timestamp: int) -> None:
        with path.open("wb") as destination:
            with gzip.GzipFile(fileobj=destination, mode="wb", mtime=timestamp) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    directory = tarfile.TarInfo("nolane_habitat-0.1.0a20")
                    directory.type = tarfile.DIRTYPE
                    directory.mode = 0o755
                    directory.mtime = timestamp
                    archive.addfile(directory)
                    member = tarfile.TarInfo("nolane_habitat-0.1.0a20/habitat.py")
                    member.size = len(b"print('stable')\n")
                    member.mode = 0o644
                    member.mtime = timestamp
                    archive.addfile(member, BytesIO(b"print('stable')\n"))

    def test_normalizes_timestamp_only_sdist_differences_to_identical_bytes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            self._write_sdist(first, timestamp=1_700_000_000)
            self._write_sdist(second, timestamp=1_800_000_000)

            first_hash = normalize_sdist(first, epoch=0)
            second_hash = normalize_sdist(second, epoch=0)

            self.assertEqual(first_hash, second_hash)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as archive:
                member = archive.getmember("nolane_habitat-0.1.0a20/habitat.py")
                self.assertEqual(0, member.mtime)
                self.assertEqual(b"print('stable')\n", archive.extractfile(member).read())

    def test_rejects_non_file_or_directory_members(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "unsafe.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                link = tarfile.TarInfo("unsafe-link")
                link.type = tarfile.SYMTYPE
                link.linkname = "target"
                archive.addfile(link)

            with self.assertRaisesRegex(ValueError, "unsupported member type"):
                normalize_sdist(path, epoch=0)


if __name__ == "__main__":
    unittest.main()
