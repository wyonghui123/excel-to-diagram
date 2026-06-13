# 7 大交互细节 - 测试覆盖专项分析

> **分析日期**: 2026-06-11
> **触发**: 用户反馈"annotation/连线点击/高亮联动/tooltip/端点箭头/legend/容器节点文字格式"这 7 个细节, 问"是否有覆盖"
> **结论先行**: **全部未覆盖**. 0 个测试, 0 个断言

---

## 0. TL;DR

| # | 用户问的细节 | 覆盖? | 关键文件 | 风险等级 |
|---|------------|-------|---------|---------|
| 1 | annotation 点击联动 | ❌ 0 测试 | [annotationOverlay.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/annotation/annotationOverlay.js) | **高** |
| 2 | 连线点击高亮联动 | ❌ 0 测试 | [useTooltip.js:262-287](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/tooltip/useTooltip.js#L262-L287) | **高** |
| 3 | 连线 tooltip 内容完整性 | ❌ 0 测试 | [useTooltip.js:46-58 formatTooltipText](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/tooltip/useTooltip.js#L46-L58) | **高** |
| 4 | 连线端点和箭头在节点边 | ❌ 0 测试 | mermaid.layout + [useTooltip.js:398-441 拖尾圆点](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/tooltip/useTooltip.js#L398-L441) | **中** |
| 5 | legend 相关 | ❌ 0 测试 | [useSvgProcessor.js:188-269](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/renderer/useSvgProcessor.js#L188-L269) | **高** |
| 6 | 容器标题文字格式完整性 | ❌ 0 测试 | [formatContainerTitle.js](file:///d:/filework/excel-to-diagram/src/utils/formatContainerTitle.js) | **中** |
| 7 | 节点文字格式与完整性 | ❌ 0 测试 | [syntax/* + CSS](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css) | **中** |

**总分: 0/7 (0%) 覆盖**. 这 7 个细节**全部没有针对性测试**, 任何改动都没有回归保护.

---

## 1. Annotation 点击 + 联动 (❌ 完全未覆盖)

### 1.1 涉及功能

```javascript
// annotationOverlay.js:276-343 bindAnnotationInteraction
container.querySelectorAll('.annotation-item').forEach(item => {
  item.addEventListener('click', () => {
    const targetId = item.getAttribute('data-target-id');
    const ann = annotationMap.get(targetId);
    const targetType = ann ? ann.targetType : null;  // 'container' / 'node' / 'relation'
    if (targetId && targetType) {
      highlightTargetElement(svg, targetId, targetType);  // ← 联动核心
      item.classList.add('annotation-item-selected');
      item.style.background = 'rgba(0, 0, 0, 0.05)';
    }
  });

  item.addEventListener('mouseenter', () => {
    hoverTargetElement(svg, targetId, true);  // hover 联动
  });
});
```

### 1.2 联动逻辑 (highlightTargetElement)

| 目标类型 | 联动效果 | 视觉变化 |
|---------|---------|---------|
| **relation** (边线) | 找 `data-relation-code=...` 或 `.edgeLabel` (text includes targetId) | 加 `.annotation-highlighted` class + drop-shadow 红光 |
| **container** (容器) | 找 `data-container-code=...` 或 `.subgraph/.cluster` (label includes targetId) | 加 class + 容器描边变红 |
| **node** (节点) | 找 `data-code=...` 或 `.node` (label includes targetId) | 加 class + 节点 rect 红色 drop-shadow |

### 1.3 应该有的测试 (但没有)

```python
# tests/e2e/test_annotation_interaction.py - 应该但没有
def test_annotation_node_click_highlights_node(self):
    """Annotation 节点备注: 点击 -> 节点高亮 (红色 drop-shadow)"""
    # 1) 注入有 annotation 的测试数据
    arch_data = create_arch_data(
        nodes=5,
        relations=3,
        annotations=[{
            'targetType': 'node',
            'targetId': 'BO_001',
            'content': '关键节点',
        }]
    )
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)  # 等渲染 + annotation 面板
    
    # 2) 验证 annotation 面板存在
    annotations = chart_page.query_selector_all('.annotation-item')
    assert len(annotations) == 1
    
    # 3) 点击 annotation
    annotations[0].click()
    chart_page.wait_for_timeout(500)
    
    # 4) 验证目标节点被高亮
    highlighted = chart_page.query_selector_all('.annotation-highlighted')
    assert len(highlighted) == 1
    
    # 5) 验证节点 rect 有 drop-shadow filter
    rect_filter = chart_page.evaluate("""(highlighted) => {
        const rect = highlighted[0].querySelector('rect');
        return rect ? rect.style.filter : '';
    }""", [highlighted])
    assert 'drop-shadow' in rect_filter

def test_annotation_relation_click_highlights_edge(self):
    """Annotation 关系备注: 点击 -> 边线高亮"""
    # ... 同上, targetType='relation'
    # 验证 .annotation-highlighted 应用到 edgeLabel / flowPath

def test_annotation_container_click_highlights_container(self):
    """Annotation 容器备注: 点击 -> 容器高亮"""
    # ... 同上, targetType='container'
    # 验证 .annotation-highlighted 应用到 .subgraph/.cluster

def test_annotation_hover_triggers_hover_state(self):
    """Annotation hover 触发 hoverTargetElement"""
    # mouseenter -> drop-shadow 出现 (但与 click 高亮不同, 是 hover 而非 selected)
    
def test_annotation_click_outside_clears(self):
    """点击 annotation 面板外 -> clearAllHighlights"""
    # svg.click() -> 所有 .annotation-highlighted 移除
```

### 1.4 风险

- **高风险**: 任何 annotation 改动都没有回归保护
- 已知可能的问题:
  - `formatContainerTitle` 改了格式, 但 `targetId` 匹配用 `text.includes(targetId)`, 容器标题加 `\n` 后 `includes` 仍能匹配 (但需要测)
  - `data-relation-code` / `data-container-code` / `data-code` 属性在 mermaid 渲染时是否被注入? 这是隐式依赖

---

## 2. 连线点击高亮 + 联动 (❌ 完全未覆盖)

### 2.1 涉及功能

```javascript
// useTooltip.js:262-287 setupPathEvents 的 click 处理
path.addEventListener('click', (e) => {
  e.stopPropagation()
  selectedElements.path = null
  selectedElements.label = null
  selectedElements.sourceNode = null
  selectedElements.targetNode = null
  selectedElements.path = path  // ← 选中的 path

  const relation = pathToRelationMap.get(path)
  if (relation) {
    // 找对应的 label
    const correspondingLabel = Array.from(labels).find((label) => {
      const labelText = label.textContent || label.innerHTML
      return labelText.trim() === relation.relationCode
    })
    if (correspondingLabel) {
      selectedElements.label = correspondingLabel
    }
    // 联动: 高亮 source 和 target 节点
    highlightNode(svg, relation.source, 'source', selectedElements)
    highlightNode(svg, relation.target, 'target', selectedElements)
  }
})
```

### 2.2 联动效果

| 元素 | 视觉变化 |
|------|---------|
| 边线 (path) | `strokeWidth = '4px'` + `filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'` |
| source 节点 | `rect.stroke = '#FF6B6B'` + `strokeWidth = '4px'` + drop-shadow |
| target 节点 | 同上 |
| source/target label | `fontWeight = 'bold'` + `fontSize = '16px'` |

### 2.3 应该有的测试 (但没有)

```python
def test_edge_click_highlights_path(self):
    """点击连线: path 变粗 + drop-shadow"""
    # 1) 准备数据
    arch_data = create_arch_data(nodes=3, relations=1)
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)
    
    # 2) 找 path (注意: path 可能嵌套在 .edgePath 内)
    path = chart_page.query_selector('.mermaid-content .edgePath path')
    initial_stroke_width = path.get_attribute('stroke-width')
    
    # 3) 点击 path
    path.click()
    chart_page.wait_for_timeout(500)
    
    # 4) 验证 path 变粗
    new_stroke_width = path.get_attribute('stroke-width')
    assert float(new_stroke_width) > float(initial_stroke_width)
    # 应该是 4px
    assert new_stroke_width == '4'

def test_edge_click_highlights_source_and_target_nodes(self):
    """点击连线: 联动高亮 source + target 节点"""
    # ... 同上
    # 验证 2 个 .node 被高亮 (rect.stroke = '#FF6B6B')
    highlighted_rects = chart_page.evaluate("""(() => {
        return Array.from(document.querySelectorAll('.mermaid-content .node rect'))
            .filter(r => r.style.stroke === 'rgb(255, 107, 107)')
            .length;
    })()""")
    assert highlighted_rects == 2  # source + target

def test_edge_click_bolds_labels(self):
    """点击连线: source/target 节点 label 加粗 + 放大"""
    # ... 同上
    # 验证 2 个 .nodeLabel 的 fontWeight = bold

def test_edge_click_clears_previous_highlight(self):
    """点击新连线: 之前的高亮被清除"""
    # 1) 点击连线 1, 高亮节点 A->B
    # 2) 点击连线 2, 高亮节点 B->C
    # 3) 验证 A 不再高亮 (高亮从 A 移到 C)
    
def test_click_outside_edge_clears_highlight(self):
    """点击空白区域: 高亮清除"""
    # 1) 点击连线, 高亮
    # 2) 点击 SVG 空白
    # 3) 验证所有高亮清除 (rect.stroke 恢复原值)
```

### 2.4 风险

- **高风险**: 连线点击是核心交互功能
- 隐藏的 bug 风险:
  - `pathToRelationMap.get(path)`: 如果 mermaid 重渲染后 path 引用变了, 映射失效
  - `Array.from(labels).find(...)`: 标签文本匹配, 但 `label.textContent` 包含 trailing whitespace, `.trim()` 已处理 (但要测)
  - `selectedElements` 状态没清理, 多次点击会内存泄漏

---

## 3. 连线 Tooltip 内容完整性 (❌ 完全未覆盖)

### 3.1 涉及功能

```javascript
// useTooltip.js:46-58 formatTooltipText
const formatTooltipText = (relation) => {
  if (!relation) return '无关系说明'
  const relationCode = relation.relationCode || ''
  const relationDesc = relation.relationDesc || '无关系说明'
  const sourceName = relation.sourceName || ''
  const targetName = relation.targetName || ''
  const annotationContent = relation.annotationContent || ''

  let text = `${relationCode}\n${sourceName} → ${targetName}\n${relationDesc}`
  if (annotationContent) {
    text += `\n备注: ${annotationContent}`
  }
  return text
}
```

### 3.2 完整 tooltip 格式 (4-5 行)

```
REL_001                                    ← relationCode
订单管理 → 支付服务                          ← sourceName → targetName
订单创建后触发支付请求                        ← relationDesc
备注: 关键业务路径, 需重点关注                ← annotationContent (可选)
```

### 3.3 应该有的测试 (但没有)

```python
def test_edge_tooltip_full_content(self):
    """连线 tooltip 应包含 4-5 行完整内容"""
    arch_data = {
        'nodes': [
            {'code': 'BO_001', 'name': '订单管理'},
            {'code': 'BO_002', 'name': '支付服务'},
        ],
        'relationships': [{
            'relationCode': 'REL_001',
            'source': 'BO_001',
            'target': 'BO_002',
            'sourceName': '订单管理',
            'targetName': '支付服务',
            'relationDesc': '订单创建后触发支付请求',
            'annotationContent': '关键业务路径, 需重点关注',
        }]
    }
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)
    
    # 1) 找 path
    path = chart_page.query_selector('.mermaid-content .edgePath path')
    
    # 2) mouseenter
    path.hover()  # 等价于 mouseenter
    chart_page.wait_for_timeout(500)
    
    # 3) 验证 tooltip 显示且内容完整
    tooltip = chart_page.query_selector('#mermaid-tooltip')
    assert tooltip.is_visible()
    text = tooltip.inner_text()
    
    # 验证 4 个核心字段都在
    assert 'REL_001' in text
    assert '订单管理' in text and '支付服务' in text
    assert '订单创建后触发支付请求' in text
    assert '关键业务路径' in text  # 备注
    assert '备注' in text  # 备注前缀

def test_edge_tooltip_no_annotation(self):
    """连线 tooltip: 没有 annotationContent 时不显示 '备注' 行"""
    arch_data['relationships'][0].pop('annotationContent')
    # ... 同上
    text = tooltip.inner_text()
    assert '备注' not in text
    assert '订单创建后触发支付请求' in text  # 关系说明仍存在

def test_edge_tooltip_no_desc(self):
    """连线 tooltip: 没有 relationDesc 时显示 '无关系说明'"""
    arch_data['relationships'][0].pop('relationDesc')
    # ... 同上
    text = tooltip.inner_text()
    assert '无关系说明' in text

def test_edge_tooltip_no_source_or_target_name(self):
    """连线 tooltip: 缺 sourceName/targetName 时不报错"""
    # 验证 '无关系说明' 不会因空字符串变成 ' → \n无关系说明'

def test_edge_tooltip_position(self):
    """tooltip 位置: 在 path mouseenter 位置 + 10px 偏移"""
    # 1) 找到 path 的 bounding box
    # 2) 模拟 mouseenter (mouse.move 到 path 中心)
    # 3) 验证 tooltip.left / tooltip.top 在 mouse 位置 + 10px

def test_edge_tooltip_hides_on_mouseleave(self):
    """mouseout: tooltip 隐藏"""
    # 1) mouseenter -> 显示
    # 2) mousemove 到 SVG 外
    # 3) 验证 tooltip.style.visibility = 'hidden'

def test_edge_label_tooltip_same_as_path(self):
    """label hover 也应显示同样的 tooltip"""
    # 1) hover .edgeLabel (标签)
    # 2) 验证 tooltip 内容同 path hover
    # 3) 这两个应该有相同的 text (由 formatTooltipText 统一)
```

### 3.4 风险

- **高风险**: tooltip 是用户查看关系详细信息的唯一途径
- 隐藏 bug 风险:
  - `relationCode = ''` 时, tooltip 第 1 行是空行 (UI 不友好)
  - `\n` 换行符在 `<div>` 中可能不生效 (需 `white-space: pre-line`, CSS 已有, 但需测)
  - 多语言: 中文 + 英文混排的 tooltip 宽度可能超 300px (CSS `max-width: 300px` + `wordWrap: break-word`)

---

## 4. 连线端点和箭头在节点边 (❌ 完全未覆盖)

### 4.1 涉及功能

**Mermaid 内部 layout 引擎 (dagre/elk) 决定**:
- 边线 path 的 `d` 属性 (M 命令 + 曲线)
- 端点位置: 起点 = source 节点的某个边 (top/right/bottom/left), 终点 = target 节点的某个边
- 箭头 marker: `marker-end="..."` 引用 `<defs>` 里的 `<marker>`

**项目层 (useTooltip.js:290-447 addTrailingDottedLines)**:
- 拖尾虚线 (line from label center to edge endpoint)
- 拖尾圆点 (circle at edge endpoint)

### 4.2 应该有的测试 (但没有)

```python
def test_edge_endpoints_on_node_edges(self):
    """边线端点应在节点的 4 边之一 (top/right/bottom/left) 上"""
    arch_data = create_arch_data(nodes=2, relations=1)
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)
    
    # 1) 解析 path d 属性, 找起点 (M 后的第一对坐标)
    path_d = chart_page.evaluate("""(() => {
        const path = document.querySelector('.mermaid-content .edgePath path');
        return path ? path.getAttribute('d') : '';
    })()""")
    
    # 解析起点
    m = re.match(r'M\s*([\d.]+)\s*,?\s*([\d.]+)', path_d)
    start_x, start_y = float(m.group(1)), float(m.group(2))
    
    # 2) 找 source 节点的 bbox
    source_bbox = chart_page.evaluate("""(() => {
        const node = document.querySelector('.mermaid-content .node');  // 第一个节点 = source
        if (!node) return null;
        const rect = node.querySelector('rect');
        if (!rect) return null;
        return {
            x: parseFloat(rect.getAttribute('x') || 0),
            y: parseFloat(rect.getAttribute('y') || 0),
            width: parseFloat(rect.getAttribute('width') || 0),
            height: parseFloat(rect.getAttribute('height') || 0)
        };
    })()""")
    
    # 3) 验证起点在 source 的 4 边之一 (容差 2px)
    tolerance = 2
    on_left = abs(start_x - source_bbox['x']) < tolerance
    on_right = abs(start_x - (source_bbox['x'] + source_bbox['width'])) < tolerance
    on_top = abs(start_y - source_bbox['y']) < tolerance
    on_bottom = abs(start_y - (source_bbox['y'] + source_bbox['height'])) < tolerance
    
    # 同时在节点范围内
    in_x = source_bbox['x'] <= start_x <= source_bbox['x'] + source_bbox['width']
    in_y = source_bbox['y'] <= start_y <= source_bbox['y'] + source_bbox['height']
    
    is_on_edge = (on_left or on_right or on_top or on_bottom) and in_x and in_y
    assert is_on_edge, f"起点 ({start_x}, {start_y}) 不在 source 节点 {source_bbox} 的边上"

def test_edge_target_endpoints_on_node_edges(self):
    """边线终点应在 target 节点的 4 边之一上"""
    # 解析 path d 找 L 命令的最后一对坐标
    # ... 同上

def test_edge_has_arrow_marker(self):
    """边线应有 marker-end 箭头"""
    marker_end = chart_page.evaluate("""(() => {
        const path = document.querySelector('.mermaid-content .edgePath path');
        return path ? path.getAttribute('marker-end') : '';
    })()""")
    assert marker_end and 'url(' in marker_end  # 引用 <defs> 里的 marker

def test_trailing_dotted_line_exists(self):
    """拖尾虚线: data-trailing-line 元素存在"""
    trailing = chart_page.query_selector_all('[data-trailing-line="true"]')
    assert len(trailing) > 0

def test_trailing_marker_exists(self):
    """拖尾圆点: data-trailing-marker 元素存在"""
    markers = chart_page.query_selector_all('[data-trailing-marker="true"]')
    assert len(markers) > 0

def test_trailing_dotted_line_attributes(self):
    """拖尾虚线: stroke=#333, stroke-dasharray=4,3"""
    attrs = chart_page.evaluate("""(() => {
        const line = document.querySelector('[data-trailing-line="true"]');
        return {
            stroke: line.getAttribute('stroke'),
            dasharray: line.getAttribute('stroke-dasharray'),
            opacity: line.getAttribute('opacity')
        };
    })()""")
    assert attrs['stroke'] == '#333333'
    assert attrs['dasharray'] == '4,3'

def test_hide_tails_class(self):
    """hide-tails class 时拖尾线隐藏"""
    # 1) 等渲染 + addTrailingDottedLines (默认显示)
    # 2) hideLinkLabelTails=true 或 layoutEngine='elk' -> shouldHideTails=true
    # 3) 2s 后, svg.classList 应包含 'hide-tails'
    # 4) 验证 .hide-tails CSS 选择器把 [data-trailing-line] opacity 设为 0
```

### 4.3 风险

- **中风险**: 端点位置错误会让连线"穿出"或"脱离"节点, 视觉非常明显
- 隐藏 bug 风险:
  - Mermaid v11 升级后端点位置算法可能变
  - ELK 引擎 vs Dagre 引擎的端点位置不同
  - `addTrailingDottedLines` 用 `getTotalLength` + `getPointAtLength` 计算, 但路径可能在 label 中心附近不是最近点 (用 nearestPoint 选最近点, 但没测)
  - `getAttribute('transform')` 解析 fail 时 warn 跳过, 没降级方案

---

## 5. Legend 相关 (❌ 完全未覆盖)

### 5.1 涉及功能

```javascript
// useSvgProcessor.js:188-269 buildColorLegendData
const buildColorLegendData = (diagramData, nodeColorMappings, centerScopeHighlight = true) => {
  // 1) 收集 groupKey (按 colorGroupBy: domain / subDomain / serviceModule)
  // 2) 第一个中心范围 ('中心范围', centerScopeColor, isCenter=true)
  // 3) 然后各分组颜色 ({ name: groupKey, color: node.color })
  return legendData
}

// annotationOverlay.js:527 overlayColorLegend
// 在 SVG 上叠加 .color-legend-panel (data-annotation-layer="legend")
```

### 5.2 legend 结构

```html
<div class="color-legend-panel" data-annotation-layer="legend">
  <div class="color-legend-title">图例</div>
  <div class="color-legend-list">
    <div class="legend-item">
      <span class="legend-dot" style="background:#EDEDED"></span>
      <span class="legend-name">中心范围</span>
    </div>
    <div class="legend-sep"></div>  ← 仅在 isCenter 且非最后一项时
    <div class="legend-item">
      <span class="legend-dot" style="background:#FF6B6B"></span>
      <span class="legend-name">订单管理</span>
    </div>
    <div class="legend-item">
      <span class="legend-dot" style="background:#4ECDC4"></span>
      <span class="legend-name">支付服务</span>
    </div>
    ...
  </div>
</div>
```

### 5.3 应该有的测试 (但没有)

```python
def test_legend_panel_exists(self):
    """Legend 面板存在"""
    arch_data = create_arch_data(nodes=5, color_group_by='domain')
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)
    
    legend = chart_page.query_selector('.color-legend-panel')
    assert legend is not None

def test_legend_panel_has_title(self):
    """Legend 标题: '图例'"""
    # 验证 .color-legend-title 文本 = "图例"

def test_legend_includes_center_scope(self):
    """有 isCenter=true 节点时, legend 第一个是 '中心范围'"""
    arch_data['nodes'][0]['isCenter'] = True
    # ... 渲染
    legend_items = chart_page.query_selector_all('.legend-item')
    first_name = legend_items[0].query_selector('.legend-name').inner_text()
    assert first_name == '中心范围'

def test_legend_color_dot_matches_node(self):
    """Legend 颜色块颜色 = 对应节点颜色"""
    # 1) 注入节点 1 颜色 = #FF6B6B
    # 2) 验证 legend 中 '订单管理' 行的 .legend-dot background = #FF6B6B

def test_legend_separator_after_center(self):
    """中心范围后有 separator (如果不是最后一项)"""
    # 验证 center 之后有 .legend-sep
    seps = chart_page.query_selector_all('.legend-sep')
    assert len(seps) >= 1

def test_legend_no_separator_when_only_center(self):
    """只有中心范围, 无分组节点时, legend 不显示 separator"""
    # 仅 1 个 isCenter 节点, 无其他节点
    arch_data = {'nodes': [{'isCenter': True, 'name': '中心', 'code': 'C1'}], 'relationships': []}
    # 渲染
    seps = chart_page.query_selector_all('.legend-sep')
    assert len(seps) == 0  # 没有 separator

def test_legend_group_by_domain(self):
    """colorGroupBy='domain' 时按 domain 分组"""
    arch_data = {
        'nodes': [
            {'code': 'N1', 'name': '订单', 'domain': '业务域A'},
            {'code': 'N2', 'name': '支付', 'domain': '业务域A'},
            {'code': 'N3', 'name': '库存', 'domain': '业务域B'},
        ],
        'colorGroupBy': 'domain',
    }
    # 渲染
    legend_items = chart_page.query_selector_all('.legend-item')
    names = [item.query_selector('.legend-name').inner_text() for item in legend_items]
    assert '业务域A' in names
    assert '业务域B' in names
    # '订单' 和 '支付' 不应在 legend (因为 domain 相同, 合并)

def test_legend_group_by_subdomain(self):
    """colorGroupBy='subDomain' 时按 subDomain 分组"""
    # 同上, 但 groupKey = node.subDomain

def test_legend_group_by_serviceModule(self):
    """colorGroupBy='serviceModule' 时按 serviceModuleName 分组"""
    # 同上, 但 groupKey = node.serviceModuleName

def test_legend_custom_color_mapping(self):
    """自定义颜色映射 nodeColorMappings 覆盖默认"""
    nodeColorMappings = [{'nodeCode': 'N1', 'color': '#123456'}]
    # 验证 N1 的图例颜色 = '#123456' (而非 node.color)

def test_legend_hidden_when_no_color_group(self):
    """没有 colorGroupBy 或所有 groupKey 为空时, legend 不显示"""
    arch_data = {'nodes': [{'code': 'N1', 'name': '订单'}]}  # 没 domain
    # 渲染
    legend = chart_page.query_selector('.color-legend-panel')
    # 要么不显示, 要么空 (取决于实现)
    # 实际: legend.length > 0 但只有 '中心范围' (如果没有 isCenter, 则空)
```

### 5.4 单元测试 (vitest) - 测 buildColorLegendData 纯函数

```javascript
// src/composables/useMermaid/renderer/__tests__/useSvgProcessor.spec.js
describe('useSvgProcessor - buildColorLegendData', () => {
  it('应按 domain 分组, 相同 domain 合并', () => {
    const { buildColorLegendData } = useSvgProcessor({ /* ... */ })
    const data = {
      nodes: [
        { code: 'N1', name: '订单', domain: '业务A' },
        { code: 'N2', name: '支付', domain: '业务A' },
        { code: 'N3', name: '库存', domain: '业务B' },
      ],
      colorGroupBy: 'domain'
    }
    const legend = buildColorLegendData(data, [], true)
    expect(legend).toHaveLength(2)  // 业务A + 业务B
    expect(legend.map(l => l.name)).toEqual(['业务A', '业务B'])
  })

  it('应将 isCenter 节点从分组中排除, 并放在第一位', () => {
    const data = {
      nodes: [
        { code: 'C1', name: '中心1', domain: 'A', isCenter: true },
        { code: 'N1', name: '普通1', domain: 'A' },
      ],
      colorGroupBy: 'domain'
    }
    const legend = buildColorLegendData(data, [], true)
    expect(legend[0]).toMatchObject({ name: '中心范围', isCenter: true })
    expect(legend[1].name).toBe('A')
  })

  it('无 colorGroupBy 时, 默认按 domain', () => { /* ... */ })
  it('空 nodes 返回空数组', () => { /* ... */ })
  it('nodeColorMappings 覆盖默认颜色', () => { /* ... */ })
  it('centerScopeHighlight=false 时不显示中心范围', () => { /* ... */ })
})
```

### 5.5 风险

- **高风险**: legend 是用户理解颜色含义的关键 UI
- 隐藏 bug 风险:
  - `data.serviceModules` 和 `data.nodes` 都遍历, 容器/节点混合分组容易出错
  - `centerScopeColor || centerObjectColor || '#EDEDED'`: 三种 fallback, 哪个优先级?
  - `isCenter` 节点不参与 colorMap (line 224), 但后续 nodes.forEach 仍会 set (line 247), 但因为有 if (colorMap.has(groupKey)) return, 不会重复添加

---

## 6. 容器标题文字格式完整性 (❌ 完全未覆盖)

### 6.1 涉及功能

```javascript
// src/utils/formatContainerTitle.js
export function formatContainerTitle(title, maxLength = 12) {
  if (!title) return title

  // 模式 1: 主名称（路径1 / 路径2 / ...）
  const bracketMatch = title.match(/^(.+?)[（(](.+)[）)]$/)
  if (bracketMatch) {
    const mainPart = bracketMatch[1].trim()
    const pathPart = bracketMatch[2].trim()
    return `${mainPart}\n（${pathPart}）`  // ← 加 \n 让标题分两行
  }

  // 模式 2: 包含 " / " 分隔
  if (title.includes(' / ')) {
    return title.replace(/\s*\/\s*/g, '\n')  // ← / 换行
  }

  // 模式 3: 超长标题按字符数分行
  if (title.length > maxLength) {
    // ... 字符级别分行
  }

  return title
}
```

### 6.2 应该有的测试 (但没有)

```javascript
// src/utils/__tests__/formatContainerTitle.spec.js
describe('formatContainerTitle', () => {
  it('空标题返回原值', () => {
    expect(formatContainerTitle('')).toBe('')
    expect(formatContainerTitle(null)).toBe(null)
    expect(formatContainerTitle(undefined)).toBe(undefined)
  })

  it('模式 1: 中文括号分行', () => {
    expect(formatContainerTitle('订单管理（电商 / 物流 / 供应链）'))
      .toBe('订单管理\n（电商 / 物流 / 供应链）')
  })

  it('模式 1: 英文括号分行', () => {
    expect(formatContainerTitle('Order Management(EC / Logistics)'))
      .toBe('Order Management\n(EC / Logistics)')
  })

  it('模式 2: / 分隔换行', () => {
    expect(formatContainerTitle('订单 / 支付 / 库存'))
      .toBe('订单\n支付\n库存')
  })

  it('模式 2: / 前后空格也处理', () => {
    expect(formatContainerTitle('订单  /  支付  /  库存'))
      .toBe('订单\n支付\n库存')  // \s* 包含多空格
  })

  it('模式 3: 超长标题按 maxLength 分行', () => {
    const title = '订单管理模块全功能服务'  // 11 字符
    const result = formatContainerTitle(title, 4)
    expect(result).toBe('订单管理\n模块全\n功能服\n务')
  })

  it('短标题 (< maxLength) 不处理', () => {
    expect(formatContainerTitle('订单', 12)).toBe('订单')
  })

  it('边界: 长度 == maxLength 不处理', () => {
    expect(formatContainerTitle('订单管理模块', 6)).toBe('订单管理模块')  // 6 == 6, 不进入循环
  })

  it('模式 1 vs 模式 2 优先级: 括号优先', () => {
    // '订单（电商）' -> 模式 1
    expect(formatContainerTitle('订单（电商）')).toBe('订单\n（电商）')
  })

  it('嵌套括号只匹配最外层', () => {
    // '订单（电商 / 物流（国际））' -> 匹配最外层
    // 实际: regex /^(.+?)[（(](.+)[）)]$/ 贪婪匹配内部括号
    // .+ 是贪婪, 可能匹配过多
    // 需要测实际行为
  })
})
```

### 6.3 E2E 容器标题显示测试 (但没有)

```python
def test_container_title_no_truncation(self):
    """容器标题不应被截断 (长标题分行展示)"""
    arch_data = {
        'containers': [{
            'name': '订单管理（电商 / 物流 / 供应链）',
            'nodes': [{'code': 'N1', 'name': '订单'}]
        }],
        'nodes': [{'code': 'N1', 'name': '订单'}]
    }
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)
    
    # 1) 找容器标题
    cluster_label = chart_page.query_selector('.mermaid-content .cluster-label')
    assert cluster_label is not None
    
    # 2) 验证内容包含原始字符
    text = cluster_label.inner_text()  # 用 inner_text 让 \n 生效
    assert '订单管理' in text
    assert '电商' in text
    assert '物流' in text
    
    # 3) 验证换行 (\n 转换为 <br> 或 多个 <tspan>)
    # 注意: Mermaid 用 <foreignObject> 时 \n 变 <br>, 用 <text> 时变 <tspan>
    # 验证至少 2 行: inner_text 应含 \n
    assert '\n' in text

def test_container_title_format_consistency(self):
    """容器标题格式与 formatContainerTitle 一致"""
    # 1) 验证 mermaid 渲染后的 .cluster-label 内容 = formatContainerTitle(原始) 渲染后
    # 这需要在 mermaid 渲染时拦截输入
    
def test_container_title_slash_format(self):
    """'订单 / 支付' 模式: 容器标题分多行"""
    arch_data['containers'][0]['name'] = '订单 / 支付 / 库存'
    # 渲染, 验证 3 行

def test_container_title_short_no_change(self):
    """短标题 < 12 字符: 不分行"""
    arch_data['containers'][0]['name'] = '订单管理'  # 4 字符
    # 渲染, 验证 1 行
```

### 6.4 风险

- **中风险**: 标题格式化是纯函数, 易测, 但**没人测**
- 隐藏 bug 风险:
  - `regex /^(.+?)[（(](.+)[）)]$/` 的 `(.+)` 贪婪匹配, 对嵌套括号 `订单（电商（国际））` 行为未知
  - `formatContainerTitle` 在 elkZoneLayout.js:59 用, 在 groupedStyle.js 也有用, 多处使用, 没单测保护
  - 短标题误判: `订单（短）` 只有 1 个括号项, 仍分 2 行 (`订单\n（短）`), 视觉可能不如 `订单（短）` 紧凑

---

## 7. 节点文字格式与完整性 (❌ 完全未覆盖)

### 7.1 涉及功能

**节点文字生成** ([src/composables/useMermaid/syntax/](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/)):

```javascript
// useBusinessObjectSyntax.js (推测, 没读全)
const nodeLabel = `${node.name}\n(${node.code})`  // 节点名 + 换行 + (code)
mermaid += `  ${nodeId}["${nodeLabel}"]:::node\n`
```

**节点样式** ([MermaidComponent.css](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css)):

```css
/* 业务对象图节点 */
.mermaid-content.businessObject :deep(.nodeLabel) {
  font-size: 14px;  /* 文字大小 */
  color: #333;
  text-align: center;
}

/* 节点容器 (rect) */
.mermaid-content.businessObject :deep(.node rect) {
  fill: #ffffff;
  stroke: #333333;
  stroke-width: 2px;
}
```

### 7.2 应该有的测试 (但没有)

```python
def test_node_label_text_content(self):
    """节点标题内容: 应包含 name 和 code"""
    arch_data = {
        'nodes': [
            {'code': 'BO_001', 'name': '订单管理'},
        ]
    }
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)
    
    # 1) 找节点
    node = chart_page.query_selector('.mermaid-content .node')
    label = node.query_selector('.nodeLabel')
    
    # 2) 验证 textContent 包含 name 和 code
    text = label.inner_text()
    assert '订单管理' in text
    assert 'BO_001' in text  # 应该在 (code) 中

def test_node_label_two_lines(self):
    """节点标题分两行: name \\n (code)"""
    # inner_text 包含 \n
    text = label.inner_text()
    assert text.count('\n') == 1  # 1 个换行

def test_node_rect_size_matches_label(self):
    """节点 rect 大小应容纳 label 文字 (不被截断)"""
    # 1) 读 rect.width, rect.height
    # 2) 读 label 的 getBBox() / getBoundingClientRect()
    # 3) 验证 rect 足够大 (label.scrollWidth < rect.width)
    rect = node.query_selector('rect')
    rect_w = float(rect.get_attribute('width'))
    rect_h = float(rect.get_attribute('height'))
    # label 是 foreignObject 内的 div, 读 div.scrollWidth
    label_scroll_w = chart_page.evaluate(
        "(el) => el.querySelector('foreignObject div').scrollWidth", [node]
    )
    assert label_scroll_w <= rect_w + 2  # 2px 容差

def test_node_long_name_truncation(self):
    """超长节点名 (30+ 字符) 不应撑爆容器"""
    long_name = '订单管理服务模块全功能集成业务'  # 15 字符
    arch_data['nodes'][0]['name'] = long_name
    # 渲染
    # 1) 验证 rect 宽度 > label scrollWidth (自动 resize)
    # 2) 或者: 验证 label 内有 word-wrap / line break (多行)
    
def test_node_special_characters(self):
    """节点名含特殊字符 (HTML 特殊字符 / 引号) 不破坏 SVG"""
    arch_data['nodes'][0]['name'] = '<script>alert(1)</script>'
    # 渲染
    # 验证 mermaid 不会破坏 (securityLevel: 'loose' 或 htmlLabels: true)
    # Mermaid 会 escape <, > 但不 escape 引号
    # 验证页面没 XSS
    
def test_node_chinese_full_width(self):
    """中文字符宽度计算正确 (1 个中文 = 1 个 ASCII 宽?)"""
    # 实际: 1 个中文 = 2 个 ASCII 宽 (取决于 font-family)
    # 验证 rect 宽度能容纳中文字符
    
def test_node_emoji(self):
    """节点含 emoji 是否正常显示"""
    arch_data['nodes'][0]['name'] = '订单 📦 管理'
    # 渲染
    # 验证 emoji 显示 (需要字体支持)

def test_node_font_size_consistent(self):
    """所有节点 font-size 一致"""
    nodes = chart_page.query_selector_all('.mermaid-content .node .nodeLabel')
    font_sizes = set()
    for n in nodes:
        font_size = chart_page.evaluate(
            "(el) => getComputedStyle(el).fontSize", [n]
        )
        font_sizes.add(font_size)
    assert len(font_sizes) == 1  # 所有节点 font-size 一致

def test_node_color_legends_match(self):
    """节点 fill 颜色 = legend 中对应图例颜色"""
    # 1) 找第一个节点的 fill
    node_fill = chart_page.evaluate(
        "(el) => el.querySelector('rect').style.fill || getComputedStyle(el.querySelector('rect')).fill",
        [node]
    )
    # 2) 在 legend 中找对应 name
    # 3) 验证 legend dot background = node_fill
```

### 7.3 风险

- **中风险**: 节点文字是图表最核心的展示元素
- 隐藏 bug 风险:
  - 节点名 vs code 谁在前? `name\n(code)` 还是 `code\nname`? (现在是 name 在前)
  - 中文字符 + emoji + 特殊字符混排的宽度计算
  - 长节点名是否会自动换行 / 截断 / 缩字号?
  - `<foreignObject>` 内的 HTML 注入风险 (mermaid 用了 `loose` securityLevel, 允许 HTML)

---

## 8. 整体测试覆盖矩阵 (7 维度 × N 测试)

| 维度 | 单元测试 | 组件测试 | E2E 测试 | 视觉回归 | 合计 | 风险 |
|------|---------|---------|---------|---------|------|------|
| 1. annotation 点击联动 | 0 | 0 | 0 | 0 | **0/6** | 高 |
| 2. 连线点击高亮联动 | 0 | 0 | 0 | 0 | **0/5** | 高 |
| 3. 连线 tooltip 内容 | 0 | 0 | 0 | 0 | **0/7** | 高 |
| 4. 连线端点 + 箭头 | 0 | 0 | 0 | 0 | **0/7** | 中 |
| 5. legend | 0 | 0 | 0 | 0 | **0/11** | 高 |
| 6. 容器标题格式 | 0 | 0 | 0 | 0 | **0/13** | 中 |
| 7. 节点文字格式 | 0 | 0 | 0 | 0 | **0/8** | 中 |
| **合计** | **0** | **0** | **0** | **0** | **0/57** | |

**7 个维度 × 0 测试 = 0/57 = 0% 覆盖**.

---

## 9. 为什么这 7 个细节特别重要

### 9.1 这 7 个细节都是"用户感知的核心"

| 维度 | 用户感知 |
|------|---------|
| annotation 联动 | 用户点备注, **期望** 图表相应位置高亮, 这是"联动"的核心价值 |
| 连线点击高亮 | 用户点线, **期望** 看到线变粗 + 节点变红, 这是"导航"的核心价值 |
| tooltip 内容 | 用户 hover, **期望** 看到完整的关系说明, 这是"信息获取"的唯一途径 |
| 端点箭头 | 用户看图, **期望** 连线从节点的"边"出发/进入, 这是"视觉正确"的基本要求 |
| legend | 用户看色, **期望** 知道每个颜色代表什么, 这是"图例"的根本作用 |
| 容器标题格式 | 用户看容器, **期望** 标题分多行展示, 这是"信息密度"的设计要求 |
| 节点文字 | 用户看节点, **期望** name + code 都显示, 这是"识别节点"的基本需求 |

### 9.2 这 7 个细节都是"易改易错"的代码区域

| 维度 | 改 1 行会引发什么? |
|------|------------------|
| annotation | 改 `data-target-id` 属性名 -> 联动全失效, 用户体验崩溃 |
| 连线点击 | 改 `pathToRelationMap` key 算法 -> 联动失效或错位 |
| tooltip | 改 `formatTooltipText` 字段顺序 -> 用户看到错位信息 |
| 端点箭头 | 改 layout 引擎 -> 端点位置变化, 可能穿出节点 |
| legend | 改 `colorGroupBy` 默认值 -> 颜色分组错乱 |
| 容器标题 | 改 formatContainerTitle regex -> 标题分行错误 |
| 节点文字 | 改 syntax 模板 (如 name + code 顺序) -> 节点显示错乱 |

### 9.3 这 7 个细节都是"沉默的 bug" (silent bug)

不像"页面崩溃" / "500 错" 这种明显错误, 这 7 个细节的 bug 都是:
- **页面不崩**
- **用户能继续用**
- **但功能不完整/不直观/不美观**
- **用户默默放弃该功能, 不会主动报 bug**

**例子**:
- annotation 点击不联动? 用户不会报"annotation 联动失效", 会说"备注没用, 不看了"
- tooltip 显示 `无关系说明`? 用户不会报"tooltip 字段缺失", 会说"这个图看不到关系"
- 端点穿出节点? 用户不会报"端点位置错", 会说"这图好丑"

---

## 10. 立即可补的测试清单 (~150 行)

### 10.1 formatContainerTitle 单元测试 (13 个, ~80 行)

新建 [src/utils/__tests__/formatContainerTitle.spec.js](file:///d:/filework/excel-to-diagram/src/utils/__tests__/formatContainerTitle.spec.js):

```javascript
import { describe, it, expect } from 'vitest'
import { formatContainerTitle } from '../formatContainerTitle'

describe('formatContainerTitle', () => {
  // ... 上面的 13 个测试
})
```

**价值**: 13 个测试覆盖纯函数, 5 分钟写完, 立刻防护 3 种格式模式 + 边界条件.

### 10.2 useSvgProcessor buildColorLegendData 单元测试 (6 个, ~80 行)

新建 [src/composables/useMermaid/renderer/__tests__/useSvgProcessor.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/renderer/__tests__/useSvgProcessor.spec.js):

```javascript
// 上面 §5.4 的 6 个测试
```

**价值**: 6 个测试覆盖 legend 数据生成的 3 种分组模式 + 中心范围 + 颜色映射.

### 10.3 useAnnotation 单元测试 (4 个, ~50 行)

新建 [src/composables/useMermaid/annotation/__tests__/useAnnotation.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/annotation/__tests__/useAnnotation.spec.js):

```javascript
import { describe, it, expect } from 'vitest'
import { useAnnotation } from '../useAnnotation'

describe('useAnnotation - parseAnnotationsFromData', () => {
  it('业务对象图: 应从 serviceModules + nodes + links 收集 annotation', () => {
    const { parseAnnotationsFromData } = useAnnotation()
    const data = {
      serviceModules: [{ code: 'SM1', name: '订单', annotationContent: '关键模块' }],
      nodes: [{ code: 'N1', name: '订单管理', annotationContent: '关键节点' }],
      links: [{ source: 'N1', target: 'N2', annotationContent: '关键关系' }]
    }
    const result = parseAnnotationsFromData(data, 'businessObject')
    expect(result).toHaveLength(3)
    expect(result[0].targetType).toBe('container')
    expect(result[1].targetType).toBe('node')
    expect(result[2].targetType).toBe('relation')
  })

  it('服务模块图: 应从 containers 收集 annotation (含 nodes 嵌套)', () => {
    const { parseAnnotationsFromData } = useAnnotation()
    const data = {
      containers: [{
        code: 'C1', name: '订单', annotationContent: '容器备注',
        nodes: ['N1']
      }],
      nodes: [
        { id: 'N1', name: '订单管理', annotationContent: '节点备注' }
      ]
    }
    const result = parseAnnotationsFromData(data, 'serviceModule')
    expect(result).toHaveLength(2)
  })

  it('annotationContent 为空时, 节点不加入', () => {
    // ... 只算有 content 的
  })

  it('numbering: 1, 2, 3 递增 + 补 0 (ANN001, ANN002, ANN003)', () => {
    // 验证 id = 'ANN001' (3 位补 0)
  })
})
```

### 10.4 E2E 7 大维度核心场景 (10 个, ~300 行)

新建 [tests/e2e/test_chart_interaction_details.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_chart_interaction_details.py):

```python
"""业务对象图 7 大交互细节 E2E - v2 复盘回归保护"""

# 1. annotation 点击联动
def test_d1_annotation_node_click_highlights_node(self): pass
def test_d2_annotation_relation_click_highlights_edge(self): pass

# 2. 连线点击高亮联动
def test_d3_edge_click_highlights_path_and_nodes(self): pass
def test_d4_edge_click_clears_previous_highlight(self): pass

# 3. tooltip 内容
def test_d5_edge_tooltip_full_content(self): pass
def test_d6_edge_tooltip_no_annotation(self): pass

# 4. 端点箭头
def test_d7_edge_endpoints_on_node_edges(self): pass
def test_d8_edge_has_arrow_marker(self): pass

# 5. legend
def test_d9_legend_panel_with_groups(self): pass
def test_d10_legend_center_scope(self): pass
```

**价值**: 10 个 E2E 覆盖 7 大维度的核心场景, 1 周内可完成.

---

## 11. 总结

### 11.1 用户问的 7 个细节覆盖情况

| # | 细节 | 覆盖? | 应有测试数 | 关键风险 |
|---|------|-------|----------|---------|
| 1 | annotation 点击联动 | **❌** | 6 个 (3 targetType × 2) | 联动核心, 0 保护 |
| 2 | 连线点击高亮联动 | **❌** | 5 个 (高亮/联动/状态清理) | 核心交互, 0 保护 |
| 3 | tooltip 内容完整性 | **❌** | 7 个 (5 字段 × 2 模式) | 信息获取, 0 保护 |
| 4 | 端点 + 箭头在节点边 | **❌** | 7 个 (4 边 + 箭头 + 拖尾) | 视觉正确, 0 保护 |
| 5 | legend | **❌** | 11 个 (3 分组 × 2 + 中心范围 + 颜色映射) | 颜色理解, 0 保护 |
| 6 | 容器标题格式 | **❌** | 13 个 (3 模式 + 边界) | 纯函数, 易测, 没人测 |
| 7 | 节点文字格式 | **❌** | 8 个 (内容/分行/特殊字符) | 核心展示, 0 保护 |

**合计: 0/57 测试 = 0% 覆盖**.

### 11.2 这 7 个细节的共同特征

1. **都是"用户感知核心"**: 用户最直接接触的功能
2. **都是"易改易错"**: 改 1 行就破坏联动/格式
3. **都是"沉默 bug"**: 不崩, 但功能失效, 用户默默放弃
4. **都是"测试盲区"**: 单元/组件/E2E/视觉, 0 个维度覆盖

### 11.3 立即可补 (1 周, ~510 行)

1. **formatContainerTitle 单测 (80 行, 13 测试)** - 纯函数, 5 分钟写完
2. **buildColorLegendData 单测 (80 行, 6 测试)** - 纯函数, 半天写完
3. **useAnnotation 单测 (50 行, 4 测试)** - 解析逻辑, 1 小时写完
4. **E2E 7 维度核心 10 场景 (300 行, 10 测试)** - 1 天写完

**合计 ~510 行, 1 周工作量, 把这 7 个细节从 0% 覆盖提升到 30% 覆盖**.

### 11.4 中期目标 (1 月, ~1500 行)

- 拆 useTooltip (parseLabelText / matchPathsToRelations 抽离)
- 抽 useAnnotationOverlay (highlightTargetElement 可测)
- 补 E2E 7 维度完整 57 个场景
- 加视觉回归 5 个基线 (annotation 高亮/edge 高亮/legend/容器标题/节点文字)

**合计 ~1500 行 + 重构, 1 月工作量, 把这 7 个细节从 30% 提升到 80% 覆盖**.

## 12. 行动清单

### 立即 (P0, 1 周)
- [ ] 加 `formatContainerTitle.spec.js` (13 测试)
- [ ] 加 `useSvgProcessor.spec.js#buildColorLegendData` (6 测试)
- [ ] 加 `useAnnotation.spec.js#parseAnnotationsFromData` (4 测试)
- [ ] 加 `tests/e2e/test_chart_interaction_details.py` (10 场景)
- [ ] 把这 7 个细节加到 SESSION_REMINDER 防遗漏

### 短期 (P1, 1 月)
- [ ] 拆 useTooltip 抽离 matchPathsToRelations
- [ ] 抽 useAnnotationOverlay 关键函数
- [ ] 补 E2E 完整 57 场景
- [ ] 加视觉回归 5 个基线

### 中期 (P2, 季度)
- [ ] 接入 Storybook annotation story
- [ ] 接入 Storybook legend story
- [ ] 接入 Storybook edge highlight story
- [ ] 集成 Chromatic 视觉 review
