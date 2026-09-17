# -*- coding: utf-8 -*-
"""
[Spec 19 M2-9] 受托管理员测试数据搭建 (幂等, spec19_ 前缀便于清理)

场景:
    全局管理员将「组织管理委托」授予 delegate 用户:
      - delegate 归属 org 16 (Test Group, org 15 的子组织)
      - 委托权限集 = 模板克隆 (7 功能码) 绑定到 org 16
      - 行级范围: org 资源 condition='id = 15' → 可管理 15 整棵子树
验证夹具:
    - 范围内目标: org 16 / user test_regular(9994, 归属 org 15)
    - 范围外目标: org 404 (需确认存在) / 归属 org 9 的用户
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from meta.core.db_path import get_meta_db_path

now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
conn = sqlite3.connect(get_meta_db_path())
c = conn.cursor()

# ---------- 1. delegate 用户 ----------
row = c.execute("SELECT id FROM users WHERE username='spec19_delegate'").fetchone()
if row:
    delegate_id = row[0]
    print(f'[1] delegate 已存在 id={delegate_id}')
else:
    c.execute(
        "INSERT INTO users (username, display_name, email, status, created_at, created_by) "
        "VALUES ('spec19_delegate', 'Spec19 受托管理员', 'spec19_delegate@test.local', 'active', ?, 'spec19_setup')",
        (now,))
    delegate_id = c.lastrowid
    print(f'[1] 创建 delegate id={delegate_id}')

# ---------- 2. org 归属 (org 16) ----------
c.execute("INSERT OR IGNORE INTO org_members (user_id, org_id, is_manager, joined_at) VALUES (?, 16, 0, ?)",
          (delegate_id, now))
print('[2] delegate ∈ org 16')

# ---------- 3. 委托权限集 (模板克隆) ----------
TEMPLATE_CODES = ['org_member:manage', 'org:create', 'org:read', 'org:update',
                  'user:create', 'user:read', 'user:update']
row = c.execute("SELECT id FROM permission_sets WHERE code='spec19_delegate_set'").fetchone()
if row:
    set_id = row[0]
    print(f'[3] 委托权限集已存在 id={set_id}')
else:
    c.execute(
        "INSERT INTO permission_sets (code, name, description, is_active, is_system, priority, "
        "created_at, created_by) VALUES ('spec19_delegate_set', 'Spec19 委托测试权限集', "
        "'M2-9b API 级验证用: 模板 7 功能码 + org 行级范围 id=15', 1, 0, 0, ?, 'spec19_setup')",
        (now,))
    set_id = c.lastrowid
    print(f'[3] 创建委托权限集 id={set_id}')

for code in TEMPLATE_CODES:
    prow = c.execute('SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
    if not prow:
        raise SystemExit(f'FATAL: 权限码 {code} 缺失')
    exists = c.execute(
        "SELECT 1 FROM permission_set_permissions WHERE permission_set_id=? AND permission_code=?",
        (set_id, code)).fetchone()
    if not exists:
        c.execute(
            "INSERT INTO permission_set_permissions (permission_set_id, permission_code, permission_id, granted, created_at) "
            "VALUES (?, ?, ?, 1, ?)", (set_id, code, prow[0], now))
print(f'[3] 绑定 {len(TEMPLATE_CODES)} 功能码')

# ---------- 4. 权限集绑定到 org 16 ----------
c.execute("INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id, created_at, created_by) "
          "VALUES (16, ?, ?, 'spec19_setup')", (set_id, now))
print('[4] 权限集 → org 16')

# ---------- 5. org 行级范围规则: id = 15 ----------
row = c.execute("SELECT id FROM data_permission_rules WHERE permission_set_id=? AND resource_type='org' "
                "AND rule_type='condition'", (set_id,)).fetchone()
if row:
    print(f'[5] 行级规则已存在 id={row[0]}')
else:
    c.execute(
        "INSERT INTO data_permission_rules (rule_type, resource_type, condition, permission_level, "
        "is_denied, permission_set_id, created_at, updated_at, created_by) "
        "VALUES ('condition', 'org', 'id = 15', 'edit', 0, ?, ?, ?, 'spec19_setup')",
        (set_id, now, now))
    print('[5] 行级规则: condition = id = 15')

# ---------- 6. 验证夹具确认 ----------
print('\n[6] 夹具确认:')
for oid in (15, 16, 1045, 8329, 404, 9):
    r = c.execute('SELECT id, parent_id, name FROM orgs WHERE id=?', (oid,)).fetchone()
    print(f'   org {oid}: {r}')
print('   in-scope 目标用户 test_regular:', c.execute(
    "SELECT u.id, u.username, om.org_id FROM users u JOIN org_members om ON om.user_id=u.id "
    "WHERE u.username='test_regular'").fetchall())
print('   org 9 成员样例:', c.execute(
    "SELECT om.user_id, u.username FROM org_members om JOIN users u ON u.id=om.user_id "
    "WHERE om.org_id=9 LIMIT 3").fetchall())
if not c.execute('SELECT 1 FROM org_members WHERE org_id=9 LIMIT 1').fetchone():
    print('   [!] org 9 无成员 — 需要一个范围外用户夹具')

conn.commit()
conn.close()
print('\nDONE: 测试数据就绪。delegate=spec19_delegate, 权限集=spec19_delegate_set')
