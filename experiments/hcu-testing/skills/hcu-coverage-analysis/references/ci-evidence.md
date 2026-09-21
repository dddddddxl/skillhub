# Observed CI before coverage judgments

## Acquire read-only evidence

Resolve repository, exact branch, branch tip and observation time. Use the available connector, GitHub CLI/API, or the platform's equivalent read-only API. For GitHub an optional standard-library helper collects metadata:

```sh
python scripts/github_snapshot.py --repository OWNER/REPO --branch release/BRANCH --since 2026-09-01T00:00:00Z --output /new/snapshot.json
```

It reads a token only from `GH_TOKEN` or `GITHUB_TOKEN`; it never persists one. Metadata is discovery, not execution proof. It queries all run event types for the branch, not only `pull_request`. Record bounded pagination, unavailable jobs/artifacts, incomplete history and filters. Use `pull_request_target`, `workflow_dispatch`, `schedule`, `push`, reusable and external CI as relevant. A branch filter can miss an external scheduler or default-branch workflow that checks out the target; explicitly inspect those routes before an absence claim. Do not replay workflow commands.

For relevant recent runs in each lane, inspect **job attempts and logs/test artifacts**, not just green workflow summaries. Identify checkout SHA (not necessarily event/head SHA), workflow revision, package/wheel source, image/platform/model, job/matrix/partition, actual command and test result IDs. Obtain artifacts using the connector/CLI; store only scoped, sanitized evidence outside the source checkout. Never publish raw logs with credentials, internal endpoints, request data or private model paths. Failed downloads mean unavailable evidence, not empty results.

Normalize reviewed per-job evidence into the run JSON described in `branch-contract.md`. Per-test evidence can come from JUnit or native runner logs; mark its granularity and preserve a hash plus a traceable source locator. `counts` alone cannot establish which tests ran. File-level native logs establish file-level observations only. Distinguish not selected, collected, running, passed, failed, skipped, xfailed and setup-blocked. Record rerun attempts separately. A successful retry does not erase earlier failures. All-skipped runs must not become successful functional evidence.

For JUnit use `python scripts/junit_observations.py --junit job.xml --context reviewed-job.json --output /new/run.json`. Context supplies the repository/branch/lane/platform/checkout identity and run/job/attempt/source locator. JUnit must supply `file` or context must provide `case_paths` keyed by `classname::name`; use `test_file` only when this is a verified single-file run. Unmapped paths fail instead of being guessed from class names. The helper hashes the raw artifact but does not prove supplied context; verify it against the job/build logs before setting `source_identity: verified`.

If only an older branch commit has artifacts, inventory it as historical and report distance/ancestry. Do not use it as proof for changed behavior at today's tip. Merge-ref and wheel builds require verified source identity; an event's `head_sha` alone is insufficient. Where the source cannot be proved, retain unresolved identity.

## Effective selection and SGLang

Follow triggers and target checkout → job gates/dependencies → actual matrix entries → wrapper arguments → discovery → registration/disabled → include/exclude → partition → runtime skip. Use the project's native collection-only interface only after reviewing its safety. Never import arbitrary test modules to count tests.

For SGLang read the selected revision's `run_suite.py` and `ci_register.py`. Mirror their discovery exactly (which may include non-`test_*` Python files). Run each **actual job's** `--list` with its suite, nightly flag, include-files and partition; a union of a suite's allowlists does not prove every job works. Capture exit codes, missing paths, duplicate/omitted partitions and effective selected files. Caches must key commit, workflow and exact command; stale logs are not reusable proof. An existing mixin may replace a deleted test file while CI still references the old path.

Collection is source design evidence, not a CI execution artifact. An enabled test with model-dependent SkipTest is not evidence that CI performed inference. A nightly declaration does not prove a release branch is scheduled: check default branch, workflow target ref and external dispatch. Keep those facts separate from test quality.
