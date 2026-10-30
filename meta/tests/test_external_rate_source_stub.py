# -*- coding: utf-8 -*-
"""外部价源取数接口桩测试（SO Wave3 C1/M3）

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §4 D9 / §10.11

测试策略:
  · 内存 SQLite 真表（列齐全，与 YAML 字段一一对应）+ 包一层 DataSource 形状
  · 种子行走 factories/_raw_sql_bridge（不在测试文件内联 DML）
"""

import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.services.external_rate_source_stub import (
    ADAPTERS,
    EXTERNAL_SOURCE_UNSUPPORTED,
    ExternalRateSourceError,
    ManualOverrideAdapter,
    get_adapter,
)
from meta.tests.factories._raw_sql_bridge import insert

_TABLE = 'external_rate_sources'

_SCHEMA = """
CREATE TABLE external_rate_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    source TEXT,
    quote_code TEXT,
    calendar_id INTEGER,
    fallback_rule TEXT,
    override_rate REAL,
    override_valid_from TEXT,
    override_valid_to TEXT,
    override_reason TEXT
);
"""


class _MemDS:
    """sqlite3 连接 → DataSource 形状（桩只用到 query）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


def _db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(_SCHEMA)
    return conn


def _add_source(conn, code='LME_COPPER', rate=None, valid_from=None,
                valid_to=None, reason=None):
    insert(conn, _TABLE, code=code, name=code, source='custom',
           quote_code=None, calendar_id=None, fallback_rule=None,
           override_rate=rate, override_valid_from=valid_from,
           override_valid_to=valid_to, override_reason=reason)


def _adapter(conn, source_code=None):
    return ManualOverrideAdapter(_MemDS(conn), source_code=source_code)


def test_manual_override_hit():
    conn = _db()
    _add_source(conn, rate=88.5, valid_from='2026-10-01',
                valid_to='2026-11-30', reason='占位期人工取价')
    quote = _adapter(conn).fetch_quote('LME_COPPER', 10, 'USD', '2026-10-30')
    assert quote is not None
    assert quote['rate'] == 88.5
    assert quote['on_date'] == '2026-10-30'
    assert quote['currency'] == 'USD'
    assert quote['source'] == 'LME_COPPER'


def test_manual_override_missing_returns_none():
    conn = _db()
    _add_source(conn, rate=None, valid_from='2026-10-01',
                valid_to='2026-11-30')
    assert _adapter(conn).fetch_quote('LME_COPPER', 10, 'USD', '2026-10-30') is None


def test_manual_override_out_of_window_returns_none():
    conn = _db()
    _add_source(conn, rate=88.5, valid_from='2026-10-01',
                valid_to='2026-11-30')
    adapter = _adapter(conn)
    # 失效日之后
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-12-01') is None
    # 生效日之前
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-09-15') is None
    # 边界日（首末日均包含）
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-10-01') is not None
    assert adapter.fetch_quote('LME_COPPER', 10, 'USD', '2026-11-30') is not None


def test_manual_override_no_row_returns_none():
    conn = _db()
    _add_source(conn, code='LME_COPPER', rate=88.5)
    assert _adapter(conn).fetch_quote('PLATTS_ALUMINA', 10, 'USD', '2026-10-30') is None


def test_unknown_adapter_rejected():
    with pytest.raises(ExternalRateSourceError) as exc:
        get_adapter('platts')
    assert exc.value.code == EXTERNAL_SOURCE_UNSUPPORTED
    # 手工覆盖是本期唯一注册的适配器
    assert list(ADAPTERS) == ['manual_override']
