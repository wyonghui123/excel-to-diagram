# 审批流 Spec（Approval Workflow P0）

> 版本：v0.3 草案 ｜ 日期：2026-11-15 ｜ 状态：待评审（未实现）
> 定位：把审批域从「5 个真源半驱动」收敛为「2 个真源 + 派生」，并补齐前端审批动作与策略配置
> 判尺：单一事实源（SSOT）+ 元数据驱动；不造重型框架、不做超范围重构
> 复用底座：[`decision_effect.py`](../../meta/core/decision_effect.py)｜[`approval_meta_loader.py`](../../meta/core/approval_meta_loader.py)｜[`document_approval_service.py`](../../meta/services/document_approval_service.py)｜[`task_decision_api.py`](../../meta/api/task_decision_api.py)
> 关联 spec：[`spec-bo-metadata-single-source-2026-11-11.md`](./spec-bo-metadata-single-source-2026-11-11.md)｜[`spec-rule-model-2026-11-10.md`](./spec-rule-model-2026-11-10.md)｜[`spec-print-platform-2026-11-15.md`](./spec-print-platform-2026-11-15.md)
> 证据等级：`C` = 仓内已核实（含行号）；`F` = Oracle Fusion；`S` = SAP；`D` = 本 Spec 决策

---

## 0. 结论先行

### 0.1 一句话结论

审批域**不是缺能力，而是缺唯一边界**：求值链、决策-生效协议、四眼、幂等、任务账本都已实现且质量不低（`C`）；问题在于**同一事实在多处各有一份定义**，且**前端从未调用决策端点**。P0 只做两件事：把「审批人/动作/单据引用」收敛进 YAML 与任务快照，把 `POST /tasks/{id}/decision` 接到 UI 上。

### 0.2 现状修正（相对口头评审的修正，必须先看）

| # | 先前的判断 | 核对后的结论 | 证据 |
|---|---|---|---|
| 1 | 审批接入点硬编码在 Python | **错**。接入点判定**已经是** YAML 驱动：`get_approval_meta()` 读 BO 顶层 `approval.table`，「未声明即不可审批」 | `approval_meta_loader.py:34-50,53-71`；`document_approval_service.py:83-85` |
| 2 | 决策动作需改成 YAML `decision: true` | **过度设计**。`executor_config.decision_actions` 在建任务时**冻结进任务**，决策只读快照 ⇒ 历史任务不受后续配置变更影响。保留该范式，只把「写入时的那份来源」从常量换成派生 | `approval_task_service.py:122-124`；`decision_effect.py:84-101` |
| 3 | 建任务元数据都在 Python | **成立**。`APPROVAL_TASK_SPECS` 仍持有 `table`（与 YAML `approval.table` 重复）、`title_prefix`、`title_field`、`app_id`、`id_key` | `approval_task_service.py:25-54` |
| 4 | 前端「零调用」decision | **成立**。`src` 内无 `/decision` 调用，抽屉只有「认领」 | 全仓 grep `decision` 无 API 调用；`TaskDetailDrawer.vue:22-27` |

### 0.3 Decision Log

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D-AP-01** | 审批接入点唯一判据 = BO YAML 存在 `approval.table` 且非空；不新增注册表 | 独立 `approval_object_registry` 表 | 已实现且与打印 D-PR-17 同构（派生优于登记）；再登记一次就是再造真源 |
| **D-AP-02** | `APPROVAL_TASK_SPECS` 的 `title_prefix/title_field/app_id/id_key/title_prefix` 并入 YAML `approval:` 段；Python 侧删除常量，改由 `get_approval_meta()` 返回扩展字典 | 保留常量、YAML 只留 table | 两处 `table` 是已存在漂移；扩展键有默认值，历史 YAML 零改动 |
| **D-AP-03** | 决策动作**派生**：默认 `{bo}.approve` / `{bo}.reject`，在 action registry 中校验存在性；YAML `approval.decision_actions` 可显式覆盖 | 每个 YAML 手写 `decision: true` 标记 | 阈值 4 个 BO 全部符合命名约定；显式覆盖保留给特例，避免改 220 个 YAML |
| **D-AP-04** | 任务表新增 `doc_ref_type` / `doc_ref_id` 两列；审批任务写入；去重查询改用新列；`doc_ref` 继续写同值但**不再作为判定依据** | 把 `doc_ref` 改成 `type:id` 字符串 | 改格式破坏历史数据与所有读取方；加列零迁移风险 |
| **D-AP-05** | `approval_status` 明确为**只读投影**：只允许展示，禁止参与分支；用 lint 门禁而非新增元数据机制 | 给 YAML 加 `computed_from` 键 | 现有 YAML 已有注释声明「真源=tasks」；缺的是**执行**而不是声明，门禁更轻 |
| **D-AP-06** | 审核权限判定 = `is_admin` 短路，否则校验 `{object_type}:approve`；无该权限一律 fail-closed | 只放宽为「任务候选人」 | 候选人当前为空数组（`assign_policy='claim'`），按候选人判等于全员放行 |
| **D-AP-07** | `approval_policies` 增加 `version`；快照写入 `policy_version`；策略变更**不回写**在途任务 | 策略变更时重算在途任务 | 在途审批必须按发起时规则走完（审计口径）；重算会造成审批人凭空变更 |
| **D-AP-08** | 策略编辑 = 表单 + JSON 条件，不做流程画布 | 可视化流程设计器 | 与打印 D-PR-01 同判：画布维护成本远超收益；30 个策略页用表单足够 |
| **D-AP-09** | 审批链展示直接读 `inputs.policy_snapshot`（已含 steps / conditions_explain / metrics），**不新增审批链 API** | 新建 `/tasks/{id}/chain` | 快照已冻结且结构稳定，再造接口等于复制真源 |
| **D-AP-10** | P0/P1 不做加签、转签、委托、会签（`approve_mode≠any`）、SLA 升级 | 同期实现 | 需要多任务编排与定时器，属引擎级改造；当前 schema 字段保留但不执行 |
| **D-AP-11** | 前端状态文案单一真源：后端枚举 label → `src/constants/taskStatus.js` 单文件派生；端点不可用才回落内置表 | 各处保留硬编码副本 | 当前 5 处副本；收敛到 1 个文件 + 1 个端点 |
| **D-AP-12** | 批量审批 = 前端逐条调用现有端点（复用 `effect_key` 幂等），不新增批量 API | 新增 `/tasks/batch-decision` | 新增批量协议等于第二套错误语义；协议层已有幂等与 502 可重试契约 |

### 0.4 不采纳

| # | 不采纳项 | 出处 | 理由 |
|---|---|---|---|
| N-AP-01 | 可视化流程设计器 / BPMN 画布 | `F` 的 BPM Workflow | 我方策略是「条件 + 串行步骤」，画布解决的是我方没有的问题 |
| N-AP-02 | 独立审批中心（新一级菜单 + 独立菜单树） | `F` Transaction Console | 审批是任务的一种 `type`，任务中心已具备；另建中心会复制待办与权限 |
| N-AP-03 | 并行会签 / First-Responder-Wins / 投票百分比 | `F` Approval Group | 需要多任务实例与计数归并，属引擎改造；`approve_mode` 保留字段即可 |
| N-AP-04 | 审批人动态改签未来步骤（`F` Task History） | `F` | 依赖运行期链可变，与 D-AP-07 的「快照冻结」冲突；P2 再议 |
| N-AP-05 | 邮件/IM 通知内建 | `S`/`F` 工作流通知 | 接平台通知中心，不在审批域内自建通道 |

---

## 1. 范围与非目标

### 1.1 P0 范围

1. **单一事实源收敛**：YAML `approval:` 扩键、删除 `APPROVAL_TASK_SPECS`、决策动作派生、`doc_ref` 拆列、策略 `version`、`approval_status` 门禁。
2. **权限修复**：`_reviewer_permission` 改按 `{bo}:approve` 判定（含历史双段权限码兼容）。
3. **前端审批动作**：任务详情抽屉的通过 / 驳回 / 退回修改（`allow_rework`）+ 审批链与条件解释展示 + 单据跳转。
4. **状态中文化**：任务状态文案收敛为单一派生源，覆盖 5 处硬编码点。
5. **收件箱深化**：`approval` 分区置顶、列文案走元数据、多选批量。
6. **策略配置与试算**：规则中心审批策略页签新增列表 / 编辑 / **命中试算**（复用 resolver，零新逻辑）。

### 1.2 非目标

- 加签、转签、委托、会签、SLA 超时升级（引擎级，P2）。
- 审批链运行期变更（`F` Task History 语义）。
- 审批策略版本回滚 / 差异对比（仅记 `version`，不做 Diff UI）。
- 流程画布、自定义表单字段、独立审批中心、通知通道。

---

## 2. 事实基线（取证）

### 2.1 真源盘点

| # | 真源 | 位置 | 内容 | 性质 |
|---|---|---|---|---|
| 1 | BO YAML `approval:` | `meta/schemas/*.yaml`（4 处：`purchase_order:196`、`transfer_order:99`、`requisition:83`、`service_request:79`） | `table` + `amount_fields` | **合法真源**（接入点） |
| 2 | `APPROVAL_TASK_SPECS` | `meta/services/approval_task_service.py:25-54` | `table`（与 #1 重复）、`title_prefix`、`title_field`、`app_id`、`id_key` | **待收敛** |
| 3 | `DECISION_ACTIONS` | 同上 `:57-74` | `approve/reject` → `bo.action` | **待派生**（写任务时用） |
| 4 | `approval_policies` 三表 | `v178__approval_rule_model.py:38-93` | 策略 / 条件 / 步骤 | **合法真源**（运行期） |
| 5 | 任务 + 快照 | `tasks(type='approval')`、`inputs.policy_snapshot` | 在途审批事实 | **合法真源**（运行态） |
| 6 | `approval_status` 列 | `purchase_order.yaml:1108-1121`（自注「只读缓存」） | 单据侧审批态 | **投影**（仅展示） |
| 7 | 前端状态文案 | `TaskCenter.vue:18-20`、`TaskDetailDrawer.vue:7-9`、`AssociationSection.vue:984-985`、`EngineeringChangeDetailPage.vue:462`、`TaskInboxPanel.vue:43` | 中文/英文标签 | **副本**（待收敛） |

目标：真源 = #1 + #4 + #5；#2/#3 归入 #1 派生；#6/#7 归入投影。

### 2.2 决策协议契约（已实现，不改）

```
POST /api/v1/tasks/<task_id>/decision
body: { decision: "approve" | "reject", comment?: str, allow_rework?: bool }
禁用键: submitter_id / four_eyes / reviewer_permission   （400）
```

| 环节 | 行为 | 证据 |
|---|---|---|
| 权限事实 | `reviewer_permission=None` ⇒ fail-closed；当前传 `is_admin(user)` | `task_decision_api.py:46-48,86`；`decision_effect.py:223-233` |
| 四眼 | `type='approval'` 时默认强制，基准 = 任务 `created_by`，**不可由客户端指定** | `decision_effect.py:265-267`；`task_decision_api.py:12-13` |
| 幂等 | `effect_key = hash(task_id, attempt)` | `decision_effect.py:69-71` |
| 动作解析 | `executor_config.decision_actions[decision]` ⇒ action_id | `decision_effect.py:84-101` |
| **先生效后归位** | 必须拿到 BO 生效回执（`receipt_key` 非空）才改任务状态 | `decision_effect.py:332-338` |
| 归位映射 | `approve→done`；`reject→failed`，`allow_rework=True→in_progress` | `decision_effect.py:118-122` |
| 失败语义 | 守卫失败 `409`；未生效 `502 {retryable:true}`；其他 `500` | `task_decision_api.py:89-97` |
| 返回 | `{status:'completed', task_status, decision, action_id, receipt}` | `decision_effect.py:367-370` |

### 2.3 快照结构（已冻结，前端直接消费）

`document_approval_service.py:116-134`：

```
{ object_type, trigger_action, policy_id, policy_code, policy_name, priority,
  hit_policy, amount, steps[{step_no, approver_type, approver_ref,
                             approve_mode, sla_hours, min_amount, max_amount}],
  conditions, conditions_explain[], metrics, resolved_at }
```

`conditions_explain` = 逐条 `{field, op, expected, actual, passed}`，可直接渲染为「为什么命中这条策略」。**这是试算页与审批链的共同数据源。**

### 2.4 策略命中口径（已统一，勿另立）

`rule_hit_policy.ORDER_BY` = `priority DESC, effective_from DESC, id DESC`，默认 `first`（`document_approval_service.py:218-220`）；金额分段未覆盖时回退整条链（`:263-271`）。

---

## 3. 收敛设计

### 3.1 YAML `approval:` 段扩展（D-AP-02 / D-AP-03）

```yaml
approval:
  table: purchase_orders                      # 必填；存在即「可审批」
  amount_fields: [gross_amount, net_amount]   # 可选；缺省回落 DEFAULT_AMOUNT_FIELDS，[] 表示恒 0
  # ---- 以下新增，全部有默认值，历史 YAML 无需改动 ----
  title_prefix: 采购订单审批                   # 默认: "{name}审批"
  title_field: order_no                       # 默认: 空 ⇒ 标题用记录 id
  id_key: purchase_order_id                   # 默认: "{bo}_id"
  app_id: procurement                         # 默认: MetaObject.app 或 ''
  decision_actions:                           # 默认派生 {bo}.approve / {bo}.reject
    approve: purchase_order.approve
    reject: purchase_order.reject
```

**派生与校验规则**（`approval_meta_loader.py` 内实现）：

1. `get_approval_meta()` 返回值扩展为上述 6 键；`table` 为空串即「不可审批」（保持现语义）。
2. `decision_actions` 未声明时派生 `{bo}.approve` / `{bo}.reject`；**派生过程不做 action registry 存在性校验**（M1 实施偏离，理由见下），显式声明时若只给一半则记 warning 并整体视为不可审批。
   - 偏离理由：`service_request.approve` / `requisition.approve` 由 `meta/services/demand_entry_decision.py` 在运行期（而非 `bo_action_registrations.py`）注册，registry 装配顺序不稳定；启动期做存在性校验会把可审批对象整体误降级为不可审批。动作缺失由决策执行期的硬错误兜底，fail-closed 效果相同（`resolve_decision_action` 找不到动作即拒绝）。
3. `app_id` 已核对：`MetaObject` 无 `app` 字段（`meta/core/models.py`），YAML 顶层 `app` 不被 `yaml_loader` 解析 ⇒ 默认回落空串；需要业务域的 BO（如 `purchase_order` / `transfer_order`）在 `approval:` 段显式写 `app_id`。

**改动点**：`approval_task_service.py` 删除 `APPROVAL_TASK_SPECS` 与 `DECISION_ACTIONS`，`create_task` 改用 `get_approval_meta(object_type)`；未知/非法对象仍返回 `None`（幂等语义不变）。

### 3.2 任务表拆引用（D-AP-04）

迁移 `v276__approval_ssot.py`（编号实际取 v276，v275 已被打印平台占用）：

```sql
ALTER TABLE tasks ADD COLUMN doc_ref_type VARCHAR(200);
ALTER TABLE tasks ADD COLUMN doc_ref_id   VARCHAR(200);
CREATE INDEX IF NOT EXISTS idx_tasks_approval_ref
    ON tasks (doc_ref_type, doc_ref_id, status);

ALTER TABLE approval_policies ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
```

- 审批任务写入 `doc_ref_type = object_type`、`doc_ref_id = record_id`；`doc_ref` 继续写 `str(record_id)`（只读兼容，不再判定）。
- 去重条件（`approval_task_service.py:95-99`）改为 `type='approval' AND doc_ref_type=? AND doc_ref_id=? AND status NOT IN (...)`。
- 历史数据回填（实施口径）：`migrate()` 内按 `inputs` 的 `{bo}_id` 键反推（映射表 `ID_KEY_TO_OBJECT` 覆盖 purchase_order / transfer_order / requisition / service_request），命中即写 `doc_ref_type` + `doc_ref_id`；反推不到的后端不猜，留空 ⇒ 权限判定 fail-closed（非 admin 一律拒）。

### 3.3 `approval_status` 投影门禁（D-AP-05）

- 保留列与枚举，前端可展示，后端可写（guard interceptor 写 `pending`，决策服务写终态）。
- 新增门禁测试 `meta/tests/test_approval_status_projection.py`：对审批引擎 4 个模块（`approval_meta_loader` / `decision_effect` / `approval_task_service` / `document_approval_service`）做 token 级扫描，只禁「**读判定**」：`approval_status` 作为 NAME token 出现即失败；注释、文档串、SQL 文本与字典键（写投影）不计入。口径写入本 spec §2.1，替代 YAML 注释（注释不执行）。

### 3.4 权限收敛（D-AP-06）

```python
def _reviewer_permission(user, object_type: str) -> bool:
    if not user:
        return False
    if is_admin(user):
        return True
    if not object_type:              # 历史任务无 doc_ref_type ⇒ fail-closed
        return False
    return user_has_permission(user.get('permissions') or [], f'{object_type}:approve')
```

- `object_type` 由 `_task_object_type(data_source, task_id)` 读 `tasks.doc_ref_type` 得到；缺失（历史任务）⇒ 直接返回 `False`（fail-closed，不放宽）。
- 用 `permission_gate.user_has_permission` 而不是 `evaluate_code`：后者在 `gate_mode=shadow` 下会放行，审核权限必须严格判定。
- 修复历史双段播种：`purchase_order:purchase_order_approve` 等旧码由 `permission_sync_service` 播种为别名并标记 `deprecated`，`has_permission` 兼容双段（收敛动作见既有计划，不在本 spec 重复）。
- `scripts/check_permission_consistency.py` 增加 **R7**（实施口径与本节初稿不同，以此为准）：凡是 YAML `approval.table` 非空的 BO，其 `{bo}:approve` 必须出现在 DECLARED 或 STORED 权限集合中，否则报 `approval_permission_missing`。理由：`decision_actions` 默认就是派生值，校验派生物没有意义；真正会让非 admin 审核人必然被拒的是权限码缺失。

### 3.5 策略版本（D-AP-07）

- 策略保存时 `version = version + 1`（含条件/步骤的子表改动）。
- `snapshot` 增加 `policy_version`（`document_approval_service.py:116-134`）。
- 在途任务不重算：决策时只读任务快照，`resolve_decision_action` 也不查策略表 —— 已成立，仅需在文档与测试中固化。

---

## 4. API 契约

### 4.1 已有（不改，前端接入）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/tasks/<task_id>/decision` | 通过 / 驳回（含退回修改） |
| GET | `/api/v1/task-inbox` | 分区待办（含 `approval`） |
| GET | `/api/v1/task-inbox/counts` | 分区计数 |
| GET | `/api/v1/tasks/<task_id>` | 任务详情（含 `inputs.policy_snapshot`、`executor_config`） |
| GET | `/api/v1/tasks/<task_id>/events` | 活动流 |
| POST | `/api/v1/tasks/<task_id>/claim` | 认领（审批场景可不用） |

### 4.2 新增

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/approval-policies` | 列表（`scope_bo` / `status` 过滤，含 `version`） |
| GET | `/api/v1/approval-policies/<id>` | 详情（策略 + 条件 + 步骤） |
| POST/PUT | `/api/v1/approval-policies[/<id>]` | 保存（`version+1`） |
| GET | `/api/v1/approval-policies/preview?object_type=&record_id=&trigger_action=submit` | **命中试算**：薄适配 `DocumentApprovalResolver.resolve()`，只读，返回 `required/policy_code/steps/conditions_explain/snapshot` |

试算端点**不实现任何判定逻辑**，仅转调 resolver 并做权限/入参消毒 —— 保证试算与生产求值同源（`C`：`document_approval_service.py:81-143`）。

---

## 5. 前端 UI 方案

### 5.1 信息架构

```
① /system/task-management  待办收件箱（分区：待我审核 置顶）
        │ 点行
        ▼
② TaskDetailDrawer  任务详情（状态 / 单据 / 审批链 / 动作）
        │ 决策
        ▼
   POST /tasks/{id}/decision  → 刷新收件箱 + 任务详情

③ /system/rule-center · 审批策略  策略列表 / 编辑 / 命中试算
```

组件全部复用现有：`PageShell`、`MetaTable`、`Drawer`、`AppButton`、`AppAlert`、`EnumTag`、`FilterBar`、`useMessage`。

### 5.2 入口 ① 收件箱（改造，不重建）

| 项 | 现状 | 改动 |
|---|---|---|
| 列文案 | 英文直出（`TaskCenter.vue:11-24`） | 走 `taskStatus.js` + 列 label 派生 |
| 分区 | 5 分区，approval 不置顶 | `approval` 分区默认展开且置顶 |
| 批量 | 无 | `MetaTable` `selectable` + 工具栏「批量通过 / 批量驳回」 |
| 行操作 | 打开详情 | 增加「通过 / 驳回」快捷操作（`approve` 权限门控，需二次确认） |

批量实现（D-AP-12）：逐条 `submitDecision`，单条失败不中断，汇总 `成功 N / 失败 M`，失败项展示 `message`；`502 retryable` 项提供「重试选中」。

### 5.3 入口 ② 任务详情抽屉（P0 核心）

**布局（自上而下）**

1. 头部：标题 + `EnumTag` 状态（中文）+ 优先级 + 创建时间 + 提交人。
2. 单据卡：`doc_ref_type` + `doc_ref_id` → 「查看单据」跳 `/{object_type}/{id}`（`doc_ref_type` 缺失时隐藏按钮并提示历史任务）。
3. 审批链：读 `policy_snapshot.steps`，渲染为横向步骤条 —— 显示 `step_no / approver_type:approver_ref / approve_mode / sla_hours`；当前步骤高亮。`approve_mode != 'any'` 时打「会签（未启用）」灰色标签（D-AP-10）。
4. 命中依据（可折叠）：`conditions_explain` 逐条 `field op expected → actual`（✓/✗），`metrics` 与 `amount` 副标题。
5. 动作区：
   - `通过`（primary）/ `驳回`（danger）/ 驳回时勾选「退回修改（允许返工）」
   - 驳回 `comment` 必填；通过可选
   - 按钮来源 = `executor_config.decision_actions` 的键（**不读前端常量**）
   - 权限门控：`authStore.hasPermission(`${doc_ref_type}:approve`) || isAdmin`
   - 加载态：`AppButton loading`；`409` 提示「任务状态已变化，刷新后重试」并自动刷新；`502` 提示「单据未生效，可重试」
6. 活动流：复用现有 `/events`。

**新增 service**

```js
// src/services/taskService.js
export async function submitDecision(taskId, { decision, comment = '', allowRework = false })
// POST /api/v1/tasks/{id}/decision  → { decision, comment, allow_rework: allowRework }
```

**状态中文化（D-AP-11）**

```
src/constants/taskStatus.js      ← 单一派生源（11 态 label + tag type）
  · 优先 GET /api/v2/meta/task/ui-config 的 status 枚举 label
  · 端点不可用回落内置表（同文件，单一副本）
```

替换 5 处：`TaskCenter.vue`、`TaskDetailDrawer.vue`、`TaskInboxPanel.vue`、`AssociationSection.vue`、`EngineeringChangeDetailPage.vue`。

### 5.4 入口 ③ 规则中心 · 审批策略

`rule_center_view.yaml:150-155` 现仅 `detail`，补：

| Tab / 区 | 内容 |
|---|---|
| 策略列表 | `MetaTable`：code / name / scope_bo / trigger_action / priority / version / status / 生效区间；行操作：编辑 / 停启用 |
| 编辑抽屉 | 基本信息 + 条件行（`field_id / operator / value_*`，复用打印绑定的 JSON 校验风格）+ 步骤行（`step_no / approver_type / approver_ref / min-max / approve_mode(只读 any) / sla_hours`）；保存后 `version+1` |
| 命中试算 | 选 `object_type + record_id` → `preview` → 展示 `required / policy_code / steps / conditions_explain`；**复用 `RuleTracePanel` 的 steps/chain 渲染**（`RuleTracePanel.vue:170-207`） |

权限：`approval_policy:{read,create,update}`（与既有 BO 动作码风格一致；`approval_policy` 已是 BO 则无需新码，实施前核对 registry）。

---

## 6. 实施分期与验收

| 阶段 | 内容 | 验收（可执行） |
|---|---|---|
| **M1 后端收敛**（✅ 已完成） | YAML 扩键 + 删 `APPROVAL_TASK_SPECS` / `DECISION_ACTIONS` + 迁移 v276 + `_reviewer_permission` + 门禁 R7 + `approval_status` 门禁测试 | 见下方「M1 验收记录」 |
| **M2 P0 UI** | `submitDecision` + 抽屉动作 / 审批链 / 依据 / 单据跳转 + `taskStatus.js` + 5 处替换 | 前端构建通过；3010 冒烟：非 admin 用户对无 `{bo}:approve` 单据不可见动作；驳回填意见后可成功并刷新 |
| **M3 策略与批量** | 策略 CRUD + `preview` + 收件箱批量 | `preview` 与生产 `resolve()` 返回一致（同 record 对比断言）；批量部分失败仍出汇总 |
| **M4（P2，不在本期）** | 加签 / 转签 / 委托 / 会签 / SLA | — |

**M1 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 测试 | 188 passed / 0 failed：`test_document_approval` 25、`test_task_decision_api` 6、`test_approval_status_projection` 4、`test_rule_dispatcher` 20、`test_demand_entry_m1` 42、`test_transfer_order_service` 28、`test_purchase_order_guard` 31、`test_transfer_order_guard` 32 |
| 门禁 R7 | `check_permission_consistency.py` 的 `approval_permission_missing` 为**空**（4 个审批对象的 `{bo}:approve` 均已入库）；脚本整体 exit 1 来自**既有** R1/R5 `project:*` 问题，与本次无关 |
| schema drift | `python -m meta.tools.sync_schema --generate` 后 `generated_schema.sql` diff 仅 4 行（两个新列 + 一条索引），无无关漂移 |
| 迁移 v276 | dev 库（`meta/architecture.db`）已执行并取证：`tasks.doc_ref_type/doc_ref_id`、`approval_policies.version`、`idx_tasks_approval_ref` 均存在；库内 `type='approval'` 任务 0 条，回填 0 条（无数据可填） |

**M1 实施前置探测结论**：

1. `MetaObject` **无** `app` 字段（`meta/core/models.py`）⇒ `app_id` 默认空串，需要业务域的 BO 显式声明。
2. `task.yaml` 是 BO，列/索引改 YAML 后由 `sync_schema --generate` 产出 DDL，drift 门禁保持绿。
3. `approval_policy` **未注册为 BO**（无 `approval_policy.yaml`）⇒ M3 策略 CRUD 必须走专用 API，不能走通用 BO API。

---

## 7. 风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 历史在途任务缺 `doc_ref_type` | 权限判定回落 admin-only | v276 迁移内已按 `inputs` 反推回填；反推不到的保持 fail-closed |
| R2 | 派生 `decision_actions` 与真实 action id 不一致 | 建任务后决策 409 | 决策执行期由 `resolve_decision_action` 硬失败兜底（fail-closed）；R7 门禁保证 `{bo}:approve` 权限码存在。**不做**启动期 action 存在性校验（见 §3.1 偏离理由） |
| R3 | YAML 扩键被 schema lint 拒 | M1 阻塞 | 扩键全部可选；先改 `yaml_loader` 白名单再改 4 个 YAML |
| R4 | 前端绕过 `decision_actions` 自造动作 | 决策失败或错误动作 | 代码评审规则：动作键只允许来自任务 `executor_config` |
| R5 | `approval_status` 仍有隐性分支读取 | 状态漂移 | 门禁测试（§3.3）；新代码一律读 tasks |