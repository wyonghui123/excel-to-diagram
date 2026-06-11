# -*- coding: utf-8 -*-
"""
[R2-2.3 2026-06-11] N+1 优化性能回归测试

目标: 锁定 _batch_count_children + _batch_count_descendant_relations 的性能特性,
防止未来修改退回 N+1 实现.

测试策略:
1. [正确性] 批量版结果 = 单记录版结果 (mock data_source 对比)
2. [性能] 批量版 SQL 调用次数 = 1 (无论 records 多大)
3. [边界] 空 records / 无 id / 无 relations / 自环 / 多对多场景
4. [回退] mock data_source 抛错时, batch 正确 fallback 到单记录 (并跑 N 次)
"""
import sys
import os
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.computation_service import computation_service


# ════════════════════════════════════════════════════════
# Mock MetaObject + registry.patch
# ════════════════════════════════════════════════════════

class _MockMetaObj:
    def __init__(self, table_name='service_modules'):
        self.table_name = table_name


@pytest.fixture(autouse=True)
def patched_registry(monkeypatch):
    """Patch registry.get 让它返回 mock MetaObject (autouse: 所有测试自动用)."""
    from meta.core import models as models_module

    def _fake_get(object_type):
        return _MockMetaObj(table_name={
            'service_module': 'service_modules',
            'business_object': 'business_objects',
            'sub_domain': 'sub_domains',
            'domain': 'domains',
            'version': 'versions',
            'product': 'products',
            'enum_type': 'enum_types',
            'enum_value': 'enum_values',
        }.get(object_type, f'{object_type}s'))

    monkeypatch.setattr(models_module.registry, 'get', _fake_get)
    return _fake_get


# ════════════════════════════════════════════════════════
# Mock DataSource
# ════════════════════════════════════════════════════════

class _FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
    def fetchall(self):
        return list(self.rows)
    def fetchone(self):
        return self.rows[0] if self.rows else None


class _EmptyCursor:
    def fetchall(self):
        return []
    def fetchone(self):
        return None


class _SequencedDS:
    """按 execute 调用顺序返回预设的 rows 列表.

    responses: list of (list-of-tuples), 第 i 次 execute 返回 responses[i].
    """
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self._idx = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params or ()))
        if self._idx >= len(self.responses):
            return _EmptyCursor()
        rows = self.responses[self._idx]
        self._idx += 1
        return _FakeCursor(rows)


def _make_ds(responses):
    """便捷构造: responses = [list-of-tuples, ...] (按顺序)."""
    return _SequencedDS(responses)


# ════════════════════════════════════════════════════════
# R2-2.1 性能测试: _batch_count_children
# ════════════════════════════════════════════════════════

class TestBatchCountChildrenSingleSQL:
    """[R2-2.1] 批量 count_children 必须只发 1 个 SQL."""

    def test_20_records_1_sql_call(self):
        """20 条 records → 1 次 execute."""
        records = [{'id': i} for i in range(1, 21)]
        computation = {
            'type': 'count_children',
            'target_object': 'service_module',
            'foreign_key': 'service_module_id',
        }

        ds = _make_ds([
            [(1, 5), (2, 3), (5, 7), (10, 0)],
        ])

        computation_service._batch_count_children(
            ds, 'domain', records, 'child_count', computation
        )

        assert len(ds.calls) == 1, f"FAIL: ran {len(ds.calls)} SQL, expected 1"
        sql, params = ds.calls[0]
        assert 'IN (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)' in sql, sql
        assert 'GROUP BY service_module_id' in sql
        assert 'COUNT(*)' in sql
        assert len(params) == 20

    def test_count_results_match_single_record(self):
        """批量版结果与单记录版结果一致 (mock 对比)."""
        records = [{'id': i} for i in range(1, 6)]
        computation = {
            'type': 'count_children',
            'target_object': 'service_module',
            'foreign_key': 'service_module_id',
        }

        # --- path A: batch ---
        ds_batch = _make_ds([
            [(1, 5), (2, 3), (3, 0), (4, 2), (5, 7)],
        ])
        batch_records = [dict(r) for r in records]
        computation_service._batch_count_children(
            ds_batch, 'domain', batch_records, 'cnt', computation
        )

        # --- path B: single-record ---
        ds_single = _make_ds([
            [(5,)],
            [(3,)],
            [(0,)],
            [(2,)],
            [(7,)],
        ])
        single_records = [dict(r) for r in records]
        for rec in single_records:
            rec['cnt'] = computation_service._count_children(
                ds_single, 'domain', rec['id'], computation
            )

        for b, s in zip(batch_records, single_records):
            assert b['cnt'] == s['cnt'], (
                f"id={b['id']}: batch={b['cnt']} != single={s['cnt']}"
            )

    def test_missing_id_records_get_zero(self):
        """无 id 的 record 应得 0."""
        records = [{'id': 1}, {'id': None}, {'no_id': True}, {'id': 2}]
        computation = {
            'type': 'count_children',
            'target_object': 'service_module',
            'foreign_key': 'service_module_id',
        }
        ds = _make_ds([[(1, 10), (2, 20)]])

        computation_service._batch_count_children(
            ds, 'domain', records, 'cnt', computation
        )

        assert records[0]['cnt'] == 10
        assert records[1]['cnt'] == 0   # id=None
        assert records[2]['cnt'] == 0   # no id
        assert records[3]['cnt'] == 20

    def test_empty_records_returns_immediately(self):
        """空 records 列表不跑 SQL."""
        ds = _make_ds([])
        computation_service._batch_count_children(
            ds, 'domain', [], 'cnt', {'type': 'count_children'}
        )
        assert len(ds.calls) == 0

    def test_records_without_any_valid_id_returns_zero(self):
        """全部 records 都无 id, 不跑 SQL, 全设为 0."""
        records = [{'no_id': True}, {'also_no_id': True}]
        computation = {
            'type': 'count_children',
            'target_object': 'service_module',
            'foreign_key': 'service_module_id',
        }
        ds = _make_ds([])

        computation_service._batch_count_children(
            ds, 'domain', records, 'cnt', computation
        )

        assert len(ds.calls) == 0
        for r in records:
            assert r['cnt'] == 0

    def test_sql_failure_falls_back_to_per_record(self):
        """SQL 抛错时 fallback 到单记录 (保证正确性)."""
        records = [{'id': 1}, {'id': 2}]
        computation = {
            'type': 'count_children',
            'target_object': 'service_module',
            'foreign_key': 'service_module_id',
        }

        class BrokenDS:
            def __init__(self):
                self.calls = []
            def execute(self, sql, params=None):
                self.calls.append((sql, params or ()))
                if len(self.calls) == 1:
                    raise RuntimeError("simulated DB error")
                return _FakeCursor([(7,)])

        ds = BrokenDS()
        computation_service._batch_count_children(
            ds, 'domain', records, 'cnt', computation
        )

        assert len(ds.calls) == 3  # 1 batch fail + 2 per-record
        assert records[0]['cnt'] == 7
        assert records[1]['cnt'] == 7


# ════════════════════════════════════════════════════════
# R2-2.2 性能测试: _batch_count_descendant_relations
# ════════════════════════════════════════════════════════

class TestBatchCountDescendantRelationsSingleSQL:
    """[R2-2.2] 批量 count_descendant_relations 必须只发 1 个 SQL."""

    @pytest.mark.parametrize("object_type,parent_col", [
        ('domain', 'sd.domain_id'),
        ('sub_domain', 'sm.sub_domain_id'),
        ('service_module', 'bo.service_module_id'),
    ])
    def test_20_records_1_sql_call(self, object_type, parent_col):
        """20 条 records → 1 次 execute."""
        records = [{'id': i} for i in range(1, 21)]

        ds = _make_ds([
            [(1, 5), (2, 3), (5, 7), (10, 0)],
        ])

        computation_service._batch_count_descendant_relations(
            ds, object_type, records, 'relation_count'
        )

        assert len(ds.calls) == 1, (
            f"FAIL [{object_type}]: ran {len(ds.calls)} SQL, expected 1"
        )
        sql, params = ds.calls[0]
        assert f'GROUP BY {parent_col}' in sql, sql
        assert 'COUNT(DISTINCT r.id)' in sql, sql
        assert 'LEFT JOIN relationships' in sql
        assert f'{parent_col} IN (' in sql
        assert len(params) == 20

    def test_count_results_match_single_record(self):
        """批量版结果与单记录版结果一致 (每条记录独立 mock, 避免序列偏移)."""
        # --- path A: batch (5 ids in one SQL) ---
        ds_batch = _make_ds([
            [(1, 5), (2, 3), (3, 0), (4, 2), (5, 7)],
        ])
        batch_records = [{'id': i} for i in range(1, 6)]
        computation_service._batch_count_descendant_relations(
            ds_batch, 'domain', batch_records, 'rc'
        )

        # --- path B: single-record (each with own mock) ---
        expected = {1: 5, 2: 3, 3: 0, 4: 2, 5: 7}
        for rid, exp in expected.items():
            # 独立 mock: bo_ids 查询 + count 查询
            # 注意: _count_descendant_relations 在 bo_ids 为空时 early-return (只跑 1 个 SQL)
            if rid == 3:
                # id=3: 空 bo_ids → 1 SQL only
                ds = _make_ds([[]])
            else:
                # 其他: 至少 1 个 bo + count 查询
                ds = _make_ds([
                    [(10 * rid,)],  # dummy bo_id
                    [(exp,)],
                ])

            cnt = computation_service._count_descendant_relations(ds, 'domain', rid)
            assert cnt == exp, f"id={rid}: single-record expected {exp}, got {cnt}"

        for b, exp in zip(batch_records, expected.values()):
            assert b['rc'] == exp, (
                f"id={b['id']}: batch={b['rc']} != single={exp}"
            )

    def test_distinct_count_dedupes_self_loop(self):
        """自环关系必须用 DISTINCT 去重."""
        records = [{'id': 1}, {'id': 2}]
        ds = _make_ds([[(1, 5), (2, 3)]])
        computation_service._batch_count_descendant_relations(
            ds, 'domain', records, 'rc'
        )
        sql, _ = ds.calls[0]
        assert 'COUNT(DISTINCT' in sql, "DISTINCT required for self-loop dedup"

    def test_left_join_handles_zero_relations(self):
        """LEFT JOIN 确保无 relations 的 parent 也返 count=0."""
        records = [{'id': 1}, {'id': 99}]
        ds = _make_ds([[(1, 5)]])
        computation_service._batch_count_descendant_relations(
            ds, 'domain', records, 'rc'
        )
        assert records[0]['rc'] == 5
        assert records[1]['rc'] == 0  # not in result, count_map.get -> 0

    def test_empty_records_returns_immediately(self):
        ds = _make_ds([])
        computation_service._batch_count_descendant_relations(
            ds, 'domain', [], 'rc'
        )
        assert len(ds.calls) == 0

    def test_unsupported_object_type_falls_back(self):
        """不支持的 object_type (如 user_group) → _count_descendant_relations 立即返 0 (无 SQL)."""
        records = [{'id': 1}, {'id': 2}]

        class _PermissiveDS:
            def __init__(self):
                self.calls = []
            def execute(self, sql, params=None):
                self.calls.append((sql, params or ()))
                return _FakeCursor([(5,)])

        ds = _PermissiveDS()
        computation_service._batch_count_descendant_relations(
            ds, 'user_group', records, 'rc'
        )
        # _count_descendant_relations 对 user_group 走 else: return 0 (无 SQL)
        # fallback 调了 2 次, 但每次都是 0 SQL → 共 0 SQL
        assert len(ds.calls) == 0
        assert records[0]['rc'] == 0
        assert records[1]['rc'] == 0

    def test_sql_failure_falls_back_to_per_record(self):
        """批量 SQL 抛错时 fallback 到单记录."""
        records = [{'id': 1}, {'id': 2}]

        class BrokenDS:
            def __init__(self):
                self.calls = []
            def execute(self, sql, params=None):
                self.calls.append((sql, params or ()))
                if len(self.calls) == 1:
                    raise RuntimeError("simulated JOIN failure")
                return _FakeCursor([(8,)])

        ds = BrokenDS()
        computation_service._batch_count_descendant_relations(
            ds, 'domain', records, 'rc'
        )
        # 1 batch fail + 2 x 2 per-record = 5
        assert len(ds.calls) == 5
        assert records[0]['rc'] == 8
        assert records[1]['rc'] == 8


# ════════════════════════════════════════════════════════
# 防退化断言 (锁死 N+1 不再回来)
# ════════════════════════════════════════════════════════

class TestNoNPlusOneRegression:
    """[R2-2.3 防退化] 任何后续修改不能把批量版退回 N+1."""

    @pytest.mark.parametrize("object_type", [
        'domain', 'sub_domain', 'service_module',
    ])
    def test_descendant_relations_uses_single_sql_for_any_size(self, object_type):
        """[防退化] 100 条 records → 仍只跑 1 SQL."""
        records = [{'id': i} for i in range(1, 101)]
        rows = [(i, 0) for i in range(1, 101)]
        ds = _make_ds([rows])

        computation_service._batch_count_descendant_relations(
            ds, object_type, records, 'rc'
        )
        assert len(ds.calls) == 1, (
            f"[REGRESSION] {object_type} ran {len(ds.calls)} SQL (expected 1)."
        )

    @pytest.mark.parametrize("object_type", [
        'domain', 'sub_domain', 'service_module', 'version', 'product',
    ])
    def test_count_children_uses_single_sql_for_any_size(self, object_type):
        """[防退化] 100 条 records → 仍只跑 1 SQL."""
        records = [{'id': i} for i in range(1, 101)]
        computation = {
            'type': 'count_children',
            'target_object': 'service_module',
            'foreign_key': 'service_module_id',
        }
        rows = [(i, 0) for i in range(1, 101)]
        ds = _make_ds([rows])

        computation_service._batch_count_children(
            ds, object_type, records, 'cnt', computation
        )
        assert len(ds.calls) == 1, (
            f"[REGRESSION] {object_type} ran {len(ds.calls)} SQL (expected 1)."
        )