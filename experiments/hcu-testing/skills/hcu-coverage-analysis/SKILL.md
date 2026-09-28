---
name: hcu-coverage-analysis
description: 审计仓库分支或单个 PR 的测试与 CI 覆盖：结合行为变更、具体断言、有效测试选择和实际运行证据，识别缺测例、弱断言、CI 故障和证据不足，输出中文报告及可交接补测清单。适用于 AI Review agent 审查 PR 的 CI 质量。
---

# 海光功能测试覆盖审计

默认用中文输出审计报告、缺口理由和补测建议；保留代码路径、任务 ID 与机器可读字段名称。

## 单个 PR 的 CI Review

输入为 PR URL/编号，或调用方明确要求审查某个 PR 的测试与 CI 时，阅读[PR CI 审查流程与数据约定](references/pr-ci-review.md)。使用 `pr_snapshot.py` 收集 PR、变更文件、checks/statuses、run/job 和可读取的门禁配置；使用 `pr_review.py` 校验并生成中文 `report.md`、`review.json` 和 `test-backlog.json`。

从固定 base/head 的行为变化出发，核查具体测试断言、workflow 触发条件、矩阵和选择参数。PR head、测试合并提交、合入后的发布提交分别记录。绿色 job、PR 描述中的“已测试”和测试注册都不能代替具体场景执行证据；日志拿不到时仍完成静态审查，保留未知项。

给 AI Review agent 的调用方式和实际 SGLang 示例见[调用示例](references/pr-ci-example.md)。此模式审查 PR 变更范围；全仓功能分母及近期多个 PR 的审计走下面的分支模式。默认只读，审查意见输出到调用方；补测、重跑 CI、发布评论按用户已经授权的范围执行。

## 分支测试缺口审计

阅读[功能审计流程](references/functional-audit.md)和[分支审计数据约定](references/branch-contract.md)。先取得实际 CI 运行及测例身份，再将业务合同、近期 PR 行为变更映射到具体断言。输出 v2 报告、实际测例清单、PR 变更矩阵和补测任务。

新审计按[行为深审约定](references/behavior-depth.md)建立功能分母台账、逐场景断言映射和 PR 改前/改后影响链，并启用 behavior 校验。源码导航索引只帮助找到实现、调用者和继承关系；未审模块、动态路径和预算外 PR 必须保留为待审，不能算已覆盖。

面向用户的报告按[标准输出格式](references/output-format.md)组织。用户要求直接在聊天中查看时，使用其中的精简版结构输出结论，不要只给附件或原始 JSON；审计多个分支时，每个分支单独给出完整结论，再提供横向对比。

[旧版约定](references/audit-contract.md)仅用于兼容 v1 报告；新审计不能因此省略分支、实际运行或近期 PR 分析。

按[CI 证据采集说明](references/ci-evidence.md)采集运行证据。SGLang 还须逐项检查真实 job 的矩阵和选择参数。配置存在、注册成功或仅执行收集，不等于测试已经运行。

分开报告四个维度：断言设计、有效选择、分支调度、实际执行。功能合同数量、PR 行为覆盖及实测代码行覆盖率也必须分开；缺少证据记为未知，不能填写零或猜测百分比。

## 范围与输出

默认只读分析。不要为了审计擅自启动测试套件、下载模型、改变 CI 门禁或生成测试补丁。区分缺测例、被排除/禁用、断言不足、运行证据缺失和需求不明确。PR 与日常测试分别评估，不能互相充当通过证据。

补测清单可交给 `hcu-test-generation`，也可由其他智能体按任务字段处理，不强制安装关联 Skill。生成清单不等于授权执行或发布。

## 可选：Python 代码行覆盖证据

有 coverage.py 报告时可使用下面的工具，将未覆盖行关联到具体功能/场景。功能审计不以该报告为前提，也不能将代码行覆盖率等同于功能覆盖率。

取得来源明确的新 coverage.py JSON，并记录采集时的提交；传入干净代码副本。旧报告仅因文件存在，不能被复用。检查实际采集范围和告警：仓库的 coverage `source` 配置可能覆盖命令行 `include`。窄范围评估须在采集和导出时保持同一明确配置，不能给广范围报告换个标签。

```bash
python /path/to/skill/scripts/analyze.py --repo /path/to/checkout --coverage /path/to/coverage.json --tested-commit FULL_SHA --output /path/to/report.json
```

加 `--base-ref BASE_SHA` 可分析变更行，基线必须是测试提交的祖先。在隔离环境使用与采集端一致的 coverage.py 版本，已验证版本为 7.6.1。变更行模式通过公开分析接口排除非语句行；全文件模式使用语句统计，不直接统计原始 trace 长度。

该工具衡量新增/修改的可执行 Python 语句，不涵盖删除代码或所有上游差异。覆盖路径必须位于代码副本内，报告使用相对路径。

读过未覆盖代码再判风险，优先关注 HCU 分发、不支持功能的回退、dtype/shape 和近期缺陷。语句数量不能证明数值、分支、分布式、性能或内核正确性。工具会检查来源、路径和格式；仅提供 SHA 并不能证明报告确实来自该提交，仍须核对采集过程并说明限制。
