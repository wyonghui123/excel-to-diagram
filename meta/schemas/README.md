# 元模型定义目录

## 这是什么？

这里是**语义数据模型的定义文件**，描述了业务系统的核心对象结构。

## ⚠️ 本目录包含两类性质完全不同的对象

本目录**不是**单一性质的对象集合，而是**两类对象混放**。阅读与修改前务必先确认文件属于哪一类：

| 类别 | 判据 | 归属 |
|---|---|---|
| **① 平台维度链** | `semantics.category` 非 `core_entity`，位于下面的「产品版本维度链」 | **平台元数据自身**（描述"这个平台由什么构成"） |
| **② 业务对象** | 有 `fields` 定义、`table_name` 非空、可被业务数据引用 | **业务/领域对象**（承载业务数据） |

> **为什么必须区分**：① 描述平台结构、随平台版本演进；② 承载业务数据、随业务演进。
> 两者变更节奏、影响半径、回滚策略完全不同，混放时容易误判影响面。

## 业务对象分区

### ① 锚层（身份 / 组织 / 位置）

四锚对象是绝大多数业务对象的外键来源：

| 对象 | 文件 | 作用 |
|---|---|---|
| `party` | [party.yaml](./party.yaml) | 身份锚（客户/供应商/员工统一主体），含 `party_internal` / `party_archive` / `party_relation` 配套 |
| `org` | [org.yaml](./org.yaml) | 组织锚。`semantics.category = security_entity`（治理分域，**刻意不同于 `core_entity`**） |
| `item` | [items.yaml](./items.yaml) | 物料锚。含 `item_group` / `item_xref` / `item_attribute_values` / `item_uom_conversion` 子表 |
| `location` | [location.yaml](./location.yaml) | 位置锚。自引用树，四类型 `site` / `warehouse` / `zone` / `bin` |

### ② 支持对象

| 对象 | 文件 | 说明 |
|---|---|---|
| `uom` | [uom.yaml](./uom.yaml) | 计量单位。**`item.base_uom` / `purchase_uom` / `sales_uom` 与 `item_uom_conversion` 的引用前提** |
| `calendar` / `calendar_day` | [calendar.yaml](./calendar.yaml) | 日历与日期展开 |
| `address` | [address.yaml](./address.yaml) | 地址 |
| `region` | [region.yaml](./region.yaml) | 行政区划 |

> **单位换算闭环（重要）**：`uom` ↔ `item_uom_conversion` ↔ `items` 三表构成完整闭环——
> `uom.yaml` 声明 `restrict_on: item_uom_conversions.uom_id`（禁止删除被引用的单位），
> `item_uom_conversion.yaml` 声明 `uom_id → target_bo: uom`，
> `items.yaml` 声明 `base_uom → target_bo: uom`。
> **换算率 `factor` 定义在换算表，不冗余存于 `uom`**；`uom` 只提供单位定义与精度。
> 修改这三者中任一文件时，必须检查另外两个。

### ③ 事务对象

`task_queue` · `task_execution` · `scheduled_task` · `ai_async_task` · `change_event` · `change_subscription` · `audit_log` · `annotation`

### ④ 平台元数据自身（维度链 + 权限 + 基础设施）

**产品版本维度链**（描述平台构成，**不是业务数据**）：
[product.yaml](./product.yaml) → [version.yaml](./version.yaml) → [domain.yaml](./domain.yaml) → [sub_domain.yaml](./sub_domain.yaml) → [service_module.yaml](./service_module.yaml) → [business_object.yaml](./business_object.yaml) → [relationship.yaml](./relationship.yaml)

> **注**：[hierarchies.yaml](./hierarchies.yaml) 的 `biz_hierarchy` 是**该链的权威声明**（`levels[]` 含 `table_name` / `foreign_key_field`）。
> 多个模块（如 `condition_parser`、`permission_dimension_engine`）已改为从它读取层级链，避免双份声明漂移。
> **本目录其他文件不应重复定义层级关系。**

其余平台元数据文件：
- **权限**（20 个）：`user` / `org_member` / `role` / `role_permission` / `role_data_permission` / `role_dimension_scope` / `permission` / `permission_rule` / `permission_bundle` / `permission_resource` / `menu` / `menu_permission` 等
- **元模型基础设施**：`enum_type` / `enum_value` / `hierarchies` / `dimension_object_mapping` / `resource_types` / `aspects` / `shared_properties` / `filter_variant` / `audit_log_expectations` / `_standard_actions` / `_action_groups` / `_audit_materialization` / `_template`
- **测试**：`test_objects` / `test_table`

### 无对应 YAML 的配套文件

`generated_schema.sql` · `index_generator.py` · `model_registry.py` · `schema_loader.py`

## 如何阅读

按上面的分区定位文件：
- 想了解**平台由什么构成** → 读产品版本维度链 + `hierarchies.yaml`
- 想给**业务对象加字段** → 读锚层 / 支持对象 / 事务对象区的对应文件
- 想了解**规则模型在哪一层** → 见下方「规则模型的归属」

## 规则模型的归属（重要）

**规则模型（`meta/core/rule_executor.py` 等）不属于本目录，也不属于"对象"层。**

| 项 | 说明 |
|---|---|
| 归属 | **机制层**（foundation 蓝图的定义） |
| 判定依据 | 规则模型**零真实主数据依赖**——只消费「字段名 → 值」映射，绑定哪个对象由规则声明自身携带 |
| 运行落点 | 三段并存：BO 声明层（`MetaObject.rules`）· EO 实例层（`RuleContext.data`）· 基础设施层（Executor + `default_by_priority`） |
| 本目录的关系 | 规则**声明**会绑定到本目录的对象（如 `items.yaml` 里可写 DEFAULT 规则），但**机制代码不依赖任何具体对象** |

详见 `docs/superpowers/specs/2026-10-02-rule-model-spec.md` §7A「分层归属」。

## 层级关系（产品版本维度链）

```
产品线 (product)
  └── 版本 (version)
        └── 领域 (domain)
              └── 子领域 (sub_domain)
                    └── 服务模块 (service_module)
                          └── 业务对象 (business_object)
                                ↕ 业务关系 (relationship)
```

## 如何修改

1. **确认文件类别**（见顶部「两类性质完全不同的对象」）
2. **编辑 YAML 文件** - 添加/修改字段、关系、操作等
3. **检查变更** - `python -m meta.tools.sync_schema --diff`
4. **执行同步** - `python -m meta.tools.sync_schema --execute`

### 主数据删除约束

锚层与支持对象（`party` / `org` / `item` / `location` / `uom` / `address` / `region`）遵循 **S19：主数据禁止物理删除**，
通过 `deletion_policy.mode: restrict` + `restrict_on` 实现。修改这些文件时不要移除该配置。

## 持久化控制

### 不需要持久化的对象

```yaml
id: search_dto
name: 搜索DTO
table_name: ""          # 可以留空
persistent: false       # 标记为非持久化
```

### 计算字段（不存数据库）

```yaml
fields:
  - id: display_text
    name: 显示文本
    type: string
    persistent: false   # 不持久化
    computed: true      # 计算字段
    compute_expr: "code + ' - ' + name"
```

### 数据库视图

```yaml
id: active_products
name: 活跃产品视图
table_name: v_active_products
is_view: true
view_definition: "SELECT * FROM products WHERE is_active = 1"
```

## AI Agent 注意

**这是元模型的唯一真相来源**。当需要理解业务模型或进行迭代优化时：

1. **优先阅读此目录下的 YAML 文件**
2. **修改元模型时直接编辑 YAML 文件**
3. **涉及字段变更时运行 Schema 同步**

详细规则见：`.trae/rules/meta-model-schema-sync.md`
