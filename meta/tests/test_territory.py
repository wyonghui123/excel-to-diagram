# -*- coding: utf-8 -*-
"""区域守卫测试（R-TER-1 / R-TER-2 索引口径 / R-TER-3 + 分配有效期 + 拦截器接线）

依据: docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md §7.4
      meta/services/territory_guard_service.py
      meta/core/interceptors/territory_guard_interceptor.py

口径: 守卫服务用假数据源按 SQL 形态返回（只实现两条查询），
      拦截器用 SimpleNamespace 造上下文；不在本文件写裸 SQL DML。
"""
import pytest

pytestmark = pytest.mark.unit

from types import SimpleNamespace

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.territory_guard_interceptor import (
    TerritoryGuardInterceptor,
)
from meta.services.territory_guard_service import (
    TerritoryGuardError,
    TerritoryGuardService,
)


class _FakeDS:
    """只实现守卫用到的 SQL 形态。"""

    def __init__(self, parents=None, statuses=None, raise_on_query=False,
                 children=None, levels=None):
        self.parents = parents or {}
        self.statuses = statuses or {}
        self.raise_on_query = raise_on_query
        self.children = children or {}   # parent_id -> [child_id]
        self.levels = levels or {}       # child_id -> 现值 level
        self.updates = []                # apply_levels 落库记录

    @staticmethod
    def _key(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def query(self, sql, params):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'SELECT id, parent_id, level FROM territories' in sql:
            rows = []
            for parent_id in params:
                for child_id in self.children.get(int(parent_id), []):
                    rows.append({'id': child_id, 'parent_id': int(parent_id),
                                 'level': self.levels.get(child_id)})
            return rows
        key = self._key(params[0])
        if 'SELECT parent_id FROM territories' in sql:
            if key not in self.parents:
                return []
            return [{'parent_id': self.parents[key]}]
        if 'SELECT status FROM territories' in sql:
            if key not in self.statuses:
                return []
            return [{'status': self.statuses[key]}]
        raise AssertionError('未预期的 SQL: {0}'.format(sql))

    def execute(self, sql, params):
        self.updates.append((sql, params))


def _svc(**kw):
    return TerritoryGuardService(_FakeDS(**kw))


def _ctx(object_id, action, params, old_data=None, ds=None, object_id_value=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=object_id_value if object_id_value is not None else params.get('id'),
        data_source=ds or _FakeDS(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# R-TER-1 —— 区域树不得成环
# ─────────────────────────────────────────────────────────────────────────────

class TestTerritoryParent:

    def test_blank_parent_passes(self):
        _svc().validate_territory_write({'parent_id': None})
        _svc().validate_territory_write({'parent_id': ''})

    def test_invalid_parent_rejected(self):
        with pytest.raises(TerritoryGuardError) as e:
            _svc().validate_territory_write({'parent_id': 'abc'})
        assert e.value.rule == 'territory_parent_invalid'
        assert e.value.field_name == 'parent_id'

    def test_self_parent_rejected(self):
        with pytest.raises(TerritoryGuardError) as e:
            _svc().validate_territory_write({'parent_id': 5}, exclude_id=5)
        assert e.value.rule == 'territory_parent_cycle'

    def test_chain_closing_cycle_rejected(self):
        # 5 的父指向 6，而 6 的父正是 5 → 把 5 的父改成 6 会闭合环
        svc = _svc(parents={6: 5})
        with pytest.raises(TerritoryGuardError) as e:
            svc.validate_territory_write({'parent_id': 6}, exclude_id=5)
        assert e.value.rule == 'territory_parent_cycle'

    def test_legal_chain_passes(self):
        svc = _svc(parents={6: 5, 5: 2, 2: None})
        svc.validate_territory_write({'parent_id': 6}, exclude_id=7)

    def test_ten_levels_passes(self):
        parents = {i: i - 1 for i in range(2, 11)}
        parents[1] = None
        _svc(parents=parents).validate_territory_write({'parent_id': 10})

    def test_depth_over_limit_rejected(self):
        parents = {i: i - 1 for i in range(2, 12)}
        svc = _svc(parents=parents)
        with pytest.raises(TerritoryGuardError) as e:
            svc.validate_territory_write({'parent_id': 11})
        assert e.value.rule == 'territory_parent_depth'
        assert e.value.field_name == 'parent_id'

    def test_missing_parent_stops_and_passes(self):
        # 上层不存在 → 交给真外键，不在守卫里上溯
        _svc(parents={}).validate_territory_write({'parent_id': 99})

    def test_query_failure_fails_open(self):
        _svc(raise_on_query=True).validate_territory_write({'parent_id': 9})


# ─────────────────────────────────────────────────────────────────────────────
# R-TER-4 —— level 由父链派生，父节点变更时级联重算子树
# ─────────────────────────────────────────────────────────────────────────────

class TestTerritoryLevel:

    def test_root_level_is_one(self):
        assert _svc().validate_territory_write({'parent_id': None}) == 1
        assert _svc().validate_territory_write({'parent_id': ''}) == 1

    def test_child_level_is_parent_plus_one(self):
        svc = _svc(parents={2: 1, 1: None})
        assert svc.validate_territory_write({'parent_id': 2}) == 3

    def test_query_failure_returns_none_for_fail_open(self):
        # 读侧异常时不写 level（保留旧值），不阻断主写入
        assert _svc(raise_on_query=True).validate_territory_write(
            {'parent_id': 9}) is None

    def test_plan_recomputes_whole_subtree(self):
        # 5 移到 level=2 之下 → 5 为 3，子 6/7 为 4，孙 8 为 5
        svc = _svc(children={5: [6, 7], 6: [8]}, levels={6: 2, 7: 2, 8: 3})
        assert dict(svc.plan_descendant_levels(5, 3)) == {6: 4, 7: 4, 8: 5}

    def test_plan_skips_unchanged_nodes(self):
        svc = _svc(children={5: [6]}, levels={6: 2})
        assert svc.plan_descendant_levels(5, 1) == []

    def test_plan_rejects_subtree_over_depth_limit(self):
        svc = _svc(children={5: [6], 6: [7]}, levels={6: 10, 7: 11})
        with pytest.raises(TerritoryGuardError) as e:
            svc.plan_descendant_levels(5, 10)
        assert e.value.rule == 'territory_parent_depth'
        assert e.value.field_name == 'parent_id'

    def test_plan_query_failure_fails_open(self):
        assert _svc(raise_on_query=True).plan_descendant_levels(5, 3) == []

    def test_apply_levels_writes_each_node(self):
        ds = _FakeDS()
        TerritoryGuardService(ds).apply_levels([(6, 4), (7, 4)])
        assert len(ds.updates) == 2
        assert ds.updates[0][1] == (4, 6)
        assert ds.updates[1][1] == (4, 7)

    def test_apply_levels_swallows_write_failure(self):
        class _BadDS(_FakeDS):
            def execute(self, sql, params):
                raise RuntimeError('database is locked')

        # 展示字段写失败只告警，不阻断主写入
        TerritoryGuardService(_BadDS()).apply_levels([(6, 4)])


# ─────────────────────────────────────────────────────────────────────────────
# 分配有效期 + R-TER-3 —— 停用区域不再被新的分配引用
# ─────────────────────────────────────────────────────────────────────────────

class TestAssignmentWrite:

    def test_equal_dates_rejected(self):
        with pytest.raises(TerritoryGuardError) as e:
            _svc(statuses={1: 'active'}).validate_assignment_write({
                'territory_id': 1,
                'effective_from': '2026-10-01',
                'effective_to': '2026-10-01',
            })
        assert e.value.rule == 'assignment_date_range'
        assert e.value.field_name == 'effective_to'

    def test_inverted_dates_rejected(self):
        with pytest.raises(TerritoryGuardError) as e:
            _svc(statuses={1: 'active'}).validate_assignment_write({
                'territory_id': 1,
                'effective_from': '2026-10-10',
                'effective_to': '2026-10-01',
            })
        assert e.value.rule == 'assignment_date_range'

    def test_ordered_dates_pass(self):
        _svc(statuses={1: 'active'}).validate_assignment_write({
            'territory_id': 1,
            'effective_from': '2026-10-01',
            'effective_to': '2026-10-31',
        })

    def test_open_ended_passes(self):
        _svc(statuses={1: 'active'}).validate_assignment_write({
            'territory_id': 1,
            'effective_from': '2026-10-01',
            'effective_to': None,
        })

    def test_inactive_territory_rejected(self):
        with pytest.raises(TerritoryGuardError) as e:
            _svc(statuses={3: 'inactive'}).validate_assignment_write({
                'territory_id': 3,
            })
        assert e.value.rule == 'territory_inactive'
        assert e.value.field_name == 'territory_id'

    def test_active_territory_passes(self):
        _svc(statuses={3: 'active'}).validate_assignment_write({
            'territory_id': 3,
        })

    def test_unknown_territory_defers_to_fk(self):
        _svc(statuses={}).validate_assignment_write({'territory_id': 99})

    def test_query_failure_fails_open(self):
        _svc(raise_on_query=True).validate_assignment_write({
            'territory_id': 3,
            'effective_from': '2026-10-01',
            'effective_to': '2026-10-31',
        })


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

class TestInterceptor:

    def test_should_execute_matrix(self):
        it = TerritoryGuardInterceptor()
        for action in ('crud_create', 'crud_update'):
            assert it.should_execute(_ctx('territory', action, {})) is True
            assert it.should_execute(
                _ctx('salesperson_territory_assignment', action, {})) is True
        assert it.should_execute(_ctx('territory', 'crud_read', {})) is False
        assert it.should_execute(
            _ctx('salesperson_territory_assignment', 'crud_list', {})) is False
        assert it.should_execute(_ctx('salesperson', 'crud_create', {})) is False

    def test_priority_after_sales_order_guard(self):
        assert TerritoryGuardInterceptor().priority == 50

    def test_territory_cycle_raises_validation_failed(self):
        ds = _FakeDS(parents={6: 5})
        with pytest.raises(ValidationFailedError) as e:
            TerritoryGuardInterceptor().before_action(
                _ctx('territory', 'crud_update',
                     {'id': 5, 'parent_id': 6}, ds=ds))
        detail = e.value.details[0]
        assert detail['rule'] == 'territory_parent_cycle'
        assert detail['field_name'] == 'parent_id'

    def test_territory_create_with_valid_parent_passes(self):
        ds = _FakeDS(parents={6: None})
        TerritoryGuardInterceptor().before_action(
            _ctx('territory', 'crud_create', {'code': 'T1', 'parent_id': 6}, ds=ds))

    def test_assignment_create_on_inactive_territory_raises(self):
        ds = _FakeDS(statuses={3: 'inactive'})
        with pytest.raises(ValidationFailedError) as e:
            TerritoryGuardInterceptor().before_action(
                _ctx('salesperson_territory_assignment', 'crud_create',
                     {'salesperson_id': 1, 'territory_id': 3}, ds=ds))
        assert e.value.details[0]['rule'] == 'territory_inactive'

    def test_assignment_update_without_territory_change_passes(self):
        # 既有分配在区域停用后仍可改主区域标记，不因区域状态被阻断
        ds = _FakeDS(statuses={3: 'inactive'})
        TerritoryGuardInterceptor().before_action(
            _ctx('salesperson_territory_assignment', 'crud_update',
                 {'id': 7, 'is_primary': 1},
                 old_data={'territory_id': 3},
                 ds=ds))

    def test_assignment_update_with_territory_change_checked(self):
        ds = _FakeDS(statuses={3: 'inactive'})
        with pytest.raises(ValidationFailedError) as e:
            TerritoryGuardInterceptor().before_action(
                _ctx('salesperson_territory_assignment', 'crud_update',
                     {'id': 7, 'territory_id': 3},
                     old_data={'territory_id': 1},
                     ds=ds))
        assert e.value.details[0]['rule'] == 'territory_inactive'

    def test_assignment_update_without_territory_change_skips_date_check(self):
        # 未改区域 → 拦截器短路，有效期不在此处校验
        TerritoryGuardInterceptor().before_action(
            _ctx('salesperson_territory_assignment', 'crud_update',
                 {'id': 7, 'effective_to': '2026-10-01'},
                 old_data={'territory_id': 1},
                 ds=_FakeDS(statuses={1: 'active'})))

    # ── R-TER-4：level 注入与子树级联 ─────────────────────────────────────
    def test_create_injects_derived_level(self):
        ctx = _ctx('territory', 'crud_create',
                   {'code': 'T1', 'parent_id': 6}, ds=_FakeDS(parents={6: None}))
        TerritoryGuardInterceptor().before_action(ctx)
        assert ctx.params['level'] == 2

    def test_create_ignores_client_supplied_level(self):
        ctx = _ctx('territory', 'crud_create',
                   {'code': 'T1', 'parent_id': 6, 'level': 99},
                   ds=_FakeDS(parents={6: None}))
        TerritoryGuardInterceptor().before_action(ctx)
        assert ctx.params['level'] == 2

    def test_root_create_gets_level_one(self):
        ctx = _ctx('territory', 'crud_create', {'code': 'T1'}, ds=_FakeDS())
        TerritoryGuardInterceptor().before_action(ctx)
        assert ctx.params['level'] == 1

    def test_parent_change_cascades_subtree(self):
        # 5 从根移到 2 之下（level 3）→ 子 6 由 2 变 4
        ds = _FakeDS(parents={2: 1, 1: None}, children={5: [6]}, levels={6: 2})
        ctx = _ctx('territory', 'crud_update', {'id': 5, 'parent_id': 2},
                   old_data={'id': 5, 'parent_id': None}, ds=ds)
        TerritoryGuardInterceptor().before_action(ctx)
        assert ctx.params['level'] == 3
        assert len(ds.updates) == 1
        assert ds.updates[0][0].startswith('UPDATE')
        assert ds.updates[0][1] == (4, 6)

    def test_parent_unchanged_skips_cascade(self):
        ds = _FakeDS(parents={1: None}, children={5: [6]}, levels={6: 2})
        ctx = _ctx('territory', 'crud_update', {'id': 5, 'name': '新名'},
                   old_data={'id': 5, 'parent_id': 1}, ds=ds)
        TerritoryGuardInterceptor().before_action(ctx)
        assert ctx.params['level'] == 2
        assert ds.updates == []
