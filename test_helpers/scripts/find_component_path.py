"""
打印所有组件树结构, 定位 ObjectScopeSection 的真实位置
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

        # 打印所有组件树
        result = cli.evaluate("""
            () => {
                const allComps = [];

                const walk = (comp, depth = 0, path = '') => {
                    if (depth > 50 || !comp) return;
                    const name = comp.type?.__name || comp.type?.name || comp.type?.__file?.split('/').pop() || 'Anonymous';
                    const allNames = [name];
                    if (comp.type?.__name) allNames.push(comp.type.__name);
                    if (comp.subTree) {
                        const cname = comp.subTree.type?.__name || comp.subTree.type?.name || '';
                        if (cname) allNames.push(cname);
                    }

                    allComps.push({
                        name,
                        uid: comp.uid,
                        depth,
                        path: path.substring(0, 100),
                        hasSetupState: !!comp.setupState,
                        setupStateKeys: comp.setupState ? Object.keys(comp.setupState).slice(0, 20) : []
                    });

                    if (comp.subTree) {
                        walk(comp.subTree, depth + 1, path + '>subTree');
                    }
                    const children = comp.componentTree || [];
                    for (let i = 0; i < children.length; i++) {
                        walk(children[i], depth + 1, path + '>child[' + i + ']');
                    }
                };

                const app = document.querySelector('#app')?.__vue_app__;
                if (!app) return { error: 'No app' };

                walk(app._instance);

                // 搜索可能与 el-tree 相关的组件
                const treeRelatedComps = allComps.filter(c =>
                    c.name.toLowerCase().includes('scope') ||
                    c.name.toLowerCase().includes('object') ||
                    c.name.toLowerCase().includes('tree') ||
                    c.name.toLowerCase().includes('relation')
                );

                return {
                    totalComps: allComps.length,
                    treeRelated: treeRelatedComps,
                    // 列出所有组件名 (去重)
                    allNames: [...new Set(allComps.map(c => c.name))].sort()
                };
            }
        """)

        print(f"\n[总组件数] {result.get('totalComps')}")
        print(f"\n[所有组件名 (去重)]: {result.get('allNames', [])}")
        print(f"\n[与 tree/scope 相关的组件] ({len(result.get('treeRelated', []))} 个):")
        for comp in result.get('treeRelated', []):
            print(f"  - {comp['name']} (uid={comp['uid']}, depth={comp['depth']}, path={comp['path']})")
            print(f"    setupState 键: {comp.get('setupStateKeys', [])}")

        # 找到 el-tree 容器并追溯父组件链
        print("\n\n[El-tree 父组件链]:")
        tree_chain = cli.evaluate("""
            () => {
                const trees = document.querySelectorAll('.el-tree');
                const results = [];

                for (let i = 0; i < trees.length; i++) {
                    const tree = trees[i];
                    const chain = [];
                    let current = tree.__vueParentComponent;
                    let depth = 0;
                    while (current && depth < 30) {
                        chain.push({
                            name: current.type?.__name || current.type?.name || 'Anonymous',
                            uid: current.uid,
                            depth
                        });
                        current = current.parent;
                        depth++;
                    }
                    results.push({
                        treeIndex: i,
                        chain: chain.slice(0, 15)
                    });
                }

                return results;
            }
        """)
        print(json.dumps(tree_chain, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()


if __name__ == "__main__":
    main()
