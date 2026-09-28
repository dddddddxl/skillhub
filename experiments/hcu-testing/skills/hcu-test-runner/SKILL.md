---
name: hcu-test-runner
description: 使用 pytest 或 SGLang 海光原生入口执行选定 Python 测例，记录结果、设备预检和源代码版本。适用于海光适配验证；不负责安装驱动或发布测试结果。
---

# 海光测试执行

默认用中文解释执行方案、失败原因与验证边界，保留原始命令和测试标识。

SGLang HCU PR 测试套件/白名单场景先阅读[原生入口说明](references/sglang.md)，使用对应适配器。下面的 pytest 工具不实现原生套件选择；原生日志与 JUnit 是不同证据格式，不能承诺原生运行一定产出 JUnit。

阅读目标仓库的测试说明，只选择范围明确的入口。在隔离副本或容器内运行，并确认所需 DTK 环境。设备节点存在或 `device_count()` 大于零都不能单独证明 HCU 可用：设备预检工具还会分配张量、计算并同步。

## 执行方式

使用 Python 3.8 及以上运行自带工具：

```bash
python /path/to/skill/scripts/run_tests.py --repo /path/to/checkout --output /path/to/new-results --require-hcu -- tests/test_selected.py
```

CPU 测试不加 `--require-hcu`。`--` 后是 pytest 参数。输出必须是代码副本之外的新目录，包含 `result.json`、`junit.xml` 和 `test.log`。容器运行时通过 `--image-id` 传入不可变镜像 ID；工具记录该值，不自动推断。

结果同时保留逐条 JUnit classname/name 身份和工件 SHA256；JUnit 没有 file 时不猜路径，审计需另行对齐。dirty 运行仍需单独记录真实补丁和安装包/build 身份，不能用基础提交冒充改后版本。原始日志分享前脱敏，脱敏后的工件重新计算 hash。

## 判定与安全边界

结合退出码和 JUnit 数量判定：零收集、全跳过、报告损坏、超时和缺硬件都不是通过。CPU 成功不代表 HCU 验证成功。保留失败证据，不能为变绿修产品代码、弱化断言、增加跳过或改容差；环境失败先报告缺失条件再决定重试。

工具以当前权限运行已审阅的仓库测试。使用满足任务的最小设备分配和明确时间预算。报告源提交、工作区修改状态、选定测试、镜像、环境及未验证范围。日志可能含项目数据，分享前必须审查。
