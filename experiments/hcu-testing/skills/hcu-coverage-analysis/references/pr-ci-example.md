# AI Review agent 调用示例：SGLang PR #436

以下是 2026-09-28 的只读实测摘录，不是模板虚构结果；后续运行须重新采集。未触发 CI、发表评论或占用 HCU 设备。

## 交给外层 agent 的请求

```text
使用 hcu-coverage-analysis 的 PR CI Review 模式，审查
https://github.com/HYGON-AI/sglang-das/pull/436。
目标平台 HCU gfx936，重点检查 PR HCU CI 是否覆盖新增行为。
固定 PR base/head，读取实际 run/job/attempt 与失败日志，区分
断言设计、CI 选择、具体行为执行；说明替代测试为何足够或不足。
只读审查，不重跑、不评论、不执行 PR 代码。
输出中文 report.md、review.json 和可交给 hcu-test-generation 的
test-backlog.json；缺证据写未知，不用文件成功率充当代码覆盖率。
```

本地安装时可写 `$hcu-coverage-analysis`；其他 AI Review 框架让 agent 读取本目录 `SKILL.md` 即可。Skill 不是平台 API，不假设 aireview 已有专用调用接口。

## 输出摘录

**审查结论：建议补充或修正测试/CI（changes_recommended），不等于发现产品缺陷或拒绝合并。**

| 项目 | 结果 |
|---|---|
| PR | [#436：HCU gfx936 DeepSeek-V4 INT8 Persistent Paged MQA](https://github.com/HYGON-AI/sglang-das/pull/436) |
| 目标分支 | release/20260825_v0.5.18 |
| base | 50beda6a90ba4dd7c85d667530c2614b13122fbf |
| head | 6f0f185a691c16b0134a26f2ff172c7e2af31edb |
| 审查范围 | 4 个变更文件，3 类新增行为；不是全仓审计 |
| CI 事实 | [HCU run 35820902721](https://github.com/HYGON-AI/sglang-das/actions/runs/35820902721)，attempt 2：Stage A 成功，Stage B 3 个分片成功、required-2 失败 |
| 失败日志 | [job 107080422410](https://github.com/HYGON-AI/sglang-das/actions/runs/35820902721/job/107080422410)：10/15 **测试文件**通过；存在 HIPBLAS_STATUS_ALLOC_FAILED、端口占用、连接失败症状；不能因此认定新内核回归 |
| 代码覆盖率 | 无同版本 coverage 工件，未测量 |

| 行为 | 断言设计 | CI 选择 | 具体行为执行 | 补测方向 |
|---|---|---|---|---|
| B1 路由选择/回退 | 已审范围缺口 | 未知 | 未核验 | 开关、容量比 2.0 边界、gfx936、dtype/shape/layout/device、spec/ragged 长度 |
| B2 INT8 数值/边界/TopK | 已审范围缺口 | 未知 | 未核验 | 0/1/63/64/65/255/256/257、混合长度、页表、scale、有效区及 TopK |
| B3 capture/replay | 已审范围缺口 | 未知 | 未核验 | 预热后捕获，固定 shape 改变长度/页表并多次重放 |

证据依据：

- [开关默认关闭](https://github.com/HYGON-AI/sglang-das/blob/6f0f185a691c16b0134a26f2ff172c7e2af31edb/python/sglang/srt/environ.py#L1397)。需要证明新路径命中，不能拿普通 smoke 的绿灯代替。
- [路由逻辑](https://github.com/HYGON-AI/sglang-das/blob/6f0f185a691c16b0134a26f2ff172c7e2af31edb/python/sglang/srt/layers/attention/dsv4/indexer.py#L118)和 graph 分支是新增行为，需要分别审查。
- [已有 DSV4 attention 测试](https://github.com/HYGON-AI/sglang-das/blob/6f0f185a691c16b0134a26f2ff172c7e2af31edb/test/registered/attention/unittests/dsv4/test_deepseek_v4.py#L1)明确绕过 C4Indexer；[已有 HCU DSA 测试](https://github.com/HYGON-AI/sglang-das/blob/6f0f185a691c16b0134a26f2ff172c7e2af31edb/test/registered/unit/layers/attention/dsa/test_hcu_indexer.py#L1)测另一条 DSA/LightOp ABI，不能据同名 MQA 推断已覆盖。
- [新内核](https://github.com/HYGON-AI/sglang-das/blob/6f0f185a691c16b0134a26f2ff172c7e2af31edb/python/sglang/srt/layers/attention/dsv4/csrc/paged_mqa_pers_jit.cu#L426)不保证全部容量尾部初始化；数值 oracle 应比较有效区并核验下游 TopK 长度限制，不能生成错误的全矩阵断言。

### 补测交接

| 任务 | 路由 | 稳定场景 ID | 验收重点 |
|---|---|---|---|
| G1 | write | G1-route、G1-length | 真实路由函数的正反例；CPU结果不冒充HCU计算验证 |
| G2 | upstream_first | G2-boundary、G2-width | 兼容上游参考/独立数值 oracle，gfx936正确性；非法宽度单测单列 |
| G3 | write | G3-replay | 多次重放随输入改变，旧状态负控应失败 |

三个任务通过 `check_handoff.py --task G1 --task G2 --task G3` 形成 generation-plan，保留 PR 上下文、源码指纹、场景合同。此处验证了交接，不表示三个新增硬件测试已经编写或通过。

限制：只读检查已有 CI；缺全部分片日志/外部配置和同版本覆盖率工件；分支保护旧接口不可见，不能推断无门禁。报告保留“已审范围缺口”和“实际执行未知”的区别。CI 红灯根因另行定位，不据 PR 正文“Not run”推断没有实际运行。
