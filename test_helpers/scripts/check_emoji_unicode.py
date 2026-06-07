"""
检查 emoji 选项的精确 Unicode 编码
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        # 认证
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(500)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(2000)

        # 导航到详情页
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(3000)

        # 点击添加备注
        cli.click("text=添加备注")
        cli.wait_for_timeout(2000)

        # 点击下拉框
        cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return;
                const formItems = dialog.querySelectorAll('.el-form-item');
                for (const item of formItems) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.includes('分类')) {
                        const sel = item.querySelector('.el-select');
                        if (sel) sel.click();
                        return;
                    }
                }
            }
        """)
        cli.wait_for_timeout(3000)

        # 获取 emoji 选项的精确 Unicode 编码
        result = cli.evaluate("""
            () => {
                const items = document.querySelectorAll('.el-option');
                const emojiItems = [];

                for (const item of items) {
                    const text = item.textContent;
                    if (text.includes('重要') || text.includes('警告') || text.includes('信息') || text.includes('提示')) {
                        // 获取每个字符的 Unicode 编码
                        const chars = [];
                        for (const ch of text) {
                            chars.push({
                                char: ch,
                                code: ch.charCodeAt(0),
                                hex: ch.charCodeAt(0).toString(16),
                                isEmoji: ch.charCodeAt(0) > 0x1F000
                            });
                        }

                        emojiItems.push({
                            text: text,
                            textHex: Array.from(text).map(c => c.charCodeAt(0).toString(16)).join(' '),
                            chars: chars
                        });
                    }
                }

                return emojiItems;
            }
        """)

        print("=" * 60)
        print("中文 + emoji 组合选项的 Unicode 编码：")
        print("=" * 60)
        for item in result:
            print(f"\n文本: '{item['text']}'")
            print(f"文本 Hex: {item['textHex']}")
            for ch_info in item['chars']:
                print(f"  字符: '{ch_info['char']}' | 码点: U+{ch_info['hex'].upper().padStart(4, '0')} | emoji: {ch_info['isEmoji']}")

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/14_emoji_unicode.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
