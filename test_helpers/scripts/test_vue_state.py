"""检查为什么 relation tree 没有数据"""
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

        # 检查组件状态
        info = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const result = {
                    treeCount: trees.length,
                    panels: []
                };
                
                // 检查所有 panel
                document.querySelectorAll('.collapsible-panel').forEach(p => {
                    const title = p.querySelector('.panel-title, [class*="title"]')?.textContent?.trim();
                    const collapsed = p.classList.contains('is-collapsed');
                    result.panels.push({ title, collapsed });
                });
                
                if (trees.length >= 2) {
                    const relTree = trees[1];
                    const vc = relTree.__vueParentComponent;
                    if (vc) {
                        const proxy = vc.proxy;
                        result.elTree = {
                            data: proxy.data?.length || 0,
                            storeNodes: proxy.store ? Object.keys(proxy.store.nodesMap).length : 0,
                            display: window.getComputedStyle(relTree).display
                        };
                        
                        // 检查 Vue 组件 props
                        const props = proxy.$props || {};
                        result.elTreeProps = {
                            dataLength: props.data?.length || 0,
                            nodeKey: props.nodeKey
                        };
                    }
                }
                
                return result;
            }
        """)
        print(f"Info: {info}")

        # 检查 loading 状态
        loading_info = cli.evaluate("""
            () => {
                const loading = document.querySelector('.rss-loading');
                const empty = document.querySelector('.rss-empty');
                const overlay = document.querySelector('.rss-tree-disabled-overlay');
                return {
                    loadingVisible: loading?.offsetParent !== null,
                    loadingDisplay: loading ? window.getComputedStyle(loading).display : 'N/A',
                    emptyVisible: empty?.offsetParent !== null,
                    emptyDisplay: empty ? window.getComputedStyle(empty).display : 'N/A',
                    overlayVisible: overlay?.offsetParent !== null
                };
            }
        """)
        print(f"Loading: {loading_info}")

        # 检查 Vue 组件内部状态 (通过 __vueParentComponent)
        vue_state = cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
                for (const panel of panels) {
                    const titleEl = panel.querySelector('.panel-title, [class*="title"]');
                    if (titleEl?.textContent?.includes('关系范围')) {
                        // 找到 RelationScopeSection 组件
                        const vc = panel.__vueParentComponent;
                        if (!vc) return { error: 'no vc' };
                        
                        // 向下找 RelationScopeSection
                        const findSection = (comp) => {
                            if (!comp) return null;
                            if (comp.type?.name === 'RelationScopeSection' || 
                                comp.type?.__name === 'RelationScopeSection') {
                                return comp;
                            }
                            if (comp.subTree?.component) {
                                return findSection(comp.subTree.component);
                            }
                            if (comp.ctx?.$ && findSection(comp.ctx.$)) {
                                return findSection(comp.ctx.$);
                            }
                            return null;
                        };
                        
                        // 简化: 直接检查 panel 内的元素
                        const section = panel.querySelector('.rss-root');
                        if (!section) return { error: 'no rss-root' };
                        
                        const sectionVc = section.__vueParentComponent;
                        if (!sectionVc) return { error: 'no section vc' };
                        
                        // 检查 setupState
                        const setup = sectionVc.setupState || {};
                        return {
                            allRelationships: setup.allRelationships?.length || 0,
                            businessObjects: setup.businessObjects?.length || 0,
                            classifierLoading: setup.classifierLoading,
                            loadError: setup.loadError,
                            hasData: setup.hasData
                        };
                    }
                }
                return { error: 'panel not found' };
            }
        """)
        print(f"Vue State: {vue_state}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
