"""
E2E 闭环验证: 用户管理页 -> 点 "变更时间" 列头 -> 验证排序生效

流程:
  1. authenticated_page 自动登录 (admin)
  2. 导航到 /user-permission?tab=users
  3. 切到 "用户" Tab
  4. 等待表格加载 (无变更时间排序)
  5. 截图 #1: 初始状态
  6. 点击 "变更时间" 列头
  7. 等待 API 重发 (sort_by=updated_at&order=desc)
  8. 截图 #2: 排序后状态
  9. 验证: 首行 username 与 API 验证 (admin) 一致
  10. 点击 "变更时间" 列头 (toggle to asc)
  11. 截图 #3: 升序状态
  12. 验证: 排序方向变化
"""
import asyncio
import json
import sys
from pathlib import Path

from test_helpers.browser_auth import authenticated_page, API_URL

SCREENSHOT_DIR = Path(r'd:\filework\excel-to-diagram\test-results\e2e_user_sort')
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def get_first_row_data(page):
    """从表格首行提取 username 和 updated_at 文本"""
    return await page.evaluate("""() => {
        const rows = document.querySelectorAll('.el-table__body tbody tr');
        if (rows.length === 0) return null;
        const cells = rows[0].querySelectorAll('td');
        return {
            cellCount: cells.length,
            // 取前 4 个单元格的文本（username/email/display_name/status 大致在前几列）
            cellTexts: Array.from(cells).slice(0, 5).map(c => c.innerText.trim()),
        };
    }""")


async def get_column_header_texts(page):
    """提取所有列头文本，找变更时间列的下标"""
    return await page.evaluate("""() => {
        const headers = document.querySelectorAll('.el-table__header thead th');
        return Array.from(headers).map(h => {
            // 列头里可能包了排序 caret span，去掉
            const contentEl = h.querySelector('.cell') || h;
            return contentEl.innerText.trim();
        });
    }""")


async def main():
    print('=' * 60)
    print('E2E 闭环验证: 用户管理页 -> 变更时间排序')
    print('=' * 60)

    # 0. 先用 API 拿基线数据，浏览器验证后做对比
    import requests
    api_baseline = {}
    s = requests.Session()
    s.get(f'{API_URL}/api/v1/auth/dev-login?username=admin')
    for order_dir in ['desc', 'asc']:
        r = s.get(f'{API_URL}/api/v1/users?page=1&page_size=5&sort_by=updated_at&order={order_dir}')
        data = r.json()
        if data.get('success'):
            api_baseline[order_dir] = [(u.get('username'), u.get('updated_at')) for u in data['data']]
    print('\n[API 基线]')
    for k, v in api_baseline.items():
        print(f'  {k}: {v}')

    async with authenticated_page(target_url='/user-permission?tab=users') as page:
        # 1. 切到"用户" Tab
        print('\n[1] 等待并切到"用户" Tab...')
        try:
            user_tab = page.get_by_role('tab', name='用户').first
            await user_tab.wait_for(state='visible', timeout=10000)
            await user_tab.click()
            print('  [OK] 已切到用户 Tab')
        except Exception as e:
            print(f'  [WARN] getByRole 失败，尝试备用 selector: {e}')
            user_tab = page.locator('.el-tabs__item:has-text("用户"), [role="tab"]:has-text("用户")').first
            await user_tab.wait_for(state='visible', timeout=10000)
            await user_tab.click()
            print('  [OK] (备用) 已切到用户 Tab')

        # 2. 等待表格加载
        print('\n[2] 等待用户表格加载...')
        try:
            await page.wait_for_selector('.el-table__body tbody tr', timeout=15000)
        except Exception as e:
            print(f'  [ERROR] 表格未出现: {e}')
            await page.screenshot(path=str(SCREENSHOT_DIR / '00-no-table.png'))
            return False

        row_count = await page.locator('.el-table__body tbody tr').count()
        print(f'  [OK] 表格有 {row_count} 行')

        # 3. 提取列头找"变更时间"列
        print('\n[3] 提取列头...')
        headers = await get_column_header_texts(page)
        print(f'  列头: {headers}')

        # 找包含"变更时间"/"更新时间"/"updated" 的列下标
        change_time_idx = None
        for i, h in enumerate(headers):
            if '变更' in h or '更新' in h or 'updated' in h.lower() or 'change' in h.lower():
                change_time_idx = i
                print(f'  [OK] "变更时间"列下标: {i} (header: {h!r})')
                break
        if change_time_idx is None:
            print(f'  [WARN] 未找到"变更时间"列！列头: {headers}')
            # 列出所有有 cell 的列，让用户知道有哪些列
            for i, h in enumerate(headers):
                if h:
                    print(f'    col {i}: {h!r}')

        # 4. 截图初始状态
        screenshot_initial = SCREENSHOT_DIR / '01-initial.png'
        await page.screenshot(path=str(screenshot_initial), full_page=True)
        print(f'\n[4] 截图: {screenshot_initial}')

        # 5. 记录初始首行
        first_row_initial = await get_first_row_data(page)
        print(f'  初始首行: {first_row_initial}')

        # 6. 点击"变更时间"列头（如果找到了）
        if change_time_idx is not None:
            print(f'\n[5] 点击"变更时间"列头 (第 {change_time_idx} 列)...')
            # 监听 API 请求
            api_calls = []

            async def on_request(req):
                if '/api/v1/users' in req.url and req.method == 'GET':
                    api_calls.append(req.url)

            page.on('request', on_request)

            # 点列头（click .cell 或 sortable caret）
            header_locator = page.locator('.el-table__header thead th').nth(change_time_idx)
            await header_locator.click()
            print('  [OK] 已点击列头')

            # 7. 等待 API 重发 + 表格更新
            try:
                await page.wait_for_function(
                    """() => {
                        const sortCaret = document.querySelector('.el-table__header .sort-caret.descending');
                        return sortCaret !== null;
                    }""",
                    timeout=8000,
                )
                print('  [OK] 排序 caret 已变成 descending')
            except Exception as e:
                print(f'  [WARN] 排序 caret 状态变化超时: {e}')

            await page.wait_for_timeout(1000)  # 让 UI 稳定一下

            # 8. 检查 API 调用是否包含 sort_by=updated_at
            sort_calls = [u for u in api_calls if 'sort_by' in u or 'ordering' in u]
            print(f'\n[6] 监听到的 API 调用: {len(api_calls)} 条')
            for c in api_calls[:5]:
                print(f'    {c}')
            if sort_calls:
                print(f'  [OK] 检测到排序 API 调用: {sort_calls[0]}')
            else:
                print('  [WARN] 未检测到带 sort 参数的 API 调用')

            # 9. 截图排序后状态
            screenshot_desc = SCREENSHOT_DIR / '02-sorted-desc.png'
            await page.screenshot(path=str(screenshot_desc), full_page=True)
            print(f'  截图: {screenshot_desc}')

            # 10. 提取排序后首行
            first_row_desc = await get_first_row_data(page)
            print(f'  排序后首行: {first_row_desc}')

            # 11. API 对比
            api_desc = api_baseline.get('desc', [])
            api_desc_usernames = [u[0] for u in api_desc]
            print(f'  API desc top5: {api_desc_usernames}')

            # 12. 验证
            verify_ok = True
            if first_row_desc and api_desc:
                first_username_in_browser = first_row_desc.get('cellTexts', [None])[0]
                first_username_in_api = api_desc[0][0]
                if first_username_in_browser and first_username_in_api:
                    if first_username_in_browser == first_username_in_api:
                        print(f'  [OK] 浏览器首行 ({first_username_in_browser}) == API 首行 ({first_username_in_api})')
                    else:
                        print(f'  [FAIL] 浏览器首行 ({first_username_in_browser}) != API 首行 ({first_username_in_api})')
                        verify_ok = False

            # 13. 再点一次切到 asc
            print(f'\n[7] 再点一次切到 asc...')
            await header_locator.click()
            try:
                await page.wait_for_function(
                    """() => {
                        const sortCaret = document.querySelector('.el-table__header .sort-caret.ascending');
                        return sortCaret !== null;
                    }""",
                    timeout=8000,
                )
                print('  [OK] 排序 caret 已变成 ascending')
            except Exception as e:
                print(f'  [WARN] 排序 caret 状态变化超时: {e}')

            await page.wait_for_timeout(1000)

            screenshot_asc = SCREENSHOT_DIR / '03-sorted-asc.png'
            await page.screenshot(path=str(screenshot_asc), full_page=True)
            print(f'  截图: {screenshot_asc}')

            first_row_asc = await get_first_row_data(page)
            print(f'  asc 首行: {first_row_asc}')

            api_asc = api_baseline.get('asc', [])
            api_asc_usernames = [u[0] for u in api_asc]
            print(f'  API asc top5: {api_asc_usernames}')

            if first_row_asc and api_asc:
                first_username_in_browser = first_row_asc.get('cellTexts', [None])[0]
                first_username_in_api = api_asc[0][0]
                if first_username_in_browser and first_username_in_api:
                    if first_username_in_browser == first_username_in_api:
                        print(f'  [OK] 浏览器 asc 首行 ({first_username_in_browser}) == API asc 首行 ({first_username_in_api})')
                    else:
                        print(f'  [FAIL] 浏览器 asc 首行 ({first_username_in_browser}) != API asc 首行 ({first_username_in_api})')
                        verify_ok = False

            page.remove_listener('request', on_request)

            print('\n' + '=' * 60)
            print(f'验证结果: {"[OK] PASS" if verify_ok else "[FAIL] FAIL"}')
            print('=' * 60)
            return verify_ok
        else:
            print('\n[FAIL] 找不到"变更时间"列，无法继续验证')
            return False


if __name__ == '__main__':
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
