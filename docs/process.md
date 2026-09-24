# Author-led development with AI assistance

The idea for failroute originated with Yufeiyang Chen. He directs the project
and makes the key decisions, including the choices made across successive
manuscript revisions. Claude and other generative AI tools assist with
implementation, tests, refactoring, analysis, documentation, and drafting.
The author is responsible for the resulting claims and final manuscript.

The two recorded real-code labelling rounds were run by LLM agents. Their
agreement does not establish independent validation; the paper documents this
limit separately from the author's intellectual direction and decision-making.

## Checks on AI-assisted work

The executable checks are specified in [CI](../.github/workflows/ci.yml) and
[pyproject.toml](../pyproject.toml):

- Tests run across Linux, macOS, and Windows and the supported Python matrix.
- `tools/benchmark.py` checks explicit positive and negative fixture expectations.
  Passing this gate checks regressions against those expectations, not real-world
  defect precision or recall.
- `ruff`, strict `mypy`, the coverage floor, and the repository self-scan check
  implementation properties. Reviewed exceptions use `# failroute: ignore`.

Tests can reject an incorrect AI-generated implementation. They cannot establish
that a finding is a defect or identify who made a particular judgement.
Key decisions remain the author's responsibility, informed by code, checks,
comparisons, and the project's documented limitations.

## Triage before upstream reporting

Recorded triage of twelve findings in a well-maintained red-teaming framework
classified them as intentional contracts: decoder fallbacks, capability probes,
and existence checks. A skipped log line was cosmetic; no issue was filed for
that sample. In a different evaluation framework, a repeated bare-except
pattern was consolidated into one issue with a failure-consequence argument
and reproduction, rather than reported once per metric class.

These project outcomes illustrate the reporting standard: a detector match
enters a review queue. External reports need evidence of the wrong outcome and
a reproduction against the relevant upstream version. The purpose is to make the reports useful to maintainers, with evidence for
each claimed consequence.

## A development example: `silent-suppress`

The project added detection of `contextlib.suppress`, a context-manager form
of exception swallowing that a walker limited to `ExceptHandler` would miss.
Fixture expectations preceded that implementation and exposed false negatives;
the checks then passed after import resolution and opt-out handling were added.
An early draft also flagged cancellation suppression inconsistently with the
handler rules, and regression checks drove a correction across both syntaxes.
Later predicate changes and their negative results are described in the
[current paper](../paper/arxiv/main.pdf).

This sequence demonstrates how executable expectations constrain AI-assisted
implementation and make regressions reviewable.

## Reproduce and interpret

```console
pytest
python tools/benchmark.py
```

For the paper's corpus scans, baseline comparisons, and statistical analyses,
use [ARTIFACT.md](../paper/ARTIFACT.md). Fixture scores, LLM labels, and
confirmed failure mechanisms are different evidence; the paper keeps their
limits explicit. The original annotation files remain unchanged.
