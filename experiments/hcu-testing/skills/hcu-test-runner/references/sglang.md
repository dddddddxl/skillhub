# SGLang HCU native execution

Use `scripts/run_sglang.py` for repositories with `.github/workflows/pr-test-hcu.yml` and `test/run_suite.py`. Requires PyYAML and the Python/runtime dependencies of the selected checkout. The adapter reads literal workflow commands, then calls the project's own AST collector. It does not copy tests or maintain a second whitelist. Unsupported workflow shapes fail closed.

First plan without executing tests:

```sh
python /path/to/skill/scripts/run_sglang.py --repo /checkout --output /results/plan --suite stage-b-test-1-hcu-small
```

Execute one reviewed file with `--execute --include-file registered/path/test_name.py`. Add `--require-hcu` for device tests, `--timeout 180` for a per-process bound, and `--image-id IMMUTABLE_ID`. Each output directory must be new. The adapter preserves the native per-file runner. It does not reproduce the entire CI workflow's build, API checks, gating or partition matrix; do not call a selected run a full PR pass.

This version supports source mode only: set PYTHONPATH to the checkout's `python` directory. It checks the imported sglang path before execution. Use the project's compatible image, read-only driver libraries and DTK setup, offline model policy, bounded CPU/memory/threads, and only an available device. Provisioning and occupancy checks remain the caller's responsibility. No credentials or site-specific paths belong in this skill.

Artifacts: result.json, collection.log, source-probe.log, test.log, and preflight.log for requested hardware. These are native logs, not JUnit. Pass requires a matching successful native timing record plus a recognized nonempty unittest summary with at least one non-skipped case. Unrecognized summaries yield `native_success_unverified`, not pass. All-skipped/empty tests yield `no_tests_executed`. Nonzero native execution yields `execution_failure`; inspect logs to distinguish test defects from runtime/environment failures. A successful tensor probe alone does not prove the selected test used the accelerator.

Registration does not imply PR inclusion. Respect suite, workflow whitelist, disabled/nightly flags and native collection. Test resource requirements must be reviewed separately: the HCU label also includes CPU-only tests. Do not automatically launch model services, fetch weights, enable disabled cases, or expand from one file to the full suite.
