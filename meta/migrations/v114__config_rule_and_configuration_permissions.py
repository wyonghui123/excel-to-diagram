# -*- coding: utf-8 -*-
"""[v114 2026-10-25] 配置规则与配置实例 权限交付

背景:
  P3 新增两组对象，均由父对象详情内维护（child_sections），不建顶层菜单：
    - config_rule / config_rule_term：结构详情第三级内联表（模型版本维护规则）
    - configuration / configuration_value / configuration_component：
      求解产物，结果层三表（实例头 + 特征值 + 组件）
  内联表格的按钮判定仍需双段式权限码，与 v113 为 item_structure_attribute
  落权限的理由相同。

本迁移补齐:
  5 个对象 × create / read / update / delete / list = 25 条权限。

权限口径:
  双段式 {object_id}:{object_id}_{action}
  （例 config_rule:config_rule_create）。

幂等:
  INSERT OR IGNORE；重复执行只输出 [SKIP]。

回滚:
  **保留** permissions 行 —— 可能已被角色授予，删除有风险。
"""
import sqlite3
from pathlib import Path

OBJECTS = (
    ('config_rule', '配置规则'),
    ('config_rule_term', '规则条件项'),
    ('configuration', '配置实例'),
    ('configuration_value', '配置特征值'),
    ('configuration_component', '配置组件'),
)

_RANK = ('create', 'read', 'update', 'delete', 'list')

_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'{object_id}:{object_id}_{action}',
     f'{_ACTION_LABEL[action]}{label}',
     object_id,
     action)
    for object_id, label in OBJECTS
    for action in _RANK
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return

    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, resource_type, action),
        )
        if cur.rowcount:
            created += 1
            print(f'  - [NEW] 权限 {code} ({name})')

    if created:
        print(f'  - [SUMMARY] permissions: +{created} 新增')
    else:
        print(f'  - [SKIP] {len(PERMISSIONS)} 条权限码均已存在, 无新增')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v114] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v114] 开始: 配置规则与配置实例 权限')
        _do_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v114] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 25 条双段式权限码就位。"""
    if not db_path.exists():
        print('[v114 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'permissions'):
            print('[v114 verify] FAIL: permissions 表不存在')
            return False

        missing = []
        for code, _name, _rt, _action in PERMISSIONS:
            if not conn.execute(
                    "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone():
                missing.append(code)
        if missing:
            print(f'[v114 verify] FAIL: 缺权限码 {missing}')
            return False

        malformed = [c for c, _n, _r, _a in PERMISSIONS
                     if c.count(':') != 1
                     or not c.split(':')[1].startswith(c.split(':')[0] + '_')]
        if malformed:
            print(f'[v114 verify] FAIL: 非双段式权限码 {malformed}')
            return False

        print(f'[v114 verify] OK: {len(PERMISSIONS)} 条双段式权限码齐备')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """permissions 行保留（可能已被角色授予），无删除动作。"""
    print('[v114] downgrade: permissions 行保留 (可能已被角色授予)')
    return True


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v114] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v114] verify: {"PASS" if _v else "FAIL"}')
