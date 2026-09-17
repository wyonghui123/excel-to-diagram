# -*- coding: utf-8 -*-
"""
[2026-09-05 HOTFIX] 迁移重跑损伤修复
事故: migration runner 因旧式 schema_migrations 记录缺 .py 后缀重跑历史迁移,
      旧版 rename_roles_to_permission_sets.py (含 DROP 活表) 将
      permission_sets / permission_set_permissions / user_permission_sets
      DROP 后用陈旧 roles 系表顶替 (DDL 自动提交, 部分执行后 FAILED)。

修复: 从 bak_pre_menu_rebuild_20260901 (9/1 18:50 全量备份) 还原 3 表,
      缺失集 (1195-1232/12666, 9/1 后创建) 以占位行重建,
      记账层: 旧式记录补 .py 后缀 / 清理重复与 FAILED 记录 / SQL 已应用标记 SUCCESS。
模板 12675 由后续 v084 重跑补种 (本脚本不处理)。
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from meta.core.db_path import get_meta_db_path

cur_db = get_meta_db_path()
ref_db = str(Path(cur_db).parent / 'architecture.db.bak_pre_menu_rebuild_20260901')
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

conn = sqlite3.connect(cur_db)
ref = sqlite3.connect(ref_db)
cc, cr = conn.cursor(), ref.cursor()

# ---------- Step A: 还原 3 张表 ----------
# A1. ref 数据读入内存
ref_sets = cr.execute(
    "SELECT id, code, name, description, is_active, created_at, updated_at, "
    "       created_by, updated_by, is_system, user_count, menu_count, "
    "       permission_count, data_perm_count "
    "FROM permission_sets ORDER BY id").fetchall()
ref_bindings = cr.execute(
    "SELECT id, permission_set_id, permission_code, created_at, permission_id, granted "
    "FROM permission_set_permissions ORDER BY id").fetchall()
ref_ups = cr.execute(
    "SELECT id, user_id, permission_set_id, created_at "
    "FROM user_permission_sets ORDER BY id").fetchall()

# A2. 引用 id 勘察 → 9/1 备份缺失的集合以占位行重建
ref_ids = {r[0] for r in ref_sets}
dim_refs = {r[0] for r in cc.execute(
    "SELECT DISTINCT permission_set_id FROM permission_set_dimension_scopes "
    "WHERE permission_set_id IS NOT NULL")}
dpr_refs = {r[0] for r in cc.execute(
    "SELECT DISTINCT permission_set_id FROM data_permission_rules "
    "WHERE permission_set_id IS NOT NULL")}
menu_refs = {r[0] for r in cc.execute(
    "SELECT DISTINCT permission_set_id FROM permission_set_menu_permissions")}
org_refs = {r[0] for r in cc.execute(
    "SELECT DISTINCT permission_set_id FROM org_permission_sets")}
needed = (dim_refs | dpr_refs | menu_refs | org_refs) - ref_ids
print(f'[A2] 备份缺失但被引用的集合 id: {sorted(needed)}')

extra_rows = []
for sid in sorted(needed):
    extra_rows.append((
        sid, f'restored_{sid}', f'Restored Set {sid}',
        '2026-09-05 迁移重跑事故恢复占位行（原名未留存于备份）',
        1, now, now, 'hotfix_migration_rerun', None, 0, 0, 0, 0, 0, 0,
    ))

# A3. 功能绑定过滤: permission_id 必须仍存在于当前 permissions 表
cur_perm_ids = {r[0] for r in cc.execute('SELECT id FROM permissions')}
kept_bindings = [b for b in ref_bindings if b[4] in cur_perm_ids]
dropped_bindings = len(ref_bindings) - len(kept_bindings)
print(f'[A3] ref 绑定 {len(ref_bindings)} 行, 保留 {len(kept_bindings)} (悬空 permission_id 丢弃 {dropped_bindings})')

# A4. 重建表 (与事故前 live schema 一致, 9/1 备份缺 priority 列则补上)
cc.execute('DROP TABLE IF EXISTS user_permission_sets')
cc.execute('DROP TABLE IF EXISTS permission_set_permissions')
cc.execute('DROP TABLE IF EXISTS permission_sets')
cc.execute("""
CREATE TABLE permission_sets (
    id INTEGER PRIMARY KEY,
    code VARCHAR(200),
    name VARCHAR(200),
    description TEXT,
    is_active INTEGER,
    created_at VARCHAR(200),
    updated_at VARCHAR(200),
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    is_system INTEGER,
    user_count INTEGER,
    menu_count INTEGER,
    permission_count INTEGER,
    data_perm_count INTEGER,
    priority INTEGER DEFAULT 0
)""")
cc.execute("""
CREATE TABLE permission_set_permissions (
    id INTEGER PRIMARY KEY,
    permission_set_id INTEGER,
    permission_code VARCHAR(200),
    created_at VARCHAR(200),
    permission_id INTEGER,
    granted INTEGER
)""")
cc.execute("""
CREATE TABLE user_permission_sets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    permission_set_id INTEGER,
    created_at VARCHAR(200)
)""")

all_sets = [tuple(r) + (0,) for r in ref_sets] + extra_rows  # priority 补 0
cc.executemany(
    "INSERT INTO permission_sets (id, code, name, description, is_active, created_at, "
    "updated_at, created_by, updated_by, is_system, user_count, menu_count, "
    "permission_count, data_perm_count, priority) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    all_sets)
cc.executemany(
    "INSERT INTO permission_set_permissions (id, permission_set_id, permission_code, "
    "created_at, permission_id, granted) VALUES (?,?,?,?,?,?)",
    kept_bindings)
cc.executemany(
    "INSERT INTO user_permission_sets (id, user_id, permission_set_id, created_at) "
    "VALUES (?,?,?,?)", ref_ups)
conn.commit()
print(f'[A4] 还原完成: permission_sets={len(all_sets)}, bindings={len(kept_bindings)}, '
      f'user_permission_sets={len(ref_ups)}')

# ---------- Step B: schema_migrations 记账修复 ----------
# B1. 旧式记录 (缺 .py) 且文件存在、且无新式记录 → 补 .py
mig_dir = Path(cur_db).parent / 'migrations'
records = {r[0]: r[1] for r in cc.execute("SELECT id, migration_name FROM schema_migrations")}
names = list(records.values())
for old in list(names):
    if old.endswith(('.py', '.sql')):
        continue
    new = old + '.py'
    if not (mig_dir / new).exists():
        print(f'[B1] 跳过 (文件不存在): {old}')
        continue
    if new in names:
        cc.execute("DELETE FROM schema_migrations WHERE migration_name = ?", (old,))
        print(f'[B1] 删除旧式重复记录: {old} (新式已存在)')
    else:
        cc.execute("UPDATE schema_migrations SET migration_name = ? WHERE migration_name = ?",
                   (new, old))
        print(f'[B1] 补后缀: {old} → {new}')
    names = [new if n == old else n for n in names]

# B2. FAILED 记录清理
for name, action in [
    ('2026_06_28_bug_v031_sm_domain_id_trigger.sql', 'mark_success'),  # 已应用, 非幂等重跑失败
    ('rename_roles_to_permission_sets.py', 'delete'),                  # 事故元凶, 文件将归档
    ('rename_user_groups_to_orgs.py', 'delete'),                       # 事故同伙, 文件将归档
    ('v084__org_admin_delegation_m2.py', 'delete'),                    # 因损伤失败, 表还原后重跑
]:
    if action == 'mark_success':
        cc.execute("UPDATE schema_migrations SET status='SUCCESS', "
                   "error_message='[2026-09-05 hotfix] 已应用标记: 非幂等 SQL 重跑失败, 列/触发器实际已存在' "
                   "WHERE migration_name = ? AND status='FAILED'", (name,))
        print(f'[B2] 标记 SUCCESS: {name}')
    else:
        cc.execute("DELETE FROM schema_migrations WHERE migration_name = ? AND status='FAILED'", (name,))
        print(f'[B2] 删除 FAILED 记录: {name}')
conn.commit()

# B3. 记账终态
print('\n[B3] schema_migrations 终态:')
for r in cc.execute("SELECT id, migration_name, status FROM schema_migrations ORDER BY id"):
    print('   ', r)

conn.close()
ref.close()
print('\nDONE: 表还原 + 记账修复完成。下一步: 归档危险旧文件 → 重跑 v084 → 重启服务。')
