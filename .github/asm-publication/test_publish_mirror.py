import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import publish_mirror as publisher


class ExportTests(unittest.TestCase):
    def source(self, path, extra=None):
        commit, digest = 'a' * 40, 'b' * 64
        url = 'https://codeload.github.com/sheltermanager/asm3/tar.gz/' + commit
        manifest = f'packaging_format = 2\nid = "asm3"\nversion = "51.1~ynh10"\n[resources.sources.main]\nurl = "{url}"\nsha256 = "{digest}"\n'
        files = {'manifest.toml': manifest.encode(),
                 'upstream.lock.json': json.dumps({'repository': 'sheltermanager/asm3',
                     'commit': commit, 'url': url, 'sha256': digest}).encode(),
                 'scripts/install': b'#!/bin/bash\n',
                 'scripts/upgrade': b'#!/bin/bash\n'}
        files.update(extra or {})
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in files.items():
                item = tarfile.TarInfo('source/' + name)
                item.size, item.mode = len(data), 0o755 if name.startswith('scripts/') else 0o644
                archive.addfile(item, io.BytesIO(data))

    def test_export_excludes_private_root_and_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source(root / 'source.tar.gz', {'private-note.txt': b'private fixture', '.github/workflows/evil.yml': b'x'})
            files = publisher.export(root / 'source.tar.gz', root / 'out')
            self.assertNotIn('private-note.txt', files)
            self.assertNotIn('.github/workflows/evil.yml', files)
            self.assertEqual(files['scripts/install']['mode'], 0o755)

    def test_unknown_distribution_file_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source(root / 'source.tar.gz', {'scripts/new': b'new'})
            with self.assertRaisesRegex(ValueError, 'Archivo nuevo'):
                publisher.export(root / 'source.tar.gz', root / 'out')

    def test_tampered_transfer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source(root / 'source.tar.gz')
            files = publisher.export(root / 'source.tar.gz', root / 'main')
            (root / 'receipt.json').write_text(json.dumps({'source_sha': 'a'*40, 'main_files': files}))
            publisher.verify(root)
            (root / 'main/manifest.toml').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'alterada'):
                publisher.verify(root)

    def test_unknown_file_in_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'secret.txt').write_text('fixture')
            with self.assertRaisesRegex(ValueError, 'ajeno'):
                publisher.inventory(root)

    def test_artifact_restores_executable_modes_from_verified_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.source(root / 'source.tar.gz')
            files = publisher.export(root / 'source.tar.gz', root / 'main')
            record = {'source_sha': 'a'*40, 'main_files': files}
            (root / 'receipt.json').write_text(json.dumps(record))
            executable = root / 'main/scripts/install'
            executable.chmod(0o644)
            publisher.verify(root)
            self.assertEqual(executable.stat().st_mode & 0o777, 0o755)
            record['main_files']['scripts/install']['mode'] = 0o4755
            (root / 'receipt.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'permisos'):
                publisher.verify(root)

    def test_controller_paths_cannot_enter_allowlist(self):
        with patch.object(publisher, 'CONTROL') as control:
            (control / 'public-files.txt').read_text.return_value = '.github/workflows/other.yml\n'
            with self.assertRaisesRegex(ValueError, 'no autorizada'):
                publisher.allowed()


if __name__ == '__main__':
    unittest.main()
