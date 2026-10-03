# -*- coding: utf-8 -*-
"""
T-03 分摊 allocate() 集成测试 (真实保存链路 ActionExecutor)

覆盖:
1. 1 父 3 子总额 100 → 33.34/33.33/33.33, 落库 + Σ 精确守恒
2. 带 id 的权重按 id 对齐 (与子行 id 顺序无关)
3. 权重数 != 子行数 → 422, 且零写入
4. 注入第 2 行写入失败 → 整体回滚 (业务表零残留)
5. 权重 id 不属于该父 → 422
6. 父行不存在 / 值为空 → 错误
"""
import os

import pytest

pytestmark = pytest.mark.integration

# 本文件使用临时 sqlite + 建表/插入夹具, 按项目惯例绕过 raw-SQL 守卫
os.environ.setdefault('ALLOW_RAW_SQL', '1')

from unittest.mock import patch

from meta.core.action_executor import ActionExecutor, ActionResult
from meta.core.models import (
    ActionType, FieldType, MetaAction, MetaField, MetaObject, registry,
)
from meta.core.rule_executor import RuleEngine
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.services.allocation_service import AllocationError, AllocationService

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
    amount REAL
)
"""


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
    """独立 sqlite + 注入 registry (其余对象仍走真实 registry)。"""
    ds = SQLiteAdapter()
    ds.connect(path=str(tmp_path / 'alloc.db'))
    ds.execute(ORDERS_DDL)
    ds.execute(LINES_DDL)

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

    # 无审计表/用户上下文: 关闭审计, 仍走 WriteGuard/校验/compute 全链路
    def build_executor(self):
        return ActionExecutor(self.ds, RuleEngine(self.ds), audit_enabled=False)

    with patch.object(registry, 'get', side_effect=fake_get), \
         patch('meta.services.cascade_service.HierarchyConfigLoader.get_foreign_key',
               return_value='order_id'), \
         patch('meta.services.cascade_service.HierarchyConfigLoader.get_parent_object',
               return_value='order'), \
         patch.object(AllocationService, '_build_executor', build_executor):
        yield ds, parent_meta, child_meta


def _seed(ds, parent_amount=100, child_amounts=(0, 0, 0)):
    ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', ?)",
               (parent_amount,))
    child_ids = []
    for amt in child_amounts:
        cur = ds.execute(
            "INSERT INTO order_lines (order_id, amount) VALUES (1, ?)", (amt,)
        )
        child_ids.append(cur.lastrowid)
    return child_ids


def _amounts(ds, child_ids):
    return [
        ds.execute("SELECT amount FROM order_lines WHERE id = ?", (cid,)).fetchone()[0]
        for cid in child_ids
    ]


def test_allocate_third_split_conserves(env):
    ds, _, _ = env
    child_ids = _seed(ds, 100)

    result = AllocationService(data_source=ds).allocate({
        'parent_id': 1, 'target_object': 'order_line',
        'target_field': 'amount', 'weights': [1, 1, 1],
    })

    assert result['verified'] is True
    assert result['total'] == '100.00'
    assert [a['id'] for a in result['allocations']] == child_ids
    assert [a['value'] for a in result['allocations']] == [
        '33.34', '33.33', '33.33',
    ]
    assert _amounts(ds, child_ids) == pytest.approx([33.34, 33.33, 33.33])
    total = ds.execute(
        "SELECT SUM(amount) FROM order_lines WHERE order_id = 1"
    ).fetchone()[0]
    assert round(total, 2) == 100.00


def test_allocate_weights_aligned_by_id(env):
    ds, _, _ = env
    child_ids = _seed(ds, 100, (0, 0))
    lo, hi = child_ids

    result = AllocationService(data_source=ds).allocate({
        'parent_id': 1, 'target_object': 'order_line', 'target_field': 'amount',
        'weights': [{'id': hi, 'weight': 3}, {'id': lo, 'weight': 7}],
    })

    # hi 权重 3 → 30, lo 权重 7 → 70 (按 id 对齐, 与传入顺序无关)
    assert dict((a['id'], a['value']) for a in result['allocations']) == {
        lo: '70.00', hi: '30.00',
    }
    assert _amounts(ds, child_ids) == pytest.approx([70.0, 30.0])


def test_allocate_count_mismatch_422_and_no_write(env):
    ds, _, _ = env
    child_ids = _seed(ds, 100)

    with pytest.raises(AllocationError) as exc:
        AllocationService(data_source=ds).allocate({
            'parent_id': 1, 'target_object': 'order_line',
            'target_field': 'amount', 'weights': [1, 1],
        })
    assert exc.value.status_code == 422
    assert _amounts(ds, child_ids) == [0, 0, 0]


def test_allocate_rolls_back_on_row_failure(env):
    ds, _, _ = env
    child_ids = _seed(ds, 100)

    real = ActionExecutor(ds, RuleEngine(ds), audit_enabled=False)

    class FlakyExecutor:
        def __init__(self):
            self.calls = 0

        def execute(self, obj, action_id, params, skip_rules=False):
            self.calls += 1
            if self.calls == 2:
                return ActionResult.fail(error='INJECTED', message='boom')
            return real.execute(obj, action_id, params, skip_rules)

    with patch.object(AllocationService, '_build_executor',
                      lambda self: FlakyExecutor()):
        with pytest.raises(AllocationError):
            AllocationService(data_source=ds).allocate({
                'parent_id': 1, 'target_object': 'order_line',
                'target_field': 'amount', 'weights': [1, 1, 1],
            })

    # 第一行已写入但被整体回滚 → 业务表零残留
    assert _amounts(ds, child_ids) == [0, 0, 0]


def test_allocate_weight_id_not_belonging_422(env):
    ds, _, _ = env
    child_ids = _seed(ds, 100, (0, 0))

    with pytest.raises(AllocationError) as exc:
        AllocationService(data_source=ds).allocate({
            'parent_id': 1, 'target_object': 'order_line', 'target_field': 'amount',
            'weights': [{'id': child_ids[0], 'weight': 1},
                        {'id': 99999, 'weight': 1}],
        })
    assert exc.value.status_code == 422
    assert _amounts(ds, child_ids) == [0, 0]


def test_allocate_parent_missing_404(env):
    ds, _, _ = env
    # 存在 1 个子行 (fk=777) 但父行 777 不存在 → 子行数匹配, 父行校验报 404
    ds.execute("INSERT INTO order_lines (order_id, amount) VALUES (777, 0)")

    with pytest.raises(AllocationError) as exc:
        AllocationService(data_source=ds).allocate({
            'parent_id': 777, 'target_object': 'order_line',
            'target_field': 'amount', 'weights': [1],
        })
    assert exc.value.status_code == 404


def test_allocate_parent_value_empty_422(env):
    ds, _, _ = env
    ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', NULL)")
    ds.execute("INSERT INTO order_lines (order_id, amount) VALUES (1, 0)")

    with pytest.raises(AllocationError) as exc:
        AllocationService(data_source=ds).allocate({
            'parent_id': 1, 'target_object': 'order_line',
            'target_field': 'amount', 'weights': [1],
        })
    assert exc.value.status_code == 422


class TestSplit:
    """T-04 拆分成 N 个新行 (共用同一守恒引擎)。"""

    def _rows(self, ds):
        return ds.execute(
            "SELECT id, order_id, amount FROM order_lines ORDER BY id"
        ).fetchall()

    def test_split_creates_three_rows_conserved(self, env):
        ds, _, _ = env
        ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', 100)")

        result = AllocationService(data_source=ds).split({
            'parent_id': 1, 'target_object': 'order_line',
            'target_field': 'amount', 'split_count': 3,
        })

        assert result['verified'] is True
        assert result['total'] == '100.00'
        assert [a['value'] for a in result['allocations']] == [
            '33.34', '33.33', '33.33',
        ]
        rows = self._rows(ds)
        assert len(rows) == 3
        assert all(r[1] == 1 for r in rows)           # fk 指向父行
        assert round(sum(r[2] for r in rows), 2) == 100.00

    def test_split_with_weights_and_template(self, env):
        ds, _, _ = env
        ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', 100)")

        result = AllocationService(data_source=ds).split({
            'parent_id': 1, 'target_object': 'order_line',
            'target_field': 'amount', 'weights': [3, 7],
            'template': {'name': 'L'},
        })

        assert [a['value'] for a in result['allocations']] == ['30.00', '70.00']
        rows = self._rows(ds)
        assert [r[2] for r in rows] == pytest.approx([30.0, 70.0])
        assert len(rows) == 2

    def test_split_rolls_back_on_failure(self, env):
        ds, _, _ = env
        ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', 100)")

        real = ActionExecutor(ds, RuleEngine(ds), audit_enabled=False)

        class FlakyExecutor:
            def __init__(self):
                self.calls = 0

            def execute(self, obj, action_id, params, skip_rules=False):
                self.calls += 1
                if self.calls == 2:
                    return ActionResult.fail(error='INJECTED', message='boom')
                return real.execute(obj, action_id, params, skip_rules)

        with patch.object(AllocationService, '_build_executor',
                          lambda self: FlakyExecutor()):
            with pytest.raises(AllocationError):
                AllocationService(data_source=ds).split({
                    'parent_id': 1, 'target_object': 'order_line',
                    'target_field': 'amount', 'split_count': 3,
                })

        assert self._rows(ds) == []      # 首行已建但被整体回滚

    def test_split_requires_weights_or_count(self, env):
        ds, _, _ = env
        ds.execute("INSERT INTO orders (id, name, amount) VALUES (1, 'O1', 100)")

        with pytest.raises(AllocationError):
            AllocationService(data_source=ds).split({
                'parent_id': 1, 'target_object': 'order_line',
                'target_field': 'amount',
            })
