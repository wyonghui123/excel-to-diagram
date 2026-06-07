# -*- coding: utf-8 -*-
"""
UI 端验证: business_object 创建后是否正确显示在列表中
- 直接调 dev-login,不依赖 storageState (避免过期)
"""
import asyncio
import time
from pathlib import Path

import requests
from playwright.async_api import async_playwright

APP = "http://localhost:3004"
BASE = "http://localhost:3010"


async def main():
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 先调 dev-login 拿 cookie (server 端 session)
    print(f"[1] Calling dev-login")
    api_sess = requests.Session()
    r = api_sess.get(f"{BASE}/api/v1/auth/dev-login?username=admin", timeout=10)
    print(f"[1] dev-login: {r.status_code}")
    if r.status_code != 200:
        print(f"[ERR] dev-login failed: {r.text[:200]}")
        return 1

    # 2. 抓 cookies
    cookies = api_sess.cookies.get_dict()
    print(f"[2] Got cookies: {list(cookies.keys())}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 3. 把 cookies 加到 browser context
        context = await browser.new_context()
        await context.add_cookies([
            {
                "name": name,
                "value": value,
                "url": APP,
            }
            for name, value in cookies.items()
        ])
        pg = await context.new_page()

        # 4. 抓 console + page error
        console_errors = []
        page_errors = []
        pg.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        pg.on("pageerror", lambda err: page_errors.append(str(err)))

        # 5. 导航
        target_url = f"{APP}/system/archdata"
        print(f"[3] Navigating to: {target_url}")
        try:
            await pg.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            print(f"[3] Navigation done")
        except Exception as e:
            print(f"[3][ERR] Navigation: {e}")
            await browser.close()
            return 1

        await asyncio.sleep(3)
        print(f"[4] Current URL: {pg.url}")

        # 6. 截图
        await pg.screenshot(path=str(out_dir / "ui_archdata_state.png"), full_page=True)
        print(f"[5] Screenshot: {out_dir / 'ui_archdata_state.png'}")

        # 7. 抓页面文本
        body_text = await pg.evaluate("() => document.body?.innerText?.substring(0, 800) || ''")
        print(f"[6] Body text (first 800):")
        print(body_text[:800])

        # 8. 健康检查
        if page_errors:
            print(f"[7] Page errors: {page_errors[:3]}")
        if console_errors:
            print(f"[8] Console errors: {console_errors[:3]}")
        if not page_errors and not console_errors:
            print(f"[7] No JS errors")

        # 9. 关键: 找 BO 新建入口
        new_btns = pg.get_by_role("button", name="新建")
        new_count = await new_btns.count()
        print(f"[9] 新建 button count: {new_count}")

        if new_count > 0:
            await new_btns.first.click()
            await asyncio.sleep(1)

            # 找代码 + 名称字段
            code_input = pg.get_by_label("代码", exact=False)
            if await code_input.count() == 0:
                code_input = pg.get_by_label("编码", exact=False)
            name_input = pg.get_by_label("名称", exact=False)

            test_code = f"E2E_UI_{int(time.time())}"
            if await code_input.count() > 0:
                await code_input.first.fill(test_code)
                print(f"[10] Filled code: {test_code}")
            else:
                print(f"[10][WARN] Code input not found")
            if await name_input.count() > 0:
                await name_input.first.fill("UI验证BO")
                print(f"[10] Filled name")
            else:
                print(f"[10][WARN] Name input not found")

            await asyncio.sleep(0.5)
            await pg.screenshot(path=str(out_dir / "ui_archdata_form.png"), full_page=True)

            # 11. 保存
            save_btn = pg.get_by_role("button", name="保存")
            save_count = await save_btn.count()
            print(f"[11] Save button count: {save_count}")
            if save_count > 0:
                await save_btn.first.click()
                print(f"[11] Clicked 保存")
                await asyncio.sleep(3)

            # 12. 截图保存后
            await pg.screenshot(path=str(out_dir / "ui_archdata_after_save.png"), full_page=True)
            print(f"[12] Screenshot after save: {out_dir / 'ui_archdata_after_save.png'}")

            # 13. 关键检查: 表格中是否出现 test_code
            html = await pg.content()
            if test_code in html:
                print(f"[OK] BO {test_code} FOUND in DOM after save")
            else:
                print(f"[BUG-UI] BO {test_code} NOT found in DOM after save")
                # 但可能抽屉未关闭
                dialog_visible = await pg.locator(".el-dialog__wrapper:not([style*='display: none']), .el-drawer__open").is_visible()
                print(f"      Dialog/drawer visible: {dialog_visible}")
                # 看一下是否有成功提示
                success_msgs = await pg.locator(".el-message--success, [class*='success']").all_text_contents()
                if success_msgs:
                    print(f"      Success messages: {success_msgs[:3]}")

            # 14. 关闭抽屉后再检查
            cancel_btn = pg.get_by_role("button", name="取消")
            if await cancel_btn.count() > 0:
                await cancel_btn.first.click()
                await asyncio.sleep(1)
            close_btn = pg.locator(".el-dialog__close, .el-drawer__close-btn")
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await asyncio.sleep(1)
            # 再找一次
            html_after = await pg.content()
            if test_code in html_after:
                print(f"[OK] BO {test_code} FOUND in DOM after closing drawer")
            else:
                print(f"[BUG-UI] BO {test_code} still NOT in DOM after closing drawer")
                await pg.screenshot(path=str(out_dir / "ui_archdata_final.png"), full_page=True)
                print(f"      Final screenshot: {out_dir / 'ui_archdata_final.png'}")

        await browser.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
