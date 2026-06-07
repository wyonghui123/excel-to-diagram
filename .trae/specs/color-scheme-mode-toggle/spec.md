# 颜色方案模式切换 Spec

## Why

当前颜色方案主要针对两个场景：中心范围（高亮显示）和关系带来的非中心范围对象。但用户需要一个额外场景：不需要区分中心范围，严格按照领域→子领域→服务模块的层级结构分配颜色。

## What Changes

- 新增颜色方案模式开关：`centerScopeHighlight`（布尔值，默认 `true`）
- 当 `centerScopeHighlight: true` 时：保持现有逻辑，区分中心范围和关系范围
- 当 `centerScopeHighlight: false` 时：纯层级颜色方案，不区分中心，统一按 `domain + subDomain + serviceModule` 组合分配颜色
- 新模式下 Legend 不显示"中心范围"图例项
- 配置项 `centerScopeColor` 在新模式下不生效（但保留配置项）

## Impact

- Affected specs: 颜色配置、Legend 显示
- Affected code:
  - `ColorCalculator.compute()` - 新增 centerScopeHighlight 参数
  - `useDiagramData.js` - 透传 centerScopeHighlight 参数
  - `ServiceModuleConfig.vue` - 添加开关配置
  - Legend 组件 - 根据 centerScopeHighlight 决定是否显示中心范围图例

---

## ADDED Requirements

### Requirement: 颜色方案模式切换

系统 SHALL 提供 `centerScopeHighlight` 配置项，支持两种颜色方案模式。

#### Scenario: 区分中心范围模式（默认）
- **WHEN** `centerScopeHighlight: true`（默认）
- **THEN** 颜色按"中心范围 vs 非中心（关系带来）"区分
- **AND** Legend 显示"中心范围"图例项
- **AND** `centerScopeColor` 配置生效

#### Scenario: 纯层级模式
- **WHEN** `centerScopeHighlight: false`
- **THEN** 颜色按 `domain + subDomain + (colorGroupBy === 'serviceModule' ? serviceModule : '')` 组合分配
- **AND** 不区分 isCenter，所有节点统一按层级结构着色
- **AND** Legend 不显示"中心范围"图例项
- **AND** `centerScopeColor` 配置项存在但不生效

### Requirement: Legend 动态显示

Legend 组件 SHALL 根据 `centerScopeHighlight` 值动态决定是否显示"中心范围"图例项。

#### Scenario: 区分中心范围模式的 Legend
- **WHEN** `centerScopeHighlight: true`
- **THEN** Legend 显示中心范围项（使用 centerScopeColor）
- **AND** Legend 显示各层级颜色项

#### Scenario: 纯层级模式的 Legend
- **WHEN** `centerScopeHighlight: false`
- **THEN** Legend 不显示中心范围项
- **AND** Legend 仅显示按层级（领域/子领域/服务模块）着色的颜色项

---

## MODIFIED Requirements

### Requirement: ColorCalculator.compute()

**MODIFIED**: 新增 `centerScopeHighlight` 参数，当为 `false` 时忽略 `isCenter` 属性，统一按层级分配颜色。

#### Scenario: 纯层级模式颜色计算
- **WHEN** 调用 `ColorCalculator.compute()` 时 `centerScopeHighlight: false`
- **THEN** 颜色 key 仅基于 `domain + subDomain + (colorGroupBy === 'serviceModule' ? serviceModule : '')` 组合
- **AND** `isCenter` 属性不影响颜色分配

---

## 技术设计

### 配置项数据结构

```typescript
interface ColorConfig {
  colorGroupBy: 'domain' | 'subDomain' | 'serviceModule';
  colorScheme: string;
  centerScopeColor: string;      // 中心范围颜色（保留但不生效）
  centerScopeHighlight: boolean; // 新增：默认 true
  customColors: Record<string, string>;
}
```

### UI 位置

在 ServiceModuleConfig.vue 颜色配置区域，与 `colorGroupBy`、`colorScheme` 等选项放在一起。

### 实现要点

1. **ColorCalculator.compute()**：
   - 新增 `centerScopeHighlight` 参数
   - 当 `false` 时，颜色分配逻辑忽略 `isCenter`

2. **Legend 显示逻辑**：
   - 接收 `centerScopeHighlight` 参数
   - 当 `false` 时，不渲染中心范围图例项

3. **状态持久化**：
   - `centerScopeHighlight` 与其他颜色配置一起保存到 localStorage
