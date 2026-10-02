# -*- coding: utf-8 -*-
"""[A1 2026-10-02] 统一任务运行时底座 schema — task.v1 四表定义

职责:
- 平台提供**唯一**的 task.v1 结构定义（Task / TaskTemplate / Workflow / Run），
  MetaObject 形式（元数据驱动，非 migration 裸建；同 `doc_flow_schema.py` 机制）
- 四表落**平台库**（`meta/architecture.db`）—— §12.1「五、」Q1 拍板：
  任务对业务对象仅弱引用（`doc_ref` + `line_refs`，不建 FK），跨库不触 F5 铁律；
  统一收件箱（A8）要求跨应用可见，故落平台库

**不是业务 BO**：不注册进 BO registry —— Task 生命周期归任务引擎（A2 状态机），
若注册为 BO，通用 BO API 可直接改 `status`，绕过状态机。任务侧 API 归 A4/A8 自建。

关键纪律（本文件只落结构，不落引擎）:
- 状态只挂实例：`tasks.status` 是唯一状态列；`workflow_runs` **不建独立状态列**
  （Run 进度由子任务状态派生聚合，见综合缝合分析 §3.2）
- 弱引用不建 FK：`doc_ref` / `line_refs` / `parent_task_id` / `workflow_run_id`
  一律无外键约束
- 幂等键 `{run}:{task}:{attempt}` 由引擎计算（§9.2），**不落列**——`id` 为 uuid
  唯一，三元组天然唯一，落列即双写
- `sla` 仅存配置快照；SLA 运行态（Stage / Has breached）归 F2 独立对象，不入本表

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.2 / §7.3 / §7.4 / §12.1
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §2.4 / §3.2 / §6
"""
from __future__ import annotations

from meta.core.models import (
    FieldType, IndexSource, MetaField, MetaIndex, MetaObject,
)

# ─────────────────────────────────────────────────────────────────────────────
# 表名常量（与既有 task_queues / task_executions / scheduled_tasks 无冲突）
# ─────────────────────────────────────────────────────────────────────────────

TASK_ID = "task"
TASK_TABLE = "tasks"

TASK_TEMPLATE_ID = "task_template"
TASK_TEMPLATE_TABLE = "task_templates"

WORKFLOW_ID = "workflow"
WORKFLOW_TABLE = "workflows"

WORKFLOW_RUN_ID = "workflow_run"
WORKFLOW_RUN_TABLE = "workflow_runs"

# 11 态（§7.2 状态机）—— 仅作文档/校验口径，本模块不实现迁移守卫（A2）
TASK_STATUSES = (
    "pending", "ready", "claimed", "in_progress", "blocked",
    "waiting_approval", "done", "failed", "cancelled", "skipped", "dead",
)
# 执行方式维度（§7.5）—— executor 是维度不是类型
EXECUTOR_TYPES = ("human", "agent", "cron", "system", "webhook")
# 业务分类（§7.3）—— 与 executor_type 正交
TASK_TYPES = ("story", "automation", "approval", "review", "notification")


def _f(fid: str, ftype: FieldType, *, required: bool = False,
       unique: bool = False, default=None, description: str = "") -> MetaField:
    return MetaField(
        id=fid, name=fid, field_type=ftype, db_column=fid,
        required=required, unique=unique, default=default, description=description,
    )


def _idx(name: str, columns, *, unique: bool = False, description: str = "") -> MetaIndex:
    return MetaIndex(
        fields=list(columns), db_columns=list(columns), name=name,
        unique=unique, source=IndexSource.SCHEMA, description=description,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Task（实例层：最小工作单元，11 态）
# ─────────────────────────────────────────────────────────────────────────────

def _build_task_meta() -> MetaObject:
    """构造 Task 表 MetaObject（每次调用返回新实例，避免共享可变状态）。"""
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="任务 ID（uuid4 hex，主键）"),
        _f("code", FieldType.STRING,
           description="人读编号 T-1234（§7.3 pattern ^T-[0-9]+$）"),
        _f("title", FieldType.STRING, required=True, description="任务标题"),
        _f("description", FieldType.TEXT, description="任务描述"),
        _f("type", FieldType.STRING, required=True, default="story",
           description="业务分类 story/automation/approval/review/notification（UI 用，不参与调度）"),
        _f("status", FieldType.STRING, required=True, default="pending",
           description="11 态：pending/ready/claimed/in_progress/blocked/waiting_approval/"
                       "done/failed/cancelled/skipped/dead（唯一状态列）"),
        _f("priority", FieldType.STRING, default="P2",
           description="优先级 P0/P1/P2/P3"),

        # 维度归属：A8 行级可见性过滤（app_id + 分配者 + 角色）为验收硬项（§12.1 Q1 配套）
        _f("app_id", FieldType.STRING,
           description="所属应用（行级可见性过滤键；空 = 平台级任务）"),

        # executor 维度（§7.3 executor_spec 展开；fallback 实现 executor 嵌套）
        _f("executor_type", FieldType.STRING, required=True,
           description="执行方式 human/agent/cron/system/webhook"),
        _f("executor_assignee", FieldType.STRING,
           description="指派人 user_id/agent_id；cron/webhook 为空"),
        _f("executor_candidates", FieldType.JSON,
           description="抢单候选池（用户或用户组数组）"),
        _f("assign_policy", FieldType.STRING, default="direct",
           description="direct/claim/round_robin/skill_based/ai_routed"),
        _f("executor_config", FieldType.JSON,
           description="按 executor_type 解释（§9 各 executor 规范）"),
        _f("executor_fallback", FieldType.JSON,
           description="失败/超时后升级到的另一个 executor_spec"),
        _f("claim_timeout_seconds", FieldType.INTEGER, default=300,
           description="认领后未 start 的回收阈值"),
        _f("timeout_seconds", FieldType.INTEGER, description="执行超时"),
        _f("retry_policy", FieldType.JSON,
           description="max_attempts/initial_backoff_ms/backoff_multiplier/max_backoff_ms/non_retryable"),

        _f("due_at", FieldType.DATETIME, description="截止时间"),
        _f("sla", FieldType.JSON,
           description="SLA 配置快照 warn_at_pct/on_breach；运行态归 F2 独立对象"),

        # 结构：父子拆解（树）× DAG 依赖（图），两者正交（§6）
        _f("parent_task_id", FieldType.STRING,
           description="父任务 ID（手动拆解 / Agent Plan-and-Execute），弱引用无 FK"),
        _f("workflow_run_id", FieldType.STRING,
           description="所属 Run ID（弱引用无 FK）"),
        _f("workflow_node_id", FieldType.STRING,
           description="Run 内节点标识"),
        _f("deps", FieldType.JSON,
           description="依赖数组 [{task_id, when}]，when=done/skipped/done_or_skipped；默认 AND"),

        _f("inputs", FieldType.JSON, description="入参实例值"),
        _f("inputs_schema", FieldType.JSON, description="入参 JSON Schema（强校验）"),
        _f("outputs", FieldType.JSON, description="出参（完成后回写）"),
        _f("outputs_schema", FieldType.JSON, description="出参 JSON Schema"),
        _f("acceptance", FieldType.JSON,
           description="验收：{kind:checklist,items} 或 {kind:eval,evaluator,threshold}"),

        _f("attempt", FieldType.INTEGER, default=1, description="尝试序号（幂等键组成，从 1 起）"),
        _f("trace_id", FieldType.STRING, description="OTel trace id（创建即注入）"),
        _f("agent_session_id", FieldType.STRING,
           description="Agent 会话 ID（checkpoint 续跑；非 agent executor 为空）"),

        # 业务对象弱引用（综合缝合分析 §6.2 关系 1）——跨环节关联键
        _f("doc_ref", FieldType.STRING,
           description="单据级弱引用（businessKey 等价物，跨环节关联键）；无 FK"),
        _f("line_refs", FieldType.JSON,
           description="行级弱引用数组（可选，Phase 3 启用）；不建 FK、不建行级生命周期表"),

        _f("created_by", FieldType.STRING, description="创建者 user_id/agent_id/system"),
        _f("created_at", FieldType.DATETIME, description="创建时间"),
        _f("started_at", FieldType.DATETIME, description="开始时间"),
        _f("finished_at", FieldType.DATETIME, description="结束时间"),
        _f("fail_reason", FieldType.STRING,
           description="失败/终止原因 error/timeout/max_iterations/budget_exhausted/"
                       "guardrail/tool_failure/handoff_to_human/review_rejected"),
        _f("meta", FieldType.JSON, description="业务自定义 KV，引擎不解释"),
        _f("updated_at", FieldType.DATETIME, description="更新时间"),
    ]

    indexes = [
        _idx("uq_tasks_code", ["code"], unique=True,
             description="人读编号唯一"),
        _idx("idx_tasks_status", ["status", "priority"],
             description="收件箱：按状态 + 优先级取待办"),
        _idx("idx_tasks_inbox", ["app_id", "status"],
             description="A8 行级可见性过滤 + 跨应用收件箱（Q1 配套）"),
        _idx("idx_tasks_assignee", ["executor_type", "executor_assignee", "status"],
             description="我的待办（含 agent 身份）"),
        _idx("idx_tasks_run", ["workflow_run_id"],
             description="Run 进度聚合（Run 状态派生走此索引）"),
        _idx("idx_tasks_parent", ["parent_task_id"],
             description="子任务树"),
        _idx("idx_tasks_doc", ["doc_ref"],
             description="按单据追任务（跨环节关联）"),
    ]

    return MetaObject(
        id=TASK_ID,
        name="任务",
        table_name=TASK_TABLE,
        description="统一任务实例（11 态唯一状态列；executor 为维度；对业务对象仅弱引用）",
        fields=fields,
        indexes=indexes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. TaskTemplate（定义层：Workflow 节点定义）
# ─────────────────────────────────────────────────────────────────────────────

def _build_task_template_meta() -> MetaObject:
    """构造 TaskTemplate 表 MetaObject。

    节点结构抄 Oracle 已核实的最小充分集（§12.1 C2）：主干 `step_number` +
    单亲 `parent_step_number` + 分支块 `group_name`——**不是通用 DAG**。
    """
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="模板节点 ID（如 wf-invoice-processing@3.n1，主键）"),
        _f("workflow_id", FieldType.STRING, required=True,
           description="所属 Workflow 定义 ID（弱引用无 FK）"),
        _f("workflow_version", FieldType.INTEGER, required=True,
           description="所属 Workflow 版本（定义层版本化）"),
        _f("node_id", FieldType.STRING, required=True,
           description="Run 内节点标识（n1/n2…）"),
        _f("step_number", FieldType.INTEGER,
           description="主干节点编号（Oracle STEP_NUMBER 对位）"),
        _f("parent_step_number", FieldType.INTEGER,
           description="单亲节点编号（分支块挂载点；0/空 = 主干）"),
        _f("group_name", FieldType.STRING,
           description="分支块/分组名（§7.4 nodes[].group）"),
        _f("title", FieldType.STRING, required=True, description="默认任务标题"),
        _f("description", FieldType.TEXT, description="节点描述"),
        _f("type", FieldType.STRING, required=True, default="story",
           description="默认业务分类"),
        _f("priority", FieldType.STRING, default="P2", description="默认优先级"),
        _f("executor_type", FieldType.STRING, required=True,
           description="默认执行方式"),
        _f("executor_assignee", FieldType.STRING, description="默认指派人"),
        _f("executor_candidates", FieldType.JSON, description="默认候选池"),
        _f("assign_policy", FieldType.STRING, default="direct",
           description="默认分配策略"),
        _f("executor_config", FieldType.JSON, description="执行配置（§9）"),
        _f("executor_fallback", FieldType.JSON, description="默认 fallback executor_spec"),
        _f("claim_timeout_seconds", FieldType.INTEGER, default=300,
           description="默认认领回收阈值"),
        _f("timeout_seconds", FieldType.INTEGER, description="默认执行超时"),
        _f("retry_policy", FieldType.JSON, description="默认重试策略"),
        _f("inputs_schema", FieldType.JSON, description="入参 JSON Schema"),
        _f("outputs_schema", FieldType.JSON, description="出参 JSON Schema"),
        _f("acceptance", FieldType.JSON, description="默认验收配置"),
        _f("sla", FieldType.JSON, description="节点级 SLA 配置"),
        _f("meta", FieldType.JSON, description="业务自定义 KV"),
        _f("created_at", FieldType.DATETIME, description="创建时间"),
        _f("updated_at", FieldType.DATETIME, description="更新时间"),
    ]

    indexes = [
        _idx("uq_task_template_node", ["workflow_id", "workflow_version", "node_id"],
             unique=True, description="同版本内节点唯一"),
        _idx("idx_task_template_wf", ["workflow_id", "workflow_version"],
             description="按定义版本取全部节点"),
    ]

    return MetaObject(
        id=TASK_TEMPLATE_ID,
        name="任务模板节点",
        table_name=TASK_TEMPLATE_TABLE,
        description="Workflow 静态节点定义（定义层无状态；Run 启动时按版本克隆为 Task）",
        fields=fields,
        indexes=indexes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Workflow（定义层：版本化编排定义）
# ─────────────────────────────────────────────────────────────────────────────

def _build_workflow_meta() -> MetaObject:
    """构造 Workflow 表 MetaObject（定义层，**无状态列**——§3.3 定律 1）。"""
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="Workflow 版本行 ID（uuid4 hex，主键；一个 key 多版本多行）"),
        _f("workflow_key", FieldType.STRING, required=True,
           description="业务键（如 wf-invoice-processing），跨版本稳定"),
        _f("version", FieldType.INTEGER, required=True, description="版本号（从 1 递增）"),
        _f("name", FieldType.STRING, required=True, description="流程名称"),
        _f("description", FieldType.TEXT, description="流程描述"),
        _f("owner", FieldType.STRING, description="属主"),
        _f("trigger_kind", FieldType.STRING, default="manual",
           description="触发方式 manual/schedule/event/api（C3 事件入的唯一入口）"),
        _f("trigger_expr", FieldType.STRING,
           description="触发表达式（cron 表达式或事件条件）"),
        _f("edges", FieldType.JSON,
           description="边数组 [{from,to,when,comment}]；when=done/failed/skipped/表达式"),
        _f("sla", FieldType.JSON,
           description="流程级 SLA {total_hours, critical_path}"),
        _f("meta", FieldType.JSON, description="业务自定义 KV"),
        _f("created_by", FieldType.STRING, description="创建者"),
        _f("created_at", FieldType.DATETIME, description="创建时间"),
        _f("updated_at", FieldType.DATETIME, description="更新时间"),
    ]

    indexes = [
        _idx("uq_workflow_key_version", ["workflow_key", "version"], unique=True,
             description="同 key 同版本唯一；在途 Run 快照旧版本不受新版本影响"),
        _idx("idx_workflow_key", ["workflow_key"],
             description="按业务键取版本序列"),
    ]

    return MetaObject(
        id=WORKFLOW_ID,
        name="工作流定义",
        table_name=WORKFLOW_TABLE,
        description="编排定义层（版本化；定义层无状态——节点/边只描述主干与分支块）",
        fields=fields,
        indexes=indexes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. WorkflowRun（实例层；**无独立状态列**，进度派生聚合）
# ─────────────────────────────────────────────────────────────────────────────

def _build_workflow_run_meta() -> MetaObject:
    """构造 Run 表 MetaObject。

    **刻意不建 status 列**：Run 进度由子任务状态派生聚合（综合缝合分析 §3.2
    「Run（建议）：由子任务状态**派生**（聚合视图）；不建独立状态列，避免双写」）。
    """
    fields = [
        _f("id", FieldType.STRING, required=True, unique=True,
           description="Run ID（uuid4 hex，主键）"),
        _f("workflow_id", FieldType.STRING, required=True,
           description="所快照的 Workflow 版本行 ID（弱引用无 FK）"),
        _f("workflow_key", FieldType.STRING, description="业务键（便于按 key 追溯）"),
        _f("workflow_version", FieldType.INTEGER, required=True,
           description="快照版本号（在途 Run 不受定义升级影响）"),
        _f("name", FieldType.STRING, description="Run 显示名"),
        _f("trigger_kind", FieldType.STRING,
           description="实际触发方式 manual/schedule/event/api"),
        _f("definition_snapshot", FieldType.JSON,
           description="Workflow 定义快照（§7.4 创建时快照 version）"),
        _f("variables", FieldType.JSON,
           description="Run 内传递变量（上游 outputs 按 edge 注入下游 inputs）"),
        _f("inputs", FieldType.JSON, description="Run 入参"),
        _f("outputs", FieldType.JSON, description="Run 出参"),
        _f("created_by", FieldType.STRING, description="创建者"),
        _f("created_at", FieldType.DATETIME, description="创建时间"),
        _f("started_at", FieldType.DATETIME, description="开始时间"),
        _f("finished_at", FieldType.DATETIME, description="结束时间"),
        _f("meta", FieldType.JSON, description="业务自定义 KV"),
        _f("updated_at", FieldType.DATETIME, description="更新时间"),
    ]

    indexes = [
        _idx("idx_run_workflow", ["workflow_id"],
             description="按定义版本回溯 Run"),
        _idx("idx_run_key", ["workflow_key"],
             description="按业务键取历史 Run"),
    ]

    return MetaObject(
        id=WORKFLOW_RUN_ID,
        name="工作流运行实例",
        table_name=WORKFLOW_RUN_TABLE,
        description="编排实例层（无独立状态列；进度由子任务状态派生聚合）",
        fields=fields,
        indexes=indexes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 建表入口
# ─────────────────────────────────────────────────────────────────────────────

def build_task_meta_objects() -> list:
    """返回 task.v1 四表 MetaObject（顺序：定义层 → 实例层）。"""
    return [
        _build_workflow_meta(),
        _build_task_template_meta(),
        _build_workflow_run_meta(),
        _build_task_meta(),
    ]


def ensure_task_tables(data_source) -> int:
    """在**平台库**建 task.v1 四表 + 索引（幂等，启动期调用）。

    走 sync_schema_from_meta（SchemaMigrator）：表存在则跳过、缺列则补、
    索引 CREATE INDEX IF NOT EXISTS —— 与 doc_flow 边表同一机制。

    四表是**平台机制表**（非业务 BO，不进 BO registry），故显式登记进
    表名安全白名单（table_name_validator），使后续引擎写路径通过校验。

    Returns:
        本次执行的 SQL 语句列表（首次 = 4 建表 + 索引；幂等重放时仅索引
        `CREATE ... IF NOT EXISTS`）。
    """
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    object_names = [TASK_TABLE, TASK_TEMPLATE_TABLE, WORKFLOW_TABLE, WORKFLOW_RUN_TABLE]
    for name in object_names:
        register_table_name(name)
    return sync_schema_from_meta(data_source, build_task_meta_objects())


def task_tables_exist(data_source) -> dict:
    """返回 {表名: 是否存在}（验收用：验证建表结果）。"""
    result = {}
    for name in (TASK_TABLE, TASK_TEMPLATE_TABLE, WORKFLOW_TABLE, WORKFLOW_RUN_TABLE):
        try:
            rows = data_source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchall()
        except Exception:  # noqa: BLE001 - 库不可读视为不存在
            rows = []
        result[name] = bool(rows)
    return result