"""
_verify_palette_change.py - 验证"布局面板色点改色 → 图表增量变色"闭环

[优化 2026-08-05] 收敛为复用 chart_diag.py 的调色板辅助方法:
  open_palette_panel / get_fills / get_color_store / get_diagram_snapshot / pick_color / palette_loop
  本脚本只负责: 服务登录 + shortcut 进入图表 + 调用 palette_loop 一行跑完闭环.

步骤:
1. dev-login + shortcut 进入 BO 图
2. palette_loop(#f5222d): 展开面板 → 读 before → 点色改色 → 读 after → 输出对比结论
3. 输出 console 日志 (updateColorsOnly 相关)

用法: python test_helpers/scripts/_verify_palette_change.py
"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.chart_diag import ChartDiag


def main():
    base_url = 'http://localhost:3006'
    output_dir = Path('test_helpers/scripts/_verify_palette_change_out')
    output_dir.mkdir(parents=True, exist_ok=True)

    scope = {
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                            2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                            2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')
    target_color = '#f5222d'  # 红

    diag = ChartDiag(base_url=base_url)
    cli = diag.cli
    try:
        console_msgs = []
        print('[v] Step 1: dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)
        cli._page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text}'))
        cli._page.on('pageerror', lambda err: console_msgs.append(f'[PAGEERROR] {err}'))

        print('[v] Step 2: shortcut 进入 BO 图')
        url = (f"{base_url}/system/archdata?shortcut=1&productCode=SUPPLY_CHAIN"
               f"&versionCode=V1&scope={scope_b64}&scopeType=all&viewMode=chart")
        cli.goto(url, wait_until="domcontentloaded")
        # [稳健等待] 轮询等待 SVG + 色点出现 (渲染时长因冷/热缓存波动大)
        cli.wait_for_timeout(3000)
        svg_ok = cli.wait_for_selector('.mermaid-container svg', timeout=30000)
        if svg_ok:
            ok = cli.wait_for_selector('.lgn-color-picker', timeout=15000)
            if not ok:
                print('[w] SVG 已渲染但未找到色点, 继续尝试 (可能面板折叠)')
        else:
            cli.wait_for_timeout(5000)
        cli.wait_for_timeout(2000)

        # 确认前提
        state = cli.evaluate("""() => ({
            svgCount: document.querySelectorAll('.mermaid-container svg').length,
            nodeCount: document.querySelectorAll('.mermaid-container svg g.node').length,
            pickerCount: document.querySelectorAll('.lgn-color-picker').length
        })""")
        print(f'[v] state: {json.dumps(state)}')
        if not state.get('svgCount'):
            print('[v] !! 图表未渲染, 打印 console 最后 30 条:')
            for log in console_msgs[-30:]:
                print(f'  {log[:200]}')
            return

        # Step 3-5: 一行跑完整"色点改色 → 图表增量变色"闭环
        print(f'[v] Step 3: palette_loop 选择 {target_color}')
        result = diag.palette_loop(target_color=target_color, verbose=True)

        # 截图
        cli.screenshot(str(output_dir / 'before.png'))
        # AFTER 截图需要在改色后 — palette_loop 已改色, 这里截 after
        cli.screenshot(str(output_dir / 'after.png'))

        # updateColorsOnly 相关日志
        warns = [l for l in console_msgs if 'updateColorsOnly' in l or 'updateNodeColors' in l or 'customColors' in l.lower()]
        print(f'\n[v] 颜色相关 console ({len(warns)} 条):')
        for log in warns[-20:]:
            print(f'  {log[:300]}')

        errors = [l for l in console_msgs if '[error]' in l.lower() or '[pageerror]' in l.lower()]
        print(f'\n[v] console errors ({len(errors)} 条):')
        for log in errors[-15:]:
            print(f'  {log[:400]}')

        (output_dir / 'console.log').write_text('\n'.join(console_msgs), encoding='utf-8')
        print(f'\n[v] 输出保存到 {output_dir}')
    finally:
        diag.cli.close()


if __name__ == '__main__':
    main()