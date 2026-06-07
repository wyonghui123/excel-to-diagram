"""
检查 EnumService 缓存中是否有带 emoji 的选项
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1000)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(3000)

        cli.click("text=添加备注")
        cli.wait_for_timeout(3000)

        # 检查 EnumService 的缓存
        result = cli.evaluate("""
            () => {
                // 尝试找到 EnumService 的缓存
                const results = {};

                // 方法1: 检查 Vue 全局
                try {
                    const app = document.querySelector('#app').__vue_app__;
                    if (app) {
                        const pinia = app.config.globalProperties.$pinia;
                        if (pinia) {
                            results.piniaStores = Array.from(pinia._s.keys());
                        }
                    }
                } catch (e) {
                    results.piniaError = e.message;
                }

                // 方法2: 尝试找到 annotation_category 的缓存数据
                // 枚举缓存通常在某个 store 中
                try {
                    // 检查是否有全局的 enum cache
                    const bodyHTML = document.body.innerHTML;
                    // 检查 DOM 中是否有 emoji 文本
                    const emojiMatch = bodyHTML.match(/[\\u2600-\\uFFFF]/g);
                    results.pageHasEmoji = emojiMatch ? emojiMatch.slice(0, 20) : [];
                } catch (e) {
                    results.domError = e.message;
                }

                return results;
            }
        """)

        print("=" * 60)
        print("EnumService 缓存检查：")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 检查 DOM 中是否有 emoji 文本
        emoji_in_page = cli.evaluate("""
            () => {
                const body = document.body.innerText;
                // 检查常见的 emoji
                const emojis = ['[WARNING]', '[ALERT]', '[DECORATIVE]', 'ℹ'];
                const found = emojis.filter(e => body.includes(e));
                return found;
            }
        """)
        print(f"\n页面中发现的 emoji: {emoji_in_page}")

        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_05_enum_check.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
