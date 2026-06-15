import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    # 先尝试 /audit-log 路由
    cli.authenticated_navigate('/audit-log', wait_for_selector='body', timeout=15000)
    cli.screenshot('audit_log_current.png')
    
    # 获取页面 URL 和标题
    url = cli.page.url
    title = cli.page.title()
    print(f'[URL] {url}')
    print(f'[TITLE] {title}')
    
    # 检查是否有 .audit-log-management 元素
    has_audit = cli.page.locator('.audit-log-management').count()
    print(f'[AUDIT-ELEMENT] count={has_audit}')
    
    # 检查是否有 GenericObjectList (旧版)
    has_generic = cli.page.locator('.generic-object-list, [class*="object-list"]').count()
    print(f'[GENERIC-LIST] count={has_generic}')
    
    # 获取表格列头
    headers = cli.page.locator('.el-table__header th').all_text_contents()
    print(f'[HEADERS] {headers[:15]}')
    
    errors = cli.check_health()
    print('[HEALTH]', errors)
