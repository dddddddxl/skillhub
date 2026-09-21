---
name: hcu-coverage-analysis
description: Audit a specified repository and branch by identifying observed CI tests, tracing business requirements and recent PR changes, and reporting missing scenarios, weak assertions, selection gaps and coverage evidence with an actionable backlog.
---

# Functional test coverage audit

For branch test-gap audits, use [functional-audit.md](references/functional-audit.md) and the [branch audit contract](references/branch-contract.md). Start with observed CI runs and test identities, then map business contracts and recent PR behavior changes to assertions. Produce a version-2 report, observed-test inventory, PR-change matrix and backlog. The [legacy contract](references/audit-contract.md) remains supported for old version-1 reports; do not use it to omit branch/runtime/PR analysis in a new audit.

Read [CI evidence collection](references/ci-evidence.md) to collect runtime evidence. For SGLang also follow its exact-matrix checklist there. Never label configured or merely collected tests as actually executed. Separate assertion design, effective selection, branch scheduling and execution. Report functional-contract counts, recent-PR behavior coverage and measured line coverage separately; missing evidence is unknown, not zero or a guessed percentage.

Default to read-only inspection. Do not launch suites, download models, change CI gates, or generate test patches merely to audit coverage. Distinguish missing tests, tests excluded/disabled, insufficient assertions, unavailable execution evidence, and uncertain requirements. Report unknowns; do not manufacture an overall completeness percentage from test counts or filenames. PR and daily coverage are separate views, not interchangeable proof.

The backlog can be consumed by `hcu-test-generation`, or by another agent using its task fields without installing a sibling skill. Creating a backlog is not authorization to execute it or publish changes.

## Optional Python line evidence

Use the existing helper below when a coverage.py report is available; no coverage report is required for a functional audit. Attach its findings to the relevant feature/scenario rather than treating line coverage as functional coverage.

Obtain a fresh coverage.py JSON report from a known test run. Record the checkout commit when collecting it and pass that commit to the helper. Never reuse an old report just because a file exists. Use a clean checkout to make commit provenance meaningful.

Check the report's actual file scope and collection warnings: a repository's coverage `source` setting can override a command-line `include`. For deliberately narrow evaluations, use an explicit coverage configuration consistently during collection and export; do not silently relabel a broad report as module-only coverage.

```bash
python /path/to/skill/scripts/analyze.py --repo /path/to/checkout --coverage /path/to/coverage.json --tested-commit FULL_SHA --output /path/to/report.json
```

Add `--base-ref BASE_SHA` for changed-line analysis; baseline must be an ancestor of the tested commit. Install the same coverage.py version used for collection (validated with 7.6.1) in the isolated analysis environment. Changed-line mode uses its public analysis API to exclude traced non-statement lines. Full-file mode uses coverage.py's statement summaries, not the raw trace length. This measures added/modified executable Python lines, not deleted code or all upstream differences. Coverage paths must resolve inside the checkout. Generate portable reports with relative paths.

Read the uncovered code before assigning risk. Prioritize HCU dispatch, unsupported-feature fallback, dtype/shape handling and recent defects, rather than assuming long functions are always important. Counts describe executable Python statements. They do not prove numerical correctness, branch completeness, distributed behavior, performance, or internal HCU kernel coverage.

The helper validates evidence and reports missing statements. It fails if no source files match, provenance is invalid or the report is malformed. Review source/report collection together: a supplied SHA alone cannot prove the report was collected from that SHA. Provide both the ranked gaps and evidence limitations.
