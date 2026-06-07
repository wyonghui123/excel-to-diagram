"""
通过 Element Plus API 检查 el-option 的 label prop
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

        # 检查对话框中所有 el-option 的 label 属性
        result = cli.evaluate("""
            () => {
                const result = {
                    optionCount: 0,
                    labelValues: [],
                    iconValues: []
                };

                // 获取所有 el-option 和 el-select-dropdown__item
                const options1 = document.querySelectorAll('.el-option');
                const options2 = document.querySelectorAll('.el-select-dropdown__item');

                const allOptions = [...options1, ...options2];
                const seenTexts = new Set();

                // 对于每个 el-option，获取其 DOM 属性 label
                for (const opt of allOptions) {
                    const labelAttr = opt.getAttribute('label');
                    const textContent = opt.textContent.trim();

                    // 跳过重复
                    if (seenTexts.has(textContent)) continue;
                    seenTexts.add(textContent);

                    // 检查是否是分类相关的选项
                    const isAnnotation = textContent.includes('重要') ||
                                        textContent.includes('警告') ||
                                        textContent.includes('信息') ||
                                        textContent.includes('提示');

                    if (isAnnotation) {
                        result.optionCount++;
                        result.labelValues.push({
                            text: textContent,
                            labelAttr: labelAttr,
                            hasEmoji: /[\\u2600-\\uFFFF]/.test(textContent)
                        });
                    }
                }

                return result;
            }
        """)

        print("=" * 60)
        print("el-option label 属性检查：")
        print("=" * 60)
        print(f"分类相关选项数: {result['optionCount']}")
        for opt in result['labelValues']:
            marker = "[X]" if opt['hasEmoji'] else "[OK]"
            print(f"  {marker} text='{opt['text']}' | labelAttr={opt['labelAttr']}")

        # 检查 DOM 文本的 Unicode 编码
        unicode_result = cli.evaluate("""
            () => {
                const options1 = document.querySelectorAll('.el-option');
                const options2 = document.querySelectorAll('.el-select-dropdown__item');
                const results = [];
                const seen = new Set();

                for (const opt of [...options1, ...options2]) {
                    const text = opt.textContent.trim();
                    if (seen.has(text)) continue;
                    seen.add(text);

                    if (text.includes('重要') || text.includes('警告') ||
                        text.includes('信息') || text.includes('提示')) {
                        const chars = [];
                        for (const ch of text) {
                            chars.push({
                                char: ch,
                                code: ch.charCodeAt(0)
                            });
                        }
                        results.push({
                            text: text,
                            chars: chars
                        });
                    }
                }
                return results;
            }
        """)

        print("\n" + "=" * 60)
        print("Unicode 编码分析：")
        print("=" * 60)
        for opt in unicode_result:
            print(f"\n文本: '{opt['text']}'")
            for ch in opt['chars']:
                marker = "[SYMBOL] emoji" if ch['code'] > 0x1F000 else "[SYMBOL] 常规"
                print(f"  {marker} U+{ch['code'].toString(16).upper().padStart(4,'0')} '{ch['char']}'")

        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_07_label_prop.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
