# 元数据模型治理 - 检查清单

## Phase 1: 文档化

- [ ] **docs/api/enum-api.md 存在**
  - [ ] 包含 `/enum-types` GET 端点规范
  - [ ] 包含 `/enum-types/{id}` GET 端点规范
  - [ ] 包含 `/enum-types/{id}/values` GET 端点规范
  - [ ] 文档说明响应格式嵌套结构 `data.data`
  - [ ] 包含请求/响应 JSON 示例

- [ ] **docs/metadata/cross-table-filters.md 存在**
  - [ ] 包含 `cross_table_filters` 完整配置结构
  - [ ] 包含 `association` 配置规范
  - [ ] 包含 `ui.options_source` 选项说明
  - [ ] 包含完整 YAML 示例
  - [ ] 包含配置错误示例和说明

- [ ] **component-governance.md 更新**
  - [ ] 添加"配置契约"章节
  - [ ] 添加元数据配置治理要求
  - [ ] 添加 API 规范遵循要求

---

## Phase 2: 服务封装

- [ ] **src/services/enumService.js 存在**
  - [ ] `loadOptions(enumTypeId, options)` 方法实现
  - [ ] 缓存机制（Map）实现
  - [ ] 错误处理和日志实现
  - [ ] `_normalizeEnumValues()` 规范化方法实现
  - [ ] `clearCache()` 方法实现
  - [ ] `preload(enumTypeIds)` 方法实现
  - [ ] JSDoc 注释完整

- [ ] **src/utils/configValidator.js 存在**
  - [ ] `validateCrossTableFilters()` 方法实现
  - [ ] 必需字段验证实现
  - [ ] `options_source` 互斥验证实现
  - [ ] `enum_type` 存在性验证实现
  - [ ] `validateAndLog()` 方法实现
  - [ ] JSDoc 注释完整

- [ ] **EnumService 单元测试**
  - [ ] `loadOptions()` 基本功能测试通过
  - [ ] 缓存机制测试通过
  - [ ] 错误处理测试通过
  - [ ] 响应数据规范化测试通过
  - [ ] `preload()` 测试通过
  - [ ] 测试覆盖率 > 80%

- [ ] **ConfigValidator 单元测试**
  - [ ] 有效配置验证通过
  - [ ] 缺失必需字段验证失败
  - [ ] `options_source=enum` 验证
  - [ ] `options_source=api` 验证
  - [ ] 测试覆盖率 > 80%

---

## Phase 3: 重构集成

- [ ] **useGlobalFilters.js 重构**
  - [ ] 导入 EnumService
  - [ ] 枚举加载使用 `EnumService.loadOptions()`
  - [ ] 添加 ConfigValidator 调用
  - [ ] 添加错误处理
  - [ ] 移除重复代码

- [ ] **EnumSelect.vue 检查**
  - [ ] 如有独立逻辑，已统一使用 EnumService
  - [ ] 组件行为与 useGlobalFilters 一致

- [ ] **配置验证日志**
  - [ ] 验证失败输出警告日志
  - [ ] 不阻断应用启动

---

## Phase 4: 测试覆盖

- [ ] **端到端测试 - 跨表过滤**
  - [ ] FilterBar 加载备注类型选项成功
  - [ ] 多选下拉框显示枚举值
  - [ ] 选择备注类型生成 EXISTS 查询
  - [ ] 错误处理正确

- [ ] **端到端测试 - 配置验证**
  - [ ] 有效配置加载成功
  - [ ] 无效配置输出警告
  - [ ] 不阻断启动

- [ ] **集成测试**
  - [ ] EnumService 与 API 集成通过
  - [ ] ConfigValidator 与配置集成通过
  - [ ] useGlobalFilters 完整流程通过

---

## 最终验收

- [ ] 所有文档已完成
- [ ] 所有代码已重构
- [ ] 所有测试已通过
- [ ] 测试覆盖率达标
- [ ] 代码审查通过
