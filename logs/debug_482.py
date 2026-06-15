# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 完整 debug：抓取所有 console / network / UI
模拟用户实际操作: 选 482 (Test Group) → 批量删除
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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies([{
            "name": "auth_token", "value": token, "domain": "localhost", "path": "/"
        }])
        page = await context.new_page()

        # 完整记录 console
        console_logs = []
        page.on("console", lambda msg: console_logs.append((msg.type, msg.text)))
        # 完整记录 network responses
        api_responses = []
        page.on("response", lambda r: api_responses.append((r.status, r.request.method, r.url, r.text))
                if '/api/' in r.url else None)

        # 打开页面
        print("=" * 70)
        print("STEP 1: navigate /user-permission?tab=user-groups")
        print("=" * 70)
        await page.goto(f"{base_url}/user-permission?tab=user-groups")
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # 找 482 行 (Test Group / grp_b1281622)
        print()
        print("=" * 70)
        print("STEP 2: find row id=482 (Test Group)")
        print("=" * 70)
        # 482 这个 id 前端可能不直接显示, 但 row 的 data 应该有 id
        # 找包含 grp_b1281622 或 Test Group 的行
        row = page.locator("tr:has-text('grp_b1281622'), tr:has-text('Test Group')").first
        row_count = await row.count()
        print(f"  row count for grp_b1281622/Test Group: {row_count}")
        if row_count == 0:
            print("  [ERROR] row not found in page")
            await page.screenshot(path="d:/filework/excel-to-diagram/_dbg_ug_no_row.png", full_page=True)
            # 看看页面有什么
            html = await page.content()
            if 'grp_b1281622' in html:
                print("  but 'grp_b1281622' IS in page HTML")
            else:
                print("  'grp_b1281622' NOT in page HTML (probably on different page)")
            await browser.close()
            return 1

        # 勾选该行
        print()
        print("=" * 70)
        print("STEP 3: select row 482")
        print("=" * 70)
        chk = row.locator(".el-checkbox").first
        if await chk.count() > 0:
            await chk.click(force=True)
            await page.wait_for_timeout(500)
            print("  selected")
        else:
            print("  [WARN] no checkbox in row")
        await page.screenshot(path="d:/filework/excel-to-diagram/_dbg_ug_selected.png", full_page=True)

        # 找批量删除按钮
        print()
        print("=" * 70)
        print("STEP 4: find and click '批量删除' button")
        print("=" * 70)
        # 列出所有可见按钮文本
        all_btns = await page.locator("button:visible").all()
        btn_texts = []
        for b in all_btns:
            t = (await b.text_content() or "").strip()
            cls = await b.get_attribute("class") or ""
            if t and t != "":
                btn_texts.append((t, cls[:60]))
        print(f"  visible buttons ({len(btn_texts)}):")
        for t, c in btn_texts[:30]:
            print(f"    {t!r:30s} class={c}")

        # 找 "批量删除" 按钮
        batch_del = page.locator("button:has-text('批量删除')").first
        if await batch_del.count() == 0:
            print("  [WARN] no '批量删除' button visible, try other variants")
            batch_del = page.locator("button:has-text('删除')").last
        print(f"  batch delete button found: {await batch_del.count() > 0}")
        if await batch_del.count() == 0:
            await page.screenshot(path="d:/filework/excel-to-diagram/_dbg_ug_no_batch.png", full_page=True)
            print("  [FATAL] cannot find batch delete button")
            await browser.close()
            return 1

        # 点击批量删除
        await batch_del.click()
        await page.wait_for_timeout(800)
        await page.screenshot(path="d:/filework/excel-to-diagram/_dbg_ug_confirm.png", full_page=True)

        # 找确认弹窗的"确定"按钮
        print()
        print("=" * 70)
        print("STEP 5: confirm delete")
        print("=" * 70)
        confirm = page.locator(".el-message-box .el-button--primary, .el-message-box button:has-text('确定')").last
        print(f"  confirm btn found: {await confirm.count() > 0}")
        if await confirm.count() == 0:
            print("  [WARN] no confirm button")
            await browser.close()
            return 1
        await confirm.click()
        await page.wait_for_timeout(4000)  # 等 API 响应 + 弹窗
        await page.screenshot(path="d:/filework/excel-to-diagram/_dbg_ug_after.png", full_page=True)

        # 抓所有 el-notification / el-message DOM
        print()
        print("=" * 70)
        print("STEP 6: dump all notifications / messages in DOM")
        print("=" * 70)
        notifications = await page.locator(".el-notification, .el-message, .el-message-box").all()
        print(f"  found {len(notifications)} notification/message elements")
        for i, n in enumerate(notifications):
            text = (await n.text_content() or "").strip()
            cls = await n.get_attribute("class") or ""
            visible = await n.is_visible()
            print(f"  [{i}] visible={visible} class={cls[:80]} text={text[:200]!r}")

        # console
        print()
        print("=" * 70)
        print("CONSOLE LOGS")
        print("=" * 70)
        for t, txt in console_logs[-30:]:
            print(f"  [{t}] {txt[:200]}")

        # api responses
        print()
        print("=" * 70)
        print("API RESPONSES (last 10)")
        print("=" * 70)
        for status, method, url, body in api_responses[-10:]:
            print(f"  [{status}] {method} {url[:150]}")
            print(f"     body: {body[:300] if body else 'None'}")

        # 验证 DB
        print()
        print("=" * 70)
        print("STEP 7: verify DB")
        print("=" * 70)
        import sqlite3
        conn = sqlite3.connect("meta/architecture.db")
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM user_groups WHERE id=482")
        row482 = cur.fetchone()
        print(f"  user_group 482 in DB: {row482}")
        if row482:
            print("  [BUG? CANDIDATE] 482 still exists — but did UI show error?")
        else:
            print("  ❌ 482 DELETED - BUG CONFIRMED!")

        await browser.close()


asyncio.run(main())
