"""
chart_probe_legend_reset.py - "图例隐藏 × 切展开层级重置" 唯一正式回归探针 (P0-3, 2026-09-04)

命名说明: 原 probe_legend_v10.py 被 .gitignore `probe_*.py` 误伤 (该规则有意忽略历史临时
探针 v2~v9). 正式回归探针不可被版本控制忽略 → 移入 chart_probe_* 家族 (与 chart_probe_base.py
同族, 同属 test_helpers 基础设施, 不受 probe_* 忽略规则影响).

语义 B: 切展开层级 = 重置为全显 (store + 面板树 + SVG 三者一致)。
同时验证: 直接点击图例隐藏 (不切层级) 仍然生效且不被误重置。

依赖: 前端含 P0-2 的 debug.visibilitySnapshot() (MermaidComponent.vue)。
判定统一消费四层快照 (visibilitySnapshot), 不再各自拼装 DOM/store 断言。

运行: python test_helpers/chart_probe_legend_reset.py
"""
import sys, json
sys.path.insert(0, r'd:/filework/excel-to-diagram')
from test_helpers.chart_probe_base import ChartProbe, CheckCollector

# 聚合节点 SVG 判据: 命中 "供应网络" 折叠聚合节点 (serviceModule 层)
COLLAPSE_SNC_MARKERS = ('COLLAPSE_SM_SNC', 'COLLAPSE_SNC')


def store_snc_hidden(s):
    """store 层 SNC 处于"用户隐藏" (已排除 ELK 系统语义)."""
    return 'SNC' in (s.get('storeUserHidden') or [])


def chart_snc_hidden(s):
    """chartConfig 面板树 SNC 处于用户隐藏 (可能未同步/无 chartConfig → False)."""
    ch = s.get('chartUserHidden')
    return ch is not None and 'SNC' in ch


def svg_snc_none_ids(s):
    return [d.get('id', '') for d in (s.get('svg') or {}).get('displayNone', [])
            if any(m in (d.get('id') or '') for m in COLLAPSE_SNC_MARKERS)]


def svg_snc_hidden(s):
    return len(svg_snc_none_ids(s)) > 0


with ChartProbe() as probe:
    probe.login_and_open()
    chk = CheckCollector()

    # --- A: 真实图例点击隐藏 (不切层级) → store/面板/SVG 三者一致隐藏 ---
    probe.legend_click('✎供应网络')
    sa = probe.wait_until_snapshot(
        lambda s: store_snc_hidden(s),
        'SNC hidden in store after legend click')
    chk.add('A.click hides SNC in store', store_snc_hidden(sa),
            json.dumps(sa.get('storeUserHidden'), ensure_ascii=False))
    chk.add('A.panel SNC visible=false (user-hidden)', chart_snc_hidden(sa),
            json.dumps(sa.get('chartUserHidden'), ensure_ascii=False))
    chk.add('A.svg COLLAPSE_SM_SNC display=none', svg_snc_hidden(sa),
            json.dumps(svg_snc_none_ids(sa)))

    # --- B: 切 subDomain 再回 serviceModule → 全显重置 (store/面板清空, svg 显示) ---
    def reset_ok(s):
        return (not store_snc_hidden(s)) and (not chart_snc_hidden(s)) and (not svg_snc_hidden(s))

    probe.set_expand_level('subDomain')
    probe.set_expand_level('serviceModule')
    sb = probe.wait_until_snapshot(reset_ok, 'all reset to visible after level switch')
    chk.add('B.store hidden cleared', not store_snc_hidden(sb),
            json.dumps(sb.get('storeUserHidden'), ensure_ascii=False))
    chk.add('B.panel SNC user-hidden cleared', not chart_snc_hidden(sb),
            json.dumps(sb.get('chartUserHidden'), ensure_ascii=False))
    chk.add('B.svg SNC visible (not display:none)', not svg_snc_hidden(sb),
            json.dumps(svg_snc_none_ids(sb)))

    if not chk.summary():
        sys.exit(1)
