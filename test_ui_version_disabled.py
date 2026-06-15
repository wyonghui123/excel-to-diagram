"""
UI 验证：新建架构对象时，版本字段应该 readonly（disabled），值从 context 注入

覆盖对象：领域(domain)、子领域(sub_domain)、服务模块(service_module)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

OUT_DIR = Path("d:/filework/excel-to-diagram/test_output/version_disabled")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OBJECTS = [
    ('领域', 'domain'),
    ('子领域', 'sub_domain'),
    ('服务模块', 'service_module'),
]


def open_new_drawer(cli, page, tab_text, object_name):
    """打开指定 tab 的新建 drawer"""
    print(f"\n========== {object_name} ==========")
    # 切到对应 tab
    tab = page.query_selector(f".el-tabs__item:has-text('{tab_text}')")
    if not tab:
        print(f"  [FAIL] 找不到 '{tab_text}' tab")
        return False
    tab.click()
    time.sleep(2.0)
    # 点新建
    new_btn = page.query_selector("button:has-text('新建')")
    if not new_btn:
        print(f"  [FAIL] 找不到'新建'按钮")
        return False
    new_btn.click()
    time.sleep(4.0)
    return True


def main():
    cli = PlaywrightCLI()
    page = None
    results = []
    try:
        # Step 1: 登录
        print("[1] 登录...")
        page = cli.authenticated_navigate(
            '/system/archdata',
            wait_for_selector='.el-tabs, .multi-object-management',
            timeout=20000
        )
        time.sleep(3.0)

        # Step 2: 选产品
        print("[2] 选产品+版本...")
        selects = page.query_selector_all(".el-select__wrapper")
        if not selects:
            print("  [FAIL] 找不到产品 select")
            return False
        selects[0].click(force=True)
        time.sleep(1.5)
        opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
        if not opts:
            print("  [FAIL] 产品下拉没选项")
            return False
        opts[0].click(force=True)
        time.sleep(2.0)

        # 选版本
        time.sleep(1.0)
        selects = page.query_selector_all(".el-select__wrapper")
        if len(selects) < 2:
            print("  [FAIL] 找不到版本 select")
            return False
        selects[1].click(force=True)
        time.sleep(1.5)
        opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
        if not opts:
            print("  [FAIL] 版本下拉没选项")
            return False
        version_name = opts[0].text_content().strip()
        opts[0].click(force=True)
        time.sleep(2.0)
        print(f"  选中的版本: {version_name}")

        # Step 3: 对每个对象分别测试
        for tab_text, obj_name in OBJECTS:
            # 关闭当前 drawer
            close_btn = page.query_selector(".el-drawer__close-btn")
            if close_btn:
                close_btn.click()
                time.sleep(1.0)

            if not open_new_drawer(cli, page, tab_text, obj_name):
                results.append((obj_name, False, 'open drawer failed'))
                continue

            # 检查版本字段
            version_check = page.evaluate("""() => {
                const drawer = document.querySelector('.el-drawer')
                if (!drawer) return { error: 'no drawer' }

                // 找所有"版本"字段
                const items = drawer.querySelectorAll('.el-form-item, .form-field, .op-field')
                const result = { found: false }
                for (const item of items) {
                    const labelEl = item.querySelector('.el-form-item__label, .field-label, label, .op-label')
                    if (!labelEl) continue
                    const label = labelEl.textContent.trim()
                    if (!label.includes('版本')) continue

                    const sel = item.querySelector('.el-select__wrapper')
                    if (sel) {
                        const selection = sel.querySelector('.el-select__selection')
                        const placeholder = sel.querySelector('.el-select__placeholder')
                        const isDisabled = sel.classList.contains('is-disabled')
                        const inputDisabled = !!item.querySelector('input[disabled]')
                        const selectionText = (selection?.textContent || '').trim()
                        const placeholderText = (placeholder?.textContent || '').trim()
                        result.found = true
                        result.label = label
                        result.selectionText = selectionText
                        result.placeholderText = placeholderText
                        result.isDisabled = isDisabled
                        result.inputDisabled = inputDisabled
                    }
                }
                return result
            }""")

            sel_text = (version_check.get('selectionText') or '').strip()
            is_displaying = version_check.get('found') and sel_text and sel_text != '请选择'
            is_readonly = version_check.get('isDisabled', False)

            if version_check.get('found'):
                print(f"  版本字段: label='{version_check.get('label')}'")
                print(f"    selectionText='{sel_text}'")
                print(f"    isDisabled={is_readonly} (期望: True)")
                print(f"    isDisplaying={is_displaying} (期望: True)")
            else:
                print(f"  [FAIL] 没找到版本字段")

            passed = is_displaying and is_readonly
            results.append((obj_name, passed, version_check))
            page.screenshot(path=str(OUT_DIR / f"{obj_name}.png"), full_page=True)

        # 汇总
        print("\n" + "="*60)
        print("汇总:")
        all_pass = True
        for obj, passed, info in results:
            mark = '[OK]' if passed else '[FAIL]'
            print(f"  {mark} {obj}")
            if not passed:
                all_pass = False
                print(f"       info: {info}")
        print("="*60)
        return all_pass
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
