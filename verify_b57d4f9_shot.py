import sys, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/product-management', timeout=45000)
    time.sleep(7)
    saved = cli.screenshot('b57d4f9_verified.png', full_page=True)
    print('[SCREENSHOT SAVED]', saved)
