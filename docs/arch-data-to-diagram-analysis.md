## 目录

1. [一、核心问题：领域和子领域没有编码](#一-核心问题：领域和子领域没有编码)
2. [二、数据模型对比](#二-数据模型对比)
3. [三、数据转换关系（更新版）](#三-数据转换关系（更新版）)
4. [四、用户交互流程](#四-用户交互流程)
5. [五、技术实现要点](#五-技术实现要点)
6. [六、UI设计建议](#六-ui设计建议)
7. [七、测试场景](#七-测试场景)
8. [八、关键注意事项](#八-关键注意事项)
9. [九、实施计划](#九-实施计划)
10. [十、AA图生成页面完整数据流分析](#十-aa图生成页面完整数据流分析)
11. [十一、数据转换完整映射表](#十一-数据转换完整映射表)
12. [十二、实施检查清单](#十二-实施检查清单)

---
# 架构数据管理 → AA图生成 数据转换分析

## 一、核心问题：领域和子领域没有编码

### 1.1 元数据模型分析

| 对象类型 | code 字段 | 说明 |
|---------|----------|------|
| **domain** | `领域编码（预留）` | **可能为空**，描述明确标注"预留" |
| **sub_domain** | `子领域编码（预留）` | **可能为空**，描述明确标注"预留" |
| **service_module** | 有编码 | 实际使用 |
| **business_object** | 有编码 | **业务键**，用于唯一标识 |

### 1.2 AA图数据结构分析

AA图的 `domainProducts` 结构：
```javascript
{
  name: "供应链云",     // 领域名称（不是编码）
  code: undefined,     // 可能为空！
  modules: [
    {
      name: "采购",     // 子领域名称（不是编码）
      code: undefined, // 可能为空！
      submodules: [
        {
          name: "采购申请服务",
          code: "SM_PROC_REQ",  // 服务模块有编码
          businessObjects: [
            { code: "BO_PROC_REQ", name: "采购申请" }  // 业务对象有编码
          ]
        }
      ]
    }
  ]
}
```

**关键结论**：
- AA图的 `centerScope` 是**业务对象编码列表**，不是领域/子领域编码
- 领域和子领域在AA图中通过 `name` 标识，不依赖 `code`
- 转换时必须查询到业务对象层级才能获取编码

---

## 二、数据模型对比

### 2.1 架构数据管理页面

#### 对象树选择
```javascript
// 选中的节点ID集合（格式：{type}_{objectId}）
checkedNodeIds: Set<string>  // 例如: ['domain_1', 'sub_domain_2', 'sm_3']

// 过滤参数
hierarchyFilter: {
  version_id: number,           // 版本ID
  domain_id: number[],          // 领域ID列表
  sub_domain_id: number[],      // 子领域ID列表
  service_module_id: number[],  // 服务模块ID列表
  business_object_id: number[]  // 业务对象ID列表
}
```

#### 关系树选择
```javascript
// 选中的关系类型编码
relationTypeFilter: string[]  // 例如: ['同领域跨子领域', '同子领域跨服务模块']
```

#### 版本信息
```javascript
selectedProductId: number
selectedVersionId: number
```

### 2.2 AA图生成页面

#### 中心范围
```javascript
// 业务对象编码列表（注意：不是领域/子领域编码！）
centerScope: string[]  // 例如: ['BO_PROC_REQ', 'BO_CONTRACT']

// 中心范围标记（可选，用于UI显示）
centerScopeMarkers: Map<string, Object>
```

#### 关系范围
```javascript
// 选中的关系节点ID
selectedRelationNodeIds: string[]

// 关系分类树
relationCategoryTree: Object[]
```

#### 图表类型
```javascript
chartType: 'domain' | 'subdomain' | 'service_module' | 'business_object'
```

#### 数据源
```javascript
previewData: {
  domainProducts: Object[],    // 领域-子领域-服务模块层级结构
  businessObjects: Object[],   // 业务对象列表
  relationships: Object[]      // 关系列表
}
```

---

## 三、数据转换关系（更新版）

### 3.1 架构管理 → AA图 映射表

| 架构管理 | AA图 | 转换逻辑 |
|---------|------|---------|
| `selectedVersionId` | 数据源查询 | 根据版本ID查询所有业务对象和关系 |
| `domain_id[]` | `centerScope` | **查询领域下所有业务对象的code** |
| `sub_domain_id[]` | `centerScope` | **查询子领域下所有业务对象的code** |
| `service_module_id[]` | `centerScope` | **查询服务模块下所有业务对象的code** |
| `business_object_id[]` | `centerScope` | 直接查询业务对象的code |
| `relationTypeFilter[]` | `selectedRelationNodeIds` | 映射关系类型到关系树节点 |

### 3.2 核心转换函数（更新版）

```javascript
/**
 * 将架构管理的过滤条件转换为AA图的centerScope
 * 
 * 关键点：
 * 1. centerScope 是业务对象编码列表，不是领域/子领域编码
 * 2. 领域和子领域可能没有编码，必须查询到业务对象层级
 * 3. 业务对象的 code 字段是业务键，一定存在
 */
async function convertToCenterScope(hierarchyFilter) {
  const { version_id, domain_id, sub_domain_id, service_module_id, business_object_id } = hierarchyFilter
  
  // 1. 如果有业务对象ID，直接查询code
  if (business_object_id?.length > 0) {
    const bos = await api.list('business_object', { 
      version_id,
      id: business_object_id 
    })
    return bos.map(bo => bo.code)
  }
  
  // 2. 如果有服务模块ID，查询服务模块下的业务对象code
  if (service_module_id?.length > 0) {
    const bos = await api.list('business_object', { 
      version_id,
      service_module_id 
    })
    return bos.map(bo => bo.code)
  }
  
  // 3. 如果有子领域ID，查询子领域下的业务对象code
  //    注意：不能使用 sub_domain.code，因为可能为空
  if (sub_domain_id?.length > 0) {
    const bos = await api.list('business_object', { 
      version_id,
      sub_domain_id 
    })
    return bos.map(bo => bo.code)
  }
  
  // 4. 如果有领域ID，查询领域下的业务对象code
  //    注意：不能使用 domain.code，因为可能为空
  if (domain_id?.length > 0) {
    const bos = await api.list('business_object', { 
      version_id,
      domain_id 
    })
    return bos.map(bo => bo.code)
  }
  
  // 5. 如果只有版本ID，查询该版本下所有业务对象code
  if (version_id) {
    const bos = await api.list('business_object', { version_id })
    return bos.map(bo => bo.code)
  }
  
  return []
}

/**
 * 构建AA图的domainProducts结构
 * 
 * 关键点：
 * 1. 领域和子领域只有 name，没有 code（或 code 为空）
 * 2. 服务模块有 name 和 code
 * 3. 业务对象有 code（业务键）
 */
async function buildDomainProductsForDiagram(hierarchyFilter) {
  const { version_id, domain_id, sub_domain_id, service_module_id } = hierarchyFilter
  
  // 1. 查询领域列表
  const domains = await api.list('domain', { version_id, id: domain_id })
  
  // 2. 查询子领域列表
  const subDomains = await api.list('sub_domain', { 
    version_id, 
    domain_id,
    id: sub_domain_id 
  })
  
  // 3. 查询服务模块列表
  const serviceModules = await api.list('service_module', { 
    version_id,
    sub_domain_id,
    id: service_module_id 
  })
  
  // 4. 查询业务对象列表
  const businessObjects = await api.list('business_object', { 
    version_id,
    domain_id,
    sub_domain_id,
    service_module_id 
  })
  
  // 5. 构建层级结构
  const domainProducts = []
  
  domains.forEach(domain => {
    const domainObj = {
      name: domain.name,        // 只有 name，不使用 code
      modules: []
    }
    
    // 找到该领域下的子领域
    const childSubDomains = subDomains.filter(sd => sd.domain_id === domain.id)
    
    childSubDomains.forEach(subDomain => {
      const subDomainObj = {
        name: subDomain.name,   // 只有 name，不使用 code
        submodules: []
      }
      
      // 找到该子领域下的服务模块
      const childServiceModules = serviceModules.filter(sm => sm.sub_domain_id === subDomain.id)
      
      childServiceModules.forEach(sm => {
        // 找到该服务模块下的业务对象
        const childBOs = businessObjects.filter(bo => bo.service_module_id === sm.id)
        
        subDomainObj.submodules.push({
          name: sm.name,
          code: sm.code,        // 服务模块有 code
          businessObjects: childBOs.map(bo => bo.code)  // 业务对象有 code
        })
      })
      
      if (subDomainObj.submodules.length > 0) {
        domainObj.modules.push(subDomainObj)
      }
    })
    
    if (domainObj.modules.length > 0) {
      domainProducts.push(domainObj)
    }
  })
  
  return domainProducts
}

/**
 * 将架构管理的关系类型转换为AA图的关系范围
 */
function convertToRelationScope(relationTypeFilter, relationCategoryTree) {
  // 关系类型到关系树节点的映射
  const typeToNodeMap = {
    '跨领域': 'cross_domain',
    '同领域跨子领域': 'same_domain_cross_subdomain',
    '同子领域跨服务模块': 'same_subdomain_cross_module',
    '同服务模块': 'same_module'
  }
  
  return relationTypeFilter.map(type => typeToNodeMap[type]).filter(Boolean)
}
```

---

## 四、用户交互流程

### 4.1 当前AA图步骤流程
```
StepUpload(0) → StepScope(1) → StepChartType(2) → StepConfig(3) → StepDisplay(4)
     ↓              ↓                ↓
  上传文件     选择中心范围      选择图表类型
               选择关系范围
```

### 4.2 从架构管理跳转的流程
```
架构管理 → 点击"展示图表" → StepChartType(图表类型选择)
                                   ↓
                              StepConfig(配置)
                                   ↓
                              StepDisplay(展示)
```

### 4.3 交互方案

#### 方案A：直接跳转到图表类型选择（推荐）
1. 用户在架构管理选择范围
2. 点击"展示图表"按钮
3. 系统自动：
   - 根据过滤条件查询业务对象和关系数据
   - 构建 centerScope（业务对象编码列表）
   - 构建 previewData（domainProducts结构）
   - 转换关系范围
4. 跳转到AA图的 StepChartType 步骤

#### 方案B：跳转到范围确认页面
1. 用户在架构管理选择范围
2. 点击"展示图表"按钮
3. 系统自动：
   - 查询并构建数据
   - 显示范围确认页面（简化版的StepScope）
4. 用户确认后进入图表类型选择

### 推荐方案：方案A + 混合导航模式

理由：
- 用户已在架构管理中选择了范围，无需重复确认
- 减少操作步骤，提升用户体验
- 保持数据一致性

### 4.4 导航交互设计（关键）

#### 问题分析

从架构管理跳转到AA图步骤3后，用户点击"上一步"应该去哪里？

| 场景 | 问题 |
|------|------|
| 步骤3点击"上一步" | 回到步骤2？但用户没有选择过关系范围 |
| 步骤0-2显示 | 用户可能困惑"我没选过这些" |
| 返回架构管理 | 需要恢复之前的选择状态 |

#### 导航方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A. 完整步骤** | 可回退到步骤1/2修改 | 灵活 | 用户可能困惑 |
| **B. 直接返回** | 上一步直接返回架构管理 | 简洁 | 无法微调范围 |
| **C. 只读确认** | 显示确认页，可进入编辑模式 | 清晰 | 增加页面 |
| **D. 混合模式** | 上一步返回架构管理，但可点击步骤导航修改 | 平衡 | 需要状态标记 |

#### 推荐方案：D. 混合模式（简化版 - 不允许点击预设步骤）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    从架构管理跳转后的导航流程                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  架构数据管理页面                                                            │
│  └─ 点击"展示图表" ──────────────────────────────────────────────┐          │
│                                                                  │          │
│                                                                  ▼          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AA图生成页面                                                         │   │
│  │                                                                      │   │
│  │ 步骤导航: [✓ 导入] [✓ 中心] [✓ 关系] [● 类型] [  配置] [  展示]      │   │
│  │           已完成    已完成   已完成   当前                           │   │
│  │           (禁用)   (禁用)  (禁用)                                    │   │
│  │                                                                      │   │
│  │ ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │ │ 当前步骤: 步骤3 - 图表类型选择                                    │ │   │
│  │ │                                                                  │ │   │
│  │ │ [← 上一步]                              [下一步 →]               │ │   │
│  │ │     │                                        │                  │ │   │
│  │ │     │ 返回架构管理                            │ 进入配置步骤      │ │   │
│  │ │     ▼                                        ▼                  │ │   │
│  │ └─────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  注意：步骤0-2显示为已完成状态，但点击无效（禁用）                             │
│        如需修改范围，需返回架构管理页面                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 核心规则

1. **步骤导航显示**
   - 显示完整6个步骤
   - 步骤0-2显示为"已完成"状态（灰色勾选）
   - 步骤0-2点击无效（禁用状态）

2. **"上一步"按钮行为**
   - 步骤3点击"上一步"：**直接返回架构管理页面**
   - 步骤4/5点击"上一步"：正常回退到上一步骤

3. **返回架构管理**
   - 恢复之前的选择状态（通过路由state或全局状态）

#### 重要说明：对AA图原有流程无影响

**此方案只涉及导航控制变更，不影响AA图原有的数据结构和数据流逻辑：**

| 变更类型 | 是否变更 | 说明 |
|---------|---------|------|
| **数据结构** | ❌ 不变更 | previewData, centerScope, centerScopeMarkers, selectedRelationNodeIds, chartType, diagramData 等结构不变 |
| **数据流逻辑** | ❌ 不变更 | 步骤0→1→2→3→4→5的数据传递逻辑不变 |
| **组件逻辑** | ❌ 不变更 | StepScope, StepConfig, StepDisplay 等组件内部逻辑不变 |
| **导航控制** | ✅ 变更 | 步骤导航点击行为、"上一步"按钮行为有条件变更 |

**变更点仅限于：**
1. 新增 `initFromArchData` 状态标记
2. 步骤导航的 `canGoToStep` 方法增加条件判断
3. "上一步"按钮的 `handlePrev` 方法增加条件判断

#### 实现代码示例

```javascript
// useDiagramSteps.js 扩展
export function useDiagramSteps() {
  const initFromArchData = ref(false)  // 标记是否从架构管理跳转
  
  // 步骤导航点击逻辑（原有逻辑扩展）
  const canGoToStep = (index) => {
    // 架构管理入口：禁用步骤0-2的点击
    if (initFromArchData.value && index < 3) {
      return false
    }
    // 原有逻辑不变
    return index <= currentStep.value + 1 || completedSteps.value.has(index)
  }
  
  // 上一步逻辑（原有逻辑扩展）
  const handlePrev = () => {
    // 架构管理入口 + 步骤3 → 返回架构管理
    if (initFromArchData.value && currentStep.value === 3) {
      router.push({ 
        name: 'ArchDataManagement', 
        state: { restoreSelection: true } 
      })
    } else {
      // 原有逻辑不变
      prevStep()
    }
  }
  
  // 初始化方法 - 从架构管理跳转时调用
  const initFromArchDataManager = () => {
    initFromArchData.value = true
    currentStep.value = 3  // 直接跳到步骤3
  }
  
  // 初始化方法 - Excel导入时调用（原有逻辑不变）
  const resetSteps = () => {
    initFromArchData.value = false
    currentStep.value = 0
    completedSteps.value.clear()
  }
  
  return {
    initFromArchData,
    canGoToStep,
    handlePrev,
    initFromArchDataManager,
    resetSteps,
    // ...
  }
}
```

#### UI 显示效果

```
正常AA图流程（Excel导入）：
[1 导入] → [2 中心] → [3 关系] → [4 类型] → [5 配置] → [6 展示]
    ↓          ↓          ↓
  可点击    可点击      可点击

从架构管理跳转：
[✓ 导入] [✓ 中心] [✓ 关系] [● 类型] [  配置] [  展示]
  禁用     禁用      禁用     当前
  (灰)     (灰)      (灰)

- 已完成步骤：灰色勾选标记，点击无效
- 当前步骤：高亮显示
- 上一步按钮：返回架构管理
```

#### 影响范围总结

| 组件/逻辑 | 是否需要修改 | 修改内容 |
|----------|------------|---------|
| useDiagramSteps.js | ✅ 需要 | 新增状态标记、扩展导航逻辑 |
| StepNavigator.vue | ✅ 需要 | 禁用步骤的样式显示 |
| StepScope.vue | ❌ 不需要 | - |
| StepConfig.vue | ❌ 不需要 | - |
| StepDisplay.vue | ❌ 不需要 | - |
| useDiagramData.js | ❌ 不需要 | - |
| diagramConfigStore | ❌ 不需要 | - |
| 数据结构 | ❌ 不需要 | - |
| 数据流逻辑 | ❌ 不需要 | - |

---

## 五、技术实现要点

### 5.1 数据传递方式

**选项1：URL参数传递**
```javascript
// 架构管理页面
router.push({
  name: 'AADiagram',
  query: {
    version_id: selectedVersionId,
    domain_id: domainIds,
    sub_domain_id: subDomainIds,
    // ...
  }
})
```

**选项2：全局状态传递**
```javascript
// 使用 Pinia store 或 provide/inject
const diagramInitData = {
  versionId: selectedVersionId,
  hierarchyFilter: hierarchyFilter.value,
  relationTypeFilter: relationTypeFilter.value
}

// 存储到全局状态
diagramConfigStore.setInitFromArchData(diagramInitData)
router.push({ name: 'AADiagram' })
```

**推荐：选项2** - 更灵活，支持复杂数据结构

### 5.2 数据查询API

需要新增或复用以下API：

```javascript
// 查询业务对象（带层级信息）
GET /api/v1/business_object?version_id=2&domain_id=1,2

// 查询关系（带层级信息）
GET /api/v1/relationships?version_id=2&domain_id=1,2

// 查询domainProducts结构（用于AA图）
// 新增API：返回完整的层级结构
GET /api/v1/meta/hierarchy/domain_products?version_id=2&domain_id=1,2
```

### 5.3 AA图页面改造

```javascript
// useDiagramData.js 新增初始化方法
async function initFromArchData(archData) {
  const { versionId, hierarchyFilter, relationTypeFilter } = archData
  
  // 1. 查询业务对象和关系数据
  const [bos, rels] = await Promise.all([
    api.list('business_object', { version_id: versionId, ...hierarchyFilter }),
    api.list('relationships', { version_id: versionId, ...hierarchyFilter })
  ])
  
  // 2. 构建 centerScope（业务对象编码列表）
  centerScope.value = bos.map(bo => bo.code)
  
  // 3. 构建 previewData
  //    - domainProducts: 从API查询或前端构建
  //    - businessObjects: bos
  //    - relationships: rels
  previewData.value = await buildPreviewDataFromArchData(versionId, hierarchyFilter)
  
  // 4. 设置关系范围
  if (relationTypeFilter?.length > 0) {
    selectedRelationNodeIds.value = convertToRelationScope(relationTypeFilter)
  }
}

/**
 * 从架构管理数据构建预览数据
 */
async function buildPreviewDataFromArchData(versionId, hierarchyFilter) {
  // 1. 查询所有层级数据
  const [domains, subDomains, serviceModules, businessObjects, relationships] = await Promise.all([
    api.list('domain', { version_id: versionId, ...hierarchyFilter }),
    api.list('sub_domain', { version_id: versionId, ...hierarchyFilter }),
    api.list('service_module', { version_id: versionId, ...hierarchyFilter }),
    api.list('business_object', { version_id: versionId, ...hierarchyFilter }),
    api.list('relationships', { version_id: versionId, ...hierarchyFilter })
  ])
  
  // 2. 构建 domainProducts 结构
  //    注意：领域和子领域只有 name，没有 code
  const domainProducts = buildDomainProductsHierarchy(domains, subDomains, serviceModules, businessObjects)
  
  return {
    domainProducts,
    businessObjects,
    relationships,
    serviceModules
  }
}
```

---

## 六、UI设计建议

### 6.1 架构管理页面新增按钮

```html
<button class="adm-btn chart-btn" @click="handleShowChart" :disabled="!canShowChart">
  <AppIcon name="chart" />
  展示图表
</button>
```

位置：放在"导出"按钮旁边

### 6.2 按钮启用条件
- 已选择版本
- 至少选择了一个领域或更细粒度的节点

---

## 七、测试场景

1. **基本场景**：选择一个领域 → 展示图表 → 验证中心范围正确（业务对象编码列表）
2. **混合选择**：选择多个不同粒度的节点 → 验证合并逻辑正确
3. **关系过滤**：选择关系范围 → 验证关系范围正确传递
4. **空选择**：未选择任何范围 → 按钮禁用
5. **版本切换**：切换版本后 → 清空之前的选择
6. **领域无编码**：选择没有编码的领域 → 验证仍能正确查询业务对象

---

## 八、关键注意事项

### 8.1 领域和子领域编码问题

| 场景 | 错误做法 | 正确做法 |
|------|---------|---------|
| 构建 centerScope | `domain.code` | 查询领域下的业务对象，使用 `bo.code` |
| 构建 domainProducts | `domain.code` 作为标识 | 只使用 `domain.name` 作为标识 |
| 过滤业务对象 | `bo.domain_code === domain.code` | `bo.domain_id === domain.id` 或 `bo.domain === domain.name` |

### 8.2 数据一致性

- 架构管理的 `domain_id` 是数据库ID
- AA图的 `domain.name` 是领域名称
- 转换时需要通过API查询建立映射关系

### 8.3 性能考虑

- 批量查询所有层级数据，避免N+1问题
- 使用 Promise.all 并行查询
- 考虑缓存已查询的数据

---

## 九、实施计划

| 阶段 | 任务 | 工作量 |
|-----|------|-------|
| **阶段1** | 后端API扩展 | 0.5天 |
| - | 新增 `/api/v1/meta/hierarchy/domain_products` API | |
| - | 扩展现有API支持层级过滤参数 | |
| **阶段2** | 前端数据转换 | 1天 |
| - | 实现 `convertToCenterScope` 函数 | |
| - | 实现 `buildDomainProductsForDiagram` 函数 | |
| - | 实现 `initFromArchData` 方法 | |
| **阶段3** | UI交互 | 0.5天 |
| - | 架构管理页面添加"展示图表"按钮 | |
| - | AA图页面支持从架构管理初始化 | |
| **阶段4** | 测试验证 | 0.5天 |
| - | 单元测试 | |
| - | E2E测试 | |
| - | 用户验收测试 | |

**总工作量：2.5天**

---

## 十、AA图生成页面完整数据流分析

### 10.1 整体数据流架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AA图生成页面数据流                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────────┐    ┌───────────────────────────┐   │
│  │ StepUpload  │───>│ useExcelParser  │───>│ previewData               │   │
│  │ (步骤0)     │    │ handleFileUpload│    │ ├─ domainProducts         │   │
│  └─────────────┘    └─────────────────┘    │ ├─ businessObjects        │   │
│                                            │ ├─ serviceModules         │   │
│                                            │ └─ relationships          │   │
│                                            └─────────────┬─────────────┘   │
│                                                          │                  │
│  ┌─────────────────────────────────────────────────────┼──────────────┐   │
│  │ diagramConfigStore (Pinia Store)                    │              │   │
│  │ ├─ centerScope: string[]           ◄────────────────┤ StepScope    │   │
│  │ ├─ centerScopeMarkers: Map         ◄────────────────┤ (步骤1,2)    │   │
│  │ ├─ chartType: string               ◄────────────────┤              │   │
│  │ ├─ colorScheme, colorGroupBy...    ◄────────────────┤ StepChartType│   │
│  │ └─ layoutControlConfig: Object     ◄────────────────┤ (步骤3)      │   │
│  └─────────────────────────────────────────────────────┴──────────────┘   │
│                                                          │                  │
│  ┌─────────────────────────────────────────────────────┼──────────────┐   │
│  │ StepConfig (步骤4)                                  │              │   │
│  │ ├─ CenterDomainSelect / ServiceModuleConfig         │              │   │
│  │ │   └─ 颜色配置、中心范围高亮                        │              │   │
│  │ └─ LayoutSelector                                    │              │   │
│  │     └─ 布局分组控制                                  │              │   │
│  └─────────────────────────────────────────────────────┴──────────────┘   │
│                                                          │                  │
│  ┌─────────────────────────────────────────────────────┼──────────────┐   │
│  │ generateDiagram()                                   │              │   │
│  │ ├─ 过滤业务对象、服务模块、关系                      │              │   │
│  │ ├─ 计算 isCenter 标识                               │              │   │
│  │ ├─ 构建 GroupModel                                  │              │   │
│  │ └─ 生成 diagramData                                 │              │   │
│  └─────────────────────────────────────────────────────┴──────────────┘   │
│                                                          │                  │
│  ┌─────────────────────────────────────────────────────┼──────────────┐   │
│  │ StepDisplay (步骤5)                                 │              │   │
│  │ └─ MermaidComponent                                  │              │   │
│  │     └─ 渲染图表                                      │              │   │
│  └─────────────────────────────────────────────────────┴──────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 核心数据模型结构

#### 10.2.1 previewData（数据源）

```javascript
previewData: {
  // 领域-子领域-服务模块层级结构
  domainProducts: [
    {
      name: "供应链云",           // 领域名称（不是编码）
      code: undefined,           // 可能为空！
      modules: [                  // 子领域列表
        {
          name: "采购",           // 子领域名称（不是编码）
          code: undefined,       // 可能为空！
          submodules: [           // 服务模块列表
            {
              name: "采购申请服务",
              code: "SM_PROC_REQ",  // 服务模块有编码
              businessObjects: ["BO_PROC_REQ", "BO_REQ_ITEM"]  // 业务对象编码列表
            }
          ]
        }
      ]
    }
  ],
  
  // 业务对象列表（扁平化）
  businessObjects: [
    {
      code: "BO_PROC_REQ",        // 业务键，必须存在
      name: "采购申请",
      domain: "供应链云",          // 领域名称
      subDomain: "采购",           // 子领域名称
      serviceModule: "SM_PROC_REQ",  // 服务模块编码
      serviceModuleName: "采购申请服务",
      annotationContent: "",      // 备注内容
      annotationCategory: "info"  // 备注类型
    }
  ],
  
  // 服务模块列表
  serviceModules: [
    {
      code: "SM_PROC_REQ",        // 服务模块编码
      name: "采购申请服务",
      domain: "供应链云",
      subDomain: "采购",
      annotationContent: "",
      annotationCategory: "info"
    }
  ],
  
  // 业务对象关系列表
  relationships: [
    {
      relationCode: "REL_001",    // 关系编码
      sourceCode: "BO_PROC_REQ",  // 源业务对象编码
      targetCode: "BO_CONTRACT",  // 目标业务对象编码
      sourceName: "采购申请",
      targetName: "合同",
      relationDesc: "关联",       // 关系说明
      annotationContent: "",      // 备注内容
      annotationCategory: "info"
    }
  ]
}
```

#### 10.2.2 diagramConfigStore（配置状态）

```javascript
diagramConfigStore: {
  // 图表类型
  chartType: 'businessObject' | 'serviceModule',
  previousChartType: '',
  chartTypeChanged: false,
  
  // 中心范围（核心！）
  centerScope: ['BO_PROC_REQ', 'BO_CONTRACT'],  // 业务对象编码列表
  centerScopeMarkers: {
    domains: Map<string, boolean>,      // 领域名称 -> 是否为中心
    subDomains: Map<string, boolean>,   // 子领域名称 -> 是否为中心
    serviceModules: Map<string, boolean> // 服务模块编码/名称 -> 是否为中心
  },
  
  // 配色配置
  colorScheme: 'default' | 'vibrant' | 'pastel' | ...,
  colorGroupBy: 'domain' | 'subDomain' | 'serviceModule',
  nodeTextColor: 'black',
  centerScopeColor: '#EDEDED',
  centerScopeHighlight: true,
  customColors: {},
  
  // 布局配置
  layoutTemplate: 'default',
  layoutEngine: 'elk' | 'dagre',
  layoutControlConfig: {
    enabled: true,
    overallDirection: 'LR',
    groups: [...],
    engine: 'elk'
  }
}
```

#### 10.2.3 关系分类树结构

```javascript
relationCategoryTree: [
  {
    id: 'internal',              // 内部关系
    label: '内部关系',
    children: [
      {
        id: 'internal-cross-domain',
        label: '跨领域',
        relationCodes: ['REL_001', 'REL_002'],
        count: 2
      },
      {
        id: 'internal-same-domain-cross-subdomain',
        label: '同领域跨子领域',
        relationCodes: ['REL_003'],
        count: 1
      },
      {
        id: 'internal-same-subdomain-cross-module',
        label: '同子领域跨服务模块',
        relationCodes: ['REL_004'],
        count: 1
      },
      {
        id: 'internal-same-module',
        label: '同服务模块',
        relationCodes: ['REL_005'],
        count: 1
      }
    ]
  },
  {
    id: 'external',              // 外部关系
    label: '外部关系',
    children: [...]
  }
]
```

### 10.3 各步骤数据流详解

#### 10.3.1 步骤0：导入（StepUpload）

**输入**：Excel文件

**处理流程**：
```javascript
handleFileUpload(file)
  → parseExcelFile(file)           // 解析Excel
  → parseServiceModules()          // 解析服务模块
  → parseBusinessObjects()         // 解析业务对象
  → parseRelationships()           // 解析关系
  → buildDomainProducts()          // 构建层级结构
  → previewData.value = {...}      // 存储结果
```

**输出**：`previewData`

**步骤导航统计**：
```javascript
stepStats[0] = {
  domains: previewData.domainProducts.length,
  subDomains: 统计所有子领域数量,
  serviceModules: 统计所有服务模块数量,
  businessObjects: 统计所有业务对象数量,
  objectRelations: previewData.relationships.length
}
```

#### 10.3.2 步骤1：中心范围选择（StepScope - center模式）

**输入**：
- `previewData.domainProducts` - 层级树
- `previewData.businessObjects` - 业务对象列表

**核心交互**：
- 用户通过 `CenterScopeSelector` 组件选择业务对象
- 选中的业务对象编码存储到 `centerScope`

**输出**：
```javascript
centerScope = ['BO_PROC_REQ', 'BO_CONTRACT']  // 业务对象编码列表
centerScopeMarkers = {
  domains: Map { "供应链云" => true },
  subDomains: Map { "采购" => true },
  serviceModules: Map { "SM_PROC_REQ" => true }
}
```

**步骤导航统计**：
```javascript
stepStats[1] = {
  domains: 中心范围涉及的领域数,
  subDomains: 中心范围涉及的子领域数,
  serviceModules: 中心范围涉及的服务模块数,
  businessObjects: centerScope.length
}
```

#### 10.3.3 步骤2：关系范围选择（StepScope - relation模式）

**输入**：
- `centerScope` - 中心范围
- `previewData.relationships` - 关系列表
- `previewData.businessObjects` - 业务对象列表

**核心处理**：
```javascript
// 构建关系分类树
relationCategoryTree = buildRelationCategoryTree(
  relationships,
  centerScope,
  businessObjects
)

// 用户选择关系节点
selectedRelationNodeIds = ['internal-cross-domain', 'external-cross-domain']

// 计算关系范围涉及的业务对象编码
relationFilteredBoCodes = 根据选中的关系计算
```

**输出**：
```javascript
selectedRelationNodeIds = ['internal-cross-domain']
relationFilteredBoCodes = ['BO_PROC_REQ', 'BO_CONTRACT', 'BO_VENDOR']  // 包含中心范围 + 关系新增
```

**步骤导航统计**（增量统计）：
```javascript
stepStats[2] = {
  domains: 新增领域数,           // 带+前缀显示
  subDomains: 新增子领域数,
  serviceModules: 新增服务模块数,
  businessObjects: 新增业务对象数,
  objectRelations: 选中的关系数
}
```

#### 10.3.4 步骤3：图表类型选择（StepChartType）

**输入**：无

**核心交互**：
- 用户选择图表类型：`businessObject` 或 `serviceModule`

**输出**：
```javascript
chartType = 'businessObject' | 'serviceModule'
```

**步骤导航统计**（总数统计）：
```javascript
stepStats[3] = {
  domains: 中心+外部总领域数,
  subDomains: 中心+外部总子领域数,
  serviceModules: 中心+外部总服务模块数,
  businessObjects: 中心+外部总业务对象数,
  objectRelations: 选中的关系数
}
```

#### 10.3.5 步骤4：配置（StepConfig）

**输入**：
- `previewData` - 数据源
- `filteredDomainProducts` - 过滤后的层级结构
- `filteredContainers` - 过滤后的容器列表
- `centerScope` - 中心范围
- `centerScopeMarkers` - 中心范围标记

**核心组件**：

1. **CenterDomainSelect / ServiceModuleConfig**
   - 配色方案选择
   - 颜色分组方式
   - 中心范围高亮设置

2. **LayoutSelector**
   - 布局引擎选择
   - 分组控制配置

**输出**：
```javascript
diagramConfig = {
  colorScheme: 'default',
  colorGroupBy: 'domain',
  centerScopeHighlight: true,
  layoutEngine: 'elk',
  layoutControlConfig: {...}
}
```

**步骤导航统计**（根据图表类型不同）：
```javascript
// 业务对象图
stepStats[4] = {
  serviceModules: 服务模块数,
  businessObjects: 业务对象数,
  objectRelations: 关系数
}

// 服务模块图
stepStats[4] = {
  serviceModules: 服务模块数,
  serviceModuleRelations: 服务模块关系数
}
```

#### 10.3.6 步骤5：展示（StepDisplay）

**输入**：
- `diagramData` - 图表数据
- `chartType` - 图表类型
- `annotationConfig` - 配置信息

**核心处理**：
```javascript
generateDiagram() {
  // 1. 计算最终显示范围
  finalBoCodes = centerScope ∪ relationFilteredBoCodes
  
  // 2. 过滤业务对象
  filteredBusinessObjects = businessObjects.filter(bo => finalBoCodes.has(bo.code))
  
  // 3. 计算 isCenter 标识
  filteredBusinessObjects.forEach(bo => {
    bo.isCenter = centerScope.has(bo.code)
  })
  
  // 4. 过滤关系
  filteredRelationships = relationships.filter(rel => 
    finalBoCodes.has(rel.sourceCode) && 
    finalBoCodes.has(rel.targetCode) &&
    selectedRelationCodes.includes(rel.relationCode)
  )
  
  // 5. 构建 GroupModel
  groupModel = GroupModel.fromUserConfig(architectureGroups, userConfig)
  
  // 6. 生成图表数据
  diagramData = buildDiagramData({
    businessObjects: filteredBusinessObjects,
    relationships: filteredRelationships,
    domainProducts: filteredDomainProducts,
    ...
  })
}
```

**输出**：
```javascript
diagramData = {
  nodes: [...],           // 节点列表
  links: [...],           // 连线列表
  containers: [...],      // 容器列表
  mermaidCode: "...",     // Mermaid代码
  _unifiedMermaidCode: "..."  // 统一渲染器代码
}
```

### 10.4 关键计算属性

#### 10.4.1 filteredContainers

```javascript
// 用于配置步骤的容器列表
filteredContainers = computed(() => {
  const finalBoCodes = centerScope ∪ relationFilteredBoCodes
  
  if (chartType === 'serviceModule') {
    // 服务模块图：按子领域分组
    return serviceModules按子领域分组(finalBoCodes)
  } else {
    // 业务对象图：按子领域分组
    return businessObjects按子领域分组(finalBoCodes)
  }
})
```

#### 10.4.2 filteredDomainProducts

```javascript
// 过滤后的层级结构
filteredDomainProducts = computed(() => {
  const finalBoCodes = centerScope ∪ relationFilteredBoCodes
  
  return domainProducts.filter(domain => {
    domain.modules = domain.modules.filter(subDomain => {
      subDomain.submodules = subDomain.submodules.filter(sm => {
        return sm.businessObjects.some(bo => finalBoCodes.has(bo.code))
      })
      return subDomain.submodules.length > 0
    })
    return domain.modules.length > 0
  })
})
```

#### 10.4.3 displayStats

```javascript
// 步骤导航显示的统计信息
displayStats = computed(() => {
  return {
    import: stats,                    // 导入步骤：总数
    center: centerStats,              // 中心步骤：中心范围统计
    external: externalStats,          // 外部关联统计
    incremental: incrementalStats,    // 关系步骤：增量统计
    total: totalStats,                // 类型步骤：总数统计
    config: configStats               // 配置步骤：根据图表类型
  }
})
```

### 10.5 从架构管理跳转需要初始化的数据

| 数据项 | 来源 | 转换逻辑 |
|-------|------|---------|
| `previewData` | API查询 | 根据version_id和hierarchyFilter查询 |
| `centerScope` | API查询 | 查询业务对象的code列表 |
| `centerScopeMarkers` | 前端计算 | 根据centerScope计算 |
| `selectedRelationNodeIds` | 转换 | 从relationTypeFilter映射 |
| `relationCategoryTree` | 前端计算 | 根据previewData和centerScope构建 |
| `chartType` | 默认值 | 'businessObject' |

---

## 十一、数据转换完整映射表

### 11.1 架构管理 → AA图 数据映射

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          架构数据管理页面                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  selectedVersionId: number                                                  │
│  hierarchyFilter: {                                                         │
│    domain_id: number[],                                                     │
│    sub_domain_id: number[],                                                 │
│    service_module_id: number[],                                             │
│    business_object_id: number[]                                             │
│  }                                                                          │
│  relationTypeFilter: string[]                                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          数据转换层                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. API查询业务对象 → 提取 code → centerScope                               │
│  2. API查询所有层级数据 → 构建 previewData                                  │
│  3. 关系类型映射 → selectedRelationNodeIds                                  │
│  4. 计算 centerScopeMarkers                                                 │
│  5. 构建 relationCategoryTree                                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AA图生成页面                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  previewData: {                                                             │
│    domainProducts: [...],                                                   │
│    businessObjects: [...],                                                  │
│    serviceModules: [...],                                                   │
│    relationships: [...]                                                     │
│  }                                                                          │
│  centerScope: string[]  // 业务对象编码列表                                  │
│  selectedRelationNodeIds: string[]                                          │
│  chartType: 'businessObject'                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 关键转换函数签名

```javascript
/**
 * 从架构管理数据初始化AA图
 * @param {Object} archData - 架构管理数据
 * @param {number} archData.versionId - 版本ID
 * @param {Object} archData.hierarchyFilter - 层级过滤条件
 * @param {string[]} archData.relationTypeFilter - 关系类型过滤
 * @returns {Promise<void>}
 */
async function initFromArchData(archData) { ... }

/**
 * 查询业务对象编码列表
 * @param {number} versionId - 版本ID
 * @param {Object} hierarchyFilter - 层级过滤条件
 * @returns {Promise<string[]>} 业务对象编码列表
 */
async function convertToCenterScope(versionId, hierarchyFilter) { ... }

/**
 * 构建预览数据
 * @param {number} versionId - 版本ID
 * @param {Object} hierarchyFilter - 层级过滤条件
 * @returns {Promise<Object>} previewData
 */
async function buildPreviewDataFromArchData(versionId, hierarchyFilter) { ... }

/**
 * 转换关系类型到关系节点ID
 * @param {string[]} relationTypeFilter - 关系类型列表
 * @returns {string[]} 关系节点ID列表
 */
function convertToRelationNodeIds(relationTypeFilter) { ... }
```

---

## 十二、实施检查清单

### 12.1 数据转换检查

- [ ] centerScope 是否正确转换为业务对象编码列表
- [ ] domainProducts 中领域/子领域是否只使用 name
- [ ] businessObjects 是否包含完整的层级信息（domain, subDomain, serviceModule）
- [ ] relationships 是否正确关联业务对象编码
- [ ] centerScopeMarkers 是否正确计算

### 12.2 数据完整性检查

- [ ] previewData.domainProducts 是否完整构建
- [ ] previewData.businessObjects 是否包含所有必要字段
- [ ] previewData.serviceModules 是否包含所有必要字段
- [ ] previewData.relationships 是否包含所有必要字段

### 12.3 UI交互检查

- [ ] 步骤导航统计是否正确显示
- [ ] 配置步骤是否正确接收过滤后的数据
- [ ] 图表展示是否正确渲染
