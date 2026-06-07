"""
OSS/RSS 树测试辅助函数

封装非标准 CSS 选择器、面板展开、树交互等测试所需的领域知识。
所有函数接受 PlaywrightCLI 实例作为第一个参数。

选择器速查:
  OSS label: [data-testid="oss-tree-label"] 或 .oss-node-label
  RSS label: [data-testid="rss-tree-label"] 或 .rss-node-label
  OSS tree:  document.querySelectorAll('.el-tree')[0]
  RSS tree:  document.querySelectorAll('.el-tree')[1]
  OSS/RSS 面板: .rst-panel-object / .rst-panel-relation
  面板 header:  .collapsible-panel__header
  checkbox:     .el-checkbox__original

使用示例:
    from test_helpers.tree_helpers import (
        expand_all_panels, get_rss_labels, click_oss_by_label,
        get_rss_component_state, wait_tree_stable
    )
    with PlaywrightCLI() as cli:
        cli.authenticated_navigate(...)
        expand_all_panels(cli)
        labels = get_rss_labels(cli)
        # labels: ['范围内', '同子领域跨服务模块', ...]
"""

import time
import json


# ============================================================
# Selectors
# ============================================================

OSS_TREE_SEL = "document.querySelectorAll('.el-tree')[0]"
RSS_TREE_SEL = "document.querySelectorAll('.el-tree')[1]"
OSS_LABEL_SEL = "[data-testid='oss-tree-label']"
RSS_LABEL_SEL = "[data-testid='rss-tree-label']"
OSS_PANEL_SEL = ".rst-panel-object"
RSS_PANEL_SEL = ".rst-panel-relation"


# ============================================================
# Panel operations
# ============================================================

def _expand_panel(cli, panel_selector: str):
    """展开折叠面板（内部），仅展开不切换"""
    cli.evaluate(f"""() => {{
        const panel = document.querySelector('{panel_selector}');
        if (panel) {{
            const isCollapsed = panel.classList.contains('is-collapsed');
            if (isCollapsed) {{
                const header = panel.querySelector('.collapsible-panel__header');
                if (header) header.click();
            }}
        }}
    }}""")


def expand_oss_panel(cli):
    """展开 OSS（对象范围）折叠面板"""
    _expand_panel(cli, OSS_PANEL_SEL)


def expand_rss_panel(cli):
    """展开 RSS（关系范围）折叠面板"""
    _expand_panel(cli, RSS_PANEL_SEL)


def expand_all_panels(cli):
    """展开所有折叠面板"""
    expand_oss_panel(cli)
    expand_rss_panel(cli)


# ============================================================
# Tree label reading
# ============================================================

def get_oss_labels(cli) -> list:
    """获取 OSS 树所有节点的 label 文本"""
    return cli.evaluate(f"""
        () => Array.from(document.querySelectorAll(`{OSS_LABEL_SEL}`))
            .map(el => el.textContent.trim())
    """)


def get_rss_labels(cli) -> list:
    """获取 RSS 树所有节点的 label 文本"""
    return cli.evaluate(f"""
        () => Array.from(document.querySelectorAll(`{RSS_LABEL_SEL}`))
            .map(el => el.textContent.trim())
    """)


def get_oss_node_count(cli) -> int:
    """获取 OSS 树节点总数（包括隐藏的）"""
    return cli.evaluate(f"({OSS_TREE_SEL})?.querySelectorAll('.el-tree-node').length || 0")


def get_rss_node_count(cli) -> int:
    """获取 RSS 树节点总数（包括隐藏的）"""
    return cli.evaluate(f"({RSS_TREE_SEL})?.querySelectorAll('.el-tree-node').length || 0")


def get_rss_visible_nodes(cli) -> list[dict]:
    """获取 RSS 树当前可见的节点详情"""
    return cli.evaluate(f"""() => {{
        const tree = {RSS_TREE_SEL};
        if (!tree) return [];
        const nodes = tree.querySelectorAll('.el-tree-node');
        const result = [];
        nodes.forEach((n, i) => {{
            if (n.offsetHeight > 0) {{
                const label = n.querySelector(`{RSS_LABEL_SEL}`);
                result.push({{
                    idx: i,
                    label: label ? label.textContent.trim().substring(0, 60) : '-',
                    expanded: n.classList.contains('is-expanded'),
                    leaf: n.classList.contains('is-leaf'),
                    childCount: n.querySelectorAll('.el-tree-node__children .el-tree-node').length
                }});
            }}
        }});
        return result;
    }}""")


# ============================================================
# Tree checkbox interaction
# ============================================================

def click_oss_by_label(cli, label_text: str, exact: bool = True) -> bool:
    """
    通过 label 文本点击 OSS 树对应 checkbox

    Args:
        cli: PlaywrightCLI 实例
        label_text: 要点击的节点 label 文本
        exact: True=精确匹配, False=包含匹配

    Returns:
        是否成功点击
    """
    match_fn = "l.textContent.trim() === text" if exact else "l.textContent.trim().includes(text)"
    page = cli._ensure_browser()
    js_code = f"""(text) => {{
        const labels = document.querySelectorAll(`{OSS_LABEL_SEL}`);
        for (const l of labels) {{
            const trimmed = l.textContent.trim();
            if ({match_fn}) {{
                const content = l.closest('.el-tree-node__content');
                if (content) {{
                    content.click();
                    return {{ clicked: true, label: trimmed, path: 'content' }};
                }}
                const node = l.closest('.el-tree-node');
                const cb = node?.querySelector('.el-checkbox__original');
                if (cb) {{ cb.click(); return {{ clicked: true, label: trimmed, path: 'checkbox' }}; }}
                l.click();
                return {{ clicked: true, label: trimmed, path: 'label' }};
            }}
        }}
        return {{ clicked: false }};
    }}"""
    result = page.evaluate(js_code, label_text)
    return (result or {}).get('clicked', False)


def click_rss_by_label(cli, label_text: str, exact: bool = True) -> bool:
    """通过 label 文本点击 RSS 树对应 checkbox"""
    match_fn = "l.textContent.trim() === text" if exact else "l.textContent.trim().includes(text)"
    result = cli.evaluate(f"""(text) => {{
        const labels = document.querySelectorAll(`{RSS_LABEL_SEL}`);
        for (const l of labels) {{
            const trimmed = l.textContent.trim();
            if ({match_fn}) {{
                const content = l.closest('.el-tree-node__content');
                if (content) {{
                    content.click();
                    return {{ clicked: true, label: trimmed, path: 'content' }};
                }}
                const node = l.closest('.el-tree-node');
                const cb = node?.querySelector('.el-checkbox__original');
                if (cb) {{ cb.click(); return {{ clicked: true, label: trimmed, path: 'checkbox' }}; }}
                l.click();
                return {{ clicked: true, label: trimmed, path: 'label' }};
            }}
        }}
        return {{ clicked: false }};
    }}""", label_text)
    return (result or {}).get('clicked', False)


# ============================================================
# Component state (via _test expose)
# ============================================================

def get_rss_component_state(cli) -> dict:
    """获取 RelationScopeSection 组件内部状态

    优先使用 comp.exposed._test（正式暴露接口），
    回退到 comp.setupState（Vue 内部 API）。
    """
    return cli.evaluate("""() => {
        let comp = document.querySelectorAll('.el-tree')[1]?.__vueParentComponent;
        for (let i = 0; i < 20 && comp; i++) {
            if (comp.type?.__name === 'RelationScopeSection') {
                // 优先使用 exposed._test
                if (comp.exposed?._test) {
                    const t = comp.exposed._test;
                    return {
                        source: '_test',
                        hasData: t.hasData,
                        loading: t.loading,
                        error: t.error,
                        relationCount: t.relationCount,
                        filterParams: t.filterParams,
                        selectedCodes: t.selectedCodes,
                        treeDataLen: Array.isArray(t.treeData) ? t.treeData.length : 0
                    };
                }
                // 回退到 setupState
                const ss = comp.setupState;
                if (ss) {
                    const td = ss.classifierTreeData;
                    const len = td?.value?.length ?? td?.length ?? 0;
                    return {
                        source: 'setupState',
                        loading: ss.classifierLoading?.value ?? false,
                        relationCount: ss.allRelationships?.value?.length || 0,
                        treeDataLen: len,
                        hasData: len > 0,
                        error: ss.loadError?.value || null
                    };
                }
                return { error: 'no state accessible', exposedKeys: comp.exposed ? Object.keys(comp.exposed) : [] };
            }
            comp = comp.parent;
        }
        return { error: 'RelationScopeSection not found' };
    }""")


def get_oss_component_state(cli) -> dict:
    """获取 ObjectScopeSection 组件内部状态"""
    return cli.evaluate("""() => {
        let comp = document.querySelectorAll('.el-tree')[0]?.__vueParentComponent;
        for (let i = 0; i < 20 && comp; i++) {
            if (comp.type?.__name === 'ObjectScopeSection') {
                if (comp.exposed?._test) {
                    const t = comp.exposed._test;
                    return {
                        source: '_test',
                        loading: t.loading,
                        nodeCount: t.nodeCount,
                        checkedKeyCount: t.checkedKeys?.length || 0,
                        checkedNodeCount: t.checkedNodeCount
                    };
                }
                const ss = comp.setupState;
                if (ss) {
                    return {
                        source: 'setupState',
                        loading: ss.loading?.value ?? false,
                        nodeCount: ss.treeData?.value?.length || 0,
                        checkedKeyCount: 0 // setupState can't easily get ElTree methods
                    };
                }
                return { error: 'no state accessible' };
            }
            comp = comp.parent;
        }
        return { error: 'ObjectScopeSection not found' };
    }""")


# ============================================================
# Waiting helpers
# ============================================================

def wait_tree_stable(cli, tree_index: int = 0, min_nodes: int = 1,
                     timeout: int = 15000) -> bool:
    """
    等待 el-tree 渲染稳定（至少有 min_nodes 个可见节点）

    Args:
        cli: PlaywrightCLI 实例
        tree_index: 0=OSS tree, 1=RSS tree
        min_nodes: 最少可见节点数
        timeout: 超时 ms

    Returns:
        是否成功等到
    """
    start = time.time()
    while (time.time() - start) * 1000 < timeout:
        visible = cli.evaluate(f"""() => {{
            const tree = document.querySelectorAll('.el-tree')[{tree_index}];
            if (!tree) return 0;
            let count = 0;
            tree.querySelectorAll('.el-tree-node').forEach(n => {{
                if (n.offsetHeight > 0) count++;
            }});
            return count;
        }}""")
        if visible >= min_nodes:
            return True
        time.sleep(0.5)
    return False


def wait_rss_filter_applied(cli, timeout: int = 10000) -> bool:
    """
    等待 RSS filter 生效（visible nodes 发生变化后再稳定）

    适用于 OSS 点击后等待 RSS 树重新加载的场景。
    """
    start = time.time()
    prev = get_rss_visible_nodes(cli)
    prev_count = len(prev)

    while (time.time() - start) * 1000 < timeout:
        time.sleep(1)
        curr = get_rss_visible_nodes(cli)
        curr_count = len(curr)
        if curr_count != prev_count:
            # 数量已变化，等待一下确认稳定
            time.sleep(1.5)
            after = get_rss_visible_nodes(cli)
            if len(after) == curr_count:
                return True
            prev = after
            prev_count = len(after)
    return False
