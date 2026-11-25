import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release_suite as suite


class ReleaseSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="midnight-qa-test-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "app"
        (self.project / "midnight").mkdir(parents=True)
        (self.project / "assets").mkdir()
        (self.project / "midnight/pages").mkdir()
        (self.project / "midnight/services").mkdir()
        (self.project / "main.py").write_text("print('hello')\n")
        (self.project / "midnight/application.py").write_text('APP_ID = "io.midnightcore.ControlCenter"\n')
        (self.project / "midnight/window.py").write_text("class Window: pass\n")
        (self.project / "assets/style.css").write_text(".main { background: #000; }\n")
        (self.project / "assets/logo.svg").write_text("<svg/>")
        (self.project / "LICENSE").write_text("TEST LICENSE - not for production\n")
        (self.project / "README.md").write_text("Example test project\n")

    def check(self):
        return suite.audit(self.project, run_tests=False)

    def test_valid_minimal_project(self):
        result = self.check()
        self.assertEqual(result['errors'], [])

    def test_bad_python_syntax_rejected(self):
        (self.project / 'midnight/window.py').write_text('def broken(:\n')
        self.assertTrue(any('Python parse failed' in s for s in self.check()['errors']))

    def test_missing_internal_module_rejected(self):
        (self.project / 'midnight/window.py').write_text('from midnight.pages.missing import Page\n')
        self.assertTrue(any('Missing Python module' in s for s in self.check()['errors']))

    def test_legacy_gtk_call_rejected(self):
        (self.project / 'midnight/window.py').write_text('dialog.format_secondary_text("no")\n')
        self.assertTrue(any('Deprecated GTK dialog call' in s for s in self.check()['errors']))

    def test_application_id_mismatch(self):
        (self.project / 'midnight/application.py').write_text('APP_ID = "other.app"\n')
        self.assertTrue(any('Application ID mismatch' in s for s in self.check()['errors']))

    def test_symlink_rejected(self):
        (self.project / 'assets/image.png').symlink_to(self.project / 'README.md')
        self.assertTrue(any('Symlink' in s for s in self.check()['errors']))

    def test_sensitive_git_file_rejected(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.project, check=True)
        (self.project / '.env').write_text('PASSWORD=test\n')
        subprocess.run(['git', 'add', '-f', '.env'], cwd=self.project, check=True)
        self.assertTrue(any('Sensitive' in s for s in self.check()['errors']))

    def test_token_value_hidden_in_report(self):
        secret = 'gh' + 'p_' + ('A' * 36)
        (self.project / 'midnight/window.py').write_text('KEY = ' + repr(secret) + '\n')
        result = self.check()
        self.assertTrue(any('GitHub access token' in s for s in result['errors']))
        self.assertTrue(all(secret not in s for s in result['errors']))

    def test_release_bundle_allowlist_checksum_and_manifest(self):
        (self.project / '.env').write_text('SECRET=do-not-include\n')
        (self.project / 'assets/credentials.key').write_text('do-not-include\n')
        (self.project / 'assets/cache.bin').write_bytes(b'cache')
        (self.project / 'midnight/__pycache__').mkdir()
        (self.project / 'midnight/__pycache__/x.pyc').write_bytes(b'cache')
        result = self.check()
        self.assertEqual(result['errors'], [])
        output, checksum, _ = suite.build_bundle(self.project, result)
        with zipfile.ZipFile(output) as z:
            files = z.namelist()
            self.assertTrue(any(n.endswith('/midnight/window.py') for n in files))
            self.assertFalse(any('.env' in n or '.key' in n or 'cache.bin' in n or '__pycache__' in n for n in files))
            manifest_path = next(n for n in files if n.endswith('/SOURCE_MANIFEST.json'))
            manifest = json.loads(z.read(manifest_path))
            name = manifest_path.removesuffix('SOURCE_MANIFEST.json')
            for rel, digest in manifest['sha256'].items():
                self.assertEqual(hashlib.sha256(z.read(name + rel)).hexdigest(), digest)
        expected = hashlib.sha256(output.read_bytes()).hexdigest()
        self.assertIn(expected, checksum.read_text())

    def test_build_refuses_failed_audit(self):
        (self.project / 'midnight/window.py').write_text('def f(:\n')
        with self.assertRaises(RuntimeError):
            suite.build_bundle(self.project, self.check())

    def test_report_written_without_secret_leak(self):
        data = self.check()
        report = suite.make_report(data, self.project)
        self.assertTrue(report.is_file())
        self.assertIn('GUI verification required', report.read_text())


if __name__ == '__main__':
    unittest.main()
