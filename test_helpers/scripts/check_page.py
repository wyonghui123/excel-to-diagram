"""检查页面是否加载"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def main():
    cli = PlaywrightCLI()
    try:
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)
        print("[OK] 页面加载成功")
    except Exception as e:
        print(f"[ERROR] {e}")
        # 看看页面
        try:
            html = cli.evaluate('() => document.body.innerHTML.substring(0, 2000)')
            print(f"[body html] {html[:2000]}")
        except:
            pass
    finally:
        cli.close()


if __name__ == "__main__":
    main()
