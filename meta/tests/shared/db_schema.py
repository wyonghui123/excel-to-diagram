# -*- coding: utf-8 -*-
"""测试侧 DDL 复用：audit_logs 表结构（唯一真源对齐生产）。

真源（2026-11-09 核对）：
1. ``meta/schemas/generated_schema.sql`` — audit_logs 基线 31 列
2. ``meta/scripts/migrate_v318_audit.py`` — 追加 7 列 + 5 个索引
3. ``meta/schemas/.drift_report.json`` — 生产实表额外列
   ``created_at_epoch``(BIGINT) / ``updated_at``(DATETIME)

=> 合计 40 列。``parent_action_id`` 在生产 audit_logs 中不存在，不得加入。

使用约束：
- 只用于「业务表 + 审计表」的测试夹具，替代各文件里手写的 20~30 列 audit_logs DDL。
- 迁移/结构演进类测试（审计归档、v_audit_all 视图、updated_at 物化、FK 重构等）
  DDL 本身就是被测对象，必须保留自身 DDL，**不得**改用本模块。
- 直接 ``from meta.tests.shared.db_schema import create_audit_logs``，
  不要经 ``meta.tests.shared`` 包聚合导入（会带 fixtures/mocks 副作用）。
"""

# 生产 audit_logs 完整结构（40 列）。SQLite 动态类型，列顺序与生产保持一致便于比对。
AUDIT_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_category VARCHAR(200) NOT NULL DEFAULT 'business',
    log_level VARCHAR(200) NOT NULL DEFAULT 'INFO',
    object_type VARCHAR(200) NOT NULL,
    object_id INTEGER NOT NULL,
    parent_object_type VARCHAR(200),
    parent_object_id INTEGER,
    action VARCHAR(200) NOT NULL,
    field_name VARCHAR(200),
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    user_name VARCHAR(200),
    ip_address VARCHAR(200),
    user_agent VARCHAR(200),
    created_at DATETIME NOT NULL DEFAULT 'NOW()',
    extra_data TEXT,
    trace_id VARCHAR(200),
    transaction_id VARCHAR(200),
    change_set_id VARCHAR(200),
    reason_code VARCHAR(200),
    status VARCHAR(200) DEFAULT 'written',
    status_entered_at DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    agent_id VARCHAR(200),
    agent_session_id VARCHAR(200),
    tool_call_id VARCHAR(200),
    agent_reasoning TEXT,
    action_kind VARCHAR(20) DEFAULT 'instance',
    outcome VARCHAR(20) DEFAULT 'success',
    cascade_root_id INTEGER,
    cascade_root_action VARCHAR(50),
    retention_until DATETIME,
    prev_hash CHAR(64),
    row_hash CHAR(64),
    created_at_epoch BIGINT,
    updated_at DATETIME
)
"""


def create_audit_logs(target):
    """在 ``target`` 上创建 audit_logs 表（幂等）。

    兼容两类调用方：
    - ``sqlite3.Connection`` → ``executescript``
    - ``meta.core.sql_adapters.SQLiteAdapter`` → ``execute``
    """
    if hasattr(target, "executescript"):
        target.executescript(AUDIT_LOGS_DDL)
    else:
        target.execute(AUDIT_LOGS_DDL)
    target.commit()