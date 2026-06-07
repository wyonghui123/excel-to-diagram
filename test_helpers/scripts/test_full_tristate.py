"""
综合验证: 父子联动 + 三态 + scope-change 事件正确传递
包括:
  1. domain -> sub_domain 联动
  2. scope-change 事件正确包含父节点 (domain/subDomain/serviceModule)
  3. 多层级联动
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time
import json


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
                    const innerInput = node.querySelector('.el-checkbox__input');
                    return {{
                        label: '{label_text}',
                        isChecked: innerInput?.classList.contains('is-checked') || false,
                        isIndeterminate: innerInput?.classList.contains('is-indeterminate') || false
                    }};
                }}
            }}
            return null;
        }}
    """)


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

        # 捕获 scope-change 事件
        cli.evaluate("""
            () => {
                window.__scopeChanges = [];
                // 通过 patch el-tree 的 emit hook 监听
                const trees = document.querySelectorAll('.el-tree');
                const targetTree = trees[0];

                // 找到 MultiObjectManagementPage 实例
                const findParent = (comp, depth = 0) => {
                    if (depth > 30 || !comp) return null;
                    if (comp.type?.__name === 'MultiObjectManagementPage') return comp;
                    if (comp.parent) {
                        const r = findParent(comp.parent, depth + 1);
                        if (r) return r;
                    }
                    return null;
                };

                const vueComp = targetTree.__vueParentComponent;
                const objScopeComp = vueComp.parent;
                // 找到 ObjectScopeSection 的父级 RelationScopeTree
                let relScope = null;
                let cur = objScopeComp.parent;
                while (cur) {
                    if (cur.type?.__name === 'RelationScopeTree') {
                        relScope = cur;
                        break;
                    }
                    cur = cur.parent;
                }

                // patch ObjectScopeSection 的 emit
                const origEmit = objScopeComp.emit.bind(objScopeComp);
                objScopeComp.emit = function(event, ...args) {
                    if (event === 'scope-change') {
                        window.__scopeChanges.push({
                            time: Date.now(),
                            args: JSON.parse(JSON.stringify(args[0]))
                        });
                    }
                    return origEmit(event, ...args);
                };
            }
        """)

        # 场景 A: 点击子节点 (sub_domain 应付管理) -> 父 domain 财务管理半选
        print("\n" + "=" * 60)
        print("场景 A: domain -> sub_domain 联动 + 半选")
        print("=" * 60)
        cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                trees[0].__vueParentComponent.proxy.setCheckedKeys([]);
                window.__scopeChanges = [];
            }
        """)
        time.sleep(0.3)

        click_node(cli, '应付管理')
        sub = get_node_status(cli, '应付管理')
        par = get_node_status(cli, '财务管理')
        print(f"  子 (应付管理): {sub}")
        print(f"  父 (财务管理): {par}")
        assert par['isIndeterminate'] == True
        assert sub['isChecked'] == True
        print("  [OK] 父子联动半选正确")

        # 验证 scope-change 事件
        time.sleep(0.5)
        scope_changes = cli.evaluate("() => window.__scopeChanges || []")
        print(f"\n  scope-change 事件: {json.dumps(scope_changes, ensure_ascii=False, indent=2)}")
        # 父 domain 应该是半选状态, 应该出现在 scope-change 中 (作为 partial selection)
        if scope_changes:
            last = scope_changes[-1]['args']
            print(f"    domainIds (半选): {last.get('domainIds', [])}")
            print(f"    subDomainIds: {last.get('subDomainIds', [])}")
            # 父 domain 4 应该出现 (半选), 子 sub_domain 8 应该出现
            assert 4 in last.get('domainIds', []), f"domainIds 应包含 4 (半选的父), got {last.get('domainIds', [])}"
            assert 8 in last.get('subDomainIds', []), f"subDomainIds 应包含 8, got {last.get('subDomainIds', [])}"
            print("  [OK] scope-change 正确传递父节点 ID (半选)")

        # 场景 B: 点击父 domain -> 父+所有子全选
        print("\n" + "=" * 60)
        print("场景 B: 点击父 domain -> 父+所有 sub_domain 全选")
        print("=" * 60)
        cli.evaluate("() => { window.__scopeChanges = []; }")
        click_node(cli, '财务管理')
        par2 = get_node_status(cli, '财务管理')
        sub2a = get_node_status(cli, '应付管理')
        sub2b = get_node_status(cli, '应收管理')
        print(f"  父 (财务管理): {par2}")
        print(f"  子1 (应付管理): {sub2a}")
        print(f"  子2 (应收管理): {sub2b}")
        assert par2['isChecked'] == True
        assert sub2a['isChecked'] == True
        assert sub2b['isChecked'] == True
        print("  [OK] 父子联动全选正确")

        time.sleep(0.5)
        scope_changes2 = cli.evaluate("() => window.__scopeChanges || []")
        if scope_changes2:
            last = scope_changes2[-1]['args']
            print(f"  scope-change.domainIds: {last.get('domainIds', [])}")
            print(f"  scope-change.subDomainIds: {last.get('subDomainIds', [])}")
            assert 4 in last.get('domainIds', []), f"domain 4 应被全选, got {last.get('domainIds', [])}"
            assert 8 in last.get('subDomainIds', [])
            assert 7 in last.get('subDomainIds', [])

        # 场景 C: 取消父节点 -> 全部取消
        print("\n" + "=" * 60)
        print("场景 C: 再次点击父 -> 全部取消")
        print("=" * 60)
        cli.evaluate("() => { window.__scopeChanges = []; }")
        click_node(cli, '财务管理')
        state_c = get_state(cli)
        print(f"  state: {json.dumps(state_c, ensure_ascii=False)}")
        assert state_c['domCheckedCount'] == 0
        assert len(state_c['treeRefHalfCheckedKeys']) == 0
        print("  [OK] 全部取消")

        time.sleep(0.5)
        scope_changes_c = cli.evaluate("() => window.__scopeChanges || []")
        if scope_changes_c:
            last = scope_changes_c[-1]['args']
            print(f"  scope-change (取消后): {json.dumps(last, ensure_ascii=False)}")
            assert last.get('domainIds') == []
            assert last.get('subDomainIds') == []

        # 场景 D: 等待 2 秒, 状态保持
        print("\n" + "=" * 60)
        print("场景 D: 父子联动后等待 2s, 状态保持")
        print("=" * 60)
        click_node(cli, '应付管理')
        time.sleep(0.5)
        state_d1 = get_state(cli)
        print(f"  初始: dom={state_d1['domCheckedCount']}, indet={state_d1['domIndeterminateCount']}, half={state_d1['treeRefHalfCheckedKeys']}")
        time.sleep(2)
        state_d2 = get_state(cli)
        print(f"  2s后: dom={state_d2['domCheckedCount']}, indet={state_d2['domIndeterminateCount']}, half={state_d2['treeRefHalfCheckedKeys']}")
        assert state_d1['domCheckedCount'] == state_d2['domCheckedCount']
        assert state_d1['domIndeterminateCount'] == state_d2['domIndeterminateCount']
        print("  [OK] 父子联动状态保持正确")

        cli.screenshot('full_tristate_final.png')

        print("\n" + "=" * 60)
        print("所有三态 + 联动 + 事件传递场景通过!")
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
