"""普通逻辑：填写任务、源提交、独立预期、原生 CI 命令；每个场景独立出结果。"""
import pytest


def case_specs():
    # 仅返回轻量规格；收集时不启动服务、分配设备或导入产品。
    # [{id: "G1:zero", kwargs: {value: 0}, expected: 0},
    #  {id: "G1:negative", kwargs: {value: -1}, error: ValueError, match: "negative"}]
    raise NotImplementedError("模板未填充：请定义有稳定 ID 的业务场景")


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        cases = case_specs()
        ids = [case["id"] for case in cases]
        if not ids or any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("场景不能为空且 ID 必须唯一")
        metafunc.parametrize("case", cases, ids=ids)


@pytest.fixture
def target():
    # 返回真实被测函数。资源型 fixture 用 yield/finally 释放。
    raise NotImplementedError("模板未填充：请导入真实函数")


def test_logic_contract(case, target):
    if "error" in case:
        assert case["error"] not in (Exception, BaseException), case["id"]
        assert case.get("match"), "应检查稳定错误信息，或按有依据的合同调整"
        with pytest.raises(case["error"], match=case["match"]):
            target(**case["kwargs"])
    else:
        assert target(**case["kwargs"]) == case["expected"], case["id"]
