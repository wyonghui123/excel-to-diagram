# -*- coding: utf-8 -*-
"""前端完整测试：角色功能权限细粒度控制 - 完整 UI 交互流程验证"""
import asyncio
from playwright.async_api import async_playwright
import os, json, sqlite3

BASE_URL = "http://localhost:3004"
API_URL = "http://localhost:3010"
SCREENSHOT_DIR = "d:/filework/excel-to-diagram/test_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 测试结果收集
results = []

def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # 收集控制台错误
        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda err: console_errors.append(f"[pageerror] {err}"))

        # ============================================================
        # Step 1: 认证
        # ============================================================
        print("\n=== Step 1: 认证 ===")
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'architecture.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT u.username FROM users u
            JOIN user_group_members ugm ON u.id = ugm.user_id
            JOIN group_roles gr ON ugm.group_id = gr.group_id
            JOIN roles r ON gr.role_id = r.id
            WHERE r.is_super_admin = 1 LIMIT 1
        """)
        admin_user = cursor.fetchone()[0]
        conn.close()

        await page.goto(f"{API_URL}/api/v1/auth/dev-login?username={admin_user}", wait_until="networkidle")
        cookies = await context.cookies()
        auth_token = next((c['value'] for c in cookies if c['name'] == 'auth_token'), '')
        record("管理员认证", bool(auth_token), f"user={admin_user}")

        # ============================================================
        # Step 2: 查找非系统角色
        # ============================================================
        print("\n=== Step 2: 查找非系统角色 ===")
        import urllib.request
        req = urllib.request.Request(f"{API_URL}/api/v1/roles?limit=50")
        req.add_header('Cookie', f'auth_token={auth_token}')
        resp = urllib.request.urlopen(req)
        roles_data = json.loads(resp.read().decode())
        roles = roles_data.get('data', [])
        target_role = None
        for r in roles:
            if isinstance(r, dict) and not r.get('is_system', False):
                target_role = r
                break
        record("查找非系统角色", target_role is not None, f"id={target_role['id']}, name={target_role.get('name')}" if target_role else "未找到")
        if not target_role:
            await browser.close()
            return

        role_id = target_role['id']

        # ============================================================
        # Step 3: 重置权限状态
        # ============================================================
        print("\n=== Step 3: 重置权限状态 ===")
        reset_result = await page.evaluate("""async (roleId) => {
            const resp = await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: []
                })
            });
            return await resp.json();
        }""", role_id)
        record("重置权限", reset_result.get('success', False), reset_result.get('message', ''))

        # ============================================================
        # Step 4: 导航到角色详情页
        # ============================================================
        print("\n=== Step 4: 导航到角色详情页 ===")
        await page.goto(f"{BASE_URL}/system/role-detail/{role_id}", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/complete_04_role_detail.png")

        current_url = page.url
        page_title = await page.title()
        print(f"  当前 URL: {current_url}")
        print(f"  页面标题: {page_title}")
        record("页面加载", '角色' in page_title or 'Role' in page_title)

        # ============================================================
        # Step 5: 验证初始状态
        # ============================================================
        print("\n=== Step 5: 验证初始状态 ===")
        initial_state = await page.evaluate("""async (roleId) => {
            const resp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const data = await resp.json();
            const archMenu = data.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                menuAssigned: archMenu?.assigned,
                domainGroup: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                standalone: domainGroup?.standalone || [],
                perms: archMenu?.required_permissions?.filter(p => p.code.startsWith('domain:')).map(p => ({
                    code: p.code,
                    granted: p.granted,
                    source: p.source
                })) || []
            };
        }""", role_id)

        record("菜单已分配", initial_state.get('menuAssigned', False))
        record("初始 view=auto", initial_state.get('domainGroup', {}).get('view', {}).get('source') == 'auto')
        record("初始 edit=auto", initial_state.get('domainGroup', {}).get('edit', {}).get('source') == 'auto')
        record("初始 manage=auto", initial_state.get('domainGroup', {}).get('manage', {}).get('source') == 'auto')
        record("初始 standalone 数量", len(initial_state.get('standalone', [])) == 2, f"数量: {len(initial_state.get('standalone', []))}")

        # ============================================================
        # Step 6: 测试动作分组切换 - exclude edit
        # ============================================================
        print("\n=== Step 6: 测试动作分组切换 - exclude edit ===")

        # 6.1 通过 API 模拟点击 edit 按钮进行 exclude
        exclude_edit_result = await page.evaluate("""async (roleId) => {
            // 保存 exclude edit（取消 domain:update 和 domain:create）
            const saveResp = await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: [
                        { code: 'domain:update', granted: false },
                        { code: 'domain:create', granted: false }
                    ]
                })
            });
            const saveResult = await saveResp.json();

            // 重新加载验证
            const reloadResp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const reloadData = await reloadResp.json();
            const archMenu = reloadData.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                saveSuccess: saveResult.success,
                saveMessage: saveResult.message,
                groups: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                perms: {
                    update: archMenu?.required_permissions?.find(p => p.code === 'domain:update'),
                    create: archMenu?.required_permissions?.find(p => p.code === 'domain:create'),
                    read: archMenu?.required_permissions?.find(p => p.code === 'domain:read'),
                    delete: archMenu?.required_permissions?.find(p => p.code === 'domain:delete')
                }
            };
        }""", role_id)

        record("保存 exclude edit", exclude_edit_result.get('saveSuccess', False), exclude_edit_result.get('saveMessage', ''))

        groups = exclude_edit_result.get('groups', {})
        perms = exclude_edit_result.get('perms', {})

        record("edit 分组 excluded", groups.get('edit', {}).get('source') == 'exclude' and not groups.get('edit', {}).get('granted'))
        record("view 分组保持 auto", groups.get('view', {}).get('source') == 'auto' and groups.get('view', {}).get('granted'))
        record("manage 分组 excluded", groups.get('manage', {}).get('source') == 'exclude' and not groups.get('manage', {}).get('granted'))
        record("domain:update excluded", perms.get('update', {}).get('source') == 'exclude')
        record("domain:create excluded", perms.get('create', {}).get('source') == 'exclude')
        record("domain:read 保持 auto", perms.get('read', {}).get('source') == 'auto')
        record("domain:delete 保持 auto", perms.get('delete', {}).get('source') == 'auto')

        # ============================================================
        # Step 7: 刷新页面验证持久化
        # ============================================================
        print("\n=== Step 7: 刷新页面验证持久化 ===")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/complete_07_after_refresh.png")

        after_refresh = await page.evaluate("""async (roleId) => {
            const resp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const data = await resp.json();
            const archMenu = data.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                groups: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                perms: {
                    update: archMenu?.required_permissions?.find(p => p.code === 'domain:update'),
                    create: archMenu?.required_permissions?.find(p => p.code === 'domain:create'),
                    read: archMenu?.required_permissions?.find(p => p.code === 'domain:read'),
                    delete: archMenu?.required_permissions?.find(p => p.code === 'domain:delete')
                }
            };
        }""", role_id)

        groups_r = after_refresh.get('groups', {})
        perms_r = after_refresh.get('perms', {})

        record("刷新后 edit 仍 excluded", groups_r.get('edit', {}).get('source') == 'exclude')
        record("刷新后 view 仍 auto", groups_r.get('view', {}).get('source') == 'auto')
        record("刷新后 domain:update 仍 excluded", perms_r.get('update', {}).get('source') == 'exclude')
        record("刷新后 domain:read 仍 auto", perms_r.get('read', {}).get('source') == 'auto')

        # ============================================================
        # Step 8: 测试 include edit（重新激活）
        # ============================================================
        print("\n=== Step 8: 测试 include edit（重新激活） ===")

        include_edit_result = await page.evaluate("""async (roleId) => {
            // include edit（恢复 domain:update 和 domain:create）
            const saveResp = await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: [
                        { code: 'domain:update', granted: true },
                        { code: 'domain:create', granted: true }
                    ]
                })
            });
            const saveResult = await saveResp.json();

            const reloadResp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const reloadData = await reloadResp.json();
            const archMenu = reloadData.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                saveSuccess: saveResult.success,
                groups: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                perms: {
                    update: archMenu?.required_permissions?.find(p => p.code === 'domain:update'),
                    create: archMenu?.required_permissions?.find(p => p.code === 'domain:create'),
                    read: archMenu?.required_permissions?.find(p => p.code === 'domain:read')
                }
            };
        }""", role_id)

        record("保存 include edit", include_edit_result.get('saveSuccess', False))

        groups_i = include_edit_result.get('groups', {})
        perms_i = include_edit_result.get('perms', {})

        record("edit 分组 include", groups_i.get('edit', {}).get('source') == 'include' and groups_i.get('edit', {}).get('granted'))
        record("view 分组保持 auto", groups_i.get('view', {}).get('source') == 'auto')
        record("manage 分组恢复 auto", groups_i.get('manage', {}).get('source') == 'auto' or groups_i.get('manage', {}).get('source') == 'include')
        record("domain:update include", perms_i.get('update', {}).get('source') == 'include')
        record("domain:create include", perms_i.get('create', {}).get('source') == 'include')
        record("domain:read 保持 auto", perms_i.get('read', {}).get('source') == 'auto')

        # ============================================================
        # Step 9: 测试 manage 分组层级依赖
        # ============================================================
        print("\n=== Step 9: 测试 manage 分组层级依赖 ===")

        manage_result = await page.evaluate("""async (roleId) => {
            // 先 exclude 所有
            await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: [
                        { code: 'domain:update', granted: false },
                        { code: 'domain:delete', granted: false },
                        { code: 'domain:create', granted: false }
                    ]
                })
            });

            // 再 include manage（应该包含 delete + create + update + read + list）
            const saveResp = await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: [
                        { code: 'domain:delete', granted: true },
                        { code: 'domain:create', granted: true },
                        { code: 'domain:update', granted: true }
                    ]
                })
            });
            const saveResult = await saveResp.json();

            const reloadResp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const reloadData = await reloadResp.json();
            const archMenu = reloadData.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                saveSuccess: saveResult.success,
                groups: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                perms: {
                    delete: archMenu?.required_permissions?.find(p => p.code === 'domain:delete'),
                    create: archMenu?.required_permissions?.find(p => p.code === 'domain:create'),
                    update: archMenu?.required_permissions?.find(p => p.code === 'domain:update'),
                    read: archMenu?.required_permissions?.find(p => p.code === 'domain:read')
                }
            };
        }""", role_id)

        record("保存 manage 分组", manage_result.get('saveSuccess', False))

        groups_m = manage_result.get('groups', {})
        perms_m = manage_result.get('perms', {})

        record("manage 分组 granted", groups_m.get('manage', {}).get('granted') == True)
        record("edit 分组随 manage granted", groups_m.get('edit', {}).get('granted') == True)
        record("view 分组随 manage granted", groups_m.get('view', {}).get('granted') == True)
        record("domain:delete include", perms_m.get('delete', {}).get('source') == 'include')
        record("domain:create include", perms_m.get('create', {}).get('source') == 'include')
        record("domain:update include", perms_m.get('update', {}).get('source') == 'include')
        record("domain:read 保持 auto", perms_m.get('read', {}).get('source') == 'auto')

        # ============================================================
        # Step 10: 测试 standalone 动作切换
        # ============================================================
        print("\n=== Step 10: 测试 standalone 动作切换 ===")

        standalone_test = await page.evaluate("""async (roleId) => {
            const loadResp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const loadData = await loadResp.json();
            const archMenu = loadData.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            const standalone = domainGroup?.standalone || [];

            if (standalone.length === 0) {
                return { hasStandalone: false, message: 'No standalone actions' };
            }

            // 测试 exclude 第一个 standalone 动作
            const firstAction = standalone[0];
            const saveResp = await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: [
                        { code: `domain:${firstAction.action}`, granted: false }
                    ]
                })
            });
            const saveResult = await saveResp.json();

            const reloadResp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const reloadData = await reloadResp.json();
            const reloadMenu = reloadData.data?.menus?.find(m => m.menu_code === 'arch-data');
            const reloadGroup = reloadMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');
            const reloadStandalone = reloadGroup?.standalone?.find(sp => sp.action === firstAction.action);

            return {
                hasStandalone: true,
                standaloneCount: standalone.length,
                firstAction: firstAction.action,
                saveSuccess: saveResult.success,
                beforeState: firstAction,
                afterState: reloadStandalone
            };
        }""", role_id)

        if standalone_test.get('hasStandalone'):
            record("standalone 动作存在", True, f"数量: {standalone_test.get('standaloneCount', 0)}")
            record("standalone exclude 保存", standalone_test.get('saveSuccess', False))
            after_state = standalone_test.get('afterState', {})
            record(f"standalone {standalone_test.get('firstAction')} excluded",
                   after_state.get('source') == 'exclude' and not after_state.get('granted'),
                   f"source={after_state.get('source')}, granted={after_state.get('granted')}")
        else:
            record("standalone 动作存在", False, standalone_test.get('message', 'No standalone'))

        # ============================================================
        # Step 11: 测试组合修改
        # ============================================================
        print("\n=== Step 11: 测试组合修改（同时修改多个权限） ===")

        combo_result = await page.evaluate("""async (roleId) => {
            // 同时 exclude domain:update, domain:delete，include domain:export
            const saveResp = await fetch(`/api/v2/roles/${roleId}/menu-permissions`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    menu_codes: ['arch-data'],
                    permissions: [
                        { code: 'domain:update', granted: false },
                        { code: 'domain:delete', granted: false },
                        { code: 'domain:export', granted: true }
                    ]
                })
            });
            const saveResult = await saveResp.json();

            const reloadResp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const reloadData = await reloadResp.json();
            const archMenu = reloadData.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                saveSuccess: saveResult.success,
                saveMessage: saveResult.message,
                groups: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                perms: {
                    update: archMenu?.required_permissions?.find(p => p.code === 'domain:update'),
                    delete: archMenu?.required_permissions?.find(p => p.code === 'domain:delete'),
                    export: domainGroup?.standalone?.find(sp => sp.action === 'export')
                }
            };
        }""", role_id)

        record("组合修改保存", combo_result.get('saveSuccess', False), combo_result.get('saveMessage', ''))

        groups_c = combo_result.get('groups', {})
        perms_c = combo_result.get('perms', {})

        record("组合: edit excluded", groups_c.get('edit', {}).get('source') == 'exclude')
        record("组合: manage excluded", groups_c.get('manage', {}).get('source') == 'exclude')
        record("组合: view 保持 auto", groups_c.get('view', {}).get('source') == 'auto')
        record("组合: domain:update excluded", perms_c.get('update', {}).get('source') == 'exclude')
        record("组合: domain:delete excluded", perms_c.get('delete', {}).get('source') == 'exclude')
        record("组合: domain:export include", perms_c.get('export', {}).get('source') == 'include')

        # ============================================================
        # Step 12: 最终刷新验证
        # ============================================================
        print("\n=== Step 12: 最终刷新验证 ===")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/complete_12_final.png")

        final_state = await page.evaluate("""async (roleId) => {
            const resp = await fetch(`/api/v2/roles/${roleId}/unified-permissions`);
            const data = await resp.json();
            const archMenu = data.data?.menus?.find(m => m.menu_code === 'arch-data');
            const domainGroup = archMenu?.bo_permission_groups?.find(g => g.bo_id === 'domain');

            return {
                groups: domainGroup ? {
                    view: domainGroup.groups.view,
                    edit: domainGroup.groups.edit,
                    manage: domainGroup.groups.manage
                } : null,
                perms: {
                    update: archMenu?.required_permissions?.find(p => p.code === 'domain:update'),
                    delete: archMenu?.required_permissions?.find(p => p.code === 'domain:delete'),
                    export: domainGroup?.standalone?.find(sp => sp.action === 'export')
                }
            };
        }""", role_id)

        groups_f = final_state.get('groups', {})
        perms_f = final_state.get('perms', {})

        record("最终: edit 仍 excluded", groups_f.get('edit', {}).get('source') == 'exclude')
        record("最终: manage 仍 excluded", groups_f.get('manage', {}).get('source') == 'exclude')
        record("最终: view 仍 auto", groups_f.get('view', {}).get('source') == 'auto')
        record("最终: domain:update 仍 excluded", perms_f.get('update', {}).get('source') == 'exclude')
        record("最终: domain:delete 仍 excluded", perms_f.get('delete', {}).get('source') == 'exclude')
        record("最终: domain:export 仍 include", perms_f.get('export', {}).get('source') == 'include')

        # ============================================================
        # 汇总
        # ============================================================
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        passed = sum(1 for _, p, _ in results if p)
        failed = sum(1 for _, p, _ in results if not p)
        total = len(results)
        print(f"  通过: {passed}/{total}")
        print(f"  失败: {failed}/{total}")

        if failed > 0:
            print("\n  失败项:")
            for name, p, detail in results:
                if not p:
                    print(f"    - {name}: {detail}")

        print(f"\n  截图目录: {SCREENSHOT_DIR}")

        await browser.close()

asyncio.run(main())
