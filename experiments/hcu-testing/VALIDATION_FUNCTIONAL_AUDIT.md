# Functional audit and test-generation handoff

Date: 2026-09-21. This iteration extends the experimental skills; it does not change the published catalog or target project's CI.

## New behavior

`hcu-coverage-analysis` now routes repository PR/daily completeness questions to a functional audit, while preserving the original coverage.py helper as optional supporting evidence. The agent establishes a feature denominator from requirements/code, traces actual CI selection and reads assertions. The standard-library helper indexes candidate files, validates source/run references and generates a Markdown matrix, checked audit JSON and structured test backlog. It does not infer semantics from filenames.

`hcu-test-generation` consumes selected backlog IDs and rechecks the source commit/fingerprints. Its procedure searches existing and version-compatible upstream tests before deciding to reuse/adapt/author. Existing disabled tests route to validation/CI review, not automatic duplication. The handoff is advisory, not authorization to execute suites or change gates.

## Checks performed

- 18 contract/CLI tests passed on Windows Python 3.10 and in an isolated Linux container.
- Checks cover source identity, dirty snapshots, path/line/reference errors, missing tasks, unknown daily mappings, disabled-versus-supported contradictions, unavailable/stale/all-skipped/failing run evidence, explicit task selection and output overwrite protection.
- Real SGLang source `16229e94d0a0a218875ab0db2133c12d9695abd1`: inventory and evidence rendering completed; the generation handoff accepted `G_METRICS` and `G_COMPILE` with different routes.
- Native nightly collection confirmed the referenced BF16 attention file is enabled in `nightly-hcu-core-functional`. Collection only; no model/device test was executed.
- Both changed Skill entrypoints passed quick_validate. The repository's catalog validator and generation/check passed in the Linux candidate workspace; the local Python lacked PyYAML, so its initial catalog validation was blocked rather than counted as passing.
- Read-only target source remained clean; the CPU-only, network-disabled, 1 CPU/2 GiB container was stopped and removed. Existing Jenkins work was not manipulated.

The reviewed example contains four bounded feature contracts, eight lane cells and five tasks. Three daily mappings remain unknown with explicit follow-up tasks. It is intentionally not a whole-repository completeness claim and does not treat earlier manual test passes as current CI lane evidence.

## Reproduce

```sh
python experiments/hcu-testing/tests/test_functional_audit.py
python experiments/hcu-testing/tests/build_sglang_audit_example.py --output /new/audit-input.json
python experiments/hcu-testing/skills/hcu-coverage-analysis/scripts/audit.py inventory --repo /sglang-checkout --output /new/inventory.json
python experiments/hcu-testing/skills/hcu-coverage-analysis/scripts/audit.py render --repo /sglang-checkout --input /new/audit-input.json --output /new/report
python experiments/hcu-testing/skills/hcu-test-generation/scripts/check_handoff.py --repo /sglang-checkout --backlog /new/report/test-backlog.json --task G_METRICS --task G_COMPILE
```

The SGLang example is pinned and agent-authored, not an automatic detector. A different commit/repository requires new evidence and feature mapping. Schema checks do not prove the cited source semantically establishes the claim. Full upstream search/adaptation and end-to-end execution of backlog tasks were not performed in this iteration; earlier generation/runner evidence remains separately documented in VALIDATION_SGLANG.md.
