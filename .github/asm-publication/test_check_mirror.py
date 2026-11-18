import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from check_mirror import inspect_archive
from github_mirror import Mirror, ArchiveRedirect
from urllib.request import Request


class ArchiveTests(unittest.TestCase):
    def archive(self, changes=None, link=None):
        commit, digest = 'a' * 40, 'b' * 64
        url = 'https://codeload.github.com/sheltermanager/asm3/tar.gz/' + commit
        manifest = f'packaging_format = 2\nid = "asm3"\nversion = "51.1~ynh10"\n[resources.sources.main]\nurl = "{url}"\nsha256 = "{digest}"\n'
        files = {'root/manifest.toml': manifest.encode(),
                 'root/upstream.lock.json': json.dumps({'repository': 'sheltermanager/asm3',
                     'commit': commit, 'url': url, 'sha256': digest}).encode(),
                 'root/scripts/install': b'#!/bin/bash\n',
                 'root/scripts/upgrade': b'#!/bin/bash\n'}
        files.update(changes or {})
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w:gz') as archive:
            for name, value in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(value)
                archive.addfile(entry, io.BytesIO(value))
            if link:
                entry = tarfile.TarInfo(link)
                entry.type, entry.linkname = tarfile.SYMTYPE, '/etc/passwd'
                archive.addfile(entry)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'archive.tar.gz'
            path.write_bytes(raw.getvalue())
            return inspect_archive(path)

    def test_valid_distribution(self):
        value = self.archive()
        self.assertEqual(value['version'], '51.1~ynh10')
        self.assertEqual(value['tracked_files'], 4)
        self.assertEqual(value['upstream_commit'], 'a' * 40)

    def test_traversal_and_multiple_roots(self):
        for name in ('root/../outside', '/absolute', 'another/file', 'root/.git/config'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.archive({name: b'x'})

    def test_links_are_rejected(self):
        with self.assertRaises(ValueError):
            self.archive(link='root/private_git_manager/link')

    def test_wrong_upstream(self):
        for changes in ({'repository': 'other/repo'}, {'commit': 'invalid'},
                        {'sha256': 'c' * 64}, {'url': 'https://other.invalid/source'}):
            lock = {'repository': 'sheltermanager/asm3', 'commit': 'a' * 40,
                    'sha256': 'b' * 64,
                    'url': 'https://codeload.github.com/sheltermanager/asm3/tar.gz/' + 'a' * 40}
            lock.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.archive({'root/upstream.lock.json': json.dumps(lock).encode()})



class ReaderTests(unittest.TestCase):
    @patch.dict('os.environ', {'MIRROR_READ_TOKEN': 'fixture'})
    def test_other_repository_rejected(self):
        with self.assertRaises(ValueError):
            Mirror('jacksignal')

    @patch.dict('os.environ', {'MIRROR_READ_TOKEN': 'fixture'})
    def test_identity_and_privacy_required(self):
        for update in ({'private': False}, {'id': 1}, {'full_name': 'other/repo'}):
            metadata = {'id': 1463391767, 'full_name': 'Gente-del-Condado/asm3_ynh-private', 'private': True}
            metadata.update(update)
            with self.subTest(update=update), patch.object(Mirror, 'request', return_value=metadata), self.assertRaises(ValueError):
                Mirror('asm3_ynh-private').verify()

    def test_redirect_drops_authorization(self):
        request = Request('https://api.github.com/repos/a/b/tarball/x', headers={'Authorization': 'Bearer fixture'})
        new = ArchiveRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://codeload.github.com/a/b/legacy.tar.gz/x')
        self.assertIsNone(new.get_header('Authorization'))

    def test_untrusted_redirect_rejected(self):
        with self.assertRaises(ValueError):
            ArchiveRedirect().redirect_request(Request('https://api.github.com/a'), None, 302, 'Found', {}, 'https://other.invalid/a')


if __name__ == '__main__':
    unittest.main()
