# Merged-PR location matching protocol (revised tooling)

The frozen `paper/merged-pr-recall.csv` and associated manuscript ratios are historical evidence. They were produced with a removed-lines-only candidate-site selector and manual review. This revised driver is an exploratory location-matching tool. Its output is **not semantic defect detection or a new recall estimate**, and must not be substituted for those historical values without a separately reviewed re-evaluation.

## Base-side sites

- Use the merge commit's first parent as the pre-fix snapshot. This convention requires checking the repository's merge strategy: for rebased PRs, the first parent of the reported merge commit need not precede the entire PR. The driver does not resolve that ambiguity automatically.
- Parse each unified diff's old (`--- a/...`) path. Renamed Python files are fetched using their old name. Deleted Python files remain eligible. New files (`--- /dev/null`) have no pre-fix site and are excluded.
- Deleted lines contribute their exact old-file line numbers.
- A contiguous edit block consisting only of additions contributes one insertion anchor: the preceding base-side line, clamped to line 1 at the beginning of a file. For a zero-length old range `@@ -N,0 ...`, this is `max(1, N)`. Added lines never advance the base-side cursor.
- A replacement block containing both additions and deletions contributes the removed lines only. Context, hunk boundaries, and file boundaries separate blocks. The no-newline marker does not consume a line or separate a block.
- Match any FailRoute finding within an inclusive three-line distance of any selected site in the same base file. A match can be semantically unrelated: the proximity test deliberately does not assert that the rule identifies the repaired defect.

Output uses `location_match` rather than the historical `detected` field. A positive match means proximity only. `no` requires retrieval of all eligible base files; incomplete retrieval without a positive match is `n/a`. New-file-only and non-Python changes are `n/a`. Failed diff/commit retrieval and failed analyzer execution stop the run rather than silently becoming negative findings. A positive row with incomplete retrieval is marked in its note.

## Safe execution

Run from the repository with GitHub CLI access and FailRoute installed:

```sh
python tools/merged_pr_recall.py --out /tmp/failroute-pr-locations.csv
```

The default committed output is guarded before any network calls. Overwriting frozen evidence requires the explicit `--allow-overwrite-frozen` escape hatch; do not use it for manuscript reproduction. A new run uses the current analyzer and current upstream PR data, so it is not an exact historical replay. Cached diffs in `/tmp/a3` should be reviewed for provenance before making claims. Non-ASCII C-octal-quoted paths are rejected; supply a diff generated with `git -c core.quotePath=false diff` for those paths.

No empirical ratios have been recomputed by this repair. Semantic validation still requires reviewing the upstream repair, pre-fix behavior, and the matched finding; proximity alone cannot establish coverage of a failure mode.
