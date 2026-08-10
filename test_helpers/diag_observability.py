# -*- coding: utf-8 -*-
"""验证 2026-08-10 可观测性落地能力:
  - __archPage.help() 能力清单
  - __archPage.diag() 三份状态
  - __archPage.exportUrl() 复现链接
  - URL 状态应用 (?fold= &scopeHighlight=)
  - 状态真相面板 (工具栏按钮 openTruthPanel + TruthPanel 渲染)

  注意: headless 环境图表渲染极慢 (~38s), 故不用固定超时等 selector,
  改为轮询等待 __archPage.diag 就绪 (它是能力的真实门控点).
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

def wait_api(page, loops=60, delay=1500):
    """轮询等待 __archPage.diag 就绪, 返回耗时秒数; 超时返回 None"""
    for i in range(loops):
        ok = page.evaluate("() => !!(window.__archPage && window.__archPage.diag && window.__archPage.help)")
        if ok:
            return round((i + 1) * delay / 1000, 1)
        page.wait_for_timeout(delay)
    return None

def main():
    cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
    try:
        page = cli.authenticated_navigate(
            "/system/archdata?preset=scp&mode=debug&scopeHighlight=1&fold={\"SCP\":true,\"MM\":false}",
            timeout=20000
        )
        # 不依赖 selector, 轮询等待能力就绪 (headless 渲染慢)
        ready_in = wait_api(page)
        print(f"== API 就绪耗时: {ready_in}s")
        assert ready_in is not None, "__archPage.diag 60s 内未就绪"

        # --- 1. help() 能力清单 ---
        help_ = page.evaluate("() => window.__archPage.help()")
        print("== [1] help() keys:", list((help_ or {}).keys()))
        assert help_ and 'openTruthPanel' in help_ and 'exportUrl' in help_ and 'verify' in help_ and 'captureNodeSignature' in help_, "help() 缺少能力"
        print("== [1] OK help() 完整")

        # --- 2. URL 状态应用: scopeHighlight=1 + fold ---
        csh = page.evaluate("() => window.__archPage.diag().config.centerScopeHighlight")
        print("== [2] URL scopeHighlight=1 应用后 centerScopeHighlight:", csh)
        assert csh is True, "scopeHighlight=1 未应用"

        diag = page.evaluate("""() => {
            const d = window.__archPage.diag();
            const byKey = {};
            d.store.forEach(g => byKey[g.key] = g);
            return { scp: byKey['SCP']?.collapsed, mm: byKey['MM']?.collapsed };
        }""")
        print("== [2] fold 应用后 store SCP.collapsed:", diag['scp'], "MM.collapsed:", diag['mm'])
        assert diag['scp'] is True, "fold: SCP 未折叠"
        assert diag['mm'] is False, "fold: MM 未保持展开"
        print("== [2] OK URL fold/scopeHighlight 已应用")

        # --- 3. exportUrl() 生成复现链接 ---
        url = page.evaluate("() => window.__archPage.exportUrl()")
        print("== [3] exportUrl:", url)
        assert url and ('fold=' in url) and ('scopeHighlight=' in url), "exportUrl 缺少 fold/scopeHighlight"
        print("== [3] OK exportUrl 含 fold+scopeHighlight")

        # --- 4. openTruthPanel 打开真相面板并渲染 ---
        page.evaluate("() => window.__archPage.openTruthPanel()")
        page.wait_for_timeout(1000)
        panel = page.query_selector('[data-testid="truth-panel"]')
        has_rows = False
        if panel:
            rows = page.query_selector_all('[data-testid="truth-panel"] .truth-panel__table tbody tr')
            has_rows = len(rows) > 1
            print("== [4] 真相面板已渲染, 表格行数:", len(rows))
        else:
            print("== [4] !! 真相面板未渲染")
        assert panel is not None and has_rows, "真相面板未渲染或空"
        cli.screenshot("truth_panel.png")
        print("== [4] OK 真相面板渲染含分组行")

        # --- 5. 工具栏「真相」按钮存在 ---
        btn = page.evaluate("""() => {
            const b = [...document.querySelectorAll('button')].find(x => (x.textContent||'').includes('真相'));
            return !!b;
        }""")
        print("== [5] 工具栏真相按钮存在:", btn)
        assert btn, "工具栏「真相」按钮缺失"

        print("\n[RESULT] 全部可观测性能力验证通过")
    finally:
        cli.close()

if __name__ == "__main__":
    main()
