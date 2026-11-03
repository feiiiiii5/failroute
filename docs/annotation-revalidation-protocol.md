# Contract revalidation protocol

Status: proposed 2026-11-03; not yet executed by independent human annotators.
The original 80 + 60 automated labels remain frozen historical observations.
This protocol must not be described as the one those runs followed.

1. Freeze detector versions and packages before selecting a new evaluation set.
   Keep development packages and copied function families out of the held-out set.
2. Sample detector-only, baseline-only, shared and unreported sites separately.
   Keep probabilities, strata and site identities; report findings and unique sites
   separately. Do not pool purposive examples into prevalence estimates.
3. Have two human reviewers independently inspect the guarded operation, reachable
   failure paths, return/state channels, callers, tests and documented policies.
   Hide tool severity and prior labels until their initial judgements are recorded.
4. Record separately: whether an operational failure is reachable; whether the
   caller can distinguish it; whether the policy is intentional; whether the task's
   contract is violated; and the observable consequence. A comment, type annotation
   or log statement alone establishes neither safety nor caller distinguishability.
5. Use DEFECT only with a supported consequence chain; CONTRACT with explicit
   admissible caller behaviour; FALSE_POSITIVE when the detected structural premise
   is wrong; and UNCERTAIN when decisive evidence is missing. Retain uncertainty.
6. Capture source commit, file/span, caller and test evidence, reasoning, reviewer,
   date, disagreements and adjudication. A fault-injection test should demonstrate
   the failure outcome where feasible. A merged change alone is not a bug verdict.
7. Preserve original records and publish corrections as separate, source-linked
   records. Recompute every affected result from the selected version. Report
   agreement separately from correctness and aggregate at the package/family level.

A new LLM-assisted pass may help locate evidence but cannot be reported as the
independent human validation above. Record model, version, exact prompt, context,
parameters and outputs for any new automated pass. Never reconstruct unavailable
historical prompts or reviewer identities by guesswork.
