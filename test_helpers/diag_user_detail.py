"""抓用户详情页的 network 请求"""
import time
from playwright.sync_api import sync_playwright

LOG_PATH = r'd:\filework\excel-to-diagram\test_helpers\diag_user_detail_full.log'
log_lines = []
def log(msg):
    print(msg)
    log_lines.append(str(msg))
    try:
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    all_reqs = []
    def on_request(req):
        url = req.url
        if '/api/' in url:
            all_reqs.append(url)
            log(f'  [REQ] {url}')

    def on_response(resp):
        url = resp.url
        if '/api/' in url and resp.status == 200:
            # 异步获取 body
            try:
                body = resp.body()
                if b'user_group' in body or b'member_count' in body or b'_display' in body or b'parent_id' in body:
                    import json
                    d = json.loads(body)
                    log(f'  [RESP] {url}')
                    if isinstance(d.get('data'), list):
                        for item in d['data'][:3]:
                            log(f'    item keys: {list(item.keys())}')
                            log(f'    item: {str(item)[:300]}')
                    elif isinstance(d.get('data'), dict):
                        log(f'    data keys: {list(d["data"].keys())}')
            except Exception as e:
                pass

    page.on('request', on_request)
    page.on('response', on_response)

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)

    # 点击第一行的"编辑"或双击
    rows = page.locator('.el-table__body tr')
    rows.first.dblclick()
    time.sleep(3)

    # 等详情页加载
    page.wait_for_selector('.association-section, .op-section, .section', timeout=8000)
    time.sleep(2)

    # 找用户组 section
    sections = page.locator('.association-section, .op-section, .section, .assoc-section')
    log(f'\n=== Sections: {sections.count()} ===')
    for i in range(min(sections.count(), 5)):
        text = sections.nth(i).text_content()[:150]
        log(f'  section[{i}]: {text!r}')

    # 看详情页 URL
    log(f'\n  URL: {page.url}')

    # 找所有 API 请求
    log(f'\n=== All API requests ===')
    for r in all_reqs:
        log(f'  {r}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter21-user-detail.png', full_page=True)
    browser.close()
log('\n=== DONE ===')
