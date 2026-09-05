#!/usr/bin/env python3
"""Measure which lint rules actually fire on which handler shapes.

`covered_by_for()` in src/failroute/rules/_shared.py infers, per finding, which lint
rules already point at that handler. It is a static inference, and V2 caught it
over-crediting: it named bandit:B110 and ruff:S110 for a literal
`except (ValueError, TypeError): pass`, and all four baselines return nothing on that
file. B110/S110 fire on *broad* handlers; the inference never looked at the caught
type.

This tool exists so the mapping is derived from measurement rather than from rule
documentation. It generates a probe module covering handler kind x body shape, runs
every linter in the paper's baseline set over it, attributes each hit to the case
whose function span contains it, and emits the matrix the detector's table must match.

Three traps this tool defends against, all of them hit by earlier batches:

* A linter that FAILS looks exactly like a linter that finds nothing if you only read
  stdout. Every invocation's exit code is recorded, and a non-zero exit with empty
  output is fatal rather than an empty hit set.
* ruff exits 2 on an invalid selector, so a typo silently empties the result. Every
  rule in the matrix has a positive control: a case that must trigger it. A rule with
  no hits anywhere fails the run instead of being recorded as "never fires".
* `flake8 --exclude` with a space in the pattern silently zeroes the output. This tool
  never passes --exclude.

The probe module is generated into a temporary directory and is NOT written into the
repository: it is a dense file of deliberate bare-except handlers, and the project's
CI self-scan runs the detector over the whole repo, so committing it would pollute
that gate. The measured matrix is the artefact; the probe is reproducible from this
file.

Usage:
    cd 新项目-failroute && PYTHONPATH=src .venv/bin/python tools/lint_mapping_probe.py
    PYTHONPATH=src .venv/bin/python tools/lint_mapping_probe.py --check-parity
Writes bench/lint-rule-mapping.json. With --check-parity it additionally runs the
detector's own covered_by over the same probe source and compares it with the measured
matrix case by case, exiting non-zero on any over- or under-credit; that is what the
claims ledger runs, so the shipped inference cannot drift from the measurement.
"""
import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "bench", "lint-rule-mapping.json")
PY = os.path.abspath(os.path.join(ROOT, ".venv", "bin", "python"))
if not os.path.exists(PY):
    PY = sys.executable

# Handler kinds. The detector's own classification has three classes (bare,
# catch-all-typed, narrow-typed); the probe splits them finer so that a linter which
# distinguishes BaseException from Exception, or a mixed tuple from a plain one, shows
# up in the matrix instead of being averaged away.
KINDS = [
    ("bare", "", "bare"),
    ("exception", "Exception", "catch_all_typed"),
    ("baseexception", "BaseException", "catch_all_typed"),
    ("mixed_tuple", "(Exception, ValueError)", "catch_all_typed"),
    ("narrow_single", "ValueError", "narrow_typed"),
    ("narrow_tuple", "(ValueError, TypeError)", "narrow_typed"),
    # Three forms that occur in the corpus and that the detector classifies by a
    # different route: its _handler_catches_base_exception bails out when any tuple
    # member is not a plain Name, so (Exception, asyncio.CancelledError) is treated as
    # NOT catch-all and loses the BLE001/W0718 credit. That is an error in the opposite
    # direction from the one V3 was called to fix, and it over-states novelty, so it has
    # to be measured rather than assumed away. A caught type that is a call expression
    # (the corpus has `except anyio.get_cancelled_exc_class():`) is not statically
    # resolvable at all and gets its own class.
    ("dotted_narrow", "asyncio.CancelledError", "narrow_typed"),
    ("dotted_mixed", "(Exception, asyncio.CancelledError)", "catch_all_typed"),
    ("call_expr", "make_exc()", "unresolved_type"),
    # The exact form the corpus contains and the detector mis-classifies: a tuple with
    # one statically unresolvable member and a plain `Exception`. _handler_exc_member_names
    # returns None as soon as any member is unresolvable, so the handler is treated as
    # narrow and loses its BLE001/W0718/S110 credit -- under-crediting the linters, which
    # over-states novelty. Three inspect_ai findings have this shape.
    ("call_mixed", "(make_exc(), Exception)", "catch_all_typed"),
    ("dotted_exception", "builtins.Exception", "catch_all_typed"),
]

# Body shapes, in the detector's own terms: empty (pass/...), continue-only, a returned
# constant, an assigned constant, and the discarded-comparison ("dead probe") shape that
# B015 points at.
BODIES = ["pass", "ellipsis", "continue", "return_none", "assign", "dead_probe"]

# Rules the detector's covered_by table names, plus SIM105 (which the V3 task list asks
# to audit even though the table does not currently credit it) and W0703 (pylint's
# broad-except, the analogue of ruff's BLE001 in the paper's baseline selection).
RUFF_SELECT = ["E722", "BLE001", "S110", "S112", "B015", "SIM105"]
# B001 is deliberately absent: it is a flake8-bugbear code and ruff rejects it with
# exit code 2 ("Unknown rule selector"), which aborts the run rather than matching
# nothing. Ruff's bare-except coverage comes from E722. bugbear:B001 is probed through
# flake8 below, which is where the detector's table says it comes from.
BANDIT_TESTS = ["B110", "B112"]
FLAKE8_SELECT = ["E722", "B001", "B015", "B017"]
PYLINT_ENABLE = ["W0702", "W0703", "W0705", "W0706", "W0718"]

# Which case must trigger each rule, so a dead selector cannot pass as "never fires".
POSITIVE_CONTROL = {
    "flake8:E722": ("bare", "pass"),
    "ruff:E722": ("bare", "pass"),
    "bugbear:B001": ("bare", "pass"),
    "pylint:W0702": ("bare", "pass"),
    "ruff:BLE001": ("exception", "pass"),
    "pylint:W0718": ("exception", "pass"),
    "bandit:B110": ("bare", "pass"),
    "ruff:S110": ("bare", "pass"),
    "bandit:B112": ("bare", "continue"),
    "ruff:S112": ("bare", "continue"),
    "bugbear:B015": ("narrow_single", "dead_probe"),
    "ruff:B015": ("narrow_single", "dead_probe"),
    "ruff:SIM105": ("bare", "pass"),
}


def case_name(kind_slug, body):
    return "case_%s_%s" % (kind_slug, body)


def render_case(kind_slug, exc, body):
    """One function holding exactly one construct, so hits attribute unambiguously."""
    name = case_name(kind_slug, body)
    guard = "a == 1" if body == "dead_probe" else "f()"
    if body == "pass":
        handler = "        pass"
    elif body == "ellipsis":
        handler = "        ..."
    elif body == "continue":
        # `continue` is only legal inside a loop, so this case wraps the try in one.
        return (
            "def %s():\n"
            "    for _ in range(3):\n"
            "        try:\n"
            "            f()\n"
            "        except%s:\n"
            "            continue\n"
            "    return None\n" % (name, (" " + exc) if exc else "")
        )
    elif body == "return_none":
        handler = "        return None"
    elif body == "assign":
        handler = "        out = None"
    elif body == "dead_probe":
        handler = "        out = False"
    else:
        raise AssertionError(body)
    tail = "    return out\n" if body in ("assign", "dead_probe") else ""
    head = "    out = None\n" if body in ("assign", "dead_probe") else ""
    return (
        "def %s():\n"
        "%s"
        "    try:\n"
        "        %s\n"
        "    except%s:\n"
        "%s\n"
        "%s" % (name, head, guard, (" " + exc) if exc else "", handler, tail)
    )


SUPPRESS_CASES = [
    ("case_suppress_narrow", "ValueError", "narrow_typed"),
    ("case_suppress_broad", "Exception", "catch_all_typed"),
]


def render_suppress(name, exc):
    return (
        "def %s():\n"
        "    with contextlib.suppress(%s):\n"
        "        f()\n"
        "    return None\n" % (name, exc)
    )


def build_probe():
    parts = [
        '"""Generated by tools/lint_mapping_probe.py -- do not edit or commit."""',
        "import asyncio",
        "import builtins",
        "import contextlib",
        "",
        "",
        "def f():",
        "    return 1",
        "",
        "",
        "def g(a):",
        "    return a",
        "",
        "",
        "def make_exc():",
        "    return ValueError",
        "",
        "",
    ]
    for kind_slug, exc, _cls in KINDS:
        for body in BODIES:
            parts.append(render_case(kind_slug, exc, body))
            parts.append("")
    for name, exc, _cls in SUPPRESS_CASES:
        parts.append(render_suppress(name, exc))
        parts.append("")
    return "\n".join(parts) + "\n"


def run(cmd, timeout=900):
    """Run a linter, refusing to treat a failed command as an empty hit set."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and not out:
        sys.exit(
            "error: %s exited %d with empty stdout -- a failed linter is not zero hits.\n"
            "stderr: %s" % (" ".join(str(c) for c in cmd[:6]), proc.returncode,
                            (proc.stderr or "").strip()[:600])
        )
    return proc.returncode, out, (proc.stderr or "").strip()


def collect(path):
    """{rule: set(lineno)} from all four linters, with exit codes recorded."""
    hits = defaultdict(set)
    rcs = {}

    rc, out, _ = run([PY, "-m", "ruff", "check", "--no-cache", "--isolated",
                      "--select", ",".join(RUFF_SELECT),
                      "--output-format", "json", path])
    rcs["ruff"] = rc
    for d in json.loads(out or "[]"):
        hits["ruff:" + d["code"]].add(d["location"]["row"])

    rc, out, _ = run([PY, "-m", "bandit", "-r", path, "-f", "json", "-q",
                      "-t", ",".join(BANDIT_TESTS)])
    rcs["bandit"] = rc
    for d in json.loads(out or "{}").get("results", []):
        hits["bandit:" + d["test_id"]].add(d["line_number"])

    rc, out, _ = run([PY, "-m", "flake8", "--select", ",".join(FLAKE8_SELECT),
                      "--format", "%(row)d\t%(code)s", path])
    rcs["flake8"] = rc
    dropped = 0
    for ln in (out or "").splitlines():
        row = ln.split("\t")
        if len(row) == 2 and row[0].strip().isdigit():
            code = row[1].strip()
            hits[("bugbear:" if code.startswith("B") else "flake8:") + code].add(int(row[0]))
        elif ln.strip():
            dropped += 1
    if dropped:
        print("  [warn] flake8: %d unparseable row(s) dropped" % dropped, file=sys.stderr)

    rc, out, _ = run([PY, "-m", "pylint", "--disable=all",
                      "--enable", ",".join(PYLINT_ENABLE),
                      "--output-format=json", "--persistent=n", path], timeout=1800)
    rcs["pylint"] = rc
    for d in json.loads(out or "[]"):
        # pylint's JSON carries both a symbol (bare-except) and a message id (W0702);
        # the detector's table names message ids, so collect symbols and map below.
        hits["pylint:" + d["symbol"]].add(d["line"])
    return hits, rcs


def symbol_to_code():
    """pylint JSON gives symbols (bare-except); the table names message ids (W0702)."""
    return {"bare-except": "W0702", "broad-except": "W0703", "duplicate-except": "W0705",
            "try-except-raise": "W0706", "broad-exception-caught": "W0718"}


def probe_pylint_alias(path):
    """Which ids does pylint emit when ONLY the retired W0703 is enabled?

    RQ1's baseline invokes pylint with ``W0702,W0703,W0705,W0706``. A reproducer who
    counts W0703 messages finds zero and would reasonably conclude the broad-except
    rule never ran. Over the corpus that exact selection emits 389 W0718 messages and
    no W0703: pylint 4.x accepts W0703 as an alias and reports under the renamed id.
    W0718 is deliberately NOT enabled here, so whatever comes out can only have come
    from the alias.
    """
    rc, out, _ = run([PY, "-m", "pylint", "--disable=all", "--enable=W0703",
                      "--output-format=json", "--persistent=n", path], timeout=1800)
    ids = defaultdict(int)
    for d in json.loads(out or "[]"):
        ids[d.get("message-id")] += 1
    return {"enabled": "W0703", "exit_code": rc, "emitted_message_ids": dict(sorted(ids.items()))}


def case_spans(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    spans = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("case_"):
            spans[node.name] = (node.lineno, node.end_lineno or node.lineno)
    return spans


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check-parity", action="store_true",
                    help="also run the detector's own covered_by over the same probe and "
                         "compare it with the measured matrix, case by case; exit non-zero "
                         "on any over- or under-credit")
    ap.add_argument("--keep", action="store_true", help="do not delete the generated probe")
    args = ap.parse_args()

    os.chdir(ROOT)
    if not os.path.exists(PY):
        sys.exit("error: interpreter missing: %s" % PY)
    for mod in ("ruff", "bandit", "flake8", "pylint"):
        rc, out, err = run([PY, "-m", mod, "--version"], timeout=120)
        if rc != 0:
            sys.exit("error: %s is unusable under %s (rc=%d): %s" % (mod, PY, rc, (out + err)[:300]))

    # Selector pre-flight. ruff is the one tool that rejects an unknown code loudly
    # (exit 2), so validate its selectors up front and name the bad code. bandit,
    # flake8 and pylint all silently ignore an unknown id -- a typo there reads as
    # "this rule never fires" -- so those are covered by POSITIVE_CONTROL below, which
    # fails the run if a rule that must fire on some case fires on none.
    bad = [c for c in RUFF_SELECT
           if run([PY, "-m", "ruff", "rule", c], timeout=120)[0] != 0]
    if bad:
        sys.exit("error: ruff does not recognise selector(s): %s" % ", ".join(bad))

    tmp = tempfile.mkdtemp(prefix="failroute-lintmap-")
    path = os.path.join(tmp, "lint_mapping_probe.py")
    src = build_probe()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)

    spans = case_spans(path)
    expected_cases = {case_name(k, b) for k, _, _ in KINDS for b in BODIES}
    expected_cases |= {n for n, _, _ in SUPPRESS_CASES}
    missing = expected_cases - set(spans)
    if missing:
        sys.exit("error: probe generation lost cases: %s" % sorted(missing))

    raw, rcs = collect(path)
    alias = probe_pylint_alias(path)
    sym = symbol_to_code()
    hits = defaultdict(set)
    for rule, lines in raw.items():
        if rule.startswith("pylint:"):
            hits["pylint:" + sym.get(rule.split(":", 1)[1], rule.split(":", 1)[1])] |= lines
        else:
            hits[rule] |= lines

    # attribute every hit to the case whose function span contains it
    per_case = defaultdict(set)
    unattributed = []
    for rule, lines in hits.items():
        for ln in lines:
            owner = [n for n, (a, b) in spans.items() if a <= ln <= b]
            if len(owner) == 1:
                per_case[owner[0]].add(rule)
            else:
                unattributed.append((rule, ln, owner))

    cls_of = {}
    for kind_slug, _exc, cls in KINDS:
        for body in BODIES:
            cls_of[case_name(kind_slug, body)] = (cls, body)
    for name, _exc, cls in SUPPRESS_CASES:
        cls_of[name] = (cls, "suppress")

    derived = defaultdict(set)
    for name, rules in per_case.items():
        key = cls_of[name]
        derived[key] |= rules
    # cases nothing fired on must still appear in the matrix, as an empty set
    for name, key in cls_of.items():
        derived.setdefault(key, set())

    controls = {}
    for rule, (kind_slug, body) in POSITIVE_CONTROL.items():
        controls[rule] = rule in per_case.get(case_name(kind_slug, body), set())
    dead = sorted(r for r, ok in controls.items() if not ok)
    # rules that fired nowhere at all are indistinguishable from a broken selector
    never = sorted(r for r in hits if not hits[r])

    # Finding-level parity, distinct from --check-parity's handler-level one: this reads
    # covered_by off real Finding objects, so it also catches a rule that computes the
    # facts correctly and then fails to propagate them into what it emits.
    _unused_shared, vocab = table_vocabulary()
    parity = []
    try:
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from failroute.analyzer import scan_source  # noqa: E402
        findings = scan_source(src)
        by_line = {}
        for f in findings:
            for name, (a, b) in spans.items():
                if a <= f.lineno <= b:
                    by_line.setdefault(name, []).append(f)
        for name, fs in sorted(by_line.items()):
            claimed = set()
            for f in fs:
                claimed |= set(f.covered_by or ())
            measured = per_case.get(name, set()) & vocab
            parity.append({"case": name, "class": cls_of[name][0], "body": cls_of[name][1],
                           "findings": len(fs),
                           "claimed": sorted(claimed),
                           "measured_in_vocabulary": sorted(measured),
                           "over_credit": sorted(claimed - measured),
                           "under_credit": sorted(measured - claimed)})
    except Exception as exc:  # pragma: no cover - detector import is optional here
        parity = [{"error": "%s: %s" % (type(exc).__name__, exc)}]

    out = {
        "generated_at_utc8": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "interpreter": PY,
        "probe_cases": len(spans),
        "linter_exit_codes": rcs,
        "pylint_w0703_alias": alias,
        "selectors": {"ruff": RUFF_SELECT, "bandit": BANDIT_TESTS,
                      "flake8": FLAKE8_SELECT, "pylint": PYLINT_ENABLE},
        "positive_controls": controls,
        "positive_controls_failed": dead,
        "rules_that_fired_nowhere": never,
        "unattributed_hits": [{"rule": r, "line": l, "owners": o} for r, l, o in unattributed],
        "derived": {"%s|%s" % k: sorted(v) for k, v in sorted(derived.items())},
        "per_case": {n: sorted(r) for n, r in sorted(per_case.items())},
        "detector_parity": parity,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    print("probe: %d cases, %d functions" % (len(spans), len(spans)))
    print("linter exit codes: %s" % rcs)
    print("pylint --enable=W0703 alone emits: %s (rc=%d)"
          % (alias["emitted_message_ids"] or "nothing", alias["exit_code"]))
    if "W0718" not in alias["emitted_message_ids"]:
        print("  🔴 W0703 no longer resolves to W0718 -- RQ1's pylint baseline "
              "description needs re-checking", file=sys.stderr)
    print("positive controls failed: %s" % (dead or "none"))
    print("rules that fired nowhere: %s" % (never or "none"))
    print("unattributed hits: %d" % len(unattributed))
    print()
    print("%-18s %-12s %s" % ("class", "body", "rules that actually fired"))
    for (cls, body), rules in sorted(derived.items()):
        print("%-18s %-12s %s" % (cls, body, ", ".join(sorted(rules)) or "(none)"))

    # The asymmetry the V3 fix turns on, printed per caught-type FORM rather than per
    # merged class, so a claim can assert it from a recomputation. bandit's B110/B112
    # are strictly narrower than ruff's S110/S112: gating all four on one "broad"
    # predicate would leave that difference in place.
    print()
    for body, pair in (("pass", ("bandit:B110", "ruff:S110")),
                       ("continue", ("bandit:B112", "ruff:S112"))):
        for rule in pair:
            kinds = [slug for slug, _exc, _cls in KINDS
                     if rule in per_case.get(case_name(slug, body), set())]
            print("FIRES_ON %s body=%s forms=%s" % (rule, body, ",".join(kinds) or "NONE"))
    for name, _exc, _cls in SUPPRESS_CASES:
        print("SUPPRESS %s rules=%s" % (name, ",".join(sorted(per_case.get(name, []))) or "NONE"))
    print()
    over = [p for p in parity if p.get("over_credit")]
    under = [p for p in parity if p.get("under_credit")]
    print("detector parity: %d findings-bearing cases, %d over-credit, %d under-credit"
          % (len([p for p in parity if "case" in p]), len(over), len(under)))
    for p in over[:10]:
        print("  OVER  %-32s claims %s but nothing fired" % (p["case"], p["over_credit"]))
    for p in under[:10]:
        print("  UNDER %-32s missing %s" % (p["case"], p["under_credit"]))
    print("\nwrote %s" % args.out)

    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("kept probe at %s" % path)

    rc = 0
    if dead:
        print("error: %d positive control(s) failed -- a dead selector reads as 'never fires'"
              % len(dead), file=sys.stderr)
        rc += 1
    if unattributed:
        print("error: %d hit(s) could not be attributed to a case" % len(unattributed),
              file=sys.stderr)
        rc += 1

    if args.check_parity:
        rc += check_parity(out["per_case"])
    return rc


TABLE_NAMES = (
    "_LINT_BY_BARE",
    "_LINT_BY_CATCH_ALL_TYPED",
    "_LINT_BY_PASS_BODY_BROAD",
    "_LINT_BY_PASS_BODY_BARE_OR_EXCEPTION",
    "_LINT_BY_CONTINUE_BODY_BROAD",
    "_LINT_BY_CONTINUE_BODY_BARE_OR_EXCEPTION",
    "_LINT_BY_DISCARDED_COMPARISON",
)


def table_vocabulary():
    """The set of lint rules the detector's tables can credit, read from the module.

    Both parity levels restrict themselves to this set. The probe measures more rules
    than the tables credit --- ruff SIM105 fires on every handler kind with a pass or
    ellipsis body, and pylint W0703 is an input alias reported as W0718 --- and neither
    is a defect in the table, so counting them as under-credit would misreport a
    deliberate decision as a bug.
    """
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import failroute.rules._shared as shared  # noqa: E402

    vocabulary = set()
    missing = []
    for name in TABLE_NAMES:
        val = getattr(shared, name, None)
        if val is None:
            missing.append(name)
        else:
            vocabulary |= set(val)
    if missing:
        sys.exit("error: _shared.py no longer defines: %s (rename TABLE_NAMES here too)"
                 % ", ".join(missing))
    return shared, vocabulary


def check_parity(per_case):
    """Compare the detector's actual ``covered_by`` against the measured matrix.

    Behavioural, not textual: this parses the same probe source, runs the production
    ``handler_facts_for`` over it, and compares each handler's ``covered_by`` with the
    rules the linters really fired on that case. Comparing source text would only prove
    the constants say something plausible; comparing behaviour proves the function that
    ships produces it.

    Restricted to the vocabulary the tables credit. The probe also measures ruff SIM105
    and pylint W0703, and neither belongs in the comparison: SIM105 is deliberately not
    credited (see the constants in _shared.py) and W0703 is an input alias that pylint
    reports as W0718.
    """
    shared, vocabulary = table_vocabulary()

    tree = ast.parse(build_probe())
    facts = shared.handler_facts_for(tree)

    over, under, checked = [], [], 0
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("case_"):
            continue
        handlers = [n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)]
        measured = set(per_case.get(node.name, [])) & vocabulary
        if not handlers:
            # a contextlib.suppress case: no handler, so nothing to credit, and the
            # measurement must agree that no linter fires on it either
            if measured:
                over.append((node.name, sorted(measured), []))
            checked += 1
            continue
        for handler in handlers:
            f = facts.get(id(handler))
            if f is None:
                print("error: handler_facts_for produced no facts for %s" % node.name,
                      file=sys.stderr)
                return 1
            claimed = set(f.covered_by)
            checked += 1
            if claimed - measured:
                over.append((node.name, sorted(claimed - measured), sorted(claimed)))
            if measured - claimed:
                under.append((node.name, sorted(measured - claimed), sorted(claimed)))

    print()
    print("parity check: %d handler(s)/case(s) compared against the measured matrix" % checked)
    print("  vocabulary credited by the tables: %s" % ", ".join(sorted(vocabulary)))
    if over:
        print("  OVER-CREDIT (%d) -- the detector names a rule that did not fire:" % len(over))
        for name, extra, full in over:
            print("    %-32s claims %s extra (full: %s)" % (name, extra, full))
    if under:
        print("  UNDER-CREDIT (%d) -- a rule fired that the detector does not name:" % len(under))
        for name, miss, full in under:
            print("    %-32s missing %s (full: %s)" % (name, miss, full))
    if not over and not under:
        print("  exact agreement on every case")
    return 1 if (over or under) else 0


if __name__ == "__main__":
    sys.exit(main())
