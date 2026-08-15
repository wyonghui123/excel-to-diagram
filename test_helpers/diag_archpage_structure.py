"""快速诊断 window.__archPage 结构与 debugLayout 快照 keys (定位 probe 注入断言失败根因)."""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.env_preflight import FRONTEND_URL, preflight

preflight(require_backend=True)
cli = PlaywrightCLI(headless=True)
try:
    page = cli._ensure_browser()
    page.set_default_timeout(40000)
    page.goto(f'{FRONTEND_URL}/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded', timeout=15000)
    time.sleep(1)
    page.goto(f'{FRONTEND_URL}/system/archdata?preset=scp&mode=debug', wait_until='domcontentloaded', timeout=15000)
    page.wait_for_function("() => { const svgs = document.querySelectorAll('svg'); for (const s of svgs) if ((s.textContent||'').length > 200) return true; return false; }", timeout=90000)
    page.wait_for_function("() => { const a=document.querySelector('#app')?.__vue_app__; const p=a?.config?.globalProperties?.$pinia; const s=p?._s?.get('diagramConfig'); return !!(s && s.layoutControlConfig); }", timeout=20000)

    # 展开到业务对象层级 (与 probe 一致)
    page.evaluate("() => window.__archPage && window.__archPage.debug && window.__archPage.debug.setExpandLevel('businessObject')")
    time.sleep(2)

    info = page.evaluate('''() => {
      const ap = window.__archPage || {};
      const out = { keys: Object.keys(ap), debugType: typeof ap.debug, debugKeys: ap.debug ? Object.keys(ap.debug) : null };
      if (ap.debugLayout) {
        out.dblKeys = Object.keys(ap.debugLayout);
        for (const k of Object.keys(ap.debugLayout)) {
          const v = ap.debugLayout[k];
          if (Array.isArray(v)) out[k + '_len'] = v.length;
          else if (v && typeof v === 'object') out[k + '_keys'] = Object.keys(v).slice(0,10);
          else out[k + '_val'] = String(v).slice(0,80);
        }
      } else {
        out.dblMissing = true;
      }
      // 渲染树: store.layoutControlConfig.groups 里是否有 _elkGroup 字段
      try {
        const pinia = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
        const store = pinia._s.get('diagramConfig');
        const lcc = store.layoutControlConfig || {};
        let elkCount = 0, smCount = 0, sample = [];
        function walk(items, depth) {
          for (const g of items || []) {
            if (!g) continue;
            if (g._elkGroup) { elkCount++; if (sample.length < 5) sample.push({ title: g.title, elk: g._elkGroup, enabled: g.enabled, visible: g.visible }); }
            if (g.groupType === 'serviceModule') smCount++;
            walk(g.children, depth + 1);
          }
        }
        walk(lcc.groups, 0);
        out.panel = { lccGroups: (lcc.groups||[]).length, elkCount, smCount, sample };
      } catch (e) { out.panel = { err: String(e) }; }
      return out;
    }''')
    print(json.dumps(info, ensure_ascii=False, indent=2))
finally:
    cli.close()
