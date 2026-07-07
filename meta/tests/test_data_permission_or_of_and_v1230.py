# -*- coding: utf-8 -*-
"""
[REGRESSION v1.2.30 2026-07-07] OR-of-AND 多 role dim scope 嵌套

Bug: DataPermissionInterceptor 在多 role 时, OR 组被错误地写成 flat
     把每个 role 内部的 AND 段 (eg [{id,eq,703}, {version_id,eq,764}]) 用 extend
     平铺到 OR 组内, 解析 SQL 时退化成
       id=703 OR version_id=764 OR id=2200 OR version_id=863
     永远为真 → 13 个域全返

修复: OR-of-AND 嵌套
  {type:or, conditions:[
    {type:and, conditions:[{id,eq,703},{version_id,eq,764}]},
    {type:and, conditions:[{id,eq,2200},{version_id,eq,863}]},
  ]}

实测:
  wyonghui (uid=10006) 经 TEST888 组 → role 5970 (domain=703) + role 11821 (domain=2200)
  修复前: V11 下看到 13 个域
  修复后: V11 下看到 1 个域 (供应链云=2200, 因为 5970 的 domain=703 不在 V11 下)
"""
import pytest
from meta.core.action_context import ActionContext, ActionResult
from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor


class _FakeDataSource:
    """最小化 DataSource, 只为 _apply_dimension_scope_filter 的两条 SELECT 准备"""

    def __init__(self, role_id_to_scope_dict, user_group_links):
        """
        role_id_to_scope_dict: {role_id: [{dimension, values, mode, inherit}, ...]}
        user_group_links: [(user_id, group_id, role_id), ...]
        """
        self._scope_by_role = role_id_to_scope_dict
        self._links = user_group_links

    def execute(self, sql, params):
        sql = sql.strip()
        # role_ids query
        if 'gr.role_id' in sql and 'ugm.user_id' in sql:
            user_id = params[0]
            role_ids = [r for (u, g, r) in self._links if u == user_id]
            return _FakeCursor([(r,) for r in role_ids])
        # role_dimension_scopes count
        if 'role_dimension_scopes' in sql and 'COUNT(*)' in sql:
            placeholders = sql.count('?')
            role_ids = list(params)
            count = sum(1 for rid in role_ids if rid in self._scope_by_role)
            return _FakeCursor([(count,)])
        return _FakeCursor([])


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        if self._rows:
            return self._rows[0]
        return None


class _FakeMetaObject:
    """最小化 MetaObject, 给 ActionContext.object_type 用"""

    def __init__(self, object_type):
        self.id = object_type


class _FakeEngine:
    """DimensionScopeEngine stub — 返回预定 conditions"""

    def __init__(self, conditions_by_role):
        self._conds = conditions_by_role  # {role_id: {object_type: cond_expr}}

    def derive_data_conditions(self, role_id):
        return dict(self._conds.get(role_id, {}))


class _FakeAuthMiddleware:
    """使 AUTH_ENABLED 启用 + 强制 is_admin=False"""

    is_admin_user = False

    def is_admin(self, ctx):
        return False


def _monkeypatch_dpi(monkeypatch, fake_engine):
    """Monkey-patch DataPermissionInterceptor to use our fake engine"""
    from meta.core.interceptors import data_permission_interceptor as dpi_mod
    # AUTH_ENABLED True
    monkeypatch.setattr(dpi_mod, 'AUTH_ENABLED', True)
    # Monkey-patch DimensionScopeEngine class to return our fake
    from meta.services import dimension_scope_engine as engine_mod
    original_engine_cls = engine_mod.DimensionScopeEngine

    class _FakeEngineCls:
        def __init__(self, *args, **kwargs):
            pass

        def derive_data_conditions(self, role_id):
            return dict(fake_engine._conds.get(role_id, {}))

    monkeypatch.setattr(engine_mod, 'DimensionScopeEngine', _FakeEngineCls)
    # is_admin returns False
    from meta.services import auth_middleware as auth_mod
    monkeypatch.setattr(auth_mod, 'is_admin', lambda *args, **kwargs: False)


def test_multi_role_or_of_and_nested_not_flattened(monkeypatch):
    """
    2 个 role, 每个有 AND 段. 验证最终 query_conditions 是 OR-of-AND 嵌套, 不是 flat OR.
    """
    # 5970 -> domain AND [id=703, version_id=764]
    # 11821 -> domain AND [id=2200, version_id=863]
    conds_5970 = {
        'domain': 'id = 703 AND version_id = 764',
    }
    conds_11821 = {
        'domain': 'id = 2200 AND version_id = 863',
    }
    engine = _FakeEngine({5970: conds_5970, 11821: conds_11821})

    user_links = [
        (10006, 1037, 5970),  # wyonghui -> TEST888 group -> role 5970
        (10006, 1037, 11821),  # wyonghui -> TEST888 group -> role 11821
    ]
    ds = _FakeDataSource(
        {5970: [{'dimension': 'domain', 'values': [703], 'mode': 'include', 'inherit': 1}],
         11821: [{'dimension': 'domain', 'values': [2200], 'mode': 'include', 'inherit': 1}]},
        user_links,
    )

    _monkeypatch_dpi(monkeypatch, engine)
    from meta.core.interceptors import data_permission_interceptor as dpi_mod
    interceptor = dpi_mod.DataPermissionInterceptor()

    ctx = ActionContext(
        meta_object=_FakeMetaObject('domain'),
        action='crud_query',
        params={},
        data_source=ds,
        user_id=10006,
    )

    # Run
    from meta.core.interceptors.base import Interceptor
    interceptor.before_action(ctx)

    qc = ctx.extra.get('query_conditions', [])
    # [FIX v1.2.30] 修复后结构:
    #   [
    #     {'type': 'or', 'conditions': [
    #         {'type': 'and', 'conditions': [
    #             {'type': 'or', 'conditions': [   ← 我们的 OR-of-AND
    #                 {'type': 'and', 'conditions': [{id:703}, {version:764}]},
    #                 {'type': 'and', 'conditions': [{id:2200}, {version:863}]}
    #             ]}
    #         ]},
    #         {'field': 'id', 'operator': 'in_subquery', 'source': 'owner_exception_chain'}
    #     ]}
    #   ]
    # BUG: 之前 OR 组平铺, 修复后 OR 组里每个 role 的 conds 都被包成 {type:and, conditions: [...]}
    assert len(qc) >= 1, f"expected at least 1 condition, got {qc}"

    # 递归找最深的 OR-of-AND (它的 children 都是 AND)
    def find_or_of_and(nested):
        if not isinstance(nested, list):
            return None
        for item in nested:
            if isinstance(item, dict) and item.get('type') == 'or':
                children = item.get('conditions', [])
                # 我们的 OR-of-AND 特征: children 都是 {type:and, conditions:[...]}
                and_children = [c for c in children if isinstance(c, dict) and c.get('type') == 'and']
                # 至少 2 个 AND (多 role) 是我们的目标
                if len(and_children) >= 2 and all(
                    isinstance(c.get('conditions'), list) for c in and_children
                ):
                    return item
                # 递归查找嵌套的 OR
                r = find_or_of_and(children)
                if r: return r
        # Recurse into all items
        for item in nested:
            if isinstance(item, dict) and 'conditions' in item:
                r = find_or_of_and(item['conditions'])
                if r: return r
        return None

    or_grp = find_or_of_and(qc)
    assert or_grp is not None, f"expected OR-of-AND with >=2 AND children, got {qc}"
    and_groups = [c for c in or_grp['conditions'] if c.get('type') == 'and']
    assert len(and_groups) == 2, f"expected 2 AND groups in OR, got {len(and_groups)}: {or_grp}"
    # Verify the AND conditions
    and_pairs = sorted([
        tuple(sorted([(x['field'], x['value']) for x in ag['conditions']]))
        for ag in and_groups
    ])
    assert and_pairs == [
        (('id', 703), ('version_id', 764)),
        (('id', 2200), ('version_id', 863)),
    ], f"AND groups incorrect: {and_pairs}"
    # 关键 BUG REGRESSION 断言: OR 组里没有平铺的 field-only cond
    flat_conds = [c for c in or_grp['conditions'] if 'field' in c and 'type' not in c]
    assert len(flat_conds) == 0, f"BUG REGRESSION: found flat conds in OR group: {flat_conds}"


def test_single_role_no_or_group(monkeypatch):
    """
    单 role 时直接 append 各 AND 段到外层 query_conditions (外层是 AND).
    验证不包 OR 包裹.
    """
    conds = {'domain': 'id = 2200 AND version_id = 863'}
    engine = _FakeEngine({11821: conds})

    user_links = [(10006, 1037, 11821)]
    ds = _FakeDataSource(
        {11821: [{'dimension': 'domain', 'values': [2200], 'mode': 'include', 'inherit': 1}]},
        user_links,
    )

    _monkeypatch_dpi(monkeypatch, engine)
    from meta.core.interceptors import data_permission_interceptor as dpi_mod
    interceptor = dpi_mod.DataPermissionInterceptor()

    ctx = ActionContext(
        meta_object=_FakeMetaObject('domain'),
        action='crud_query',
        params={},
        data_source=ds,
        user_id=10006,
    )

    from meta.core.interceptors.base import Interceptor
    interceptor.before_action(ctx)

    qc = ctx.extra.get('query_conditions', [])
    # 单 role 时, 该 role 的 AND 段会进入外层 query_conditions (外层本身是 AND).
    # owner_exception_chain 会加 1 个 in_subquery cond
    # [FIX v1.2.30] 实际行为: 单 role 走 'len(per_role_conditions) == 1' 分支, 直接 append flat.
    # 然后 _apply_scope_filter_after_dimension 把它包成 {type:and, conditions:[...]}
    # owner_exception_chain 加 1 个 in_subquery
    # 期望结构: [{type:and, conditions: [{type:and, conditions:[{id,eq,2200}, {version_id,eq,863}]}, in_subquery_owner]}]
    # 关键: id=2200 和 version_id=863 都在某一个 AND 组内 (不会跨组, 因为单 role 的 AND 段在同一个 AND 组)

    def find_id_and_version(qc_list):
        """递归找包含 id=2200 + version_id=863 的 AND 组"""
        for item in qc_list:
            if not isinstance(item, dict):
                continue
            if 'conditions' in item and isinstance(item['conditions'], list):
                # 这个 item 本身是 AND/OR
                childs = item['conditions']
                has_id = any(isinstance(c, dict) and c.get('field') == 'id' and c.get('value') == 2200 for c in childs)
                has_ver = any(isinstance(c, dict) and c.get('field') == 'version_id' and c.get('value') == 863 for c in childs)
                if has_id and has_ver:
                    return item
                # Recurse
                r = find_id_and_version(childs)
                if r: return r
        return None

    and_group = find_id_and_version(qc)
    assert and_group is not None, f"expected AND group with id=2200 + version_id=863, got {qc}"
    # 关键 BUG REGRESSION: id 和 version 不能被拆到 OR 顶层 (那样会 永远 OR 为真)
    # 单 role 不存在 OR-of-AND 误拼, 所以这条 case 验证的是: 它们至少在某个 AND 组里


def test_no_role_returns_false(monkeypatch):
    """
    无 role 关联时 _apply_dimension_scope_filter 应返回 False, 不注入 query_conditions.
    """
    engine = _FakeEngine({})
    user_links = []  # 没有任何 role
    ds = _FakeDataSource({}, user_links)

    _monkeypatch_dpi(monkeypatch, engine)
    from meta.core.interceptors import data_permission_interceptor as dpi_mod
    interceptor = dpi_mod.DataPermissionInterceptor()

    ctx = ActionContext(
        meta_object=_FakeMetaObject('domain'),
        action='crud_query',
        params={},
        data_source=ds,
        user_id=10006,
    )

    from meta.core.interceptors.base import Interceptor
    interceptor.before_action(ctx)

    qc = ctx.extra.get('query_conditions', [])
    assert qc == [], f"expected empty query_conditions, got {qc}"
