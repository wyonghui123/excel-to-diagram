# -*- coding: utf-8 -*-
"""只测一次成功删除, 看 ElMessage.success 是否弹"""
import asyncio
import sys
import time
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    import sqlite3
    conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
    cur = conn.cursor()
    ts = f'success_{int(time.time())}'
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
        msgs_at = []
        page.on('console', lambda m: print(f'[console.{m.type}] {m.text[:200]}'))
        # 监听 el-message 出现
        await page.add_init_script("""
            window.__seenMessages = [];
            const observer = new MutationObserver(() => {
              document.querySelectorAll('.el-message, .el-notification').forEach(el => {
                if (!el.__captured) {
                  el.__captured = true;
                  window.__seenMessages.push({
                    type: el.className,
                    text: el.textContent || '',
                    time: Date.now(),
                  });
                }
              });
            });
            document.addEventListener('DOMContentLoaded', () => {
              observer.observe(document.body, {childList: true, subtree: true});
            });
        """)
        await page.goto('http://localhost:3004/user-permission?tab=user-groups')
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)

        # 直接用 page.evaluate 调 UI 路径 (复现 handleBatchDelete 内部)
        result = await page.evaluate(f'''
            async () => {{
                const httpMod = await import('/src/utils/httpClient.js')
                // 直接走 httpClient, 这是 useMetaList.handleBatchDelete 内部实际路径
                const r = await httpMod.apiV2.post('/bo/user_group/batch-delete', {{ids: [{gid}]}})
                console.log('[UI httpClient result]', JSON.stringify(r, null, 2))
                return r
            }}
        ''')
        print(f'\n=== handleBatchDelete result ===')
        print(f'  success = {result.get("success")}')
        print(f'  message = {result.get("message")!r}')

        # 走 useMetaList.handleBatchDelete 内部 success 分支 (这是用户实际点删除后的代码路径)
        await page.evaluate(f'''
            async () => {{
                // 直接调 window 上的 ElMessage (element-plus 在 main.js 暴露过)
                const EPlus = window.ElementPlus || (await import('element-plus'))
                const ElMessage = EPlus.ElMessage || (window).ElMessage
                if (ElMessage) {{
                    ElMessage.success('成功删除 1 条记录')
                    console.log('[useMetaList success branch] ElMessage.success fired')
                }} else {{
                    console.log('[FAIL] ElMessage not available')
                    console.log('  window keys:', Object.keys(window).filter(k => k.includes('El')))
                }}
            }}
        ''')
        await page.wait_for_timeout(2000)
        seen = await page.evaluate('window.__seenMessages')
        print(f'\n=== 实际看到的消息 ===')
        for m in seen:
            print(f'  - class={m["type"][:60]} text={m["text"][:200]!r}')

        # 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/_success_msg.png', full_page=True)

        await browser.close()
        print('\n✅ Done')

asyncio.run(main())
