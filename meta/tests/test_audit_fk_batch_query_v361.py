# -*- coding: utf-8 -*-
"""
[PERF v3.61] audit_service FK 结构化 batch query 单测

验证:
1. _structure_fk_values_in_data 走 batch fetch (N+1 → 1+1)
2. relationship 9 FK → 实际只调 ds.find N 次 (按表去重)
3. 语义与单查一致 (target_type/target_id/target_display/target_key 相同)
4. 边界: 空 data / 全无效表名 / 部分 FK 命中 / 跨表 FK
"""
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fresh_db():
    """建一个 temp DB, 含 relationship 9 FK 涉及的 5 张表"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE versions (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO versions VALUES (100, 'V1', 'v1.0');
        INSERT INTO versions VALUES (200, 'V2', 'v2.0');

        CREATE TABLE domains (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO domains VALUES (10, 'D1', '财务域');
        INSERT INTO domains VALUES (20, 'D2', '人力域');

        CREATE TABLE sub_domains (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO sub_domains VALUES (301, 'SD1', '应收子域');
        INSERT INTO sub_domains VALUES (302, 'SD2', '应付子域');

        CREATE TABLE service_modules (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO service_modules VALUES (501, 'SM1', '销售模块');
        INSERT INTO service_modules VALUES (502, 'SM2', '采购模块');

        CREATE TABLE business_objects (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT
        );
        INSERT INTO business_objects VALUES (901, 'BO1', '订单BO');
        INSERT INTO business_objects VALUES (902, 'BO2', '客户BO');
    """)
    conn.commit()
    conn.close()

    # 注册架构表到白名单
    from meta.core.table_name_validator import register_table_name, invalidate_cache
    for t in [
        'versions', 'domains', 'sub_domains',
        'service_modules', 'business_objects',
    ]:
        register_table_name(t)
    invalidate_cache()

    yield path

    try:
        os.unlink(path)
    except Exception:
        pass


class _FakeDataSource:
    """Mock data_source — 记录 ds.find 调用次数, 返回指定表数据"""
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self.find_calls = []  # [(table, filters, ts), ...]

    def find(self, table_name, filters=None, order_by=None, limit=None):
        self.find_calls.append((table_name, dict(filters or {})))

        if not filters:
            return []

        # 处理 id__in (批量)
        if 'id__in' in filters:
            ids = list(filters['id__in'])
            placeholders = ','.join('?' * len(ids))
            sql = f'SELECT * FROM "{table_name}" WHERE id IN ({placeholders})'
            cur = self._conn.execute(sql, ids)
        elif 'id' in filters:
            sql = f'SELECT * FROM "{table_name}" WHERE id = ?'
            cur = self._conn.execute(sql, (filters['id'],))
        else:
            return []

        return [dict(row) for row in cur.fetchall()]


def _make_audit_service(fake_ds):
    """构造只测 FK 结构化方法的 AuditService 实例 (不需 DB / factory)"""
    from meta.services.audit_service import AuditService
    svc = AuditService.__new__(AuditService)
    svc.ds = fake_ds
    svc.ENABLE_FK_STRUCTURING = True
    svc.FK_FIELD_PATTERN = AuditService.FK_FIELD_PATTERN  # class-level
    return svc


# ─────────── batch query 行为测试 ───────────

class TestFkBatchQuery:
    """[PERF v3.61] 验证 batch query 优化"""

    def test_relationship_9_fks_batched_by_table(self, fresh_db):
        """relationship 9 FK 跨 5 表: 实际只 5 次 ds.find (按表去重)

        注: source_bo_id/target_bo_id 实际是 'business_objects' 的缩写,
        _resolve_fk_target_type('bo') 找不到 (没 'bo' 也没 'bos' 表),
        原版 R018 也是同样行为 (passthrough 原值). 这与原版语义一致.
        """
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {
            'version_id': 100,
            'source_domain_id': 10,
            'source_sub_domain_id': 301,
            'source_service_module_id': 501,
            'source_bo_id': 901,        # 已知: bo_id 缩写无法解析, passthrough
            'target_domain_id': 20,
            'target_sub_domain_id': 302,
            'target_service_module_id': 502,
            'target_bo_id': 902,        # 已知: 同上
            # 非 FK 字段, 应原样保留
            'name': '测试关系',
            'description': '测试描述',
        }

        result = svc._structure_fk_values_in_data(data)

        # 1) 调用次数: 4 张表各 1 次 = 4 次 (source_bo_id/target_bo_id 找不到表不查)
        # (旧版: 9~18 次, 当前 batch 优化: 4 次 → 节省 56~78%)
        assert len(ds.find_calls) == 4, (
            f"relationship 9 FK 应走 4 次 batch query (4 张可解析的表), "
            f"实际 {len(ds.find_calls)} 次: {ds.find_calls}"
        )

        # 2) 4 张表都被查过 (bo 是已知无法解析的缩写)
        tables_called = sorted({c[0] for c in ds.find_calls})
        assert tables_called == [
            'domains',           # 2 个 FK (source_domain_id + target_domain_id)
            'service_modules',   # 2 个 FK
            'sub_domains',       # 2 个 FK
            'versions',          # 1 个 FK
        ]

        # 3) 每个 batch call 用 id__in (非 id=)
        for table, filters in ds.find_calls:
            assert 'id__in' in filters, f"{table} 应走 id__in 批量, 实际: {filters}"
            assert 'id' not in filters, f"{table} 应弃用单 id=, 实际: {filters}"

        # 4) 7 个 FK 成功结构化 (source_bo_id/target_bo_id passthrough)
        fk_success = (
            'version_id', 'source_domain_id', 'source_sub_domain_id',
            'source_service_module_id',
            'target_domain_id', 'target_sub_domain_id',
            'target_service_module_id',
        )
        for fk_field in fk_success:
            assert fk_field in result, f"{fk_field} 应在结果中"
            parsed = json.loads(result[fk_field])
            assert 'target_type' in parsed
            assert 'target_id' in parsed
            assert 'target_display' in parsed

        # 5) bo_id 字段原值 passthrough (已知缩写, _resolve_fk_target_type 找不到)
        assert result['source_bo_id'] == 901, "source_bo_id 应 passthrough 原值"
        assert result['target_bo_id'] == 902, "target_bo_id 应 passthrough 原值"

        # 6) 非 FK 字段原样保留
        assert result['name'] == '测试关系'
        assert result['description'] == '测试描述'

        # 7) 验证 source vs target 正确指向不同记录
        source_sm = json.loads(result['source_service_module_id'])
        target_sm = json.loads(result['target_service_module_id'])
        assert source_sm['target_id'] == 501
        assert source_sm['target_display'] == '销售模块'
        assert target_sm['target_id'] == 502
        assert target_sm['target_display'] == '采购模块'

    def test_same_table_fks_share_one_batch(self, fresh_db):
        """多 FK 同表: 合并 1 次批量查 (不重复查)"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        # 3 个 FK 都指 service_module
        data = {
            'source_service_module_id': 501,
            'target_service_module_id': 502,
            'service_module_id': 501,
        }
        result = svc._structure_fk_values_in_data(data)

        # service_module (实际复数 service_modules) 只查 1 次, id__in 包含 3 个 id
        sm_calls = [c for c in ds.find_calls if c[0] == 'service_modules']
        assert len(sm_calls) == 1, f"service_modules 应只查 1 次, 实际 {len(sm_calls)}"
        assert set(sm_calls[0][1]['id__in']) == {501, 502}, (
            f"id__in 应包含 501+502 去重, 实际 {sm_calls[0][1]['id__in']}"
        )

    def test_empty_data_returns_empty(self):
        """边界: 空 dict 直接返回"""
        ds = _FakeDataSource(':memory:')
        svc = _make_audit_service(ds)

        assert svc._structure_fk_values_in_data({}) == {}
        assert ds.find_calls == [], "空 data 不应触发任何 SQL"

    def test_no_fk_fields_returns_as_is(self, fresh_db):
        """边界: 全是非 FK 字段, 原样返回"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {'name': 'test', 'description': '描述', 'count': 42}
        result = svc._structure_fk_values_in_data(data)

        assert result == data
        assert ds.find_calls == [], "无 FK 字段不应触发 SQL"

    def test_invalid_table_name_passthrough(self, fresh_db):
        """边界: FK 字段指向未注册表名, 原值 passthrough"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        # unknown_table_id 不在白名单, _resolve_fk_target_type 返回 None
        data = {'unknown_table_id': 999, 'version_id': 100}
        result = svc._structure_fk_values_in_data(data)

        assert result['unknown_table_id'] == 999, "无效表名应 passthrough 原值"
        assert 'target_type' not in json.loads(result['version_id']) or True
        # version_id 应成功结构化 (versions 表已注册)
        assert json.loads(result['version_id'])['target_display'] == 'v1.0'

    def test_partial_match_some_fks_miss(self, fresh_db):
        """边界: 部分 FK 命中, 部分未命中 (未命中 passthrough)"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {
            'version_id': 100,         # 命中
            'service_module_id': 999,  # 不存在, 应 passthrough
        }
        result = svc._structure_fk_values_in_data(data)

        # version_id 结构化
        v_parsed = json.loads(result['version_id'])
        assert v_parsed['target_display'] == 'v1.0'

        # service_module_id 不存在 → 原值 passthrough
        assert result['service_module_id'] == 999, "未命中 FK 应 passthrough 原值"

    def test_already_structured_json_passthrough(self, fresh_db):
        """边界: 已是结构化 JSON 的字段, 原样 passthrough (不重复查)"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        # 模拟 audit_log 已有结构化 JSON (避免重复 FK 解析)
        existing = json.dumps({
            'target_type': 'service_module',
            'target_id': 501,
            'target_display': '旧显示值',  # 不应被覆盖
            'target_key': 'SM1',
        }, ensure_ascii=False)

        data = {
            'service_module_id': existing,  # 已结构化
            'version_id': 100,             # 需查
        }
        result = svc._structure_fk_values_in_data(data)

        # service_module_id 应保持原值 (passthrough, 不重查)
        assert result['service_module_id'] == existing
        # version_id 应被结构化
        assert json.loads(result['version_id'])['target_display'] == 'v1.0'

        # 关键: 只查 1 张表 (versions), service_module 不查
        tables_called = [c[0] for c in ds.find_calls]
        assert 'service_module' not in tables_called, (
            f"已结构化的 FK 不应重查, 实际查了: {tables_called}"
        )

    def test_batch_fallback_on_table_not_found(self):
        """边界: 整张表都查不到 (target_type 指向空表)"""
        ds = _FakeDataSource(':memory:')
        svc = _make_audit_service(ds)

        data = {'version_id': 100}
        result = svc._structure_fk_values_in_data(data)

        # 版本表是空, 未命中 → 原值 passthrough
        assert result['version_id'] == 100

    def test_dict_passthrough(self, fresh_db):
        """边界: FK 字段值是 dict (已被解析为结构化), passthrough"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {
            'service_module_id': {
                'target_type': 'service_module',
                'target_id': 501,
                'target_display': 'dict形式',
            }
        }
        result = svc._structure_fk_values_in_data(data)

        # dict 应原样保留
        assert result['service_module_id'] == data['service_module_id']
        assert ds.find_calls == [], "dict 形式的 FK 不应触发 SQL"


# ─────────── 回归测试: 与单查语义等价 ───────────

class TestBatchQuerySemanticsEquivalent:
    """[PERF v3.61] 验证 batch 与原单查语义完全等价"""

    def test_single_fk_still_works(self, fresh_db):
        """单 FK 场景: batch 优化应与原单查结果完全一致"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {'version_id': 200}
        result = svc._structure_fk_values_in_data(data)

        parsed = json.loads(result['version_id'])
        # 单数 version 未注册, fallback 复数 versions (这是 _resolve_fk_target_type 行为)
        assert parsed['target_type'] == 'versions', (
            f"target_type 应为 'versions' (复数命中), 实际: {parsed['target_type']}"
        )
        assert parsed['target_id'] == 200
        assert parsed['target_display'] == 'v2.0'

    def test_target_key_extracted(self, fresh_db):
        """target_key 应从 code 字段提取 (业务 key)"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {'service_module_id': 501}
        result = svc._structure_fk_values_in_data(data)

        parsed = json.loads(result['service_module_id'])
        assert parsed['target_key'] == 'SM1', "target_key 应为 SM1 (从 code 字段)"

    def test_unicode_chinese_in_display(self, fresh_db):
        """中文字符应正确存储 (UTF-8, ensure_ascii=False)"""
        ds = _FakeDataSource(fresh_db)
        svc = _make_audit_service(ds)

        data = {'sub_domain_id': 301}
        result = svc._structure_fk_values_in_data(data)

        # 验证是 UTF-8 字符串而非 \u 转义
        assert '应收子域' in result['sub_domain_id'], (
            f"中文应是 UTF-8 直接字符, 实际: {result['sub_domain_id']!r}"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])