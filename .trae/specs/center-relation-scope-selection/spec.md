﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿# 中心范围+关系范围二级选择模式 Spec

## Why

产品经理需要清晰了解"我负责的范围"与"这些范围与其他模块的关系"，现有的单一范围选择模式无法区分"中心范围"和"关系范围"，导致展示结果不够聚焦。

## What Changes

- 新增中心范围选择功能，支持选择业务对象集合作为中心范围
- 新增关系分类树展示功能，基于中心范围展示关系分类结构
- 新增关系范围选择功能，支持按分类选择要展示的关系
- 修改范围选择步骤布局，支持二级选择模式
- 修改业务对象关系表格，基于关系范围选择结果过滤展示

## Impact

- Affected specs: 范围选择步骤、关系过滤功能
- Affected code: StepScope.vue, DataPreview.vue, useDiagramData.js

---

## ADDED Requirements

### Requirement: 中心范围选择

系统应支持用户选择业务对象集合作为中心范围，并基于此展示业务对象列表和服务模块列表。

#### Scenario: 选择中心范围
- **WHEN** 用户在中心范围选择器中选择业务对象
- **THEN** 系统更新中心范围状态
- **AND** 系统展示中心范围的业务对象列表
- **AND** 系统展示中心范围的服务模块列表

#### Scenario: 保存中心范围预设
- **WHEN** 用户点击保存预设按钮
- **THEN** 系统保存当前中心范围配置
- **AND** 用户可快速加载已保存的预设

### Requirement: 关系分类树展示

系统应基于中心范围，展示关系分类树，支持逐级展开。

关系分类结构：
```
## 中心范围内对象关系
├── 跨领域 (n)
│   └── 领域A - 领域B (n)
│       └── 子领域A1 - 子领域B1 (n)
│           └── 服务模块... - 服务模块... (n)
├── 同领域跨子领域 (n)
├── 同子领域跨服务模块 (n)
└── 同服务模块 (n)

## 中心范围与外部对象关系
├── 跨领域 (n)
├── 同领域跨子领域 (n)
├── 同子领域跨服务模块 (n)
└── 同服务模块 (n)
```

#### Scenario: 展示关系分类树
- **WHEN** 用户完成中心范围选择
- **THEN** 系统展示关系分类树
- **AND** 每个节点显示关系数量统计

#### Scenario: 逐级展开关系分类
- **WHEN** 用户点击某个分类节点（如跨领域）
- **THEN** 系统展开显示下一层级（如领域A-领域B）
- **AND** 每个子节点也显示关系数量

### Requirement: 关系范围选择

系统应支持用户通过关系分类树选择要展示的关系范围。

#### Scenario: 选择关系分类
- **WHEN** 用户勾选某个关系分类节点
- **THEN** 系统选中该分类下的所有关系
- **AND** 更新业务对象关系表格展示

#### Scenario: 多选关系分类
- **WHEN** 用户勾选多个关系分类节点
- **THEN** 系统合并展示所有选中的关系

### Requirement: 关系数量统计

系统应在每个关系分类节点旁显示该分类下的关系数量。

#### Scenario: 显示关系数量
- **WHEN** 系统展示关系分类树
- **THEN** 每个节点旁显示该分类下的关系数量
- **AND** 数量实时更新

### Requirement: 选中优先排序

系统应将选中的关系/节点排在前面展示。

#### Scenario: 排序选中项
- **WHEN** 用户选中某些关系
- **THEN** 系统将选中的关系排在列表前面
- **AND** 未选中的关系排在后面

### Requirement: 业务对象关系表格联动

业务对象关系表格应基于关系范围选择结果进行展示。

#### Scenario: 过滤展示关系
- **WHEN** 用户选择关系范围
- **THEN** 业务对象关系表格仅展示选中的关系
- **AND** 表格支持排序和筛选

### Requirement: 步骤导航统计显示

系统应在步骤导航中显示每个步骤的统计信息，帮助用户了解当前选择的数据规模。

#### 统计展示规则

| 步骤 | 显示内容 | 说明 |
|------|----------|------|
| 导入 | X领域 · Y子域 · Z对象 · W关系 | 显示导入的总数据量 |
| 中心 | X领域 · Y子域 · Z对象 | 显示中心范围的完整统计（不含关系） |
| 关系 | +X领域 · +Y子域 · +Z对象 · +W关系 | 显示相比中心步骤新增的统计（带+前缀） |
| 类型 | X领域 · Y子域 · Z对象 · W关系 | 显示总数统计（中心+外部） |
| 配置 | 根据图表类型显示 | 业务对象图：服务模块、对象、关系；服务模块图：服务模块、模块关系 |
| 展示 | 不显示 | 最终展示步骤不显示统计 |

#### 显示条件
- 只有当业务对象数量大于0时才显示统计
- 配置步骤检查服务模块、对象、关系、模块关系任一有值即显示

#### 统计计算规则

1. **中心步骤统计**：基于用户当前选择的中心范围（`selectedScope`）计算，显示领域、子域、对象数量（不含关系）

2. **关系步骤统计（增量）**：
   - 领域、子域、服务模块、业务对象：基于外部关联的业务对象计算（不在中心范围内的关联对象）
   - 关系数量：显示总关系数（包含中心范围内部的关系）

3. **类型步骤统计（总数）**：基于中心范围和外部关联的并集计算

4. **配置步骤统计**：根据选择的图表类型显示
   - 业务对象图：服务模块数、业务对象数、对象关系数
   - 服务模块图：服务模块数、服务模块关系数

#### Scenario: 显示步骤统计
- **WHEN** 用户完成数据导入
- **THEN** 步骤导航显示各步骤的统计信息
- **AND** 统计随用户选择实时更新

## REMOVED Requirements

### Requirement: 关系方向性

**Reason**: 暂不考虑关系方向性（主动/被动关系区分），简化首版实现。

**Migration**: 后续版本可扩展此功能。

---

## 3. 技术设计

### 3.1 数据结构

#### 中心范围数据结构

```typescript
interface CenterScope {
  id: string;                    // 范围唯一标识
  name: string;                  // 范围名称
  businessObjectCodes: string[]; // 选中的业务对象编码列表
  createdAt: Date;               // 创建时间
  updatedAt: Date;               // 更新时间
}
```

#### 关系分类树节点数据结构

```typescript
interface RelationCategoryNode {
  id: string;                    // 节点唯一标识
  name: string;                  // 节点名称
  level: 'category' | 'domain' | 'subdomain' | 'serviceModule' | 'businessObject';
  count: number;                 // 该分类下的关系数量
  children?: RelationCategoryNode[]; // 子节点
  relationCodes?: string[];      // 该节点包含的关系编码（叶子节点）
  isSelected?: boolean;          // 是否选中
  isExpanded?: boolean;          // 是否展开
}
```

#### 关系分类类型

```typescript
type RelationCategoryType = 
  | 'cross-domain'              // 跨领域
  | 'same-domain-cross-subdomain' // 同领域跨子领域
  | 'same-subdomain-cross-module' // 同子领域跨服务模块
  | 'same-module';              // 同服务模块

type RelationScopeType = 
  | 'internal'                  // 中心范围内
  | 'external';                 // 中心范围与外部
```

### 3.2 关系分类算法

```javascript
function classifyRelation(relation, centerScope, businessObjects) {
  const sourceBo = businessObjects.find(bo => bo.code === relation.sourceCode);
  const targetBo = businessObjects.find(bo => bo.code === relation.targetCode);
  
  const sourceInCenter = centerScope.includes(relation.sourceCode);
  const targetInCenter = centerScope.includes(relation.targetCode);
  
  // 判断关系范围类型
  const scopeType = (sourceInCenter && targetInCenter) ? 'internal' : 'external';
  
  // 判断关系分类类型
  let categoryType;
  if (sourceBo.domain !== targetBo.domain) {
    categoryType = 'cross-domain';
  } else if (sourceBo.subDomain !== targetBo.subDomain) {
    categoryType = 'same-domain-cross-subdomain';
  } else if (sourceBo.serviceModule !== targetBo.serviceModule) {
    categoryType = 'same-subdomain-cross-module';
  } else {
    categoryType = 'same-module';
  }
  
  return { scopeType, categoryType };
}
```

### 3.3 组件设计

#### 新增组件

| 组件 | 职责 |
|------|------|
| CenterScopeSelector.vue | 中心范围选择器，复用现有树形选择逻辑 |
| RelationCategoryTree.vue | 关系分类树组件，支持逐级展开和选择 |
| RelationCategoryNode.vue | 关系分类树节点组件 |

#### 修改组件

| 组件 | 修改内容 |
|------|---------|
| StepScope.vue | 添加二级选择模式的布局和状态管理 |
| DataPreview.vue | 添加关系范围选择Tab，联动业务对象关系表格 |
| useDiagramData.js | 添加中心范围和关系范围的状态管理，添加步骤统计计算 |
| StepNavigator.vue | 添加步骤统计显示功能，支持不同步骤的统计格式化 |

### 3.5 步骤导航统计设计

#### 统计数据结构

```typescript
interface StepStats {
  domains: number;              // 领域数量
  subDomains: number;           // 子领域数量
  serviceModules: number;       // 服务模块数量
  businessObjects: number;      // 业务对象数量
  objectRelations: number;      // 对象关系数量
  serviceModuleRelations?: number; // 服务模块关系数量（用于配置步骤）
}

interface DisplayStats {
  import: StepStats;            // 导入步骤统计
  center: StepStats;            // 中心步骤统计
  external: StepStats;          // 外部关系统计
  incremental: StepStats;       // 增量统计（关系步骤使用）
  total: StepStats;             // 总数统计
  config: {                     // 配置步骤统计（根据图表类型）
    serviceModules?: number;
    businessObjects?: number;
    objectRelations?: number;
    serviceModuleRelations?: number;
  }
}
```

#### 统计计算逻辑

```javascript
// useDiagramData.js

// 中心范围的业务对象编码集合（使用 selectedScope 作为当前选择的中心范围）
const centerBoCodes = computed(() => {
  // 优先使用 selectedScope（当前用户选择的范围）
  // 如果 selectedScope 为空，则使用 centerScope（预设中的中心范围）
  return new Set(selectedScope.value?.length > 0 ? selectedScope.value : (centerScope.value || []));
});

// 外部关联的业务对象编码集合（关系范围中不在中心范围的）
const externalBoCodes = computed(() => {
  const external = new Set();
  relationBoCodes.value.forEach(code => {
    if (!centerBoCodes.value.has(code)) {
      external.add(code);
    }
  });
  return external;
});

const selectedStats = computed(() => {
  const centerStats = calculateStatsForBoCodes(Array.from(centerBoCodes.value));
  const externalStats = calculateStatsForBoCodes(Array.from(externalBoCodes.value));
  const totalStats = calculateStatsForBoCodes(Array.from(selectedBoCodes));
  
  // 计算增量统计（外部关联的业务对象统计）
  // 注意：关系数量需要包含中心范围内部的关系（即总数）
  const incrementalStats = {
    domains: externalStats.domains,                    // 外部关联的领域
    subDomains: externalStats.subDomains,              // 外部关联的子域
    serviceModules: externalStats.serviceModules,      // 外部关联的服务模块
    businessObjects: externalStats.businessObjects,    // 外部关联的业务对象
    objectRelations: totalStats.objectRelations        // 包含中心范围内部的关系
  };
  
  return { 
    import: importStats,           // 导入步骤统计
    center: centerStats,           // 中心步骤统计
    external: externalStats,       // 外部关系统计
    incremental: incrementalStats, // 增量统计（关系步骤使用）
    total: totalStats              // 总数统计（类型步骤使用）
  };
});

// 配置步骤统计根据图表类型计算
const configStats = computed(() => {
  if (chartType.value === 'serviceModule') {
    return {
      serviceModules: totalStats.serviceModules,
      serviceModuleRelations: totalStats.serviceModuleRelations
    };
  } else {
    return {
      serviceModules: totalStats.serviceModules,
      businessObjects: totalStats.businessObjects,
      objectRelations: totalStats.objectRelations
    };
  }
});
```

#### 关键设计决策

1. **centerBoCodes 计算逻辑**：优先使用 `selectedScope`（当前用户选择的范围），如果为空则使用 `centerScope`（预设中的中心范围）。这确保了统计始终基于用户实际选择的数据。

2. **增量统计的领域计算**：直接使用 `externalStats` 的领域统计，而不是 `totalStats - centerStats`。这样能正确反映外部关联业务对象所在的领域。

3. **关系步骤的关系数量**：使用 `totalStats.objectRelations` 而不是 `externalStats.objectRelations`，确保关系步骤显示的关系数量包含中心范围内部的关系。

#### 统计格式化规则

```javascript
// StepNavigator.vue
function formatMinimalStats(stats, index) {
  // 步骤1（中心）：显示领域、子域、对象
  if (index === 1) return `${stats.domains}领域 · ${stats.subDomains}子域 · ${stats.businessObjects}对象`;
  
  // 步骤2（关系）：显示增量（带+前缀）
  if (index === 2) return `+${stats.domains}领域 · +${stats.subDomains}子域 · +${stats.businessObjects}对象 · +${stats.objectRelations}关系`;
  
  // 步骤4（配置）：根据图表类型
  if (index === 4) {
    if (chartType === 'serviceModule') {
      return `${stats.serviceModules}服务模块 · ${stats.serviceModuleRelations}模块关系`;
    } else {
      return `${stats.serviceModules}服务模块 · ${stats.businessObjects}对象 · ${stats.objectRelations}关系`;
    }
  }
  
  // 其他步骤：显示完整统计
  return `${stats.domains}领域 · ${stats.subDomains}子域 · ${stats.businessObjects}对象 · ${stats.objectRelations}关系`;
}
```

### 3.4 状态管理

```javascript
// useDiagramData.js 新增状态
const centerScope = ref([]);           // 中心范围（业务对象编码数组）
const centerScopePresets = ref([]);    // 中心范围预设列表
const relationScope = ref({            // 关系范围选择
  internal: {
    'cross-domain': false,
    'same-domain-cross-subdomain': false,
    'same-subdomain-cross-module': false,
    'same-module': false
  },
  external: {
    'cross-domain': false,
    'same-domain-cross-subdomain': false,
    'same-subdomain-cross-module': false,
    'same-module': false
  }
});
const relationCategoryTree = computed(() => {
  // 基于中心范围计算关系分类树
});
```

---

## 4. 影响分析

### 4.1 影响的文件

| 文件 | 影响类型 | 说明 |
|------|---------|------|
| src/views/AADiagramApp/components/steps/StepScope.vue | 修改 | 添加二级选择布局 |
| src/components/DataPreview.vue | 修改 | 添加关系范围选择Tab |
| src/views/AADiagramApp/composables/useDiagramData.js | 修改 | 添加中心范围和关系范围状态，添加步骤统计计算逻辑 |
| src/views/AADiagramApp/components/StepNavigator.vue | 修改 | 添加步骤统计显示功能 |
| src/views/AADiagramApp/index.vue | 修改 | 添加步骤统计传递逻辑 |
| src/components/CenterScopeSelector.vue | 新增 | 中心范围选择器 |
| src/components/RelationCategoryTree.vue | 新增 | 关系分类树组件 |
| src/components/RelationCategoryNode.vue | 新增 | 关系分类树节点组件 |
| src/services/relationClassifier.js | 新增 | 关系分类算法服务 |

---

## 5. 验收标准

### 5.1 功能验收

#### 中心范围+关系范围选择
- [x] 用户可以选择业务对象集合作为中心范围
- [x] 系统基于中心范围展示业务对象列表和服务模块列表
- [x] 系统展示关系分类树，支持逐级展开
- [x] 用户可以选择关系分类，支持多选
- [x] 业务对象关系表格基于选择结果过滤展示
- [x] 选中的关系排在前面
- [x] 每个分类节点显示关系数量统计

#### 步骤导航统计显示
- [x] 导入步骤显示完整统计（领域、子域、对象、关系）
- [x] 中心步骤显示中心范围统计（领域、子域、对象，不含关系）
- [x] 关系步骤显示增量统计（带+前缀）
- [x] 类型步骤显示总数统计
- [x] 配置步骤根据图表类型显示相应统计
  - [x] 业务对象图：服务模块、对象、关系
  - [x] 服务模块图：服务模块、模块关系
- [x] 展示步骤不显示统计
- [x] 统计随用户选择实时更新

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 大数据量性能问题 | 关系分类计算耗时 | 使用Web Worker后台计算 |
| 用户理解成本 | 二级选择模式较复杂 | 提供引导提示和帮助文档 |
| 状态管理复杂度 | 多个状态联动 | 使用composable封装状态逻辑 |