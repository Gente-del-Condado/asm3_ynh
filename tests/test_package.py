import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


server = module("server", "conf/server.py")
updater = module("updater", "tools/update_upstream.py")


class SourceArchiveTests(unittest.TestCase):
    def test_portable_extraction_rejects_traversal_and_links(self):
        import io,tarfile,tempfile
        smoke=module('smoke_test','tools/smoke_test.py')
        for name,kind in (('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE)):
            with tempfile.TemporaryDirectory() as directory,tarfile.open(fileobj=io.BytesIO(),mode='w') as archive:
                member=tarfile.TarInfo(name);member.type=kind;archive.addfile(member,io.BytesIO())
                with self.assertRaises(ValueError):smoke.extract_source(archive,Path(directory)/'out')

    def test_portable_extraction_preserves_regular_source(self):
        import io,tarfile,tempfile
        smoke=module('smoke_test','tools/smoke_test.py')
        with tempfile.TemporaryDirectory() as directory:
            data=io.BytesIO()
            with tarfile.open(fileobj=data,mode='w') as archive:
                member=tarfile.TarInfo('root/file');member.size=3;archive.addfile(member,io.BytesIO(b'abc'))
            data.seek(0)
            with tarfile.open(fileobj=data) as archive:smoke.extract_source(archive,Path(directory)/'out')
            self.assertEqual((Path(directory)/'out/root/file').read_bytes(),b'abc')


class ProxyTests(unittest.TestCase):
    def test_prefix_https_remote_ip_and_cookie_isolation(self):
        for prefix in ("", "/", "/refugio", "/apps/asm3"):
            with self.subTest(prefix=prefix):
                got = {}

                def application(env, respond):
                    got.update(env)
                    respond("200 OK", [("Set-Cookie", "asm_session_id=abc; Path=/; Secure; HttpOnly"),
                                       ("Set-Cookie", "asm_remember_me=token; Secure")])
                    return [b"ok"]

                def respond(status, headers, exc_info=None):
                    got["headers"] = headers

                proxy = server.ProxyApplication(application, prefix, "asm3__2")
                result = proxy({"REMOTE_ADDR": "127.0.0.1", "HTTP_X_REAL_IP": "198.51.100.42",
                                "PATH_INFO": "/login", "HTTP_COOKIE": "asm_session_id=wrong; asm_session_id_asm3=other; asm_session_id_asm3__2=right; asm_remember_me_asm3__2=remember"}, respond)
                self.assertEqual(result, [b"ok"])
                self.assertEqual(got["SCRIPT_NAME"], prefix.rstrip("/"))
                self.assertEqual(got["PATH_INFO"], "/login")
                self.assertEqual(got["REMOTE_ADDR"], "198.51.100.42")
                self.assertEqual(got["wsgi.url_scheme"], "https")
                self.assertIn("asm_session_id=right", got["HTTP_COOKIE"])
                self.assertNotIn("asm_session_id=wrong", got["HTTP_COOKIE"])
                self.assertIn("asm_remember_me=remember", got["HTTP_COOKIE"])
                self.assertTrue(got["headers"][0][1].startswith("asm_session_id_asm3__2="))
                for _, cookie in got["headers"]:
                    self.assertIn("Path=" + prefix.rstrip("/") + "/", cookie)
                    self.assertIn("Secure", cookie)


class UpdaterTests(unittest.TestCase):
    def test_stable_tags(self):
        self.assertEqual(updater.normalize_version("51-1"), "51.1")
        self.assertEqual(updater.normalize_version("v52"), "52")
        for tag in ("52u", "../../bad", "52-rc1", "51\n"):
            with self.assertRaises(ValueError):
                updater.normalize_version(tag)

    def test_changes_only_source_and_version(self):
        text = (ROOT / "manifest.toml").read_text()
        current = {"url": "https://codeload.github.com/example/new", "sha256": "f" * 64, "version": "52"}
        changed = updater.update_manifest(text, {}, current)
        self.assertIn('version = "52~ynh1"', changed)
        self.assertIn(current["url"], changed)
        self.assertEqual(text.split("    [resources.system_user]")[1], changed.split("    [resources.system_user]")[1])

    def test_moved_tag_increments_packaging_revision(self):
        text = (ROOT / "manifest.toml").read_text()
        import tomllib
        version = tomllib.loads(text)["version"].split("~")[0]
        revision = int(tomllib.loads(text)["version"].split("~ynh")[1])
        current = {"url": "https://example.com/archive", "sha256": "e" * 64, "version": version}
        changed = updater.update_manifest(text, {}, current)
        self.assertIn(f'version = "{version}~ynh{revision + 1}"', changed)


if __name__ == "__main__":
    unittest.main()
