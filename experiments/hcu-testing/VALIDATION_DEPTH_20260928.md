# 功能深审与补测闭环验证（2026-09-28）

这次在个人仓库实验区统一此前尚未上传的中文入口、测例编写/模板改动，并补强功能分母、PR 行为影响、逐场景执行和完成记录。正式 components.d / skills 目录不变，没有启用任何项目 CI。

## 本轮改进

1. 新审计使用 behavior 深审：功能候选台账保留 reviewed/deferred/excluded/unknown；场景具备输入、预期、独立 oracle、可检出错误和精确断言映射。PR 记录改前/改后、触发、入口、调用者、后端和必测场景。
2. 增加只读 Python AST 导航：直接读 Git blob，保留导入别名、继承和词法调用，以及预算外文件。批量读取避免大仓库逐文件启动 Git 的开销。索引不是自动业务理解或完整调用图。
3. PR 详情预算不再丢掉已检索候选；未展开 PR 与分页截断均显式保留。实际 CI 仍需 case ID、版本/build 和 lane 证据。
4. 修复“只引用通过子集即可把整个功能标为 passed”：默认要求所有映射场景；显式 all/any 分组支持每通道要求，已失败的等价项不能被另一通过项掩盖。
5. 稳定语义场景 ID 从审计传至生成、参数化测试和完成结果；旧清单序号兼容但标记 legacy_ordinal。
6. 三套中文 pytest 模板一场景一结果，收集期不初始化设备；NumPy/PyTorch 模板使用具体数值断言，不接受空比较回调。
7. 增加完成记录检查器：核对工件 hash、场景完整性、版本/补丁、正反例、原始验收及 CI 证据要求。结果只是 evidence_consistent，不自动关闭缺口。
8. 执行器记录逐条 JUnit 结果与工件 hash。修复 Windows 超时只杀父进程、留下子进程占用日志的问题；只终止本次启动的测试进程树。

按 skill-creator 将主要工作流保留在中文 SKILL.md，细节放入引用文档；验证采用实际输入和反例，而非仅匹配文案。

## 回归与规范检查

本地 Windows / Python 3.10，隔离验证环境补充 PyYAML 6.0.3、coverage.py 7.6.1，使用已有 pytest/NumPy。未安装/更改节点环境，未占用 GPU。

| 检查 | 结果 |
|---|---|
| test_*audit.py（含模板、深审、交接、完成记录） | 105 / 105 通过 |
| test_helpers.py | 12 / 12 通过 |
| test_runner_cli.py | 4 / 4 通过 |
| test_sglang_adapter.py | 16 / 16 通过；首次 Windows 超时回归失败，修复后通过 |
| source_index 批量读取改动后重跑 test_depth_audit.py | 9 / 9 通过，属于上面 105 项的重复验证 |
| 三个 Skill 的 quick_validate.py | 全部通过 |
| validate_skills.py、generate_catalog.py、--check | 通过；正式目录仍为 1 component / 1 skill，三个实验 Skill 单独校验 |
| git diff --check | 通过 |

共 137 个不同的回归检查通过；这不是 137 个 SGLang 产品测例，也不是 HCU 硬件验证。

可复现命令：

```bash
python -m unittest discover -s experiments/hcu-testing/tests -p 'test_*audit.py' -v
python -m unittest discover -s experiments/hcu-testing/tests -p test_helpers.py -v
python -m unittest discover -s experiments/hcu-testing/tests -p test_runner_cli.py -v
python -m unittest discover -s experiments/hcu-testing/tests -p test_sglang_adapter.py -v
python scripts/validate_skills.py
python scripts/generate_catalog.py --check
```

## 真实 SGLang 固定源码验证

使用已有只读 checkout：HYGON-AI/sglang-das，SHA `50beda6a90ba4dd7c85d667530c2614b13122fbf`。这是固定历史快照，不是本次获取的分支最新状态。

- 对 python/sglang/srt 索引：发现 1726 个 Python 候选，本轮预算内 1000 个全部解析，726 个明确 deferred，另计 411 个非 Python 文件；获得 14481 个符号和 80946 条词法调用。成功定位 HCU sparse MQA 的路由类和选择函数。没有把未分析部分当成覆盖。
- 使用新的普通逻辑模板，对 observability/utils.py 的 generate_buckets 填入 5 个稳定 ID 场景：默认去重排序、custom 转换去重、双侧指数值、非法 base、空默认桶。收集 5 个，正例 5 passed / 0 skipped。
- 在隔离源码副本把默认规则的 sorted(set(default_buckets)) 改成 list(default_buckets)：目标 default-dedup 断言失败，其他 4 个通过，0 setup/import error，进程按预期返回 1。
- 验证直接加载纯 Python 模块副本，避免初始化完整 SGLang 包；原始源码与基线副本的 Git blob 身份一致。未修改 SGLang checkout、原生 unittest 文件、工作流或注册。

这证明模板能够调用真实产品函数、识别具体行为回归并保留逐场景结果；不证明原生 CI 已接入、不构成分支全量覆盖审计、不证明 HCU 数值内核。生成文件与原始日志留在本地证据目录，未把机器路径、内部地址或运行日志上传到公共仓库。

## 仍需人工/智能体判断

- 功能分母是否完整、动态调用和非 Python 后端语义、PR 影响是否遗漏。
- oracle 是否独立、断言是否足够、any 组是否真的等价、验收是否需要真实 CI。
- 工件的原始真实性、安装包/镜像与 checkout 是否相同、GPU/多卡/模型资源约束。

机器检查拒绝已知的结构性误报，但无法把人为编造的完整记录变成真实测试证据。原生 SGLang 适配器仍是受限入口，不是任意 workflow/matrix 的通用执行器。
