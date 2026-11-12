# Spec：单据 BO 层「元数据模型驱动 + 单一事实」治理规范

> 日期：2026-11-11　类型：**只读审计 + 治理规范**（本文不产生代码改动）
> 适用范围：`meta/schemas/*.yaml`（220 个）、`apps/*/schemas`（8 个）、`meta/core/bo_action_registry.py`、
> `meta/services/bo_action_registrations.py`、`meta/api/bo_api.py`、单据服务层。
> 关联：`docs/specs/bo-metadata-gap-2026-11-06/spec.md`（判定口径来源）、
> `.trae/rules/meta-menu-retirement.md` §四（权限码双段式存量结论）。

---

## 0. 结论

1. **权限体系只统一了「存储的生效路径」，判定层与声明层都不统一。** 存储生效路径唯一
   （`user → 个人组织 → org_permission_sets → permission_set_permissions → permissions`）；但判定层是**四条链路并存**
   （Gate / YAML RLS 覆盖 / action_ref 补充 / 未接线的 5 层 PDP），声明层是**七处声明位、仅一处自动入库**。
2. **`customer_invoice:create` 不是一个"写错的码"，而是落进了两个命名世界的缝隙**：单据类对象用双段式
   `{bo}:{bo}_{action}` 并由迁移播种，基础数据类对象用单段式 `{bo}:{action}` 并由 `permission_sync` 自动播种。
   `customer_invoice.yaml` **既没有 `authorization:`，也没有顶层 `actions:`**，于是它既不产生 declared 码、也不入库，
   运行时只剩 canonical 单段回退 → strict 下非管理员必然 403。
3. **元数据驱动只覆盖了「形状 + 展示」半层**：路由、字段、枚举、值帮助已元数据化；动作、状态转移、精度、取号、
   DDL 仍是 Python 字面量或多处双写。
4. **单一是"单一意图、多处实现"，不是单一事实**：状态值 4 处、金额精度 4 套、权限码 **7 处声明位 + 3 种码格式**、
   取号 2 轨、DDL 2 源。
5. 修复顺序：**先封堵已生效的越权面（F4）**，再把**权限声明收敛 + 自动入库 + 校验器**做成闭环（一次覆盖 228 个对象），
   同时清理悬空的 PDP 迁移；之后收敛状态机/精度/取号，最后做动作元数据化与 CI 门禁。

---

## 1. 判定口径

沿用 `bo-metadata-gap-2026-11-06/spec.md` §1：

| 判定 | 含义 |
|---|---|
| **已覆盖** | 有独立元数据声明 + 运行时强制执行 + 可被通用 API/视图消费 |
| **部分覆盖** | 有实现，但靠约定/硬编码、只在个别 BO 生效、缺声明层或配置重复 |
| **缺失** | 无对应模型或机制 |
| **空转** | 机制已建成，但声明层零使用 |

---

## 2. 权限体系专项（「为什么没对齐」）

> 研究范围：`meta/core/permission_gate.py`、`meta/services/permission_resolver.py`、`meta/core/interceptors/`
> 下 3 个权限拦截器 + `pdp_mixin.py`、`meta/api/decorators.py`、`meta/services/{permission_service,
> permission_sync_service,menu_permission_service,auth_middleware}.py`、`rls/{loader,enforce}.py`、
> `rls_rules/*.yaml`、`meta/core/yaml_loader.py`（`_resolve_authorization`）。

### 2.1 全景：四个平面，只有半个平面是统一的

| 平面 | 组成 | 现状 |
|---|---|---|
| **存储** | `permissions` / `permission_set_permissions` / `org_permission_sets` / `field_permissions` / `data_permission_rules` / `menu_permissions` | 生效路径唯一（org 路径）；但存在一张从未播种的并行表 `user_permission_sets` |
| **判定（PDP）** | `permission_gate.evaluate()` / `permission_resolver.check()` / `rls.check_action()` / `action_permission_interceptor` | **四条链路并存**，其中一条未通电 |
| **拦截（PEP）** | `permission_interceptor`(30) / `action_permission_interceptor`(31) / `write_scope` / `data_permission` / `owner_permission` / `org_admin_guard` / `association` | 主链路生效；write_scope/data_permission 的 PDP 调用是空悬 |
| **声明** | YAML `authorization` / YAML `actions` / ui actions / registry `permission_required` / 迁移脚本 / `rls_rules/*.yaml` / `@require_permission` | **七处声明位，仅一处自动入库** |

结论修正：**判定层也不统一，存储层也不是单表**。上一版「判定入口唯一、存储表唯一」的结论不成立。

### 2.2 存储平面：一条生效链路 + 一张死表

生效链路（[permission_service.py:90-103](file:///d:/filework/excel-to-diagram/meta/services/permission_service.py#L90-L103)）：

```
user → user_orgs(个人组织) → org_permission_sets → permission_set_permissions → permissions.code
```

`get_user_permissions()` 注释明确「仅通过组织路径，含祖先组织继承」。**这是唯一真正装配 JWT `permissions` 的路径。**

并行死表：`user_permission_sets`（user → set 直连）

- 全仓 `meta/migrations/` 无任何 `INSERT INTO user_permission_sets`（grep 0 命中）；
- 只有 `PermissionResolver._check_action()` 在读它；
- 结论：它是 Phase 4 PDP 迁移留下的**未播种表**，与 org 路径不是同一事实源。

其他存储平面（各自独立，互不引用）：
`field_permissions`（字段级）、`data_permission_rules`（prohibition/行规则）、`menu_permissions`（菜单）、
`permission_set_data_permission` / `permission_set_dimension_scope`（数据权限两套模型）。

### 2.3 判定平面：四条链路对比

| # | 链路 | 入口 | 码格式 | 生效性 | 失败模式 |
|---|---|---|---|---|---|
| L1 | **Gate（主）** | `permission_gate.evaluate()` / `evaluate_code()`；被 `PermissionInterceptor`(30) 与 `@require_permission` 调用 | `{bo}:{suffix}`（声明优先，回退 canonical） | ✅ 生产生效 | `strict` 403 / `shadow` 告警放行 / `off` 放行 |
| L2 | **YAML RLS 覆盖** | `permission_interceptor._check_yaml_permission()` → `rls.check_action()` | `role:admin` 等**静态角色名** | ✅ 生产生效（仅 10 个实体） | True 直接放行（**绕过 L1**）；False 403 `RLS denied`；None 回落 L1 |
| L3 | **动作补充** | `ActionPermissionInterceptor`(31)，匹配 `state_transition.action_ref` | 直接查 `user.permissions` 里的 `action_ref` 字面量 | ✅ 生产生效（仅 crud_update + 状态转移） | 无码 403；`allowed_roles` 只写 debug 日志、**不 raise** |
| L4 | **PDP（5 层）** | `PermissionResolver.check()`：Prohibition→Action→Field→Row→Owner | `{resource_type}.{action}`（**点号**） | ❌ **未接线**：`_call_pdp` 仅在 `write_scope_interceptor:320`、`data_permission_interceptor:174`、`pdp_mixin:32` 定义，全仓无生产调用；`check_with_grayscale()` 仅测试调用 | 若接线：表空 fallback **allow**；`check()` 末尾默认 Allow |

L2 的细节（关键）：`_check_yaml_permission()` 是三态返回，且角色码需 normalize（dict→code，`Spec 19 M2` 补丁）；
用户角色若不在 yaml `applies_to` 名单内则返回 `None` 回落 JWT。即**同一个人可能因角色 code 恰好叫 `manager`
而获得 YAML 放行，也可能因角色 code 是 `sales_clerk` 而回落 JWT 被拒**。

### 2.4 声明平面：七处声明位（含一处勘误）

| # | 声明位置 | 数量 | 运行时消费 | 自动入库 |
|---|---|---|---|---|
| A | YAML `authorization.permissions.{action}` | 24 个 schema | ✅ `resolve_declared_permission()`，**优先于 canonical** | ❌ |
| B | YAML 顶层 `actions:` → `MetaAction.get_permission_code()` | 46 个 schema | ❌ 运行时不读 | ✅ **唯一自动源**（`permission_sync_service._derive_from_object`） |
| C | `ui_view_config.*.actions[].permission` | 多处 | 仅前端按钮显隐 | ❌ |
| D | Python `BusinessActionMeta.permission_required`（`bo_action_registrations.py`） | 字面量 | ✅ `bo_action_registry.call()` | ❌ |
| E | 迁移/seed 硬编码（`v236/v239/v242/v243`、`init_menu_permissions.py`、`init_permission_bundles.py`） | 批量 | — | ✅（硬编码） |
| F | `rls_rules/*.yaml` 的 `actions` / `row_filters` / `field_masks` | 10 个实体 | ✅ L2 覆盖 | ❌ **完全在 `permissions` 表之外** |
| G | API `@require_permission('字面量')` | 多处 | ✅ `evaluate_code()` | ❌ 无声明校验 |

**勘误**：`meta/schemas/` 中 `crud_permissions` **0 命中**，`yaml_loader.py` 也不解析它。上一版把
`crud_permissions` 列为声明位 B 是错误的，本版删除。

结构性风险：A 决定**运行时**取哪个码，B 决定**入库**哪些码。同一对象若两者并存，天然可分歧；
`_resolve_authorization()` 在 `check: true` 时会为缺失动作自动补 `{object_id}:{action}`（[yaml_loader.py:2416-2418](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2416-L2418)），
这使 A 的形态默认是**单段**，而迁移播种的存量为**双段**。

### 2.5 门禁与灰度

- `platform_flags.permission_gate_mode()` 默认 `STRICT`；`shadow` / `off` 是显式降级开关，不是默认。
- PDP 侧另有 `WRITE_SCOPE_AUDIT_ONLY` 三阶段灰度（`check_with_grayscale`）：`AUDIT_ONLY` 返回旧判定、
  `SOFT_DEFAULT` 任一 Allow 即放行、`HARD_REJECT` 仅新体系。**该灰度未接入生产**，属未通电代码。

### 2.6 `customer_invoice` 的证据链

1. `customer_invoice.yaml` **既无** `authorization:`（24 个有该块的对象之一不含它），**也无**顶层 `actions:`
   （46/228 有）。
2. → A、B 两个声明源都缺席 → `permission_sync` 产出 **0 条**码，`authorization` 也不产生 declared 码。
3. → 运行时回退 canonical 单段：[permission_gate.py:96-107](file:///d:/filework/excel-to-diagram/meta/core/permission_gate.py#L96-L107)
   `crud_create` → `customer_invoice:create`。
4. → 但 `permissions` 表只有迁移播种的双段码 `customer_invoice:customer_invoice_create/read/...`。
5. → `strict` 下非管理员「新建发票」必然 403，前端按钮也不渲染。
6. 孤例：[customer_invoice.yaml:1095](file:///d:/filework/excel-to-diagram/meta/schemas/customer_invoice.yaml#L1095)
   `permission: customer_invoice:create`，而 detail 动作用双段码（[L1136-L1156](file:///d:/filework/excel-to-diagram/meta/schemas/customer_invoice.yaml#L1136-L1156)）
   → 同一文件两种命名空间并存。
7. 对照正确样例：[sales_order.yaml:1729](file:///d:/filework/excel-to-diagram/meta/schemas/sales_order.yaml#L1729)
   `sales_order:sales_order_create`（与 `init_menu_permissions.py` 播种一致）。

### 2.7 缺陷清单（F1-F10）

| ID | 缺陷 | 证据 | 性质 |
|---|---|---|---|
| **F1** | PDP fallback fail-open：`user_permission_sets` 为空时，只要任意权限集声明过该码，**所有用户**都放行；`check()` 末尾也默认 Allow | [permission_resolver.py:713](file:///d:/filework/excel-to-diagram/meta/services/permission_resolver.py#L713)、[check():252](file:///d:/filework/excel-to-diagram/meta/services/permission_resolver.py#L252) | 潜在（未通电），一旦接线即全量越权 |
| **F2** | Prohibition 不按角色绑定，对全系统生效；且 `is_superuser` 短路发生在 prohibition 之前 | [permission_resolver.py:370](file:///d:/filework/excel-to-diagram/meta/services/permission_resolver.py#L370) | 潜在（同上） |
| **F3** | 双管理员语义：`permission_gate.is_admin_user` 与 `auth_middleware.is_admin` 都认 `'*'`，PDP 认 `is_superuser` | [permission_gate.py:54](file:///d:/filework/excel-to-diagram/meta/core/permission_gate.py#L54)、[auth_middleware.py:195](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py#L195) | 语义分裂 |
| **F4** | **越权面**：`X-Agent-Id` 请求头（无签名校验）→ 注入 `ai-agent` 角色 → `rls_rules` 对 10 个实体（user/role/product/order/sub_domain/service_module/business_object/domain/version/user_group）`read` 放行 | [permission_interceptor.py:507 `inject_ai_agent_role`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L507)、`rls_rules/*.yaml` | ✅ **生产生效**，任意已登录用户可自抬 |
| **F5** | YAML 成为第二事实源：10 实体的读权限由静态角色名决定、**短路 JWT**；自定义角色码则回落 JWT | L2 三态逻辑（[permission_interceptor.py:550](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L550)） | 行为不可预测 |
| **F6** | 静默放行：`parent_read` / `chain_read` 默认 audit-only（`PARENT_READ_STRICT_MODE` / `CHAIN_DERIVATION_STRICT_MODE` 默认 false）；`allowed_roles` 不 raise | [permission_interceptor.py:28-31](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L28-L31)、`action_permission_interceptor._check_allowed_roles` | ✅ 生产生效 |
| **F7** | `annotation` 特判用**原始 JWT 列表** `user_has_permission(parent_perm)` 放行，绕过 L1 的 YAML Deny 与 `shadow` 语义 | [permission_interceptor.py:178-196](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L178-L196) | 局部旁路 |
| **F8** | `evaluate()` 请求内缓存键为 `(user_id, object_type, action)`，不含 resource/params；`inject_ai_agent_role` 在首次判定后才替换 `g.current_user`，可能命中旧决策 | `permission_gate.evaluate()` | 一致性隐患 |
| **F9** | `permission_sync` 只遍历 `obj.actions` → 182 个无 `actions:` 的对象**不会被自动播种**（其码只能靠迁移硬编码）；且无 `source` 字段区分声明源/播种源 | `_derive_from_object` | ✅ 已致 403 |
| **F10** | 码格式三套：Gate 冒号单段 / 迁移双段 / PDP 点号 | 全仓 | 漂移根因 |

### 2.8 根因（按影响排序）

| # | 根因 | 影响面 |
|---|---|---|
| G1 | **「是否自动入库」取决于对象是否写顶层 `actions:`**，而非统一推导 | 182 个对象 CRUD 码可能缺失 |
| G2 | **声明源与判定源分离**：运行时读 A，入库读 B；两套谁也不是权威 | 声明对了运行时未必对，反之亦然 |
| G3 | **无声明一致性校验**：`validate_consistency` 只比对 YAML actions ↔ DB，不覆盖 A/C/D/E/F/G | 漂移静默，上线后由用户 403 暴露 |
| G4 | **命名规范无仲裁**：单段/双段/点号三套并存 | 跨对象引用与按钮声明靠人工对齐 |
| G5 | **迁移未收尾**：PDP 已实现 5 层但未接线，且其依赖表从未播种 | 悬空代码 + 潜在 fail-open |

补充证据：
- [write_scope_interceptor.py:1484](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L1484) 硬编码 `f'{object_type}:create'`（假设单段）。
- `.trae/rules/meta-menu-retirement.md` §四已记录「单段码在 permissions 表 0 命中 → 不报错、静默隐藏按钮」。

### 2.9 统一设计（R1-R8）

**R1 — 单一 PDP（唯一门面）**

`permission_gate.evaluate()` 保持唯一对外判定入口，内部按固定顺序组合策略：
`prohibition（按 permission_set 绑定）→ declared/canonical code → YAML 覆盖（作为数据，不作为旁路）→ 权限集`。
`PermissionResolver` 降级为内部策略 provider（仅保留 `check_owner` / 行级判定），**删除 fail-open fallback 与默认 Allow**；
`pdp_mixin._call_pdp` / `check_with_grayscale` 要么接线并纳入该门面，要么删除，不允许长期悬空。

**R2 — 单一码格式（推荐全量单段 `{bo}:{action}`）**

与 `resolve_required_permission` 的 canonical 回退天然一致；`permissions` 表只允许一种形态，迁移脚本一次性
重命名存量双段码并同步授权关系。若选双段，则必须同时改 canonical 回退——冲突面更大，不推荐。

**R3 — 单一声明源**

每对象一个声明源：`authorization.permissions`（`check: true` 时自动补全）为**权威声明**；顶层 `actions:` 仅承载
业务动作并**引用**权威声明。运行时与入库都从同一合并结果（`MetaObject.permission_declarations`）派生。
`ui_view_config` / `BusinessActionMeta` / `@require_permission` 只允许引用，校验器拦截发明新码。

**R4 — 自动入库对象级化 + 溯源**

`permission_sync_service` 从「遍历 `obj.actions`」改为「遍历 registry 全对象」，产出标准 CRUD 码 + 业务动作码；
`permissions` 增 `source` 字段（`declared` / `standard` / `seed`），迁移播种与同步不再互相覆盖。
另修 `sync_all()` 的 `mark_synced()` 语义（当前虽会被调用，但 `validate_consistency` 不覆盖新源）。

**R5 — RLS 归位**

`rls_rules/*.yaml` 只保留 `row_filters` / `field_masks`；`actions` 段改为声明**权限码**而非静态角色名，
或明确标记 `bypass_jwt: true` 并纳入审计；从 `applies_to` 移除 `ai-agent`，`X-Agent-Id` 必须由服务端签发
（签名/白名单），不得仅凭 header 注入角色。

**R6 — 一致性校验器（CI 门禁）**

检查四组集合：

- 声明集 = 权威声明 ∪ 标准 CRUD 推导集
- 引用集 = ui actions ∪ registry `permission_required` ∪ `authorization.permissions` ∪ `@require_permission`
  ∪ `rls_rules.actions`
- 入库集 = `permissions` 表
- 授予集 = `org_permission_sets` / 权限集引用

任意 `引用集 - 声明集`、`引用集 - 入库集`、`声明集 - 入库集` 非空 → exit 1，输出 file:line。

**R7 — 灰度只允许存在于单一 PDP 内部**

`shadow` / `off` / 三阶段灰度统一由 `permission_gate` 读取一个 flag；不再允许拦截器各自读 env 形成第二条路径
（`PARENT_READ_STRICT_MODE` 等应上收为正式判定层，而非 audit-only 旁路）。

**R8 — 存量修复**

- `customer_invoice.yaml:1095` → 统一到规范码（方案 1 下需确保 `customer_invoice:create` 入库）。
- `write_scope_interceptor.py:1484` 的 `f'{object_type}:create'` 改调 `permission_gate` 的 canonical 生成函数。
- 对 182 个无声明源的对象跑一次 R4 同步，产出缺失码清单并确认后入库。
- 封堵 F4：移除 header 注入或加签名校验；对 `rls_rules` 的 `ai-agent` 规则重新评审。

---

## 3. 元数据驱动评级

| 层 | 评级 | 证据 | 缺口 |
|---|---|---|---|
| 路由 / 通用 CRUD | 已覆盖 | `bo_api.py` 全 `/＜object_type＞` 动态路由 | 无 |
| 字段 / 枚举 / 值帮助 / 切面复用 | 已覆盖 | `yaml_loader` `aspects`/`includes`；220 schema 注册 | 无 |
| 准入模式 | 已覆盖 | `generic_api_mode` 定义 + `bo_api.py` 守卫 | 无 |
| 表结构 DDL | **部分覆盖** | `sync_schema.py` 派生 `generated_schema.sql`，需手工 sync | 与迁移双源，无自动 diff |
| 取号 | **部分覆盖** | YAML `numbering` vs `bo_api.py:209 _NUMBERED_OBJECTS`（3 对象） | 声明不参与通用取号 |
| 动作（Action） | **部分覆盖** | `bo_action_registrations.py` 全 Python 字面量；仅 46/228 schema 有顶层 `actions:`，且运行时不读、只用于同步入库 | YAML 声明与注册表未合一 |
| 功能权限判定 | **部分覆盖** | 主链路 `permission_gate` 生效；另有 YAML RLS 覆盖（10 实体）、`action_ref` 补充、未接线的 5 层 PDP | 四条链路并存，见 §2.3 |
| 动作运行时约束 | **缺失** | `bo_action_registry.call()` 明确不走拦截器链 | 审计/组织范围/字段策略/事件不生效 |
| 状态 × 字段矩阵 | **空转** | 引擎/拦截器/YAML 结构就绪，全仓零 `field_policy` 声明 | 未启用 |

---

## 4. 单一事实漂移清单

### P0（已实际影响运行）

**D1 状态字段四份定义，DDL 不等价**

| 位置 | 形态 |
|---|---|
| `customer_invoice.yaml` enum_values | 5 值 |
| YAML `state_transition` | 转移矩阵 |
| `customer_invoice_service.py` 常量 | Python 列表 |
| `v236__customer_invoice.py:134-135` | `VARCHAR(20)` + CHECK(5 值) |
| `generated_schema.sql` | `VARCHAR(200)` + **无 CHECK** |

从迁移建库有约束，从 generated 建库约束静默消失。`receipt`、`sales_order` 同构复现。

**D2 权限码漂移** → 见 §2。

**D3 动作双入口、合规性不等价**

- 通用 CRUD：`bo_framework` 完整拦截器链。
- BO 动作：`registry.call()` 仅权限字符串 + preconditions，**不过审计/组织范围/字段策略/事件/版本**。
- 且该差异只写在一行注释里，无元数据字段表达。

### P1

**D4 状态机三份**：YAML `state_transition` / 服务层硬编码转移表 / DDL CHECK。
`customer_invoice_actions.py`、`customer_invoice_service.py`、`receipt_service.py`、`sales_order_guard_service.py` 各自维护。

**D5 金额精度四套**：`meta/core/rounding.py` 已存在且发票已复用；`sales_order_amount_service`、
`sales_order_header_discount_service`、`billing_plan_service` 各写 Decimal 舍入，`billing_due_list.py` 用 SQL `ROUND(...,4)` 字面量。

**D6 取号双轨**：YAML `numbering` vs `_NUMBERED_OBJECTS` 三对象白名单；`customer_invoice` 声明取号却由服务层自取。

**D7 字段白名单重复**：`customer_invoice_service.HEADER_FIELDS` 与 YAML `fields` 双份。

### P2

**D8 分摊尾差**：抬头折扣走 `allocation_service.plan`（尾差守恒），发票行分摊自写比例舍入（无尾差回收）。
**D9 一致性门禁缺失**：`sync_schema --diff` / `drift_check` 手工执行，`.drift_report.json` 已陈旧。
**D10 apps/*/schemas 第二加载目录**：与 `meta/schemas` 无统一清单与冲突检测。

---

## 5. 特异性（硬编码特判）清单

> 指通用路由中按对象名/对象集合写死的分支——元数据驱动的反面。

| # | 位置 | 特判内容 | 收敛建议 |
|---|---|---|---|
| S1 | `bo_api.py:209` | `_NUMBERED_OBJECTS` 仅 3 个对象取号 | 改为读 YAML `numbering` |
| S2 | `bo_api.py:709/948/1042/1056` | `audit_log` 4 处分支 | 转为 YAML 能力开关（如 `capabilities.audit_read: true`） |
| S3 | `bo_api.py:978/1072-1077` | relationship 排序/过滤白名单 | 转为 `semantics.filterable` + `allowed_sort_fields` 声明 |
| S4 | `bo_api.py:206-236/264-317` | 销售订单默认值、销售员、取号清单 | 转为 `defaults:` / `numbering:` 声明 |
| S5 | `write_scope_interceptor.py:1484` | `f'{object_type}:create'` 单段假设 | 走 `permission_gate.required_code()` |
| S6 | `customer_invoice_service.py` `HEADER_FIELDS` | 字段白名单 | 读 `MetaObject.fields` |
| S7 | `bo_action_registry.call()` | 绕过拦截器链 | 增加 `governance` 元数据字段（`none/audit/audit_scope`）+ 白名单测试 |
| S8 | `apps/*/schemas` | 第二 schema 目录 | 纳入统一清单与冲突检测 |

---

## 6. 细化任务

| ID | 任务 | 改动点 | 验收标准 | 测试 |
|---|---|---|---|---|
| T1 | 权限命名规范定型 | §2.9 R2 | 全仓只有一种码形态（单段/双段二选一，**需用户拍板**）；`permissions` 表零双形态；grep 混用 = 0 | 新增 `test_permission_naming.py` |
| T2 | 权限自动入库对象级化 + 溯源 | `permission_sync_service`、`permissions.source` | 任意 BO（含无 `actions:` / 无 `authorization:`）均有标准 CRUD 码入库；断言 228/228；`source` 可区分 declared/standard/seed | `test_permission_sync_coverage.py` |
| T3 | 顶层 `permissions:` 声明块 | `models.py` / `yaml_loader.py` | 声明块可解析、可同步、可导出 OpenAPI；与 `authorization.permissions` 合并为唯一 `permission_declarations` | YAML 加载单测 + 同步幂等 |
| T4 | 一致性校验器 + CI | 新脚本 / `validate_consistency` | **四集合**校验：引用集 ⊆ 声明集 ⊆ 入库集；覆盖 A/C/D/E/F/G 七处声明位；漂移 exit 1 并输出 file:line | 故意注入漂移的负向用例（每声明位至少 1 条） |
| T5 | 存量清理 | `customer_invoice.yaml:1095`、`write_scope_interceptor.py:1484`、182 个无声明对象 | 三处走统一码；缺失码清单为空 | 权限单测 + E2E 新建发票 |
| T13 | PDP 迁移收尾 | `permission_resolver.py`、`pdp_mixin.py`、`auth_middleware.is_admin` | 二选一并落地：①接线进 `permission_gate` 门面（删除 fail-open fallback / 默认 Allow / prohibition 不绑角色 / 两套管理员语义）；②整体删除 `user_permission_sets` 与灰度死码 | `test_secure_by_default.py` 全绿 + 新增 fail-open 负向用例 |
| T14 | 越权面与静默放行封堵 | `permission_interceptor.inject_ai_agent_role`、`rls_rules/*.yaml`、annotation 特判、parent/chain 开关 | `X-Agent-Id` 无签名不得注入角色；`rls_rules` 移除静态 `ai-agent` 放行或改为 AND JWT；annotation 特判走 `permission_gate`；`PARENT_READ_STRICT_MODE` / `CHAIN_DERIVATION_STRICT_MODE` 默认 true | 越权回归：任意用户带 `X-Agent-Id` 读 user/role 必须 403 |
| T6 | 状态机单一派生 | YAML → Python 常量 + DDL CHECK 生成 | 三处值集合完全一致（脚本比对） | `test_state_machine_single_source.py` |
| T7 | DDL 单源 | `sync_schema` 纳入迁移 / CI diff | `sync_schema --diff` 空输出 | 现有 P15 比对扩展 |
| T8 | 精度统一 | 4 处改调 `rounding.py` | 同额同精度同结果 | 金额单测 + 现有单据回归 |
| T9 | 取号元数据化 | `_NUMBERED_OBJECTS` → YAML | 声明即生效 | 取号单测 |
| T10 | 动作元数据化 | YAML `actions:` → registry | 注册表由 YAML 加载 | 注册表单测 |
| T11 | 动作治理显式化 | `BusinessActionMeta.governance`（`none/audit/audit_scope`） | 每个动作标注，白名单可测 | 契约测试 |
| T12 | 特异性收敛 | S1-S8 | 通用路由无对象名分支 | 现有回归 + 新增负向用例 |

### 6.1 落地现状（2026-11-11 会话，改动未提交）

| ID | 状态 | 证据 |
|---|---|---|
| T1 | 运行时已按**单段式**实现，尚待用户正式定型 | `permission_sync_service._derive_from_object`（对象级派生、标准 CRUD 补齐、单段码） |
| T2 | 已实现 | `sync_all` 改为遍历 registry 并对每个对象派生；无 `actions:` / 无 `authorization:` 的对象同样入库 |
| T4 | 已实现（未接 CI） | `scripts/check_permission_consistency.py`：A/C/D/G 四引用位 + DECLARED/STORED/GRANTED 三集合，R1/R1w/R2/R3/R4，漂移 exit 1 |
| T5 | 部分 | v249/v250 已执行入库；`customer_invoice` 码已统一；**菜单种子未纳入校验** |
| T6-T11 | 未实现 | 见 §10 的 E1-E8 |
| T13 / T14 | 未实现 | 见 §7 |

> 本文 §10 是上述待办的**执行级细化**（改动点 / 验收 / 测试 / 回滚）；§9 是设计取舍的对标依据。

---

## 7. 实施顺序与门禁

```
P0  T14 → T1 → T2 → T4 → T5   （先封越权面，再闭权限声明闭环，一次覆盖全部对象）
P1  T13 → T6 → T7 → T8 → T9   （收尾 PDP 迁移 + 单一事实收敛）
P2  T3 → T10 → T11 → T12      （动作与特异性元数据化）
```

门禁：
- 每次合并必须 `python d:\filework\test.py --failed` 通过。
- T1 未拍板码格式前，T2/T4 只做实现不做入库变更（避免一半单段一半双段）。
- T14 的越权回归用例为 P0 阻断项：任意用户伪造 `X-Agent-Id` 读 `user` / `role` 必须 403。
- T4 校验器进入 pre-merge 检查，失败阻断合并。
- T7 的 `sync_schema --diff` 空输出作为合并前置条件。

---

## 8. 非目标

- 不引入 SAP 双轨状态、传输请求、多级状态网络（见 `bo-metadata-gap` §7）。
- 不在本轮实现 `field_policy` 声明（引擎已就绪，属独立议题）。
- 不重构 `apps/*/schemas` 目录结构，仅纳入统一清单。

---

## 9. 对标依据（元数据模型驱动头部产品）

> 完整横评见 `docs/specs/spec-metadata-driven-backend-research.md`（2026-06-07，7 个产品 × 能力矩阵 × 差距 × 路线图）。
> 另一份 `docs/research/head-product-metadata-permission-research.md` 在 SAP 章节中途截断（仅 152 行），**不作为引用依据**。

行业共同点只有一句：**动作、权限、状态、DDL 都是一等元数据，且都带「差异检测 + 部署前校验」**。
本仓当前是「数据形状已元数据化，单据行为仍是代码字面量」，9 项待办正是补齐行为层。

| 头部机制 | 典型产品 | 本仓对应项 | 采用的设计含义 |
|---|---|---|---|
| 声明式动作契约（参数/权限/幂等 → 运行时注册） | Salesforce Apex/Metadata API、SAP CAP CDS actions、Dataverse Custom API、Palantir Ontology Action Type | E8 / E3 | YAML `actions:` 必须成为注册表的**唯一人工声明位**；`governance`（`none/audit/audit_scope`）等治理属性显式声明，不能靠注释 |
| 状态模型挂在对象元数据上，UI/ACL 同源 | ServiceNow Table + UI Action + ACL、Salesforce Validation Rule/Flow | E4 / E7 | `state_transition` 单一派生；Python 只做读取，不复制转移表 |
| Schema 由元数据生成，部署前做 diff | Salesforce Metadata API source tracking、Dataverse Solution 导出/比较 | E2 / E9 | 迁移是建库合同，`generated_schema.sql` 是**期望快照**；CI 比对「快照 ≡ 实际库」 |
| 权限点集中声明，其余产物生成 | Salesforce Permission Set / Profile 生成、ServiceNow ACL 继承 | E1 / E7 | 单一生成函数 + 回写/`--check`，禁止手工第二份 |
| 平台级精度/编号策略 | Dataverse 货币精度、SAP 编号范围（Number Range） | E5 / E6 | 精度/取号从对象声明派生，服务层只调用 |

结论：**不引入新框架**，只把已有 YAML 提升为行为层真源，并把「生成 + 校验」固化进 CI（与上述产品的部署门禁同构）。

---

## 10. 九项执行细化（E1-E9）

> 映射：E1↔P0-1↔T1/T2/T4/T5；E2↔P0-2↔T7；E3↔P0-3↔T11；E4↔P1-4↔T6；
> E5↔P1-5↔T8；E6↔P1-6↔T9；E7↔P1-7↔T1/T3；E8↔P2-8↔T10；E9↔P2-9↔T4/T7。

### E1 权限码对齐闭环（P0）

**现状（已取证）**
- 已完成（未提交）：`permission_sync_service._derive_from_object` 已是对象级派生、单段码、标准 CRUD 补齐；`scripts/check_permission_consistency.py` 已覆盖 A/C/D/G 四引用位与 DECLARED/STORED/GRANTED 三集合。
- 未完成：① 无「registry 派生 → 回写 YAML `ui_view_config.*.actions[].permission`」的生成器；② 校验未纳入**菜单种子**；③ 未进 CI。

**目标设计**
- 权威方向定为 **registry 派生优先**（取代 §6 T1 的「待拍板」）：`_derive_from_object` 是唯一生成函数，YAML 的 `permission:` 是它的投影。
- 新增 `scripts/sync_permission_codes.py --check|--write`：按 canonical 码回写 ui actions 与缺失的 `authorization.permissions` 键，幂等（跑两次零 diff）。
- 校验集合扩为 **5 类**：引用集（A/C/D/G + MENU）、声明集、入库集、授予集。

**改动点**
- `meta/services/permission_sync_service.py`：把 `_derive_from_object` 提为模块级 `derive_object_permissions(obj) -> List[str]`，供同步与生成器共用（单一生成函数）。
- 新增 `scripts/sync_permission_codes.py`：只做**值替换**（`permission: <码>` 行级锚点），不重排 YAML；`--check` 输出 `file:line` 并 exit 1。
- `scripts/check_permission_consistency.py`：新增 MENU 集合读取（`menu_permissions.required_permissions`），规则 R5 `MENU ⊆ STORED`（error）、R6 `MENU ⊆ DECLARED`（warning）。
- `meta/scripts/init_menu_permissions.py`：定位为菜单种子生成源，新增 `--check` 断言代码常量与 DB 一致。

**验收**
1. `python scripts/sync_permission_codes.py --check` → exit 0，diff 0。
2. `python scripts/check_permission_consistency.py` → R1=R2=R3=R5=0；R1w/R4 仅 WARNING。
3. 负向：临时改一个 ui permission 为错码 → 两个命令均 exit 1 且打印 `file:line`。

**测试**：新增 `meta/tests/test_permission_code_sync.py`（幂等两次、错码检测、菜单集缺失检测）。
**回滚**：生成器只改 YAML，`git revert` 即回退；DB 不变。
**风险**：行级回写可能破坏 YAML 排版 → 先在 3 个对象试跑并人工 diff；不做 ruamel 重排。

### E2 DDL 单源（P0）

**现状（已取证）**
- `generated_schema.sql` 中状态列为 `VARCHAR(200)` 且无 CHECK；`v236__customer_invoice.py` 为 `VARCHAR(20)` + CHECK(5 值)。`schema_generator` 无 enum→CHECK 渲染，STRING 统一 `VARCHAR(200)`。
- `sync_schema --diff` 比对的是 `.schema_version.json` 的元模型哈希，**不比对真实 DB**。

**目标设计（方案 A：迁移单源 + generated 作期望快照）**
- 建库唯一合同 = `meta/migrations/*`；`generated_schema.sql` 降级为「由 registry 渲染的期望快照」，CI 断言二者等价。
- `schema_generator` 补齐：STRING 长度取 `semantics.max_length`（缺省 200）；`MetaField.enum_values` 非空 → 渲染 `CHECK (col IN (...))`（值顺序与迁移一致）。
- `sync_schema` 增加真实库比对：`--diff --against db|snapshot --check`，用 `PRAGMA table_info` + `sqlite_master.sql` 归一化后比较。

**改动点**
- `meta/core/schema_generator.py`：长度 + CHECK 渲染（按 dialect 分支，SQLite 先行）。
- `meta/tools/sync_schema.py`：新增 `--against` / `--check`；保留原哈希 diff 作变更提示。
- 新迁移：为 `receipt` / `sales_order` 等状态列补齐 CHECK，与 `customer_invoice` 同构。

**验收**
1. 空库执行全部迁移 → `python -m meta.tools.sync_schema --diff --check` → exit 0。
2. 手工把某表状态列改为 `VARCHAR(200)` → 同命令 exit 1，指出 `table.column`。
3. 新增带 `enum_values` 的对象但无迁移 → CI 失败并提示生成迁移。

**测试**：`meta/tests/test_schema_single_source.py`（DDL 归一化器单测 + 漂移负向）。
**回滚**：保留改造前 `generated_schema.sql` 作为 revert 基线；迁移只新增不删除。
**风险**：MySQL/PG 的 CHECK 语法差异 → 生成器按 dialect 分支，CI 本轮只校验 SQLite。

### E3 `call()` 链路治理（P0）

**现状（已取证）**
- `bo_action_registry.call()` 仅做 `permission_required` + `preconditions`；`BusinessActionMeta` 无 `governance`。
- `bo_action_api.py:162` 的 HTTP action 端点也调用 `call()`，即**所有 BO 动作共用该轻链路**；`_build_user_context()` 只提供 `user_id/user_name/ip_address/permissions`（无 data_source / org）。

**目标设计（两步，均 P0）**

> §14.1 修正：不用布尔，改为三值枚举。布尔把「许可 / 前置条件 / 留痕」压成一维，Step 2 必然二次迁移（依据 Palantir Action Type 的三个正交面）。

- Step 1 声明化：`governance: Optional[str] = None`，取值 `none | audit | audit_scope`
  - `none`：只做 `permission_required` + `preconditions`（保持现状语义）；
  - `audit`：额外写审计；
  - `audit_scope`：审计 + 组织范围校验。
  - `bo_action_contract.validate_action_meta` 要求非 None（`BO_ACTION_GOVERNANCE=warn` 时降为 WARNING，`strict` 时 ERROR）；白名单测试。
- Step 2 治理最小集：`call()` 按 `governance` 分支
  - `audit` / `audit_scope`：写 `audit_logs`（action_id / object_type / params_hash / user_id / status / trace_id），用 trace_id 去重避免与 ActionExecutor 双写；
  - `audit_scope`：必须同时声明 `org_scope: {param_field: xxx}`，用 `OrgScopeService.visible_org_ids` 校验入参；**声明了 `audit_scope` 却缺 `org_scope` → 契约 ERROR**（不静默降级）。
- 拒绝方案：在 `call()` 内实例化 18 拦截器链——依赖 Flask `ActionContext`/`data_source`，且与既有审计双写。

**改动点**
- `meta/core/bo_action_registry.py`：`BusinessActionMeta` 增 `governance: Optional[str]`、`org_scope: Optional[dict]`；`call()` 按治理级别分支。
- `meta/core/bo_action_contract.py`：`governance` 枚举必填校验（受灰度开关控制）+ `audit_scope` ↔ `org_scope` 联动校验 + `org_scope` 形状校验（`param_field` 必须存在于 `parameters`）。
- `meta/services/bo_action_registrations.py`：19 个 action 逐一标注（只读类 `none`，普通写类 `audit`，跨组织写类 `audit_scope`）。
- 复用 `AuditService`（`meta/core/interceptors/audit_interceptor.py` 已依赖）新增最小记录函数 `write_action_audit(entry: dict) -> None`。

**验收**
1. `report_registry_contracts()` 0 error，无 `governance is None`，无 `audit_scope` 缺 `org_scope`。
2. 写类 action 成功调用后 `audit_logs` 恰新增 1 行且含 action_id。
3. 跨组织入参 → 返回失败且 code=`ORG_SCOPE_DENIED`。
4. HTTP action 端点回归无重复审计。

**测试**：`meta/tests/test_bo_action_governance.py`（白名单 / 审计写入 / 跨组织拒绝 / 幂等去重）。
**回滚**：`governance` 默认 None 会 fail-fast → 先用 `BO_ACTION_GOVERNANCE=warn` 灰度一版（None 与缺 `org_scope` 仅 WARNING），再切 `strict`。
**风险**：审计双写与性能 → 仅对 `object_type` 为真实 BO 的写动作记录；params 只存哈希与白名单字段。

### E4 状态机单一派生（P1）

**现状（已取证）**
- YAML 已解析（`MetaObject.get_state_transitions()`，`models.py:1337`）；4 个服务仍各维护转移表：`attribute_promotion_service.py:42`、`change_request_service.py:25`、`configuration_guard_service.py:38`、`purchase_order_guard_service.py:37`；另有 `customer_invoice` / `receipt` / `sales_order` 同构。

**目标设计**
- YAML `state_transition` 是唯一声明；新增只读 API：`allowed_transitions(object_id, current)` / `can_transition(from, to)` / `transition_action(from, to)`。
- 服务层删除本地 dict，只调用 API；DDL CHECK 由 `enum_values` 派生（联动 E2）。

**改动点**
- 新增 `meta/core/state_machine.py`（薄封装 + 进程内缓存，schema mtime 失效）。
- 4 个服务替换为 API 调用；`models.py` 增加 `MetaObject.transition_map()` 便捷方法。
- 实施前置脚本：输出「服务表 − YAML 边」差集，缺失边补进 YAML 后才删代码。

**验收**
1. `grep` 4 个服务的转移 dict = 0。
2. 对有 `state_transition` 的对象遍历 YAML 全部边，API 返回一致；非法边被拒。
3. 状态值集合（YAML enum / DDL CHECK / 服务引用）三方比对脚本 0 diff。

**测试**：`meta/tests/test_state_machine_single_source.py`（全量边 + 非法边）。
**风险**：YAML 漏声明隐式转移 → 用上述差集脚本作为删代码的硬门禁，禁止先删后补。

### E5 金额精度统一（P1）

**现状（已取证）**
- `meta/core/rounding.py` 已提供 `round_amount`（L120）、`round_by_mode`（L79）、`normalize_decimals`（L101）。
- 例外仍在：`customer_invoice_service.py:209` 自写 `quantize`、`billing_plan_service.py:107` 自写、`billing_due_list.py` 用 SQL `ROUND(...,4)` 字面量、`sales_order_guard_service.py:326` 自建 `_round_amount`。

**目标设计**

> §14.1 修正：精度来源不止一处（Dataverse 也是「货币记录精度 + 列 precision」两处并存），必须显式规定优先级，否则同名金额在不同模块取到不同小数位。

- Python 舍入 100% 走 `round_amount(value, places, mode)`；`places` 由 `places_for(object_id, field_id)` 给出，优先级**固定**为：
  1. 字段 `semantics.precision`（字段级显式声明）
  2. 货币 `currency.decimal_places`（货币记录精度）
  3. `DEFAULT_AMOUNT_DECIMALS`（=2，平台兜底）
- 三档全缺 → 返回兜底值并记 WARNING（不猜测 4）；`places` 超出 `0..MAX_AMOUNT_DECIMALS` 按 `normalize_decimals` 收敛。
- SQL 小数位从同一映射取，禁止字面量；值经 int 白名单校验后再拼 SQL。

**改动点**
- `meta/core/rounding.py`：新增 `places_for(object_id: str, field_id: str | None = None) -> int`（按 schema mtime 失效的缓存，内部实现上述优先级链）。
- 4 处替换：`customer_invoice_service.py:209`、`billing_plan_service.py:107`、`sales_order_guard_service.py:326` 改 `round_amount(..., places_for(obj, field), mode)`；`billing_due_list.py` 改 `f"ROUND(x, {places})"` 且 `places = places_for(...)`。
- 新增 `scripts/check_rounding_single_source.py`：允许清单外出现 `quantize(` / `ROUND(` → exit 1。

**验收**
1. 表驱动用例：同额/同精度/同 mode 各模块结果一致。
2. 优先级链负向用例：字段声明 3 / 货币 2 → 取 3；仅货币 4 → 取 4；皆无 → 2 且有 WARNING。
3. lint 0 检出。
4. `billing_due_list` 输出金额与改造前逐行一致（快照比对）。

**回滚**：单文件替换，按文件 revert。
**风险**：`none`/`round` 历史等价语义 → 沿用 `rounding.py` 已固定映射，不改语义。

### E6 取号元数据化（P1）

**现状（已取证）**
- `meta/api/bo_api.py:205-220`：`_NUMBERED_OBJECTS` 仅 3 对象，另有 `_NUMBER_SEQ_LABELS` / `_NUMBER_SEQ_FIELDS` 三份常量。
- YAML `numbering` 已有 6 个对象（`sales_order.yaml:99` 形如 `no_field/date_field/type_table`）→ 与白名单已漂移。

**目标设计**
- `_NUMBERED_OBJECTS` 改为 `[o.id for o in registry if o.numbering]`；编号列/日期列/类型表/中文标签全部来自 YAML。
- 服务层自取号（`customer_invoice`）收敛到统一取号服务。

**改动点**
- `meta/api/bo_api.py`：删除 3 个常量与映射，新增 `_numbering_spec(object_id)` 读 `MetaObject.numbering`（标签回落 `MetaObject.name`）。
- 取号服务统一入口（现有 `DocumentNumberService` 若存在则复用）。

**验收**
1. 给任一 YAML 加 `numbering:` 后新建即自动取号，**无需改 Python**。
2. 现有 6 对象编号格式回归一致；唯一约束与并发取号用例通过。

**风险**：`numbering` 结构不统一（部分对象用 `number_sequence_id`）→ 以 `no_field/date_field/type_table` 为最小键集，缺键对象加载期 WARNING，不猜测。

### E7 权限点收敛为一处声明（P1）

**现状**：单段化 + 对象级派生已完成（未提交）；但人工声明仍分散在 YAML `authorization` / ui `permission`、`bo_action_registrations.py` 字面量、API 装饰器、菜单种子。

**目标设计**
- 唯一**人工**声明位 = YAML（`authorization.permissions` + `actions[].permission`）。
- 其余全部**生成**：`permissions` 表（`sync_all`）、ui actions（E1 生成器）、菜单 `required_permissions`（`scripts/sync_menu_permissions.py`）、OpenAPI（`list_schemas`）。
- `bo_action_registrations.py` 的 `permission_required` 从 YAML actions 读取（依赖 E8）。

**验收**
1. 全仓新增权限码只允许出现在 YAML；`grep` 检查无「新造码」。
2. 三个生成器 `--check` 均 0 diff。
3. 新增对象只写 YAML 即可获得 DB 权限、ui 码、菜单项。

**依赖**：E8（否则字面量无法移除）。**风险**：生成器写 YAML 与人工编辑冲突 → 只允许生成器写 `permission:` 值，其余字段不碰。

### E8 YAML `actions:` → registry 启动加载（P2）

**现状（已取证）**
- `yaml_loader.parse_action`（`yaml_loader.py:1905`）已产出 `MetaAction`（id/name/type/method/path/schema/parameters/behavior），`MetaAction` 定义于 `models.py:688`，**无 handler/permission/governance 字段**。
- 注册表仍由 `bo_action_registrations.py` 的 19 条字面量 populate；仅 46/228 schema 有顶层 `actions:`，且运行时不读。

**目标设计**

> §14.1 修正：`handler` 是「代码执行入口」，比 `permission` 更危险。Palantir 明确警告「函数编辑权限不跟随动作权限」——动作的许可不自动约束 handler 内部的越权读写，因此必须加命名空间白名单与加载期校验。

- 新增启动期 `bo_action_loader`：把 YAML 顶层 `actions:` 注册进 registry，handler 用 dotted path 解析；重复 action_id 启动失败。
- handler 只能指向 **`meta.services.actions.*`** 命名空间的模块级纯函数；其它前缀 → 启动 fail-fast。
- 未迁移的字面量进 `LEGACY_LITERAL_ACTIONS` 白名单，CI 断言**只减不增**。

**改动点**
- `meta/core/models.py`：`MetaAction` 增 `handler: str`、`permission: str`、`governance: Optional[str]`。
- `meta/core/yaml_loader.py parse_action`：解析上述三字段（缺 `handler` 时不进注册表，仅保留 UI 动作语义）。
- 新增 `meta/services/bo_action_loader.py`：`load_actions(registry) -> int`，importlib 解析 + `registry.register()`；在 app 启动（或 `meta/__init__`）调用。加载期做三件事：命名空间白名单校验、action_id 去重、`permission`/`governance` 与 E1 声明集交叉校验。
- `meta/services/bo_action_registrations.py`：`LEGACY_LITERAL_ACTIONS` 白名单常量 + 启动加载顺序（YAML 优先，字面量兜底）。
- 权限配置变更审计：YAML 中 `permission` / `governance` 变化导致注册结果改变时，写 `audit_logs`（`action=permission_config_change`，含 object_id / action_id / 字段 diff），避免「改 YAML 即改授权」无声生效。

**验收**
1. YAML 声明一个测试 action → `registry.has()` True 且 `call()` 可执行。
2. 注册总数 = YAML 声明数 + 白名单数。
3. handler 路径错误 → 启动 fail-fast，报 object_id + action_id。
4. handler 命名空间越界（如 `meta.api.*`）→ 启动 fail-fast。
5. 修改某 action 的 `permission` 后重启 → `audit_logs` 新增 1 条 `permission_config_change`。

**测试**：`meta/tests/test_bo_action_loader.py`（正常 / 重复 / 坏 handler / 命名空间越界 / 权限变更审计 / 白名单只减不增）。
**回滚**：`BO_ACTION_LOADER=off` 关闭 YAML 加载，回落到 19 条字面量（白名单兜底）。
**风险**：启动期 import 副作用 → handler 只允许模块级纯函数；加载失败不吞异常。

### E9 一致性门禁进 CI（P2）

**现状**：`.github/workflows/schema-check.yml` 实为 GraphQL 兼容性检查；`check_permission_consistency.py` 与 `sync_schema --diff` 均未接入 CI。

**目标设计**
- 新增/改造 workflow（`metadata-gate.yml`），三个 job：
  1. `permission-gate`：`python scripts/check_permission_consistency.py` + `sync_permission_codes.py --check`
  2. `schema-gate`：建临时库 → 执行迁移 → `sync_schema --diff --check`
  3. `action-contract-gate`：`report_registry_contracts()`（含 E3 的 `governance` 枚举必填、E8 的 handler 命名空间白名单与 action_id 去重、legacy 白名单只减不增）
- 本地等价入口：`scripts/metadata_gate.ps1`（一条命令跑三项，pre-merge 使用）。

**验收**
1. PR 注入任一类漂移 → 对应 job 红。
2. main 全绿；本地 `metadata_gate.ps1` 与 CI 结果一致。

**风险**：CI 无 DB → 先跑迁移建临时库；权限 gate 需要确定性 seeds，用测试快照而非线上库。

---

## 11. 验收与门禁矩阵

| 门禁 | 命令 | 通过标准 | 失败级别 |
|---|---|---|---|
| 权限一致性 | `python scripts/check_permission_consistency.py` | R1=R2=R3=R5=0 | 阻断 |
| 权限码回写幂等 | `python scripts/sync_permission_codes.py --check` | diff=0 | 阻断 |
| DDL 单源 | `python -m meta.tools.sync_schema --diff --check` | exit 0 | 阻断 |
| 动作契约 | `report_registry_contracts()` | 0 error（`governance` 非空、`audit_scope`↔`org_scope` 一致、legacy 白名单只减不增） | 阻断 |
| 精度单源 | `python scripts/check_rounding_single_source.py` | 0 检出 | 阻断 |
| 状态机三方一致 | `test_state_machine_single_source.py` | 全量边通过 | 阻断 |
| 回归 | `python d:\filework\test.py --failed` | 全绿 | 阻断 |

---

## 12. 实施顺序（细化后）

```
Wave 0  提交现有 T2/T4（用户授权后）——避免与后续生成器冲突
Wave 1  E1 → E3 → E2            （权限闭环、行为治理、DDL 单源）
Wave 2  E4 → E6 → E5 → E7      （状态机、取号、精度、声明收敛）
Wave 3  E8 → E9                 （动作元数据化 + CI 门禁）
```

每 Wave 末尾必须 `python d:\filework\test.py --failed` 全绿；E9 的 workflow 在 Wave 3 前可先用本地 `metadata_gate.ps1` 顶替。

---

## 13. TBD 清单

| ID | 事项 | 缺失信息 | 下一步 |
|---|---|---|---|
| TBD-1 | 权限码格式正式定型 | 运行时已按单段实现（T2/T4），但原 T1 标注「需用户拍板」 | ✅ 已拍板（2026-11-11）：**单段 `{bo}:{action}` 定型**，双段仅留只读 alias 过渡 |
| TBD-2 | `governance` 治理分期 | 本轮是否同时实现审计+组织范围（E3 Step 2）还是只做声明+白名单（Step 1） | ✅ 已拍板：**Step 1 + Step 2 同批实施**（同一 commit，`BO_ACTION_GOVERNANCE=warn` 灰度） |
| TBD-3 | `generated_schema.sql` 去留 | 保留为期望快照 vs 彻底删除、只留迁移 | 建议保留 + CI 校验（E2 方案 A） |
| TBD-4 | 菜单种子真源 | DB `menu_permissions` vs `init_menu_permissions.py` 常量 | ✅ 已拍板：**DB 为运行时真源**，脚本降级为生成器 + `--check` |
| TBD-5 | `MetaAction` 新字段命名 | `handler` / `permission` / `governance` 是否与既有 `behavior` 冲突 | 实施前在 1 个对象试解析 |
| TBD-6 | 4 服务的隐式转移是否全在 YAML | 需差集脚本证明「服务表 ⊆ YAML」 | E4 前置，禁止先删后补 |
| TBD-7 | Wave 0 未提交改动 | T2/T4 + v249/v250 是否先 commit | ✅ 已拍板：**先单独 commit 存量再开 Wave 1** |

---

## 14. 头部产品机制复核结论（2026-11-11）

> 完整论证见 `docs/specs/spec-metadata-driven-backend-research.md` §7。本节只记录**对本文档有约束力**的修正。

### 14.1 对 E1-E9 的三处修正

| 项 | 原方案 | 修正 | 原因 |
|---|---|---|---|
| **E3** | `lightweight: Optional[bool]` | 改 `governance: none \| audit \| audit_scope`（枚举，默认 `None` 待声明） | 布尔把「许可 / 前置条件 / 留痕」三件事压成一维，Step 2 必然二次迁移；Palantir Action Type 是三个正交面 |
| **E5** | 精度按 `currency.decimal_places` / `semantics.precision` 二选 | 明确优先级链：**字段 `semantics.precision` > 货币 `decimal_places` > `DEFAULT_AMOUNT_DECIMALS`** | Dataverse 的 precision 同时存在于列与货币记录，必须有确定优先级，否则两处不一致时行为随机 |
| **E8** | `handler` 仅做 dotted-path 解析 | 增加**模块命名空间白名单 + 加载期校验 + 权限配置变更审计** | Palantir 官方警告「函数编辑权限不跟随动作权限」；我们等价的攻击面是「改 YAML 即换 handler」 |

### 14.2 TBD 定型结论（已确认 2026-11-11）

- **TBD-1 → 单段定型**。双段码进 `permission_aliases` 只读过渡表，resolver 先查单段、再查 alias，禁止新增双段；过渡期结束删表。
- **TBD-2 → Step 1 + Step 2 同批**（声明 + 契约必填 + 白名单 + 审计 + 组织范围，同一 commit）；`BO_ACTION_GOVERNANCE=warn` 灰度，先影子后 enforce。
- **TBD-3 → 保留快照**；文件头标注「非运行输入」，并加一条测试断言「无运行时代码读取 `generated_schema.sql`」。
- **TBD-4 → DB 为运行时真源**，`init_menu_permissions.py` 降级为种子生成器 + `--check`。
- **TBD-7 → 先 commit**（T2/T4 + v249/v250），再开 Wave 1；否则生成器 diff 与存量改动不可分离。

### 14.3 明确不在本轮范围

**E10 MetaBundle（元数据发布包 + 环境漂移预演）**：头部四家都有这层（update set / solution / Metadata API / CDS build），
E9 的 CI 门禁只是其子集。因当前单库单环境，**本轮不做**，记为 E9 之后的 P1 候选：

```
scripts/metadata_bundle.py build
scripts/metadata_bundle.py validate --against db   # 只读预演，exit 0|1
```

同时明确**拒绝**照搬的四项：运行时改元数据、脚本式 ACL、每对象一个权限集、动作与处理器权限脱钩（详见研究 §7.4）。

---

## 15. 文件级落地清单（可执行）

> 状态：`✅` 磁盘上已存在（未提交）；`⬜` 待新增。
> 执行约束：测试只走 `python d:\filework\test.py --failed|--all|--file`（禁 pytest）；服务只走 `scripts/service_manager`（禁直起进程）；文件写入用 Write/Edit（禁 `echo >`）。

| 项 | 新增文件 | 修改文件 | 迁移 | 测试文件 | 验收命令 | 前置依赖 |
|---|---|---|---|---|---|---|
| **E1** | `scripts/sync_permission_codes.py` ⬜ | `permission_sync_service.py`（提 `derive_object_permissions`）、`check_permission_consistency.py`（+MENU 集、R5/R6）、`init_menu_permissions.py`（`--check`） | v249 / v250 ✅ | `test_permission_code_sync.py` ⬜ | `python scripts/sync_permission_codes.py --check`；`python scripts/check_permission_consistency.py` | 无（Wave 1 首项） |
| **E3** | — | `bo_action_registry.py`（`governance`/`org_scope`）、`bo_action_contract.py`、`bo_action_registrations.py`（19 条标注） | 无 | `test_bo_action_governance.py` ⬜ | `report_registry_contracts()`（`BO_ACTION_GOVERNANCE=strict`） | 无 |
| **E2** | 迁移 `v251__align_status_check.py` ⬜ | `schema_generator.py`（长度/CHECK）、`sync_schema.py`（`--against`/`--check`） | v251 ⬜（只新增） | `test_schema_single_source.py` ⬜ | `python -m meta.tools.sync_schema --diff --check` | 无 |
| **E4** | `meta/core/state_machine.py` ⬜ | `attribute_promotion_service.py:42`、`change_request_service.py:25`、`configuration_guard_service.py:38`、`purchase_order_guard_service.py:37` | 无 | `test_state_machine_single_source.py` ⬜ | 差集脚本「服务表 − YAML 边」= 0 | E2（列类型稳定后） |
| **E6** | — | `bo_api.py`（删 `_NUMBERED_OBJECTS` 等 3 常量） | 无 | `test_numbering_single_source.py` ⬜ | 6 对象编号回归 | 无 |
| **E5** | `scripts/check_rounding_single_source.py` ⬜ | `rounding.py`（`places_for`）、4 处调用点 | 无 | `test_rounding_single_source.py` ⬜ | `python scripts/check_rounding_single_source.py` | 无 |
| **E7** | `scripts/sync_menu_permissions.py` ⬜ | `bo_action_registrations.py`（`permission_required` 改读 YAML） | 无 | `test_permission_single_declaration.py` ⬜ | 三个生成器 `--check` 均 0 diff | E1、E8 |
| **E8** | `meta/services/bo_action_loader.py` ⬜、`meta/services/actions/__init__.py` ⬜ | `models.py`、`yaml_loader.py`（`parse_action`）、`bo_action_registrations.py`（legacy 白名单） | 无 | `test_bo_action_loader.py` ⬜ | 启动自检（越界/重复 → fail-fast） | E1、E3 |
| **E9** | `.github/workflows/metadata-gate.yml` ⬜、`scripts/metadata_gate.ps1` ⬜ | — | 无 | — | CI 三 job 全绿 = 本地脚本全绿 | E1/E2/E3/E5/E8 |

### 15.1 提交切分

每项一个 commit，禁止跨项混合；提交信息按 `feat(meta): E<n> <一句话>`：

```
① [pm-authorized] chore(meta): 提交存量 T2/T4 + v249/v250      ← 已拍板，Wave 1 前置
② feat(meta): E1 权限码单源生成 + 校验扩 MENU
③ feat(meta): E3 动作治理（Step 1 声明+契约 + Step 2 审计/组织范围，同一 commit）
④ feat(meta): E2 DDL 单源（长度/CHECK 渲染 + 真实库 diff）
⑤ feat(meta): E4 状态机单一派生
⑥ feat(meta): E6 取号元数据化
⑦ feat(meta): E5 金额精度优先级链
⑧ feat(meta): E8 YAML actions 启动加载（handler 白名单）
⑨ feat(meta): E7 权限点单一声明位收口
⑩ ci(meta): E9 metadata gate 三 job
```

每 Wave 末（Wave 1/2/3）必须 `python d:\filework\test.py --failed` 全绿再进下一步。

### 15.2 开工前置（已解除）

| 阻塞 | 影响 | 结论（2026-11-11 拍板） |
|---|---|---|
| TBD-1 | E1/E7 的码格式 | **单段定型**；双段仅留 alias 读过渡 |
| TBD-2 | E3 范围 | **Step 1 + Step 2 同批**，灰度 `BO_ACTION_GOVERNANCE=warn` |
| TBD-7 | 生成器 diff 与存量混叠 | **先提交** T2/T4 + v249/v250 |
| TBD-4 | E1 `--check` 的比对方向 | **DB 为运行时真源**，脚本只生成 + `--check` |

四项均已解除，唯一未动的是「① 存量 commit」这个动作本身——它受 AGENTS.md 第 6 条约束：
主工作树禁止 commit，需 worktree 或 PM 显式授权（`[pm-authorized]`）。

---

## 16. 实现方案（代码级）

> 本章是 §10 + §15 的落地版：每一步给出**改哪个文件、插入点什么、伪代码、怎么验证、怎么退**。
> 所有「新增」均已标出；复用现有函数处写明出处，避免二次造轮子。

### 16.1 实施基线（开工前 1 次）

```
python scripts/service_manager.py doctor          # 端口/服务/DB 锁
python d:\filework\test.py --failed               # 当前失败基线必须为空
python scripts/check_permission_consistency.py    # 记录 R1/R2/R3/R4 现状数值
git status --short                                # 记录未提交存量（T2/T4/v249/v250）
```

基线不干净就不开工——否则后续无法区分「我的改动引入」与「存量」。

### 16.2 通用改动协议

| 约定 | 内容 |
|---|---|
| YAML → 模型 → 契约 三段式 | 任何新字段必须同时在 `models.py`（存储）、`yaml_loader.py`（解析）、`*_contract.py`（校验）三处出现，缺一不算落地 |
| 灰度开关 | `BO_ACTION_GOVERNANCE=warn|strict`（E3）、`BO_ACTION_LOADER=on|off`（E8）、`METADATA_GATE=dry|enforce`（E9）；默认取「不破坏现状」的一侧 |
| 测试命名 | `meta/tests/test_<主题>_single_source.py`；每个文件至少含 1 个负向用例 |
| 退路 | 每个 E 单独 commit；回滚 = `git revert <sha>`，不依赖开关 |
| 禁止 | pytest 直跑、`echo >`、直连 DB 改表、`Start-Process` 起服务 |

### 16.3 E1（权限码单源 + 校验扩 MENU）

**Step 1　抽纯函数（不改行为）**

`meta/services/permission_sync_service.py`：

```python
def derive_object_permissions(obj) -> List[str]:
    """纯函数：YAML MetaObject → 权限码集合（单段）。
    规则：① 标准 CRUD 四码必出；② obj.actions 逐条 get_permission_code(obj.id)；
         ③ authorization.permissions 的值（若有）并入。去重后排序，便于 diff。
    """
def _derive_from_object(obj) -> List[str]:      # 现有私有实现
    return derive_object_permissions(obj)       # 保留旧入口，供既有调用方
```

验证：`python d:\filework\test.py --file meta/tests/test_permission_sync_service.py`（应零变化）。

**Step 2　新增生成器 `scripts/sync_permission_codes.py`**

```
--check            只读：DB 现有码 vs derive 结果，输出 missing/extra 两段，有差异 exit 1
--write            入库：仅插缺失码；对 extra 只告警不删（删码需人工）
--object <id>      限单个对象（调试）
```

伪代码：

```python
codes = {obj_id: derive_object_permissions(obj) for obj in registry.get_all().values()}
stored = {row['code'] for row in query_permissions()}
missing = {c for cs in codes.values() for c in cs} - stored
extra   = stored - set().union(*codes.values())
if args.check and (missing or extra): print_diff(); sys.exit(1)
if args.write:
    for code in sorted(missing): upsert_permission(code)   # 复用 permission_sync_service 现有入库函数
```

> 入库函数不新写 SQL：优先复用 `permission_sync_service` 内既有写库路径（`sync_all` / 单对象同步）；若只暴露批量入口，则新增 `sync_object_permissions(obj)` 包一层，**不复制 INSERT 语句**。

**Step 3　校验器扩 MENU 集合**

`scripts/check_permission_consistency.py` 追加两个规则（沿用现有 A/C/D/G 引用位框架）：

| 规则 | 断言 |
|---|---|
| R5 | `menu_permissions.required_permissions` 的每个码 ∈ DECLARED ∪ STORED |
| R6 | 有菜单但 `required_permissions` 为空 → 告警（不阻断，存量豁免表 `MENU_EMPTY_ALLOWLIST`） |

同时把 R1 口径固化在脚本注释里：**引用 ⊆ 声明 ∪ 入库**（引用方多一个都不行，入库方可多——多出的是待清理 extra）。

**Step 4　`init_menu_permissions.py --check`**

DB `menu_permissions` 是**运行时唯一真源**：启动/部署不重建菜单权限，只读模式输出「种子 vs DB」差异，`--write` 才补写缺失行。种子文件降级为**生成器**，不再参与运行期判定（TBD-4 已拍板）。

**验收**：`sync_permission_codes --check` exit 0；`check_permission_consistency` R1/R2/R3/R5 = 0；`--help` 不产生副作用。

---

### 16.4 E3（动作治理：Step 1 + Step 2 同批）

> 已拍板：Step 1 与 Step 2 在**同一个 commit** 交付。Step 1 的契约告警由 `BO_ACTION_GOVERNANCE=warn` 灰度（不阻断启动），Step 2 对未标注 action 等价 `none`（行为与改造前一致），因此「同批」不引入额外风险面。19 条注册项必须在同一批次内全部标注，不允许部分标注上线。

**Step 1　模型 + 契约**

`meta/core/bo_action_registry.py`：

```python
@dataclass
class BusinessActionMeta:
    ...
    governance: Optional[str] = None        # 'none' | 'audit' | 'audit_scope'
    org_scope: Optional[Dict[str, Any]] = None   # {'param_field': 'org_id'}
```

`register(...)` 末尾追加同名两参数并透传；`list_schemas()` 输出 `governance`（OpenAPI 可观测）。

`meta/core/bo_action_contract.py`：

```python
GOVERNANCE_LEVELS = ('none', 'audit', 'audit_scope')

def _check_governance(meta) -> List[str]:
    gov = getattr(meta, 'governance', None)
    if gov is None:
        return [] if _GOVERNANCE_MODE == 'warn' else ['governance 未声明（warn 灰度中）']
    if gov not in GOVERNANCE_LEVELS:
        return [f"governance 非法：{gov!r}（允许 {GOVERNANCE_LEVELS}）"]
    errs = []
    if gov == 'audit_scope':
        scope = getattr(meta, 'org_scope', None) or {}
        pf = scope.get('param_field')
        if not pf: errs.append("audit_scope 必须声明 org_scope.param_field")
        else:
            props = (getattr(meta, 'input_schema', None) or {}).get('properties') or {}
            if pf not in props: errs.append(f"org_scope.param_field={pf!r} 不在 input_schema.properties")
    return errs
```

在 `validate_action_meta()` 末尾 `errors.extend(_check_governance(meta))`；`_GOVERNANCE_MODE = os.getenv('BO_ACTION_GOVERNANCE', 'warn').lower()`。

**Step 1 验收**：`report_registry_contracts(level='error')` 在 19 条全部标注后 0 违规；故意写错枚举 → 违规清单含 action_id。

**Step 2　`call()` 接入（影子期先只写日志）**

> 「影子期」= 先接审计与范围判定、`BO_ACTION_GOVERNANCE=warn` 下只记录不拒绝；确认一周无异常后再把 `audit_scope` 的拒绝从 warn 提升为 enforce（一次开关切换，不改代码）。

`BoActionRegistry.call()` 在「权限检查之后、`check_preconditions` 之前」插入：

```python
gov = getattr(meta, 'governance', None) or 'none'
enforce = os.getenv('BO_ACTION_GOVERNANCE', 'warn').lower() == 'strict'
audit_ctx = None
if gov in ('audit', 'audit_scope'):
    audit_ctx = {
        'action_id': meta.action_id,
        'object_type': meta.object_type,
        'params_hash': hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16],
        'user_id': (context or {}).get('user_id'),
        'trace_id': (context or {}).get('trace_id') or uuid.uuid4().hex,
        'status': 'denied',
    }
if gov == 'audit_scope':
    err = _check_org_scope(meta, params, context)     # 委托 OrgScopeService.visible_org_ids
    if err:
        _write_action_audit(audit_ctx)               # status='denied' 先落审计
        if enforce:
            return {'success': False, 'data': None, 'message': err, 'code': 'ORG_SCOPE_DENIED'}
        logger.warning("[governance] warn 模式放行：%s %s", meta.action_id, err)
# ... handler 执行成功把 audit_ctx['status'] 改 'ok' / 异常改 'error'
finally:
    if audit_ctx: _write_action_audit(audit_ctx)
```

> 两个开关不要混用：`_GOVERNANCE_MODE`（契约层，决定「未声明」是否报错）与 `enforce`（运行层，决定「范围不符」是否拒绝）读同一环境变量、不同取值域——`warn` 两者都放行，`strict` 两者都拦截。

`_write_action_audit(entry)` 放 `meta/services/action_audit.py`：

```python
def write_action_audit(entry: dict) -> None:
    """复用 AuditService.log()；dedupe key = (trace_id, action_id)。
       data_source 从 entry 取（调用方塞入），缺席则 logger.warning 后跳过——审计不得阻断业务。"""
```

落 `audit_logs` 时：`object_type=meta.object_type`、`object_id=params.get(<主键字段>, 0)`（该列 NOT NULL，缺省 0）、`action=action_id`、`status=entry['status']`、`extra_data={'params_hash': ...}`、`trace_id` 原样。

**Step 2 验收**：
- 审计：调用一个 `audit` action → `audit_logs` 新增 1 行，`trace_id` 与请求一致；同一 `trace_id` 重放 → 不新增（dedupe 生效）。
- 范围：伪造 `param_field` 指向不可见组织 → `code=ORG_SCOPE_DENIED`，且已落审计（status=denied）。
- 回归：`none` 类 action 的行为、耗时与改造前一致。

**回滚**：`BO_ACTION_GOVERNANCE=warn` 时 Step 1 不阻断；Step 2 未标注 == `none`，等价旧行为。

---

### 16.5 E2（DDL 单源）

**Step 1　类型渲染参数化**

`meta/core/schema_generator.py` L31 的静态字典改为函数：

```python
def _sql_type(field) -> str:
    if field.type is FieldType.STRING:
        return f"VARCHAR({getattr(field.semantics, 'max_length', None) or 200})"
    return FIELD_TYPE_TO_SQL[field.type]

def _sql_check(field) -> Optional[str]:
    vals = field.enum_values or []
    if not vals or len(vals) > 50: return None      # 大枚举不入 DDL，走值帮助
    quoted = ", ".join("'" + str(v).replace("'", "''") + "'" for v in vals)
    return f"CHECK ({field.column} IN ({quoted}))"
```

生成列时把 `_sql_check` 结果拼在列定义后（SQLite 支持列级 CHECK）。

**Step 2　`sync_schema` 比对真实 DB**

`meta/tools/sync_schema.py` 增 `--against {db,snapshot}`：

```python
def _db_schema(conn) -> Dict[str, dict]:
    # {table: {'columns': {name: (type, notnull, dflt)}, 'sql': <sqlite_master.sql>}}
    # 来源：PRAGMA table_info(t) + SELECT sql FROM sqlite_master WHERE type='table'
```

`--check`：生成 DDL（内存）vs `_db_schema()` → 差异按「列缺失 / 类型不符 / CHECK 缺失」三分类打印，exit 1。
默认**只打印不执行**；执行必须显式 `--apply`（且仅限 ADD COLUMN / CHECK 补齐两类，DROP 一律拒绝）。

**Step 3　迁移 `v251__align_status_check.py`**

只处理「列已存在、只缺 CHECK」的表（receipt / sales_order 等）。SQLite 无 `ALTER ADD CONSTRAINT`，统一走重建：

```
CREATE TABLE <t>__new (... 同列定义 + CHECK ...);
INSERT INTO <t>__new SELECT * FROM <t>;
DROP TABLE <t>; ALTER TABLE <t>__new RENAME TO <t>;
（索引/触发器按 sqlite_master 里原 DDL 重建）
```

迁移必须幂等：开头 `PRAGMA table_info` 判断 CHECK 是否已存在。

**验收**：`--check` exit 0；迁移在 v249/v250 之后顺序执行成功；`test_schema_single_source.py` 覆盖「枚举列 CHECK 存在 / 长度超限被 CHECK 拦截」两种负向。

---

### 16.6 E4（状态机单一派生）

新增 `meta/core/state_machine.py`（纯读，不缓存跨请求的 DB 连接）：

```python
def _edges(object_id: str) -> Dict[Tuple[str, str], Optional[str]]:
    obj = registry.get(object_id)              # MetaRegistry.get
    return {(t.from_state, t.to_state): t.action_ref for t in obj.get_state_transitions()}

def allowed_transitions(object_id, from_state=None) -> List[str]
def can_transition(object_id, src, dst) -> bool
def transition_action(object_id, src, dst) -> Optional[str]   # 无声明边返回 None
```

缓存：`@lru_cache(maxsize=256)` 按 `(object_id, len(edges))` 失效即可（schema 运行期不变）；测试前 `_edges.cache_clear()`。

4 个服务的替换（只删本地 dict，函数签名不变）：
- `attribute_promotion_service.py:42` → `can_transition(...)`
- `change_request_service.py:25` → `allowed_transitions(...)`
- `configuration_guard_service.py:38` → `transition_action(...)`
- `purchase_order_guard_service.py:37` → `can_transition(...)`

**验收**：4 个服务原有测试全绿；`grep -n "transitions *=" meta/services/` 仅剩注释；新增「服务表 − YAML 边」差集脚本 = 0。

---

### 16.7 E6（取号元数据化）

`meta/api/bo_api.py` L205-220 三常量改为函数：

```python
def _numbered_objects() -> List[str]:
    return [o.id for o in registry.get_all().values() if getattr(o, 'numbering', None)]

def _numbering_spec(object_id: str) -> Dict[str, Any]:
    obj = registry.get(object_id)
    spec = getattr(obj, 'numbering', None) or {}
    # 键：no_field / date_field / type_table；标签回落 obj.name
    # 缺 no_field → logger.warning 并返回 {}（调用方走旧逻辑，不猜测）
```

调用点改为 `for object_id in _numbered_objects()`，标签 `spec.get('label') or obj.name`。

**验收**：6 个编号对象（receipt / sales_order / …）各建 1 条单，编号串与改造前逐字符一致。

---

### 16.8 E5（精度优先级链）

`meta/core/rounding.py` 新增（保持 core 不访问 DB）：

```python
def resolve_places(object_id: str, field_id: str | None = None,
                   currency_decimals: int | None = None) -> Tuple[int, str]:
    """返回 (places, source)；source ∈ {'field','currency','default'}。
       优先级：field.semantics.precision > currency_decimals > DEFAULT_AMOUNT_DECIMALS。"""
def places_for(object_id, field_id=None, currency_decimals=None) -> int:
    return resolve_places(...)[0]
```

字段精度取自行内注册表（`registry.get(object_id)` → 字段 `semantics.precision`），**不查库**；`currency_decimals` 仍由调用方查货币表后传入（保持现有职责划分）。

4 处替换（见 §10 E5），SQL 侧：

```python
places = places_for(obj, field, currency_decimals)
sql = f"ROUND(x, {int(places)})"     # int() 白名单，禁止直接插字符串
```

`scripts/check_rounding_single_source.py`：扫描 `meta/` 下 `quantize(` / `ROUND(`，命中不在 allowlist（currency 服务、迁移）即 exit 1。

**验收**：三档优先级用例 + 快照比对（billing_due_list 逐行一致）。

---

### 16.9 E8（YAML actions 启动加载）

`MetaAction` 三字段（`models.py:688` 内追加）：`handler: str = ""`、`permission: str = ""`、`governance: Optional[str] = None`；`parse_action()`（`yaml_loader.py:1905`）同名解析。

新增 `meta/services/actions/__init__.py`（handler 唯一允许的包）与 `meta/services/bo_action_loader.py`：

```python
ALLOWED_PREFIX = 'meta.services.actions.'

def load_actions(registry=None) -> int:
    for obj in meta_registry.get_all().values():
        for act in getattr(obj, 'actions', []) or []:
            if not act.handler: continue                      # 纯 UI 动作跳过
            action_id = f"{obj.id}.{act.id}"
            if registry.has(action_id) and action_id not in LEGACY_LITERAL_ACTIONS:
                raise ActionContractError(f"重复注册：{action_id}")
            mod_name, fn_name = act.handler.rsplit('.', 1)[0], act.handler.rsplit('.', 1)[1]
            if not mod_name.startswith(ALLOWED_PREFIX):
                raise ActionContractError(f"handler 越界：{act.handler}")
            fn = getattr(importlib.import_module(mod_name), fn_name)   # 不做 fallback
            registry.register(action_id=action_id, handler=fn, object_type=obj.id,
                              permission_required=act.permission or act.get_permission_code(obj.id),
                              governance=act.governance,
                              preconditions=(act.behavior.preconditions if act.behavior else None))
    return count
```

启动接线：`server.create_app()` 与 `ApplicationBuilder.with_bo_actions()` 均在 `register_all_bo_actions()` **之后**调用 `load_actions()`；`BO_ACTION_LOADER=off` 时跳过。

权限变更审计：loader 加载完成后对比上一份快照文件 `.runtime/action_registry_snapshot.json`（action_id → permission/governance），有差异写 `audit_logs(action='permission_config_change', extra_data={'diff': ...})`，然后覆盖快照。

**验收**：正常加载 / 重复 id / 越界 handler / 权限变更四条用例；`--` 启动自检失败必须让服务起不来（不是告警）。

---

### 16.10 E7（单一声明位收口）

人工只写两处：`authorization.permissions`（运行时）与 `actions[].permission`（入库/菜单/OpenAPI 同源）。

生成器三个，均支持 `--check`（CI 用）：
1. `sync_permission_codes.py`（E1）→ `permissions`
2. `sync_menu_permissions.py`（新增）→ `menu_permissions.required_permissions`
3. OpenAPI 由 `registry.list_schemas()` 实时输出（不落文件）

`bo_action_registrations.py` 的 `permission_required` 改为「读 YAML（经 E8 loader）；legacy 白名单继续用字面量」。

**验收**：三个生成器 `--check` 均 0 diff；随机改一个 YAML 权限值 → 三者同时报 diff（证明同源）。

---

### 16.11 E9（门禁）

`.github/workflows/metadata-gate.yml` 三 job，共用步骤：

```yaml
- uses: actions/setup-python@v5
  with: { python-version: '3.11' }
- run: pip install -r requirements.txt
- run: python meta/tests/shared/bootstrap_ci_db.py   # 用现成 test helper 建临时库
```

| job | 命令 | 失败含义 |
|---|---|---|
| `permission-gate` | `python scripts/sync_permission_codes.py --check` + `python scripts/check_permission_consistency.py` | 声明/入库/引用三方漂移 |
| `schema-gate` | `python -m meta.tools.sync_schema --diff --against db --check` | DDL 与 YAML 不一致 |
| `action-contract-gate` | `BO_ACTION_GOVERNANCE=strict python -m meta.core.bo_action_contract`（或等价 `-c` 调用 `assert_registry_contracts`）+ loader 自检 | 动作治理/契约违规 |

本地等价：`scripts/metadata_gate.ps1`（顺序跑三条，`METADATA_GATE=dry` 只打印不 exit）。

**验收**：故意注入 1 处漂移 → 对应 job 红、另两个绿；恢复后三绿。

### 16.12 验收总口径

| 层 | 命令 | 通过标准 |
|---|---|---|
| 单测 | `python d:\filework\test.py --failed` | 0 failed |
| 权限 | `sync_permission_codes --check` + `check_permission_consistency` | exit 0，R1/R2/R3/R5=0 |
| DDL | `sync_schema --diff --check` | exit 0 |
| 动作 | `BO_ACTION_GOVERNANCE=strict` + loader 自检 | 启动成功、0 违规 |
| 端到端 | 3006 单据新建（customer_invoice） | 非管理员可见按钮且 200，不再 403 |