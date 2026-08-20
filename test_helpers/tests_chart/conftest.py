# -*- coding: utf-8 -*-
"""
tests_chart 共享 fixture — 图表配置/展示模块回归套件 (收敛一次性 diag_* 脚本).

[目的] 后续图表模块持续迭代, 以「回归 + 问题排查」为主要目的:
  - 共享打开 SCP 图表 + 展开面板的 fixture, 避免每个回归文件重复 setup.
  - 提供 window 级 error collector, 统一断言页面无运行时报错.

[运行] (需前端 3004 + 后端 3010 运行中)
  python -m pytest test_helpers/tests_chart -m e2e -q

[约定]
  - 标准场景: SCP (供应链计划子领域, ~30 BO) — 严禁全量加载 (效率铁律).
  - 真实浏览器交互优先用 page.mouse / Playwright 原生事件; HTML5 拖拽在 headless
    下用 DispatchEvent+dragstart/drop 模拟 (与 _diag_drag_broken 口径一致, 稳定可跑).
"""
import json
import sys
import time

import pytest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.env_preflight import preflight, FRONTEND_URL
from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.scenario import get_scenario_url

pytestmark = pytest.mark.e2e


@pytest.fixture(scope='module')
def chart_page():
    """打开 SCP 图表 (模块级, 多个用例复用同一会话, 避免重复全量渲染)."""
    preflight(require_backend=True)
    cli = PlaywrightCLI(headless=True)
    page = cli._ensure_browser()

    # 集中收集页面运行时报错, 供用例断言 "无 JS 异常"
    page_errors = []
    page.on('pageerror', lambda e: page_errors.append(str(e)[:300]))

    # 打开 SCP 图表视图
    page.goto(f"{FRONTEND_URL}/api/v1/auth/dev-login?username=admin",
              wait_until='domcontentloaded', timeout=15000)
    page.goto(get_scenario_url('scp'), wait_until='domcontentloaded', timeout=20000)

    # 等 store 就绪 (与既有 _diag_drag_broken 口径一致)
    for i in range(45):
        time.sleep(1)
        if page.evaluate("() => !!window.__archPage?.expandState"):
            break

    yield {'page': page, 'errors': page_errors}
    cli.close()


@pytest.fixture()
def panel(chart_page):
    """展开"图表设置"面板, 返回 page (供拖拽/分组交互)."""
    d = chart_page
    page = d['page']
    page.evaluate("""()=>{
        const heads = Array.from(document.querySelectorAll('.collapsible-panel__header'))
        const t = heads.find(h => h.textContent.includes('图表设置'))
        if (t) t.click()
    }""")
    page.wait_for_timeout(1500)
    return page


# ---- 图表面板交互辅助 (收敛含 _diag_drag_broken 的一次性逻辑) ----

def row_titles(page):
    """面板分组行标题列表."""
    return page.evaluate("""() =>
        Array.from(document.querySelectorAll('.lgn-row')).map(r => {
            const t = r.querySelector('.lgn-title-text')
            return t ? (t.textContent || '').trim() : '(no title)'
        })""")


def drop_zone_visible(page):
    """顶层放置区 (拖分组到此提升为顶层) 是否真正可见.
    [DRAG-FIX 2026-08-19] 放置区改为始终渲染 + CSS class 显隐 (避免 dragstart 同步
    增删 DOM 节点打断原生拖拽) — 判断必须用 CSS 可见性, 不能只看 DOM 存在."""
    return page.evaluate("""() => {
        const z = document.querySelector('.lgn-top-drop-zone')
        if (!z) return false
        const cs = getComputedStyle(z)
        return cs.display !== 'none' && cs.visibility !== 'hidden' &&
               z.getBoundingClientRect().height > 0
    }""")


def dragstart_group(page, title_part):
    """在指定标题分组行派发 dragstart (HTML5 拖拽起点), 返回是否派发成功."""
    return page.evaluate("""(part) => {
        const rows = Array.from(document.querySelectorAll('.lgn-row'))
        const row = rows.find(r => (r.querySelector('.lgn-title-text')||{}).textContent?.includes(part))
        if (!row) return false
        const dt = new DataTransfer()
        const title = (row.querySelector('.lgn-title-text')||{}).textContent.trim()
        dt.setData('text/plain', JSON.stringify({
            type: 'group', groupId: title, sourceGroupId: title, sourceIndex: 0, parentId: null
        }))
        row.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
        return true
    }""", title_part)


def drop_group(page, src_title_part, dst_title_part):
    """对目标分组行派发 drop (同层/跨层移动), 触发 emitUpdate → 面板重建."""
    return page.evaluate("""({src, dst}) => {
        const rows = Array.from(document.querySelectorAll('.lgn-row'))
        const row = rows.find(r => (r.querySelector('.lgn-title-text')||{}).textContent?.includes(dst))
        if (!row) return false
        const dt = new DataTransfer()
        dt.setData('text/plain', JSON.stringify({
            type: 'group', groupId: src, sourceGroupId: src, sourceIndex: 0, parentId: null
        }))
        row.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
        row.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
        return true
    }""", {'src': src_title_part, 'dst': dst_title_part})


def group_tree(page):
    """面板分组树扁平化: [{title, id, depth, parentId, groupType, childCount}]."""
    return page.evaluate("""() => {
        const cfg = window.__archPage?.storeProxy?.layoutControlConfig
        const walk = (list, depth, parentId, acc) => {
            (list||[]).forEach(g => {
                acc.push({ title: g.title, id: g.id, depth, parentId: g.parentId,
                           groupType: g.groupType, childCount: (g.children||[]).length })
                walk(g.children, depth+1, g.id, acc)
            })
        }
        const acc = []
        walk(cfg?.groups, 0, null, acc)
        return acc
    }""")


def children_titles(page, group_id):
    """某分组 children 的标题顺序 (断言同级重排生效)."""
    return page.evaluate("""(pid) => {
        const cfg = window.__archPage?.storeProxy?.layoutControlConfig
        const flat = []
        const walk = (l) => (l||[]).forEach(g => { flat.push(g); walk(g.children); walk(g.containers); })
        walk(cfg?.groups)
        const g = flat.find(x => x.id === pid)
        return (g?.children||[]).map(c => c.title)
    }""", group_id)


def drag_reorder_real(page, src_title, dst_title):
    """用真实 parentId 做 dragstart→drop, 触发真实 Vue 拖拽处理器 (同级重排).
    返回: 是否派发成功."""
    info = page.evaluate("""({src, dst}) => {
        const cfg = window.__archPage?.storeProxy?.layoutControlConfig
        const flat = []
        const walk = (l) => (l||[]).forEach(g => { flat.push(g); walk(g.children); walk(g.containers); })
        walk(cfg?.groups)
        const s = flat.find(g => g.title === src)
        const d = flat.find(g => g.title === dst)
        if (!s || !d) return null
        return { srcId: s.id, dstId: d.id, srcParent: s.parentId }
    }""", {'src': src_title, 'dst': dst_title})
    if not info:
        return False
    return page.evaluate("""({info, src, dst}) => {
        const rows = Array.from(document.querySelectorAll('.lgn-row'))
        const srcRow = rows.find(r => (r.querySelector('.lgn-title-text')||{}).textContent?.trim() === src)
        const dstRow = rows.find(r => (r.querySelector('.lgn-title-text')||{}).textContent?.trim() === dst)
        if (!srcRow || !dstRow) return false
        const dt = new DataTransfer()
        dt.setData('text/plain', JSON.stringify({
            type: 'group', groupId: info.srcId, sourceGroupId: info.srcId,
            sourceIndex: 0, parentId: info.srcParent
        }))
        srcRow.dispatchEvent(new DragEvent('dragstart', { bubbles:true, dataTransfer: dt }))
        dstRow.dispatchEvent(new DragEvent('dragover', { bubbles:true, cancelable:true, dataTransfer: dt }))
        dstRow.dispatchEvent(new DragEvent('drop', { bubbles:true, cancelable:true, dataTransfer: dt }))
        return true
    }""", {'info': info, 'src': src_title, 'dst': dst_title})


def drag_make_child(page, src_title, dst_title):
    """拖 src 分组到 dst 分组的「左侧区」→ 成为其子分组 (move-group).
    依赖 handleRowDrop 基于 clientX 相对行左侧 <35% 判定子分组."""
    info = page.evaluate("""({src, dst}) => {
        const cfg = window.__archPage?.storeProxy?.layoutControlConfig
        const flat = []
        const walk = (l) => (l||[]).forEach(g => { flat.push(g); walk(g.children); walk(g.containers); })
        walk(cfg?.groups)
        const s = flat.find(g => g.title === src)
        const d = flat.find(g => g.title === dst)
        if (!s || !d) return null
        return { srcId: s.id, dstId: d.id, srcParent: s.parentId }
    }""", {'src': src_title, 'dst': dst_title})
    if not info:
        return False
    return page.evaluate("""({info, src, dst}) => {
        const rows = Array.from(document.querySelectorAll('.lgn-row'))
        const srcRow = rows.find(r => (r.querySelector('.lgn-title-text')||{}).textContent?.trim() === src)
        const dstRow = rows.find(r => (r.querySelector('.lgn-title-text')||{}).textContent?.trim() === dst)
        if (!srcRow || !dstRow) return false
        const r = dstRow.getBoundingClientRect()
        // 拖到目标行左侧区 (clientX = 行左 + 15% 宽) → 触发 move-group
        const clientX = r.left + r.width * 0.15
        const clientY = r.top + r.height / 2
        const dt = new DataTransfer()
        dt.setData('text/plain', JSON.stringify({
            type: 'group', groupId: info.srcId, sourceGroupId: info.srcId,
            sourceIndex: 0, parentId: info.srcParent
        }))
        srcRow.dispatchEvent(new DragEvent('dragstart', { bubbles:true, dataTransfer: dt }))
        dstRow.dispatchEvent(new DragEvent('dragover', { bubbles:true, cancelable:true, dataTransfer: dt, clientX, clientY }))
        dstRow.dispatchEvent(new DragEvent('drop', { bubbles:true, cancelable:true, dataTransfer: dt, clientX, clientY }))
        return true
    }""", {'info': info, 'src': src_title, 'dst': dst_title})