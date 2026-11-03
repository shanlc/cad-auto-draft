"""Regression test for the GitHub Actions smoke-test failure.

On a Windows Actions runner the console encoding is cp1252, which
cannot encode Chinese. Before the fix, running the CLI (or the frozen
exe, which shares cli.main) under PYTHONIOENCODING=cp1252 crashed
with UnicodeEncodeError at the first Chinese print ("报告: ...")
and exited with code 1, even though the DXF itself was generated.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestCliEncoding(unittest.TestCase):
    def test_cli_survives_cp1252_console(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "cp1252"
        env["PYTHONPATH"] = str(root / "src")
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-m", "cad_auto_draft.cli",
                 "--input", str(root / "examples" / "hotel_floor.json"),
                 "--out", tmp],
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
            self.assertTrue(Path(tmp, "draft.dxf").is_file())
            self.assertTrue(Path(tmp, "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
