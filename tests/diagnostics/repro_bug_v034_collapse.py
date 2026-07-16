"""
复现 BUG-V034 v2 报告: 点击节点后树自动收起

场景:
1. 进入 archdata 页 (TTTTT000/V11)
2. 手动展开一个 SM 节点 (采购管理)
3. 观察节点展开状态
4. 点击该节点的 checkbox (勾选)
5. 观察是否自动收起

预期: 节点保持展开
实际(报告): 节点被收起
"""
import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_UI = "http://localhost:3004"
SCREENSHOT_DIR = Path("d:/filework/test_output")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_tree_state(page, label):
    return page.evaluate("""(label) => {
        const nodes = document.querySelectorAll('.el-tree-node');
        let expanded = 0;
        const expandedLabels = [];
        nodes.forEach(n => {
            const icon = n.querySelector('.el-tree-node__expand-icon');
            const isExpanded = n.getAttribute('aria-expanded') === 'true' ||
                              (icon && icon.classList.contains('expanded'));
            if (isExpanded) {
                expanded++;
                const lbl = n.querySelector('.el-tree-node__label');
                if (lbl) expandedLabels.push(lbl.textContent.trim().substring(0, 40));
            }
        });
        console.log(`[${label}] total=${nodes.length} expanded=${expanded} labels=${expandedLabels.join(' | ')}`);
        return { label, total: nodes.length, expanded, labels: expandedLabels };
    }""", label)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()

        # 监听 console
        page.on("console", lambda msg: print(f"[CONSOLE.{msg.type}] {msg.text}"))

        # 登录
        page.goto(f"{BASE_UI.replace('3004', '3010')}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)

        # 进入页面
        url = f"{BASE_UI}/system/archdata?productId=507&versionId=863"
        print(f"[INFO] Navigating: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        s1 = inspect_tree_state(page, "INITIAL")
        page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_v2_initial.png"))

        # 找到一个有可点击展开箭头的节点, 模拟用户手动展开
        print("\n[STEP 1] 手动展开第一个 SM 节点...")
        # 找 domain 节点的 expand icon
        result = page.evaluate("""() => {
            const expandIcons = document.querySelectorAll('.el-tree-node__expand-icon');
            for (const icon of expandIcons) {
                // 找未展开的 icon (没有 expanded class)
                if (!icon.classList.contains('expanded') && icon.offsetParent) {
                    icon.click();
                    const node = icon.closest('.el-tree-node');
                    const lbl = node ? node.querySelector('.el-tree-node__label') : null;
                    return { clicked: lbl ? lbl.textContent.trim() : '?', isVisible: icon.offsetParent !== null };
                }
            }
            return { clicked: null };
        }""")
        print(f"[INFO] Clicked expand icon: {result}")
        time.sleep(2)

        s2 = inspect_tree_state(page, "AFTER_MANUAL_EXPAND")
        page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_v2_after_expand.png"))

        # 现在点击一个 checkbox (这会触发 handleBoCheck → scope-change → 上游 silent reload)
        print("\n[STEP 2] 勾选一个 SM 节点 (采购管理 类似)...")
        result = page.evaluate("""() => {
            // 找当前可见的 checkbox (在展开的 SM 节点里)
            const checkboxes = document.querySelectorAll('.el-tree-node__content .el-checkbox input');
            for (const cb of checkboxes) {
                if (!cb.checked && cb.offsetParent) {
                    // 找 checkbox 所在的 node
                    const node = cb.closest('.el-tree-node');
                    const lbl = node ? node.querySelector('.el-tree-node__label') : null;
                    const text = lbl ? lbl.textContent.trim().substring(0, 30) : '?';
                    cb.click();
                    return { clicked: text };
                }
            }
            return { clicked: null };
        }""")
        print(f"[INFO] Clicked checkbox: {result}")
        time.sleep(3)

        s3 = inspect_tree_state(page, "AFTER_CHECKBOX_CHECK")
        page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_v2_after_check.png"))

        # 报告
        print("\n========= BUG 验证结果 =========")
        print(f"Initial:    expanded={s1['expanded']} (期望 0)")
        print(f"After exp:  expanded={s2['expanded']} (期望 >= 1, 用户手动展开的节点)")
        print(f"After ck:   expanded={s3['expanded']} (期望保持 >= 1, 不要自动收起)")

        if s2["expanded"] >= 1 and s3["expanded"] < s2["expanded"]:
            print(f"\n[BUG 确认] 用户手动展开的节点在勾选后被收起!")
            print(f"  - 手动展开后: {s2['expanded']}")
            print(f"  - 勾选后:     {s3['expanded']}")
            print(f"  - 损失:       {s2['expanded'] - s3['expanded']} 个展开节点")
            browser.close()
            return True

        if s2["expanded"] >= 1 and s3["expanded"] >= s2["expanded"]:
            print(f"\n[PASS] 展开状态保持, BUG 已修复")

        browser.close()
        return False


if __name__ == "__main__":
    try:
        bug_confirmed = run()
        sys.exit(1 if bug_confirmed else 0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(2)
