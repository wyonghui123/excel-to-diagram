"""
正确的三态验证: 使用正确的 DOM 选择器
正确结构: <label class="el-checkbox"><span class="el-checkbox__input is-indeterminate">
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


def get_node_status(cli, label_text):
    return cli.evaluate(f"""
        () => {{
            const trees = document.querySelectorAll('.el-tree');
            const targetTree = trees[0];
            const nodes = targetTree.querySelectorAll('.el-tree-node');
            for (const node of nodes) {{
                const labelEl = node.querySelector('.oss-node-label');
                if (labelEl?.textContent?.trim() === '{label_text}') {{
                    const checkbox = node.querySelector('.el-checkbox');
                    // Element Plus el-checkbox 内部: .el-checkbox__input 上有 is-indeterminate
                    const innerInput = node.querySelector('.el-checkbox__input');
                    return {{
                        label: '{label_text}',
                        // 父级 (el-checkbox) 上的 class
                        isChecked: checkbox?.classList.contains('is-checked') || false,
                        // 子级 (el-checkbox__input) 上的 class
                        isCheckedInner: innerInput?.classList.contains('is-checked') || false,
                        isIndeterminate: innerInput?.classList.contains('is-indeterminate') || false,
                        ariaChecked: checkbox?.getAttribute('aria-checked')
                    }};
                }}
            }}
            return null;
        }}
    """)


def click_node(cli, label_text):
    cli.evaluate(f"""
        () => {{
            const trees = document.querySelectorAll('.el-tree');
            const targetTree = trees[0];
            const nodes = targetTree.querySelectorAll('.el-tree-node');
            for (const node of nodes) {{
                const labelEl = node.querySelector('.oss-node-label');
                if (labelEl?.textContent?.trim() === '{label_text}') {{
                    const checkbox = node.querySelector('.el-checkbox');
                    if (checkbox) checkbox.click();
                    return;
                }}
            }}
        }}
    """)
    time.sleep(0.5)


def get_state(cli):
    return cli.evaluate("""
        () => {
            const trees = document.querySelectorAll('.el-tree');
            const targetTree = trees[0];
            const vueComp = targetTree.__vueParentComponent;
            const elTreeRef = vueComp.proxy;

            return {
                domCheckedCount: targetTree.querySelectorAll('.el-checkbox__input.is-checked').length,
                domIndeterminateCount: targetTree.querySelectorAll('.el-checkbox__input.is-indeterminate').length,
                treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                treeRefHalfCheckedKeys: elTreeRef.getHalfCheckedKeys()
            };
        }
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
                print(f"[OK] 找到 {tree_count} 个 el-tree")
                break
            time.sleep(1)

        # 获取树信息
        sub_children = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const d4 = store.nodesMap['d_4'];
                return d4 ? d4.childNodes.map(c => ({ id: c.data.id, name: c.data.name, type: c.data.type })) : [];
            }
        """)
        print(f"\n[d_4 财务管理 的子节点]: {json.dumps(sub_children, ensure_ascii=False)}")

        # 场景 1: 只点击子节点 -> 父节点半选
        print("\n" + "=" * 60)
        print("场景 1: 点击子节点 (应付管理) -> 父 domain 应半选")
        print("=" * 60)

        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                trees[0].__vueParentComponent.proxy.setCheckedKeys([]);
            }
        """)
        time.sleep(0.3)

        click_node(cli, '应付管理')
        sub = get_node_status(cli, '应付管理')
        par = get_node_status(cli, '财务管理')
        print(f"  子 (应付管理): {sub}")
        print(f"  父 (财务管理): {par}")

        state = get_state(cli)
        print(f"  state: {json.dumps(state, ensure_ascii=False)}")

        assert sub['isChecked'] or sub['isCheckedInner'], "应付管理 should be checked"
        assert par['isIndeterminate'] == True, f"财务管理 should be indeterminate, got {par}"
        print("  [OK] 场景 1 通过!")

        # 场景 2: 点击 财务管理 父 -> 父+子应全选
        print("\n" + "=" * 60)
        print("场景 2: 点击父 domain (财务管理) -> 父+子应全选")
        print("=" * 60)
        click_node(cli, '财务管理')
        par2 = get_node_status(cli, '财务管理')
        sub2 = get_node_status(cli, '应付管理')
        sub2b = get_node_status(cli, '应收管理')
        print(f"  父 (财务管理): {par2}")
        print(f"  子1 (应付管理): {sub2}")
        print(f"  子2 (应收管理): {sub2b}")

        state2 = get_state(cli)
        print(f"  state: {json.dumps(state2, ensure_ascii=False)}")

        assert par2['isChecked'] or par2['isCheckedInner'], "财务管理 should be fully checked"
        assert par2['isIndeterminate'] == False, "财务管理 should NOT be indeterminate"
        assert sub2['isChecked'] or sub2['isCheckedInner'], "应付管理 should be checked"
        assert sub2b['isChecked'] or sub2b['isCheckedInner'], "应收管理 should be checked"
        print("  [OK] 场景 2 通过!")

        # 场景 3: 清空, 点击 bo -> 父 sub_domain 和 domain 都半选
        print("\n" + "=" * 60)
        print("场景 3: 清空, 点击 bo -> 父 sub_domain 和 domain 应半选")
        print("=" * 60)
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                trees[0].__vueParentComponent.proxy.setCheckedKeys([]);
            }
        """)
        time.sleep(0.3)

        bo_children = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const s8 = store.nodesMap['s_8'];
                return s8 ? s8.childNodes.map(c => ({ id: c.data.id, name: c.data.name, type: c.data.type })) : [];
            }
        """)
        print(f"\n[s_8 应付管理 的子节点 (bo)]: {json.dumps(bo_children, ensure_ascii=False)}")

        if bo_children and len(bo_children) > 0:
            first_bo = bo_children[0]
            click_node(cli, first_bo['name'])
            print(f"\n  点击了 bo: {first_bo['name']}")
            time.sleep(0.5)

            bo_st = get_node_status(cli, first_bo['name'])
            sub_st = get_node_status(cli, '应付管理')
            par_st = get_node_status(cli, '财务管理')
            print(f"  bo ({first_bo['name']}): {bo_st}")
            print(f"  sub_domain (应付管理): {sub_st}")
            print(f"  domain (财务管理): {par_st}")

            assert bo_st['isChecked'] or bo_st['isCheckedInner'], "BO should be checked"
            assert sub_st['isIndeterminate'] == True, f"sub_domain 应半选, got {sub_st}"
            assert par_st['isIndeterminate'] == True, f"domain 应半选, got {par_st}"
            print("  [OK] 场景 3 通过! 三态正确显示")

        # 场景 4: 点击父 domain 全选所有 bo
        print("\n" + "=" * 60)
        print("场景 4: 点击 domain 父节点 -> 所有 bo 联动全选")
        print("=" * 60)
        click_node(cli, '财务管理')
        time.sleep(0.5)
        par4 = get_node_status(cli, '财务管理')
        sub4 = get_node_status(cli, '应付管理')
        state4 = get_state(cli)
        print(f"  父 (财务管理): {par4}")
        print(f"  sub_domain (应付管理): {sub4}")
        print(f"  state: {json.dumps(state4, ensure_ascii=False)}")

        assert par4['isChecked'] or par4['isCheckedInner'], "财务管理 should be fully checked"
        assert sub4['isChecked'] or sub4['isCheckedInner'], "应付管理 should be fully checked"
        print("  [OK] 场景 4 通过! 父子联动全选正确")

        # 场景 5: 1.5s 后状态保持
        print("\n" + "=" * 60)
        print("场景 5: 1.5s 后状态保持 (防止 silent refresh 清空)")
        print("=" * 60)
        time.sleep(1.5)
        state5 = get_state(cli)
        print(f"  state: {json.dumps(state5, ensure_ascii=False)}")
        assert state5['domCheckedCount'] >= 2, f"应仍有 2+ checked, got {state5['domCheckedCount']}"
        print("  [OK] 场景 5 通过!")

        cli.screenshot('tristate_final.png')

        print("\n" + "=" * 60)
        print("所有三态场景通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[FAIL] 验证失败: {e}")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
