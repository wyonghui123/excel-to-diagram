# 细化稿：G4 工程 BOM 消费方（工程变更单 + 差异应用）

- 文档版本：v1.3
- 日期：2026-11-03
- 状态：已评审（2026-11-03 采纳 Oracle/NetSuite 对标结论），P1 实施中
- 归属：**独立专题（ECM 工程变更管理）**，不占 project 轨里程碑 M4；project 轨对其无硬依赖，属非阻塞项
- 关联主 Spec：[`spec-project-type-object-model-research-2026-10-31.md`](./spec-project-type-object-model-research-2026-10-31.md) §3 G4 / §7 Q2 / §8.4 D5
- 关联对象：`items` / `item_structure` / `item_structure_line` / `work_order_components` / `work_definition`
- 迁移编号：预计 `v198`（当前仓库最大 `v196`＝`batch_foundation`；`v197` 已被 P5 批次策略方案预占，以实际落地时为准）

---

## 1. 背景

主 Spec 缺口表 G4：

> `usage=engineering` 无消费方（项目 BOM 快照已裁决不建，D5 撤销）｜P0｜工程变更与项目实例化 BOM 不可表达

现状事实（已核实）：

| 事实 | 位置 |
|---|---|
| `item_structure.usage` 有 `production / engineering / sales / costing` 四值 | [item_structure.yaml](../../meta/schemas/item_structure.yaml) L119-138 |
| 只有 `production` 参与展开；其余用途 `explode_item` 直接返回空集合并提示 | [item_structure_explode_service.py](../../meta/services/item_structure_explode_service.py) L125-141 |
| 结构头有 `revision / status / valid_from / valid_to`；结构行只有 `valid_from / valid_to`，无行级 status | 同上 YAML L169-330 / L292-307 |
| 展开按 `status='active'` + 日期覆盖过滤结构行 | explode L146-168 |
| 工单展开快照落在 `work_order_components`，展开后不回读 BOM（AC-07） | 主 Spec §2.3 / §8.4 |
| 项目级 BOM 快照表 `project_structure_snapshot` 已裁决**不建**（D5 撤销） | 主 Spec §8.4 / 变更记录 v1.4 |

因此 G4 的剩余问题不是「项目 BOM 快照」，而是：**工程态 BOM 没有任何读写消费方，工程变更无法表达，也无法安全地把工程差异落到生产 BOM**。

**定位判定（v1.1，SAP / Oracle 对标后修正）**：本设计属于 **ECM（Engineering Change Management，工程变更管理）**，不是 **ETO（Engineer-to-Order，按单设计）**。

- ECM 是「变更控制机制」：谁在什么时间、因何原因、把哪一版设计 BOM 改成哪一版制造 BOM，如何生效与追溯；
- ETO 是「业务模式」：销售订单/项目驱动，每个订单重新设计，BOM 随设计逐步成型，需要项目专用 BOM、项目库存、WBS 成本归集；
- 两者可组合（ETO 场景变更更频繁），但本设计没有「订单驱动的项目专用 BOM」这一 ETO 核心，故只覆盖 ECM。详见文末附录 A。

## 2. 范围

### 2.1 本期做

1. **工程 BOM 差异对比**：同一物料下 `usage=engineering` 与 `usage=production` 的结构行差异（新增 / 修改 / 移除）。
2. **工程变更单**：把差异固化为可评审、可审计的变更单（头 + 明细），带状态流转。
3. **变更应用**：审批通过后，把变更明细落到 `item_structure_line`（生产结构），并保留历史行。
4. **项目归集（可空）**：变更单可挂 `project_id`，用于项目筛选；**不改变项目 360 的五段结构**。
5. **变更影响预览（v1.1 增补）**：`where-used` 只读分析，列出受影响的父项结构、以及已展开的在途工单（只列不改，对齐 SAP change monitor / Oracle affected objects 的最小能力）。

### 2.2 本期不做

| 不做项 | 理由 |
|---|---|
| `project_structure_snapshot` / 项目 BOM 快照 | D5 保留撤销；快照粒度继续落在工单 `work_order_components` |
| 新增 `usage=project` 枚举 | 与 D5 冲突，且项目不持有 BOM 快照（见 §3） |
| ECO 多级审批 / 会签 / 审批流引擎 | 本期用状态机 + 权限；复杂审批出现后再接 workflow |
| 在途工单回冲 / 自动改工单 | 工单展开快照已隔离（AC-07）；P1 只做**只读**影响预览（§2.1 #5 / AC-G4-9），不自动改 |
| 给 `item_structure_line` 加 `status` 列 | 不加列；失效复用 `valid_to`（explode 已按日期窗口过滤） |
| BOM 基线冻结 / 多版本对比报表 | 无真实诉求；出现后再评估轻量基线表 |

## 3. 裁决：Q2 选 `usage=engineering`，不新增 `usage=project`

主 Spec Q2 的两个候选：

- **A（采纳）**：为 `usage=engineering` 补消费方（本细化稿的工程变更单 + 差异应用）。
- B（否决）：新增 `usage=project`，把项目实例化 BOM 落到结构表。

采纳 A 的理由：

1. `engineering` 的语义就是「工程设计态 BOM」，与 `production` 并行存在、用 `revision` 表达版本，天然是工程变更的输入；
2. `usage=project` 会让「项目」变成 BOM 的持有者，与 D5「项目不建 BOM 快照」直接冲突，且需要新增枚举值 + 数据迁移，收益仅为换个标签；
3. 项目实例化的诉求已由「工单展开快照 + 配置实例 `structure_id/config_hash`」满足（AC-07），不需要第四种用途。

**结论**：枚举保持四值，`engineering` 由本细化稿的变更单消费；`project` 不新增。

## 4. 业务场景

| # | 场景 | 输入 | 输出 |
|---|---|---|---|
| S1 | 工程与生产 BOM 差异预览 | 工程结构 id、生产结构 id、基准日 | 差异行集合（add / modify / remove），只读，不落库 |
| S2 | 发起工程变更 | 差异集合 + 变更原因 + 生效日 + 可选项目 | `engineering_change(status=draft)` + 明细 |
| S3 | 评审与批准 | 变更单 | `in_review → approved` / `rejected` |
| S4 | 应用变更 | 已批准变更单 + 生效日 | 生产结构行新增 / 关旧开新 / 失效；变更单 `applied` |
| S5 | 追溯 | 变更单 id | 头 + 明细 + 应用时间 / 人；项目维度可按 `project_id` 过滤 |

## 5. 数据模型

### 5.1 复用（不改语义）

| 对象 | 用法 |
|---|---|
| `items` | 变更单的根物料；`item_type=goods`（服务不参与 BOM 变更） |
| `item_structure` | 工程结构：`usage=engineering`、`status=active`、`revision` 标识工程版本；生产结构：`usage=production` |
| `item_structure_line` | 差异与应用的目标行；失效用 `valid_to`，不物理删 |
| `work_order_components` | 只作为 AC-07 的隔离证据，**不修改** |
| `work_definition` | 不在本期联动（工艺路线与 BOM 变更独立评审） |

### 5.2 新增 `engineering_change`（工程变更单）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 主键 |
| `change_no` | string(40) | 变更单号，唯一；建议 `EC-{年月}-{序号}` |
| `title` | string(120) | 变更标题 |
| `change_type` | string | `new`（首次工程 BOM）/ `revise`（改版）/ `obsolete`（停用） |
| `project_id` | integer | 可选；平台扩展标签（Oracle/SAP 的 ECO 无项目关联），仅用于筛选，不改变 360 段 |
| `reason` | text | 变更原因 |
| `effective_date` | date | 生效日（应用时写入结构行 `valid_from`） |
| `status` | string | `draft / in_review / approved / applied / rejected / cancelled` |
| `applied_at` | datetime | 应用时间（可空） |
| `applied_by` | string(40) | 应用人（可空） |
| `created_at / updated_at` | datetime | 审计字段 |

约束与索引：

- `change_no` 唯一；
- 索引：`(status)`、`(project_id)`；
- 关系：`project_id → project`（可空）；`item_id / source_structure_id / target_structure_id` **下沉到明细行**（见 §5.3），以便一张变更单覆盖多个装配物料（对齐 NetSuite ECO：一个 ECO 可含多个 item）；
- P1 兼容约束（服务层）：一张变更单的所有明细 `target_structure_id` 必须相同（等价「一单一个根结构」），后续放开时无需迁移；
- `deletion_policy`：`restrict`（终态用 `cancelled`，不提供物理删除）；
- `skip_generic_api: true` + `requires_state_machine: true`（沿用 G7 机制，通用 CRUD / agent 工具不得改状态）；
- 归档：不单独建表，`rejected / cancelled` 保留可查。

### 5.3 新增 `engineering_change_line`（变更明细）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | integer | 主键 |
| `change_id` | integer | 父变更单（真外键，cascade） |
| `line_no` | integer | 行号，`(change_id, line_no)` 唯一 |
| `line_type` | string | `add / modify / remove` |
| `target_structure_id` | integer | 目标生产结构（`usage=production`，软引用，必填） |
| `source_structure_id` | integer | 来源工程结构（`usage=engineering`，软引用，`add/modify` 必填） |
| `source_structure_line_id` | integer | 来源工程行 id（软引用；`add/modify` 从该行复制新值） |
| `structure_line_id` | integer | 生产侧被修改 / 移除的行 id；`add` 时为空 |
| `component_item_id` | integer | 组件物料（真外键，restrict） |
| `match_key` | string(120) | 差异匹配键（`component_item_id + substitute_group_code + operation_seq`），便于复核 |
| `old_qty_per / new_qty_per` | number | `modify` 时新旧用量；`add` 只有 new；`remove` 只有 old |
| `old_valid_to / new_valid_to` | date | 可空；用于说明失效窗口变化 |
| `note` | text | 差异说明 |

约束：

- `change_id + line_no` 唯一；索引 `(change_id)`、`(component_item_id)`、`(target_structure_id)`；
- 明细只允许在 `draft / in_review` 阶段追加或删除；`approved` 之后不可改（服务层校验）；草稿明细允许物理删，`apply` 后只失效不删除；
- `add` 必须带 `source_structure_line_id`、不得带 `structure_line_id`；`modify/remove` 必须带 `structure_line_id` 且属于目标结构；`modify` 还要带 `source_structure_line_id`；
- 设计上允许多物料（每行自带结构），P1 服务层限制同一 `target_structure_id`。

### 5.4 差异不落表

差异是**实时计算结果**，不建 `engineering_bom_diff` 表：

- 避免「差异表」与两套 BOM 形成第三份数据源；
- 只有用户确认后，才把差异行写入 `engineering_change_line`；
- 复核时按变更单明细与当前 BOM 重新对比，若生产结构已被并发修改，`apply` 前置校验会拒绝（见 §6.3）。

### 5.5 差异匹配规则

以 `(component_item_id, substitute_group_code, operation_seq)` 为匹配键，按 `line_no` 稳定排序逐条配对：

| 情况 | 判定 |
|---|---|
| 工程有、生产无 | `add` |
| 生产有、工程无 | `remove` |
| 两侧都有且 `qty_per / fixed_qty / valid_to / optional_flag` 有差异 | `modify` |
| 同一匹配键两侧多行、无法一一对应 | 标记 `ambiguous`，**不自动生成明细**，要求人工在预览页逐行指定 |

## 6. 服务与动作

新增 `meta/services/engineering_change_service.py`（事务边界由调用方控制，与 labor / work_order 服务一致）。

### 6.1 只读差异

```python
EngineeringChangeService(ds).diff(
    source_structure_id, target_structure_id,
    as_of=None,            # 默认今天；按 status=active + valid 窗口过滤
) -> {
    'rows': [{'line_type': 'add|modify|remove', 'match_key': ..., 'old': {...}, 'new': {...}}],
    'ambiguous': [...],
    'source_revision': ..., 'target_revision': ...,
}
```

- 两侧结构必须存在且 `usage` 正确（source=engineering、target=production）、`status=active`；
- 结构行按 `valid_from/valid_to` 过滤，边界规则复用 explode 的 `_covers`（含端点）。

### 6.2 创建变更单

```python
create_change(ds, *, change_type, title, reason, effective_date,
              project_id=None, lines, created_by) -> change_id
# lines: [{'line_type', 'target_structure_id', 'source_structure_id',
#          'source_structure_line_id', 'structure_line_id',
#          'component_item_id', 'old_qty_per', 'new_qty_per',
#          'old_valid_to', 'new_valid_to', 'note'}]
```

校验：

1. 每条明细的 `target_structure_id` 存在且 `usage=production`，`source_structure_id` 存在且 `usage=engineering`，两者归属同一 `item_id`；
2. **P1 限制：所有明细的 `target_structure_id` 必须一致**（一单一个根结构）；表结构已按多物料设计，后续放开无需迁移；
3. `effective_date` 不早于今天（补录场景另议）；
4. `add` 必须带 `source_structure_line_id` 且不带 `structure_line_id`；`modify/remove` 必须带 `structure_line_id` 且属于目标结构，`modify` 还要带 `source_structure_line_id`；
5. 明细行数 1..N，`line_no` 连续；
6. `project_id` 为空或存在。

### 6.3 状态流转

| 动作 | 迁移 | 前置条件 | 权限 |
|---|---|---|---|
| `submit` | `draft → in_review` | 至少 1 条明细 | `engineering_change:create` |
| `approve` | `in_review → approved` | 明细完整、结构未被并发改动 | `engineering_change:approve` |
| `reject` | `in_review → rejected` | 必填驳回原因 | `engineering_change:approve` |
| `cancel` | `draft/in_review/approved → cancelled` | 未 applied | `engineering_change:create` |
| `apply` | `approved → applied` | 见 §6.4 | `engineering_change:apply` |

- 通用更新 / agent 工具对 `status` 的写入被 `requires_state_machine` 拦截；
- 所有动作写审计（操作人、时间、前后状态）；
- **Q2 已决**：P1 不接通用 workflow（审批规则尚未定义）；保留 `in_review` 与独立 `approve` 作为接入点，后续只加 `workflow_run_id` 列并让 `submit` 触发，不改状态机。

### 6.4 应用变更（`apply`）

单事务内按 `line_no` 顺序执行：

| 明细类型 | 操作 |
|---|---|
| `add` | 从 `source_structure_line_id` 复制字段 INSERT `item_structure_line`（`valid_from=effective_date`） |
| `modify` | 旧行 `valid_to = effective_date - 1 天`（关旧）+ 从 `source_structure_line_id` 复制字段 INSERT 新行（`valid_from=effective_date`） |
| `remove` | 旧行 `valid_to = effective_date - 1 天` |

**Q3 补充决定**：`apply` **不新建结构版本、不改 `item_structure.revision`**，只在同一版本内切换行有效期；结构版本级历史留 P2（需要时再加 `new_revision`）。避免「结构版本 + 行有效期」双重记账。

前置校验（任一失败整体回滚）：

1. 变更单 `status=approved`；
2. 目标结构与创建时 `revision` 一致，来源工程结构 `revision` 亦一致（防止并发改版）；
3. 每条 `structure_line_id` 仍存在且属于目标结构，`source_structure_line_id` 仍存在且属于来源结构；
4. `effective_date` 合法；
5. 同一目标结构不允许存在另一张 `approved` 未应用的变更单（串行化，避免两次 apply 互相覆盖）。

执行后：

- 更新变更单 `status=applied / applied_at / applied_by`；
- **不回冲 `work_order_components`**（AC-07 隔离）；
- 幂等：重复 `apply` 已 `applied` 的变更单直接返回成功，不重复写行。

## 7. API

统一前缀 `/api/v1`，响应走 `_response_contract`，不直接使用 `jsonify`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/engineering-changes` | 列表（`status / item_id / project_id` 过滤，分页） |
| GET | `/engineering-changes/<id>` | 头 + 明细 |
| POST | `/engineering-changes/diff` | 只读差异预览（不落库） |
| POST | `/engineering-changes` | 从差异创建变更单 |
| POST | `/engineering-changes/<id>/submit` | 提交评审 |
| POST | `/engineering-changes/<id>/approve` | 批准（body 可带意见） |
| POST | `/engineering-changes/<id>/reject` | 驳回（必填原因） |
| POST | `/engineering-changes/<id>/cancel` | 取消 |
| POST | `/engineering-changes/<id>/apply` | 应用到生产 BOM |

- 通用 BO 读写对该对象关闭（`skip_generic_api`）；读也可走专用 GET，避免与状态机语义混淆；
- 权限键：`engineering_change:view / create / approve / apply`，写入权限 YAML（不在代码硬编码）。

## 8. 前端（P1 最小集）

| 页面 | 内容 |
|---|---|
| 变更单列表 | 状态 / 物料 / 项目 / 生效日列；状态筛选；新建入口 |
| 变更单详情 | 头信息 + 明细表（`line_type` 色标）+ 状态动作按钮（按权限） |
| 差异预览 | 选择工程结构 / 生产结构 / 基准日 → 只读差异表；勾选行 + 填写原因 → 创建变更单 |

- 复用现有 BO 列表壳与抽屉表单；**项目 360 不新增段**；
- 写操作全部走 §7 专用端点，不经过通用 `PUT /bo/...`。

## 9. 迁移与 YAML 落点

| 项 | 内容 |
|---|---|
| 迁移 | `v198__engineering_change.py`：建 `engineering_changes` / `engineering_change_lines` + 索引；`verify / migrate / rollback`（rollback 先删明细表再删头表） |
| YAML | `meta/schemas/engineering_change.yaml`、`engineering_change_line.yaml`（`skip_generic_api` / `requires_state_machine` / `rules` 状态迁移） |
| 菜单 | 工程变更单菜单节点（挂在物料 / BOM 域下） |
| 权限 | `engineering_change:*` 四个权限键 |
| 回归 | `check_architecture.py` 计数不得上升；通用 CRUD 拦截测试 |

## 10. 分期

| 阶段 | 内容 | 出口 |
|---|---|---|
| **P1（本期）** | 差异预览 + 变更单（draft/in_review/approved/applied）+ apply + 专用 API + 最小前端 | G4 从「无消费方」变为「有可审计的工程变更链路」 |
| P2 | 生效日定时应用；影响预览扩展到更多单据类型（仍只读） | 减少手工 apply |
| P3 | ECO 与工单追溯、项目 BOM 基线对比（仅在真实诉求出现时） | 对应主 Spec §8.4「何时再做」 |

## 11. 验收标准

| # | 标准 |
|---|---|
| AC-G4-1 | `explode_item(usage='engineering')` 仍返回空集合并提示；工程 BOM 不参与生产展开 |
| AC-G4-2 | 差异算法对 add / modify / remove 三类均能精确识别；同键多行标记 `ambiguous`，不自动生成明细 |
| AC-G4-3 | `apply` 后：新增行生效、修改行「旧行关闭 + 新行生效」、移除行失效；历史行可查 |
| AC-G4-4 | `apply` 前后 `work_order_components` 行数 / 值不变（AC-07 不回冲） |
| AC-G4-5 | 通用 BO 更新 `status` 被拒；状态只能经 §6.3 专用动作 |
| AC-G4-6 | 并发场景：目标结构 `revision` 变化或已有未应用变更单时，`apply` 拒绝并回滚 |
| AC-G4-7 | 重复 `apply` 幂等；变更单 `project_id` 可空；项目 360 仍五段 |
| AC-G4-8 | 所有动作写审计（人 / 时间 / 前后状态） |
| AC-G4-9 | 变更单详情可查看影响预览：受影响父项结构 + 在途工单清单；预览为只读，不得修改工单或结构 |
| AC-G4-10 | 多物料预留：表结构允许明细各自挂结构；P1 服务层对跨 `target_structure_id` 的变更单报错（后续放开不改表） |
| AC-G4-11 | `apply` 不改变 `item_structure.revision`，只切换行 `valid_to/valid_from`；explode 按日期正确区分新旧 |

## 12. 风险与回滚

| 风险 | 处理 |
|---|---|
| 变更直接改主数据，误操作影响新工单 | `approve` 与 `apply` 双权限分离；审计留痕；`effective_date` 不早于今天 |
| 两张变更单并发改同一生产结构 | apply 前置校验「同一目标结构仅一张 approved 未应用」+ 事务 |
| `valid_to` 边界误判 | 沿用 explode `_covers` 的「含端点」语义；关旧日 = 生效日前一天 |
| 结构 `revision` 漂移 | 创建时记录、apply 时比对，不一致拒绝 |
| 回滚 | 迁移 `rollback` 只删两张新表；已应用的 BOM 变更通过反向变更单处理，不做自动回滚 |

## 13. 待评审确认（2026-11-03 已采纳 Oracle/NetSuite 对标结论）

| # | 问题 | 决定 | 依据 |
|---|---|---|---|
| Q1 | 变更单是否需要 `project_id` | 保留可空；仅筛选标签，不加 360 段；标注「平台扩展，Oracle/SAP 的 ECO 无项目关联」 | NetSuite/EBS ECO 无项目字段 |
| Q2 | 审批是否接通用 workflow | P1 不接；保留 `in_review` + 独立 `approve` 作为 seam，后续只加 `workflow_run_id` | NetSuite SuiteApprovals 把审批作为一等能力，但平台审批规则未定义 |
| Q3 | `modify` 关旧开新 vs 原地更新 | 关旧开新；**`apply` 不新建结构版本**，只切行有效期 | Oracle 用生效/失效日期表达增删改 |
| Q4 | `remove` 物理删 vs `valid_to` 失效 | `valid_to` 失效；**草稿明细允许物理删**，apply 后只失效 | 保留历史可追溯 |
| Q5 | 变更单是否允许跨物料 | 表结构支持多物料（`item_id / struct` 下沉明细）；**P1 服务层限制同一目标结构**，后续放开零迁移 | NetSuite ECO 支持一单多 item |

## 14. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-03 | v1.0 | 初稿：裁决 Q2（engineering 补消费方）、变更单两表、差异实时计算、apply 规则、P1/P2/P3 分期与 8 条验收 |
| 2026-11-03 | v1.1 | SAP / Oracle 对标后校正：明确本设计为 ECM（非 ETO）；P1 增补 where-used 影响预览；新增 AC-G4-9；补充附录 A |
| 2026-11-03 | v1.2 | 定位收口：G4 拆为**独立专题（ECM）**，不占 project 轨 M4；取证确认 project 轨无硬依赖（`engineering_change` 仅存于本稿，`usage=engineering` 无任何代码消费方） |
| 2026-11-03 | v1.3 | 采纳 Oracle/NetSuite 结论：结构 / 物料下沉明细行（多物料预留，P1 限制单目标结构）、`apply` 不新建结构版本、草稿明细可物理删、`project_id` 定为平台扩展标签；Q1–Q5 转已决；新增 AC-G4-10/11；影响预览归入 P1、P2 只做定时应用与扩展 |

---

## 附录 A：业界对标（SAP / Oracle）与设计校正

### A.1 对标对象

- **SAP**：ETO 业务流程（SD 销售订单 → PS 项目/WBS → 设计/BOM/工艺 → MRP/生产订单 → 交付结算）；ECM 工程变更管理（Change Master Record）；BOM 用途键（1 生产 / 2 设计 / 3 通用 / 5 销售 / 6 成本）。
- **Oracle**：EBS 离散制造中 `Engineering BOM` 与 `Manufacturing BOM` 分离，ECO 可由 mass change 生成并支持未来生效日；Project Manufacturing 用「项目引用 / 项目库存」支持按项目生产；Fusion PLM / NetSuite 的 `Change Order` 以受影响对象 + 审批工作流 + BOM revision 为核心。

### A.2 九维对比

| 维度 | SAP | Oracle | 本设计（G4） |
|---|---|---|---|
| 业务模式定位 | **ETO**：销售订单 + 项目/WBS + Super BOM + 项目库存；**ECM** 是独立变更机制，可与 ETO 组合 | **Project Manufacturing**（项目引用/项目库存）与 **Change Order** 分离，可组合 | **只做 ECM**；无订单驱动的项目专用 BOM |
| BOM 种类 | 用途 1 生产 / 2 设计 / 3 通用 / 5 销售 / 6 成本 | Engineering BOM 与 Manufacturing BOM 分开 | `production / engineering` 等四值，语义对齐 SAP 用途 1/2 |
| 变更单据 | Change Master Record（变更号）覆盖 BOM、工艺路线、物料、文档 | ECO / Change Order，关联受影响 BOM、组件、工艺 | `engineering_change` + 明细，仅 BOM |
| 生效控制 | 日期生效，或参数生效（序列号 / 批次 / 客户等） | 日期 / 序列号 effectivity；工程 BOM 支持未来生效日 | **仅日期**（`effective_date`） |
| 版本与历史 | 变更前后双版本保存，变更号长期可追溯 | BOM revision + ECO 历史 | 结构 `revision` + 关旧开新（`valid_to`） |
| 影响分析 | where-used / change monitor / 按用途释放 | affected objects / where-used | **v1.1 补只读影响预览**（父项结构 + 在途工单） |
| 审批 | 变更号审批与释放 | Approval workflow | 状态机 + approve/apply 双权限 |
| 项目 / 订单 | ETO：WBS、项目库存、按项目成本归集 | Project Manufacturing：项目引用、项目库存 | `project_id` 可空，仅归集，不建项目 BOM |
| 工艺路线联动 | ECM 同一变更号可覆盖 routing | 变更单可含工艺/流程变更 | 本期不联动（工艺走 `work_definition`，G3） |

### A.3 结论

1. **选型正确**：`usage=engineering` 对应 SAP 的「设计 BOM（用途 2）」，`production` 对应「生产 BOM（用途 1）」；两套 BOM 并行、变更单驱动 EBOM→MBOM，与 SAP ECM / Oracle ECO 属同一族。
2. **不是 ETO**：ETO 的核心是「销售订单 → 项目专用 BOM/工艺 → 项目库存/成本」，本设计没有这一层；D5 明确不建项目 BOM 快照，故 ETO 链路不在 G4 范围。把 G4 称为 ETO 会误导评审。
3. **最小必要补齐是影响分析**：SAP / Oracle 的变更单都以 where-used 影响面为前提；本设计原先只有「差异」，缺少「改了会影响谁」，v1.1 已补 AC-G4-9 与 P1 影响预览。

### A.4 差距分级

| 级别 | 差距 | 处理 |
|---|---|---|
| P1（本期） | where-used 影响预览（父项结构 + 在途工单，只读） | 已补入 §2.1 / AC-G4-9 |
| P2 | ECR（变更申请）与 ECO（变更执行）分离；影响面扩展到在途采购/工单；工艺路线联动 | 真实审批诉求出现再做 |
| P3 / 不做 | 参数化 effectivity（序列号 / 批次 / 客户）、redline 图文档、按用途释放（仅成本不生产）、项目专用 BOM（D5） | 平台无对应诉求，明确不做 |

### A.5 若产品目标确实是 ETO

则不能扩展 G4，应另立 **G15（按单设计链路）**，最小范围：

1. 销售订单/项目 → 项目专用 BOM 与工艺（允许从标准 BOM 复制后本地修改）；
2. 项目库存/项目引用（采购与生产按项目归集）；
3. 项目成本归集（设计工时 + 制造工时 + 采购）。

在此之前，G4 的 ECM 链路可独立交付，不会与 ETO 方案冲突。

