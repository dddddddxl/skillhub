# Branch-aware CI / recent-PR audit validation

Date: 2026-09-21. Experimental local update; not published or merged.

## Implemented

- Version-2 branch audit retains v1 compatibility and pins the named local branch to the clean source commit.
- Assertion design, effective selection, branch scheduling and execution are independent fields. Existing supported assertions may coexist with unknown scheduling, without generating duplicate test-authoring tasks.
- Observed CI inventory records repo/branch/checkout identity, platform, lane, run/job/attempt, granularity, source locator, case IDs/outcomes and artifact hashes. A historical or unresolved build cannot prove current behavior. File-only success cannot prove a specific method executed; passed behavior requires matching path and reviewed case IDs.
- Read-only GitHub metadata discovery queries all event types, bounds pagination/runs/PRs and exposes truncation. It discovers jobs/artifacts but does not equate metadata with actual tests.
- JUnit normalization preserves observed identities/outcomes without failure payloads. Source paths require explicit mapping; all skipped is not pass.
- Recent PR schema records target branch, base/head, landed versus prospective state, behavior changes, feature links and followups. Rename-aware Git diff navigation includes removed/renamed tests and guards against empty merged-head comparisons. It does not infer business semantics from diff size.
- Shared followups and acyclic dependencies pass through to test-generation handoff. Selecting a task reports unselected dependencies rather than executing them.
- Instructions require exact matrix selection checks, inherited/mixin/migrated test review, counterevidence and separate finding classification/confidence.

## Checks

- **47 tests passed** on Windows Python 3.10: 18 existing audit/handoff tests plus 29 v2/discovery/JUnit/diff checks.
- Negative cases include wrong branch/SHA/platform/lane, unresolved wheel identity, unrelated method within the same file, file-only evidence, mismatched counts, all-skipped results, missing PR mappings, open PR falsely treated as landed, deferred review hidden in a complete window, missing shared tasks and cyclic dependencies.
- Git diff fixture exercises a renamed test and changed production behavior. API fixtures verify all-event discovery, PR detail lookup and explicit pagination truncation. JUnit fixtures reject guessed paths and omit sensitive failure payloads.
- Both changed Skill entrypoints passed skill-creator quick validation using local Python 3.13/PyYAML 6.0.2.
- SkillHub catalog validation, generation and generation --check passed; the published catalog remains unchanged (one registered skill/component). These experimental skills are not claimed as catalog entries.
- A supplied reviewed SGLang `release/20260825_v0.5.18` audit at `2b8d2b04a5a730f2b9031342af00932f583003f1` was converted and rendered into v2 outputs. API assertion design remains supported despite unknown daily scheduling, and JSON selection repair hands off with a shared scheduling dependency. The target checkout remained clean.

## Limitations

Live unauthenticated GitHub discovery returned HTTP 403. Full authenticated metadata → original CI artifacts → recent PR diff review → v2 report has **not** been forward-tested end-to-end in this iteration. The SGLang regression honestly leaves runtime artifacts and recent PR review unavailable; it is not a fresh completed branch audit. Another authorized connector/CLI or authenticated API can provide the required evidence in actual use.

The helpers are deterministic evidence/structure checks, not an autonomous semantic completeness classifier. No accuracy percentage is claimed. Functional and PR coverage are counts against reviewed contracts; line/branch/kernel coverage remains unmeasured without matching instrumented artifacts. No target CI changes, model execution, node configuration changes, push or merge occurred.

## Reproduce

```sh
python -m unittest discover -s experiments/hcu-testing/tests -p 'test_*audit.py'
python experiments/hcu-testing/skills/hcu-coverage-analysis/scripts/github_snapshot.py --repository OWNER/REPO --branch BRANCH --since 2026-09-01T00:00:00Z --output /new/metadata.json
python experiments/hcu-testing/skills/hcu-coverage-analysis/scripts/junit_observations.py --junit /evidence/job.xml --context /evidence/reviewed-job.json --output /new/run.json
python experiments/hcu-testing/skills/hcu-coverage-analysis/scripts/changes.py --repo /snapshot --base BASE_SHA --head HEAD_SHA --target TARGET_SHA --output /new/diff.json
python experiments/hcu-testing/skills/hcu-coverage-analysis/scripts/audit.py render --repo /snapshot --input /evidence/audit-v2.json --output /new/report
```

Read `references/branch-contract.md` before composing v2 input. Reports and task IDs are advisory; none of these commands authorizes CI mutation, execution or publication.
