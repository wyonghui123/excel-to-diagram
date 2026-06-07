"""调试页面结构"""
import sys, os, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI()
cli.request('http://localhost:3010/api/v1/auth/dev-login?username=admin')
cli.goto('http://localhost:3004/system/archdata')
time.sleep(5)

# 检查页面内容
result = cli.evaluate("""() => {
    return {
        title: document.title,
        url: window.location.href,
        hasApp: !!document.querySelector('#app'),
        hasTree: !!document.querySelector('.el-tree'),
        hasPanel: !!document.querySelector('.collapsible-panel'),
        bodyText: document.body?.innerText?.substring(0, 800)
    }
}""")
print("Page info:", json.dumps(result, ensure_ascii=False))

# 截图
cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/debug_page.png')
print("Screenshot saved")

cli.close()
