# ConditionRuleBuilder 通用条件规则配置组件

> **版本**: v1.0
> **日期**: 2026-08-26
> **状态**: 设计中 → 待实现
> **作者**: AI Agent
> **触发**: 用户提报「条件规则 Rule Builder 不通用，未支持嵌套 AND/OR」

---

## 一、背景与目标

### 1.1 当前痛点

1. **组件重复**：`ConditionRuleDialog.vue` 和 `ConditionRuleEditor.vue` 是两套独立的 Rule Builder 实现，违反 [UI_COMPONENT_GUIDELINES.md](../UI_COMPONENT_GUIDELINES.md) 中「复用现有组件」核心原则
2. **不支持嵌套**：现有 Rule Builder 用扁平数组 + `connector: 'AND' | 'OR'`，**无法表达 `(A AND B) OR (C AND D)`**
3. **命名不一致**：UI 暴露 `AND/OR` SQL 关键字给用户，不符合企业 UX 规范
4. **无可视化分组**：用户必须切到「高级模式 textarea」写表达式，可读性差

### 1.2 目标

- 抽取一个**通用**的 `<ConditionRuleBuilder>` 组件到 `src/components/common/`
- 支持**单层 AND/OR**（立即可用）+ **嵌套组**（进阶）
- 序列化**向后兼容**：现有 `flat` 表达式仍可读写
- 重构 `ConditionRuleDialog` 和 `ConditionRuleEditor` 都使用新组件
- 提供**清晰的组件 API**，便于业务侧继续扩展（不只是数据权限）

### 1.3 非目标

- 不重写后端 `condition_converter.py`（保持兼容）
- 不做 OR 的可视化「合并相同字段」优化（SAP GRC 才会做的脏活，留 backlog）
- 不动「权限维度」维度的另一个独立 UI（ConditionRuleEditor 的 dimension mode）

---

## 二、行业调研

### 2.1 头部产品方案

| 产品 | 嵌套支持 | 实现 |
|---|---|---|
| [Salesforce Lookup Filter](https://help.salesforce.com/s/articleView?id=sf.links_lookup_filters_overview.htm) | ✅ | 平面 + 顶层 AND/OR，不支持显式分组 |
| [Proofpoint Cloud Rule Editor](https://docs.public.analyze.proofpoint.com/admin/cloud/cloud_rule_editor/advanced_mode.htm) | ✅ | Condition Group 递归嵌套，无限层级 |
| [Lead Distro AI Buyer Filter](https://www.leaddistro.ai/docs/buyer-custom-field-filters) | ✅ | `(A AND B) OR (C AND D)` drag-and-drop |
| [JD Edwards Configurator](http://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoabc/bracket-selection-beginning-and-bracket-selection-ending.html) | ✅ | 显式括号 `(Seg 1 = A O Seg 2 = B) A Seg 3 = C` |
| [MetacatUI QueryBuilder](https://nceas.github.io/metacatui/docs/src_js_views_queryBuilder_QueryBuilderView.js.html) | ✅ | `nestedLevelsAllowed` 参数控制最大层级 |
| [SAP GRC Critical Permission](https://togglenow.com/learnings/how-to-build-custom-ruleset-for-critical-permission/) | ⚠️ | **不支持混合** AND/OR，强制 OR（反例）|

### 2.2 设计选择

采用 **Proofpoint 模型** + **MetacatUI 嵌套深度控制**：
- 树形结构，每层是「connector + 子节点列表」
- 嵌套深度上限 3 层（用户体验 + UI 可控性）
- 序列化时输出**带括号**的表达式（与现有 Python 表达式解析兼容）

---

## 三、数据模型

### 3.1 树形结构

```js
/**
 * 条件节点统一模型
 * - rule: 原子条件（叶子节点）
 * - group: 组合条件（内部节点）
 */
ConditionNode =
  | RuleNode
  | GroupNode

interface RuleNode {
  type: 'rule'                // 必填，标识是叶子
  id: string                   // 唯一 ID（UUID/nanoid）
  field: string                // 字段 db_column
  fieldType: string            // integer/float/datetime/text/string/boolean/enum
  operator: string             // =/!=/>/</>=/<= /晚于/早于/不早于/不晚于/包含/不包含/等于/不等于/在列表中/不在列表中
  value: string | number | boolean | Array
  // 关联元数据（用于 value picker）
  relationObject?: string
  isBusinessKey?: boolean
  isEnum?: boolean
  enumValues?: Array
  enumRef?: string
}

interface GroupNode {
  type: 'group'               // 必填，标识是组合
  id: string
  connector: 'AND' | 'OR'      // 当前组内子节点的连接方式
  children: ConditionNode[]    // 子节点数组（>= 1）
}
```

### 3.2 顶层默认结构

UI 初始状态总是 `GroupNode`：

```js
{
  type: 'group',
  id: 'root',
  connector: 'AND',
  children: [
    {
      type: 'rule',
      id: 'rule-1',
      field: 'id',
      fieldType: 'integer',
      operator: '=',
      value: ''
    }
  ]
}
```

### 3.3 与现有 flat 模型的对比

| 维度 | 现有 flat | 新树形 |
|---|---|---|
| 数据结构 | `Array<{connector, field, op, value}>` | `Tree<GroupNode | RuleNode>` |
| 顶层 connector | 无（首个元素无 connector） | 必有（root 节点） |
| 嵌套 | 不支持 | 支持（深度 ≤ 3） |
| 序列化 | `A AND B OR C` | `(A AND B) OR C`（带括号）|
| 兼容性 | 现有 | 向后兼容 |

---

## 四、组件 API

### 4.1 Props

```ts
defineProps({
  // 双向绑定的条件树
  modelValue: {
    type: Object as PropType<GroupNode>,
    required: true
  },
  // 字段元数据（用于字段下拉选项 + field type 判断）
  fieldMetadata: {
    type: Array as PropType<FieldMetadata[]>,
    default: () => []
  },
  // 资源类型（用于 picker 显示 "选择 {resource_type}..."）
  resourceType: {
    type: String,
    default: ''
  },
  // 最大嵌套深度（默认 3，MetacatUI 同款设计）
  maxNestingLevel: {
    type: Number,
    default: 3
  },
  // 是否禁用全部控件（用于只读预览）
  disabled: {
    type: Boolean,
    default: false
  },
  // 是否显示「显示表达式」预览框
  showPreview: {
    type: Boolean,
    default: true
  }
})
```

### 4.2 Emits

```ts
defineEmits<{
  'update:modelValue': [tree: GroupNode]          // v-model 同步
  'validate': [isValid: boolean, errors: string[]] // 校验结果
  'change': [tree: GroupNode]                     // 任意变动
}>()
```

### 4.3 Slots

```ts
defineSlots<{
  // 自定义字段渲染（高级用户场景）
  'field-cell'?: (props: { node: RuleNode }) => any
  // 自定义值渲染（高级用户场景）
  'value-cell'?: (props: { node: RuleNode }) => any
}>()
```

### 4.4 Exposed（给父组件调用）

```ts
defineExpose({
  /** 同步序列化结果到父组件的 customCondition / form.condition */
  syncToString(): string,
  /** 从字符串反序列化（暂不实现，前端 textarea 不强制同步 builder） */
  parseFromString(text: string): void,
  /** 校验当前条件树 */
  validate(): { valid: boolean; errors: string[] }
})
```

---

## 五、UI 设计

### 5.1 单层 AND/OR（v1，立即可用）

```
条件定义 *
┌──────────────────────────────────────────────────┐
│ [字段 ▼] [操作符 ▼] [值输入控件]              [×] │
│ [且][或] [字段 ▼] [操作符 ▼] [值输入控件]    [×] │
│ [且][或] [字段 ▼] [操作符 ▼] [值输入控件]    [×] │
│                                                  │
│ [+ 添加条件]                                     │
└──────────────────────────────────────────────────┘
```

复用 v25 已实现：
- 字段：`AppSelect`（来自 `customFieldOptions`）
- 操作符：`AppSelect`（按 `getOperatorOptions(fieldType)`）
- 值：5 个分支派发（picker / date / number / boolean / text）
- connector：`<ElRadioGroup>` 中文「且 / 或」

### 5.2 嵌套组（v2，spec 设计）

```
条件定义 *
┌──────────────────────────────────────────────────┐
│ [且 ▼]                                              │
│   [字段 ▼] [操作符 ▼] [值]                      [×] │
│   [字段 ▼] [操作符 ▼] [值]                      [×] │
│   [+ 添加条件] [⊕ 添加子组]                      │
│                                                  │
│   ─ 或 ─                                         │
│                                                  │
│   [且 ▼] 子组 #2                                  │
│     [字段 ▼] [操作符 ▼] [值]                   [×] │
│     [+ 添加条件] [⊕ 添加子组]                   │
│                                                  │
│ [+ 添加条件] [⊕ 添加子组]                        │
└──────────────────────────────────────────────────┘
```

- 子组 UI 用**缩进 + 左边框**区分（与 Tableau / Proofpoint 一致）
- 顶部 connector 切换「且/或」+ 缩进视觉提示「子组内部」
- 「⊕ 添加子组」按钮把当前 rule 转成 group + 提示用户加新条件

### 5.3 嵌套深度限制（v2）

`maxNestingLevel=3` 时：
- 顶级 group（depth=0）
- 子 group（depth=1）
- 孙 group（depth=2）
- 不能再添加（按钮 disabled）

实现：`RuleBuilderGroup.vue` 接收 `level: number` prop，递归调用自己。

---

## 六、序列化

### 6.1 输出格式

与 `condition_converter.py` 兼容的 Python 表达式：

```python
# 单层
"status = 'active' AND domain_id IN (1, 2, 3)"

# 嵌套
"(status = 'active' AND domain_id IN (1, 2, 3)) OR (created_at > '2026-08-01' AND is_active = true)"
```

**关键**：
- 嵌套 group **必须带括号**
- 括号内最后一条 rule **不带尾随 connector**
- 顶层 group **不带括号**（除非它本身是嵌套组的子节点）

### 6.2 序列化算法

```typescript
/**
 * 递归序列化条件树为 Python 表达式
 * [v1] 实现: ConditionRuleBuilder.serialize(tree) → string
 */
function serialize(node: ConditionNode): string {
  if (node.type === 'rule') {
    return serializeRule(node)
  }
  // group
  const parts = node.children.map(c => serialize(c))
  // connector 拼接（最后一个不带 connector）
  let result = parts[0]
  for (let i = 1; i < parts.length; i++) {
    result += ` ${node.connector} ${parts[i]}`
  }
  // 嵌套 group 才包括号（顶层不包，由父组件决定）
  return node.id === 'root' ? result : `(${result})`
}
```

### 6.3 兼容性保证

- v25 之前的 flat 模型序列化结果 `A AND B` 仍是合法输出
- 树形模型至少有一个 group 时，序列化结果也是合法的 flat 表达式
- 后端 `condition_converter.py` 无需改动

### 6.4 反序列化（Phase 5 实现）

为了**支持「编辑已存规则」**和**高级模式 textarea 双向同步**，需要反序列化：

```python
# 伪代码：用 Python ast 解析, 但前端用 PEG.js / 自写简单 parser
# [TODO Phase 5]: 解析器只支持单层 AND/OR（与 v25 兼容）
# 嵌套场景下用户必须用 builder 编辑（不允许 textarea）
```

---

## 七、迁移路径

### 7.1 Phase 1 (本周): spec + 单层组件抽取

1. 创建 `src/components/common/ConditionRuleBuilder/`
   - `ConditionRuleBuilder.vue`（主组件，单层版）
   - `ConditionRuleRow.vue`（单行 Rule，picker/date/number/boolean/text 五分支）
   - `index.js`
   - `types.ts`（RuleNode / GroupNode 类型）
   - `serializers.ts`（`serialize()` + 反序列化 stub）
   - `__tests__/ConditionRuleBuilder.spec.js`

2. 从 `ConditionRuleDialog.vue` 抽出 5 个值控件 + 字段元数据加载逻辑
3. 抽取 `getOperatorOptions(fieldType)` 到 `ConditionRuleBuilder` 模块

### 7.2 Phase 2 (下周): 嵌套支持

1. 新增 `RuleBuilderGroup.vue` 递归组件
2. 新增「⊕ 添加子组」按钮 + 嵌套深度限制
3. 序列化器升级支持嵌套（自动加括号）

### 7.3 Phase 3 (后续): ConditionRuleEditor 迁移

1. ConditionRuleEditor 的「自定义条件」tab 切换到 `<ConditionRuleBuilder>`
2. 保留「权限维度」dimension mode 不动（独立模块）

### 7.4 不破坏性保证

- ConditionRuleDialog 现有 API（emits `update:form.condition`）保持不变
- 条件树通过 v-model 双向绑定到父组件
- 序列化结果与 v25 flat 表达式**完全兼容**

---

## 八、风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 嵌套 UI 太复杂 | 用户困惑 | 嵌套深度 ≤ 3；提供折叠/展开 |
| 序列化与后端解析不兼容 | 保存失败 | Phase 1 不做嵌套，先保兼容 |
| 组件抽取破坏现有功能 | 回归 | 详细单元测试 + E2E 截图对比 |
| 字段元数据加载时机不对 | 首屏空白 | 父组件预加载 fieldMetadata 传入 |
| 反序列化复杂度高 | textarea 双向同步失败 | Phase 5 实现 + 仅支持单层 |

---

## 九、验收清单

### Phase 1 (单层)

- [ ] ConditionRuleDialog UI 与 v25 完全一致
- [ ] ConditionRuleEditor 「自定义条件」tab 切到新组件，UI 与之前一致
- [ ] 序列化结果与 v25 完全一致（5 种类型各跑一个 case）
- [ ] LIKE / IN / boolean / datetime / number 五种值控件正常
- [ ] 字段切换时 operator + value 重置（v23 修复保留）
- [ ] 单元测试覆盖：序列化、字段类型→操作符映射、5 个值控件

### Phase 2 (嵌套)

- [ ] 可创建嵌套组，UI 缩进清晰
- [ ] 嵌套深度 ≤ maxNestingLevel，超出禁用「添加子组」按钮
- [ ] 序列化结果带括号，后端能解析
- [ ] 嵌套 UI 截图与 Proofpoint / MetacatUI 风格一致

### Phase 3 (编辑器迁移)

- [ ] ConditionRuleEditor 「自定义条件」tab 完全切到新组件
- [ ] 现有 dimension mode 不受影响
- [ ] 无 console 报错、无回归

---

## 十、参考资源

- [UI_COMPONENT_GUIDELINES.md](../UI_COMPONENT_GUIDELINES.md) — 复用原则
- [ENTERPRISE_UI_BENCHMARK.md](../ENTERPRISE_UI_BENCHMARK.md) — 头部产品设计
- [condition_converter.py](../../meta/core/condition_converter.py) — 后端解析器（参考）
- [Proofpoint Cloud Rule Editor](https://docs.public.analyze.proofpoint.com/admin/cloud/cloud_rule_editor/advanced_mode.htm) — Condition Group 嵌套参考
- [MetacatUI QueryBuilder](https://nceas.github.io/metacatui/docs/src_js_views_queryBuilder_QueryBuilderView.js.html) — `nestedLevelsAllowed` 设计
- [Salesforce Lookup Filter](https://help.salesforce.com/s/articleView?id=sf.links_lookup_filters_overview.htm) — Field + Operator + Value 范式

---

## 十一、变更日志

| 日期 | 变化 | 作者 |
|---|---|---|
| 2026-08-26 | 初稿 | AI Agent |
