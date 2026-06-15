#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test deep insert with unique code and capture full payload"""
import asyncio
import json
import time
import random
from playwright.async_api import async_playwright

async def main():
    unique_suffix = f"{int(time.time())}_{random.randint(1000,9999)}"
    product_code = f"AUTOTEST_{unique_suffix}"
    product_name = f"AutoTest Product {unique_suffix}"
    version_name = f"v1.0_{unique_suffix}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Collect console logs and API requests
        console_logs = []
        api_logs = []
        api_requests = []
        page.on('console', lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on('pageerror', lambda err: console_logs.append(f"[PAGE ERROR] {err}"))

        async def log_request(req):
            if '/api/v2/bo/product/deep' in req.url:
                try:
                    body = req.post_data
                    api_requests.append(f"REQUEST: {req.method} {req.url} body={body}")
                except:
                    api_requests.append(f"REQUEST: {req.method} {req.url}")
        page.on('request', lambda r: asyncio.create_task(log_request(r)))

        async def log_response(resp):
            if '/api/v2/bo/product' in resp.url:
                try:
                    body = await resp.json()
                    api_logs.append(f"[{resp.status}] {resp.request.method} {resp.url} -> {json.dumps(body, ensure_ascii=False)[:400]}")
                except:
                    api_logs.append(f"[{resp.status}] {resp.request.method} {resp.url}")
        page.on('response', lambda r: asyncio.create_task(log_response(r)))

        # Step 1: Login
        await page.goto('http://localhost:3004/')
        await page.wait_for_load_state('networkidle')
        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_load_state('networkidle')

        # Step 2: Navigate to product list
        await page.goto('http://localhost:3004/product-management', wait_until='networkidle')
        await page.wait_for_timeout(3000)

        # Step 3: Click "New Product" button
        new_btn = page.locator('button:has-text("新建产品")').first
        await new_btn.click()
        await page.wait_for_timeout(3000)

        # Step 4: Fill in product details
        name_input = page.locator('input[placeholder="请输入名称"]').first
        await name_input.fill(product_name)
        code_input = page.locator('input[placeholder="请输入产品编码"]').first
        await code_input.fill(product_code)

        # Step 5: Click "新建" button in version list
        all_new_btns = await page.query_selector_all('button:has-text("新建")')
        for btn in reversed(all_new_btns):
            try:
                if await btn.is_visible():
                    text = (await btn.text_content() or '').strip()
                    if text == '新建':
                        await btn.click()
                        break
            except:
                pass

        await page.wait_for_timeout(2000)

        # Step 6: Fill in version name
        all_inputs = await page.query_selector_all('input')
        for inp in all_inputs:
            try:
                if await inp.is_visible():
                    ph = await inp.get_attribute('placeholder') or ''
                    val = await inp.input_value()
                    if '版本' in ph and val == '':
                        await inp.fill(version_name)
                        break
            except:
                pass

        await page.wait_for_timeout(1000)

        # Step 7: Click Save
        save_btn = page.locator('button:has-text("保存")').first
        await save_btn.click()
        await page.wait_for_timeout(5000)

        # Print all captured data
        print("="*60)
        print(f"PRODUCT CODE: {product_code}")
        print(f"VERSION NAME: {version_name}")
        print("="*60)
        print("\nREQUESTS:")
        for log in api_requests:
            print(log)
        print("\nRESPONSES:")
        for log in api_logs:
            print(log)
        print("\nDEEP INSERT RELATED CONSOLE LOGS:")
        for log in console_logs:
            if 'Deep' in log or 'deep' in log:
                print(log)

        await browser.close()

asyncio.run(main())
