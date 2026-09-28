"""NumPy/PyTorch 数值合同：填写任务、源提交、独立参考、精度依据和 CI 命令。

只使用目标仓库已有依赖。torch 分支检查实际输出设备；不自行分配卡或 mock 内核。
"""
import copy
import math
import pytest


def case_specs():
    # [{id: "G_NUM:signed", spec: [-2.0, 0.0, 3.0], kind: "numpy",
    #   dtype: "float64", rtol: 1e-6, atol: 1e-8}, ...]
    # torch 场景另外填写 device（如 "cuda:0"）、dtype（如 "torch.float16"）。
    raise NotImplementedError("模板未填充：请定义数值场景及容差依据")


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        cases = case_specs()
        ids = [case["id"] for case in cases]
        if not ids or any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("场景不能为空且 ID 必须唯一")
        metafunc.parametrize("case", cases, ids=ids)


@pytest.fixture
def implementations():
    # 返回 (真实被测函数, 独立参考)，两者接收规格并各自构造输入。
    # 必须审阅参考来源；两个不同函数对象仍可能错误地共用同一实现。
    raise NotImplementedError("模板未填充：请接入真实计算与独立参考")


def test_numerical_contract(case, implementations):
    run, reference = implementations
    assert run is not reference, "不能直接以被测函数充当参考"
    rtol, atol = case["rtol"], case["atol"]
    assert all(math.isfinite(t) and t >= 0 for t in (rtol, atol)), case["id"]
    expected = reference(copy.deepcopy(case["spec"]))
    actual = run(copy.deepcopy(case["spec"]))
    assert actual.shape == expected.shape, case["id"]
    assert str(actual.dtype) == case["dtype"], case["id"]
    if case["kind"] == "torch":
        import torch
        assert isinstance(actual, torch.Tensor) and isinstance(expected, torch.Tensor)
        assert str(actual.device) == case["device"], case["id"]
        torch.testing.assert_close(actual.cpu(), expected.cpu(), rtol=rtol, atol=atol,
                                   check_dtype=False, equal_nan=False)
    elif case["kind"] == "numpy":
        import numpy as np
        assert isinstance(actual, np.ndarray) and isinstance(expected, np.ndarray)
        np.testing.assert_allclose(actual, expected, rtol=rtol, atol=atol, equal_nan=False)
    else:
        raise ValueError("按目标仓库增加明确数值断言，不能提供空比较回调")
