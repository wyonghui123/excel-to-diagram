# Spec 20: 维度范围业务键锚定 (Dimension Scope Business Key)

> 状态: Implemented (核心链路) | 日期: 2026-09-06, 验收: 2026-09-11 | 前置: Spec 16 (role→permission_set 迁移), Spec 08 (wildcard/exclude)
> 关联代码: `meta/services/dimension_scope_engine.py`, `meta/core/derivation_pipeline.py`, `meta/api/permission_set_dimension_scope_api.py`, `meta/migrations/v085__add_bizkey_code_indexes.py`

---

## 1. 背景与问题

### 1.1 用户场景

管理员为「供应链云」领域配置编辑权限集的数据范围：

```
产品  include [A, B, C]     inherit_children=1
版本  (空)                   —
领域  include [供应链云]     inherit_children=1
```

期望语义：**拥有该权限集的用户可访问 A/B/C 三个产品下所有版本的「供应链云」领域及其全部子对象**。产品版本升级（新建版本，供应链云领域以相同业务编码继续存在）后，**权限自动覆盖新版本，无需批量更新权限集**。

### 1.2 现状缺陷（已验证）

| # | 缺陷 | 证据 |
|---|------|------|
| D1 | `dimension_values` 只支持数字 ID。字符串值被 `dimension_scope_engine.py:355` 的 `isdigit()` 过滤**静默丢弃** → 该维度不参与过滤 → **fail-open（权限放大）** | 代码实测 |
| D2 | 即使解析成 ID，`derivation_pipeline` 在 derive 时刻把 `derive_data_conditions` 生成的 SQL（含数字 ID 快照）物化为 RAW 字符串存入 `permission_set_effective_intents`。**新版本/新域创建后快照过期**，权限不覆盖新对象（仅 wildcard 例外，P5 修复 2026-07-26） | `derivation_pipeline.py:537-541,583` |
| D3 | 管理员在 search help 中选择的是「A@v01 下的供应链云」实例，但落库的只有该实例 ID，跨版本语义丢失 | 配置流程实测 |
| D4 | 每次版本升级需手工批量更新所有相关权限集的 `dimension_values` | 用户痛点本源 |

### 1.3 业务键基础设施（已验证，可直接复用）

| 事实 | 证据 |
|------|------|
| domain/BO 的 code 跨版本稳定复用 | DB 实测：`BO_SUPPLIER` 跨 4 版本；多个 domain code 跨 3-4 版本 |
| 唯一约束为 `(version_id, code)`，跨版本允许同 code | `domain.yaml` indexes |
| 导入链路以 `(code, version_id)` 联合查找，不会跨版本撞车 | `import_export_service.py:8134 _find_by_key` |
| 版本→领域 **不级联**（`cascade_delete: false`），新版本下的领域为显式创建且沿用业务编码 | `version.yaml:461` |
| 维度链 `product → version → domain → sub_domain` 的 chain 条件生成本身就是嵌套子查询风格 | `_build_chain_condition` |

---

## 2. 目标 / 非目标

### 目标

- G1: `dimension_values` 支持**业务键（code 字符串）**作为锚点，运行时解析为该维度当前全部同名实例（跨所有版本）。
- G2: **新版本/新域创建后权限自动生效**，无需 re-derive、无需批量更新权限集（子查询动态化）。
- G3: 解析失败（业务键 0 命中）时 **fail-closed**（该维度生成 `1=0`，绝不退化为不过滤）。
- G4: 存量数字 ID 配置行为**完全不变**（零迁移）。
- G5: 提供特性开关，可一键禁用（用户安全规范）。

### 非目标

- N1: 不引入「读/写分离的数据范围」（scope 对该权限集持有的所有 action 通用生效，现状即如此；用户配置中的「双向/read」属于功能权限层，不在本 Spec 范围）。
- N2: 不做跨产品限定语法（如 `PRODUCT_A/SCM`）——维度间 AND 交集已提供产品约束；列为 Phase 2 备选。
- N3: 不修改 `permission_set_effective_intents` 的存储结构（复用 RAW SQL 通道）。
- N4: 菜单推荐 / 权限推荐（`derive_recommended_menus` / `derive_permissions`）继续用 ID 快照，不动态化（属建议性质，re-derive 即刷新）。

---

## 3. 术语

| 术语 | 定义 |
|------|------|
| 业务键 (business key) | 实体的 `code` 字段值，如 `SCM`；在 `(version_id, code)` 内唯一，跨版本可复用 |
| 锚点 (anchor) | dimension_values 中的字符串元素，运行时解析为维度实例集合 |
| ID 快照 | derive 时刻解析出的数字 ID 固化到 SQL 字符串（现状行为，导致 G2 缺陷） |
| 动态子查询 | 生成的 SQL 中以 `IN (SELECT id FROM <table> WHERE code IN (...))` 表达锚点，每次执行实时解析 |
| fail-closed | 业务键解析 0 命中时该维度生成 `1=0`（不可见），并记录告警 |

---

## 4. 方案设计

### 4.1 核心：锚点 → 动态子查询（而非 ID 快照）

`dimension_values` 解析规则（`expand_dimension_values` 内）：

```
数字字符串        → 直接 ID（现状不变）
'*'              → wildcard（现状不变）
非数字字符串      → 业务键锚点（本 Spec 新增）
```

引擎内部新增解析结果维度 `key_anchors[dim_code] = set(codes)`，与现有 `expanded[dim_code] = set(ids)` 并行存在。

**生成资源过滤 SQL 时**（`derive_data_conditions`），维度值的 SQL 表达统一为：

```sql
-- 纯数字（现状）
<field> IN (64)

-- 纯业务键（新增）
<field> IN (SELECT id FROM domains WHERE code IN ('SCM'))

-- 混合（统一为一个子查询）
<field> IN (SELECT id FROM domains WHERE id IN (64) OR code IN ('SCM'))
```

**inherit_children 向下展开**：以锚点子查询为 chain 起点构造嵌套子查询（与 `_build_chain_condition` 现有风格同构）：

```sql
-- domain 锚点 SCM → sub_domain 条件（动态）
sub_domain_id IN (
  SELECT id FROM sub_domains
  WHERE domain_id IN (SELECT id FROM domains WHERE code IN ('SCM'))
)
```

**关键效果**：SQL 字符串本身不含易变 ID，经 `derivation_pipeline` 物化为 RAW intent 后，**每次查询执行时实时解析** → 新版本新建 domain(code=SCM) 后自动命中 → **G2 达成，无需 re-derive**。

### 4.2 fail-closed 语义（G3）

| 场景 | 行为 |
|------|------|
| 锚点解析命中 ≥1 | 正常生成子查询条件 |
| 锚点解析命中 0（拼错/对象未建） | **该维度生成 `1=0`** + `logger.warning`（含 permission_set_id、dim_code、codes）+ 写审计事件（`audit_async_queue` 现有通道，type=`dim_scope_bizkey_unresolved`） |
| 同维度混合（数字有效 + 锚点失败） | **整维度 `1=0`**（严格模式；避免部分成功的歧义授权），warning 同上 |
| 未配置该维度 | 不限制（现状不变，与「配置了但失败」严格区分） |

> 设计依据：用户既定原则「scopeCode 失败必须中止，严禁回退到全量/静默放大」。现状 D1 的 fail-open 恰是要消灭的缺陷。

### 4.3 特性开关（G5）

- 环境变量 `DIM_SCOPE_BIZKEY_ENABLED`，默认 `true`。
- **OFF 行为**：字符串锚点不做解析，该维度生成 `1=0`（fail-closed，而非历史的 fail-open）。
- 开关读取集中于 `dimension_scope_engine` 单点，热生效（每请求读取 env，与现有 TESTING 判断风格一致）。

### 4.4 各消费路径影响矩阵

| 消费路径 | 处理 |
|----------|------|
| `derive_data_conditions`（核心权限 SQL） | 子查询动态化（4.1） |
| `derivation_pipeline` 物化 intents | 零改动（RAW SQL 通道天然兼容子查询字符串） |
| `IntentScopeAdapter` 消费 RAW | 零改动（直接拼接，实施时以集成测试验证） |
| `expand_dimension_values` 的 ID 集合输出（菜单/权限推荐） | 锚点在解析时同步解析为当刻 ID 快照（读路径一次 `code IN` 查询），推荐类消费不变 |
| wildcard / exclude / `_has_explicit_include_for_dim` 笛卡尔语义 | 零改动；exclude 仍只对维度自身生效 |
| `get_wildcard_dims` | 零改动（锚点 ≠ wildcard） |

### 4.5 后端改动清单

| 文件 | 改动 |
|------|------|
| `meta/services/dimension_scope_engine.py` | ① `expand_dimension_values`：字符串分支解析锚点，产出 `key_anchors`；② 维度值 SQL 表达函数 `_dim_value_sql(dim, ids, codes)`；③ `derive_data_conditions` 各 binding 生成点（direct/fk/chain/fk_expanded）统一走 `_dim_value_sql`；④ fail-closed 判定与告警；⑤ 开关 |
| `meta/api/permission_set_dimension_scope_api.py` | 保存时校验：字符串锚点做存在性**预检**（warning 不阻塞——允许先配权限集后建对象）；新增 resolve 预览端点 |
| 新迁移 `meta/migrations/v0XX_bizkey_index/` | 为 `domains/sub_domains/products/versions` 补 `code` 单列索引（现有唯一索引 `(version_id, code)` 最左前缀不匹配纯 code 查询；数据量小但索引廉价） |
| 审计 | 新增 `dim_scope_bizkey_unresolved` 事件类型 |

新增 API（运维/前端自查）：

```
POST /api/v1/permission-sets/{id}/dimension-scopes/resolve-preview
→ { "domain": { "SCM": { "resolved_count": 3, "instances": [{"id":64,"version":"v01","product":"A"}, ...] },
               "SCM_TYPO": { "resolved_count": 0, "warning": "unresolved" } } }
```

### 4.6 前端改动（最小闭环）

| 位置 | 改动 |
|------|------|
| 权限集编辑 · 数据范围 · 维度值选择器 | 选定实例后同时取到 `code`；对声明 business_key 的维度提供「跨版本（业务键）/ 仅此实例（ID）」存储切换，**默认业务键**；业务键模式显示提示「跨所有版本的同编码对象自动生效」 |
| 维度值回显 | 数字 → `ID 64`；字符串 → `SCM（供应链云 · 当前命中 3 个实例）`（数据来自 resolve-preview） |
| resolve-preview 失败项 | 红色警示 `未解析到实例` |

### 4.7 配置示例（目标态）

```json
// permission_set_dimension_scopes
[
  {"dimension_code": "product", "scope_mode": "include", "dimension_values": [101, 102, 103], "inherit_children": 1},
  {"dimension_code": "domain",  "scope_mode": "include", "dimension_values": ["SCM"], "inherit_children": 1}
]
// version 不配置 → 不限制（现状语义）
```

---

## 5. 兼容性

- 存量数字 ID：代码路径不变（T4 实测存量 `vals=[64]`）→ 零迁移。
- 存量字符串值：现状被静默忽略（fail-open）。上线后这些 scope 变为「解析或 fail-closed」——当前库内**无**字符串存量（已验证），无实际影响。
- wildcard / exclude / 笛卡尔保留语义：不受影响。

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| 跨产品同名 code 误授权 | 中 | 维度间 AND 交集天然收窄（配置 product include 即约束）；resolve-preview 暴露命中实例；Phase 2 预留 `PRODUCT_CODE/KEY` 限定语法 |
| RAW SQL 子查询在 IntentScopeAdapter 拼接不兼容 | 中 | 集成测试前置验证；拼接点已确认为直接透传，异常时开关兜底 |
| 锚点拼错 → 用户突然全不可见（fail-closed） | 中 | 保存时 warning 预检 + resolve-preview 红色提示 + 告警日志；属安全侧偏好（宁不可见勿越权） |
| 子查询性能 | 低 | code 索引迁移（4.5）；维度表 ≤ 数千行 |
| chain 嵌套子查询与 fk_expanded 的 `_expand_down`（快照式）交互 | 中 | fk_expanded 路径遇到锚点维度时改用嵌套子查询展开（4.1 统一规则），单测覆盖 |

## 7. 测试计划

- **单测**（`meta/tests/test_dim_scope_bizkey.py`）：
  1. 混合值解析；2. 锚点 0 命中 → `1=0`；3. 开关 OFF → fail-closed；4. inherit 子查询 SQL 快照断言（不含具体子 ID）；5. exclude/wildcard 回归；6. `_has_explicit_include_for_dim` 笛卡尔语义回归。
- **集成测试（G2 核心验收）**：
  建 PS（domain 锚点 SCM）→ derive → 用户查询可见域 X → **新建版本 v2 + domain(code=SCM)**（不 re-derive）→ 同用户查询**可见 v2 供应链云** → 反例：domain(code=OTHER) 不可见。
- **回归**：存量数字 scope 的 effective_intents 生成结果 diff 为空。
- **E2E**：前端按业务键配置 → 三产品下供应链云全部可见/可编辑；resolve-preview 回显。

## 8. 实施分期

| 期 | 内容 | 交付判据 |
|----|------|----------|
| P1 | 引擎锚点解析 + 子查询动态化 + fail-closed + 开关 + 索引迁移 + 单测/集成测试 | G2 集成测试绿 |
| P2 | resolve-preview API + 保存预检 + 告警审计 | API 手测通过 |
| P3 | 前端选择器业务键模式 + 回显/警示 | E2E 绿 |
| P2'（备选，暂缓） | `PRODUCT_CODE/KEY` 限定语法 | 按需启动 |
| P3'（备选，暂缓） | Snowflake 式事件物化：对象创建事件 → 自动增量 re-derive（消除校验时子查询开销；需保证所有创建入口事件可靠，漏事件即断权） | 校验路径性能实测不达标时启动 |

## 9. 业界对标（2026-09-06 调研）

"资源随版本/层级演进，权限自动跟上而无需批量改配置"，头部产品共三条路线：

| 产品 | 机制 | 核心思想 | 与本方案的关系 |
|------|------|---------|---------------|
| Azure RBAC | 范围层级继承（管理组→订阅→资源组→资源），父级 assignment 子级自动继承 | 层级挂载点继承 | ≈ 已实现的维度 chain 子查询（`_build_chain_condition`） |
| AWS IAM ABAC | 标签匹配（principal tag = resource tag 才放行）；官方定位即"新增资源无需更新 policy" | 属性等值匹配，运行时动态判定 | ≈ **本 Spec 的业务键锚定**：领域 code 即资源"标签"，新版本自动命中 |
| Snowflake | Future Grants（`ON FUTURE <object_type>`），对象创建事件自动 apply grant | 声明式未来授权，事件驱动物化 | 备选路线（P3'）；查询零开销但依赖事件可靠，漏事件即断权 |
| SAP PFCG | 组织级别(Org Level) + 派生角色(Derived Role) + `*` | Master 角色改一次 push-down 全部派生角色；**但每个新组织单元仍需手工生成派生角色** | 反面参照：工具化批量更新 ≠ 根治；本方案走 AWS ABAC 档根治 |

- fail-closed 设计与 AWS IAM 基石原则 implicit deny（未明确允许即拒绝）一致。
- 结论：本方案 = Azure 式层级继承（已有）+ AWS 式属性锚定（新增），符合业界主流，无需返工。

## 10. 开放问题

1. IntentScopeAdapter 对含子查询的 RAW value 的拼接位置（WHERE 直接拼接 vs 包裹）——P1 首个验证项，若需包裹则在生成侧统一加括号。
2. 是否需要为 `service_modules.business_objects` 等非 HIERARCHY_BO 的 code 也开放锚点（当前维度链 4 层已够用，默认不做）。

## 11. 验收记录（2026-09-11）

**结论：P1/P2 全量落地，P3 框架落地（Rule Builder 内选择器为后续跟进项）。**

| 期 | 验收项 | 证据 |
|----|--------|------|
| P1 | 引擎锚点解析/动态子查询/fail-closed/开关 | `meta/tests/test_dim_scope_bizkey.py` 28 用例全过（commit fabb26a→50d64ae） |
| P1 | **G2 铁证**：新版本插入同 code 域后 SQL 字符串不变、执行自动命中（不 re-derive） | `TestG2DynamicAcceptance`：t1 derive 记录 SQL → t2 插入 v3+domain(120,'SCM') → t3 旧 SQL 执行命中 {64,88,90,120}，FIN(70) 不误命中；子域新实例 401 同样覆盖 |
| P1 | 数字 golden 零回归 | `test_numeric_golden_regression` 逐串断言；全量回归基线 diff（Spec20 前引擎 33 failed = Spec20 后 33 failed，无新增） |
| P1 | code 单列索引 | v085 迁移（commit 7402fe1）：dev 库 4/4 创建，幂等重跑 created=0/4，verify=True |
| P2 | 保存预检 + resolve-preview | TDD 5 用例（commit c04ebac）；dev 实测 POST domain=["SCM","TYPO_X"] → 200 + warnings 含 TYPO_X 未解析；resolve-preview 返回 SCM resolved_count=3（跨版本 id 771/1225/2200） |
| P3 | 前端锚点展示/水合/警示 | commit 2829183；浏览器级实测（PS 1198，数据已还原）：权限配置矩阵领域行显示「SCM（跨版本·命中 3）、TYPO_X（跨版本·未命中）」；`npm run build` 通过、chunk import 图无环 |

**开关**：`DIM_SCOPE_BIZKEY_ENABLED=1`（dev `.env` 已开；OFF 时锚点 fail-closed，数字 ID 行为不受影响）。

**遗留**：
1. ConditionRuleBuilder 的 FK picker 内「跨版本（业务键）/仅此实例（ID）」选择器尚未提供 UI——当前锚点经 API 写入，前端已能正确回显/水合/警示；在 Rule Builder 内直接新建锚点为下一步 P3 跟进项。
2. 既有失败测试 11 个（`test_intent_scope_adapter.py`、`test_derivation_pipeline.py` 等，`role_id` 旧签名/`permission_set_effective_intents` 缺表）为 Spec 19 迁移前陈旧测试，与本 Spec 无关，基线已确认。
3. §4.5 提及的 `dim_scope_bizkey_unresolved` 独立审计事件未单独建类型（fail-closed 已保证安全；未解析以保存 warnings + resolve-preview warning 呈现），如需审计可查 dimension_scopes 保存审计。

## 12. v5 字段即模式 · 通用性细化（2026-09-12 落地）

> 演进：v3 双 Tab（FK picker 内二次选模式）→ v4 自引用字段去 Tab → **v5 字段即模式全量泛化**。
> 核心命题：**字段类型即选择器模式，交互中不存在任何模式切换动作**（SAP F4 原则：F4 是字段的函数）。
> 双 Tab 在「字段即模式」视角下暴露为冗余：选择字段时模式已被唯一确定，Tab 属于二次确认噪音。

### 12.1 字段 → 模式映射（唯一真源）

| 字段类型 | 例（domain 资源） | 选择器形态 | 谓词产物 | 时间语义 |
|---------|------------------|-----------|---------|---------|
| 自引用 ID | `id` | 纯实例树 | `id IN (64,88)` | 快照 |
| 自引用业务键 | `code` | 无 Tab，业务键列表直出 | `code IN ('AM')` | 动态 |
| FK ID | `version_id` | 纯实例树（**双 Tab 退役**） | `version_id IN (10)` | 快照 |
| FK code（虚拟解析字段） | `version_code` | 无 Tab，目标维度业务键列表直出 | `version_id IN (10,20)`（**左值改写**） | 动态 |

### 12.2 通用性架构（零硬编码）

1. **FK code 字段白名单（元数据规则，非字段名枚举）** — `condition_permission_service._fk_code_field_map`：
   `storage=virtual` ∧ `redundancy.type=resolution` ∧ `source_field` 以 `_id` 结尾 ∧ 字段名以 `_code` 结尾 ∧ 解析维度 ∈ `_DIM_TABLES`。
   任意资源（含未来新增）满足四条件即自动获得 FK code 能力。
2. **语义信号 `anchor_semantics`（`instance`/`bizkey`/`null`）** — 后端 `get_resource_field_metadata` 按同源规则判定并随 field-metadata 下发；前端分组/hint/placeholder 全部由该信号派生，旧后端缺信号时前端按 `is_business_key`/`is_foreign_key` 兜底（向后兼容）。
3. **锚点展开左值改写** — FK code 谓词（`IN`/`=`）展开时改写为物理 FK 列（`version_code IN ('v01')` → `version_id IN (10,20)`）；数字 token 强制按业务键解析。`_anchor_target_of_field` 返回 `(维度, 物理左值列, 数字按ID?)` 三元组。

### 12.3 五层交互感知（把「快照 vs 动态」的时间差压缩到配置时刻）

| 层 | 载体 | 实现 |
|----|------|------|
| L1 字段下拉语义分组 | 「实例锚定 · 快照」/「业务键锚定 · 动态」/「属性条件」 | `RuleBuilderGroup.SEMANTICS_GROUPS`，anchor_semantics 驱动 |
| L2 对偶 hint | 实例树顶部「规则固定指向…」↔ 业务键列表顶部「自动适配…」（镜像句式，对比学习） | `SearchHelpDialog.vh-instance-hint` + `source.instance_hint` 可覆盖 |
| L3 placeholder 双行制 | 「选择xx实例...」↔「按xx业务键锚定...」 | `ConditionRuleRow.pickerPlaceholder`，self-ref/FK 同源判定 |
| L4 保存契约 toast | 含业务键锚点时提示「父对象下新增同名编码实例将自动纳入本规则」 | `ConditionRuleDialog.collectBizkeyAnchorFields` + `isBizkeyRuleValue` |
| L5 命中数心跳 | 业务键列表/回显 tag 携带当前命中数（0 命中红色） | v2 既有能力，tag「CODE（业务键·命中 N）」父对象中立 |

### 12.4 验收（2026-09-12）

| 项 | 证据 |
|----|------|
| 后端单测 | `test_dim_scope_bizkey.py` 63/63（新增 `TestFkCodeFieldMap`/`TestFkCodeExpansion`/`TestFkCodeFieldMetadata`） |
| E2E | `_spec20_bizkey_e2e.py` **24/24 PASS**（新增 L1 分组/5C FK code/5D FK id 退役/hint/placeholder/L4 toast 9 项断言） |
| 构建 | `npm run build` 通过，chunk-cycles OK（35 chunk 无环） |

**顺手修复**：`rule-helpers.ts` v4 遗留重复声明（SyntaxError）；`vite.config.js` visualizer 无条件注册致常规 build gzip 统计 zlib OOM，按 FR-018 原意改 `--mode analyze` 按需启用。

## 13. [FIX 2026-09-12] 条件弹窗两问题：行级连接符失同步 + 字段下拉被遮挡

### 13.1 「或」连接符不生效（公式恒 AND）

**根因**：v27 UI 模型中行与行的连接符存在每个 child 自己的 `connector`（顶层组内 rule 行首「且/或」segmented；子组由 tag-row 控制），而 `serializeGroup` 统一用 `group.connector` 拼接——顶层组没有组级连接符控件，root.connector 恒为 'AND' 且从不被 UI 更新。**序列化数据源与 UI 数据源错位**。

**修复**（[serializers.ts](../../../src/components/common/ConditionRuleBuilder/serializers.ts)）：
- 逐 child 取 `child.connector`；兜底区分语境：顶层组回落 `group.connector`（v26 flat 旧树/存量测试兼容），嵌套子组兜底 'AND'（子组 node.connector 是「与外层前一项的连接符」外层语义，不能作组内兜底）。
- `serializeDisplay` 同构修复（中文预览「或」）。
- 顺手修脏公式：空 part（未完成规则行）连同其 connector 跳过，空嵌套组输出 `''` 不再产生 `()`/` AND ` 空段。
- 混合 AND/OR 平铺输出，求值依赖标准布尔优先级（AND > OR，Python/SQL 共识），与 `parseConditionToRuleRows` 行级模型闭环。

**测试**：`serializers.spec.js` 33/33（新增 5 用例：用户报障场景/混合连接符/子组 connector/旧树回落/中文显示；更新 3 个存量嵌套用例树模型对齐 v27 UI 语义）。

### 13.2 字段下拉被「规则作用域」遮挡

**根因**：`.app-select-popper` 的 `z-index: var(--z-index-select)` 引用了**从未定义的 token**（tokens-yonyou.scss 只有 `--z-index-dropdown`，无 `--z-index-select`）→ 声明 invalid at computed-value time → 这条 `!important` 规则把 Element Plus popper 的 inline z-index (2000) 覆盖为 auto → teleported=false 的内联下拉按 DOM 顺序被后续兄弟区域（规则作用域 section）盖住。

**修复**：[tokens-yonyou.scss](../../../src/styles/tokens-yonyou.scss) 补 `--z-index-select: 1500`（popover 档：盖 modal 1400，让位 notification 1700）。

**验证**（`test_helpers/_condition_connector_verify.py`）：下拉 computed z-index = '1500'，`elementFromPoint` 于下拉项中心命中 popper 内部（顶层无遮挡），截图 `v_dropdown_zindex.png`。
