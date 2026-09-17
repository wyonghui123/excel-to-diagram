# Rule Builder FK Picker 跨版本选择器 — 头部产品对标研究

> **研究日期**: 2026-09-11 | **状态**: Research Report (P3 续接输入) | **研究目的**: 在实施 Spec 20 Task 9.2 之前，对比头部产品（AWS IAM / Salesforce / SAP Fiori / Snowflake / Datadog / Notion-Airtable / Microsoft Power Apps / Retool）在「外键/资源选择器」中如何呈现「跨版本/属性匹配」与「仅此实例/具体 ID」的二元选择，给出本项目推荐方案。
>
> **研究范围**: UI 层 picker 形态（mode toggle / dual-tab / segmented / 物理分离 / 策略层），与 Spec §9 已有业界对标（业务键锚定整体概念，AWS IAM ABAC / Azure RBAC / Snowflake Future Grants / SAP PFCG）形成上下层互补。

---

## 一、研究问题

Rule Builder 中外键字段（FK / business_key / enum）的值控件走 `SearchHelpDialog` picker。当前 picker 只能选「具体记录 ID（数字）」。Spec 20 落地后，dimension_values 已能存「业务键（code 字符串）」，后端 resolve-preview 端点已能返回 `code → 当前命中实例数`。**前端 picker UI 尚未提供「跨版本（业务键）/仅此实例（ID）」切换**，这是 Task 9.2 的 P3 续接项。

待回答：

1. 头部产品如何表达「具体 ID」与「属性/范围匹配」的二元关系？
2. 模式切换的 UI 形态是什么？（toggle / radio / segmented / 双 tab / 物理分离）
3. 默认模式是什么？视觉如何提示「跨版本命中数」？
4. 错误回退（业务键拼错 / 当前 0 命中）如何呈现？
5. 本项目 Vue 3 + Element Plus + SearchHelpDialog 上下文，哪种方案最适合？

---

## 二、头部产品对比矩阵

| 产品 | 「具体 ID」入口 | 「属性/范围匹配」入口 | 模式切换 UI | 默认模式 | 命中数提示 | 错误回退 |
|------|----------------|---------------------|------------|---------|-----------|---------|
| **AWS IAM Visual Editor** | Resources 折叠区 → Add ARN → Visual ARN Editor modal（List ARNs / typeahead） | Request conditions 折叠区 → Condition Key/Qualifier/Operator/Value 四列行 | **两个独立折叠区**（无 toggle） | ARN | Validation tab 数字徽章（Security/Errors/Warnings/Suggestions） | 4 档警告 + `aws:TagKeys` 白名单 |
| **Salesforce Record Picker** | `lightning-record-picker` 单条 RecordId | Lookup Filter（Setup 级） + Criteria-Based Sharing Rule | **物理分离**（不同 UI 入口） | Record Picker 单选 | 无内置命中数提示 | `error.errorCode: 'ERR_RP00x'` 事件；Lookup Dialog 红字 "Record Not Found" |
| **SAP Fiori F4 Value Help** | Select From List Tab（单选/多选） | Define Conditions Tab（include/exclude 区间） | **Icon Tab Bar 顶部双 Tab** | Select From List | 无（解析在服务端） | "No items found" + 重载按钮 |
| **SAP PFCG Authorization** | Specific Value 单值 | Interval / Pattern（`*`、`?`）/ Full Authorization `*` | **专用表格行**（每行一个区间或通配） | Specific Value | Org Level 派生（父级选 → 子级自动） | 静态校验（值不在白名单则拦截） |
| **Snowflake Row Access Policy / Future Grants** | 无 picker UI（SQL 表达式） | SQL `CASE WHEN` + `GRANT ... ON FUTURE TABLES` | **完全无 picker**（策略层） | 策略层透明执行 | 无（透明执行） | 审计日志 |
| **Microsoft Power Apps PCF** | Static record list | Dynamic OData query | **Dual-Tab（Static / Dynamic）** | Static | Dynamic Tab 自定义渲染 | `error` 事件 |
| **Datadog Monitors** | Tag 精确 `key:value` | 通配符 `*` / `~` 排除（单输入框混合） | **无**（单输入框统一） | Tag 精确 | 无（标签不存在 = 不匹配） | 静默失败（治理纪律解决） |
| **Airtable Linked Record** | Cell 内嵌搜索 + 选中 | Formula 字段独立 | **完全分离**（字段类型不同） | Linked Record | 无 | 字段红字提示 |
| **Notion Relation** | Cell 内嵌搜索 + 选中 | Formula 2.0 独立 | **完全分离**（property 类型不同） | Relation | 无 | 字段变灰 |
| **Retool / Appsmith** | Select 组件（用户侧） | Query Builder（开发者侧） | **强制物理分离 + 角色分层** | Select 组件 | 无 | 开发者处理 |

---

## 三、四大 UI 模式分类

### 模式 A — 单输入框 + 通配符（Datadog 风格）

```
[ SCM*                                    ]   ← 单输入框
提示: * 匹配任意字符, ~ 前缀表示排除
```

**适用**: 标签维度少、取值空间稳定（如 K8s label）。

### 模式 B — Dual-Tab（Power Apps PCF 风格）

```
┌────────────────────────────────────┐
│  [ 具体记录 (Static) | 跨版本 (Dynamic) ]   ← 顶部 tab 切换
├────────────────────────────────────┤
│  [搜索 SCM...                ] [搜索]  │
│  ☐ SCM 供应链云 (命中 3)             │
│  ☐ FIN 财务域 (命中 5)                │
└────────────────────────────────────┘
```

**适用**: 双角色系统（业务+开发者），业务用户偶尔需要 Dynamic。

### 模式 C — Segmented 模式切换器（SAP Fiori 风格）

```
┌────────────┬────────────┬────────────┐
│ 仅此实例    │ 跨版本·业务键 │ 区间匹配   │   ← 顶部 segmented
└────────────┴────────────┴────────────┘
[选具体记录 / 输入业务键 / 输范围]
```

**适用**: 同一语义层级下有多选模式，UI 强制让用户先选模式再选值。

### 模式 D — 物理分离（Airtable / Notion / Retool 风格）

```
维度 1：[ picker (具体 ID)       ▼]   ← 永远只能选具体记录
维度 2：[ 输入 'SCM' 跨所有版本  ]   ← 独立属性匹配入口
```

**适用**: 两种语义有清晰的不同 UI 表达，混在一起反而混乱。

### 模式 E — 策略层（Snowflake 风格）

```
[后端透明执行 SQL 表达式]
[用户根本不感知模式选择]
```

**适用**: 跨版本自动化是企业级核心诉求时。

---

## 四、关键判断原则

1. **「具体 ID」是用户的工作产出 → picker；「具体 ID」是配置 → 策略**  
   - Datadog Monitor 是配置 → 用 picker（模式 A）  
   - Airtable 一行记录的关联 → 是工作产出 → 用 picker（模式 D 的 picker 端）  
   - Snowflake 行访问 → 是策略 → 用 E

2. **「跨版本自动化」只有 E 能根治**  
   - A/B/C/D 都需要用户/管理员**手动更新**  
   - E（策略层）是唯一「今天定义的规则，明天自动覆盖新对象」的方案  
   - 我们后端 `dimension_values` 业务键锚点（动态子查询）= **E 的轻量子集**

3. **业务用户不会主动切 toggle**  
   - 经验法则：Dual-Tab（模式 B）实际使用中 95% 用户只点 Static Tab

4. **AWS 是「不要在同一行切换」的最佳实践**  
   - Resource 区和 Condition 区是**两个独立折叠区**，不混在一起  
   - 理由：ARN 选择器与 Tag Key/Value 是完全不同的语义层级

---

## 五、本项目适配分析

### 5.1 当前 Rule Builder 上下文

| 维度 | 现状 | Spec 20 后端已具备 |
|------|------|------------------|
| Picker 触发 | `ConditionRuleRow.vue` 值列点击触发 `SearchHelpDialog`（**仅当 `usePicker=true`，见下方触发条件**） | — |
| Picker 主体 | `SearchHelpDialog`（已支持 hierarchical F4、左树右表） | — |
| 值存储 | `rule.value: string`（逗号分隔 ID 列表） | 后端 `_normalize_dim_values_to_ids` 放行字符串 |
| 业务键解析 | 不感知 | `POST /dimension-scopes/resolve-preview` 返回 `{code: {resolved_count, instances[]}}` |
| 视觉反馈 | tag chip 只显示 name/code | — |
| 默认模式 | 全是 ID | — |

### 5.1.1 ⚠️ 触发范围精确化（用户疑问解答）

> 用户的疑问："这里的优化是针对 Search Help 对吧，是针对字段 = ID 或者 business key 相关的时候会触发对吗"
>
> **答复：是的，但精确触发条件比"字段 = ID 或 business key"更窄**。证据：

#### 触发条件（来自 `ConditionRuleRow.vue:259-262`）

```js
const usePicker = computed(() => {
  const r = props.rule
  return r.relationObject || r.isBusinessKey || r.isEnum || (r.enumValues && r.enumValues.length > 0) || r.enumRef
})
```

**任一为真即触发 SearchHelpDialog**：
- `r.relationObject` 有值（FK 外键，指向另一 BO）
- `r.isBusinessKey` 为真（业务主键，自引用）
- `r.isEnum` / `r.enumValues` / `r.enumRef` 任一为真（枚举字段）

#### 本次"跨版本·业务键"优化生效的精确子集

> **当字段是「FK 且指向 hierarchy 维度 BO」或「业务主键自引用」时，才会进入本次双 Tab picker 优化范围。**

精确判定（来自 [rule-helpers.ts:64-73](file:///d:/filework/excel-to-diagram/src/components/common/ConditionRuleBuilder/rule-helpers.ts#L64-L73)）：

```js
} else if (HIERARCHY_DIMENSIONS.has(targetBo)) {
  // 命中 hierarchy 维度白名单 → display_mode='tree'
}
```

`HIERARCHY_DIMENSIONS = { product, version, domain, sub_domain, service_module, business_object }`

#### 哪些场景**不**在本次优化范围

| 场景 | `usePicker` | 行为 | 本次优化? |
|------|------------|------|----------|
| `enum` 字段（`status` / `priority`） | ✅ true | `sourceType='enum'`，渲染固定值列表，不走后端 | ❌ 不涉及 |
| FK 指向非 hierarchy BO（如 `creator_user_id`） | ✅ true | `display_mode='flat'`，普通列表 | ❌ 不涉及（没有"跨版本"语义） |
| **FK 指向 hierarchy 维度**（`domain_id` / `product_id` 等） | ✅ true | `display_mode='tree'`，hierarchical F4 | ✅ **是** |
| **业务主键自引用**（`id` / `code` 字段） | ✅ true | `display_mode='flat'` 或 `'tree'` | ✅ **是** |
| number / datetime / boolean 字段 | ❌ false | 走 ElInputNumber / ElDatePicker / AppSelect | ❌ 不走 picker |

#### "跨版本"语义的根因

只有 hierarchy 维度的 `code` 字段才有"跨 version 命中"的语义（`domain.code='SCM'` 跨所有 product+version 命中同名 domain）。其他字段（如 `creator_user_id`、`status`）没有"跨版本"概念，因为它们不依赖 version 维度存在。

因此「跨版本·业务键」Tab 的显示条件**与"是否命中 hierarchy 维度"等价**，不需要额外的元数据标志位。

### 5.1.2 ⚠️ 触发根因精确化（用户疑问解答 — 第二轮）

> 用户的疑问："可以理解为只有针对存在父对象的情况下，这个才有意义对吧，否则 id 和 business key 其实都是一样的，确认下这个理解正确吗"
>
> **答复：理解需要修正。** 关键不是「存在父对象」，而是「**同一 code 跨多份记录（跨版本 / 跨其他载体）多份实例**」。

#### 关键判据对比

| 概念 | 含义 | 是否触发业务键锚定 |
|------|------|------------------|
| **有父对象（FK 字段）** | `domain_id → domain`、`version_id → version` | ❌ **不是**触发条件 |
| **同一 code 跨多份记录** | `code='SCM'` 在 v01=64、v02=88、v03=90 共 3 行 | ✅ **是**触发条件 |

#### 反例（推翻"需要父对象"假设）

**`product`** 是 hierarchy 链的**根节点**（`PARENT_FIELD_MAP` 中没有 `product`），**没有父对象**：

```python
PARENT_FIELD_MAP = {
    'version': 'product_id',           # version 有父对象
    'domain': 'version_id',            # domain 有父对象
    'sub_domain': 'domain_id',         # sub_domain 有父对象
    'service_module': 'sub_domain_id', # service_module 有父对象
    'business_object': 'service_module_id',
    # product: 无父对象 — 是 hierarchy 链的根
}
```

但 `product.code` 仍然跨版本独立存在 — `product.code='PURCHASING'` 在 v01=1、v02=2、v03=3 各占一行。**没有父对象，但跨版本锚定依然成立**。

#### "ID 和 code 何时等价" 的精确边界

**只有当资源单实例（同一 code 只对应一行）时**，ID 与 code 等价：

| Case | 触发业务键模式有意义？ | 理由 |
|------|----------------------|------|
| 资源**单实例**（不重复） | ❌ 无意义 | ID=64 ↔ code='SCM' 互推，选哪个都一样 |
| 资源**跨版本重复** | ✅ **核心场景** | 选 ID 64 锁一行；选 code 'SCM' 自动覆盖 4 条同名记录 |
| 资源**仅在同版本内重复** | ⚠️ 视场景 | 选 ID 锁一个；选 code 锁一批；用户需明确意图 |

#### Spec 20 §1.3 实测数据佐证

> `BO_SUPPLIER` 跨 4 版本：`v01=64`、`v02=88`、`v03=90`、`v04=120`
>
> 选 ID 64 → 只命中 v01 一行
>
> 选 code `'BO_SUPPLIER'` → 命中 4 条全部

**这是「ID vs code」语义分化的根本动机**，与「是否存在父对象」正交。

#### 修正后的精确表述

> 业务键锚定的根本动机是：**「同一 code 在库内存在多份实例」**。
>
> hierarchy 链（product → version → domain → sub_domain）天然导致 `(version_id, code)` 联合下重复（每个 version 各建一份），所以 hierarchy 内的字段才有「跨版本」语义。
>
> 「跨版本·业务键」Tab 的显示条件不是「字段有父对象」，而是 **「字段所在 BO 的 `code` 在库内存在跨记录重复」** — 实际等价于 **「字段所在 BO 命中 `HIERARCHY_DIMENSIONS` 白名单」**（因为只有 hierarchy BO 才会出现跨版本重复）。
>
> 因此判定逻辑保持不变（用 hierarchy 白名单判定），但**根因要修正为"跨记录重复"而非"有父对象"**。

### 5.2 关键约束

- **Rule Builder 的 FK picker** 是「给已有值赋予语义」的 picker，不是策略编辑器 → 排除模式 E
- 业务用户不懂 SQL/正则 → 排除模式 D 的「输入 'SCM' 跨所有版本」自由文本
- 与 Spec 20 已落地的**矩阵锚点 UI**（PermissionConfigPanel 的「SCM（跨版本·命中 3）」chip）**保持视觉一致** — 用户已经在矩阵里看到过这种表述，picker 内出现类似 chip 会降低学习成本
- Element Plus 提供 `el-radio-button` segmented 与 `el-tabs` — 两种都可低成本实现

### 5.2.1 ⚠️ 通用性边界澄清（防误读）

> 用户的疑问："上面我理解是基于父子通用元模型的或者 hierarchy 的对吧，确认下"
>
> **答复：不基于父子通用元模型，也不基于 hierarchy 元数据。** 这里是两件不同的事，必须分清：

#### A. Rule Builder FK picker 上下文（本次任务真正要做的事）

- 字段元数据来源：后端 `permission_rule_api.get_field_metadata()` 返回 `{relation_object, is_business_key, field_type, is_foreign_key}`
- **不包含** `cascade_parent` / `is_hierarchy` / `parent_field` 等层级元数据
- picker 触发判定（`ConditionRuleRow.vue:262`）：`r.relationObject || r.isBusinessKey || r.isEnum || r.enumValues || r.enumRef`
- FK 是**平级引用**（`domain_id` → `domain` 对象），不是层级树
- 「跨版本」= **同一 code 跨多个 version_id 自动命中**，与父子层级无关

#### B. Hierarchical F4 Value Help（2026-07-22 已落地，是另一件事）

- 这是 *picker 内部*的「左树右表」让用户**浏览层级结构**
- 但**选中的仍是「具体一条实例」**，不是「一段 code 范围」
- hierarchy 是 picker 的**展示形态**，不是 code 锚点的判定依据

#### C. 「通用性」到底在哪里（与 hierarchy 无关）

| 通用性维度 | 落地形式 | 与 hierarchy 的关系 |
|----------|---------|-------------------|
| **跨 BO 通用** | 所有 `is_business_key=true` 或自引用字段（FK 指向自己）都生效 — 不限于 domain，也覆盖 product/version/BO | 无关 |
| **跨层级通用** | business_key 既可存在于 hierarchy 中间节点（domain/sub_domain），也可存在于叶节点（BO）；picker 不需要区分节点类型 | 无关 |
| **跨 picker 类型通用** | 同一套 `mode='instance'\|'code'` segmented 既能用于 FK、也能用于 enum、也能用于 business_key 自引用 | 无关 |
| **跨维度通用** | dimension_values 业务键锚定对所有 4 个维度（product/version/domain/sub_domain）通用 | 无关 |

#### D. 实施时禁止做的事

- ❌ 不要让 picker 读取 hierarchy / cascade_parent 元数据来决定 mode 切换 — 这些与 code 锚定正交
- ❌ 不要让 picker 树形展示（hierarchical F4）与 code 锚点 mode 互相干扰 — 两种特性可共存但不耦合
- ❌ 不要为 mode 切换引入新的字段元数据标志（如 `cross_version_supported`）— 直接用 `is_business_key` 与「值是否含非数字」自动判定

#### E. 一个边界 case：层级中间节点的「跨版本」是否还是同 code

是的，**无论节点在 hierarchy 哪一层，code 锚定的语义都是「跨所有 version 命中同 code 实例」**：
- product 是 hierarchy 根节点 → `code='PURCHASING'` 跨所有版本命中 product
- domain 是 hierarchy 中间节点 → `code='SCM'` 跨所有版本 + 所有 product 命中 domain  
- BO 是 hierarchy 叶节点 → `code='PO'` 跨所有版本 + 所有祖先链路命中 BO

这意味着 picker 内的 code list 永远不需要按 hierarchy 分组展示 — 后端 `/<bo>/codes` 端点返回的就是「该 BO 类型下所有去重 code + 每个 code 的全局命中数」，前端直接 flat 展示。

### 5.3 三选一决策

| 候选方案 | 模式 | 优点 | 缺点 | 推荐度 |
|---------|------|------|------|--------|
| **A. Picker 内 Segmented 模式切换（顶部 Single/Range/Code 切换）** | C | 用户进入 picker 前先选模式，语义清晰；与 SAP Fiori F4 同源 | 多一步交互；Rule Builder 行高只有 28px，picker 内 segmented 可能挤 | ⭐⭐⭐⭐ |
| **B. Picker 内 Dual-Tab（Static 记录列表 / Code 列表）** | B | 与 Power Apps PCF 同源；Static 维持现状，Code Tab 显示所有可锚定 code + 命中数 | Dual-Tab 用户多不切；Code 列表本身也是 picker（meta-picker） | ⭐⭐⭐ |
| **C. Picker 顶部一行 toggle chip：仅此实例 / 跨版本·业务键**（已选模式 → 决定下方 list 内容） | C 变体 | 最低学习成本；模式本身就是 picker 的「过滤器」；与 Spec 20 矩阵 chip 视觉一致 | 多一个组件；初次进入 picker 默认行为需明 | ⭐⭐⭐⭐⭐ |

---

## 六、推荐方案：Picker 顶部 Toggle Chip + 双 List 内容切换

### 6.1 UI 形态

```
┌────────────────────────────────────────────────────────────────┐
│  选择：领域                                              [X]   │
├────────────────────────────────────────────────────────────────┤
│  [ 仅此实例 (ID) ]  [ 跨版本·业务键 ]     ← 顶部 segmented     │
│  [搜索 SCM...                                ]   [搜索]        │
│                                                                │
│  ┌─ 仅此实例 ───────────────────────────────────────────────┐  │
│  │ ☐ 64  供应链云 v01                                       │  │
│  │ ☐ 88  供应链云 v02                                       │  │
│  │ ☐ 90  供应链云 v03                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ 跨版本·业务键 ─────────────────────────────────────────┐  │
│  │ ☐ SCM   供应链云 (当前命中 3 个实例)                     │  │
│  │ ☐ FIN   财务域    (当前命中 5 个实例)                    │  │
│  │ ☑ TYPO  (0 命中 · 红色警示)                              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│            [取消]                              [确定]          │
└────────────────────────────────────────────────────────────────┘
```

### 6.2 关键设计决策

1. **顶部 Segmented（非 Dual-Tab）**  
   - 模式 A/B 切换有强语义对立（具体 vs 跨版本），用 `el-radio-button` 横向 segmented 比 `el-tabs` 占用高度更少
   - 与 Spec 20 矩阵「包含 / 排除」segmented 视觉一致（已落地）

2. **同一 picker 内两个 list 内容不同**  
   - 「仅此实例」list：后端 instances API（按当前 version 过滤）
   - 「跨版本·业务键」list：后端新增 `/<bo>/codes` 端点，返回 `{code, resolved_count, warning?}`
   - 不在 list 中混入两种语义 — 避免 Datadog 通配符风格静默失败

3. **默认模式跟随字段类型**  
   - 字段 `is_business_key=true` → 默认「跨版本·业务键」（与 ConditionRuleDialog.loadFieldMetadata 默认选业务主键对齐）
   - 否则 → 默认「仅此实例」

4. **命中数视觉提示**  
   - `resolved_count >= 1`：绿色 chip `(命中 N)`
   - `resolved_count == 0`：红色 chip `(0 命中 · 当前无匹配)` + 整个行红框
   - 命中数随搜索关键字更新（用户输入 `SC` → 实时显示 `SCM (命中 3)` / `SCRMKT (命中 0)`）

5. **确认后回填 rule.value 形式**  
   - 「仅此实例」模式：`rule.value = "64,88,90"`（现状不变）
   - 「跨版本·业务键」模式：`rule.value = "SCM,FIN"`（后端 `_resolve_bizkeys` 已支持字符串）
   - **不**额外存储 mode 字段 — mode 由值是否全为非数字自动判断（与 Spec 20 `_is_anchor_code` 一致）

6. **pickerSelectedItems 同时支持两种模式**  
   - ID 模式：`[{id: 64, name: '供应链云 v01', code: 'SCM'}, ...]`
   - Code 模式：`[{code: 'SCM', resolved_count: 3, instances: [...]}]`
   - `RuleRow` 的 chip 显示：name + 模式徽章（仅跨版本显示「·跨版本」）

### 6.3 与现有能力的复用

| 已有能力 | 复用方式 |
|---------|---------|
| `SearchHelpDialog` 主体 | 内部新增 `<PickerModeSegmented>` + 两种 list 切换，不动 modal 框架 |
| `permissionService.loadDimensionInstances` | 复用为「仅此实例」list 的 fetcher |
| `permissionService.resolveDimensionScopePreview` | 复用为「跨版本·业务键」list 的 fetcher（按 code 拉命中数） |
| Spec 20 矩阵 chip 视觉 | picker 顶部 segmented 与矩阵「包含/排除」按钮同款 |
| `_is_anchor_code` 判定（后端） | 前端读取 `rule.value` 时调用同一判定逻辑决定 chip 显示模式 |

### 6.4 不推荐方案及理由

| 不推荐 | 理由 |
|--------|------|
| **Datadog 通配符单输入框** | 业务用户不知道 `*`/`~` 语法；与现有 picker 范式差异大 |
| **Power Apps Dual-Tab** | 95% 用户只点 Static；Segmented 比 Tab 占用更少高度 |
| **Airtable 完全分离（独立 Code 输入框）** | Rule Builder 是单字段单 picker 范式，加独立入口破坏一致性 |
| **SAP Range 模式** | 当前无 `from/to` 数据模型支持，引入成本大于收益 |
| **SAP Pattern 通配符** | 业务用户不懂通配符 |
| **Snowflake 策略层** | Rule Builder 是 picker 上下文，不是策略编辑器；本末倒置 |

---

## 七、实施要点（输入 Task 9.2 续接）

### 7.1 后端

- [ ] 新增 `GET /api/v1/<bo>/codes?q=&page=&page_size=` 端点
  - 返回 `[{code: 'SCM', resolved_count: 3, sample_instance_id: 64, sample_name: '供应链云 v01'}]`
  - 复用 `dimension_scope_engine._resolve_bizkeys` 做 code → 当前命中实例解析
  - 性能：受 v085 单列索引加持，O(N) 扫描

### 7.2 前端

- [ ] `SearchHelpDialog` 新增 `mode: 'instance' | 'code'` prop + 顶部 `el-radio-button` segmented
- [ ] `permissionService.loadDimensionCodes(bo, params)` 包装新后端端点
- [ ] `ConditionRuleRow.vue` 调用 picker 时根据 `rule.isBusinessKey` 决定初始 mode
- [ ] `pickerSelectedItems` 同时支持两种模式的数据结构（schema 已支持）
- [ ] 命中数为 0 的行：红框 + tooltip「当前无匹配实例，是否仍要使用？」
- [ ] 回填 `rule.value`：ID 模式不变，Code 模式存 `'SCM,FIN'` 字符串

### 7.3 测试

- [ ] Vitest：`SearchHelpDialog` 在 mode='code' 时显示 codes list + 命中数
- [ ] Vitest：0 命中 code 显示红色警示
- [ ] Vitest：rule.value 存储正确（混合模式如 `"64,SCM"`）
- [ ] E2E：Rule Builder 内选「跨版本·业务键」→ 后端 anchor 解析 → 矩阵 chip 显示「SCM（跨版本·命中 N）」
- [ ] E2E：刷新后回填 picker，mode segmented 自动恢复为「跨版本·业务键」

### 7.4 风险与缓解

| 风险 | 缓解 |
|------|------|
| Code list 数据量大（如 10k+ codes） | 分页 + 关键字过滤；与现有 instance list 一致 |
| 用户误选 0 命中 code | 0 命中红框 + 二次确认；后端 `_preflight_anchor_warnings`（Spec 20 Task 8 已落地）兜底 |
| 模式混淆（picker 内行为不一致） | mode segmented 在 picker 内显著位置，picker 关闭时 mode 不持久化（rule.value 自身决定） |
| 「跨版本·业务键」模式与现有 dimension_values 数字 ID 混存 | 后端 `_is_anchor_code` 已判定；前端不需要额外 mode 字段 |

---

## 八、官方文档引用清单

| 产品 | 关键文档 | URL |
|------|---------|-----|
| AWS IAM ABAC | Define permissions based on attributes with ABAC | https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction_attribute-based-access-control.html |
| AWS IAM Visual Editor | Create IAM policies (console) | https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create-console.html |
| AWS IAM Access Analyzer | IAM Access Analyzer policy validation | https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html |
| Salesforce Record Picker | lightning-record-picker (LWC) | https://developer.salesforce.com/docs/platform/lightning-component-reference/guide/lightning-record-picker.html |
| Salesforce Criteria-Based Sharing Rules | Criteria-Based Sharing Rules | https://help.salesforce.com/s/articleView?id=sf.security_sharing_rules_criteria.htm |
| Salesforce SOQL Relationship | SOQL relationship queries | https://developer.salesforce.com/docs/platform/salesforce-soql-sosl/guide/sforce-api-calls-soql-relationships.html |
| SAP Fiori Elements Value Help | Configuring Value Help | help.sap.com/docs/SAP_FIORI_elements |
| SAP ABAP Search Help | Search Help | help.sap.com/docs/SAP_ABAP |
| SAP PFCG Org Level | Authorization Objects (Organizational Level) | help.sap.com/docs/SAP_NETWEAVER_AS_ABAP_PLATFORM |
| Datadog Monitor Scope | Tags and Monitors | https://docs.datadoghq.com/monitors/configuration/?tab=thresholdalert#scope |
| Airtable Linked Record | Linked Record Field | https://support.airtable.com/docs/linked-record-field |
| Notion Relations | Relations & rollups | https://www.notion.so/help/relations-and-rollups |
| Microsoft Power Apps PCF | Component Framework | https://learn.microsoft.com/en-us/power-apps/developer/component-framework/overview |
| Microsoft Conditional Access | What is Conditional Access | https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview |
| Snowflake Row Access Policy | Row-level security | https://docs.snowflake.com/en/user-guide/security-row-intro |
| Snowflake Future Grants | GRANT | https://docs.snowflake.com/en/sql-reference/sql/grant-privilege |
| Retool Query Builder | Querying resources | https://docs.retool.com/apps/salesforce/querying-resources |

---

## 九、结论

> **核心结论**: 头部产品对「具体 ID vs 属性匹配」的处理呈四象限分布（toggle / segmented / 物理分离 / 策略层）。本项目 Rule Builder FK picker 的上下文（单字段单 picker + 业务用户 + 已有后端能力）最适合**「Picker 顶部 Segmented 模式切换 + 同一 picker 内双 list 内容切换」**（模式 C 变体）。该方案与 Spec 20 已落地的矩阵 chip 视觉一致、复用现有 `SearchHelpDialog` 与 `resolve-preview` 端点、避免 Datadog 通配符静默失败与 Power Apps Dual-Tab 使用率低的问题。
>
> **关键差异化**: 模式 C 变体不依赖单独存储 mode 字段，**靠 `rule.value` 是否含非数字字符串自动判定** — 与后端 `_is_anchor_code` 判定逻辑同源，零新存储 schema，新老值混存零迁移成本。
