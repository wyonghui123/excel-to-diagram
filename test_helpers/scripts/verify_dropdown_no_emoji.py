"""
完整的下拉框分类选项验证 - 处理 Unicode
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from test_helpers.browser_auth_cli import PlaywrightCLI

def safe_print(s):
    try:
        print(s)
    except UnicodeEncodeError:
        # 替换非 ASCII 字符
        print(s.encode('utf-8', errors='replace').decode('utf-8'))

def main():
    cli = PlaywrightCLI()
    out_dir = "d:/filework/excel-to-diagram/test_results"
    os.makedirs(out_dir, exist_ok=True)

    try:
        safe_print("=" * 60)
        safe_print("Step 1: 认证")
        safe_print("=" * 60)
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1500)

        safe_print("\n" + "=" * 60)
        safe_print("Step 2: 加载首页")
        safe_print("=" * 60)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)

        safe_print("\n" + "=" * 60)
        safe_print("Step 3: 导航到详情页")
        safe_print("=" * 60)
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(4000)
        cli.screenshot(f"{out_dir}/verify_01_detail.png")

        safe_print("\n" + "=" * 60)
        safe_print("Step 4: 查找并点击 '添加备注' 按钮")
        safe_print("=" * 60)
        click_ok = cli.click("text=添加备注")
        safe_print(f"点击结果: {click_ok}")
        cli.wait_for_timeout(3000)
        cli.screenshot(f"{out_dir}/verify_02_dialog.png")

        dialog_visible = cli.is_visible("text=新增备注")
        safe_print(f"对话框可见: {dialog_visible}")

        safe_print("\n" + "=" * 60)
        safe_print("Step 5: 点击 '分类' 下拉框")
        safe_print("=" * 60)
        cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return 'no dialog';
                const formItems = dialog.querySelectorAll('.el-form-item');
                for (const item of formItems) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            sel.click();
                            return 'clicked';
                        }
                    }
                }
                return 'no category select found';
            }
        """)
        cli.wait_for_timeout(2000)
        cli.screenshot(f"{out_dir}/verify_03_dropdown_open.png")

        safe_print("\n" + "=" * 60)
        safe_print("Step 6: 获取所有下拉选项")
        safe_print("=" * 60)
        options_info = cli.evaluate("""
            () => {
                const result = {
                    dropdownCount: 0,
                    categoryOptions: [],
                    allCategoryTexts: [],
                    unicodeInfo: []
                };

                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                result.dropdownCount = dropdowns.length;

                for (const dd of dropdowns) {
                    const style = window.getComputedStyle(dd);
                    const isVisible = style.display !== 'none' && style.visibility !== 'hidden';

                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    for (const item of items) {
                        const text = item.textContent.trim();
                        const hex = Array.from(text).map(c => 'U+' + c.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')).join(' ');

                        const chineseLabels = ['重要', '警告', '信息', '提示'];
                        const emojiLabels = ['[WARNING]', '[ALERT]', 'ℹ', '[DECORATIVE]'];
                        const hasChinese = chineseLabels.some(l => text.includes(l));
                        const hasEmoji = emojiLabels.some(e => text.includes(e));

                        if (hasChinese || hasEmoji) {
                            result.categoryOptions.push({
                                text: text,
                                unicode: hex,
                                hasEmoji: hasEmoji,
                                hasChinese: hasChinese,
                                dropdownVisible: isVisible
                            });
                        }
                    }
                }

                result.allCategoryTexts = result.categoryOptions.map(o => o.text);
                return result;
            }
        """)

        safe_print(f"下拉框总数: {options_info['dropdownCount']}")
        safe_print(f"分类相关选项数: {len(options_info['categoryOptions'])}")
        safe_print("")

        # 详细输出
        for i, opt in enumerate(options_info['categoryOptions']):
            tag = ""
            if opt['hasEmoji'] and opt['hasChinese']:
                tag = "[X] 含 emoji"
            elif opt['hasEmoji']:
                tag = "[X] 仅 emoji"
            elif opt['hasChinese']:
                tag = "[OK] 纯中文"
            else:
                tag = "? 未知"
            safe_print(f"  [{i+1}] {tag} -> '{opt['text']}'")
            safe_print(f"       Unicode: {opt['unicode']}")

        # 统计
        correct = sum(1 for o in options_info['categoryOptions']
                     if o['hasChinese'] and not o['hasEmoji'])
        with_emoji = sum(1 for o in options_info['categoryOptions'] if o['hasEmoji'])

        safe_print("\n" + "=" * 60)
        safe_print("验证结果")
        safe_print("=" * 60)
        safe_print(f"正确的中文选项: {correct}")
        safe_print(f"带 emoji 的选项: {with_emoji}")

        # 期望结果
        expected_labels = ['重要', '警告', '信息', '提示']
        unique_correct_texts = set()
        for o in options_info['categoryOptions']:
            if o['hasChinese'] and not o['hasEmoji']:
                for label in expected_labels:
                    if label in o['text']:
                        unique_correct_texts.add(label)

        safe_print(f"\n发现的纯中文标签: {sorted(unique_correct_texts)}")
        safe_print(f"期望的标签: {sorted(expected_labels)}")

        if unique_correct_texts == set(expected_labels) and with_emoji == 0:
            safe_print("\n[OK] 测试通过！所有 4 个分类选项都是纯中文，没有任何 emoji")
            return 0
        else:
            safe_print("\n[X] 测试失败！")
            if with_emoji > 0:
                safe_print(f"   - 还有 {with_emoji} 个带 emoji 的选项")
            missing = set(expected_labels) - unique_correct_texts
            if missing:
                safe_print(f"   - 缺少标签: {missing}")
            return 1

    except Exception as e:
        safe_print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cli.close()

if __name__ == "__main__":
    sys.exit(main())
