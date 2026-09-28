# From a selected gap to maintainable tests

## Design before implementation

Use the selected task's inputs, expected result, oracle, negative control and acceptance conditions. Inspect the called implementation, existing assertions/mixins and repository instructions. Build a small matrix of scenario → input/setup → observable outcome → oracle → proposed test ID → environment. Include normal, boundary and error cases where they apply; explain inapplicable categories rather than inventing unsupported behavior. Preserve scenario IDs from the handoff plan so results can map back to the gap.

Keep product requirements separate from implementation details. A backend-dispatch contract may need a spy on the external backend selection call; that does not prove numerical correctness. Numerical paths need an independent reference with documented dtype/shape tolerances. A service response being nonempty cannot prove LoRA weights took effect, reranking order, or image understanding.

Inspect local and version-compatible upstream candidates first. Record inspected revision/path and disposition. If a suitable test exists, extend or adapt it; do not duplicate it in a new directory. If upstream is inaccessible, record that limit rather than claiming no upstream test exists.

## Choose the writer from the repository

Read the existing test class, conftest/config and the actual runner command. A unittest class run directly with `python test_file.py` should normally stay unittest; pytest collecting it locally is not enough to justify replacing it with module-level pytest functions. For new files follow neighboring tests and registrations, not a universal output directory. Standalone requests without a backlog still need a scoped module/change and explicit acceptance criteria.

### When pytest fits

- Use fixtures for resources, not to hide the behavior under test. Prefer function scope for mutable state; release servers, files and temporary environment changes with teardown/finally. Do not edit a shared node's environment.
- Parameterize genuine variants with descriptive IDs (e.g. `cu64`, `cu72`, `unsupported-cu`) and explicit expected results. Keep independent failure mechanisms separately diagnosable.
- Use temporary paths and reversible patching for external I/O/environment. Never mock the computation whose correctness the task claims to validate.
- Assert meaningful values, shapes/dtypes, ordering, side effects or exception contracts. Check specific exception types and stable message fragments when relevant; do not catch broad exceptions and pass.
- Use the repository's supported numerical assertion helpers and tolerances. Seeds help reproduce inputs but do not prove deterministic GPU kernels.
- Keep registered markers, dependency versions and existing plugins. Adding a framework/plugin dependency requires a real need and permitted scope, not a generic template.

### When unittest fits

- Extend the existing TestCase/mixin and retain runner conventions. Use `subTest` for simple input variants; choose separately named methods when individual CI identities matter.
- Use setUp/tearDown, addCleanup or context managers so cleanup also happens on failures. Avoid leaking class-level mutable state across methods.
- Use the project's assertion helpers, assertRaises and scoped mocks. Preserve existing skip reasons; do not convert missing hardware into a fake passing mock test.

## Execute and challenge

First inspect the native collection-only command for safety and verify selected IDs. Run only authorized tests in an isolated workspace/environment with time, device and model limits. Do not start the full suite from a bare `pytest` command by default. Capture command, exit code, actual executed/skipped IDs and JUnit/native artifacts where available.

Run the correct implementation first. Then apply a task-specific wrong behavior in a disposable copy and check that the intended assertion fails, not an import/setup error. Restore or discard only that isolated mutation. Record both patch identities. For example, a 72CU routing test should fail when eligibility is changed back to 64CU-only, while the unmodified positive test passes. This example does not authorize modifying the actual target repository.

On failure classify product defect, test error, environment problem, unsupported behavior or unknown. Fix a demonstrated test error within scope; do not delete assertions, increase tolerances or add skip/xfail to make the run green. If the same unresolved failure persists after a justified correction/retry, stop with evidence instead of an unbounded edit-until-pass loop. Product fixes, CI gate changes and model/device provisioning need their own authorization.

## Design references

Compared with Ascend's [generate-unit-test](https://github.com/Ascend/agent-skills/blob/master/skills/mindspeed-llm-auto-ut-skills/skills/generate-unit-test/SKILL.md) and [pytest-writer](https://github.com/Ascend/agent-skills/blob/master/skills/mindspeed-llm-auto-ut-skills/skills/pytest-writer/SKILL.md), reviewed 2026-09-22. This is independently written workflow guidance, not a copied template. Retained ideas: scenario design followed by framework-specific authoring. Not retained: whole-project default generation, a fixed auto_ut directory, a MindSpeed runner dependency, or modifying tests until they pass. No vendor-specific template/code is bundled; verify source/license before any future copying.
