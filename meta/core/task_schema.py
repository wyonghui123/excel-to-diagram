# -*- coding: utf-8 -*-
"""[A1 2026-10-02] 统一任务运行时底座 schema — task.v1 四表

[G7 2026-11-02] 定义已迁至 YAML（meta/schemas/workflow.yaml / task_template.yaml /
workflow_run.yaml / task.yaml），本模块保留：
- 表名 / 对象 id 常量（其它模块依赖）；
- 状态机口径常量（TASK_STATUSES / EXECUTOR_TYPES / TASK_TYPES）；
- 从 registry 取 MetaObject 的兼容入口（懒 import，避免循环依赖）；
- ensure_task_tables()：YAML 定义驱动幂等建表（表名白名单登记仍在）。

纪律（不变）:
- 任务对象是**平台机制对象**：注册进统一元模型，但 `skip_generic_api: true`
  ⇒ 不暴露通用 BO API / agent 工具 / 自动菜单；Task 生命周期归任务引擎（A2 状态机）。
- 状态只挂实例：`tasks.status` 是唯一状态列；`workflow_runs` **不建独立状态列**。
- 弱引用不建 FK：`doc_ref` / `line_refs` / `parent_task_id` / `workflow_run_id` 一律无外键。
"""
from __future__ import annotations

from typing import List

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

# 定义层 → 实例层（与 YAML 注册顺序无关，按 id 取）
TASK_DOMAIN_OBJECT_IDS = (WORKFLOW_ID, TASK_TEMPLATE_ID, WORKFLOW_RUN_ID, TASK_ID)


def _ensure_task_domain_registered() -> None:
    """确保六表 YAML 已注册进 registry（懒 import 规避 models ↔ yaml_loader 循环）。"""
    from meta.core.models import registry
    from meta.core.task_event_schema import TASK_EVENT_ID, WORKLOG_ID

    ids = TASK_DOMAIN_OBJECT_IDS + (TASK_EVENT_ID, WORKLOG_ID)
    if all(registry.get(obj_id) is not None for obj_id in ids):
        return

    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
    register_from_directory(get_yaml_schema_dir())


_TASK_DOMAIN_YAML_CACHE = None


def _task_domain_from_yaml() -> dict:
    """直接按 YAML 目录加载六对象（不依赖 registry 状态）。

    测试会把 `meta.core.models.registry` 换成 stub（只放被测对象），
    headless 迁移也可能尚未全局注册；此时从 YAML 目录兜底取定义，
    保证建表入口与代码定义时代行为一致。
    """
    global _TASK_DOMAIN_YAML_CACHE
    if _TASK_DOMAIN_YAML_CACHE is None:
        from meta.core.yaml_loader import get_yaml_schema_dir, load_yaml_directory
        _TASK_DOMAIN_YAML_CACHE = {
            obj.id: obj for obj in load_yaml_directory(get_yaml_schema_dir())
        }
    return _TASK_DOMAIN_YAML_CACHE


def _get_task_domain_object(obj_id):
    from meta.core.models import registry
    _ensure_task_domain_registered()
    obj = registry.get(obj_id)
    if obj is not None:
        return obj
    return _task_domain_from_yaml().get(obj_id)


def get_task_meta_objects() -> List:
    """返回任务域六表 MetaObject（定义层 → 实例层 → 事件账）。

    定义唯一来源 = `meta/schemas/*.yaml`；本入口供 ensure / 迁移 / 测试复用。
    """
    ids = TASK_DOMAIN_OBJECT_IDS + _task_event_object_ids()
    return get_task_meta_objects_for(ids)


def _task_event_object_ids() -> tuple:
    from meta.core.task_event_schema import TASK_EVENT_ID, WORKLOG_ID
    return (TASK_EVENT_ID, WORKLOG_ID)


def get_task_meta_objects_for(ids) -> List:
    """按 id 取 MetaObject（调用方只需本模块负责的表时使用）。"""
    return [obj for obj in (_get_task_domain_object(i) for i in ids) if obj is not None]


# ─────────────────────────────────────────────────────────────────────────────
# 建表入口
# ─────────────────────────────────────────────────────────────────────────────

def ensure_task_tables(data_source) -> List[str]:
    """在**平台库**建 task.v1 四表 + 索引（幂等，启动期调用）。

    定义来自 YAML（`meta/schemas/{workflow,task_template,workflow_run,task}.yaml`），
    走 sync_schema_from_meta（SchemaMigrator）：表存在则跳过、缺列则补、
    索引 CREATE INDEX IF NOT EXISTS。

    四表是**平台机制表**，故显式登记进表名安全白名单（table_name_validator）。

    Returns:
        本次执行的 SQL 语句列表（首次 = 4 建表 + 索引；幂等重放时仅索引
        `CREATE ... IF NOT EXISTS`）。
    """
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import register_table_name

    object_names = [TASK_TABLE, TASK_TEMPLATE_TABLE, WORKFLOW_TABLE, WORKFLOW_RUN_TABLE]
    for name in object_names:
        register_table_name(name)
    return sync_schema_from_meta(data_source, get_task_meta_objects_for(TASK_DOMAIN_OBJECT_IDS))


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
