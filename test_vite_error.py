"""检查 Vite 错误"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问首页...")

        page = cli._ensure_browser()
        page.goto("http://localhost:3004", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # 检查 vite-error-overlay
        print("\n2. 检查 Vite 错误...")
        error_info = page.evaluate('''() => {
            const overlay = document.querySelector('vite-error-overlay');
            if (overlay) {
                // 获取 shadow DOM 内容
                const shadow = overlay.shadowRoot;
                if (shadow) {
                    return {
                        exists: true,
                        message: shadow.querySelector('.message')?.textContent,
                        stack: shadow.querySelector('.stack')?.textContent,
                        errorType: shadow.querySelector('.error-type')?.textContent
                    };
                }
                return {
                    exists: true,
                    text: overlay.textContent
                };
            }
            return { exists: false };
        }''')
        print(f"Vite 错误: {error_info}")

        print("\n测试完成!")

    except Exception as e:
        print(f"测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()

if __name__ == '__main__':
    test()
