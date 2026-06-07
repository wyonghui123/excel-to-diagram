# 元数据模型治理 - 任务清单

## Phase 1: 文档化

### 任务 1.1: 创建枚举 API 规范文档

- [x] 创建 `docs/api/enum-api.md`
- [x] 文档包含 `/enum-types` 端点规范
- [x] 文档包含 `/enum-types/{id}` 端点规范
- [x] 文档包含 `/enum-types/{id}/values` 端点规范
- [x] 文档说明响应格式（嵌套结构）
- [x] 添加请求/响应示例

### 任务 1.2: 创建跨表过滤配置契约文档

- [x] 创建 `docs/metadata/cross-table-filters.md`
- [x] 文档说明 `cross_table_filters` 配置结构
- [x] 文档说明 `association` 配置规范
- [x] 文档说明 `ui` 配置规范
- [x] 文档说明 `options_source` 选项来源
- [x] 包含完整的 YAML 示例
- [x] 包含错误配置示例和说明

### 任务 1.3: 更新组件治理规范

- [x] 更新 `.trae/rules/component-governance.md`
- [x] 添加"配置契约"章节
- [x] 添加"元数据配置治理"要求
- [x] 添加"API 规范遵循"要求

---

## Phase 2: 服务封装

### 任务 2.1: 创建统一枚举加载服务

- [x] 创建 `src/services/enumService.js`
- [x] 实现 `loadOptions(enumTypeId, options)` 方法
- [x] 实现缓存机制（Map）
- [x] 实现错误处理和日志
- [x] 实现 `_normalizeEnumValues()` 规范化方法
- [x] 实现 `clearCache()` 方法
- [x] 实现 `preload(enumTypeIds)` 预加载方法
- [x] 添加 JSDoc 注释

### 任务 2.2: 创建配置验证工具

- [x] 创建 `src/utils/configValidator.js`
- [x] 实现 `validateCrossTableFilters()` 方法
- [x] 实现必需字段验证
- [x] 实现 `options_source` 互斥验证
- [x] 实现 `enum_type` 存在性验证
- [x] 实现 `validateAndLog()` 验证并日志方法
- [x] 添加 JSDoc 注释

### 任务 2.3: 单元测试 - EnumService

- [ ] 测试 `loadOptions()` 基本功能
- [ ] 测试缓存机制
- [ ] 测试错误处理（无效 ID）
- [ ] 测试响应数据规范化
- [ ] 测试 `preload()` 预加载
- [ ] 测试覆盖率 > 80%

### 任务 2.4: 单元测试 - ConfigValidator

- [ ] 测试有效配置验证通过
- [ ] 测试缺失必需字段
- [ ] 测试 `options_source=enum` 但无 `enum_type`
- [ ] 测试 `options_source=api` 但无 `api_endpoint`
- [ ] 测试覆盖率 > 80%

---

## Phase 3: 重构集成

### 任务 3.1: 重构 useGlobalFilters

- [x] 修改 `src/composables/useGlobalFilters.js`
- [x] 导入 EnumService
- [x] 修改枚举加载逻辑使用 EnumService.loadOptions()
- [x] 添加 ConfigValidator.validateAndLog() 调用
- [x] 添加错误处理和日志
- [x] 移除重复的枚举加载代码

### 任务 3.2: 更新 EnumSelect 组件

- [ ] 检查 `src/components/common/EnumSelect.vue`
- [ ] 如有独立枚举加载逻辑，统一使用 EnumService
- [ ] 确保组件行为与 useGlobalFilters 一致

### 任务 3.3: 添加开发时配置验证

- [ ] 在 useGlobalFilters 加载配置时调用 ConfigValidator
- [ ] 验证失败时输出警告日志但不阻断功能
- [ ] 帮助开发者在开发时发现配置错误

---

## Phase 4: 测试覆盖

### 任务 4.1: 端到端测试 - 跨表过滤

- [ ] 测试 FilterBar 加载备注类型选项
- [ ] 测试多选下拉框正确显示枚举值
- [ ] 测试选择备注类型后生成正确的 EXISTS 查询
- [ ] 测试备注类型不存在时的错误处理

### 任务 4.2: 端到端测试 - 配置验证

- [ ] 测试有效配置加载成功
- [ ] 测试无效配置输出警告日志
- [ ] 测试配置错误不阻断应用启动

### 任务 4.3: 集成测试

- [ ] 测试 EnumService 与 API 的集成
- [ ] 测试 ConfigValidator 与配置的集成
- [ ] 测试 useGlobalFilters 完整流程

---

## 任务依赖关系

```
Phase 1 (文档化)
  ├── 任务 1.1 ──┐
  ├── 任务 1.2 ──┼── 任务 1.3
  └── 任务 1.3 ──┘

Phase 2 (服务封装)
  ├── 任务 2.1 ──┐
  └── 任务 2.2 ──┴── 任务 2.3, 任务 2.4

Phase 3 (重构集成)
  └── 任务 3.1 ── 任务 3.2 ── 任务 3.3

Phase 4 (测试覆盖)
  ├── 任务 4.1 ──┐
  └── 任务 4.2 ──┴── 任务 4.3
```

---

## 验收标准

| 阶段 | 完成标准 |
|------|----------|
| Phase 1 | 所有文档已创建并审阅 |
| Phase 2 | EnumService 和 ConfigValidator 可独立运行 |
| Phase 3 | useGlobalFilters 使用统一服务 |
| Phase 4 | 所有测试通过，覆盖率达标 |
