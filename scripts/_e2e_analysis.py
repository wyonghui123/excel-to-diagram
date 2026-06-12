# -*- coding: utf-8 -*-
"""[Verify] 详细分析 TEST60 业务流结果"""
import sqlite3
import os

db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'architecture.db')
conn = sqlite3.connect(db)
cursor = conn.cursor()

print('=' * 70)
print('  TEST60 业务流验证分析')
print('=' * 70)

# 1) TEST60 → group 330 → role 1803 → perms
cursor.execute('''SELECT DISTINCT p.code FROM permissions p
                  JOIN role_permissions rp ON rp.permission_id = p.id
                  JOIN group_roles gr ON gr.role_id = rp.role_id
                  JOIN user_group_members ugm ON ugm.group_id = gr.group_id
                  WHERE ugm.user_id = 1223
                  ORDER BY p.code''')
perms = [r[0] for r in cursor.fetchall()]
print(f'\n[1] TEST60 effective perms ({len(perms)}):')
for p in perms:
    print(f'  {p}')

# 2) BO → perm 矩阵
print('\n[2] 5 BO × 5 action 矩阵 (v1.0.1 read/list 合并后):')
bos = ['product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object']
actions = ['create', 'read', 'update', 'delete', 'list']
print(f'  {"BO":<18} | ' + ' | '.join(f'{a:>8}' for a in actions))
print(f'  ' + '-' * 75)
for bo in bos:
    row = f'  {bo:<18} | '
    for a in actions:
        has = f'{bo}:{a}' in perms
        row += f' {"✅" if has else "❌":>8} |'
    print(row)

# 3) E2E 结果预测
print('\n[3] E2E 验证预测 (基于 perms):')
print('  ✅ product GET    : role 有 product:read → 200 (v1.0.1 crud_list→read)')
print('  ❌ version GET    : role 无 version:read → 403 (预期, 角色未配 version:*)')
print('  ✅ domain GET     : role 有 domain:read → 200')
print('  ✅ sub_domain GET : role 有 sub_domain:read → 200')
print('  ✅ product POST   : role 有 product:create → 200/400 (业务校验)')

# 4) version 修复建议
print('\n[4] version 403 修复建议:')
print('  - 选项 A: 给 role 1803 加 version:read (5 动作 + product 同模板)')
print('  - 选项 B: 实现 v1.0.1 D11 A2 (链中任一 read → 链尾 list 隐含)')
print('    含义: 既然有 product:read + product 是 version 的 parent, 应能 list version')

# 5) v1.0.1 A.4 修复了什么
print('\n[5] v1.0.1 A.4 实际修复了什么:')
print('  旧 (v1.0): crud_list 需要 product:list 权限')
print('  新 (v1.0.1): crud_list 映射到 read 权限, 所以 product:read 即够')
print('  → TEST60 角色有 product:read (无 product:list), 现能 list product')

conn.close()
