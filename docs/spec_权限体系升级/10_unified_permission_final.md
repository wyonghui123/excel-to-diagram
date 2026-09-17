# Spec 10: 统一权限架构 — 最终方案

> 日期：2026-07-24 | 版本：v1.0 | 状态：最终方案，待评审
> 前置：Spec 01-08 (权限体系元数据驱动化升级 + 维度范围笛卡尔积)
> 来源：基于 Spec 09 研究成果提炼，去除决策过程，保留最终结论

---

## 1. 架构总览

### 1.1 三层分离模型

```
┌──────────────────────────────────────────────────────┐
│ Layer 3: 交互层 (Interaction)                         │
│   高效模式: 模板 + 维度推导 + 级别选择 + 条件细调      │
│   细粒度模式: 直接编辑 Intent 事实 (同页Tab无缝切换)   │
│   辅助: 推导链可视化 + SQL预览 + 冲突检测 + 完整性指示  │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────────────────────────────────────┐
│ Layer 2: 配置层 (Configuration)                       │
│   统一规则表 (permission_rules): 维度+条件+级别 三合一  │
│   菜单授权 (role_menus): 入口权限 → BO actions 推导    │
│   推导管道: 8步 → role_effective_intents               │
│   辅助: LEVEL_BUNDLES(展开模板) + permission_templates │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────────────────────────────────────┐
│ Layer 1: 事实层 (Fact / Single Source of Truth)       │
│   role_effective_intents: 权限检查唯一依据             │
│   Intent = (role_id, bo_id, action_name, data_scope)  │
│   data_scope: {include:[...], exclude:[...]}          │
│   action 独立, 无隐含包含                              │
│   条件统一: dimension/owner/field → field op value     │
└──────────────────────────────────────────────────────┘
```

### 1.2 层间职责

| 层 | 职责 | 不做什么 |
|----|------|---------|
| Layer 1 | 描述"权限是什么" — 原子事实 | 不关心"怎么来的" |
| Layer 2 | 描述"怎么高效生成事实" — 推导策略 | 不直接被求值引擎使用 |
| Layer 3 | 描述"怎么让用户易用" — 交互体验 | 不包含权限逻辑 |

### 1.3 与当前系统映射

| 当前概念 | 新归属 | 变化 |
|---------|--------|------|
| `role_intents` | Layer 1 | 升级为 `role_effective_intents`，增加 data_scope JSON |
| `role_dimension_scopes` | Layer 2 | 合并到 `permission_rules.include_conditions` |
| `data_permission_rules` | Layer 2 | 合并到 `permission_rules.include_conditions` |
| `role_permission_levels` | Layer 2 | 降为 `permission_rules.permission_level` 字段 |
| `role_menus` | Layer 2 | 保留，菜单授权输入 |
| `IntentPermissionChecker` | Layer 1 | 升级为 `EffectiveIntentChecker` |
| `menu_bo_linker` | Layer 2 | 保留，增加反向推导 (FR-011) |
| `DimensionScopeEngine` | Layer 2 | 保留，维度展开+笛卡尔积 |

---

## 2. Layer 1: 事实层

### 2.1 设计原则

1. **单一事实来源**: `role_effective_intents` 是权限检查的唯一依据
2. **action 独立**: read/create/update/delete 各自独立，无隐含包含（对齐 SAP ACTVT）
3. **条件统一**: 所有数据范围条件统一为 `{field, op, value}` 结构（对齐 Salesforce Criteria）
4. **Deny 即 exclude**: 否决通过 `data_scope.exclude` 表达（对齐 AWS Effect:Deny）

### 2.2 数据模型

```sql
CREATE TABLE role_effective_intents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id         INTEGER NOT NULL,
    bo_id           TEXT NOT NULL,           -- 业务对象 (product/version/...)
    action_name     TEXT NOT NULL,           -- 独立明细 (read/create/update/delete/list/...)
    data_scope      TEXT,                    -- JSON: {include:[...], exclude:[...]}
    derivation_mode TEXT DEFAULT 'dynamic',  -- dynamic(CHILDREN_OF) | static(IN,冻结)
    source          TEXT DEFAULT 'derived',  -- derived / manual / template
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(role_id, bo_id, action_name, data_scope_hash)
);
```

**data_scope JSON 结构**:

```json
{
  "include": [
    {"field": "domain_id",     "op": "IN",  "value": [1,2,3]},
    {"field": "sub_domain_id", "op": "CHILDREN_OF", "value": {"parent_field": "domain_id"}},
    {"field": "risk_level",    "op": "<=",  "value": 3},
    {"field": "owner_id",      "op": "=",   "value": "${user.id}"}
  ],
  "exclude": [
    {"field": "status",        "op": "=",   "value": "archived"}
  ]
}
```

**语义矩阵**:

| include | exclude | SQL | 含义 |
|---------|---------|-----|------|
| `[]` | `[]` | `WHERE 1=1` | 全部允许，无否决 |
| `[{conditions}]` | `[]` | `WHERE conditions` | 允许匹配条件的 |
| `[]` | `[{conditions}]` | `WHERE NOT (conditions)` | 全部允许但排除匹配的 |
| `[{inc}]` | `[{exc}]` | `WHERE inc AND NOT (exc)` | 允许inc但排除exc |

### 2.3 条件操作符

| 类别 | 操作符 | 方向 | SQL | 示例 |
|------|--------|------|-----|------|
| 等值/比较 | `=`, `!=`, `<`, `<=`, `>`, `>=` | — | `field op ?` | `risk_level <= 3` |
| 集合 | `IN`, `NOT IN` | — | `field IN (?,?)` | `domain_id IN (1,2,3)` |
| 向下继承 | `CHILDREN_OF` | 父→子 | 子查询 | `sub_domain_id CHILDREN_OF domain_id` |
| 向下递归 | `DESCENDANTS_OF` | 祖先→后代 | `WITH RECURSIVE` | 全层级后代 |
| 向上追溯 | `ANCESTORS_OF` | 子→父 | 子查询 | `domain_id ANCESTORS_OF sub_domain_id` |
| 向上递归 | `ANCESTORS_ALL_OF` | 后代→根 | `WITH RECURSIVE` | 全层级回溯到根 |

**向下 vs 向上的不对称性**:

| 维度 | 向下 (parent→children) | 向上 (child→parent) |
|------|----------------------|---------------------|
| 集合性质 | 开放集 (可增长) | 闭集 (固定) |
| 新增节点影响 | 新子节点→集合扩大 | 新兄弟→父不变 |
| 静态IN是否过期 | **会过期** | **永不过期** |
| 默认存储策略 | **CHILDREN_OF** (动态) | **静态IN** |
| 可选 | 冻结为静态IN (审计) | ANCESTORS_OF (极罕见) |
| 语义 | 数据范围定义 | 上下文导航 |

**derivation_mode 按维度类型区分** (FR-015):

- 稳定维度 (product/domain): 默认 `static` → IN (SAP FI/MM 派生角色式)
- 动态维度 (organization/territory): 默认 `dynamic` → CHILDREN_OF (SAP HR S_STRUCT式)
- 管理员可逐 Intent 覆盖默认值

### 2.4 求值引擎

```python
class EffectiveIntentChecker:
    def check(self, user_id, bo_id, action_name, record_context):
        # 优先级1: Owner (字段元数据is_owner标记, 不受exclude限制)
        # 优先级2: Exclude 一票否决 (所有规则的exclude取并集)
        # 优先级3: Include 允许 (任一规则include匹配即允许)
        # 默认: 拒绝
```

**SQL 语义**: `WHERE include_conditions AND NOT exclude_conditions`

### 2.5 action 独立性

Layer 1 中每个 action 是独立 Intent，无隐含包含。包含关系在 Layer 2 的 LEVEL_BUNDLES 中定义:

```
Layer 1: product:read 和 product:delete 是两条独立Intent
Layer 2: "write级别" = {read, list, export, create, update, import} (分组模板)
         "admin级别" = write + {delete}
```

---

## 3. Layer 2: 配置层

### 3.1 设计原则

1. **3个配置源**: permission_rules (统一) + role_menus + manual_intents
2. **字段元数据驱动**: 维度展开、Owner优先级等通过元数据标记触发
3. **分组模型**: 权限级别、菜单、模板都是分组模板，展开为多个action Intent
4. **action condition 仅在 Layer 2**: 一条规则可覆盖多action；Layer 1保持action独立

### 3.2 统一规则表

维度范围 + 条件规则 + 权限级别 三合一，消除原来3表的冗余:

```sql
CREATE TABLE permission_rules (
    id INTEGER PRIMARY KEY,
    role_id INTEGER NOT NULL,
    -- 对象+权限级别 (Model B: 同条目绑定)
    resource_type       VARCHAR NOT NULL,
    permission_level    VARCHAR NOT NULL,
    -- 统一数据范围 (维度+条件统一为field op value)
    include_conditions  TEXT,    -- JSON: [{field, op, value}, ...]
    exclude_conditions  TEXT,    -- JSON: [{field, op, value}, ...]
    -- 维度特有属性 (FIELD_METADATA自动识别维度字段)
    derivation_mode     TEXT DEFAULT 'auto',
    inherit_children    INTEGER DEFAULT 1,
    -- 元数据
    source              TEXT DEFAULT 'manual',  -- manual/template/derived
    template_id         INTEGER,
    priority            INTEGER DEFAULT 0,
    is_enabled          INTEGER DEFAULT 1
);
```

**原3表映射**:

| 原表 | 新表映射 |
|------|---------|
| role_dimension_scopes | `include_conditions=[{field:dim+"_id", op:mode, value:vals}]` |
| data_permission_rules | `include_conditions=[...field conditions...]` |
| role_permission_levels | `permission_level` 字段 (每条规则自带) |

### 3.3 配置源

```
真正的配置源 (3个):
  源1: permission_rules (统一规则 = 维度+条件+级别)
  源2: role_menus (菜单授权 → BO actions推导)
  源3: role_intents_manual (手动Intent, 最高优先级)

辅助机制 (不是配置源):
  LEVEL_BUNDLES: action展开模板 (write→{read,list,create,update,import})
  permission_templates: 配置宏 (应用时展开为源1+源2的条目)
```

**头部产品配置源数对比**: SAP 2个 / Salesforce 2个 / AWS 1个 / Oracle 1个 / **我们 3个**

### 3.4 分组模型

#### 权限级别组

```python
LEVEL_BUNDLES = {
    'none':  [],
    'read':  ['read', 'list', 'export'],
    'write': ['read', 'list', 'export', 'create', 'update', 'import'],
    'admin': ['read', 'list', 'export', 'create', 'update', 'import', 'delete'],
}
```

配置时选 `write` → 展开为6个action Intent。每个action的data_scope可独立细调。

#### 菜单组

```python
menu "架构数据管理":
  bo_bindings: [product(primary), domain(secondary), sub_domain(secondary)]
  → 推导: product:read/list/create/update, domain:read/list, sub_domain:read/list
```

#### 模板组

```python
template "采购员标准权限":
  dimensions: domain=[采购], sub_domain=[采购供应]
  levels: product=write, version=read, sub_domain=read
  conditions: product: [{risk_level, "<=", 3}]
  menus: [采购管理, 架构数据管理]
  → 一键应用, 生成完整Intent集合
```

#### 组织维度组 — 未来扩展

> 当前系统尚无组织管理模块，此分组为未来预留。组织上线后可关联维度范围。

### 3.5 字段元数据

```python
FIELD_METADATA = {
    "domain_id": {
        "is_dimension": True,
        "dimension_chain": "domain→sub_domain→service_module",
        "triggers_menu_derivation": True,
        "triggers_permission_derivation": True,
        "cascade_filter": {"sub_domain_id": "domain_id"},
        "default_derivation_mode": "static",   # 稳定维度, 默认IN
    },
    "sub_domain_id": {
        "is_dimension": True,
        "parent_field": "domain_id",        # 笛卡尔积检测
        "default_derivation_mode": "static",
    },
    "owner_id": {
        "is_owner": True,                   # 求值引擎优先检查
        "runtime_variable": "${user.id}",
    },
    "risk_level": {
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

### 3.6 推导管道 (8步)

```
源1: permission_rules ──┐
源2: role_menus ────────┼──→ 推导管道 ──→ role_effective_intents
源3: manual_intents ────┘
     ↑ 模板展开时写入源1+源2

Step 1: 加载3个配置源
Step 2: 加载对象基线 (object_owd, 可选)
Step 3: 统一展开 (permission_rules → Layer 1 Intents)
  - 维度字段: 层级展开 + 笛卡尔积 + derivation_mode
  - permission_level → LEVEL_BUNDLES展开为actions
  - 非维度字段 → 直接作为field_conditions
  - Owner字段 → 标记优先级
  - exclude_conditions → data_scope.exclude
Step 4: 维度→菜单推导 (derive_recommended_menus)
Step 5: 菜单→BO actions推导 + 反向建议 (FR-011)
Step 6: 冲突解决 (源优先级: manual > template > derived)
Step 7: 合并 → 写入 role_effective_intents
Step 8: 标记受影响的静态Intent为stale (FR-014)
```

### 3.7 笛卡尔积语义

AC-008 修复在推导管道 Step 3 自然保留:

```
配置: domain=all + sub_domain=[101]

修复前: sub_domain自动展开为全4个 (配置失效)
修复后: sub_domain保留{101} (笛卡尔积精确生效)

业务含义: 王经理在所有领域范围内，只能看采购供应子领域的数据
即: 领域(4个) × 子领域(1个) = 4条可见数据路径
```

---

## 4. Layer 3: 交互层

### 4.1 双模式同页切换 (FR-019, 对齐 AWS Visual↔JSON)

```
┌──────────────────────────────────────────────────────┐
│ 角色权限配置 — [采购员]     [高效模式 | 细粒度模式]   │
├──────────────────────────────────────────────────────┤
│                                                      │
│ === 高效模式 ===                                      │
│                                                      │
│ Step 1: 选择起点                                     │
│   [采购员标准模板 ▼]  [复制角色▼]  [从零开始]        │
│                                                      │
│ Step 2: 配置维度范围 (自动推导菜单+功能权限)          │
│   领域: [采购 ▼]  子领域: [采购供应 ▼]               │
│   → 自动推导: 采购管理菜单 + product:read 等          │
│                                                      │
│ Step 3: 选择权限级别                                 │
│   产品: [读写 ▼]  → read,list,create,update,import   │
│   版本: [只读 ▼]  → read,list,export                 │
│                                                      │
│ Step 4: 添加条件约束                                 │
│   产品·读写: + 风险等级 ≤ 3                           │
│   产品·删除: + 创建者 = 本人                         │
│                                                      │
│ Step 5: 补充菜单 (手动追加)                           │
│   ☑ 系统管理 [手动]                                  │
│                                                      │
│ Step 6: 预览+保存                                    │
│   [推导链] [SQL预览] [匹配资源] [模拟] [保存]        │
└──────────────────────────────────────────────────────┘

切换到细粒度模式 (同一页面, 修改保持):
┌──────────────────────────────────────────────────────┐
│ 产品 (product): 🔵配置完整                           │
│ ┌────────────┬──────────────────────┬──────────┐     │
│ │ action     │ data_scope           │ exclude  │     │
│ ├────────────┼──────────────────────┼──────────┤     │
│ │ read       │ domain IN (1,2,3)    │ —        │     │
│ │            │ AND risk_level <= 3   │          │     │
│ │ create     │ domain IN (1,2,3)    │ —        │     │
│ │            │ AND created_by=me    │          │     │
│ │ delete     │ owner_id = me        │ —        │     │
│ │ export     │ (全部)               │ ⛔ 全部  │     │
│ └────────────┴──────────────────────┴──────────┘     │
│                                                      │
│ 版本 (version): 🔵配置完整                           │
│ ┌────────────┬──────────────────────┬──────────┐     │
│ │ read       │ (继承product维度)     │ —        │     │
│ └────────────┴──────────────────────┴──────────┘     │
│                                                      │
│ enum_type: 🔴未配置                                  │
└──────────────────────────────────────────────────────┘
```

### 4.2 交互特性

| 特性 | 说明 | 对标产品 |
|------|------|---------|
| **完整性指示** | 🔴未配置 🟡部分配置 🟢完整 + 角色级汇总 | SAP PFCG 红黄绿灯 |
| **推导链可视化** | 维度→菜单→actions 可点击查看来源 | SAP SU24 |
| **SQL预览+资源预估** | 实时SQL + 匹配数量+占比 | — |
| **冲突检测** | data_scope范围差异 + exclude冲突 | AWS Access Analyzer |
| **角色对比** | 角色A vs B 差异 + 用户有效权限汇总 | SAP ROLE_CMP |
| **访问模拟** | 用户+action+记录 → 允许/拒绝+原因 | AWS IAM Policy Simulator |
| **批量用户分配** | 角色详情页管理已分配用户 | SAP SU10 |
| **权限级别提示** | 选择级别时显示包含的actions | — |
| **差异对比** | 修改前vs修改后 高亮差异 | — |

---

## 5. 头部产品对比

### 5.1 配置模型

| 维度 | SAP PFCG | Salesforce | Oracle VPD | AWS IAM | **本方案** |
|------|----------|------------|------------|---------|-----------|
| 权限级别位置 | ACTVT,同条目 | Access Level,同规则 | statement_types,同策略 | Action,同Statement | action_name,同Intent |
| 范围定义 | 业务字段值域 | Owner/Criteria | WHERE谓词函数 | Resource+Condition | data_scope |
| 级别与范围 | 同条目绑定 | 同规则绑定 | 策略级绑定 | 同Statement | 同Intent绑定 |
| Deny/Exclude | ❌ | ❌ | ❌ | ✅ Effect:Deny | ✅ data_scope.exclude |
| 条件结构 | 结构化字段值 | 结构化Criteria | 自由SQL函数 | 结构化Condition | `{field,op,value}` |
| 条件类型区分 | ❌ | ❌ | ❌ | ❌ | ❌ (统一) |
| 配置源数 | 2 | 2 | 1 | 1 | **3** |

### 5.2 层级继承

| 维度 | SAP | Salesforce | Oracle | AWS | **本方案** |
|------|-----|-----------|--------|-----|-----------|
| 向下继承 | S_STRUCT INHER=X | ❌ | CONNECT BY | SCP向下 | CHILDREN_OF |
| 向上继承 | ❌ | Role Hierarchy | CONNECT BY PRIOR | ❌ | 多角色并集 |
| 继承时机 | 双轨(派生+结构) | 运行时 | 运行时 | 运行时 | 双轨(static+dynamic) |
| 基线/OWD | ❌ | ✅ | ❌ | ❌ | ✅ (FR-012) |

### 5.3 交互模型

| 特性 | SAP PFCG | Salesforce | AWS IAM | **本方案** |
|------|----------|------------|---------|-----------|
| 配置模式 | Tab式 | Tab式 | Visual↔JSON | 高效↔细粒度(同页) |
| 完整性指示 | ✅ 红黄绿灯 | ❌ | ✅ Validation | ✅ |
| 对比/差异 | ✅ ROLE_CMP | ✅ View Summary | ✅ Access Analyzer | ✅ |
| 模拟/调试 | ✅ SU53 | ❌ | ✅ Policy Simulator | ✅ |
| 批量分配 | ✅ SU10 | ✅ | ✅ | ✅ |
| 互斥约束 | ❌ | ✅ | ❌ | ✅ |
| 版本化/回滚 | ✅ Transport | ❌ | ✅ 5版本 | ✅ |

### 5.4 本方案独有优势

1. **维度层级展开**: 头部产品都没有，需手动配每个字段值
2. **笛卡尔积语义**: AC-008，头部产品未显式处理父子维度冲突
3. **三层分离**: 头部产品配置与事实混杂
4. **CHILDREN_OF默认+冻结可选**: SAP双轨但需手动选，我们默认动态+可选冻结

---

## 6. 功能需求汇总

### Must (必须实现)

| ID | 描述 | 验收标准 |
|----|------|---------|
| FR-001 | role_effective_intents 表 | data_scope={include,exclude} + derivation_mode + source |
| FR-002 | EffectiveIntentChecker | Owner > Exclude > Include > 默认拒绝 |
| FR-003 | 推导管道 (8步) | 3源→Intents, 笛卡尔积保留, 级别展开 |
| FR-004 | 字段元数据注册表 | is_dimension, is_owner, default_derivation_mode |
| FR-005 | SQL谓词生成器 | 所有操作符 + 运行时变量 + 层级子查询 |
| FR-015 | derivation_mode按维度类型区分 | 稳定维度默认static, 动态维度默认dynamic |
| FR-019 | 配置模式同页无缝切换 | 高效↔细粒度Tab切换, 修改不丢失 |

### Should (应该实现)

| ID | 描述 |
|----|------|
| FR-006 | 高效配置UI (模板+维度+级别+条件) |
| FR-007 | 细粒度配置UI (直接编辑Intent) |
| FR-008 | 推导链可视化 |
| FR-009 | SQL预览与资源预估 |
| FR-011 | 菜单反向推导 (BO→menu建议) |
| FR-013 | 配置源优先级 (manual > template > derived) |
| FR-014 | 重推导触发机制 (SAP PFUD等价) |
| FR-017 | 完整性指示 (红黄绿灯) |
| FR-018 | 角色对比 |
| FR-020 | 批量用户分配 |

### Could (可以实现)

| ID | 描述 |
|----|------|
| FR-010 | 冲突检测 |
| FR-012 | 对象基线共享 (OWD) |
| FR-016 | 访问模拟 (AWS Policy Simulator等价) |
| FR-021 | 角色互斥约束 |
| FR-022 | 配置变更版本化 |

---

## 7. 实施计划

| Phase | 内容 | 依赖 |
|-------|------|------|
| **Phase 1** | Layer 1 基础设施: effective_intents表 + 求值引擎 + SQL生成 + 字段元数据 | — |
| **Phase 2** | Layer 2 推导管道: 统一展开 + 维度集成 + 菜单集成 + 级别展开 | Phase 1 |
| **Phase 3** | Layer 3 交互: 双模式UI + 推导链 + SQL预览 + 完整性指示 + 同页切换 | Phase 2 |
| **Phase 4** | 迁移兼容: 数据迁移 + Feature flag + 回归测试 | Phase 1-3 |

---

## 8. 端到端验收

### AC-E2E-001: 维度+条件融合

```
配置: domain=all + sub_domain=[101] + risk_level<=3 + level=write
预期:
  product:read  data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101), risk_level<=3]}
  product:list  data_scope={include:[domain_id IN (1,2,3), sub_domain_id IN (101)]}
  ... (6个actions独立)
验证: 笛卡尔积生效, 条件仅绑定read, 6个actions独立
```

### AC-E2E-002: Exclude一票否决

```
配置: product:export data_scope={include:[], exclude:[status='archived']}
验证: status='archived'时export→拒绝; status='active'时export→允许
```

### AC-E2E-003: Owner优先级

```
配置: product:manage data_scope={include:[owner_id=me]}
      product:delete data_scope={include:[], exclude:[status='archived']}
验证: Owner删除自己archived产品→允许; 非Owner删除archived产品→拒绝
```

### AC-E2E-004: 条件统一

```
配置: 维度domain_id IN (1,2,3) + Owner owner_id=me + 条件risk_level<=3 + 否决status='archived'
验证: data_scope中四种类型统一为 include/exclude + field op value
```

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 迁移期间双系统并存 | Feature flag灰度切换 |
| 推导管道性能 | 增量推导 + 缓存effective_intents |
| action独立性破坏LEVEL_ORDER | Layer 2级别展开保持兼容 |
| 字段元数据维护成本 | 从business_object.yaml自动生成 |
| CHILDREN_OF运行时子查询性能 | 稳定维度默认static, 仅动态维度用CHILDREN_OF |

---

## 10. 通用规则引擎愿景

`{field, op, value}` 是通用条件表达式模型，可复用于:

| 场景 | 当前实现 | 统一后 |
|------|---------|--------|
| 权限规则 | 自由表达式 | `{field,op,value}` |
| 维度范围 | JSON数组 | `{field,op,value}` |
| 数据验证 | 各组件自定义 | ConditionEngine |
| 工作流条件 | 自定义 | ConditionEngine |
| 筛选器 | 前端filter | ConditionEditor.vue |

权限架构是通用规则引擎的第一个应用场景和验证基础。

---

## 11. 相关文档

| 文档 | 说明 |
|------|------|
| Spec 01-07 | 权限体系元数据驱动化升级 |
| [Spec 08](./08_dimension_scope_wildcard_exclude.md) | 维度范围笛卡尔积 (AC-008) |
| [Spec 09](./09_unified_permission_architecture.md) | 研究过程文档 (含决策记录) |
