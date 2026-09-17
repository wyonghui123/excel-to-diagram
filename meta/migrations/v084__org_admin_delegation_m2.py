# -*- coding: utf-8 -*-
"""
[v084 2026-09-05] Spec 19 M2：组织管理委托授权数据层

内容（TR-001 + FR-003 + 连带修复 + 功能码治理）：
  Phase 1: data_permission_rules 加 expires_at 列（委托有效期，可空=永久）
  Phase 2: permission_sets 加 priority 列（DEFAULT 0）
           —— 连带修复：can_assign_role/get_role_priority 依赖该列，
              当前库缺列导致 PUT /users/<id> 携带 role_ids 时 OperationalError（二次检查 V4 连带发现）
  Phase 3: permissions 注册 Spec 19 新权限码（幂等）：
           - org:move / org_member:manage（M1 已定义）
           - org:create / org:read / org:update（BO 写路径 PermissionInterceptor
             实际校验格式 {object}:{suffix}；旧 org:org_create 系 v1 遗留码，
             BO 链路不消费）
           - user:create / user:read / user:update（同上，v1 /users 委托路径消费）
  Phase 4: seed「组织管理员」权限集模板（FR-003）：
           permission_sets: code='org_admin_template', is_system=0
           绑定功能码（新格式）：org_member:manage / org:create / org:read /
                      org:update / user:create / user:read / user:update
           （模板不预置 org 行级绑定——绑定组织由全局管理员使用时配置，
             模板仅预置功能码组合，避免 seed 即授权）
           —— [API 级验证发现修正] 旧版绑定 org:org_create/user:user_create 等
              旧格式码，PermissionInterceptor 校验 {object}:{suffix} 格式，
              受托管理员功能钥匙实际不可获得；本次替换绑定并清理旧格式绑定。

幂等性：
  - 列已存在跳过；权限码/模板以 code 唯一定位，重复执行 0 变更
  - verify: 列存在 + 码存在 + 模板存在 + 绑定 7 码齐全
  - FR-011 存量报告：org_members.is_manager=1 与 orgs.manager_id 行数（当前 dev 库均为 0，切换零风险）

downgrade:
  删除模板权限集及其绑定、删除新权限码；expires_at/priority 列保留
  （SQLite 3.35 前 DROP COLUMN 不可用，列无害，数据级回滚即可）。
"""
import sqlite3
from pathlib import Path

TEMPLATE_CODE = 'org_admin_template'
NEW_PERMISSION_CODES = [
    ('org:move', '组织移动（变更上级组织）', 'org', 'move'),
    ('org_member:manage', '组织成员管理（委托统一码）', 'org_member', 'manage'),
    ('org:create', '组织创建（受托子组织）', 'org', 'create'),
    ('org:read', '组织查看', 'org', 'read'),
    ('org:update', '组织编辑（受托子树）', 'org', 'update'),
    ('user:create', '用户创建（受托范围）', 'user', 'create'),
    ('user:read', '用户查看', 'user', 'read'),
    ('user:update', '用户编辑（受托范围）', 'user', 'update'),
]
# 旧格式码（{obj}:{obj}_{action}）：BO 链路不消费，从模板绑定中清理
LEGACY_TEMPLATE_CODES = [
    'org:org_create', 'org:org_update', 'org:org_read', 'org:org_list',
    'user:user_create', 'user:user_update', 'user:user_read', 'user:user_list',
]
TEMPLATE_PERMISSION_CODES = [
    'org_member:manage',
    'org:create', 'org:read', 'org:update',
    'user:create', 'user:read', 'user:update',
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _add_column(conn: sqlite3.Connection, table: str, ddl_column: str) -> bool:
    col = ddl_column.split()[0]
    if _has_column(conn, table, col):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl_column}")
    return True


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        # Phase 1: expires_at（委托有效期）
        # [2026-09-14 prod 彩排修正] data_permission_rules 由代码 lazy create
        # (condition_permission_service._ensure_unified_table)，spec15 prod 库无此表。
        # 表不存在时跳过（新表 DDL 已含 expires_at 列），避免迁移 FAILED。
        if _table_exists(conn, 'data_permission_rules'):
            _add_column(conn, 'data_permission_rules', 'expires_at VARCHAR(50)')
        else:
            print('[v084] data_permission_rules 不存在, 跳过 expires_at (lazy create 建表已含该列)')

        # Phase 2: priority（can_assign_role 连带修复）
        _add_column(conn, 'permission_sets', 'priority INTEGER DEFAULT 0')

        # Phase 3: 新权限码（幂等）
        # [2026-09-14 prod 彩排修正] prod spec15 的 permissions 表无 created_at 列
        # (id, code, name, resource_type, action, description, resource_id, scope)，
        # 列探测后动态构造 INSERT。
        perm_cols = {r[1] for r in conn.execute('PRAGMA table_info(permissions)')}
        ins_cols = ['code', 'name', 'resource_type', 'action']
        if 'created_at' in perm_cols:
            ins_cols.append('created_at')
        ph = ', '.join(['?'] * (len(ins_cols) - (1 if 'created_at' in perm_cols else 0))
                       + (["datetime('now')"] if 'created_at' in perm_cols else []))
        for code, name, rtype, action in NEW_PERMISSION_CODES:
            conn.execute(
                f"INSERT OR IGNORE INTO permissions ({', '.join(ins_cols)}) VALUES ({ph})",
                (code, name, rtype, action),
            )
        conn.commit()

        # Phase 4: 模板权限集 + 功能码绑定（幂等）
        row = conn.execute(
            "SELECT id FROM permission_sets WHERE code = ?", (TEMPLATE_CODE,)
        ).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO permission_sets (code, name, description, is_active, is_system, "
                "priority, created_at, created_by) VALUES (?, ?, ?, 1, 0, 0, datetime('now'), 'v084_seed')",
                (TEMPLATE_CODE, '组织管理员模板',
                 'Spec 19 FR-003 预置模板：组织/成员管理功能码组合。'
                 '使用时请为具体组织配置该权限集并绑定 org 行级范围。'),
            )
            template_id = cur.lastrowid
        else:
            template_id = row[0]

        # [2026-09-06 schema 自适应修复] permission_set_permissions 存在两种形态:
        #   ID-form (staging v083 系): (permission_set_id, permission_id, granted, created_at)
        #   CODE-form (部分 dev/worktree 库): 含 permission_code 列
        # [2026-09-14 prod 彩排修正] prod 第三形态: v070 仅 RENAME 表名, 列仍为 role_id
        #   LEGACY-ID-form: (role_id, permission_id, granted, created_at) — 由 v087 backfill
        # 按实际列名选择写入列, 三种库均可执行。
        psp_cols = {r[1] for r in conn.execute('PRAGMA table_info(permission_set_permissions)')}
        has_code_col = 'permission_code' in psp_cols
        if 'permission_set_id' in psp_cols:
            id_col = 'permission_set_id'
        elif 'role_id' in psp_cols:
            id_col = 'role_id'
        else:
            raise RuntimeError(
                f'[v084] permission_set_permissions 无 permission_set_id/role_id 列: {sorted(psp_cols)}')

        for code in TEMPLATE_PERMISSION_CODES:
            prow = conn.execute(
                "SELECT id FROM permissions WHERE code = ?", (code,)
            ).fetchone()
            if prow is None:
                continue
            if has_code_col:
                conn.execute(
                    f"INSERT OR IGNORE INTO permission_set_permissions "
                    f"(permission_set_id, permission_code, permission_id, granted, created_at) "
                    f"VALUES (?, ?, ?, 1, datetime('now'))",
                    (template_id, code, prow[0]),
                )
            else:
                conn.execute(
                    f"INSERT OR IGNORE INTO permission_set_permissions "
                    f"({id_col}, permission_id, granted, created_at) "
                    f"VALUES (?, ?, 1, datetime('now'))",
                    (template_id, prow[0]),
                )

        # [API 级验证发现修正] 清理旧格式码绑定（幂等）：BO 链路不消费 {obj}:{obj}_{action}
        for legacy_code in LEGACY_TEMPLATE_CODES:
            if has_code_col:
                conn.execute(
                    "DELETE FROM permission_set_permissions "
                    "WHERE permission_set_id = ? AND permission_code = ?",
                    (template_id, legacy_code),
                )
            else:
                conn.execute(
                    f"DELETE FROM permission_set_permissions "
                    f"WHERE {id_col} = ? AND permission_id IN "
                    "(SELECT id FROM permissions WHERE code = ?)",
                    (template_id, legacy_code),
                )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        ok = True
        if not _table_exists(conn, 'data_permission_rules'):
            print('[v084 verify] SKIP: data_permission_rules 不存在 (lazy create 建表已含 expires_at)')
        elif not _has_column(conn, 'data_permission_rules', 'expires_at'):
            print('[v084 verify] FAIL: data_permission_rules.expires_at 缺失')
            ok = False
        if not _has_column(conn, 'permission_sets', 'priority'):
            print('[v084 verify] FAIL: permission_sets.priority 缺失')
            ok = False
        for code, _, _, _ in NEW_PERMISSION_CODES:
            if not conn.execute(
                "SELECT 1 FROM permissions WHERE code = ?", (code,)
            ).fetchone():
                print(f'[v084 verify] FAIL: 权限码 {code} 缺失')
                ok = False
        trow = conn.execute(
            "SELECT id FROM permission_sets WHERE code = ?", (TEMPLATE_CODE,)
        ).fetchone()
        if not trow:
            print('[v084 verify] FAIL: 模板权限集缺失')
            ok = False
        else:
            psp_cols = {r[1] for r in conn.execute('PRAGMA table_info(permission_set_permissions)')}
            id_col = ('permission_set_id' if 'permission_set_id' in psp_cols
                      else 'role_id' if 'role_id' in psp_cols else None)
            if id_col is None:
                print('[v084 verify] FAIL: permission_set_permissions 无 id 列')
                ok = False
            else:
                bound = conn.execute(
                    f"SELECT COUNT(*) FROM permission_set_permissions "
                    f"WHERE {id_col} = ?", (trow[0],),
                ).fetchone()[0]
                if bound < len(TEMPLATE_PERMISSION_CODES):
                    print(f'[v084 verify] FAIL: 模板绑定 {bound}/{len(TEMPLATE_PERMISSION_CODES)}')
                    ok = False

        # FR-011 存量报告（信息性，不影响 verify 结果）
        try:
            im = conn.execute(
                "SELECT COUNT(*) FROM org_members WHERE is_manager = 1"
            ).fetchone()[0]
            mi = conn.execute(
                "SELECT COUNT(*) FROM orgs WHERE manager_id IS NOT NULL"
            ).fetchone()[0]
            print(f'[v084 verify] FR-011 存量: is_manager={im} 行, manager_id={mi} 行'
                  f'（M3 移除遗留读取路径）')
        except sqlite3.OperationalError:
            pass
        return ok
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        psp_cols = {r[1] for r in conn.execute('PRAGMA table_info(permission_set_permissions)')}
        id_col = ('permission_set_id' if 'permission_set_id' in psp_cols
                  else 'role_id' if 'role_id' in psp_cols else 'permission_set_id')
        trow = conn.execute(
            "SELECT id FROM permission_sets WHERE code = ?", (TEMPLATE_CODE,)
        ).fetchone()
        if trow:
            conn.execute(
                f"DELETE FROM permission_set_permissions WHERE {id_col} = ?",
                (trow[0],),
            )
            conn.execute("DELETE FROM permission_sets WHERE id = ?", (trow[0],))
        for code, _, _, _ in NEW_PERMISSION_CODES:
            conn.execute(f"DELETE FROM permission_set_permissions WHERE {id_col} = "
                         "(SELECT id FROM permissions WHERE code = ?)", (code,))
            conn.execute("DELETE FROM permissions WHERE code = ?", (code,))
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'architecture.db'
    print(f'[v084] migrating {db}')
    migrate(db)
    ok = verify(db)
    print(f'[v084] verify: {"PASS" if ok else "FAIL"}')
    sys.exit(0 if ok else 1)
