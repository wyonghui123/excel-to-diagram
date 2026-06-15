# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 精细化 debug: 用 response 监听 + 多次 snapshot 抓 el-message
"""
import asyncio
import json
import sys
import urllib.request
from playwright.async_api import async_playwright


def http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if data is not None:
        req.data = data
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


async def main():
    base_url = "http://localhost:3004"

    body = json.dumps({"username": "admin", "password": "admin123"}).encode()
    status, data = http("POST", "http://localhost:3010/api/v2/action/user.authenticate",
                        headers={"Content-Type": "application/json"}, data=body)
    token = json.loads(data)["data"]["token"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)  # headed for visual
        context = await browser.new_context()
        await context.add_cookies([{
            "name": "auth_token", "value": token, "domain": "localhost", "path": "/"
        }])
        page = await context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append((msg.type, msg.text)))
        page.on("pageerror", lambda err: console_logs.append(("pageerror", str(err))))

        # 监听 batch-delete API 调用
        batch_delete_responses = []

        async def on_response(r):
            if 'batch-delete' in r.url:
                try:
                    txt = await r.text()
                except Exception:
                    txt = "<err>"
                batch_delete_responses.append((r.status, r.request.method, r.url, txt))
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        # 打开页面
        print("STEP 1: navigate")
        await page.goto(f"{base_url}/user-permission?tab=user-groups")
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # 找 482
        row = page.locator("tr:has-text('grp_b1281622'), tr:has-text('Test Group')").first
        await row.locator(".el-checkbox").first.click(force=True)
        await page.wait_for_timeout(500)
        print("STEP 2: selected")

        # 点批量删除
        batch_del = page.locator("button:has-text('批量删除')").first
        await batch_del.click()
        await page.wait_for_timeout(800)
        print("STEP 3: clicked batch delete")

        # 点确认
        confirm = page.locator(".el-message-box .el-button--primary, .el-message-box button:has-text('确定')").last
        print(f"  confirm btn count: {await confirm.count()}")
        if await confirm.count() == 0:
            # 截屏 + 兜底: 直接看 el-message-box HTML
            html = await page.content()
            import re
            box_match = re.search(r'el-message-box.*?</div>.*?</div>', html, re.DOTALL)
            if box_match:
                print(f"  el-message-box content (first 500): {box_match.group(0)[:500]}")
            await page.screenshot(path="d:/filework/excel-to-diagram/_dbg2_no_confirm.png", full_page=True)
            await browser.close()
            return 1
        await confirm.click()
        print("STEP 4: clicked confirm")

        # 抓 el-message 在多个时间点
        for t_ms in [50, 200, 500, 1000, 2000, 3500]:
            await page.wait_for_timeout(t_ms - (sum([50, 150, 300, 500, 1000, 1500][:[50, 200, 500, 1000, 2000, 3500].index(t_ms)+1])))
            msgs = await page.locator(".el-message, .el-notification").all()
            if msgs:
                for m in msgs:
                    text = (await m.text_content() or "").strip()
                    cls = (await m.get_attribute("class") or "")
                    print(f"  t={t_ms}ms: el-message class={cls[:60]} text={text[:200]!r}")
        # 截图 + 录屏截帧
        await page.screenshot(path="d:/filework/excel-to-diagram/_dbg2_final.png", full_page=True)
        await page.screenshot(path="d:/filework/excel-to-diagram/_dbg2_viewport.png")

        # API 调用
        print()
        print("BATCH-DELETE API CALLS:")
        for s, m, u, b in batch_delete_responses:
            print(f"  [{s}] {m} {u[:150]}")
            print(f"     body: {b[:500]}")

        # console 日志
        print()
        print("CONSOLE (relevant):")
        for typ, txt in console_logs:
            if any(k in txt.lower() for k in ['batch', 'delete', 'error', 'message', 'group', 'success']):
                print(f"  [{typ}] {txt[:200]}")

        # DB check
        import sqlite3
        conn = sqlite3.connect("meta/architecture.db")
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM user_groups WHERE id=482")
        print()
        print(f"DB: user_group 482 = {cur.fetchone()}")

        await browser.close()


asyncio.run(main())
