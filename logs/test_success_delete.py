# -*- coding: utf-8 -*-
"""[FIX 2026-06-12] 测试成功删除空用户组时, success message 是否正确显示"""
import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    # 先用 SQL 插入一个全新的空组, 保证可删
    import sqlite3
    conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
    cur = conn.cursor()
    import time
    ts = f'success_test_{int(time.time())}'
    cur.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)", (f'{ts}_grp', f'{ts}_name'))
    gid = cur.lastrowid
    conn.commit()
    conn.close()
    print(f'Created empty group id={gid}')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        # 注入登录态 (用环境变量拿 token, 或 fallback 到 curl 拿)
        import os
        import urllib.request
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.open(urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin', method='GET'), timeout=10)
        for c in cj:
            if c.name == 'auth_token':
                token = c.value
                break
        if not token:
            print('FATAL: no auth token')
            return
        print(f'Got token: {token[:30]}...')
        await context.add_cookies([{
            'name': 'auth_token', 'value': token,
            'domain': 'localhost', 'path': '/',
        }])
        page = await context.new_page()
        page.on('console', lambda m: print(f'[console.{m.type}] {m.text[:200]}'))
        await page.goto('http://localhost:3004/user-permission?tab=user-groups')
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)
        # 直接调 batch-delete API, 走和 UI 完全一样的路径
        api_url = f'http://localhost:3010/api/v2/bo/user_group/batch-delete'
        resp = await page.request.post(api_url, data={'ids': [gid]})
        print(f'\n=== API 直接调用 ===')
        print(f'  status: {resp.status}')
        body = await resp.text()
        print(f'  body: {body}')

        # 模拟 UI: 通过页面里的 useMetaList handleBatchDelete 触发
        # 这是最关键的 — 看 UI 路径
        print(f'\n=== 模拟 UI handleBatchDelete (通过浏览器 fetch 走 httpClient) ===')
        result = await page.evaluate(f'''
            async () => {{
                const mod = await import('/src/composables/useMetaList.js')
                const {{ useMetaList }} = mod
                // 这里 useMetaList 是 factory, 我们手动构造一个 ctx
                // 实际 UI 路径就是 useMetaList() 返回的 handleBatchDelete
                // 直接调后端 batch-delete 看 httpClient 怎么处理 200 success
                const httpMod = await import('/src/utils/httpClient.js')
                const r = await httpMod.apiV2.post('/bo/user_group/batch-delete', {{ids: [{gid}]}})
                console.log('[UI httpClient result]', JSON.stringify(r, null, 2))
                return r
            }}
        ''')
        print(f'\nUI httpClient result.success = {result.get("success")}')
        print(f'UI httpClient result.success_count = {result.get("success_count")}')
        print(f'UI httpClient result.data = {result.get("data")}')
        print(f'UI httpClient result.errors = {result.get("errors")}')

        # 现在真实 UI: 跳到该组, 勾选, 批量删除
        print(f'\n=== 真实 UI: 搜索 + 勾选 + 删除 ===')
        await page.goto('http://localhost:3004/user-permission?tab=user-groups')
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)
        # 搜索
        search = page.locator('input[placeholder*="代码"], input[placeholder*="搜索"]').first
        if await search.count() > 0:
            await search.fill(f'{ts}_grp')
            await page.keyboard.press('Enter')
            await page.wait_for_timeout(1500)

        # 勾选第一行
        rows = page.locator('table tbody tr')
        n = await rows.count()
        print(f'  搜索结果: {n} 行')
        if n == 0:
            print('  ❌ 找不到组, 跳过 UI 测试')
        else:
            first_checkbox = rows.first.locator('input[type="checkbox"]')
            await first_checkbox.click()
            await page.wait_for_timeout(500)

            # 找批量删除按钮
            batch_btn = page.locator('button:has-text("批量删除")').first
            if await batch_btn.count() > 0:
                await batch_btn.click()
                await page.wait_for_timeout(500)
                # 确认
                confirm_btn = page.locator('.el-message-box button:has-text("确定")').first
                if await confirm_btn.count() > 0:
                    await confirm_btn.click()
                    # 抓 el-message / el-notification
                    await page.wait_for_timeout(500)
                    for t_ms in [50, 200, 500, 1000, 2000, 3500]:
                        await page.wait_for_timeout(t_ms if t_ms == 50 else (t_ms - [50,200,500,1000,2000,3500][[50,200,500,1000,2000,3500].index(t_ms)-1]))
                        msgs = await page.locator(".el-message, .el-notification").all()
                        if msgs:
                            for m in msgs:
                                text = (await m.text_content() or "").strip()
                                cls = (await m.get_attribute("class") or "")
                                print(f'  t={t_ms}ms: class={cls[:50]} text={text[:200]!r}')
                    await page.screenshot(path='d:/filework/excel-to-diagram/_success_msg.png', full_page=True)
                else:
                    print('  ❌ 确认弹窗没出现')
            else:
                print('  ❌ 批量删除按钮没出现')

        # 验证 DB 中已被删
        conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM user_groups WHERE id = ?', (gid,))
        n_after = cur.fetchone()[0]
        conn.close()
        print(f'\nDB 中 id={gid} 存在? {n_after > 0}')

        await browser.close()
        print('\n✅ 测试完成')

asyncio.run(main())
