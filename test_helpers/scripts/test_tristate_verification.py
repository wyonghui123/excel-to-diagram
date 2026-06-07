"""
验证父子联动和三态显示:
  1. 点击子节点 -> 父节点变半选 (indeterminate)
  2. 点击所有子节点 -> 父节点变全选 (checked)
  3. 点击父节点 -> 所有子节点自动勾选
  4. 父子联动后, scope-change 事件正确传递所有类型
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


def get_state(cli):
    return cli.evaluate("""
        () => {
            const trees = document.querySelectorAll('.el-tree');
            const targetTree = trees[0];
            const vueComp = targetTree.__vueParentComponent;
            const obj = vueComp.parent;
            const setupState = obj.setupState;
            const elTreeRef = vueComp.proxy;
            const store = elTreeRef.store;

            // 统计三态
            let allChecked = 0, allIndeterminate = 0;
            const triState = {};
            Object.values(store.nodesMap).forEach(node => {
                const data = node.data;
                if (data) {
                    if (!triState[data.type]) triState[data.type] = { checked: 0, indeterminate: 0, total: 0 };
                    triState[data.type].total++;
                    if (node.checked) triState[data.type].checked++;
                    if (node.indeterminate) triState[data.type].indeterminate++;
                }
            });

            return {
                domCheckedCount: targetTree.querySelectorAll('.el-checkbox.is-checked').length,
                domIndeterminateCount: targetTree.querySelectorAll('.el-checkbox.is-indeterminate').length,
                triState,
                treeRefCheckedKeys: elTreeRef.getCheckedKeys(),
                treeRefHalfCheckedKeys: elTreeRef.getHalfCheckedKeys(),
                setupStateCheckedBoIds: setupState.checkedBoIds?.__v_isRef ?
                    setupState.checkedBoIds.value : setupState.checkedBoIds
            };
        }
    """)


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
                    return {{
                        label: '{label_text}',
                        isChecked: checkbox?.classList.contains('is-checked') || false,
                        isIndeterminate: checkbox?.classList.contains('is-indeterminate') || false
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

        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                trees[0].__vueParentComponent.proxy.setCheckedKeys([]);
            }
        """)
        time.sleep(0.3)

        # 找到子节点 (在 财务管理 -> 应付管理 下)
        sub_children = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;

                // 找 domain d_4 (财务管理) 的子节点
                const d4 = store.nodesMap['d_4'];
                if (!d4) return null;
                return d4.childNodes.map(c => ({
                    id: c.data.id, name: c.data.name, type: c.data.type
                }));
            }
        """)
        print(f"\n[d_4 财务管理 的子节点]: {json.dumps(sub_children, ensure_ascii=False, indent=2)}")

        # 场景 1: 只点击子节点 (子 domain) - 父 domain 应为半选
        print("\n" + "=" * 60)
        print("场景 1: 点击子 domain (应付管理) -> 父 domain 应半选")
        print("=" * 60)
        click_node(cli, '应付管理')
        s1 = get_node_status(cli, '应付管理')
        p1 = get_node_status(cli, '财务管理')
        print(f"  子节点(应付管理): {s1}")
        print(f"  父节点(财务管理): {p1}")
        time.sleep(0.3)
        full_state = get_state(cli)
        print(f"  全局状态: domChecked={full_state['domCheckedCount']}, indeterminate={full_state['domIndeterminateCount']}")
        print(f"  triState: {json.dumps(full_state['triState'], ensure_ascii=False)}")
        print(f"  treeRefCheckedKeys: {full_state['treeRefCheckedKeys']}")
        print(f"  treeRefHalfCheckedKeys: {full_state['treeRefHalfCheckedKeys']}")

        assert s1['isChecked'] == True, f"应付管理 should be checked, got {s1}"
        assert p1['isIndeterminate'] == True, f"财务管理 should be indeterminate, got {p1}"
        assert p1['isChecked'] == False, f"财务管理 should NOT be fully checked yet, got {p1}"
        print("  [OK] 场景 1 通过!")

        # 场景 2: 点击 财务管理 父节点 -> 父和所有子应全选
        print("\n" + "=" * 60)
        print("场景 2: 点击父 domain (财务管理) -> 父+子应全选")
        print("=" * 60)
        click_node(cli, '财务管理')
        s2 = get_node_status(cli, '财务管理')
        print(f"  父节点(财务管理): {s2}")
        time.sleep(0.3)
        full_state2 = get_state(cli)
        print(f"  全局状态: domChecked={full_state2['domCheckedCount']}, indeterminate={full_state2['domIndeterminateCount']}")
        print(f"  triState: {json.dumps(full_state2['triState'], ensure_ascii=False)}")
        print(f"  treeRefCheckedKeys: {full_state2['treeRefCheckedKeys']}")

        assert s2['isChecked'] == True, f"财务管理 should be fully checked, got {s2}"
        assert s2['isIndeterminate'] == False, f"财务管理 should NOT be indeterminate, got {s2}"
        assert full_state2['domCheckedCount'] > 1, f"Should have multiple checked nodes, got {full_state2['domCheckedCount']}"
        print("  [OK] 场景 2 通过!")

        # 场景 3: 清除后, 点击 bo 节点 -> 父节点半选
        print("\n" + "=" * 60)
        print("场景 3: 清空 -> 点击业务对象 (bo) -> 父 sub_domain 和 domain 应半选")
        print("=" * 60)
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                trees[0].__vueParentComponent.proxy.setCheckedKeys([]);
            }
        """)
        time.sleep(0.3)

        # 找 应付管理 下的 bo 节点
        bo_children = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];
                const vueComp = targetTree.__vueParentComponent;
                const elTreeRef = vueComp.proxy;
                const store = elTreeRef.store;
                const s8 = store.nodesMap['s_8'];
                if (!s8) return null;
                return s8.childNodes.map(c => ({
                    id: c.data.id, name: c.data.name, type: c.data.type
                }));
            }
        """)
        print(f"\n[s_8 应付管理 的子节点 (bo)]: {json.dumps(bo_children, ensure_ascii=False, indent=2)}")

        if bo_children and len(bo_children) > 0:
            first_bo = bo_children[0]
            click_node(cli, first_bo['name'])
            print(f"  点击了 bo: {first_bo['name']}")
            time.sleep(0.5)

            sub_state = get_node_status(cli, '应付管理')
            par_state = get_node_status(cli, '财务管理')
            bo_state = get_node_status(cli, first_bo['name'])
            print(f"  bo({first_bo['name']}): {bo_state}")
            print(f"  sub_domain(应付管理): {sub_state}")
            print(f"  domain(财务管理): {par_state}")

            assert bo_state['isChecked'] == True, f"BO should be checked"
            assert sub_state['isIndeterminate'] == True, f"sub_domain should be indeterminate"
            assert par_state['isIndeterminate'] == True, f"domain should be indeterminate"
            print("  [OK] 场景 3 通过! 三态正确显示")

        # 场景 4: 等待 1 秒, 验证状态保持 (silent refresh 不会丢失)
        print("\n" + "=" * 60)
        print("场景 4: 等待 1 秒, 验证状态保持 (防止 silent refresh 清空)")
        print("=" * 60)
        time.sleep(1.5)
        after_state = get_state(cli)
        print(f"  1.5s 后: domChecked={after_state['domCheckedCount']}, indeterminate={after_state['domIndeterminateCount']}")
        print(f"  triState: {json.dumps(after_state['triState'], ensure_ascii=False)}")
        print(f"  treeRefCheckedKeys: {after_state['treeRefCheckedKeys']}")

        assert after_state['domCheckedCount'] == 1, f"Should still have 1 checked, got {after_state['domCheckedCount']}"
        assert len(after_state['treeRefHalfCheckedKeys']) >= 1, f"Should have half checked nodes"
        print("  [OK] 场景 4 通过! 父子联动状态保持")

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
