import tempfile
import unittest
import zipfile
import stat
from pathlib import Path
from unittest import mock

from habitat.source_bridge import ArchiveLimits, ImportErrorUnsafe, prepare_source, safe_extract_zip, snapshot_metadata


class SourceBridgeTests(unittest.TestCase):
    def test_folder_is_linked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / "src"; src.mkdir(); (src / "a.py").write_text("x=1")
            got, mode = prepare_source(src, root / "hab")
            self.assertEqual(got, src.resolve()); self.assertEqual(mode, "linked-folder")

    def test_loose_file_is_managed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / "single.py"; source.write_text("x=1")
            got, mode = prepare_source(source, root / "hab")
            self.assertEqual(mode, "managed-file")
            self.assertEqual((got / "single.py").read_text(), "x=1")

    def test_zip_is_managed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); z = root / "p.zip"
            with zipfile.ZipFile(z, "w") as f: f.writestr("p/a.py", "x=1")
            got, mode = prepare_source(z, root / "hab")
            self.assertEqual(mode, "managed-zip"); self.assertTrue((got / "a.py").exists())

    def test_zip_size_limit_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); z = root / "large.zip"
            with zipfile.ZipFile(z, "w") as f: f.writestr("big.txt", "1234567890")
            with self.assertRaises(ImportErrorUnsafe):
                safe_extract_zip(z, root / "out", ArchiveLimits(max_total_uncompressed=5))

    def test_zip_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); z = root / "link.zip"
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(z, "w") as f: f.writestr(info, "target")
            with self.assertRaises(ImportErrorUnsafe): safe_extract_zip(z, root / "out")

    def test_zip_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); z = root / "bad.zip"
            with zipfile.ZipFile(z, "w") as f: f.writestr("../escape.txt", "bad")
            with self.assertRaises(ImportErrorUnsafe): safe_extract_zip(z, root / "out")

    def test_snapshot_metadata_normalizes_equivalent_root_spellings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "made.txt"
            source.write_text("x")
            alias = root.parent / "placeholder" / ".." / root.name
            with mock.patch("habitat.source_bridge.iter_project_files", return_value=[source.resolve()]):
                snapshot = snapshot_metadata(alias)
            self.assertEqual(snapshot, {"made.txt": (1, source.stat().st_mtime_ns)})

if __name__ == "__main__": unittest.main()
