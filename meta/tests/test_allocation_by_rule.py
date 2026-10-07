# -*- coding: utf-8 -*-
"""
分摊执行 `allocate_by_rule()` + 留痕 `record_allocation_results()` 测试 (FR-013)
=======================================================================

**纯守恒算法 `plan_floor()` 已在 `test_allocation_plan.py` 之外单独覆盖**，
本文件只测「配置 → 权重 → 分摊 → 落库 → 留痕」这条链路：

1.  `basis=equal` 均分；`basis=quantity/value/...` 按 `basis_field` 取权重
2.  `basis_field` 缺失 / 子行该列为空或非正 → 422 且零写入
3.  `floor` waterfall：抬到地板价、差额由未触顶行重分、Σ 仍守恒；
    `n × floor > total` → 422（不静默截断）
4.  `rounding=ceil/floor` 改变总额取整方向，Σ 仍守恒
5.  `group_by`：组间均分 + 组内按 basis；同组行不连续时结果仍正确
6.  留痕：头记总额 + 行记摊得额，`origin=unplanned` / `allocation_rule_id`
    / `allocation_basis` / `source_document_*` 均可回放
7.  `persist_result=false` 只摊不留痕
"""
import os

import pytest

pytestmark = pytest.mark.integration

# 本文件使用临时 sqlite + 建表/插入夹具, 按项目惯例绕过 raw-SQL 守卫
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import sqlite3  # noqa: E402
from decimal import Decimal  # noqa: E402

from meta.core.action_executor import ActionExecutor  # noqa: E402
from meta.core.models import (  # noqa: E402
    ActionType, FieldType, MetaAction, MetaField, MetaObject, registry,
)
from meta.core.models_enums import FieldType as _FT  # noqa: E402,F401
from meta.core.rule_executor import RuleEngine  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.core.sql_adapters import SQLiteAdapter  # noqa: E402
from meta.core.table_name_validator import register_table_name  # noqa: E402
from meta.services.allocation_service import (  # noqa: E402
    AllocationError, AllocationService, plan_floor,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    amount REAL
)
"""

LINES_DDL = """
CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    amount REAL,
    qty REAL,
    weight REAL,
    cost_center TEXT
)
"""


# ----------------------------------------------------------------------
# 纯算法：plan_floor
# ----------------------------------------------------------------------
class TestPlanFloor:
    def test_no_floor_is_identity_to_plan(self):
        from meta.services.allocation_service import plan
        assert plan_floor(100, [1, 1, 1]) == plan(100, [1, 1, 1])

    def test_zero_floor_is_no_constraint(self):
        assert sum(plan_floor(100, [1, 1, 1], floor=0)) == 100

    def test_non_positive_floor_is_no_constraint(self):
        """负地板价对正金额无意义 → 不得把结果钳成负数。"""
        vals = plan_floor(100, [1, 1, 1], floor=-10)
        assert vals == [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]

    def test_floor_below_allocation_is_untouched(self):
        vals = plan_floor(100, [1, 1, 1], floor=10)
        assert vals == [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]

    def test_floor_raises_and_conserves(self):
        """100 分 3 行、floor=30 → 30/33.34/36.66 一类，Σ 仍 100 且每份 ≥30。"""
        vals = plan_floor(100, [1, 1, 1], floor=30)
        assert min(vals) >= Decimal('30')
        assert sum(vals) == Decimal('100')

    def test_floor_raises_smallest_and_redistributes(self):
        """权重 90/9/1、floor=100 → 最小那份被抬到 100，缺口由其余行承接。"""
        vals = plan_floor(1000, [90, 9, 1], floor=100)
        assert min(vals) >= Decimal('100')
        assert sum(vals) == Decimal('1000')

    def test_floor_conflict_raises_422(self):
        """3 × 40 = 120 > 100，数学无解 → 报错而非静默截断。"""
        with pytest.raises(AllocationError) as exc:
            plan_floor(100, [1, 1, 1], floor=40)
        assert exc.value.status_code == 422
        assert '地板价无法满足' in str(exc.value)

    def test_floor_exactly_reachable(self):
        """3 × 33.33 = 99.99 ≤ 100 → 可行，Σ 仍精确 100。"""
        vals = plan_floor(100, [1, 1, 1], floor=33.33)
        assert min(vals) >= Decimal('33.33')
        assert sum(vals) == Decimal('100')


# ----------------------------------------------------------------------
# 端到端：allocate_by_rule
# ----------------------------------------------------------------------
def _parent_meta():
    return MetaObject(
        id='order', name='订单', table_name='orders',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True, unique=True),
            MetaField(id='name', name='名称', field_type=FieldType.STRING,
                      db_column='name'),
            MetaField(id='amount', name='金额', field_type=FieldType.FLOAT,
                      db_column='amount'),
        ],
    )


def _child_meta():
    return MetaObject(
        id='order_line', name='订单行', table_name='order_lines',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id', required=True, unique=True),
            MetaField(id='order_id', name='订单', field_type=FieldType.INTEGER,
                      db_column='order_id'),
            MetaField(id='amount', name='金额', field_type=FieldType.FLOAT,
                      db_column='amount'),
            MetaField(id='qty', name='数量', field_type=FieldType.FLOAT,
                      db_column='qty'),
            MetaField(id='weight', name='重量', field_type=FieldType.FLOAT,
                      db_column='weight'),
            MetaField(id='cost_center', name='成本中心',
                      field_type=FieldType.STRING, db_column='cost_center'),
        ],
        actions=[
            MetaAction(id='crud_create', name='创建', action_type=ActionType.CRUD,
                       method='POST', path='/api/order_lines'),
            MetaAction(id='crud_update', name='更新', action_type=ActionType.CRUD,
                       method='PUT', path='/api/order_lines'),
        ],
    )


@pytest.fixture
def env(tmp_path):
    """独立 sqlite + 注入 registry；calc_results 按 yaml 真实建表。"""
    import logging
    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'alloc.db'))
    ds.execute(ORDERS_DDL)
    ds.execute(LINES_DDL)

    # calc_results 走 yaml 建表（验证 schema 新列真的存在）
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(os.path.join(ROOT, "meta", "schemas"))
    finally:
        logging.disable(logging.NOTSET)
    gen = SchemaGenerator("sqlite")
    # 【2026-10-07 拆表】分摊留痕已迁至独立表 allocation_results，
    #   不再写 calc_results（共用导致定价重算作废留痕 / write_back 写两遍）。
    #   仍需建 calc_result：定价链路同库，且要验证它不再含分摊列。
    cr_meta = registry.get("calc_result")
    assert cr_meta is not None, "calc_result 未注册"
    ar_meta = registry.get("allocation_result")
    assert ar_meta is not None, "allocation_result 未注册"
    # calc_result / allocation_result 均有 FK → 目标表须先建
    for obj_name in ("pricing_period", "external_rate_source",
                     "allocation_rule"):
        obj = registry.get(obj_name)
        assert obj is not None, f"{obj_name} 未注册"
        ds.execute(gen.generate_create_table(obj))
    ds.execute(gen.generate_create_table(cr_meta))
    ds.execute(gen.generate_create_table(ar_meta))

    parent_meta = _parent_meta()
    child_meta = _child_meta()
    for obj in (parent_meta, child_meta):
        register_table_name(obj.table_name)

    meta_map = {'order': parent_meta, 'order_line': child_meta}
    original_get = registry.get

    def fake_get(key):
        if key in meta_map:
            return meta_map[key]
        return original_get(key)

    def build_executor(self):
        return ActionExecutor(self.ds, RuleEngine(self.ds), audit_enabled=False)

    from unittest.mock import patch
    with patch.object(registry, 'get', side_effect=fake_get), \
         patch('meta.services.cascade_service.HierarchyConfigLoader.get_foreign_key',
               return_value='order_id'), \
         patch('meta.services.cascade_service.HierarchyConfigLoader.get_parent_object',
               return_value='order'), \
         patch.object(AllocationService, '_build_executor', build_executor):
        yield ds


def _seed(ds, parent_amount=100, lines=()):
    """lines: [(qty, weight, cost_center), ...]；空 = 三行零值。"""
    ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', ?)",
               (parent_amount,))
    ids = []
    for qty, wt, cc in (lines or ((0, 0, None),) * 3):
        cur = ds.execute(
            "INSERT INTO order_lines (order_id, amount, qty, weight,"
            " cost_center) VALUES (1, 0, ?, ?, ?)", (qty, wt, cc)
        )
        ids.append(cur.lastrowid)
    return ids


def _rule(ds, **kw):
    """插入一条分摊规则，返回 id。"""
    row = dict(code=kw.pop('code', 'AR1'), name='规则1',
               basis=kw.pop('basis', 'equal'), manual_factor=kw.pop(
                   'manual_factor', None),
               group_by=kw.pop('group_by', None),
               rounding=kw.pop('rounding', None),
               floor=kw.pop('floor', None),
               target=kw.pop('target', 'expense'), description=None,
               created_at='2026-10-07 00:00:00',
               updated_at='2026-10-07 00:00:00')
    row.update(kw)
    cols = ','.join(row)
    qs = ','.join('?' * len(row))
    cur = ds.execute(
        f"INSERT INTO allocation_rules ({cols}) VALUES ({qs})",
        tuple(row.values()),
    )
    return cur.lastrowid


def _amounts(ds, child_ids):
    return [ds.execute(
        "SELECT amount FROM order_lines WHERE id = ?", (cid,)
    ).fetchone()[0] for cid in child_ids]


def _svc(ds):
    return AllocationService(data_source=ds)


class TestAllocateByRule:
    def test_equal_basis_splits_evenly(self, env):
        ds = env
        ids = _seed(ds, 100)
        rid = _rule(ds, basis='equal')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'persist_result': False,
        })

        assert r['verified'] is True
        assert r['basis'] == 'equal'
        assert [a['value'] for a in r['allocations']] == [
            '33.34', '33.33', '33.33',
        ]
        assert _amounts(ds, ids) == pytest.approx([33.34, 33.33, 33.33])

    def test_quantity_basis_uses_basis_field(self, env):
        ds = env
        ids = _seed(ds, 100, lines=((10, 0, None), (30, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'qty', 'persist_result': False,
        })

        assert [a['value'] for a in r['allocations']] == [
            '10.00', '30.00', '60.00',
        ]
        assert _amounts(ds, ids) == pytest.approx([10, 30, 60])

    def test_weight_basis_uses_basis_field(self, env):
        ds = env
        _seed(ds, 90, lines=((0, 1, None), (0, 2, None), (0, 7, None)))
        rid = _rule(ds, basis='weight')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'weight', 'persist_result': False,
        })
        assert [a['value'] for a in r['allocations']] == [
            '9.00', '18.00', '63.00',
        ]

    def test_basis_field_required_for_quantity(self, env):
        ds = env
        ids = _seed(ds, 100, lines=((10, 0, None), (30, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity')

        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'persist_result': False,
            })
        assert 'basis_field' in str(exc.value)
        assert _amounts(ds, ids) == [0, 0, 0]

    def test_null_basis_field_is_422_and_no_write(self, env):
        ds = env
        ids = _seed(ds, 100, lines=((10, 0, None), (None, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity')

        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'basis_field': 'qty', 'persist_result': False,
            })
        assert exc.value.status_code == 422
        assert _amounts(ds, ids) == [0, 0, 0]

    def test_zero_basis_field_is_422_and_no_write(self, env):
        """零权重行会「分不到金额」，静默跳过等于凭空丢钱 → 必须拒。"""
        ds = env
        ids = _seed(ds, 100, lines=((10, 0, None), (0, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity')

        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'basis_field': 'qty', 'persist_result': False,
            })
        assert exc.value.status_code == 422
        assert _amounts(ds, ids) == [0, 0, 0]

    def test_manual_basis_without_factor_is_422(self, env):
        ds = env
        _seed(ds, 100)
        rid = _rule(ds, basis='manual', manual_factor=None)

        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'persist_result': False,
            })
        assert 'manual_factor' in str(exc.value)

    def test_manual_basis_with_factor_splits_evenly(self, env):
        """schema 的 manual_factor 是**单值** → 只能等权（配置表达力上限）。"""
        ds = env
        ids = _seed(ds, 100)
        rid = _rule(ds, basis='manual', manual_factor=2.5)

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'persist_result': False,
        })
        assert [a['value'] for a in r['allocations']] == [
            '33.34', '33.33', '33.33',
        ]
        assert _amounts(ds, ids) == pytest.approx([33.34, 33.33, 33.33])

    def test_unknown_rule_is_404(self, env):
        ds = env
        _seed(ds, 100)
        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': 999, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'persist_result': False,
            })
        assert exc.value.status_code == 404

    def test_explicit_weights_override_basis(self, env):
        ds = env
        ids = _seed(ds, 100, lines=((90, 0, None), (9, 0, None), (1, 0, None)))
        rid = _rule(ds, basis='quantity')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'weights': [1, 1, 1], 'persist_result': False,
        })
        # 显式权重优先 → 均分，而非按 qty 的 9:0.9:0.1
        assert [a['value'] for a in r['allocations']] == [
            '33.34', '33.33', '33.33',
        ]

    def test_no_children_is_422(self, env):
        ds = env
        ds.execute("INSERT INTO orders (id, name, amount) VALUES (1,'O1',100)")
        rid = _rule(ds, basis='equal')
        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'persist_result': False,
            })
        assert exc.value.status_code == 422


class TestFloorAndRounding:
    def test_floor_raises_and_conserves(self, env):
        ds = env
        ids = _seed(ds, 100)
        rid = _rule(ds, basis='equal', floor=30)

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'persist_result': False,
        })
        vals = [float(a['value']) for a in r['allocations']]
        assert min(vals) >= 30
        assert round(sum(vals), 2) == 100.00
        assert _amounts(ds, ids) == pytest.approx(vals)

    def test_floor_conflict_is_422_and_no_write(self, env):
        ds = env
        ids = _seed(ds, 100)
        rid = _rule(ds, basis='equal', floor=40)   # 3 × 40 = 120 > 100

        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'persist_result': False,
            })
        assert exc.value.status_code == 422
        assert _amounts(ds, ids) == [0, 0, 0]

    def test_spec_floor_overrides_rule_floor(self, env):
        ds = env
        _seed(ds, 100)
        rid = _rule(ds, basis='equal', floor=None)

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'floor': 30, 'persist_result': False,
        })
        assert min(float(a['value']) for a in r['allocations']) >= 30

    def test_rounding_ceil_rounds_total_up(self, env):
        """10.4 分 3 行、scale=0、ceil → 总额 11 → 4/4/3。"""
        ds = env
        ids = _seed(ds, 10.4)
        rid = _rule(ds, basis='equal', rounding='ceil')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'scale': 0, 'persist_result': False,
        })
        vals = [int(a['value']) for a in r['allocations']]
        assert sum(vals) == 11
        assert _amounts(ds, ids) == pytest.approx(vals)

    def test_rounding_floor_rounds_total_down(self, env):
        """10.4 → floor → 总额 10 → 4/3/3。"""
        ds = env
        _seed(ds, 10.4)
        rid = _rule(ds, basis='equal', rounding='floor')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'scale': 0, 'persist_result': False,
        })
        vals = [int(a['value']) for a in r['allocations']]
        assert sum(vals) == 10

    def test_rounding_ceil_on_exact_total_is_identity(self, env):
        """整数总额下 ceil 不改变任何东西（不得凭空多摊）。"""
        ds = env
        _seed(ds, 12)
        rid = _rule(ds, basis='equal', rounding='ceil')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'scale': 0, 'persist_result': False,
        })
        vals = [int(a['value']) for a in r['allocations']]
        assert sum(vals) == 12

    def test_illegal_rounding_is_rejected(self, env):
        ds = env
        _seed(ds, 100)
        rid = _rule(ds, basis='equal', rounding=None)
        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'rounding': 'nearest', 'persist_result': False,
            })
        assert 'rounding' in str(exc.value)

    def test_source_total_differs_when_rounded_up(self, env):
        """ceil 改了总额 → `source_total` 保留父行原值供对账。"""
        ds = env
        _seed(ds, 10.4)
        rid = _rule(ds, basis='equal', rounding='ceil')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'scale': 0, 'persist_result': False,
        })
        assert r['total'] == '11'
        # 比数值而非字符串：父行原值从 DB 读回是 float，str() 不补尾零
        assert Decimal(r['source_total']) == Decimal('10.4')


class TestGroupBy:
    def test_groups_split_evenly_then_by_basis(self, env):
        """组间均分 + 组内按 basis：2 组各 50，组内按 qty 1:3。"""
        ds = env
        ids = _seed(ds, 100, lines=(
            (1, 0, 'CC1'), (1, 0, 'CC2'), (3, 0, 'CC1'), (3, 0, 'CC2'),
        ))
        rid = _rule(ds, basis='quantity', group_by='cost_center')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'qty', 'persist_result': False,
        })

        got = {a['id']: (a['value'], a['group']) for a in r['allocations']}
        assert got[ids[0]] == ('12.50', 'CC1')   # 组1 总额 50，1:3 → 12.5/37.5
        assert got[ids[2]] == ('37.50', 'CC1')
        assert got[ids[1]] == ('12.50', 'CC2')
        assert got[ids[3]] == ('37.50', 'CC2')
        assert _amounts(ds, ids) == pytest.approx([12.5, 12.5, 37.5, 37.5])

    def test_non_contiguous_group_members_are_correct(self, env):
        """同组行在 rows 里不连续（CC1,CC2,CC1）——按下标回填，不得串位。"""
        ds = env
        ids = _seed(ds, 90, lines=(
            (1, 0, 'CC1'), (1, 0, 'CC2'), (9, 0, 'CC1'),
        ))
        rid = _rule(ds, basis='quantity', group_by='cost_center')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'qty', 'persist_result': False,
        })
        got = dict((a['id'], a['value']) for a in r['allocations'])
        # 2 组各 45；CC1 组内 1:9 → 4.5 / 40.5；CC2 单行 → 45
        assert got == {ids[0]: '4.50', ids[1]: '45.00', ids[2]: '40.50'}

    def test_group_by_with_floor_conserves(self, env):
        ds = env
        ids = _seed(ds, 100, lines=(
            (1, 0, 'CC1'), (1, 0, 'CC2'), (1, 0, 'CC1'), (1, 0, 'CC2'),
        ))
        rid = _rule(ds, basis='equal', group_by='cost_center', floor=20)

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'persist_result': False,
        })
        vals = [float(a['value']) for a in r['allocations']]
        assert min(vals) >= 20
        assert round(sum(vals), 2) == 100.00

    def test_group_by_floor_conflict_is_422(self, env):
        ds = env
        ids = _seed(ds, 100, lines=(
            (1, 0, 'CC1'), (1, 0, 'CC2'), (1, 0, 'CC1'), (1, 0, 'CC2'),
        ))
        rid = _rule(ds, basis='equal', group_by='cost_center', floor=30)
        with pytest.raises(AllocationError) as exc:
            _svc(ds).allocate_by_rule({
                'allocation_rule_id': rid, 'parent_id': 1,
                'target_object': 'order_line', 'target_field': 'amount',
                'persist_result': False,
            })
        assert exc.value.status_code == 422
        assert _amounts(ds, ids) == [0, 0, 0, 0]


class TestRecordAllocationResults:
    def test_persists_header_and_line_rows(self, env):
        ds = env
        ids = _seed(ds, 100, lines=((10, 0, None), (30, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity', target='expense')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'qty', 'document_type': 'order',
            'charge_source': 'invoice',
            'source_document_type': 'invoice', 'source_document_id': 777,
        })

        res = r['result_ids']
        assert res['header_result_id'] is not None
        assert len(res['line_result_ids']) == 3

        # 【2026-10-07 拆表】留痕迁至allocation_results，且不再有
        #   process_code 列（分摊不经 calc_procedure，无过程可指）。
        header = ds.execute(
            "SELECT level, document_line_id, amount, origin, charge_source,"
            " source_document_type, source_document_id, target,"
            " allocation_basis, allocation_rule_id, parent_id"
            " FROM allocation_results WHERE id = ?",
            (res['header_result_id'],)
        ).fetchone()
        assert header[0] == 'header'
        assert header[1] is None
        assert header[2] == 100.0
        assert header[3] == 'unplanned'
        assert header[4] == 'invoice'
        assert header[5] == 'invoice' and header[6] == 777
        assert header[7] == 'expense'
        assert header[8] == 'quantity'
        assert header[9] == rid
        assert header[10] == 1

        lines = ds.execute(
            "SELECT document_line_id, amount, sequence, level"
            " FROM allocation_results WHERE id IN (?,?,?) ORDER BY sequence",
            tuple(res['line_result_ids']),
        ).fetchall()
        assert [l[0] for l in lines] == ids
        assert [l[1] for l in lines] == pytest.approx([10.0, 30.0, 60.0])
        assert [l[2] for l in lines] == [1, 2, 3]
        assert {l[3] for l in lines} == {'line'}

    def test_line_rows_carry_allocated_amounts(self, env):
        ds = env
        ids = _seed(ds, 100, lines=((10, 0, None), (30, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'qty', 'document_type': 'order',
        })
        line_ids = r['result_ids']['line_result_ids']
        rows = ds.execute(
            "SELECT document_line_id, amount FROM allocation_results"
            " WHERE id IN (?,?,?)", tuple(line_ids),
        ).fetchall()
        got = {r0[0]: r0[1] for r0 in rows}
        assert got == dict(zip(ids, [10.0, 30.0, 60.0]))

    def test_header_line_conservation_holds(self, env):
        """头记总额 == Σ行记摊得额（FR-013「头记总额、行记摊得额」）。"""
        ds = env
        _seed(ds, 100, lines=((1, 0, None), (1, 0, None), (1, 0, None)))
        rid = _rule(ds, basis='equal')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'document_type': 'order',
        })
        rid_hdr = r['result_ids']['header_result_id']
        line_ids = r['result_ids']['line_result_ids']
        qs = ','.join('?' * len(line_ids))
        total = ds.execute(
            f"SELECT SUM(amount) FROM allocation_results"
            f" WHERE id IN ({qs})",
            tuple(line_ids),
        ).fetchone()[0]
        header = ds.execute(
            "SELECT amount FROM allocation_results WHERE id = ?", (rid_hdr,)
        ).fetchone()[0]
        assert round(total, 2) == round(header, 2) == 100.0

    def test_persist_result_false_skips_trace(self, env):
        ds = env
        _seed(ds, 100)
        rid = _rule(ds, basis='equal')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'persist_result': False,
        })
        assert r['result_ids'] is None
        n = ds.execute("SELECT COUNT(*) FROM allocation_results").fetchone()[0]
        assert n == 0

    def test_schema_has_source_document_columns(self, env):
        """schema 两列真的建出来了（否则 INSERT 会 OperationalError）。"""
        ds = env
        cols = {r[1] for r in ds.execute(
            "PRAGMA table_info(allocation_results)")}
        assert {'source_document_type', 'source_document_id'} <= cols

    def test_allocation_columns_absent_from_calc_result(self, env):
        """拆表的**核心断言**：分摊列不得留在定价表里。

        留在calc_results 上意味着两条链路仍共表——那正是本次修复掉的
        缺陷根因（定价重算作废分摊留痕 / write_back 写两遍）。故不是
        「暂未迁走」，而是**永不该有**。
        """
        ds = env
        cols = {r[1] for r in ds.execute("PRAGMA table_info(calc_results)")}
        moved = {'charge_source', 'source_document_type',
                 'source_document_id', 'allocation_basis',
                 'allocation_rule_id'}
        assert not (cols & moved), f"定价表仍含分摊列: {cols & moved}"

    def test_allocation_result_has_no_price_columns(self, env):
        """新表**不得**含价格列——非金额分摊下它们不是空值而是错值。

        `price_mode='carry'`意为「无价格」、`base=待摊总额` 是把金额
        当计算基数。这类列一旦存在，工时/数量分摊就会在表里留下一批
        看着像数据、实则无意义的字段。
        """
        ds = env
        cols = {r[1] for r in ds.execute(
            "PRAGMA table_info(allocation_results)")}
        price_cols = {'rate', 'base', 'price_mode', 'rate_source',
                      'result_semantic', 'base_level', 'base_source',
                      'rolling', 'process_code'}
        assert not (cols & price_cols), f"分摊表仍含价格列: {cols & price_cols}"

    def test_rule_snapshot_is_recorded(self, env):
        """当次配置须快照进留痕——规则会被改，只存 rule_id 答不出
        「当时按什么摊的」。"""
        ds = env
        _seed(ds, 100, lines=((10, 0, None), (30, 0, None), (60, 0, None)))
        rid = _rule(ds, basis='quantity')

        r = _svc(ds).allocate_by_rule({
            'allocation_rule_id': rid, 'parent_id': 1,
            'target_object': 'order_line', 'target_field': 'amount',
            'basis_field': 'qty', 'document_type': 'order',
            'group_by': 'cost_center', 'rounding': 'ceil', 'floor': 20,
        })
        hdr = r['result_ids']['header_result_id']
        got = ds.execute(
            "SELECT allocation_basis, allocation_basis_field, group_by,"
            " rounding, floor_value"
            " FROM allocation_results WHERE id = ?", (hdr,)
        ).fetchone()
        assert got == ('quantity', 'qty', 'cost_center', 'ceil', 20.0)
