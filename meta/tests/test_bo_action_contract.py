import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - BO Action 注册契约固化（B1）
测试 meta.core.bo_action_contract 模块（契约形状 + 机器校验 + 前置条件求值）

覆盖目标（对齐 §12.1 B1 / §9.1 / §9.2）：
  1. 契约四要件固化：idempotent / preconditions / input_schema / 返回信封
  2. 机器校验器：命名 / schema 形状 / 取值域 / 缓存一致性 / 前置条件形状
  3. 严格模式 assert_registry_contracts 抛错；非严格 report 返回违规数
  4. 前置条件求值：input_present / input_equals / input_in
  5. 注册表 call() 调用 handler 前统一拦截未满足前置条件
  6. 真实 19 个 action 全部合规（B1 未破坏既有注册）
"""

from meta.core.bo_action_contract import (
    ACTION_ID_PATTERN,
    PRECONDITION_KINDS,
    RESPONSE_ENVELOPE_KEYS,
    ActionContractError,
    assert_registry_contracts,
    check_preconditions,
    report_registry_contracts,
    validate_action_meta,
    validate_preconditions,
    validate_registry,
)
from meta.core.bo_action_registry import BusinessActionMeta, bo_action_registry


# ─────────────────────────────────────────────────────────────────────────────
# 夹具
# ─────────────────────────────────────────────────────────────────────────────

def _meta(**kw) -> BusinessActionMeta:
    """构造一个默认合规的 BusinessActionMeta，可按需覆盖字段。"""
    params = dict(
        action_id='demo.action',
        handler=lambda p, c: {'success': True, 'data': None, 'message': 'ok'},
        description='演示 action',
        object_type='*',
        category='business',
        input_schema={'type': 'object', 'properties': {'x': {'type': 'string'}}},
        operation_type='action',
        visibility='normal',
        idempotent=False,
        requires_auth=True,
        requires_admin=False,
        async_supported=False,
        cacheable=False,
        cache_ttl=0,
        preconditions=None,
    )
    params.update(kw)
    return BusinessActionMeta(**params)


class _FakeRegistry:
    """最小注册表替身：validate_registry 只依赖 list_all()。"""

    def __init__(self, metas):
        self._metas = list(metas)

    def list_all(self):
        return list(self._metas)


def _with_isolated_registry(case):
    """在快照-恢复下操作全局单例注册表（避免污染其他测试）。"""
    saved = dict(bo_action_registry._actions)
    try:
        bo_action_registry.clear()
        return case()
    finally:
        bo_action_registry._actions.clear()
        bo_action_registry._actions.update(saved)


# ─────────────────────────────────────────────────────────────────────────────
# 契约四要件固化
# ─────────────────────────────────────────────────────────────────────────────

class TestContractShape:
    """TC-B1-001~004 契约形状固化"""

    def test_TC_B1_001_响应信封常量(self):
        """返回契约 = 统一信封 success/data/message"""
        assert RESPONSE_ENVELOPE_KEYS == ('success', 'data', 'message')

    def test_TC_B1_002_前置条件kind封闭集(self):
        """前置条件 kind 为封闭集合"""
        assert PRECONDITION_KINDS == ('input_present', 'input_equals', 'input_in')

    def test_TC_B1_003_preconditions字段默认空(self):
        """BusinessActionMeta 新增 preconditions 字段，默认 None（不影响既有 action）"""
        assert _meta().preconditions is None

    def test_TC_B1_004_register接受preconditions(self):
        """register() 透传 preconditions，且随 list_schemas 输出"""
        def _run():
            pre = [{'kind': 'input_present', 'field': 'object_type'}]
            bo_action_registry.register(
                'demo.with_pre', _meta().handler, description='带前置条件',
                object_type='*', category='business',
                input_schema={'type': 'object',
                              'properties': {'object_type': {'type': 'string'}}},
                preconditions=pre,
            )
            assert bo_action_registry.get('demo.with_pre').preconditions == pre
            schema = [s for s in bo_action_registry.list_schemas()
                      if s['action_id'] == 'demo.with_pre'][0]
            assert schema['preconditions'] == pre
        _with_isolated_registry(_run)


# ─────────────────────────────────────────────────────────────────────────────
# 机器校验器
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateActionMeta:
    """TC-B1-010~020 单 action 契约校验"""

    def test_TC_B1_010_合规action无违规(self):
        """默认构造的 action 无任何违规"""
        assert validate_action_meta(_meta()) == []

    def test_TC_B1_011_action_id命名非法(self):
        """action_id 不匹配命名规则 → 违规"""
        errs = validate_action_meta(_meta(action_id='Bad-ID'))
        assert any('action_id' in e for e in errs)

    def test_TC_B1_012_handler不可调用(self):
        """handler 非可调用 → 违规"""
        errs = validate_action_meta(_meta(handler=None))
        assert any('handler' in e for e in errs)

    def test_TC_B1_013_object_type缺失(self):
        """object_type 为空 → 违规"""
        errs = validate_action_meta(_meta(object_type=''))
        assert any('object_type' in e for e in errs)

    def test_TC_B1_014_input_schema_required含未声明字段(self):
        """required 含 properties 未声明字段 → 违规"""
        errs = validate_action_meta(_meta(
            input_schema={'type': 'object', 'properties': {'x': {'type': 'string'}},
                          'required': ['y']}))
        assert any('未声明字段' in e for e in errs)

    def test_TC_B1_015_input_schema_type非object(self):
        """input_schema.type 非 object → 违规"""
        errs = validate_action_meta(_meta(
            input_schema={'type': 'array', 'properties': {}}))
        assert any("input_schema.type" in e for e in errs)

    def test_TC_B1_016_output_schema形状非法(self):
        """output_schema 非 dict → 违规"""
        errs = validate_action_meta(_meta(output_schema='not-a-dict'))
        assert any('output_schema' in e for e in errs)

    def test_TC_B1_017_operation_type与visibility取值域(self):
        """operation_type / visibility 越域 → 违规"""
        errs = validate_action_meta(_meta(operation_type='job', visibility='secret'))
        assert any('operation_type' in e for e in errs)
        assert any('visibility' in e for e in errs)

    def test_TC_B1_018_cacheable与ttl一致性(self):
        """cacheable=True 但 cache_ttl<=0 → 违规"""
        errs = validate_action_meta(_meta(cacheable=True, cache_ttl=0))
        assert any('cache_ttl' in e for e in errs)

    def test_TC_B1_019_布尔字段类型(self):
        """idempotent 非 bool → 违规"""
        errs = validate_action_meta(_meta(idempotent='yes'))
        assert any('idempotent' in e for e in errs)

    def test_TC_B1_020_前置条件形状由校验器接管(self):
        """preconditions 非法 kind → 违规（由 validate_preconditions 承接）"""
        errs = validate_action_meta(_meta(
            preconditions=[{'kind': 'magic', 'field': 'x'}]))
        assert any('kind 非法' in e for e in errs)


class TestValidatePreconditions:
    """TC-B1-030~034 前置条件声明形状"""

    def test_TC_B1_030_None合法(self):
        assert validate_preconditions(None) == []

    def test_TC_B1_031_非list违规(self):
        assert validate_preconditions({'kind': 'input_present'})

    def test_TC_B1_032_缺field违规(self):
        errs = validate_preconditions([{'kind': 'input_present'}])
        assert any('缺少 field' in e for e in errs)

    def test_TC_B1_033_input_equals缺value违规(self):
        errs = validate_preconditions([{'kind': 'input_equals', 'field': 'x'}])
        assert any('缺少 value' in e for e in errs)

    def test_TC_B1_034_input_in需非空values(self):
        errs = validate_preconditions([{'kind': 'input_in', 'field': 'x', 'values': []}])
        assert any('values' in e for e in errs)


class TestValidateRegistry:
    """TC-B1-040~043 全表校验 / 严格模式 / 日志模式"""

    def test_TC_B1_040_全合规返回空(self):
        reg = _FakeRegistry([_meta(), _meta(action_id='demo.two')])
        assert validate_registry(reg) == {}

    def test_TC_B1_041_收集违规映射(self):
        reg = _FakeRegistry([_meta(action_id='demo.bad', object_type='')])
        violations = validate_registry(reg)
        assert 'demo.bad' in violations

    def test_TC_B1_042_严格模式抛错(self):
        reg = _FakeRegistry([_meta(object_type='')])
        with pytest.raises(ActionContractError):
            assert_registry_contracts(reg)

    def test_TC_B1_043_日志模式返回违规数(self):
        good = _FakeRegistry([_meta()])
        bad = _FakeRegistry([_meta(object_type=''), _meta(action_id='demo.ok2')])
        assert report_registry_contracts(good) == 0
        assert report_registry_contracts(bad) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 前置条件求值
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckPreconditions:
    """TC-B1-050~056 前置条件求值"""

    def test_TC_B1_050_无前置条件恒满足(self):
        assert check_preconditions(_meta(), {'x': 1}) == []

    def test_TC_B1_051_input_present满足与缺失(self):
        meta = _meta(preconditions=[{'kind': 'input_present', 'field': 'object_type'}])
        assert check_preconditions(meta, {'object_type': 'user'}) == []
        assert check_preconditions(meta, {}) != []
        assert check_preconditions(meta, {'object_type': ''}) != []

    def test_TC_B1_052_input_equals(self):
        meta = _meta(preconditions=[{'kind': 'input_equals',
                                    'field': 'object_type', 'value': 'version'}])
        assert check_preconditions(meta, {'object_type': 'version'}) == []
        unmet = check_preconditions(meta, {'object_type': 'user'})
        assert unmet and 'object_type' in unmet[0]

    def test_TC_B1_053_input_in(self):
        meta = _meta(preconditions=[{'kind': 'input_in',
                                    'field': 'format', 'values': ['xlsx', 'csv']}])
        assert check_preconditions(meta, {'format': 'csv'}) == []
        assert check_preconditions(meta, {'format': 'pdf'}) != []

    def test_TC_B1_054_多项只报未满足项(self):
        meta = _meta(preconditions=[
            {'kind': 'input_present', 'field': 'a'},
            {'kind': 'input_present', 'field': 'b'},
        ])
        unmet = check_preconditions(meta, {'a': 1})
        assert len(unmet) == 1 and 'b' in unmet[0]

    def test_TC_B1_055_params为None不崩(self):
        meta = _meta(preconditions=[{'kind': 'input_present', 'field': 'a'}])
        assert check_preconditions(meta, None) != []

    def test_TC_B1_056_非dict条目跳过(self):
        meta = _meta(preconditions=['oops'])
        assert check_preconditions(meta, {'a': 1}) == []


# ─────────────────────────────────────────────────────────────────────────────
# call() 统一拦截
# ─────────────────────────────────────────────────────────────────────────────

class TestCallInterception:
    """TC-B1-060~062 注册表 call() 调用 handler 前拦截"""

    def test_TC_B1_060_未满足返回PRECONDITION_FAILED(self):
        def _run():
            called = []
            bo_action_registry.register(
                'demo.pre', lambda p, c: called.append(1) or {'success': True},
                description='带前置条件', object_type='*', category='business',
                input_schema={'type': 'object',
                              'properties': {'object_type': {'type': 'string'}}},
                preconditions=[{'kind': 'input_present', 'field': 'object_type'}],
            )
            result = bo_action_registry.call('demo.pre', {})
            assert result['success'] is False
            assert result['code'] == 'PRECONDITION_FAILED'
            assert called == []  # handler 未被调用
        _with_isolated_registry(_run)

    def test_TC_B1_061_满足则正常执行(self):
        def _run():
            bo_action_registry.register(
                'demo.pre2', lambda p, c: {'success': True, 'data': {'ok': 1}},
                description='带前置条件', object_type='*', category='business',
                input_schema={'type': 'object',
                              'properties': {'object_type': {'type': 'string'}}},
                preconditions=[{'kind': 'input_equals',
                                'field': 'object_type', 'value': 'user'}],
            )
            result = bo_action_registry.call('demo.pre2', {'object_type': 'user'})
            assert result['success'] is True
            assert result['data'] == {'ok': 1}
        _with_isolated_registry(_run)

    def test_TC_B1_062_无前置条件零行为变化(self):
        def _run():
            bo_action_registry.register(
                'demo.plain', lambda p, c: {'success': True, 'data': 42},
                description='无前置条件', object_type='*', category='business',
            )
            result = bo_action_registry.call('demo.plain', {})
            assert result['success'] is True and result['data'] == 42
        _with_isolated_registry(_run)


# ─────────────────────────────────────────────────────────────────────────────
# 真实 19 个 action 全合规（B1 不破坏既有注册）
# ─────────────────────────────────────────────────────────────────────────────

class TestRealRegistryContract:
    """TC-B1-070~071 真实注册表契约"""

    def test_TC_B1_070_真实19个action全合规(self):
        """注册全部真实 action 后，契约校验零违规（既有注册形状达标）"""
        def _run():
            from meta.services.bo_action_registrations import register_all_bo_actions
            register_all_bo_actions(bo_action_registry)
            assert len(bo_action_registry.list_ids()) == 19
            assert validate_registry(bo_action_registry) == {}
        _with_isolated_registry(_run)

    def test_TC_B1_071_命名规则覆盖既有action(self):
        """既有 action_id 命名全部匹配固化规则"""
        def _run():
            from meta.services.bo_action_registrations import register_all_bo_actions
            register_all_bo_actions(bo_action_registry)
            for aid in bo_action_registry.list_ids():
                assert ACTION_ID_PATTERN.match(aid), aid
        _with_isolated_registry(_run)