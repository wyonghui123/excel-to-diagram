# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 调试：dump 浏览器里 MetaListPage 实际状态
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

    # 登录
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

        await page.goto(f"{base_url}/user-permission?tab=user-groups")
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # 看表格里所有行 + 列
        print("=" * 70)
        print("TABLE HTML SNAPSHOT")
        print("=" * 70)
        # 找第一个数据行
        rows = page.locator("tbody tr")
        row_count = await rows.count()
        print(f"tbody rows: {row_count}")
        if row_count > 0:
            row0 = rows.first
            cells = row0.locator("td")
            cell_count = await cells.count()
            print(f"row 0 cells: {cell_count}")
            for i in range(cell_count):
                cell = cells.nth(i)
                text = await cell.text_content()
                inner_buttons = await cell.locator("button").count()
                inner_html = await cell.inner_html()
                print(f"  cell[{i}]: text={text!r}, buttons={inner_buttons}, html={inner_html[:200]}")

        # 找操作列
        print()
        print("=" * 70)
        print("LOOKING FOR ROW ACTION COLUMNS")
        print("=" * 70)
        action_cols = page.locator("td.action-column, .row-action-trigger, .el-dropdown")
        print(f"action columns: {await action_cols.count()}")
        if await action_cols.count() > 0:
            html = await action_cols.first.inner_html()
            print(f"first action col html: {html[:500]}")

        # 找所有 button
        all_buttons = await page.locator("button").all()
        print(f"all buttons on page: {len(all_buttons)}")
        for i, b in enumerate(all_buttons[:30]):
            text = (await b.text_content() or "").strip()
            cls = await b.get_attribute("class")
            if "删除" in text or "delete" in (cls or "").lower() or "row-action" in (cls or ""):
                print(f"  btn[{i}]: text={text!r}, class={cls}")

        await browser.close()


asyncio.run(main())
