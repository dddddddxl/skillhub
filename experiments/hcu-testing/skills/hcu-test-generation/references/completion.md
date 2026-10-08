# 补测完成记录与回填

在目标仓库之外写 completion.json，不覆盖原审计，不自动关闭缺口。每个明确选定任务保留一条记录；未选任务不动。独立请求先建立局部任务/场景 ID。

## 必须回答的问题

- 复用、适配、新写、验证已有、提议修选择，还是阻塞？记录 disposition 和理由，以及检索的上游/本地 revision、路径、许可证。
- 用哪个框架、改了哪些 test_paths？记录原生收集和执行入口，不猜固定目录。
- 跑的是哪个提交/补丁、哪个安装包/build、镜像和设备？基础提交不是改后版本身份。
- 每个计划场景的真实输入/预期/oracle、测试 ID、运行或跳过结果是什么？未执行不能丢弃。
- 故障注入是否让目标断言失败？导入、setup、环境错误不能算反例成功。
- CI 能否选择到，以及真实 CI 是否执行，是两个问题。本地通过不等于 CI 通过。
- 每项 acceptance 是否满足？仍缺什么前置条件，CPU 结论之外还剩哪些 HCU/数值/分布式风险？

这些说明可以保留在记录的 disposition、framework、test_paths、environment、upstream、rationale 等扩展字段，机器校验不会代替语义审核。

## 机器校验格式

新记录使用 completion v2，generation-plan 仍为 plan_schema_version=1。顶层字段：

```json
{
  "schema_version": 2,
  "repository": "<与计划一致>",
  "audit_source_commit": "<计划的完整 SHA>",
  "evidence": [
    {"id": "POS", "path": "positive.json", "sha256": "<工件 SHA256>"}
  ],
  "tasks": []
}
```

每条 tasks 记录：

| 字段 | 格式 |
|---|---|
| task_id | 与 generation-plan 的选中任务一致 |
| status | implemented_unverified / validated / blocked / needs_review |
| validated_scope | 有边界的中文说明，例如“CPU 路由，不含 HCU 数值内核” |
| tested_revision | {source_commit, patch_sha256}；干净提交 patch_sha256=null |
| scenario_results | 每项 {scenario_id,tests}；tests 非空，每项 {test_id,outcome,evidence} |
| acceptance_results | 原 acceptance 每项 {condition,status,evidence}；status=met/unmet/unknown，met 必须引工件 |
| negative_controls | 每项 {scenario_id,test_id,baseline_evidence,tested_revision,mutation,target_assertion,failure_kind,evidence} |
| ci_selection / ci_execution | 工件 ID；没有则 null，不填“pass”字符串 |
| unresolved_prerequisites | 尚未满足的前置条件列表 |

一个计划场景可以落到多个实际方法，全部列入 tests；场景内 test_id 唯一，不能保留代表 test_id、covered_test_ids 或场景级 outcome/evidence。例如：

```json
{
  "scenario_id": "G4-width",
  "tests": [
    {"test_id": "Wrapper::test_invalid_width", "outcome": "passed", "evidence": "POS"},
    {"test_id": "Wrapper::test_forwarding", "outcome": "passed", "evidence": "POS"}
  ]
}
```

tests 的 outcome 为 passed/failed/error/skipped/xfailed/not_run；不同方法可以引用不同运行工件。scenario_id 沿用计划，不重排改号；not_run 必须 evidence=null 并有非空 reason。方法未知时，tests 只保留一个 test_id=null 的 not_run 占位，不与已知方法混用。新增需求先更新计划，不能拿新场景替换原场景而让旧缺口消失。说明性/需求澄清任务可返回 needs_review 与调查结果，不强造“validated 测例”。

旧 schema_version=1 继续按原单 test_id 格式和原验收语义校验，不暗中套用 v2 的新门槛。v1 的非 validated 记录不会校验负控/CI 的完整一致性，也不校验 raw_artifacts；需要这些保证时显式迁移为 v2，不能把 v1 的 evidence_consistent 当成 v2 验收。

## 工件内容

evidence 的路径相对于 completion.json 所在目录，不能逃逸；每份工件必须是 JSON，记录脱敏后文件 SHA256。原生输出可先归一化为以下格式，同时保留原始日志/工件定位和 hash 供人工复查，不编造缺失字段：

- 正例/反例运行：source_commit、patch_sha256、command、exit_code、status、counts（tests/failed/errors/skipped）、cases（每项 id、outcome）；另保留环境、安装包身份、原始工件路径/hash。
- outcome=passed/failed/error/skipped/xfailed；status 使用 pass/test_failure 等执行器枚举。JUnit classname::name 与原生 node ID 不一定相同，必须用实际工件 ID 做对齐，不猜文件路径。
- 选择工件：source_commit、patch_sha256、lane、command、exit_code、status、selected_ids、unresolved_gates。成功使用 status=pass、exit_code=0；阻塞可用 selection_blocked 并保留真实退出码和原因。
- CI 运行：在运行格式之上添加 lane、run_id、job_id、attempt、source_identity=verified，保留服务端链接和 checkout/build 证据。

若逐 case 显式带 run_id/job_id/attempt/tested_sha/source_identity/source_commit/patch_sha256，字段类型和值必须与所属运行的父身份相同；tested_sha 对齐父 source_commit。不可把不同 run/job/attempt 的通过子集拼成一次运行。未提供逐 case 身份时不编造、不推断；机器只能核对已声明的字段和文件 hash，任意原始日志拼接或虚假来源仍须评审复核，不能宣称均可自动识别。

v2 的运行和选择工件必须有非空 raw_artifacts，每项为 {path,sha256}，例如 `{"path":"positive.log","sha256":"<脱敏文件的 SHA256>"}`。raw 路径相对于引用它的 JSON 文件所在目录，文件不必是 JSON；解析后仍必须留在 completion 的证据根目录内，禁止绝对路径、逃逸路径、缺失或 hash 不符。所有已声明的原始引用都会校验，包括尚未用于验收的工件；ENV/SUMMARY 等说明工件不必强造原始日志。交付必须包含脱敏后的实际日志/XML，不能仅提交指向被 gitignore 排除日志的清单。脱敏或移动后同步更新引用及外层 JSON 的 hash。

干净提交运行可直接引用兼容的 runner result.json；dirty 运行须补齐实际变更身份，否则拒绝 validated。建议先在隔离副本提交允许的补丁；若不提交，记录 tracked diff 的 SHA256，并另外记录所有新增/未跟踪源文件和测试文件 hash。一个 diff hash 不涵盖未跟踪文件，更不证明安装包与工作区一致。

反例 tested_revision 使用与正例相同 base commit 和不同 patch_sha256；在隔离副本中变更，记录具体 mutation 和目标断言。每条 negative_controls 的 test_id 必须命中同场景中一个已 passed 的方法，baseline_evidence 必须与该方法的正例 evidence 一致；反例实际 cases 中该方法必须 failed，运行须 test_failure/exit 1，不能用其他方法失败或 error 冒充。一个方法可有多种 mutation，一个反例工件可分别映射多个确实失败的方法，但相同 (scenario_id,test_id,evidence) 不可重复。failure_kind=target_assertion 需要人工读失败日志确认，不能为了满足字段而填写。若正例使用已提交补丁，负例基于该提交。

## 验收规则

```bash
python scripts/check_completion.py --plan /evidence/generation-plan.json --completion /evidence/completion.json
```

v2 在所有任务状态下检查已填证据：任务/场景完整性、JSON 与原始工件 hash/路径、逐方法结果、运行计数、版本/补丁身份、反例目标及基线、acceptance 中已填引用、CI 身份。未完成状态允许缺失负控/CI，但不允许错误引用或伪称成功。填写 ci_execution 就必须有真实 run_id/job_id、正整数 attempt 和 source_identity=verified，即使计划没有要求它，也不能放入本地结果冒充 CI。

默认代码任务 required_evidence 为 positive、negative_control、ci_selection；要求真实 CI 的 acceptance 必须在审计计划里加 ci_execution。validated 要求所有列出的方法 passed、acceptance 全 met、依赖/前置条件清零；默认每个计划场景还需至少一条合格反例，不无依据升级为每个附加方法都必须 mutation。若计划对负控有更具体要求，需逐项人工核对，不在完成阶段暗改证据要求。

CI 选择和执行都检查全部 tests ID 的并集，而非代表方法。阻塞选择可保留在 implemented_unverified/blocked/needs_review；validated 的必需选择证据须 pass/exit 0、无 unresolved_gates，并选中全部方法。必需 CI 执行证据须 pass/exit 0，包含全部方法且每项 passed，不能靠所需方法通过掩盖该运行的显式 error/test_failure。未处理的依赖、未满足条件、missing cases 或不确定身份都不能声明 validated。

脚本返回 evidence_consistent 仅表示结构与引用相容；不证明日志真实、断言足够、oracle 独立、业务需求完整、补丁来自所述来源。仍需读源代码、目标失败断言和工件。没有设备、缺真实 CI 或只做 CPU 路由时，使用 implemented_unverified/needs_review 并保留未验证范围。复审分支变化及选择规则后再决定是否关闭原缺口。
