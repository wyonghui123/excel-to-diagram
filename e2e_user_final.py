"""E2E 浏览器验证: 用户管理页变更时间排序"""
import asyncio
from test_helpers.browser_auth import authenticated_page

SCREENSHOT_DIR = r'd:\filework\excel-to-diagram\test-results\e2e_user_sort'


async def get_first_5_rows(page):
    return await page.evaluate("""() => {
        const rows = document.querySelectorAll('.el-table__body tbody tr');
        const out = [];
        for (let i = 0; i < Math.min(5, rows.length); i++) {
            const cells = rows[i].querySelectorAll('td');
            out.push({
                username: (cells[1]?.innerText || '').trim(),
                updated: (cells[7]?.innerText || '').trim(),
            });
        }
        return out;
    }""")


async def main():
    print('=' * 70)
    print('E2E 浏览器验证: 用户管理页变更时间排序')
    print('=' * 70)

    async with authenticated_page(target_url='/user-permission?tab=users') as page:
        # 切到用户 tab
        try:
            user_tab = page.get_by_role('tab', name='用户').first
            await user_tab.wait_for(state='visible', timeout=10000)
            await user_tab.click()
        except Exception:
            page.locator('.el-tabs__item:has-text("用户"), [role="tab"]:has-text("用户")').first.click()

        await page.wait_for_selector('.el-table__body tbody tr', timeout=15000)
        await page.wait_for_timeout(2000)
        print(f'\n[页面已加载]')

        # 初始状态
        before = await get_first_5_rows(page)
        print(f'\n[初始前 5 行]')
        for r in before:
            print(f'  {r}')

        # 截图初始
        await page.screenshot(path=fr'{SCREENSHOT_DIR}\e2e_01_before.png', full_page=True)

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

        # 点击列头（应该是 desc → asc 切换，或者 null → desc）
        print(f'\n[点击"变更时间"列头（第 {idx} 列）]')
        await header.click()
        await page.wait_for_timeout(3000)

        after_click1 = await get_first_5_rows(page)
        print(f'\n[点击 1 次后 前 5 行]')
        for r in after_click1:
            print(f'  {r}')

        await page.screenshot(path=fr'{SCREENSHOT_DIR}\e2e_02_click1.png', full_page=True)

        # 再点一次
        print(f'\n[再次点击"变更时间"列头]')
        await header.click()
        await page.wait_for_timeout(3000)

        after_click2 = await get_first_5_rows(page)
        print(f'\n[点击 2 次后 前 5 行]')
        for r in after_click2:
            print(f'  {r}')

        await page.screenshot(path=fr'{SCREENSHOT_DIR}\e2e_03_click2.png', full_page=True)

        # 验证
        print(f'\n[验证]')
        before_usernames = [r['username'] for r in before]
        after1_usernames = [r['username'] for r in after_click1]
        after2_usernames = [r['username'] for r in after_click2]

        if before_usernames != after1_usernames:
            print(f'  [OK] 首次点击后顺序变化了')
        else:
            print(f'  [FAIL] 首次点击后顺序未变')

        if after1_usernames != after2_usernames:
            print(f'  [OK] 再次点击后顺序又变化了')
        else:
            print(f'  [FAIL] 再次点击后顺序未变')


if __name__ == '__main__':
    asyncio.run(main())
