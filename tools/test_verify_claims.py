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


class HistoricalClaimsTest(unittest.TestCase):
    """A claim whose inputs are missing is reported HIST, never PASS, and is run when they exist."""

    def _run(self, root, *extra):
        return subprocess.run([sys.executable, str(root / "tools/verify_claims.py"),
                               "--only", "hist", *extra], cwd=root, text=True,
                              capture_output=True)

    def test_missing_commit_is_hist_and_present_commit_runs(self):
        if shutil.which("git") is None:
            self.skipTest("needs git")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir()
            (root / "claims").mkdir()
            shutil.copyfile(Path(__file__).with_name("verify_claims.py"),
                            root / "tools/verify_claims.py")
            git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run([*git, "init", "-q"], check=True)
            subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            head = subprocess.run([*git, "rev-parse", "HEAD"], check=True, text=True,
                                  capture_output=True).stdout.strip()
            # The command would PASS if run; a missing input must still not read as PASS.
            claim = {"id": "gone", "stmt": "needs a lost commit", "cmd": "echo ok",
                     "expect": "ok", "historical": {"reason": "rewritten history",
                                                    "requires_git_objects": ["0" * 40]}}
            (root / "claims/hist.json").write_text(json.dumps([claim]))
            result = self._run(root)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("HIST", result.stdout)
            self.assertNotIn("gone                         PASS", result.stdout)
            self.assertIn("1 HISTORICAL CLAIM(S) NOT INDEPENDENTLY REPRODUCIBLE", result.stdout)
            self.assertIn("ALL CURRENT CLAIMS PASS", result.stdout)
            self.assertIn("expectation kept unchanged: 'ok'", result.stdout)
            strict = self._run(root, "--strict-historical")
            self.assertEqual(strict.returncode, 1, strict.stdout)
            # When the commit exists the claim is executed and judged on its output.
            claim["historical"]["requires_git_objects"] = [head]
            claim["expect"] = "not-in-output"
            (root / "claims/hist.json").write_text(json.dumps([claim]))
            result = self._run(root)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("1 CLAIM(S) FAILED", result.stdout)


if __name__ == "__main__":
    unittest.main()
