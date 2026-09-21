"""Agent-reviewed bounded example for one pinned SGLang source revision.

This is not an automatic feature detector or a full-repository audit.
Run audit.py render against the pinned clean checkout to validate its references.
"""
import argparse
import json

SHA = '16229e94d0a0a218875ab0db2133c12d9695abd1'
PR = '.github/workflows/pr-test-hcu.yml'
DAILY = '.github/workflows/nightly-test-hcu.yml'
METRICS = 'test/registered/unit/observability/test_metrics_utils.py'
COMPILE = 'test/registered/backends/test_torch_compile.py'
KV = 'test/registered/attention/test_create_kvindices.py'
ATTN = 'test/registered/hcu/kernels/test_attention_reference_hcu.py'


def evidence(id, path, start, end, claim):
    return dict(id=id, kind='source', path=path, start=start, end=end, claim=claim)


def cell(selection, coverage, reason, *refs):
    return dict(selection=selection, coverage=coverage, execution='not_verified', reason=reason, evidence=list(refs))


def case(name, inputs, expected, oracle, negative_control):
    return dict(name=name, inputs=inputs, expected=expected, oracle=oracle, negative_control=negative_control)


def build():
    refs = [
        evidence('PRODUCT', 'README.md', 56, 69, '仓库声明 torch.compile 和 paged attention 等能力；不是 HCU 全功能认证。'),
        evidence('METRIC_API', 'python/sglang/srt/observability/utils.py', 34, 56, '默认桶排序去重、规则分发与指数桶函数实现。'),
        evidence('METRIC_TEST', METRICS, 1, 151, '指定文件的现有测试；默认输入已排序且无重复，未测试指数桶函数，空列表注释实际再次传 None。'),
        evidence('PR_LIST', PR, 780, 838, 'Stage-B 显式白名单与分片；包含 metrics 和 KV 文件，不含通用 torch_compile 文件。'),
        evidence('COMPILE_TEST', COMPILE, 23, 97, 'HCU 注册禁用及原因；测例已有，包含启动参数与吞吐阈值，不能直接认定 HCU 阈值适用。'),
        evidence('KV_TEST', KV, 1, 151, 'KV 索引与页表重建测试，含参考结果和相等断言；只支持这里实际枚举的配置。'),
        evidence('DAILY_TRIGGER', DAILY, 1, 58, 'daily cron 与手动过滤入口；不能代替实际执行记录。'),
        evidence('DAILY_MATRIX', DAILY, 641, 678, 'core-functional 和 one-hcu 的矩阵、nightly 标志和前置条件。'),
        evidence('DAILY_COMMAND', DAILY, 1044, 1075, '通过原生 runner 执行 suite，传递 nightly、分片和可选白名单。'),
        evidence('ATTN_TEST', ATTN, 4, 115, '已注册 nightly core-functional；Torch 独立参考与两种 BF16 配置比较，阈值 1e-2。'),
    ]
    feature = lambda id, name, requirement, sources, path, kind, assertion, test_ref, lanes: dict(
        id=id, name=name, requirement=requirement, evidence=sources,
        tests=[dict(path=path, assertion_kind=kind, assertion=assertion, evidence=[test_ref])], lanes=lanes)
    features = [
        feature('F_METRICS', '监控桶生成', '默认桶排序去重、空规则与指数序列的边界行为', ['METRIC_API'], METRICS, 'behavior',
                '常规规则结果已断言，但默认去重和指数序列缺少有区分力的场景。', 'METRIC_TEST', {
                    'pr': cell('included', 'partial', '该文件进入 PR 白名单；函数覆盖和断言范围不完整。', 'PR_LIST', 'METRIC_TEST'),
                    'daily': cell('unknown', 'unknown', '本轮未完成所有 nightly/复用入口的映射，不能声称日常没有该能力。', 'DAILY_TRIGGER', 'DAILY_COMMAND', 'METRIC_TEST')}),
        feature('F_COMPILE', 'torch.compile HCU 验证', '已有编译服务测例在 HCU 上有可重复、适合该平台的验收依据', ['PRODUCT'], COMPILE, 'performance',
                '启动编译模式并检查吞吐；还有混入的精度套件。阈值是否适合当前 HCU 需单独复核。', 'COMPILE_TEST', {
                    'pr': cell('disabled', 'gap', '测试已存在但 HCU 注册禁用，并且不在 PR 白名单。应先验证已有测例，不应重复生成。', 'COMPILE_TEST', 'PR_LIST'),
                    'daily': cell('unknown', 'unknown', '该文件的 PR 禁用不证明其他 HCU nightly 编译测例也缺失；需查替代测试。', 'COMPILE_TEST', 'DAILY_MATRIX')}),
        feature('F_KV', 'KV 索引与页表重建', '已枚举的 batch/page-size/window-start 组合与参考索引相等', ['PRODUCT'], KV, 'numerical',
                '比较生成索引与参考；batch=1/37/1786，页尺寸=4/64/256，覆盖窗口开关。不是所有 shape 的证明。', 'KV_TEST', {
                    'pr': cell('included', 'supported', 'PR 白名单包含文件，静态断言支持此限定合同；本轮未核验 CI 执行日志。', 'PR_LIST', 'KV_TEST'),
                    'daily': cell('unknown', 'unknown', '未证明 nightly 是否直接或间接复用这些精确场景。', 'DAILY_COMMAND', 'KV_TEST')}),
        feature('F_ATTN_NIGHTLY', '日常 BF16 decode attention 参考', '日常专用参考测例中的两种 MHA/GQA 小规模配置', ['PRODUCT'], ATTN, 'numerical',
                '独立 Torch softmax/einsum 参考与设备结果比较，限定两种配置、seq_len=17。', 'ATTN_TEST', {
                    'pr': cell('not_applicable', 'not_applicable', '此条仅审计日常专用合同；PR 的其他 attention 测例不在本条判断范围，不要求机械复制。', 'ATTN_TEST', 'PR_LIST'),
                    'daily': cell('included', 'supported', '标准定时配置且前置 gate 成功时进入 core-functional；两种配置有参考断言。没有新鲜 CI 运行证据。', 'ATTN_TEST', 'DAILY_MATRIX', 'DAILY_COMMAND')}),
    ]
    tasks = [dict(id='G_METRICS', feature_id='F_METRICS', priority='P1', lanes=['pr'], route='upstream_first',
                  reason='现有 PR 测例无法保证默认桶排序去重和指数序列边界；优先复用已验证的补充测试或上游等价测试。',
                  evidence=['METRIC_API', 'METRIC_TEST', 'PR_LIST'], cases=[
                      case('默认桶非有序重复输入', '[4,1,4,2]；rule=None/[]/[default]', '[1,2,4]，原输入不变', '明确期望数组', '删除排序去重时断言必须失败'),
                      case('指数序列和零长度', 'start=.25,width=2,length=4；length=0/1；非整数倍率1.5', '[.25,.5,1,2]；空序列；首项不偏移', '手算序列，注明浮点容差', '指数由 i 改为 i+1 时断言必须失败')],
                  prerequisites=['CPU 单测，兼容的 SGLang Python 环境；无需模型或加速卡'],
                  acceptance=['不重复现有覆盖；目标测试实际执行而非 skip', '两种负向控制在独立副本被拒绝', '原生 PR 收集结果包含拟补充的位置'],
                  search=['先查本仓同功能测试和已有实验补充测试', '由仓库元数据确认 sglang 上游，再检索 exponential_buckets/generate_buckets 测例；记录实际 commit 和许可证']),
             dict(id='G_COMPILE', feature_id='F_COMPILE', priority='P1', lanes=['pr'], route='validate_existing',
                  reason='这是已有测试缺少适用性/重复验证和 CI 接入证据的问题，不是无测试。禁止直接删 disabled 或沿用其他平台吞吐阈值。',
                  evidence=['COMPILE_TEST', 'PR_LIST'], cases=[
                      case('已有编译服务用例适用性', '现有 --enable-torch-compile 和 batch 限制；固定模型/DTK/设备', '服务运行、预期输出及有依据的平台阈值，明确重复运行结果', '已有用例合同和经审核 HCU 基线', '错误输出/未运行编译路径/低于经审核阈值不能通过')],
                  prerequisites=['分配可用 HCU 和本地模型、数据、兼容依赖；明确超时', '恢复 CI 必测门禁需另行授权'],
                  acceptance=['说明当前禁用原因是否消除并保存重复验证证据', '若需修改用例或 CI，单独提出小补丁；不通过扩大容差掩盖失败'],
                  search=['先读已有 test_torch_compile.py 及 MMLUMixin', '搜索 HCU nightly torch_compile 替代测试，避免重复建设']),
    ]
    for fid, name, test_ref in [('F_METRICS', '监控桶', 'METRIC_TEST'), ('F_COMPILE', '编译路径', 'COMPILE_TEST'), ('F_KV', 'KV 索引', 'KV_TEST')]:
        tasks.append(dict(id='G_DAILY_' + fid[2:], feature_id=fid, priority='P2', lanes=['daily'], route='clarify_requirement',
                          reason=name + '的日常映射尚未确认；先查现有入口/等价测例，不把未知当作缺测例。',
                          evidence=[test_ref, 'DAILY_TRIGGER', 'DAILY_COMMAND'],
                          cases=[case('确认日常选择链路', '定时默认配置、suite、nightly 标志、filters 和注册状态', '得到可引用的包含/排除/条件选择结论及等价场景映射', '配置、原生只收集结果和可用 CI 运行工件', '仅文件存在或套件名含 nightly 不得判定覆盖')],
                          prerequisites=['完整日常工作流及脚本可读；运行工件不可用时保留 not_verified'],
                          acceptance=['补全此矩阵单元证据；如果真有缺口再拆分补测/接入任务'],
                          search=['追踪 nightly-test-hcu.yml、run_suite.py、nightly 注册和等价测试，不启动模型测试']))
    return dict(schema_version=1, repository='https://github.com/HYGON-AI/sglang-das', source_commit=SHA,
                scope=dict(platform='HCU BW1100', lanes=['pr', 'daily'], extent='bounded',
                           feature_basis='依据产品 README、监控函数合同及现有测试，审阅四个限定功能条目；不是从测试数量推导全仓功能分母。',
                           limitations=['这是新版 Skill 的四条目实仓样例，不是全仓完整性审计。',
                                        '未审阅所有模型/量化/分布式/API/性能组合；未执行测试或核验近期 CI 工件。',
                                        '本轮静态审阅；历史手工通过结果不代表当前 PR/日常实际执行。',
                                        '三个日常映射保留未知；不应解释为日常没有覆盖。']), evidence=refs, features=features, tasks=tasks)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    a = p.parse_args()
    with open(a.output, 'x', encoding='utf-8') as stream:
        json.dump(build(), stream, ensure_ascii=False, indent=2)
