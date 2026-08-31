# Annotation Protocol: Is this failure-routing finding a defect?

**Version 1.0 — 2026-08-30**

This document defines the decision procedure used to label `failroute` findings in the
empirical study. It is written so that a second annotator, working independently and
seeing only the finding plus its source context, reaches the same label.

The protocol is itself a contribution of the study: the interesting question is not
*"can a tool find `except: pass`"* — it trivially can — but **"when does suppressing a
failure actually constitute a defect?"** That question has not, to our knowledge, been
given an operational answer.

---

## 1. Labels

| Label | Meaning |
|---|---|
| **TP** — true defect | The construct converts a failure into a result that a caller cannot distinguish from success, and this is not what the surrounding code intends. |
| **IC** — intentional contract | The suppression is deliberate and defensible given the surrounding code. The behaviour is what a competent maintainer would want. |
| **UND** — undecidable | The available context is insufficient to decide. Must not be forced into TP or IC. |

`UND` is a first-class outcome. Forcing a label when the context does not support one is
the main way an annotation study becomes worthless.

---

## 2. What you are given

For each finding:

- `repo`, `file`, `lineno`, `rule`
- 15 lines of source before and 15 after
- the enclosing function signature

If the label depends on information outside that window (for example, whether the
caller checks a sentinel), the answer is **UND**. Do not guess about unseen code.

---

## 3. Decision procedure

Apply the gates **in order**. The first gate that fires determines the label.

### Gate 0 — Is the construct actually on a failure path?

If the `except` / `suppress` block cannot be entered by a genuine operational failure
(for example, it guards an expression that cannot raise), the finding is about dead code,
not failure routing.

→ **IC**, note `dead-handler`.

### Gate 1 — Is the exception class narrow *and* matched to a known-benign condition?

A narrow catch that names a condition the code is legitimately probing for:

```python
try:
    import orjson                      # optional dependency
except ImportError:
    orjson = None
```

Canonical benign pairs: `ImportError` for optional dependencies · `FileNotFoundError`
for cache/optional-file misses · `AttributeError` for capability probing ·
`KeyError` for optional-key lookup · `NotImplementedError` for optional backend methods ·
`asyncio.CancelledError` / `KeyboardInterrupt` / `StopIteration` for control-flow absorption.

→ **IC**, note `narrow-benign`.

⚠️ A **bare** `except:` or `except Exception:` never satisfies this gate, even if the
comment claims a specific cause. The claim must be in the exception class, not the prose.

### Gate 2 — Does any signal escape?

Does the handler do at least one of:
- re-raise (bare `raise`, or raise a wrapping exception)
- log at **WARNING or above** (`DEBUG`/`INFO` does **not** count — it is not seen in production)
- increment a metric / emit telemetry / set an error flag on a returned object
- return a value the caller is documented to check (a sentinel with a checked contract
  visible in the window)

→ if yes, **IC**, note `signal-escapes` + which signal.

⚠️ `logger.debug(...)` alone → continue to Gate 3. Debug logging is the most common way a
silent failure *looks* handled while remaining invisible.

### Gate 3 — Is the suppressed operation load-bearing for the function's contract?

Read the function signature and name. Ask: **if this operation silently did nothing, would
the function still be doing what its name promises?**

- `get_score()` / `evaluate()` / `validate()` / `load()` / `fetch()` — the operation *is*
  the contract → load-bearing
- `_cleanup()` / `close()` / `shutdown()` / `_emit_telemetry()` / `_record_metric()` —
  best-effort by nature → not load-bearing

If **not** load-bearing → **IC**, note `best-effort-path`.

### Gate 4 — Can the caller distinguish the failure outcome from a legitimate one?

This is the decisive gate. Compare the value produced on the failure path against the
values the function legitimately produces.

- Handler returns `0.0` from a scoring function whose valid range includes `0.0` →
  **indistinguishable** → **TP**
- Handler returns `[]` from a search function where "no results" is a legitimate outcome →
  **indistinguishable** → **TP**
- Handler falls through to an implicit `None` from a function whose other paths return
  objects → **indistinguishable only if `None` is not the documented absent-value** →
  usually **TP**
- Handler returns a distinct sentinel the caller must check (`_MISSING`, `Err(...)`,
  `None` where the signature is `Optional[X]` and `None` means "absent") →
  **distinguishable** → **IC**

If you cannot determine the function's legitimate value range from the window → **UND**.

### Gate 5 — Default

If no gate above resolves it: **UND**.

---

## 4. Worked examples

### 4.1 TP — evaluation score

```python
def compute_relevance(self, question, answer):
    try:
        return self._judge.score(question, answer)
    except Exception:
        return 0.0
```

Gate 1: `except Exception` — not narrow. Gate 2: no signal. Gate 3: `compute_relevance`
is entirely about producing the score — load-bearing. Gate 4: `0.0` is inside the valid
score range; a caller aggregating scores cannot tell a judge outage from a genuinely
irrelevant answer. → **TP**.

### 4.2 IC — capability probing

```python
try:
    self.system_prompt = model.get_system_prompt()
except AttributeError:
    self.system_prompt = ""
```

Gate 1 fires: `AttributeError` is the canonical capability-probe class, and the
alternative value is a documented empty default. → **IC**, `narrow-benign`.

⚠️ Note the contrast: if this were `except:` (bare), Gate 1 would **not** fire, and the
finding would proceed to Gate 3/4 and likely land on **TP** — because a misconfigured
model would silently run under an empty prompt. This pair is exactly why the exception
class, not the intent, is the discriminator.

### 4.3 IC — best-effort teardown

```python
def _close_transport(self):
    try:
        self._sock.close()
    except OSError:
        pass
```

Gate 1: `OSError` on close is a known-benign condition. → **IC**. (Gate 3 would also
resolve it: `_close_transport` is a teardown path.)

### 4.4 UND — contract not visible

```python
def _resolve(self, ref):
    try:
        return self._registry[ref]
    except KeyError:
        return None
```

Gate 1: `KeyError` on a registry lookup *looks* like optional-key lookup, but whether
`None` is a legitimate "not registered" answer or a silent corruption depends on the
callers, which are not in the window. → **UND**.

---

## 5. Annotator rules

1. **Label from the window only.** If you need the caller, the label is `UND`.
2. **Do not run the tool's own reasoning back on itself.** The rule name (`silent-fallback`
   etc.) tells you what pattern matched; it is **not evidence** that the pattern is a defect.
3. **Do not consult the upstream repository's issue tracker or git history.** The study
   measures what is decidable from the code.
4. **Record the gate number that fired** for every finding. A label without a gate is
   not usable.
5. **One line of reasoning per finding**, stating the specific evidence — not a restatement
   of the gate.

---

## 6. Reporting requirements

Every reported figure must carry:

- **Which corpus** — the pinned-source snapshot ID, not "the repos"
- **Which rules** — per-rule precision, never a single blended number across rules with
  very different base rates
- **UND rate** — reported separately; precision computed as `TP / (TP + IC)` with the
  `UND` count stated alongside, never silently dropped
- **Who annotated** — see §7

---

## 7. 🔴 Disclosure requirement (non-negotiable)

If any label in a reported figure was produced by an automated annotator (an LLM), the
paper **must** state this explicitly wherever the figure appears, and must **not**:

- describe the resulting agreement statistic as *human* inter-rater agreement
- describe automated annotators as *independent* in the sense used for human raters
  (they share training data and failure modes)
- omit the adjudication procedure

The defensible framing is: *"candidate findings were labelled by N automated annotators
applying the protocol in §3 independently; the agreement statistic is reported as a measure
of protocol determinacy, not of human validation; all disagreements and a random sample of
agreements were adjudicated by the author."*

Anything stronger than that is a misrepresentation and invalidates the study.

---

## 8. Change log

- **1.0 (2026-08-30)** — initial version. Gates 0–5, four worked examples, disclosure
  requirement.
