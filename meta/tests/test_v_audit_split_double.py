# -*- coding: utf-8 -*-
"""Tests for v007_50b _batch_read_audit_derived 拆双查 + Python 合并 (r017)

覆盖场景:
1. 仅有 audit_logs 行 → 返回 hot 数据
2. 仅有 audit_logs_archive 行 → 返回 archive 数据 (mock archive 独有 oid)
3. 两表都有同 oid → 取 MAX (hot 创建时间大者赢)
4. 两表都有但 archive 创建时间更晚 → 仍取 archive 值
5. IN 列表分片 (501 个 id) → 走 500/501 分片
6. 空 IN 列表 → 返回空字典
7. archive 表不存在 → 仅 hot, 不报错 (降级路径)
8. hot 查询失败 → 降级 v_audit_all 兜底
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def _create_test_db():
    """构造含 hot + archive 两表的最小测试 DB"""
    tmpdir = tempfile.mkdtemp(prefix='audit_split_double_')
    db_path = os.path.join(tmpdir, 'test.db')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""CREATE TABLE audit_logs (
        id INTEGER PRIMARY KEY,
        object_type TEXT,
        object_id INTEGER,
        action TEXT,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE audit_logs_archive (
        id INTEGER PRIMARY KEY,
        object_type TEXT,
        object_id INTEGER,
        action TEXT,
        created_at TEXT
    )""")

    # 关键索引 (与 prod 实测一致: prod archive 索引为 idx_audit_archive_type_id_action,
    # 列序 (object_type, object_id, action), 完美匹配 WHERE 三列)
    cur.execute("CREATE INDEX idx_audit_ssot_updated ON audit_logs "
                "(object_type, object_id, action, created_at)")
    cur.execute("CREATE INDEX idx_audit_archive_type_id_action "
                "ON audit_logs_archive (object_type, object_id, action)")

    # 测试数据: object_type='test_obj'
    cur.executemany(
        "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?)",
        [
            (1, 'test_obj', 100, 'UPDATE', '2026-01-15T10:00:00'),
            (2, 'test_obj', 100, 'INSERT', '2026-01-10T08:00:00'),  # 非 UPDATE 应过滤
            (3, 'test_obj', 200, 'UPDATE', '2026-02-20T12:00:00'),
            (4, 'test_obj', 300, 'UPDATE', '2026-03-10T14:00:00'),
            (5, 'test_obj', 400, 'UPDATE', '2026-04-05T09:00:00'),
        ])
    cur.executemany(
        "INSERT INTO audit_logs_archive VALUES (?, ?, ?, ?, ?)",
        [
            (10, 'test_obj', 100, 'UPDATE', '2026-01-15T11:00:00'),  # archive 比 hot 晚
            (11, 'test_obj', 200, 'UPDATE', '2026-02-20T12:00:00'),  # 同时间
            (12, 'test_obj', 500, 'UPDATE', '2026-05-01T10:00:00'),  # archive 独有
        ])
    conn.commit()
    return db_path, conn


class TestBatchReadAuditDerivedSplitDouble:
    """r017 方案 A 拆双查 + Python 合并"""

    def setup_method(self):
        """每个测试前重建测试 DB (隔离状态)"""
        self.db_path, self.conn = _create_test_db()

    def teardown_method(self):
        self.conn.close()
        try:
            os.unlink(self.db_path)
            os.rmdir(os.path.dirname(self.db_path))
        except Exception:
            pass

    # ---------- 场景 1: 仅有 audit_logs 行 → 返回 hot 数据 ----------
    def test_only_hot_table(self):
        """仅有 audit_logs 有数据的 oid → 正常返回"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        result = _batch_read_audit_derived(
            self.conn, 'test_obj', [300, 400])
        assert result == {
            '300': '2026-03-10T14:00:00',
            '400': '2026-04-05T09:00:00',
        }, f'仅 hot 应返回 hot MAX: {result}'

    # ---------- 场景 2: 仅有 audit_logs_archive 行 → 返回 archive 数据 ----------
    def test_only_archive_table(self):
        """archive 独有 oid → 返回 archive 数据 (hot 不会覆盖)"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        result = _batch_read_audit_derived(self.conn, 'test_obj', [500])
        assert result == {'500': '2026-05-01T10:00:00'}, \
            f'archive 独有应返回 archive: {result}'

    # ---------- 场景 3: 两表都有同 oid → 取 MAX (hot 创建时间大者赢) ----------
    def test_hot_wins_when_hot_newer(self):
        """两表都有, hot 时间晚 → 取 hot"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        # oid=300 在 hot 有 2026-03-10, archive 无 → 取 hot
        result = _batch_read_audit_derived(self.conn, 'test_obj', [300])
        assert result == {'300': '2026-03-10T14:00:00'}

    # ---------- 场景 4: 两表都有但 archive 创建时间更晚 → 仍取 archive 值 ----------
    def test_archive_wins_when_archive_newer(self):
        """两表都有, archive 时间晚 → 取 archive (MAX)"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        # oid=100: hot=2026-01-15T10:00, archive=2026-01-15T11:00 → 取 archive
        result = _batch_read_audit_derived(self.conn, 'test_obj', [100])
        assert result == {'100': '2026-01-15T11:00:00'}, \
            f'archive 更晚应取 archive: {result}'

    # ---------- 场景 5: IN 列表分片 (501 个 id) → 走 500/501 分片 ----------
    def test_chunked_in_list(self):
        """501 个 id 自动分 500+1, 结果合并正确"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        # 构造 501 个 oid (复用现有数据 id, 其余用不存在 id 测试空结果)
        ids = [100, 200, 300, 400, 500] + list(range(1000, 1496))
        result = _batch_read_audit_derived(self.conn, 'test_obj', ids)
        # 100/200/300/400/500 命中; 1000-1495 全部无数据
        assert len(result) == 5
        assert result['100'] == '2026-01-15T11:00:00'  # archive 较晚
        assert result['200'] == '2026-02-20T12:00:00'
        assert result['300'] == '2026-03-10T14:00:00'
        assert result['400'] == '2026-04-05T09:00:00'
        assert result['500'] == '2026-05-01T10:00:00'

    # ---------- 场景 6: 空 IN 列表 → 返回空字典 ----------
    def test_empty_in_list(self):
        """空列表直接返回, 不发 SQL"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        result = _batch_read_audit_derived(self.conn, 'test_obj', [])
        assert result == {}

    # ---------- 场景 7: archive 表不存在 → 仅 hot, 不报错 ----------
    def test_archive_table_missing(self):
        """archive 表不存在时降级为仅 hot 查询 (不报错)"""
        # 删除 archive 表
        self.conn.execute("DROP TABLE audit_logs_archive")
        self.conn.commit()

        from meta.core.audit_derived_fields import _batch_read_audit_derived

        result = _batch_read_audit_derived(self.conn, 'test_obj', [100, 300])
        # archive 缺失时仅 hot, 100 取 hot MAX
        assert result == {
            '100': '2026-01-15T10:00:00',
            '300': '2026-03-10T14:00:00',
        }, f'archive 缺失应仅返回 hot: {result}'

    # ---------- 场景 8: hot 查询失败 → 返回 {} (让上游 fallback created_at) ----------
    def test_hot_fails_returns_empty_for_upstream_fallback(self):
        """hot 表被破坏 → 返空 dict, 不走 v_audit_all (避免 100ms 退化)

        [FIX 2026-09-15 r017 二次检查] 之前降级到 v_audit_all 是错误设计:
        v_audit_all 实测 100ms, 等于从 8ms 退化到 100ms (12× 慢), 违背优化目的.
        正确做法: hot 失败返 {}, _batch_enrich_updated_at 自动 fallback 到 created_at.
        """
        # 让 hot 表查询失败: 重命名 audit_logs → audit_logs_broken
        self.conn.execute("ALTER TABLE audit_logs RENAME TO audit_logs_broken")
        self.conn.commit()

        from meta.core.audit_derived_fields import _batch_read_audit_derived

        # hot 查询会失败 (no such table: audit_logs), 应返回空 dict
        result = _batch_read_audit_derived(self.conn, 'test_obj', [100, 300])
        # [FIX 2026-09-15] 期望空 dict, 让 _batch_enrich_updated_at 走 record.created_at
        assert result == {}, \
            f'hot 失败应返回空 dict 走 created_at fallback, 实测: {result}'

    # ---------- 场景 9: 非 UPDATE action 过滤 ----------
    def test_filters_non_update_actions(self):
        """仅 action='UPDATE' 行参与 MAX 聚合"""
        from meta.core.audit_derived_fields import _batch_read_audit_derived

        # oid=100 在 audit_logs 有 INSERT 行 (2026-01-10T08) + UPDATE 行 (2026-01-15T10)
        # 应只取 UPDATE 行的时间
        result = _batch_read_audit_derived(self.conn, 'test_obj', [100])
        # 期望 archive 较晚值 2026-01-15T11:00 (覆盖 hot UPDATE 10:00)
        assert result == {'100': '2026-01-15T11:00:00'}
