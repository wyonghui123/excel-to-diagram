"""
备注类型下拉框验证测试 v2
严格验证：下拉框展开后，只获取下拉框内的选项
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

import os
os.makedirs("d:/filework/excel-to-diagram/test_results", exist_ok=True)

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(screenshot_dir='d:/filework/excel-to-diagram/test_results')

    try:
        # Step 1: 认证
        print("[1/8] dev-login...")
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1000)
        print("[OK] dev-login 成功")

        # Step 2: 导航到详情页
        print("[2/8] 导航到业务对象详情页...")
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(2000)

        # 使用 router.push 导航
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router
                router.push('/detail/business_object/25')
            }
        """)

        if not cli.wait_for_selector("text=添加备注", timeout=15000):
            print("[FAIL] 详情页加载超时")
            cli.screenshot("d:/filework/excel-to-diagram/test_results/01_detail_page.png")
            return False
        print("[OK] 详情页加载成功")
        cli.screenshot("d:/filework/excel-to-diagram/test_results/01_detail_page.png")

        # Step 3: 点击添加备注按钮
        print("[3/8] 点击添加备注按钮...")
        cli.click("text=添加备注")
        cli.wait_for_timeout(2000)

        # 等待对话框
        if not cli.wait_for_selector("text=新增备注", timeout=5000):
            print("[FAIL] 对话框未出现")
            cli.screenshot("d:/filework/excel-to-diagram/test_results/02_dialog_failed.png")
            return False
        print("[OK] 对话框已打开")
        cli.screenshot("d:/filework/excel-to-diagram/test_results/02_dialog.png")

        # Step 4: 获取对话框内默认选中的值
        print("[4/8] 检查默认选中的分类...")
        selected_category = cli.evaluate("""
            () => {
                // 获取 el-select 中当前选中的 span 文本
                const select = document.querySelector('.el-dialog .el-select');
                if (!select) return 'NOT_FOUND';
                const selected = select.querySelector('.el-input__inner, .el-select__wrapper');
                return selected ? selected.textContent.trim() : 'NO_SELECTION';
            }
        """)
        print(f"[DEBUG] 默认选中: {selected_category}")

        # Step 5: 点击下拉框展开
        print("[5/8] 点击下拉框展开...")
        # 点击 el-select 的 input 区域
        clicked = cli.click(".el-dialog .el-select input")
        print(f"[DEBUG] 点击结果: {clicked}")
        cli.wait_for_timeout(1000)

        # Step 6: 获取下拉框展开后的选项（只获取下拉列表内的选项）
        print("[6/8] 获取下拉框内的选项...")
        dropdown_options = cli.evaluate("""
            () => {
                // 找到所有 el-select-dropdown（浮层）
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                const options = [];
                for (const dd of dropdowns) {
                    // 检查这个 dropdown 是否可见
                    const style = window.getComputedStyle(dd);
                    if (style.display === 'none' || style.visibility === 'hidden') continue;

                    // 在可见的 dropdown 中找选项
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    for (const item of items) {
                        const text = item.textContent.trim();
                        options.push(text);
                    }
                }
                return options;
            }
        """)
        print(f"[DEBUG] 下拉框内选项: {dropdown_options}")

        # Step 7: 截图下拉框状态
        cli.screenshot("d:/filework/excel-to-diagram/test_results/03_dropdown_options.png")

        # Step 8: 验证
        print("[7/8] 验证结果...")
        expected_labels = ['重要', '警告', '信息', '提示']
        found_labels = [label for label in expected_labels if any(label in opt for opt in dropdown_options)]

        # 检查是否有英文标签
        english_labels = [label for label in ['IMPORTANT', 'WARNING', 'INFO', 'TIP'] if any(label in opt for opt in dropdown_options)]

        # 检查是否有 emoji
        emoji_found = any(emoji in opt for opt in dropdown_options for emoji in ['[WARNING]', '[ALERT]', '[DECORATIVE]', 'ℹ', '[DECORATIVE]', '[SYMBOL]', '[SYMBOL]'])

        print(f"\n下拉框内选项数量: {len(dropdown_options)}")
        print(f"下拉框内选项: {dropdown_options}")
        print(f"找到的中文标签: {found_labels}")
        print(f"找到的英文标签: {english_labels}")
        print(f"发现 emoji: {emoji_found}")

        # 最终判断
        if len(found_labels) == 4 and len(english_labels) == 0:
            print("\n[OK] 测试通过！下拉框正确显示 4 个中文标签，无英文/emoji:")
            for label in expected_labels:
                print(f"   - {label}")
            return True
        elif len(english_labels) > 0:
            print(f"\n[X] 测试失败！发现英文标签: {english_labels}")
            print("   说明 CATEGORY_CONFIG 映射未生效")
            return False
        elif emoji_found:
            print(f"\n[X] 测试失败！发现 emoji 标签")
            print("   说明 annotationConfig.js 中的 emoji 未被正确移除")
            return False
        else:
            print(f"\n[X] 测试失败！只找到 {len(found_labels)}/4 个中文标签")
            return False

    except Exception as e:
        print(f"[ERROR] 测试异常: {e}")
        import traceback
        traceback.print_exc()
        try:
            cli.screenshot("d:/filework/excel-to-diagram/test_results/99_error.png")
        except:
            pass
        return False
    finally:
        cli.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
