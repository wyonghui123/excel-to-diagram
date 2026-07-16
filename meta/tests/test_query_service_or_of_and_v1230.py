# -*- coding: utf-8 -*-
"""
[REGRESSION v1.2.30 2026-07-07] OR-of-AND multi-role dim scope in QueryService.export path

Bug mirror of BUG-V027 from DPI:
  DataPermissionInterceptor._apply_dimension_scope_filter 的 v1.2.30 修复了
  meta/core/interceptors/data_permission_interceptor.py 的 OR-of-AND 嵌套.
  但 query_service._try_apply_dimension_scope (export 路径) 是平行实现,
  原 bug 把每个 role 的 AND 段平铺到 builder.or_where, SQL 退化为恒真 → 业务对象 export 全表 3000+

本测试验证多 role 时 OR-of-AND 已经被改用 where_raw 实现.
"""
import pytest
from meta.core.query_builder import QueryBuilder


class _FakeCursor:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        if self._scalar is not None:
            return (self._scalar,)
        if self._rows:
            return self._rows[0]
        return None


class _FakeDataSource:
    """最小 mock 用于 _try_apply_dimension_scope 的两次 SQL 查询"""

    def __init__(self, role_id_rows=None, scope_count_rows=None):
        self._calls = 0
        self._role_id_rows = role_id_rows or []
        self._scope_count_rows = scope_count_rows or []

    def execute(self, sql, params=None):
        self._calls += 1
        if 'group_roles' in sql:
            return _FakeCursor(rows=self._role_id_rows)
        if 'role_dimension_scopes' in sql:
            return _FakeCursor(rows=self._scope_count_rows)
        return _FakeCursor()


class _FakeField:
    def __init__(self, fid):
        self.id = fid


class _FakeMetaObject:
    """最小 MetaObject mock, 提供 QueryBuilder 需要的 attributes"""

    def __init__(self, object_type='business_object', table_name='business_objects'):
        self.object_type = object_type
        self.table_name = table_name
        # _try_apply_dimension_scope 用 builder._get_db_column(field) (它是保护方法)
        # builder 内部通过 _field_map 查 - 我们给个 owner_id field
        self.fields = [_FakeField('owner_id')]
        self.analytical_model = None
        self.id = object_type
        self.name = object_name = object_type


def test_multi_role_or_of_and_not_flattened(monkeypatch):
    """多 role 时 OR-of-AND 必须用 AND 包裹每个 role 内的段"""
    from meta.services import query_service as qs
    from meta.services.dimension_scope_engine import DimensionScopeEngine

    fake_role_to_conds = {
        5970: {'business_object': 'id IN (1, 2, 3) AND service_module_id IN (10, 20)'},
        11821: {'business_object': 'id IN (100, 200) AND service_module_id IN (110, 220)'},
    }

    monkeypatch.setattr(
        DimensionScopeEngine,
        'derive_data_conditions',
        lambda self, role_id: fake_role_to_conds.get(role_id, {}),
    )
    from meta.services import chain_owner_resolver
    monkeypatch.setattr(chain_owner_resolver, 'is_in_chain', lambda ot: False)

    ds = _FakeDataSource(
        role_id_rows=[(5970,), (11821,)],
        scope_count_rows=[(2,)],
    )
    service = qs.QueryService(ds)

    meta = _FakeMetaObject()
    builder = QueryBuilder(ds, meta)

    result = service._try_apply_dimension_scope(builder, user_id=10006, object_type='business_object')
    assert result is True

    sql, params = builder.build_sql()
    print(f"\n[Multi-role SQL]\n  {sql}")
    print(f"[Multi-role params]\n  {params}")

    # 核心断言 1: 必须有 AND 包裹
    assert ' AND ' in sql, f"Multi-role SQL must contain AND: {sql}"
    # 核心断言 2: role 之间必须有 OR
    assert ' OR ' in sql, f"Multi-role SQL must contain OR between roles: {sql}"

    # BUG regression check:
    # 修复: SQL 含 "(id IN (?,?,?) AND service_module_id IN (?,?)) OR (id IN (?,?) AND service_module_id IN (?,?))"
    # bug:    SQL 含 "id IN (?,?,?) OR service_module_id IN (?,?) OR id IN (?,?) OR ..." (平铺 OR, AND 段丢失)
    # 检查: 第一个 "id IN" 后面必须 AND service_module_id, 不能 OR
    assert 'id IN (?, ?, ?) OR service_module_id' not in sql, (
        f"BUG-V027 regression: id should AND with service_module_id within same role, "
        f"not OR across roles. SQL: {sql}"
    )
    # 强检查: 应有 AND 段包外层
    assert ' AND ' in sql
    # 检查: 两个 role 之间用 OR (外层), 不应连续平铺
    import re
    or_segs = re.split(r'\)\s*OR\s*\(', sql)
    print(f"  OR-segments (split): {or_segs}")
    and_count_in_seg = sum(1 for s in or_segs if ' AND ' in s)
    assert and_count_in_seg >= 2, (
        f"BUG-V027: Expected at least 2 OR-segments with AND inside (one per role), "
        f"got {and_count_in_seg}. SQL: {sql}"
    )


def test_single_role_uses_or_where_path(monkeypatch):
    """单 role 走老 or_where 路径 (id IN (...) OR owner_id = ? 形式), 不引入 AND 包裹"""
    from meta.services import query_service as qs
    from meta.services.dimension_scope_engine import DimensionScopeEngine

    fake_role_to_conds = {
        5970: {'business_object': 'id IN (1, 2, 3) AND service_module_id IN (10, 20)'},
    }
    monkeypatch.setattr(
        DimensionScopeEngine,
        'derive_data_conditions',
        lambda self, role_id: fake_role_to_conds.get(role_id, {}),
    )
    from meta.services import chain_owner_resolver
    monkeypatch.setattr(chain_owner_resolver, 'is_in_chain', lambda ot: False)

    ds = _FakeDataSource(
        role_id_rows=[(5970,)],
        scope_count_rows=[(1,)],
    )
    service = qs.QueryService(ds)

    meta = _FakeMetaObject()
    builder = QueryBuilder(ds, meta)

    result = service._try_apply_dimension_scope(builder, user_id=10006, object_type='business_object')
    assert result is True

    sql, params = builder.build_sql()
    print(f"\n[Single-role SQL]\n  {sql}")

    # 单 role: 不加 owner exception (business_object is not chain), 应该只有 dim scope OR cond
    # QueryBuilder 用 ? 作为占位符, 不是真实数字
    assert 'id IN (?, ?, ?)' in sql
    assert 'service_module_id IN (?, ?)' in sql


def test_multi_role_with_in_subquery(monkeypatch):
    """多 role 含 in_subquery (实际 export 触发场景) 应该正确生成 OR-of-AND + IN(subquery)"""
    from meta.services import query_service as qs
    from meta.services.dimension_scope_engine import DimensionScopeEngine

    fake_role_to_conds = {
        5970: {
            'business_object':
                'service_module_id IN (1, 2, 3) AND service_module_id IN '
                '(SELECT id FROM service_modules WHERE sub_domain_id IN (138, 139, 284))'
        },
        11821: {
            'business_object':
                'service_module_id IN (100, 200) AND service_module_id IN '
                '(SELECT id FROM service_modules WHERE sub_domain_id IN (297, 299))'
        },
    }
    monkeypatch.setattr(
        DimensionScopeEngine,
        'derive_data_conditions',
        lambda self, role_id: fake_role_to_conds.get(role_id, {}),
    )
    from meta.services import chain_owner_resolver
    monkeypatch.setattr(chain_owner_resolver, 'is_in_chain', lambda ot: False)

    ds = _FakeDataSource(
        role_id_rows=[(5970,), (11821,)],
        scope_count_rows=[(2,)],
    )
    service = qs.QueryService(ds)

    meta = _FakeMetaObject()
    builder = QueryBuilder(ds, meta)

    result = service._try_apply_dimension_scope(builder, user_id=10006, object_type='business_object')
    assert result is True, "_try_apply_dimension_scope should return True"

    sql, params = builder.build_sql()
    print(f"\n[in_subquery SQL]\n  {sql}")
    print(f"[in_subquery params]\n  {params}")

    # 关键断言: 必须包含 IN(subquery)
    assert 'IN (SELECT' in sql, (
        f"in_subquery raw SQL should be inserted via IN (SELECT ...). Got: {sql}"
    )
    # 必须有 AND 包裹
    assert ' AND ' in sql
    # 必须有 OR 包裹 role 间
    assert ' OR ' in sql


def test_multi_role_with_single_in_subquery(monkeypatch):
    """与上一个类似, 但只 role 5970 多个服务模块来源有 in_subquery"""
    from meta.services import query_service as qs
    from meta.services.dimension_scope_engine import DimensionScopeEngine

    fake_role_to_conds = {
        5970: {'business_object': 'service_module_id IN (1, 2, 3)'},
        11821: {
            'business_object':
                'service_module_id IN (SELECT id FROM service_modules WHERE sub_domain_id IN (297))'
        },
    }
    monkeypatch.setattr(
        DimensionScopeEngine,
        'derive_data_conditions',
        lambda self, role_id: fake_role_to_conds.get(role_id, {}),
    )
    from meta.services import chain_owner_resolver
    monkeypatch.setattr(chain_owner_resolver, 'is_in_chain', lambda ot: False)

    ds = _FakeDataSource(
        role_id_rows=[(5970,), (11821,)],
        scope_count_rows=[(2,)],
    )
    service = qs.QueryService(ds)

    meta = _FakeMetaObject()
    builder = QueryBuilder(ds, meta)
    result = service._try_apply_dimension_scope(builder, user_id=10006, object_type='business_object')
    assert result is True
    sql, params = builder.build_sql()
    print(f"\n[single-in_subquery SQL]\n  {sql}")
    assert 'IN (?' in sql or 'IN (SELECT' in sql


def test_no_role_returns_false(monkeypatch):
    """用户没有任何 role scope -> 直接返回 False, 不动 builder"""
    from meta.services import query_service as qs
    from meta.services.dimension_scope_engine import DimensionScopeEngine

    monkeypatch.setattr(
        DimensionScopeEngine,
        'derive_data_conditions',
        lambda self, role_id: {},
    )

    ds = _FakeDataSource(
        role_id_rows=[(9999,)],
        scope_count_rows=[(0,)],
    )
    service = qs.QueryService(ds)

    meta = _FakeMetaObject()
    builder = QueryBuilder(ds, meta)

    result = service._try_apply_dimension_scope(builder, user_id=10006, object_type='business_object')
    assert result is False

    sql, params = builder.build_sql()
    assert 'WHERE' not in sql or 'IN (' not in sql, (
        f"Expected empty WHERE clause when no role has scope, got: {sql}"
    )
