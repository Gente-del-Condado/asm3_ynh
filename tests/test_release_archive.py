"""La entrega se construye en una copia limpia sin los workflows retirados."""
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseArchiveTest(unittest.TestCase):
    def test_clean_copy_builds_archive_and_bundle_without_forgejo_workflows(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / 'package'
            shutil.copytree(ROOT, copied, ignore=shutil.ignore_patterns('.git', '.forgejo', 'dist', '__pycache__', '*.pyc', '.venv'))
            result = subprocess.run(['bash', 'tools/build_release.sh'], cwd=copied,
                                    check=True, capture_output=True, text=True)
            archive_path = next((copied / 'dist').glob('*.tar.gz'))
            with tarfile.open(archive_path) as archive:
                names = set(archive.getnames())
                self.assertTrue({'manifest.toml', 'scripts/install', 'LICENSE', 'README.md'} <= names)
                self.assertFalse(any(name == '.forgejo' or name.startswith('.forgejo/') for name in names))
            self.assertEqual(len(list((copied / 'dist').glob('*.bundle'))), 1)
            for checksum in (copied / 'dist').glob('*.sha256'):
                subprocess.run(['sha256sum', '-c', checksum.name], cwd=copied / 'dist',
                               check=True, capture_output=True)
            self.assertIn('.bundle', result.stdout)


if __name__ == '__main__':
    unittest.main()
