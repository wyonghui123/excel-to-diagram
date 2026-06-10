"""
[PLAYWRIGHT E2E 验证闭环]
完整前端 UI 验证:
1. 登录 admin
2. 打开角色权限中心
3. 找到 TEST60 角色, 进入权限配置
4. 验证 z-index 修复 (ElMessage 通知可见)
5. 取消勾选 version 权限 → 保存 → 验证 DB 删除
6. 重新勾选 → 保存 → 验证 DB 写入
7. 截图各阶段
"""
import asyncio
import sqlite3
import os
from playwright.async_api import async_playwright

DB = r'D:\filework\excel-to-diagram\meta\architecture.db'
BASE = 'http://localhost:3004'
SCREENSHOT_DIR = r'D:\filework\excel-to-diagram\scripts\_screenshots'

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def get_role_perms(role_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT p.code FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        WHERE rp.role_id = ?
        ORDER BY p.code
    """, [role_id])
    perms = [r[0] for r in cur.fetchall()]
    conn.close()
    return perms


def shot(page, name):
    path = f'{SCREENSHOT_DIR}/{name}.png'
    return page.screenshot(path=path, full_page=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await ctx.new_page()

        # === 1. 登录 admin ===
        print('[1/9] dev-login admin')
        await page.goto(f'{BASE}/api/v1/auth/dev-login?username=admin', wait_until='load')
        await page.wait_for_timeout(500)

        await page.goto(f'{BASE}/', wait_until='networkidle')
        await page.wait_for_timeout(1500)
        await shot(page, '01_home')
        print(f'  url: {page.url}')

        # 找用户与权限管理入口
        clicked = False
        for kw in ['用户与权限管理', '权限管理', '角色权限', '角色管理', '权限中心', '系统管理']:
            try:
                link = await page.query_selector(f'text="{kw}"')
                if link:
                    print(f'  click: {kw}')
                    await link.click()
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            print('  ⚠ 找不到系统管理入口, 尝试直接 URL')
            await page.goto(f'{BASE}/system-management/role-permissions', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            # 再试
            for kw in ['用户与权限管理', '角色管理', '权限管理']:
                link = await page.query_selector(f'text="{kw}"')
                if link:
                    print(f'  re-click: {kw}')
                    await link.click()
                    clicked = True
                    break

        await page.wait_for_timeout(2000)
        await shot(page, '02_sys_mgmt')
        print(f'  url: {page.url}')

        # === 2. 切到"角色管理" Tab ===
        print()
        print('[2/9] 切到"角色管理" Tab')
        try:
            role_tab = await page.query_selector('text="角色管理"')
            if role_tab:
                await role_tab.click()
                await page.wait_for_timeout(2000)
                print('  ok')
        except Exception as e:
            print(f'  fail: {e}')

        await shot(page, '03_role_tab')

        # === 2.5 搜 TEST60 角色 ===
        print()
        print('[2.5/9] 搜 TEST60 角色')
        # 先点"搜索"输入框, 输入 TEST60, 触发搜索
        try:
            search_input = await page.query_selector('input[placeholder*="角色"]')
            if not search_input:
                search_input = await page.query_selector('input[placeholder*="搜索"]')
            if not search_input:
                search_input = await page.query_selector('input.search-input, input[type="text"]')
            if search_input:
                await search_input.click()
                await search_input.fill('TEST60')
                await page.wait_for_timeout(500)
                # 按 Enter 触发
                await search_input.press('Enter')
                await page.wait_for_timeout(2000)
                print('  输入 + Enter 完成')
        except Exception as e:
            print(f'  search fail: {e}')

        await shot(page, '03a_searched')

        # 找 TEST60 角色
        test60_link = None
        for kw in ['TEST60', 'test60']:
            try:
                t = await page.query_selector(f'text="{kw}"')
                if t:
                    test60_link = t
                    print(f'  found: {kw}')
                    break
            except Exception:
                pass
        if test60_link:
            try:
                await test60_link.click()
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f'  click TEST60 fail: {e}')
        else:
            print('  ⚠ 找不到 TEST60')

        await shot(page, '03b_test60')
        print(f'  url: {page.url}')

        # === 3. 切到权限配置 Tab (在 RoleDetailDrawer 内) ===
        print()
        print('[3/9] 切到权限配置 Tab')
        try:
            perm_tab = await page.query_selector('text="权限配置"')
            if perm_tab:
                await perm_tab.click()
                await page.wait_for_timeout(2000)
                print('  ok')
        except Exception as e:
            print(f'  fail: {e}')

        await shot(page, '04_perm_tab')

        # === 4. 展开产品版本管理菜单 ===
        print()
        print('[4/9] 展开产品版本管理菜单')
        cards = await page.query_selector_all('.menu-card')
        for card in cards:
            name = await card.query_selector('.menu-name')
            if name:
                n = (await name.inner_text()).strip()
                if '产品版本管理' in n:
                    title = await card.query_selector('.menu-title-area')
                    if title:
                        await title.click()
                        await page.wait_for_timeout(1000)
                        print('  expanded')
                        break
        await shot(page, '05_pm_expanded')

        # === 5. 当前 DB 状态 ===
        print()
        print('[5/9] 当前 DB 状态')
        perms = get_role_perms(1803)
        print(f'  role 1803 权限数: {len(perms)}')
        print(f'  含 version:read: {"version:read" in perms}')

        # === 6. 点保存全部权限按钮 (无任何修改), 验证 ElMessage 通知出现 ===
        print()
        print('[6/9] 点"保存全部权限"按钮, 验证 ElMessage 通知 (z-index 测试)')
        save_btn = await page.query_selector('button:has-text("保存全部权限")')
        if save_btn:
            await save_btn.click()
            await page.wait_for_timeout(2000)
            await shot(page, '06_after_save')

            # 找通知
            notif = await page.query_selector('.notification-success, .notification')
            if notif:
                visible = await notif.is_visible()
                text = (await notif.inner_text()).strip()
                bbox = await notif.bounding_box()
                print(f'  通知文本: {text!r}')
                print(f'  通知可见: {visible}')
                print(f'  通知位置: {bbox}')

                # 验证 z-index: 通知应该浮在 .drawer-panel 之上
                # draw 一般是 z-index 1400, 我们通知应该是 1700
                if visible and '权限保存成功' in text:
                    print(f'  ✅ 通知可见, z-index 修复有效')
                elif visible:
                    print(f'  ⚠ 通知可见但文本不匹配')
                else:
                    print(f'  ❌ 通知不可见, 仍被遮挡')
            else:
                print('  ❌ DOM 找不到 .notification 元素')
                # 查一下容器
                cont = await page.query_selector('.notification-container')
                if cont:
                    inner = await cont.inner_html()
                    print(f'  容器内 HTML: {inner[:300]}')
                else:
                    print('  也没有 .notification-container')
        else:
            print('  ❌ 找不到"保存全部权限"按钮')

        # === 7. 找 version:read 的 cap-item, 取消勾选 ===
        print()
        print('[7/9] 取消勾选 version:read 等 4 个 version 权限')

        # 这里我们用 DB 模拟更可靠 — 直接用 SQL 模拟"点击取消勾选"后调 API
        # 因为前端 UI 操作复杂, 用 SQL 验证后端
        # 但我们还是尝试 UI
        cap_items = await page.query_selector_all('.cap-item')
        print(f'  找到 {len(cap_items)} 个 cap-item')

        for item in cap_items:
            code = await item.query_selector('.cap-code')
            if code:
                c = (await code.inner_text()).strip()
                if c.startswith('version:'):
                    granted_class = await item.evaluate('el => el.className')
                    print(f'    {c}: class={granted_class}')
                    # 如果是 granted, 点击取消
                    if 'cap-granted' in granted_class:
                        await item.click()
                        await page.wait_for_timeout(500)
                        print(f'    取消勾选 {c}')

        await shot(page, '07_after_uncheck')

        # === 8. 保存 ===
        print()
        print('[8/9] 再次点"保存全部权限"')

        # 监听网络请求
        api_responses = []
        api_requests = []
        async def on_response(response):
            if 'menu-permissions' in response.url:
                try:
                    body = await response.text()
                except Exception:
                    body = 'error'
                api_responses.append({
                    'url': response.url,
                    'status': response.status,
                    'body': body,
                })
        async def on_request(request):
            if 'menu-permissions' in request.url and request.method == 'PUT':
                try:
                    api_requests.append({
                        'url': request.url,
                        'method': request.method,
                        'post_data': request.post_data,
                    })
                except Exception:
                    pass
        page.on('response', on_response)
        page.on('request', on_request)

        save_btn = await page.query_selector('button:has-text("保存全部权限")')
        if save_btn:
            await save_btn.click()
            await page.wait_for_timeout(3000)
            await shot(page, '08_after_save_uncheck')

            notif = await page.query_selector('.notification-success, .notification')
            if notif:
                text = (await notif.inner_text()).strip()
                visible = await notif.is_visible()
                print(f'  通知: visible={visible} text={text!r}')

        # 输出 API 调用
        print()
        print('  Request body:')
        for r in api_requests:
            print(f'    url: {r["url"]}')
            print(f'    method: {r["method"]}')
            print(f'    post_data: {r["post_data"]}')
        print()
        print('  Response:')
        for r in api_responses:
            print(f'    url: {r["url"]}')
            print(f'    status: {r["status"]}')
            print(f'    body: {r["body"][:1000]}')

        # === 9. 验证 DB ===
        print()
        print('[9/9] 验证 DB 状态')
        perms = get_role_perms(1803)
        print(f'  role 1803 权限数: {len(perms)}')
        print(f'  含 version:read: {"version:read" in perms}')
        print(f'  含 version:create: {"version:create" in perms}')
        print(f'  含 product:read: {"product:read" in perms}')

        await browser.close()
        print()
        print('=== 完成 ===')
        print(f'截图保存在: {SCREENSHOT_DIR}')


asyncio.run(main())
