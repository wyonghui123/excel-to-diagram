"""
test_chart_regression.py - 图表展示模块交互回归 (E2E)
================================================================
覆盖 2026-08-13~14 的修复:
  - Fix E (ELK 系统分组误判): 隐藏项目云 → 采购供应 BO 保持可见, 取消隐藏恢复
  - Fix B (双击不折叠): 双击已展开容器不执行折叠
  - Fix A (右键临时高亮): 右击容器出现选中高亮, 点击其他位置清除
  - Fix C (右键菜单结构): 全局菜单小标题+一级项; 对象菜单折叠/展开放首位

依赖: 前端(3004) + 后端(3010) 运行中 (dev-login).
运行: python -m pytest test_helpers/tests_chart/test_chart_regression.py -v -m e2e
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pytest
from test_helpers.env_preflight import preflight
from test_helpers.scenario_runner import ScenarioRunner, snapshot_chart, diff_snapshots

pytestmark = pytest.mark.e2e


@pytest.fixture(scope='module')
def runner():
    preflight(require_backend=True)
    r = ScenarioRunner(scenario='mm-cross-domain')
    r.open()
    # 一次性展开到业务对象 (后续测试共享此状态, 避免重复全量渲染)
    r.page.evaluate("() => window.__archPage.debug.setExpandLevel('businessObject')")
    r.wait_render_stable(clear_marker=True)
    yield r
    r.close()


def mm_collapsed(page):
    return page.evaluate("""() => {
      const cfg = window.__archPage.storeProxy.layoutControlConfig
      const flat = []
      const walk = (l) => (l||[]).forEach(g => { if(!g) return; flat.push(g); walk(g.children); walk(g.containers); })
      walk(cfg.groups)
      const mm = flat.find(g => (g.elementCode||g.id) === 'MM')
      return mm ? mm.collapsed : null
    }""")


# ---------------------------------------------------------------
# Fix E: ELK 系统分组误判 (2026-08-14 最核心回归)
# ---------------------------------------------------------------
def test_elk_hide_unhide_mm_bo_visible(runner):
    """隐藏/取消隐藏项目云(PM) 均不得影响采购供应(MM) 的 BO 可见性."""
    page = runner.page
    before = snapshot_chart(page, watch=['MM', 'PM'])
    assert before['groupBo']['MM']['boCount'] > 0, '采购供应 BO 未渲染'

    # 隐藏 PM (增量, 同步 display:none, 短等待即可)
    page.evaluate("() => window.__archPage.debug.setGroupVisible('PM', false)")
    page.wait_for_timeout(800)
    after_hide = snapshot_chart(page, watch=['MM', 'PM'])
    d = diff_snapshots(before, after_hide, watch=['MM'])
    assert not d['watch']['MM']['missing'] and not d['watch']['MM']['hidden'], \
        f"隐藏 PM 后采购供应 BO 不应消失: {d['watch']['MM']}"

    # 取消隐藏 PM
    page.evaluate("() => window.__archPage.debug.setGroupVisible('PM', true)")
    page.wait_for_timeout(800)
    after_unhide = snapshot_chart(page, watch=['MM', 'PM'])
    d2 = diff_snapshots(before, after_unhide, watch=['MM'])
    assert not d2['watch']['MM']['missing'] and not d2['watch']['MM']['hidden'], \
        f"取消隐藏 PM 后采购供应 BO 仍应恢复: {d2['watch']['MM']}"

    # PM 自身应被隐藏
    assert after_hide['groupBo']['PM']['boCount'] > 0
    pm_bo = after_hide['groupBo']['PM']['boNodes']
    pm_hidden = [c for c, disp in pm_bo.items() if disp == 'none']
    assert len(pm_hidden) == after_hide['groupBo']['PM']['boCount'], \
        f'PM 自身 BO 应被隐藏: hidden={len(pm_hidden)}/{after_hide["groupBo"]["PM"]["boCount"]}'


# ---------------------------------------------------------------
# Fix B: 双击已展开容器不折叠 (仅右键可折叠)
# ---------------------------------------------------------------
def test_dblclick_expanded_does_not_collapse(runner):
    page = runner.page
    assert mm_collapsed(page) is False, '前置: MM 应为展开态'
    collapsed_before = mm_collapsed(page)

    # 双击已展开的 MM 容器 (用属性选择器, 容器 wrapper 可能 id 为空)
    page.evaluate("() => window.__archPage.debug.testDblClick('g.cluster[data-container-code=\"MM\"]')")
    page.wait_for_timeout(1500)

    collapsed_after = mm_collapsed(page)
    assert collapsed_after == collapsed_before, \
        f'双击已展开容器不应折叠: before={collapsed_before} after={collapsed_after}'


# ---------------------------------------------------------------
# Fix A: 右键临时高亮 (生命周期)
# ---------------------------------------------------------------
def test_rightclick_temporary_highlight(runner):
    page = runner.page
    # 右键一个容器 → 出现 annotation-highlighted
    page.evaluate("() => window.__archPage.debug.testRightClick('g.cluster[data-container-code=\"MM\"]')")
    page.wait_for_timeout(500)
    hl = page.evaluate("() => document.querySelectorAll('.mermaid-content .annotation-highlighted').length")
    assert hl >= 1, '右键容器后应出现选中高亮'

    # 点击图表其他位置 → 高亮清除 (菜单关闭)
    page.evaluate("""() => {
      const ev = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: 5, clientY: 5 })
      document.dispatchEvent(ev)
    }""")
    page.wait_for_timeout(500)
    hl_after = page.evaluate("() => document.querySelectorAll('.mermaid-content .annotation-highlighted').length")
    assert hl_after == 0, f'点击其他位置后右键高亮应清除: {hl_after}'


# ---------------------------------------------------------------
# Fix C: 右键菜单结构
# ---------------------------------------------------------------
def test_context_menu_structure(runner):
    page = runner.page

    def menu_items():
        return page.evaluate("""() => {
          const menu = document.querySelector('.mermaid-ctx-menu')
          if (!menu) return null
          const out = { headers: [], items: [] }
          menu.querySelectorAll('.ctx-menu-header-sm, .ctx-menu-header, .ctx-menu-item').forEach(el => {
            const cls = el.className || ''
            const label = (el.textContent || '').trim()
            if (cls.includes('ctx-menu-header-sm') || cls.includes('ctx-menu-header')) out.headers.push(label)
            else out.items.push(label)
          })
          return out
        }""")

    # 1) 对象菜单: 折叠/展开在前, 关系高亮在后
    page.evaluate("() => window.__archPage.debug.testRightClick('g.cluster[data-container-code=\"MM\"]')")
    page.wait_for_timeout(500)
    obj_menu = menu_items()
    assert obj_menu is not None, '对象右键菜单未出现'
    assert obj_menu['items'][0] == '折叠', f'对象菜单首项应为折叠: {obj_menu["items"]}'
    assert obj_menu['items'][-1] == '关系高亮', f'对象菜单末项应为关系高亮: {obj_menu["items"]}'
    assert '展开到服务模块' in obj_menu['items'] and '展开到业务对象' in obj_menu['items']

    # 2) 全局菜单: 小标题「展开层级」+ 4 个一级展开项
    #    (在 svg 根元素上派发 contextmenu → identifyGroupFromSvg 未命中分组 → 全局菜单)
    page.evaluate("""() => {
      const svg = document.querySelector('.mermaid-content svg')
      const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 100, clientY: 100, button: 2 })
      svg.dispatchEvent(ev)
    }""")
    page.wait_for_timeout(500)
    global_menu = menu_items()
    assert global_menu is not None, '全局右键菜单未出现'
    assert '展开层级' in global_menu['headers'], f'全局菜单应有「展开层级」小标题: {global_menu["headers"]}'
    for expect in ['展开到领域', '展开到子领域', '展开到服务模块', '展开到业务对象']:
        assert expect in global_menu['items'], f'全局菜单缺少 {expect}: {global_menu["items"]}'
