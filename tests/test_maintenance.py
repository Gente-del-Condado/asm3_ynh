import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("asm3_build", ROOT / "conf/build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildMessagesTests(unittest.TestCase):
    def prepare_source(self, directory):
        root = Path(directory)
        (root / "VERSION").write_text("51-1")
        (root / "src/asm3").mkdir(parents=True)
        (root / "reports").mkdir()
        (root / "reports/example.rep").write_text("test report")
        (root / "scripts/schema").mkdir(parents=True)
        return root

    def test_progress_does_not_contaminate_generated_javascript(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_source(directory)
            output = io.StringIO()
            environments = []

            def generate(command, **kwargs):
                environments.append(kwargs["env"])
                if command[1].endswith("make_db.py"):
                    (root / "scripts/schema/schema.db").write_bytes(b"test sqlite")
                else:
                    kwargs["stdout"].write("var schema = {};\n")

            with patch.object(build.subprocess, "run", side_effect=generate):
                with patch.dict(os.environ, {"ASM3_YNH_MAINTENANCE_LOG": "1"}):
                    with redirect_stdout(output):
                        build.build(root)
            self.assertEqual(environments[0]["ASM3_YNH_MAINTENANCE_LOG"], "1")
            self.assertNotIn("ASM3_YNH_MAINTENANCE_LOG", environments[1])
            self.assertIn("esquema SQLite temporal", output.getvalue())
            self.assertEqual((root / "src/static/js/bundle/schema.js").read_text(), "var schema = {};\n")
            self.assertFalse((root / "scripts/schema/schema.db").exists())

    def test_schema_generation_failure_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare_source(directory)
            failure = subprocess.CalledProcessError(23, ["schema-generator"])
            with patch.object(build.subprocess, "run", side_effect=failure):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(subprocess.CalledProcessError) as raised:
                        build.build(root)
            self.assertEqual(raised.exception.returncode, 23)
            self.assertFalse((root / "src/static/js/bundle/schema.js").exists())
