# Checklist: FieldPolicyEngine 统一字段策略引擎

## Phase 1: FieldPolicyEngine 基础

- [x] `meta/services/field_policy_engine.py` 文件创建完成 ✅
- [x] `PolicyContext` dataclass 定义完整（row, object, user, action） ✅
- [x] `FieldPolicy` dataclass 定义完整（editable, visible, required） ✅
- [x] `_load_system_fields()` 正确加载系统字段集合 ✅
- [x] `_is_immutable()` 正确检查 immutable 语义 ✅
- [x] `determine_editable()` 系统字段检查通过 ✅
- [x] `determine_editable()` ui.editable 配置检查通过 ✅
- [x] `determine_editable()` immutable 语义检查通过 ✅
- [x] mutability='locked' 逻辑正确（所有字段不可编辑） ✅
- [x] mutability='fully_editable' 逻辑正确（所有字段可编辑） ✅
- [x] mutability='extensible' 逻辑正确（非系统字段可编辑） ✅
- [ ] FieldPolicyEngine 单元测试通过

## Phase 2: 前端集成

- [x] `src/composables/useFieldPolicy.js` 文件创建完成 ✅
- [x] `editableMap` 计算属性正确返回字段映射 ✅
- [x] `isEditable(fieldId, row)` 函数正确判定 ✅
- [x] 新行判定逻辑正确（id 以 `__new_` 开头） ✅
- [x] MetaListPage 成功导入 useFieldPolicy ✅
- [x] useMetaList 集成 useFieldPolicy ✅
- [ ] 前端 isEditable 与后端 determine_editable 结果一致

## Phase 3: ActionPolicy 重构

- [x] `ActionPolicy` 类创建完成 ✅
- [x] `should_show_action(action_id)` 方法正确过滤操作 ✅
- [x] `should_show_import()` 正确检查 create 权限 ✅
- [x] `should_show_export()` 始终返回 true ✅
- [x] view_config_service.py 使用 ActionPolicy ✅
- [x] `_enrich_columns_with_policy()` 调用 FieldPolicyEngine ✅
- [x] 硬编码系统字段判断已移除 ✅
- [ ] enum_type（locked）不显示 CRUD 按钮（需重启后端测试）
- [ ] enum_value（extensible）正确显示按钮（需重启后端测试）

## Phase 4: YAML Schema 扩展

- [x] `FieldPolicy` dataclass 在 models.py 中定义 ✅
- [x] `semantics.field_policy` 解析支持添加 ✅
- [x] `semantics.mutability` 解析支持添加 ✅
- [ ] `PolicyEvaluator.evaluate()` 安全表达式求值实现
- [ ] `when/then` 规则匹配正确
- [ ] `default` 兜底值正确处理
- [ ] 现有 YAML 配置无需修改可工作
- [ ] field_policy 声明规范文档更新

## 集成验证

- [ ] enum_type 页面（locked）显示正确
- [ ] enum_value 页面（extensible）显示正确
- [ ] user 页面（fully_editable）显示正确
- [ ] 新增行中 code 字段可编辑
- [ ] 现有行中 immutable 字段不可编辑
- [ ] 系统字段自动不可编辑
- [ ] 重置按钮保留父级上下文
- [ ] 导入按钮只在有 CRUD 时显示
- [ ] 导出按钮始终显示
- [ ] 不可编辑单元格显示灰色背景

## Phase 5: FieldPolicy Validation

- [x] `FieldPolicyValidationInterceptor` 类创建完成 ✅
- [x] `before_create()` 验证方法实现 ✅
- [x] `before_update()` 验证方法实现 ✅
- [x] `_validate_fields()` 核心验证逻辑正确 ✅
- [x] BOFramework 集成成功 ✅
- [x] CRUD 操作前调用 validation ✅
- [x] 错误信息包含字段名和原因 ✅
- [ ] locked 对象不允许更新的测试通过（需重启后端测试）
- [ ] immutable 字段不允许修改的测试通过（需重启后端测试）
- [ ] extensible 对象的系统字段不允许修改的测试通过（需重启后端测试）

## 回归测试

- [ ] Phase 17 Inline Edit 功能正常
- [ ] Phase 9 通用能力模型正常
- [ ] Phase 13 DisplayName 功能正常
- [ ] 所有现有测试通过
