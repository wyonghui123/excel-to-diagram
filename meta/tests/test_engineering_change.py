# -*- coding: utf-8 -*-
"""G4 工程 BOM 消费方：工程变更单（ECM）验收测试

覆盖 AC-G4-1 ~ AC-G4-11:
  1  工程 BOM 不参与生产展开
  2  diff 精确产出 add / modify / remove + ambiguous（不落表）
  3  add / modify / remove 应用到生产 BOM
  4  apply 显式事务失败回滚
  5  通用 BO 路径改 status 被拒（skip_generic_api / requires_state_machine）
  6  apply 时结构 revision 漂移拒绝
  7  同一目标结构已有 approved 变更时 apply 拒绝
  8  所有动作写审计（人 / 时间 / 前后状态）
  9  where-used 只读（受影响父项结构 + 在途工单）
 10  apply 幂等（重复调用不重复写）
 11  apply 不改 item_structures.revision；工程 / 生产展开按生效日切换

建库一律临时文件 SQLite + 真实 v200 迁移（不连生产库）。
运行: python D:\\filework\\test.py --file meta/tests/test_engineering_change.py
"""
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, timedelta

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import meta.api.engineering_change_api as ec_api  # noqa: E402
import meta.services.auth_middleware as auth_mw  # noqa: E402
from meta.core.task_state_machine import (  # noqa: E402
    TaskTransitionError,
    check_meta_object_status_update,
)
from meta.migrations import v200__engineering_change as v200  # noqa: E402
from meta.services.engineering_change_service import (  # noqa: E402
    EngineeringChangeError,
    EngineeringChangeService,
)
from meta.services.item_structure_explode_service import (  # noqa: E402
    ItemStructureExplodeService,
)

pytestmark = pytest.mark.unit

EFF = (date.today() + timedelta(days=5)).isoformat()
EFF_PREV = (date.today() + timedelta(days=4)).isoformat()

_SCHEMA = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    project_no TEXT,
    name TEXT
);
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    item_type TEXT,
    status TEXT
);
CREATE TABLE item_structures (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL,
    usage TEXT NOT NULL DEFAULT 'production',
    alternative_no INTEGER NOT NULL DEFAULT 1,
    revision TEXT NOT NULL,
    base_qty REAL NOT NULL DEFAULT 1,
    base_uom_id INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    created_at DATETIME,
    created_by TEXT,
    updated_at DATETIME,
    updated_by TEXT
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
    valid_from DATETIME,
    valid_to DATETIME,
    operation_seq INTEGER,
    phantom_flag INTEGER NOT NULL DEFAULT 0,
    substitute_group_code TEXT,
    included_in_base_price INTEGER NOT NULL DEFAULT 0,
    bom_price REAL,
    note TEXT,
    created_at DATETIME,
    created_by TEXT,
    updated_at DATETIME,
    updated_by TEXT
);
CREATE UNIQUE INDEX uidx_item_structure_line_no
    ON item_structure_lines (structure_id, line_no);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY,
    work_order_no TEXT,
    status TEXT,
    created_at DATETIME
);
CREATE TABLE work_order_components (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER NOT NULL,
    structure_line_id INTEGER,
    component_item_id INTEGER NOT NULL,
    line_no INTEGER,
    qty_per REAL,
    qty_required REAL
);
CREATE TABLE change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL,
    object_id INTEGER,
    event_type TEXT,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    status TEXT,
    created_at DATETIME
);
"""


class _DS:
    """最小数据源：query / execute / transaction（供服务直连 sqlite）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cursor = self.conn.execute(sql, params or [])
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])

    @contextmanager
    def transaction(self):
        try:
            yield self
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise


def _seed(conn):
    conn.executescript("""
        INSERT INTO projects (id, project_no, name) VALUES (10, 'P-10', '项目十');
        INSERT INTO items (id, code, name, item_type, status) VALUES
            (100, 'I-100', '整机', 'goods', 'active'),
            (200, 'I-200', '组件A', 'goods', 'active'),
            (201, 'I-201', '组件B', 'goods', 'active'),
            (202, 'I-202', '组件C', 'goods', 'active'),
            (203, 'I-203', '组件D', 'goods', 'active'),
            (300, 'I-300', '其它整机', 'goods', 'active');

        INSERT INTO item_structures
            (id, item_id, usage, alternative_no, revision, base_qty, base_uom_id,
             status, valid_from)
        VALUES
            (10, 100, 'engineering', 1, 'ENG-1', 1, 1, 'active', '2020-01-01'),
            (20, 100, 'production',  1, 'PROD-1', 1, 1, 'active', '2020-01-01'),
            (30, 300, 'production',  1, 'PROD-2', 1, 1, 'active', '2020-01-01'),
            (40, 300, 'engineering', 1, 'ENG-2', 1, 1, 'active', '2020-01-01');

        INSERT INTO item_structure_lines
            (id, structure_id, line_no, component_item_id, qty_per, operation_seq,
             valid_from)
        VALUES
            (1, 10, 1, 200, 2, 10, '2020-01-01'),
            (2, 10, 2, 201, 3, 20, '2020-01-01'),
            (3, 10, 3, 203, 1, 30, '2020-01-01'),
            (11, 20, 11, 200, 2, 10, '2020-01-01'),
            (12, 20, 12, 201, 1, 20, '2020-01-01'),
            (13, 20, 13, 202, 1, 40, '2020-01-01'),
            (21, 30, 21, 201, 4, 10, '2020-01-01'),
            (22, 40, 1, 200, 5, 10, '2020-01-01');

        INSERT INTO work_orders (id, work_order_no, status, created_at)
        VALUES (1000, 'WO-OPEN', 'In Progress', '2026-01-01'),
               (1001, 'WO-CLOSED', 'Closed', '2026-01-01');
        INSERT INTO work_order_components
            (id, work_order_id, structure_line_id, component_item_id, line_no,
             qty_per, qty_required)
        VALUES (1, 1000, 12, 201, 12, 1, 5),
               (2, 1001, 21, 200, 21, 4, 32);
    """)


def _build_db(tmp_path):
    path = tmp_path / 'meta.db'
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    _seed(conn)
    conn.commit()
    conn.close()
    assert v200.migrate(path), 'v200 迁移失败'
    return path, sqlite3.connect(str(path))


@pytest.fixture()
def db(tmp_path):
    path, conn = _build_db(tmp_path)
    yield conn, path
    conn.close()


@pytest.fixture()
def service(db):
    conn, _path = db
    return EngineeringChangeService(_DS(conn))


def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _diff_lines(diff):
    keys = ('line_type', 'target_structure_id', 'source_structure_id',
            'source_structure_line_id', 'structure_line_id',
            'component_item_id', 'match_key', 'old_qty_per', 'new_qty_per',
            'old_valid_to', 'new_valid_to')
    return [{k: row.get(k) for k in keys} for row in diff['rows']]


def _create(service, diff, **overrides):
    payload = dict(
        change_type='revise', title='G4 工程变更', reason='对账差异',
        effective_date=EFF, project_id=10,
        lines=_diff_lines(diff), actor='tester')
    payload.update(overrides)
    return service.create_change(**payload)


def _line_by_component(conn, structure_id, component_id):
    rows = _rows(conn,
                 'SELECT * FROM item_structure_lines '
                 'WHERE structure_id = ? AND component_item_id = ? '
                 'ORDER BY id', (structure_id, component_id))
    return rows[-1] if rows else None


# ======================================================================
# 迁移：幂等 / verify / rollback
# ======================================================================
_ADMIN_SCHEMA = """
CREATE TABLE projects (id INTEGER PRIMARY KEY, project_no TEXT, name TEXT);
CREATE TABLE items (id INTEGER PRIMARY KEY, item_no TEXT, name TEXT,
                    item_type TEXT, status TEXT);
CREATE TABLE enum_types (
    id VARCHAR(200) PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    mutability TEXT NOT NULL, dimension_schema TEXT, description TEXT,
    created_at DATETIME
);
CREATE TABLE enum_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT, enum_type_id TEXT NOT NULL,
    code TEXT NOT NULL, name TEXT NOT NULL, name_en TEXT, sort_order INTEGER,
    is_active INTEGER, is_system INTEGER, created_at DATETIME
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL, resource_type TEXT, action TEXT, description TEXT,
    resource_id INTEGER, scope TEXT
);
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
    name TEXT, is_active INTEGER DEFAULT 1
);
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, permission_set_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL, granted INTEGER DEFAULT 1,
    created_at DATETIME
);
CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT, menu_code TEXT UNIQUE NOT NULL,
    menu_name TEXT NOT NULL, menu_path TEXT, page_type TEXT,
    object_types TEXT, primary_object_type TEXT, bo_bindings TEXT,
    required_permissions TEXT, required_any_permission INTEGER,
    data_permission_hint TEXT, page_config TEXT, parent_menu TEXT, icon TEXT,
    color TEXT, description TEXT, sort_order INTEGER, is_active INTEGER,
    show_in_sidebar INTEGER, auto_generated INTEGER
);
CREATE TABLE menu_permissions (
    menu_code TEXT UNIQUE NOT NULL, menu_name TEXT NOT NULL, menu_path TEXT,
    required_permissions TEXT, required_any_permission INTEGER,
    parent_menu TEXT, icon TEXT, sort_order INTEGER, is_active INTEGER,
    data_permission_hint TEXT, created_at DATETIME, updated_at DATETIME
);
"""


class TestMigration:

    def test_enum_permission_menu_seeds(self, tmp_path):
        path = tmp_path / 'admin.db'
        conn = sqlite3.connect(str(path))
        conn.executescript(_ADMIN_SCHEMA)
        conn.executescript("""
            INSERT INTO permission_sets (id, code, name, is_active)
            VALUES (1, 'admin', '管理员', 1), (2, 'default', '默认', 1);
            INSERT INTO menus (menu_code, menu_name, menu_path, page_type,
                               is_active, show_in_sidebar, auto_generated)
            VALUES ('master-data', '主数据', '/master-data', 'object_list', 1, 1, 0);
        """)
        conn.commit()
        conn.close()

        assert v200.migrate(path) is True
        assert v200.verify(path) is True

        conn = sqlite3.connect(str(path))
        rows = conn.execute(
            "SELECT code FROM permissions WHERE resource_type = "
            "'engineering_change' ORDER BY code").fetchall()
        assert [r[0] for r in rows] == [
            'engineering_change:engineering_change_apply',
            'engineering_change:engineering_change_approve',
            'engineering_change:engineering_change_create',
            'engineering_change:engineering_change_view']
        assert conn.execute(
            "SELECT COUNT(*) FROM enum_values WHERE enum_type_id = "
            "'engineering_change_status'").fetchone()[0] == 6
        menu = conn.execute(
            "SELECT parent_menu, sort_order FROM menus WHERE menu_code = "
            "'engineering-change'").fetchone()
        assert menu == ('master-data', 105)
        assert conn.execute(
            "SELECT COUNT(*) FROM menu_permissions WHERE menu_code = "
            "'engineering-change'").fetchone()[0] == 1
        conn.close()

    def test_migrate_verify_idempotent_rollback(self, tmp_path):
        path = tmp_path / 'bare.db'
        conn = sqlite3.connect(str(path))
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()

        assert v200.migrate(path) is True
        assert v200.migrate(path) is True  # 幂等
        assert v200.verify(path) is True

        assert v200.rollback(path) is True
        conn = sqlite3.connect(str(path))
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='engineering_changes'").fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='engineering_change_lines'").fetchone() is None
        conn.close()


# ======================================================================
# AC-G4-2 diff
# ======================================================================
class TestDiff:

    def test_diff_add_modify_remove(self, service, db):
        conn, _path = db
        result = service.diff_structures(10, 20)
        rows = {row['component_item_id']: row for row in result['rows']}

        assert result['ambiguous'] == []
        assert result['summary'] == {'add': 1, 'modify': 1, 'remove': 1}
        assert 200 not in rows  # 未变化不产出

        modify = rows[201]
        assert modify['line_type'] == 'modify'
        assert modify['source_structure_line_id'] == 2
        assert modify['structure_line_id'] == 12
        assert modify['old_qty_per'] == 1
        assert modify['new_qty_per'] == 3
        assert modify['match_key'] == '201||20'

        add = rows[203]
        assert add['line_type'] == 'add'
        assert add['structure_line_id'] is None
        assert add['source_structure_line_id'] == 3

        remove = rows[202]
        assert remove['line_type'] == 'remove'
        assert remove['source_structure_line_id'] is None
        assert remove['structure_line_id'] == 13

        # 只读：diff 不落表
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM engineering_changes')[0]['n'] == 0
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM engineering_change_lines'
                          )[0]['n'] == 0

    def test_diff_ambiguous_when_same_key_multi_rows(self, service, db):
        conn, _path = db
        conn.execute(
            'INSERT INTO item_structure_lines '
            '(structure_id, line_no, component_item_id, qty_per, operation_seq, '
            'valid_from) VALUES (10, 99, 201, 9, 20, ?)', ('2020-01-01',))
        conn.commit()

        result = service.diff_structures(10, 20)
        keys = [row['match_key'] for row in result['ambiguous']]
        assert '201||20' in keys
        assert all(row['component_item_id'] != 201 for row in result['rows'])
        # 其它键仍正常产出
        assert {r['line_type'] for r in result['rows']} == {'add', 'remove'}

    def test_list_returns_item_and_project_names(self, service, db):
        change = _create(service, service.diff_structures(10, 20))
        result = service.list_changes(status='draft')

        assert result['total'] == 1
        row = result['items'][0]
        assert row['id'] == change['id']
        assert row['item_no'] == 'I-100'
        assert row['item_name'] == '整机'
        assert row['project_no'] == 'P-10'
        assert row['project_name'] == '项目十'
        assert row['line_count'] == 3

    def test_list_without_project_keeps_names_null(self, service, db):
        change = _create(service, service.diff_structures(10, 20), project_id=None)

        row = next(r for r in service.list_changes()['items']
                   if r['id'] == change['id'])
        assert row['project_id'] is None
        assert row['project_no'] is None
        assert row['project_name'] is None


# ======================================================================
# AC-G4-3 / 4 / 6 / 7 / 8 / 10 / 11 apply 全链路
# ======================================================================
class TestApply:

    def test_create_requires_single_target_structure(self, service, db):
        conn, _path = db
        diff = service.diff_structures(10, 20)
        lines = _diff_lines(diff)
        # 明细 0 = add(203)：目标切到结构 30，来源切到结构 40（同物料 300）以隔离 P1 校验
        lines[0].update({'target_structure_id': 30, 'source_structure_id': 40,
                         'source_structure_line_id': 22})
        with pytest.raises(EngineeringChangeError) as exc:
            service.create_change(change_type='revise', title='跨结构',
                                  reason='x', effective_date=EFF,
                                  lines=lines, actor='tester')
        assert exc.value.rule == 'EC_TARGET_STRUCTURE_MISMATCH'

        # 来源结构与目标结构物料不一致
        lines = _diff_lines(diff)
        lines[0].update({'source_structure_id': 40,
                         'source_structure_line_id': 22})
        with pytest.raises(EngineeringChangeError) as exc:
            service.create_change(change_type='revise', title='物料不一致',
                                  reason='x', effective_date=EFF,
                                  lines=lines, actor='tester')
        assert exc.value.rule == 'EC_STRUCTURE_ITEM_MISMATCH'

    def test_revision_drift_rejected_on_apply(self, service, db):
        conn, _path = db
        change = _create(service, service.diff_structures(10, 20))
        service.submit(change['id'], actor='tester')
        service.approve(change['id'], actor='manager')

        conn.execute("UPDATE item_structures SET revision = 'PROD-1X' WHERE id = 20")
        conn.commit()
        with pytest.raises(EngineeringChangeError) as exc:
            service.apply(change['id'], actor='manager')
        assert exc.value.rule == 'EC_REVISION_DRIFT'
        # 失败不写任何结构行 / 不迁移状态
        assert _rows(conn, 'SELECT status FROM engineering_changes WHERE id = ?',
                     (change['id'],))[0]['status'] == 'approved'
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM item_structure_lines '
                          'WHERE structure_id = 20')[0]['n'] == 3

    def test_competing_approved_change_rejected(self, service, db):
        conn, _path = db
        diff = service.diff_structures(10, 20)
        first = _create(service, diff)
        service.submit(first['id'], actor='tester')
        service.approve(first['id'], actor='manager')

        second = _create(service, diff)
        service.submit(second['id'], actor='tester')
        service.approve(second['id'], actor='manager')

        with pytest.raises(EngineeringChangeError) as exc:
            service.apply(first['id'], actor='manager')
        assert exc.value.rule == 'EC_CONFLICT_APPROVED'

        service.cancel(second['id'], actor='manager', reason='让位')
        applied = service.apply(first['id'], actor='manager')
        assert applied['status'] == 'applied'

    def test_apply_add_modify_remove_and_idempotent(self, service, db):
        conn, _path = db
        # 结构 revision 快照（AC-G4-11）
        before_struct = _rows(conn, 'SELECT id, revision FROM item_structures '
                                    'WHERE id IN (10, 20) ORDER BY id')
        before_wo = _rows(conn, 'SELECT id, status, work_order_no FROM work_orders '
                                'ORDER BY id')
        before_woc = _rows(conn, 'SELECT * FROM work_order_components ORDER BY id')

        diff = service.diff_structures(10, 20)
        change = _create(service, diff)
        assert change['status'] == 'draft'
        assert change['change_no'].startswith('EC-')
        assert len(change['lines']) == 3

        service.submit(change['id'], actor='tester')
        service.approve(change['id'], actor='manager', comment='OK')
        result = service.apply(change['id'], actor='manager')
        assert result['status'] == 'applied'
        assert result['applied_lines'] == 3
        assert result['already_applied'] is False

        # modify：关旧（生效日前一天）+ 从来源工程行复制插新（生效日）
        old_modify = _rows(conn, 'SELECT * FROM item_structure_lines WHERE id = 12')[0]
        assert old_modify['valid_to'] == EFF_PREV
        new_modify = _line_by_component(conn, 20, 201)
        assert new_modify['valid_from'] == EFF
        assert new_modify['qty_per'] == 3
        assert new_modify['line_no'] > 13  # (structure_id, line_no) 唯一，新行另取行号

        # remove：只关旧，不删除历史
        old_remove = _rows(conn, 'SELECT * FROM item_structure_lines WHERE id = 13')[0]
        assert old_remove['valid_to'] == EFF_PREV

        # add：复制来源工程行，valid_from = 生效日
        added = _line_by_component(conn, 20, 203)
        assert added['valid_from'] == EFF
        assert added['qty_per'] == 1
        assert added['line_no'] > 13

        # AC-G4-11：不改 revision / 不新建结构版本
        after_struct = _rows(conn, 'SELECT id, revision FROM item_structures '
                                   'WHERE id IN (10, 20) ORDER BY id')
        assert before_struct == after_struct
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM item_structures')[0]['n'] == 4

        # AC-G4-3：工程 / 生产展开按生效日切换
        explode = ItemStructureExplodeService(_DS(conn))
        before = explode.explode_structure(20, as_of=EFF_PREV)
        after = explode.explode_structure(20, as_of=EFF)
        before_rows = {r['component_item_id']: r for r in before['lines']}
        after_rows = {r['component_item_id']: r for r in after['lines']}
        assert before_rows[201]['total_qty'] == 1
        assert before_rows[202]['total_qty'] == 1
        assert 203 not in before_rows
        assert after_rows[201]['total_qty'] == 3
        assert 202 not in after_rows
        assert after_rows[203]['total_qty'] == 1

        # AC-G4-10：幂等
        count_before = _rows(conn, 'SELECT COUNT(*) AS n FROM item_structure_lines '
                                   'WHERE structure_id = 20')[0]['n']
        audit_before = _rows(conn, 'SELECT COUNT(*) AS n FROM change_events '
                                   'WHERE object_type = ?', ('engineering_change',)
                             )[0]['n']
        again = service.apply(change['id'], actor='manager')
        assert again['already_applied'] is True
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM item_structure_lines '
                          'WHERE structure_id = 20')[0]['n'] == count_before
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM change_events '
                          'WHERE object_type = ?', ('engineering_change',)
                    )[0]['n'] == audit_before
        # applied 后不能重新提交
        with pytest.raises(EngineeringChangeError) as exc:
            service.submit(change['id'], actor='tester')
        assert exc.value.rule == 'EC_STATE_INVALID'

        # AC-G4-3：工单侧完全不动
        assert _rows(conn, 'SELECT id, status, work_order_no FROM work_orders '
                          'ORDER BY id') == before_wo
        assert _rows(conn, 'SELECT * FROM work_order_components ORDER BY id'
                    ) == before_woc

        # AC-G4-8：审计（人 / 时间 / 前后状态）
        events = _rows(conn, 'SELECT * FROM change_events WHERE object_type = ? '
                             'ORDER BY id', ('engineering_change',))
        actions = [json.loads(e['payload'])['action'] for e in events]
        assert actions == ['create', 'submit', 'approve', 'apply']
        payloads = [json.loads(e['payload']) for e in events]
        assert all(p['actor'] in ('tester', 'manager') for p in payloads)
        assert (payloads[0]['old_status'], payloads[0]['new_status']) == (None, 'draft')
        assert (payloads[-1]['old_status'], payloads[-1]['new_status']) == (
            'approved', 'applied')
        assert all(e['created_at'] for e in events)

    def test_apply_transaction_rolls_back_midway(self, service, db, monkeypatch):
        conn, _path = db
        change = _create(service, service.diff_structures(10, 20))
        service.submit(change['id'], actor='tester')
        service.approve(change['id'], actor='manager')

        original = service._insert_copied_line
        calls = {'n': 0}

        def boom(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('injected failure')
            return original(*args, **kwargs)

        monkeypatch.setattr(service, '_insert_copied_line', boom)
        with pytest.raises(RuntimeError):
            service.apply(change['id'], actor='manager')

        # 第一笔（add）插入必须回滚；旧行未被关闭；头仍 approved
        assert _rows(conn, 'SELECT status FROM engineering_changes WHERE id = ?',
                     (change['id'],))[0]['status'] == 'approved'
        assert _rows(conn, 'SELECT COUNT(*) AS n FROM item_structure_lines '
                          'WHERE structure_id = 20')[0]['n'] == 3
        assert _rows(conn, 'SELECT valid_to FROM item_structure_lines WHERE id = 12'
                     )[0]['valid_to'] is None


# ======================================================================
# AC-G4-1 / 5 框架边界
# ======================================================================
class TestFrameworkGuards:

    def test_engineering_usage_not_exploded(self, db):
        conn, _path = db
        result = ItemStructureExplodeService(_DS(conn)).explode_item(
            100, usage='engineering', as_of=EFF)
        assert result['structure_id'] is None
        assert result['lines'] == []
        assert result['warnings'][0]['rule'] == 'item_structure_usage_not_enabled'

    def test_yaml_declares_generic_bypass_and_state_machine(self):
        schemas = os.path.join(ROOT, 'meta', 'schemas')
        header = yaml.safe_load(open(os.path.join(schemas,
                                                  'engineering_change.yaml'),
                                     encoding='utf-8'))
        line = yaml.safe_load(open(os.path.join(schemas,
                                                'engineering_change_line.yaml'),
                                   encoding='utf-8'))
        assert header['skip_generic_api'] is True
        assert header['requires_state_machine'] is True
        assert line['skip_generic_api'] is True

        # 真实 loader 注册（aspects / shared 解析）不能报错，且开关落到 MetaObject
        from meta.core.yaml_loader import (
            load_yaml_file, parse_aspects_yaml, parse_shared_properties)
        shared = parse_shared_properties(schemas)
        aspects = parse_aspects_yaml(schemas)
        header_obj = load_yaml_file(
            os.path.join(schemas, 'engineering_change.yaml'), shared, aspects)
        line_obj = load_yaml_file(
            os.path.join(schemas, 'engineering_change_line.yaml'), shared, aspects)
        assert header_obj is not None and header_obj.id == 'engineering_change'
        assert header_obj.skip_generic_api is True
        assert line_obj is not None and line_obj.id == 'engineering_change_line'
        assert line_obj.skip_generic_api is True

        assert {r['id'] for r in header['rules']} == {
            'submit_engineering_change', 'approve_engineering_change',
            'reject_engineering_change', 'cancel_engineering_change',
            'apply_engineering_change'}

        # 通用更新路径：draft → approved 不在本对象允许的迁移中，必须被拒
        assert header_obj.requires_state_machine() is True
        with pytest.raises(TaskTransitionError):
            check_meta_object_status_update(
                header_obj, {'status': 'draft'}, {'status': 'approved'})


# ======================================================================
# AC-G4-9 where-used 只读
# ======================================================================
class TestWhereUsed:

    def _snapshot(self, conn):
        tables = ('engineering_changes', 'engineering_change_lines',
                  'item_structures', 'item_structure_lines', 'work_orders',
                  'work_order_components', 'change_events')
        return {t: _rows(conn, 'SELECT * FROM %s ORDER BY id' % t)
                for t in tables}

    def test_where_used_structures_work_orders_and_read_only(self, service, db):
        conn, _path = db
        change = _create(service, service.diff_structures(10, 20))
        before = self._snapshot(conn)

        result = service.where_used(change['id'])

        assert result['read_only'] is True
        # 只有发生变更的组件才算受影响（未变化的组件 200 不在变更明细中）
        assert result['affected_component_item_ids'] == [201, 202, 203]
        parent_ids = [row['structure_id'] for row in result['parent_structures']]
        assert parent_ids == [30]  # 目标 20 / 来源 10 自身不计为受影响父项
        assert [w['work_order_no'] for w in result['work_orders']] == ['WO-OPEN']
        assert result['work_orders'][0]['components'][0]['component_item_id'] == 201

        after = self._snapshot(conn)
        assert before == after  # 不得写任何表

    def test_where_used_unknown_change_404_rule(self, service):
        with pytest.raises(EngineeringChangeError) as exc:
            service.where_used(99999)
        assert exc.value.rule == 'EC_NOT_FOUND'


# ======================================================================
# API 冒烟：统一响应 + 权限装饰器 + 路由注册
# ======================================================================
class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {'user_id': '1', 'username': 'admin', 'token_version': 0,
                'permissions': ['*']}


AUTH = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'}


@pytest.fixture()
def api_client(monkeypatch, db):
    from flask import Flask
    conn, _path = db
    ec_api.init_service(_DS(conn))
    monkeypatch.setattr(auth_mw, 'token_blacklist_service', _FakeBlacklist())
    monkeypatch.setattr(auth_mw, 'TokenService', _FakeTokenService)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(ec_api.engineering_change_bp)
    yield app.test_client(), conn
    ec_api._service = None


class TestApi:

    def test_full_route_smoke(self, api_client):
        client, conn = api_client

        diff = client.post('/api/v1/engineering-changes/diff',
                           json={'source_structure_id': 10,
                                 'target_structure_id': 20}, headers=AUTH)
        assert diff.status_code == 200
        diff_body = diff.get_json()
        assert diff_body['success'] is True
        assert diff_body['data']['summary'] == {'add': 1, 'modify': 1,
                                                'remove': 1}

        create = client.post('/api/v1/engineering-changes', json={
            'change_type': 'revise', 'title': 'API 建模', 'reason': 'r',
            'effective_date': EFF, 'project_id': 10,
            'lines': _diff_lines(diff_body['data']),
        }, headers=AUTH)
        assert create.status_code == 200
        created = create.get_json()['data']
        change_id = created['id']
        assert created['status'] == 'draft'

        listed = client.get('/api/v1/engineering-changes', headers=AUTH)
        assert listed.status_code == 200
        assert listed.get_json()['data']['total'] == 1

        detail = client.get('/api/v1/engineering-changes/%s' % change_id,
                            headers=AUTH)
        assert detail.status_code == 200
        assert len(detail.get_json()['data']['lines']) == 3

        for action in ('submit', 'approve', 'apply'):
            resp = client.post('/api/v1/engineering-changes/%s/%s'
                               % (change_id, action), json={}, headers=AUTH)
            assert resp.status_code == 200, action
        assert resp.get_json()['data']['status'] == 'applied'

        where_used = client.get(
            '/api/v1/engineering-changes/%s/where-used' % change_id,
            headers=AUTH)
        assert where_used.status_code == 200
        assert where_used.get_json()['data']['read_only'] is True

    def test_reject_requires_reason(self, api_client):
        client, _conn = api_client
        diff = client.post('/api/v1/engineering-changes/diff',
                           json={'source_structure_id': 10,
                                 'target_structure_id': 20}, headers=AUTH)
        created = client.post('/api/v1/engineering-changes', json={
            'change_type': 'revise', 'title': '驳回', 'reason': 'r',
            'effective_date': EFF, 'lines': _diff_lines(diff.get_json()['data']),
        }, headers=AUTH).get_json()['data']
        client.post('/api/v1/engineering-changes/%s/submit' % created['id'],
                    json={}, headers=AUTH)

        resp = client.post('/api/v1/engineering-changes/%s/reject' % created['id'],
                           json={}, headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'EC_REJECT_REASON_REQUIRED'

    def test_not_found_maps_404(self, api_client):
        client, _conn = api_client
        resp = client.get('/api/v1/engineering-changes/99999', headers=AUTH)
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'EC_NOT_FOUND'
