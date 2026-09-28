# 中文 pytest 小模板

先看目标分支现有测试及收集入口。仅在需要新文件且原生入口支持 pytest 时使用；原有 unittest 文件继续沿用原框架。以下模板独立编写，未复制厂商模板代码。

| 骨架 | 适用范围 |
| --- | --- |
| [pytest_logic.py.tpl](../assets/pytest_logic.py.tpl) | 普通函数的正常、边界、异常合同 |
| [pytest_routing.py.tpl](../assets/pytest_routing.py.tpl) | 支持条件与回退选择，不证明设备计算正确 |
| [pytest_numerical.py.tpl](../assets/pytest_numerical.py.tpl) | 真实计算对比独立参考，内置 NumPy/PyTorch 数值、shape/dtype 断言 |

## 填充与接入

1. 复制选中的 `.py.tpl` 到仓库实际收集的 `test_*.py` 位置。资产后缀避免 SkillHub 本身误收集教学骨架。
2. 填写文件头的缺口 ID、场景、源提交、预期依据、原生收集和执行命令；没有审计任务时建立局部场景 ID。
3. 填充 `case_specs()` 的轻量输入规格及 fixture 中的真实实现。导入产品/初始化设备放在 fixture，不能在收集阶段发生；不自行安装依赖或启动设备任务。
4. 每个 case 的 `id` 直接进入 pytest 参数化和 JUnit；不能为空或重复。保留交接场景 ID，禁止将所有场景塞进一个循环测例。没有异常合同的函数不编造异常；说明不适用即可。
5. 使用仓库已有 fixture 管理文件、服务及设备生命周期；需释放资源时使用 `yield`/`finally`。未授权不得启动服务或加载模型。
6. 先验证 CI 收集和正确实现，再在隔离副本注入目标回归，确认是业务断言失败而不是导入错误。按 completion.md 回填。

## 数值模板的约束

`actual` 必须来自真实被测函数；`expected` 来自规格、已验证基线或独立参考实现，不能包装同一被测函数冒充参考。模板检查 shape、原始 dtype，PyTorch 还检查指定 device，然后用 `torch.testing.assert_close` 或 `numpy.testing.assert_allclose`，禁用 NaN 相等，容差须有限且非负。PyTorch 示例转 CPU 比较只用于结果核对，不证明性能或设备内部路径。其他框架按仓库要求写具体断言；不再接受可能为空操作的比较回调。对象不相同只是最弱的检查，独立 oracle 仍必须人工审阅。

不默认 skip/xfail、不提供 `assert True`、不默认 mock 内核、不预设某张设备。硬件不足应按仓库规则明确报错或跳过，并在验收中记为未验证。模板中的非空检查只能阻止最简单的空用例，不代替预期结果评审和故障注入。
