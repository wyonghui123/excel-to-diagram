# Spec: OSS→RSS 事件数据流加固

## 1. Background & Objectives

### 1.1 Background

多对象管理页面左侧面板包含两个范围选择树：
- **OSS（ObjectScopeSection）**：对象范围选择树
- **RSS（RelationScopeSection）**：关系范围选择树

**期望行为**：用户变更 OSS 选择 → RSS 自动清空已选状态。

**当前链路涉及 4 个文件、9 个函数/回调**，依赖隐式约定（`null` vs `[]`、`setTimeout(0)`、对象引用替换），极度脆弱。

### 1.2 Business Objectives

- OSS 变更后 RSS 正确清空（功能正确性）
- 开发者修改任一环节时有明确的运行时保障（可维护性）
- 出问题时 5 分钟内通过控制台 trace 日志定位根因（可调试性）

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 用户反馈：OSS 变更后 RSS 未清空 |
| User/Stakeholder | Yes | 业务用户正确性需求 + 开发者可维护性需求 |
| Solution | Yes | 架构重构：事件链路加固 + trace 日志 |
| Functional | Yes | FR-001 ~ FR-006 |
| Nonfunctional | Yes | NFR-001 ~ NFR-004 |

## 3. Functional Requirements

### FR-001: OSS 勾选变更 → RSS 清空
- OSS 勾选后，RSS 树 `getCheckedKeys()` 返回 `[]`
- USE_FILTERSOURCE 和非 USE_FILTERSOURCE 模式均生效
- Priority: Must

### FR-002: OSS 变更不得触发 @check 循环
- 一次 OSS 变更最多产生一次 `scope-change` emit
- `setCheckedKeys` 触发的 `@check` 被 guard 阻断
- Priority: Must

### FR-003: 结构化 trace 日志
- 每次 OSS 用户点击生成唯一 traceId
- 链路每个节点输出格式统一日志：`[ComponentName] eventName payload`
- DEV 模式通过 `console.debug` 输出，生产环境可关闭
- Priority: Must

### FR-004: ObjectScopeSection watch 竞态修复
- `settingFromProp` 设置紧贴 `setCheckedKeys`，消除 nextTick 窗口期用户点击被忽略的竞态
- Priority: Must

### FR-005: 响应式更新语义统一
- `scopeIds.relationExtra` 更新始终通过替换对象引用
- `clearScope()` 和 `handleScopeChange()` 使用一致的 `[]` 语义
- Priority: Must

### FR-006: 防御性 @check 循环阻断
- 使用计数器（depth）替代布尔旗标
- 所有手动 `settingFromProp` 位置统一为 `createScopeGuard()`
- Priority: Should

## 4. Nonfunctional Requirements

| ID | Requirement | Measurement | Priority |
|----|------------|-------------|----------|
| NFR-001 | 可调试性 | DEV 模式点击 OSS 可见 ≥ 7 条 trace 日志 | Must |
| NFR-002 | 竞态安全 | 快速连点 OSS 不产生状态不一致 | Must |
| NFR-003 | 代码一致性 | OSS/RSS guard 用法一致 | Should |
| NFR-004 | 向后兼容 | 现有 101 单元测试通过 | Must |

## 5. External Interface Requirements

无变更。组件 props/emits interface 保持不变。

## 6. Transition Requirements

渐进式重构，每步独立 commit 可单独 revert：
1. 新增 `trace.js` + `scopeGuard.js`
2. ObjectScopeSection watch 竞态修复 + guard + trace
3. RelationScopeSection guard + trace + JSDoc
4. RelationScopeTree 移除 setTimeout
5. useMultiObjectPage 语义统一
6. 单元测试 + 回归

## 7. Constraints & Assumptions

- Vue 3.4+, Element Plus 2.x
- Element Plus `setCheckedKeys` 在当前版本同步触发 `@check`（已用计数器防御未来变更）
- `treeRef.value` 在 watch 触发时已就绪

## 8. Priorities

| ID | Requirement | Priority |
|----|------------|----------|
| FR-004 | OSS watch 竞态修复 | Must |
| FR-003 | Trace 日志 | Must |
| FR-005 | 响应式更新语义统一 | Must |
| FR-001 | OSS→RSS 清空 | Must |
| FR-002 | @check 循环阻断 | Must |
| FR-006 | 计数器替代布尔 | Should |

## 9. RFC — 技术设计

### 9.1 As-Is 问题清单

| # | 位置 | 问题 | 严重度 |
|---|------|------|--------|
| 1 | ObjectScopeSection watch | `settingFromProp=true` 在 nextTick 外设置，窗口期用户点击被忽略 | 高 |
| 2 | RelationScopeTree | `setTimeout(emitScopeChange, 0)` timing hack | 中 |
| 3 | useMultiObjectPage | 必须替换 relationExtra 对象引用，无编译时保障 | 中 |
| 4 | RelationScopeSection computed | 必须返回 null（非 []），依赖 == 宽松判等 | 中 |
| 5 | 两组件 settingFromProp | 写法不一致（nextTick vs sync） | 低 |
| 6 | 全局 | 无可用的 trace 日志 | 高 |

### 9.2 Target Architecture

新增两个工具模块，不改变组件树结构：

```
src/utils/trace.js          ← 新增：结构化日志工具
src/composables/scopeGuard.js ← 新增：统一的 setCheckedKeys 循环阻断守卫

ObjectScopeSection.vue      ← 竞态修复 + guard + trace
RelationScopeSection.vue    ← guard + trace + JSDoc
RelationScopeTree.vue       ← 移除 setTimeout
useMultiObjectPage.js       ← null → [] 语义统一
```

### 9.3 关键设计决策

1. **移除 setTimeout**：`selectedRelationCodes` 在 `emitScopeChange` 前已更新为 `[]`，同步 emit 即可。不需要 defer。
2. **null → [] 统一**：`clearScope()` 用 `[]`，`handleScopeChange` 也用 `[]`。每次替换 `scopeIds.relationExtra` 对象引用（新对象）保证 watch 触发。
3. **计数器替代布尔**：`createScopeGuard()` 返回 `{ enter, exit, active }`，内部使用 `ref(0)` 深度计数，防御 Element Plus 递归 @check。
4. **所有手动 settingFromProp 统一为 guard**：TBD 项已根据行业知识决定 — 全部替换，符合 NFR-003 一致性原则。

### 9.4 实施方案

实施顺序：trace.js → scopeGuard.js → ObjectScopeSection → RelationScopeSection → RelationScopeTree → useMultiObjectPage → 回归测试。

## 10. TBD List

无。所有 TBD 项已在 RFC 9.3.4 中根据行业知识确定。
