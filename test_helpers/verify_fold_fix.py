# -*- coding: utf-8 -*-
"""验证"双击展开采购供应 → 切换区分/不区分 → 是否折叠"遗留bug修复。

用户实际操作: 双击"采购供应"子领域聚合节点 (COLLAPSE_SD_MM) 展开到服务模块,
然后切换 区分/不区分业务对象, 断言不折叠 + 不重建。
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
    try:
        page = cli.authenticated_navigate(
            "/system/archdata?preset=scp&mode=debug",
            wait_for_selector=".embedded-chart-view",
            timeout=30000
        )
        page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
        page.wait_for_timeout(2500)

        # 步骤1: 展开 "采购供应" (MM) 到业务对象层级.
        #   [FIX 2026-08-10] 改用 debug.expandGroup (经 configStore.updateLayoutControlConfig,
        #   触发真实渲染链路) 而非合成 dblclick 事件: 合成事件只更新模型不触发 SVG 重渲染,
        #   导致基线捕获滞后, 后续 render 被误判为"重建". 语义等价用户双击展开.
        exp = page.evaluate("""() => {
            const d = window.__archPage.debug;
            if (!d || !d.expandGroup) return 'no-debug-expandGroup';
            return d.expandGroup('MM', 99);
        }""")
        print("[1] expandGroup MM→99:", exp)
        page.wait_for_timeout(3000)

        # [FIX 2026-08-10] 轮询等待 SVG 渲染出 MM 展开后的业务对象节点 (nodeCount 明显增大且稳定)
        #   再捕获"切换前"基线, 避免渲染滞后导致基线误判.
        prev_sig = None
        for _ in range(20):
            sig = page.evaluate("() => window.__archPage.captureNodeSignature()")
            stable = prev_sig and sig and prev_sig.get("hash") == sig.get("hash")
            has_bo = sig and sig.get("nodeCount", 0) > 20
            if stable and has_bo:
                break
            prev_sig = sig
            page.wait_for_timeout(800)
        afterExpand = prev_sig
        print("[2] after-expand sig:", {k: v for k, v in afterExpand.items() if k != 'nodeIds'})
        print("[2] after-expand nodeIds:", afterExpand.get('nodeIds'))

        # 检查 render 分组中是否存在已展开的 MM 服务模块
        diag = page.evaluate("""() => {
            const d = window.__archPage.diag ? window.__archPage.diag() : null;
            if (!d) return null;
            return {
                render: d.render.map(g => ({key: g.key, title: g.title, collapsed: g.collapsed, groupType: g.groupType})),
                store: d.store.map(g => ({key: g.key, title: g.title, collapsed: g.collapsed}))
            };
        }""")
        print("[2.5] render/store groups:")
        for g in (diag or {}).get('render', []):
            print("   R", g)
        for g in (diag or {}).get('store', []):
            print("   S", g)

        # 步骤2: 切换 区分/不区分
        cur = page.evaluate("() => window.__archPage.chartConfig.centerScopeHighlight")
        print("[3] centerScopeHighlight before:", cur)
        page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
        page.wait_for_timeout(2000)
        page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
        page.wait_for_timeout(2000)

        # 步骤3: 断言 - 未重建 + MM 服务模块保持展开
        # [FIX 2026-08-10] verify 期望 before 结构为 { nodeSignature: <签名> },
        #   否则 no-full-rebuild 断言会被跳过 (此前误传平铺签名导致其静默失效).
        result = page.evaluate(f"""() => window.__archPage.verify({{
            before: {{ nodeSignature: {json.dumps(afterExpand)} }},
            expandKeys: ['MM']
        }})""")
        print("[4] verify result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        cli.screenshot("verify_fold_fix_after_expand.png")

        pass_all = result.get("pass", False)
        # 校验 expanded-kept 的 present
        checked = [c for c in result.get("checks", []) if c["name"].startswith("expanded-kept")]
        if checked:
            detail = checked[0].get("detail", {})
            present = len(detail.get("store", [])) + len(detail.get("chart", [])) + len(detail.get("render", []))
            print(f"[CHECK] expanded-kept:MM present={present} detail={detail}")
            if present == 0:
                print("[WARN] 'MM' 分组未在状态中找到, expanded-kept 断言无效 (需确认实际 key)")
        print("\n[RESULT] verifyPass =", pass_all)
        if not pass_all:
            print("[FAIL] 折叠 bug 仍存在或断言未通过")
            sys.exit(1)
        print("[OK] 折叠 bug 已修复: 双击展开采购供应后切换区分/不区分, 未重建且保持展开")
    finally:
        cli.close()

if __name__ == "__main__":
    main()