#!/usr/bin/env python3
"""Re-scan the pinned corpus with a *pinned* version of the detector.

Several claims in claims/f2.json and claims/f3.json assert historical facts: what
failroute v0.8.0 found when it scanned the pinned corpus. Those facts do not change
when the detector improves, but the claims used to re-scan with whatever was in the
working tree, so the V1 predicate refactor turned eleven of them red -- and because
all eleven are marked `slow`, `verify_claims.py --skip-slow` hid them from V1's own
acceptance.

This tool fixes the definition domain rather than the expectation. It materialises a
git worktree at the pinned ref and runs *that tree's own* detector and exporter over
the corpus, so the scan is the historical one. The analysis tools downstream
(coverage_union, delta_findings, draw_sample, truth_probe_check) stay current: they
are measurement instruments, and the claims' expectations were produced by the
committed versions of them.

Why the worktree's own rescan_corpus.py and not the repo's current one: the current
exporter writes severity / isomorphism / covered_by / verdict, fields that v0.8.0's
Finding does not have. Running the current exporter against the pinned source raises
AttributeError. A matched committed pair is also simply the more faithful reproduction.

The worktree is created if missing and reused if it already points at the right
commit, so eleven claims do not pay for eleven checkouts. It is rebuildable from the
tag at any time, so nothing here is evidence that lives only in an untracked file.

Usage:
    cd 新项目-failroute && .venv/bin/python tools/pinned_rescan.py --out /tmp/pinned-scan
    .venv/bin/python tools/pinned_rescan.py --ref v0.8.0 --out /tmp/x --with-context

Prints the resolved sha, the finding total, and the per-rule and per-package counts,
so a claim can match on the numbers directly.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REF = "v0.8.0"


def sh(cmd, cwd=ROOT, timeout=3600, check=True):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        sys.exit("error: `%s` exited %d\nstdout: %s\nstderr: %s"
                 % (" ".join(cmd[:6]), proc.returncode,
                    (proc.stdout or "").strip()[:400], (proc.stderr or "").strip()[:600]))
    return proc


def resolve(ref):
    proc = sh(["git", "rev-parse", ref + "^{commit}"], check=False)
    if proc.returncode != 0:
        sys.exit("error: cannot resolve pinned ref %r -- is the tag present in this clone?\n"
                 "  git rev-parse said: %s" % (ref, (proc.stderr or "").strip()[:300]))
    return proc.stdout.strip()


def ensure_worktree(ref, sha, path):
    """Create the pinned worktree, or reuse it when it already points at `sha`."""
    if os.path.isdir(path):
        head = sh(["git", "rev-parse", "HEAD"], cwd=path, check=False).stdout.strip()
        if head == sha:
            return "reused"
        # wrong commit (or a stale directory from an earlier ref): rebuild it
        sh(["git", "worktree", "remove", "--force", path], check=False)
        shutil.rmtree(path, ignore_errors=True)
    sh(["git", "worktree", "add", "--detach", path, sha])
    return "created"


def link_corpus(wt):
    """The pinned corpus is fetched, not committed, so it is absent from a fresh worktree."""
    src = os.path.join(ROOT, "paper", "corpus")
    dst = os.path.join(wt, "paper", "corpus")
    if not os.path.isdir(src):
        sys.exit("error: the pinned corpus is missing from the main checkout: %s\n"
                 "  run `python tools/fetch_corpus.py` first" % src)
    if os.path.islink(dst) or os.path.isdir(dst):
        return "present"
    if not os.path.isdir(os.path.join(wt, "paper")):
        sys.exit("error: pinned tree has no paper/ directory: %s" % wt)
    os.symlink(src, dst)
    return "linked"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default=DEFAULT_REF,
                    help="git ref to pin the detector to (default: %(default)s)")
    ap.add_argument("--worktree", default=None,
                    help="where to materialise it (default: /tmp/fr-pinned-<ref>)")
    ap.add_argument("--out", required=True, help="directory for the per-package jsonl files")
    ap.add_argument("--with-context", action="store_true",
                    help="pass --with-context through to the pinned exporter")
    ap.add_argument("--remove-worktree", action="store_true",
                    help="delete the worktree afterwards instead of leaving it for reuse")
    args = ap.parse_args()

    os.chdir(ROOT)
    py = os.path.join(ROOT, ".venv", "bin", "python")
    if not os.path.exists(py):
        py = sys.executable

    sha = resolve(args.ref)
    wt = args.worktree or ("/tmp/fr-pinned-" + re.sub(r"[^A-Za-z0-9._-]", "-", args.ref))
    state = ensure_worktree(args.ref, sha, wt)
    corpus = link_corpus(wt)

    exporter = os.path.join(wt, "tools", "rescan_corpus.py")
    if not os.path.isfile(exporter):
        sys.exit("error: pinned tree has no tools/rescan_corpus.py: %s" % exporter)

    out = os.path.abspath(args.out)
    if os.path.exists(out):
        if not os.path.isdir(out):
            sys.exit("error: --out exists and is not a directory: %s" % out)
        shutil.rmtree(out)

    cmd = [py, exporter, "--out", out]
    if args.with_context:
        cmd.append("--with-context")
    env = dict(os.environ, PYTHONPATH=os.path.join(wt, "src"))
    proc = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=3600, env=env)
    if proc.returncode != 0:
        sys.exit("error: pinned rescan failed (rc=%d)\nstdout: %s\nstderr: %s"
                 % (proc.returncode, (proc.stdout or "").strip()[:800],
                    (proc.stderr or "").strip()[:800]))

    import glob
    rows = []
    for fn in sorted(glob.glob(os.path.join(out, "*.jsonl"))):
        for line in open(fn, encoding="utf-8"):
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        sys.exit("error: pinned rescan produced no findings -- that is a failure, not a result")

    by_rule = Counter(r["rule"] for r in rows)
    by_pkg = Counter(r["repo"] for r in rows)
    print("pinned ref      : %s (%s)" % (args.ref, sha[:12]))
    print("worktree        : %s [%s]" % (wt, state))
    print("corpus          : %s" % corpus)
    print("exporter        : %s" % exporter)
    print("out             : %s" % out)
    print("PINNED_TOTAL=%d" % len(rows))
    print("PINNED_PER_RULE " + " ".join("%s=%d" % (k, v) for k, v in sorted(by_rule.items())))
    print("PINNED_PER_PKG " + " ".join("%s=%d" % (k, v) for k, v in sorted(by_pkg.items())))
    # The pinned exporter's own package table, verbatim. F3.per_pkg was frozen
    # against that format; reproducing history means reproducing its output
    # shape as well, not restating it in a new one and rewriting the claim.
    for line in (proc.stdout or "").splitlines():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s+\d+$", line):
            print(line)

    if args.remove_worktree:
        sh(["git", "worktree", "remove", "--force", wt], check=False)
        shutil.rmtree(wt, ignore_errors=True)
        print("worktree removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
