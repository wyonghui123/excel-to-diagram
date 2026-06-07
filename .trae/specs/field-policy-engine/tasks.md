# Tasks: FieldPolicyEngine 统一字段策略引擎

## Phase 1: FieldPolicyEngine 基础 (MVP)

- [x] Task 1.1: 创建 FieldPolicyEngine 类 ✅
  - [x] SubTask 1.1.1: 在 `meta/services/` 创建 `field_policy_engine.py`
  - [x] SubTask 1.1.2: 实现 `PolicyContext` dataclass（包含 row, object, user, action）
  - [x] SubTask 1.1.3: 实现 `FieldPolicy` dataclass（包含 editable, visible, required）
  - [x] SubTask 1.1.4: 实现 `_load_system_fields()` 加载系统字段集合
  - [x] SubTask 1.1.5: 实现 `_is_immutable()` 检查字段 immutable 语义

- [x] Task 1.2: 实现 `determine_editable()` 核心方法 ✅
  - [x] SubTask 1.2.1: 系统字段硬编码检查（created_at, updated_at, is_system 等）
  - [x] SubTask 1.2.2: ui.editable 显式配置检查
  - [x] SubTask 1.2.3: immutable 语义检查
  - [x] SubTask 1.2.4: mutability 逻辑评估（locked/fully_editable/extensible）

- [x] Task 1.3: 实现 mutability determination 逻辑 ✅
  - [x] SubTask 1.3.1: `locked` → 所有字段不可编辑
  - [x] SubTask 1.3.2: `fully_editable` → 所有字段可编辑
  - [x] SubTask 1.3.3: `extensible` → 非系统字段可编辑

- [ ] Task 1.4: 单元测试
  - [ ] SubTask 1.4.1: determine_editable() 系统字段测试
  - [ ] SubTask 1.4.2: determine_editable() mutability 测试
  - [ ] SubTask 1.4.3: determine_editable() 新行测试

---

## Phase 2: 前端集成

- [x] Task 2.1: 创建 useFieldPolicy Hook ✅
  - [x] SubTask 2.1.1: 在 `src/composables/` 创建 `useFieldPolicy.js`
  - [x] SubTask 2.1.2: 实现 `editableMap` 计算属性
  - [x] SubTask 2.1.3: 实现 `isEditable(fieldId, row)` 函数
  - [x] SubTask 2.1.4: 新行判定逻辑（id 以 `__new_` 开头）

- [x] Task 2.2: MetaListPage 集成 ✅
  - [x] SubTask 2.2.1: 导入 useFieldPolicy Hook ✅
  - [x] SubTask 2.2.2: 替换 InlineEditCell 的 `isCellEditable` 调用 ✅
  - [x] SubTask 2.2.3: 简化本地 `isCellEditable` 函数 ✅

- [ ] Task 2.3: 验证一致性
  - [ ] SubTask 2.3.1: 前端 isEditable 与后端 determine_editable 结果对比测试

---

## Phase 3: ActionPolicy 重构

- [x] Task 3.1: 创建 ActionPolicy 类 ✅
  - [x] SubTask 3.1.1: 在 `meta/services/action_policy.py` 中创建 `ActionPolicy` 类
  - [x] SubTask 3.1.2: 实现 `should_show_action(action_id)` 方法
  - [x] SubTask 3.1.3: 实现 `should_show_import()` 方法（需要 create 权限）
  - [x] SubTask 3.1.4: 实现 `should_show_export()` 方法（始终显示）

- [x] Task 3.2: 重构 view_config_service.py ✅
  - [x] SubTask 3.2.1: 拆分 `_merge_default_actions()` 函数 ✅
  - [x] SubTask 3.2.2: 创建 `_enrich_columns_with_policy()` 调用 FieldPolicyEngine ✅
  - [x] SubTask 3.2.3: 移除原有的硬编码系统字段判断 ✅

- [ ] Task 3.3: 集成测试
  - [ ] SubTask 3.3.1: enum_type（locked）不显示 CRUD 按钮测试
  - [ ] SubTask 3.3.2: enum_value（extensible）正确显示按钮测试

---

## Phase 4: YAML Schema 扩展

- [x] Task 4.1: 扩展 MetaField 模型 ✅
  - [x] SubTask 4.1.1: 在 `meta/core/models.py` 添加 `FieldPolicy` dataclass
  - [x] SubTask 4.1.2: 添加 `semantics.field_policy` 解析支持
  - [x] SubTask 4.1.3: 添加 `semantics.mutability` 解析支持

- [ ] Task 4.2: 实现 field_policy determination 规则
  - [ ] SubTask 4.2.1: 实现 `PolicyEvaluator.evaluate()` 安全表达式求值
  - [ ] SubTask 4.2.2: 实现 `when/then` 规则匹配
  - [ ] SubTask 4.2.3: 实现 `default` 兜底值

- [ ] Task 4.3: 向后兼容
  - [ ] SubTask 4.3.1: 现有 YAML 无需修改即可工作
  - [ ] SubTask 4.3.2: 添加 field_policy 是可选的增强功能

- [ ] Task 4.4: 文档更新
  - [ ] SubTask 4.4.1: 更新 spec.md 添加 YAML 示例
  - [ ] SubTask 4.4.2: 添加 field_policy 声明规范文档

---

## Phase 5: FieldPolicy Validation（API Service 层）

> **关键**：前端 Dynamic UI 控制了 editable，但后端 API 必须独立做 validation，防止恶意请求绕过前端直接调用 API。

- [x] Task 5.1: 创建 FieldPolicyValidationInterceptor ✅
  - [x] SubTask 5.1.1: 创建 `FieldPolicyValidationInterceptor` 类
  - [x] SubTask 5.1.2: 实现 `before_create()` 验证方法
  - [x] SubTask 5.1.3: 实现 `before_update()` 验证方法
  - [x] SubTask 5.1.4: 实现 `_validate_fields()` 核心验证逻辑

- [x] Task 5.2: 集成到 BOFramework ✅
  - [x] SubTask 5.2.1: 在 `crud_create` 和 `crud_update` 前调用 validation ✅
  - [x] SubTask 5.2.2: 返回清晰的错误信息（字段名 + 原因） ✅

- [ ] Task 5.3: Validation 测试
  - [ ] SubTask 5.3.1: 测试 locked 对象不允许更新
  - [ ] SubTask 5.3.2: 测试 immutable 字段不允许修改
  - [ ] SubTask 5.3.3: 测试 extensible 对象的系统字段不允许修改

---

## Task Dependencies

```
Phase 1 (基础)
├── Task 1.1 ← 开始
├── Task 1.2 ← 依赖 Task 1.1
├── Task 1.3 ← 依赖 Task 1.2
└── Task 1.4 ← 依赖 Task 1.2, 1.3

Phase 2 (前端)
├── Task 2.1 ← 依赖 Phase 1 完成
├── Task 2.2 ← 依赖 Task 2.1
└── Task 2.3 ← 依赖 Task 2.2

Phase 3 (ActionPolicy)
├── Task 3.1 ← 依赖 Phase 1 完成
├── Task 3.2 ← 依赖 Task 3.1
└── Task 3.3 ← 依赖 Task 3.2

Phase 4 (Schema)
├── Task 4.1 ← 依赖 Phase 1 完成
├── Task 4.2 ← 依赖 Task 4.1
├── Task 4.3 ← 依赖 Task 4.2
└── Task 4.4 ← 依赖 Task 4.3

建议并行执行:
- Phase 1 Task 1.1-1.3 (顺序)
- Phase 3 Task 3.1-3.2 (可以在 Phase 1 同时进行)
```

---

## Verification Plan

1. **单元测试**：每个 Task 完成后执行对应测试
2. **集成测试**：Phase 完成后执行端到端测试
3. **回归测试**：确保现有功能不受影响
4. **一致性测试**：前端 isEditable 与后端 determine_editable 结果对比
