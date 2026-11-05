import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("forgejo_pr", ROOT / "tools/forgejo_pr.py")
forgejo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forgejo)


class ForgejoTests(unittest.TestCase):
    def test_existing_update_is_not_duplicated(self):
        pull = {"head": {"ref": forgejo.BRANCH, "repo": {"full_name": "org/asm3_ynh"}}, "html_url": "https://forge.example/org/asm3_ynh/pulls/4"}
        with patch.object(forgejo.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps([pull]).encode())) as call:
            self.assertEqual(forgejo.propose("https://forge.example", "org/asm3_ynh", "test-token"), pull)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0].get_method(), "GET")

    def test_new_pull_uses_repository_default_branch(self):
        replies = [[], {"default_branch": "stable"}, {"html_url": "https://forge.example/org/asm3_ynh/pulls/5"}]
        streams = [io.BytesIO(json.dumps(reply).encode()) for reply in replies]
        with patch.object(forgejo.urllib.request, "urlopen", side_effect=streams) as call:
            forgejo.propose("https://forge.example", "org/asm3_ynh", "test-token")
        req = call.call_args.args[0]
        self.assertEqual(req.full_url, "https://forge.example/api/v1/repos/org/asm3_ynh/pulls")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data)["base"], "stable")
        self.assertEqual(req.get_header("Authorization"), "token test-token")

    def test_missing_credentials_are_rejected_before_network(self):
        with patch.object(forgejo.urllib.request, "urlopen") as call:
            with self.assertRaises(ValueError):
                forgejo.propose("https://forge.example", "org/asm3_ynh", "")
            call.assert_not_called()
