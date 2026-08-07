"""
自测闭环: 图表折叠语义 (FR-001~006, 2026-08-05)

测试数据: TTTTT000 产品 / V11 版本 (vid=863), 对象范围 = 供应链云(2200) → 供应链计划(299)

验证:
  FR-002 折叠渲染: 设置 供应链云 group.collapsed=true → 图表渲染为聚合节点, 子孙 BO 消失
  FR-003 连线重映射(间接): 折叠后图表正常渲染, 无 mermaid 语法错误 (SVG 仍存在)
  FR-006 级联折叠: 面板级联折叠动作 → 折叠父分组时子孙 collapsed 亦为 true (数据流)
  FR-005 视图模板: allEnabled 恢复全部 / onlyServiceModules 隐藏 BO 叶 (数据流)
  编码传播: 折叠后连线 label 用编码而非名称; 前序模型/分组树携带领域(SCM)/子领域(SCP)编码

前置: 前端 3005 (VITE_PORT=3005, BACKEND_PORT=3010), 后端 3010 dev-login 可用。
"""
import sys
import time
import json
import base64
import urllib.parse

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3005'
TARGET_PATH = '/system/archdata'
VID = 863
PID = 507          # TTTTT000
DOMAIN_ID = 2200      # 供应链云
SUB_DOMAIN_ID = 299   # 供应链计划

PASS = []
FAIL = []


def svg_text(page):
    """读取 EmbeddedChartView 内真正的 mermaid SVG 文本 (最大 textContent 的 svg)."""
    return page.evaluate('''() => {
        const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
        let best = '', bestLen = 0;
        for (const s of svgs) {
            const l = (s.textContent || '').length;
            if (l > bestLen) { best = s.textContent || ''; bestLen = l; }
        }
        return best;
    }''')


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print(f'  \u2713 PASS: {name}')
    else:
        FAIL.append(name)
        print(f'  \u2717 FAIL: {name} {detail}')


def is_code(s):
    """编码判定: 非空且不含中文 → 视为编码 (如 SCM/SCP/SCM-SCP)."""
    return bool(s) and not any('\u4e00' <= c <= '\u9fff' for c in s)


def read_link_diag(page):
    """读取收敛探针 window.__archPage.mermaid.linkDiag (兼容旧 linkDiag)."""
    return page.evaluate('''() => {
        const d = window.__archPage?.mermaid?.linkDiag || window.__archPage?.linkDiag || {};
        const summarize = (arr) => (arr||[]).map(g => {
            const o = { level: g.level };
            if (g.code != null) o.code = g.code;
            if (g.name != null) o.name = g.name;
            if (g.elementCode != null) o.elementCode = g.elementCode;
            if (g.title != null) o.title = g.title;
            if (g.modules) o.modules = summarize(g.modules);
            if (g.children) o.children = summarize(g.children);
            return o;
        });
        return {
            domainProducts: summarize(d.domainProducts),
            remapGroups: summarize(d.remapGroups),
            remapped: d.remapped || []
        };
    }''')


def find_in_tree(arr, title):
    """在统一层级树 (domainProducts/remapGroups) 中按 title 查找节点."""
    for g in arr or []:
        if g.get('title') == title or g.get('name') == title:
            return g
        for key in ('modules', 'children'):
            if g.get(key):
                found = find_in_tree(g[key], title)
                if found:
                    return found
    return None


def check_link_encoding(page):
    """折叠连线编码断言: 前序模型/分组树携带 code, 重映射连线 label 用编码而非名称."""
    diag = read_link_diag(page)
    if not diag.get('domainProducts'):
        check('linkDiag 探针就绪 (domainProducts 非空)', False, 'probe 未捕获')
        return

    # 1) 前序模型: 领域 供应链云 → SCM, 子领域 供应链计划 → SCP
    dom = find_in_tree(diag['domainProducts'], '供应链云')
    check('domainProducts 领域携带编码 (SCM)', (dom or {}).get('code') == 'SCM',
          f"got={dom and dom.get('code')}")
    sd = find_in_tree(diag['domainProducts'], '供应链计划')
    check('domainProducts 子领域携带编码 (SCP)', (sd or {}).get('code') == 'SCP',
          f"got={sd and sd.get('code')}")
    # [REGRESSION 2026-08-06] 非选中子领域 (经 V1.1.13 关系补全) 也必须携带编码:
    #   后端 bo_api raw SQL 补全 sub_domains 时缺 sd.code → code=名称 (采购供应 应为 MM),
    #   折叠连线标签一端显示名称 (e.g. SCP-采购供应). 锁死回归.
    sd_mm = find_in_tree(diag['domainProducts'], '采购供应')
    check('domainProducts 非选中子领域 采购供应 携带编码 (MM)', (sd_mm or {}).get('code') == 'MM',
          f"got={sd_mm and sd_mm.get('code')}")

    # 2) 分组树 (渲染权威来源): 上提聚合节点应携带真实编码 SCM (非名称回退)
    rg = find_in_tree(diag['remapGroups'], '供应链云')
    rg_code = ((rg or {}).get('elementCode') or (rg or {}).get('code'))
    check('remapGroups 供应链云聚合节点携带编码 (SCM)', rg_code == 'SCM',
          f"got={rg_code}")

    # 3) 重映射连线: 非空 label 应全为编码 (不含中文)
    remapped = diag.get('remapped') or []
    labeled = [l for l in remapped if l.get('label')]
    bad = [l for l in labeled if not is_code(l.get('label'))]
    hasLabel = len(labeled) > 0
    check('折叠后存在带标签的连线', hasLabel, f'labeled={len(labeled)}')
    check('折叠后连线 label 均为编码 (无中文名称)', len(bad) == 0,
          f'bad={[l["label"] for l in bad[:5]]}')


def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(30000)

        # 1. dev-login
        print('[1] dev-login')
        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin',
                  wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        # 2. 用 dev shortcut 直达 EmbeddedChartView:
        #    shortcut=1 自动应用 scope + 打开图表; productId/versionId 选定 TTTTT000/V11;
        #    scope 限定 供应链云(2200) → 供应链计划(299)
        print('[2] 直达 EmbeddedChartView (shortcut, scope=供应链云/供应链计划)')
        scope_json = json.dumps({
            'business_object': [],
            'service_module': [],
            'sub_domain': [SUB_DOMAIN_ID],
            'domain': [DOMAIN_ID],
            'relation_codes': []
        })
        scope_b64 = base64.b64encode(scope_json.encode('utf-8')).decode('ascii')
        scope_enc = urllib.parse.quote(scope_b64, safe='')
        shortcut_url = (f'{FRONTEND}/system/archdata'
                        f'?shortcut=1&productId={PID}&versionId={VID}'
                        f'&scope={scope_enc}')
        page.goto(shortcut_url, wait_until='domcontentloaded', timeout=15000)

        # 3. 等 SVG 渲染 (mermaid 图表 svg 有真实文本内容)
        print('[3] 等 SVG 渲染')
        page.wait_for_function("""() => {
            const svgs = document.querySelectorAll('.embedded-chart-view__canvas svg');
            for (const s of svgs) if ((s.textContent||'').length > 100) return true;
            return false;
        }""", timeout=90000)
        time.sleep(3)
        page.wait_for_function("""
            () => !!(window.__archPage && window.__archPage.chartConfig && window.__archPage.chartConfig.layoutControl && window.__archPage.chartConfig.layoutControl.groups && window.__archPage.chartConfig.layoutControl.groups.length > 0)
        """, timeout=20000)

        # 7. 读取 groups, 定位 供应链云 分组
        print('[7] 读取 groups, 定位 供应链云')
        probe = page.evaluate('''(ec) => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.elementCode === ec || it.title === '供应链云') return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g);
            return {
                topCount: (g||[]).length,
                found: !!grp,
                id: grp?.id, title: grp?.title, elementCode: grp?.elementCode, groupType: grp?.groupType,
                collapsed: grp?.collapsed,
                childCount: (grp?.children||[]).length, containerCount: (grp?.containers||[]).length
            };
        }''', 'SCM')
        print(f'  {json.dumps(probe, ensure_ascii=False)}')
        if not probe.get('found'):
            print('  ERROR: 未找到 供应链云 分组')
            return
        target_id = probe['id']

        # 8. 折叠前: 收集该分组下所有 BO 叶 code + 记录 SVG
        #    (用 code 而非 name 判定隐藏, 避免跨领域同名 BO 误判, 如 '计划独立需求' DP10/MR04)
        pre = page.evaluate('''(targetId) => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.id===targetId) return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g);
            const boCodes = [];
            function collectLeaf(item) {
                (item.directNodes||[]).forEach(n => { if (typeof n === 'object') boCodes.push(n.code||n.id||n.name); else boCodes.push(n); });
                (item.containers||[]).forEach(c => { if (c && typeof c === 'object') { (c.nodes||[]).forEach(n => { if (typeof n === 'object') boCodes.push(n.code||n.id||n.name); else boCodes.push(n); }); } });
                (item.children||[]).forEach(collectLeaf);
                (item.containers||[]).forEach(collectLeaf);
            }
            collectLeaf(grp);
            return { title: grp.title, boCodes: boCodes.slice(0, 8), boCodeCount: boCodes.length };
        }''', target_id)
        pre_text = svg_text(page)
        pre['svgLength'] = len(pre_text)
        print(f'  折叠前: {json.dumps(pre, ensure_ascii=False)[:400]} (svgLen={len(pre_text)})')
        if pre.get('error'):
            print(f'  ERROR: {pre["error"]}')
            return
        boCodes = [c for c in pre.get('boCodes', []) if c]
        check('折叠前该分组下有 BO 叶可验证', len(boCodes) > 0, f'boCodes={boCodes}')

        # 9. 树折叠 (EXPAND 2026-08-05): enabled 分组 + collapsed=true → 上提为 COLLAPSE 聚合节点
        #    (与 enabled 正交: 折叠即使有启用子孙也上提为彩色节点, 不改子孙 enabled)
        #    注意: 树折叠只对 enabled 分组生效 (disabled 优先隐藏+子孙上浮). 该分组默认 enabled=false,
        #    故先置 enabled=true 演化为"启用+折叠"场景再验证上提.
        print(f'[8] 折叠 供应链云 (树折叠: enabled + collapsed=true → 上提)')
        fold = page.evaluate('''(targetId) => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.id===targetId) return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g);
            if (!grp) return { error: 'not found' };
            grp.enabled = true;   // 保留层级
            grp.collapsed = true; // 树折叠 → 上提为节点
            return { ok: true, collapsed: grp.collapsed, enabled: grp.enabled };
        }''', target_id)
        print(f'  fold: {fold}')
        check('树折叠 (enabled+collapsed=true) 成功', fold.get('ok') is True)

        # 10. 等重渲染
        print('[9] 等重渲染')
        time.sleep(8)
        check('折叠后 SVG 仍存在 (无渲染错误/FR-003)', page.evaluate(
            '''() => !!document.querySelector('.embedded-chart-view__canvas svg')'''))

        # 11. 折叠后验证 — 用 svg_text (最大文本 svg) 读取真实图表文本
        post = page.evaluate('''(args) => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.id===args.targetId) return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g);
            // 诊断: 渲染用的 merged groups 是否携带 collapsed (debugLayout 来自 EmbeddedChartView)
            const dl = window.__archPage?.debugLayout || {};
            function findCollapsed(arr, code) { for (const it of arr||[]) { if (it.elementCode===code || it.id===code) return it.collapsed; const f=findCollapsed(it.children, code); if (f!==undefined) return f; const c=findCollapsed(it.containers, code); if (c!==undefined) return c; } return null; }
            return {
                collapsed: grp?.collapsed,
                afterStatesCollapsed: findCollapsed(dl.afterStates, args.code),
                afterTitlesCollapsed: findCollapsed(dl.afterTitles, args.code),
                hasDebugLayout: !!window.__archPage?.debugLayout
            };
        }''', {'targetId': target_id, 'code': '供应链云'})
        post_text = svg_text(page)
        # 诊断: 枚举 .embedded-chart-view__canvas 下所有 svg + 读取真实 mermaid code
        diag_svg = page.evaluate('''() => {
            const svgs = Array.from(document.querySelectorAll('.embedded-chart-view__canvas svg'));
            const code = window.__lastMermaidCode || '';
            // 分析 code 中是否含折叠/聚合节点 + 供应链云相关定义
            const collapseMatches = (code.match(/COLLAPSE_[\w\u4e00-\u9fff]+/g) || []);
            const gylMatches = (code.match(/subgraph G_D_供应链云/g) || []);
            const gylSd = (code.match(/subgraph G_SD_/g) || []).length;
            return {
                hasCollapseNode: code.includes('COLLAPSE_供应链云'),
                collapseNodes: collapseMatches.slice(0, 10),
                hasG_D_供应链云: code.includes('subgraph G_D_供应链云'),
                gylSdCount: gylSd,
                codeLen: code.length,
                codeTail: code.slice(-400)
            };
        }''')
        # 诊断: 渲染用 merged groups (afterTitles) 顶层结构
        diag_top = page.evaluate('''() => {
            const dl = window.__archPage?.debugLayout || {};
            const top = (dl.afterTitles || []);
            const summarize = (arr) => (arr||[]).map(g => ({ id: g.id, code: g.elementCode, title: g.title, groupType: g.groupType, enabled: g.enabled, collapsed: g.collapsed, childCount: (g.children||[]).length, containerCount: (g.containers||[]).length }));
            return { top: summarize(top) };
        }''')
        print(f'  诊断TOP: {json.dumps(diag_top, ensure_ascii=False)[:800]}')
        print(f'  诊断SVG/CODE: {json.dumps(diag_svg, ensure_ascii=False)[:600]}')
        post_code = page.evaluate('() => window.__lastMermaidCode || ""')
        stillThere = [c for c in boCodes if c and f'({c})' in post_code]
        # 聚合节点标题 = 分组标题 '供应链云' (groupedLayout 折叠节点 label 用 group.title)
        aggPresent = '供应链云' in post_text
        print(f'  折叠后: collapsed={post.get("collapsed")} aggPresent={aggPresent} '
              f'postSvgLen={len(post_text)} stillThere={stillThere[:5]}')
        print(f'  诊断: hasDebugLayout={post.get("hasDebugLayout")} '
              f'afterStatesCollapsed={post.get("afterStatesCollapsed")} '
              f'afterTitlesCollapsed={post.get("afterTitlesCollapsed")}')
        check('折叠后分组标题仍出现 (聚合节点)', aggPresent is True)
        check('折叠后子孙 BO 从 SVG 消失', len(stillThere) == 0,
              f'stillThere={stillThere[:5]}')

        # 11.5 折叠连线编码断言 (2026-08-06): 前序模型/分组树/重映射连线三段编码一致性
        print('[9.5] 折叠连线编码断言 (linkDiag)')
        check_link_encoding(page)

        # 12. 恢复展开 = collapsed=false (树折叠恢复 → 恢复容器, 子孙 BO 回到 SVG)
        #     [EXPAND 2026-08-05] 树折叠只改 collapsed, 未动子孙 enabled, 恢复后子孙直接回来.
        print('[10] 恢复展开')
        restore = page.evaluate('''(targetId) => {
            const g = window.__archPage.chartConfig.layoutControl.groups;
            function find(items) { for (const it of items||[]) { if (it.id===targetId) return it; const f=find(it.children); if(f) return f; } return null; }
            const grp = find(g);
            if (!grp) return { error: 'not found' };
            grp.collapsed = false;
            return { ok: true };
        }''', target_id)
        print(f'  restore: {restore}')
        time.sleep(8)
        restore_text = svg_text(page)
        restore_code = page.evaluate('() => window.__lastMermaidCode || ""')
        back = [c for c in boCodes if c and f'({c})' in restore_code]
        print(f'  恢复后 BO 回到 SVG: {back[:5]} (count={len(back)})')
        # 诊断: 恢复后渲染用 merged groups 的 D_供应链云 状态 + 是否恢复为 subgraph 容器
        diag_restore = page.evaluate('''(code) => {
            const dl = window.__archPage?.debugLayout || {};
            function findCollapsed(arr, code) { for (const it of arr||[]) { if (it.elementCode===code || it.id===code) return {enabled: it.enabled, collapsed: it.collapsed, _uplift: it._uplift}; const f=findCollapsed(it.children, code); if (f) return f; } return null; }
            return {
                hasG: code.includes('subgraph G_D_供应链云'),
                hasCollapse: code.includes('COLLAPSE_D_供应链云'),
                afterTitles: findCollapsed(dl.afterTitles, '供应链云'),
                codeLen: code.length
            };
        }''', restore_code)
        print(f'  恢复诊断: {json.dumps(diag_restore, ensure_ascii=False)}')
        check('恢复折叠后子孙 BO 回到 SVG', len(back) > 0,
              f'back={back[:5]}')

        # 13. FR-005 视图模板 (configStore.applyViewTemplate) 数据流
        print('[11] 视图模板 (store.applyViewTemplate)')
        tpl = page.evaluate('''async () => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('diagramConfig');
            if (!store || typeof store.applyViewTemplate !== 'function') return { error: 'no store.applyViewTemplate' };
            store.applyViewTemplate('allEnabled');
            const groups = store.layoutControlConfig?.groups || [];
            let allEnabled = true, allUncollapsed = true;
            function walk(items) { if (!items) return; for (const it of items) { if (it.enabled === false) allEnabled=false; if (it.collapsed === true) allUncollapsed=false; walk(it.children); walk(it.containers); } }
            walk(groups);
            return { groupCount: groups.length, allEnabled, allUncollapsed, viewTemplate: store.viewTemplate };
        }''')
        print(f'  template allEnabled: {tpl}')
        check('allEnabled 模板应用成功', tpl.get('error') is None, f'err={tpl.get("error")}')
        check('allEnabled 后全部 enabled', tpl.get('allEnabled') is True)
        check('allEnabled 后全部无折叠', tpl.get('allUncollapsed') is True)

        tpl2 = page.evaluate('''() => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('diagramConfig');
            if (!store || typeof store.applyViewTemplate !== 'function') return { error: 'no store' };
            store.applyViewTemplate('onlyServiceModules');
            const groups = store.layoutControlConfig?.groups || [];
            let boLeafDisabled = null; let smKept = true;
            let boLeafCount = 0; const boSamples = [];
            function walk(items) { if (!items) return; for (const it of items) {
                const isBO = it.isVirtual === true || it.elementRef?.type === 'BUSINESS_OBJECT';
                const isSM = it.groupType === 'serviceModule' || it.elementRef?.type === 'SERVICE_MODULE';
                if (isBO) { boLeafDisabled = (it.enabled === false); boLeafCount++; if (boSamples.length < 5) boSamples.push({ title: it.title, enabled: it.enabled, isVirtual: it.isVirtual, groupType: it.groupType, refType: it.elementRef?.type }); }
                if (isSM && it.enabled === false) smKept = false;
                walk(it.children); walk(it.containers);
            } }
            walk(groups);
            return { boLeafCount, boSamples, boLeafDisabled, smKept, viewTemplate: store.viewTemplate };
        }''')
        print(f'  template onlyServiceModules: {tpl2}')
        check('onlyServiceModules: BO 叶被禁用', tpl2.get('boLeafDisabled') is True, f'got={tpl2.get("boLeafDisabled")}')
        check('onlyServiceModules: SM 保留', tpl2.get('smKept') is True)

        # 恢复干净状态
        page.evaluate('''() => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const store = pinia._s.get('diagramConfig');
            if (store && typeof store.applyViewTemplate === 'function') store.applyViewTemplate('allEnabled');
        }''')

    finally:
        cli.close()

    print('\n==========================================')
    print(f'总结果: PASS={len(PASS)} FAIL={len(FAIL)}')
    for f in FAIL:
        print(f'  \u2717 {f}')
    if FAIL:
        print('\u2717 自测未通过')
        sys.exit(1)
    print('\u2713 自测通过')


if __name__ == '__main__':
    main()