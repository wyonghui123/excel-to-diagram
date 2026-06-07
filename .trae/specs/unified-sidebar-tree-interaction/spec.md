# 统一左侧树形选择交互架构 Spec

## Why

当前架构数据管理模块的"层级数据"和"业务关系"两个 Tab 使用不同的左侧交互组件（TreeNavigator vs DynamicFilter），交互模式不统一，且切换 Tab 时选择状态丢失。用户需要一种统一的交互模式：先在领域树中选择范围，再根据 Tab 切换查看对象数据或关系数据。

## What Changes

- **统一左侧面板**：两个 Tab 共用同一个左侧面板容器，内容根据 Tab 动态切换
- **领域树保持不变**：层级数据 Tab 继续使用 TreeNavigator
- **新增关系范围树**：业务关系 Tab 使用基于领域树选择动态生成的关系范围树，替换现有 DynamicFilter
- **跨 Tab 状态联动**：领域树的选择结果作为关系范围树的输入，关系范围树动态生成
- **上下文提示**：关系范围树顶部显示"基于选择的领域"提示
- **快捷切换入口**：领域树底部增加"查看关系"快捷按钮
- **空状态引导**：未选择领域时关系范围树显示引导提示
- **双向联动**：关系树节点支持跳转到对象视图

## Impact

- Affected specs: relation-management-view-extension, center-relation-scope-selection
- Affected code:
  - `src/views/ArchDataManageApp/index.vue` - 主框架左侧面板重构
  - `src/views/ArchDataManageApp/components/DynamicFilter.vue` - 替换为关系范围树
  - `src/views/ArchDataManageApp/components/TreeNavigator.vue` - 增加选择状态持久化和快捷按钮
  - `src/views/ArchDataManageApp/stores/archDataStore.js` - 增加跨 Tab 共享选择状态
  - 新增 `src/views/ArchDataManageApp/components/RelationScopeTree.vue` - 关系范围树组件
  - 新增 `src/views/ArchDataManageApp/composables/useRelationScopeTree.js` - 关系范围树数据计算逻辑

---

## ADDED Requirements

### Requirement: 统一左侧面板容器

系统 SHALL 提供统一的左侧面板容器，两个 Tab 共用同一布局区域，内容根据当前 Tab 动态切换。

#### Scenario: 层级数据 Tab 左侧
- **WHEN** 用户选择"层级数据" Tab
- **THEN** 左侧面板显示领域树（TreeNavigator）
- **AND** 领域树保持当前选择状态

#### Scenario: 业务关系 Tab 左侧
- **WHEN** 用户选择"业务关系" Tab
- **THEN** 左侧面板显示关系范围树
- **AND** 关系范围树基于领域树的选择动态生成

### Requirement: 关系范围树

系统 SHALL 提供关系范围树组件，基于领域树中选择的领域动态生成关系分类结构。

关系范围树结构：
```
📌 基于选择: 供应链云、采购云
├─ 中心范围关系 (n)
│   └─ [展开后显示选中领域内部的关系分类]
├─ 跨领域 (n)
│   ├─ 供应链云 → 采购云 (n)
│   │   ├─ 采购供应 → 供应商管理 (n)
│   │   └─ ...
│   └─ 供应链云 → 财务云 (n)
├─ 同领域跨子域 (n)
│   ├─ 供应链云 (n)
│   │   ├─ 采购供应 → 销售服务 (n)
│   │   └─ ...
│   └─ ...
└─ 同子域跨服务模块 (n)
    ├─ 供应链云 / 采购供应 (n)
    │   ├─ 采购管理 → 供应商管理 (n)
    │   └─ ...
    └─ ...
```

#### Scenario: 基于领域选择生成关系树
- **WHEN** 用户在领域树中选择了"供应链云"和"采购云"
- **THEN** 关系范围树基于这两个领域的关系数据动态生成
- **AND** 每个节点显示关系数量统计

#### Scenario: 逐级展开关系分类
- **WHEN** 用户点击"跨领域"节点
- **THEN** 展开显示领域对（如"供应链云 → 采购云"）
- **AND** 继续展开显示子领域对、服务模块对

#### Scenario: 选择关系范围
- **WHEN** 用户勾选某个关系范围节点
- **THEN** 右侧关系列表仅展示该范围内的关系
- **AND** 支持多选合并展示

#### Scenario: 默认展开策略
- **WHEN** 关系范围树生成
- **THEN** 默认只展开第一层（中心范围/跨领域/同领域跨子域/同子域跨服务模块）
- **AND** 子节点默认折叠

### Requirement: 跨 Tab 选择状态联动

系统 SHALL 在领域树和关系范围树之间建立联动关系，领域树的选择决定关系范围树的内容。

#### Scenario: 领域选择影响关系树
- **WHEN** 用户在领域树中选中/取消选中某个领域
- **THEN** 切换到业务关系 Tab 时，关系范围树基于最新选择重新生成

#### Scenario: 切换 Tab 保留领域选择
- **WHEN** 用户从层级数据 Tab 切换到业务关系 Tab
- **THEN** 领域树的选择状态保留
- **AND** 关系范围树基于该选择生成

### Requirement: 上下文提示

系统 SHALL 在关系范围树顶部显示当前基于哪些领域选择生成的上下文信息。

#### Scenario: 显示上下文提示
- **WHEN** 关系范围树显示
- **THEN** 顶部显示"📌 基于选择: 供应链云、采购云"
- **AND** 领域名称从领域树选择状态获取

#### Scenario: 无选择时的提示
- **WHEN** 领域树中未选择任何领域
- **THEN** 关系范围树区域显示空状态引导

### Requirement: 快捷切换入口

系统 SHALL 在领域树底部提供"查看关系"快捷按钮，一键切换到业务关系 Tab。

#### Scenario: 点击查看关系
- **WHEN** 用户在领域树中选择了至少一个领域
- **THEN** 领域树底部显示"查看这些领域的关系"按钮
- **AND** 点击后自动切换到业务关系 Tab

#### Scenario: 未选择领域时
- **WHEN** 领域树中未选择任何领域
- **THEN** "查看关系"按钮禁用

### Requirement: 空状态引导

系统 SHALL 在用户未选择领域时，在关系范围树区域显示引导提示。

#### Scenario: 未选择领域
- **WHEN** 用户切换到业务关系 Tab 但未在领域树中选择任何领域
- **THEN** 显示"⚠️ 请先在层级数据中选择领域"提示
- **AND** 提供"跳转到层级数据"按钮

### Requirement: 双向联动跳转

系统 SHALL 支持从关系范围树节点跳转到对象视图。

#### Scenario: 跳转到源对象
- **WHEN** 用户在关系范围树中右键点击或长按某个关系范围节点
- **THEN** 显示"查看源对象"和"查看目标对象"选项
- **AND** 点击后切换到层级数据 Tab 并定位到对应对象

## MODIFIED Requirements

### Requirement: 主框架左侧面板重构

原 `index.vue` 中左侧面板根据 Tab 条件渲染 TreeNavigator 或 DynamicFilter，修改为统一面板容器 + 动态内容切换。

原代码：
```vue
<TreeNavigator v-if="activeTab === 'hierarchy'" ... />
<DynamicFilter v-else-if="activeTab === 'relationship'" ... />
```

修改为：
```vue
<aside class="adm-sidebar">
  <TreeNavigator v-show="activeTab === 'hierarchy'" ... />
  <RelationScopeTree v-show="activeTab === 'relationship'" ... />
</aside>
```

使用 `v-show` 而非 `v-if` 确保两个组件都保持挂载状态，切换时不丢失内部状态。

### Requirement: archDataStore 状态扩展

`archDataStore.js` SHALL 增加以下共享状态：

```javascript
// 新增状态
selectedDomains: [],        // 领域树中选中的领域列表
selectedSubDomains: [],     // 领域树中选中的子领域列表
relationScopeSelection: [], // 关系范围树中选中的范围
```

## REMOVED Requirements

### Requirement: DynamicFilter 在业务关系 Tab 中的使用

**Reason**: DynamicFilter 的表单式筛选交互被关系范围树替代，关系范围树提供更直观的层级化关系选择体验。

**Migration**: DynamicFilter 组件保留但不再在业务关系 Tab 中使用，未来可用于其他需要表单式筛选的场景。

---

## 技术设计

### 数据结构

#### 关系范围树节点

```typescript
interface RelationScopeNode {
  id: string
  name: string
  level: 'root' | 'scope' | 'category' | 'domain-pair' | 'subdomain-pair' | 'module-pair'
  count: number
  children?: RelationScopeNode[]
  sourceDomain?: string
  targetDomain?: string
  sourceSubDomain?: string
  targetSubDomain?: string
  sourceModule?: string
  targetModule?: string
  isSelected?: boolean
  isExpanded?: boolean
}
```

### 关系范围树生成算法

```javascript
function buildRelationScopeTree(selectedDomains, allRelationships, businessObjects) {
  const tree = { children: [] }

  // 1. 筛选出涉及选中领域的关系
  const filteredRels = allRelationships.filter(rel => {
    const sourceBo = businessObjects.find(bo => bo.code === rel.sourceCode)
    const targetBo = businessObjects.find(bo => bo.code === rel.targetCode)
    return selectedDomains.some(d =>
      d === sourceBo?.domain || d === targetBo?.domain
    )
  })

  // 2. 分类：中心范围 vs 外部
  const centerBoCodes = new Set(
    businessObjects
      .filter(bo => selectedDomains.includes(bo.domain))
      .map(bo => bo.code)
  )

  const internalRels = filteredRels.filter(rel =>
    centerBoCodes.has(rel.sourceCode) && centerBoCodes.has(rel.targetCode)
  )
  const externalRels = filteredRels.filter(rel =>
    centerBoCodes.has(rel.sourceCode) || centerBoCodes.has(rel.targetCode)
  )

  // 3. 按分类维度分组
  // 中心范围关系
  tree.children.push(buildCategorySubtree('中心范围关系', internalRels, businessObjects))

  // 外部关系按分类维度
  const crossDomain = externalRels.filter(rel => sourceBo.domain !== targetBo.domain)
  const sameDomainCrossSub = externalRels.filter(rel =>
    sourceBo.domain === targetBo.domain && sourceBo.subDomain !== targetBo.subDomain
  )
  const sameSubCrossModule = externalRels.filter(rel =>
    sourceBo.subDomain === targetBo.subDomain && sourceBo.serviceModule !== targetBo.serviceModule
  )

  if (crossDomain.length) tree.children.push(buildCategorySubtree('跨领域', crossDomain, businessObjects))
  if (sameDomainCrossSub.length) tree.children.push(buildCategorySubtree('同领域跨子域', sameDomainCrossSub, businessObjects))
  if (sameSubCrossModule.length) tree.children.push(buildCategorySubtree('同子域跨服务模块', sameSubCrossModule, businessObjects))

  return tree
}
```

### 组件设计

| 组件 | 职责 | 状态 |
|------|------|------|
| RelationScopeTree.vue | 关系范围树组件，支持展开/折叠/选择 | 新增 |
| useRelationScopeTree.js | 关系范围树数据计算 composable | 新增 |
| TreeNavigator.vue | 领域树，增加选择状态持久化和快捷按钮 | 修改 |
| archDataStore.js | 增加跨 Tab 共享选择状态 | 修改 |
| index.vue | 左侧面板重构为统一容器 | 修改 |

### 布局设计

```
┌───────────────────────────────────────────────────────┐
│  返回  │  架构数据管理    │ 搜索  │ 导入 导出 刷新    │
├────────┬──────────────────────────────────────────────┤
│        │  [层级数据]  [业务关系]                        │
│        ├──────────────────────────────────────────────┤
│ (动态) │                                              │
│        │                                              │
│ Tab1:  │  右侧内容区                                   │
│ 领域树  │  对象列表 / 关系列表                          │
│        │                                              │
│ Tab2:  │                                              │
│ 关系   │                                              │
│ 范围树  │                                              │
│        │                                              │
└────────┴──────────────────────────────────────────────┘
```
