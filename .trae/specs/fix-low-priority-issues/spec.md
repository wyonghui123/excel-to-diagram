# 低优先级代码质量问题修复 Spec

## Why

代码审查发现 5 个低优先级问题，涉及前端逻辑错误（`externalBoCodes` 计算无效）、安全改进（Token 存储方式）、代码组织（Store 贫血模型）、配置一致性（`HierarchyConfigLoader` 无缓存失效）和副作用问题（`_enrich_record` 修改原始数据）。这些问题不影响核心功能，但影响代码质量和长期可维护性。

## What Changes

### Bug 修复
- 修复 `diagramDataStore.js` 中 `externalBoCodes` 计算逻辑错误

### 安全改进
- Token 存储从 localStorage 改为 HttpOnly Cookie（需后端配合）

### 代码组织
- `diagramDataStore` 添加业务计算逻辑，减少贫血模型

### 配置一致性
- `HierarchyConfigLoader` 添加 `reload()` 方法，与 `MetaRegistry` 行为一致

### 副作用消除
- `_enrich_record_with_names` 不再修改传入的 record 对象

## Impact

- Affected code:
  - `src/stores/diagramDataStore.js`
  - `src/stores/authStore.js`
  - `meta/services/cascade_service.py` (HierarchyConfigLoader)
  - `meta/api/manage_api.py` (_enrich_record_with_names)

---

## ADDED Requirements

### Requirement: externalBoCodes 逻辑修复

系统 SHALL 正确计算外部关联的业务对象编码集合。

#### Scenario: 中心范围和关系范围有交集
- **WHEN** centerScope = ['A', 'B']，relationFilteredBoCodes = ['B', 'C', 'D']
- **THEN** externalBoCodes = Set(['C', 'D'])（关系范围中不在中心范围内的）

#### Scenario: 中心范围为空
- **WHEN** centerScope = []，relationFilteredBoCodes = ['B', 'C']
- **THEN** externalBoCodes = Set(['B', 'C'])

---

### Requirement: HierarchyConfigLoader 缓存失效

系统 SHALL 支持 `HierarchyConfigLoader` 的配置重新加载。

#### Scenario: 配置文件修改后
- **WHEN** 调用 `HierarchyConfigLoader.reload()`
- **THEN** 下次 `get_config()` 返回最新的配置内容

---

### Requirement: _enrich_record 不修改原始数据

系统 SHALL 在 `_enrich_record_with_names` 中不修改传入的 record 字典，而是返回新的字典。

#### Scenario: enrich 后原始数据不变
- **WHEN** 调用 `_enrich_record_with_names('service_module', record)`
- **THEN** 原始 record 字典不被修改，返回的字典包含额外名称字段

---

## MODIFIED Requirements

### Requirement: Token 存储

当前实现：Token 存储在 localStorage，容易被 XSS 攻击窃取。

修改方案（渐进式）：
1. 短期：保持 localStorage 不变，但添加 XSS 防护（CSP Header）
2. 长期：后端设置 HttpOnly Cookie，前端不再手动管理 Token

**注意：** HttpOnly Cookie 方案需要后端配合修改，当前仅标记为待办，不做实现。

### Requirement: diagramDataStore 业务逻辑

当前实现：Store 只有 setter，业务逻辑散落在组件中。

修改方案：将 `externalBoCodes` 的正确计算逻辑移入 Store，并添加 `centerScope` 状态。

---

## REMOVED Requirements

无移除的需求。
