"""
深入检查下拉框选项来源
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
        cli.click(".el-dialog .el-select input")
        cli.wait_for_timeout(1500)

        # 获取所有可见 dropdown 的选项详情
        details = cli.evaluate("""
            () => {
                const results = [];
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const style = window.getComputedStyle(dd);
                    if (style.display === 'none') continue;
                    if (style.visibility === 'hidden') continue;

                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    for (const item of items) {
                        results.push({
                            text: item.textContent.trim(),
                            innerHTML: item.innerHTML.substring(0, 300),
                            classList: item.className,
                            visible: item.offsetParent !== null
                        });
                    }
                }
                return results;
            }
        """)

        print("=" * 60)
        print("下拉框选项详情：")
        print("=" * 60)
        for i, item in enumerate(details):
            print(f"\n--- 选项 {i+1} ---")
            print(f"文本: {item['text']}")
            print(f"HTML: {item['innerHTML']}")
            print(f"可见: {item['visible']}")

        # 检查 emoji
        emoji_items = [item for item in details if any(e in item['text'] for e in ['[WARNING]', '[ALERT]', '[DECORATIVE]', 'ℹ', '[DECORATIVE]'])]
        chinese_items = [item for item in details if any(label in item['text'] for label in ['重要', '警告', '信息', '提示'])]
        english_items = [item for item in details if any(label in item['text'] for label in ['IMPORTANT', 'WARNING', 'INFO', 'TIP'])]
        page_items = [item for item in details if '条' in item['text'] or '/' in item['text']]

        print("\n" + "=" * 60)
        print("分析结果：")
        print("=" * 60)
        print(f"总选项数: {len(details)}")
        print(f"带 emoji 选项: {len(emoji_items)}")
        print(f"中文选项: {len(chinese_items)}")
        print(f"英文选项: {len(english_items)}")
        print(f"分页/无关选项: {len(page_items)}")

        if emoji_items:
            print("\n[X] 发现 emoji 选项（违反规范）：")
            for item in emoji_items:
                print(f"   {item['text']}")

        if english_items:
            print("\n[X] 发现英文选项（映射未生效）：")
            for item in english_items:
                print(f"   {item['text']}")

        if chinese_items:
            print("\n中文选项：")
            for item in chinese_items:
                print(f"   {item['text']}")

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/04_dropdown_detail.png")
        print("\n截图已保存到 test_results/04_dropdown_detail.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
