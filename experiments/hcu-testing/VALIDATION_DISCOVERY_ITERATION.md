# CI discovery iteration validation

This iteration addresses failures observed during the SGLang 0.5.18 audit, without changing SGLang or enabling CI.

## Changes checked

- Discover branch runs, recent PR head runs, and explicitly selected workflows across branches. Deduplicate candidates and retain all discovery routes.
- Bound detail calls separately from candidate discovery. Keep deferred candidates, pagination bounds and unavailable endpoints visible. An artifact denial does not erase readable jobs; PR lookup failure does not erase workflow results.
- Report file-vs-method counting limits, run status and reviewed/deferred PR counts.
- Emit non-blocking review warnings for cross-lane design conflicts and partial design without test mappings. These warnings do not auto-fix semantic judgments.

## Validation

`python -m unittest discover -s experiments/hcu-testing/tests -p 'test_*audit.py'` covers legacy audit, branch/PR identity, JUnit, diff handling, multi-route discovery, partial API failures, budgeting and semantic review warnings.

Result on 2026-09-22: all 58 tests passed (previously 47). Skill frontmatter validation, repository catalog validation/generation/check, and `git diff --check` also passed. The formal catalog remains unchanged.

An offline replay used previously retrieved 2026-09-21 GitHub evidence for `release/20260825_v0.5.18` at `2b8d2b04a5a730f2b9031342af00932f583003f1`. The old branch-only snapshot had 10 selected wheel runs; the replay retained 21 unique candidates and expanded 10 by the configured budget, including discovery of PR run `35519161040` and nightly run `35537251885` that branch-only lookup missed. Unrecorded routes were marked unavailable, not returned as empty.

The unreviewed audit input produced four semantic review warnings. The previously corrected input produced none and preserved five actual job records / 46 file records. Zero warnings is not proof that the audit is semantically complete.

This is an offline replay of real saved evidence, not a fresh GitHub snapshot or a new HCU test run. No raw CI logs, private model payloads, tokens or internal endpoints are included in this validation note. Existing limitations remain: method-level results, build provenance, external dispatch and complete PR semantic review still need evidence.

## Follow-on test authoring handoff

The test-generation skill now separates behavior design, repository-native pytest/unittest authoring, bounded execution and per-task completion evidence. A read-only `--output` option exports a selected generation plan with stable scenario IDs (within the pinned backlog), branch/PR/runtime context and transitive unmet dependencies. It does not choose a framework from a filename heuristic or execute generated code.

After this change, all 66 audit/handoff regression tests passed (eight new handoff tests), along with Skill and catalog checks. The real saved SGLang backlog at the same pinned SHA was checked for `G_SPARSE72` and `G_JSON`: the former routes to search/adapt/write, the latter to proposed CI selection repair. This proves selection and handoff behavior only; no SGLang test patch, GPU execution, negative-control experiment or CI repair was performed in this iteration. The completion contract remains agent/human-reviewed, not an automated proof of test correctness.
