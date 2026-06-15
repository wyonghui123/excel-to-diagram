#!/usr/bin/env python3
"""Test EnumService import directly via dynamic import in browser"""
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: console_logs.append(f'[pageerror] {err}'))

        await page.goto('http://localhost:3004/', timeout=20000)
        await page.wait_for_load_state('networkidle', timeout=15000)

        # Login
        await page.evaluate("""async () => {
            await fetch('/api/v1/auth/dev-login?username=admin', {credentials: 'include'});
        }""")

        # Try dynamic import
        result = await page.evaluate("""async () => {
            try {
                const mod = await import('/src/services/enumService.js');
                const svc = mod.default || mod.EnumService;
                return {
                    hasMod: !!mod,
                    hasDefault: !!mod.default,
                    hasNamed: !!mod.EnumService,
                    defaultKeys: mod.default ? Object.keys(mod.default).slice(0, 10) : null,
                    hasCache: svc && svc._cache ? true : false,
                    cacheSize: svc && svc._cache ? svc._cache.size : -1,
                    cacheKeys: svc && svc._cache ? [...svc._cache.keys()] : null,
                };
            } catch (e) {
                return {error: e.message};
            }
        }""")
        print(f'Direct import test: {json.dumps(result, ensure_ascii=False, indent=2)}')

        # Try calling loadOptions directly
        load_result = await page.evaluate("""async () => {
            try {
                const mod = await import('/src/services/enumService.js');
                const svc = mod.default || mod.EnumService;
                if (!svc) return {error: 'no svc'};

                const dirResult = await svc.loadOptions('direction', { cache: true, throwError: false });
                const typeResult = await svc.loadOptions('relation_type', { cache: true, throwError: false });

                return {
                    dirCount: dirResult.length,
                    dirSample: dirResult[0],
                    typeCount: typeResult.length,
                    typeSample: typeResult[0],
                    cacheKeys: [...svc._cache.keys()],
                };
            } catch (e) {
                return {error: e.message, stack: e.stack};
            }
        }""")
        print(f'loadOptions result: {json.dumps(load_result, ensure_ascii=False, indent=2)}')

        await browser.close()

asyncio.run(main())
