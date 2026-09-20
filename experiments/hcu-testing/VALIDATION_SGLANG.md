# SGLang bounded validation

Validated 2026-09-20 against HYGON-AI/sglang-das commit `16229e94d0a0a218875ab0db2133c12d9695abd1`. This is an experimental evaluation, not a full PR gate or product certification. No target SGLang source or CI configuration was changed.

## Results

| Capability | Observed evidence |
|---|---|
| Native test selection | Read workflow whitelist, confirmed 45 Stage-B files with native `run_suite.py --list` |
| CPU execution | Existing metrics utility tests: 9 passed |
| Single-device execution | KV index/page-table kernel tests: 2 passed on BW1100, repeated successfully |
| Missing device handling | Hidden-device preflight correctly returned environment_blocked |
| Adapter validation | 16 helper/CLI fixture checks passed; existing pytest-helper CLI regression 4 passed |
| Generated tests | 19 new CPU metrics tests; existing plus generated: 28 passed, no skips/errors |
| Mutation: remove default sorting/deduplication | Existing 9 tests still passed; generated tests caught 3 assertion failures |
| Mutation: exponent shifted by one | Existing 9 tests still passed; generated tests caught 3 assertion failures |
| Python coverage analysis | Only observability/utils.py: 26/30 statements (86.67%) to 30/30 (100%) |
| Provenance rejection | Incorrect tested commit rejected; no valid output artifact written |
| Coverage-helper regression | 12 checks passed after empty-file trace compatibility correction |

Device runtime: PyTorch 2.11.0, HIP 6.3.26113, BW1100. Image identity: `sha256:4189a3af160467901207e0ee80b8e911ee24e32fddeee06dd9977d1130bf08a9`. This digest records the tested environment, not a claim that the image is publicly available. Coverage.py 7.6.1 was used.

## Scope and limitations

The native adapter reads the selected checkout's workflow rather than shipping a frozen test list. It currently supports source mode and one-file execution, not full workflow build/API gates or partition scheduling. Native logs are not JUnit. Unrecognized summaries are not promoted to a pass.

Generated assertions use explicit arithmetic examples rather than the implementation as an oracle. Numerical tolerances for CPU float calculations are documented in the tests. Mutations were applied only to independent Python source snapshots. These are deliberately injected faults, not claims of existing product defects. This was agent-driven evaluation, not independent blind multi-agent assessment.

Coverage is executable Python statement coverage for one file, not whole-project, branch, numerical, model-service, performance, or device-kernel coverage. During evaluation, a repository coverage source setting overrode an include filter; the final bounded run explicitly controlled configuration. Empty imported modules can have a non-statement line-1 trace; the analyzer now handles that specific case without inflating coverage or accepting real out-of-range lines.

## Reproduction entry points

- Native adapter: `skills/hcu-test-runner/references/sglang.md`.
- Adapter fixture tests: `python tests/test_sglang_adapter.py` (requires PyYAML).
- Helper invariants: `python tests/test_helpers.py` (requires coverage.py).
- Metrics evaluation: `python tests/evaluate_sglang_metrics.py --repo /checkout --output /new-results --image-id IMAGE_ID`. Requires a compatible SGLang source runtime, pytest, coverage.py, Git, and Linux for the explicit `/dev/null` coverage configuration. Output must be new and outside the checkout. It creates mutation snapshots and retains results.
- `tests/evaluate.py` is the historical SkillHub evaluation harness; it expects previously prepared sibling checkouts, runtime validator, and evidence artifacts. It is not a standalone bootstrap command.

Use isolated runtime resources. The actual device run used one visible device, explicit resource limits and network isolation. The metrics generation/coverage run used no device mapping, one CPU quota and 4 GiB memory. No host driver/configuration changes or model downloads were required; temporary containers were removed. Site paths, credentials, raw node logs, bytecode and coverage databases are intentionally not published here.

Product ownership, source-of-truth repository and catalog registration remain separate decisions before formal admission.
