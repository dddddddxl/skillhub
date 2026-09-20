---
name: hcu-coverage-analysis
description: Analyze coverage.py JSON against the exact tested checkout and rank uncovered Python code, optionally limited to changed lines. Use to prioritize HCU adaptation test gaps; does not measure device-kernel coverage.
---

# Coverage analysis

Obtain a fresh coverage.py JSON report from a known test run. Record the checkout commit when collecting it and pass that commit to the helper. Never reuse an old report just because a file exists. Use a clean checkout to make commit provenance meaningful.

Check the report's actual file scope and collection warnings: a repository's coverage `source` setting can override a command-line `include`. For deliberately narrow evaluations, use an explicit coverage configuration consistently during collection and export; do not silently relabel a broad report as module-only coverage.

```bash
python /path/to/skill/scripts/analyze.py --repo /path/to/checkout --coverage /path/to/coverage.json --tested-commit FULL_SHA --output /path/to/report.json
```

Add `--base-ref BASE_SHA` for changed-line analysis; baseline must be an ancestor of the tested commit. Install the same coverage.py version used for collection (validated with 7.6.1) in the isolated analysis environment. Changed-line mode uses its public analysis API to exclude traced non-statement lines. Full-file mode uses coverage.py's statement summaries, not the raw trace length. This measures added/modified executable Python lines, not deleted code or all upstream differences. Coverage paths must resolve inside the checkout. Generate portable reports with relative paths.

Read the uncovered code before assigning risk. Prioritize HCU dispatch, unsupported-feature fallback, dtype/shape handling and recent defects, rather than assuming long functions are always important. Counts describe executable Python statements. They do not prove numerical correctness, branch completeness, distributed behavior, performance, or internal HCU kernel coverage.

The helper validates evidence and reports missing statements. It fails if no source files match, provenance is invalid or the report is malformed. Review source/report collection together: a supplied SHA alone cannot prove the report was collected from that SHA. Provide both the ranked gaps and evidence limitations.
