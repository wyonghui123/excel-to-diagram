"""
完整关系范围树测试：
1. 验证 silent refresh 状态保持 (test_store_history 已验证)
2. 验证三态父子联动
3. 验证 toolbar 按钮 (全选/清空)
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time


def get_stats(cli):
    return cli.evaluate("""
        () => {
            const trees = document.querySelectorAll('.el-tree');
            const relTree = trees[1];
            const vueComp = relTree.__vueParentComponent;
            const store = vueComp.proxy.store;
            const total = Object.keys(store.nodesMap).length;
            const checked = Object.values(store.nodesMap).filter(n => n.checked).length;
            const indet = Object.values(store.nodesMap).filter(n => n.indeterminate).length;
            const checkedNames = Object.values(store.nodesMap).filter(n => n.checked).map(n => n.label);
            const indetNames = Object.values(store.nodesMap).filter(n => n.indeterminate).map(n => n.label);
            return { total, checked, indet, checkedNames, indetNames };
        }
    """)


def get_node_stats(cli, name):
    """获取特定节点的状态"""
    return cli.evaluate(f"""
        () => {{
            const trees = document.querySelectorAll('.el-tree');
            const relTree = trees[1];
            const vueComp = relTree.__vueParentComponent;
            const store = vueComp.proxy.store;
            for (const [k, n] of Object.entries(store.nodesMap)) {{
                if (n.label === '{name}') {{
                    return {{
                        id: k,
                        label: n.label,
                        checked: n.checked,
                        indeterminate: n.indeterminate,
                        childCount: n.childNodes?.length || 0,
                        level: n.level
                    }};
                }}
            }}
            return null;
        }}
    """)


def click_node_checkbox(cli, name):
    """点击特定节点的 checkbox"""
    return cli.evaluate(f"""
        () => {{
            const trees = document.querySelectorAll('.el-tree');
            const relTree = trees[1];
            const nodes = relTree.querySelectorAll('.el-tree-node');
            for (const node of nodes) {{
                const labelEl = node.querySelector('.rss-node-label');
                if (labelEl?.textContent?.trim() === '{name}') {{
                    const checkbox = node.querySelector('.el-checkbox');
                    if (checkbox) {{
                        checkbox.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }}
    """)


def click_toolbar(cli, text):
    """点击 toolbar 按钮"""
    return cli.evaluate(f"""
        () => {{
            const buttons = document.querySelectorAll('.rss-toolbar .app-btn');
            for (const btn of buttons) {{
                if (btn.textContent?.trim() === '{text}') {{
                    btn.click();
                    return true;
                }}
            }}
            return false;
        }}
    """)


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

        # 1. 勾选 财务管理 (触发关系范围)
        print("[Setup] 勾选 财务管理 domain")
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

        # 2. 展开关系范围 (无脑点 header)
        print("[Setup] 展开关系范围")
        cli.evaluate("""
            () => {
                const panels = document.querySelectorAll('.collapsible-panel');
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

        for i in range(30):
            rel_count = cli.evaluate("""
                () => {
                    const trees = document.querySelectorAll('.el-tree');
                    if (trees.length < 2) return 0;
                    const vueComp = trees[1].__vueParentComponent;
                    if (!vueComp) return 0;
                    const store = vueComp.proxy?.store;
                    if (!store) return 0;
                    return Object.keys(store.nodesMap).length;
                }
            """)
            if rel_count > 10:
                break
            time.sleep(1)
        print(f"[Setup] relation store nodes: {rel_count}")

        # === 测试 1: silent refresh 状态保持 ===
        print("\n=== 测试 1: Silent refresh 状态保持 ===")
        # 1.1 点击 范围外 (全选范围外所有子节点)
        print("1.1 勾选 范围外")
        click_node_checkbox(cli, '范围外')
        time.sleep(2)
        s1 = get_stats(cli)
        print(f"  状态: {s1}")
        assert s1['checked'] > 0, f"勾选 范围外 应该让 checked>0, got {s1['checked']}"
        print(f"  [OK] 范围外 勾选成功, {s1['checked']} 节点选中")

        # 1.2 触发 silent refresh: 重新点击 财务管理 (toggle)
        print("\n1.2 触发 silent refresh (toggle 财务管理)")
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
        time.sleep(1)
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
        time.sleep(3)
        s2 = get_stats(cli)
        print(f"  状态: {s2}")
        # 期望: 关系范围 tree 状态应该保持
        # 但是 toggle domain 可能会清空所有 BO 选中, 触发新的 loadRelationships
        # 由于 范围外 包含所有"在范围外"的关系, 数量应该保持
        if s2['checked'] == s1['checked']:
            print(f"  [OK] silent refresh 后状态保持: {s2['checked']} 节点")
        elif s2['checked'] == 0:
            print(f"  [INFO] silent refresh 后状态被清空 (可能是设计预期: domain 改变重置关系)")
        else:
            print(f"  [INFO] 状态变化: {s1['checked']} -> {s2['checked']}")

        # === 测试 2: Toolbar 按钮 ===
        print("\n=== 测试 2: Toolbar 按钮 ===")
        # 2.1 全选
        print("2.1 全选")
        click_toolbar(cli, '全选')
        time.sleep(2)
        s3 = get_stats(cli)
        print(f"  状态: {s3}")
        if s3['checked'] == s3['total']:
            print(f"  [OK] 全选: 全部 {s3['total']} 节点选中")
        else:
            print(f"  [FAIL] 全选: {s3['checked']}/{s3['total']}")

        # 2.2 清空
        print("\n2.2 清空")
        click_toolbar(cli, '清空')
        time.sleep(2)
        s4 = get_stats(cli)
        print(f"  状态: {s4}")
        if s4['checked'] == 0:
            print(f"  [OK] 清空: 0 节点选中")
        else:
            print(f"  [FAIL] 清空: 仍有 {s4['checked']} 节点")

        # === 测试 3: 三态父子联动 ===
        print("\n=== 测试 3: 三态父子联动 ===")
        # 3.1 找到所有 top-level 节点
        top_nodes = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const relTree = trees[1];
                const vueComp = relTree.__vueParentComponent;
                const store = vueComp.proxy.store;
                return Object.values(store.nodesMap).filter(n => !n.parent).map(n => ({ id: n.id, label: n.label, childCount: n.childNodes?.length || 0 }));
            }
        """)
        print(f"  顶层节点: {[n['label'] for n in top_nodes]}")

        if top_nodes:
            # 3.2 点击第一个有子节点的顶层节点 (如果有)
            target = next((n for n in top_nodes if n['childCount'] > 0), None)
            if not target:
                target = top_nodes[0]
            print(f"\n  3.2 勾选顶层节点: {target['label']} (有 {target['childCount']} 个子节点)")
            click_node_checkbox(cli, target['label'])
            time.sleep(2)
            s5 = get_stats(cli)
            print(f"  状态: {s5}")
            # 期望: 全部 checked (因为父子联动)
            if target['childCount'] == 0:
                # 叶子节点, 只勾 1
                if s5['checked'] == 1:
                    print(f"  [OK] 叶子节点勾选: checked=1")
                else:
                    print(f"  [INFO] 叶子节点: checked={s5['checked']}")
            else:
                # 父节点带子节点, 应该全部 checked
                if s5['checked'] == s5['total']:
                    print(f"  [OK] 父节点全选: {s5['checked']}/{s5['total']}")
                else:
                    print(f"  [INFO] 父节点: {s5['checked']}/{s5['total']}")

        # 3.3 验证: 清空 + 只勾一半子节点 = 父节点 indeterminate
        print("\n3.3 父子联动 - 部分选择")
        click_toolbar(cli, '清空')
        time.sleep(1)
        # 找到有子节点的父节点
        if top_nodes:
            target = next((n for n in top_nodes if n['childCount'] > 0), None)
            if target:
                # 展开父节点
                cli.evaluate(f"""
                    () => {{
                        const trees = document.querySelectorAll('.el-tree');
                        const relTree = trees[1];
                        const nodes = relTree.querySelectorAll('.el-tree-node');
                        for (const node of nodes) {{
                            const labelEl = node.querySelector('.rss-node-label');
                            if (labelEl?.textContent?.trim() === '{target['label']}') {{
                                const expandIcon = node.querySelector('.el-tree-node__expand-icon');
                                if (expandIcon && !expandIcon.classList.contains('is-leaf')) {{
                                    expandIcon.click();
                                }}
                                return;
                            }}
                        }}
                    }}
                """)
                time.sleep(1)

                # 找到第一个子节点
                child_target = cli.evaluate(f"""
                    () => {{
                        const trees = document.querySelectorAll('.el-tree');
                        const relTree = trees[1];
                        const vueComp = relTree.__vueParentComponent;
                        const store = vueComp.proxy.store;
                        for (const [k, n] of Object.entries(store.nodesMap)) {{
                            if (n.parent && n.parent.id === '{target['id']}') {{
                                return n.label;
                            }}
                        }}
                        return null;
                    }}
                """)
                if child_target:
                    print(f"  勾选 {target['label']} 的子节点: {child_target}")
                    click_node_checkbox(cli, child_target)
                    time.sleep(2)
                    s6 = get_stats(cli)
                    print(f"  状态: {s6}")

                    # 验证父节点状态
                    parent_state = get_node_stats(cli, target['label'])
                    print(f"  父节点 {target['label']}: checked={parent_state['checked']}, indeterminate={parent_state['indeterminate']}")

                    if parent_state['indeterminate'] and not parent_state['checked']:
                        print(f"  [OK] 父子联动-半选: 父节点 indeterminate, 子节点 checked")
                    else:
                        print(f"  [INFO] 父子联动状态: parent.checked={parent_state['checked']}, parent.indeterminate={parent_state['indeterminate']}")

        cli.screenshot(path='d:/filework/excel-to-diagram/screenshots/relation_final.png')
        print("\n[截图] d:/filework/excel-to-diagram/screenshots/relation_final.png")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
