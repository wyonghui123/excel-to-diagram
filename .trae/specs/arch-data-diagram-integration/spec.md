# 架构数据管理跳转AA图功能 Spec

## Why

用户在架构数据管理页面选择了范围后，需要能够直接跳转到AA图生成页面展示图表，避免重复选择范围，提升用户体验。

## What Changes

- 架构数据管理页面新增"展示图表"按钮
- 实现架构管理数据到AA图数据的转换逻辑
- AA图页面支持从架构管理跳转的初始化
- 导航控制：从架构管理跳转时，步骤0-2禁用点击，步骤3的"上一步"返回架构管理

## Impact

- Affected specs: 
  - architecture-data-management
  - center-relation-scope-selection
- Affected code:
  - `src/views/AADiagramApp/composables/useDiagramSteps.js`
  - `src/views/AADiagramApp/composables/useDiagramData.js`
  - `src/views/AADiagramApp/components/StepNavigator.vue`
  - `src/stores/diagramConfigStore.js`
  - 架构数据管理页面（新增按钮）

---

## ADDED Requirements

### Requirement: 数据转换

系统 SHALL 将架构管理的过滤条件转换为AA图所需的数据结构。

#### Scenario: 领域ID转换为centerScope
- **GIVEN** 用户在架构管理选择了领域ID列表
- **WHEN** 系统执行数据转换
- **THEN** 系统查询该领域下所有业务对象的code，存入centerScope

#### Scenario: 子领域ID转换为centerScope
- **GIVEN** 用户在架构管理选择了子领域ID列表
- **WHEN** 系统执行数据转换
- **THEN** 系统查询该子领域下所有业务对象的code，存入centerScope

#### Scenario: 服务模块ID转换为centerScope
- **GIVEN** 用户在架构管理选择了服务模块ID列表
- **WHEN** 系统执行数据转换
- **THEN** 系统查询该服务模块下所有业务对象的code，存入centerScope

#### Scenario: 业务对象ID转换为centerScope
- **GIVEN** 用户在架构管理选择了业务对象ID列表
- **WHEN** 系统执行数据转换
- **THEN** 系统直接查询业务对象的code，存入centerScope

#### Scenario: 关系类型转换为关系节点ID
- **GIVEN** 用户在架构管理选择了关系类型过滤
- **WHEN** 系统执行数据转换
- **THEN** 系统将关系类型映射为AA图的关系节点ID

### Requirement: previewData构建

系统 SHALL 根据架构管理的过滤条件构建AA图的previewData。

#### Scenario: 构建domainProducts
- **GIVEN** 架构管理的过滤条件
- **WHEN** 系统构建previewData
- **THEN** domainProducts包含领域-子领域-服务模块层级结构
- **AND** 领域和子领域只使用name属性（不使用code，因为可能为空）
- **AND** 服务模块和业务对象使用code属性

#### Scenario: 构建businessObjects列表
- **GIVEN** 架构管理的过滤条件
- **WHEN** 系统构建previewData
- **THEN** businessObjects包含完整的层级信息（domain, subDomain, serviceModule）

#### Scenario: 构建relationships列表
- **GIVEN** 架构管理的过滤条件
- **WHEN** 系统构建previewData
- **THEN** relationships包含业务对象关系列表

### Requirement: 导航控制

系统 SHALL 根据入口来源控制导航行为。

#### Scenario: Excel导入入口
- **GIVEN** 用户通过Excel文件导入进入AA图
- **WHEN** 用户操作步骤导航
- **THEN** 步骤0-5正常显示和点击
- **AND** "上一步"按钮正常回退到上一步骤

#### Scenario: 架构管理跳转入口 - 步骤导航显示
- **GIVEN** 用户从架构管理跳转到AA图
- **WHEN** AA图页面加载完成
- **THEN** 步骤0-2显示为"已完成"状态（灰色勾选）
- **AND** 步骤0-2点击无效（禁用状态）
- **AND** 当前步骤为步骤3（图表类型选择）

#### Scenario: 架构管理跳转入口 - 上一步按钮
- **GIVEN** 用户从架构管理跳转到AA图
- **AND** 当前步骤为步骤3
- **WHEN** 用户点击"上一步"按钮
- **THEN** 系统返回架构管理页面
- **AND** 恢复之前的选择状态

#### Scenario: 架构管理跳转入口 - 步骤4/5上一步
- **GIVEN** 用户从架构管理跳转到AA图
- **AND** 当前步骤为步骤4或步骤5
- **WHEN** 用户点击"上一步"按钮
- **THEN** 系统正常回退到上一步骤

### Requirement: 架构管理页面按钮

系统 SHALL 在架构数据管理页面提供"展示图表"按钮。

#### Scenario: 按钮显示
- **GIVEN** 用户在架构数据管理页面
- **WHEN** 页面加载完成
- **THEN** 显示"展示图表"按钮

#### Scenario: 按钮启用条件
- **GIVEN** 用户在架构数据管理页面
- **WHEN** 用户未选择任何范围
- **THEN** "展示图表"按钮禁用

#### Scenario: 按钮点击
- **GIVEN** 用户已选择范围
- **WHEN** 用户点击"展示图表"按钮
- **THEN** 系统执行数据转换
- **AND** 跳转到AA图的步骤3

---

## MODIFIED Requirements

### Requirement: useDiagramSteps扩展

系统 SHALL 支持从架构管理跳转的初始化。

#### Scenario: 初始化标记
- **GIVEN** 系统需要区分入口来源
- **WHEN** 从架构管理跳转时
- **THEN** initFromArchData状态标记为true

#### Scenario: 步骤导航点击控制
- **GIVEN** initFromArchData为true
- **WHEN** 用户点击步骤0-2
- **THEN** 点击无效（canGoToStep返回false）

### Requirement: useDiagramData扩展

系统 SHALL 支持从架构管理数据初始化。

#### Scenario: 初始化方法
- **GIVEN** 架构管理传递的数据
- **WHEN** 调用initFromArchData方法
- **THEN** 系统查询并构建previewData
- **AND** 设置centerScope
- **AND** 计算centerScopeMarkers
- **AND** 构建relationCategoryTree

---

## REMOVED Requirements

无移除的需求。

---

## 关键注意事项

### 领域和子领域编码问题

| 对象类型 | code字段 | 处理方式 |
|---------|---------|---------|
| domain | 可能为空 | 只使用name属性 |
| sub_domain | 可能为空 | 只使用name属性 |
| service_module | 有编码 | 使用code属性 |
| business_object | 有编码 | 使用code属性（业务键） |

### 对AA图原有流程无影响

此方案只涉及导航控制变更，不影响AA图原有的数据结构和数据流逻辑：

| 变更类型 | 是否变更 |
|---------|---------|
| 数据结构 | ❌ 不变更 |
| 数据流逻辑 | ❌ 不变更 |
| 组件逻辑 | ❌ 不变更 |
| 导航控制 | ✅ 变更 |
