"""
诊断版: 2026-08-06 三项视觉优化验证 (tooltip 说明行隐藏 / 上提标题祖先路径 / 多行标题渲染高度)
运行环境: 需要前端 3005 + 后端 3011 已启动.
验证场景:
  A. remapped 连线携带 sourceLevel/targetLevel
  B. 上提服务模块 需求计划(DP) 标题含祖先路径 (供应链云/供应链计划), 用名称而非编码
  C. 折叠到子领域层级, 制造两端均高层级(<=2)的关系, hover 后 tooltip 应隐藏"说明行"
  D. 上提聚合节点(COLLAPSE_<id>)多行 label 渲染: 含 <br> 且高度容纳多行
"""
import sys
import time
import json
import base64
import urllib.parse

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3005'
VID = 863
PID = 507
DOMAIN_ID = 2200
SUB_DOMAIN_ID = 299

PASS = []
FAIL = []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print(f'  \u2713 PASS: {name}')
    else:
        FAIL.append(name)
        print(f'  \u2717 FAIL: {name} {detail}')


def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(30000)

        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        scope_json = json.dumps({
            'business_object': [], 'service_module': [],
            'sub_domain': [SUB_DOMAIN_ID], 'domain': [DOMAIN_ID], 'relation_codes': []
        })
        scope_b64 = base64.b64encode(scope_json.encode('utf-8')).decode('ascii')
        scope_enc = urllib.parse.quote(scope_b64, safe='')
        page.goto(f'{FRONTEND}/system/archdata?shortcut=1&productId={PID}&versionId={VID}&scope={scope_enc}',
                  wait_until='domcontentloaded', timeout=15000)

        page.wait_for_function("""() => {
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            for (const s of svgs) if ((s.textContent||'').length > 100) return true;
            return false;
        }""", timeout=90000)
        time.sleep(3)

        # [A] 折叠 供应链云, 检查 remapped 连线 sourceLevel/targetLevel
        print('[A] remapped 连线携带 sourceLevel/targetLevel')
        page.evaluate('''() => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.elementCode==='SCM') return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g); if (grp) { grp.enabled = true; grp.collapsed = true; }
        }''')
        time.sleep(9)
        diag = page.evaluate('''() => {
            const d = window.__archPage?.mermaid?.linkDiag || {};
            const rm = d.remapped || [];
            return { total: rm.length, items: rm.slice(0, 12).map(l => ({
                src: l.sourceCode, tgt: l.targetCode, srcLv: l.sourceLevel, tgtLv: l.targetLevel
            })) };
        }''')
        check('remapped 连线携带 sourceLevel/targetLevel', (diag['items'] or []) and any(
            isinstance(i.get('srcLv'), (int, float)) for i in diag['items']),
            f"samples={diag['items'][0] if diag['items'] else None}")

        # [B] 上提服务模块 需求计划 (DP) 标题祖先路径
        print('\n[B] 上提服务模块 需求计划 (DP) 标题祖先路径')
        page.evaluate('''() => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function walk(items) { if (!items) return; for (const it of items) { it.collapsed = false; walk(it.children); walk(it.containers); } }
            walk(g);
        }''')
        time.sleep(6)
        page.evaluate('''() => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.elementCode==='DP') return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g); if (grp) { grp.enabled = true; grp.collapsed = true; }
        }''')
        time.sleep(9)
        code = page.evaluate('() => window.__lastMermaidCode || ""')
        dp_zone = code[code.find('需求计划'):code.find('需求计划') + 120] if '需求计划' in code else ''
        check('上提 DP 标题含祖先路径 (供应链云/供应链计划)', '供应链云/供应链计划' in dp_zone,
              f'zone={dp_zone[:80]}')
        check('祖先路径用名称而非编码', not ('SCM/SCP' in dp_zone), f'zone={dp_zone[:80]}')

        # [D] 上提聚合节点多行 label 渲染
        node_info = page.evaluate('''() => {
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            let svg = null;
            for (const s of svgs) if ((s.textContent||'').length > 100) { svg = s; break; }
            if (!svg) return { found: false };
            const nodes = Array.from(svg.querySelectorAll('.node'))
                .filter(n => (n.id||'').indexOf('COLLAPSE') >= 0);
            const out = nodes.map(n => {
                const fo = n.querySelector('foreignObject');
                const div = fo ? fo.querySelector('div') : null;
                return {
                    id: n.id,
                    text: div ? div.textContent : '',
                    foHeight: fo ? parseFloat(fo.getAttribute('height')) : null,
                    hasBr: !!n.querySelector('br')
                };
            });
            return { found: !!svg, nodes: out };
        }''')
        print(f'  COLLAPSE 节点: {json.dumps(node_info, ensure_ascii=False)}')
        dp_node = None
        for n in node_info.get('nodes') or []:
            if '需求计划' in (n['text'] or ''):
                dp_node = n
                break
        if dp_node:
            check('上提节点多行 label 含 <br> 换行', dp_node.get('hasBr'), f'{json.dumps(dp_node)}')
            height_ok = dp_node.get('foHeight') and dp_node['foHeight'] >= 40  # 2 行至少 40px
            check('上提节点多行 label 高度容纳两行', height_ok, f"height={dp_node.get('foHeight')}")
        else:
            check('找到上提 DP 节点', False, f'not found, nodes={[n.get("id") for n in node_info.get("nodes") or []]}')

        # [C] tooltip 高层级关系说明行隐藏
        print('\n[C] 折叠到子领域层级, hover 高层级关系 tooltip')
        page.evaluate('''() => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function walk(items) { if (!items) return; for (const it of items) {
                it.collapsed = (it.groupType === 'subDomain') ? true : false;
                it.enabled = true;
                walk(it.children); walk(it.containers);
            } }
            walk(g);
        }''')
        time.sleep(9)
        diag2 = page.evaluate('''() => {
            const d = window.__archPage?.mermaid?.linkDiag || {};
            const rm = d.remapped || [];
            return { highLevelCount: rm.filter(l => (l.sourceLevel <= 2) && (l.targetLevel <= 2)).length };
        }''')
        check('存在两端均高层级(<=2)的关系连线', (diag2.get('highLevelCount') or 0) > 0,
              f"count={diag2.get('highLevelCount')}")
        tooltip = page.evaluate('''() => {
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            let svg = null;
            for (const s of svgs) if ((s.textContent||'').length > 100) { svg = s; break; }
            if (!svg) return null;
            const labels = Array.from(svg.querySelectorAll('.edgeLabel'));
            const target = labels[3] || labels[0];
            if (!target) return null;
            const rect = target.getBoundingClientRect();
            const opts = { bubbles: true, cancelable: true, clientX: rect.x + rect.width/2, clientY: rect.y + rect.height/2 };
            target.dispatchEvent(new MouseEvent('mouseenter', opts));
            target.dispatchEvent(new MouseEvent('mousemove', opts));
            return target;  // 返回元素以便后续读取 tooltip
        }''')
        time.sleep(1)
        tooltip_text = page.evaluate('''() => {
            const el = document.getElementById('mermaid-tooltip');
            return el ? el.textContent : null;
        }''')
        print(f'  tooltip 内容: {repr(tooltip_text)}')
        if tooltip_text:
            check('tooltip 显示关系header', '→' in tooltip_text, repr(tooltip_text[:60]))
            # 高层级说明行已隐藏: 原始 desc (如"供应链计划...")不应整段出现; 这里以"类型/方向行存在但无说明行"为准
            has_type = '类型:' in tooltip_text
            has_desc_line = '关系说明' in tooltip_text
            check('tooltip 已隐藏高层级说明行', has_type and not has_desc_line, repr(tooltip_text[:80]))
        else:
            check('tooltip 有内容', False, 'tooltip empty')

    finally:
        cli.close()

    print('\n==========================================')
    print(f'总结果: PASS={len(PASS)} FAIL={len(FAIL)}')
    for f in FAIL:
        print(f'  \u2717 {f}')
    if FAIL:
        sys.exit(1)
    print('\u2713 自测通过')


if __name__ == '__main__':
    main()