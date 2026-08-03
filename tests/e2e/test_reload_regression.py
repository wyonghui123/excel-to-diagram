"""
test_reload_regression.py - GlobalToolbar refresh 触发图表 reload 回归测试
========================================================================

[B5 2026-08-03] 验证 reload 链路 (window.__archPage.reload → forceRerender →
  mermaid.run() 全量重绘 SVG) 不退化. 历史背景: 曾因 nextTick 内引用未定义变量
  抛 ReferenceError, mermaid.run() 没机会执行 → <pre> 保留 mermaid code 文本,
  用户看到 text 而非 SVG.

[测试场景]
  1. 打开图表页 (ChartDiag.open_chart, scope=DEFAULT 30 BO)
  2. 记录 reload 前基线: SVG 节点数 / stepMeta.reload (应不存在或为 undefined)
  3. 注册 page.on('pageerror') 监听未捕获异常 (含 UnhandledRejection)
  4. 调用 window.__archPage.reload() (与 GlobalToolbar refresh 等价入口)
  5. 等 wait_render_stable(clear_marker=True) → 新渲染完成
  6. 断言:
       A. SVG 存在 (querySelector('svg') 非空)
       B. g.node 数 > 0 (mermaid.run() 真的把 <pre> 转成了 SVG)
       C. stepMeta.reload 存在 (A3 埋点: forceRerender → diag.recordStepMeta('reload'))
       D. 无 pageerror 事件 (nextTick try/catch + mermaid.run().catch() 兜底有效)

[浏览器测试铁律]
  唯一合法入口: test_helpers/browser_auth_cli.py (PlaywrightCLI).
  禁用任何 MCP 浏览器工具 (mcp_Chrome_DevTools_MCP_* / mcp_Playwright_* 等).
  详见 .trae/rules/.deprecated/mcp-testing.md 顶部说明.

[用法]
  cd d:/filework/excel-to-diagram
  python -m tests.e2e.test_reload_regression
  # 或
  python tests/e2e/test_reload_regression.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# 兼容 `python -m tests.e2e.test_reload_regression` 和 `python tests/e2e/test_reload_regression.py`
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from test_helpers.chart_diag import ChartDiag, DEFAULT_SCOPE
from test_helpers.chart_fixtures import BASE_URL, PRODUCT_CODE, VERSION_ID


def run_reload_regression() -> Dict[str, Any]:
    """执行一次 reload 回归测试, 返回结果字典."""
    diag = ChartDiag(base_url=BASE_URL,
                     product_code=PRODUCT_CODE,
                     version_id=VERSION_ID)
    pageerrors: List[str] = []
    try:
        # 1. 打开图表 (DEFAULT_SCOPE = 30 BO 子域 299)
        diag.open_chart(scope=DEFAULT_SCOPE, wait_for_selector='svg g.node')
        diag.wait_render_stable(clear_marker=False)

        # 2. 记录 reload 前基线
        baseline = page_eval_reload_baseline(diag)
        print(f'[baseline] svgExists={baseline["svgExists"]}, '
              f'nodeCount={baseline["nodeCount"]}, '
              f'reloadStepMeta={baseline["reloadStepMeta"]}')

        # 3. 注册 pageerror 监听 (捕获 nextTick/mermaid.run 未捕获异常)
        diag.page.on('pageerror', lambda exc: pageerrors.append(str(exc)))

        # 4. 触发 reload (与 GlobalToolbar refresh 等价入口)
        diag.page.evaluate("() => window.__archPage && window.__archPage.reload && window.__archPage.reload()")

        # 5. 等新渲染完成 (clear_marker=True: 确保等的是本次 reload 触发的新渲染)
        #   reload → forceRerender → renderMermaid → diag.beginRender/endRender
        #   → EmbeddedChartView onDiagRenderEnd → 设 data-chart-rendered=true
        render_state = diag.wait_render_stable(timeout_ms=30000, clear_marker=True)

        # 6. 收集 post-reload 状态
        post = page_eval_reload_baseline(diag)
        print(f'[post]     svgExists={post["svgExists"]}, '
              f'nodeCount={post["nodeCount"]}, '
              f'reloadStepMeta={post["reloadStepMeta"]}, '
              f'renderNodeCount={render_state["nodeCount"]}')
        if pageerrors:
            print(f'[pageerrors] {len(pageerrors)} 个:')
            for i, e in enumerate(pageerrors, 1):
                print(f'  [{i}] {e}')

        # 7. 断言
        checks = {
            'A_svg_exists': post['svgExists'] is True,
            'B_node_count_gt_0': post['nodeCount'] > 0,
            'C_reload_stepmeta_fired': post['reloadStepMeta'] is not None,
            'D_no_pageerror': len(pageerrors) == 0,
        }
        # 节点数不应大幅缩水 (reload 是相同数据重绘, 节点数应 >= baseline 的 90%)
        if baseline['nodeCount'] > 0:
            ratio = post['nodeCount'] / baseline['nodeCount']
            checks['E_node_count_not_shrunk'] = ratio >= 0.9
        else:
            checks['E_node_count_not_shrunk'] = True

        passed = all(checks.values())
        for name, ok in checks.items():
            print(f'  [{"OK" if ok else "FAIL"}] {name}')

        return {
            'passed': passed,
            'checks': checks,
            'baseline': baseline,
            'post': post,
            'render_state': render_state,
            'pageerrors': pageerrors,
        }
    finally:
        diag.close()


def page_eval_reload_baseline(diag: ChartDiag) -> Dict[str, Any]:
    """读取当前 SVG / stepMeta.reload 状态."""
    return diag.page.evaluate("""() => {
        const svg = document.querySelector('.embedded-chart-view__canvas svg, .mermaid-container svg')
        const meta = window.__archPage?.mermaid?.stepMeta?.reload || null
        return {
            svgExists: !!svg,
            nodeCount: svg ? svg.querySelectorAll('g.node').length : 0,
            reloadStepMeta: meta,
            // [DIAG] pre 仍存在 = mermaid.run() 没成功转换 (退化信号)
            preExists: !!document.querySelector('.embedded-chart-view__canvas pre.mermaid, .mermaid-container pre.mermaid'),
        }
    }""")


def main() -> int:
    print('=' * 72)
    print('reload 回归测试 (B5 2026-08-03)')
    print('=' * 72)
    result = run_reload_regression()
    print('=' * 72)
    if result['passed']:
        print('[PASS] reload 链路正常: SVG 重绘 + 节点数 > 0 + A3 埋点 + 无 pageerror')
        return 0
    else:
        failed = [k for k, v in result['checks'].items() if not v]
        print(f'[FAIL] 失败项: {failed}')
        if result['pageerrors']:
            print(f'  pageerror 详情:')
            for e in result['pageerrors']:
                print(f'    - {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
