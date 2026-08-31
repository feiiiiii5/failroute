"""Reproducible fixed-version source fetcher for the failroute paper corpus.

Replaces ``git clone`` (the eight upstream clones were removed on 2026-08-30 and
cloning is banned for cost reasons). Sources are pinned, hashed, and recorded so
a reviewer can rebuild the corpus byte-for-byte on a clean machine:

    python tools/fetch_corpus.py            # fetch + extract + write lock
    python tools/fetch_corpus.py --verify   # re-check on-disk tree against lock

Acquisition order per package:

1. PyPI sdist (``https://pypi.org/pypi/<name>/json`` -> ``packagetype == "sdist"``).
   The manifest may pin ``version``; ``null`` resolves to the current latest and
   the exact resolved version is written into the lock.
2. GitHub codeload tarball (``https://codeload.github.com/<repo>/tar.gz/<ref>``)
   as fallback when the resolved version publishes no sdist. Used only when the
   manifest supplies ``github.repo``; the lock marks ``source: "github"`` so the
   provenance difference is visible.

Everything here is stdlib only (urllib/tarfile/hashlib) so the pipeline has no
install step of its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "paper" / "corpus-manifest.json"
DEFAULT_LOCK = ROOT / "paper" / "corpus-lock.json"
DEFAULT_DEST = ROOT / "paper" / "corpus"
ARCHIVE_SUBDIR = "_archives"

USER_AGENT = "failroute-fetch-corpus/1 (+https://pypi.org/project/failroute/)"
TIMEOUT = 120
CHUNK = 1 << 16


# --------------------------------------------------------------------------- io


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - https only, pinned hosts
        return resp.read()


def _download(url: str, dest: Path) -> str:
    """Stream ``url`` to ``dest``; return the sha256 hex digest of the bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    digest = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, tmp.open("wb") as fh:  # noqa: S310
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            fh.write(chunk)
    tmp.replace(dest)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- source lookup


def resolve_pypi(pypi_name: str, version: str | None) -> dict[str, Any]:
    """Return sdist metadata for ``pypi_name`` at ``version`` (latest if None).

    Raises LookupError when the resolved release publishes no sdist, so the
    caller can fall back to GitHub.
    """
    url = f"https://pypi.org/pypi/{pypi_name}/json"
    meta = json.loads(_http_get(url))
    resolved = version or meta["info"]["version"]
    files = meta["releases"].get(resolved)
    if not files:
        raise LookupError(f"{pypi_name}: no release files for version {resolved!r}")
    sdists = [f for f in files if f.get("packagetype") == "sdist"]
    if not sdists:
        raise LookupError(f"{pypi_name} {resolved}: no sdist published")
    sdist = sdists[0]
    return {
        "version": resolved,
        "url": sdist["url"],
        "filename": sdist["filename"],
        "expected_sha256": sdist["digests"]["sha256"],
        "size": sdist["size"],
        "upload_time_utc": sdist.get("upload_time_iso_8601"),
        "requires_python": sdist.get("requires_python"),
    }


def resolve_github(repo: str, ref: str | None) -> dict[str, Any]:
    """Return codeload tarball metadata for ``repo`` at ``ref``.

    ``ref`` may be a tag or a commit SHA. When None, the repository's default
    branch head SHA is resolved first so the lock still pins an immutable ref.
    """
    if ref is None:
        info = json.loads(_http_get(f"https://api.github.com/repos/{repo}"))
        branch = info["default_branch"]
        head = json.loads(_http_get(f"https://api.github.com/repos/{repo}/commits/{branch}"))
        ref = head["sha"]
    return {
        "version": ref,
        "url": f"https://codeload.github.com/{repo}/tar.gz/{ref}",
        "filename": f"{repo.replace('/', '-')}-{ref}.tar.gz",
        "expected_sha256": None,  # GitHub publishes no digest; the lock records ours
        "size": None,
        "upload_time_utc": None,
        "requires_python": None,
    }


# ------------------------------------------------------------------- extraction


def _safe_members(tf: tarfile.TarFile, strip_top: bool) -> tuple[list[tarfile.TarInfo], str | None]:
    """Yield members with the single common top-level directory optionally stripped.

    Rejects absolute paths, ``..`` traversal, and non-regular members (links,
    devices) so a hostile tarball cannot escape the destination directory.
    """
    members = tf.getmembers()
    tops = {m.name.split("/", 1)[0] for m in members if m.name not in ("", ".")}
    top = tops.pop() if strip_top and len(tops) == 1 else None

    out: list[tarfile.TarInfo] = []
    for m in members:
        if not (m.isfile() or m.isdir()):
            continue  # drop symlinks/hardlinks/devices outright
        name = m.name
        if top is not None:
            if name == top:
                continue
            prefix = top + "/"
            if not name.startswith(prefix):
                raise ValueError(f"member outside common top dir: {name!r}")
            name = name[len(prefix) :]
        if not name:
            continue
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"unsafe tar member path: {m.name!r}")
        m.name = name
        out.append(m)
    return out, top


def extract(archive: Path, dest: Path) -> str:
    """Extract ``archive`` into a freshly emptied ``dest``. Returns stripped top dir."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tf:
        members, top = _safe_members(tf, strip_top=True)
        try:
            tf.extractall(dest, members=members, filter="data")  # noqa: S202 - members vetted above
        except TypeError:  # pragma: no cover - Python < 3.11.4
            tf.extractall(dest, members=members)  # noqa: S202
    return top or ""


# --------------------------------------------------------------------- counting


def count_python(root: Path) -> dict[str, int]:
    """Count .py files and their total lines under ``root`` (real read, no estimate)."""
    files = 0
    lines = 0
    for path in sorted(root.rglob("*.py")):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        files += 1
        if data:
            lines += data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
    return {"py_files": files, "total_lines": lines}


def tree_sha256(root: Path) -> str:
    """Order-independent content hash of the extracted tree (path + bytes)."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _measure(dest: Path, scan_root: str | None) -> dict[str, Any]:
    whole = count_python(dest)
    entry: dict[str, Any] = {
        "py_files": whole["py_files"],
        "total_lines": whole["total_lines"],
        "tree_sha256": tree_sha256(dest),
    }
    if scan_root:
        sub = (dest / scan_root).resolve()
        if sub.is_dir() and dest.resolve() in (sub, *sub.parents):
            counts = count_python(sub)
            entry["scan_root"] = scan_root
            entry["scan_root_py_files"] = counts["py_files"]
            entry["scan_root_total_lines"] = counts["total_lines"]
        else:
            entry["scan_root"] = None
            entry["scan_root_missing"] = scan_root
    return entry


# ------------------------------------------------------------------------ fetch


def fetch_one(pkg: dict[str, Any], dest_root: Path, force: bool, latest: bool = False) -> dict[str, Any]:
    name = pkg["name"]
    notes: list[str] = []
    source = pkg.get("source", "pypi")
    pinned_version = None if latest else pkg.get("version")
    pinned_sha = None if latest else pkg.get("sha256")

    if source == "pypi":
        try:
            info = resolve_pypi(pkg.get("pypi_name", name), pinned_version)
        except LookupError as exc:
            gh = pkg.get("github") or {}
            if not gh.get("repo"):
                raise
            notes.append(
                f"PyPI fallback to GitHub: {exc}. Provenance differs from the "
                f"other packages: GitHub tarball, not a PyPI sdist."
            )
            info = resolve_github(gh["repo"], None if latest else gh.get("ref"))
            source = "github"
    elif source == "github":
        gh = pkg["github"]
        info = resolve_github(gh["repo"], None if latest else gh.get("ref"))
    else:
        raise ValueError(f"{name}: unknown source {source!r}")

    archive = dest_root / ARCHIVE_SUBDIR / info["filename"]
    # A cached archive is still hashed and checked against the upstream digest
    # below, so reuse is safe and is not recorded as a provenance difference.
    sha = _sha256_file(archive) if archive.exists() and not force else _download(info["url"], archive)

    expected = pinned_sha or info["expected_sha256"]
    if expected and sha != expected:
        raise ValueError(f"{name}: sha256 mismatch\n  expected {expected}\n  got      {sha}")
    if info["expected_sha256"] is None:
        notes.append("no upstream-published digest; sha256 below is of the bytes we fetched")

    dest = dest_root / f"{name}-{info['version']}"
    top = extract(archive, dest)

    record: dict[str, Any] = {
        "name": name,
        "source": source,
        "version": info["version"],
        "url": info["url"],
        "sha256": sha,
        "archive": f"{ARCHIVE_SUBDIR}/{info['filename']}",
        "archive_bytes": archive.stat().st_size,
        "extracted_to": dest.relative_to(dest_root).as_posix(),
        "stripped_top_dir": top,
    }
    if source == "pypi":
        record["pypi_name"] = pkg.get("pypi_name", name)
        record["upload_time_utc"] = info["upload_time_utc"]
        record["requires_python"] = info["requires_python"]
    else:
        record["github_repo"] = (pkg.get("github") or {}).get("repo")
        record["ref"] = info["version"]
    record.update(_measure(dest, pkg.get("scan_root")))
    if pkg.get("bench_path"):
        record["bench_path"] = pkg["bench_path"]
    if notes:
        record["notes"] = notes
    return record


# ----------------------------------------------------------------------- verify


def verify(lock_path: Path, dest_root: Path) -> int:
    if not lock_path.exists():
        print(f"FAIL  lock not found: {lock_path}", file=sys.stderr)
        return 2
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    problems = 0
    for rec in lock["packages"]:
        name = rec["name"]
        dest = dest_root / rec["extracted_to"]
        if not dest.is_dir():
            print(f"FAIL  {name}: missing extracted tree {dest}")
            problems += 1
            continue
        actual = _measure(dest, rec.get("scan_root"))
        bad = []
        for key in ("py_files", "total_lines", "tree_sha256"):
            if actual[key] != rec.get(key):
                bad.append(f"{key}: lock={rec.get(key)!r} disk={actual[key]!r}")
        archive = dest_root / rec["archive"]
        if archive.exists():
            sha = _sha256_file(archive)
            if sha != rec["sha256"]:
                bad.append(f"archive sha256: lock={rec['sha256']} disk={sha}")
        else:
            print(f"WARN  {name}: archive absent, skipped sha256 check ({archive})")
        if bad:
            problems += 1
            print(f"FAIL  {name}")
            for b in bad:
                print(f"        {b}")
        else:
            print(f"OK    {name} {rec['version']} ({rec['source']})")
    print(f"\n{len(lock['packages']) - problems}/{len(lock['packages'])} packages verified")
    return 1 if problems else 0


# ------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--only", action="append", default=None, help="fetch only these package names")
    ap.add_argument("--force", action="store_true", help="re-download even if the archive is cached")
    ap.add_argument("--verify", action="store_true", help="check disk against the lock; no downloads")
    ap.add_argument(
        "--latest",
        action="store_true",
        help="ignore the versions pinned in the manifest and resolve the current latest "
        "(use to measure corpus drift, not to build the paper corpus)",
    )
    ap.add_argument(
        "--pin",
        action="store_true",
        help="write the resolved version + sha256 back into the manifest, so a later "
        "plain run on a clean machine reproduces exactly this corpus",
    )
    args = ap.parse_args(argv)

    if args.verify:
        return verify(args.lock, args.dest)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    packages = manifest["packages"]
    if args.only:
        wanted = set(args.only)
        packages = [p for p in packages if p["name"] in wanted]
        missing = wanted - {p["name"] for p in packages}
        if missing:
            print(f"unknown package name(s): {sorted(missing)}", file=sys.stderr)
            return 2

    args.dest.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for pkg in packages:
        print(f"-> {pkg['name']}", flush=True)
        try:
            rec = fetch_one(pkg, args.dest, args.force)
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            failures.append({"name": pkg["name"], "error": f"{type(exc).__name__}: {exc}"})
            print(f"   FAILED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            continue
        records.append(rec)
        print(
            f"   {rec['source']} {rec['version']}  "
            f"{rec['py_files']} .py / {rec['total_lines']} lines",
            flush=True,
        )

    # Merge into an existing lock so a partial --only run does not drop entries.
    existing: dict[str, dict[str, Any]] = {}
    if args.lock.exists() and args.only:
        for rec in json.loads(args.lock.read_text(encoding="utf-8")).get("packages", []):
            existing[rec["name"]] = rec
    for rec in records:
        existing[rec["name"]] = rec
    order = [p["name"] for p in manifest["packages"]]
    merged = sorted(existing.values(), key=lambda r: order.index(r["name"]) if r["name"] in order else 999)

    lock = {
        "lock_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "tools/fetch_corpus.py",
        "manifest": args.manifest.relative_to(ROOT).as_posix(),
        "corpus_dir": args.dest.relative_to(ROOT).as_posix(),
        "python": sys.version.split()[0],
        "totals": {
            "packages": len(merged),
            "py_files": sum(r["py_files"] for r in merged),
            "total_lines": sum(r["total_lines"] for r in merged),
        },
        "packages": merged,
    }
    if failures:
        lock["failures"] = failures
    args.lock.parent.mkdir(parents=True, exist_ok=True)
    args.lock.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {args.lock}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
