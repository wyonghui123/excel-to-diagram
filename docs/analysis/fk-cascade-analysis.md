# FK 联动交互方案分析

> 调研日期：2026-06-08
> 触发问题：新建业务对象，录入领域→子领域→服务模块后，变更领域时子领域/服务模块未清空，仍能选到旧值。

## 一、问题复现路径

1. 选 `domain_id = 5`（领域 A）
2. 选 `sub_domain_id = 30`（领域 A 下的子领域）
3. 选 `service_module_id = 100`（子领域 30 下的服务模块）
4. **重新选 `domain_id = 8`（领域 B）**
5. ❌ 现象：子领域/服务模块的 `formData` 值没被清空，dropdown 仍显示旧值，保存时把属于领域 A 的子领域 ID 提交，破坏数据一致性

## 二、我们当前的实现

### 2.1 yaml 声明（配置是齐的）

[meta/schemas/business_object.yaml:555-684](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L555-L684)：

```yaml
- id: domain_id
  value_help:
    behavior:
      parameter_bindings:
        - local_field: version_id
          target_field: version_id
          required: true

- id: sub_domain_id
  value_help:
    behavior:
      parameter_bindings:
        - local_field: domain_id
          target_field: domain_id
          required: true

- id: service_module_id
  value_help:
    behavior:
      parameter_bindings:
        - local_field: sub_domain_id
          target_field: sub_domain_id
          required: true
```

并且每个字段 ui 上有 `depends_on` / `cascade_group` / `cascade_level` 元数据。

### 2.2 后端筛选（filter 正确）

`useValueHelp.getFilterParams` ([useValueHelp.js:190-201](file:///d:/filework/excel-to-diagram/src/composables/useValueHelp.js#L190-L201))：
- 读取 `behavior.parameter_bindings`
- 把 `formValues[local_field]` 映射成 `filters[target_field]`
- 后端 `searchValueHelp` 用 filters 做 `WHERE domain_id = ?` 过滤
- ✅ 后端筛选**正确**

### 2.3 前端 options 联动（部分工作）

[ValueHelpField.vue:185-203](file:///d:/filework/excel-to-diagram/src/components/common/ValueHelpField.vue#L185-L203)：
```js
watch(() => bindingsKey(), (newKey, oldKey) => {
  if (newKey !== oldKey) {
    optionsList.value = []              // 清空 options
    if (bindingSatisfied.value) {
      const filters = getFilterParams(...)
      loadOptions('', { filters })      // 重新加载 filtered options
    }
  }
})
```

- ✅ 父字段变化时 **options 重新加载**（dropdown 显示新领域的子领域）
- ❌ **formData.sub_domain_id 没被清空**（旧值仍在前端 state）

### 2.4 ❌ 关键 bug：级联清空工具"就绪但未接线"

[useCascadeSelect.js:226-262](file:///d:/filework/excel-to-diagram/src/composables/useCascadeSelect.js#L226-L262) `useFormCascade.initialize()`：

```js
async function initialize() {
  // ... 推断父字段 ...
  if (!unwatch) {
    unwatch = cascade.watchParentChanges(formData, function(fieldId, _newValue) {
      cascade.clearAllDownstream(fieldId, formData.value)  // ← 父变 → 清空下游
    })
  }
}
```

[DetailPage.vue:194-197](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L194-L197)：
```js
const cascade = useFormCascade(
  computed(() => entityMeta.value),
  computed(() => data.value || {})
)
```

✅ 引入了 `useFormCascade`
❌ **从未调用 `cascade.initialize()`**！`watchParentChanges` 没注册 → `clearAllDownstream` 永远不执行。

**根因总结**：
| 层级 | 状态 |
|------|------|
| yaml 配置（声明式级联） | ✅ 齐全 |
| 后端 filter（按父筛选 options） | ✅ 正确 |
| 前端 options 联动（dropdown 重载） | ✅ 工作 |
| **`useFormCascade.initialize()` 接线** | ❌ **未调用** |
| **父变清空下游 formData** | ❌ **未生效** |

## 三、行业方案对比

### 3.1 Ant Design Form（声明式 dependencies）

```jsx
<Form.Item label="部门">
  <Select onChange={v => form.setFieldsValue({ owner: undefined, nodes: [] })} />
</Form.Item>
<Form.Item label="负责人" dependencies={['department']}>
  <Select options={ownerMap[dept] || []} />
</Form.Item>
```

- `dependencies` 触发重新渲染
- **不自动清空**——需手动 `setFieldsValue` 清空下游
- 优点：声明直观；缺点：清空逻辑散落各处

### 3.2 Formily（被动联动 / 主动 effects）

```jsx
<SchemaField.String
  name="department"
  x-component="Select"
  x-reactions={({ deps }) => {
    // 父变化时清空子
    return { target: 'owner', fulfill: { state: { value: '' } } }
  }}
/>
```

- **被动模式（passive）**：声明 target 字段，源变 → 自动 fulfill
- 也可写 `effects()` + `onFieldValueChange` 调 `setFieldState('owner', { reset: true })`
- 优点：依赖图自动维护；缺点：抽象重，小表单 overkill

### 3.3 Antd Cascader（单组件多级）

```jsx
<Cascader options={[
  { value: 'zhejiang', label: 'Zhejiang', children: [
    { value: 'hangzhou', label: 'Hangzhou', children: [...] }
  ]}
]} />
```

- 一个组件三层联动，值是数组 `['zhejiang', 'hangzhou', 'xihu']`
- **不适用**我们的场景：FK 跨多个对象的 attribute（如 domain_id 来自 domain 对象，sub_domain_id 来自 sub_domain 对象）
- 我们的子领域/服务模块是**扁平多个独立下拉**，不是嵌套 children

### 3.4 简道云 / 钉钉宜搭 / 飞书多维表格

[简道云官方文档](https://help.jodoo.com/en/articles/11476724-how-to-handle-related-forms-data-when-master-form-data-updates-or-is-deleted) 列出三种级联策略：
1. **同步更新（Synchronizing Updates）**：父变自动同步到子表
2. **级联删除（Cascading Delete）**：父删 → 子表记录全删
3. **级联清空（Cascading Clear）**：父删 → 子的 FK 字段清空，其他保留

> "Cascading Clear ... the corresponding field in the related form is cleared, but other data in the related form is kept."

- 行业共识：**级联清空**是标准模式
- 用户/PM 可在 automation 里选策略

### 3.5 Retool / ToolJet / Appsmith（低代码）

- 配 FK 关系时勾选"clear dependent fields on change"
- 默认行为：**父变自动清空所有引用字段**
- 这是 low-code 行业的事实标准

### 3.6 SAP / Oracle Forms（传统 ERP）

- 严格模式：FK 设定后**整张单据不能改 FK**（"Set up before save"）
- 或者 FK 变 → 弹窗确认是否级联清空/删除
- 工业风但用户学习成本高

## 四、对比矩阵

| 方案 | 父变清空子 | 用户可配策略 | 实现成本 | 我们的选择 |
|------|----------|------------|---------|-----------|
| Antd Form dependencies | ❌ 手动 | ❌ | 低 | - |
| Formily reactions | ✅ 自动 | ❌ | 中 | - |
| Formily effects+reset | ✅ 显式 | ❌ | 中 | - |
| Antd Cascader | N/A | N/A | 中 | 不适用 |
| 简道云/宜搭 | ✅ 标准 | ✅ | 低 | **方向参考** |
| Retool/ToolJet | ✅ 默认 | 部分 | 低 | **方向参考** |
| SAP/Oracle | ✅ 强制 | ❌ | 高 | - |
| **我们当前** | ❌ bug | ❌ | - | ❌ |

## 五、我们交互方案是否合理？

### 5.1 合理部分 ✅

- **yaml 声明式级联**是对的（不要硬编码）
- **后端 filter 而非前端拼接**是对的（性能 + 安全）
- **context 字段自动注入**（version_id）是对的
- **parameter_bindings + depends_on 分离**架构清晰

### 5.2 不合理部分 ❌

1. **`cascade.initialize()` 漏接**——核心 bug
2. **没有父变清空子策略**——简道云/Retool 都是默认行为
3. **没有"FK 不可改"语义提示**——`semantics.immutable: true` 已声明但 UI 没体现（domain_id 应该是新建后不能改，但当前允许改）
4. **没有提交时一致性校验**——如果前端没清空，后端直接 save，破坏数据
5. **没有用户可见的"级联提示"**——父变时弹"将清空子字段"会让用户安心

### 5.3 评估结论

**底层设计是对的，缺最后一公里**：
- yaml 配置齐
- 后端 filter 对
- 前端工具齐（`useFormCascade.clearAllDownstream`）
- ❌ 工具未接线 + ❌ 缺提交兜底校验

## 六、修复方向（待选）

### 方案 A：最小修复——接 cascade.initialize（最简）

```js
// DetailPage.vue onMounted
onMounted(async () => {
  // ... 现有逻辑 ...
  await loadEntityMeta()
  // [FIX] 启动级联监听
  cascade.initialize()  // ← 父变清空子
})
```

**行为**：父变 → 下游 formData 自动清空 + dropdown 重载
**风险**：低。`clearAllDownstream` 已实现
**不足**：清空时没有提示，用户可能意外丢失输入

### 方案 B：策略可配置（简道云风格）

yaml 加 `cascade_strategy: clear | warn | block`：

```yaml
- id: sub_domain_id
  semantics:
    cascade_strategy: warn  # clear/warn/block
```

- `clear`（默认）：父变 → 静默清空
- `warn`：父变 → 弹"将清空子字段，确认？" → 用户确认后清空
- `block`：父变 → 阻止保存（强制用户先手动清空）

**优点**：用户掌控 + 业务灵活
**风险**：中。需新增 yaml schema + 前端弹窗逻辑 + 后端校验

### 方案 C：声明式 reactions 引擎（Formily 风格）

引入统一的"字段反应"系统：

```js
const reactions = {
  'domain_id': [
    { when: 'changed', target: 'sub_domain_id', action: 'clear' },
    { when: 'changed', target: 'service_module_id', action: 'clear' },
  ],
  'sub_domain_id': [
    { when: 'changed', target: 'service_module_id', action: 'clear' },
  ],
}
```

**优点**：扩展性强，未来加"联动显示/联动校验"都顺
**风险**：高。当前只有一个 use case，过度设计

### 方案 D：FK 锁定（SAP 风格）

`semantics.immutable: true` 的字段在**新建后**立即 disabled（防止误改）。

- domain_id / sub_domain_id 在新建时是单选（context 注入），但当前允许用户改 domain_id
- 应该在保存前都是 readonly（值由 context 注入），保存后 = 主键

**优点**：彻底防止 FK 误改
**风险**：中。需要重新审视"FK 编辑"业务场景是否真需要

## 七、我的推荐

**方案 A + 方案 B 的轻量版**：

1. **接 `cascade.initialize()`**（方案 A 核心，5 行代码）
2. **加 `warn` 提示**（轻量版 B）：
   - 父字段变化 → 弹"ElMessageBox.confirm" → "将清空下游子领域/服务模块"
   - 用户取消 → 父字段回滚到原值
3. **后端兜底校验**：提交时检查 `sub_domain_id.domain_id == data.domain_id`，不一致返 400

这样既修了 bug，又给了用户控制感，还防止前端 bug 漏过。

## 八、待用户确认

- 是否采用 A+B 轻量版？
- 或者你倾向哪个方向？
- 是否要先看 UI 实际复现问题（我可以写个 UI 测试覆盖）？

---

### 附录：复现 UI 测试草稿

```python
# test_ui_cascade_clear.py
# 1. 登录 → 选产品+版本 → 切到"业务对象" tab
# 2. 新建 → 选 domain=A → 选 sub_domain=X → 选 service_module=Y
# 3. 把 domain 改成 B
# 4. 断言：
#    - sub_domain_id 是 null（不是 X）
#    - service_module_id 是 null（不是 Y）
#    - dropdown 不显示 X/Y
```

