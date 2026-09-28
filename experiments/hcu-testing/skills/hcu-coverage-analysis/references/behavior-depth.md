# 功能与 PR 的行为深审

新审计设置 `scope.analysis_depth: "behavior"`，在 v2 报告中加入 `analysis`。旧版仍可读取，但没有这些记录不能声称已做功能全景深审。机器校验只验证追踪关系；“产品应当如何工作”仍需阅读代码和需求来判断。

## 先扩大检索，再缩小结论

先建立独立于已有测试的功能台账：产品文档、CLI/API、模块公共接口、后端适配、发布承诺、近期缺陷。逐项记录已审、待审、未知、明确不支持/排除及理由。分母不完整时只报本轮已审数量，禁止用测试文件数量推全仓百分比。

用只读导航工具辅助定位实现和调用者：

```bash
python scripts/source_index.py --repo /checkout --path python/sglang/srt --max-files 500 --output /evidence/source-index.json
```

工具读取 HEAD 的 Git blob，不执行仓库 Python，不跟随文件符号链接；记录符号、词法调用、导入别名、类继承、行号及 blob/hash。输出预算外路径、解析失败和非 Python 文件数。它不是完整调用图：继续追踪别名、注册表、基类、动态分发和 C++/HIP 实现，不能把 AST 命中当业务关系已确认。

## 逐条审阅行为

对每个功能写“输入/状态 → 可观察输出 → 独立 oracle → 能检出的错误”，再匹配具体测试 ID 和断言源行。按业务选择边界，不强求笛卡尔积：

- 路由：命中、未命中、回退、dtype/shape/设备交界；路由正确不代表数值正确。
- 状态：首次/重复、并发、取消、失败后重试和资源清理。
- 数值：独立参考、shape/dtype/device、容差依据，极值/空输入/NaN 合同。
- PR：读固定 base/head 的真实 diff，比较改前/改后行为；追公共入口、调用方、后端路径和删除/弱化的测试。

优先深审改变外部语义、后端分发、错误处理及测试选择的 PR；低风险项可以有理由排除。快照中的 `pr_candidates` 保留本轮检索到的所有候选，即使只为前 20 个拉详情；详情限制和分页截断分别报告。不能把“未拉详情”写成“无风险”。超出分页范围的 PR 总量仍未知。

## analysis 数据字段（schema_version=1）

所有 evidence 均引用顶层证据 ID，源证据必须可核查行号；示例中的文字需要替换为实际阅读结果。

| 字段 | 每项必填内容 |
|---|---|
| `feature_inventory` | `id,name,basis,status,reason,feature_ids,evidence,followups` |
| `scenarios` | `id,feature_id,lanes,inputs,expected,oracle,failure_mode,status,tests,evidence,followups` |
| `pr_impacts` | `change_id,before,after,trigger,risk,entrypoints,callers,backend_paths,scenario_ids,exclusions,evidence` |

`basis` 为 `documented/inferred/unsupported/unknown`；`status` 在功能台账中为 `reviewed/deferred/excluded/unknown`，在场景中为 `supported/gap/unknown`。推断需求必须标明来源和不确定性。未知调用方用“unknown：原因及后续调查”保留，不编造关系。

`scenarios.tests` 每项为 `{path,id,assertion,evidence}`，对应 feature.tests 的精确 case ID，evidence 包含该测试文件的断言行。场景 supported 仅指断言设计，不是已执行。一个 supported 功能不能掩盖同通道 gap/unknown 场景。PR 影响必须映射到相关 feature 的场景；每条已审行为变更都要有影响记录，文档/格式-only PR 可在 PR 层说明排除理由。

场景 ID 使用稳定语义键，如 `G_SPARSE:cu72-supported`；缺口场景通过 `tasks[].cases[].id` 原样交接，重排不改 ID。缺口、未知和待审都需要 followup。为代码测例任务写 `required_evidence`（默认 positive、negative_control、ci_selection）；验收要求真实 CI 时必须加 ci_execution。不能在生成阶段为通过验收悄悄降低证据要求。

实际执行仍按 branch-contract.md 的每通道 all/any 必测组核查。any 只能用于明确等价的替代测试，不可把正常、边界、异常当替代项。深审时每个声称已通过的行为场景必须在必测组里有所体现。

## 输出与交接

标准聊天结论中增加：功能台账已审/待审/排除/未知数量；关键场景→断言→执行的对应关系；高风险 PR 的改前/改后及遗漏场景。完整 Markdown 自动包含功能分母、场景追踪和 PR 影响表。仍分开报告设计、选择、调度、实际执行；本工具不产生全仓行覆盖率。
