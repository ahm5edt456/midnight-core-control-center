"""Stage 11 tests run exclusively in temporary HOME/XDG directories."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import packager as pkg


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="midnight-stage11-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.data_home = self.home / ".local/share"
        self.bin_home = self.home / ".local/bin"
        self.project = self.home / "Projects/midnight-core-control-center"
        for d in (self.project / "midnight", self.project / "assets"):
            d.mkdir(parents=True)
        self.replace_main("print('installed main v1')\n")
        (self.project / "midnight/__init__.py").write_text("")
        (self.project / "midnight/application.py").write_text(
            'APP_ID = "io.midnightcore.ControlCenter"\n'
        )
        (self.project / "midnight/window.py").write_text("class Window: pass\n")
        (self.project / "assets/style.css").write_text("/* Styles */\n")
        (self.project / "assets/logo.svg").write_text("<svg/>\n")
        (self.project / "assets/private.key").write_text("TOP-SECRET\n")
        (self.project / ".env").write_text("SECRET=123\n")
        (self.project / "midnight/__pycache__").mkdir()
        (self.project / "midnight/__pycache__/application.cpython-313.pyc").write_bytes(b"bad")
        self.backups = self.data_home / "midnight-core/backups"
        self.backups.mkdir(parents=True)
        (self.backups / "user-backup.zip").write_bytes(b"keep this")
        self.user_config = self.home / ".config/midnight-core"
        self.user_config.mkdir(parents=True)
        (self.user_config / "aliases.bash").write_text("alias x='true'\n")
        self.environment = patch.dict(os.environ, {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data_home),
            "XDG_BIN_HOME": str(self.bin_home),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        # The container test runner may be root; production code still forbids sudo.
        self.root_check = patch.object(pkg, "check_not_root")
        self.root_check.start()
        self.addCleanup(self.root_check.stop)
        self.p = pkg.paths()

    def replace_main(self, contents):
        (self.project / "main.py").write_text(contents)

    def test_install_files_and_source_unchanged(self):
        pkg.install(self.project)
        self.assertTrue(self.p["app"].joinpath("main.py").exists())
        self.assertTrue(self.p["launcher"].exists())
        self.assertTrue(os.access(self.p["launcher"], os.X_OK))
        self.assertTrue(self.p["desktop"].exists())
        self.assertTrue(self.p["icon"].exists())
        self.assertIn(pkg.APP_ID, self.p["desktop"].name)
        self.assertIn("Icon=" + pkg.APP_ID, self.p["desktop"].read_text())
        self.assertEqual((self.project / "main.py").read_text(), "print('installed main v1')\n")

    def test_launch(self):
        pkg.install(self.project)
        result = subprocess.run([self.p["launcher"]], capture_output=True, text=True, check=True)
        self.assertIn("installed main v1", result.stdout)

    def test_reinstall_updates_snapshot_not_original(self):
        pkg.install(self.project)
        self.replace_main("print('installed main v2')\n")
        pkg.install(self.project)
        self.assertIn("v2", (self.p["app"] / "main.py").read_text())
        self.assertEqual((self.project / "main.py").read_text(), "print('installed main v2')\n")

    def test_uninstall_keeps_settings_backups_and_source(self):
        pkg.install(self.project)
        pkg.uninstall()
        self.assertFalse(self.p["app"].exists())
        self.assertFalse(self.p["launcher"].exists())
        self.assertFalse(self.p["desktop"].exists())
        self.assertFalse(self.p["icon"].exists())
        self.assertTrue((self.backups / "user-backup.zip").exists())
        self.assertTrue((self.user_config / "aliases.bash").exists())
        self.assertTrue((self.project / "main.py").exists())

    def test_reject_unknown_desktop_file(self):
        self.p["desktop"].parent.mkdir(parents=True)
        self.p["desktop"].write_text("[Desktop Entry]\nName=Another app\n")
        with self.assertRaises(pkg.PackagingError):
            pkg.install(self.project)
        self.assertEqual(self.p["desktop"].read_text(), "[Desktop Entry]\nName=Another app\n")
        self.assertFalse(self.p["app"].exists())

    def test_reject_source_symlink(self):
        (self.project / "midnight/unsafe.py").symlink_to(self.home / "private.txt")
        (self.home / "private.txt").write_text("secret")
        with self.assertRaises(pkg.PackagingError):
            pkg.install(self.project)
        self.assertFalse(self.p["app"].exists())

    def test_invalid_python_source_preserves_previous_install(self):
        pkg.install(self.project)
        self.replace_main("print(\n")
        with self.assertRaises(pkg.PackagingError):
            pkg.install(self.project)
        self.assertIn("v1", (self.p["app"] / "main.py").read_text())

    def test_reject_application_id_mismatch(self):
        (self.project / "midnight/application.py").write_text('APP_ID="wrong.app"\n')
        with self.assertRaises(pkg.PackagingError):
            pkg.install(self.project)

    def test_no_private_files_or_caches_in_package(self):
        pkg.install(self.project)
        self.assertFalse((self.p["app"] / ".env").exists())
        self.assertFalse((self.p["app"] / "assets/private.key").exists())
        self.assertFalse((self.p["app"] / "midnight/__pycache__").exists())
        self.assertFalse((self.p["app"] / ".git").exists())

    def test_uninstall_refuses_unrecognized_launcher(self):
        pkg.install(self.project)
        self.p["launcher"].write_text("#!/bin/sh\necho not ours\n")
        with self.assertRaises(pkg.PackagingError):
            pkg.uninstall()
        self.assertTrue(self.p["app"].exists())

    def test_atomic_install_failure_rollback(self):
        pkg.install(self.project)
        old = self.p["app"].joinpath("main.py").read_text()
        old_launcher = self.p["launcher"].read_bytes()
        self.replace_main("print('new v2')\n")
        original_writer = pkg.atomic_write
        failed_once = [False]
        def failing_writer(path, data, mode):
            if path == self.p["desktop"] and not failed_once[0]:
                failed_once[0] = True
                raise PermissionError("simulated desktop write failure")
            return original_writer(path, data, mode)
        with patch.object(pkg, "atomic_write", side_effect=failing_writer):
            with self.assertRaises(PermissionError):
                pkg.install(self.project)
        self.assertEqual(self.p["app"].joinpath("main.py").read_text(), old)
        self.assertEqual(self.p["launcher"].read_bytes(), old_launcher)
        self.assertEqual(self.p["desktop"].read_bytes(), pkg.make_desktop(self.p["launcher"]))

    def test_reject_unowned_install_directory(self):
        self.p["app"].mkdir(parents=True)
        (self.p["app"] / "user-data.txt").write_text("keep")
        with self.assertRaises(pkg.PackagingError):
            pkg.install(self.project)
        self.assertEqual((self.p["app"] / "user-data.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
