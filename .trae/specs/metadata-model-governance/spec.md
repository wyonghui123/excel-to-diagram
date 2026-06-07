# 元数据模型治理规范 Spec

> **创建日期**: 2026-05-08
> **相关Spec**: meta-model-driven-filters, p1-phase-b-analytics-aggregation, unified-meta-model-design
> **参考**: SAP One Domain Model, SAP CDS Annotation System, OpenAPI Specification

---

## 一、Why

### 问题背景

在实现 `cross_table_filters`（跨表关联过滤）功能时，暴露了元数据模型治理的严重缺陷：

#### 问题 1：配置契约不清晰

```yaml
# business_object.yaml - 跨表过滤配置
cross_table_filters:
  - id: annotation_category
    ui:
      options_source: enum
      enum_type: annotation_category  # 这个 ID 从哪来？没有文档说明
```

**现象**：
- 开发者不知道 `annotation_category` 枚举类型 ID 从何而来
- 没有验证机制检查这个 ID 是否存在
- 配置错误只能在运行时通过调试发现

#### 问题 2：API 路径约定混乱

| 模块 | API 路径 | 返回格式 |
|------|----------|---------|
| 元对象 API | `/enum-types/<id>` | `data.values` |
| 枚举 API | `/enum-types/<id>/values` | `data.data` (嵌套) |
| 代码中使用 | `/api/v1/enums/<id>` | ❌ 错误 |

**根因**：不同模块的 API 设计者各自为政，没有统一的 API 规范文档

#### 问题 3：缺乏配置-消费-验证闭环

```javascript
// useGlobalFilters.js - 闭着眼睛写
options: ctf.ui?.options_source === 'enum' ? [] : [],  // 初始为空
```

**问题**：
- ❌ 没有检查 `enum_type` 是否存在
- ❌ 没有验证 API 路径是否正确
- ❌ 没有处理 API 返回结构的差异
- ❌ 没有添加任何调试/验证逻辑

#### 问题 4：代码复用意识不足

**现象**：
- 项目中已经有 `EnumSelect` 组件和枚举加载逻辑
- 选择重新写一套枚举加载代码
- 结果引入了 bug

---

### 目标

建立**元数据模型治理体系**，确保：

1. ✅ **配置契约明确化** - 所有元数据配置都有清晰的类型定义和约束
2. ✅ **API 规范统一化** - 所有 API 遵循统一的路径和响应格式规范
3. ✅ **验证机制完善化** - 配置从定义到消费全程可验证
4. ✅ **代码复用最大化** - 通用逻辑封装为可复用服务

---

## 二、What Changes

### 核心改进

#### 1. 建立配置契约文档（CDD - Configuration Definition Document）

参考 SAP CDS 注解系统，为每个元数据配置建立契约文档：

```yaml
# cross_table_filters 配置契约
cross_table_filters:
  - id: string (必需, 唯一标识)
    display_name: string (必需, 显示名称)
    description: string (可选, 描述)
    
    # Association 定义
    association:
      target_table: string (必需, 目标表名)
      target_alias: string (可选, 默认值: t)
      join_type: enum(exists|inner|left) (可选, 默认值: exists)
      on_conditions: array (必需)
        - left_field: string (必需)
          operator: enum(eq|ne|gt|lt|ge|le|like|in) (必需)
          right_field: string (必需)
      where_conditions: array (可选)
        - field: string (必需)
          operator: string (必需)
          parameter: string (必需, 对应前端参数名)
    
    # UI 配置
    ui:
      filter_type: enum(search|select|multi-select|date|date-range|number) (必需)
      filter_label: string (可选)
      filter_placeholder: string (可选)
      
      # 选项配置（互斥）
      options_source: enum(static|enum|api) (必需)
      static_options: array (当 options_source=static 时必需)
      enum_type: string (当 options_source=enum 时必需)
      api_endpoint: string (当 options_source=api 时必需)
      
      position: number (可选, 排序位置)
```

#### 2. 建立统一的 API 规范

参考 OpenAPI Specification，为所有枚举相关 API 建立统一规范：

```yaml
# 枚举相关 API 规范
/openapi/v1:
  /enum-types:
    get:
      summary: 获取枚举类型列表
      response: 
        success: true
        data: EnumType[]
        page: number
        page_size: number
        total: number
      
  /enum-types/{enum_type_id}:
    get:
      summary: 获取枚举类型详情
      response:
        success: true
        data: EnumTypeDetail  # 注意：包含 values 引用
      
  /enum-types/{enum_type_id}/values:
    get:
      summary: 获取枚举值列表
      response:
        success: true
        data: 
          data: EnumValue[]  # 嵌套结构：列表数据
          enum_type: EnumType  # 嵌套结构：关联的枚举类型
          page: number
          page_size: number
          total: number
```

**关键点**：
- 路径统一使用 `/enum-types`（复数形式）
- 详情和值分离为不同端点
- 返回格式统一：`success: true, data: {...}`

#### 3. 建立统一的枚举加载服务

```javascript
// src/services/enumService.js

/**
 * 统一枚举加载服务
 * 参考 SAP Value Help 机制
 */
export const EnumService = {
  
  /**
   * 加载枚举选项
   * @param {string} enumTypeId - 枚举类型 ID
   * @param {Object} options - 加载选项
   * @param {Object} options.headers - 请求头
   * @param {boolean} options.cache - 是否缓存（默认 true）
   * @returns {Promise<Array<{value: string, label: string}>>}
   */
  async loadOptions(enumTypeId, options = {}) {
    const { headers = {}, cache = true } = options;
    
    // 检查缓存
    if (cache && this._cache.has(enumTypeId)) {
      return this._cache.get(enumTypeId);
    }
    
    // 验证枚举类型 ID
    if (!enumTypeId) {
      throw new Error('[EnumService] enumTypeId is required');
    }
    
    // 调用 API
    const response = await fetch(
      `/api/v1/enum-types/${enumTypeId}/values`,
      { headers }
    );
    
    const result = await response.json();
    
    // 验证响应
    if (!result.success) {
      throw new Error(`[EnumService] Failed to load enum ${enumTypeId}: ${result.message}`);
    }
    
    // 解析数据（统一处理嵌套结构）
    const values = this._normalizeEnumValues(result.data?.data || []);
    
    // 缓存结果
    if (cache) {
      this._cache.set(enumTypeId, values);
    }
    
    return values;
  },
  
  /**
   * 规范化枚举值格式
   * @private
   */
  _normalizeEnumValues(rawValues) {
    if (!Array.isArray(rawValues)) {
      console.warn('[EnumService] Expected array, got:', typeof rawValues);
      return [];
    }
    
    return rawValues.map(v => ({
      value: v.code || v.value,
      label: v.name || v.label
    }));
  },
  
  /**
   * 清除缓存
   */
  clearCache() {
    this._cache.clear();
  },
  
  /**
   * 预加载枚举
   */
  async preload(enumTypeIds, options = {}) {
    return Promise.all(
      enumTypeIds.map(id => this.loadOptions(id, options))
    );
  }
};

// 缓存实现
EnumService._cache = new Map();
```

#### 4. 建立配置验证机制

```javascript
// src/utils/configValidator.js

/**
 * 元数据配置验证器
 * 参考 SAP CDS 注解验证
 */
export const ConfigValidator = {
  
  /**
   * 验证 cross_table_filters 配置
   */
  validateCrossTableFilters(config) {
    const errors = [];
    const warnings = [];
    
    if (!Array.isArray(config)) {
      errors.push('cross_table_filters must be an array');
      return { valid: false, errors, warnings };
    }
    
    config.forEach((filter, index) => {
      // 必需字段验证
      if (!filter.id) {
        errors.push(`[${index}] Missing required field: id`);
      }
      
      if (!filter.association) {
        errors.push(`[${index}] Missing required field: association`);
      } else {
        // Association 验证
        if (!filter.association.target_table) {
          errors.push(`[${index}] Missing association.target_table`);
        }
        
        if (!filter.association.on_conditions?.length) {
          errors.push(`[${index}] Missing association.on_conditions`);
        }
      }
      
      // UI 配置验证
      if (!filter.ui) {
        warnings.push(`[${index}] Missing ui configuration`);
      } else {
        if (!filter.ui.filter_type) {
          errors.push(`[${index}] Missing ui.filter_type`);
        }
        
        if (!filter.ui.options_source) {
          warnings.push(`[${index}] Missing ui.options_source, defaulting to text`);
        } else if (filter.ui.options_source === 'enum') {
          if (!filter.ui.enum_type) {
            errors.push(`[${index}] Missing ui.enum_type when options_source=enum`);
          }
        } else if (filter.ui.options_source === 'api') {
          if (!filter.ui.api_endpoint) {
            errors.push(`[${index}] Missing ui.api_endpoint when options_source=api`);
          }
        }
      }
    });
    
    return {
      valid: errors.length === 0,
      errors,
      warnings
    };
  },
  
  /**
   * 验证并输出警告日志
   */
  validateAndLog(config, configName = 'config') {
    const result = this.validateCrossTableFilters(config);
    
    if (result.errors.length > 0) {
      console.error(`[ConfigValidator] ${configName} validation failed:`, result.errors);
    }
    
    if (result.warnings.length > 0) {
      console.warn(`[ConfigValidator] ${configName} warnings:`, result.warnings);
    }
    
    if (result.valid) {
      console.log(`[ConfigValidator] ${configName} validation passed`);
    }
    
    return result;
  }
};
```

---

## 三、Impact

### 受影响的代码

**前端**：
- `src/composables/useGlobalFilters.js` - 重构为使用 EnumService
- `src/services/` - 新增 enumService.js
- `src/utils/` - 新增 configValidator.js
- `src/components/common/EnumSelect.vue` - 统一枚举加载入口

**后端**：
- `meta/api/enum_api.py` - 添加 API 规范注释
- `meta/core/models.py` - 添加配置契约类型定义

**文档**：
- `docs/api/enum-api.md` - API 规范文档（新增）
- `docs/metadata/cross-table-filters.md` - 跨表过滤配置文档（新增）
- `.trae/rules/component-governance.md` - 组件治理规范（已有，扩展）

---

## 四、ADDED Requirements

### Requirement: 配置契约文档化

系统**应当**为每个元数据配置提供配置契约文档。

#### Scenario: 文档化 cross_table_filters 配置
- **GIVEN** 开发者需要配置跨表过滤
- **WHEN** 开发者查阅 `cross_table_filters` 配置契约文档
- **THEN** 文档清晰说明了所有字段的类型、约束和示例

#### Scenario: 配置验证
- **GIVEN** 开发者配置了 `options_source: enum` 但未提供 `enum_type`
- **WHEN** 应用启动或加载配置时
- **THEN** 系统输出警告日志，指出配置错误

---

### Requirement: 统一的枚举加载服务

系统**应当**提供统一的枚举加载服务，所有枚举相关功能使用该服务。

#### Scenario: 通过 EnumService 加载枚举
- **GIVEN** 前端需要加载 `annotation_category` 枚举的选项
- **WHEN** 调用 `EnumService.loadOptions('annotation_category')`
- **THEN** 返回统一的 `{value, label}` 格式数组

#### Scenario: 枚举选项缓存
- **GIVEN** 同一枚举被多次加载
- **WHEN** 第二次调用 `EnumService.loadOptions()`
- **THEN** 直接从缓存返回，不发起网络请求

#### Scenario: 枚举加载错误处理
- **GIVEN** 枚举类型 ID 不存在
- **WHEN** 调用 `EnumService.loadOptions('non_existent_enum')`
- **THEN** 抛出明确的错误信息

---

### Requirement: API 规范统一

系统**应当**遵循统一的 API 规范。

#### Scenario: API 路径规范
- **GIVEN** 需要调用枚举相关 API
- **WHEN** 开发者查阅 API 规范文档
- **THEN** 文档明确说明了正确的路径和响应格式

#### Scenario: API 响应格式统一
- **GIVEN** 调用 `/api/v1/enum-types/{id}/values`
- **WHEN** API 返回数据
- **THEN** 响应格式为 `{success: true, data: {...}}`

---

### Requirement: 配置验证机制

系统**应当**在运行时验证元数据配置。

#### Scenario: 启动时验证
- **GIVEN** 应用启动加载元模型
- **WHEN** `cross_table_filters` 配置包含错误
- **THEN** 系统输出验证错误日志，但不影响启动

#### Scenario: 开发时验证
- **GIVEN** 开发者修改了元模型配置
- **WHEN** 运行时加载该配置
- **THEN** 系统通过 `ConfigValidator` 进行验证并输出结果

---

## 五、MODIFIED Requirements

### Requirement: useGlobalFilters 重构

**原需求**: `useGlobalFilters` 中硬编码枚举加载逻辑

**修改后**: `useGlobalFilters` **应当**使用统一的 `EnumService` 加载枚举选项：

```javascript
// 使用 EnumService
import { EnumService } from '@/services/enumService'

const crossTableFilters = metaObj.analytical_model?.cross_table_filters || []
for (const filter of crossTableFilters) {
  if (filter.ui?.options_source === 'enum' && filter.ui?.enum_type) {
    try {
      filter.options = await EnumService.loadOptions(filter.ui.enum_type)
    } catch (e) {
      console.error(`[useGlobalFilters] Failed to load enum:`, e)
    }
  }
}
```

---

## 六、技术方案

### 6.1 目录结构

```
src/
├── services/
│   └── enumService.js          # 统一枚举加载服务
├── utils/
│   └── configValidator.js      # 配置验证工具
├── composables/
│   └── useGlobalFilters.js     # 使用 EnumService
└── components/
    └── common/
        └── EnumSelect.vue      # 使用 EnumService

docs/
├── api/
│   └── enum-api.md            # 枚举 API 规范
└── metadata/
    └── cross-table-filters.md # 跨表过滤配置文档
```

### 6.2 实现计划

#### Phase 1: 文档化（1天）
- 创建 `docs/api/enum-api.md` - API 规范文档
- 创建 `docs/metadata/cross-table-filters.md` - 配置契约文档
- 更新 `.trae/rules/component-governance.md` - 添加配置治理章节

#### Phase 2: 服务封装（1天）
- 创建 `src/services/enumService.js` - 统一枚举服务
- 创建 `src/utils/configValidator.js` - 配置验证工具
- 添加缓存和错误处理

#### Phase 3: 重构集成（1天）
- 重构 `useGlobalFilters.js` 使用 EnumService
- 添加配置验证日志
- 验证 EnumSelect 组件使用统一服务

#### Phase 4: 测试覆盖（1天）
- 编写 EnumService 单元测试
- 编写 ConfigValidator 测试
- 编写端到端测试

---

## 七、验收标准

### 文档化验收
- [ ] `docs/api/enum-api.md` 包含所有枚举 API 规范
- [ ] `docs/metadata/cross-table-filters.md` 包含完整配置契约
- [ ] 所有新增配置都有对应的契约文档

### 服务化验收
- [ ] EnumService 封装了所有枚举加载逻辑
- [ ] useGlobalFilters 使用 EnumService
- [ ] EnumSelect 组件使用 EnumService

### 验证机制验收
- [ ] ConfigValidator 验证所有 cross_table_filters 配置
- [ ] 配置错误时输出明确的错误日志
- [ ] 验证过程不影响应用启动

### 测试覆盖验收
- [ ] EnumService 单元测试覆盖率 > 80%
- [ ] ConfigValidator 单元测试覆盖率 > 80%
- [ ] 端到端测试验证完整流程

---

## 八、参考资料

- [SAP CDS Annotations](https://help.sap.com/doc/saphelp_nw750/7.5.5/en-US/cf/e84f2b4c0d4a11d189710000e829fbbb/content.htm?no_cache=true)
- [OpenAPI Specification 3.0](https://spec.openapis.org/oas/v3.0.3)
- [SAP Fiori Elements Value Help](https://ui5.sap.com/#/topic/5eb51e93f1cb4de1a4c2f42c9f2dfa3e)
- `meta-model-driven-filters` spec - 过滤系统规范
- `p1-phase-b-analytics-aggregation` spec - 分析聚合规范
