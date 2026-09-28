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

顶层字段：

```json
{
  "schema_version": 1,
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
| scenario_results | 每项 {scenario_id,test_id,outcome,evidence}；outcome=passed/failed/skipped/not_run |
| acceptance_results | 原 acceptance 每项 {condition,status,evidence}；status=met/unmet/unknown，met 必须引工件 |
| negative_controls | 每项 {scenario_id,test_id,baseline_evidence,tested_revision,mutation,target_assertion,failure_kind,evidence} |
| ci_selection / ci_execution | 工件 ID；没有则 null，不填“pass”字符串 |
| unresolved_prerequisites | 尚未满足的前置条件列表 |

scenario_id 沿用计划，不重排改号；not_run 仍保留 test_id（未知可为 null）和 evidence=null，并写明原因。新增需求先更新计划，不能拿新场景替换原场景而让旧缺口消失。说明性/需求澄清任务可返回 needs_review 与调查结果，不强造“validated 测例”。

## 工件内容

evidence 的路径相对于 completion.json 所在目录，不能逃逸；每份工件必须是 JSON，记录脱敏后文件 SHA256。原生输出可先归一化为以下格式，同时保留原始日志/工件定位和 hash 供人工复查，不编造缺失字段：

- 正例/反例运行：source_commit、patch_sha256、command、exit_code、status、counts（tests/failed/errors/skipped）、cases（每项 id、outcome）；另保留环境、安装包身份、原始工件路径/hash。
- outcome=passed/failed/error/skipped/xfailed；status 使用 pass/test_failure 等执行器枚举。JUnit classname::name 与原生 node ID 不一定相同，必须用实际工件 ID 做对齐，不猜文件路径。
- 选择工件：source_commit、patch_sha256、lane、command、selected_ids、unresolved_gates。
- CI 运行：在运行格式之上添加 lane、run_id、job_id、attempt、source_identity=verified，保留服务端链接和 checkout/build 证据。

干净提交运行可直接引用兼容的 runner result.json；dirty 运行须补齐实际变更身份，否则拒绝 validated。建议先在隔离副本提交允许的补丁；若不提交，记录 tracked diff 的 SHA256，并另外记录所有新增/未跟踪源文件和测试文件 hash。一个 diff hash 不涵盖未跟踪文件，更不证明安装包与工作区一致。

反例 tested_revision 使用与正例相同 base commit 和不同 patch_sha256；在隔离副本中变更，记录具体 mutation 和目标断言。failure_kind=target_assertion 需要人工读失败日志确认，不能为了满足字段而填写。若正例使用已提交补丁，负例基于该提交。

## 验收规则

```bash
python scripts/check_completion.py --plan /evidence/generation-plan.json --completion /evidence/completion.json
```

检查：任务/场景完整性、工件 hash、正例逐 case 结果、运行计数、版本/补丁身份、反例是否同一目标测试且非 error、原始验收条件是否保留、CI 选择/运行要求。

默认代码任务 required_evidence 为 positive、negative_control、ci_selection；要求真实 CI 的 acceptance 必须在审计计划里加 ci_execution。每个声明 validated 的场景都需要非跳过正例，默认还需对应反例。正例/反例确实不适用时先在计划说明适用边界和验收口径，不在完成阶段暗改证据要求。计划里未处理的依赖、未满足的条件、missing cases 或不确定身份都不能声明 validated。

脚本返回 evidence_consistent 仅表示结构与引用相容；不证明日志真实、断言足够、oracle 独立、业务需求完整、补丁来自所述来源。仍需读源代码、目标失败断言和工件。没有设备、缺真实 CI 或只做 CPU 路由时，使用 implemented_unverified/needs_review 并保留未验证范围。复审分支变化及选择规则后再决定是否关闭原缺口。
