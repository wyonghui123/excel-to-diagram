"""检查 overlay 的完整样式"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def main():
    cli = PlaywrightCLI()
    try:
        cli.authenticated_navigate(
            '/system/archdata?productId=1&versionId=1',
            wait_for_selector='.multi-object-management',
            timeout=20000
        )
        cli.wait_for_timeout(3000)

        for i in range(15):
            tree_count = cli.evaluate("() => document.querySelectorAll('.el-tree').length")
            if tree_count > 0:
                break
            time.sleep(1)

        # 1. 勾选 财务管理
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const objectTree = trees[0];
                const nodes = objectTree.querySelectorAll('.el-tree-node');
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) checkbox.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)

        # 2. 展开关系范围
        cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel, .rst-panel-relation');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const header = panel.querySelector('.panel-header, [class*="header"]');
                        if (header) header.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(3)

        # 检查 overlay
        overlay = cli.evaluate("""
            () => {
                const overlay = document.querySelector('.rss-tree-disabled-overlay');
                if (!overlay) return { exists: false };
                const style = window.getComputedStyle(overlay);
                return {
                    exists: true,
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    pointerEvents: style.pointerEvents,
                    position: style.position,
                    zIndex: style.zIndex,
                    top: style.top,
                    left: style.left,
                    right: style.right,
                    bottom: style.bottom,
                    width: style.width,
                    height: style.height,
                    offsetParent: overlay.offsetParent?.className,
                    parentClass: overlay.parentElement?.className
                };
            }
        """)
        print(f"Overlay: {overlay}")

        # 检查 classifierLoading 的实际值
        loading_val = cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        const section = panel.querySelector('.rss-root');
                        if (!section) return { error: 'no rss-root' };
                        const vc = section.__vueParentComponent;
                        if (!vc) return { error: 'no vc' };
                        const setup = vc.setupState || {};
                        return {
                            classifierLoading: setup.classifierLoading,
                            hasData: setup.hasData,
                            allRelationships: setup.allRelationships?.length || 0
                        };
                    }
                }
                return { error: 'panel not found' };
            }
        """)
        print(f"Loading val: {loading_val}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
