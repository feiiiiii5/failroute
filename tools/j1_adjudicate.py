#!/usr/bin/env python3
"""J1: apply the diff-read re-adjudication of the 52 title-screened rows.

Every merged PR previously excluded from the recall denominator by reading its
title only is re-judged from its actual diff (fetched by tools/j1_diff_screen.py
into /tmp/j1, metadata saved as paper/j1-diff-meta.json). Each judgement is
recorded in the ledger note with a reason and the merge-commit sha prefix, so
every family exclusion is traceable to a commit.

Family criterion applied (same operational reading as the H1 audit, which
already counted non-handler cases such as PyRIT#2466 'silent list filtering'):
an underlying error condition / anomalous input is converted into a
success-shaped result with no signal. Generic computation bugs with no error
condition being silenced are NOT family; fixes that make failures LOUDER
(raise/warn/validation) are NOT family; fixes that ADD a deliberate contract
are NOT family.

Result: 49 maintain no; 3 flip to yes (unstructured#4438, PyRIT#2309,
truera/trulens#2653). Denominator moves 11 -> 14, numerator 2 -> 3.

Usage: python3 tools/j1_adjudicate.py   (idempotent)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "paper" / "merged-pr-recall.csv"
META = ROOT / "paper" / "j1-diff-meta.json"
TMP_META = Path("/tmp/j1/meta.json")

FLIPS = {
    ("Unstructured-IO/unstructured", "4438"): (
        "6d383401fbdede725cabd671ef9c4b0c5692c2fc",
        "unstructured/file_utils/filetype.py",
        "",
        "no",
        "diff-read J1 FLIP: pre-fix decoded file-like objects with errors=\"ignore\", "
        "silently stripping undecodable characters into a corrupt-but-success-shaped "
        "text_head (issue #4434; diff's own words: \"silently stripped\"); decode-failure "
        "condition silenced without a handler -> non-handler family shape (merge 104b585d4e84)",
    ),
    ("microsoft/PyRIT", "2309"): (
        "60d8abc3218a60e7c1d2acd969e3f0bcea010af4",
        "pyrit/converter/braille_converter.py",
        "",
        "no",
        "diff-read J1 FLIP: unmapped braille symbols were silently dropped, corrupting the "
        "encoded prompt (\"a@b.com\" -> \"ab.com\"); silent drop of anomalous input, no handler "
        "-> non-handler family shape; parallels audit precedent PyRIT#2466 (merge 446e47b60d2f)",
    ),
    ("truera/trulens", "2653"): (
        "34e10d97630b2f843b35e8a852d2a368000779ab",
        "src/feedback/trulens/feedback/llm_provider.py",
        "src/feedback/trulens/feedback/llm_provider.py:265",
        "yes",
        "diff-read J1 FLIP: pre-fix silently normalized out-of-scale JSON scores — "
        "(raw-min)/(max-min) with no range check plus except(TypeError,ValueError): "
        "normalized_score=-1.0; validation failure became a success-shaped score; failroute "
        "flags the pre-fix handler at :265 (no-action) (merge 9f013f23a54a)",
    ),
}

NO_REASONS = {
    "unionai-oss/pandera#2454": "check_input decorator signature introspection; ValueError raised explicitly; no error condition silenced",
    "EvolvingLMMs-Lab/lmms-eval#1472": "video-frame dispatch feature (is_qwen3_vl flag); no failure silenced",
    "cvs-health/uqlm#457": "config-mutation fix (prompts_in_nli); no error condition silenced",
    "microsoft/PyRIT#2471": "default-value registry lookup semantics; no failure silenced",
    "griptape-ai/griptape#2276": "usage-delta accumulation arithmetic; no error condition silenced",
    "EleutherAI/lm-evaluation-harness#4039": "answer-normalization string logic (comma strip); wrong computation, no error condition silenced",
    "EleutherAI/lm-evaluation-harness#4037": "sqrt-normalization string logic; wrong computation, no error condition silenced",
    "EleutherAI/lm-evaluation-harness#4035": "ADDs an intentional FileNotFoundError swallow (idempotent delete); fix adds a contract, does not remove a silenced failure",
    "microsoft/PyRIT#2467": "GCG typed-state refactor; exceptions still propagate (state cleared on raise); no failure silenced",
    "letta-ai/letta-code#3977": "TypeScript files; out of language scope",
    "rhesis-ai/rhesis#2574": "migration advisory lock; handlers re-raise or log; failure handling made louder, not silenced",
    "rhesis-ai/rhesis#2573": "cache-token inclusion in usage extraction; None input returns documented zeroes; no error condition silenced",
    "msoedov/agentic_security#329": "p95 latency percentile computation; statistics fix",
    "msoedov/agentic_security#328": "circuit-breaker half-open state machine; failures still trip the breaker (visible)",
    "cvs-health/uqlm#451": "time.sleep -> asyncio.sleep in async paths; blocking fix, failures still raised",
    "rhesis-ai/rhesis#2501": "TSX frontend; out of language scope",
    "rhesis-ai/rhesis#2500": "enforces test-set type with explicit ValueError/TestSetInaccessibleError; fix makes failure loud",
    "UKGovernmentBEIS/inspect_ai#4905": "dataset-choices parsing drops empty strings from trailing commas; parse normalization, no error condition silenced",
    "rhesis-ai/rhesis#2498": "TSX styling; out of language scope",
    "rhesis-ai/rhesis#2497": "k8s secrets manifests; configuration, not code",
    "rhesis-ai/rhesis#2495": "sorting feature; no failure silenced",
    "Arize-ai/openinference#3565": "instrumentor restores constructors on uninstrument; state restoration, no error condition silenced",
    "Arize-ai/openinference#3563": "same shape as #3565 (portkey); state restoration",
    "Tencent/AI-Infra-Guard#539": "path containment via commonpath; security correctness, failures raise",
    "microsoft/PyRIT#2399": "NatoConverter word-boundary logic; raises ValueError on unsupported type (visible)",
    "UKGovernmentBEIS/inspect_evals#2132": "metric-granularity fix (attempt-level cerr); NaN sentinel is documented, no error condition silenced",
    "run-llama/llama_index#22527": "adds explicit ValueError validation before the AWS call; fix makes failure loud",
    "UKGovernmentBEIS/inspect_evals#2055": "YAML asset config; not code",
    "pydantic/pydantic-ai#6929": "parameter-name fix per model family (max_tokens); no failure silenced",
    "future-agi/future-agi#1862": "JSX frontend; out of language scope",
    "Tencent/AI-Infra-Guard#510": "TSX layout; out of language scope",
    "rhesis-ai/rhesis#2280": "Redis retry cooldown replacing a permanent latch; degraded state logged (warning), failure visible; recovery fix",
    "unionai-oss/pandera#2429": "Optional-field nullable inference; added defensive except/pass is part of the feature; defect was wrong nullability",
    "unionai-oss/pandera#2420": "scalar groupby keys accepted (typing); pre-fix raised",
    "UKGovernmentBEIS/inspect_ai#4614": "data-URI recognition; parse coverage, no error condition silenced",
    "UKGovernmentBEIS/inspect_ai#4612": "string-to-bool coercion for YAML; data typing",
    "UKGovernmentBEIS/inspect_ai#4610": "fix explicitly skips all-NA groups to avoid a crash; pre-fix crashed loudly; fix adds a documented skip",
    "truera/trulens#2617": "dashboard tag splitting; frontend util",
    "trailofbits/fickling#299": "Severity hashability; trivial fix",
    "trailofbits/fickling#298": "IndexError fix warns on unidentified format; failure surfaced via warning/ValueError",
    "vllm-project/vllm-metal#540": "documentation only",
    "Ishannaik/agent-sweep#145": "SARIF schema validation test; test feature",
    "dottxt-ai/outlines#1933": "dict-mutation fix across calls; state bug, no error condition silenced",
    "rhesis-ai/rhesis#2177": "TSX frontend state; out of language scope (silently-discarded UI fields are React state, not Python failure-routing)",
    "rhesis-ai/rhesis#2176": "dead-code removal / DB migration; chore",
    "langwatch/langwatch#5739": "TypeScript; out of language scope",
    "langwatch/langwatch#5738": "TypeScript; out of language scope",
    "rhesis-ai/rhesis#2156": "TSX modal; out of language scope",
    "NVIDIA/garak#1942": "UX: probe name in progress bar",
}


def main() -> int:
    if not CSV.is_file():
        sys.exit(f"error: missing {CSV}")
    if TMP_META.is_file() and not META.is_file():
        META.write_text(TMP_META.read_text(), encoding="utf-8")
    if not META.is_file():
        sys.exit("error: paper/j1-diff-meta.json missing (run tools/j1_diff_screen.py first)")
    meta = json.load(open(META))

    import csv as _csv
    import io

    buf = io.StringIO(CSV.read_text(encoding="utf-8"))
    records = list(_csv.DictReader(buf))
    done = sum(1 for r in records if "diff-read J1" in r["note"])
    if done == 52:
        yes = sum(1 for r in records if r["belongs_to_family"] == "yes")
        print(f"already applied: 52 diff-read J1 rows; family rows={yes}")
        return 0
    n_ts = n_flip = 0
    for r in records:
        key = f"{r['repo']}#{r['pr_number']}"
        if (r["repo"], r["pr_number"]) in FLIPS:
            sha, file, line, detected, note = FLIPS[(r["repo"], r["pr_number"])]
            r["belongs_to_family"] = "yes"
            r["pre_fix_sha"] = sha
            r["file"] = file
            r["line"] = line
            r["detected"] = detected
            r["rule_matched"] = "no-action" if detected == "yes" else ""
            r["note"] = note
            n_flip += 1
        elif "title-screened" in r["note"]:
            if key not in NO_REASONS:
                sys.exit(f"error: no J1 reason recorded for {key}")
            m = meta.get(key, {})
            sha = (m.get("merge_commit_sha") or "")[:10]
            if not sha:
                sys.exit(f"error: no merge sha in meta for {key}")
            r["note"] = f"diff-read J1: {NO_REASONS[key]} (merge {sha})"
            n_ts += 1
    if n_ts != 49 or n_flip != 3:
        sys.exit(f"error: expected 49 no-updates + 3 flips, got {n_ts} + {n_flip}")

    out = io.StringIO()
    w = _csv.DictWriter(out, fieldnames=records[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(records)
    CSV.write_text(out.getvalue(), encoding="utf-8")
    yes = sum(1 for r in records if r["belongs_to_family"] == "yes")
    ts_left = sum(1 for r in records if "title-screened" in r["note"])
    print(f"updated: 49 maintained-no upgraded to diff-read, 3 flipped; family rows={yes}; title-screened left={ts_left}")
    # 16 = 13 pre-J1 family rows (11 recall-audited + 2 recall-excluded) + 3 flips
    return 0 if ts_left == 0 and yes == 16 else 1


if __name__ == "__main__":
    raise SystemExit(main())
