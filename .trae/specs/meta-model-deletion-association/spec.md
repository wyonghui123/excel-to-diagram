# 管理维度权限配置界面 Spec

## Why

当前角色权限配置界面采用技术导向的扁平化设计，用户需要逐个配置权限规则，配置效率低（15-30分钟/角色）、易出错（错误率15-20%），且无法直观展示管理维度（对象类型）的层级关系和影响范围。

需要重构为面向业务视角的管理维度配置界面，基于现有的 `permission_rule` 表，提供"选择管理维度→配置条件规则→实时预览影响范围"的配置流程，将配置时间缩短至 3-5 分钟，错误率降至 <5%。

## What Changes

* **复用现有数据模型**：`permission_rule` 表（resource\_type + condition + inherit\_to\_children + propagate\_to\_parents）

* **新增默认管理维度**：产品（product）作为默认管理维度

* **新增核心引擎**：`ManagementDimensionEngine`（基于 permission\_rule 计算影响范围）

* **新增前端组件**：

  * `ManagementDimensionSelector.vue` - 管理维度选择器（列表/卡片形式）

  * `ConditionRuleEditor.vue` - 条件规则编辑器（支持 value help）

  * `ImpactPreview.vue` - 影响范围实时预览（向上父关联 + 向下级联）

* **新增 API 端点**：5 个核心端点（管理维度元数据 + 影响计算）

* **复用已有能力**：`EnumCacheManager`（缓存权限规则计算结果）

## Impact

* **Affected specs**:

  * `auth-permission-system` - 权限系统基础架构

  * `permission-unified-semantic-migration` - 权限语义统一

  * `condition-based-permission` - 条件权限服务（已实现 permission\_rule）

* **Affected code**:

  * `src/views/SystemManagement/RolePermissionCenter.vue` - 重构为管理维度配置界面

  * `meta/services/` - 新增 `management_dimension_engine.py`

  * `meta/schemas/permission_rule.yaml` - 复用现有模型（resource\_type 包含 product）

  * `meta/core/enums/cache_manager.py` - 复用缓存能力

## ADDED Requirements

### Requirement: 管理维度元数据管理

系统 SHALL 提供管理维度（对象类型）的元数据管理功能，支持默认维度和自定义维度的统一管理。

#### Scenario: 获取默认管理维度列表

* **WHEN** 用户访问角色权限配置界面

* **THEN** 系统显示默认的管理维度列表：

  * 产品（product）

  * 版本（version）

  * 领域（domain）

  * 子领域（sub\_domain）

  * 服务模块（service\_module）

  * 业务对象（business\_object）

  * 关系（relationship）

* **AND** 每个维度显示其名称、描述、图标

* **AND** 维度列表支持搜索、过滤

#### Scenario: 添加自定义管理维度

* **WHEN** 管理员在"管理维度配置"页面添加新的维度"成本中心（cost\_center）"

* **THEN** 系统将该维度添加到可用维度列表

* **AND** 用户可以在权限配置界面选择该维度

* **AND** 维度定义存储在元数据配置中（YAML 或数据库）

#### Scenario: 管理维度元数据来源

* **WHEN** 系统初始化时

* **THEN** 从 `hierarchies.yaml` 和 `permission_rule.yaml` 中读取管理维度定义

* **AND** 自动生成维度选择器

* **AND** 维度变更时无需修改代码

### Requirement: 条件规则编辑器

系统 SHALL 提供条件规则编辑器，支持用户配置基于管理维度的条件表达式，并提供 value help 选择实例值。

#### Scenario: 配置领域维度条件规则

* **WHEN** 用户选择"领域"管理维度

* **AND** 点击"添加条件规则"

* **THEN** 显示条件规则编辑器，包含：

  * 条件字段选择器（如：id, name, code, domain\_type）

  * 操作符选择器（=, !=, IN, NOT IN, LIKE, >, <）

  * 值输入框或 value help（选择具体实例）

* **AND** value help 显示所有领域的实例列表（如：供应链、财务、人力资源）

* **AND** 支持多选（如：选择"供应链"和"财务"）

#### Scenario: 配置产品维度条件规则

* **WHEN** 用户选择"产品"管理维度

* **AND** 配置条件："product\_id IN (1, 2, 3)"

* **THEN** 系统保存该条件规则到 `permission_rule` 表

* **AND** resource\_type = 'product'

* **AND** condition = 'product\_id IN (1, 2, 3)'

#### Scenario: 配置权限级别和继承规则

* **WHEN** 用户配置完条件表达式后

* **THEN** 可以选择权限级别（read/write/admin）

* **AND** 可以配置向下继承（inherit\_to\_children）

* **AND** 可以配置向上传播（propagate\_to\_parents）

* **AND** 可以配置是否禁止（is\_denied）

#### Scenario: Value Help 显示实例列表

* **WHEN** 用户点击条件值输入框的 value help 按钮

* **THEN** 弹出实例选择对话框

* **AND** 显示该管理维度下所有实例的列表（如：所有领域、所有产品）

* **AND** 支持搜索、过滤、分页

* **AND** 支持多选

* **AND** 选择后自动填充到条件表达式

### Requirement: 影响范围实时预览

系统 SHALL 提供影响范围实时预览功能，基于条件规则计算受影响的对象及其父子关联。

#### Scenario: 计算领域维度的影响范围

* **WHEN** 用户配置"领域"维度的条件规则："id IN (1, 2)"

* **AND** 启用"向下继承"（inherit\_to\_children = true）

* **THEN** 系统计算影响范围：

  * 直接影响：2 个领域（ID=1, 2）

  * 向下级联：这 2 个领域下的所有子领域、服务模块、业务对象

  * 向上传播：如果子对象有权限，父对象只读可见

* **AND** 显示统计摘要：

  * 领域：2 个

  * 子领域：6 个

  * 服务模块：15 个

  * 业务对象：45 个

* **AND** 计算延迟 < 100ms

#### Scenario: 查看详细影响对象清单

* **WHEN** 用户点击"查看详细清单"

* **THEN** 显示表格，包含以下列：

  * 对象类型（领域/子领域/服务模块/业务对象）

  * 对象编码、名称

  * 影响方式（直接匹配/向下继承/向上传播）

  * 权限级别（read/write/admin）

* **AND** 支持按对象类型过滤

* **AND** 支持导出 Excel

#### Scenario: 向上父关联计算

* **WHEN** 用户配置"业务对象"维度的条件规则

* **AND** 启用"向上传播"（propagate\_to\_parents = true）

* **THEN** 系统计算受影响的业务对象

* **AND** 自动计算这些业务对象的父对象（服务模块、子领域、领域）

* **AND** 为父对象提供只读可见性

* **AND** 在影响范围预览中标记"向上传播"

#### Scenario: 向下级联计算

* **WHEN** 用户配置"领域"维度的条件规则

* **AND** 启用"向下继承"（inherit\_to\_children = true）

* **THEN** 系统计算受影响的领域

* **AND** 自动计算这些领域的子对象（子领域、服务模块、业务对象）

* **AND** 为子对象继承相同的权限级别

* **AND** 在影响范围预览中标记"向下继承"

### Requirement: 管理维度配置界面布局

系统 SHALL 提供清晰的管理维度配置界面，采用"选择维度→配置规则→预览影响"的三步流程。

#### Scenario: 界面布局

* **WHEN** 用户访问角色权限配置界面

* **THEN** 显示以下区域：

  * **区域 1：管理维度选择器**

    * 显示所有可用的管理维度（列表或卡片形式）

    * 支持搜索、过滤

    * 显示每个维度的规则数量

  * **区域 2：条件规则编辑器**

    * 条件表达式编辑

    * 权限级别选择

    * 继承规则配置

    * Value Help 实例选择

  * **区域 3：影响范围预览**

    * 统计摘要

    * 详细对象清单

    * 向上父关联 + 向下级联展示

  * **区域 4：已配置规则列表**

    * 显示该角色的所有权限规则

    * 支持编辑、删除、启用/禁用

    * 支持排序、过滤

#### Scenario: 选择管理维度

* **WHEN** 用户在区域 1 点击"领域"维度卡片

* **THEN** 区域 2 显示"领域"维度的条件规则编辑器

* **AND** 区域 3 显示该维度已有的规则影响范围

* **AND** 区域 4 高亮显示"领域"维度的规则

#### Scenario: 保存条件规则

* **WHEN** 用户在区域 2 配置完条件规则

* **AND** 点击"保存"

* **THEN** 系统保存规则到 `permission_rule` 表

* **AND** 自动失效该角色的权限缓存

* **AND** 区域 3 实时更新影响范围预览

* **AND** 区域 4 更新规则列表

### Requirement: 权限规则缓存与性能

系统 SHALL 复用 `EnumCacheManager` 缓存权限规则计算结果，确保高性能。

#### Scenario: 缓存权限规则计算结果

* **WHEN** 系统计算某个角色的权限影响范围

* **THEN** 将计算结果缓存到内存（TTL = 300s）

* **AND** 后续相同查询直接从缓存读取

* **AND** 缓存命中时延迟 < 0.1ms

#### Scenario: 规则变更后缓存失效

* **WHEN** 用户修改角色的权限规则

* **THEN** 系统自动失效该角色的权限缓存

* **AND** 下次查询时重新计算

* **AND** 失效操作延迟 < 10ms

#### Scenario: 性能指标

* **WHEN** 系统运行时

* **THEN** 满足以下性能指标：

  * 缓存命中时：权限影响计算 < 0.1ms

  * 首次计算时：权限影响计算 < 100ms

  * 缓存命中率：> 95%

  * 界面响应时间：< 200ms

  * 并发支持：50+ 用户同时配置

## MODIFIED Requirements

### Requirement: 角色权限配置界面布局

现有角色权限配置界面 SHALL 重构为 4 区域布局：

**区域 1：管理维度选择器**

* 显示所有可用的管理维度（产品、版本、领域、子领域等）

* 支持列表或卡片视图切换

* 显示每个维度的规则数量

* 支持搜索、过滤

**区域 2：条件规则编辑器**

* 条件表达式编辑（字段、操作符、值）

* Value Help 实例选择

* 权限级别选择（read/write/admin）

* 继承规则配置（向下继承、向上传播）

* 禁止权配置

**区域 3：影响范围预览**

* 统计摘要（按对象类型分组）

* 详细对象清单（支持展开）

* 影响方式标记（直接匹配/向下继承/向上传播）

* 支持导出

**区域 4：已配置规则列表**

* 显示该角色的所有权限规则

* 支持编辑、删除、启用/禁用

* 支持排序、过滤

* 显示规则的 resource\_type 和 condition

## REMOVED Requirements

### Requirement: 扁平化权限规则配置

**Reason**: 采用管理维度配置替代，提升配置效率和准确性。

**Migration**:

* 现有 `permission_rule` 表数据保持不变

* 新界面提供更好的配置体验

* 向后兼容，现有权限检查逻辑不受影响

### Requirement: 实例级数据权限配置

**Reason**: 统一使用条件型权限，简化权限模型。

**Migration**:

* 已在 `condition-based-permission` spec 中完成迁移

* 本 spec 不涉及实例级权限

