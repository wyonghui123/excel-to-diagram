# -*- coding: utf-8 -*-
"""精确复现用户路径: 双击展开 采购供应(MM) 到服务模块 → 连续切换区分/不区分 三次.

核心疑问(用户): 增量更新应只变更颜色, 但第三次切换"看起来重构了".
本脚本用真实双击链路展开 MM, 稳定后连续切换 3 次, 每次抓取:
  - captureNodeSignature (hash): 结构是否变化 (真重建判据)
  - renderMeta.lastRender: 是否调用了 renderMermaid (含 skipped 标志)
  - render groups 中 MM 的 collapsed
区分两种情况:
  A) 真重建: 结构 hash 变化 (折叠/展开被重置)
  B) 假象: hash 不变, 但 lastRender 每次都更新且 skipped=false → 每次切换都全量跑了
     mermaid.run (重排+缩放重置), 只是结构恰好相同. 这也算"应避免"的重建.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

def sig(page):
    return page.evaluate("() => window.__archPage.captureNodeSignature()")

def meta(page):
    return page.evaluate("""() => {
        const d = window.__archPage.diag ? window.__archPage.diag() : null;
        if (!d) return null;
        // 修正 lastRender 的 skipped 字段 (endRender 可能没写 skipped=true, 用 nodeCount 推断)
        return {
            csh: d.config.centerScopeHighlight,
            renderSkippedCount: d.renderMeta.renderSkippedCount,
            lastRender: d.renderMeta.lastRender,
            mmRender: (d.render || []).filter(g => g.key === 'MM').map(g => g.collapsed)
        };
    }""")

def wait_stable(page, getter, timeout_loops=25):
    """等待 getter 返回值连续两次一致 (排除渲染中间态). 返回最终值."""
    prev = None
    for _ in range(timeout_loops):
        v = getter()
        if prev is not None and v is not None and json.dumps(v, ensure_ascii=False) == json.dumps(prev, ensure_ascii=False):
            return v, False  # (最终值, 是否超时未稳定)
        prev = v
        page.wait_for_timeout(900)
    return prev, True

def main():
    cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
    try:
        page = cli.authenticated_navigate(
            "/system/archdata?preset=scp&mode=debug",
            wait_for_selector=".embedded-chart-view",
            timeout=30000
        )
        page.wait_for_function("() => !!window.__archPage && !!window.__archPage.captureNodeSignature", timeout=30000)
        page.wait_for_timeout(3000)

        # 双击展开 采购供应(MM) —— 走真实双击链路 (markGroupManualSet)
        dbl = page.evaluate("""() => {
            const d = window.__archPage.debug;
            if (!d || !d.testDblClick) return 'no-testDblClick';
            return d.testDblClick('g.node[id*="COLLAPSE_SD_MM"]');
        }""")
        print("== [1] testDblClick COLLAPSE_SD_MM:", dbl.get('targetCode') if isinstance(dbl, dict) else dbl)

        # 等待"双击展开"真正渲染完成: 轮询直到 SVG 签名稳定 (排除 mermaid 渲染滞后).
        #   双击展开 MM 到服务模块后 nodeCount 应明显增大 (BO 节点展开), 需等 SVG 稳定.
        base, _ = wait_stable(page, lambda: sig(page))
        print("== [2] 双击展开后 SVG 稳定 base sig:", {k: v for k, v in base.items() if k != 'nodeIds'})
        print("== [2] base nodeIds:", base.get('nodeIds'))
        print("== [2] base meta:", meta(page))

        # 连续切换三次
        for i in range(1, 4):
            page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
            stab2, _ = wait_stable(page, lambda: meta(page))
            s2, _ = wait_stable(page, lambda: sig(page))
            struct_changed = s2.get("hash") != base.get("hash")
            lr = stab2['lastRender'] or {}
            skipped = lr.get('skipped')
            incremental = lr.get('incremental')
            # 增量路径 endRender 传 incremental=true; 全量路径不传 (undefined)
            path = 'INCREMENTAL(updateColorsOnly)' if incremental is True else ('SKIPPED' if skipped is True else 'FULL(renderMermaid)')
            print(f"== [toggle {i}] csh={stab2['csh']} MM collapse={stab2['mmRender']} "
                  f"sigHash={s2['hash']} node={s2['nodeCount']} cluster={s2['clusterCount']} edge={s2['edgeCount']} "
                  f"STRUCT_CHANGED={struct_changed} PATH={path} lastRender.ts={lr.get('startTime')} "
                  f"renderSkippedCount={stab2['renderSkippedCount']}")
            print(f"== [toggle {i}] nodeIds:", s2.get('nodeIds'))

        cli.screenshot("diag_three_toggle.png")
    finally:
        cli.close()

if __name__ == "__main__":
    main()