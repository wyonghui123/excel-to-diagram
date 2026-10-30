# -*- coding: utf-8 -*-
"""Gen1 任务基础设施表（task_queues / task_executions）唯一 DDL 真源

背景
  这两张表过去由两处各自建：
    - `meta/scripts/init_task_seed.py::_ensure_task_tables`（裸 DDL，启动种子）
    - `meta/schemas/task_queue.yaml` / `task_execution.yaml`（YAML → sync_schema）
  两处 DDL 一旦漂移，就会「YAML 建的表和种子建的表字段不同」。

  YAML 双轨已在本 change 删除，因此把 DDL 收敛到本模块：
    - `init_task_seed` 启动时调用 `ensure_task_infra_tables()`（幂等建表）
    - `meta/migrations/v156__adopt_task_infra_tables.py` 存量库同样调用它

  注意：这两张表属于「作业执行基础设施」，不是 Gen2 任务域六表
  （tasks/task_templates/workflows/workflow_runs/task_events/task_worklogs，
  见 `meta/core/task_schema.py`）。
"""
import logging

logger = logging.getLogger(__name__)

TASK_QUEUE_TABLE = 'task_queues'
TASK_EXECUTION_TABLE = 'task_executions'

TASK_QUEUE_DDL = """
    CREATE TABLE IF NOT EXISTS task_queues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(200) UNIQUE NOT NULL,
        description TEXT,
        priority INTEGER NOT NULL DEFAULT 50,
        max_workers INTEGER NOT NULL DEFAULT 3,
        timeout INTEGER NOT NULL DEFAULT 300,
        enabled INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""

TASK_EXECUTION_DDL = """
    CREATE TABLE IF NOT EXISTS task_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(500),
        task_id INTEGER,
        task_type VARCHAR(100),
        handler VARCHAR(200),
        status VARCHAR(50) DEFAULT 'pending',
        trigger_type VARCHAR(50) DEFAULT 'cron',
        queue VARCHAR(100) DEFAULT 'business',
        priority INTEGER DEFAULT 50,
        timeout INTEGER DEFAULT 300,
        max_retries INTEGER DEFAULT 3,
        started_at DATETIME,
        completed_at DATETIME,
        duration_ms INTEGER,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        result TEXT,
        queued_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""

# 期望列（verify 用；允许存量库多列，不允许多列以外缺列）
TASK_QUEUE_COLUMNS = (
    'id', 'name', 'description', 'priority', 'max_workers', 'timeout',
    'enabled', 'created_at',
)

TASK_EXECUTION_COLUMNS = (
    'id', 'name', 'task_id', 'task_type', 'handler', 'status', 'trigger_type',
    'queue', 'priority', 'timeout', 'max_retries', 'started_at', 'completed_at',
    'duration_ms', 'error_message', 'retry_count', 'result', 'queued_at',
    'created_at',
)

INFRA_TABLES = (
    (TASK_QUEUE_TABLE, TASK_QUEUE_DDL, TASK_QUEUE_COLUMNS),
    (TASK_EXECUTION_TABLE, TASK_EXECUTION_DDL, TASK_EXECUTION_COLUMNS),
)


def ensure_task_infra_tables(data_source) -> None:
    """幂等建 task_queues / task_executions，并登记表名白名单。"""
    from meta.core.table_name_validator import register_table_name

    for name, ddl, _cols in INFRA_TABLES:
        register_table_name(name)
        data_source.execute(ddl)
    data_source.commit()
    logger.info("Task infra tables ensured")
