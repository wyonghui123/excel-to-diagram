# GroupModel 架构优化建议

## 2026-04-05：分组标题显示修复过程中发现的问题

---

## 问题背景

在修复"禁用父分组时子分组标题显示父级名称"的问题时，发现 GroupModel 存在多个架构和代码层面的问题，增加了调试和修复的难度。

---

## 1. ID 生成策略不一致

### 问题描述

| 数据来源 | ID 格式 | 示例 |
|---------|--------|------|
| GroupModel 内部 | `类型前缀_名称` | `SD_供应链计划` |
| 用户配置 | `group_时间戳_随机字符串` | `group_1775440964640_2lgthy117` |
| 架构数据 | `类型前缀_名称` | `D_供应链云` |

### 影响

- `mergeUserGroup` 需要多种匹配策略：id → elementCode → title
- 增加了代码复杂性和出错概率
- 调试时难以追踪 ID 对应关系

### 优化建议

```
方案 A：建立 ID 映射表
- 创建 unifiedId = hash(原始ID, 类型)
- 所有模块使用 unifiedId 进行匹配

方案 B：统一 ID 生成策略
- 用户配置使用与 GroupModel 相同的 ID 格式
- 或 GroupModel 支持解析 group_xxx 格式的 ID
```

---

## 2. 数据流不清晰

### 问题描述

- `updateEnabled` 方法定义了但从未被调用，系统却能正常工作
- `mergeUserGroup` 的调用路径不明确
- 禁用状态如何传递到 GroupModel 不清楚

### 影响

- 难以理解代码的执行路径
- 调试时需要大量追踪
- 可能存在隐藏的耦合

### 优化建议

```
方案：单向数据流 + 架构图

┌─────────────┐    用户操作    ┌─────────────────┐
│   UI 层     │ ───────────────▶ │  LayoutControl  │
└─────────────┘                └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │   UserConfig    │
                               │  (嵌套结构)     │
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │  GroupModel     │
                               │  (扁平结构)     │
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │   titleMap     │
                               └─────────────────┘
```

---

## 3. 嵌套结构处理不一致

### 问题描述

- 用户配置使用嵌套结构（children 树形）
- `mergeUserGroup` 只处理顶层 groups
- `getFlattenedGroups` 对嵌套结构有另一套处理逻辑
- 递归边界不明确

### 影响

- Case 2 的根因：children 中的禁用设置没有被合并
- 代码逻辑分散在多处，容易遗漏

### 优化建议

```javascript
// 统一的递归处理函数
function processUserGroupTree(userGroup, model) {
  // 1. 合并当前节点
  model.mergeUserGroup(userGroup)

  // 2. 递归处理子节点
  if (userGroup.children) {
    userGroup.children.forEach(child => {
      processUserGroupTree(child, model)
    })
  }
}

// 统一使用
userConfig.groups.forEach(g => processUserGroupTree(g, model))
```

---

## 4. 概念定义不清晰

### 问题描述

| 概念 | 当前实现 | 问题 |
|------|---------|------|
| `isEnabled` | `layout.enabled !== false` | 是分组本身的 enabled，还是继承父级？ |
| `_disabledAncestorPath` | 禁用时设置，启用时为 undefined | 语义不明确 |
| 禁用父级时 | 子分组是否继承禁用状态？ | 业务规则不明确 |

### 影响

- 规则理解不一致，导致实现逻辑混乱
- Case 3 正常工作但逻辑有隐藏问题

### 优化建议

```javascript
// 明确命名和语义
interface GroupState {
  ownEnabled: boolean           // 自身 enabled 状态
  inheritedEnabled: boolean     // 继承父级的 enabled 状态
  effectiveEnabled: boolean     // 最终 enabled 状态

  ownDisabled: boolean           // 自身是否被禁用
  inheritedDisabledFrom: string[] // 从哪些祖先继承的禁用路径
}

// 业务规则文档化
/**
 * 禁用规则：
 * 1. 如果自身被禁用（ownDisabled=true），effectiveEnabled=false
 * 2. 如果祖先被禁用，inheritedDisabledFrom 包含祖先标题
 * 3. 禁用路径只在叶子节点或自身禁用的节点上显示
 */
```

---

## 5. 缓存失效机制不透明

### 问题描述

```javascript
// 缓存定义
this._flattenedCache = null
this._mermaidConfigCache = null

// 失效时机
this._flattenedCache = null  // 在 mergeUserGroup 中
this._mermaidConfigCache = null  // 在 mergeUserGroup 中
```

### 影响

- 不清楚哪些操作会触发缓存失效
- 可能使用脏数据

### 优化建议

```javascript
// 方案 A：使用 Vue computed（如果适用）
const flattenedGroups = computed(() => {
  return buildFlattenedGroups(this.groups, this.options)
})

// 方案 B：使用不可变数据
class GroupModel {
  constructor(groups) {
    this.groups = freeze(groups)  // 不可变
    this._flattenedCache = null
  }

  mergeUserGroup(userGroup) {
    // 返回新的 GroupModel 实例，保留旧的
    const newGroups = updateGroup(this.groups, userGroup)
    return new GroupModel(newGroups)
  }
}
```

---

## 6. 调试基础设施缺失

### 问题描述

- 这次修复依赖大量手动添加 `console.log`
- 没有统一的日志框架
- 没有断点调试友好性

### 影响

- 调试效率低
- 日志格式不统一
- 难以过滤和搜索

### 优化建议

```javascript
// 建立结构化日志框架
const Logger = {
  create(category) {
    return {
      debug: (msg, data) => console.log(`[${category}] ${msg}`, data),
      warn: (msg, data) => console.warn(`[${category}] WARN: ${msg}`, data),
      error: (msg, data) => console.error(`[${category}] ERROR: ${msg}`, data),
    }
  }
}

const groupLogger = Logger.create('GroupModel')
groupLogger.debug('mergeUserGroup', { id, title, enabled })

// 或使用 DataFlowLogger（已有雏形）
DataFlowLogger.GroupModel.mergeUserGroup(userGroup, found)
```

---

## 7. 测试覆盖不足

### 问题描述

- `mergeUserGroup` 递归处理没有测试
- 禁用状态传递没有测试
- 嵌套结构场景没有覆盖

### 影响

- 边界情况容易出现 bug
- 回归风险高

### 优化建议

```javascript
describe('GroupModel', () => {
  describe('mergeUserGroup', () => {
    it('应该递归处理嵌套的 children', () => {
      // Case 2 场景
      const userConfig = {
        groups: [{
          id: 'D_供应链云',
          title: '供应链云',
          children: [{
            id: 'SD_供应链计划',
            title: '供应链计划',
            enabled: false
          }]
        }]
      }

      const model = GroupModel.fromUserConfig(architectureGroups, userConfig)
      expect(model.isEnabled('SD_供应链计划')).toBe(false)
    })
  })

  describe('禁用状态传递', () => {
    it('Case 1: 父禁用 + 子禁用 → 孙节点显示完整路径', () => { ... })
    it('Case 2: 父启用 + 子禁用 → 孙节点显示子路径', () => { ... })
    it('Case 3: 父禁用 + 子启用 → 子节点显示父路径', () => { ... })
  })
})
```

---

## 8. 缺乏错误处理和警告

### 问题描述

- `mergeUserGroup` 找不到分组时静默失败
- `updateEnabled` 从未被调用却无人知晓

### 影响

- 问题隐藏，难以发现
- 调试困难

### 优化建议

```javascript
mergeUserGroup(userGroup) {
  let group = this.groups.get(userGroup.id)

  if (!group) {
    console.warn(`[GroupModel] mergeUserGroup: group not found`, {
      searchedId: userGroup.id,
      searchedTitle: userGroup.title,
      availableIds: [...this.groups.keys()]
    })
    return false
  }

  // 成功处理
  return true
}

// 或使用断言
console.assert(group, `[GroupModel] mergeUserGroup failed to find group: ${userGroup.id}`)
```

---

## 优先级排序

| 优先级 | 优化项 | 理由 |
|-------|--------|------|
| P0 | 嵌套结构处理统一 | 已因此产生 bug |
| P0 | 概念定义清晰化 | 影响代码正确性 |
| P1 | 数据流文档化 | 便于维护和调试 |
| P1 | 调试日志框架 | 提升调试效率 |
| **P1** | **分组控制作为默认选项** | **简化代码，减少维护负担** |
| P2 | 测试覆盖 | 提升代码质量 |
| P2 | ID 映射策略 | 需要较大重构 |
| P3 | 缓存机制优化 | 当前机制可工作 |

---

## 9. 分组控制作为默认选项

### 背景

当前系统存在两套分组逻辑：
1. **分组控制模式**：使用 `GroupModel` 处理启用/禁用、标题显示
2. **非分组控制模式**：不使用 GroupModel，直接使用架构数据

这两套逻辑并存导致：
- 代码复杂度增加
- 测试覆盖困难
- 维护成本高
- 容易引入 bug（如本次修复的问题）

### 设计方案

#### 阶段 1：将分组控制设为默认

**UI 变更**：
```
配置面板
├── 基础选项（默认显示）
│   ├── 图表类型
│   ├── 布局方向
│   └── 颜色配置
│
└── 高级选项（折叠）
    ├── [ ] 启用旧版非分组控制  ← 新增
    ├── [ ] 拖尾线
    └── 其他高级配置
```

**行为变更**：
- 默认情况下始终使用 `GroupModel.fromUserConfig()`
- 即使 `userConfig = null`，GroupModel 也会以默认状态生成配置
- 非分组控制作为"兼容性选项"保留，供老用户过渡

#### 阶段 2：移除非分组控制代码

**前提条件**：
- 分组控制功能稳定，无重大 bug
- 老用户有足够时间迁移
- 旧版数据格式迁移完成

**需要清理的代码**：
1. `useDiagramData.js` 中的条件分支
2. `filterGroupModelByScope` 中的兼容逻辑
3. 非分组控制的专用处理函数
4. UI 中的切换开关

### 代码简化目标

**Before**（当前）：
```javascript
// useDiagramData.js
if (userConfig) {
  const groupModel = GroupModel.fromUserConfig(architectureGroups, userConfig)
  const layoutControlConfig = groupModel.toMermaidConfig()
} else {
  // 非分组控制逻辑
  const layoutControlConfig = buildLayoutControlConfigFromArchitecture(...)
}
```

**After**（目标）：
```javascript
// useDiagramData.js
const groupModel = GroupModel.fromUserConfig(architectureGroups, userConfig)
const layoutControlConfig = groupModel.toMermaidConfig()
```

### 实施步骤

#### 步骤 1：UI 改造
- [ ] 在配置面板添加"高级选项"折叠区
- [ ] 将"拖尾线"移入高级选项
- [ ] 添加"启用旧版非分组控制"复选框（默认不勾选）
- [ ] 勾选时显示警告："旧版模式将在未来版本移除"

#### 步骤 2：代码改造
- [ ] `GroupModel.fromUserConfig()` 始终执行，不再判断 `userConfig` 是否存在
- [ ] 将非分组控制逻辑封装为独立函数，标记为废弃
- [ ] 添加 deprecation warning

#### 步骤 3：文档和迁移
- [ ] 更新用户文档
- [ ] 添加迁移指南
- [ ] 设置弃用时间线（建议 2-3 个版本后移除）

### 风险和缓解措施

| 风险 | 缓解措施 |
|------|---------|
| 老用户习惯旧模式 | 保留兼容选项，提供充分过渡期 |
| 旧数据格式不兼容 | 提供数据迁移工具 |
| 功能回退 | 保留分支控制开关，可快速回滚 |

### 总结

将分组控制作为默认选项的设计目标是：
1. **简化代码**：减少维护的代码分支
2. **提升质量**：统一的数据流更易于测试
3. **降低复杂度**：减少新功能开发的学习成本
4. **未来可清理**：明确非分组控制为临时方案

这是一个**中短期优化**，建议在 GroupModel 稳定后实施。

---

## 总结

GroupModel 在功能上是正确的，但在代码质量和可维护性方面存在改进空间。主要问题集中在：

1. **数据流不清晰** - 需要文档化
2. **递归处理分散** - 需要统一
3. **概念命名不准确** - 需要澄清
4. **调试工具缺失** - 需要建设

建议按优先级逐步优化，提升代码的可维护性和可调试性。
