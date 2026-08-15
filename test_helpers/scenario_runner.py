"""
scenario_runner.py - 图表调试"动作序列"运行器
======================================================================
[目的] 把"复现 → 操作 → 快照 → 对比"固化成可复用脚本:
  输入动作序列, 自动执行 + 在每个节点快照图表状态 + 输出差异摘要与 JSON.
  替代每次排查手写探针 (遍历节点/拼 selector/写 diff 逻辑) 的重复劳动.

[用法]
  from test_helpers.scenario_runner import ScenarioRunner

  runner = ScenarioRunner(scenario='mm-cross-domain')
  result = runner.run([
      {'op': 'open'},
      {'op': 'expand_level', 'key': 'businessObject'},
      {'op': 'snapshot', 'name': 'init', 'watch': ['MM', 'PM']},
      {'op': 'hide', 'code': 'PM'},
      {'op': 'render_stable'},
      {'op': 'snapshot', 'name': 'after_hide', 'watch': ['MM', 'PM']},
      {'op': 'unhide', 'code': 'PM'},
      {'op': 'render_stable'},
      {'op': 'snapshot', 'name': 'after_unhide', 'watch': ['MM', 'PM']},
      # 断言: 隐藏 PM 后 MM 的 BO 不应缺失/隐藏 (回归)
      {'op': 'diff', 'a': 'init', 'b': 'after_hide', 'watch': ['MM'],
       'expect_unchanged': True},
  ])
  runner.dump('test_helpers/out/my_scenario.json')
  runner.close()

[动作 op]
  open / expand_level(key) / expand_group(code, level) / hide(code) / unhide(code)
  collapse(code) / dblclick(code|selector) / wait(ms) / render_stable()
  snapshot(name, watch=[codes]) / screenshot(name) / diff(...)

[依赖]
  - ChartDiag (chart_diag.py): 打开图表 + wait_render_stable (data-chart-rendered 标记)
  - scenario.py: 场景/scope 构造
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from test_helpers.chart_diag import ChartDiag
from test_helpers.scenario import scope_dict_for_scenario, FRONTEND_URL, PRODUCT_CODE, VERSION_ID

OUT_DIR = Path(__file__).resolve().parent / 'out'

# 快照 JS: 枚举图表状态 (watch 编码 → 该分组子树下 BO 节点存在性与 display)
_SNAPSHOT_JS = """(watch) => {
  const out = { domains: [], hidden: [], boNodes: [], clusters: [], collapseAll: [],
                groupBo: {}, codeLen: 0, renderCount: 0, nodeCount: 0 };
  try {
    const svg = document.querySelector('.mermaid-content svg');
    if (svg) {
      out.collapseAll = Array.from(svg.querySelectorAll('[id*="COLLAPSE_"]'))
        .filter(g => !g.id.startsWith('L_')).map(g => g.id);
      svg.querySelectorAll('g.node[data-code]').forEach(g => {
        const code = g.getAttribute('data-code') || '';
        let cc = '';
        let p = g.parentElement;
        while (p && p !== svg) {
          const c = p.getAttribute && p.getAttribute('data-container-code');
          if (c) { cc = c; break; }
          p = p.parentElement;
        }
        out.boNodes.push({ code, disp: g.style.display || '', cc });
      });
      svg.querySelectorAll('g.cluster[data-container-code], .subgraph[data-container-code]').forEach(g => {
        out.clusters.push({ code: g.getAttribute('data-container-code'), id: g.id, disp: g.style.display || '' });
      });
      out.nodeCount = svg.querySelectorAll('g.node[data-code]').length;
    }
    const cfg = window.__archPage?.storeProxy?.layoutControlConfig;
    const flat = [];
    const collectBo = (g, target) => {
      if (!g) return;
      (g.directNodes || []).forEach(n => { const c = (typeof n === 'object' ? (n.code||n.name) : n); if (c) target.add(String(c)); });
      (g.children || []).forEach(ch => collectBo(ch, target));
      (g.containers || []).forEach(c => { if (c && typeof c === 'object') { (c.nodes||[]).forEach(n => { const cc = (typeof n === 'object' ? (n.code||n.name) : n); if (cc) target.add(String(cc)); }); (c.children||[]).forEach(ch2 => collectBo(ch2, target)); } });
    };
    const walk = (list) => { (list||[]).forEach(g => { if(!g) return; flat.push(g); walk(g.children); walk(g.containers); }); };
    walk(cfg?.groups);
    flat.forEach(g => {
      const c = g.elementCode || g.id || '';
      if ((g.groupType||'').toLowerCase() === 'domain') out.domains.push({ code: c, title: g.title, visible: g.visible, collapsed: g.collapsed });
      if (g.visible === false) out.hidden.push({ code: c, title: g.title, type: g.groupType });
    });
    // watch 分组子树下 BO 状态 (用分组树收集 BO 编码, 查 SVG 存在性与 display)
    (watch || []).forEach(w => {
      const target = flat.find(g => (g.elementCode||g.id) === w);
      const bos = new Set();
      if (target) collectBo(target, bos);
      out.groupBo[w] = { boCount: bos.size, boNodes: {} };
      bos.forEach(code => {
        const el = svg && svg.querySelector(`g.node[data-code="${code}"]`);
        out.groupBo[w].boNodes[code] = el ? (el.style.display || '') : 'missing';
      });
    });
    const code = window.__archPage?.mermaid?.lastRenderedCode || '';
    out.codeLen = code.length;
    out.renderCount = window.__archPage?.mermaid?.renderCount || 0;
  } catch (e) { out.error = String(e); }
  return out;
}"""


def snapshot_chart(page, watch: Optional[List[str]] = None) -> dict:
    """独立快照函数: 枚举当前图表状态 (供 runner 外部直接复用)."""
    return page.evaluate(_SNAPSHOT_JS, watch or [])


def diff_snapshots(before: dict, after: dict, watch: Optional[List[str]] = None) -> dict:
    """对比两次快照: 每个 watch 分组的 BO 缺失/隐藏 + 分组/容器变化摘要."""
    diff = {'watch': {}, 'boNodeCount': {}, 'codeChanged': before.get('codeLen') != after.get('codeLen')}
    for w in (watch or []):
        b = (before.get('groupBo') or {}).get(w, {})
        a = (after.get('groupBo') or {}).get(w, {})
        b_bo = b.get('boNodes', {}); a_bo = a.get('boNodes', {})
        missing = [c for c in b_bo if c not in a_bo]
        hidden = [c for c, d in a_bo.items() if d == 'none']
        restored = [c for c, d in a_bo.items() if b_bo.get(c) == 'none' and d != 'none']
        diff['watch'][w] = {
            'boCount_before': len(b_bo), 'boCount_after': len(a_bo),
            'missing': missing, 'hidden': hidden, 'restored': restored,
        }
    return diff


def assert_snapshot_diff(diff: dict, watch: List[str], expect_unchanged: bool = True) -> bool:
    """断言 diff: expect_unchanged=True 时 watch 分组 BO 不应缺失/隐藏. 返回是否通过."""
    ok = True
    for w in watch:
        d = diff.get('watch', {}).get(w, {})
        if expect_unchanged:
            if d.get('missing') or d.get('hidden'):
                ok = False
                print(f'[ASSERT-FAIL] 分组 {w}: 缺失 {len(d.get("missing", []))}, 隐藏 {len(d.get("hidden", []))}')
            else:
                print(f'[ASSERT-PASS] 分组 {w}: BO 保持可见 ({d.get("boCount_after")} 个)')
    return ok


class ScenarioRunner:
    """图表调试动作序列运行器."""

    def __init__(self, scenario: Optional[str] = None, scope: Optional[dict] = None,
                 product_code: str = PRODUCT_CODE, version_id: int = VERSION_ID,
                 base_url: str = FRONTEND_URL, headless: bool = True,
                 out_dir: str = str(OUT_DIR)):
        if not scope:
            if not scenario:
                raise ValueError('必须提供 scenario 或 scope 之一')
            scope = scope_dict_for_scenario(scenario)
        self.scope = scope
        self.diag = ChartDiag(base_url=base_url, product_code=product_code, version_id=version_id)
        self.page = self.diag.page
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots: Dict[str, dict] = {}
        self.diffs: List[dict] = []
        self.actions_log: List[dict] = []
        self.opened = False

    # ------------------------------------------------------------
    def _ev(self, expr: str):
        return self.page.evaluate(expr)

    def open(self):
        self.diag.open_chart(scope=self.scope)
        self.opened = True

    def wait_render_stable(self, clear_marker: bool = True, timeout_ms: int = 60000):
        try:
            return self.diag.wait_render_stable(timeout_ms=timeout_ms, clear_marker=clear_marker)
        except TimeoutError as e:
            print(f'  [WARN] render_stable 超时: {e}')

    def _selector_for_code(self, code: str) -> str:
        """定位分组在 SVG 中的元素 selector: 优先 data-container-code, 兜底 COLLAPSE id."""
        import re
        safe = re.sub(r'[^\w\u4e00-\u9fff]', '_', str(code))
        return (f'[data-container-code="{code}"], '
                f'[id*="COLLAPSE_D_{safe}"], [id*="COLLAPSE_SD_{safe}"], [id*="COLLAPSE_SM_{safe}"]')

    # ------------------------------------------------------------
    def act(self, a: dict):
        op = a.get('op')
        self.actions_log.append(a)
        if op == 'open':
            self.open()
        elif op == 'expand_level':
            self._ev(f"() => window.__archPage.debug.setExpandLevel({a['key']!r})")
            self.wait_render_stable(clear_marker=True)
        elif op == 'expand_group':
            self._ev(f"() => window.__archPage.debug.expandGroup({a['code']!r}, {a.get('level', 99)})")
            self.wait_render_stable(clear_marker=True)
        elif op in ('hide', 'unhide'):
            visible = 'false' if op == 'hide' else 'true'
            self._ev(f"() => window.__archPage.debug.setGroupVisible({a['code']!r}, {visible})")
        elif op == 'collapse':
            self._ev(f"() => window.__archPage.debug.collapseGroup({a['code']!r})")
            self.wait_render_stable(clear_marker=True)
        elif op == 'dblclick':
            sel = a.get('selector') or self._selector_for_code(a['code'])
            self._ev(f"() => window.__archPage.debug.testDblClick({sel!r})")
            self.wait_render_stable(clear_marker=True)
        elif op == 'snapshot':
            self.snapshots[a['name']] = snapshot_chart(self.page, a.get('watch'))
            print(f"  [snapshot] {a['name']}: BO节点={self.snapshots[a['name']].get('nodeCount')}, "
                  f"codeLen={self.snapshots[a['name']].get('codeLen')}")
        elif op == 'diff':
            d = diff_snapshots(self.snapshots[a['a']], self.snapshots[a['b']], a.get('watch'))
            self.diffs.append({'a': a['a'], 'b': a['b'], **d})
            if a.get('expect_unchanged'):
                assert_snapshot_diff(d, a.get('watch', []), expect_unchanged=True)
        elif op == 'wait':
            self.page.wait_for_timeout(a.get('ms', 1000))
        elif op == 'render_stable':
            self.wait_render_stable(clear_marker=a.get('clear_marker', True))
        elif op == 'screenshot':
            self.page.screenshot(path=str(self.out_dir / f"{a['name']}.png"), full_page=False)
        else:
            raise ValueError(f'未知动作 op: {op}')

    def run(self, actions: List[dict]) -> dict:
        for a in actions:
            try:
                self.act(a)
            except Exception as e:
                print(f'[ERROR] 动作 {a} 失败: {e}')
                raise
        return {'snapshots': self.snapshots, 'diffs': self.diffs, 'actions': self.actions_log}

    def dump(self, out_file: Optional[str] = None) -> str:
        out_file = out_file or str(self.out_dir / 'scenario_result.json')
        payload = {
            'scope': self.scope,
            'actions': self.actions_log,
            'snapshots': self.snapshots,
            'diffs': self.diffs,
        }
        Path(out_file).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
        print('saved ->', out_file)
        return out_file

    def close(self):
        self.diag.close()
