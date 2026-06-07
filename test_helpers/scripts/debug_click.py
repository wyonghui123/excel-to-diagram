"""
调试 Element Plus el-select 点击事件
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    out_dir = "d:/filework/excel-to-diagram/test_results"
    os.makedirs(out_dir, exist_ok=True)

    cli = PlaywrightCLI(screenshot_dir=out_dir)

    try:
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1500)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(5000)
        cli.click("text=添加备注")
        cli.wait_for_timeout(3000)

        # 标记分类 select
        cli.evaluate("""
            () => {
                const all = document.querySelectorAll('.el-select');
                for (const s of all) {
                    if (s.textContent.trim() === '重要') {
                        s.setAttribute('data-test-target', 'category-select');
                        return true;
                    }
                }
                return false;
            }
        """)

        # 先看 el-select 内部结构
        structure = cli.evaluate("""
            () => {
                const anchor = document.querySelector("[data-test-target='category-select']");
                if (!anchor) return 'no anchor';
                return anchor.outerHTML.substring(0, 2000);
            }
        """)
        print("el-select structure:")
        print(structure)
        print()

        # 尝试不同子元素的 click
        for sub_selector in ['.el-select__wrapper', '.el-select__input-wrapper', 'input', '.el-input__wrapper', '.el-input__inner']:
            state = cli.evaluate(f"""
                () => {{
                    const anchor = document.querySelector("[data-test-target='category-select']");
                    if (!anchor) return 'no anchor';
                    const target = anchor.querySelector('{sub_selector}');
                    if (!target) return 'no {sub_selector}';

                    // 派发 mousedown, mouseup, click
                    ['mousedown', 'mouseup', 'click'].forEach(et => {{
                        const evt = new MouseEvent(et, {{ bubbles: true, button: 0, cancelable: true, view: window }});
                        target.dispatchEvent(evt);
                    }});

                    return 'clicked {sub_selector}';
                }}
            """)
            cli.wait_for_timeout(1500)
            popper = cli.evaluate("""
                () => {
                    const poppers = document.querySelectorAll('body .el-select-dropdown, body .el-dropdown-menu, body .el-popper');
                    const visible = [];
                    for (const p of poppers) {
                        const items = p.querySelectorAll('.el-select-dropdown__item, .el-dropdown-menu__item, .el-popper__item');
                        const rect = p.getBoundingClientRect();
                        if (items.length > 0 && rect.width > 0) {
                            visible.push({
                                count: items.length,
                                texts: Array.from(items).map(i => i.textContent.trim())
                            });
                        }
                    }
                    return visible;
                }
            """)
            print(f"Sub '{sub_selector}': {state} -> {popper}")
            if popper and len(popper) > 0:
                print(f"  SUCCESS with sub {sub_selector}")
                break
    finally:
        cli.close()

if __name__ == "__main__":
    main()
