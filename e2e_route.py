"""E2E 请求拦截: 确认前端是否真的发了请求"""
import asyncio
from test_helpers.browser_auth import authenticated_page


async def main():
    print('=' * 70)
    print('E2E 请求拦截: 确认前端是否发请求')
    print('=' * 70)

    async with authenticated_page(target_url='/user-permission?tab=users') as page:
        # 用 route 拦截所有请求
        requests_log = []
        
        async def log_route(route):
            req = route.request
            if '/api/' in req.url and req.method == 'GET':
                requests_log.append({'url': req.url, 'method': req.method})
            await route.continue_()
        
        await page.route('**/*', log_route)

        # 切到用户 tab
        try:
            user_tab = page.get_by_role('tab', name='用户').first
            await user_tab.wait_for(state='visible', timeout=10000)
            await user_tab.click()
        except Exception:
            page.locator('.el-tabs__item:has-text("用户"), [role="tab"]:has-text("用户")').first.click()

        await page.wait_for_selector('.el-table__body tbody tr', timeout=15000)
        await page.wait_for_timeout(2000)
        
        print(f'\n[初始加载后] API 请求: {len(requests_log)} 条')
        for r in requests_log:
            print(f'  {r["method"]} {r["url"][:80]}')

        # 清空日志
        initial_count = len(requests_log)
        
        # 找变更时间列下标
        headers = await page.evaluate("""() => {
            const headers = document.querySelectorAll('.el-table__header thead th');
            return Array.from(headers).map(h => (h.querySelector('.cell') || h).innerText.trim());
        }""")
        idx = next((i for i, h in enumerate(headers) if '变更' in h), None)
        if idx is None:
            print('[FAIL] 找不到变更时间列')
            return
        header = page.locator('.el-table__header thead th').nth(idx)

        # 点击列头
        print(f'\n[点击"变更时间"列头]')
        await header.click()
        await page.wait_for_timeout(3000)

        new_requests = requests_log[initial_count:]
        print(f'\n[点击后] 新 API 请求: {len(new_requests)} 条')
        for r in new_requests:
            print(f'  {r["method"]} {r["url"][:120]}')

        # 再点一次
        initial_count = len(requests_log)
        await header.click()
        await page.wait_for_timeout(3000)

        new_requests = requests_log[initial_count:]
        print(f'\n[再次点击后] 新 API 请求: {len(new_requests)} 条')
        for r in new_requests:
            print(f'  {r["method"]} {r["url"][:120]}')


if __name__ == '__main__':
    asyncio.run(main())
