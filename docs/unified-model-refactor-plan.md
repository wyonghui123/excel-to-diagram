## 目录

1. [背景](#背景)
2. [目标](#目标)
3. [执行计划](#执行计划)
4. [技术细节](#技术细节)
5. [测试矩阵](#测试矩阵)
6. [量化收益](#量化收益)
7. [相关文件清单](#相关文件清单)
8. [备注](#备注)
9. [B.1 核心思路](#b1-核心思路)
10. [B.2 两种子方案](#b2-两种子方案)
11. [B.3 可行性验证](#b3-可行性验证)
12. [B.4 需要改动的模块](#b4-需要改动的模块)
13. [B.5 可以移除的文件](#b5-可以移除的文件)
14. [B.6 方向A与方向B对比](#b6-方向a与方向b对比)
15. [B.7 推荐路径](#b7-推荐路径)
16. [B.8 详细分析参考](#b8-详细分析参考)

---
# 统一模型重构计划 - 方向A：务实的简化

> 创建日期：2026-04-15  
> 状态：待执行  
> 优先级：中  
> 风险：低-中

---

## 背景

经过两次统一重构尝试（统一分组模型 + UnifiedRenderer），发现以下问题：

1. **UnifiedRenderer 未生效**：已禁用（`&& false`），缺少 80%+ 渲染功能（样式、tooltip、交互、注释等）
2. **代码复杂度增加**：两条并行路径（UnifiedRenderer + 旧渲染器）需要理解
3. **workaround 增加**：为了弥合 SM 图和 BO 图的结构差异，添加了 chart-type-specific 条件

### 核心问题：`containers` 的双重含义

| 含义 | 所在层 | 示例 |
|------|--------|------|
| **含义1**: 终端子分组 | GroupModel层 | `subDomainGroup.containers.push(smGroup)` |
| **含义2**: 可视化容器 | 渲染层 | `{ id, name, nodes: [...] }` |

这两个含义被混淆，导致需要 workaround 来处理。

---

## 目标

不追求完全统一，而是消除不必要的复杂性：

1. **统一数据结构**：SM 图和 BO 图都使用 `children` 承载所有层级
2. **消除 workaround**：移除 `chartType === 'serviceModule' && group.type === 'SUB_DOMAIN'` 判断
3. **清理死代码**：移除 UnifiedRenderer 和 containers 相关死代码
4. **降低概念复杂度**：`containers` 仅保留渲染层含义

---

## 执行计划

### Phase 1：修复 architectureProcessor（低风险，1行改动）

**改动文件**：[src/services/groupModel/architectureProcessor.js](file:///d:/filework/excel-to-diagram/src/services/groupModel/architectureProcessor.js)

```javascript
// 第214行
// Before:
subDomainGroup.containers.push(smGroup)

// After:
subDomainGroup.children.push(smGroup)
```

**附带修复**：[extractTerminalGroups](file:///d:/filework/excel-to-diagram/src/services/groupModel/architectureProcessor.js#L238) 函数：

```javascript
function traverse(groups) {
  for (const group of groups) {
    // 新增：检查自身是否终端
    if (isTerminalGroup(group, chartType)) {
      terminals.push(group)
    }
    if (group.children && group.children.length > 0) {
      traverse(group.children)
    }
  }
}
```

**测试范围**：
- [ ] SM 图正常显示
- [ ] SM 图 Domain 禁用后 SubDomain 提升
- [ ] SM 图 SubDomain 禁用后消失
- [ ] BO 图不受影响

---

### Phase 2：清理 GroupModel 死代码（中风险，~60行）

**改动文件**：[src/services/groupModel/GroupModel.js](file:///d:/filework/excel-to-diagram/src/services/groupModel/GroupModel.js)

| 位置 | 代码 | 操作 |
|------|------|------|
| buildIndex L124-137 | containers 注册到 groups Map | 移除 |
| getFlattenedGroups L367-374 | shouldDisplayAsDisabled 分支合并 containers | 移除 |
| getFlattenedGroups L425-434 | 正常分支合并 containers | 移除 |
| convertGroup L601-625 | 处理 group.containers | 移除 |
| convertGroup L605-606 | SUB_DOMAIN workaround | 移除 |
| toMermaidConfig L670-688 | 提升 disabled 根的 containers | 移除 |
| mergeUserGroup L197-199 | 合并用户配置的 containers | 移除 |

**测试范围**：
- [ ] SM 图所有场景
- [ ] BO 图所有场景
- [ ] 配置面板自动分组
- [ ] 颜色方案
- [ ] 注释/备注

---

### Phase 3：清理 UnifiedRenderer 死代码（极低风险）

**改动文件**：

1. [src/components/MermaidComponent.vue](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.vue)
   - 移除 L225-233（UnifiedRenderer 分支）

2. [src/views/AADiagramApp/composables/useDiagramData.js](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/composables/useDiagramData.js)
   - 移除 L1167-1213（SM 图 UnifiedRenderer 代码生成）
   - 移除 L1278-1328（BO 图 UnifiedRenderer 代码生成）

3. 可选：移除以下文件（如确认不再需要）
   - `src/services/groupModel/UnifiedRenderer.js`
   - `src/services/groupModel/ColorCalculator.js`
   - `src/services/groupModel/dataFlowLogger.js`

---

### Phase 4（未来）：统一容器解析函数（高风险，可选）

**目标**：合并 `resolveGroupContainers`（SM）和 `buildVirtualContainers`（BO）

**难点**：
- 匹配源不同（`realContainers` vs `moduleGroups`）
- 构建逻辑嵌入各自 Syntax 文件
- 需要重构容器数据源构建方式

**建议**：暂不执行，当前两个函数工作正常

---

## 技术细节

### 为什么改 architectureProcessor 就够了

`convertGroup` 的 children 循环**本来就会跳过终端节点**：

```javascript
if (!childIsTerminal && hasCode) {
  // 只有非终端子分组才被处理
  containers.push(convertGroup(child, ...))
}
// 终端子分组被跳过！
```

这意味着：
- BO 图：BO_Group 是终端 → 在 SM_Group 的 children 循环中被跳过
- SM 图（改后）：SM_Group 是终端 → 在 SubDomain 的 children 循环中被跳过

**两种图表走完全相同的逻辑**，终端节点在 convertGroup 中被跳过，由 Syntax 层通过名称匹配来解析。

### 统一后的架构模式

```
Group树构建（architectureProcessor）
  → 全部使用 children，终端节点也在 children 中
      ↓
GroupModel 索引（buildIndex）
  → 递归处理 children
      ↓
扁平化 + disabled 提升（getFlattenedGroups）
  → 终端节点推入 result
      ↓
MermaidConfig 生成（toMermaidConfig/convertGroup）
  → 非终端 children 转为 legacyGroup.containers
  → 终端 children 被跳过（统一行为）
      ↓
Syntax 层容器解析
  → SM: resolveContainersInGroup（匹配 realContainers）
  → BO: buildVirtualContainers（匹配 moduleGroups）
      ↓
统一渲染（groupedLayout）
```

---

## 测试矩阵

| 场景 | SM 图 | BO 图 |
|------|-------|-------|
| 全部启用 | ✅ SubDomain 容器中有 SM 节点 | ✅ SM 容器中有 BO 节点 |
| Domain 禁用 | ✅ SubDomain 被提升，SM 节点通过 directNodes 显示 | ✅ SubDomain 被提升，BO 节点正常显示 |
| SubDomain 禁用 | ✅ 该 SubDomain 的 SM 消失 | ✅ 该 SubDomain 的 SM/BO 消失 |
| SM 禁用（仅 BO） | N/A | ✅ 该 SM 的 BO 消失 |
| 配置面板自动分组 | ✅ SM 正确分配到分组 | ✅ BO 正确分配到分组 |
| 颜色方案 | ✅ 正确着色 | ✅ 正确着色 |
| 注释/备注 | ✅ 正确显示 | ✅ 正确显示 |

---

## 量化收益

| 指标 | 改动前 | 改动后 |
|------|--------|--------|
| chart-type-specific 分支 | 10+ 处 | 3-4 处（仅 Syntax 层和 UI 层） |
| workaround 数量 | 1 | 0 |
| containers 双重含义 | 是 | 否（仅渲染层含义） |
| 死代码行数 | ~100行 | 0 |
| 概念复杂度 | 高 | 低 |

---

## 相关文件清单

### 必须修改
- `src/services/groupModel/architectureProcessor.js`
- `src/services/groupModel/GroupModel.js`
- `src/components/MermaidComponent.vue`
- `src/views/AADiagramApp/composables/useDiagramData.js`

### 可选移除
- `src/services/groupModel/UnifiedRenderer.js`
- `src/services/groupModel/ColorCalculator.js`
- `src/services/groupModel/dataFlowLogger.js`

### 不受影响（但需测试）
- `src/composables/useMermaid/syntax/useServiceModuleSyntax.js`
- `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js`
- `src/composables/useMermaid/layouts/groupedLayout.js`
- `src/views/AADiagramApp/components/LayoutControlPanel.vue`

---

## 备注

- Phase 1 改动最小，可立即回滚
- Phase 2 改动较大，建议分步骤提交
- Phase 3 无功能影响，可随时执行
- 当前 workaround 已能正常工作，此重构是代码质量改进而非功能修复

---

# 附录：方向B — 基于 BO 图扩展支持 SM 图

> 方向B是对方向A的补充，提供更大的代码简化潜力。两者不冲突，方向A是方向B的铺垫。

## B.1 核心思路

BO 图已经有完整的 Domain → SubDomain → SM 容器层级。SM 图本质上就是 BO 图的"简化版"：
- 不展示 BO 节点
- 只展示 SM 容器
- 在 SM 容器之间画连线

## B.2 两种子方案

### 子方案 B1：SM 作为 subgraph

- SM 容器保持为 subgraph，BO 节点隐藏
- 连线在 subgraph ID 之间绘制
- **风险**：高（Mermaid 对嵌套 subgraph 间连线渲染质量不稳定）

### 子方案 B2：SM 作为 node（推荐）

```
┌─ 采购供应（供应链云）─────────────────┐
│                                       │
│   ┌─ 采购订单管理 ─┐  ┌─ 供应商管理 ─┐│
│   │  PO_MGMT       │  │  SUP_MGMT   ││
│   └───────┬────────┘  └──────┬───────┘│
└───────────┼──────────────────┼────────┘
            │     关系          │
            └──────────┬───────┘
                       │
┌─ 库存管理（供应链云）─┼───────────────┐
│                       ▼               │
│   ┌─ 库存管理 ─────────────────────┐  │
│   │  INV_MGMT                      │  │
│   └────────────────────────────────┘  │
└───────────────────────────────────────┘
```

- SM 渲染为节点（和当前 SM 图一样）
- 使用 BO 图的 moduleGroups 数据
- 使用 computedServiceModuleRelations 生成 SM 级连线
- **视觉效果与当前 SM 图完全相同**
- **风险**：中

## B.3 可行性验证

| 检查项 | 结果 | 说明 |
|--------|------|------|
| SM 数据是否可从 BO 管线获取 | ✅ | moduleGroups 已按 SM 分组 |
| SM 连线数据是否已有 | ✅ | computedServiceModuleRelations 已实现 |
| groupedLayout 能否渲染 SM 为节点 | ✅ | directNodes 机制可直接使用 |
| 颜色/样式能否复用 | ✅ | 同一套颜色方案体系 |
| Tooltip 能否适配 | ⚠️ | 需要为 SM 模式添加 SM 级 tooltip |
| 注释能否适配 | ⚠️ | 需要为 SM 模式添加 SM 级注释 |

## B.4 需要改动的模块

| 文件 | 改动内容 | 预估行数 |
|------|----------|----------|
| useBusinessObjectSyntax.js | 新增 SM 模式逻辑 | ~100-150 行 |
| useDiagramData.js | 传入 SM 级连线数据 | ~30-50 行 |
| groupedLayout.js | 空 SM 容器处理 | ~20-30 行 |

## B.5 可以移除的文件

| 文件 | 行数 |
|------|------|
| useServiceModuleSyntax.js | ~400 行 |
| serviceModuleDiagramBuilder.js | ~300 行 |
| resolveGroupContainers 相关 | ~120 行 |

**净减少代码**：~550 行

## B.6 方向A与方向B对比

| 维度 | 方向A | 方向B |
|------|-------|-------|
| 核心思路 | 统一数据结构 | 统一整个管线 |
| 删除代码 | ~100 行 | ~550 行 |
| 新增代码 | ~0 行 | ~100-150 行 |
| 净减少 | ~100 行 | ~400 行 |
| 视觉影响 | 无 | 无（B2） |
| 风险 | 低 | 中 |

## B.7 推荐路径

1. **Phase 1**：方向A（低风险）
2. **Phase 2**：验证方向B可行性
3. **Phase 3**：完整实现方向B

方向A简化了数据模型，为方向B铺垫。两者不冲突，可分阶段执行。

---

## B.8 详细分析参考

完整分析已记录到：`chats/SM图BO图统一模型重构分析-20260415.md`
