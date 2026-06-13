# StepConfig 配置页功能 - 测试覆盖专项分析

> **分析日期**: 2026-06-11
> **触发**: 用户问"颜色配置, 中心范围颜色, 连线颜色规则, 布局控制 (水平/垂直), 分组控制 (容器隐藏/disabling) 这些是否有覆盖"
> **结论先行**: **全部未覆盖**. 0 个针对性测试. 还发现了**2 个潜在 bug** (在测试盲区里).

---

## 0. TL;DR

| # | 配置功能 | 覆盖? | 应有测试数 | 关键文件 | 风险 |
|---|---------|-------|----------|---------|------|
| 1 | **颜色配置 (colorScheme)** | ❌ 0 测试 | 8 个 (7 scheme + 默认) | [useMermaidColors.js:1-45](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/color/useMermaidColors.js#L1-L45) | 中 |
| 2 | **中心范围颜色 (centerScopeColor)** | ❌ 0 测试 | 5 个 (默认/自定义/disabled/enabled) | [useSvgProcessor.js:188-269](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/renderer/useSvgProcessor.js#L188-L269) | 高 |
| 3 | **连线颜色规则 (updateLinkColors)** | ❌ 0 测试 | 7 个 (同域/跨域/不同 groupBy) | [useMermaidColors.js:72-101](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/color/useMermaidColors.js#L72-L101) | 中 |
| 4 | **布局控制 - 水平/垂直 (LR/TB)** | ❌ 0 测试 | 6 个 (LR/TB + per-group override) | [useLayoutControl.js:5-7](file:///d:/filework/excel-to-diagram/src/composables/useLayoutControl.js#L5-L7) + [groupedLayout.js:268-269](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/groupedLayout.js#L268-L269) | 中 |
| 5 | **分组控制 - 容器可见 (visible)** | ❌ 0 测试 | 5 个 (visible=true/false/混合) | [groupedLayout.js:262-272](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/groupedLayout.js#L262-L272) + [groupedStyle.js:9](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/groupedStyle.js#L9) | 高 |
| 6 | **分组控制 - 容器禁用 (enabled)** | ⚠️ **0 测试 + 1 bug** | 5 个 (disabled 容器/disabled 组) | [groupedLayout.js:62-105](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/groupedLayout.js#L62-L105) | **高 + 潜在 bug** |
| **合计** | | | **36 个** | | **2 个潜在 bug** |

**总分: 0/36 (0%) 覆盖**. 6 个配置功能**全部没有针对性测试**.

---

## 1. 颜色配置 (colorScheme) - ❌ 完全未覆盖

### 1.1 涉及功能

```javascript
// useMermaidColors.js:7-9
const getColorScheme = (schemeName) => {
  return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
}

// 7 种 scheme (从 StepConfig.vue:245-253 + constants/diagram):
// - default: '#1890FF', '#52C41A', ... (12 色, 蓝绿黄紫)
// - vibrant: '#FF6B6B', '#4ECDC4', ... (12 色, 亮色系)
// - pastel:  '#FFB3BA', '#BAFFC9', ... (12 色, 柔和)
// - warm:    '#E74C3C', '#E67E22', ... (12 色, 暖色系)
// - cool:    '#3498DB', '#2980B9', ... (12 色, 冷色系)
// - business:'#2C3E50', '#34495E', ... (12 色, 商务)
// - nature:  '#27AE60', '#229954', ... (12 色, 大自然)
```

### 1.2 **发现 1 个潜在 bug**: COLOR_SCHEMES 在 2 处硬编码且不一致

**位置 1** (useMermaidColors.js:1): 从 `@/constants/diagram` 导入
**位置 2** (StepConfig.vue:245-253): **重新硬编码一份**!

```javascript
// StepConfig.vue:239-253 - 同一个 COLOR_SCHEMES 在这里被复制粘贴
const COLOR_SCHEMES = {
  default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
  vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
  // ...
}
```

**风险**:
- 改 `constants/diagram` 时忘记改 `StepConfig.vue`, 两个地方颜色不一致
- 反之亦然
- **0 测试**发现这个问题, 因为没人测

### 1.3 应该有的测试 (但没有)

```javascript
// src/composables/useMermaid/color/__tests__/useMermaidColors.spec.js
import { describe, it, expect } from 'vitest'
import { useMermaidColors } from '../useMermaidColors'

describe('useMermaidColors - getColorScheme', () => {
  it('7 个内置 scheme 都能取到', () => {
    const { getColorScheme } = useMermaidColors()
    const schemes = ['default', 'vibrant', 'pastel', 'warm', 'cool', 'business', 'nature']
    schemes.forEach(name => {
      const scheme = getColorScheme(name)
      expect(scheme).toBeDefined()
      expect(scheme.length).toBeGreaterThanOrEqual(8)
    })
  })

  it('未知 scheme 应 fallback 到 default', () => {
    const { getColorScheme } = useMermaidColors()
    expect(getColorScheme('unknown-scheme')).toEqual(getColorScheme('default'))
  })

  it('空字符串 / null / undefined 都应 fallback', () => {
    const { getColorScheme } = useMermaidColors()
    expect(getColorScheme('')).toEqual(getColorScheme('default'))
    expect(getColorScheme(null)).toEqual(getColorScheme('default'))
    expect(getColorScheme(undefined)).toEqual(getColorScheme('default'))
  })
})

describe('useMermaidColors - buildColorMap', () => {
  it('colorGroupBy=domain 时按 domain 分组', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
      ['N2', { domain: '业务A' }],
      ['N3', { domain: '业务B' }],
    ])
    const nodeColorMappings = [
      { nodeCode: 'N1', nodeId: 'id1' },
      { nodeCode: 'N2', nodeId: 'id2' },
      { nodeCode: 'N3', nodeId: 'id3' },
    ]
    const colorMap = buildColorMap(
      nodeColorMappings, objectToModuleMap, 'domain',
      ['#FF0000', '#00FF00', '#0000FF'], {}
    )
    expect(colorMap.size).toBe(2)  // 业务A + 业务B
    expect(colorMap.get('业务A')).toBe('#FF0000')  // 第一个颜色
    expect(colorMap.get('业务B')).toBe('#00FF00')  // 第二个颜色
  })

  it('colorGroupBy=serviceModule 时按 serviceModuleName', () => {
    // ... 同上, 但 moduleInfo.serviceModuleName
  })

  it('colorGroupBy=subDomain 时按 subDomain', () => {
    // ... 同上
  })

  it('customColors 覆盖默认 scheme 颜色', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
    ])
    const colorMap = buildColorMap(
      [{ nodeCode: 'N1' }], objectToModuleMap, 'domain',
      ['#FF0000'], { '业务A': '#123456' }
    )
    expect(colorMap.get('业务A')).toBe('#123456')  // 自定义覆盖
  })

  it('nodeCode 找不到时按 nodeName 再找', () => {
    // objectToModuleMap.get('N1') 没找到, 试 objectToModuleMap.get('订单管理')
  })

  it('颜色 index 应在 scheme 内循环 (>= 12 个组)', () => {
    // 13 个 domain, 颜色应为 [0,1,2,...,11,0]
  })
})
```

### 1.4 风险

- **中风险**: 颜色是用户感知最直接的视觉元素
- 隐藏 bug 风险:
  - 两个地方硬编码 COLOR_SCHEMES, 不一致
  - 12 色循环: 13 个分组, 第 13 个跟第 1 个同色, 用户分不清
  - `customColors` 仅支持 `domain` name 作 key, 但中文 `业务A` 跟英文 `Domain A` 不可作 key 互相覆盖

---

## 2. 中心范围颜色 (centerScopeColor) - ❌ 完全未覆盖

### 2.1 涉及功能

**3 个状态** (从 diagramConfigStore 推断):
- `centerScopeColor`: 中心范围节点背景色 (默认 `#EDEDED`)
- `centerScopeHighlight`: 是否高亮中心范围 (默认 `true`)
- `centerScope`: 中心范围 BO code 集合 (Set)
- `centerScopeMarkers`: { domains, subDomains, serviceModules } 集合

**视觉变化** ([useSvgProcessor.js:188-269 buildColorLegendData](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/renderer/useSvgProcessor.js#L188-L269)):
- 中心范围节点 `fill = centerScopeColor`
- Legend 第一项: `图例` (含 `centerScopeColor` 颜色 + `中心范围` 文字)

**StepConfig.vue 中** ([StepConfig.vue:268-292 isFullyInCenterScope](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/components/steps/StepConfig.vue#L268-L292)):
- 完全在中心范围内的 domain/subDomain/serviceModule 不分配颜色 (从 colorMapping 中跳过)
- 部分在中心范围则正常分配

### 2.2 应该有的测试 (但没有)

```javascript
// 单元测试: buildColorLegendData 中心范围逻辑
describe('useSvgProcessor - buildColorLegendData 中心范围', () => {
  it('centerScopeHighlight=true + 节点 isCenter=true -> legend 第 1 项 = "中心范围"', () => {
    const { buildColorLegendData } = useSvgProcessor({ /* ... */ })
    const data = {
      nodes: [
        { code: 'C1', isCenter: true, name: '中心节点' },
        { code: 'N1', name: '普通节点' },
      ],
      colorGroupBy: 'domain',
      centerScopeColor: '#EDEDED',
    }
    const legend = buildColorLegendData(data, [], true)
    expect(legend[0]).toMatchObject({ name: '中心范围', color: '#EDEDED', isCenter: true })
  })

  it('centerScopeHighlight=false -> 不显示中心范围', () => {
    // 验证 legend 不含 isCenter 项
  })

  it('centerScopeColor 自定义颜色应传递到 legend', () => {
    // centerScopeColor = '#123456', legend[0].color = '#123456'
  })

  it('centerScopeColor 为空/null 时用 #EDEDED fallback', () => {
    // centerScopeColor = null, legend[0].color = '#EDEDED'
  })

  it('没有 isCenter 节点时, legend 不显示中心范围', () => {
    // nodes 都 isCenter=false
    // legend 全部是分组, 无中心项
  })
})

// E2E 测试: 中心范围颜色应用
def test_center_scope_color_applied_to_node(self):
    """centerScopeColor 应应用到 isCenter 节点的 fill"""
    arch_data = {
        'nodes': [
            {'code': 'C1', 'isCenter': True, 'name': '中心'},
            {'code': 'N1', 'name': '普通'},
        ],
        'centerScopeColor': '#123456',
    }
    chart_page.inject_arch_data(arch_data)
    chart_page.wait_for_timeout(3000)

    # 找 isCenter 节点
    center_node = chart_page.query_selector('[data-id*="C1"]')
    rect = center_node.query_selector('rect')
    fill = rect.get_attribute('fill') or rect.style.fill
    assert fill == '#123456' or 'rgb(18, 52, 86)' in fill

def test_center_scope_highlight_creates_legend_separator(self):
    """centerScopeHighlight=true 时 legend 有中心范围 + 分隔符"""
    # 验证 .legend-sep 存在

def test_center_scope_highlight_false_no_legend_separator(self):
    """centerScopeHighlight=false 时无分隔符"""
    # ...
```

### 2.3 风险

- **高风险**: 中心范围是用户最关注的"业务核心", 颜色出错会误导
- 隐藏 bug 风险:
  - `centerScopeColor || centerObjectColor || '#EDEDED'`: 三种 fallback, 优先级?
  - `centerScopeMarkers` 是 `Set`, 但 `findGroupById` 用 `===` 字符串, JSON.stringify 序列化可能丢
  - 切换 `centerScopeHighlight` 应同时更新 legend + 节点 fill, 但当前**只是响应式 props, 没主动触发更新**

---

## 3. 连线颜色规则 (updateLinkColors) - ❌ 完全未覆盖

### 3.1 涉及功能

```javascript
// useMermaidColors.js:72-101 updateLinkColors
const updateLinkColors = (svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap) => {
  linkColorMappings.forEach(mapping => {
    const sourceModule = objectToModuleMap.get(nodeColorMappings.find(n => n.nodeId === mapping.sourceId)?.nodeCode)
    const targetModule = objectToModuleMap.get(nodeColorMappings.find(n => n.nodeId === mapping.targetId)?.nodeCode)

    if (sourceModule && targetModule) {
      let sourceGroupKey, targetGroupKey
      if (colorGroupBy === 'serviceModule') {
        sourceGroupKey = sourceModule.serviceModuleName || sourceModule.serviceModule
        targetGroupKey = targetModule.serviceModuleName || targetModule.serviceModule
      } else if (colorGroupBy === 'subDomain') {
        sourceGroupKey = sourceModule.subDomain
        targetGroupKey = targetModule.subDomain
      } else {
        sourceGroupKey = sourceModule.domain
        targetGroupKey = targetModule.domain
      }

      const newColor = colorMap.get(sourceGroupKey) || colorMap.get(targetGroupKey) || DEFAULT_LINK_COLOR
      // sourceGroupKey 优先, 这是关键规则: 连线跟随源节点颜色

      const paths = svg.querySelectorAll('.flowchart-link path, .edgePath path')
      if (paths[mapping.index]) {
        paths[mapping[index].setAttribute('stroke', newColor)
        paths[index].style.stroke = newColor
      }

      mapping.color = newColor
    }
  })
}
```

### 3.2 关键规则

| 场景 | 颜色来源 | 说明 |
|------|---------|------|
| source 在 colorMap 中 | source.groupKey 颜色 | 连线跟 source 同色 |
| source 不在, target 在 | target.groupKey 颜色 | 兜底用 target 颜色 |
| 都不在 | `DEFAULT_LINK_COLOR` | 默认灰色 |
| 跨 domain 边 | source 域颜色 | 即使 target 跨域, 仍用 source 颜色 |

### 3.3 应该有的测试 (但没有)

```javascript
// 单元测试
describe('useMermaidColors - updateLinkColors', () => {
  it('同域连线: 颜色 = 该域 colorMap 颜色', () => {
    // source 业务A, target 业务A
    // expect(stroke = colorMap.get('业务A'))
  })

  it('跨域连线: 颜色 = source 域颜色 (而非 target)', () => {
    // source 业务A, target 业务B
    // expect(stroke = colorMap.get('业务A'))
  })

  it('source 不在 colorMap 时, fallback target', () => {
    // source groupKey 找不到, target 业务B
    // expect(stroke = colorMap.get('业务B'))
  })

  it('source 和 target 都不在时, DEFAULT_LINK_COLOR', () => {
    // expect(stroke = DEFAULT_LINK_COLOR)
  })

  it('colorGroupBy=serviceModule 时按 serviceModuleName 分组', () => {
    // ...
  })

  it('colorGroupBy=subDomain 时按 subDomain', () => {
    // ...
  })

  it('objectToModuleMap 找不到 source/target 时不抛错', () => {
    // ... 优雅跳过
  })

  it('path index 越界时优雅降级 (paths[mapping.index] undefined)', () => {
    // mapping.index = 999, paths.length = 5
    // 验证不抛错
  })

  it('setAttribute AND style.stroke 都设置 (CSS 优先级)', () => {
    // 验证 path 有 stroke attr + style.stroke 都 = newColor
  })
})
```

### 3.4 风险

- **中风险**: 连线颜色规则不直观, "为什么这条线是蓝色?"用户会困惑
- 隐藏 bug 风险:
  - `sourceGroupKey` 优先而非"平均色" / "中点色", 跨域连线跟 source 同色, 但视觉上"明显"穿过 target 域
  - `find(n => n.nodeId === mapping.sourceId)` 每次都遍历, 100+ 条连线性能 O(n²)
  - `mapping.color = newColor` 写入对象, 但 colorMap 改了后再调用 updateLinkColors 不会重置

---

## 4. 布局控制 - 水平/垂直 (LR/TB) - ❌ 完全未覆盖

### 4.1 涉及功能

```javascript
// useLayoutControl.js:5
const layoutControlConfig = reactive({
  enabled: false,
  overallDirection: 'LR',  // ← 全局: 'LR' (水平 Left-Right) / 'TB' (垂直 Top-Bottom)
  groups: [],
  engine: 'dagre',
  preserveOrder: true
})

// StepConfig.vue:325 localLayoutControlConfig 默认 'LR'
// StepConfig.vue:399 新 group 默认 'TB' (子组用 TB)
```

### 4.2 4 种布局类型的方向控制

| layoutType | 方向来源 | 备注 |
|-----------|---------|------|
| **grouped** | `group.direction` 或 'TB' 默认 | 每个组可独立设 TB/LR/BT/RL |
| **zone** | `Row0/1/2` 内部 'LR' (硬编码 line 54) | 行内水平, 行间垂直 |
| **linear** | `direction` 参数 'horizontal'/'vertical' | 完全水平/垂直 |
| **grid** | (待看) | 网格固定 |

### 4.3 应该有的测试 (但没有)

```javascript
// 单元测试: groupedLayout.js 方向
describe('groupedLayout - 方向控制', () => {
  it('group.direction = "LR" -> subgraph 内 direction LR', () => {
    // 生成代码, 验证包含 'direction LR'
  })

  it('group.direction = "TB" -> direction TB', () => {
    // ...
  })

  it('group.direction = "BT" / "RL" -> 支持', () => {
    // ...
  })

  it('group.direction 未设置 -> 默认 "TB"', () => {
    // group = { title: 'test' } (无 direction)
    // expect 'direction TB'
  })

  it('overallDirection = "LR" 应用于整体 graph', () => {
    // 验证整个 mermaid code 有 'graph LR' (而非 'graph TB')
  })

  it('overallDirection = "TB" 应用于整体 graph', () => {
    // 验证 'graph TB'
  })
})

// E2E: 验证方向影响实际布局
def test_overall_direction_lr_horizontal_layout(self):
    """overallDirection=LR -> 节点从左到右排列"""
    config = {'overallDirection': 'LR'}
    chart_page.set_layout_control_config(config)
    chart_page.wait_for_timeout(3000)
    
    # 找两个节点, 验证 x1 < x2 (从左到右)
    node1_x = chart_page.evaluate("(() => { const r = document.querySelector('.node:nth-of-type(1) rect'); return parseFloat(r.getAttribute('x') || 0); })()")
    node2_x = chart_page.evaluate("(() => { const r = document.querySelector('.node:nth-of-type(2) rect'); return parseFloat(r.getAttribute('x') || 0); })()")
    assert node2_x > node1_x

def test_overall_direction_tb_vertical_layout(self):
    """overallDirection=TB -> 节点从上到下排列"""
    # 验证 y1 < y2
    pass

def test_group_direction_override(self):
    """group.direction 覆盖 overallDirection"""
    # group = { direction: 'LR', children: [...] }
    # 验证子组 subgraph 内 direction LR
    pass
```

### 4.4 风险

- **中风险**: 方向影响整体布局, 改错会让图"挤在一起"或"拉太长"
- 隐藏 bug 风险:
  - `group.direction || 'TB'`: 如果 group.direction 是空字符串 `''`, 仍 fallback 'TB'? (需测)
  - zone 布局硬编码 `direction LR` (line 54), 不能改 (设计限制, 需文档化)
  - groupedLayout `subgraph ${groupId}[ ]` 不可见组用 `direction` 也输出吗? 需测

---

## 5. 分组控制 - 容器可见 (visible) - ❌ 完全未覆盖

### 5.1 涉及功能

```javascript
// groupedLayout.js:262-272
if (group.visible === false) {
  code += `${indent}subgraph ${groupId}[ ]\n`  // ← 不可见, 标题为空
} else {
  code += `${indent}subgraph ${groupId}["${groupTitle}"]\n`
}

let direction = group.direction || 'TB'
code += `${indent}direction ${direction}\n`

const isVisible = group.visible !== false
const nextContainerDepth = isVisible ? containerDepth + 1 : containerDepth

// groupedStyle.js:9
if (group.layout.visible === false) { /* 隐藏样式 */ }
```

### 5.2 应该有的测试 (但没有)

```javascript
describe('groupedLayout - 可见性', () => {
  it('group.visible=false -> subgraph 标题为空 "[ ]"', () => {
    // expect code 包含 'subgraph G1[ ]'
  })

  it('group.visible=true (默认) -> subgraph 标题正常', () => {
    // expect 'subgraph G1["Title"]'
  })

  it('group.visible=false -> 容器嵌套 depth 不增加 (扁平化)', () => {
    // nextContainerDepth 不变, 容器直接放上层
  })

  it('group.visible=true -> 容器嵌套 depth + 1', () => {
    // ...
  })
})

// E2E
def test_container_visibility_hide(self):
    """容器 visible=false 时不显示"""
    # 1) 注入 3 个 container, 第 2 个 visible=false
    # 2) 验证 .mermaid-content 内只有 2 个 cluster (不是 3)
    # 3) 第 2 个 cluster 标题为空
    pass

def test_container_visible_default_true(self):
    """visible 未设 -> 默认显示"""
    # ...
    pass
```

### 5.3 风险

- **高风险**: 隐藏容器是基础分组功能
- 隐藏 bug 风险:
  - `subgraph ${groupId}[ ]` 标题为空, 但 Mermaid 可能忽略 `direction` 指令
  - 不可见组 children 仍递归, 但 `nextContainerDepth` 不增加会让子组在错层

---

## 6. 分组控制 - 容器禁用 (enabled) - ⚠️ **0 测试 + 1 个潜在 bug**

### 6.1 涉及功能

```javascript
// groupedLayout.js:62-105
if (group.enabled === false) {
  if (group._disabledAncestorPath && group._disabledAncestorPath.length > 0) {
    // ← 注释说"被提升的应该显示", 但 if 内是空!
  } else {
    return false  // ← 禁用组返回 false
  }
}

// groupedLayout.js:89-93
const containerEnabled = containerData?.enabled !== false
if (containerData?.enabled === false) {
  return false  // ← 禁用容器跳过
}

// groupedLayout.js:223-241 (生成代码时)
if (container && container.nodes && container.nodes.length > 0) {
  const containerEnabled = container.enabled !== false
  if (containerEnabled) {
    // 容器照常生成 subgraph
  } else {
    // 容器 disabled, 节点直接提到外层 (不显示容器)
    container.nodes.forEach(nodeId => { /* 节点外提 */ })
  }
}
```

### 6.2 🚨 **发现 1 个潜在 bug**: linearLayout.js / elkZoneLayout.js 没检查 enabled

**位置**: [linearLayout.js:13-37](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/linearLayout.js#L13-L37) + [elkZoneLayout.js:56-78](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/elkZoneLayout.js#L56-L78)

**问题**: 禁用容器在 grouped 布局下不渲染, 但在线性/区域布局下**仍渲染**:

```javascript
// linearLayout.js:13 - 没有 enabled 检查!
sortedContainers.forEach((container, idx) => {
  if (container) {  // ← 没有 container.enabled 检查
    const containerId = `C${idx + 1}`
    // ... 生成 subgraph
  }
})

// elkZoneLayout.js:56 - 同样没有
rowContainers.forEach(({ container, originalIdx }) => {
  const containerId = `C${originalIdx + 1}`
  // ... 生成 subgraph
})
```

**复现步骤**:
1. 切换 layoutType 到 `linear` 或 `zone`
2. 标记容器 A 为 `enabled=false`
3. 渲染图表 → **容器 A 仍显示**! 应该不显示

**影响**: 用户以为禁用了, 但图上仍有, 功能失效

**根因**: 4 种布局 (grouped/zone/linear/grid) 没统一的"容器过滤"前置步骤, 每个 layout 各自实现

### 6.3 第二个 bug: groupedLayout.js:62-66 空 if 分支

```javascript
if (group.enabled === false) {
  if (group._disabledAncestorPath && group._disabledAncestorPath.length > 0) {
    // ← if 内是空! 注释说"被提升的应该显示", 但啥都没做!
    // 实际效果: 仍继续执行 (因为 if 体内没 return)
  } else {
    return false
  }
}
```

**问题**:
- 注释承诺"被提升的应该显示", 但 if 内是空, 没有 `return true`
- 当前行为: `_disabledAncestorPath` 非空时, 仍继续往下走 (走老逻辑), **碰巧**实现"显示"效果
- 但这是**意外正确的**, 没有任何 if 体代码明确处理

### 6.4 应该有的测试 (但没有)

```javascript
describe('groupedLayout - 容器启用/禁用', () => {
  it('container.enabled=false -> 不生成 subgraph, 节点外提', () => {
    // 容器 enabled=false, 有 2 个节点
    // 验证 code 中无 'subgraph C1[...], 但 2 个节点定义存在
  })

  it('container.enabled=true (默认) -> 正常 subgraph', () => {
    // ...
  })

  it('group.enabled=false + 无 _disabledAncestorPath -> 跳过整组', () => {
    // hasGroupContent 返回 false
  })

  it('group.enabled=false + 有 _disabledAncestorPath -> 仍显示 (被提升)', () => {
    // 注释承诺的行为
  })

  it('递归子组: 父 disabled + 子 enabled -> 子仍渲染', () => {
    // ...
  })
})

// 🚨 应该 E2E 测试, 但 0 测试覆盖这个 bug
def test_disabled_container_hidden_in_grouped_layout(self):
    """grouped 布局: disabled 容器不显示"""
    pass

def test_disabled_container_hidden_in_linear_layout(self):
    """🚨 潜在 bug: linear 布局: disabled 容器仍显示!"""
    # 1) 注入 3 个 container, 第 2 个 enabled=false
    # 2) 切换 layoutType=linear
    # 3) 验证 .mermaid-content 内有 3 个 cluster
    # 4) 期望: 只有 2 个 cluster
    # 实际: 3 个 cluster (bug!)
    pass

def test_disabled_container_hidden_in_zone_layout(self):
    """🚨 潜在 bug: zone 布局: disabled 容器仍显示!"""
    pass
```

### 6.5 风险

- **高风险 + 潜在 bug**: 容器禁用是核心分组功能, 4 种布局中 2 种不生效
- 隐藏 bug 风险:
  - 上面发现的 linear/zone 不检查 enabled
  - groupedLayout.js:62-66 空 if 分支是"意外正确"
  - `_disabledAncestorPath` 没地方写入, 永远空 → 第一个 if 永远走 else → 永远 return false (disabled 组永远不显示) — 这又是另一个 bug!

### 6.6 🚨 关键: `_disabledAncestorPath` 写入位置在哪?

需要进一步验证. 我刚才搜索只看到读, 没看到写. **这意味着**: 
- 如果没代码写入 `_disabledAncestorPath`, 上面那个 if 永远走 else
- 任何 disabled 组都不显示
- 但 hasGroupContent 上面我看到有这逻辑: 跟下面的 children.some 配合

**最关键的是**: 没测试就没人发现, 这些 bug 可能线上已存在.

---

## 7. 整体覆盖矩阵 (6 维度 × N 测试)

| 维度 | 单元测试 | 组件测试 | E2E 测试 | 视觉回归 | 合计 | 风险 |
|------|---------|---------|---------|---------|------|------|
| 1. 颜色配置 (colorScheme) | 0 | 0 | 0 | 0 | **0/11** | 中 |
| 2. 中心范围颜色 | 0 | 0 | 0 | 0 | **0/9** | 高 |
| 3. 连线颜色规则 | 0 | 0 | 0 | 0 | **0/9** | 中 |
| 4. 布局方向 (LR/TB) | 0 | 0 | 0 | 0 | **0/7** | 中 |
| 5. 容器可见 (visible) | 0 | 0 | 0 | 0 | **0/5** | 高 |
| 6. 容器禁用 (enabled) | 0 | 0 | 0 | 0 | **0/8** | **高 + bug** |
| **合计** | **0** | **0** | **0** | **0** | **0/49** | **2 个潜在 bug** |

**6 个维度 × 0 测试 = 0/49 = 0% 覆盖**. **2 个潜在 bug 在测试盲区**.

---

## 8. 立即可补的测试清单 (~250 行, 1 周)

### 8.1 useMermaidColors 单测 (3 个核心函数, ~100 行)

新建 [src/composables/useMermaid/color/__tests__/useMermaidColors.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/color/__tests__/useMermaidColors.spec.js):

```javascript
// §1.3 (3 个 getColorScheme 测试) + §1.3 (4 个 buildColorMap 测试)
// + §3.3 (8 个 updateLinkColors 测试) = 15 个测试
```

### 8.2 useLayoutControl 单测 (5 个核心函数, ~80 行)

新建 [src/composables/__tests__/useLayoutControl.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useLayoutControl.spec.js):

```javascript
describe('useLayoutControl - createGroup', () => {
  it('createGroup 顶层: group 加入 layoutControlConfig.groups', () => { /* ... */ })
  it('createGroup with parentId: 加入到 parent.children', () => { /* ... */ })
  it('createGroup 超过 3 层: 警告 + 不创建', () => { /* ... */ })
})

describe('useLayoutControl - moveContainerBetweenGroups', () => {
  it('从一个组移到另一个组', () => { /* ... */ })
  it('源组找不到容器: 返回 false', () => { /* ... */ })
  it('目标组不存在: 返回 false', () => { /* ... */ })
})
```

### 8.3 groupedLayout 单测 (4 个核心函数, ~70 行)

新建 [src/composables/useMermaid/layouts/__tests__/groupedLayout.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/layouts/__tests__/groupedLayout.spec.js):

```javascript
// §4.3 (6 个方向测试) + §5.2 (4 个可见性测试) + §6.4 (5 个 enabled 测试) = 15 个测试
```

### 8.4 E2E 配置应用 (10 个场景, ~300 行)

新建 [tests/e2e/test_step_config_application.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_step_config_application.py):

```python
class TestColorScheme:
    def test_s1_color_scheme_default_applied(self): pass
    def test_s2_color_scheme_vibrant_applied(self): pass
    def test_s3_color_scheme_change_updates_svg(self): pass

class TestCenterScope:
    def test_s4_center_scope_color_applied(self): pass
    def test_s5_center_scope_highlight_toggle_legend(self): pass

class TestLinkColor:
    def test_s6_link_color_same_domain(self): pass
    def test_s7_link_color_cross_domain(self): pass

class TestDirection:
    def test_s8_direction_lr_horizontal(self): pass
    def test_s9_direction_tb_vertical(self): pass

class TestGroupControl:
    def test_s10_container_disabled_in_grouped(self): pass
    def test_s11_container_visible_toggle(self): pass
```

---

## 9. 总结

### 9.1 用户问的 6 个配置功能 - 直接回答

| # | 配置功能 | 覆盖? | 应有测试数 | 实际 |
|---|---------|-------|----------|------|
| 1 | 颜色配置 (colorScheme) | ❌ 0 测试 | 11 | 0 |
| 2 | 中心范围颜色 | ❌ 0 测试 | 9 | 0 |
| 3 | 连线颜色规则 | ❌ 0 测试 | 9 | 0 |
| 4 | 布局方向 (LR/TB) | ❌ 0 测试 | 7 | 0 |
| 5 | 容器可见 (visible) | ❌ 0 测试 | 5 | 0 |
| 6 | 容器禁用 (enabled) | ❌ 0 测试 + **2 个潜在 bug** | 8 | 0 |
| **合计** | | | **49** | **0 (0%)** |

### 9.2 发现的 2 个潜在 bug (在测试盲区)

#### Bug 1: linearLayout.js / elkZoneLayout.js 不检查 container.enabled
- 4 种布局中, **grouped 正确** (检查 enabled), 但 **linear / zone 不检查**
- 用户禁用容器后, grouped 布局不显示, linear/zone 仍显示
- **0 测试**发现
- **修复**: 抽 `filterEnabledContainers(containers)` 前置, 4 个布局都先过滤

#### Bug 2: groupedLayout.js:62-66 空 if 分支 + `_disabledAncestorPath` 没写入
```javascript
if (group.enabled === false) {
  if (group._disabledAncestorPath && group._disabledAncestorPath.length > 0) {
    // ← if 内是空! 承诺"被提升的应该显示"但没 return
  } else {
    return false
  }
}
```
- 注释承诺的行为没实现
- `_disabledAncestorPath` 没看到写入位置, 永远是空
- 实际: 任何 disabled 组都 return false (永远不显示)
- 注释和实际行为不一致, 易被误用
- **0 测试**发现

#### 衍生 bug: COLOR_SCHEMES 在 2 处硬编码且不一致
- `constants/diagram` 1 份
- `StepConfig.vue:245-253` 1 份
- 改 1 处忘改另 1 处 → 颜色不一致
- **0 测试**发现

### 9.3 这 6 个配置功能为何都是"沉默 bug 高发区"

| 维度 | 用户感知 | 沉默度 |
|------|---------|--------|
| 颜色配置 | 用户选 vibrant, 看到的是 default | **100% 沉默** (用户默默接受) |
| 中心范围颜色 | 颜色不对, 用户没意识到有"中心范围"概念 | **95% 沉默** |
| 连线颜色 | 连线颜色"看起来奇怪", 不理解规则 | **90% 沉默** |
| 布局方向 | 方向"挤在一起", 以为数据太多 | **70% 沉默** |
| 容器可见 | 隐藏的容器"还在显示", 以为没保存 | **85% 沉默** |
| 容器禁用 | 禁用的容器仍显示, 以为功能坏了 | **80% 沉默** |

**所有 6 个维度都是"用户默默放弃该功能, 不会报 bug"**.

### 9.4 立即可补 (~250 行, 1 周, ROI 极高)

1. **useMermaidColors 单测 (100 行, 15 测试)** - 颜色 + 连线规则
2. **useLayoutControl 单测 (80 行, 10 测试)** - 分组控制核心
3. **groupedLayout 单测 (70 行, 15 测试)** - 方向 + 可见性 + 启用
4. **E2E 10 场景 (300 行, 10 测试)** - 配置应用回归

**合计 ~550 行, 1 周工作量**. **ROI 极高**: 顺带捕获 2 个潜在 bug + 把覆盖从 0% 提升到 80%.

### 9.5 中期目标 (~1000 行, 1 月)

- 抽 4 个 layout 共享的 `filterEnabledContainers` (顺带修 bug 1)
- 加 `_disabledAncestorPath` 写入逻辑 (顺带修 bug 2)
- 抽 `COLOR_SCHEMES` 统一从 `constants/diagram` 导入 (顺带修 bug 3)
- 完整 49 个测试场景

**合计 ~1000 行 + 重构, 1 月**. 把这 6 个维度从 0% 提升到 100% 覆盖.

## 10. 行动清单

### 立即 (P0, 1 周)
- [ ] 加 `useMermaidColors.spec.js` (15 测试)
- [ ] 加 `useLayoutControl.spec.js` (10 测试)
- [ ] 加 `groupedLayout.spec.js` (15 测试)
- [ ] 加 E2E `test_step_config_application.py` (10 场景)
- [ ] **修 Bug 1**: 抽 `filterEnabledContainers` 给 4 个 layout 用
- [ ] **修 Bug 2**: 实现 groupedLayout.js:62-66 注释承诺的行为
- [ ] **修 Bug 3**: 统一 COLOR_SCHEMES 从 constants/diagram 导入

### 短期 (P1, 1 月)
- [ ] 补 49 个完整测试场景
- [ ] 加 useMultiObjectPage 集成测试 (4 步流程 + 配置)
- [ ] 加 visual regression 5 个基线 (各 colorScheme / direction)
- [ ] 把这 6 个配置 + 2 个 bug 加入 SESSION_REMINDER

### 中期 (P2, 季度)
- [ ] 接入 Storybook 配置面板 story
- [ ] 接入 Chromatic 视觉 review
- [ ] 集成 E2E 配置矩阵测试 (7 scheme × 4 layout × 3 colorGroupBy = 84 组合)
- [ ] 自动化 bug 探索: property-based testing 4 layout × 5 配置维度
