# -*- coding: utf-8 -*-
"""
拖拽类回归 — 拖拽调整分组后, 后续拖拽任何节点仍应可用.

[背景/复现] 用户反馈: "拖拽调整分组后, 后续继续拖拽任何节点都拖拽不了了"。
根因 (2026-08-19 定位):
  drop 触发 emitUpdate() → 面板 v-for 重建 → 拖拽源 DOM 被移除 →
  浏览器不再派发 dragend → draggingGroup 卡 true → 顶层放置区常显、
  (在 v-if 移除前) 后续拖拽 dragstart 被判定为"仍在拖拽", 拖拽失效。
修复: LayoutControlPanel 兜底监听 window 级 drop/dragend, 拖放结束可靠复位 draggingGroup。

[断言]
  - t1: 初始放置区隐藏 (drag-before 不占用空间)
  - t2: 拖拽开始 (dragstart) → 放置区出现
  - t3: drop (重建面板, 不发 dragend) → 放置区复位隐藏 (修复点)
  - t4: 再次拖拽任一节点 (dragstart) → 放置区再次出现 (拖拽仍可用)
  - t5: 页面无 JS 运行时错误
"""
import time

import pytest

from conftest import (row_titles, drop_zone_visible, dragstart_group, drop_group,
                      group_tree, children_titles, drag_reorder_real, drag_make_child)

pytestmark = pytest.mark.e2e


def test_drag_after_group_reorder_still_works(chart_page, panel):
    page = chart_page['page']

    # 前置: 面板有可拖拽行
    titles = row_titles(page)
    assert len(titles) >= 2, f'面板应至少 2 个分组行, 实际: {titles}'
    src = next((t for t in titles if t and t != '(no title)'), None)
    dst = next((t for t in titles if t and t != src and t != '(no title)'), None)
    assert src and dst, f'需两个有效分组行: {titles}'

    # t1: 初始放置区隐藏
    assert not drop_zone_visible(page), '初始放置区应隐藏'

    # t2: dragstart → 放置区出现
    assert dragstart_group(page, src), f'dragstart 派发失败 src={src}'
    page.wait_for_timeout(300)
    assert drop_zone_visible(page), 'dragstart 后放置区应出现'

    # t3: drop (触发 emitUpdate → 面板重建, 不派发 dragend) → 放置区复位隐藏
    assert drop_group(page, src, dst), f'drop 派发失败 src={src} dst={dst}'
    page.wait_for_timeout(1200)
    assert not drop_zone_visible(page), 'drop 后面板重建, 放置区应复位隐藏 (修复点)'

    # t4: 再次拖拽 → 仍可用 (dragstart 再次生效)
    assert dragstart_group(page, src), f'二次 dragstart 派发失败 src={src}'
    page.wait_for_timeout(300)
    assert drop_zone_visible(page), '再次拖拽 (dragstart) 放置区应再次出现, 证明拖拽仍可用'
    # 复位 (触发 window drop → 归位), 避免影响后续用例
    page.evaluate("() => window.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true }))")
    page.wait_for_timeout(300)
    assert not drop_zone_visible(page), '拖放结束后放置区应复位隐藏'

    # t5: 页面无 JS 运行时错误
    page.wait_for_timeout(500)
    assert not chart_page['errors'], f'出现 JS 运行时错误: {chart_page["errors"][:5]}'


def test_group_parentid_synced_and_reorder_works(chart_page, panel):
    """修复: 自动分组树 parentId 必须与 children 层级一致, 否则同级拖拽重排失效.

    [根因 2026-08-19] businessObjectAutoGrouper/layoutPanelAdapter 构建的分组树
    children 有层级但各节点 parentId 恒为 null → handleRowDrop 判定
    data.parentId===props.group.parentId 全 null 相等 → 走 reorder, 但
    handleReorderGroups 用 parentId 定位兄弟数组时在根数组找不到嵌套分组 → 静默 no-op.
    修复: 面板消费点统一 syncGroupParentIds.
    """
    page = chart_page['page']

    # t1: 分组树 parentId 与深度层级一致 (SD 的 parent = D_SCM, SM 的 parent = SD_SCP)
    tree = group_tree(page)
    by_title = {g['title']: g for g in tree}
    assert '供应链云' in by_title and '供应链计划' in by_title and '需求计划' in by_title, \
        f'缺少核心分组: {list(by_title.keys())[:8]}'
    scm = by_title['供应链云']
    scp = by_title['供应链计划']
    dp = by_title['需求计划']
    assert scp['parentId'] == scm['id'], f'供应链计划.parentId 应为 D_SCM, 实际 {scp["parentId"]}'
    assert dp['parentId'] == scp['id'], f'需求计划.parentId 应为 SD_SCP, 实际 {dp["parentId"]}'

    # t2: 同级拖拽重排真实生效 (需求计划 → 供应计划, 应在 SD_SCP.children 内换序)
    before = children_titles(page, scp['id'])
    assert '需求计划' in before and '供应计划' in before, f'SD_SCP children 缺分组: {before}'
    assert drag_reorder_real(page, '需求计划', '供应计划'), 'drag_reorder 派发失败'
    page.wait_for_timeout(1200)
    after = children_titles(page, scp['id'])
    # 需求计划应移到供应计划之后 (被放到目标位置末尾)
    assert '需求计划' in after
    assert before.index('需求计划') < after.index('需求计划'), \
        f'同级重排未生效: before={before} after={after}'
    # 其他分组相对顺序保持
    others_before = [t for t in before if t not in ('需求计划',)]
    others_after = [t for t in after if t not in ('需求计划',)]
    assert others_before == others_after, f'其他分组相对顺序被破坏: {others_before} vs {others_after}'

    # t3: 页面无 JS 运行时错误
    page.wait_for_timeout(300)
    assert not chart_page['errors'], f'出现 JS 运行时错误: {chart_page["errors"][:5]}'


def test_new_group_drag_to_left_becomes_child(chart_page, panel):
    """修复: 两个根级自定义分组, 拖一个到另一个「左侧区」应成为子分组 (move-group).

    [根因 2026-08-20] handleRowDrop 对两个根级分组(parentId 同为 null)永远判定
    data.parentId===props.group.parentId → 只走 reorder-groups(重排), 无法拖入成为子分组.
    修复: 拖到目标行左侧区(<35% 宽) → move-group(成为子分组); 右侧 → reorder(重排).
    """
    from conftest import drag_make_child
    page = chart_page['page']

    # 点击两次"新增" → 两个根级自定义分组 (都是 parentId=null, 无 children)
    page.evaluate("""()=>{
        const btn = Array.from(document.querySelectorAll('button')).find(b => (b.textContent||'').includes('新增'))
        if (btn) btn.click()
    }""")
    page.wait_for_timeout(400)
    page.evaluate("""()=>{
        const btn = Array.from(document.querySelectorAll('button')).find(b => (b.textContent||'').includes('新增'))
        if (btn) btn.click()
    }""")
    page.wait_for_timeout(1000)

    # 记录新增前的根级分组 (新增分组顶到列表最前)
    titles = row_titles(page)
    tree = group_tree(page)
    custom = [g for g in tree if g['groupType'] == 'custom' and g['depth'] == 0]
    assert len(custom) >= 2, f'应有至少 2 个根级自定义分组, 实际: {len(custom)}'
    g1, g2 = custom[0], custom[1]
    assert g1['parentId'] is None and g2['parentId'] is None, '根级自定义分组 parentId 应为 None'

    # 拖 g1 到 g2 左侧区 → 成为 g2 的子分组
    assert drag_make_child(page, g1['title'], g2['title']), 'drag_make_child 派发失败'
    page.wait_for_timeout(1200)

    # 断言 g1 现在是 g2 的 children
    after_tree = group_tree(page)
    g2_after = next(g for g in after_tree if g['title'] == g2['title'])
    g1_after = next(g for g in after_tree if g['title'] == g1['title'])
    assert g1_after['parentId'] == g2['id'], \
        f'拖到左侧区后 g1({g1["title"]}) 应成为 g2({g2["title"]}) 的子分组, 实际 parentId={g1_after["parentId"]}'

    # 页面无 JS 错误
    page.wait_for_timeout(300)
    assert not chart_page['errors'], f'出现 JS 运行时错误: {chart_page["errors"][:5]}'