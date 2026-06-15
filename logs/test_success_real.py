# -*- coding: utf-8 -*-
"""跑真实成功删除, 验证三重通知都弹 (success 分支)"""
import asyncio
import sys
import time
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    import sqlite3
    conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
    cur = conn.cursor()
    ts = f'succ_{int(time.time())}'
    cur.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)", (f'{ts}_grp', f'{ts}_name'))
    gid = cur.lastrowid
    conn.commit()
    conn.close()
    print(f'Created empty group id={gid}, code={ts}_grp')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        import urllib.request, http.cookiejar
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        opener.open(urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin', method='GET'), timeout=10)
        for c in cj:
            if c.name == 'auth_token':
                token = c.value
                break
        await context.add_cookies([{
            'name': 'auth_token', 'value': token,
            'domain': 'localhost', 'path': '/',
        }])

        page = await context.new_page()
        await page.add_init_script("""
            window.__seenMessages = [];
            const obs = new MutationObserver(() => {
              document.querySelectorAll('.el-message, .el-notification, .el-message-box').forEach(el => {
                if (!el.__cap) {
                  el.__cap = true;
                  window.__seenMessages.push({
                    type: el.className,
                    text: (el.textContent || '').trim(),
                    time: Date.now(),
                  });
                }
              });
            });
            document.addEventListener('DOMContentLoaded', () => {
              obs.observe(document.body, {childList: true, subtree: true});
            });
        """)

        await page.goto('http://localhost:3004/user-permission?tab=user-groups')
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)

        # 搜索新创建的组
        search = page.locator('input[placeholder*="代码"], input[placeholder*="搜索"]').first
        if await search.count() > 0:
            await search.fill(f'{ts}_grp')
            await page.keyboard.press('Enter')
            await page.wait_for_timeout(1500)

        # 找 table
        await page.wait_for_selector('table', timeout=10000)
        rows = page.locator('table tbody tr')
        n = await rows.count()
        print(f'  搜索结果: {n} 行')
        if n == 0:
            print('  ❌ 找不到组, 跳过')
            await browser.close()
            return

        # 勾选第一行 (Element Plus 的 input[type=checkbox] 是隐藏的, 点 .el-checkbox 包裹的 span)
        first_cb = rows.first.locator('.el-checkbox').first
        await first_cb.click(force=True)
        await page.wait_for_timeout(500)

        # 点批量删除
        batch_btn = page.locator('button:has-text("批量删除")').first
        if await batch_btn.count() == 0:
            print('  ❌ 批量删除按钮没找到')
            await page.screenshot(path='d:/filework/excel-to-diagram/_no_batch_btn.png', full_page=True)
            await browser.close()
            return
        await batch_btn.click()
        await page.wait_for_timeout(500)
        # 确认
        confirm = page.locator('.el-message-box button:has-text("确定")').first
        await confirm.click()

        # 抓消息
        for t in [50, 200, 500, 1000, 2000, 3500]:
            await page.wait_for_timeout(300)
        seen = await page.evaluate('window.__seenMessages')
        print(f'\n=== 实际抓到的消息 ({len(seen)}) ===')
        for m in seen:
            print(f'  - type={m["type"][:60]}')
            print(f'    text={m["text"][:200]!r}')

        # 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/_success_msg.png', full_page=True)

        # 验证 DB
        conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM user_groups WHERE id = ?', (gid,))
        n_after = cur.fetchone()[0]
        conn.close()
        print(f'\nDB 中 id={gid} 仍存在? {n_after > 0}')

        await browser.close()
        print('\n✅ Done')

asyncio.run(main())
