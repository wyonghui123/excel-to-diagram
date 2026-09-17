# Org 人员维度 + 权限体系迁移方案（Spec）

> 文档编号: 14 | 状态: 草案 | 更新: 2026-07-26
> 主题: 将 org 接入权限体系；**默认不加 org 字段**（路线 A：数据范围走业务维度，org 仅作为人员维度）；将现有 `user→user_group→role` 授权体系平滑迁移
> 前置: `09_unified_permission_architecture.md` / `10_unified_permission_final.md` / `13_organization_model_integration.md`
> 关联: §13.6.5 组织级授权+角色聚合 / §13.7 分阶段路线

---

## 1. 背景与范围

### 1.1 背景
13 号文档完成组织模型目标设计（org / position / person / user / org_relationship）。本文档回答落地问题：
1. **org 是否要作为"管理维度"给对象加字段** —— 结论：默认**不加**，见 §2/§3。
2. 现有 `user→user_group→role` 授权链**如何平滑迁移**到 org 人员模型。

### 1.2 范围
- 最新决策：**默认路线 A（不加 org 字段）** 与演进路线 B 的判断标准。
- 一期最小模型（position 后置）。
- 存量权限数据分阶段迁移（双轨对账与回滚）。

---

## 2. 核心决策：默认路线 A——不加 org 字段

> **决策（2026-07-26，经供应链/采购/库存用例推演）**：当组织树与业务维度树**同构/层层对应**时，数据可见范围**完全可由业务维度树表达，org 字段是冗余**。默认**所有对象都不加 org 字段**，org 只作为"用户归属 + 人员管理"的维度（用户挂到哪些 org），数据范围全走现有业务维度（domain/sub_domain/service_module）+ `inherit_children`。

### 2.1 为何成立（同构推导）
```
业务维度树                            org 树（组织）
供应链云(domain)         ↔           供应链云产品部门
 └─ 采购供应(sub_domain) ↔           采购供应组
     ├─ 采购管理  ─────────              ├─ 采购管理小组
     └─ 库存管理  ─────────              └─ 库存管理小组
```
- 用户A/采购管理小组 可见 = 采购管理(业务维度 service_module) 及下游
- 用户B/库存管理小组 可见 = 库存管理
- 用户C/采购供应组  可管理 = 采购供应(业务维度 sub_domain) 及下级（`inherit_children=true`）
- **上述全部用"业务维度 + inherit_children"实现，org 字段零参与。**

### 2.2 路线 A 下 org 扮演的角色
- org 只表达**"用户属于哪个组织节点"**（`user_org_assignment`），决定：① 用户的 org 祖先链 → `org_role` 授权继承（§13.6.5）；② 人事归属。
- **不表达**"业务数据行属于哪个组织"——数据归属由业务维度树自带层级承载。

### 2.3 默认不加的对象
`product/version/domain/sub_domain/service_module/business_object`（平台元模型）及未来应用业务 BO 的定义：**均不加 `owning_org_id`**。

### 2.4 平台能力 vs 应用层（org 的未来落点，关键定位）
本项目当前构建的是**平台能力（元模型）**：product→version→domain→sub_domain→service_module→**business_object 定义**。它们自身是"抽象/分类"，数据行通常**无需** org（§2.1/§2.3）。

**org 数据权限的未来落点 = 应用层**：后续在平台上**新增的具体业务对象 schema（如 sales_order，及其数据行/instance）**，其数据行**天然归属某组织**，才需要 `owning_org_id`。

> 平台提供的是**"管理维度接入能力"**：未来应用**按需声明**即可——
> ① 在新应用 BO schema 字段加 `owning_org_id`(direct)；② 登记 `dimension_object_mapping(dimension_code: org)`；③ 复用 `role_dimension_scopes(org)` 配角色数据权限。
> **平台本身不改**，新增应用按需声明接入 org。"未来扩大业务模型就需要 org" = 未来新增应用层业务对象的 instance 需要 org，而**不是**平台元模型（含 service_module）需要。

---

## 3. 何时才需要 org 字段（路线 B，演进判定）

> 路线 A 的成立前提是"org 树与业务维度树**同构**"。当前提不成立、或未来应用层业务对象的 instance 需按组织隔离时，进入路线 B。**org 字段加在应用层 instance 数据行，而非平台元模型。**

### 3.1 触发条件（满足任一才考虑加）
1. **应用层 instance 按组织隔离**：新增业务对象（sales_order 等）的数据行天然归属某组织，需按 org 切分可见/管理（几乎所有真实单据类 BO 都会命中）。
2. **同层数据按组织拆分**：未来应用内同一 BO 的记录分给不同 org（如"一部分归采购管理小组、一部分归库存管理小组"）。
3. **org 树与业务树不同构**：某子领域/服务模块在 org 树上横跨多个部门，或 org 层级与业务层级无法一一对应。
4. **外部企业(客商)数据隔离**：客户/供应商的单据需按其外部 org 隔离（§13.5.2d 外部用户边界）。

### 3.2 触发时才的最小加标方式（落点 = 应用层 instance）
- **加在应用层新业务对象 schema 上**（direct 打标）：
```
# [未来] 新增 sales_order.yaml（应用层业务对象）
sales_order.owning_org_id = 该采购订单归属的 org（如 采购管理小组 / 库存管理小组）
```
- **不做"平台逐层加列"**：平台元模型（service_module / business_object）自身**不因 org 被打标**；如需其组织可见性，用 `dimension_org_mapping`（维度值↔org 对齐）表达，而非加列。
- 上层（domain / sub_domain ↔ org）对应**不落字段**，由 org 树 `parent_id` + `inherit_children` 推导（例：选 org=采购供应组，inherit 含采购管理小组、库存管理小组）。
- 仅当"业务树与 org 树**不同构**"（某子领域横跨两 org）才引入轻量 `dimension_org_mapping`，仍**不是给对象加列**。

### 3.3 路线 B 的接入（复用平台现有维度能力）
```yaml
# dimension_object_mapping.yaml（仅 route B 启用，登记应用层 BO）
- dimension_code: org
  dimension_type: generic
  value_table: org
  value_field: id
  applies_to:
    - bo: sales_order       # 未来应用层业务对象，自身带 owning_org_id
      field: owning_org_id
      filter_type: direct
```
角色范围：`role_dimension_scopes(dimension_code='org', dimension_values=[org节点], inherit_children=true)` —— **复用现有数据权限配置入口，平台不改**。
数据评估：业务维度 AND 组织维度（combination_policy: AND）。

---

## 4. 权限评估（路线 A 为主，附带路线 B 扩展）

### 4.1 路线 A（默认）：数据范围 = 业务维度
```
可执行(user, action, 数据行) ⇐ ∃ role ∈ 用户角色集(任职 org 祖先链的 org_role[additive]):
      role.permission 含 action
      AND 数据行命中 role.dimension_scope(业务维度 domain/sub_domain/service_module, 含 inherit_children)
```
### 4.2 路线 B（演进叠加）：业务维度 AND 组织维度
- 在 4.1 基础上追加 `AND 数据行 owning_org_id ∈ 用户组织维度范围`。

### 4.3 优先级（对齐 §13 继承现有）
| 优先级 | 来源 | 行为 |
|--------|------|------|
| 高 | 手动意图 `granted=false`(FR-013) | deny 强制排除 |
| 高 | 手动意图 `granted=true`(FR-013) | grant 强制放行 |
| 中 | 任职 org 祖先链 `org_role`（additive）| allow |
| 中 | position 角色（二期）| additive |
| 低 | 对象级默认 OWD(FR-012) / 默认 deny | 兜底 |

--- 非 deny 全为加法，对齐 SAP PFCG / Workday security group additive。

---

## 5. 迁移方案（分阶段 + 双轨对账）

### 5.0 前提判断
现网授权**已是单一 `user→user_group→role` 路径**（permission_service 明确移除 user_roles 直连；有 drop_user_roles_table 迁移）。故角色链（role/role_permission/role_menus/role_dimension_scopes）**全部复用**，迁移焦点在"语义混乱的 user_group 层归位"。

### Phase 0 — 冻结与快照（不改行为）
- 全量备份：roles / role_permissions / role_menus / role_dimension_scopes / user_groups / group_roles / user_group_members / group_data_permissions。
- 生成"迁移前快照"，供回滚与对账基线。

### Phase 1 — 建 org 骨架（干净新增，与存量隔离）
- 建 `org`（parent_id 主层级 + org_type + org_function）、`user_org_assignment`、`org_role` 表/YAML。
- 将企业真实组织架构（供应链云部门→采购供应组→采购管理/库存管理小组）铺入 org 树——**不涉及存量权限**，最干净的第一步。

### Phase 2 — 业务型 user_group 树迁入 org（启发式）
- 遍历 `user_groups`（排除 `personal_group_user_*`），结构属性映射到 org：name/code→org；parent→org.parent_id；按关键词/人工判定 org_type。
- 归位决策：能固化为部门/团队 → org；临时协作/跨组织 → 降级"临时聚合 user_group"（§13.5.2a4）。

### Phase 3 — 授角色关系迁移（group_roles → org_role）
- 业务组角色 → `org_role`（org 级，inherit_children=true，天然支持"父组 read 兜底 + 子组管理"）。
- **personal_group 角色先保全**：建用户默认 position（或兜底 job.default_role_set），转移个人组角色 → 再删 personal_group。**最大数据安全点。**

### Phase 4 — 成员映射 + 切换
- `user_group_members` → `user_org_assignment(org=映射组, position=可空, is_primary 按行政归属)`。
- `group_data_permissions` → 业务维度数据范围合并（**默认不进 org 维度**，路线 A）。
- `derivation_pipeline` 加"org 祖先链角色聚合"→ 产出 `role_effective_intents`。
- **切换入口**：`permission_service.get_user_permissions/get_user_roles` 改为经新模型解析，**接口签名不变**。

### 5.1 双轨对账（线上可用 + 可回滚）
- feature flag（复用 `PERMISSION_FLAG_*`）控制授权来源：OFF=旧 `user→group→role`；ON=新 `任职→org_role→role`。
- 过渡期对账：断言同一 user 新旧两套角色/权限集**完全一致**，不一致报警 → 修正映射再切。
- **重点告警**：
  - 旧 user_group 默认不向上继承、新 org 默认祖先链继承 → 可能**权限放大**，对账 `diff` 单列"新增继承角色"人工确认。
  - personal_group 删除前必须已迁移角色，否则角色丢失。

---

## 6. 风险与决策记录

| # | 风险/决策 | 应对 |
|---|-----------|------|
| 1 | 默认路线 A 需不断验证"同构"成立 | 每个新 use case 先走"业务维度能否覆盖"，覆盖即 A；不覆盖升级路线 B |
| 2 | 父继承导致权限意外放大 | 对账 `diff` 单列新继承角色，人工确认后切全域 |
| 3 | personal_group 角色丢失 | 必须先迁移再删除，快照可回滚 |
| 4 | position 后置阶段缺失 | 一期全 org_role + 业务维度覆盖供应链用例；position 二期叠加不破坏一期 |
| 5 | route B org 落点选错对象 | org 字段加在**应用层新业务对象的 instance 数据行**，平台元模型(含 service_module)**不因 org 打标**；平台层组织可见性用 dimension_org_mapping |

---

## 7. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-26 | AI Assistant | 创建：org 接入 + 权限迁移。**默认路线 A：不加 org 字段，数据范围走业务维度，org 仅作人员维度**；路线 B 仅在不同构/按组织切同层数据时引入；Phase 0~4 + 双轨对账 |
| 2026-07-26 | AI Assistant | 迭代2：厘清**平台能力 vs 应用层**——org 数据权限落点 = 未来应用层新业务对象（如 sales_order）的 instance 数据行，平台元模型(含 service_module)**不因 org 打标**；平台提供"管理维度接入能力"(dimension_object_mapping + role_dimension_scopes)，新增应用按需声明接入(§2.4/§3) |