---
name: hcu-test-runner
description: Execute selected Python tests using pytest or the SGLang HCU native runner, recording results, device preflight and source revision. Use when validating HCU adaptations; does not provision drivers or publish results.
---

# HCU test execution

For SGLang's HCU PR suite/whitelist workflow, read [sglang.md](references/sglang.md) and use the native adapter. The pytest helper below does not implement native suite selection. Native logs and JUnit are different evidence formats; do not promise JUnit for native runs.

Read the target project's testing instructions and select a bounded existing test entrypoint. Run in an isolated checkout/container with its verified DTK environment loaded. Device nodes alone and device_count() alone do not prove HCU execution works: the helper allocates a tensor, computes and synchronizes.

Run the bundled helper with Python 3.8+:

```bash
python /path/to/skill/scripts/run_tests.py --repo /path/to/checkout --output /path/to/new-results --require-hcu -- tests/test_selected.py
```

Omit `--require-hcu` for CPU tests. Arguments after `--` are pytest arguments. Output must be a new directory outside the checkout. The helper writes result.json, junit.xml and test.log. Supply `--image-id` with the immutable image ID when running in a container; it is recorded, not inferred.

Classify results using both exit code and JUnit counts. No collected tests, all-skipped tests, malformed reports, timeout and missing hardware are not passes. CPU success is not HCU verification. Keep failed evidence. Do not repair production code, weaken assertions, add skips or change tolerances just to get a green result. When failure is environmental, report the missing prerequisite before retrying.

The helper runs reviewed project tests with your current permissions. Use the smallest practical device allocation and explicit time budget. Report the exact source revision, dirty state, selected tests, image identity, environment and remaining untested scope. Logs can contain project data; review them before sharing.
