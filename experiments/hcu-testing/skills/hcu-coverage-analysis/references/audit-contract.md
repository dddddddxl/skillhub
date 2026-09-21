# Audit input and handoff contract (version 1)

The agent writes JSON from inspected evidence. `audit.py` validates references, structural consistency and source identity; it does not automatically infer feature completeness or prove that a cited statement supports a claim. Human/agent semantic review remains necessary.

Top-level input:

```json
{
  "schema_version": 1,
  "repository": "https://github.com/owner/repo",
  "source_commit": "FULL_COMMIT_SHA",
  "scope": {
    "platform": "target platform",
    "lanes": ["pr", "daily"],
    "extent": "bounded",
    "feature_basis": "Product contracts and explicitly named modules reviewed",
    "limitations": ["Only specified modules reviewed; no recent CI artifacts available"]
  },
  "evidence": [],
  "features": [],
  "tasks": []
}
```

`extent` is `bounded` or `repository_reviewed`; neither claims exhaustive correctness. Bounded scope must have limitations. Use stable IDs so follow-up runs can track the same gaps.

Evidence:

- Source: `{ "id":"E1", "kind":"source", "path":"relative/file.py", "start":1, "end":20, "claim":"What these lines establish" }`. Path must resolve inside the checkout, with valid inclusive line bounds. The output adds whole-file SHA256.
- Run: `{ "id":"R1", "kind":"run", "path":"relative/result.json", "claim":"What this artifact establishes", "source_commit":"...", "platform":"..." }`. Path is relative to the input JSON's directory, and cannot escape it. The output records its SHA256. Metadata must match audited commit/platform for a matrix execution claim. The helper recognizes the test runner's JSON with `source_commit`, `status` and `counts`: pass needs status `pass`, tests > skipped >= 0, and zero failures/errors. Other mapped statuses are `test_failure`/`execution_failure`, `no_tests_executed`, `environment_blocked`/`timeout`. Raw JUnit/logs remain reviewable evidence but cannot automatically establish a verified execution state; supply traceable normalized runner evidence or retain `not_verified`. Inspect provenance and lane/platform matching; metadata alone is not proof. Do not include credentials, model payloads or internal endpoints in portable reports.

Feature: `{ "id":"F1", "name":"...", "requirement":"Checkable behavior, not just a module name", "evidence":["E1"], "tests":[...], "lanes":{...} }`.

Each test: `{ "path":"relative/test.py", "assertion_kind":"behavior", "assertion":"What is actually checked", "evidence":["E2"] }`. Kinds: `smoke`, `behavior`, `numerical`, `error`, `performance`, `unknown`. A test path must be backed by source evidence for that file.

Every declared lane has `{ "selection":"included", "coverage":"partial", "execution":"not_verified", "reason":"...", "evidence":["E2","E3"] }`.

- Selection: `included`, `conditional`, `excluded`, `disabled`, `unknown`, `not_applicable`.
- Coverage: `supported`, `partial`, `gap`, `unknown`, `not_applicable`. `supported` means static assertions support this *bounded* contract, not all related functionality. It requires tests with described assertions, source evidence and `included` selection. Never use it merely because a file exists.
- Execution: `not_verified`, `passed`, `failed`, `skipped`, `blocked`. A verified execution state requires a matching run artifact reference. `passed` is incompatible with disabled/excluded/unknown selection for the audited lane. Manual runs outside the lane can be noted but do not establish lane success.

Task fields (all required):

```json
{
  "id": "G1",
  "feature_id": "F1",
  "priority": "P1",
  "lanes": ["pr"],
  "route": "upstream_first",
  "reason": "Why this gap matters and why this route",
  "evidence": ["E1","E2"],
  "cases": [{
    "name": "Concrete scenario",
    "inputs": "Representative inputs and boundary variants",
    "expected": "Observable expected behavior",
    "oracle": "Independent reference or authoritative contract",
    "negative_control": "Intentional wrong behavior the assertion must reject"
  }],
  "prerequisites": ["CPU only; no model or network needed"],
  "acceptance": ["Selected tests run rather than skip; negative control is rejected"],
  "search": ["Local and upstream modules/test paths or search terms to inspect"]
}
```

Priorities: P0/P1/P2. Routes: `upstream_first`, `write`, `validate_existing`, `repair_selection`, `clarify_requirement`. Even clarification/validation tasks specify the question/scenario and acceptance evidence, not a fabricated implementation. Upstream paths are search hints until inspected at an immutable revision; do not describe hints as existing usable tests.

Outputs: `audit.json` with checked evidence hashes; `report.md`; and `test-backlog.json` with repository, commit, scope, tasks, evidence and source fingerprints. The downstream skill must recheck the source snapshot and select task IDs explicitly. It writes a completion report per task with reused upstream provenance, adaptations, changed files, execution evidence and unresolved blockers. An audit never grants permission to modify CI, download models, publish or merge.
