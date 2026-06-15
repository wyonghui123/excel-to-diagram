import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    page = cli._ensure_browser()

    # Step 1: dev-login 设 cookie
    page.goto(
        "http://localhost:3010/api/v1/auth/dev-login?username=admin",
        wait_until="domcontentloaded",
        timeout=15000,
    )
    print('[STEP1] dev-login OK, url=', page.url)

    # Step 2: 加载首页（用 networkidle 等久一点，Vite 慢）
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=45000)
    print('[STEP2] 首页加载完成, url=', page.url)

    # Step 3: 等待 store
    cli._wait_for_store_ready(timeout=30000)
    print('[STEP3] store ready')

    # Step 4: SPA 内部导航
    page.evaluate("""
        () => {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push('/product-management')
        }
    """)
    time.sleep(5)  # 等表格渲染
    print('[STEP4] navigated to /product-management, url=', page.url)

    # 1. 测正常态
    normal = cli.evaluate('''() => {
        const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
        if (!th) return {error: 'no th'};
        return {
            state: 'normal',
            bg: getComputedStyle(th).backgroundColor,
            borderBottom: getComputedStyle(th).borderBottom,
            count: document.querySelectorAll('.custom-table .el-table__header th.el-table__cell').length
        };
    }''')

    # 2. 触发 hover
    th_locator = page.locator('.custom-table .el-table__header th.el-table__cell')
    th_count = th_locator.count()
    if th_count > 0:
        th_locator.first.hover()
        time.sleep(0.8)

        hover = cli.evaluate('''() => {
            const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
            if (!th) return {error: 'no th'};
            return {
                state: 'hover',
                bg: getComputedStyle(th).backgroundColor,
                borderBottom: getComputedStyle(th).borderBottom
            };
        }''')
        cli.screenshot('verify_hover_7d0b78d.png', full_page=True)
    else:
        hover = {'error': f'no th locator, count={th_count}'}

    print('[VERIFY 7d0b78d HOVER]')
    print('Normal:', json.dumps(normal, ensure_ascii=False))
    print('Hover:', json.dumps(hover, ensure_ascii=False))

    # 判定
    expected_no_hover_gray = 'rgb(249, 250, 251)'  # #f9fafb
    if hover.get('bg') == expected_no_hover_gray:
        print('[FAIL] hover 仍是灰色 #f9fafb')
    elif hover.get('bg') in ('rgba(0, 0, 0, 0)', 'transparent'):
        print('[PASS] hover 是 transparent，符合修复预期')
    else:
        print(f"[INFO] hover bg = {hover.get('bg')}")
