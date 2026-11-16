# 审批流 Spec（Approval Workflow P0）

> 版本：v0.18 ｜ 日期：2026-11-16 ｜ 状态：P0 已交付（M1-M3 验收通过）；M4（P2）任务域通用能力已实现并验收（M4-1~M4-5，§8），二次检查与元数据驱动审计见 §8.9；M5（通用任务引擎）已实施并验收（§9.8）；2026-11-16 完成存量表名/列名规范化（§9.10）、取人解析行业复核（§9.11）、全仓运行期表名收口（§9.12）与任务域二次检查 + Fusion/SAP 头部对标（§9.13）；同日完成 §9.13.6 全部 6 步（动作表/REST、cancel·hold·resume、withdraw 回退、单据侧只读投影、批量护栏、策略条件构建器 + 实例三步态），收口 G-13-6（快照结构版本 + 写入期校验，§9.13.6.5），并完成 live 3010 手工冒烟与 6 项缺陷修复（§9.13.6.6）
> 定位：把审批域从「5 个真源半驱动」收敛为「2 个真源 + 派生」，并补齐前端审批动作与策略配置
> 判尺：单一事实源（SSOT）+ 元数据驱动；不造重型框架、不做超范围重构
> 复用底座：[`decision_effect.py`](../../meta/core/decision_effect.py)｜[`approval_meta_loader.py`](../../meta/core/approval_meta_loader.py)｜[`document_approval_service.py`](../../meta/services/document_approval_service.py)｜[`task_decision_api.py`](../../meta/api/task_decision_api.py)
> 关联 spec：[`spec-bo-metadata-single-source-2026-11-11.md`](./spec-bo-metadata-single-source-2026-11-11.md)｜[`spec-rule-model-2026-11-10.md`](./spec-rule-model-2026-11-10.md)｜[`spec-print-platform-2026-11-15.md`](./spec-print-platform-2026-11-15.md)
> 证据等级：`C` = 仓内已核实（含行号）；`F` = Oracle Fusion；`S` = SAP；`P` = 其他头部产品公开文档（ServiceNow / Salesforce / Jira / Camunda / 飞书 / 钉钉）；`D` = 本 Spec 决策

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
| N-AP-03 | 并行会签 / First-Responder-Wins / 投票百分比 | `F` Approval Group | P0 不采纳；M4 改为「单任务 + 参与流水归并」（§8.3，任务域通用能力），不做多任务实例与投票比例 |
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

- 加签、转签、委托、会签、SLA 超时升级（P0 不做；P2 已立项，设计见 §8，实施按 §8.7 分期）。
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
| **M2 P0 UI**（✅ 已完成） | `submitDecision` + 抽屉动作 / 审批链 / 依据 / 单据跳转 + `taskStatus.js` + 状态文案替换 | 见下方「M2 验收记录」 |
| **M3 策略与批量**（✅ 已完成） | 策略 CRUD + `preview` + 收件箱批量 | 见下方「M3 验收记录」 |
| **M4（P2）**（M4-1~M4-5 ✅ 全部完成，见 §8） | 转签 / 加签（含会签归并） / 委托 / SLA 记录与超时升级 / 前端 | 见 §8.7 分期验收 + 「M4-1~M4-5 验收记录」 |

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

**M2 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 前端测试 | `taskService` + `TaskDetailDrawer` + `TaskInboxPanel` + `TaskCenter.schedule` 共 41 passed（新增抽屉 6 例：状态中文化 / 审批链与依据 / admin 短路 / `{bo}:approve` 白名单 / 无权限提示 / 驳回必填 + `allow_rework` 透传） |
| 后端测试 | `test_task_inbox.py` 14 passed（新增 `TC_INBOX_030` 详情契约）、`test_task_decision_api.py` 6 passed、`test_task_query_read.py` 全绿 |
| 构建/lint | `npm run build` 通过（chunk-cycles OK）；`eslint` 无新增错误（仅既有 `URLSearchParams` warning） |
| 契约补充（实现必需） | 详情端点此前不含快照字段，M2 在 `task_inbox.py` 增加 `_DETAIL_EXTRA_COLUMNS`（`inputs` / `executor_config` / `doc_ref_type` / `doc_ref_id`），仅详情返回、不进收件箱 entry，避免列表 payload 膨胀 |
| 偏离说明 | 状态文案实际收敛 **3 处任务状态展示**（`TaskCenter` 监控表、`TaskInboxPanel` 行、抽屉状态 chip）。Spec §2.1 #7 另两处（`AssociationSection` 的 `approval_status`、`EngineeringChangeDetailPage` 的变更单状态）属于**不同枚举域**（BO 投影 / 变更单状态），并入 `taskStatus.js` 会造成错误合并，保持原样 |
| 未做 | live 3010 冒烟未执行（需要种子审批任务 + 真实用户权限）；权限门控与决策错误映射已由组件测试覆盖 |

**M3 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 后端服务 | `meta/services/approval_policy_admin_service.py`：列表/详情/保存（version 新建=1、更新=+1，子表整体替换在单事务内）/`preview`（薄适配，直接委托 `DocumentApprovalResolver.resolve`）/`options` |
| 后端 API | `meta/api/approval_policy_api.py`：`GET /api/v1/approval-policies`（分页+3 筛选）、`/options`、`/preview`、`/<id>`、`POST`、`PUT`；`app_builder.py` + `server.py` 双处注册 |
| 后端测试 | `test_approval_policy_admin.py` 20 passed（version 递增 / 子表替换 / 编码唯一 / 运算符与 AND 逻辑 / 步骤必填 / `preview` 与 `resolve` 同 record 断言一致 / 无策略 `reason=no_policy` / 6 条路由未登录 401）；回归 `test_rule_center_api.py` 26、`test_document_approval.py` 25、`test_task_inbox.py` 14 全绿 |
| 前端（规则中心） | `TAB_KINDS` 新增 `approval_policy`；`approval` 页签 `kind` 升级；新增顶层 `approval_policy` 元数据段（列/字段/字典/文案）；`src/services/approvalPolicyService.js` + `src/views/RuleCenter/ApprovalPolicyPanel.vue`（列表 / 编辑抽屉 / 条件 JSON / 步骤行编辑 / 试算） |
| 前端（收件箱） | `taskService.sortApprovalFirst` + `summarizeBatchResults`（纯函数）；`useTaskInbox.submitBatch` 逐条 `submitDecision`、失败不中断、成功后才重载；`TaskInboxPanel` 批量栏（全选 / 意见 / 批量通过 / 批量驳回 / 502 重试）+ approval 行置顶与左侧标记 |
| 前端测试/构建 | `taskService` + `useTaskInbox` + `TaskInboxPanel` 共 44 passed（新增置顶稳定排序、批量成功/失败汇总、502 可重试、驳回必填意见）；`npm run build` 通过 |
| 偏离 1：权限码 | 仓内不存在 `approval_policy:{read,write}`，策略 API 复用既有 `rule_center:read` / `rule_center:write`，避免新增第二权限真源（如需独立码需同步权限种子 + 门禁 R7） |
| 偏离 2：页签 id | 复用既有 `approval` 页签 id（仅升级 `kind`），避免打破 `test_view_config_has_expected_tabs` 对 tab id 的精确断言 |
| 偏离 3：批量 UI | 未引入 `MetaTable selectable`，保持 `TaskInboxPanel` 既有 `ul` 列表结构 + `el-checkbox` 选中，最小改动且复用现有行点击（`@click.stop` 隔离勾选） |
| 偏离 4：批量接口 | 不新增批量端点，按 D-AP-12 前端逐条调用 `POST /tasks/{id}/decision`；单条失败继续、结果汇总「成功 N / 失败 M」，`httpStatus=502` 的失败项可一键重试 |
| 偏离 5：文案 | 规则中心新增文案全部走 `rule_center_view.yaml`；收件箱新增文案沿用该组件 M2 既有内联风格（组件未接元数据文件），未扩散为新的文案真源 |

---

## 7. 风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 历史在途任务缺 `doc_ref_type` | 权限判定回落 admin-only | v276 迁移内已按 `inputs` 反推回填；反推不到的保持 fail-closed |
| R2 | 派生 `decision_actions` 与真实 action id 不一致 | 建任务后决策 409 | 决策执行期由 `resolve_decision_action` 硬失败兜底（fail-closed）；R7 门禁保证 `{bo}:approve` 权限码存在。**不做**启动期 action 存在性校验（见 §3.1 偏离理由） |
| R3 | YAML 扩键被 schema lint 拒 | M1 阻塞 | 扩键全部可选；先改 `yaml_loader` 白名单再改 4 个 YAML |
| R4 | 前端绕过 `decision_actions` 自造动作 | 决策失败或错误动作 | 代码评审规则：动作键只允许来自任务 `executor_config` |
| R5 | `approval_status` 仍有隐性分支读取 | 状态漂移 | 门禁测试（§3.3）；新代码一律读 tasks |

---

## 8. M4（P2）设计：任务域通用能力（改派 / 加签（会签） / 委托 / SLA）

> 版本：v0.9 ｜ 状态：**M4-1 改派 / M4-2 加签·会签 / M4-3 委托 / M4-4 SLA / M4-5 前端 已实现并验收（M4 收口）** ｜ 决策编号接续 §0.3（D-AP-13 起）
> **SSOT 修正（相对 v0.4）**：这四项（改派、加签/会签、委托、SLA）一律落在 `tasks` 任务域，**对所有任务类型生效**，审批只是第一个消费者；不建审批专属执行人表
> 实施顺序：**改派 → 加签/会签 → 委托 → SLA**；每步独立可验收、可回滚
> 判尺不变：不造审批引擎、不引入新调度器、不复制真源

### 8.0 SSOT 复核：v0.4 的「第二真源」

| 事实 | 唯一真源（既有 / 新增） | v0.4 的错误写法 |
|---|---|---|
| 谁能做这个任务 | `tasks.executor_candidates`（参与集合，`task_assignment.py:119-130`）+ `assign_policy` | 自建 `approval_task_approvers`，与候选池并存 ⇒ 两个执行人真源 |
| 当前锁定给谁 | `tasks.executor_assignee`（`_persist_claim` 已按此写，`task_assignment.py:142-157`） | 台账里再存一份 `assignee`，双侧可漂移 |
| 每人做了什么 | 新增 `task_participations`（参与流水，**事实**不是分配真源） | 把「票」当成「审批人定义」存 |
| 委托关系 | 新增 `task_delegations`（任务域，按 app/type/doc_ref 匹配） | 审批专属 `approval_delegations`，其他任务类型无法复用 |
| 完成口径 | `tasks.executor_config.completion_mode`（JSON 已有字段，零迁移） | 用「是否存在 added 行」隐式推导 |
| SLA | `tasks.sla` + `task_slas` + `sla_ladder` + `task_tick`（全部既有） | 另写审批 SLA 分支 |
| 审计 | `task_worklogs(note)` / `task_participations` | 扩 `EVENT_TYPES` 或另建审批审计表 |

结论：**能力归属任务域，审批只做「建任务时写配置 + 决策时消费」**；沿用 D-AP-01「派生优于登记」。

### 8.1 任务域扩展（零 ALTER + 两张流水表）

**决策 D-AP-13（修订）**：不新增审批专属表；分配真源沿用 `tasks` 现有列，只补一张通用「参与流水」与一张「委托」表。

```sql
-- 迁移 v277__task_participation_delegation.py（编号取当前最大 +1，现 276）
CREATE TABLE IF NOT EXISTS task_participations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(200) NOT NULL,
    participant VARCHAR(200) NOT NULL,
    role VARCHAR(200) NOT NULL DEFAULT 'required',   -- required | added | transferred_in
    outcome VARCHAR(200) NOT NULL DEFAULT 'pending', -- pending|accepted|rejected|skipped|transferred
    comment TEXT,
    decided_by VARCHAR(200), on_behalf_of VARCHAR(200), decided_at DATETIME,
    created_by VARCHAR(200), created_at DATETIME, updated_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_participation_task  ON task_participations(task_id, outcome);
CREATE INDEX IF NOT EXISTS idx_participation_actor ON task_participations(participant, outcome);

CREATE TABLE IF NOT EXISTS task_delegations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delegator VARCHAR(200) NOT NULL, delegate VARCHAR(200) NOT NULL,
    scope_type VARCHAR(200) NOT NULL DEFAULT 'any',  -- any|app|type|doc_ref_type
    scope_value VARCHAR(200),
    effective_from DATETIME, effective_to DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'active',   -- active|revoked|expired
    reason TEXT, created_by VARCHAR(200), created_at DATETIME, updated_at DATETIME
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_task_delegation
    ON task_delegations(delegator, delegate, scope_type, scope_value, effective_from);
```

**审批建任务只写既有字段**（`approval_task_service.create_task`，单事务）：

| 快照输入 | 落到哪 |
|---|---|
| `steps[0].approver_type='user'` 的 `approver_ref` | `tasks.executor_candidates`（数组）；仅一人时 `executor_assignee` 同值 |
| `steps[0].approve_mode` | `executor_config.completion_mode`（`any`/`all`） |
| `steps[0].sla_hours` | `tasks.sla` + `tasks.due_at`（见 §8.5） |
| `role/position/org` 型审批人 | 不落 candidates（组织未建模，**不臆造**），沿用 `{bo}:approve` + `role_apps` 可见性 |

**参与流水落行**：建任务时为每个 candidate 写一行 `role='required', outcome='pending'`；与 candidates **同函数双写**（§8.8 R8）。

**收件箱两处通用修正**（`meta/core/task_inbox.py`）：

- `_visible` 已含候选池分支（`:145` `is_candidate`），委托只需在该分支上扩「active 受托人」；
- `_derive_buckets` 的 `approval` / `todo` 分区判据从 `is_assignee` 扩为 `is_assignee or is_candidate`（`:159-166`）——否则加签人收不到待办。该修正对 claim 任务同样成立（同一语义）。

### 8.2 通用改派（转签，M4-1）

**决策 D-AP-15**：改派是**任务域能力**，不是审批专属。服务放 `meta/core/task_assignment.py`（与 `claim_task` / `resolve_assignment` 同级），审批只做准入 hook 与话术。语义 = 替换 `executor_candidates`，不改快照、不调 BO、不改 `doc_ref*`；旧参与行留痕 `transferred` 而非删除。

| 项 | 通用口径（对所有任务类型） | 审批 hook（附加，不替代） |
|---|---|---|
| API | `POST /api/v1/tasks/<id>/assign`，body `{to_user, reason}`（`reason` 必填） | —— |
| 服务 | `task_assignment.reassign_task(ds, task_id, *, to_user, actor, reason)`：单事务内 ① 条件 UPDATE candidates/assignee ② 旧参与行 `outcome='transferred'` ③ 新参与行 `role='transferred_in', outcome='pending'` ④ worklog | —— |
| 准入 | ① actor ∈ `executor_assignee` / `executor_candidates` / active 受托人 **或** admin；② 任务非终态（`done`/`failed`/`cancelled` → `409`） | 额外要求 `status='waiting_approval'` 且 `type='approval'` |
| 目标校验 | 目标 ≠ 当前 assignee；目标非空 | 目标 ≠ `tasks.created_by`（四眼基准，`decision_effect.py:265-267`）；目标具备 `{bo}:approve` 或为 admin ⇒ 否则 `409` |
| 不变量 | `executor_candidates` 是**唯一**「谁能做」真源；`assign_policy` / `sla` / `due_at` / `inputs` / `doc_ref*` 一律不动 | 快照 `steps[0].approver_ref` 只作历史记录，不回写 |
| 失败语义 | 任务不存在 `404`；无准入 `403`；终态/目标非法 `409`；未登录 `401` | —— |

**注意**：改派**不**改 `assign_policy`。原 `claim` 任务改派后仍是 `claim`（新人成为唯一候选），原 `direct` 任务仍是 `direct`。若业务要「改派后必须由新人认领」，属策略变更，不在 M4。

**审计**：走 `task_worklogs`（`entry_type='note'`，`task_event_schema.py:57-59` 已含 `note`），detail `{action:'reassign', from:[...], to, reason}`。**需新增 `record_worklog()`**（与 `record_transition` 同级，直接 INSERT `task_worklogs`）——仓内现只有 `record_transition` 顺带写 worklog（`task_event_schema.py:221-236`），无独立写入口。**不扩 `EVENT_TYPES`**（`task_event_schema.py:52-54` 仅 5 类，扩枚举牵动事件表 YAML 与既有断言）；改派不是状态迁移，无需伪造 `task_events`。

### 8.3 参与与归并（加签 / 会签，M4-2）

**决策 D-AP-14**：完成口径由 `executor_config.completion_mode`（既有 JSON 字段，零迁移）决定：`any`（默认，首个有效决策即完成）/ `all`（全部 required+added 参与人行 approve 才算完成）。归并在**参与流水层**完成，不新增任务状态、不新增批次表。

| 概念 | 通用口径 | 审批落点 |
|---|---|---|
| `any` | 首个 `outcome='pending'` 参与人 approve ⇒ 走现有 `decide_and_apply`（一次生效 → 任务终态） | BO 生效一次 → `done` |
| `all` | 当前**全部** `required`+`added` 行 approve 才通过；未齐 ⇒ 200 `{status:'partially_approved', remaining, votes}`，**不调 BO、不改任务状态** | 会签 |
| 加签 | `POST /api/v1/tasks/<id>/participate` `{participant, comment?}`：新增 `role='added', outcome='pending'` 行；对 `any` 任务**不改** completion_mode（加签人在 any 下等同第二可投人） | 加签后若 completion_mode 已为 `all` ⇒ 计入；若业务要「加签即全员」，由前端显式传 `require_all=true` 改 `executor_config.completion_mode='all'`（一次写入，走 `record_worklog`） |
| reject | 任一 pending 行 reject ⇒ 立即 `decide_and_apply(reject)`，其余 pending 行置 `skipped`（fail-closed） | 任务 `failed` |
| 重复投票 | 同一 `participant` 对同一任务重复投票 → `409`（该行已非 pending） | —— |
| 准入 | actor ∈ 该任务 `required`/`added` 参与人 **或** active 受托人 **或** admin | 另需通过 D-AP-06 权限事实（`{bo}:approve`） |

**决策端点语义扩展**（协议本体不改，`meta/services/task_participation.py` 薄层负责归并判定）：

```
POST /tasks/<id>/decision
  → 200 {status:'completed', task_status, decision, action_id, receipt}     # 已生效
  → 200 {status:'partially_approved', remaining:[participant...], votes:[...]} # all 未齐，无副作用
  → 409 / 502 语义不变
```

**前端**：抽屉新增「参与人进度」列表（姓名 + 角色 + 状态 + 意见）与「加签」按钮；`status='partially_approved'` 提示「已记录你的意见，等待其他参与人」并刷新进度，**不关闭抽屉、不提示成功**。

**明确不做**：跨 `step_no` 串行推进（step1 通过 → step2 待审）。现网 `steps` 多行实际语义是金额分段（`_load_steps` 按 `min/max_amount` 过滤），串行推进需要「部分生效」与任务中间态，属引擎级改造，留 M5。

### 8.4 委托（M4-3）

**决策 D-AP-16**：委托是**准入期身份展开**（任务域能力），不改任务归属、不写 `executor_assignee`。

| 项 | 口径 |
|---|---|
| API | `GET/POST/PUT/DELETE /api/v1/task-delegations[/<id>]`（`delegator` 强制 = 当前用户，admin 可代配）；`GET /api/v1/task-delegations/active` 返回「我受托于谁」 |
| 有效期 | `effective_from ≤ now ≤ effective_to`（空 = 无限）；`status='active'` |
| 范围 | `scope_type='any'` 全任务；`app` / `type` / `doc_ref_type` + `scope_value` 精确匹配任务对应列（审批只是 `doc_ref_type={bo}` 的一个使用例） |
| 决策准入 | actor 候选身份 = 自身 + active 受托的 delegator；命中受托 ⇒ 参与行 `decided_by=actor, on_behalf_of=delegator` |
| 可见性 | 受托人经 §8.1 的「active 受托人」分支在 `_visible` 派生可见，不写 `executor_assignee` |
| 撤销 | 改 `status='revoked'` 立即失效；已投的票保留 `on_behalf_of` 审计 |
| 约束 | 不允许委托给提交人（`created_by`，四眼）；`delegator ≠ delegate`；同一 `(delegator, delegate, scope_type, scope_value)` 有效期不得重叠（唯一索引兜底） |

### 8.5 SLA（M4-4）

**决策 D-AP-17**：SLA 记录与告警全部复用任务域现有底座（`tasks.sla` / `task_slas` / `sla_ladder` / `task_tick`），**只新增「超时改派」这一执行动作**，且默认关闭。

| 环节 | 口径 | 复用点 |
|---|---|---|
| 开单 | 建任务时若当前步骤 `sla_hours` 非空：写 `tasks.sla = {target_seconds: h*3600, warn_at_pct: 80, alert_at_pct: 95, grace_seconds: 0, on_breach: null}` 与 `tasks.due_at = created_at + h`，随后 `open_sla_for_task(task_id)` 按快照开单 | `sla_ladder.py:281-301`（读 `tasks.sla` + `due_at` 开单，**不接受外部传 due_at**） |
| 告警 | `task_tick` 现有 escalate 段推进梯级；收件箱 `alert` 分区已消费（与任务类型无关） | `task_tick.py:94-98`、`task_inbox.py:114-132` |
| 超时改派 | 仅当 `executor_config.sla_on_breach = {action:'reassign', fallback_assignee:'u-x'}` 时，`task_tick` 消费 `scan_escalations` 返回的 `action='reassign'` 项（`sla_ladder.py:70-82,102-113`），复用 §8.2 `reassign_task` 改派一次，写 worklog `{action:'sla_reassign'}` | 新增 `apply_sla_reassign`（`task_tick` 内，通用，非审批专属） |
| 默认 | 未声明 `fallback_assignee` ⇒ `on_breach` 保持 `notify`，行为与现状完全一致（只告警，不动任务） | —— |
| 边界 | 不改 `sla_ladder`「只产出动作意图」的分层纪律（`sla_ladder.py:113`）；执行只在 `task_tick` 统一分支，不另立调度器 | —— |

### 8.6 API 汇总

| 方法 | 路径 | 里程碑 | 权限 |
|---|---|---|---|
| POST | `/api/v1/tasks/<id>/assign` | M4-1 | 任务参与人 / 受托人 / admin（审批附加四眼 + `{bo}:approve`） |
| POST | `/api/v1/tasks/<id>/participate` | M4-2 | 任务参与人 / 受托人 / admin |
| GET | `/api/v1/tasks/<id>/participations` | M4-2 | 任务可见者 |
| POST | `/api/v1/tasks/<id>/decision`（扩展返回 `partially_approved`） | M4-2 | 不变（D-AP-06） |
| GET/POST/PUT/DELETE | `/api/v1/task-delegations[/<id>]` | M4-3 | 本人 / admin |
| GET | `/api/v1/task-delegations/active` | M4-3 | 登录用户 |

**权限码**：四个新端点一律**不新增权限码**，沿用仓内既有口径——登录态 + 任务级准入（与 `POST /tasks/<id>/claim` 同构，`task_inbox_api.py:254-256` 即无权限码）；审批附加的 `{bo}:approve` 走既有动词权限。

新表若被 `sync_schema --generate` 覆盖，需在 `meta/schemas/` 增 `task_participation.yaml` / `task_delegation.yaml`（与既有 `task_event.yaml` / `task_worklog.yaml` 同目录同风格，`skip_auto_menu: true`、`skip_generic_api: true`），否则迁移内建表并登记 drift 白名单 —— 实施前用 `python -m meta.tools.sync_schema --generate` 实测决定（M1 同入口）。

### 8.7 分阶段验收（可执行）

| 阶段 | 交付 | 验收命令与断言 |
|---|---|---|
| **M4-1 改派**（✅ 已完成） | 两张表 + 建任务落参与行 + `reassign_task` + `/assign` API + `_visible` 委托分支 + 抽屉按钮 | `python d:\filework\test.py --file meta/tests/test_task_reassign.py`：① 改派后旧行 `transferred`、新行 `pending`、candidates/assignee 变更、worklog 一条 `reassign`；② 非参与人 409/403；③ 审批：目标无 `{bo}:approve` / 目标=提交人 409；④ 改派后决策仍按快照执行且 BO 仅调一次；⑤ 终态 409、未登录 401；⑥ **非审批任务**（`type='todo'`，`assign_policy='direct'`）改派后收件箱归属正确 |
| **M4-2 加签/会签**（✅ 已完成） | `/participate` + `task_participation` 归并 + `/participations` + 前端进度与 partial 处理 | `--file meta/tests/test_task_participation.py`：① `any` 首票调 BO 一次；② `all` 三人前两票 `partial` 且任务仍 `waiting_approval`、BO 调用计数 0；③ 第三票调 BO 一次且 `done`；④ 任一 reject 立即 `failed`，其余 `skipped`；⑤ `require_all=true` 加签后要求全员；⑥ 同人重复投票 409；⑦ 加签人收件箱可见；⑧ **非审批任务** `all` 模式下同逻辑成立（不调 BO） |
| **M4-3 委托**（✅ 已完成） | delegations CRUD + active 端点 + 准入展开 + `on_behalf_of` 审计 | `--file meta/tests/test_task_delegation.py`：① 区间内/范围匹配可投且记 `on_behalf_of`；② 区间外 / 范围不符 / 已撤销 / 非受托人 409；③ 委托给 `created_by` 409；④ 委托人自己仍可投；⑤ 收件箱可见性；⑥ `scope_type='type'` 对非审批任务生效 |
| **M4-4 SLA**（✅ 已完成） | 建任务开单 + 超时改派（默认关闭） | `--file meta/tests/test_task_sla.py`：① `sla_hours=4` ⇒ `task_slas` 有行且 `due_at=created+4h`；② `now+3.5h` 扫描 warn 且收件箱 `alert`=1；③ `now+5h` + `fallback_assignee` ⇒ assignee 变更 + worklog；④ 未配置 ⇒ 只告警不改派；⑤ 非审批任务同配置同样改派 |
| **M4-5 前端**（✅ 已完成） | 抽屉参与人进度 / 改派 / 加签 / 委托设置页 / SLA 倒计时 | `npx vitest run src/views/TaskCenter src/services` + `npm run build`：partial 不关抽屉不报成功、无权限不渲染动作、委托表单区间校验 |
| **回归（每阶段）** | 不改既有协议 | `--file meta/tests/test_task_decision_api.py`（6）、`test_document_approval.py`（25）、`test_task_inbox.py`（14）、`test_approval_policy_admin.py`（20）、`test_task_assignment.py` / `test_task_claim.py`（既有认领链路）；`check_permission_consistency.py` R7 保持空 |

**M4-1 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 测试 | `test_task_reassign.py` 16 passed；回归 `test_task_inbox.py` 14 passed |
| 实现 | `meta/core/task_assignment.reassign_task`（单事务：条件 UPDATE candidates/assignee + 旧行 `transferred` + 新行 `transferred_in` + worklog）；`meta/api/task_assign_api.py` `POST /api/v1/tasks/<id>/assign`（`reason` 必填）；迁移 v277 两表 |
| 审批 hook | 目标无 `{bo}:approve`（或 `*`）⇒ 409；目标 = `created_by` ⇒ 409（四眼）；非数字 id ⇒ fail-closed |
| 通用性 | `type='todo'` + `assign_policy='direct'` 改派后收件箱归属正确（无审批分支） |
| 修复 | `task_assign_api` 成功路径原 `json_response(ok(...))` 会对 Flask Response 二次 jsonify ⇒ 改为返回 `({success, data}, 200)` |

**M4-2 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 测试 | `test_task_participation.py` **13 passed**；回归 `test_task_decision_api.py` 6、`test_document_approval.py` 25、`test_task_inbox.py` 14、`test_task_reassign.py` 16 全绿 |
| 新增文件 | `meta/services/task_participation.py`（薄层：`participate` / `participations_view` / `decide_with_participation`）；`meta/api/task_participation_api.py`（`POST /participate`、`GET /participations`）；`meta/tests/test_task_participation.py` |
| 改动文件 | `approval_task_service.py`（`executor_config.completion_mode` 由 `policy_snapshot.steps` 最小 `step_no` 的 `approve_mode` 派生，仅 any/all）；`task_decision_api.py`（决策改调 `decide_with_participation`，新增 403/404/409/400 映射）；`server.py`（注册蓝图） |
| 归并口径 | `any`：首票即 `decide_and_apply`（BO 一次）→ 任务终态；`all`：未齐 ⇒ **200** `{status:'partially_approved', remaining, votes}`，**不调 BO、不改任务状态**；任一 reject ⇒ 立即 `failed` + 其余 `skipped` |
| 加签 | `POST /participate` 默认 `participant=actor`；`require_all=true` 在**同一事务**内追加参与行 + candidates + `completion_mode='all'`（写 worklog `action=completion_mode`）；已是参与人再传 `participant` ⇒ 409 |
| 准入 | admin 短路回协议（无参与行时）；否则 actor ∈ `required`/`added` 参与人 或 active 受托人；审批任务另需 `{bo}:approve`（`reviewer_permission is not True` ⇒ 403） |
| 委托代投 | 已接入：`record_outcome(decided_by=actor, on_behalf_of=delegator)`；受托人 = `created_by` ⇒ 409（四眼）——M4-3 只需补 CRUD API 与独立测试文件 |
| 非审批任务 | `all` 模式同归并逻辑，但 `effect_applied=False`、不调 BO、任务状态不变（TC_PART_008） |
| 偏离说明 | ① `decide_and_apply` 返回不含 `remaining` ⇒ `setdefault("remaining", [])`；② `DataSource` 无 `query()`，统一 `execute().fetchall()` + `zip(columns, row)`；③ 参与表缺失 ⇒ 完全退回 `decide_and_apply`（legacy 语义不变） |

**M4-3 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 测试 | `test_task_delegation.py` **9 passed**；回归 `test_task_inbox.py` 14、`test_task_participation.py` 13、`test_task_decision_api.py` 6 全绿 |
| 新增文件 | `meta/api/task_delegation_api.py`（GET/POST `/task-delegations`、GET `/task-delegations/active`、PUT/DELETE `/task-delegations/<id>`）；`meta/tests/test_task_delegation.py` |
| 改动文件 | `meta/core/task_delegation.py` 新增 `list_active_for_delegate`（active 端点用，读路径已有）；`meta/core/task_inbox.py`：`_visible` 支持传入 `is_delegate` 复用判定，`_derive_buckets` 增 `is_delegate` 使受托人进入 `todo`/`approval` 分区（仅对非直接参与人查询一次）；`meta/server.py` 注册蓝图 |
| CRUD 语义 | 撤销 = `DELETE` → `status='revoked'`（保留审计行）；`include_inactive=true` 可回看；`delegator` 强制 = 当前用户（admin 可代配，`created_by` 记 admin）；区间重叠 / 自委托 / 范围缺值 / 区间倒置 → 400；他人配置 → 403；不存在 → 404 |
| 准入展开 | 决策层沿用 M4-2 已接入的 `active_delegators_for`（有效期 + `any/app/type/doc_ref_type` 匹配）；`on_behalf_of` 只写参与行，不动 `executor_assignee`/`candidates` |
| 四眼 | 委托给任务 `created_by` 在任务侧拒绝（409），配置期不做任务判定（委托为全局配置） |
| 通用性 | `scope_type='type'` + 非审批任务（`type='story'`）代处理成立；收件箱 `todo` 可见 |

**M4-4 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 测试 | `test_task_sla_reassign.py` **8 passed**；回归 `test_task_sla.py` 18、`test_task_tick.py` **11**、`test_document_approval.py` 25、`test_task_participation.py` 13、`test_task_reassign.py` 16 全绿 |
| 新增文件 | `meta/tests/test_task_sla_reassign.py` |
| 改动文件 | `meta/services/approval_task_service.py`：`create_task` 内 `_resolve_sla`（取 `steps` 最小 `step_no` 的 `sla_hours`）派生 `tasks.sla` + `tasks.due_at = created_at + h*3600`（`grace_seconds=0`、`on_breach=null`），事务内 seed 参与行后 `_open_sla` 调 `open_sla_for_task`；`meta/core/task_tick.py`：新增 `apply_sla_reassign` 并在 escalate 段调用，返回体/`counts` 增 `sla_reassigns` |
| 开单 | 仅当当前步骤 `sla_hours > 0` 才开单；`_open_sla` 失败只 warning，不阻断建任务（表缺失/异常安全） |
| 默认关闭 | `tasks.sla.on_breach` 固定 `null`（只记录）；改派唯一开关是 `executor_config.sla_on_breach = {action:'reassign', fallback_assignee:'u-x'}`。缺动作/缺兜底人 ⇒ 只告警（TC_SLA_R_005/006） |
| 梯级消费 | 命中 `RUNG_BREACH(3)` 才动作；`rung >= RUNG_DEAD_LETTER(4)` 不改派（死信走工单升级）；`grace_seconds=0` 时不产生死信梯级，测试可稳定落在 T3 |
| 幂等/留痕 | 改派复用 `reassign_task(actor='system', admin=True, target_permitted=True if type=='approval')` + 补 `task_worklogs` 的 `detail.action='sla_reassign'`；重复 tick 不重复改派（梯级单调） |
| 通用性 | 非审批任务（`type='story'`）配置相同同样改派；`target_permitted` 仅审批任务传 `True`（配置即授权，spec §8.5） |
| 偏离说明 | ① spec 原文写「消费 `scan_escalations` 返回的 `action='reassign'` 项」，实现改为「到达 breach 梯级 + `executor_config` 声明 reassign」——因为 `tasks.sla.on_breach` 快照按 §8.5 设计固定为 `null`，若以 finding 的 action 为准则永远不会触发；`executor_config` 是唯一开关（更符合「未配置即现状」）；② `DataSource` 无 `query()`，统一 `execute().fetchall()` + `zip(columns,row)`；③ `test_task_tick.py` 三处 `counts` 精确断言补 `sla_reassigns: 0`（返回体新增键） |

**M4-5 验收记录（2026-11-15）**：

| 项 | 结果 |
|---|---|
| 测试 | `npx vitest run src/services/__tests__/taskService.spec.js src/views/TaskCenter/__tests__/TaskDetailDrawer.spec.js` ⇒ **49 passed**（service 30 / drawer 19，新增 11 例）；`npm run build` 成功（chunk-cycles OK） |
| 改动文件 | `src/services/taskService.js`：新增 `fetchParticipations` / `reassignTask` / `participateTask` / `fetchDelegations` / `createDelegation` / `revokeDelegation`（`apiV1.delete` 首次使用）+ 纯函数 `normalizeParticipations` / `canReassignTask` / `formatSlaRemaining` / `validateDelegationForm`；`src/views/TaskCenter/TaskDetailDrawer.vue`：到期行追加 SLA 倒计时、新增「参与人进度 / 改派 / 加签 / 我的委托」四块 + 样式 |
| 合同对齐 | 参与进度直接读 `participations_view` 契约：`participants`（含 `on_behalf_of`）/ `counts`（`pending|accepted|rejected|skipped|transferred`）/ `remaining` / `completion_mode`；前端不做二次归并 |
| partial 不误报 | 加签返回 `status='partially_approved'` ⇒ 抽屉提示「已加签，会签未齐」，任务与抽屉均不关闭；`done` 由后续投票 / 其它消费者触发刷新 |
| 无权限不渲染 | `canReassignTask` 与服务端准入同口径（admin / 当前执行人 / 候选人；终态一律不渲染）；`canParticipate` 限参与人（admin / 执行人 / 候选人）且任务非终态；服务端仍做最终裁决 |
| SLA 倒计时 | `formatSlaRemaining(due_at)` ⇒「剩余 3h 30m」/「已超时 2h 0m」，逾期红色；非法/空 `due_at` 返回 null 不渲染 |
| 委托设置 | 抽屉内「我的委托」：列表（`delegator` 由服务端强制为当前用户）+ 新建（`delegate` / `scope_type` / `scope_value` / 区间）+ 撤销（DELETE → revoked）；表单先经 `validateDelegationForm`（受托人必填、不能委托自己、范围需值、区间不倒置），与后端 `create_delegation` 同口径 |
| 偏离说明 | spec 写「委托设置页」，实现为抽屉内「我的委托」区块（用户级配置随抽屉展开，避免新增路由/页面骨架）；如需独立页可在后续无风险迁移，接口与校验已就绪 |

### 8.8 M4 风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R6 | 迁移编号 v277 与并行 worktree 撞号 | 迁移冲突 | 实施前取 `meta/migrations` 当前最大号 +1（现 276）；撞号方顺延并同步 |
| R7 | `partially_approved` 是 200，前端误判为审批成功 | 用户以为已通过 | 仅在 `completion_mode='all'` 返回；前端按 `data.status` 分支；测试覆盖 |
| R8 | 参与流水与 `executor_candidates` 双写漂移 | 「谁能做」出现两个答案 | **`executor_candidates` 为唯一分配真源**，`executor_assignee` 仅作当前锁定的投影，`task_participations` 只记「谁做了什么」；建任务/改派/加签在**同一函数同一事务**内双写，测试断言一致 |
| R9 | 委托展开导致越权 | 受托人看到/处理不该看的单 | 只在决策准入与 `_visible` 派生展开，不写权限、不改归属；区间/范围严格匹配，撤销即失效 |
| R10 | 会签「全员通过才生效」放大卡单 | 时长不可控 | 加签需当前参与人主动发起；SLA（M4-4）+ 改派（M4-1）提供逃生口；不默认开启 `all` |
| R11 | 能力通用化冲击非审批任务 | 既有 claim/direct 链路回归 | 新增字段一律走 `executor_config` 可选键；`_derive_buckets` 放宽为 `is_assignee or is_candidate` 需同时验证 claimable 分区不变；M4-1~M4-4 每个测试文件都含 1 条非审批任务用例（见 §8.7） |

### 8.9 二次检查与元数据驱动审计（2026-11-15）

**判定口径**：表/列/索引的唯一真源是 `meta/schemas/*.yaml`（BO）；平台运维表（`task_idempotency` / `task_async` / `task_slas` / `task_participations` / `task_delegations`）按既有惯例在 Python 内用内联 `MetaObject` 建表（`_f` / `_idx` / `_build_*_meta` / `ensure_*_tables`），**不入 YAML、不进 `generated_schema.sql`**。`drift_check` 与 `sync_schema --check` 均只扫 YAML 对象，因此平台表不入 YAML 不产生漂移；`test_metadata_completeness` / `test_schema_single_source` 亦无「DB 表必须进 YAML」断言。

| 审计项 | 结论 |
|---|---|
| 内联 MetaObject ↔ 迁移 DDL | `task_participation.py` / `task_delegation.py` 的字段、索引与 `v277` DDL 逐项一致（含 `on_behalf_of`、`uidx_task_delegation` 复合唯一键） |
| 启动装配 | `manage_api.init_services` 依次 ensure task / event / idempotency / async / sla / participation / delegation，headless 场景同样兜底；`server.py` 蓝图按 `is_module_enabled('tasks')` 门控（禁用即真 404） |
| 数据源一致 | ensure 与三个新蓝图（assign / participation / delegation）均落平台库（`get_meta_db_path()`），无跨库错配 |
| `tasks` 主表 | `task.yaml` 已含 `due_at` / `sla` / `doc_ref_type` / `doc_ref_id` 与 `idx_tasks_approval_ref`；快照 `generated_schema.sql` / `.schema_version.json` 已同步（M1 完成），M4 未再 ALTER 主表 |
| 元模型门禁 | `python -m meta.tools.lint_metamodel` exit 0（relations 217/0、actions 23/0、permissions 24/0、doc-flow 14/0、capabilities 216/0）；`sync_schema --check` / `check_permission_consistency.py` 的非零项全部落在 `vendor_invoice*` 等无关域，属既有基线，非 M4 引入 |
| 委托生效链路 | `is_delegate_for` → `task_inbox` 可见性、`task_participation._delegators` → 决策代投（`on_behalf_of` 留痕 + 四眼拦截）、`list_active_for_delegate` → 前端「我的委托」，三处同源 |

**补修（本轮）**：`meta/tests/test_g7_task_domain_meta_migration.py` 的 v154 基线未随 M1 更新，导致 3 例红（`doc_ref_type` / `doc_ref_id` / `idx_tasks_approval_ref` 缺失）。已补齐 `EXPECTED_COLUMNS["task"]`、`EXPECTED_INDEXES["task"]`、`expected_index_names`，重跑 **15 passed**。该红是本 spec M1 遗留，不是 M4 引入。

**评估后不修（记录）**：
1. `task_slas` 无独立迁移，依赖 F2 既有启动期 `ensure_sla_tables`；与 v277 建表模式不完全对称，但属 M4 之前的既有事实，改动收益低于风险。
2. `update_delegation` 调整 `effective_to` 时只校验区间倒置，不校验同关系跨行重叠；创建路径已有重叠拒绝（`create_delegation`），更新路径属低频入口。
3. SQLite 中 `scope_value` 为 NULL 时 `uidx_task_delegation` 不去重（NULL 互不相等）；应用层用 `COALESCE(scope_value,'')` 做重叠/重复判定，已覆盖该语义。
4. 审批策略 `steps` 实为**金额分段**（`_load_steps` 按 `min_amount/max_amount` 过滤，同为并行审批人集合），不存在顺序推进，因此「后续步骤不重开 SLA」不是缺口。

---

## 9. 通用任务引擎（Task Engine）：Fusion 对标与审批通用化

### 9.1 结论先行

1. **运行时已经是通用的**：`tasks` + `task_participations` + `task_delegations` + `task_slas` + 改派/加签/委托/SLA 全部按 `task_id` 运作，与 `tasks.type` 无关（§8 已验收）。审批没有专属引擎。
2. **不通用的是定义层**：`approval_policies → approval_policy_steps → approval_policy_conditions` 三张表把「谁、在哪个阶段、满足什么条件时、做什么动作」绑死在审批（`scope_bo` / `trigger_action` 语义 + 表名）。
3. **结论**：不新建第二套引擎、不改表名，定义层补 **4 列**（`approval_policies.task_type`、`approval_policy_steps.stage_no / action_type / routing_json`）+ 主表补 1 列（`tasks.stage_no`）+ 扩展 2 个枚举（`approver_type` / `approve_mode`），把「步骤」升级为 Fusion 的「Stage + Participant + Action」。**审批 = `task_type='approval'` 的一个实例**，工单、复核、巡检、催办复用同一套定义与流转。
4. **零回归目标**：现有 25 例 `document_approval*` 与 15 例 G7 基线不改——`stage_no` 默认 1、`approve_mode` 现有取值语义不变、唯一索引重建等价。

### 9.2 Oracle Fusion AMX 四层对标（F）

| 层 | Fusion（F） | 我们的现状（C） | 差距 |
|---|---|---|---|
| 定义容器 | Approval Task（绑定业务对象） | `approval_policies(scope_bo, trigger_action)`，[v178 L40-73](file:///d:/filework/excel-to-diagram/meta/migrations/v178__approval_rule_model.py#L40-L73) | 无 `task_type`，只服务审批 |
| 阶段 Stage | 绑 collection（header / lines） | 无 | `step_no` 是金额分段的**并行集合**，不是阶段（§8.9-4） |
| 参与者 Participant | Serial / Parallel / FYI + Voting Regime | `approve_mode ∈ any/all` + `approver_type` | 无知会（FYI）、无串行会签、无对象维度 |
| 规则 Rule | Condition + Action，按 Stage 生效 | `approval_policy_conditions`，单层 AND、策略级 | 无 `stage_no`、无 OR、`rule_predicate` 仅 13 个标量算子（[rule_predicate.py L21-38](file:///d:/filework/excel-to-diagram/meta/core/rule_predicate.py#L21-L38)） |
| 动作 Action | Approval required / Automatic / Information only | 只有「必审」 | 无自动通过、无抄送知会 |
| 取人 List Builder | 8 类算法 + 6 个路由参数 | 仅 `approver_type='user'` 出候选人（[approval_task_service.py L136-146](file:///d:/filework/excel-to-diagram/meta/services/approval_task_service.py#L136-L146)） | role/org/position 为空池；缺 manager / manager_chain / job_level / expression / 发起人自选 |

**判尺**：Fusion 的「下一级」= `Start With` 选经理；「多级」= `Number of Approval Levels` / `Minimum Job Level`（可跳级）；「多级对象」= Stage 绑定的 collection。三者是**三个独立维度**，不能用一个 `step_no` 表达。

### 9.3 「下一级 / 多级」解析链：Fusion 6 参数 → 我们的字段

| Fusion 路由参数 | 落到 `routing_json` 的键 | 解析实现（仓内真源） |
|---|---|---|
| Approval Chain Of | `approval_chain_of` | 起始主体：`employee` / `position` / `org`；默认取发起人的 employee |
| Start With | `start_with` | `manager`（直属主管，一跳）/ `position` / `self` / 指定 user（值口径 = `users.username`，不支持 user id / 显示名）；映射 `employee.manager_employee_id`（[employee.yaml L54](file:///d:/filework/excel-to-diagram/meta/schemas/employee.yaml#L54)，自关联汇报线，服务层已校验不成环） |
| Number of Approval Levels | `levels` | `1` = 只下一级；`N` = 上溯 N 跳；`0/null` = 到顶 |
| Minimum Job Level | `min_job_level` | 沿链过滤，职级不足则继续上溯（= Fusion 的跳级） |
| Top Worker in Hierarchy | `top_worker_id` | 到顶的哨兵（通常是 CEO / 法人负责人），命中即停 |
| Include | `include[]` | `requester`（含发起人）/ `self`（含当前人）/ `skip_empty`（空节点跳过不阻塞） |

组织维度另有 `org_scope ∈ self | descendants`：子树人员走 [`org_service.get_org_subtree_user_ids` L122](file:///d:/filework/excel-to-diagram/meta/services/org_service.py#L122) / [`get_all_descendant_orgs` L206](file:///d:/filework/excel-to-diagram/meta/services/org_service.py#L206)。

**硬边界（D-GT-02）**：`CHILDREN_OF / DESCENDANTS_OF / ANCESTORS_OF`（[condition_parser.py L68-70](file:///d:/filework/excel-to-diagram/meta/core/condition_parser.py#L68-L70)）**只用于对象维度与数据权限**，不得混入取人；取人一律走 §9.5 的 resolver，避免规则求值退化成数据库递归。

### 9.4 目标模型（v278 草案：仅加列 + 重建唯一索引）

| 表 | 新列 | 类型 / 默认 | 语义 |
|---|---|---|---|
| `approval_policies` | `task_type` | `VARCHAR(200) DEFAULT 'approval'` | 定义服务的任务类型：`approval` / `work_order` / `review` / `inspection` / `reminder` …；审批只是枚举值之一 |
| `approval_policy_steps` | `stage_no` | `INTEGER NOT NULL DEFAULT 1` | 阶段序号（顺序推进）；现有数据全为 1 = 单阶段并行集合，语义与今天完全一致 |
| `approval_policy_steps` | `action_type` | `VARCHAR(200) DEFAULT 'approve'` | `approve`（必审）/ `auto`（自动通过，不建人工待办）/ `notify`（知会/抄送，只读可见） |
| `approval_policy_steps` | `routing_json` | `TEXT` | §9.3 的 6 个路由参数 + 取人器参数（`org_scope` / `position_ref` / `expression`） |
| `tasks` | `stage_no` | `INTEGER NOT NULL DEFAULT 1` | 运行时当前阶段（进 `task.yaml`，走元数据派生 + 快照同步）；现有任务全为 1，语义不变 |

**枚举扩展（零 ALTER，列本身无 CHECK 约束）**：
- `approver_type`：`user` / `role` / `org` / `position`（现有）＋ `group` / `manager` / `manager_chain` / `position_hierarchy` / `job_level` / `expression` / `initiator_choice`（发起人自选）。
- `approve_mode`：`any`（= first responder wins）/ `all`（= consensus）＋ `serial`（串行会签，按 `step_no` 逐个签）。**不新增 `voting` 列**——避免 `approve_mode` 与 `voting` 双真源。
  - **阶段聚合口径**：同一 `stage_no` 内任一步 `approve_mode='all'` ⇒ 整个阶段按 `all` 结算，否则 `any`（`task_stage` / `approval_task_service` 同一规则）。
  - **`serial` 本轮未实现**：`completion_mode` 仅消费 `any` / `all`；按 `step_no` 逐个签需要引擎级调度（一次只暴露一个待办），留待后续迭代，当前传入 `serial` 按 `any` 处理。
- `routing_json.quorum`（可选，P：Camunda `completionCondition`）：N 中 M 通过，如 `{"required": 2}`；缺省时 `any`=1、`all`=全部，与现状等价。**已实现**：建任务 / 阶段推进时把同阶段各步最大值写入 `executor_config.quorum_required`；`decide_with_participation` 以「当前候选池内通过票数 ≥ required」判定是否 settle（未达 ⇒ `partially_approved` 并回传 `quorum_required`）。

**索引变更**：`uidx_approval_policy_step` 由 `(policy_id, step_no)` 改为 `(policy_id, stage_no, step_no)`（[v178 L108-110](file:///d:/filework/excel-to-diagram/meta/migrations/v178__approval_rule_model.py#L108-L110)）。现有数据 `stage_no=1`，新旧唯一约束等价，无数据冲突。

**决策 D-GT-01（不改表名）**：改名为 `task_definitions / task_stages / task_participants` 会牵动 25 例测试、`generated_schema.sql` 快照、规则中心前端与历史审计记录；通用性由 `task_type` + 语义文档获得，代价从「迁移风险」降为「命名不一致」。若后续出现**非审批模板的真实需求**（需要独立管理界面/独立权限域），再做一次 rename 迁移，届时数据模型已稳定。

### 9.5 取人器（Resolver）统一契约

新增 `meta/core/task_assignee_resolver.py`（单职责、可注册）：

```
resolve(participant, ctx) -> Resolution(candidates: list[str], explain: list[dict], source: str)
ctx = {task_type, object_type, record: Mapping, initiator, org_id, employee_id}
```

| `approver_type` | resolver 真源 | 说明 |
|---|---|---|
| `user` | `approver_ref` 逗号/数组名单 | 现行为不变 |
| `role` / `group` | `user_role` / 组关系表 | 组型 = 业务编组，role 型 = 权限角色 |
| `org` | `org_service` 子树 + `routing_json.org_scope` | 支持 `self` / `descendants` |
| `position` | `employee.position` | 岗位持有人 |
| `manager` | `employee.manager_employee_id` 一跳 | 「下一级」 |
| `manager_chain` | 上溯 `levels` 跳 + `min_job_level` 跳级 + `top_worker_id` 哨兵 | 「多级」 |
| `position_hierarchy` | 岗位层级链 | Fusion Position Hierarchy |
| `job_level` | 按职级阈值过滤 | Fusion Minimum Job Level |
| `expression` | `rule_predicate.evaluate` | 复用统一谓词，不新写求值器 |
| `initiator_choice` | 提交时 `inputs.approver_selection` | 发起人自选；服务层通道已备（`create_task(approver_selection=…)` → `ctx` → `inputs`），**上游提交入口未接（P3）**；范围校验未实现，按传入名单取人（残差见 §9.8） |

**约束**：
1. **输出 `explain` 与 `rule_predicate` 同构**（`field/op/expected/actual/passed`）→ 前端可直接展示「为什么是这个人 / 为什么一个人都没有」。
2. **空池不再静默返回 `[]`**，必须带原因，写入 `executor_config` **双键**（两者互补，不互相替代）：
   - `assign_explain`：判定链数组（`field / op / expected / actual / passed / step_no`，与 §9.5 约束 1 同构），回答「哪一步、筛掉了谁」；
   - `assign_reason`：枚举单值（`no_member` / `level_exhausted` / `missing_manager` / `no_such_role` / `unsupported_approver_type` / `no_data_source`），回答「为什么一个都没有」，供前端一句话说明。
3. `approval_task_service._derive_candidates` 由「只认 user」改为调用 resolver；调用点唯一。
4. **权限不替代、也不被替代**（D-AP-06 不变）：resolver 回答「可能是谁」，`{bo}:approve` / `task:handle` 回答「能不能做」。
5. **批量查询**：一次拉 `employee`（按 org/职级）后内存上溯，禁止逐人递归查询（R14）。

### 9.6 流转规则已通用（无需改造）

| 能力 | 实现 | 依赖 `type='approval'`？ | 结论 |
|---|---|---|---|
| 改派 / 转签 | `task_assign_api` → `tasks.executor_assignee` | 否 | 通用 |
| 加签 / 会签 | `task_participation` + `executor_config.completion_mode` | 否 | 通用 |
| 委托 | `task_delegations` + `is_delegate_for` | 否 | 通用 |
| SLA | `task_slas` + `tasks.due_at / sla` | 否 | 通用 |
| 阶段推进（M5 新增） | `tasks.stage_no`（元数据驱动加列）| 否 | 通用 |

→ 因此「审批流流转规则」**已经是通用规则**：任何任务类型只要有 `stage_no` 与参与者，就能复用改派/加签/委托/SLA/阶段推进。

### 9.7 通用化边界：必须留在审批的 4 个钩子

| 归属 | 内容 |
|---|---|
| 审批专属 | ① 条件求值对象 = 单据行（`scope_bo` → `_load_record`）；通用任务从 `inputs` 取字段 |
| 审批专属 | ② `approval_status` 投影回 BO（D-AP-05） |
| 审批专属 | ③ 权限 `{bo}:approve`；其他任务用 `task:handle` |
| 审批专属 | ④ `decision_actions` 指向 BO Action（`meta/core/decision_effect.py`） |
| **任务通用** | 建任务、阶段模型、参与者与投票制、取人器、改派、加签、委托、SLA、参与流水、通知 |

即：**审批 = 通用任务 + 4 个钩子**，不需要第二套引擎。

### 9.8 分期 M5（已完成 2026-11-15）

| 阶段 | 内容 | 验收 |
|---|---|---|
| ✅ M5-1 | v278 迁移：定义层 4 列（`approval_policies.task_type`；`approval_policy_steps.stage_no / action_type / routing_json`）+ `tasks.stage_no`（`task.yaml`）+ 唯一索引重建 + 快照同步 + 枚举校验 | `test_g7_task_domain_meta_migration.py` 绿；25 例 `document_approval*` 全绿 |
| ✅ M5-2 | resolver 注册表 + `_derive_candidates` 切换 + 空池 explain | `meta/tests/test_task_assignee_resolver.py` 30 passed（11 算子 + 空池 + 无 N+1 + `start_with=self/指定用户` / `approval_chain_of=org` / 岗位起点 / 首阶段 quorum 落配置） |
| ✅ M5-3 | 阶段推进：决策后 `stage_no+1`、重派生候选人、重开 SLA | `test_task_stage_advance.py` 8 passed（两阶段：候选人换人 / `stage_no=2` / SLA 新单 `stage-N` / 阶段 SLA 取各步最小值 / 会签口径聚合 / CAS 防并发连跳） |
| ✅ M5-4 | `action_type` = `auto` / `notify` | `test_task_action_type.py` 8 passed（auto 不建人工待办直接推进；notify 只读、投票被拒、不计会签分母） |
| ✅ M5-5 | 前端：阶段进度（`阶段 2/3`）+ 取人解释 + 空池原因 | `TaskDetailDrawer.spec.js` 26 passed（阶段进度 / assign_explain / 空池中文原因 / auto·notify 徽标 / 知会隐藏按钮 / notify 隐藏改派加签 / 无快照仍显示动作徽标）；`npm run build` 通过；详情接口回传 `stage_no` 并有 `test_task_inbox.py` 断言 |
| ✅ M5-fix | 审计补丁：阶段聚合（SLA min / 任一步 `all` 即 `all`）+ CAS 防连跳 + `quorum_required` 结算分母 + notify 前后端全只读 + resolver `levels` 缺省到顶 / `start_with` / `approval_chain_of` + 空池双键 `assign_explain`/`assign_reason` | `test_task_stage_advance.py` 8 / `test_task_participation.py` 16 / `test_task_assignee_resolver.py` 30 / `test_task_action_type.py` + `test_task_inbox.py` + `test_task_decision_api.py` 28 全绿；关联回归 147 passed；`TaskDetailDrawer.spec.js` 26 passed |

**风险**

| # | 风险 | 缓解 |
|---|---|---|
| R12 | 唯一索引重建期间并发写 | 迁移在单事务内 DROP/CREATE；仅影响 DDL 时刻（dev 单库）；发布窗口执行 |
| R13 | 阶段推进重复开 SLA 单 | 幂等键 `(task_id, stage_no)`；`open_sla_for_task` 查重 |
| R14 | resolver 退化为 N+1 | 批量拉 `employee` 后内存上溯；测试断言查询次数 |
| R15 | 表名与语义不一致（`approval_policies` 存非审批模板） | 文档 + API 层统一称「任务定义」，表名保留；出现真实需求再 rename（D-GT-01） |

**复核残差（2026-11-16，只读审计；均不阻塞 M5 验收）**

| # | 残差 | 现状 |
|---|---|---|
| Q1 | `initiator_choice` 生产路径恒空池 | `create_task(approver_selection=…)` → `ctx` → `inputs` 通道已备，但全仓无调用方（提交 API / UI 未接）；`resolve_stage` 不注入 `ctx['record']`，`record.approver_selection` 兜底为死分支；「可见范围校验」未实现 |
| Q2 | `start_with` 指定用户只认用户名 | `_employee_id_of_user` 仅查 `users.username`；user id / 显示名一律 `missing_manager` |
| Q3 | `notify` 参与行恒 `pending` | seed 后无终态（跨阶段也不结算）；`remaining` 已按 `VOTING_ROLES` 排除，但 `participations_view.counts` 仍计入 ⇒ 前端计数出现「待处理 1」；参与人列表显示 `notify · 待处理`，与「只读知会」语义不符（展示噪声，按需收敛） |

### 9.9 二次竞品对标（P：6 家头部产品）

| 产品 | 模型分层 | 下一级 / 多级算法 | 审批 vs 通用任务 |
|---|---|---|---|
| ServiceNow | task 表族（incident / sc_task / change 同源）→ 审批规则或 Flow「Ask for Approval」→ `sysapproval_approver`（每人一条） | 人来自用户 / 组 / 角色 + 脚本；多级靠 Approval Rules 或引擎逐级推进；经理取 `sys_user.manager`，委托走 `sys_user_delegate` | **共用** task 基表、工作流、SLA；审批记录独立成表挂接任意 task |
| SAP BTP | Workflow(BPMN) → Step → Recipient（Responsible / Manager / Group / User）→ 任务实例（收件人 / 状态 / 到期） | 运行期解析 Recipient（经理字段 / 组 / 表单变量）；多级 = 多 Step 或循环；S/4 Flexible Workflow 用 release strategy 声明级数与取人 | Workflow 是**通用人任务引擎**（My Inbox）；审批只是场景之一；Flexible Workflow 为审批专有 |
| Salesforce | Approval Process → Step → Approver → Action；Flow Orchestration：Stage → Step（interactive / background）→ Work Item + Work Guide | 自动指派 / Queue / 按 `ManagerId` 逐级（Next Automated Approver）；级数写在 Step 或编排循环内 | **两套引擎**：Approval Process 绑记录；Orchestration 通用，正被 Flow 的 Approval Orchestration 收编 |
| Jira / JSM | Workflow → Status → Transition（Condition / Validator / Post-function）；Approval 是 status 上的一条属性 | 无内置汇报线解析，人靠自定义字段或 Automation 取 Manager；多级 = 多个 approval step | **共用** workflow 引擎（approval 复用 status / transition）；Automation 独立 |
| Camunda / Flowable | Process(BPMN) → User Task（assignee / candidateUsers / candidateGroups）→ multiInstance + completionCondition → Task（dueDate） | 无组织层级；取人靠表达式调服务；多级 = 子流程 / 循环 / call activity；stage ≈ embedded sub-process | **完全通用**：审批 = user task + completionCondition；SLA = dueDate；claim / delegate 是任务语义 |
| 飞书 / 钉钉 | 审批定义（表单 + 流程）→ 节点（审批 / 抄送 / 办理 / 条件分支）→ 审批人类型（直属主管 / 连续多级主管 / 角色 / 指定成员 / 发起人自选）→ 实例 + 任务 | 直属主管第 N 级（钉钉 ≤8 级）；连续多级主管 / 部门负责人 + **审批终点**（指定层级或用户组）；级数是节点参数 | **不共用**：飞书任务、钉钉待办是独立模型；差在引擎 / 状态机 / UI，人解析同源组织架构 |

**六家共识（P，反过来印证 §9.1 的结论）**

1. 「流程定义 → 运行实例 → 每人一条待办」三层骨架，六家一致 → 我们的 `policies/steps` ↔ `tasks` ↔ `task_participations` 同构。
2. 取人一律**运行期 Resolver**（角色 / 组 / 汇报线 / 岗位 / 脚本），由 YAML 声明 `approver_type` + `routing_json` 驱动 → §9.5 的插件式 resolver 是行业标准做法。**注意口径**：Resolver 只负责「可能是谁」，其 SQL 触及的 **BO 表名 / 列名必须来自元模型**（`table_name` / `db_column`，未声明时回退并留痕 warning）；平台内核表（如 `user_permission_sets`）直连属正常，见 §9.10。
3. 多级 = **循环 + 参数化边界**（级数或「终点」），而不是在表里写死 N 行 → §9.3 的 `levels` + `top_worker_id` 正确；也解释了为什么现有 `step_no` 写不下多级。
4. **Rule（条件）与 Action（需审 / 自动通过 / 仅通知）分离** → 印证 §9.4 的 `action_type` 三态。
5. 会签 / SLA / 委托 / 加签挂在**任务实例**，不挂流程定义 → 印证 §9.6 的运行时能力已通用。

**可直接借用的 5 个机制**

| 机制 | 来源（P） | 对本 spec 的作用 |
|---|---|---|
| 审批记录独立成表挂任意 task（`sysapproval_approver`） | ServiceNow | 印证 `task_participations` 方向正确：每人一条独立状态，天然支持逐人超时 / 委托 |
| `Recipient` 三分类（Responsible / Manager / Group）+ release strategy | SAP | 印证 §9.5 枚举命名；release strategy = 我们 `routing_json` 的级数声明 |
| `Stage → Step(interactive / background)` + `Work Guide` | Salesforce | 印证 `stage_no` + `action_type`（`auto` ≈ background）可脱离审批，承载工单 / 复核 / 巡检 |
| `multiInstance` + `completionCondition` + `candidateGroups` | Camunda | 会签比例参数化 → 落 `routing_json.quorum`，不新增列 |
| 「连续多级主管 + 审批终点」 | 飞书 / 钉钉 | 级数与组织变化解耦 → `top_worker_id` 即「终点」，`levels=0` 即「到终点为止」 |

**不采纳（记录）**

1. **Jira 的「无内置汇报线，人靠 Automation 取」**：我们要的是声明式取人（组织架构在平台内），脚本取人只作为 `expression` 兜底，不做唯一手段。
2. **Salesforce 的「审批与编排两套引擎」**：正是本 spec 要避免的分叉；单引擎 + 4 个审批钩子（§9.7）成本更低。
3. **ServiceNow 的「审批本身无原生 SLA」**：我们 SLA 挂任务实例，审批与工单共享，优于其挂接方式。
4. **Step 级独立版本与生效期**（调研指出的差距 #5）：我们以 policy 版本冻结快照（D-AP-07）已覆盖在途不回溯，step 级版本收益低、成本高，不采纳。

**参考链接（官方文档）**

1. [ServiceNow 文档门户](https://www.servicenow.com/docs/)
2. [ServiceNow｜Flow Designer Approvals Overview](https://www.servicenow.com/community/workflow-automation-articles/flow-designer-approvals-overview-workflow-automation-center-of/tac-p/3541586)
3. [SAP Workflow 官方文档](https://help.sap.com/docs/workflow)
4. [Salesforce｜ApprovalProcess（Metadata API）](https://developer.salesforce.com/docs/atlas.en-us.242.0.api_meta.meta/api_meta/meta_approvalprocess.htm)
5. [Salesforce｜Flow Orchestration Help](https://help.salesforce.com/s/articleView?id=sf.flow_orchestration.htm&type=5)
6. [Atlassian｜Configure advanced work item workflows](https://support.atlassian.com/jira-cloud-administration/docs/configure-advanced-issue-workflows/)
7. [Atlassian｜Configuring Jira Service Management approvals](https://confluence.atlassian.com/adminjiraserver112/configuring-jira-service-management-approvals-1688897276.html)
8. [Camunda｜User tasks](https://docs.camunda.io/docs/components/modeler/bpmn/user-tasks/)
9. [Camunda｜Multi-instance](https://docs.camunda.io/docs/components/modeler/bpmn/multi-instance/)
10. [飞书｜管理员设计审批流程](https://www.feishu.cn/hc/zh-CN/articles/360036163653)
11. [飞书｜审批功能更新日志（连续多级部门负责人）](https://www.feishu.cn/hc/zh-CN/articles/360049067392)
12. [钉钉｜Process design（流程设计）](https://help.dingtalk.io/approval/admin-process-design)

> 取证说明：Salesforce Flow Orchestration 官方 Help 为 JS 渲染，Stage / Step / Work Guide 结论由官方 PDF 与页面标题交叉确认；SAP 仅引用官方文档门户，Recipient 三分类语义来自公开产品资料，未编造条款。

### 9.10 存量规范化（2026-11-16，S1-S9）

> 起因：M5 复核确认「取人器直连 `employees` / `orgs`」属「YAML 声明表 + 直连 SQL」的合规形态，但全仓审计发现同类问题系统性存在——**BO 表名/列名在代码里靠 `entity + 's'` / `field_id` 猜**，YAML 改名即运行期静默错误。本节记录本轮收敛结果与划界。

**口径**

| 类别 | 判据 | 处置 |
|---|---|---|
| BO 业务表（`employees` / `orgs` / `purchase_orders` 等） | YAML 声明了 `table_name` / `db_column` | 必须经 `MetadataResolver` 解析；禁止字面量表名与 `+ 's'` 拼表 |
| 平台内核表（`users` / `user_permission_sets` / `tasks` / `task_events` / `audit_logs`） | 不属于 BO 元模型 | 允许直连与字面量，代码注释标注「平台内核表」 |
| 未声明回退 | YAML 未写 `table_name` | 允许约定复数回退，但**必须 warning 留痕**，不得静默 |

**改动清单**

| # | 文件 | 改动要点 |
|---|---|---|
| S1 | [`metadata_resolver.py`](../../meta/core/metadata_resolver.py) | 新增 `get_column_name(entity, field_id)`（`db_column` 优先 → `field_id`；未声明返回 None）；`get_table_name` 收敛为**严格语义**（未声明返回 None，由调用方回退留痕），并删除类内重复定义（此前后者覆盖前者导致严格版成为死代码） |
| S2 | [`task_assignee_resolver.py`](../../meta/core/task_assignee_resolver.py) | 新增 `_table(bo)` / `_col(bo, field)` 助手（未声明时 warning 一次）；11 处 SQL 全部参数化表名/列名（role / group / org / position / job_level / manager / manager_chain / initiator 等）；`user_permission_sets` 保留字面量并注释内核表；`_resolve_org` 去掉 `match.replace('o.', '')` 脆弱替换，统一 `cols` 字典 format |
| S3 | [`_descendant_subquery.py`](../../meta/core/_descendant_subquery.py) | `_TABLE_MAP = get_table_map()`（`hierarchies.yaml`）；FK 由 `get_hierarchy_chain()` 推导；未声明 warning 并返回 None |
| S4 | [`consistency_guard.py`](../../meta/core/consistency_guard.py) | 三处重复 `_get_table_name` 收敛为模块级 `_resolve_table_name()` |
| S5 | [`effective_intent_checker.py`](../../meta/core/effective_intent_checker.py) | 新增 `_table_of(bo)`（hierarchies 映射 → MetadataResolver → 约定回退），L279 / L301 改用 |
| S6 | [`audit_derived_fields.py`](../../meta/core/audit_derived_fields.py) | `_object_type_to_table_name` 改为 MetadataResolver 优先 + 显式回退映射 |
| S7 | [`enrichment_engine.py`](../../meta/core/enrichment_engine.py) | `_get_table_name` 改为 MetadataResolver 优先 + warning + 回退 |
| S8 | [`draft_batch_save.py`](../../meta/services/draft_batch_save.py) | 删除本地 `_TABLE_NAME_MAP`（其中 `relationship` 表名本就有误），改用 `MetadataResolver → get_table_map → {bo}s` |
| S9 | 本文档 | 回写 §9.9 第 2 条过度声明 + 本节 |
| 适配 | [`key_template_interceptor.py`](../../meta/core/interceptors/key_template_interceptor.py) | `get_table_name(base_type) or base_type`，保持原「未命中构造候选表」行为不变 |

**测试**

| 用例文件 | 覆盖内容 |
|---|---|
| [`test_metadata_resolver.py`](../../meta/tests/test_metadata_resolver.py) | `get_table_name` 未声明返回 None（原「回退实体名」断言已废弃）；`TestGetColumnName` 覆盖 `db_column` 优先 / 缺省 `field_id` / 未知字段或实体返回 None |
| [`test_task_assignee_resolver.py`](../../meta/tests/test_task_assignee_resolver.py) | 新增「元模型改名」fixture：注入 5 个改名 BO（`people` / `perm_sets` / `units` / `unit_members` / `staff_records`）后 role / group / org(descendants) / position / job_level 取人仍正确；并断言 SQL 不含旧表名（词边界匹配，避免 CTE 名 `scope_orgs` 误报） |

**验收命令**

```
python d:\filework\test.py --file meta/tests/test_metadata_resolver.py,meta/tests/test_task_assignee_resolver.py
# → 64 passed

python d:\filework\test.py --file meta/tests/test_effective_intents.py,meta/tests/test_enrichment_engine.py,meta/tests/test_enrichment_engine_cache.py,meta/tests/test_consistency_guard.py,meta/tests/test_key_template_interceptor.py,meta/tests/test_key_template_interceptor_rel.py,meta/tests/test_task_participation.py,meta/tests/test_task_stage_advance.py
# → 122 passed, 2 skipped
```

**划界（本轮未纳入的 P1/P2 项）**

| 位置 | 现状 | 未纳入原因 |
|---|---|---|
| `meta/core/runtime_dimension_resolver.py:569` | 维度表名走运行期缓存映射 | 属维度域，与任务/审批无耦合，单独排期 |
| `meta/core/_computed_count_clause.py:136/140/150` | 聚合子查询拼表名 | 属通用查询内核，改动面广，需独立回归 |
| `meta/core/persistence_interceptor.py:1316/1323` | 写入前表名推导 | 同上 |
| `meta/core/interceptors/key_template_interceptor.py:130/196` | 候选表 `[t, ts, tes]` 探测 | 属「表不存在时探测候选」逻辑，非 SSOT 解析，保留 |

### 9.11 取人解析行业复核与合理性确认（2026-11-16）

> 目的：确认 §9.5 取人器契约（声明式 `approver_type` + 运行期解析 + 快照冻结 + `assign_explain` 留痕 + 元模型表名）在头部产品中是否成立，并据此补决策与分期。

#### 9.11.1 结论

**合理性成立，不需要架构调整。** 五家产品的共同范式与 §9.5 一致：审批侧只声明「要谁」，由运行期引擎解析成具体人并**物化成审批实例/审批记录**；差异只在三点——解析的数据访问封装在哪一层、是否有规则试算、无审批人时如何兜底。对应处置见 §9.11.4。

#### 9.11.2 对标矩阵

| 维度 | 我们（`C`） | Oracle Fusion（`F`） | SAP（`S`） | Salesforce（`P`） | ServiceNow（`P`） | 飞书（`P`） |
|---|---|---|---|---|---|---|
| 审批人声明 | `steps[].approver_type` + `routing_json` | 审批规则 + list builder 类型 | 责任规则（Rule Resolution） | `ApprovalProcess` 每步 approver | `Ask for Approval` 的 Rules | 审批人类型（上级 / 部门负责人 / 角色） |
| 支持类型 | user / role / group / org / position / job_level / manager / manager_chain / position_hierarchy / expression / initiator_choice | Supervisory、Job Level、Position，自定义 manager 类型自动出现 | 职能 / 岗位 / 组织 / 自定义函数模块 | 指定用户 / manager hierarchy / queue / 记录上的 User 字段 | 用户 / 组 / 前序步骤输出 | 上级 / 部门负责人 / 角色 / 连续多级部门负责人 |
| 解析时机 | 建任务时 `resolve` 并冻结 | AMX 运行期生成审批列表 | workflow step 运行期 agent determination | 提交时生成审批实例 | Flow 运行期 | 提交时生成审批实例 |
| 物化载体 | `policy_snapshot` + `executor_config.assign_explain` / `assign_reason` + candidates | AMX 审批列表 | workflow container | 审批实例 + Approval History | `sysapproval_approver` 行 | 审批实例 |
| 无审批人 | 空池 + `assign_reason`，由策略层决定 | 规则校验（Validate）+ 模拟 | 规则测试/模拟 | 按 step 的 rejection 行为 | 须显式配 rejection rules，否则流程停在 waiting | — |
| 规则试算 | 未做（§1.1 只规划了「策略命中试算」） | 有（Simulate Approval Rules，多模块） | 有（Testing and Simulating Rules） | 元数据矩阵可直接预览 | Flow 测试/调试 | — |

#### 9.11.3 数据访问归属（对「取人器直连 SQL」的定性）

| 产品 | 找人时的数据访问 | 对 §9.5 的映射 |
|---|---|---|
| SAP | 责任规则调 `RH_STRUC_GET` 等函数模块 / CDS view 取组织与主管；社区性能实践进一步建议预计算 + 共享内存缓存 | 取人器 ≈ 该封装层；表名/列名走元模型（§9.10 S2） |
| ServiceNow | `GlideRecord` 查 `sys_user_group` / `sysapproval_approver` | 平台 API 访问平台表 |
| Oracle | AMX list builder 内部上溯主管链，业务模块不写 SQL | 引擎内部完成 |
| Salesforce | 层级字段 / queue / User 字段由平台解析 | 元数据驱动 |

→ **头部同样直连表，但直连的是「平台的表 + 平台的访问组件」。** 我们的取人器扮演的就是这个平台组织服务角色；§9.10 收口后其 SQL 的表名/列名全部来自元模型，定性为「平台内部能力」，不属于「审批业务代码硬编码 SQL」。

#### 9.11.4 三处差距与处置

| # | 差距 | 头部证据 | 处置 |
|---|---|---|---|
| G1 | 缺取人试算/模拟 | Oracle「Simulate Approval Rules」（HCM 21D / HR 22A / Compensation 23A）、SAP「Testing and Simulating Rules」 | **新增 D-AP-13**：不做新引擎，复用 `resolver.resolve` + `assign_explain` 提供试算，归 P1（M6 候选） |
| G2 | 无审批人兜底语义未配置化 | ServiceNow 明确「无匹配审批人须配 rejection rules，否则停在 waiting」；Oracle 有规则 Validate | **新增 D-AP-14**：策略层增加 `on_empty`（`fail` / `skip` / `to_admin`）；resolver 保持中立只报原因，归 P2（与 D-AP-10 同批） |
| G3 | 取人结果未预计算/缓存 | SAP 建议预计算 manager 分配 + SHMA 缓存 | **新增 D-AP-15**：暂不引入。当前仅 4 个审批 BO、单任务一次解析；出现「批量建任务（导入/定时）」再评估，记为观察项不立项 |

#### 9.11.5 新增决策

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D-AP-13** | 取人试算 = 输入 `{object_type, record_id, policy_id?}` → 复用 `resolver.resolve` 输出候选人与 `assign_explain`，不落任务 | 新建模拟引擎 | `explain` 契约已与 `rule_predicate` 同构，试算只是「不写库地跑一遍」，零新逻辑 |
| **D-AP-14** | 空池兜底由策略层 `on_empty` 决定：`fail`（默认，保持 fail-closed）/ `skip`（自动通过并留审计）/ `to_admin` | resolver 内自动兜底 | 解析器只回答「谁」，兜底属业务策略；混进 resolver 会另造一套语义 |
| **D-AP-15** | 取人结果不做预计算缓存；仅当出现批量建任务场景再立项 | 建任务时预计算并缓存链条 | 当前调用量级为「一次任务一次解析」，预计算收益低于失效维护成本（与 SAP 场景的差异：SAP 是批量单据 + 长链） |

#### 9.11.6 与既有决策的一致性复核

| 既有决策 | 头部对应 | 结论 |
|---|---|---|
| D-AP-07 快照冻结、策略变更不回写 | Oracle / ServiceNow / Salesforce 均物化审批实例，在途按发起时规则走完 | 一致，保留 |
| D-AP-06 权限与取人分离 | 头部同样区分「谁是审批人」与「该用户是否有权限操作」 | 一致，保留 |
| N-AP-03 不做会签多任务，改「单任务 + 参与流水归并」 | 头部有 parallel / unanimous / first-response | 功能等价、实现更轻，保留 |
| §9.5 空池必须带原因 | 头部以 rejection rules / 规则校验表达同一约束 | 我们更细（逐条 `passed`），保留 |

#### 9.11.7 证据来源

- Oracle：[Approver Types](http://docs.oracle.com/en/cloud/saas/human-resources/25b/faucf/approver-types.html)、[How You Define Approval Rules](https://docs.oracle.com/cloud/saas/financials/24b/faiex/how-you-define-approval-rules.html)、[Various Aspects of Approval Rules](https://docs.oracle.com/en/cloud/saas/procurement/25d/oapro/various-aspects-of-approval-rules.html)、[Using Approval Management](https://docs.public.oneportal.content.oci.oraclecloud.com/en/middleware/fusion-middleware/bpm/12.2.1.3/bpm-develop/using-approval-management.html)、[HCM 21D 审批规则模拟](https://www.oracle.com/webfolder/technetwork/tutorials/tutorial/cloud/r13/wn/hcmcommon/releases/21D/21D-hcm-common-wn.htm)、[HR 22A Simulate Employment Approval Rules](https://www.oracle.com/webfolder/technetwork/tutorials/tutorial/cloud/r13/nfs/ghr/releases/22A/22A-hr-nfs.htm)
- SAP：[Configure SAP Workflow to Send Purchasing Documents to the Right Approver](https://sapinsider.org/configure-sap-workflow-to-send-purchasing-documents-to-the-right-approver/)、[Using Function Modules in Responsibility Rules](https://signatov.com/sap-workflow-using-function-modules-in-responsibility-rules/)、[Agent Determination Rules（Testing and Simulating Rules）](https://www.sap-press.com/project-management-with-sap-project-system_3614/toc/433)
- Salesforce：[ApprovalProcess Metadata](https://developer.salesforce.com/docs/atlas.en-us.242.0.api_meta.meta/api_meta/meta_approvalprocess.htm)、[Design Dynamic Approvals That Can Scale](https://www.salesforce.com/blog/metadata-driven-approvals/)
- ServiceNow：[Flow Designer Approvals Overview](https://www.servicenow.com/community/workflow-automation-articles/flow-designer-approvals-overview-workflow-automation-center-of/tac-p/3541586)、[Ask for Approval（flow action）](http://raw.githubusercontent.com/ServiceNow/ServiceNowDocs/australia/markdown/build-workflows/workflow-studio/ask-approval-flow-designer.md)、[无匹配审批人需配 rejection rules](https://www.servicenow.com/community/itsm-forum/in-the-flow-design-how-to-exclude-one-person-from-approving-the/td-p/2487836)
- 飞书：[管理员设计审批流程](https://www.feishu.cn/hc/zh-CN/articles/360036163653-%E8%AE%BE%E8%AE%A1%E5%AE%A1%E6%89%B9%E6%B5%81%E7%A8%8B)、[审批节点基础配置](https://ae.feishu.cn/hc/zh-CN/articles/147857102726)、[Lark 审批管理员手册](https://www.larksuite.com/hc/zh-CN/articles/360034502513-lark-%E5%AE%A1%E6%89%B9%E7%AE%A1%E7%90%86%E5%91%98%E6%89%8B%E5%86%8C)

### 9.12 存量规范化第 2 步（2026-11-16，二次审计后执行）

#### 9.12.1 判据复核

§9.10 只覆盖「取人器 + 层级子查询」；二次审计把判据扩到**整个 `meta/` 的运行期 SQL**，并明确区分两类同名现象：

| 现象 | 判定 | 处置 |
|---|---|---|
| 运行期用 `entity + 's'` / `'ies'` **猜**表名 | 违反 SSOT（改名即静默查错表） | 改为 `MetadataResolver.get_table_name(entity)`，未声明才回退并留痕 |
| 模块级 `X_TABLE = 'xxx'` 常量**字面量** | 违反 SSOT（同表多处各写一份） | 改为**访问函数**（调用时解析），保留字面量作兜底 |
| 迁移脚本 `vNNN__*.py` 内的表名常量 | 冻结快照（DDL 本身即历史事实） | 不动 |
| `condition_parser.py` / `hierarchy_loader.py` 的静态兜底 | 刻意静态（解析器自身的引导 fallback） | 不动 |

#### 9.12.2 改动清单（批次 A-F，共 25 文件）

| 批次 | 文件 | 改法 |
|---|---|---|
| A | `meta/core/runtime_dimension_resolver.py`（`_to_table_name`） | 先取 `get_table_name(bo_id)`，未声明才复数化 + `warning` |
| A | `meta/core/interceptors/persistence_interceptor.py`（关联目标表） | `get_table_name(rel_target_entity)`，回退原有复数化 |
| B | `amount_trace_service.py` / `amount_recalc_service.py` / `batch_selection_policy_service.py` / `batch_selection_service.py` / `query/computed_subqueries.py` | 本地表名字典改为 `(实体, 兜底表)`，运行期解析；`_COUNT_CHILDREN_MAP` 改为三元组 `(子实体, 兜底表, 外键)` |
| C | `condition_permission_service.py`（`_get_display_name_for_id`） | 字段→实体映射 + `get_column_name`；**顺带修存量 bug**：`organizations` / `departments` 表并不存在（库内实为 `orgs`），且显示列 `domain_name`/`org_name` 等均不存在（实为 `name`） |
| D | `resource_inheritance_engine.py` | `RESOURCE_TABLE_MAP.get(dim, f'{dim}s')` 全部收敛到 `_resource_table()`（链声明 → 元模型 → 复数化） |
| D | `org_context_resolver.py` | `_row_org('projects'|'sales_orders'|'locations')` 改传实体；`orgs` / `sales_order_lines` 直连改 `_table()` |
| D | `core/association/fallback.py` | `AUDIT_CHILD_CONFIG` 子项改**实体名**，表名由 `_audit_child_table()` 运行期解析（`audit_logs.object_type` 仍写解析后的表名，语义不变） |
| E | `api/audit_api.py` / `api/stats_api.py` | `meta['table']` 与 `_safe_count(ds,'products'…)` 改 `_business_table()` / `_stats_table()` |
| F | `receipt_service` / `handling_unit_service` / `serial_number_service` / `shipment_service` / `vendor_invoice_match_service` / `transfer_order_guard_service` / `purchase_order_guard_service` / `purchase_order_fulfillment_service` / `requisition_po_conversion` / `project_task_guard` / `vendor_payment_term_service` / `document_approval_decision` | 模块级 `*_TABLE` 常量 → 访问函数（`_line_table()` 等），全量引用点同步；`project_task_guard` 访问器保持公开（被 `sales_order_guard_service` 引用） |

**交叉引用同步**（常量改名后必须一起改，否则 ImportError）：

- `meta/services/receipt_actions.py`：`SCHEDULE_TABLE` → `_schedule_table()`
- `meta/core/interceptors/vendor_invoice_guard_interceptor.py`：`LINE_TABLE` → `_line_table()`
- `meta/services/sales_order_guard_service.py`：`project_task_guard.TASK_TABLE` → `project_task_guard.task_table()`

#### 9.12.3 验证

```powershell
python d:\filework\test.py --file meta/tests/test_receipt_service.py,...（22 个受影响文件）
```

结果：**492 passed, 1 skipped, exit 0**（耗时约 41s，端口 3014）。

已确认的**基线失败**（与本次改动无关，属集成模块 P1 的 fixture 漂移，另行处理）：
`meta/tests/test_shipment_single_fact.py` 6 例 —— 测试自建 `doc_flow_rule` 表缺 `condition` 列，而 `doc_flow_rule_store.upsert_rules` 已按 `31d61199` 的新 DDL 写入。

#### 9.12.4 保留项（P2，已知问题，不在本轮修）

| 位置 | 现状 | 原因 |
|---|---|---|
| `condition_permission_service._get_user_org_info` | 仍查 `users.department_id / organization_id` | 生产 `users` 实为 `primary_org_id`，整段在异常保护内静默返回空；属业务口径问题（部门=组织层级），需产品确认后单独改，避免误改权限范围 |
| `dimension_scope_engine.py` / `view_dependency_guard.py` | 复数化兜底 | 兜底仅命中未注册维度，风险低 |
| `import_export_service.py` 若干处 | 导入映射内置表名 | 属导入模板声明，随模板版本走 |
| `condition_parser.py` / `hierarchy_loader.py` | 静态兜底 | 解析器引导层，刻意保留 |

**结论**：BO 业务表的运行期表名/列名已全部经 `MetadataResolver`（或层级声明）解析，字面量仅作为「未声明」兜底且均带可读回退；平台内核表（`users` / `user_permission_sets` / `tasks` / `audit_logs` / `approval_policies`）保有直连注释，符合 §9.10 三分类口径。

### 9.13 任务域二次检查与头部产品对标（2026-11-16）

> 触发：对「流转规则配置 / 实例流转详情 / 审批专属 UI / 批量单据任务处理 / task 对象模型的动作与服务」做二次检查，并以 Oracle Fusion、SAP 为主参照细化方案。本节为设计，**不改代码**。

#### 9.13.1 仓内现状（C）

| # | 检查点 | 现状 | 证据 |
|---|---|---|---|
| 1 | 流转规则配置 | 规则中心「审批策略」页签可编辑：元数据表单 + **裸 JSON 条件** + 行内步骤表（`step_no/approver_type/approver_ref/approve_mode/min_amount/max_amount/sla_hours`）+ 命中试算 | `src/views/RuleCenter/ApprovalPolicyPanel.vue:83-209,220-304`；挂载 `RuleCenterPage.vue:274-280` |
| 2 | 实例流转详情 | `TaskDetailDrawer` 只读消费 `inputs.policy_snapshot`：审批链 `<ol>`、阶段 chip、`conditions_explain`、取人依据、`task_events` 活动流 | `TaskDetailDrawer.vue:12-15,145-258,349-362,494-503` |
| 3 | 审批专属 UI | 仅任务抽屉内 `v-if="isApproval"` 块（通过/驳回/退回修改、审批链、条件解释、单据跳转）；**无独立审批中心**；单据详情页无审批区，`approval_status` 仅作普通列 | `TaskDetailDrawer.vue:145,155-233`；`src/router/modules/system.js:48`；`purchase_order.yaml:166,1110,1484` |
| 4 | 批量处理 | 收件箱 `for-await` **串行**逐条调 `POST /tasks/:id/decision`；502 标可重试并汇总「成功 N/失败 M」；**无权限预判、无进度、无上限**；任务域无批量端点 | `useTaskInbox.js:87-107`；`taskService.js:126-139`；`TaskInboxPanel.vue:24-75,142` |
| 5 | 任务动作/服务 | 11 态 / 5 type / 18 条迁移；动作全走专属路由、未进 action registry；**cancel 无端点**、`hold/release` 无 REST、`claimed` 无退出路径 | `meta/core/task_state_machine.py:54-82`；`task_hold.py:319`；`meta/api/task_inbox_api.py` |

#### 9.13.2 头部对标矩阵（F / S / P）

| 维度 | Oracle Fusion | SAP | ServiceNow / Salesforce | 对本次的结论 |
|---|---|---|---|---|
| 规则配置 | Transaction Console → **Approval Rules** 页签 → Configure Rules（参与者、路由规则、金额区间）`F` | Flexible Workflow 在 Fiori 应用内配置步骤/条件/升级与委托 `S` | ServiceNow Flow Designer `Ask for Approval`；Salesforce `ApprovalProcess` 元数据（steps / entry criteria / allowRecall / allowedSubmitters）`P` | 我们的「策略 = 条件 + 串行步骤 + 金额分段」结构对齐；差在**条件编辑体验**，不在模型 |
| 实例流转详情 | Approval History 同时给出「已审批人 + 当前处理人 + 后续审批人」；Document History 记录 Submitted/Approved/Rejected/Returned/Reassigned `F` | My Inbox 按后端下发 decision options 渲染动作；Workflow Instance Monitor 看实例 `S` | Salesforce 记录页 Approval History / Flow 的 Approval Trace 组件 `P` | 我们缺**三步态标记**（已完成/进行中/待处理）与「谁在何时批的」合并视图 |
| 决策入口位置 | 决策在 BPM Worklist / 通知，**单据页只给历史与当前处理人** `F` | 决策在 My Inbox，单据页展示审批状态 `S` | Salesforce 例外：记录页内直接 Approve/Reject（其为 record-centric 架构）`P` | 单据页应做**只读投影 + 跳任务**，不做第二决策入口 |
| 批量 | 单据侧无批量审批，管理员用 Transaction Console 处理卡单 `F` | My Inbox 多选能力弱，主流逐条 `S` | ServiceNow My Approvals「Actions on selected rows」把 sys_ids 交服务端批量处理；也可「分组审批」聚合为一条 `P` | 小批量前端串行可接受；但需**上限 + 权限预判 + 逐条结果** |
| 任务动作 | 系统动作 escalate / reassign / delegate / pushback / withdraw / suspend / resume；**动作随状态收窄**（suspended 仅 resume/withdraw；组任务须先 claim）`F` | My Inbox 标准动作 claim / release / forward `S` | — | 动作必须**由状态机声明并下发**，前端不得按 type 硬编码 |

#### 9.13.3 差距判定

| ID | 等级 | 差距 | 影响 |
|---|---|---|---|
| G-13-1 | P1 | 单据详情页无审批上下文（`approval_status` 投影无消费方） | 用户看到「审批中」却不知道谁在批、批到第几步，必须去待办里找 |
| G-13-2 | P1 | 动作不由状态机声明：cancel 无端点、`hold/release` 无 REST、`claimed` 无退出 | 状态机有迁移但无入口；领取后弃单只能等超时回收 |
| G-13-3 | P1 | 批量审批无权限预判 / 无进度 / 无数量上限 | 批量里 403/409/502 混在一起，只显示计数，用户无法定位 |
| G-13-4 | P2 | 条件配置仅裸 JSON，无字段选择与即时校验 | 配置门槛高，错 JSON 只在保存时暴露 |
| G-13-5 | P2 | 流转详情不标当前步、无三步态；`hit_policy=false` 无原因 | 与 Oracle Approval History 差距最大的一点 |
| G-13-6 | P2 | `policy_snapshot` 无 schema 字段，仅约定写入 `inputs`（2026-11-16 已实施，见 §9.13.6.5） | 结构靠约定，缺校验 |

#### 9.13.4 细化方案

**9.13.4.1 P1-1 单据侧只读审批投影**

- 位置：BO 详情页状态区（`ObjectPage` 顶部），新增只读块；不新增独立页面、不新增审批中心（延续 N-AP-02）。
- 数据：`GET /tasks?doc_ref_type={bo}&doc_ref_id={id}`（若 `task_query.list_tasks` 不支持这两参数则补两个过滤参数）+ `inputs.policy_snapshot` + `GET /tasks/{id}/events`。**不新增资源端点**。
- 展示：审批状态徽标（读投影列）、当前处理人、阶段 n/总量、最近 3 条事件、「查看审批任务」跳任务抽屉。
- 不做：单据页直接通过/驳回（保持单一决策入口，避免绕过四眼与 `effect_key` 幂等）。
- 前端复用：`AssociationSection` 的分区外壳 + `taskStatus.js` 文案；不新建审批专用组件目录。

**9.13.4.1.1 实施设计（2026-11-16 已实施）**

> 判尺：零新增资源端点（只补 `GET /tasks` 过滤参数）+ 不新建审批组件目录（复用 `AssociationSection` 自定义取数器分支）+ 可见性 fail-closed 且**管理员不是可见性后门**。

**后端（2 文件 + 2 测试）**

| # | 文件 | 改动 |
|---|---|---|
| B1 | `meta/core/task_query.py` | `list_tasks()` 增参 `doc_ref_type` / `doc_ref_id` / `actor`；`_TASK_COLUMNS` 追加 `executor_candidates, assign_policy, doc_ref_type, doc_ref_id`（尾部四列，`_row()` 同步追加下标）；WHERE 追加两列等值条件；`actor` 非空时用 `meta.core.task_inbox._visible(task, actor=..., role_apps=None, actor_roles=None, data_source=ds)` 逐行过滤，`total` 取过滤后条数（单据维度量级 ≤ 200，不下推 SQL） |
| B2 | `meta/api/task_inbox_api.py` | `task_monitor_service()` 增 `doc_ref_type/doc_ref_id`：`is_admin` → 原全量口径；非 admin → **必须**同时提供两参数（缺一 403），且 `actor=_actor(user)` 走行级可见性；`task_monitor_route` 读取 `request.args` 两参数 |
| B3 | `meta/tests/test_task_query_read.py` | 新增：doc_ref 命中/不命中；`doc_ref_type` 为空的历史任务不被命中；`actor` 可见性三通道（assignee / created_by / 候选）命中、无关用户为空 |
| B4 | `meta/tests/test_task_api.py` | 新增：非 admin 无 doc_ref → 403；非 admin + doc_ref 但不可见 → 空 items；admin 走全量；非 admin 只给一个参数 → 403 |

**前端（4 文件 + 1 单测）**

| # | 文件 | 改动 |
|---|---|---|
| F1 | `src/services/taskService.js` | `fetchTasks()` 透传 `docRefType/docRefId`；新增纯函数 `buildApprovalProjection(task, events)`（输出 `{statusLabel, tone, assignee, stage, stageTotal, events: 最近3条倒序, legacyRef}`）便于单测 |
| F2 | `src/components/common/ObjectPage/AssociationSection.vue` | 新增分支 `customFetcher === 'approval_progress'`（与 `target_change_requests` 同构）：`fetchTasks({type:'approval', docRefType: objectType, docRefId: String(objectId), pageSize: 20})` 取 `updated_at` 最新一条；`fetchTaskEvents(task.id)`（默认 200，升序）后 `slice(-3).reverse()`；模板块：状态徽标（`statusTone` → el-tag：muted→default / info→info / warning→warning / danger→danger / success→success）、当前处理人 `task.assignee || '待分发'`、`第 {{stage}} / {{stageTotal}} 阶段`（`stageTotal` = `inputs.policy_snapshot.steps` 的 `stage_no` 去重数，缺省 1）、最近 3 条事件（`event_type` + `actor` + `occurred_at`）、「查看审批任务」按钮；历史兜底：`!task.doc_ref_type || !task.doc_ref_id` ⇒ 隐藏按钮 + 提示「历史审批任务未关联单据引用」；空任务 ⇒ 「暂无审批任务」；在 `watch(() => props.objectId, …, {immediate:true})` 与 `refresh()` 各加一条分支 |
| F3 | `src/components/common/DetailPage/DetailPage.vue` | `computedSections` 在 form sections 之后、`rule_trace` 之前 push：`detailConfig.approval_progress.enabled` 时 `{key:'approval_progress', label, icon:'check', type:'association', association:'approval_progress', assocName:'approval_progress', customFetcher:'approval_progress', readonly:true, display:'always', pageSize:1}`（= ObjectPage 顶部状态区；未声明该键的 BO 零影响） |
| F4 | `src/components/ArchWorkspaceNew.vue` | `onMounted` 读 `route.query.task` ⇒ `openTaskDetail(id)`，随后 `router.replace` 清 query（`/system/task-management` 为 admin-only，普通用户跳转落点只能是工作台 `/`） |
| F5 | `src/services/__tests__/taskService.spec.js` | `fetchTasks` doc_ref 透传断言 + `buildApprovalProjection` 用例（状态文案/阶段总数/事件截取倒序/历史兜底） |

**YAML（4 文件）**：`purchase_order` / `transfer_order` / `requisition` / `service_request` 的 `ui_view_config.detail` 增 `approval_progress: {enabled: true, label: 审批进度}`。

**验证**

```powershell
python d:\filework\test.py --file meta/tests/test_task_query_read.py,meta/tests/test_task_api.py,meta/tests/test_task_state_machine.py
npx vitest run src/services/__tests__/taskService.spec.js
```

三场景：① 采购订单 `submitted` → 详情页顶部见「审批中 + 处理人 + 阶段 n/总量 + 最近 3 条事件」；② 点击「查看审批任务」→ 工作台打开同一任务抽屉；③ 撤回后单据回退 `draft` 且任务 `cancelled`，投影块转为终态文案。

**9.13.4.2 P1-2 动作表 + 端点补齐**

1. `meta/core/task_state_machine.py` 新增 `TASK_ACTIONS`（**静态声明，非注册表**）：

```
action → {allowed_from: [...], permission: 'task:claim'|'{bo}:approve'|..., endpoint: 'POST /tasks/{id}/claim'}
claim / release / start / decision / participate / reassign / delegate
/ hold / resume / cancel / withdraw
```

2. 新端点 `GET /tasks/{id}/actions`：按 `status + type + 当前用户权限` 返回可用动作；前端按返回渲染按钮（替代 `TaskDetailDrawer` 与 `TaskInboxPanel` 的 type 硬编码）。
3. 补 `POST /tasks/{id}/cancel`：`created_by` 或 admin；允许 `pending/ready/claimed/in_progress/failed/waiting_approval` → `cancelled`（**已实施**：迁移表补 `ready/claimed/failed/waiting_approval → cancelled` 四行）。
4. 审批走 `POST /tasks/{id}/withdraw`（不叫 cancel）：仅 `created_by` 且**无任何有效 approve** 时允许；任务 → `cancelled`，单据 `approval_status` 回退（副作用落 `document_approval_decision`，沿用幂等键语义）。**已实施**：见 §9.13.6 第 3 条。
5. `hold/release` 暴露 REST（`task_hold.py` 已有实现，加两个薄端点；**已实施**：`POST /tasks/{id}/hold` 与 `POST /tasks/{id}/resume`）。
6. 实施顺序：先 2（零副作用）→ 3/5 → 4（有单据副作用，单独测试）。

**9.13.4.3 P1-3 批量护栏（不新增批量端点，延续 D-AP-12）**（2026-11-16 已实施，见 §9.13.6.2）

- 选中 > 50 条时禁止批量并提示分批（避免串行长时间占用）。
- 批量前用 `GET /tasks/{id}/actions`（或一次性拉当前用户可审批 BO 集合）过滤掉不可决策项，403 在点击前就消失。
- 并发上限 4（简单 Promise pool），保留逐条结果明细：成功 / 失败原因（403/409/502）/ 可重试。
- 幂等仍由后端 `{task_id}:{attempt}` 保证，重试不产生双生效。

**9.13.4.4 P2 条件配置复用现有构建器**（2026-11-16 已实施，见 §9.13.6.3）

- `ApprovalPolicyPanel` 条件区接 `ConditionRuleBuilder`（已存在，系统管理页在用），输出契约不变（同一 JSON 落 `approval_policy_conditions`），并保留「切到 JSON」开关。
- 步骤区补两项校验：相邻步 `min_amount/max_amount` 不重叠且不断档；`step_no` 连续。都在保存前本地校验，不新增后端规则。

**9.13.4.5 P2 实例流转三步态**（2026-11-16 已实施，见 §9.13.6.3）

- 数据源：`policy_snapshot.steps` + `task_events` + `task_participation.participations_view`；**不新增 API**。
- 渲染：每步 `已完成 / 进行中 / 待处理` 三态，已完成步附实际处理人与时间（来自参与流水/事件），当前步高亮；`hit_policy=false` 显示「未命中策略，回落默认链」等具体原因。
- 与 9.13.4.1 的只读投影共用同一渲染片段（一个组件两处用，避免第三份审批链实现）。

#### 9.13.5 决策

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D-AP-16** | 单据页只做只读审批投影，不做第二决策入口 | 单据页加通过/驳回按钮 | Oracle/SAP 均把决策留在 worklist；双入口会绕过四眼与 `effect_key` 幂等 |
| **D-AP-17** | 动作由 `TASK_ACTIONS` 声明并下发 `GET /tasks/{id}/actions` | 前端按 `type` 硬编码按钮 | Oracle BPM 动作随状态收窄；硬编码在新增动作/状态时必漏改 |
| **D-AP-18** | 审批用 `withdraw`（撤回）而非 `cancel` | 直接复用 cancel | Salesforce `allowRecall` / Oracle BPM withdraw 语义；撤回要带单据回退副作用，取消不承诺 |
| **D-AP-19** | 批量保留前端串行，加 50 条上限 + 并发 4 + 权限预判 | 新增服务端批量端点 | ServiceNow 服务端 bulk 属产品级批量控件场景；当前量级不需要第二套错误语义 |
| **D-AP-20** | 条件配置复用 `ConditionRuleBuilder`，保留 JSON 开关 | 新写条件构建器 | 同契约组件已存在，避免第二实现 |
| **D-AP-21** | `TASK_ACTIONS` 用静态表，不进 action registry | 注册进 `bo_action_registrations` | 任务动作是引擎内建，注册表是 BO 动作的机制；混用会让任务动作被 BO 权限体系误管 |

不采纳（延续或新增）：BPMN 画布（N-AP-01）、独立审批中心（N-AP-02）、服务端批量审批端点（当前量级）、会签多任务实例（N-AP-03）。

#### 9.13.6 实施顺序与验收

1. `TASK_ACTIONS` + `GET /tasks/{id}/actions`（无副作用；单测覆盖「状态 × 动作」矩阵）——**已实施（2026-11-16）**：声明在 [`task_state_machine.py`](../../meta/core/task_state_machine.py)（`TaskAction` / `TASK_ACTIONS` / `applicable_actions`，`available=False` 表示已声明未上线，默认不返回），REST 在 [`task_inbox_api.py`](../../meta/api/task_inbox_api.py)（`task_actions_service` + `_action_allowed`：`admin` 短路、`owner`、`{bo}:approve` fail-closed、`task.claim` 走候选池）；测试 `TC-TSM-050~054`、`TC-P1-040~044`
2. `cancel` / `hold` / `resume` REST（无单据副作用）——**已实施（2026-11-16）**：`cancel` 走新增 [`task_control.py`](../../meta/core/task_control.py)（`require_transition` + 条件 UPDATE + `record_transition`，只写终态时间 `finished_at`）；`hold` / `resume` 薄包装 [`task_hold.py`](../../meta/core/task_hold.py) 的 `hold_task` / `release_task`（只写事件、不改状态列，严格交替）。REST 在 `task_inbox_api.py`（`task_cancel_service` / `task_hold_service` / `task_resume_service`，权限码 `owner_or_admin` / `task.hold`）；同时按本节第 3 条校正 `cancel.allowed_from` 为 `pending/ready/claimed/in_progress/failed/waiting_approval`，迁移表补 `ready/claimed/failed/waiting_approval → cancelled` 四行（18 → 22 条）；测试 `TC-TSM-002/051/054`、`TC-P1-045~050`
3. `withdraw` + 单据回退（有副作用，单独测试 + 幂等回归）——**已实施（2026-11-16）**：任务侧新增 [`task_withdraw.py`](../../meta/core/task_withdraw.py)（`withdraw_task`：严格 `created_by` → 「无任何有效 approve」（查 `tasks.outputs.decision='approve'` 且 done，不读单据 `approval_status`）→ 单据回退（`run_idempotent`，键 `{task_id}:{attempt}:withdraw`，失败回滚可重试）→ `cancel_task` 归位）；单据回退副作用在 [`document_approval_decision.py`](../../meta/services/document_approval_decision.py)（`withdraw_approval` / `purchase_order_withdraw_handler`：`submitted → draft` + `approval_status=not_required`，草稿态幂等 no-op；其余单据类型 `WITHDRAW_NOT_SUPPORTED` fail-closed）；REST `POST /api/v1/tasks/{id}/withdraw`（`task_withdraw_service`，权限码 `owner`）；测试 `TC-P1-051~055`（含回退失败可重试、已有 approve 拒绝）+ `test_document_approval.py` 撤回 4 例
4. 单据侧只读投影块（前端，可能补 `doc_ref_*` 过滤参数）——**已实施（2026-11-16）**：见 §9.13.4.1.1 与下方验收记录（后端 `list_tasks` 补 `doc_ref_type/doc_ref_id/actor`；非管理员仅允许按单据查询并按行级可见性收敛；前端复用 `AssociationSection` 自定义取数器分支，跳转落点 = 工作台 `/`）
5. 批量护栏（前端 only）——**已实施（2026-11-16）**：见 §9.13.6.2（上限 50 / 预判 `GET /tasks/{id}/actions` / 并发 4 / 逐条明细）
6. P2：条件构建器复用 → 三步态渲染——**已实施（2026-11-16）**：见 §9.13.6.3（条件树↔JSON 双向同步 + 步骤校验；`ApprovalFlowSteps` 一个组件两处用）

验收：

```powershell
python d:\filework\test.py --file meta/tests/test_task_state_machine.py,meta/tests/test_approval_task_service.py,meta/tests/test_task_decision.py,meta/tests/test_document_approval_service.py
```

前端三场景：单据页看到「审批中 + 当前处理人 + 当前步」；收件箱批量 3 条含 1 条无权限 → 点击前即不可选；撤回后单据状态回退且任务 cancelled。

**9.13.6.1 第 4 步验收记录（2026-11-16，单据侧只读审批投影）**

| 项 | 结果 |
|---|---|
| 后端测试 | `test_task_query_read.py` + `test_task_state_machine.py` + `test_task_inbox.py` ⇒ **92 passed**（新增 `TC-P1-024~026` 单据过滤/历史任务/可见性三通道、`TC-P1-037/038` 非管理员按单据查询与缺参 403）；`test_task_api.py` 3 passed |
| 后端 lint | `ruff --select E9,F`（`task_query.py` / `task_inbox_api.py` / `test_task_query_read.py`）全过 |
| 前端测试 | `taskService.spec.js` ⇒ **35 passed**（新增 doc_ref 透传 + `buildApprovalProjection` 4 例：状态/阶段/事件截取/历史兜底） |
| 构建/lint | `npm run build` 通过（chunk-cycles OK）；`eslint` 无新增错误（2 个 `fetch` 报错与既有 warning 均为基线） |
| 元模型门禁 | `python -m meta.tools.lint_metamodel` exit 0（relations 220 / actions 23 / permissions 24 / capabilities 219，0 violation） |
| 实现口径 | ① `list_tasks` 的 `actor` 分支复用 `task_inbox._row_to_task` + `_visible`（与详情同源，避免第二套可见性）；`stage_no` 按列存在性探测（旧库未迁移不 500）。② 非管理员无 `doc_ref_*` 一律 403（阻止越权全量扫描），admin 口径不变。③ 前端投影块为 `AssociationSection` 的 `customFetcher='approval_progress'` 分支，空态「暂无审批任务」、历史任务隐藏跳转并提示。④ 跳转落点 = 工作台 `/`（`/system/task-management` 为 admin-only），`ArchWorkspaceNew` 读 `?task=` 打开抽屉后 `router.replace` 清 query |
| 未做 | live 3010 手工三场景冒烟（需种子审批任务 + 真实用户权限）；已由 92 + 35 例单测覆盖契约与派生逻辑 |

**9.13.6.2 第 5 步验收记录（2026-11-16，批量护栏）**

| 项 | 结果 |
|---|---|
| 前端测试 | `taskService.spec.js` **47 passed**（新增 5：`BATCH_MAX_SIZE=50`/`BATCH_CONCURRENCY=4`、`runWithConcurrency` 并发峰值 ≤4 且同序、单项抛错隔离、`actionAllowedFromPayload` 三态、`fetchTaskActions` 路径）；`useTaskInbox.spec.js` **12 passed**（新增 2：缺 approve 动作判 blocked、端点失败 fail-open）；`TaskInboxPanel.spec.js` **11 passed**（新增 2：51 项拦截「超过批量上限」、预判排除提示「已排除 N 项不可决策」） |
| 构建/lint | `npm run build` exit 0（chunk-cycles OK）；`eslint` 无新增问题（`useTaskInbox` 的 `max-lines-per-function` 与各处 `no-unused-vars` 均为改动前基线） |
| 实现口径 | ① **50 上限**：`BATCH_MAX_SIZE` 在 `taskService.js`，UI 层两处拦截——全选截断前 50 并提示分批、`runBatch` >50 直接报错不弹确认框。② **预判 fail-open**：`precheckDecidable` 并发 4 调 `GET /tasks/{id}/actions`，仅「响应成功且明确缺该 action」判 blocked；端点失败/结构异常保留在可决策集合（由服务端兜底），避免端点故障时整批不可用。③ **并发 4**：`runWithConcurrency` 为结果同序的简单 Promise 池（`min(limit, n)`，非法 limit 回落 1），`submitBatch` 与 `precheckDecidable` 共用。④ **逐条明细**：`batchFailedList` 渲染每条失败原因 + HTTP 状态码（403/409/502）+「可重试」标记，重试仍只重试 `retryableIds`（502） |
| 未做 | live 手工批量冒烟（需贴批）；幂等仍由后端 `{task_id}:{attempt}` 保证，重试不双生效 |

**9.13.6.3 第 6 步验收记录（2026-11-16，P2 条件构建器 + 实例三步态）**

| 项 | 结果 |
|---|---|
| 前端测试 | 新增 `src/views/RuleCenter/__tests__/approvalPolicyConditions.spec.js` **22 passed**（op 归一、条件数组 ↔ 树往返、`operator`/`value_*` 兼容、`validateSteps` 五类用例）；新增 `src/components/common/__tests__/ApprovalFlowSteps.spec.js` **5 passed**（三态标签 / missReason / 无 actor 不伪造 / 空 steps）；`taskService.spec.js` 新增 7 例 `buildApprovalFlow`（三态序列、同阶段并行、全 done、事件归属取最新、无匹配空串、`hit_policy=false` 原因、缺 `inputs` 不抛）；`TaskDetailDrawer.spec.js` **26 passed**（`approval-chain` 的 `procurement_manager` 断言保持） |
| 构建/lint | `npm run build` exit 0（chunk-cycles OK）；`eslint` 无新增问题（基线：`AssociationSection` 5 warning、`TaskDetailDrawer` 2、`taskService` `URLSearchParams` no-undef 1、`TaskInboxPanel` `_` 1） |
| 条件区口径 | `ApprovalPolicyPanel` 条件区改「构建器 / JSON」双模（`data-test="condition-mode-toggle"`）：构建器为 `ConditionRuleBuilder`（`v-model:tree` + `field-metadata`），树变更即序列化回 `conditionsText`，保存路径与落库契约（`[{field_id, operator, value}]`）不变；JSON → 构建器解析失败则 `message.error` 并停留 JSON，不静默丢数据。转换与校验抽为纯模块 `approvalPolicyConditions.js`（`normalizeOp` / `conditionsToTree` / `treeToConditions` / `validateSteps`），无法用构建器表达的条目计入 `droppedCount` 并自动停在 JSON 模式 |
| 步骤校验 | 保存前本地校验四类：`step_no` 排序后必须连续 1..n；单步 `min_amount > max_amount`；相邻步金额区间须首尾相接（空 = 无界，两侧都无界跳过，仅一侧有界即报重叠/断档）；`approver_type` / `approver_ref` 必填。失败 `message.error(errors[0])` 阻止提交，不新增后端规则 |
| 三步态口径 | 新增 `src/components/common/ApprovalFlowSteps.vue`（原语组件，无状态推理），两处复用：`TaskDetailDrawer` 的 `approval-chain` 与 `AssociationSection` 单据侧投影。状态推导集中在 `taskService.buildApprovalFlow`：`status='done'` → 全 `done`；否则按 `stage_no` 与当前阶段比较（小于 → `done`、等于 → `active`、大于 → `pending`，同阶段并行步同时 `active`）；已完成步的处理人/时间**只在事件 `payload.step_no` / `payload.stage_no` 命中时归属**（取 `occurred_at` 最新一条），无匹配留空不伪造；`hit_policy=false` 渲染「未命中策略，回落默认链」 |
| 实现偏离 | 9.13.4.5 原列的 `task_participation.participations_view` 未纳入归属判定：该视图无 `step_no` 归属键，按事件 payload 归属更准确；参与流水仍可在任务抽屉的原分区查看。单据侧 `GET /tasks` 行投影不含 `inputs`，故 `AssociationSection.loadApprovalProgress` 追加一次 `fetchTaskDetail`（失败回落行数据） |

**9.13.6.4 二次检查（2026-11-16，对照后端契约复核）**

| # | 复核项 | 结论 / 处置 |
|---|---|---|
| 1 | 条件落库键名 | **已修正**：后端 `_condition_row` 只读 `operator`，原实现写 `op` 会被静默回落为 `=`（所有条件退化成等值比较）。`treeToConditions` 改输出 `{field_id, operator, value}`，读取兼容 `op` 别名与 `value_text / value_number / value_json` 三列；`applyForm` 载入时把详情行归一成落库契约再展示 |
| 2 | 三步态的阶段域 | **已修正**：原实现拿 `step_no` 与 `stage_no` 比较（跨域），同阶段并行的多个审批人会被误判为 `pending`。改为按 `stage_no` 判态、按 `(stage_no, step_no)` 排序；旧快照无 `stage_no` 时回落 `step_no`（保持并串行语义） |
| 3 | 策略步骤阶段可配 | **已补齐**：步骤表新增「阶段」列（`stage_no`，min=1，默认取当前最大阶段 +1），否则多步策略全部落在第 1 阶段，串行推进永不触发。后端 `_step_row` 同口径（默认 1、必须 ≥1） |
| 4 | 批量预判口径 | 已核实 `task_actions_service` 按「状态 × 类型 × 权限」过滤（`{bo}:approve` 需 `doc_ref_type` 且用户有该 BO 权限），预判结果与 decision 端点的 403 同源，可放心前置 |
| 5 | 条件 JSON 往返 | 后端同时接受 `value` / `value_text` / `value_number` / `value_json`，原样回存不丢值；仅在无丢弃项时归一输出，`droppedCount>0` 保留原文并停留 JSON 模式 |
| 6 | 回归 | 6 个前端测试文件 **124 passed**（`taskService` 48、`approvalPolicyConditions` 22、`TaskDetailDrawer` 26、`TaskInboxPanel` 11、`useTaskInbox` 12、`ApprovalFlowSteps` 5）；`npm run build` exit 0（chunk-cycles OK） |

**9.13.6.5 G-13-6 收口（2026-11-16，`policy_snapshot` 结构版本 + 写入期校验）**

| 项 | 结果 |
|---|---|
| 新增 | `meta/core/policy_snapshot.py`：`SNAPSHOT_SCHEMA_VERSION = 1`、`validate_snapshot(snapshot) -> list[str]`、`snapshot_problems_for_log()`、`build_snapshot_header()`。校验层只覆盖**消费方依赖的键**（`schema_version/object_type/trigger_action/policy_id/hit_policy/amount/steps/conditions/conditions_explain/metrics/resolved_at`）与步骤级（`step_no/stage_no` ≥1 整数、`approve_mode ∈ any/all/serial`、`approver_type/approver_ref` 存在），不把整棵结构声明成重型 schema |
| 写入侧 | `document_approval_service.py` 快照字典首键写 `schema_version`；快照构建完成后调 `snapshot_problems_for_log()`，有问题 `logger.warning` 但**不阻断建任务**（fail-open，与「审批不可因校验失败阻断业务提交」一致）。**不新增** `policy_snapshot` schema 元数据键（延续 D-AP-05 的门禁优于新机制） |
| 测试 | 新增 `meta/tests/test_policy_snapshot_schema.py` **22 passed**（合法/缺键/类型错/steps 级/版本常量/压行），`test_approval_policy_admin.py` 17 passed 无回归；`test_document_approval.py` + `test_approval_status_projection.py` **33 passed**（快照多一个 `schema_version` 键未破坏既有断言） |
| lint | `ruff --select E9,F` 三个文件 All checks passed |
| 未做 | 历史在途任务快照**不回填** `schema_version`（D-AP-07：在途按发起时规则走完）；消费方（`buildApprovalFlow` / 投影）不读该键，仅作未来迁移依据 |


**9.13.6.6 live 3010 手工冒烟记录（2026-11-16，四场景 + 6 项缺陷修复）**

冒烟环境：FE `3006` + BE `3010`（`launch_detached.ps1` 脱管启动），账号 `admin`（id=1）与 `adminfin`（id=1047，`*` 权限）。

| # | 场景 | 结果 | 证据 |
|---|---|---|---|
| 1 | 单据页审批进度投影 | **通过** | PO14 详情页 `.op-approval-progress` 可见；head =「已通过 / 处理人：待分发 / 第 2 / 2 阶段 / 冒烟-采购订单金额审批」；`[data-test="flow-step"]` 2 步均 `afs-step--done`；事件流含 `status_changed 1047` |
| 2 | 批量护栏 | **通过（含 1 次瞬时 500，见已知限制 ③）** | 3 条待办：预判排除生效、>50 拦截生效、确认框展示「成功 / 失败」逐条明细、失败可重试；四眼 409 文案可读 |
| 3 | 策略条件构建器保存 → 回读 | **通过** | 规则中心「审批策略」页签 → 编辑抽屉；JSON 模式回读含 `"operator": "ge"`；保存提示「审批策略已保存（版本 5）」，列表版本列 4 → 5，条件仍为 `gross_amount ge 100.0`（不退化） |
| 4 | 任务抽屉 `approval-chain` 三态 | **通过** | 抽屉内第 1 步「已完成」、第 2 步「进行中」，阶段推进后重开三态正确 |

冒烟期间发现并修复的缺陷（均已 live 验证）：

| # | 缺陷 | 根因 | 修复 |
|---|---|---|---|
| 1 | `GET /api/v1/approval-policies` 返回 410 `API Moved` | `meta/server.py` 的 v1 sunset 中间件白名单未含 `approval-policies`（独立 Blueprint，非 BO CRUD） | `V1_SPECIAL_PREFIXES` 补 `approval-policies` |
| 2 | 批量审批预判把全部选中项判为「不可决策」 | `/tasks/{id}/actions` 返回通用 `decision` 动作，前端 `actionAllowedFromPayload` 精确匹配 `approve`/`reject` | 识别 `decision` 同时覆盖通过/驳回，并补单测（真实 payload 形状） |
| 3 | 通过第 1 阶段后任务直接 `done`、不推进阶段 | `_actor()` 返回 int `user_id`，与参与流水 `participant`（字符串）精确比较失配 → 走 admin 短路 `decide_and_apply` | 5 个 task API 的 `_actor` 统一 `str(...)`；live 返回 `stage_advanced`、`stage_no=2` |
| 4 | 单据页整页被错误边界接管（`capabilities.value.filter is not a function`） | `GET /api/print/printable` 返回 `{items, page, ...}` 对象，`PrintPanel` 按数组消费 | `capabilities.value = Array.isArray(payload) ? payload : (payload?.items || [])` |
| 5 | 审批投影分区永不挂载（`detail.approval_progress` 丢失） | `UIDetailViewConfig` dataclass 与 `yaml_loader.parse_ui_detail_view_config` 均无该字段，YAML 声明在加载期被静默丢弃 | 两处补 `approval_progress` 透传字段；`/ui-config` 回读含该键后方可渲染 |
| 6 | 多阶段任务第 2 阶段决策被当作 replay 静默忽略，任务永远 `waiting_approval` | `build_effect_key` 仅 `{task_id}:{attempt}`，`_load_task` 也未取 `stage_no` → 第 2 阶段命中第 1 阶段幂等记录 | `build_effect_key(task_id, attempt, stage_no)`：`stage_no>1` 追加 `:s{stage}`（首阶段保持旧格式）；`_TASK_COLUMNS` 补 `stage_no`；单测补键口径 |

多阶段收口 live 证据：`adminfin`（≠ 提交人 1）通过 PO14 第 2 阶段 → `effect_key="ba84459d…:1:s2"`、`replayed=false`、`task_status=done`、`receipt.approval_status=approved`、单据 `status=confirmed`；同账号（admin）在末阶段仍被四眼 409 拦截（设计如此）。两条并发决策（PO6 / PO9 第 2 阶段）均 200 完成，未复现并发异常。

已知限制（不阻断交付）：

1. 参与流水与阶段推进路径**不写 `task_events`**，已完成步骤的 `flow-step-actor` 为空或显示 `user_id`（如 `1`）而非姓名；事件流仅能反映 `status_changed` 类事件。
2. 已通过单据投影 head 仍显示「处理人：待分发」——`approverLabel` 在任务终态未回落提交人/末位审批人，属文案层面改进项。
3. 批量并发曾出现一次 500 `not an error`（逐条明细可见、重试/幂等 replay 后数据一致）。疑与平台 `get_data_source` 共享 sqlite 连接的并发写有关；本次未能稳定复现（2 条并发写全部 200），暂不调整批量并发策略（并发 4 / D-AP-12），留作平台层共享连接治理的输入。

回归：后端 `test_decision_effect` / `test_task_stage_advance` / `test_task_decision_api` / `test_task_participation` / `test_approval_policy_admin` / `test_approval_status_projection` **83 passed**（键口径新增后单跑 29 passed）；前端 `taskService.spec.js` **49 passed**；`npm run build` exit 0（chunk-cycles OK）。


#### 9.13.7 证据来源

- Oracle：[Transaction Console（HCM 审批监控）](http://docs.oracle.com/en/cloud/saas/human-resources/faucf/how-you-manage-hcm-approval-transactions.html)、[Manage Workflow Transactions（审批历史含当前处理人）](http://docs.oracle.com/en/cloud/saas/procurement/24d/oapro/manage-workflow-transactions.html)、[Document History for Purchasing Documents](https://docs.oracle.com/en/cloud/saas/procurement/24b/oaprc/document-history-for-purchasing-documents.html)、[Approval Rules 配置（Transaction Console → Configure Rules）](http://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/26B-inventory-wn-f43054.htm)、[BPM Worklist（状态与先 claim 约束）](http://docs.oracle.com/cd/E25178_01/dev.1111/e10224/bp_worklist.htm)、[Task Actions（reassign/delegate/pushback/escalate）](http://docs.oracle.com/en/middleware/soa-suite/soa/14.1.2/develop/task-actions.html)、[System Actions（suspend/resume 权限）](https://docs.cloud.oracle.com/en/middleware/soa-suite/soa/14.1.2/develop/system-actions.html)
- SAP：[My Inbox（F0862：后端下发 decision options，标准动作 claim/release/forward）](https://fioriappslibrary.hana.ondemand.com/sap/fix/externalViewer/#/detail/Apps('F0862')/S21OP)、[Flexible Workflow 配置（步骤/升级/委托）](https://www.corepath.es/blog/sap-release-strategy-vs-fiori-workflow_fr.html)
- ServiceNow：[My Approvals 批量通过/驳回（sys_ids 交服务端）](https://www.servicenow.com/community/developer-blog/enhancing-the-servicenow-my-approvals-widget-implementation-amp/ba-p/3587131)、[分组审批（多条聚合为一条）](https://www.servicenow.com/community/spm-forum/send-consolidated-approval-email-for-multiple-demands-projects/m-p/3410224)
- Salesforce：[ApprovalProcess 元数据（allowRecall / allowedSubmitters / steps）](https://developer.salesforce.com/docs/atlas.en-us.242.0.api_meta.meta/api_meta/meta_approvalprocess.htm)、[Approval History → Approval Trace 组件](https://salesforcedictionary.com/blogs/classic-approval-processes-to-flow-approvals-2026)
