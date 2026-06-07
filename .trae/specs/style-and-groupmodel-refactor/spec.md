# 样式与GroupModel重构规范

## Why
当前代码存在两大技术债：
1. **样式控制职责混乱**：JavaScript 内联样式与 CSS 规则冲突，导致"斜体不生效"、"拖尾线不显示"等 Bug 反复出现
2. **GroupModel 重构计划未完成**：Phase 1 安全防护已实施，但 Phase 2-4 尚未验证和完成

## What Changes

### 样式优化部分
- **移除 JS 内联样式**：将 `useSvgStyle.js` 的样式修改职责转移到 CSS
- **修复拖尾线控制**：将 `useTooltip.js` 的 `style.display='none'` 改为 CSS 类控制
- **移除时序 hack**：用 MutationObserver 替代 `setTimeout(..., 1200)`
- **font-synthesis 规范**：确保 foreignObject 内元素正确使用斜体

### GroupModel 重构收尾部分
- **Phase 2 验证**：确认 `useDiagramData.js` 等模块已集成日志系统
- **Phase 3 验证**：确认旧 console.log 已清理
- **Phase 4 实施**：添加循环引用和深度限制的单元测试
- **文档更新**：更新 `样式代码优化待办记录.md` 和 `groupModel-refactor-plan.md` 状态

## Impact

### 受影响的规范
- 容器标题样式控制
- 拖尾线显示控制
- GroupModel 日志系统

### 受影响的代码
- `src/composables/useMermaid/style/useSvgStyle.js`
- `src/composables/useMermaid/tooltip/useTooltip.js`
- `src/styles/edgeLabel-common.css`
- `src/services/groupModel/*.js`
- `src/views/AADiagramApp/composables/useDiagramData.js`
- `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js`
- `src/composables/useMermaid/layouts/groupedLayout.js`

---

## ADDED Requirements

### Requirement: 样式职责统一
系统 SHALL 仅通过 CSS 控制所有展示样式，JavaScript 只负责 DOM 结构操作和业务逻辑。

#### Scenario: 容器标题样式
- **WHEN** Mermaid 渲染容器标题
- **THEN** 样式完全由 `edgeLabel-common.css` 控制
- **AND** JS 不设置任何 fontStyle、fontSize、transform 内联样式

#### Scenario: 拖尾线显示控制
- **WHEN** 用户设置 `hideTails=true`
- **THEN** SVG 添加 `hide-tails` 类
- **AND** CSS 通过 `.hide-tails` 类隐藏拖尾线
- **AND** JS 不设置 `style.display='none'`

### Requirement: GroupModel 安全防护验证
系统 SHALL 确保所有递归调用都有深度限制和循环检测。

#### Scenario: 循环引用防护
- **WHEN** 构建 GroupModel 时遇到循环引用（如 A→B→C→A）
- **THEN** 检测到循环后跳过重复节点
- **AND** 记录警告日志

#### Scenario: 深度限制防护
- **WHEN** 递归深度超过 20 层
- **THEN** 停止递归并记录警告日志

### Requirement: 日志系统完整性
系统 SHALL 通过 DataFlowLogger 提供结构化日志，支持按模块开关控制。

#### Scenario: 启用特定模块日志
- **WHEN** 开发者调用 `DataFlowLogger.enable('GroupModel')`
- **THEN** 仅 GroupModel 模块日志输出到控制台
- **AND** 其他模块日志保持关闭

---

## MODIFIED Requirements

### Requirement: DataFlowLogger 配置
**MODIFIED**: 日志默认状态从 `true` 改为 `false`，避免生产环境污染控制台。

**Migration**: 开发者可通过 `DataFlowLogger.enable()` 开启调试日志。

---

## REMOVED Requirements

### Requirement: useSvgStyle.js 内联样式设置
**Reason**: JS 内联样式与 CSS 冲突，且难以维护
**Migration**: 将样式职责移至 CSS，JS 改为纯检测逻辑

### Requirement: setTimeout 样式延迟应用
**Reason**: 1200ms 延迟是时序问题的遮羞布，不可依赖
**Migration**: 使用 MutationObserver 检测渲染完成

---

## 详细实施计划

### 阶段一：样式优化（优先级最高）

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1.1 | 备份并优化 `useSvgStyle.js` - 移除内联样式，改为验证逻辑 | 无 |
| 1.2 | 修复 `useTooltip.js` - 拖尾线改用 CSS 类控制 | 1.1 |
| 1.3 | 移除 `setTimeout` hack - 改用 MutationObserver | 1.1 |
| 1.4 | 确保 `font-synthesis: style` 在 CSS 中正确设置 | 无 |
| 1.5 | 功能验证 - 测试容器标题样式和拖尾线控制 | 1.1-1.4 |

### 阶段二：GroupModel 重构收尾

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 2.1 | 验证 `useDiagramData.js` 日志集成状态 | 无 |
| 2.2 | 验证所有旧 console.log 已清理 | 无 |
| 2.3 | 添加 GroupModel 循环引用和深度限制单元测试 | 2.1-2.2 |
| 2.4 | 验证日志系统完整性 | 2.1 |

### 阶段三：文档与长效机制

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 3.1 | 创建 `style-control-map.md` | 阶段一完成 |
| 3.2 | 更新 `样式代码优化待办记录.md` 状态 | 阶段一完成 |
| 3.3 | 更新 `groupModel-refactor-plan.md` 状态 | 阶段二完成 |

---

## 验收标准

1. **样式控制统一**：所有容器标题样式由 CSS 控制，无 JS 内联样式设置
2. **拖尾线控制正常**：`hideTails=true` 时拖尾线正确隐藏
3. **无时序依赖**：移除 `setTimeout` 后样式正确应用
4. **安全防护完整**：所有递归方法都有 `checkDepth` 和 `checkCycle` 调用
5. **日志系统可用**：DataFlowLogger 支持按模块开关，默认关闭
6. **单元测试通过**：循环引用和深度限制测试通过
7. **文档同步更新**：所有待办状态与代码实现一致
