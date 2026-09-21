---
name: hcu-test-generation
description: Close selected HCU test gaps from an audit backlog or a specified change by finding reusable upstream tests, adapting them, or writing behavior-based cases. Use for test implementation after coverage review; distinguish missing tests from CI selection and validation gaps.
---

# Generate tests for HCU adaptations

When given a coverage audit/backlog, read [audit-handoff.md](references/audit-handoff.md). Confirm task IDs, source revision and permitted changes; inspect local/version-compatible upstream tests before deciding to copy, adapt or author. Accept a standalone gap description as well; no sibling skill installation is required. Do not treat `validate_existing`, `repair_selection` or `clarify_requirement` as instructions to generate duplicate tests.

Read repository guidance, the selected change and existing tests. Default to the requested module or change, not the entire upstream framework. Derive expected results from documented behavior or an independent reference; do not mirror the implementation as the oracle.

Identify applicable risks: device selection and fallback, dtype/shape/layout boundaries, empty inputs, error handling, and distributed behavior. Use CPU tests for pure configuration logic. Label device tests accurately and run them on actual HCU hardware before claiming hardware support. Mock only external dependencies, not the computation being validated.

For numerical comparisons, document dtype-specific tolerances and the reference implementation. Exercise at least one intentional incorrect behavior to confirm the new assertion catches it, in an isolated copy; never alter the user's working production code for this check.

Run the repository's existing test entrypoint or pytest directly, capture exit code and JUnit results. No sibling skill is required. A missing device means unexecuted hardware tests, not a pass. Diagnose failed tests as test error, product defect, environment issue, or unsupported behavior. Do not remove assertions, add skips/xfails, increase tolerances or change product behavior merely to pass.

Deliver the test patch, actual commands and results, assumptions behind expected values, and untested risks. Keep CPU, single-device and distributed claims separate. Do not publish or merge generated tests unless requested.
