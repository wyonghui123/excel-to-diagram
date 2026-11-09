# ALLOW_RAW_SQL: 直接建 menus / menu_permissions / permissions 缩微表并断言迁移副作用
"""P6a-2 §11.14 D4：handling-unit-list → multi_object_hub 的元数据契约测试。

覆盖：
  1. `handling_unit.yaml` 的 hub 声明与前端 hubOptions 契约一致（左树 + 三 tab +
     子容器 tab 只列直接子级）。
  2. v213 迁移把菜单改成 MOMP 形态、8 条权限码真实存在、重复执行幂等。
  3. 权限码缺失时 verify 必须失败（否则路由守卫 every 判定会整页被拦）。
  4. downgrade 恢复 v211 的 object_list 形态。
"""
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from meta.migrations import v213__handling_unit_momp as v213

REPO_ROOT = Path(__file__).resolve().parents[2]
HU_SCHEMA = REPO_ROOT / 'meta' / 'schemas' / 'handling_unit.yaml'
ITEM_SCHEMA = REPO_ROOT / 'meta' / 'schemas' / 'handling_unit_item.yaml'
TXN_SCHEMA = REPO_ROOT / 'meta' / 'schemas' / 'hu_transaction.yaml'

MENU_PATH = '/inventory/handling-units'

DDL = """
CREATE TABLE menus (
    menu_code VARCHAR(64) PRIMARY KEY,
    menu_name VARCHAR(128) NOT NULL DEFAULT '',
    menu_path VARCHAR(255) NOT NULL DEFAULT '',
    page_type VARCHAR(32) NOT NULL DEFAULT '',
    object_types TEXT NOT NULL DEFAULT '[]',
    primary_object_type VARCHAR(64) NOT NULL DEFAULT '',
    bo_bindings TEXT NOT NULL DEFAULT '[]',
    required_permissions TEXT NOT NULL DEFAULT '[]',
    required_any_permission INTEGER NOT NULL DEFAULT 0,
    parent_menu VARCHAR(64) NOT NULL DEFAULT '',
    icon VARCHAR(64) NOT NULL DEFAULT '',
    color VARCHAR(32) NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    auto_generated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE menu_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code VARCHAR(200) NOT NULL UNIQUE,
    menu_name VARCHAR(200) NOT NULL DEFAULT '',
    menu_path VARCHAR(200) NOT NULL DEFAULT '',
    required_permissions TEXT NOT NULL DEFAULT '[]',
    required_any_permission INTEGER NOT NULL DEFAULT 0,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    sort_order INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    data_permission_hint TEXT
);
CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL UNIQUE
);
"""

V211_OBJECT_TYPES = ['handling_unit']
V211_BO_BINDINGS = [
    {'bo_id': 'handling_unit', 'role': 'primary',
     'include_actions': ['read', 'create', 'update', 'delete']}
]


def _make_db(path: Path, with_menu: bool = True) -> Path:
    db = path / 'architecture.db'
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(DDL)
        for code in v213.NEW_PERMISSIONS:
            conn.execute('INSERT INTO permissions (code) VALUES (?)', (code,))
        if with_menu:
            conn.execute(
                'INSERT INTO menus (menu_code, menu_name, menu_path, page_type, '
                'object_types, primary_object_type, bo_bindings, '
                'required_permissions, parent_menu, icon, sort_order) '
                "VALUES (?, ?, ?, 'object_list', ?, 'handling_unit', ?, ?, "
                "'inventory', 'Box', 9)",
                (v213.MENU_CODE, '包装容器', MENU_PATH,
                 json.dumps(V211_OBJECT_TYPES), json.dumps(V211_BO_BINDINGS),
                 json.dumps(v213.OLD_PERMISSIONS)),
            )
            conn.execute(
                'INSERT INTO menu_permissions (menu_code, menu_name, menu_path, '
                'required_permissions, parent_menu, icon, sort_order) '
                "VALUES (?, '包装容器', ?, ?, 'inventory', 'Box', 9)",
                (v213.MENU_CODE, MENU_PATH, json.dumps(v213.OLD_PERMISSIONS)),
            )
        conn.commit()
    finally:
        conn.close()
    return db


def _read_menu(db: Path):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            'SELECT page_type, object_types, bo_bindings, required_permissions, '
            'auto_generated, menu_path, primary_object_type, parent_menu '
            'FROM menus WHERE menu_code = ?', (v213.MENU_CODE,)
        ).fetchone()
    finally:
        conn.close()


@pytest.fixture()
def db(tmp_path):
    return _make_db(tmp_path)


# ---------------------------------------------------------------- YAML 契约

def test_yaml_hub_declaration():
    """hub 段：三对象、默认 tab、嵌套父字段、子容器 tab 直接子级过滤。"""
    doc = yaml.safe_load(HU_SCHEMA.read_text(encoding='utf-8'))
    hub = doc['ui_view_config']['hub']

    assert hub['object_types'] == ['handling_unit', 'handling_unit_item',
                                   'hu_transaction', 'document_hu_link_view']
    assert hub['default_tab'] == 'handling_unit'
    assert hub['tabs'] == {
        'handling_unit': '子容器',
        'handling_unit_item': '容器内容',
        'hu_transaction': '容器事件',
        'document_hu_link_view': '关联单据',
    }
    scope = hub['scope']
    assert scope['type'] == 'hierarchy'
    assert scope['object'] == 'handling_unit'
    assert scope['scope_key'] == 'handling_unit'
    assert scope['parent_field'] == 'parent_hu_id'
    # 容器无 name/code 字段，必须显式指向 hu_no，否则树节点标签为空
    assert scope['label_field'] == 'hu_no'
    assert scope['code_field'] == 'hu_no'
    assert scope['badge_field'] == 'status'
    assert scope['paginate_all'] is True

    filters = hub['filters']
    assert filters['handling_unit'] == {'field': 'parent_hu_id',
                                        'mode': 'direct'}
    # 内容 / 事件 tab 取整棵子树（effective 口径）
    assert filters['handling_unit_item'] == {'field': 'hu_id'}
    assert filters['hu_transaction'] == {'field': 'hu_id'}
    assert filters['document_hu_link_view'] == {'field': 'hu_id'}


def test_hub_object_types_have_schemas():
    """hub 声明的对象都必须有 schema yaml，否则前端 tab 拿不到 ui_config。"""
    for path in (HU_SCHEMA, ITEM_SCHEMA, TXN_SCHEMA):
        assert path.exists(), path
    item_doc = yaml.safe_load(ITEM_SCHEMA.read_text(encoding='utf-8'))
    txn_doc = yaml.safe_load(TXN_SCHEMA.read_text(encoding='utf-8'))
    assert item_doc['id'] == 'handling_unit_item'
    assert txn_doc['id'] == 'hu_transaction'
    assert item_doc['ui_view_config']['list']['columns']
    assert txn_doc['ui_view_config']['list']['columns']


# ---------------------------------------------------------------- v213

def test_migrate_to_momp_and_verify(db):
    assert v213.migrate(db) is True
    assert v213.verify(db) is True

    page_type, ots, bo, perms, auto, path, pot, parent = _read_menu(db)
    assert page_type == 'multi_object_hub'
    assert json.loads(ots) == v213.NEW_OBJECT_TYPES
    assert json.loads(bo) == v213.NEW_BO_BINDINGS
    assert json.loads(perms) == v213.NEW_PERMISSIONS
    assert auto == 0
    assert path == MENU_PATH
    assert pot == 'handling_unit'
    assert parent == 'inventory'


def test_migrate_is_idempotent(db, capsys):
    assert v213.migrate(db) is True
    assert v213.migrate(db) is True
    output = capsys.readouterr().out
    assert '[SKIP]' in output
    assert v213.verify(db) is True


def test_menu_permissions_synced_to_eight_codes(db):
    assert v213.migrate(db) is True
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            'SELECT required_permissions, required_any_permission '
            'FROM menu_permissions WHERE menu_code = ?', (v213.MENU_CODE,)
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(row[0]) == v213.NEW_PERMISSIONS
    assert row[1] == 0


def test_menu_missing_is_skipped(tmp_path, capsys):
    db = _make_db(tmp_path, with_menu=False)
    assert v213.migrate(db) is True
    assert '[MISS]' in capsys.readouterr().out
    assert v213.verify(db) is False


def test_verify_rejects_missing_permission_code(db):
    """权限码在 permissions 表缺失时必须 FAIL：路由守卫是 every 判定。"""
    assert v213.migrate(db) is True
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            'DELETE FROM permissions WHERE code = ?',
            ('hu_transaction:hu_transaction_list',),
        )
        conn.commit()
    finally:
        conn.close()
    assert v213.verify(db) is False


def test_downgrade_restores_object_list(db):
    assert v213.migrate(db) is True
    assert v213.downgrade(db) is True

    page_type, ots, bo, perms, auto, path, pot, parent = _read_menu(db)
    assert page_type == 'object_list'
    assert json.loads(ots) == V211_OBJECT_TYPES
    assert json.loads(bo) == V211_BO_BINDINGS
    assert json.loads(perms) == v213.OLD_PERMISSIONS
    assert path == MENU_PATH
    assert pot == 'handling_unit'
    assert parent == 'inventory'
    assert v213.verify(db) is False

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            'SELECT required_permissions FROM menu_permissions '
            'WHERE menu_code = ?', (v213.MENU_CODE,)
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(row[0]) == v213.OLD_PERMISSIONS
