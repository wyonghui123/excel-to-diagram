"""
BUG-V034 验证脚本: 对象范围树自动全展开问题

直接使用 Playwright 浏览器登录, 走前端 URL。
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_UI = "http://localhost:3004"
BASE_API = "http://localhost:3010"
SCREENSHOT_DIR = Path("d:/filework/test_output")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def count_expanded_nodes(page):
    """统计已展开的树节点数量"""
    return page.evaluate("""() => {
        const nodes = document.querySelectorAll('.el-tree-node');
        let total = 0;
        let expanded = 0;
        let expandedHasChildren = 0;
        const expandedLabels = [];
        nodes.forEach(n => {
            total++;
            const icon = n.querySelector('.el-tree-node__expand-icon');
            const isExpanded = n.getAttribute('aria-expanded') === 'true' ||
                              (icon && icon.classList.contains('expanded'));
            if (isExpanded) {
                expanded++;
                const label = n.querySelector('.el-tree-node__label');
                if (label) {
                    expandedLabels.push(label.textContent.trim().substring(0, 40));
                }
                if (n.querySelector('.el-tree-node__children')) {
                    expandedHasChildren++;
                }
            }
        });
        return { total, expanded, expandedHasChildren, expandedLabels: expandedLabels.slice(0, 20) };
    }""")


def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()

        # 1. 走前端 dev-login
        print("[INFO] Dev login via UI API...")
        login_url = f"{BASE_API}/api/v1/auth/dev-login?username=admin"
        page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)

        # Hardcoded: product=507 (TTTTT000 供应链云), version=863 (V11) - has 3034 BO
        pid, vid = 507, 863
        pname, vname = "TTTTT000", "V11"
        print(f"[INFO] Using hardcoded product={pname}(id={pid}), version={vname}(id={vid})")

        # 4. 导航到 archdata 页面
        url = f"{BASE_UI}/system/archdata?productId={pid}&versionId={vid}"
        print(f"[INFO] Navigating: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 5. 等待页面加载
        print("[INFO] Waiting for page to load...")
        time.sleep(5)

        # 5.1 检查页面上有几个 el-tree
        tree_info = page.evaluate("""() => {
            const trees = document.querySelectorAll('.el-tree');
            const result = [];
            trees.forEach((t, i) => {
                const nodes = t.querySelectorAll('.el-tree-node');
                const visible = t.offsetParent !== null;
                let parent = t.parentElement;
                let parentClass = parent ? parent.className : '';
                let sectionLabel = '';
                // Find section label
                let p = t;
                for (let i = 0; i < 8; i++) {
                    p = p.parentElement;
                    if (!p) break;
                    const heading = p.querySelector('.section-title, .panel-title, h3, h4, .title');
                    if (heading) {
                        sectionLabel = heading.textContent.trim().substring(0, 50);
                        break;
                    }
                }
                result.push({
                    index: i,
                    visible,
                    nodeCount: nodes.length,
                    parentClass: parentClass.substring(0, 80),
                    sectionLabel
                });
            });
            return result;
        }""")
        print(f"[INFO] el-trees on page: {len(tree_info)}")
        for ti in tree_info:
            print(f"  - {ti}")

        # 5.2 等待树加载
        print("[INFO] Waiting for tree nodes...")
        try:
            page.wait_for_selector(".el-tree-node", timeout=20000)
            print("[OK] el-tree-node found")
        except Exception as e:
            print(f"[WARN] el-tree-node not found: {e}")
            page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_no_tree.png"))
            # 检查页面状态
            page_text = page.evaluate("() => document.body.innerText.substring(0, 500)")
            print(f"[INFO] Page text: {page_text}")
            browser.close()
            return False

        time.sleep(4)

        # 6. 初始状态统计
        stats = count_expanded_nodes(page)
        print(f"[INITIAL] total_nodes={stats['total']}, expanded={stats['expanded']}, expanded_has_children={stats['expandedHasChildren']}")
        print(f"[INITIAL] expanded_labels (first 20): {stats['expandedLabels']}")

        page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_initial.png"))

        if stats["expanded"] > 100:
            print(f"[FAIL] BUG-V034 NOT FIXED! expanded={stats['expanded']} (expected < 100)")
            page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_fail_initial.png"))
            browser.close()
            return False

        print(f"[OK] Initial expansion reasonable: {stats['expanded']} nodes")

        # 7. 测试点击未展开节点
        print("[INFO] Testing click on collapsed node...")
        clicked = page.evaluate("""() => {
            const nodes = document.querySelectorAll('.el-tree-node');
            for (const n of nodes) {
                const icon = n.querySelector('.el-tree-node__expand-icon');
                const isExpanded = n.getAttribute('aria-expanded') === 'true' ||
                                  (icon && icon.classList.contains('expanded'));
                if (!isExpanded && n.querySelector('.el-tree-node__children')) {
                    const label = n.querySelector('.el-tree-node__label');
                    if (label) {
                        label.scrollIntoView({block: 'center'});
                        label.click();
                        return label.textContent.trim().substring(0, 40);
                    }
                }
            }
            return null;
        }""")
        print(f"[INFO] Clicked: {clicked}")
        time.sleep(2)

        stats2 = count_expanded_nodes(page)
        print(f"[AFTER_CLICK] total_nodes={stats2['total']}, expanded={stats2['expanded']}, expanded_has_children={stats2['expandedHasChildren']}")
        print(f"[AFTER_CLICK] expanded_labels (first 20): {stats2['expandedLabels']}")

        page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_after_click.png"))

        if stats2["expanded"] > 100:
            print(f"[FAIL] Click triggered mass expansion! expanded={stats2['expanded']}")
            browser.close()
            return False

        delta = stats2["expanded"] - stats["expanded"]
        print(f"[OK] Click delta: {delta} (expected 0 or +1)")

        # 8. 测试勾选一个节点 (这是 BUG-V034 的核心场景: 用户报"选择树节点会自动触发全部展开")
        print("[INFO] Testing checkbox check (user reported trigger)...")
        checked = page.evaluate("""() => {
            // 找一个未勾选的 checkbox
            const checkboxes = document.querySelectorAll('.el-tree-node__content .el-checkbox');
            for (const cb of checkboxes) {
                const input = cb.querySelector('input');
                if (input && !input.checked) {
                    cb.scrollIntoView({block: 'center'});
                    cb.click();
                    const node = cb.closest('.el-tree-node');
                    const label = node ? node.querySelector('.el-tree-node__label') : null;
                    return label ? label.textContent.trim().substring(0, 40) : 'unknown';
                }
            }
            return null;
        }""")
        print(f"[INFO] Checked: {checked}")
        time.sleep(3)

        stats3 = count_expanded_nodes(page)
        print(f"[AFTER_CHECK] total_nodes={stats3['total']}, expanded={stats3['expanded']}, expanded_has_children={stats3['expandedHasChildren']}")
        print(f"[AFTER_CHECK] expanded_labels (first 20): {stats3['expandedLabels']}")

        page.screenshot(path=str(SCREENSHOT_DIR / "bug_v034_after_check.png"))

        if stats3["expanded"] > 100:
            print(f"[FAIL] Check triggered mass expansion! expanded={stats3['expanded']}")
            browser.close()
            return False

        delta2 = stats3["expanded"] - stats2["expanded"]
        print(f"[OK] Check delta: {delta2}")

        print(f"\n[PASS] BUG-V034 verified")
        print(f"  - Initial: {stats['expanded']} expanded / {stats['total']} total")
        print(f"  - After click: {stats2['expanded']} expanded / {stats2['total']} total")
        print(f"  - After check: {stats3['expanded']} expanded / {stats3['total']} total")
        browser.close()
        return True


if __name__ == "__main__":
    try:
        ok = run_verification()
        sys.exit(0 if ok else 1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(2)
