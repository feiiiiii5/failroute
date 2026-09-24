"""Exercise claim commands from a relocated checkout with shell-special paths."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RelocatedClaimsTest(unittest.TestCase):
    def test_relocated_commands_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "checkout space $literal `name`"
            companion = parent / "companion space $literal `name`"
            (root / "tools").mkdir(parents=True)
            (root / "claims").mkdir()
            companion.mkdir()
            (root / "marker").write_text("root-ok")
            (companion / "marker").write_text("companion-ok")
            shutil.copyfile(Path(__file__).with_name("verify_claims.py"),
                            root / "tools/verify_claims.py")
            (root / "python").symlink_to(sys.executable)
            code = ("import os; from pathlib import Path; "
                    "print((Path(os.environ['FAILROUTE_ROOT'])/'marker').read_text()); "
                    "print((Path(os.environ['CONTRACTLENS_ROOT'])/'marker').read_text())")
            import shlex
            claim = {"id": "portable", "stmt": "read both relocated trees",
                     "cmd": '"${FAILROUTE_ROOT}/python" -c ' + shlex.quote(code),
                     "expect": "root-ok\\ncompanion-ok"}
            path = root / "claims/portable.json"
            path.write_text(json.dumps([claim]))
            env = os.environ.copy()
            env["CONTRACTLENS_ROOT"] = str(companion)
            env["FAILROUTE_ROOT"] = "/deliberately/stale"
            command = [sys.executable, str(root / "tools/verify_claims.py"),
                       "--only", "portable"]
            result = subprocess.run(command, cwd=parent, env=env,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALL CLAIMS PASS", result.stdout)
            # An unavailable companion must fail, never be silently treated as empty data.
            env["CONTRACTLENS_ROOT"] = str(parent / "absent")
            result = subprocess.run(command, cwd=parent, env=env,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("1 CLAIM(S) FAILED", result.stdout)


if __name__ == "__main__":
    unittest.main()
