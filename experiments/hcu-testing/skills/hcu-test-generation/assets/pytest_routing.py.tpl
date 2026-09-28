"""路由与回退：填写任务、源提交及 CI 命令；通过不代表内核数值正确。"""
import pytest


def case_specs():
    # [{id: "G_ROUTE:cu72", kwargs: {cu: 72}, expected: "sparse"}, ...]
    # 分别列正例、单条件边界及有依据的组合回退；收集时不调用产品。
    raise NotImplementedError("模板未填充：请定义路由场景")


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        cases = case_specs()
        ids = [case["id"] for case in cases]
        if not ids or any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("场景不能为空且 ID 必须唯一")
        metafunc.parametrize("case", cases, ids=ids)


@pytest.fixture
def select():
    raise NotImplementedError("模板未填充：请导入真实选择函数")


def route_key(result):
    # 只提取路由标识/分组，不重新计算选择条件。返回简单标识的函数可原样返回。
    return result


def test_route_contract(case, select):
    assert route_key(select(**case["kwargs"])) == case["expected"], case["id"]
