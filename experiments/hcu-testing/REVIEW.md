# HCU 测试 Skills 私仓试验评审

日期：2026-09-20。状态：已完成第一轮节点实测，适合继续私仓试用，暂不作为正式产品认证发布。

## 交付内容

三个自包含的原型：`hcu-test-generation`、`hcu-test-runner`、`hcu-coverage-analysis`。根据 skill-creator 和仓库 skillhub-contributor 规范编写，frontmatter 仅含 name/description，无兄弟 Skill 强依赖。实现采用原创脚本，来源思路见 PROVENANCE.md。

分支：`codex/hcu-testing-skills`；变更在 `experiments/hcu-testing/`。本文件记录第一轮验证，后续 SGLang 验证见 [VALIDATION_SGLANG.md](VALIDATION_SGLANG.md)。本版本用于个人仓库分支试用，未登记到正式 catalog，原 components/skills/catalog 文件未改动。原始基线为 dc2bd2889f07ed35b975dbea31ba27b293fc5d5c。

## 实测结果

| 验证项 | 结果 | 含义 |
|---|---|---|
| 三个 Skill 格式校验 | 全部通过 | 命名、frontmatter、正文结构符合基本规范 |
| SkillHub 原有单测 | 8/8 通过 | 没有改动原产品行为 |
| 新增实际产品测试 | 11/11 通过 | 对真实 skillhub 路径校验函数增加合法、空值、类型错误、绝对路径、越界路径等测试 |
| 缺陷注入 | 11 项中 2 项按预期失败 | 在独立副本移除路径越界检查后，新测试确实检测到缺陷 |
| 脚本边界测试 | 11/11 通过 | 含全跳过、错误报告、非零退出、真实超时、统计口径等 |
| 执行器 CLI 实测 | 4/4 通过 | 在临时项目执行通过、失败、全部跳过、超时四类真实 pytest 进程 |
| 真实 HCU | 10/10 通过，两次运行 | BW1100 单设备，FP32/FP16/BF16 矩阵乘法、非连续/空张量、错误形状、错误结果断言 |
| 来源校验反例 | 全部按预期拒绝 | 错误 Commit、脏源码、无匹配的变更行 |
| 汇总验证 | 12/12 检查组通过 | 见 verification.json；检查组包含上述各项，不能与测试数简单相加 |
| 正式目录验证与生成结果检查 | 通过 | 正式 catalog 保持一致 |

PyTorch 2.11.0，HIP 6.3.26113，Python 3.10.12。HCU 镜像 ID：sha256:2c8bbb0e9dfc974f9b797c3c58051b16a89c8de542ae5bde70bac62cc88969d5。

## 覆盖率结果和修正

对隔离的 skillhub 基线源码 `scripts/` 运行 Coverage.py 7.6.1：原有测试覆盖 118/396 行（29.80%），加入 11 个生成测试后覆盖 120/396 行（30.30%）。只提升两个可执行行，但新增边界用例能发现路径越界缺陷，不能单看覆盖率涨幅评判价值。

初版分析器直接数 executed_lines，误把两个非语句的跟踪行计入总数。已修正为使用 Coverage.py 官方语句统计；变更行模式调用其公开 analysis2 API。已增加含模块文档字符串的回归用例。最终结果为 `coverage-analysis-v2.json`；旧 `coverage-analysis.json` 为保留的错误版本证据，不应用于结论。

这份覆盖率属于 skillhub 的 Python 脚本，不是 HCU 设备内核、vLLM 或 SGLang 的覆盖率。

## 节点影响

硬件测试容器限制为 2 CPU、8 GiB 内存、256 MiB 共享内存、256 进程；网络隔离、非特权，未使用 host IPC、SYS_PTRACE 或 seccomp=unconfined。只读挂载宿主机驱动目录，仅写入本次独立 evaluation 目录。通过 HIP_VISIBLE_DEVICES=0 选择一个逻辑设备执行小张量测试；这属于软件可见性限制，不是调度器级别的硬件预留。

未安装宿主机软件、未修改宿主机驱动、未改现有 Runner 配置、未挂载模型或用户公共工作目录。coverage 只安装在一次性容器内；原镜像未修改。使用的所有测试容器结束后删除，保留源文件、下载的测试依赖与日志用于复核。

## 完成度和下一步

- 测试执行器：已完成真实 HCU 单设备验证和主要失败路径验证，可私仓试用。
- 覆盖率分析：已完成真实 Python 项目和统计修正验证，可私仓试用；需在更多项目、覆盖率版本与路径形式上扩大验证。
- 测试生成：已按 Skill 流程人工驱动 Agent 完成实际用例生成与缺陷检测；尚未做多轮独立 Agent 自动触发/稳定性评测。
- 未实现上游回归归因 Skill：需要实际成功/失败运行的版本清单和日志，以避免按时间窗口猜测原因。
- 未验证 vLLM/SGLang 模型服务、多卡、跨版本兼容、性能基线。不得用本次小张量测试宣称这些能力已通过。

正式收录前，按现有 CONTRIBUTING.md 选定产品来源仓库、维护团队和发布范围，先在产品仓库维护 Skill，再通过组件登记同步到 SkillHub。当前实验原型不改动准入规则。
