"""
深度端到端测试：模拟完整的前端渲染链路
"""
import requests
import json
import sys
import os

BASE = 'http://localhost:3010'

def check(name, condition, detail=""):
    status = "[OK]" if condition else "[X]"
    print(f"  {status} {name}" + (f" | {detail}" if detail else ""))
    return condition

# ============================================================
# Step 1: Login
# ============================================================
print("=" * 70)
print("  [Step 1] 登录...")
try:
    r = requests.post(f'{BASE}/api/v1/auth/login', 
        json={'username': 'admin', 'password': 'admin123'}, timeout=5)
    data = r.json()
    token = data.get('data', {}).get('token') or data.get('token')
    assert token, f"登录失败: {data}"
    check("登录", True, f"token={token[:16]}...")
except Exception as e:
    print(f"  [X] 无法连接后端: {e}")
    sys.exit(1)

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
all_ok = True

# ============================================================
# Step 2: /visible API → 完整菜单树
# ============================================================
print(f"\n{'='*70}")
print("  [Step 2] /menu-permission/visible API → 菜单树")
r = requests.get(f'{BASE}/api/v1/menu-permission/visible', headers=headers, timeout=5)
menus = r.json().get('menus', [])
check(f"API 返回 {len(menus)} 个顶层菜单", len(menus) > 0)

# 递归查找 task-management
def find_node(nodes, code):
    for n in nodes:
        if n.get('menu_code') == code:
            return n
        for c in n.get('children', []):
            if c.get('menu_code') == code:
                return c
    return None

tm = find_node(menus, 'task-management')
check("task-management 在菜单树中", tm is not None)
if not tm:
    print("  -> 菜单树中所有 code:")
    for m in menus:
        print(f"     [{m['menu_code']}] {m['menu_name']}")
        for c in m.get('children', []):
            print(f"        └ [{c['menu_code']}] {c['menu_name']}")
    all_ok = False

# ============================================================
# Step 3: task-management 的 children
# ============================================================
print(f"\n{'='*70}")
print("  [Step 3] task-management 的子节点（GenericTabContainer 的 tabs 来源）")
if tm:
    children = tm.get('children', [])
    check(f"children 数量: {len(children)} (期望 4)", len(children) == 4)
    
    for c in children:
        has_obj = c.get('primary_object_type') or c.get('object_types')
        print(f"     [{c['menu_code']}] {c['menu_name']}"
              f"  type={c['page_type']!s:20s}  obj={c.get('primary_object_type','')!s:10s}  "
              f"has_objType={'[OK]' if has_obj else '[WARNING] '}")
        if not has_obj:
            all_ok = False
    
    check("所有 child 都有 page_type", all(child.get('page_type') for child in children))
    check("所有 child 都有 primary_object_type", all(child.get('primary_object_type') for child in children))

# ============================================================
# Step 4: 路由解析 → 组件映射
# ============================================================
print(f"\n{'='*70}")
print("  [Step 4] 模拟前端路由解析")
if tm:
    path = tm.get('menu_path', '')
    page_type = tm.get('page_type', '')
    check("menu_path", f"'{path}' → 期望 '/system/task-management'", path == '/system/task-management')
    
    PAGE_TYPE_MAP = {
        'object_list': 'GenericObjectList.vue',
        'multi_object_hub': 'GenericTabContainer.vue',
        'custom_page': '需静态路由',
        'dashboard': 'Dashboard.vue',
    }
    component = PAGE_TYPE_MAP.get(page_type, 'UNKNOWN')
    check("组件映射", f"page_type={page_type} → {component}", 
          component == 'GenericTabContainer.vue')

# ============================================================
# Step 5: 检查前端静态路由列表（模拟 _isStaticRoute）
# ============================================================
print(f"\n{'='*70}")
print("  [Step 5] 检查是否会被静态路由拦截")
STATIC_ROUTE_NAMES = [
    'home', 'dashboard', 'user-permission', 'role-detail',
    'system-admin', 'theme-preview', 'dev', 'test', 'login',
    'db-debug', 'diagram', 'config', 'component-comparison', 
    'navigation-test', 'account', 'debug', 'arch-progress',
    'management-dimension', 'demo-offcanvas-menu', 'admin-log',
]
STATIC_ROUTE_PATHS = [
    '/dev/theme-preview', '/diagram', '/config', '/test',
    '/component-comparison', '/dev/navigation-test', '/account',
    '/detail/', '/system-admin', '/role/',
    '/system/role-permission/', '/system/role-detail/',
]

name_blocked = 'task-management' in