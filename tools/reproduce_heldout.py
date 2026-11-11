#!/usr/bin/env python3
"""Reproduce held-out scans and coverage in a NEW output directory.

Uses the immutable detector commits recorded in comparison.json, current coverage
instrument, and hash-verified locked archives. No committed result is rewritten.
Cached archives are copied; missing archives are downloaded only with --fetch.
All commands, stdout/stderr, environment versions, and comparisons are retained.

    .venv/bin/python tools/reproduce_heldout.py --out-dir /tmp/fr-heldout-new
    # Add --fetch on a clean checkout without the cached held-out archives.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELDOUT = ROOT / "paper/heldout-20261111"


def json_rows(path: Path) -> list[str]:
    return sorted(json.dumps(json.loads(line), sort_keys=True)
                  for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def compare_json(fresh: Path, frozen: Path, ignore: tuple[str, ...] = ()) -> list[str]:
    a = json.loads(fresh.read_text(encoding="utf-8"))
    b = json.loads(frozen.read_text(encoding="utf-8"))
    return [key for key in sorted(set(a) | set(b)) if key not in ignore and a.get(key) != b.get(key)]


def filter_vendor(source: Path, destination: Path) -> None:
    """Change the candidate frame, not linter inputs, as in the frozen sensitivity."""
    destination.mkdir()
    for path in sorted(source.glob("*.jsonl")):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and "/dspy/_vendor/" not in json.loads(line)["file"]]
        (destination / path.name).write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def run(out: Path, fetch: bool = False) -> int:
    out = out.resolve()
    if out.exists():
        raise ValueError(f"output directory already exists: {out}")
    out.mkdir(parents=True)
    logs = out / "logs"
    logs.mkdir()
    results: list[dict] = []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", FAILROUTE_PY=sys.executable)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    def command(name: str, args: list[str], cwd: Path = ROOT, source: Path | None = None) -> None:
        call_env = dict(env, PYTHONPATH=str(source or ROOT / "src"))
        (logs / f"{name}.command.json").write_text(json.dumps({
            "argv": args, "cwd": str(cwd), "PYTHONPATH": call_env["PYTHONPATH"]}, indent=2))
        with (logs / f"{name}.log").open("w", encoding="utf-8") as fh:
            p = subprocess.run(args, cwd=cwd, env=call_env, stdout=fh, stderr=subprocess.STDOUT,
                               timeout=7200, check=False)
        if p.returncode:
            raise RuntimeError(f"{name} exited {p.returncode}; see {logs / (name + '.log')}")

    def record(name: str, ok: bool, detail: str) -> None:
        results.append({"step": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        print(f"[{results[-1]['status']}] {name}: {detail}", flush=True)
        (out / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    try:
        versions = {name: importlib.metadata.version(name) for name in
                    ("ruff", "bandit", "pylint", "flake8", "flake8-bugbear")}
        versions.update(python=sys.version, interpreter=sys.executable)
        (out / "environment.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
        original = json.loads((HELDOUT / "comparison.json").read_text())
        commits = {"v0.8.0": original["environment"]["v080_tag_commit"],
                   "v0.9.1": original["environment"]["failroute_head"]}
        (out / "detector-commits.json").write_text(json.dumps(commits, indent=2))
        sandbox = out / "sandbox"
        (sandbox / "paper").mkdir(parents=True)
        shutil.copytree(ROOT / "tools", sandbox / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(HELDOUT / "heldout-lock.json", sandbox / "paper/corpus-lock.json")
        corpus = sandbox / "paper/corpus"
        corpus.mkdir()
        # Reconstruct from exact archives instead of copying possibly contaminated trees.
        sys.path.insert(0, str(ROOT / "tools"))
        from fetch_corpus import extract

        lock = json.loads((HELDOUT / "heldout-lock.json").read_text())
        for package in lock["packages"]:
            archive = corpus / package["archive"]
            archive.parent.mkdir(parents=True, exist_ok=True)
            cached = HELDOUT / "corpus" / package["archive"]
            if cached.is_file():
                shutil.copy2(cached, archive)
            elif fetch:
                with urllib.request.urlopen(package["url"], timeout=120) as response, archive.open("wb") as fh:
                    shutil.copyfileobj(response, fh)
            else:
                raise ValueError(f"missing cached archive {cached}; rerun with --fetch and a NEW output directory")
            if hashlib.sha256(archive.read_bytes()).hexdigest() != package["sha256"]:
                raise ValueError(f"archive hash mismatch: {archive}")
            extract(archive, corpus / package["extracted_to"])
        command("verify-corpus", [sys.executable, str(sandbox / "tools/fetch_corpus.py"),
                                  "--verify"], sandbox)
        record("corpus", True, "all locked archive and extracted-tree hashes verified")
        data = out / "results"
        data.mkdir()
        shutil.copy2(HELDOUT / "heldout-lock.json", data / "heldout-lock.json")
        shutil.copy2(HELDOUT / "PROTOCOL.sha256", data / "PROTOCOL.sha256")
        (data / "scripts").mkdir()
        shutil.copy2(HELDOUT / "scripts/analyze_heldout.py", data / "scripts/analyze_heldout.py")
        for version, commit in commits.items():
            # git archive does not register worktrees or change checkout metadata.
            archive = out / f"detector-{version}.tar"
            command(f"archive-{version}", ["git", "archive", "--format=tar", "--output", str(archive),
                                           commit, "src", "tools"])
            detector = out / f"detector-{version}"
            detector.mkdir()
            with tarfile.open(archive) as tf:
                # Archives contain only this repository's already trusted source.
                tf.extractall(detector, filter="data")
            (detector / "paper").mkdir()
            shutil.copy2(HELDOUT / "heldout-lock.json", detector / "paper/corpus-lock.json")
            (detector / "paper/corpus").symlink_to(corpus, target_is_directory=True)
            findings = data / f"findings-{version}"
            command(f"scan-{version}", [sys.executable, str(detector / "tools/rescan_corpus.py"),
                                       "--out", str(findings)], detector, detector / "src")
            fresh_names = sorted(p.name for p in findings.glob("*.jsonl"))
            frozen_names = sorted(p.name for p in (HELDOUT / f"findings-{version}").glob("*.jsonl"))
            equal = fresh_names == frozen_names and all(
                json_rows(findings / name) == json_rows(HELDOUT / f"findings-{version}" / name)
                for name in fresh_names)
            count = sum(len(json_rows(findings / name)) for name in fresh_names)
            record(f"scan-{version}", equal, f"{count} findings; every JSON field compared")
            filter_vendor(findings, data / f"findings-{version}-novendor")
            for suffix in ("", "-novendor"):
                target = data / f"coverage-{version}{suffix}.json"
                cmd = [sys.executable, str(sandbox / "tools/coverage_union.py"),
                       "--findings-dir", str(data / f"findings-{version}{suffix}"), "--out", str(target)]
                if not suffix:
                    cmd += ["--emit-per-finding", str(data / f"per-finding-{version}.jsonl")]
                command(f"coverage-{version}{suffix}", cmd, sandbox)
                diff = compare_json(target, HELDOUT / target.name, ("generated_at_utc", "findings_dir"))
                record(f"coverage-{version}{suffix}", not diff, f"differing keys: {diff}")
        equal = json_rows(data / "per-finding-v0.9.1.jsonl") == json_rows(HELDOUT / "per-finding-v0.9.1.jsonl")
        record("per-finding-v0.9.1", equal, "whole rows compared, including static predictions and empirical tool sets")
        command("analysis", [sys.executable, str(data / "scripts/analyze_heldout.py")], sandbox)
        diff = compare_json(data / "comparison.json", HELDOUT / "comparison.json", ("generated_utc", "environment"))
        record("analysis", not diff, f"all scientific fields compared; differing keys: {diff}")
        # analyze_heldout records the historical environment by construction. Preserve
        # its output for comparison; environment.json documents this run's actual tools.
        return int(any(row["status"] == "FAIL" for row in results))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            importlib.metadata.PackageNotFoundError) as exc:
        record("execution", False, str(exc))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--fetch", action="store_true", help="download absent archives from their exact locked URLs")
    args = parser.parse_args()
    try:
        return run(args.out_dir, args.fetch)
    except ValueError as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
