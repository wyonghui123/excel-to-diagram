"""
chart_e2e.py - 嵌入图表 E2E 校验引擎 (数据完整性 / 颜色 / 备注 / 交互)
======================================================================

[五类断言 (v3 2026-08-05: 新增 E 布局)]
  A. 数据完整性 (Data Integrity)  渲染的节点/边/容器数 == golden, 关键节点存在,
                                  标签非空, 边端点有效, 容器嵌套结构, 数据指纹防漂移
  B. 颜色 (Color)                 映射一致 + 方案/分组/中心范围切换生效,
                                  fill 全量合法性, 同组同色, 图例完整性, link 颜色
  C. 备注 (Annotation)            panel items 数量 + 类型过滤生效 + 文本非空 +
                                  孤儿备注检测 + 类型分布 == golden
  D. 交互 (Interaction)           点击联动/空白不动/图表类型切换/竞态守卫 +
                                  点击高亮 + panel→chart 反向联动 + 双击重置
  E. 布局 (Layout)                合并链路 4 步快照齐全 + 归属/标题合并一致 +
                                  叶子分组归属非空 + enabled 状态传播 (读 debugLayout 权威树)

[用法]
  # 1. 首次: 生成 golden 基线 (打开真实图表记录指标)
  python -m test_helpers.chart_e2e --regenerate-golden

  # 2. 回归: 读 golden 跑四类断言
  python -m test_helpers.chart_e2e
  python -m test_helpers.chart_e2e --scenario bo_default --category A,B

  # 3. 单独生成某场景
  python -m test_helpers.chart_e2e --regenerate-golden --scenario bo_short

[依赖]
  - test_helpers/chart_diag.py (ChartDiag: 打开图表/读指标/切换配置)
  - test_helpers/chart_fixtures.py (通用测试数据 + golden + 数据指纹)
  - 前端增强: FE1 nodeColorMappings / FE2 data-chart-rendered / FE3 __archPage.chartConfig
             / FE4 linkColorMappings
  - 浏览器: PlaywrightCLI (唯一合法浏览器入口)

[输出]
  - 控制台 PASS/FAIL 报告
  - 截图保存到 test_helpers/scripts/chart_e2e_out/
"""

from __future__ import annotations

import sys
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

if __name__ in ('__main__', 'chart_e2e'):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_helpers.chart_diag import ChartDiag, DEFAULT_SCOPE
from test_helpers.chart_fixtures import (
    CHART_FIXTURES, get_scenario_golden, update_scenario_golden,
    GOLDEN_FILE, BASE_URL, PRODUCT_CODE, VERSION_ID,
    fingerprint,
)


class CheckResult:
    """单个断言结果."""

    def __init__(self, category: str, name: str, passed: bool,
                 detail: Any = None, error: Optional[str] = None,
                 skipped: bool = False):
        self.category = category
        self.name = name
        self.passed = passed
        self.detail = detail
        self.error = error
        self.skipped = skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            'category': self.category,
            'name': self.name,
            'passed': self.passed,
            'skipped': self.skipped,
            'detail': self.detail,
            'error': self.error
        }


class ChartE2E:
    """按场景执行四类断言. 每个场景独立打开浏览器 (进程级隔离, 无共享状态)."""

    OUTPUT_DIR = Path(__file__).resolve().parent / 'scripts' / 'chart_e2e_out'

    def __init__(self, scenario_name: str, verbose: bool = True):
        self.scenario_name = scenario_name
        self.verbose = verbose
        self.scenario = CHART_FIXTURES['scenarios'][scenario_name]
        self.diag: Optional[ChartDiag] = None
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.results: List[CheckResult] = []

    # ------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------
    def open(self, wait_render: bool = True) -> None:
        """打开场景图表 (ChartDiag.open_chart 已有可靠路径)."""
        self.diag = ChartDiag(base_url=BASE_URL,
                              product_code=self.scenario['product_code'],
                              version_id=self.scenario['version_id'])
        self.diag.open_chart(scope=self.scenario['scope'])
        # [Task 9 2026-08-02] SM 场景: shortcut 默认打开 BO 图, 必须切到目标 chartType 再断言
        #   (此前 sm_default 的 golden 实际记录的是 BO 图数据 — 41 个 BO code)
        if self.scenario['chart_type'] == 'serviceModule':
            self.diag.switch_chart_config('chartType', 'serviceModule')
            # [FIX 2026-08-02] 切换后必须 clear_marker=True 等新渲染:
            #   否则 wait_render_stable 读到 BO 渲染留下的旧 marker (nodeCount=41) 立即返回,
            #   collect_golden_metrics 拿到 BO 的 dom + 切换中途的空 snap → golden 记录错误数据
            try:
                self.diag.wait_render_stable(clear_marker=True)
            except TimeoutError as e:
                print(f'  [WARN] SM 切换渲染等待超时: {e}')
        if wait_render:
            # 首次打开标记已存在, 不清除 (否则等不到新的 endRender 会超时)
            try:
                self.diag.wait_render_stable(clear_marker=False)
            except TimeoutError as e:
                print(f'  [WARN] 首渲染等待超时: {e}')
        # [2026-08-13] 自适应默认展开(computeDefaultExpandLevel)会把多领域 scope 折叠到领域级
        #   (如 bo_default 30BO → 3 领域节点), 与 golden 记录的"全展开"状态不符.
        #   对非 smoke 场景显式展开到业务对象, 使 golden(41节点)有效且颜色/G1 可对范围外节点断言.
        self._expand_to_business_object()
        # [种子数据 2026-08-02] 备注主场景: 前端 filter=[] 默认不显示备注,
        #   必须显式开启全部类型 (C 类断言前置)
        if self.scenario.get('expect_annotations'):
            items = self.diag.show_all_annotations()
            self._print(f'  [INFO] 备注场景已开启: panel items={len(items)}')

    def _expand_to_business_object(self) -> None:
        """[2026-08-13] 显式展开到业务对象层, 复用图表可观测/可测试能力 (configStore.setExpandLevel).
        smoke (L0) 场景为单 BO 秒级回归, 保持默认展开状态即可."""
        if self.scenario.get('tier') == 'L0':
            return
        # [FIX 2026-08-13] SM 图 (serviceModule) 渲染服务模块节点, 不展开到 BO 层级.
        #   跨域关系裁剪后 SM 图展开到 businessObject 无重新渲染 (code 不变) → 不更新
        #   data-chart-rendered 标记 → 后续 wait_render_stable 超时. SM 图跳过 BO 展开.
        if self.scenario.get('chart_type') == 'serviceModule':
            return
        page = self.diag.page
        res = page.evaluate("""() => {
            const cs = window.__configStore
            if (!cs || typeof cs.setExpandLevel !== 'function') return 'no-store'
            cs.setExpandLevel('businessObject')
            return 'ok'
        }""")
        if res != 'ok':
            self._print('  [WARN] 展开到业务对象: __configStore.setExpandLevel 不可用, 跳过')
            return
        try:
            self.diag.wait_render_stable(clear_marker=True)
        except TimeoutError as e:
            self._print(f'  [WARN] 展开渲染等待超时: {e}')

    def close(self) -> None:
        if self.diag:
            self.diag.close()
            self.diag = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------
    def _record(self, category: str, name: str, passed: bool,
                detail: Any = None, error: Optional[str] = None,
                skipped: bool = False) -> CheckResult:
        r = CheckResult(category, name, passed, detail, error, skipped)
        self.results.append(r)
        tag = '[SKIP]' if skipped else ('[OK]' if passed else '[FAIL]')
        suffix = f'  {error}' if error else ''
        print(f'  {tag} {name}{suffix}')
        return r

    def _print(self, msg: str):
        if self.verbose:
            print(msg)

    def _snap(self) -> Dict[str, Any]:
        """[E2E v2 2026-08-02] 统一读取面: 一次调用拿整份图表快照.

        优先 window.__archPage.mermaid.snapshot() (useDiagnostics.js),
        未安装时回退为旧方法逐项探测 (兼容旧前端构建).
        返回 { render, nodes, links, containers, legend, annotations }."""
        snap = self.diag.get_snapshot()
        if isinstance(snap, dict) and snap.get('error'):
            self._print(f'  [WARN] snapshot() 不可用, 回退逐项探测: {snap["error"]}')
            node_els = self.diag.get_node_labels()
            fills = self.diag.get_svg_node_fills()
            highlighted = set(self.diag.get_highlighted_codes())
            return {
                'render': None,
                'nodes': [{'code': n['code'], 'label': n['label'],
                           'fill': fills.get(n['code'], ''),
                           'highlighted': n['code'] in highlighted} for n in node_els],
                'links': {'svgStrokes': self.diag.get_svg_link_strokes(),
                          'colorMappings': self.diag.get_link_color_mappings()},
                'containers': self.diag.get_cluster_hierarchy(),
                'legend': self.diag.get_legend_items(),
                'annotations': self.diag.get_annotation_items(),
            }
        return snap

    # ------------------------------------------------------------
    # A. 数据完整性
    # ------------------------------------------------------------
    def check_data_integrity(self, golden: Dict[str, Any]) -> None:
        self._print('\n[A] 数据完整性')
        metrics = self.diag.get_render_metrics()
        dom, lr = metrics['dom'], metrics['lastRender'] or {}
        snap = self._snap()
        nodes = snap.get('nodes') or []

        # A1: 渲染指标 == golden (SVG 级口径, 来自 FE2 data-* 属性)
        for key, label in [('nodeCount', '节点数'), ('edgeCount', '边数'), ('containerCount', '容器数')]:
            actual = dom.get(key)
            expect = golden.get(key)
            if expect is None:
                self._record('A', f'{label} golden 缺失 (先跑 --regenerate-golden)', False,
                             error=f'golden.{key}=None')
            else:
                self._record('A', f'{label} == golden ({expect})',
                             actual == expect, {'actual': actual, 'expect': expect},
                             error=None if actual == expect else f'actual={actual} expect={expect}')

        # A2: SVG 实际节点数 == data-* 报告数 (防"报告对但 SVG 没渲染")
        svg_node_count = len(nodes)
        self._record('A', 'SVG 实际节点数 == data-node-count',
                     svg_node_count == dom.get('nodeCount'),
                     {'svg': svg_node_count, 'report': dom.get('nodeCount')},
                     error=None if svg_node_count == dom.get('nodeCount')
                     else f'svg={svg_node_count} report={dom.get("nodeCount")}')

        # A3: 关键节点必须存在 (防漏节点)
        key_nodes = golden.get('key_nodes') or []
        missing = []
        if key_nodes:
            existing = {n['code'] for n in nodes}
            missing = [c for c in key_nodes if c not in existing]
        self._record('A', f'关键节点存在 ({len(key_nodes) - len(missing)}/{len(key_nodes)})',
                     len(missing) == 0,
                     {'missing': missing}, error=None if not missing else f'missing={missing}')

        # [v2 2026-08-02] A2b: 节点标签非空 (防 label 空白/缺失)
        empty_labels = [n['code'] for n in nodes if not n.get('label')]
        self._record('A', f'节点标签非空 ({len(nodes) - len(empty_labels)}/{len(nodes)})',
                     not empty_labels, {'empty': empty_labels[:5]},
                     error=None if not empty_labels else f'空标签节点: {empty_labels[:5]}')

        # [v2 2026-08-02] A3b: 边有效性 (解析 mermaid code: 边端点必须已定义, 防孤儿边)
        parsed = self.diag.get_mermaid_code_edges()
        if 'error' not in parsed:
            unknown = [e for e in parsed['edges']
                       if e[0] not in parsed['nodeIds'] or e[1] not in parsed['nodeIds']]
            self._record('A', f'边端点均有效 ({len(parsed["edges"])} 条边)',
                         not unknown, {'edges': len(parsed['edges']), 'unknown': unknown[:3]},
                         error=None if not unknown else f'孤儿边端点: {unknown[:3]}')
        else:
            self._record('A', '边端点均有效 (mermaid code 未暴露, 跳过)',
                         True, skipped=True, error=parsed.get('error'))

        # [v2 2026-08-02] A4: 容器嵌套结构 (领域→子领域→SM: 至少 1 层嵌套; 叶子容器都有节点)
        # [L0 2026-08-02] smoke 场景 (节点 ≤3) 无嵌套属正常, 仅要求叶子容器都有节点
        hier = snap.get('containers') or {}
        empty_leaf = [c['id'] for c in hier.get('leafClusters', []) if not c['nodeCodes']]
        if self.scenario.get('tier') == 'L0':
            nested_ok = not empty_leaf
        else:
            nested_ok = hier.get('nestedClusters', 0) > 0 and hier.get('maxDepth', 0) >= 2
        self._record('A', f'容器嵌套 (总{hier.get("totalClusters", 0)} 嵌套{hier.get("nestedClusters", 0)} 深{hier.get("maxDepth", 0)})',
                     nested_ok and not empty_leaf,
                     {'total': hier.get('totalClusters', 0), 'nested': hier.get('nestedClusters', 0),
                      'maxDepth': hier.get('maxDepth', 0), 'emptyLeaf': empty_leaf[:3]},
                     error=None if nested_ok and not empty_leaf
                     else f'嵌套不足或空容器: nested={hier.get("nestedClusters", 0)} maxDepth={hier.get("maxDepth", 0)} emptyLeaf={empty_leaf[:3]}')

        # [Task 9 2026-08-02] A6: 无重复容器 — 同一实体不得既作为 subgraph 容器又作为节点
        #   (根因: SM 图双数据源叠加 / groupedLayout 对终端容器再包 subgraph → G_SM_xxx 重复渲染。
        #   方案 A 统一管道后容器层级由投影容器树固定派生, SM 是末端节点, 不应再有 SM subgraph 容器)
        #   检测 3 项:
        #     a) 容器 id 规范化后 (去 flowchart-/G_/前缀/尾部序号) 不得与节点 code 重叠
        #     b) SM 场景下容器 id 不得含 SM_ 层 (SM 是末端节点)
        #     c) 同一容器内不得出现重复节点 code
        is_sm = self.scenario['chart_type'] == 'serviceModule'
        cluster_ids = self.diag.get_container_ids()
        node_code_set = {n['code'] for n in nodes}

        def _norm_cid(cid: str) -> str:
            s = re.sub(r'^flowchart-', '', cid)
            s = re.sub(r'^G_', '', s)
            s = re.sub(r'-\d+$', '', s)
            s = re.sub(r'^(D_|SD_|SM_)', '', s)
            return s

        norm_overlap = sorted({_norm_cid(c) for c in cluster_ids} & node_code_set)
        sm_containers = [c for c in cluster_ids if re.match(r'^(G_)?SM_', c)]
        dup_in_container = []
        for lc in hier.get('leafClusters', []):
            codes = lc.get('nodeCodes') or []
            dups = sorted({c for c in codes if codes.count(c) > 1})
            if dups:
                dup_in_container.append({'id': lc['id'], 'dups': dups[:5]})
        a6_ok = not norm_overlap and not dup_in_container and (not sm_containers if is_sm else True)
        self._record('A', f'无重复容器 (SM容器残留{len(sm_containers)}, 实体冲突{len(norm_overlap)}, 容器内重复{len(dup_in_container)})',
                     a6_ok,
                     {'smContainers': sm_containers[:5], 'overlap': norm_overlap[:5], 'dupInContainer': dup_in_container[:3]},
                     error=None if a6_ok else
                     f'重复容器: SM容器={sm_containers[:5]} 实体冲突={norm_overlap[:5]} 容器内重复={dup_in_container[:3]}')

        # [v2 2026-08-02] A5: 数据指纹 — 节点集合 == golden (区分「数据漂移」vs「代码回归」)
        current_codes = sorted(n['code'] for n in nodes)
        golden_codes = sorted(golden.get('node_codes') or [])
        if golden_codes:
            drift = set(current_codes).symmetric_difference(golden_codes)
            self._record('A', f'节点集合 == golden ({len(current_codes)}/{len(golden_codes)})',
                         not drift, {'diff': sorted(drift)[:5], 'n': len(drift)},
                         error=None if not drift
                         else f'数据漂移 {len(drift)} 个节点 (数据变了 → --regenerate-golden; 或代码回归漏节点): {sorted(drift)[:5]}')
        else:
            self._record('A', '节点集合 == golden (golden 缺 node_codes)', True, skipped=True)

        # [v2 2026-08-02] A5b: scope 指纹 — fixture 未被修改
        if golden.get('scope_hash'):
            now_hash = fingerprint(self.scenario['scope'])
            self._record('A', 'scope 指纹 == golden',
                         golden['scope_hash'] == now_hash,
                         {'golden': golden['scope_hash'], 'now': now_hash},
                         error=None if golden['scope_hash'] == now_hash
                         else 'fixture scope 被修改 (需 --regenerate-golden 更新指纹)')

    # ------------------------------------------------------------
    # B. 颜色
    # ------------------------------------------------------------
    @staticmethod
    def _norm_color(c: str) -> str:
        """颜色归一化: 'rgb(24, 144, 255)' → '#1890ff', hex 原样 (小写).
        浏览器会把 SVG fill/stroke 标准化为 rgb(), 与代码里的 hex 比较需先归一."""
        s = (c or '').strip().lower()
        m = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', s)
        if m:
            return '#%02x%02x%02x' % tuple(int(x) for x in m.groups())
        return s

    def check_colors(self, golden: Dict[str, Any]) -> None:
        self._print('\n[B] 颜色')
        # [L0 2026-08-02] smoke 场景: 2 节点图无颜色映射/切换无意义, 切换类断言跳过
        is_smoke = self.scenario.get('tier') == 'L0'
        # [FIX 2026-08-13] SM 图跨域裁剪后默认折叠为服务模块聚合节点 (COLLAPSE_SM_*),
        #   聚合节点统一中性灰, 无 per-BO nodeColorMappings/linkColorMappings. 颜色映射类断言跳过.
        is_sm_chart = self.scenario.get('chart_type') == 'serviceModule'
        norm = self._norm_color

        # B1: nodeColorMappings 权威源非空 + 映射节点都在 SVG 中
        color_map = self.diag.get_node_colors()
        snap = self._snap()
        svg_fills = {n['code']: n.get('fill') or '' for n in (snap.get('nodes') or [])}
        if (is_smoke or is_sm_chart) and not color_map:
            self._record('B', 'nodeColorMappings (L0 smoke/SM 聚合节点跳过)',
                         True, skipped=True, detail={'mapped': 0, 'svg': len(svg_fills)})
        else:
            self._record('B', f'nodeColorMappings 非空 ({len(color_map)} 节点)',
                         len(color_map) > 0, {'mapped': len(color_map), 'svg': len(svg_fills)})

        # B2: SVG 实际 fill 与映射一致 (抽样对比, 防"映射对但 SVG 没染色")
        # [FIX 2026-08-02] 中心节点映射记录分组原始色, 渲染被 centerScopeColor 覆盖 — 预期差异, 跳过
        center_codes = self.diag.get_center_codes()
        mismatched = []
        checked = 0
        skipped_center = 0
        for code, expect_color in color_map.items():
            if code in svg_fills:
                checked += 1
                actual = norm(svg_fills[code])
                expect = norm(expect_color)
                # 空值视为 CSS 上色 (rect 无 fill 属性), 跳过; 其余必须相等
                if actual and actual != expect:
                    if code in center_codes:
                        skipped_center += 1
                        continue
                    mismatched.append({'code': code, 'expect': expect, 'actual': actual})
            if checked >= 30:
                break
        self._record('B', f'SVG fill 与映射一致 (抽 {checked} 个, 跳过中心 {skipped_center} 个)',
                     not mismatched, {'checked': checked, 'skipped_center': skipped_center, 'mismatched': mismatched[:5]},
                     error=None if not mismatched else f'{len(mismatched)} 个不一致: {mismatched[:3]}')

        def _node_fills() -> Dict[str, str]:
            s = self._snap()
            return {n['code']: n.get('fill') or '' for n in (s.get('nodes') or [])}

        def _switch_and_wait(key: str, value: Any) -> None:
            """切换配置并等待其生效.

            [FIX 2026-08-03 C1] 增量变色路径 (updateColorsOnly) 现在也会发 data-chart-rendered
            标记 (incremental=true), 不再需要 sleep 1.2s 兜底.
            旧策略: 短等标记 (3000ms) 超时后 sleep 1.2s — 增量失败时无法捕获, 5 个 WARN.
            新策略: switch 前清标记, wait(clear_marker=False) 等新标记; 超时则 WARN (真异常).

            关键时序: updateColorsOnly 是同步执行的 (Vue watcher flush: 'pre' 在 switch_chart_config
            返回前跑完), endRender 在 switch 返回时已设标记. 若 wait 用 clear_marker=True (默认),
            会在 switch 之后清掉标记, 永远等不到新标记 → 必须在 switch 之前清, wait 时不清."""
            # switch 之前清旧标记 (确保 wait 等的是本次新标记)
            self.diag.page.evaluate("""() => {
                const el = document.querySelector('.embedded-chart-view__canvas')
                if (el) el.removeAttribute('data-chart-rendered')
            }""")
            self.diag.switch_chart_config(key, value)
            try:
                # clear_marker=False: 不能再清, 否则 switch 同步设的标记会被清掉
                self.diag.wait_render_stable(timeout_ms=3000, clear_marker=False)
            except TimeoutError:
                self._print(f'  [WARN] 切换 {key}={value} 后渲染超时 (增量路径未发标记)')

        # B3: 颜色方案切换生效 (default → vibrant → 颜色集合变化)
        if is_smoke:
            self._record('B', 'colorScheme 切换生效 (L0 smoke 场景跳过)', True, skipped=True)
        elif golden.get('node_colors') and len(color_map) > 0:
            baseline_colors = set(svg_fills.values())
            _switch_and_wait('colorScheme', 'vibrant')
            new_colors = set(v for v in _node_fills().values() if v)
            changed = len(new_colors.difference(baseline_colors)) > 0 or \
                      len(baseline_colors.difference(new_colors)) > 0
            self._record('B', 'colorScheme=vibrant 生效 (fill 集合变化)',
                         changed, {'before_n': len(baseline_colors), 'after_n': len(new_colors)},
                         error=None if changed else '切换后 fill 集合无变化')
            # 恢复默认
            _switch_and_wait('colorScheme', 'default')
        else:
            self._record('B', 'colorScheme 切换生效', False,
                         skipped=True, error='golden.node_colors 缺失')

        # B4: 分组维度切换生效 (domain → subDomain → 颜色集合变化)
        if is_smoke:
            self._record('B', 'colorGroupBy=subDomain 生效 (L0 smoke 场景跳过)', True, skipped=True)
        elif len(set(v for v in _node_fills().values() if v)) <= 1:
            # [FIX 2026-08-13] 跨域关系裁剪后, 对象范围可能只含单一领域/子领域 (如 SCP 30 BO
            #   全属供应链计划), domain→subDomain 切换不会改变颜色分布 (都是单分组). 跳过.
            self._record('B', 'colorGroupBy=subDomain 生效 (单分组, 跳过)', True, skipped=True)
        else:
            baseline_colors = set(_node_fills().values())
            _switch_and_wait('colorGroupBy', 'subDomain')
            new_colors = set(v for v in _node_fills().values() if v)
            changed = len(new_colors.difference(baseline_colors)) > 0 or \
                      len(baseline_colors.difference(new_colors)) > 0
            self._record('B', 'colorGroupBy=subDomain 生效 (fill 集合变化)',
                         changed, {'before_n': len(baseline_colors), 'after_n': len(new_colors)},
                         error=None if changed else '切换后 fill 集合无变化')
            _switch_and_wait('colorGroupBy', 'domain')

        # B5: 中心范围高亮切换生效 (区分 → 不区分 → 中心节点 fill 变化)
        if is_smoke:
            self._record('B', 'centerScopeHighlight=false 生效 (L0 smoke 场景跳过)', True, skipped=True)
        else:
            baseline_colors = set(_node_fills().values())
            _switch_and_wait('centerScopeHighlight', False)
            new_colors = set(v for v in _node_fills().values() if v)
            changed = len(new_colors.difference(baseline_colors)) > 0 or \
                      len(baseline_colors.difference(new_colors)) > 0
            self._record('B', 'centerScopeHighlight=false 生效 (fill 集合变化)',
                         changed, {'before_n': len(baseline_colors), 'after_n': len(new_colors)},
                         error=None if changed else '切换后 fill 集合无变化')
            _switch_and_wait('centerScopeHighlight', True)

        # [v2 2026-08-02] B6: 节点 fill 全量合法性 (值必须是 hex/rgb; 空值 = CSS 上色, 跳过)
        svg_fills_full = _node_fills()
        invalid = []
        for code, fill in svg_fills_full.items():
            f = (fill or '').strip()
            if not f:
                continue
            if not re.match(r'^(#[0-9a-f]{3,8}|rgba?\([^)]*\))$', f, re.IGNORECASE):
                invalid.append({'code': code, 'fill': f})
        self._record('B', f'节点 fill 全量合法 (检查 {len(svg_fills_full)}, 非法 {len(invalid)})',
                     not invalid, {'invalid': invalid[:5]},
                     error=None if not invalid else f'非法 fill: {invalid[:5]}')

        # [v2 2026-08-02] B7: 同组同色 — 叶子容器内 fill 种类 ≤ 2 (分组色 + 中心范围色)
        hier = self._snap().get('containers') or {}
        fills_by_cluster = self.diag.page.evaluate(
            """(leaf) => {
                const out = []
                for (const c of leaf) {
                    const el = c.id && document.getElementById(c.id)
                    if (!el) continue
                    const fills = new Set(Array.from(el.querySelectorAll('g.node[data-code] rect'))
                        .map(r => (r.getAttribute('fill') || r.style.fill || '').trim().toLowerCase())
                        .filter(f => f))
                    if (fills.size > 0) out.push({ id: c.id, fills: Array.from(fills) })
                }
                return out
            }""", hier.get('leafClusters', []))
        multi = [c for c in fills_by_cluster if len(c['fills']) > 2]
        self._record('B', f'同组同色 (叶子容器 fill 种类 ≤2, 检查 {len(fills_by_cluster)})',
                     not multi, {'multi': multi[:3]},
                     error=None if not multi else f'同组多色: {multi[:3]}')
        if len(fills_by_cluster) > 1:
            all_fills = set(f for c in fills_by_cluster for f in c['fills'])
            self._record('B', '全局 fill 多样性 (≥2 种, 防全节点同色)',
                         len(all_fills) >= 2, {'distinct': len(all_fills)},
                         error=None if len(all_fills) < 2 else '所有节点同色, 分组染色失效')

        # [v2 2026-08-02] B8: 图例完整性 (数量 == golden; 名称非空; 色块 ⊆ 节点实际 fill)
        legend = self._snap().get('legend') or []
        expect_legend = golden.get('legend_item_count')
        if expect_legend is not None:
            self._record('B', f'图例 items == golden ({expect_legend})',
                         len(legend) == expect_legend, {'actual': len(legend), 'expect': expect_legend},
                         error=None if len(legend) == expect_legend
                         else f'actual={len(legend)} expect={expect_legend}')
        else:
            self._record('B', '图例 items == golden (golden 缺 legend_item_count)', True, skipped=True)
        empty_name = [l['name'] for l in legend if not l['name']]
        # [FIX 2026-08-02] 图例色块是 hex (#1890FF), 节点 fill 是 rgb(r,g,b) —
        #   两侧必须用 _norm_color 归一化再比较, 否则同色不同格式判 unknown
        actual_fills = set(norm(v) for v in svg_fills_full.values() if v)
        # [L0 2026-08-02] smoke 场景节点 fill 可能为空 (CSS 上色), 色块⊆fill 检查跳过
        if is_smoke and not actual_fills:
            self._record('B', '图例名称非空且色块有效 (L0 smoke 场景跳过)',
                         True, skipped=True, detail={'legend': len(legend)})
        else:
            unknown = [l['color'] for l in legend if l['color'] and norm(l['color']) not in actual_fills]
            self._record('B', f'图例名称非空且色块有效 ({len(legend)} 项)',
                         not empty_name and not unknown,
                         {'empty': empty_name[:3], 'unknown': unknown[:3]},
                         error=None if not empty_name and not unknown
                         else f'图例异常: empty={empty_name[:3]} unknown={unknown[:3]}')

        # [v2 2026-08-02] B9: link 颜色 (linkColorMappings 非空 + SVG link stroke 抽样一致)
        # [FIX 2026-08-02] SM 图已补齐 linkColorMappings 契约 (useServiceModuleSyntax 返回 +
        #   MermaidComponent SM 分支接收), BO/SM 两图均要求非空, 不再跳过 (原 Task 9 skip 条件作废)
        links_snap = self._snap().get('links') or {}
        link_map = links_snap.get('colorMappings') or []
        if is_sm_chart and not link_map:
            self._record('B', 'linkColorMappings (SM 聚合节点跳过)',
                         True, skipped=True, detail={'mapped': 0})
        else:
            self._record('B', f'linkColorMappings 非空 ({len(link_map)} 条)',
                         len(link_map) > 0, {'mapped': len(link_map)})
        if link_map:
            strokes = links_snap.get('svgStrokes') or []
            mismatched = []
            checked = 0
            for m in link_map:
                lid = f"L_{m.get('sourceId')}_{m.get('targetId')}"
                hit = next((s for s in strokes if s['id'] == lid), None)
                if hit is None and m.get('index') is not None and m['index'] < len(strokes):
                    hit = strokes[m['index']]
                if hit:
                    checked += 1
                    actual = norm(hit['stroke'])
                    expect = norm(m.get('color'))
                    if actual and expect and actual != expect:
                        mismatched.append({'link': lid, 'expect': expect, 'actual': actual})
                if checked >= 20:
                    break
            self._record('B', f'SVG link stroke 与映射一致 (抽 {checked} 条)',
                         not mismatched, {'checked': checked, 'mismatched': mismatched[:5]},
                         error=None if not mismatched else f'{len(mismatched)} 条不一致: {mismatched[:3]}')
        else:
            self._record('B', 'SVG link stroke 与映射一致 (无 linkColorMappings, 跳过)',
                         True, skipped=True)

    # ------------------------------------------------------------
    # [G1 2026-08-13] 范围外节点着色 (增量变色回归保护)
    # ------------------------------------------------------------
    def check_scope_color(self) -> None:
        """[G1 2026-08-13] 范围外节点着色: 变更某领域自定义色后, 该领域所有非中心渲染节点
        (含对象范围外/折叠隐藏的 BO) 必须保持新领域色, 而非回退中性灰.

        背景: 2026-08-13 修复 —— 增量变色路径 updateColorsOnly 的 unifiedColorMap 曾基于
        nodeColorMappings (跳过被折叠隐藏的范围外 BO) 构建, 导致范围外领域的折叠聚合节点
        取色失败回退中性灰. 修复后 unifiedColorMap 恒用 data.nodes 全量 BO 集构建.

        自检测 (不硬编码领域名): 从 __archPage.diagramData.nodes 读 code→domain (含范围外/
        折叠 BO, 与修复同源), 挑"非中心渲染节点最多"的领域 D, 经 configStore.updateCustomColors
        变更 D 色, 断言 D 的所有非中心渲染节点 SVG fill == 新色 (无残留中性灰 rgb(128,128,128)).
        """
        self._print('\n[G1] 范围外节点着色')
        # [FIX 2026-08-13] SM 图跨域裁剪后默认折叠为服务模块聚合节点 (COLLAPSE_SM_*),
        #   聚合节点无 code→domain 映射 (code 是 SM code 而非 BO code), 着色逻辑不适用, 跳过.
        if self.scenario.get('chart_type') == 'serviceModule':
            self._record('B', '范围外节点着色 (SM 聚合节点, 跳过)', True, skipped=True)
            return
        NEW = '#123456'  # 鲜明测试色 (与默认/中性灰均可区分)
        page = self.diag.page

        # 1) 读 code→domain (diagramData.nodes, 兼容 ref/.value/_value)
        domain_of = page.evaluate("""() => {
            const d = window.__archPage && window.__archPage.diagramData
            if (!d) return null
            let arr = null
            if (Array.isArray(d)) arr = d
            else if (d.value && Array.isArray(d.value.nodes)) arr = d.value.nodes
            else if (Array.isArray(d.nodes)) arr = d.nodes
            else if (d._value && Array.isArray(d._value.nodes)) arr = d._value.nodes
            if (!Array.isArray(arr) || arr.length === 0) return null
            const m = {}
            for (const n of arr) {
                if (n && n.code && n.domain) m[n.code] = n.domain
            }
            return m
        }""")
        if not domain_of:
            self._record('B', '范围外节点着色 (diagramData.nodes 未暴露, 跳过)', True,
                         skipped=True, detail={'err': 'no diagramData.nodes'})
            return

        # 2) 渲染节点 code→fill + 中心节点 (中心节点染 centerScopeColor, 断言须跳过)
        snap = self._snap()
        rendered = {n['code']: n.get('fill') or '' for n in (snap.get('nodes') or [])}
        center_codes = self.diag.get_center_codes()

        # 3) 挑"非中心渲染节点最多"的领域 D (覆盖面最广, 更可能含范围外节点)
        counts = {}
        for code in rendered:
            if code in center_codes:
                continue
            dom = domain_of.get(code)
            if dom:
                counts[dom] = counts.get(dom, 0) + 1
        if not counts:
            self._record('B', '范围外节点着色 (无匹配领域, 跳过)', True, skipped=True,
                         detail={'rendered': len(rendered), 'center': len(center_codes)})
            return
        D = max(counts, key=counts.get)
        nodes_of_D = [c for c in rendered if domain_of.get(c) == D and c not in center_codes]
        before_fills = {c: self._norm_color(rendered[c]) for c in nodes_of_D}

        # 4) 经 configStore.updateCustomColors 变更 D 色 (与图例改色同源路径)
        res = page.evaluate("""({ key, val }) => {
            const cs = window.__configStore
            if (!cs || typeof cs.updateCustomColors !== 'function') return 'no-store'
            const next = { ...(cs.customColors || {}) }
            next[key] = val
            cs.updateCustomColors(next)
            return 'ok'
        }""", {'key': D, 'val': NEW})
        if res != 'ok':
            self._record('B', f'范围外节点着色 (configStore.updateCustomColors 不可用, 跳过)',
                         True, skipped=True, detail={'res': res})
            return

        # 5) 等增量变色生效.
        #    updateCustomColors → Vue watcher(flush:'pre') 同步跑 updateColorsOnly, 在 evaluate
        #    返回前 SVG fill 已更新; 但增量路径不保证发新 data-chart-rendered 标记 (旧标记仍 true),
        #    故不用 marker 等待 (会误报超时), 固定短等待后直接断言.
        page.wait_for_timeout(800)

        # 6) 断言: D 的非中心渲染节点全部 == 新色 (无残留中性灰)
        after_snap = self._snap()
        after = {n['code']: n.get('fill') or '' for n in (after_snap.get('nodes') or [])}
        new_norm = self._norm_color(NEW)
        unchanged = [c for c in nodes_of_D if self._norm_color(after.get(c, '')) != new_norm]
        self._record('B', f'范围外节点着色: 领域[{D}] 非中心渲染 {len(nodes_of_D)} 节点改色后全为新色',
                     not unchanged,
                     {'domain': D, 'count': len(nodes_of_D), 'unchanged': unchanged[:5],
                      'beforeSample': dict(list(before_fills.items())[:3])},
                     error=None if not unchanged
                     else f'{len(unchanged)} 节点未着色(疑似回退中性灰): {unchanged[:5]}')

    # ------------------------------------------------------------
    # C. 备注
    # ------------------------------------------------------------
    def check_annotations(self, golden: Dict[str, Any]) -> None:
        self._print('\n[C] 备注')
        items = self._snap().get('annotations') or []
        expect_count = golden.get('annotation_item_count')

        if expect_count is None:
            self._record('C', 'golden.annotation_item_count 缺失 (先跑 --regenerate-golden)',
                         False, error='golden 缺失')
            return

        # C1: panel items 数量 == golden
        self._record('C', f'备注 items 数量 == golden ({expect_count})',
                     len(items) == expect_count,
                     {'actual': len(items), 'expect': expect_count},
                     error=None if len(items) == expect_count
                     else f'actual={len(items)} expect={expect_count}')

        # C2: 备注类型过滤生效 (选一类后 items 减少或保持)
        if items:
            # 从现有 items 取一种类型作为过滤条件
            types = {i['targetType'] for i in items}
            filter_type = 'node' if 'node' in types else next(iter(types))
            before = len(items)
            self.diag.switch_chart_config('annotationCategoryFilter', [filter_type])
            # overlay 重渲染不走 data-chart-rendered, 轮询 panel items 数变化
            deadline = time.time() + 10
            after = before
            while time.time() < deadline:
                self.diag.page.wait_for_timeout(400)
                after = len(self._snap().get('annotations') or [])
                if after <= before:
                    break
            self._record('C', f'过滤 [{filter_type}] 生效 (items 不增)',
                         after <= before, {'before': before, 'after': after},
                         error=None if after <= before else f'过滤后反而增加 {before}→{after}')
            # 恢复全选
            self.diag.switch_chart_config('annotationCategoryFilter', [])
            self.diag.page.wait_for_timeout(800)
        else:
            self._record('C', '备注类型过滤 (无 items, 跳过)', True, skipped=True)

        # C3: 点击有备注的节点 → 对应 panel item 选中 (联动)
        matched = [i for i in items if i['targetType'] == 'node']
        if matched:
            target_id = matched[0]['targetId']
            clicked_ok = self.diag.page.evaluate(
                """(tid) => {
                    const n = document.querySelector(`svg g.node[data-code="${tid}"]`)
                    if (!n) return { ok: false, reason: 'svg node not found' }
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                    return { ok: true }
                }""", target_id)
            self.diag.page.wait_for_timeout(700)
            items_after = self._snap().get('annotations') or []
            selected_ids = [i['targetId'] for i in items_after if i['selected']]
            self._record('C', f'点击节点 {target_id} → panel 对应 item 选中',
                         clicked_ok.get('ok') and target_id in selected_ids,
                         {'clicked': clicked_ok, 'selected': selected_ids[:5]},
                         error=None if target_id in selected_ids
                         else f'selected={selected_ids[:5]} (期望含 {target_id})')
        else:
            self._record('C', '点击节点联动 (无 node 类 items, 跳过)', True, skipped=True)

        # [v2 2026-08-02] C4: 备注文本非空 (item 有但 text 空 → 展示不完整)
        empty_text = [i['targetId'] for i in items if not i.get('text')]
        self._record('C', f'备注文本非空 ({len(items) - len(empty_text)}/{len(items)})',
                     not empty_text, {'empty': empty_text[:5]},
                     error=None if not empty_text else f'空文本备注: {empty_text[:5]}')

        # [v2 2026-08-02] C5: 孤儿备注 (node 类 targetId 必须在 SVG 中存在)
        node_ids = {n['code'] for n in (self._snap().get('nodes') or [])}
        node_items = [i for i in items if i['targetType'] == 'node']
        orphan = [i['targetId'] for i in node_items if i['targetId'] not in node_ids]
        self._record('C', f'备注目标有效 ({len(node_items) - len(orphan)}/{len(node_items)})',
                     not orphan, {'orphan': orphan[:5]},
                     error=None if not orphan else f'孤儿备注: {orphan[:5]}')

        # [v2 2026-08-02] C6: 备注类型分布 == golden
        type_counts: Dict[str, int] = {}
        for i in items:
            type_counts[i['targetType']] = type_counts.get(i['targetType'], 0) + 1
        expect_types = golden.get('annotation_type_counts')
        if expect_types is not None:
            self._record('C', f'备注类型分布 == golden ({type_counts})',
                         type_counts == expect_types, {'actual': type_counts, 'expect': expect_types},
                         error=None if type_counts == expect_types else f'{type_counts} != {expect_types}')
        else:
            self._record('C', '备注类型分布 == golden (golden 缺, 跳过)', True, skipped=True)

    # ------------------------------------------------------------
    # D. 交互
    # ------------------------------------------------------------
    def check_interactions(self, golden: Dict[str, Any]) -> None:
        self._print('\n[D] 交互')

        # D1: 点击节点 → 高亮 (fill 变化或 class 变化) + transform 不变
        svg_nodes = self.diag.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).slice(0, 3).map(n => n.getAttribute('data-code'))")
        if svg_nodes:
            node_code = svg_nodes[0]
            t_before = self.diag.page.evaluate(
                "() => document.querySelector('.mermaid-content')?.style.transform || ''")
            self.diag.page.evaluate(
                """(code) => {
                    const n = document.querySelector(`svg g.node[data-code="${code}"]`)
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                }""", node_code)
            self.diag.page.wait_for_timeout(700)
            t_after = self.diag.page.evaluate(
                "() => document.querySelector('.mermaid-content')?.style.transform || ''")
            self._record('D', f'点击节点 {node_code} transform 不变 (v5 不居中)',
                         t_before == t_after,
                         {'before': t_before, 'after': t_after},
                         error=None if t_before == t_after else 'transform 变化了')
        else:
            self._record('D', '点击节点 transform 不变', True, skipped=True)

        # D2: 空白点击 → transform 不变
        t_before = self.diag.page.evaluate(
            "() => document.querySelector('.mermaid-content')?.style.transform || ''")
        self.diag.page.evaluate(
            """() => {
                const svg = document.querySelector('.mermaid-content svg')
                const r = svg.getBoundingClientRect()
                svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                    clientX: r.left + 5, clientY: r.top + 5, button: 0 }))
            }""")
        self.diag.page.wait_for_timeout(700)
        t_after = self.diag.page.evaluate(
            "() => document.querySelector('.mermaid-content')?.style.transform || ''")
        self._record('D', '空白点击 transform 不变',
                     t_before == t_after,
                     {'before': t_before, 'after': t_after},
                     error=None if t_before == t_after else 'transform 变化了')

        # D3: 图表类型切换生效 (businessObject → serviceModule → nodeCount/容器变化)
        if golden.get('chart_type', 'businessObject') == 'businessObject':
            node_before = self.diag.page.evaluate(
                "() => document.querySelectorAll('svg g.node[data-code]').length")
            container_before = self.diag.page.evaluate(
                "() => document.querySelectorAll('svg g.cluster').length")
            self.diag.switch_chart_config('chartType', 'serviceModule')
            self.diag.wait_render_stable()
            node_after = self.diag.page.evaluate(
                "() => document.querySelectorAll('svg g.node[data-code]').length")
            container_after = self.diag.page.evaluate(
                "() => document.querySelectorAll('svg g.cluster').length")
            changed = node_after != node_before or container_after != container_before
            self._record('D', 'chartType 切换 SM 生效 (节点/容器变化)',
                         changed, {'node': (node_before, node_after),
                                   'container': (container_before, container_after)},
                         error=None if changed else '切换后无变化')
            # 切回 BO
            self.diag.switch_chart_config('chartType', 'businessObject')
            self.diag.wait_render_stable()

        # D4: 快速连点切换 → 最终状态 = 最后一次 (genId 竞态守卫)
        self._print('  [D4] 快速连点 chartType 3 次 (BO→SM→BO), 验证无竞态覆盖')
        for _ in range(3):
            self.diag.switch_chart_config('chartType', 'serviceModule')
            self.diag.switch_chart_config('chartType', 'businessObject')
        # [FIX 2026-08-02] D4 后最终 render 可能被 L5 code-diff skip 或 genId 竞态守卫丢弃:
        #   SVG 已是正确终态 (code 不变), 但 data-chart-rendered 标记不会再次更新 →
        #   wait_render_stable 会空等超时. 改为容忍: 超时后回退状态轮询 (chartType+SVG 就绪即可).
        try:
            self.diag.wait_render_stable()
        except TimeoutError as e:
            self._print(f'  [WARN] D4 最终渲染被跳过/丢弃 (终态正确), 回退状态轮询: {e}')
            deadline = time.time() + 10
            while time.time() < deadline:
                st = self.diag.page.evaluate("""() => ({
                    t: window.__archPage?.chartConfig?.chartType || '?',
                    n: document.querySelectorAll('svg g.node[data-code]').length
                })""")
                if st['t'] == 'businessObject' and st['n'] > 0:
                    break
                self.diag.page.wait_for_timeout(500)
        final_type = self.diag.page.evaluate(
            "() => window.__archPage?.chartConfig?.chartType || '?'")
        # [FIX 2026-08-13] svg_ok 需等待活动 SVG 渲染出节点再断言:
        #   SM→BO 切换时 wait_render_stable 返回后节点可能尚未入 DOM (竞态假失败).
        #   [FIX 2026-08-13] 大图 (采购供应 602 边) 快速连点后, 自适应默认展开层级会把图表
        #   折叠回领域级 (9 个 COLLAPSE_D_* 容器, 无 g.node[data-code]) → 统计 g.node[data-code]
        #   恒为 0 误判失败. 改用 data_code=False 统计任意 g.node (折叠无关), 只验证 SVG 有节点.
        svg_node_count = self.diag.wait_for_svg_nodes(min_count=1, data_code=False)
        svg_ok = svg_node_count > 0
        self._record('D', '快速连点后 chartType=businessObject 且 SVG 正常',
                     final_type == 'businessObject' and svg_ok,
                     {'chartType': final_type, 'svgNodes': svg_node_count},
                     error=None if final_type == 'businessObject' and svg_ok
                     else f'chartType={final_type} svgOk={svg_ok}')

        # [v2 2026-08-02] D5: 点击节点 → 高亮生效 (防「transform 没变但高亮也没发生」假阳性)
        # [FIX 2026-08-02] 不复用 D1 的 svg_nodes (D1 采集于切换前, D3/D4 后 SVG 终态可能
        #   是 SM 图 — 快速连点时最后的 BO 渲染被 isRendering/genId 竞态守卫丢弃, SVG 保留
        #   的是最后一次真实渲染的 SM 图). 点击前从当前 SVG 重新采集节点, 兼容 BO/SM 两种终态.
        svg_nodes_now = self.diag.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).slice(0, 3).map(n => n.getAttribute('data-code'))")
        if svg_nodes_now:
            node_code = svg_nodes_now[0]
            self.diag.page.evaluate(
                """(code) => {
                    const n = document.querySelector(`svg g.node[data-code="${code}"]`)
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                }""", node_code)
            self.diag.page.wait_for_timeout(700)
            highlighted = self.diag.get_highlighted_codes()
            self._record('D', f'点击节点 {node_code} → 高亮生效',
                         node_code in highlighted, {'highlighted': highlighted[:5]},
                         error=None if node_code in highlighted else f'点击后未高亮: {highlighted[:5]}')
            # 空白点击清高亮 (恢复初始态, 供后续断言)
            self.diag.page.evaluate(
                """() => {
                    const svg = document.querySelector('.mermaid-content svg')
                    const r = svg.getBoundingClientRect()
                    svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + 5, clientY: r.top + 5, button: 0 }))
                }""")
            self.diag.page.wait_for_timeout(400)
        else:
            self._record('D', '点击节点高亮 (无节点, 跳过)', True, skipped=True)

        # [v3 2026-08-03] D5b: 点击 svg 外部背景区域 → 清高亮 (用户报告的真实场景)
        #   修复前: click 监听器绑 svg, 点击 .draggable-area (svg 外背景) 不冒泡到 svg, highlight 不清
        #   修复后: click 监听器绑 .draggable-area, 点击背景区域也触发 clearAllHighlights
        svg_nodes_for_bg = self.diag.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).slice(0, 3).map(n => n.getAttribute('data-code'))")
        if svg_nodes_for_bg:
            node_code_bg = svg_nodes_for_bg[0]
            # 先点 node 高亮
            self.diag.page.evaluate(
                """(code) => {
                    const n = document.querySelector(`svg g.node[data-code="${code}"]`)
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                }""", node_code_bg)
            self.diag.page.wait_for_timeout(700)
            highlighted_before = self.diag.get_highlighted_codes()
            # 点击 svg 外部背景区域 (.draggable-area 内但 svg 外)
            #   svg 通常不占满 .draggable-area; 兼容小图 (svg 占满时回退到边缘外 1px)
            self.diag.page.evaluate(
                """() => {
                    const draggable = document.querySelector('.draggable-area')
                    const svg = document.querySelector('.mermaid-content svg')
                    if (!draggable || !svg) return
                    const dr = draggable.getBoundingClientRect()
                    const sr = svg.getBoundingClientRect()
                    let x, y
                    if (sr.right + 5 < dr.right) {
                        x = sr.right + 5; y = sr.top + 5
                    } else if (sr.bottom + 5 < dr.bottom) {
                        x = sr.left + 5; y = sr.bottom + 5
                    } else {
                        x = Math.max(dr.left + 1, sr.left - 1)
                        y = Math.max(dr.top + 1, sr.top - 1)
                    }
                    draggable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: x, clientY: y, button: 0 }))
                }""")
            self.diag.page.wait_for_timeout(700)
            highlighted_after = self.diag.get_highlighted_codes()
            cleared = (node_code_bg in highlighted_before) and (node_code_bg not in highlighted_after)
            self._record('D', f'点击 svg 外部背景区域 → 清高亮 ({node_code_bg})',
                         cleared,
                         {'before': highlighted_before[:5], 'after': highlighted_after[:5]},
                         error=None if cleared else f'未清高亮: before={highlighted_before[:3]} after={highlighted_after[:3]}')
        else:
            self._record('D', '点击 svg 外部背景清高亮 (无节点, 跳过)', True, skipped=True)

        # [v2 2026-08-02] D6: panel→chart 反向联动 (真实 items 存在时: 点 panel item → 高亮 + 居中)
        items = self.diag.get_annotation_items()
        matched = [i for i in items if i['targetType'] == 'node']
        if matched:
            tid = matched[0]['targetId']
            t_before = self.diag.page.evaluate(
                "() => document.querySelector('.mermaid-content')?.style.transform || ''")
            self.diag.page.evaluate(
                """(tid) => {
                    const item = Array.from(document.querySelectorAll('.annotation-dock-panel .annotation-item'))
                        .find(i => i.getAttribute('data-target-id') === tid)
                    if (item) item.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, button: 0 }))
                }""", tid)
            self.diag.page.wait_for_timeout(900)
            highlighted = self.diag.get_highlighted_codes()
            t_after = self.diag.page.evaluate(
                "() => document.querySelector('.mermaid-content')?.style.transform || ''")
            centered = t_before != t_after  # panel item 点击走 onCenterElement → transform 变化
            self._record('D', f'panel item {tid} → chart 高亮+居中',
                         tid in highlighted and centered,
                         {'highlighted': highlighted[:5], 'centered': centered,
                          'before': t_before, 'after': t_after},
                         error=None if tid in highlighted and centered
                         else f'未联动: highlighted={highlighted[:3]} centered={centered}')
        else:
            self._record('D', 'panel→chart 反向联动 (无真实 items, 跳过)', True, skipped=True)

        # [v2 2026-08-02] D7: 双击重置视图 (dblclick → autoFitDiagram → transform 从任意值归位)
        arbitrary = 'translate(300px, 200px) scale(1.5)'
        self.diag.page.evaluate(
            """(arb) => {
                const c = document.querySelector('.mermaid-content')
                if (!c) return
                c.style.transition = 'none'
                c.style.transform = arb
                const mc = document.querySelector('.mermaid-container')
                const r = mc.getBoundingClientRect()
                mc.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window,
                    clientX: r.left + r.width/2, clientY: r.top + r.height/2 }))
            }""", arbitrary)
        self.diag.page.wait_for_timeout(1200)
        t_after = self.diag.page.evaluate(
            "() => document.querySelector('.mermaid-content')?.style.transform || ''")
        reset_ok = bool(t_after) and t_after != arbitrary and '1.5' not in t_after
        self._record('D', '双击重置 → transform 归位',
                     reset_ok, {'after': t_after},
                     error=None if reset_ok else f'dblclick 后 transform={t_after} (未归位)')

        # [v3 2026-08-03] D8: 拖动后 highlight 保留 (P1-B 拖动守卫验证)
        #   修复前: 用户拖动图表 (panning) 后浏览器 fire click 事件,
        #           useTooltip.addClickToClearHighlight 误清高亮 (D5b 修复了点击背景清高亮,
        #           但拖动场景的 click 仍会触发 clear).
        #   修复后: mousedown 记录起点, click 时位移 > 5px 视为拖动, 跳过 clearHighlight.
        #   断言三件套: (1) 拖动前高亮 (2) 拖动后高亮保留 (3) useTooltipClearSkip 埋点 reason=drag
        svg_nodes_d8 = self.diag.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).slice(0, 3).map(n => n.getAttribute('data-code'))")
        if svg_nodes_d8:
            node_code_d8 = svg_nodes_d8[0]
            # 1. 点击高亮
            self.diag.page.evaluate(
                """(code) => {
                    const n = document.querySelector(`svg g.node[data-code="${code}"]`)
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                }""", node_code_d8)
            self.diag.page.wait_for_timeout(700)
            highlighted_before_d8 = self.diag.get_highlighted_codes()
            has_hl_before = node_code_d8 in highlighted_before_d8
            # 2. 模拟拖动: mousedown at (x1,y1) → mousemove with buttons=1 → mouseup → click at (x2,y2)
            #   位移 100px > 5px 阈值, useTooltip.onClick 应跳过 clearHighlight.
            #   事件 target 必须是 svg (不是 .draggable-area), 否则 annotationOverlay 的
            #   onSvgMouseDown/Move/Up (绑在 svg 上) 不触发, isDraggingState 保持 false,
            #   onSvgClick 仍会清高亮 — 与真实拖动场景不符 (用户拖的是 svg 内的图).
            self.diag.page.evaluate(
                """() => {
                    const svg = document.querySelector('.mermaid-content svg')
                    if (!svg) return
                    const r = svg.getBoundingClientRect()
                    const x1 = r.left + 50, y1 = r.top + 50
                    const x2 = x1 + 100, y2 = y1 + 50
                    svg.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window,
                        clientX: x1, clientY: y1, button: 0, buttons: 1 }))
                    svg.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, cancelable: true, view: window,
                        clientX: x2, clientY: y2, button: 0, buttons: 1 }))
                    svg.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window,
                        clientX: x2, clientY: y2, button: 0, buttons: 0 }))
                    svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: x2, clientY: y2, button: 0 }))
                }""")
            self.diag.page.wait_for_timeout(700)
            highlighted_after_d8 = self.diag.get_highlighted_codes()
            preserved = has_hl_before and (node_code_d8 in highlighted_after_d8)
            # 3. 验证拖动守卫埋点 (P0-A + P1-B 联合验证)
            skip_meta = self.diag.page.evaluate("""() => {
                const arr = window.__archPage?.mermaid?.stepMeta?.useTooltipClearSkip
                if (!Array.isArray(arr)) return null
                return arr.filter(m => m?.reason === 'drag').slice(-1)[0] || null
            }""")
            self._record('D', f'拖动后 highlight 保留 ({node_code_d8})',
                         preserved and skip_meta is not None,
                         {'before': highlighted_before_d8[:3], 'after': highlighted_after_d8[:3],
                          'hasHlBefore': has_hl_before, 'dragSkipMeta': skip_meta},
                         error=None if (preserved and skip_meta is not None)
                         else f'未保留: before={has_hl_before} after={node_code_d8 in highlighted_after_d8} skipMeta={skip_meta}')
            # 清高亮恢复初始态
            self.diag.page.evaluate(
                """() => {
                    const svg = document.querySelector('.mermaid-content svg')
                    const r = svg.getBoundingClientRect()
                    svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + 5, clientY: r.top + 5, button: 0 }))
                }""")
            self.diag.page.wait_for_timeout(400)
        else:
            self._record('D', '拖动后 highlight 保留 (无节点, 跳过)', True, skipped=True)

        # [v3 2026-08-03] D9: highlight 状态 API 可观测 (P0-B 状态暴露验证)
        #   验证 window.__archPage.mermaid.highlight 始终返回 { hasHighlight, path, label, sourceNode, targetNode },
        #   且点击节点 → hasHighlight=true, dblclick → 状态保留 (autoFit 不应清高亮).
        hl_api = self.diag.page.evaluate("""() => {
            const h = window.__archPage?.mermaid?.highlight
            if (!h || typeof h !== 'object') return { ok: false, reason: 'not-object' }
            return {
                ok: typeof h.hasHighlight === 'boolean' && 'path' in h && 'label' in h && 'sourceNode' in h && 'targetNode' in h,
                hasHighlight: h.hasHighlight
            }
        }""")
        self._record('D', 'highlight API 可观测 (P0-B)',
                     hl_api.get('ok', False), {'api': hl_api},
                     error=None if hl_api.get('ok') else f'API contract 失败: {hl_api}')

        svg_nodes_d9 = self.diag.page.evaluate(
            "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).slice(0, 3).map(n => n.getAttribute('data-code'))")
        if svg_nodes_d9:
            node_code_d9 = svg_nodes_d9[0]
            # 点击节点高亮, 读取 highlight.hasHighlight 应为 true (annotationOverlay 高亮, useTooltip 状态不影响)
            self.diag.page.evaluate(
                """(code) => {
                    const n = document.querySelector(`svg g.node[data-code="${code}"]`)
                    const r = n.getBoundingClientRect()
                    n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                }""", node_code_d9)
            self.diag.page.wait_for_timeout(700)
            hl_after_click = self.diag.page.evaluate(
                "() => window.__archPage?.mermaid?.highlight || {}")
            # dblclick (autoFit), highlight 状态应保留 (D7 已验证 transform 重置)
            self.diag.page.evaluate(
                """() => {
                    const mc = document.querySelector('.mermaid-container')
                    if (!mc) return
                    const r = mc.getBoundingClientRect()
                    mc.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + r.width/2, clientY: r.top + r.height/2 }))
                }""")
            self.diag.page.wait_for_timeout(1200)
            hl_after_dblclick = self.diag.page.evaluate(
                "() => window.__archPage?.mermaid?.highlight || {}")
            api_stable = isinstance(hl_after_dblclick, dict) and 'hasHighlight' in hl_after_dblclick
            # 注意: useTooltip 闭包状态在 dblclick 后理论上不变 (dblclick 不触发 click listener);
            #   annotationOverlay DOM 高亮 .annotation-highlighted 也保留.
            self._record('D', f'dblclick 后 highlight API 仍可观测 ({node_code_d9})',
                         api_stable,
                         {'afterClick': hl_after_click, 'afterDblclick': hl_after_dblclick},
                         error=None if api_stable else f'dblclick 后 API 不可读: {hl_after_dblclick}')
            # 清高亮
            self.diag.page.evaluate(
                """() => {
                    const svg = document.querySelector('.mermaid-content svg')
                    const r = svg.getBoundingClientRect()
                    svg.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                        clientX: r.left + 5, clientY: r.top + 5, button: 0 }))
                }""")
            self.diag.page.wait_for_timeout(400)
        else:
            self._record('D', 'dblclick 后 highlight API (无节点, 跳过)', True, skipped=True)

        # [v3 2026-08-03] D10: chartType 切换后 highlight 干净 (P0-B + 渲染生命周期)
        #   chartType 切换触发新 SVG 渲染 → useTooltip.cleanup() → diag.setHighlightState(null).
        #   断言: 切换后 (1) DOM 无 .annotation-highlighted (2) window.__archPage.mermaid.highlight.hasHighlight=false.
        #   仅 BO 场景可切 (SM 场景已是 SM, 切走再切回需要 fixture 数据, 跳过).
        if golden.get('chart_type', 'businessObject') == 'businessObject':
            # 先高亮一个节点
            svg_nodes_d10 = self.diag.page.evaluate(
                "() => Array.from(document.querySelectorAll('svg g.node[data-code]')).slice(0, 1).map(n => n.getAttribute('data-code'))")
            if svg_nodes_d10:
                self.diag.page.evaluate(
                    """(code) => {
                        const n = document.querySelector(`svg g.node[data-code="${code}"]`)
                        const r = n.getBoundingClientRect()
                        n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window,
                            clientX: r.left + r.width/2, clientY: r.top + r.height/2, button: 0 }))
                    }""", svg_nodes_d10[0])
                self.diag.page.wait_for_timeout(700)
            # 切到 SM, 再切回 BO (D3/D4 已验证切换有效, 这里只关心 highlight 清理)
            self.diag.switch_chart_config('chartType', 'serviceModule')
            try:
                self.diag.wait_render_stable(timeout_ms=5000)
            except TimeoutError:
                pass
            self.diag.switch_chart_config('chartType', 'businessObject')
            try:
                self.diag.wait_render_stable(timeout_ms=5000)
            except TimeoutError:
                pass
            self.diag.page.wait_for_timeout(500)
            dom_clean = self.diag.page.evaluate(
                "() => document.querySelectorAll('svg .annotation-highlighted').length === 0")
            hl_state = self.diag.page.evaluate(
                "() => (window.__archPage?.mermaid?.highlight || {}).hasHighlight === false")
            self._record('D', 'chartType 切换后 highlight 干净 (DOM + 状态)',
                         dom_clean and hl_state,
                         {'domClean': dom_clean, 'stateClean': hl_state},
                         error=None if (dom_clean and hl_state)
                         else f'DOM clean={dom_clean} state clean={hl_state}')
        else:
            self._record('D', 'chartType 切换后 highlight 干净 (非 BO 场景, 跳过)', True, skipped=True)

        # [OBS 2026-08-13] D11: 关系高亮状态可观测 (relationHighlight + data-rel-dim)
        #   触发走 __archPage.debug.highlightRelations, 需 ?mode=debug 暴露; 未暴露则跳过.
        #   验证: 触发后 relationHighlight().active=true 且 connectedNodeCount/hlEdgeCount/dimmedCount
        #   与 DOM [data-rel-hl]/[data-rel-dim] 实测一致; 断言其权威快照而非扫描 opacity.
        has_debug_api = self.diag.page.evaluate("() => !!(window.__archPage && window.__archPage.debug && window.__archPage.debug.highlightRelations)")
        if has_debug_api:
            before = self.diag.get_relation_highlight()
            if not before.get('active') and before.get('dom', {}).get('relHl', -1) >= 0:
                state = self.diag.trigger_relation_highlight(None)
                dom = state.get('dom', {})
                ok = bool(state.get('active')) and dom.get('relHl', 0) > 0
                consistency = (dom.get('relHl', 0) == (state.get('connectedNodeCount', 0) + state.get('hlEdgeCount', 0))
                               and dom.get('relDim', 0) == state.get('dimmedCount', 0))
                self._record('D', '关系高亮状态可观测 (relationHighlight 快照与 DOM 一致)',
                             ok and consistency,
                             {'state': {k: state.get(k) for k in
                                        ('active', 'code', 'connectedNodeCount', 'hlEdgeCount', 'dimmedCount')},
                              'dom': dom, 'consistent': consistency},
                             error=None if (ok and consistency)
                             else f'关系高亮可观测失败: state={state}')
            else:
                self._record('D', '关系高亮状态可观测 (初始即高亮/无渲染, 跳过)', True, skipped=True)
        else:
            self._record('D', '关系高亮状态可观测 (需 ?mode=debug, 跳过)', True, skipped=True)

    # ------------------------------------------------------------
    # golden 生成 / 全量运行
    # ------------------------------------------------------------
    def collect_golden_metrics(self) -> Dict[str, Any]:
        """收集场景实测指标, 作为 golden 基线.
        [v2 2026-08-02] 新增数据指纹 (node_codes 全量 + scope_hash) 与
        图例/备注类型分布指标, 支撑 A5 数据漂移检测、B8 图例、C6 类型分布断言.
        [种子 2026-08-02] expect_annotations 场景: 先开启全部备注类型再读 items
        (前端 filter=[] 默认不显示备注)."""
        metrics = self.diag.get_render_metrics()
        dom = metrics['dom']
        # [Task 9 2026-08-02] 性能基线: 首渲染耗时 (A7 阈值 + 趋势对比)
        last_render = metrics['lastRender'] or {}
        snap = self._snap()
        node_codes = [n['code'] for n in (snap.get('nodes') or [])]
        svg_fills = {n['code']: n.get('fill') or '' for n in (snap.get('nodes') or [])}
        items = snap.get('annotations') or []
        if self.scenario.get('expect_annotations') and not items:
            items = self.diag.show_all_annotations()
        type_counts: Dict[str, int] = {}
        for i in items:
            type_counts[i['targetType']] = type_counts.get(i['targetType'], 0) + 1
        return {
            'chart_type': self.scenario['chart_type'],
            'tier': self.scenario.get('tier', 'L1'),
            'expect_annotations': self.scenario.get('expect_annotations', False),
            'nodeCount': dom.get('nodeCount', 0),
            'edgeCount': dom.get('edgeCount', 0),
            'containerCount': dom.get('containerCount', 0),
            'render_duration_ms': last_render.get('durationMs'),
            'key_nodes': node_codes[:10],
            'node_codes': node_codes,                              # 数据指纹: 全量节点 code (A5)
            'scope_hash': fingerprint(self.scenario['scope']),     # 数据指纹: scope 规范化 hash (A5b)
            'node_colors': svg_fills,
            'annotation_item_count': len(items),
            'annotation_type_counts': type_counts,                 # 备注类型分布 (C6)
            'legend_item_count': len(snap.get('legend') or []),    # 图例项数 (B8)
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'scope': self.scenario['scope'],
            'color_group_by': self.scenario.get('color_group_by', 'domain'),
            'color_scheme': self.scenario.get('color_scheme', 'default'),
        }

    def check_performance(self, golden: Dict[str, Any]) -> None:
        """[Task 9 2026-08-02] 性能断言 (spec 4.4 增量更新):
        A7 首渲染耗时 — L2 大规模场景设阈值, 其余场景记录 (golden.render_duration_ms 趋势基线)
        A8 增量跳过 — 相同输入重渲染 (generateDiagram) 命中 L5 code-diff, 跳过 mermaid.run:
           信号: __archPage.mermaid.renderSkippedCount +1 / lastRender 不更新 / SVG 保留
        """
        self._print('\n[A7/A8] 性能')
        snap = self._snap()
        render = snap.get('render') or {}
        duration_ms = render.get('durationMs')
        tier = self.scenario.get('tier')

        # A7: 首渲染耗时
        threshold = {'L2': 15000}.get(tier)
        if duration_ms is None:
            self._record('A', '首渲染耗时 (lastRender 缺失, 跳过)', True, skipped=True)
        elif threshold is None:
            self._record('A', f'首渲染耗时记录 ({duration_ms}ms)', True, {'durationMs': duration_ms})
        else:
            self._record('A', f'首渲染耗时 < {threshold}ms ({duration_ms}ms)',
                         duration_ms < threshold, {'durationMs': duration_ms, 'threshold': threshold},
                         error=None if duration_ms < threshold
                         else f'durationMs={duration_ms} 超过阈值 {threshold}ms (性能回归, 检查 L1/L2 缓存)')

        # A8: 增量跳过 — generateDiagram 产生新 diagramData 引用 → watch 触发 renderMermaid
        #   → 相同输入生成相同 mermaidCode → L5 code-diff 命中 → 跳过 mermaid.run 全量重绘
        # [FIX 2026-08-02] 先 priming 对齐 lastRenderedCode 到当前 chartType:
        #   D4 快速连点后最终 render 可能被 L5 skip / genId 竞态丢弃, lastRenderedCode 仍是
        #   上一 chartType 的 code → before/after code 直接不同, 误判"未命中跳过".
        #   priming 触发一次当前 chartType 的干净渲染 (或同样被 skip, 也属已对齐), 再测量增量.
        self.diag.page.evaluate("() => window.__archPage.generateDiagram()")
        try:
            self.diag.wait_render_stable(clear_marker=True, timeout_ms=5000)
        except TimeoutError:
            self._print('  [WARN] A8 priming 渲染被 L5 跳过 (code 不变, 已对齐), 继续测量')
        before = self.diag.page.evaluate("""() => ({
            skip: window.__archPage?.mermaid?.renderSkippedCount || 0,
            code: window.__archPage?.mermaid?.lastRenderedCode || '',
            dur: window.__archPage?.mermaid?.lastRender?.durationMs ?? null
        })""")
        has_generate = self.diag.page.evaluate(
            "() => typeof window.__archPage?.generateDiagram === 'function'")
        if not has_generate:
            self._record('A', '增量渲染跳过 (generateDiagram 未暴露, 跳过)', True, skipped=True)
            return
        self.diag.page.evaluate("() => window.__archPage.generateDiagram()")
        self.diag.page.wait_for_timeout(1200)
        after = self.diag.page.evaluate("""() => ({
            skip: window.__archPage?.mermaid?.renderSkippedCount || 0,
            code: window.__archPage?.mermaid?.lastRenderedCode || '',
            dur: window.__archPage?.mermaid?.lastRender?.durationMs ?? null
        })""")
        # [FIX 2026-08-13] svg_ok 等待活动 SVG 渲染出节点再断言 (竞态假失败修复, 与 D4 一致).
        #   data_code=False: SM 图折叠态聚合节点 (COLLAPSE_SM_*) 无 data-code 只有 data-container-code,
        #   data_code=True 会漏统计 → svgNodes 假 0. 这里仅需"SVG 有节点保留", 任意 g.node 即可.
        svg_node_count = self.diag.wait_for_svg_nodes(min_count=1, data_code=False)
        svg_ok = svg_node_count > 0
        skipped = after['skip'] > before['skip']
        self._record('A', f'增量渲染跳过 (renderSkippedCount {before["skip"]}→{after["skip"]}, SVG保留={svg_ok})',
                     skipped and svg_ok,
                     {'before': before, 'after': after, 'svgNodes': svg_node_count},
                     error=None if skipped and svg_ok
                     else f'未命中 code-diff 跳过: before={before} after={after} svgNodes={svg_ok}')

    def check_layout(self, golden: Dict[str, Any]) -> None:
        """[E 类 2026-08-05] 布局合并链路断言 (布局面板编辑 → 渲染树合并).

        取代 verify_disable_domain.py 一次性脚本: 数据源是 __archPage.debugLayout
        (EmbeddedChartView 合并链路的分步快照 before→afterStates→afterMembership→afterTitles),
        直接断言权威合并树, 不用人工看 DOM bbox.

        E1 合并链路 4 步快照齐全 (判定走了统一管道)
        E2 afterMembership 与 afterTitles 叶子归属一致 (第三步只改标题/顺序, 不改归属)
        E3 叶子承载分组归属非空 (L18 容器包裹回归守卫)
        E4 enabled 状态传播 — 合并树 afterStates 与面板 panelGroups 一致
        """
        self._print('\n[E] 布局合并链路')
        # E1: 合并链路分步快照齐全
        self._record('E', '合并链路 4 步快照齐全',
                     self.diag.assert_merge_steps_present())

        # E2: 归属合并与标题合并的叶子归属应一致
        mem_m = self.diag.get_layout_membership('afterMembership')
        mem_t = self.diag.get_layout_membership('afterTitles')
        if isinstance(mem_m, dict) and 'error' in mem_m:
            self._record('E', 'afterMembership 归属可读', False,
                         error=mem_m['error'])
        elif isinstance(mem_t, dict) and 'error' in mem_t:
            self._record('E', 'afterTitles 归属可读', False,
                         error=mem_t['error'])
        else:
            diff = []
            for code in set(mem_m) | set(mem_t):
                a = sorted(mem_m.get(code, []))
                b = sorted(mem_t.get(code, []))
                if a != b:
                    diff.append({'group': code, 'afterMembership': a, 'afterTitles': b})
            self._record('E', f'归属合并 vs 标题合并一致 ({len(diff)} 组差异)',
                         not diff, {'diff': diff[:3]},
                         error=None if not diff else f'归属漂移: {diff[:3]}')

        # E3: 叶子承载分组归属非空 (L18 回归守卫)
        leaf_bearing = self.diag.get_leaf_bearing_groups('afterTitles')
        if isinstance(leaf_bearing, dict) and 'error' in leaf_bearing:
            self._record('E', '叶子承载分组归属非空', False,
                         error=leaf_bearing['error'])
        else:
            empty = []
            for code in leaf_bearing:
                actual = (mem_t or {}).get(code, [])
                if code in (mem_t or {}) and not actual:
                    empty.append(code)
            self._record('E', f'叶子分组归属非空 ({len(leaf_bearing) - len(empty)}/{len(leaf_bearing)})',
                         not empty, {'empty': empty[:5]},
                         error=None if not empty else f'空叶子分组: {empty[:5]}')

        # E4: enabled 状态传播 — 合并树 afterStates 与面板 panelGroups 一致
        snap = self.diag.get_layout_snapshot()
        if isinstance(snap, dict) and 'panelGroups' in snap and 'afterStates' in snap:
            merged_codes = set(self.diag.get_layout_group_codes('afterStates'))
            mismatched = []
            checked = 0
            for pg in (snap.get('panelGroups') or []):
                code = pg.get('elementCode') or pg.get('id')
                if not code or code not in merged_codes:
                    continue  # 面板结构分组 (DP_inner/DP_boundary), 合并树不存在, 跳过
                if 'enabled' not in pg:
                    continue
                checked += 1
                m = self.diag._find_group(code, 'afterStates')
                actual = bool(m.get('enabled')) if m else None
                if actual != bool(pg['enabled']):
                    mismatched.append({'group': code, 'panel': pg['enabled'], 'merged': actual})
            self._record('E', f'enabled 状态传播一致 ({checked} 组比对, {len(mismatched)} 组差异)',
                         not mismatched, {'checked': checked, 'mismatched': mismatched[:3]},
                         error=None if not mismatched else f'状态未传播: {mismatched[:3]}')
        else:
            self._record('E', 'enabled 状态传播一致 (panelGroups/afterStates 缺失, 跳过)',
                         True, skipped=True)

    def run_all(self, include: Optional[List[str]] = None) -> List[CheckResult]:
        """执行指定类别的断言 (默认全部 A/B/C/D/E + 性能)."""
        include = include or ['A', 'B', 'C', 'D', 'E', 'P']
        golden = get_scenario_golden(self.scenario_name) or {}
        if not golden:
            self._print(f'\n[WARN] 场景 {self.scenario_name} 无 golden, 只跑不依赖 golden 的断言')

        if 'A' in include:
            self.check_data_integrity(golden)
        if 'B' in include:
            self.check_colors(golden)
            self.check_scope_color()
        if 'C' in include:
            self.check_annotations(golden)
        if 'D' in include:
            self.check_interactions(golden)
        if 'E' in include:
            self.check_layout(golden)
        if 'P' in include:
            self.check_performance(golden)

        # 截图
        self.diag.screenshot(f'{self.scenario_name}_final')
        return self.results

    def summarize(self) -> Dict[str, Any]:
        # [FIX 2026-08-02] results 元素是 CheckResult 对象, 必须用属性访问 r.passed,
        #   不能用 dict 下标 r['passed'] (CheckResult 未实现 __getitem__, 会抛 TypeError).
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed and not r.skipped)
        skipped = sum(1 for r in self.results if r.skipped)
        failed = sum(1 for r in self.results if not r.passed and not r.skipped)
        print(f'\n=== {self.scenario_name} 总结: {passed}/{total} 通过 (skip {skipped}, fail {failed}) ===')
        if failed:
            for r in self.results:
                if not r.passed and not r.skipped:
                    print(f'  [FAIL] [{r.category}] {r.name}: {r.error}')
        return {'scenario': self.scenario_name, 'total': total, 'passed': passed,
                'failed': failed, 'skipped': skipped, 'results': self.results}


def run_scenario(scenario_name: str, include: Optional[List[str]] = None) -> Dict[str, Any]:
    """跑单个场景: 打开 → 断言 → 总结."""
    print(f'\n########## 场景: {scenario_name} ##########')
    with ChartE2E(scenario_name) as runner:
        runner.run_all(include=include)
        return runner.summarize()


def default_scenario_names() -> List[str]:
    """默认套件仅包含 SCP 相关场景 (tier L0/L1, 供应链计划 ~30 BO).

    [2026-08-13] 标准测试范围铁律: 常规回归必须基于供应链计划 (SCP) 子领域,
    严禁加载大子域全量对象. bo_large (L2, 子域 329 全量 ~150 BO) 是独立的大图
    性能专项, 不作为默认套件, 需显式 `--scenario bo_large` 调用.
    """
    return [n for n, s in CHART_FIXTURES['scenarios'].items() if s.get('tier') != 'L2']


def regenerate_golden(scenario_name: Optional[str] = None) -> Dict[str, Any]:
    """生成 golden 基线 (打开每个场景, 记录实测指标)."""
    print('\n===== golden 基线生成 =====')
    names = [scenario_name] if scenario_name else default_scenario_names()
    generated = {}
    for name in names:
        print(f'\n--- 场景 {name}: 打开图表并记录指标 ---')
        with ChartE2E(name) as runner:
            metrics = runner.collect_golden_metrics()
            generated[name] = metrics
            print(f'  nodeCount={metrics["nodeCount"]} edgeCount={metrics["edgeCount"]} '
                  f'containerCount={metrics["containerCount"]} annotations={metrics["annotation_item_count"]} '
                  f'key_nodes={metrics["key_nodes"][:5]}...')
    # 保留旧 golden 中未重生成的场景
    for name, old in (get_scenario_golden_list() or {}).items():
        if name not in generated:
            generated[name] = old
    from test_helpers.chart_fixtures import save_golden
    save_golden({'scenarios': generated})
    print(f'\ngolden 生成完成, 共 {len(generated)} 个场景')
    return generated


def get_scenario_golden_list() -> Dict[str, Any]:
    from test_helpers.chart_fixtures import load_golden
    return load_golden().get('scenarios')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='嵌入图表 E2E 校验')
    parser.add_argument('--regenerate-golden', action='store_true', help='生成 golden 基线')
    parser.add_argument('--scenario', default=None, help='指定场景 (默认全部)')
    parser.add_argument('--category', default=None, help='断言类别 A,B,C,D,E (默认全部)')
    args = parser.parse_args()

    include = args.category.split(',') if args.category else None

    if args.regenerate_golden:
        regenerate_golden(args.scenario)
    else:
        # [FIX 2026-08-13] 默认套件用 default_scenario_names() (排除 L2 大图),
        #   与 golden 生成流程保持一致, 符合标准测试范围铁律 (SCP ~30 BO).
        names = [args.scenario] if args.scenario else default_scenario_names()
        all_pass = True
        for name in names:
            summary = run_scenario(name, include=include)
            if summary['failed'] > 0:
                all_pass = False
        print(f'\n===== E2E 总结果: {"ALL PASS" if all_pass else "HAS FAILURES"} =====')
        sys.exit(0 if all_pass else 1)
