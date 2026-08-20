# Spec 09: 统一权限架构 — 三层分离模型

> 日期：2026-07-24 | 版本：v1.2 | 状态：设计草案，待评审
> 前置：Spec 01-08 (权限体系元数据驱动化升级 + 维度范围笛卡尔积)
> 决策来源：2026-07-23 ~ 2026-07-24 PM 系列架构讨论
> v1.2 修正: FR-011~016 (Layer 2深度审查), derivation_mode按维度类型区分, 推导管道12步

---

## 1. 背景与动机

### 1.1 当前系统的问题

Spec 01-08 建立了维度范围权限模型和条件规则模型，但存在三个核心问题：

**问题 1: 条件与维度割裂**

`ConditionPermissionService` 和 `DimensionScopeEngine` 在运行时完全没有交互，各自独立产出 SQL WHERE 谓词。管理员需要分别在两个 UI section 配置，看不到融合后的过滤效果。

**问题 2: 三层概念混杂**

当前系统将"权限事实"、"配置方式"、"交互方式"混在一起：
- `role_permissions` 既是配置输入又是检查依据
- `role_intents` 既是推导结果又是事实来源
- 维度范围、条件规则、菜单权限各自产生 Intent，但无统一编排管道

**问题 3: 条件类型分裂**

系统区分 dimension condition / owner condition / field condition 三种类型，但三者最终都生成 SQL WHERE 谓词（`field op value`），数据结构本质相同，分裂增加了模型复杂度。

### 1.2 设计目标

- **BO-01**: 建立三层分离架构（事实层 / 配置层 / 交互层），明确各层职责边界
- **BO-02**: Layer 1 统一为单一事实表，所有条件统一为 `field op value` 结构
- **BO-03**: Layer 2 通过字段元数据驱动推导，保留维度的层级展开和自动推导能力
- **BO-04**: Layer 3 支持高效配置（模板+推导）和细粒度配置（直接编辑事实）双模式
- **BO-05**: 与头部产品（SAP PFCG / Salesforce / Oracle VPD / AWS IAM）设计对齐

### 1.3 涉众目标

- SG-01: 管理员可通过模板和维度推导高效配置权限（90% 场景）
- SG-02: 高级管理员可直接编辑 Layer 1 事实表进行细粒度调整（10% 场景）
- SG-03: 开发者可通过字段元数据扩展新的维度字段，无需修改核心模型
- SG-04: 求值引擎统一处理所有条件，消除三分支逻辑

---

## 2. 三层架构总览

```
┌──────────────────────────────────────────────────────┐
│ Layer 3: 配置交互层 (Interaction)                     │
│   高效配置: 模板 + 维度推导 + 菜单勾选                 │
│   细粒度配置: 直接编辑 Intent 事实                     │
│   可视化: 推导链 + SQL 预览 + 冲突检测                 │
└──────────────────────┬───────────────────────────────┘
                       │ 渲染 + 提交
                       ▼
┌──────────────────────────────────────────────────────┐
│ Layer 2: 配置模型层 (Configuration)                   │
│   分组模型: 权限级别 / 菜单 / 组织 / 模板              │
│   推导管道: 维度→菜单→actions / 级别展开 / 条件生成    │
│   配置源: 6 个来源 → 统一推导 → Layer 1 事实           │
└──────────────────────┬───────────────────────────────┘
                       │ 推导 + 展开
                       ▼
┌──────────────────────────────────────────────────────┐
│ Layer 1: 核心权限模型 (Fact / Single Source of Truth) │
│   role_effective_intents 表                           │
│   Intent = (role_id, bo_id, action_name, data_scope)  │
│   data_scope: {include:[...], exclude:[...]}          │
│   derivation_mode: dynamic | static                   │
└──────────────────────────────────────────────────────┘
```

### 2.1 层间职责边界

| 层 | 职责 | 不做什么 |
|----|------|---------|
| Layer 1 | 描述"权限是什么" | 不关心"怎么来的" |
| Layer 2 | 描述"怎么高效生成事实" | 不直接被求值引擎使用 |
| Layer 3 | 描述"怎么让用户易用" | 不包含权限逻辑 |

### 2.2 与当前系统的映射

| 当前概念 | 三层模型归属 | 变化 |
|---------|-------------|------|
| `role_intents` 表 | Layer 1 | 升级为 `role_effective_intents`，增加 `data_scope` |
| `role_permissions` 表 | Layer 2 配置源 | 降级为配置输入，不再是直接检查依据 |
| `role_dimension_scopes` 表 | Layer 2 配置源 | 不变，作为维度配置输入 |
| `data_permission_rules` 表 | Layer 2 配置源 | 不变，作为条件规则配置输入 |
| `role_menus` 表 | Layer 2 配置源 | 不变，作为菜单授权输入 |
| `IntentPermissionChecker` | Layer 1 求值引擎 | 升级为读取 `role_effective_intents` |
| `menu_bo_linker` | Layer 2 推导管道 | 不变，菜单→BO actions 推导 |
| `DimensionScopeEngine` | Layer 2 推导管道 | 不变，维度展开+笛卡尔积 |

---

## 3. Layer 1: 核心权限模型（事实层）

### 3.1 设计原则

- **单一事实来源**：`role_effective_intents` 是权限检查的唯一依据
- **action 独立**：read / create / update / delete 各自独立，无隐含包含
- **条件统一**：所有数据范围条件统一为 `{field, op, value}` 结构
- **Deny 即 exclude**：否决通过 `data_scope.exclude` 表达，与 Spec 08 维度 exclude 语义统一

### 3.2 数据模型

> **2026-07-24 修正**: 移除独立 `is_denied` 字段，deny 改为 `data_scope.exclude` 表达，
> 与 Spec 08 维度 exclude 语义统一。Owner 优先级由求值引擎处理。

```sql
-- Layer 1: 权限事实表 (Single Source of Truth)
CREATE TABLE role_effective_intents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id         INTEGER NOT NULL,
    bo_id           TEXT NOT NULL,           -- 业务对象标识 (product / version / ...)
    action_name     TEXT NOT NULL,           -- 独立明细功能权限 (read / create / update / delete / list / ...)
    data_scope      TEXT,                    -- JSON: {include:[...], exclude:[...]} (空=全部数据)
    derivation_mode TEXT DEFAULT 'dynamic',  -- dynamic (CHILDREN_OF,默认) | static (IN,冻结)
    source          TEXT DEFAULT 'derived',  -- 来源标记 (derived / manual / template)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(role_id, bo_id, action_name, data_scope_hash)
);

-- data_scope JSON 结构 (include/exclude 统一):
-- {
--   "include": [                        -- 允许范围 (AND 连接)
--     {"field": "domain_id",     "op": "IN",  "value": [1,2,3]},
--     {"field": "sub_domain_id", "op": "IN",  "value": [101]},
--     {"field": "risk_level",    "op": "<=",  "value": 3},
--     {"field": "owner_id",      "op": "=",   "value": "${user.id}"}
--   ],
--   "exclude": [                        -- 排除范围 (原 deny, 一票否决)
--     {"field": "status",        "op": "=",   "value": "archived"}
--   ]
-- }
-- 空 include = 全部数据 (all 语义)
-- 空 exclude = 无否决
-- SQL 语义: WHERE include_conditions AND NOT exclude_conditions
```

### 3.3 action 独立性

Layer 1 中每个 action 是独立的 Intent 记录，**无隐含包含关系**：

```
角色 5 对 product 的权限:
  Intent 1: product:read    data_scope={domain_id IN (1,2,3), risk_level<=3}
  Intent 2: product:create  data_scope={domain_id IN (1,2,3), created_by=me}
  Intent 3: product:update  data_scope={domain_id IN (1,2,3)}
  Intent 4: product:delete  data_scope={owner_id=me}
  Intent 5: product:export  data_scope={exclude:[{field:"*", op:"=", value:"*"}]}  ← 禁止导出
```

**与当前 LEVEL_ORDER 的区别**：

当前系统 `write` 隐含包含 `read`（LEVEL_ORDER 比较），Layer 1 中 read 和 write 是独立 Intent。隐含包含关系移至 Layer 2 的权限级别分组（见 §4.2）。

### 3.4 条件统一：dimension / owner / field → field condition

**核心决策**：三种条件类型在 Layer 1 统一为 `field op value` 结构。

| 原类型 | 字段 | 操作符 | 值 | 统一后 |
|--------|------|--------|-----|--------|
| Dimension | domain_id | IN | [1,2,3] | `{field:"domain_id", op:"IN", value:[1,2,3]}` |
| Dimension | sub_domain_id | IN | [101] | `{field:"sub_domain_id", op:"IN", value:[101]}` |
| Owner | owner_id | = | ${user.id} | `{field:"owner_id", op:"=", value:"${user.id}"}` |
| Field | risk_level | <= | 3 | `{field:"risk_level", op:"<=", value:3}` |

> **通用规则引擎愿景**: `{field, op, value}` 是通用的条件表达式模型，未来应抽象为
> 统一的能力模块和组件，复用于权限规则、数据验证、工作流条件、业务规则、筛选器等场景。
> 当前作为权限模型的基础，后续可演进为通用 Rule Engine (见 §12)。

**统一的充分性验证**：

1. **维度层级展开** — 是 Layer 2 推导管道的逻辑，展开后结果就是 field condition
2. **Owner 优先级** — 是求值引擎的评估顺序，不是条件数据结构的差异
3. **维度自动推导菜单** — 是 Layer 2 基于字段元数据的推导，不是条件类型的区分

### 3.4.1 data_scope 语义矩阵

`include` 和 `exclude` 均为 `[{field, op, value}]` 条件列表，空列表 = all 语义：

| include | exclude | SQL | 含义 |
|---------|---------|-----|------|
| `[]` (空) | `[]` (空) | `WHERE 1=1` | 全部允许，无否决 |
| `[{conditions}]` | `[]` (空) | `WHERE conditions` | 允许匹配条件的 |
| `[]` (空) | `[{conditions}]` | `WHERE NOT (conditions)` | 全部允许，但排除匹配的 |
| `[{inc}]` | `[{exc}]` | `WHERE inc AND NOT (exc)` | 允许 inc，但排除 exc |

**`*` (all) 语义**：空数组 `[]` 即为 `*`，不需要特殊标记。与 AWS IAM `Resource: "*"` 和 SAP `BUKRS = *` 语义一致。

### 3.5 求值引擎

```python
class EffectiveIntentChecker:
    """Layer 1 权限求值引擎 (include/exclude 统一模型)"""

    def check(self, user_id, bo_id, action_name, record_context):
        role_ids = self._get_user_roles(user_id)
        intents = self._load_intents(role_ids, bo_id, action_name)

        # 优先级 1: Owner 条件 (字段元数据标记 is_owner, 不受 exclude 限制)
        for intent in intents:
            if self._has_owner_condition(intent):
                if self._evaluate_include(intent, user_id, record_context):
                    return {'granted': True, 'reason': 'owner'}

        # 优先级 2: Exclude 一票否决 (所有规则的 exclude 取并集)
        for intent in intents:
            if self._evaluate_exclude(intent, user_id, record_context):
                return {'granted': False, 'reason': 'excluded'}

        # 优先级 3: Include 允许 (任一规则 include 匹配即允许)
        for intent in intents:
            if self._evaluate_include(intent, user_id, record_context):
                return {'granted': True, 'reason': 'allow'}

        # 默认拒绝
        return {'granted': False, 'reason': 'no_matching_intent'}

    def _evaluate_include(self, intent, user_id, record):
        """统一条件求值 — include 部分的 field op value"""
        conditions = intent.data_scope.get('include', [])
        if not conditions:
            return True  # 空 include = all
        return self._evaluate_conditions(conditions, user_id, record)

    def _evaluate_exclude(self, intent, user_id, record):
        """统一条件求值 — exclude 部分的 field op value"""
        conditions = intent.data_scope.get('exclude', [])
        if not conditions:
            return False  # 空 exclude = 无否决
        return self._evaluate_conditions(conditions, user_id, record)

    def _evaluate_conditions(self, conditions, user_id, record):
        """统一条件求值 — 所有条件都是 field op value"""
        HIERARCHY_OPS = ('CHILDREN_OF', 'DESCENDANTS_OF', 'ANCESTORS_OF', 'ANCESTORS_ALL_OF')
        for cond in conditions:
            op = cond['op']

            # 层级继承操作符: 运行时查 hierarchy (双向)
            if op in HIERARCHY_OPS:
                if not self._evaluate_hierarchy(cond, record):
                    return False
                continue

            # 标准操作符: IN, =, !=, <, <=, >, >=
            value = self._resolve_value(cond['value'], user_id)  # ${user.id} → 159
            if not self._compare(record.get(cond['field']), op, value):
                return False
        return True

    def _evaluate_hierarchy(self, cond, record):
        """层级继承求值: 向下(CHILDREN_OF/DESCENDANTS_OF) + 向上(ANCESTORS_OF/ANCESTORS_ALL_OF)"""
        field = cond['field']
        field_value = record.get(field)
        if field_value is None:
            return False

        hierarchy = FIELD_METADATA[field].get('hierarchy')

        if cond['op'] in ('CHILDREN_OF', 'DESCENDANTS_OF'):
            # 向下: 验证 field_value 是 parent 的子节点/后代
            parent_field = cond['value']['parent_field']
            parent_value = record.get(parent_field)
            if parent_value is None:
                return False
            if cond['op'] == 'CHILDREN_OF':
                return hierarchy.is_direct_child(field_value, parent_value)
            elif cond['op'] == 'DESCENDANTS_OF':
                return hierarchy.is_descendant(field_value, parent_value)

        elif cond['op'] in ('ANCESTORS_OF', 'ANCESTORS_ALL_OF'):
            # 向上: 验证 field_value 是 child 的父节点/祖先
            child_field = cond['value']['child_field']
            child_value = record.get(child_field)
            if child_value is None:
                return False
            if cond['op'] == 'ANCESTORS_OF':
                return hierarchy.is_direct_parent(field_value, child_value)
            elif cond['op'] == 'ANCESTORS_ALL_OF':
                return hierarchy.is_ancestor(field_value, child_value)
```

### 3.6 条件操作符体系

Layer 1 统一条件模型支持以下操作符：

| 类别 | 操作符 | 方向 | 求值方式 | SQL 生成 | 示例 |
|------|--------|------|---------|---------|------|
| 等值 | `=`, `!=` | — | 直接比较 | `field = ?` | `status = 'active'` |
| 比较 | `<`, `<=`, `>`, `>=` | — | 直接比较 | `field <= ?` | `risk_level <= 3` |
| 集合 | `IN`, `NOT IN` | — | 静态值列表 | `field IN (?,?)` | `domain_id IN (1,2,3)` |
| **向下继承** | `CHILDREN_OF` | 父→子 | 实时查 hierarchy | `field IN (SELECT id FROM child WHERE parent IN (...))` | `sub_domain_id CHILDREN_OF domain_id` |
| **向下递归** | `DESCENDANTS_OF` | 祖先→后代 | 递归查 hierarchy | `WITH RECURSIVE ...` | 全层级后代 |
| **向上追溯** | `ANCESTORS_OF` | 子→父 | 实时查 hierarchy | `field IN (SELECT parent FROM child WHERE id IN (...))` | `domain_id ANCESTORS_OF sub_domain_id` |
| **向上递归** | `ANCESTORS_ALL_OF` | 后代→根 | 递归查 hierarchy | `WITH RECURSIVE ...` | 全层级回溯到根 |

**向上追溯 vs 角色层级向上继承（Salesforce式）**：

| 语义 | 例子 | 产品 | 我们如何处理 |
|------|------|------|------------|
| **维度值向上推导** | 能看sub_domain=采购供应 → 也能看domain=采购汇总 | Oracle (CONNECT BY PRIOR parent=id) | `ANCESTORS_OF` 操作符 |
| **角色位置向上继承** | 经理角色 > 员工角色 → 经理自动看员工数据 | Salesforce/Snowflake (Role Hierarchy) | 多角色并集 (经理角色配更宽维度范围) |

> **Oracle 对齐验证**: Oracle 是唯一原生支持双向层级查询的产品,
> `CONNECT BY PRIOR id = parent_id`(向下) 和 `CONNECT BY PRIOR parent_id = id`(向上).
> 我们的 `CHILDREN_OF` + `ANCESTORS_OF` 双向操作符与 Oracle 完全对齐.

**`CHILDREN_OF` vs `IN` 的语义区别**：

```python
# CHILDREN_OF: 动态继承, 随层级变化, 不触发笛卡尔积
{field: "sub_domain_id", op: "CHILDREN_OF", value: {parent_field: "domain_id"}}
# → "domain 的所有子节点" (层级变更自动反映)

# IN: 静态显式值, 触发笛卡尔积检测 (AC-008)
{field: "sub_domain_id", op: "IN", value: [101]}
# → "只有 101" (手动配, 笛卡尔积)
```

**结构继承 vs 语义继承**：

| 类型 | 例子 | Layer 归属 | 理由 | SAP 对应 |
|------|------|-----------|------|---------|
| **结构继承** (hierarchy) | domain → sub_domain | **Layer 1 事实** | 数据模型固有属性, `CHILDREN_OF` 操作符 | S_STRUCT INHER=X (运行时遍历 OM 树) |
| **语义继承** (derivation) | 菜单→BO actions, 级别→actions | **Layer 2 配置** | 业务推导策略, 可调整 | 派生角色 $BUKRS (配置时静态填充) |

> **SAP 验证**: SAP 同时使用两套继承机制 — 派生角色 (配置时静态, 对应 Layer 2) 和
> 结构化授权 (运行时动态, 对应 Layer 1 CHILDREN_OF)。大型企业混合使用:
> 基础权限用派生角色, HR 敏感权限用结构化授权。这验证了我们在两层分别放置
> 不同继承机制的正确性。

#### 向下 vs 向上推导的不对称性 (重要修正)

> **核心发现**: 向下推导和向上推导有本质不对称性, 决定了不同的存储策略。

**向下推导 (parent→children) — 集合是开放/动态的**:
- domain=供应链云 → sub_domain=[采购供应, 生产制造]
- 新增子领域"研发设计" → 子节点集合扩大
- **静态 IN 会过期** — 新子节点不被包含
- **CHILDREN_OF 永不过期** — 新子节点自动包含
- 语义: **数据范围定义** — "我能看哪些数据"

**向上推导 (child→parent) — 父节点是固定/稳定的**:
- sub_domain=采购供应 → domain=供应链云
- 新增兄弟子领域 → 采购供应的父节点不变
- **静态 IN 永不过期** — 父节点不因子节点增加而改变
- **ANCESTORS_OF 价值低** — 结果等价于静态IN
- 语义: **上下文导航** — "我能追溯到哪个父级"

| 维度 | 向下 (parent→children) | 向上 (child→parent) |
|------|----------------------|---------------------|
| 集合性质 | 开放集(可增长) | 闭集(固定) |
| 新增节点影响 | 新子节点→集合扩大 | 新兄弟→父不变 |
| 静态IN是否过期 | **会过期** | **永不过期** |
| CHILDREN_OF价值 | **高** — 解决过期 | — |
| ANCESTORS_OF价值 | — | **低** — 等价于静态IN |

#### 向下推导: 默认CHILDREN_OF, 可选冻结为静态IN

> **决策**: 向下推导**默认使用 CHILDREN_OF** (动态, 运行时求值), 因为子节点集合天然动态。
> 可选"冻结"为静态IN用于审计场景 (SAP派生角色式), 需重新推导机制。

**默认 (动态模式)**:
```python
{field: "sub_domain_id", op: "CHILDREN_OF", value: {parent_field: "domain_id"}, derivation_mode: "dynamic"}
# → 语义: "供应链云的所有子领域(当前值)"
# → 新增子领域自动生效
```

**可选 (冻结模式)**:
```python
{field: "sub_domain_id", op: "IN", value: [101, 201], derivation_mode: "static"}
# → 语义: "仅采购供应+生产制造(配置时快照)"
# → 新增子领域不生效, 需重新推导
# → 审计友好: 明确记录授予范围
```

**SAP双轨验证**: FI/CO/SD/MM用派生角色(静态IN, 接受过期), HR用S_STRUCT(CHILDREN_OF, 永不过期)。

#### 向上推导: 总是静态IN

> **决策**: 向上推导**总是使用静态IN**, 因为父节点天然稳定, 永不过期。
> ANCESTORS_OF降格为"理论完整但不常用"的操作符, 仅层级重构场景需要(极罕见)。

```python
# 向上推导: 总是静态IN (父节点稳定)
{field: "domain_id", op: "IN", value: [1], derivation_mode: "static"}
# → 供应链云, 永不过期
# → 父节点不因子节点增加而改变
```

**ANCESTORS_OF重新定位**: 仅在层级重构(节点移到新父)时有价值, 但层级重构本身是运维事件, 触发重新推导即可。

### 3.7 SQL 谓词生成

```python
def intent_to_sql_where(intent, user_id, table_alias=''):
    """将 Intent 的 data_scope (include+exclude) 转为 SQL WHERE 子句

    SQL 语义: WHERE include_conditions AND NOT exclude_conditions
    """
    data_scope = intent.data_scope or {}

    # include 部分
    include_conditions = data_scope.get('include', [])
    if not include_conditions:
        include_clause = '1=1'  # all 语义
    else:
        include_clause = _conditions_to_sql(include_conditions, user_id, table_alias)

    # exclude 部分
    exclude_conditions = data_scope.get('exclude', [])
    if not exclude_conditions:
        return include_clause

    exclude_clause = _conditions_to_sql(exclude_conditions, user_id, table_alias)
    return f"{include_clause} AND NOT ({exclude_clause})"

def _conditions_to_sql(conditions, user_id, table_alias=''):
    """将 [{field, op, value}] 条件列表转为 SQL WHERE 子句"""
    parts = []
    for cond in conditions:
        field = f"{table_alias}.{cond['field']}" if table_alias else cond['field']
        op = cond['op']

        if op in ('CHILDREN_OF', 'DESCENDANTS_OF', 'ANCESTORS_OF', 'ANCESTORS_ALL_OF'):
            # 层级继承: 生成子查询 (双向)
            parts.append(_hierarchy_to_sql(cond, table_alias))
        elif op == 'IN':
            value = resolve_runtime_variable(cond['value'], user_id)
            placeholders = ','.join(['?' * len(value)])
            parts.append(f"{field} IN ({placeholders})")
        elif op in ('=', '!='):
            value = resolve_runtime_variable(cond['value'], user_id)
            parts.append(f"{field} {op} ?")
        elif op in ('<', '<=', '>', '>='):
            value = resolve_runtime_variable(cond['value'], user_id)
            parts.append(f"{field} {op} ?")

    return ' AND '.join(parts)

def _hierarchy_to_sql(cond, table_alias=''):
    """层级继承操作符 → SQL 子查询 (双向)"""
    field = cond['field']
    meta = FIELD_METADATA[field]
    child_table = meta['child_table']
    parent_column = meta['parent_column']
    op = cond['op']

    if op == 'CHILDREN_OF':
        # 向下: 找子节点
        parent_field = cond['value']['parent_field']
        pf = f"{table_alias}.{parent_field}" if table_alias else parent_field
        return (f"{field} IN (SELECT id FROM {child_table} "
                f"WHERE {parent_column} = {pf})")
    elif op == 'DESCENDANTS_OF':
        # 向下递归: 所有后代
        parent_field = cond['value']['parent_field']
        pf = f"{table_alias}.{parent_field}" if table_alias else parent_field
        return (f"{field} IN (WITH RECURSIVE descendants AS ("
                f"SELECT id FROM {child_table} WHERE {parent_column} = {pf} "
                f"UNION ALL "
                f"SELECT c.id FROM {child_table} c JOIN descendants d ON c.{parent_column} = d.id"
                f") SELECT id FROM descendants)")
    elif op == 'ANCESTORS_OF':
        # 向上: 找父节点
        child_field = cond['value']['child_field']
        cf = f"{table_alias}.{child_field}" if table_alias else child_field
        return (f"{field} IN (SELECT {parent_column} FROM {child_table} "
                f"WHERE id = {cf})")
    elif op == 'ANCESTORS_ALL_OF':
        # 向上递归: 所有祖先到根
        child_field = cond['value']['child_field']
        cf = f"{table_alias}.{child_field}" if table_alias else child_field
        return (f"{field} IN (WITH RECURSIVE ancestors AS ("
                f"SELECT {parent_column} FROM {child_table} WHERE id = {cf} "
                f"UNION ALL "
                f"SELECT c.{parent_column} FROM {child_table} c JOIN ancestors a ON c.id = a.{parent_column}"
                f") SELECT {parent_column} FROM ancestors)")
```

---

## 4. Layer 2: 配置模型层（效率层）

### 4.1 设计原则

- **多配置源**：6 个配置源各自独立，通过统一推导管道生成 Layer 1 事实
- **字段元数据驱动**：维度的层级展开、Owner 的优先级等通过字段元数据标记触发
- **分组模型**：权限级别、菜单、组织等都是分组模板，展开为多个 action Intent
- **action condition 仅在 Layer 2**：Layer 2 配置可用 `{field: "action", op: "IN", value: [...]}` 一条规则覆盖多 action；Layer 1 保持 `action_name` 独立字段（范式化，求值高效）。推导管道负责 action condition → 多条 Intent 的展开

### 4.2 分组模型

#### 4.2.1 权限级别组 (Permission Level Bundle)

```python
# Layer 2: 权限级别是分组模板, 展开为多个 action
LEVEL_BUNDLES = {
    'none':  [],
    'read':  ['read', 'list', 'export'],
    'write': ['read', 'list', 'export', 'create', 'update', 'import'],
    'admin': ['read', 'list', 'export', 'create', 'update', 'import', 'delete'],
}
```

配置时选 `write` 级别 → 展开为 6 个 action 的 Intent。但每个 action 的 data_scope 可以独立细调：

```
产品 (product) — 配置级别: write
  展开为:
    product:read    data_scope={domain_id IN (1,2,3), risk_level<=3}
    product:list    data_scope={domain_id IN (1,2,3)}
    product:create  data_scope={domain_id IN (1,2,3), created_by=me}
    product:update  data_scope={domain_id IN (1,2,3)}
    product:import  data_scope={domain_id IN (1,2,3)}
    product:export  data_scope={domain_id IN (1,2,3)}

  细调 (高级模式):
    product:delete  data_scope={owner_id=me}  ← 单独添加, 级别提升到admin
```

> **action condition 泛化**: 权限级别是预定义的 action 分组。Layer 2 配置也支持
> 自定义 action condition，一条规则覆盖多 action：
> ```python
> # 自定义 action 分组 (比固定级别更灵活)
> rule = {
>     "bo_id": "product",
>     "conditions": [
>         {"field": "action", "op": "IN", "value": ["read", "list", "export"]},
>         {"field": "domain_id", "op": "IN", "value": [1,2,3]},
>     ]
> }
> # 推导管道展开为 3 条 Layer 1 Intent (action 各自独立)
> ```
> 这与 LEVEL_BUNDLES 本质相同——都是 action 分组展开，只是一个是预定义、一个是自定义。

#### 4.2.2 菜单组 (Menu → BO actions)

```python
# 基于现有 menu_bo_linker (FR-013, SAP SU24 等价物)
# 菜单的 bo_bindings → 自动推导 BO 默认权限

menu "架构数据管理":
  bo_bindings:
    - bo_id: product,     role: primary
    - bo_id: domain,      role: secondary
    - bo_id: sub_domain,  role: secondary

  → 推导 Intents:
    product:read, product:list, product:create, product:update
    domain:read, domain:list
    sub_domain:read, sub_domain:list
```

#### 4.2.3 组织维度组 (Organization → Dimension) — 未来扩展

> **当前状态**: 系统尚无组织管理模块，此分组为未来扩展预留。
> 当组织管理模块上线后，可通过此分组将组织关联到维度范围。

```python
# 未来扩展 (当前不实现): 组织关联维度范围
organization "采购部门":
  dimension_mapping:
    domain: 采购
    sub_domain: 采购供应

  → 关联到 data_scope.include:
    {field: "domain_id", op: "IN", value: [采购领域ID]}
    {field: "sub_domain_id", op: "IN", value: [采购供应ID]}
```

#### 4.2.4 模板组 (Template Bundle)

```python
# 预定义权限包
template "采购员标准权限":
  dimensions:
    domain: [采购]
    sub_domain: [采购供应]
  levels:
    product: write
    version: read
    sub_domain: read
  conditions:
    product: [{field: "risk_level", op: "<=", value: 3}]
  menus:
    - 采购管理
    - 架构数据管理

  → 一键应用, 生成完整 Intent 集合
```

### 4.3 字段元数据驱动推导

```python
# Layer 2: 字段元数据注册表
FIELD_METADATA = {
    "domain_id": {
        "is_dimension": True,
        "dimension_chain": "domain→sub_domain→service_module",
        "triggers_menu_derivation": True,
        "triggers_permission_derivation": True,
        "value_help_source": "domains",
        "cascade_filter": {"sub_domain_id": "domain_id"},  # 级联过滤
        "default_derivation_mode": "static",   # FR-015: 稳定维度, 默认IN
    },
    "sub_domain_id": {
        "is_dimension": True,
        "parent_field": "domain_id",        # 笛卡尔积检测 (AC-008)
        "dimension_chain": "sub_domain→service_module",
        "triggers_menu_derivation": True,
        "triggers_permission_derivation": True,
        "value_help_source": "sub_domains",
        "default_derivation_mode": "static",   # FR-015: 稳定维度, 默认IN
    },
    "owner_id": {
        "is_owner": True,                   # 求值引擎优先检查
        "runtime_variable": "${user.id}",
    },
    "risk_level": {
        # 普通字段, 无额外推导
        "value_type": "integer",
        "allowed_operators": ["=", "!=", "<", "<=", ">", ">="],
    },
    "status": {
        "value_type": "enum",
        "allowed_operators": ["=", "!=", "IN", "NOT IN"],
        "value_help_source": "status_enum",
    },
}
```

### 4.4 配置源

> **§7.2 修正**: 原6个配置源合并为3个真正源+2个辅助机制。
> 维度范围(role_dimension_scopes)和条件规则(data_permission_rules)产生相同输出({field,op,value}),
> 合并为统一规则表 permission_rules。权限级别是规则属性不是独立源, 模板是宏不是独立源。

```
真正的配置源 (3个):
┌──────────────────────────────────────────────────────┐
│ 源1: permission_rules (统一规则)                      │
│   = 维度范围 + 条件规则 + 权限级别 (三合一)           │
│   每条规则:                                           │
│     role_id, resource_type,                           │
│     permission_level (write → 展开为actions),         │
│     include_conditions: [{field,op,value}, ...],      │
│     exclude_conditions: [{field,op,value}, ...],      │
│     derivation_mode, inherit_children                 │
│                                                       │
│ 源2: role_menus (菜单授权)                            │
│   菜单 → BO actions 推导 (入口权限)                   │
│                                                       │
│ 源3: role_intents_manual (手动Intent)                 │
│   直接 Layer 1 事实, 最高优先级                       │
└──────────────────────────────────────────────────────┘

辅助机制 (不是配置源):
┌──────────────────────────────────────────────────────┐
│ LEVEL_BUNDLES: action 展开模板                        │
│   write = {read, list, create, update, import}        │
│                                                       │
│ permission_templates: 配置宏                          │
│   应用时展开为源1+源2的条目, 非独立源                 │
└──────────────────────────────────────────────────────┘
```

**头部产品配置源数量对比**:

| 产品 | 配置源数 | 说明 |
|------|---------|------|
| SAP PFCG | 2 | Menu + Auth Data(统一) |
| Salesforce | 2 | Profile + PermSet |
| AWS IAM | 1 | Policy Document(统一) |
| Oracle VPD | 1 | Policy Function(统一) |
| **我们** | **3** | permission_rules + role_menus + manual |

**统一规则表**:

```sql
CREATE TABLE permission_rules (
    id INTEGER PRIMARY KEY,
    role_id INTEGER NOT NULL,
    -- 对象+权限级别 (Model B)
    resource_type       VARCHAR NOT NULL,
    permission_level    VARCHAR NOT NULL,
    -- 统一数据范围 (维度+条件统一)
    include_conditions  TEXT,    -- JSON: [{field, op, value}, ...]
    exclude_conditions  TEXT,    -- JSON: [{field, op, value}, ...]
    -- 维度特有属性
    derivation_mode     TEXT DEFAULT 'auto',
    inherit_children    INTEGER DEFAULT 1,
    -- 元数据
    source              TEXT DEFAULT 'manual',
    template_id         INTEGER,
    priority            INTEGER DEFAULT 0,
    is_enabled          INTEGER DEFAULT 1
);
```

**原3表映射**:

| 原表 | 新表映射 |
|------|---------|
| role_dimension_scopes | include_conditions=[{field:dim+"_id", op:mode, value:vals}] |
| data_permission_rules | include_conditions=[...field conditions...] |
| role_permission_levels | permission_level 字段 (每条规则自带) |

### 4.5 推导管道

```
源1: permission_rules (统一) ──┐
源2: role_menus ───────────────┼──→ 统一推导管道 ──→ role_effective_intents
源3: role_intents_manual ──────┘
     ↑ 模板展开时写入源1+源2
```

**推导步骤**：

```
Step 1: 加载3个配置源
Step 2: 加载对象基线 (object_owd) — FR-012, 可选
Step 3: 统一展开 (permission_rules → Layer 1 Intents)
  - 维度字段 (FIELD_METADATA.is_dimension=True):
    · 层级展开 (domain=all → sub_domain展开)
    · 笛卡尔积检测 (domain=all + sub_domain=[101] → {101})
    · derivation_mode由FIELD_METADATA.default_derivation_mode决定
  - permission_level → LEVEL_BUNDLES展开为actions
  - 非维度字段 → 直接作为field_conditions
  - Owner字段 (is_owner=True) → 标记优先级
  - exclude_conditions → data_scope.exclude
Step 4: 维度→菜单推导 (derive_recommended_menus)
Step 5: 菜单→BO actions 推导 (menu_bo_linker) + 反向建议 (FR-011)
Step 6: 冲突解决 (源优先级: manual > template > derived) — FR-013
Step 7: 合并 → 写入 role_effective_intents (含 derivation_mode 标记)
Step 8: 标记受影响的静态Intent为stale (若维度层级变更) — FR-014
```

> **简化效果**: 步骤从12步降到8步, 源从6降到3, 与头部产品配置源数量(1~2个)对齐。

### 4.5 笛卡尔积语义在统一模型中的位置

AC-008 修复（Spec 08）在统一模型中自然保留。笛卡尔积检测从 DimensionScopeEngine 移至推导管道的 Step 2：

```python
# 推导管道 Step 2: 维度展开 + 笛卡尔积
def expand_dimensions_with_cartesion(scopes):
    expanded = {}
    for dim_code, scope in scopes.items():
        if scope.scope_mode == 'all':
            # 检查子维度是否有显式 include
            if has_explicit_include_for_child_dim(scopes, dim_code):
                # 笛卡尔积: 父 all AND 子 include 精确值
                break  # 不沿链展开
            else:
                # 沿链展开
                expanded[dim_code] = get_all_values(dim_code)
                expanded.update(expand_children(dim_code))
        elif scope.scope_mode == 'include':
            expanded[dim_code] = scope.dimension_values

    # 转换为统一 field conditions
    return [
        {"field": f"{dim_code}_id", "op": "IN", "value": list(vals)}
        for dim_code, vals in expanded.items()
    ]
```

---

## 5. Layer 3: 配置交互方案（体验层）

### 5.1 双模式设计

#### 模式 1: 高效配置（90% 场景）

```
┌──────────────────────────────────────────────────────┐
│ 角色权限配置 — [采购员]                                │
├──────────────────────────────────────────────────────┤
│                                                      │
│ Step 1: 选择起点                                     │
│   [采购员标准模板 ▼]  [复制角色▼]  [从零开始]        │
│                                                      │
│ Step 2: 配置维度范围 (自动推导菜单+功能权限)          │
│   领域: [采购 ▼]  子领域: [采购供应 ▼]               │
│   → 自动推导: 采购管理菜单 + product:read 等          │
│                                                      │
│ Step 3: 选择权限级别 (展开为 actions)                 │
│   产品: [读写 ▼]  → read,list,create,update,import   │
│   版本: [只读 ▼]  → read,list,export                 │
│                                                      │
│ Step 4: 添加条件约束 (细化 data_scope)                │
│   产品·读写: + 风险等级 ≤ 3                           │
│   产品·删除: + 创建者 = 本人 (单独细调 delete)        │
│                                                      │
│ Step 5: 补充菜单 (手动追加)                           │
│   ☑ 系统管理 [手动]                                  │
│                                                      │
│ Step 6: 预览 + 保存                                   │
│   [查看推导链] [查看SQL] [查看匹配资源] [保存]        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

#### 模式 2: 细粒度配置（10% 高级场景）

```
┌──────────────────────────────────────────────────────┐
│ [高级模式] — 直接编辑 Layer 1 事实                    │
├──────────────────────────────────────────────────────┤
│                                                      │
│ 产品 (product):                                     │
│ ┌────────────┬──────────────────────────┬──────────┐ │
│ │ action     │ data_scope               │ exclude  │ │
│ ├────────────┼──────────────────────────┼──────────┤ │
│ │ read       │ domain_id IN (1,2,3)     │ —        │ │
│ │            │ AND risk_level <= 3       │          │ │
│ │ list       │ domain_id IN (1,2,3)     │ —        │ │
│ │ create     │ domain_id IN (1,2,3)     │ —        │ │
│ │            │ AND created_by = ${user} │          │ │
│ │ update     │ domain_id IN (1,2,3)     │ —        │ │
│ │ delete     │ owner_id = ${user.id}    │ —        │ │
│ │ export     │ (全部)                   │ ⛔ 全部  │ │
│ └────────────┴──────────────────────────┴──────────┘ │
│ [+ 添加 action]                                      │
│                                                      │
│ 版本 (version):                                     │
│ ┌────────────┬──────────────────────────┬──────────┐ │
│ │ read       │ (继承 product 维度)       │ false    │ │
│ │ list       │ (继承 product 维度)       │ false    │ │
│ └────────────┴──────────────────────────┴──────────┘ │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 5.2 交互优化

#### 5.2.1 推导链可视化

```
维度范围: 领域=采购, 子领域=采购供应
    │
    ├─→ 自动推导菜单: 采购管理 [自动]
    │       │
    │       └─→ menu_bo_linker 推导 BO actions:
    │             product: {read, list, create, update}
    │             domain: {read, list}
    │             sub_domain: {read, list}
    │
    ├─→ 权限级别: write
    │       └─→ 展开: read, list, export, create, update, import
    │
    └─→ 条件规则: 风险等级 ≤ 3
            └─→ 追加到 product:read 的 data_scope

点击任意节点可查看/修改来源配置
```

#### 5.2.2 实时 SQL 预览

```
融合 SQL 预览 (product:read):
  SELECT * FROM product
  WHERE domain_id IN (1, 2, 3)
    AND sub_domain_id IN (101)     -- 笛卡尔积生效
    AND risk_level <= 3            -- 条件规则
    AND status = 'active'

  📊 预估匹配: 约 142 条 (占总量 8.3%)
  [查看匹配资源列表]
```

#### 5.2.3 冲突检测

```
⚠ 冲突检测:
  1. product:delete 的 data_scope (owner_id=me)
     比 product:update 的 data_scope (全部) 更窄
     → 用户可修改所有数据, 但只能删除自己的
     → 这是预期行为吗? [确认] [调整]

  2. product:export 存在 Deny 规则 (全部)
     → 即使其他规则允许 export, 也会被一票否决
     → 确认要禁止导出吗? [确认] [调整]
```

#### 5.2.4 差异对比

```
修改前 vs 修改后:
  + 新增: product:delete (data_scope: owner_id=me)
  + 新增: product:export (is_denied: true)
  ~ 修改: product:read (data_scope 新增 risk_level<=3)
  - 移除: product:import
```

### 5.3 权限级别包含关系提示

UI 中权限级别选择应显示包含关系：

```
权限级别:
  ○ 无权限 (none)     — 0 个 actions
  ○ 只读 (read)       — 3 个 actions: read, list, export
  ● 读写 (write)      — 6 个 actions: 包含只读 + create, update, import
  ○ 完全管理 (admin)  — 7 个 actions: 包含读写 + delete
```

---

## 6. 头部产品对比研究

### 6.1 配置模型对比

| 维度 | SAP PFCG | Salesforce | Oracle VPD | AWS IAM | **本方案** |
|------|----------|------------|------------|---------|-----------|
| 权限级别位置 | ACTVT, 同条目 | Access Level, 同规则 | statement_types, 同策略 | Action, 同Statement | action_name, 同Intent |
| 范围定义 | 业务字段值域 | Owner/Criteria | WHERE谓词函数 | Resource+Condition | data_scope.conditions |
| 级别与范围关系 | 同条目绑定 | 同规则绑定 | 策略级绑定 | 同Statement | 同Intent绑定 |
| Deny支持 | ❌ | ❌ | ❌ | ✅ 显式Deny | ✅ data_scope.exclude |
| 条件结构 | 结构化字段值 | 结构化Criteria | 自由SQL函数 | 结构化Condition | 统一 {field,op,value} |
| 条件类型区分 | ❌ 不区分 | ❌ 不区分 | ❌ 不区分 | ❌ 不区分 | ❌ 不区分(统一) |
| 多级别配置 | 多条目不同ACTVT | 多规则不同Level | 多策略不同statement | 多Statement不同Action | 多Intent不同action |

### 6.2 层级继承机制对比

| 维度 | SAP | Salesforce | Oracle VPD | AWS IAM | **本方案** |
|------|-----|-----------|------------|---------|-----------|
| **层级继承方向** | 向下 (INHER=X) | 向上 (上级见下级数据) | 任意 (函数控制) | 向下 (SCP继承) | 向下 (CHILDREN_OF) |
| **继承时机** | 双轨: 派生(静态)+结构(动态) | 运行时 | 运行时 | 运行时(评估链) | 运行时 (CHILDREN_OF) |
| **Deny/Exclude** | 无 | 无 | 无(谓词AND) | 显式Deny ✅ | exclude ✅ |
| **条件结构** | 字段值域(结构化) | Criteria(结构化) | PL/SQL(自由) | JSON Condition(结构化) | `{field,op,value}`(结构化) |
| **层级变更自动生效** | 仅结构化授权 | 是 | 是 | 是 | 是 (CHILDREN_OF) |
| **多维度** | 多授权对象 | Territory Mgmt | 多Policy | 多SCP | 维度范围+条件 |
| **Layer 1 对应** | S_STRUCT INHER=X | Role Hierarchy | Policy Function | SCP评估链 | CHILDREN_OF操作符 |
| **Layer 2 对应** | 派生角色 $BUKRS | Sharing Rules | — | IAM Policy | 推导管道 |

**Salesforce Role Hierarchy**: 运行时向上继承, 上级自动拥有下级数据访问权限 (`Grant Access Via Hierarchies` 默认开启)。
无配置时展开概念, 是最纯粹的"结构继承是事实属性"实现。补充 Territory Management 按区域/产品线多维度控制。

**Oracle VPD Policy Function**: PL/SQL 函数可做任何事 — 查层级(`CONNECT BY`)、查权限表、查上下文。
最灵活但代价高(不可审计/不可UI配置/性能不可预测)。我们的 `CHILDREN_OF` 是其结构化子集。

**AWS IAM SCP + OU Hierarchy**: SCP 挂在 OU 上, 子 OU 自动继承, 向下取交集(越往下越严)。
评估链: SCP(护栏) → Permission Boundary(上界) → IAM Policy(授权) → Resource Policy(资源限制)。
与我们的求值引擎最接近: Owner → exclude → include → 默认拒绝。

### 6.2 Layer 2 配置模型深度对比

#### 6.2.1 SAP PFCG 配置模型

```
PFCG 配置流程 (Layer 2):
┌─────────────────────────────────────────────────────────┐
│ Step 1: 配菜单 (Menu页签)                                │
│   → 添加事务码 (ME21N/ME22N/ME23N)                      │
│   → 或创建区域菜单 (SE43, 按业务逻辑组织)                │
│   → 或从ST01 Trace导入 (基于实际使用记录)                │
│                                                          │
│ Step 2: 维护授权数据 (Authorization页签)                  │
│   → 系统自动从菜单推导授权对象 (SU24式, 等价menu_bo_linker)│
│   → 维护组织级别 ($BUKRS, $WERKS, $EKORG)               │
│   → 维护活动类型 (ACTVT=01创建/02更改/03显示)            │
│                                                          │
│ Step 3: 生成权限参数文件 (Profile)                        │
│   → 配置时物化 → Layer 1 事实                            │
│                                                          │
│ 派生角色 (Derived Role):                                 │
│   → 父角色: $BUKRS=变量 (模板)                           │
│   → 子角色: $BUKRS=1000,1100 (填充具体值)                │
│   → PFUD批量派生 → 所有子角色同步更新                    │
│                                                          │
│ 复合角色 (Composite Role):                               │
│   → 多个单一角色的并集 (= 我们的多角色并集)               │
└─────────────────────────────────────────────────────────┘
```

**Layer 2 关键机制**:
- **菜单→授权对象自动推导** (SU24): 最接近我们的 `menu_bo_linker`，添加事务码后系统自动带出关联的授权对象和字段
- **组织级别模板变量** ($BUKRS): 最接近我们的"维度范围配置"，父角色配模板、子角色填具体值
- **Trace导入**: 基于用户实际使用记录自动生成菜单，我们暂无对应
- **派生角色同步**: 父角色变更→批量同步子角色，对应我们的"层级变更→重新推导"

#### 6.2.2 Salesforce 配置模型

```
Salesforce 配置流程 (Layer 2):
┌─────────────────────────────────────────────────────────┐
│ Step 1: Profile (基线配置)                               │
│   → 对象权限: Read/Create/Edit/Delete/ViewAll/ModifyAll │
│   → 字段权限: 可见/只读/编辑 (逐字段)                    │
│   → 记录类型: 可见/可创建的记录类型                       │
│   → 登录限制: IP范围/登录时段                            │
│                                                          │
│ Step 2: Permission Set (增量配置)                        │
│   → 独立于Profile的额外权限 (只增不减)                   │
│   → Permission Set Group (权限集组 = 模板)               │
│                                                          │
│ Step 3: OWD (组织范围默认值 = 基线共享)                  │
│   → Private / Public Read / Public Read-Write            │
│                                                          │
│ Step 4: Role Hierarchy (向上继承)                        │
│   → 上级自动见下级数据 (Grant Access Via Hierarchies)    │
│                                                          │
│ Step 5: Sharing Rules (横向扩展)                         │
│   → Ownership-based: 按所有者共享                        │
│   → Criteria-based: 按条件共享 (字段+操作符+值)          │
│   → → 最接近我们的条件规则!                              │
│                                                          │
│ Step 6: Territory Management (多维度, 可选)              │
│   → 按区域/产品线/技能多维度分配                         │
└─────────────────────────────────────────────────────────┘
```

**Layer 2 关键机制**:
- **Profile+Permission Set 分层**: Profile是基线(必选1个), Permission Set是增量(可选多个), 对应我们的"模板+手动追加"
- **OWD基线**: 设定最严格的默认共享级别，所有扩展只能放宽不能收紧，对应我们的"默认拒绝→逐步授权"
- **Criteria-based Sharing Rules**: `{field, op, value}` 条件共享，与我们的条件规则设计完全一致
- **Permission Set Group**: 权限集的分组模板，对应我们的"模板组"
- **Territory Management**: 多维度控制，对应我们的"维度范围"但更成熟（支持按区域/产品/技能三维）

#### 6.2.3 Oracle VPD 配置模型

```
Oracle VPD 配置流程 (Layer 2):
┌─────────────────────────────────────────────────────────┐
│ ⚠ 无UI配置界面! 全部通过PL/SQL代码完成                    │
│                                                          │
│ Step 1: 创建Policy Function (PL/SQL)                    │
│   → 输入: schema_var, table_var                          │
│   → 输出: VARCHAR2 (WHERE谓词)                           │
│   → 可引用 Application Context (会话属性)                │
│                                                          │
│ Step 2: 注册Policy (DBMS_RLS.ADD_POLICY)                │
│   → object_schema + object_name (保护的表)               │
│   → policy_function (谓词函数)                           │
│   → statement_types (SELECT/INSERT/UPDATE/DELETE)        │
│   → policy_group (策略组 = 分组)                         │
│   → sec_relevant_cols (列级VPD = 列条件)                │
│                                                          │
│ Step 3: Application Context (运行时变量)                 │
│   → 会话级: SYS_CONTEXT('USERENV','SESSION_USER')        │
│   → 全局级: Global Application Context (跨连接池)        │
│                                                          │
│ Step 4: Policy Group (策略组)                            │
│   → DBMS_RLS.CREATE_POLICY_GROUP                        │
│   → DBMS_RLS.ADD_GROUPED_POLICY                         │
│   → 多个策略组可叠加应用                                 │
└─────────────────────────────────────────────────────────┘
```

**Layer 2 关键机制**:
- **Policy Function = 自由代码**: 最大的灵活性和最大的风险（不可审计、不可UI配置、性能不可预测）
- **Application Context = ${user.id}**: 对应我们的运行时变量，VPD原生支持
- **Policy Group**: 策略分组，多个策略叠加到同一表，对应我们的"多配置源合并"
- **Column-level VPD**: 仅当特定列被访问时才应用策略，我们没有对应（未来可扩展）
- **Static vs Dynamic Policy**: Static策略只评估一次缓存结果, Dynamic每次重新评估，对应我们的 `derivation_mode`

#### 6.2.4 AWS IAM 配置模型

```
AWS IAM 配置流程 (Layer 2):
┌─────────────────────────────────────────────────────────┐
│ Step 1: 定义Policy Document (JSON)                      │
│   → Statement[]: {Effect, Action, Resource, Condition}  │
│                                                          │
│ Step 2: 选择Policy类型                                   │
│   → AWS Managed Policy: AWS预定义模板                    │
│   → Customer Managed Policy: 自定义 (推荐)               │
│   → Inline Policy: 嵌入到角色/用户 (不推荐)              │
│                                                          │
│ Step 3: 绑定到身份                                       │
│   → IAM Role / IAM User / IAM Group                     │
│                                                          │
│ Step 4: 组织级管控 (可选)                                │
│   → SCP (Service Control Policy): OU层级护栏             │
│   → Permission Boundary: 权限上界                        │
│                                                          │
│ Step 5: 验证与审计                                       │
│   → IAM Access Analyzer: 检测过度权限                   │
│   → CloudTrail: 审计日志                                 │
└─────────────────────────────────────────────────────────┘
```

**Layer 2 关键机制**:
- **Managed Policy = 模板**: AWS预定义+自定义托管策略，可复用、可版本化，对应我们的"模板组"
- **SCP = 组织护栏**: 挂在OU上向下继承取交集，对应我们的"维度范围+向下继承"
- **Permission Boundary = 权限上界**: 限制角色最大权限范围，我们没有直接对应（可用exclude实现类似效果）
- **Access Analyzer = 冲突检测**: 自动检测过度权限，对应我们的"冲突检测"
- **Effect: Deny = 显式否决**: 与我们的 `data_scope.exclude` 完全一致

#### 6.2.5 Layer 2 配置机制综合对比

| Layer 2 机制 | SAP PFCG | Salesforce | Oracle VPD | AWS IAM | **本方案** |
|-------------|----------|------------|------------|---------|-----------|
| **菜单→权限推导** | ✅ SU24自动推导 | ✅ App Launcher→Tabs | ❌ 手写代码 | ❌ | ✅ menu_bo_linker |
| **维度/组织级别** | ✅ $BUKRS模板变量 | ✅ Territory Mgmt | ❌ | ✅ SCP+OU | ✅ 维度范围+CHILDREN_OF |
| **条件规则** | ❌ (仅字段值域) | ✅ Criteria-based Sharing | ✅ Policy Function | ✅ Condition | ✅ {field,op,value} |
| **模板** | ✅ 父角色(派生) | ✅ Profile+PermSetGroup | ❌ | ✅ Managed Policy | ✅ 模板组 |
| **分组** | ✅ 复合角色 | ✅ Permission Set Group | ✅ Policy Group | ✅ Policy Document | ✅ 权限级别组+菜单组 |
| **Deny/Exclude** | ❌ (空ACTVT≈禁止) | ❌ | ❌ | ✅ Effect:Deny | ✅ data_scope.exclude |
| **基线默认** | 无(默认全部拒绝) | ✅ OWD(基线共享) | 无(需显式定义) | 无(默认拒绝) | ✅ 默认拒绝→逐步授权 |
| **冲突检测** | ⚠ SU53手动 | ⚠ 仅运行时 | ❌ | ✅ Access Analyzer | ✅ 冲突检测(设计) |
| **UI配置** | ✅ PFCG全流程 | ✅ Setup全流程 | ❌ PL/SQL | ✅ Console/CLI | ✅ 双模式 |
| **Trace/审计** | ✅ ST01导入 | ✅ Login History | ❌ | ✅ CloudTrail | 🔄 未来扩展 |
| **配置时推导** | ✅ 派生角色PFUD | ✅ Sharing Table物化 | ❌ | ✅ Policy评估 | ✅ 推导管道 |
| **向下继承** | ✅ S_STRUCT INHER=X | ❌ | ✅ CONNECT BY | ✅ SCP向下 | ✅ CHILDREN_OF |
| **向上继承** | ❌ | ✅ Role Hierarchy | ✅ CONNECT BY PRIOR | ❌ | 多角色并集 |

#### 6.2.6 关键发现

1. **所有产品都有"菜单→权限推导"**：SAP SU24、Salesforce App→Tabs，Oracle除外（无UI）。这验证了我们的 `menu_bo_linker` 推导管道是必要的。

2. **SAP的$BUKRS = 我们的维度范围模板**：SAP的组织级别模板变量机制与我们的维度范围+派生角色推导本质相同——父角色配模板、子角色填具体值、批量派生。

3. **Salesforce的Criteria-based Sharing = 我们的条件规则**：Salesforce用 `{field, op, value}` 条件扩展共享，与我们的条件规则设计完全一致。这再次验证了条件统一为 `field op value` 的正确性。

4. **AWS的Managed Policy = 我们的模板组**：AWS托管策略可复用、可版本化，我们的模板组设计对齐。

5. **Oracle是唯一无Layer 2配置UI的产品**：所有配置通过PL/SQL代码完成。这是我们要避免的——Layer 3交互层必须提供可视化配置。

6. **我们的独有优势**：
   - **维度层级展开**：SAP/Salesforce/AWS/Oracle都没有，需手动配每个字段值
   - **笛卡尔积语义**：所有产品未显式处理父子维度冲突
   - **三层分离**：所有产品配置与事实混杂，只有我们显式分离
   - **CHILDREN_OF默认+冻结可选**：SAP双轨但需手动选，我们默认动态+可选冻结更符合向下推导的不对称性

### 6.4 本方案的定位

```
本方案 = SAP的结构化 + AWS的Deny + Salesforce的条件 + 三层分离

独有优势:
  1. 维度层级展开 (头部产品都没有, 需手动配每个字段值)
  2. 显式 Deny 一票否决 (仅 AWS 有)
  3. 笛卡尔积语义 (AC-008, 头部产品未显式处理)
  4. 三层分离 (头部产品未显式分离, 导致配置与事实混杂)
```

---

## 7. 功能需求

### FR-001: role_effective_intents 表创建

- **描述**: 创建 Layer 1 权限事实表，作为权限检查的单一事实来源
- **验收标准**:
  - [AC-001.1] 表结构包含 role_id, bo_id, action_name, data_scope (JSON), derivation_mode, source
  - [AC-001.2] data_scope 为 `{include:[...], exclude:[...]}` 结构，空 include = 全部数据
  - [AC-001.3] data_scope.exclude 表达否决范围 (原 is_denied 功能)
  - [AC-001.4] derivation_mode 为 'dynamic' (CHILDREN_OF) 或 'static' (IN,冻结), 默认值由 FIELD_METADATA.default_derivation_mode 决定
  - [AC-001.5] UNIQUE 约束防止重复 Intent
- **优先级**: Must
- **实现**: 新建 migration 脚本

### FR-002: EffectiveIntentChecker 求值引擎

- **描述**: 实现基于 role_effective_intents 的统一求值引擎 (include/exclude 模型)
- **验收标准**:
  - [AC-002.1] 优先级: Owner (不受 exclude 限制) > Exclude (一票否决) > Include (允许) > 默认拒绝
  - [AC-002.2] Owner 条件通过字段元数据 is_owner 标记识别
  - [AC-002.3] include 和 exclude 统一用 {field, op, value} 求值
  - [AC-002.4] 运行时变量 ${user.id} 正确解析
  - [AC-002.5] SQL 语义: WHERE include_conditions AND NOT exclude_conditions
- **优先级**: Must
- **实现**: `meta/core/effective_intent_checker.py`

### FR-003: 推导管道实现

- **描述**: 实现 Layer 2 配置源到 Layer 1 事实的统一推导管道
- **验收标准**:
  - [AC-003.1] 3 个配置源 (permission_rules + role_menus + manual) 均能正确推导为 Intents
  - [AC-003.2] 维度展开 + 笛卡尔积语义保留 (AC-008 回归通过)
  - [AC-003.3] 权限级别展开为多个 action Intents (LEVEL_BUNDLES)
  - [AC-003.4] 菜单→BO actions 推导 (menu_bo_linker 集成)
  - [AC-003.5] 条件规则→data_scope.include 转换
  - [AC-003.6] Owner 规则→data_scope.include 的 owner_id 条件转换
  - [AC-003.7] Deny 规则→data_scope.exclude 转换 (原 is_denied)
  - [AC-003.8] action condition ({field:"action",op:"IN",value:[...]}) 展开为多条 Intent
  - [AC-003.9] 向下推导默认生成 CHILDREN_OF 条件 (derivation_mode=dynamic)
  - [AC-003.10] 向上推导默认生成静态 IN 条件 (derivation_mode=static)
  - [AC-003.11] derivation_mode 字段正确写入 role_effective_intents
- **优先级**: Must
- **实现**: `meta/services/intent_derivation_pipeline.py`

### FR-004: 字段元数据注册表

- **描述**: 建立 BO 字段元数据注册表，驱动推导和 UI 渲染
- **验收标准**:
  - [AC-004.1] 维度字段标记 is_dimension, 配置 dimension_chain
  - [AC-004.2] Owner 字段标记 is_owner, 配置 runtime_variable
  - [AC-004.3] 普通字段配置 value_type, allowed_operators
  - [AC-004.4] 级联过滤配置 (sub_domain_id 级联自 domain_id)
- **优先级**: Must
- **实现**: `meta/core/field_metadata_registry.py`

### FR-005: SQL 谓词生成器

- **描述**: 实现 data_scope → SQL WHERE 的统一转换
- **验收标准**:
  - [AC-005.1] 支持 IN, =, !=, <, <=, >, >= 操作符
  - [AC-005.2] 运行时变量正确替换
  - [AC-005.3] 空 data_scope 生成 1=1 (all 语义)
  - [AC-005.4] 多条件 AND 连接
- **优先级**: Must
- **实现**: `meta/core/data_scope_sql_builder.py`

### FR-006: 高效配置 UI

- **描述**: 实现 Layer 3 高效配置模式（模板+维度推导+级别选择）
- **验收标准**:
  - [AC-006.1] 模板选择后一键应用
  - [AC-006.2] 维度范围配置后自动推导菜单和功能权限
  - [AC-006.3] 权限级别选择后展开为 actions
  - [AC-006.4] 条件约束可细调每个 action 的 data_scope
  - [AC-006.5] Deny 开关在每条规则旁
- **优先级**: Should
- **实现**: 升级 `PermissionConfigPanel.vue`

### FR-007: 细粒度配置 UI

- **描述**: 实现 Layer 3 高级模式（直接编辑 Intent 事实）
- **验收标准**:
  - [AC-007.1] 可直接添加/编辑/删除 Intent
  - [AC-007.2] data_scope 可逐条编辑 field/op/value
  - [AC-007.3] data_scope.exclude 可编辑 (否决范围)
  - [AC-007.4] 来源标记 (derived/manual)
- **优先级**: Should
- **实现**: 新增高级模式面板

### FR-008: 推导链可视化

- **描述**: 实现 Layer 3 推导链可视化展示
- **验收标准**:
  - [AC-008.1] 维度→菜单→actions 推导链可见
  - [AC-008.2] 点击节点可查看/修改来源
  - [AC-008.3] 来源标记 [自动]/[手动]
- **优先级**: Should
- **实现**: 新增推导链组件

### FR-009: SQL 预览与资源预估

- **描述**: 实时显示融合 SQL 和匹配资源数量
- **验收标准**:
  - [AC-009.1] 配置变更时 SQL 预览实时更新
  - [AC-009.2] 显示预估匹配资源数量和占比
  - [AC-009.3] 可查看匹配资源列表
- **优先级**: Should
- **实现**: 新增预览面板

### FR-010: 冲突检测

- **描述**: 检测配置中的潜在冲突
- **验收标准**:
  - [AC-010.1] 检测同对象不同 action 的 data_scope 范围差异
  - [AC-010.2] 检测 Deny 规则与 Allow 规则的冲突
  - [AC-010.3] 提供确认/调整交互
- **优先级**: Could
- **实现**: 新增冲突检测服务

### FR-011: 菜单反向推导 (BO action → 父菜单建议)

- **描述**: 手动添加 BO action 权限时，反向提示需要添加的父菜单 (SAP SU24 双向映射)
- **验收标准**:
  - [AC-011.1] 手动添加 product:update → 提示"建议添加: 采购管理菜单"
  - [AC-011.2] 反向建议可忽略 (非强制)
  - [AC-011.3] 推导管道 Step 4b 实现反向推导
- **优先级**: Should
- **实现**: `menu_bo_linker.reverse_suggest_menus()`

### FR-012: 对象基线共享 (OWD)

- **描述**: 每个业务对象的基线共享级别 (Salesforce OWD 等价物), 所有扩展只能放宽
- **验收标准**:
  - [AC-012.1] object_owd 表: bo_id, baseline_level (none/read/write)
  - [AC-012.2] 推导管道 Step 0: 从 OWD 基线开始, 逐步授权
  - [AC-012.3] Intent 的 action 级别不能低于 OWD 基线 (验证约束)
- **优先级**: Could
- **实现**: 新增 `object_owd` 配置表 + 推导管道 Step 0

### FR-013: 配置源优先级

- **描述**: 3 个配置源定义明确优先级, 解决冲突
- **验收标准**:
  - [AC-013.1] 优先级: manual > template > derived (模板展开后视同manual)
  - [AC-013.2] 同一 Intent 被多源推导时, 高优先级源覆盖
  - [AC-013.3] 冲突时 UI 显示警告 (哪些源冲突, 最终取哪个)
- **优先级**: Should
- **实现**: 推导管道增加 source_precedence 处理

### FR-014: 重推导触发机制

- **描述**: 维度层级变更时触发静态 Intent 重推导 (SAP PFUD 等价物)
- **验收标准**:
  - [AC-014.1] 维度值增/删/改时, 标记受影响的 Intent 为 stale
  - [AC-014.2] 管理员可手动触发重推导 (批量)
  - [AC-014.3] 可选: 定时任务自动重推导 (如每天凌晨)
  - [AC-014.4] 重推导前后可对比差异
- **优先级**: Should
- **实现**: 新增 `stale` 标记 + 重推导 API

### FR-015: derivation_mode 默认策略按维度类型区分

- **描述**: CHILDREN_OF 不应全场景默认, 应按维度类型决定 (SAP: FI/MM用静态, HR用动态)
- **验收标准**:
  - [AC-015.1] FIELD_METADATA 增加 default_derivation_mode 字段
  - [AC-015.2] 稳定维度 (product/domain): 默认 static (IN)
  - [AC-015.3] 动态维度 (organization/territory): 默认 dynamic (CHILDREN_OF)
  - [AC-015.4] 管理员可逐 Intent 覆盖默认 derivation_mode
- **优先级**: Must
- **实现**: FIELD_METADATA 扩展 + 推导管道 Step 2

### FR-016: 访问模拟

- **描述**: 输入用户+action+记录, 返回允许/拒绝+原因 (AWS IAM Policy Simulator 等价物)
- **验收标准**:
  - [AC-016.1] API: `/api/v1/permission/simulate` 输入 {user_id, bo_id, action, record_id}
  - [AC-016.2] 返回 {decision: allow/deny, reason: "Owner匹配"/"exclude命中", matched_intents: [...]}
  - [AC-016.3] UI: 配置页面可模拟"用户X能否操作记录Y"
- **优先级**: Could
- **实现**: 新增模拟端点 + UI模拟面板

### FR-017: 完整性指示 (SAP 红黄绿灯)

- **描述**: 每个对象的权限配置显示完整性状态 (SAP PFCG 红黄绿灯等价物)
- **验收标准**:
  - [AC-017.1] 🔴 红灯: 对象无任何规则 (未配置)
  - [AC-017.2] 🟡 黄灯: 对象有规则但 data_scope 不完整 (如仅有维度无条件)
  - [AC-017.3] 🟢 绿灯: 对象配置完整, 已推导为 Intents
  - [AC-017.4] 角色级别汇总: X红 Y黄 Z绿, 一目了然
- **优先级**: Should
- **实现**: 推导管道增加完整性校验 + UI信号灯

### FR-018: 角色对比 (SAP ROLE_CMP / Salesforce View Summary)

- **描述**: 并排对比两个角色的权限差异, 或查看用户的有效权限汇总
- **验收标准**:
  - [AC-018.1] 角色A vs 角色B: 高亮差异 Intent (新增/删除/修改)
  - [AC-018.2] 用户有效权限: 合并所有角色后的 Intent 汇总
  - [AC-018.3] 差异可导出 (CSV/Excel)
- **优先级**: Should
- **实现**: 新增对比面板 + `/api/v1/permission/diff`

### FR-019: 配置模式无缝切换 (AWS Visual↔JSON)

- **描述**: 高效模式↔细粒度模式 在同一页面内无缝切换 (AWS IAM Visual Editor↔JSON Editor 等价物)
- **验收标准**:
  - [AC-019.1] 高效模式修改后切换到细粒度, 已修改内容保持
  - [AC-019.2] 细粒度修改后切回高效, 高效模式反映最新状态
  - [AC-019.3] 切换时不丢失未保存修改 (提示保存)
- **优先级**: Must
- **实现**: 单一页面内双模式 Tab 切换

### FR-020: 批量用户分配

- **描述**: 角色配置完成后, 批量分配给多个用户 (SAP SU10 / Salesforce Manage Assignments 等价物)
- **验收标准**:
  - [AC-020.1] 角色详情页可查看已分配用户列表
  - [AC-020.2] 批量添加/移除用户 (支持搜索+多选)
  - [AC-020.3] 用户详情页可查看已分配角色列表
- **优先级**: Should
- **实现**: 新增角色-用户关联管理面板

### FR-021: 角色互斥约束 (Salesforce Mutual Exclusion)

- **描述**: 标记某些角色互斥, 防止同一用户同时拥有冲突角色
- **验收标准**:
  - [AC-021.1] 角色互斥对配置: 角色A ⊗ 角色B
  - [AC-021.2] 分配时检测: 用户已有角色A, 分配角色B时提示互斥
  - [AC-021.3] 可覆盖: 管理员确认后可强制分配
- **优先级**: Could
- **实现**: 新增 `role_mutual_exclusion` 表 + 分配时校验

### FR-022: 配置变更版本化 (AWS Policy Versioning)

- **描述**: permission_rules 变更保留历史版本, 支持回滚
- **验收标准**:
  - [AC-022.1] 每次保存生成新版本 (保留最近 N 版)
  - [AC-022.2] 可查看历史版本与当前版本的差异
  - [AC-022.3] 可回滚到历史版本
- **优先级**: Could
- **实现**: 新增 `permission_rules_history` 表

---

### 7.1 Layer 2 深度审查发现

基于 §6.2 头部产品 Layer 2 配置模型对比, 发现以下 6 个不合理/缺失点:

| # | 问题 | 影响产品 | 对应FR | 优先级 |
|---|------|---------|--------|--------|
| **1** | 菜单推导只有单向 (menu→BO), 缺少 BO→menu 反向建议 | SAP SU24双向 | FR-011 | Should |
| **2** | 缺少对象基线共享 (OWD), 多角色合并时起点不明 | Salesforce OWD | FR-012 | Could |
| **3** | 6个配置源无优先级, 冲突不可预测 | SAP/ Salesforce/ AWS都有明确分层 | FR-013 | Should |
| **4** | 静态Intent无重推导触发机制, 过期风险 | SAP PFUD | FR-014 | Should |
| **5** | CHILDREN_OF全场景默认过于激进, 稳定维度应用静态IN | SAP FI/MM用派生角色 | FR-015 | **Must** |
| **6** | 缺少访问模拟 (用户+action+记录→允许/拒绝+原因) | AWS IAM Simulator / SAP SU53 | FR-016 | Could |

**最关键的修正 (FR-015)**: `derivation_mode` 默认值不应全局 `dynamic`, 而应根据维度类型决定:
```python
FIELD_METADATA = {
    "domain_id": {
        "is_dimension": True,
        "default_derivation_mode": "static",   # ← 稳定维度, 默认IN
    },
    "organization_id": {                       # (未来)
        "is_dimension": True,
        "default_derivation_mode": "dynamic",  # ← 动态维度, 默认CHILDREN_OF
    },
}
```

### 7.2 Layer 3 交互层深度审查发现

基于头部产品 Layer 3 交互模型对比, 发现以下 7 个不合理/缺失点:

| # | 问题 | 影响产品 | 对应FR | 优先级 |
|---|------|---------|--------|--------|
| **1** | 无完整性指示 (红黄绿灯), 管理员不知道哪些对象未配置 | SAP PFCG信号灯 | FR-017 | Should |
| **2** | 无角色对比能力, 无法看两个角色差异或用户有效权限 | SAP ROLE_CMP / Salesforce View Summary | FR-018 | Should |
| **3** | 高效/细粒度双模式是独立面板, 非无缝切换 | AWS IAM Visual↔JSON | FR-019 | **Must** |
| **4** | 无批量用户分配, 只能逐用户配角色 | SAP SU10 / Salesforce Manage Assignments | FR-020 | Should |
| **5** | 无角色互斥约束, 可能分配冲突角色 | Salesforce Mutual Exclusion | FR-021 | Could |
| **6** | 无配置版本化, 无法回滚错误配置 | AWS Policy Versioning / SAP Transport | FR-022 | Could |
| **7** | 6配置源→3源已修正 (见§4.4) | — | §7.1 #3 | Done |

**头部产品 Layer 3 交互对比**:

| 交互特性 | SAP PFCG | Salesforce | AWS IAM | **本方案** |
|---------|----------|------------|---------|-----------|
| **配置模式** | Tab式(Menu→Auth→User→Profile) | Tab式(Objects→Fields→System) | **双编辑器(Visual↔JSON)** | **双模式(高效↔细粒度)** |
| **完整性指示** | ✅ 红黄绿灯 | ❌ | ✅ Policy Validation | ✅ FR-017 (新增) |
| **对比/差异** | ✅ ROLE_CMP | ✅ View Summary | ✅ Access Analyzer | ✅ FR-018 (新增) |
| **模拟/调试** | ✅ SU53 | ❌ | ✅ Policy Simulator | ✅ FR-016 |
| **批量分配** | ✅ SU10 | ✅ Manage Assignments | ✅ CLI/Console | ✅ FR-020 (新增) |
| **互斥约束** | ❌ | ✅ Mutual Exclusion | ❌ | ✅ FR-021 (新增) |
| **版本化/回滚** | ✅ Transport | ❌ | ✅ 5版本+回滚 | ✅ FR-022 (新增) |
| **模板/复制** | ✅ 派生角色模板 | ✅ PermSet Group | ✅ Import Managed Policy | ✅ 模板组 |
| **自动推导展示** | ✅ SU24菜单→授权 | ✅ 依赖自动启用 | ✅ — | ✅ 推导链可视化 |

**最关键的修正 (FR-019)**: 高效模式和细粒度模式必须在**同一页面内**用Tab切换,
而非独立面板。AWS IAM 的 Visual↔JSON 无缝切换是标杆——修改在两种视图间保持, 切换无丢失。

---

## 8. 实施计划

### Phase 1: Layer 1 基础设施 (核心)

- [ ] 创建 `role_effective_intents` 表
- [ ] 实现 `EffectiveIntentChecker` 求值引擎
- [ ] 实现 `data_scope_sql_builder` SQL 生成
- [ ] 字段元数据注册表初始化
- [ ] 现有 AC-008 测试回归

### Phase 2: Layer 2 推导管道

- [ ] 实现 `intent_derivation_pipeline`
- [ ] 集成 DimensionScopeEngine (维度展开+笛卡尔积)
- [ ] 集成 menu_bo_linker (菜单→BO actions)
- [ ] 实现权限级别→actions 展开
- [ ] 实现条件规则→field_conditions 转换
- [ ] 6 个配置源集成测试

### Phase 3: Layer 3 交互优化

- [ ] 高效配置模式 UI
- [ ] 细粒度配置模式 UI (高级)
- [ ] 推导链可视化
- [ ] SQL 预览与资源预估
- [ ] 冲突检测
- [ ] 差异对比

### Phase 4: 迁移与兼容

- [ ] 现有 `role_intents` 数据迁移到 `role_effective_intents`
- [ ] `IntentPermissionChecker` 切换到 `EffectiveIntentChecker`
- [ ] Feature flag 控制切换
- [ ] 回归测试

---

## 9. 验收标准 (端到端)

### AC-E2E-001: 维度+条件融合

```
配置:
  维度: domain=all, sub_domain=[101]
  条件: risk_level <= 3
  级别: write

预期 role_effective_intents:
  product:read    data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101), risk_level<=3]}
  product:list    data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101)]}
  product:create  data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101)]}
  product:update  data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101)]}
  product:import  data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101)]}
  product:export  data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101)]}

验证:
  1. sub_domain_id IN (101) 笛卡尔积生效 (非全 4 个)
  2. risk_level<=3 仅在 read 的 include (条件规则级别绑定)
  3. 6 个 actions 独立 (write 级别展开)
```

### AC-E2E-002: Exclude 一票否决 (原 Deny)

```
配置:
  product:read    data_scope={include:{domain_id IN (1,2,3)}}
  product:export  data_scope={include:{}, exclude:{status='archived'}}

验证:
  查询 status='archived' 的产品 export → 拒绝 (exclude 一票否决)
  查询 status='active' 的产品 export → 允许 (include all, exclude 不匹配)
  查询 status='active' 的产品 read   → 允许 (include 匹配)
```

### AC-E2E-003: Owner 优先级 (不受 exclude 限制)

```
配置:
  product:manage  data_scope={include:{owner_id=${user.id}}}
  product:delete  data_scope={include:{}, exclude:{status='archived'}}

验证:
  用户删除自己创建的 status='archived' 产品 → 允许 (Owner 优先, 不受 exclude 限制)
  用户删除他人创建的 status='archived' 产品 → 拒绝 (exclude 生效)
```

### AC-E2E-004: 条件统一验证

```
配置:
  维度: domain_id IN (1,2,3)
  Owner: owner_id = ${user.id}
  条件: risk_level <= 3
  否决: status = 'archived'

验证 role_effective_intents 中 data_scope:
  {
    include: [
      {field: "domain_id",  op: "IN", value: [1,2,3]},     ← 原 dimension
      {field: "owner_id",   op: "=",  value: "${user.id}"}, ← 原 owner
      {field: "risk_level", op: "<=", value: 3}             ← 原 field
    ],
    exclude: [
      {field: "status",     op: "=",  value: "archived"}    ← 原 deny
    ]
  }

  四种类型 (dimension/owner/field/deny) 统一为 include/exclude + field op value
```

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 迁移期间双系统并存 | 中 | Feature flag 控制, 灰度切换 |
| 推导管道性能 | 中 | 增量推导 + 缓存 role_effective_intents |
| action 独立性破坏现有 LEVEL_ORDER 逻辑 | 高 | Layer 2 级别展开保持兼容, 求值引擎切换 |
| 字段元数据维护成本 | 低 | 从 business_object.yaml 自动生成 |

---

## 11. 相关文档

| 文档 | 说明 |
|------|------|
| Spec 01-07 | 权限体系元数据驱动化升级 (基础) |
| [Spec 08](./08_dimension_scope_wildcard_exclude.md) | 维度范围通配符与笛卡尔积 (AC-008) |
| `meta/core/intent_resolver.py` | 现有 Intent 模型 (FR-017) |
| `meta/core/menu_bo_linker.py` | 菜单-BO 权限自动关联 (FR-013) |
| `meta/services/dimension_scope_engine.py` | 维度范围引擎 |
| `meta/services/condition_permission_service.py` | 条件权限服务 |

---

## 12. 通用规则引擎愿景 (未来演进)

### 12.1 动机

§3.4 的条件统一（dimension/owner/field → `field op value`）不仅是权限模型的简化，
更揭示了 `{field, op, value}` 是一个**通用的条件表达式模型**，可复用于多个场景。

当前系统中条件表达式分散在多处，各自实现：

| 场景 | 当前实现 | 条件模型 |
|------|---------|---------|
| 权限规则 | `data_permission_rules.condition` | 自由表达式字符串 |
| 维度范围 | `role_dimension_scopes.dimension_values` | JSON 数组 |
| BO action 条件 | `intent_resolver._evaluate_conditions` | `{field, op, value}` |
| 安全表达式 | `SafeExpressionEvaluator` | 白名单操作符 |
| 筛选器/查询 | 前端 `el-table` filter | 各组件自定义 |

### 12.2 统一能力模块设计

```
通用规则引擎 (Rule Engine) — 未来统一能力模块
├── 条件模型: {field, op, value}
│   ├── 结构化条件: {field, op, value}
│   └── 运行时变量: ${user.id}, ${now}, ${org.id}
├── 求值引擎: evaluate(conditions, context)
│   ├── 内存求值: record vs conditions
│   └── SQL 生成: to_sql_where(conditions)
├── 字段元数据: field_metadata_registry
│   ├── is_dimension: 触发层级展开
│   ├── is_owner: 触发优先级
│   ├── value_type: integer/enum/string/date
│   └── allowed_operators: [=, !=, IN, <, <=, >, >=]
├── UI 编辑器: ConditionEditor.vue (通用条件编辑组件)
│   ├── 字段选择 (基于元数据)
│   ├── 操作符选择 (基于 allowed_operators)
│   ├── 值输入 (基于 value_type)
│   └── 级联过滤 (基于 cascade_filter)
└── 应用场景:
    ├── 权限规则 (当前 — Spec 09)
    ├── 数据验证 (未来 — 表单校验/业务约束)
    ├── 工作流条件 (未来 — 流程分支)
    ├── 业务规则 (未来 — 定价/折扣/审批)
    └── 筛选器 (未来 — 列表查询/报表)
```

### 12.3 演进路径

| Phase | 内容 | 价值 |
|-------|------|------|
| **当前** | 权限模型统一为 `field op value` (Spec 09) | 权限层条件统一 |
| **Phase 1** | 抽象 `ConditionEngine` 通用模块 | 求值引擎复用 |
| **Phase 2** | 抽象 `ConditionEditor.vue` 通用组件 | UI 编辑器复用 |
| **Phase 3** | 字段元数据注册表统一 | 所有场景共享元数据 |
| **Phase 4** | 数据验证/工作流/筛选器接入 | 全场景统一 |

### 12.4 与权限架构的关系

通用规则引擎是权限架构的**自然延伸**，不是替代：

```
权限架构 (Spec 09)          通用规则引擎 (未来)
─────────────              ──────────────
data_scope.include    →    ConditionEngine.evaluate()
data_scope.exclude    →    ConditionEngine.evaluate()
field_metadata        →    field_metadata_registry (共享)
SQL 谓词生成           →    ConditionEngine.to_sql_where()
UI 条件编辑            →    ConditionEditor.vue (共享)
```

权限架构是通用规则引擎的**第一个应用场景和验证基础**。

---

## 附录 A: 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-07-23 | 笛卡尔积 (PM Option B) | 父维度 all 不覆盖子维度显式值 |
| 2026-07-24 | Model B (权限级别与范围同条目) | 所有头部产品的共识 |
| 2026-07-24 | 条件统一为 field op value | SQL 本质相同, 头部产品不区分 |
| 2026-07-24 | 三层分离架构 | 配置与事实分离, 关注点清晰 |
| 2026-07-24 | action 独立无隐含包含 | 与 SAP ACTVT 一致, 包含关系放 Layer 2 |
| 2026-07-24 | Deny 改为 data_scope.exclude | 与 Spec 08 维度 exclude 语义统一, 消除独立字段 |
| 2026-07-24 | Layer 2 支持 action condition | 一条规则覆盖多 action, 推导管道展开 |
| 2026-07-24 | 通用规则引擎愿景 | field op value 可复用于验证/工作流/筛选等场景 |
| 2026-07-24 | 结构继承归 Layer 1 (CHILDREN_OF) | 层级继承是事实属性, 运行时求值, 永不过期 |
| 2026-07-24 | 向上追溯 ANCESTORS_OF | Oracle CONNECT BY PRIOR 双向验证, 汇总报表/跨级关联是真实需求 |
| 2026-07-24 | 向下默认CHILDREN_OF(子节点动态), 向上默认静态IN(父节点稳定) | 向下向上不对称性: 开放集vs闭集; 修正了之前"配置时推导为默认"的决策 |
| 2026-07-24 | derivation_mode默认值按维度类型区分 (FR-015) | SAP FI/MM用派生角色(静态), HR用S_STRUCT(动态); 全场景CHILDREN_OF过于激进, 稳定维度默认static |
| 2026-07-24 | 6配置源→3配置源+2辅助 (§7.2) | 维度范围+条件规则+权限级别三合一→permission_rules; 模板是宏非源; 与头部产品(1~2源)对齐 |
| 2026-07-24 | Layer 3增加FR-017~022 (§7.3) | 完整性指示/角色对比/无缝切换/批量分配/互斥/版本化; 最关键: 高效↔细粒度必须同页Tab切换 |
| 2026-07-24 | 语义继承归 Layer 2 (推导管道) | 菜单→actions, 级别→展开 是配置策略, 可调整 |
| 2026-07-24 | 并集由多角色覆盖 | 角色内交集, 跨角色并集 |
