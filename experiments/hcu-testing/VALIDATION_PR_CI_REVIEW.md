# PR CI Review 验证记录（2026-09-28）

## 本次范围

在 hcu-coverage-analysis 增加单PR只读审查模式；新增元数据采集、中文结构化报告/证据校验、生成任务交接。保留原分支模式。hcu-test-generation 保留并检查PR上下文，runner 修正Windows中文源码/日志编码。没有修改SGLang产品代码或CI，也没有占用节点设备。

## 自动化结果

- 技能工具回归：**160 passed，47 subtests passed**（145.51秒）。
- 三个技能 quick_validate 全部通过；仓库 validate_skills、generate_catalog及--check通过；git diff --check通过。
- 新增PR模式23项测试，覆盖移动/过期head、脏副本、遗漏diff文件、证据路径/行号、未知不冒充缺口、job绿灯不冒充场景通过、跳过/错误、平台/lane/attempt身份、禁止跨run/attempt拼接、数组合同、PR交接、UTF-8和API分页/权限缺失。

```bash
python -m pytest experiments/hcu-testing/tests \
  --ignore=experiments/hcu-testing/tests/test_hcu_smoke.py \
  --ignore=experiments/hcu-testing/tests/test_sglang_metrics_generated.py \
  --ignore=experiments/hcu-testing/tests/test_skillhub_generated.py -q
```

三项排除是历史业务集成样例，不是被删除或改skip的工具回归：分别需要Torch/HCU、目标SGLang安装、TARGET_SKILLHUB_ROOT。首次无差别unittest discover 因这些前置条件产生3个导入错误，未记为通过；本次不为它们安装依赖或运行目标产品。

## 真实PR端到端

- 仓库：HYGON-AI/sglang-das；PR #436；目标 release/20260825_v0.5.18。
- base：50beda6a90ba4dd7c85d667530c2614b13122fbf。
- head：6f0f185a691c16b0134a26f2ff172c7e2af31edb。
- 只读采集9个run，补齐预算内job详情；文件列表完整、采集前后版本一致；保护旧接口不可读仍记未知。
- pr_review.py：review_validated，changes_recommended，4文件/3行为/3任务。
- check_handoff.py：ready_for_review，G1/G2/G3，保留PR上下文、源码指纹及5个稳定场景ID，默认要求正例、反例、CI选择和真实CI执行证据。
- 实际HCU run 35820902721 attempt2：Stage A成功，Stage B三个分片成功、required-2失败。读取后者真实日志，不能沿用PR正文状态判断“未运行”。该job文件汇总10/15通过，含资源/服务失败症状；未证明是本PR引入的产品回归。
- 新增Persistent路径的三个行为均未取得具体执行证明；设计缺口与执行未知分开。没有coverage工件，未提供虚构覆盖百分比。

具体调用和精简报告见 [PR示例](skills/hcu-coverage-analysis/references/pr-ci-example.md)。原始快照、脱敏日志摘录、分析输入、报告JSON/Markdown、补测清单、计划及JUnit保存在本次本地报告目录；未将原始环境日志上传仓库。

## 独立forward-test

第二agent只收到技能、原始快照和干净PR head，没有预设结论或主流程报告。独立输出经CLI校验通过，也是4文件/3行为/3任务。其审查发现并推动修复两类实质问题：跨运行通过子集拼接、验收/前置条件数组类型漏校验；均添加负例回归。另明确实际workflow非base/head版本的artifact证据路径，避免伪标源码版本。

## 尚不代表什么

验证了PR审查及测例生成任务交接，不代表G1/G2/G3硬件测例已经编写或执行通过，不代表批准合并，也不证明全仓功能分母完整。AI Review平台的评论发布、权限隔离与幂等更新仍由外层集成实现。
