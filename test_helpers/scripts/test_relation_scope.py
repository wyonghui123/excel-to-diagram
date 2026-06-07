"""
关系范围树 checkbox 状态测试
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


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
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            time.sleep(1)

        # 1. 先在对象范围树中勾选 domain, 让关系范围树有数据
        print("\n[Step 1] 在对象范围树中勾选 domain")
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const objectTree = trees[0];  // 第一个 el-tree 是对象范围
                const nodes = objectTree.querySelectorAll('.el-tree-node');
                let clicked = 0;
                for (const node of nodes) {
                    const labelEl = node.querySelector('.oss-node-label');
                    if (labelEl?.textContent?.trim() === '财务管理') {
                        const checkbox = node.querySelector('.el-checkbox');
                        if (checkbox) {
                            checkbox.click();
                            clicked++;
                            break;
                        }
                    }
                }
                return clicked;
            }
        """)
        time.sleep(2)

        # 2. 展开"关系范围"折叠面板
        print("\n[Step 2] 展开'关系范围'折叠面板")
        cli.evaluate("""
            () => {
                // 找到 关系范围 折叠面板
                const panels = document.querySelectorAll('.collapsible-panel, .rst-panel-relation');
                for (const panel of panels) {
                    const title = panel.querySelector('.panel-title, .el-collapse-item__header, h3, [class*="title"]')?.textContent || '';
                    if (title.includes('关系范围')) {
                        // 找到 header 并点击
                        const header = panel.querySelector('.panel-header, [class*="header"]');
                        if (header) header.click();
                        return title;
                    }
                }
                return 'not found';
            }
        """)
        time.sleep(1.5)

        # 3. 等待关系树加载
        print("\n[Step 3] 等待关系树加载...")
        for i in range(10):
            relation_tree = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    for (const tree of trees) {
                        const nodeCount = tree.querySelectorAll('.el-tree-node').length;
                        if (nodeCount > 5) {
                            return { nodeCount, isLikely: true };
                        }
                    }
                    return { nodeCount: 0, isLikely: false };
                }
            """)
            if relation_tree.get('isLikely'):
                print(f"  [OK] 关系树已加载: {relation_tree['nodeCount']} nodes")
                break
            time.sleep(1)

        # 4. 列出所有 el-tree 及其节点
        cli.evaluate("""
            () => {
                window.__treeSnapshots = [];
                const trees = document.querySelectorAll('.el-tree');
                trees.forEach((tree, i) => {
                    const nodes = tree.querySelectorAll('.el-tree-node');
                    window.__treeSnapshots.push({
                        index: i,
                        nodeCount: nodes.length,
                        firstLabels: Array.from(nodes).slice(0, 5).map(n =>
                            n.querySelector('.rss-node-label, .oss-node-label')?.textContent?.trim() ||
                            n.querySelector('.el-tree-node__label')?.textContent?.trim()
                        )
                    });
                });
            }
        """)
        snapshots = cli.evaluate("() => window.__treeSnapshots")
        print(f"\n  所有 el-tree:")
        for s in snapshots:
            print(f"    tree[{s['index']}]: {s['nodeCount']} nodes, first labels: {s['firstLabels']}")

        # 5. 找关系范围树 (带 .rss-node-label 的)
        rel_tree_idx = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                for (let i = 0; i < trees.length; i++) {
                    if (trees[i].querySelector('.rss-node-label')) return i;
                }
                return -1;
            }
        """)
        print(f"\n  关系树 index: {rel_tree_idx}")

        if rel_tree_idx < 0:
            print("[ERROR] 关系树未找到")
            return

        # 6. 检查初始状态
        print("\n[Step 4] 检查初始状态")
        state_before = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[{rel_tree_idx}];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;

                return {{
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    domIndeterminateCount: targetTree.querySelectorAll('.el-checkbox__input.is-indeterminate').length,
                    nodeCount: targetTree.querySelectorAll('.el-tree-node').length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    treeRefHalfCheckedKeys: elTreeRef.getHalfCheckedKeys()
                }};
            }}
        """)
        print(f"  state: {json.dumps(state_before, ensure_ascii=False, indent=2)}")

        # 7. 找一个可点击的 checkbox
        print("\n[Step 5] 点击关系树的一个 checkbox")
        click_info = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[{rel_tree_idx}];
                const nodes = targetTree.querySelectorAll('.el-tree-node');
                for (let i = 0; i < nodes.length; i++) {{
                    const node = nodes[i];
                    const labelEl = node.querySelector('.rss-node-label');
                    if (!labelEl) continue;
                    const label = labelEl.textContent?.trim();
                    if (!label) continue;
                    const checkbox = node.querySelector('.el-checkbox');
                    if (checkbox) {{
                        const before = checkbox.querySelector('.el-checkbox__input')?.classList.contains('is-checked') || false;
                        checkbox.click();
                        return {{
                            clicked: true,
                            index: i,
                            label,
                            beforeChecked: before
                        }};
                    }}
                }}
                return {{ error: 'No checkbox found' }};
            }}
        """)
        print(f"  click: {json.dumps(click_info, ensure_ascii=False)}")
        time.sleep(1)

        # 8. 检查点击后状态
        print("\n[Step 6] 点击后状态")
        state_after = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[{rel_tree_idx}];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;

                return {{
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    domIndeterminateCount: targetTree.querySelectorAll('.el-checkbox__input.is-indeterminate').length,
                    nodeCount: targetTree.querySelectorAll('.el-tree-node').length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    treeRefHalfCheckedKeys: elTreeRef.getHalfCheckedKeys()
                }};
            }}
        """)
        print(f"  state: {json.dumps(state_after, ensure_ascii=False, indent=2)}")

        # 9. 等 1.5s, 看状态保持
        print("\n[Step 7] 等待 1.5s, 状态保持测试")
        time.sleep(1.5)
        state_final = cli.evaluate(f"""
            () => {{
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[{rel_tree_idx}];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;

                return {{
                    domCheckedCount: targetTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                    domIndeterminateCount: targetTree.querySelectorAll('.el-checkbox__input.is-indeterminate').length,
                    treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                    treeRefHalfCheckedKeys: elTreeRef.getHalfCheckedKeys()
                }};
            }}
        """)
        print(f"  state: {json.dumps(state_final, ensure_ascii=False, indent=2)}")

        cli.screenshot('relation_tree_state.png')

        # 10. 验证
        if state_after['domCheckedCount'] > 0 and state_final['domCheckedCount'] > 0:
            print("\n[OK] 关系树 checkbox 状态保持正常")
        else:
            print(f"\n[FAIL] 关系树 checkbox 状态异常")
            print(f"  before: {state_before['domCheckedCount']}")
            print(f"  after: {state_after['domCheckedCount']}")
            print(f"  final: {state_final['domCheckedCount']}")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
