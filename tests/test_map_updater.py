import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "source"))

import map_updater


class MapUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="godimap-updater-test-"))
        self.app_dir = self.temp_dir / "app"
        self.app_dir.mkdir()
        shutil.copytree(PROJECT_DIR / "maps", self.app_dir / "maps")
        shutil.copytree(PROJECT_DIR / "mapdata", self.app_dir / "mapdata")
        (self.app_dir / "map-version.json").write_text(
            json.dumps({"version": "2026.07.30.1"}),
            encoding="utf-8",
        )
        self.manifest = json.loads(
            (PROJECT_DIR / "update" / "manifest.json").read_text(encoding="utf-8")
        )
        self.archive = (
            PROJECT_DIR
            / "output"
            / "map-releases"
            / f"maps-{self.manifest['version']}"
            / "godimap-mapdata.zip"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def local_download(self, _manifest, destination, progress_callback=None):
        shutil.copy2(self.archive, destination)
        if progress_callback:
            size = self.archive.stat().st_size
            progress_callback(size, size)

    def test_install_replaces_map_folders_and_updates_version(self):
        expected_count = len(list((PROJECT_DIR / "mapdata").rglob("*.json")))
        with mock.patch.object(map_updater, "_download", self.local_download):
            result = map_updater.download_and_install(self.manifest, self.app_dir)
        self.assertEqual(result["map_count"], expected_count)
        self.assertEqual(map_updater.load_local_version(self.app_dir), self.manifest["version"])
        self.assertEqual(len(list((self.app_dir / "mapdata").rglob("*.json"))), expected_count)

    def test_failed_version_write_restores_old_folders(self):
        old_json = (self.app_dir / "mapdata" / "lucreshia" / "luc1f.json").read_bytes()
        original_write = map_updater._write_version

        def fail_for_new_version(app_dir, version):
            if version == self.manifest["version"]:
                raise OSError("simulated version write failure")
            return original_write(app_dir, version)

        with mock.patch.object(map_updater, "_download", self.local_download), mock.patch.object(
            map_updater, "_write_version", fail_for_new_version
        ):
            with self.assertRaises(OSError):
                map_updater.download_and_install(self.manifest, self.app_dir)
        self.assertEqual(map_updater.load_local_version(self.app_dir), "2026.07.30.1")
        self.assertEqual(
            (self.app_dir / "mapdata" / "lucreshia" / "luc1f.json").read_bytes(),
            old_json,
        )

    def test_archive_rejects_parent_traversal(self):
        bad_archive = self.temp_dir / "bad.zip"
        with zipfile.ZipFile(bad_archive, "w") as archive:
            archive.writestr("maps/../../outside.txt", "bad")
        with self.assertRaises(map_updater.UpdateError):
            map_updater._extract_and_validate(bad_archive, self.temp_dir / "content")

    def test_download_retries_and_removes_partial_file(self):
        destination = self.temp_dir / "retry.zip"
        attempts = []

        def flaky_download(_manifest, path, progress_callback=None):
            attempts.append(1)
            Path(path).write_bytes(b"partial")
            if len(attempts) < 3:
                raise OSError("simulated network interruption")
            Path(path).write_bytes(b"complete")

        with mock.patch.object(map_updater, "_download_once", flaky_download), mock.patch.object(
            map_updater.time, "sleep", return_value=None
        ):
            map_updater._download(self.manifest, destination)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(destination.read_bytes(), b"complete")

    def test_tls_context_uses_bundled_certifi_ca(self):
        with mock.patch.object(map_updater.ssl, "create_default_context") as create_context:
            map_updater._tls_context()
        create_context.assert_called_once_with(cafile=map_updater.certifi.where())


if __name__ == "__main__":
    unittest.main()
