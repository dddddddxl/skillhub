# Branch audit contract (version 2)

Version 2 extends the legacy fields in `audit-contract.md`; use `audit.py render` as before. Old v1 inputs remain accepted. The schema checks traceability and internal consistency, not semantic truth.

Version 2 also accepts `kind: artifact` evidence with id/path/claim. The path is confined to the input evidence directory and hashed. Use it for saved PR diffs, metadata snapshots or sanitized logs, including prospective code absent from the target checkout. An artifact alone never proves execution; only normalized run observations can do so.

## Target, runtime and PR scope

Add `target: {branch: "release/name", ref: "refs/heads/release/name"}`. The ref must resolve to `source_commit` in the clean audited checkout. Fetch metadata/refs only in an authorized snapshot; do not checkout over user edits. This pins local identity; record remote observation time in scope limitations and refresh when needed.

Add `runtime: {status: "observed|partial|unavailable", reason: "...", evidence: ["RUN1"]}`. Every referenced run is ordinary `kind: run` evidence with the following normalized payload:

```json
{
  "repository": "https://github.com/owner/repo",
  "branch": "release/name", "lane": "pr", "platform": "HCU BW1100",
  "source_commit": "CHECKOUT_SHA", "source_identity": "verified",
  "run_id": "123", "job_id": "456", "attempt": 1,
  "source_locator": "https://github.com/owner/repo/actions/runs/123/job/456",
  "granularity": "case", "status": "pass",
  "counts": {"tests": 1, "failed": 0, "errors": 0, "skipped": 0},
  "cases": [{"id": "test_api.py::TestAPI::test_sort", "path": "test_api.py", "outcome": "passed"}]
}
```

`granularity` is `case` or `file`; file-level logs use one record per observed file and file counts, not invented method counts. `source_identity` is `verified` or `unresolved`; verification is the reviewer's responsibility using checkout/build/log provenance. Historical or unresolved runs may be inventoried but cannot prove tip execution. Cases have unique IDs per job/attempt and outcomes `passed|failed|error|skipped|xfailed|running|blocked`. Paths are repository-relative even for historical files no longer present at tip. `counts.tests` equals record count; failed/errors/skipped match records (xfailed counts skipped). Payload platform/commit must match its evidence metadata. Exact test IDs can be parameterized. Do not coalesce attempts.

Add `recent_prs: {since: "ISO date/time", until: "ISO date/time", status: "reviewed|partial|unavailable", reason: "...", followups: ["G_METADATA"], items: [...]}`. Each item:

```json
{
  "id": "123", "url": "https://github.com/owner/repo/pull/123",
  "base_branch": "release/name", "base_sha": "SHA", "head_sha": "SHA",
  "state": "merged", "in_target": "yes", "review": "reviewed",
  "reason": "merge SHA ancestry checked; actual diff read",
  "changes": [{"id": "C123_1", "description": "New duplicate-request rejection",
    "feature_ids": ["F_REQUEST"], "coverage": "partial", "evidence": ["E_CODE"], "followups": ["G_DUP"]}]
}
```

States: `open|merged|closed`; inclusion `yes|no|unknown`. Open PR must not be `yes`. Merged status is not sufficient to assert current inclusion after revert/backport; inspect commit ancestry and behavior. Review is `reviewed|deferred|excluded`; non-reviewed entries need rationale and `followups`. An excluded non-behavior PR may omit followups, but never silently exclude tests-only, assertion weakening, removed code or CI changes. Reviewed entries need behavior changes. PR change coverage is `supported|partial|gap|unknown`; IDs are unique across PRs. `partial/gap/unknown` changes need shared or specific followups. Unavailable/truncated PR review needs a followup.

Use `changes.py --repo /snapshot --base BASE_SHA --head HEAD_SHA --target TARGET_SHA --output /new/change.json` for rename-aware paths/hunks and merge-base provenance. It is navigation evidence, not a semantic diff review. Recent merged PRs and open prospective changes must be presented separately.

Do not blindly use a merged PR's present-day base-branch tip as its original diff base: if the head is already an ancestor, merge-base-to-head is empty. The helper rejects that comparison. Obtain the saved PR diff/original base or use `--mode exact` with a verified pre-merge parent and merge/squash commit; label the compared objects accurately. A revert needs a separate behavior review.

## Independent cell axes

Retain `selection`, `coverage`, `execution`, `reason`, `evidence` from v1 and add:

- `scheduling`: `verified|conditional|unknown|not_applicable` (branch/lane dispatch evidence, not test assertions).
- `followups`: task IDs for cell weaknesses. One shared task can cover several cells/axes; it need not pretend all have missing tests.
- `observations`: `[{evidence: "RUN1", case_ids: ["..."]}]`, required for execution states other than `not_verified`.

In v2 `coverage: supported` describes static assertion design and **can coexist** with excluded selection or unknown scheduling. It needs source-backed tests with reviewed assertions. Thus no new test is demanded merely because logs or scheduling are missing. A passed cell requires included selection, verified scheduling, current exact repo/branch/platform/SHA identity and observed non-skipped matching test paths/IDs. Failed/skipped/blocked claims also require matching observations. Current execution cannot use an old run or another feature's passing case.

A cell with partial/gap/unknown design, excluded/disabled/unknown/conditional selection or unknown/conditional scheduling needs `followups`. Do not force a new task for every not_verified execution: instead the top-level incomplete runtime inventory has a shared followup in `runtime.followups`.

For a passed behavior, each reviewed `tests` entry must list the applicable `case_ids`, and the selected observations must match both path and ID. Another passing method in the same file is insufficient. File-granularity logs remain in the observed inventory, but cannot establish `execution: passed` for a specific behavior; retain `not_verified` until the relevant method-level results are available.

Each feature adds `finding: {kind: "confirmed_gap|risk|improvement|unknown|supported", confidence: "high|medium|low", rationale: "...", counterevidence: "paths/alternatives inspected and limitations"}`. Confidence is evidence quality, not risk priority. Add `change_ids` to link recent PR behavior IDs (empty when unrelated).

Tasks retain legacy fields and optionally add `depends_on` task IDs. Dependencies must exist and be acyclic. Downstream handoff lists prerequisites explicitly; selecting a task does not silently authorize executing its dependencies.

## Coverage interpretation and output

Render produces `report.md`, `audit.json`, `test-backlog.json`, `observed-tests.json`, and `pr-change-matrix.json`. Summary counts distinguish all reported contracts, static supported contracts, current observed contracts, unknowns and PR behavior coverage. These are counts for an explicitly reviewed denominator, not full-repository completeness. Do not turn registration/file totals into a percentage.

Optional line evidence still uses `analyze.py`: only measured statement totals at the matching SHA can produce line/changed-line percentages. If no instrumented artifacts exist, say not measured. No invented branch/kernel coverage. Preserve new fields in handoff so generation can locate the changed behavior and distinguish selection repair from authoring tests.
