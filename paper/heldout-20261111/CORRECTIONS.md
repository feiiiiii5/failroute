# Interpretation corrections for the frozen held-out record

The protocol, logs, findings, coverage and existing manifest remain byte-identical. This sidecar records interpretation/provenance corrections for the final 11 November 2026 manuscript.

- The original README and protocol retain historical wording about “16-PR / 14-in-scope / 9-non-handler”. Those pooled ratios are withdrawn. The current source-linked interpretation is `../reference-audit.json`: 10 supported broader examples, 3 excluded, 2 uncertain, 1 location-only. These are review statuses, not a replacement defect denominator. The held-out study did not re-evaluate PR semantics.
- “Pre-registered” in the original README file inventory means locally written and hash-pinned before fetching, not deposited in a public registry. The manuscript uses the latter, precise description.
- Eleven null isomorphism values do not all come from suppress findings: there are nine `silent-suppress` and two `name-shadowing` findings. Findings, distinct sites and isomorphism values are different units.
- `comparison.json` records source commit `15dffaaf3550aa3903a534b45c33d1a8b605d1d8` for the frame named v0.9.1. That commit reports package version 0.9.2; its detector source differs from the v0.9.1 tag only in the version constant. Reproduction pins the recorded commit rather than assuming the frame name is the executed version string.
- Agreement on the observed outputs of five main rules does not prove mapping validity for every possible shape. The two held-out name-shadowing discrepancies remain unchanged as failures of the evaluated mapping. No post-test correction is substituted into the primary experiment.
- The original README sandbox commands are shorthand, not a complete runnable driver. Use `python tools/reproduce_heldout.py --out-dir /tmp/failroute-heldout --fetch` from the tagged repository. It reconstructs fresh trees, keeps the development corpus untouched, pins both original commits and compares complete finding/coverage rows. `--fetch` is only needed when cached archives are absent.

See `../FINAL-VALIDATION.md` for actual re-execution results and limits. No new defect labels, replacement PR ratios or held-out PR claims were created.
