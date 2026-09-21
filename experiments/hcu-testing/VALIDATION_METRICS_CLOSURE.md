# Functional audit task closure: G_METRICS

Date: 2026-09-21. This completes one bounded task from the functional audit backlog. It is a candidate validation, not a merged fix or a hosted CI run.

## Source and reuse decision

- HYGON base: `16229e94d0a0a218875ab0db2133c12d9695abd1`.
- Isolated candidate: `535dc5cb55995167e1aaea97f1a990cee129c0b3`, branch `codex/metrics-audit-gap`; not pushed.
- The repository's sync summary identifies official upstream `sgl-project/sglang` at `df0dc44931433b8a3488fbd4c6489e08cdee8703`.
- Inspected the upstream [test file](https://github.com/sgl-project/sglang/blob/df0dc44931433b8a3488fbd4c6489e08cdee8703/test/registered/unit/observability/test_metrics_utils.py), [implementation](https://github.com/sgl-project/sglang/blob/df0dc44931433b8a3488fbd4c6489e08cdee8703/python/sglang/srt/observability/utils.py), and [Apache-2.0 license](https://github.com/sgl-project/sglang/blob/df0dc44931433b8a3488fbd4c6489e08cdee8703/LICENSE). Test blob: `11ed061830ee2821c4368a562e10f1e09ef71351`. The inspected upstream test has the same nine existing methods and does not supply the missing cases. This is not an exhaustive claim about every upstream branch.
- Reused the earlier original experimental test ideas, adapting them into the existing unittest class. The native runner directly executes that file; top-level pytest functions would not be an appropriate drop-in replacement.

Only `test/registered/unit/observability/test_metrics_utils.py` changed: 34 insertions and one deletion. Five methods cover default sorting/deduplication without input mutation, ordinary and fractional exponential sequences, and lengths zero/one. The existing empty-input case now actually passes `[]`. Production code, CI whitelist, registration and thresholds are unchanged.

## Verified results

| Check | Result |
| --- | --- |
| Backlog source/fingerprint check | G_METRICS accepted against clean base |
| Native PR suite selection and execution | Selected existing file; 14 tests passed, zero skipped |
| Baseline / candidate pytest execution | 9 / 14 passed |
| Module statement coverage | 26/30 (86.67%) → 30/30 (100%) |
| Remove default sorting/deduplication in isolated copy | Old 9 passed; new set had 1 failure |
| Shift exponent from i to i+1 in isolated copy | Old 9 passed; new set had 3 failures |
| Negative-control errors/skips | Zero; failures were assertions |
| Source integrity after execution | Base and committed candidate remained clean |

Coverage applies only to `python/sglang/srt/observability/utils.py`. It does not establish branch, device-kernel, whole-repository or complete functional coverage. The negative controls supply behavioral evidence beyond line coverage.

## Reproduce

Use the reviewed runtime with Python 3.10, pytest and coverage.py 7.6.1. Create clean base/candidate checkouts with the candidate patch already committed, then run:

```sh
python experiments/hcu-testing/tests/evaluate_audit_metrics_closure.py \
  --base /sglang-original --candidate /sglang-candidate \
  --backlog /evaluation/functional-audit-20260921/report-v2/test-backlog.json \
  --output /evaluation/new-metrics-closure \
  --image-id sha256:4189a3af160467901207e0ee80b8e911ee24e32fddeee06dd9977d1130bf08a9
```

Actual execution used a disposable network-disabled container limited to one CPU, 4 GiB and 256 PIDs. No devices, privileged mode, host networking or models were used. Source checkouts and driver libraries were read-only mounts. Coverage was installed from an existing offline wheel into the container only. The container was stopped and removed; evidence and isolated candidate remain.

The driver records commands, patch, source commits, native selection/execution logs, JUnit, coverage analysis and `completion.json`. Mutation copies are intentionally excluded from the portable evidence archive; the driver reconstructs them.

## What this validates and what remains

The agent-assisted chain now has a real example: evidence-backed audit → explicit task handoff → version-pinned upstream review → native-style test adaptation → original runner execution → negative controls → candidate completion record. The helper does not autonomously infer the entire feature denominator or prove upstream search completeness.

G_METRICS is validated in the candidate only. The original backlog remains immutable evidence for the original commit; it must not be relabeled as fixed there. Merge/publication and hosted CI acceptance remain pending. The other four tasks remain open, including three unknown daily mappings and the existing disabled compile-test applicability task. No disabled gate was enabled.
