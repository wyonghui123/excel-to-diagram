#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test the user's scenario: create new product + new version in one go (V2)"""
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Collect console logs
        console_logs = []
        api_logs = []
        page.on('console', lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on('pageerror', lambda err: console_logs.append(f"[PAGE ERROR] {err}"))

        async def log_response(resp):
            if '/api/v2/bo/product' in resp.url or '/api/v2/bo/version' in resp.url:
                try:
                    body = await resp.json()
                    api_logs.append(f"[{resp.status}] {resp.request.method} {resp.url} -> {json.dumps(body, ensure_ascii=False)[:300]}")
                except:
                    api_logs.append(f"[{resp.status}] {resp.request.method} {resp.url}")
        page.on('response', lambda r: asyncio.create_task(log_response(r)))

        # Step 1: Login
        print("[1] Login")
        await page.goto('http://localhost:3004/')
        await page.wait_for_load_state('networkidle')

        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_load_state('networkidle')

        # Step 2: Navigate to product list
        print("[2] Navigate to product list")
        await page.goto('http://localhost:3004/product-management', wait_until='networkidle')
        await page.wait_for_timeout(3000)

        # Step 3: Click "New Product" button
        print("[3] Click 'New Product' button")
        new_btn = page.locator('button:has-text("新建产品")').first
        await new_btn.click()
        await page.wait_for_timeout(3000)

        # Step 4: Fill in product details
        print("[4] Fill in product details")
        name_input = page.locator('input[placeholder="请输入名称"]').first
        await name_input.fill('TestProduct_AutoTest')
        code_input = page.locator('input[placeholder="请输入产品编码"]').first
        await code_input.fill('TST_AUTO')

        # Print context around version list
        print("[5] Click '新建' button in version list section")
        # Find the version list section first, then click "新建" within it
        # The version list section should be below the basic info
        # Use a more specific selector
        all_new_btns = await page.query_selector_all('button:has-text("新建")')
        print(f"  Found {len(all_new_btns)} '新建' buttons total")
        for i, btn in enumerate(all_new_btns):
            try:
                text = await btn.text_content()
                visible = await btn.is_visible()
                print(f"  [{i}] visible={visible} text='{text.strip()[:30]}'")
            except:
                pass

        # Click the LAST visible "新建" button (should be in the version list section)
        clicked = False
        for btn in reversed(all_new_btns):
            try:
                if await btn.is_visible():
                    text = (await btn.text_content() or '').strip()
                    await btn.click()
                    print(f"  [OK] Clicked: '{text[:30]}'")
                    clicked = True
                    break
            except:
                pass

        if not clicked:
            print("  [WARN] Could not click any 新建 button")

        await page.wait_for_timeout(2000)

        # Take screenshot to see what's in the version list
        await page.screenshot(path='/tmp/screenshot_after_new.png', full_page=True)

        # Step 6: Look for the new row input
        print("[6] Look for new row input")
        all_inputs = await page.query_selector_all('input')
        print(f"  Found {len(all_inputs)} inputs after add")
        version_input = None
        for i, inp in enumerate(all_inputs):
            try:
                ph = await inp.get_attribute('placeholder') or ''
                val = await inp.input_value()
                visible = await inp.is_visible()
                if visible and val == '' and '版本' in ph:
                    version_input = inp
                    print(f"  [OK] Found version name input: [{i}] placeholder='{ph}'")
                    break
                # Print all visible ones for debug
                if visible and (val or 'name' in ph.lower() or '版本' in ph):
                    print(f"  [{i}] visible={visible} placeholder='{ph}' value='{val}'")
            except:
                pass

        if version_input:
            await version_input.fill('v1.0_test')
            print("  [OK] Filled version name 'v1.0_test'")
        else:
            # Try filling the last empty visible input
            for inp in reversed(all_inputs):
                try:
                    if await inp.is_visible():
                        ph = await inp.get_attribute('placeholder') or ''
                        val = await inp.input_value()
                        if val == '' and ph == '':
                            await inp.fill('v1.0_test')
                            print("  [OK] Filled last empty input with 'v1.0_test'")
                            break
                except:
                    pass

        await page.wait_for_timeout(1000)

        # Step 7: Click Save
        print("[7] Click Save button")
        save_btn = page.locator('button:has-text("保存")').first
        await save_btn.click()
        await page.wait_for_timeout(5000)

        # Take screenshot
        await page.screenshot(path='/tmp/screenshot_after_save_v2.png', full_page=True)

        # Print API logs
        print("\n" + "="*60)
        print("API LOGS:")
        print("="*60)
        for log in api_logs:
            print(log)

        # Print relevant console logs
        print("\n" + "="*60)
        print("CONSOLE LOGS (relevant):")
        print("="*60)
        for log in console_logs:
            if 'Deep' in log or 'deep' in log or 'DetailPage' in log or 'UseMetaList' in log or 'draft' in log.lower():
                print(log)

        await browser.close()

asyncio.run(main())
