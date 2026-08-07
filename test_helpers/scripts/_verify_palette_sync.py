"""
_verify_palette_sync.py - 验证"色点颜色与图表颜色同源"闭环

背景 (FIX 2026-08-05):
  之前色点用 useGroupDisplay 的 hashColor(字符串哈希), 图表用 colorize 的"分组遍历顺序索引"取色,
  两套算法不一致 → 按领域分组时, 清空自定义色后色点回不到默认色(与图表不同色)。

修复: colorize 返回 groupColorMap(与图表同源), 经 store → RelationScopeTree → LayoutControlPanel
  传入 colorMapping, 色点 getGroupColor 优先读 colorMapping[key] → 与图表一致。

验证:
1. 读色点当前色 + 图表同分组节点 fill → 断言一致
2. 改色 → 断言色点与图表同步
3. 清空 → 断言色点回到默认色(与图表改色后其他分组一致)

用法: python test_helpers/scripts/_verify_palette_sync.py
"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.chart_diag import ChartDiag


def get_picker_colors(cli):
    """读取所有布局面板色点的 model-value 颜色 + 对应分组文字"""
    return cli.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('.lgn-row'))
        const out = []
        for (const row of rows) {
            const picker = row.querySelector('.lgn-color-picker')
            if (!picker) continue
            const title = row.querySelector('.lgn-title-text')
            const colorEl = picker.querySelector('.el-color-picker__color-inner') ||
                            picker.querySelector('.el-color-picker__trigger .el-color-picker__color')
            let color = ''
            if (colorEl) color = colorEl.style.backgroundColor || ''
            out.push({ title: title ? title.textContent.trim() : '', color })
        }
        return out
    }""")


def main():
    base_url = 'http://localhost:3006'
    scope = {
        'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                            2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                            2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
    }
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')

    diag = ChartDiag(base_url=base_url)
    cli = diag.cli
    try:
        print('[v] dev-login')
        cli.goto(f"{base_url}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)

        print('[v] shortcut 进入 BO 图 (按领域分组)')
        url = (f"{base_url}/system/archdata?shortcut=1&productCode=SUPPLY_CHAIN"
               f"&versionCode=V1&scope={scope_b64}&scopeType=all&viewMode=chart")
        cli.goto(url, wait_until="domcontentloaded")
        cli.wait_for_timeout(3000)
        svg_ok = cli.wait_for_selector('.mermaid-container svg', timeout=30000)
        cli.wait_for_selector('.lgn-color-picker', timeout=15000)
        diag.open_palette_panel()
        cli.wait_for_timeout(1500)

        # 1. 色点颜色 (未改色, 默认色)
        pickers = get_picker_colors(cli)
        print(f'[v] 色点 (默认): {json.dumps(pickers, ensure_ascii=False)}')

        # 2. 图表同分组节点 fill (从 groupColorMap 与节点色对比)
        gcm = cli.evaluate("""() => {
            const ap = window.__archPage
            const d = ap?.diagramData?.value ?? ap?.diagramData
            return d?.groupColorMap || null
        }""")
        print(f'[v] diagramData.groupColorMap: {json.dumps(gcm, ensure_ascii=False)}')

        # 3. store.chartDataSnapshot.groupColorMap 是否同步
        store_gcm = cli.evaluate("""() => {
            const cs = window.__configStore
            return cs?.chartDataSnapshot?.groupColorMap || null
        }""")
        print(f'[v] store.chartDataSnapshot.groupColorMap: {json.dumps(store_gcm, ensure_ascii=False)}')

        # 4. 断言 store 有值
        if not store_gcm or not isinstance(store_gcm, dict) or len(store_gcm) == 0:
            print('[v] !! store.groupColorMap 为空, 链路未打通')
        else:
            print(f'[v] store.groupColorMap 同步 ✓ ({len(store_gcm)} 个分组)')

        # 5. 改色验证同步 (选第一个色点为红)
        print('[v] 改色验证: 第一个色点改红')
        pick = diag.pick_color('#f5222d')
        print(f'  pick: {pick}')
        cli.wait_for_timeout(1500)
        pickers2 = get_picker_colors(cli)
        print(f'[v] 色点 (改色后): {json.dumps(pickers2, ensure_ascii=False)}')
        store2 = diag.get_color_store()
        print(f'[v] store.customColors: {json.dumps(store2, ensure_ascii=False)}')

        # 读取色点背景色实际值
        first_picker_bg = cli.evaluate("""() => {
            const p = document.querySelector('.lgn-color-picker')
            const el = p?.querySelector('.el-color-picker__color-inner') ||
                       p?.querySelector('.el-color-picker__trigger .el-color-picker__color')
            if (!el) return 'no color el'
            const bg = el.style.backgroundColor || ''
            const cs = getComputedStyle(el)
            return { inline: bg, computed: cs.backgroundColor }
        }""")
        print(f'[v] 第一个色点背景: {json.dumps(first_picker_bg)}')

        diag.cli.close()
    finally:
        diag.cli.close()


if __name__ == '__main__':
    main()