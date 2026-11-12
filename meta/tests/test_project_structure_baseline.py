# -*- coding: utf-8 -*-
"""项目结构基线（G15 ETO P2-2）：哈希稳定性 / 漂移 / 守卫 / 迁移幂等。

自建最小 schema（projects / item_structures / item_structure_lines / 本表），
不依赖真实 meta/architecture.db。
"""

import os
import sqlite3

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.migrations import v209__project_structure_baseline as v209
from meta.services.project_structure_baseline_service import (
    ProjectStructureBaselineError,
    ProjectStructureBaselineService,
)

ITEM_ID = 100
OTHER_ITEM_ID = 101
UOM_ID = 3
PROJECT_ID = 1

SCHEMA = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT,
    design_mode TEXT NOT NULL DEFAULT 'standard'
);
CREATE TABLE item_structures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    usage TEXT NOT NULL DEFAULT 'production',
    alternative_no INTEGER NOT NULL DEFAULT 1,
    revision TEXT NOT NULL,
    base_qty REAL NOT NULL DEFAULT 1,
    base_uom_id INTEGER NOT NULL,
    min_select INTEGER,
    max_select INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    description TEXT
);
CREATE TABLE item_structure_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,
    qty_per REAL,
    fixed_qty REAL,
    scrap_rate REAL NOT NULL DEFAULT 0,
    optional_flag INTEGER NOT NULL DEFAULT 0,
    default_flag INTEGER NOT NULL DEFAULT 0,
    default_qty REAL,
    min_qty REAL,
    max_qty REAL,
    valid_from TEXT,
    valid_to TEXT,
    operation_seq INTEGER,
    phantom_flag INTEGER NOT NULL DEFAULT 0,
    substitute_group_code TEXT,
    included_in_base_price INTEGER NOT NULL DEFAULT 0,
    bom_price REAL,
    note TEXT
);
CREATE TABLE project_structure_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    usage TEXT NOT NULL DEFAULT 'production',
    alternative_no INTEGER NOT NULL DEFAULT 1,
    structure_id INTEGER NOT NULL DEFAULT 0,
    baseline_hash TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    note TEXT
);
CREATE UNIQUE INDEX uq_project_structure_baseline
    ON project_structure_baselines(project_id, item_id, usage, alternative_no);
CREATE INDEX idx_project_structure_baseline_item
    ON project_structure_baselines(item_id);
"""


class MemDS:
    """sqlite3 连接 → DataSource 形状（与库存测试替身同口径）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))

    def commit(self):
        self.conn.commit()


def _build_db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO projects (id, name, design_mode) VALUES (?, '标准项目', "
        "'standard')", [PROJECT_ID])
    conn.commit()
    return conn


def _service(conn):
    return ProjectStructureBaselineService(MemDS(conn))


def _add_structure(conn, item_id=ITEM_ID, usage='production', alternative_no=1,
                   revision='A', base_qty=1, base_uom_id=UOM_ID,
                   status='active', valid_from='2026-01-01', valid_to=None):
    cur = conn.execute(
        'INSERT INTO item_structures (item_id, usage, alternative_no, revision, '
        'base_qty, base_uom_id, status, valid_from, valid_to) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [item_id, usage, alternative_no, revision, base_qty, base_uom_id,
         status, valid_from, valid_to])
    conn.commit()
    return cur.lastrowid


def _add_line(conn, structure_id, line_no, component_item_id, qty_per=None,
              fixed_qty=None, scrap_rate=0, optional_flag=0, default_flag=0,
              default_qty=None, min_qty=None, max_qty=None, operation_seq=None,
              phantom_flag=0, substitute_group_code=None):
    cur = conn.execute(
        'INSERT INTO item_structure_lines (structure_id, line_no, '
        'component_item_id, qty_per, fixed_qty, scrap_rate, optional_flag, '
        'default_flag, default_qty, min_qty, max_qty, operation_seq, '
        'phantom_flag, substitute_group_code) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [structure_id, line_no, component_item_id, qty_per, fixed_qty,
         scrap_rate, optional_flag, default_flag, default_qty, min_qty,
         max_qty, operation_seq, phantom_flag, substitute_group_code])
    conn.commit()
    return cur.lastrowid


BASE_LINES = [
    {'line_no': 1, 'component_item_id': 200, 'qty_per': 2, 'fixed_qty': None,
     'scrap_rate': 0, 'optional_flag': False, 'default_flag': False,
     'default_qty': None, 'min_qty': None, 'max_qty': None,
     'operation_seq': 10, 'phantom_flag': False,
     'substitute_group_code': None},
    {'line_no': 2, 'component_item_id': 201, 'qty_per': 1, 'fixed_qty': 3,
     'scrap_rate': 0, 'optional_flag': True, 'default_flag': True,
     'default_qty': 1, 'min_qty': 1, 'max_qty': 5,
     'operation_seq': 20, 'phantom_flag': True,
     'substitute_group_code': 'G1'},
]


def _hash_of(lines, **header):
    structure = {'revision': 'A', 'base_qty': 1, 'base_uom_id': UOM_ID}
    structure.update(header)
    structure['lines'] = lines
    return _service(sqlite3.connect(':memory:')).compute_hash(structure)


# ─────────────────────────────────────────────────────────────────────────────
# 哈希稳定性
# ─────────────────────────────────────────────────────────────────────────────

def test_hash_is_independent_of_line_order():
    forward = _hash_of(BASE_LINES)
    reverse = _hash_of(list(reversed(BASE_LINES)))
    assert forward == reverse


def test_hash_normalizes_decimal_trailing_zeros():
    one = list(BASE_LINES)
    one[0] = dict(one[0], qty_per=1)
    two = list(BASE_LINES)
    two[0] = dict(two[0], qty_per=1.0, fixed_qty=None)
    assert _hash_of(one) == _hash_of(two)

    decimal_text = list(BASE_LINES)
    decimal_text[0] = dict(decimal_text[0], qty_per='1.500')
    plain = list(BASE_LINES)
    plain[0] = dict(plain[0], qty_per=1.5)
    assert _hash_of(decimal_text) == _hash_of(plain)


def test_hash_normalizes_boolean_as_one_zero():
    as_bool = list(BASE_LINES)
    as_bool[1] = dict(as_bool[1], optional_flag=True, default_flag=True)
    as_int = list(BASE_LINES)
    as_int[1] = dict(as_int[1], optional_flag=1, default_flag='true')
    assert _hash_of(as_bool) == _hash_of(as_int)

    assert _hash_of(BASE_LINES) != _hash_of(
        [dict(BASE_LINES[0], optional_flag=True)] + BASE_LINES[1:])


def test_hash_ignores_line_id_and_timestamps():
    lines_a = list(BASE_LINES)
    lines_b = [dict(line, id=9001, created_at='2026-11-04 10:00:00')
               for line in BASE_LINES]
    assert _hash_of(lines_a) == _hash_of(lines_b)


def test_hash_changes_when_header_changes():
    assert _hash_of(BASE_LINES, revision='B') != _hash_of(BASE_LINES)
    assert _hash_of(BASE_LINES, base_qty=2) != _hash_of(BASE_LINES)
    assert _hash_of(BASE_LINES, base_uom_id=4) != _hash_of(BASE_LINES)


# ─────────────────────────────────────────────────────────────────────────────
# 漂移 / 缺失
# ─────────────────────────────────────────────────────────────────────────────

def test_active_version_switch_reports_drift():
    conn = _build_db()
    old = _add_structure(conn, revision='A', valid_from='2026-01-01')
    _add_line(conn, old, 1, 200, qty_per=1)
    service = _service(conn)

    baseline = service.create_or_update({
        'project_id': PROJECT_ID, 'item_id': ITEM_ID,
        'structure_id': 0, 'as_of': '2026-11-04',
    })
    assert service.check_drift(baseline['id'], as_of='2026-11-04')['status'] \
        == 'OK'

    conn.execute("UPDATE item_structures SET status='inactive', "
                 "valid_to='2026-10-31' WHERE id=?", [old])
    new = _add_structure(conn, revision='B',
                         valid_from='2026-11-01')
    _add_line(conn, new, 1, 201, qty_per=2)

    result = service.check_drift(baseline['id'], as_of='2026-11-04')
    assert result['status'] == 'DRIFT'
    assert result['structure_id'] == new


def test_pinned_structure_content_change_reports_drift():
    conn = _build_db()
    pinned = _add_structure(conn, revision='A')
    _add_line(conn, pinned, 1, 200, qty_per=1)
    service = _service(conn)

    baseline = service.create_or_update({
        'project_id': PROJECT_ID, 'item_id': ITEM_ID,
        'structure_id': pinned,
    })
    assert service.check_drift(baseline['id'])['status'] == 'OK'

    conn.execute('UPDATE item_structure_lines SET qty_per = 2 '
                 'WHERE structure_id = ?', [pinned])
    conn.commit()
    assert service.check_drift(baseline['id'])['status'] == 'DRIFT'


def test_structure_missing():
    conn = _build_db()
    pinned = _add_structure(conn, revision='A')
    _add_line(conn, pinned, 1, 200, qty_per=1)
    service = _service(conn)

    baseline = service.create_or_update({
        'project_id': PROJECT_ID, 'item_id': ITEM_ID,
        'structure_id': pinned,
    })
    conn.execute('DELETE FROM item_structure_lines WHERE structure_id = ?',
                 [pinned])
    conn.execute('DELETE FROM item_structures WHERE id = ?', [pinned])
    conn.commit()

    result = service.check_drift(baseline['id'])
    assert result['status'] == 'STRUCTURE_MISSING'
    assert result['current_hash'] is None


# ─────────────────────────────────────────────────────────────────────────────
# 守卫
# ─────────────────────────────────────────────────────────────────────────────

def test_structure_id_must_belong_to_same_key():
    conn = _build_db()
    other = _add_structure(conn, item_id=OTHER_ITEM_ID, revision='A')
    _add_line(conn, other, 1, 200, qty_per=1)

    with pytest.raises(ProjectStructureBaselineError) as exc:
        _service(conn).create_or_update({
            'project_id': PROJECT_ID, 'item_id': ITEM_ID,
            'structure_id': other,
        })
    assert exc.value.code == 'BASELINE_STRUCTURE_MISMATCH'
    assert exc.value.http_status == 400


def test_unknown_structure_id_is_rejected():
    conn = _build_db()
    with pytest.raises(ProjectStructureBaselineError) as exc:
        _service(conn).create_or_update({
            'project_id': PROJECT_ID, 'item_id': ITEM_ID,
            'structure_id': 9999,
        })
    assert exc.value.code == 'BASELINE_STRUCTURE_MISMATCH'
    assert exc.value.http_status == 400


def test_engineered_project_is_rejected():
    conn = _build_db()
    conn.execute("UPDATE projects SET design_mode='engineered' WHERE id=?",
                 [PROJECT_ID])
    conn.commit()
    structure = _add_structure(conn, revision='A')
    _add_line(conn, structure, 1, 200, qty_per=1)

    with pytest.raises(ProjectStructureBaselineError) as exc:
        _service(conn).create_or_update({
            'project_id': PROJECT_ID, 'item_id': ITEM_ID,
            'structure_id': structure,
        })
    assert exc.value.code == 'BASELINE_DESIGN_MODE_INVALID'
    assert exc.value.http_status == 400


def test_missing_active_structure_is_rejected():
    conn = _build_db()
    with pytest.raises(ProjectStructureBaselineError) as exc:
        _service(conn).create_or_update({
            'project_id': PROJECT_ID, 'item_id': ITEM_ID, 'structure_id': 0,
            'as_of': '2026-11-04',
        })
    assert exc.value.code == 'BASELINE_STRUCTURE_MISSING'
    assert exc.value.http_status == 400


def test_same_key_upserts_single_row():
    conn = _build_db()
    structure = _add_structure(conn, revision='A')
    _add_line(conn, structure, 1, 200, qty_per=1)
    service = _service(conn)

    first = service.create_or_update({
        'project_id': PROJECT_ID, 'item_id': ITEM_ID,
        'structure_id': structure, 'note': '首次采集'})
    second = service.create_or_update({
        'project_id': PROJECT_ID, 'item_id': ITEM_ID,
        'structure_id': structure, 'note': '重复采集'})

    assert first['id'] == second['id']
    count = conn.execute(
        'SELECT COUNT(*) FROM project_structure_baselines').fetchone()[0]
    assert count == 1
    assert second['note'] == '重复采集'


# ─────────────────────────────────────────────────────────────────────────────
# 刷新
# ─────────────────────────────────────────────────────────────────────────────

def test_refresh_moves_drift_back_to_ok():
    conn = _build_db()
    pinned = _add_structure(conn, revision='A')
    _add_line(conn, pinned, 1, 200, qty_per=1)
    service = _service(conn)

    baseline = service.create_or_update({
        'project_id': PROJECT_ID, 'item_id': ITEM_ID,
        'structure_id': pinned,
    })
    conn.execute('UPDATE item_structure_lines SET qty_per = 2 '
                 'WHERE structure_id = ?', [pinned])
    conn.commit()
    assert service.check_drift(baseline['id'])['status'] == 'DRIFT'

    refreshed = service.refresh(baseline['id'], note='已接受结构变更')
    assert refreshed['baseline_hash'] != baseline['baseline_hash']
    assert refreshed['note'] == '已接受结构变更'
    assert service.check_drift(baseline['id'])['status'] == 'OK'


# ─────────────────────────────────────────────────────────────────────────────
# 迁移幂等 + verify
# ─────────────────────────────────────────────────────────────────────────────

def test_migration_is_idempotent_and_verifies(tmp_path):
    db_path = tmp_path / 'baseline.db'
    sqlite3.connect(str(db_path)).close()

    assert v209.migrate(db_path, skip_backup=True) is True
    assert v209.migrate(db_path, skip_backup=True) is True
    assert v209.verify(db_path) is True

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='project_structure_baselines'").fetchone() is not None
        index_names = {row[1] for row in conn.execute(
            'PRAGMA index_list(project_structure_baselines)').fetchall()}
        assert {'uq_project_structure_baseline',
                'idx_project_structure_baseline_item'} <= index_names
    finally:
        conn.close()
