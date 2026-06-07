# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)


def init_task_seed_data(data_source):
    _ensure_task_tables(data_source)
    init_task_queues(data_source)
    init_scheduled_tasks(data_source)


def _ensure_task_tables(data_source):
    data_source.execute("""
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
    """)
    data_source.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(200) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            category VARCHAR(100) DEFAULT 'business',
            handler VARCHAR(200) NOT NULL,
            trigger_mode VARCHAR(50) DEFAULT 'cron',
            schedule VARCHAR(200),
            queue VARCHAR(100) DEFAULT 'business',
            priority INTEGER DEFAULT 50,
            timeout INTEGER DEFAULT 300,
            max_retries INTEGER DEFAULT 3,
            handler_config TEXT DEFAULT '{}',
            description TEXT,
            enabled INTEGER DEFAULT 1,
            last_run_at DATETIME,
            next_run_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    data_source.execute("""
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
    """)
    data_source.commit()
    logger.info("Task tables ensured")


def init_task_queues(data_source):
    queues = [
        {
            'name': 'critical',
            'description': '紧急任务队列：数据库checkpoint等关键操作',
            'priority': 10,
            'max_workers': 2,
            'timeout': 600,
            'enabled': True,
        },
        {
            'name': 'ai_high',
            'description': 'AI高优先级队列：实时对话、关键推理',
            'priority': 20,
            'max_workers': 3,
            'timeout': 1200,
            'enabled': True,
        },
        {
            'name': 'ai_normal',
            'description': 'AI普通队列：批量分析、长时推理',
            'priority': 30,
            'max_workers': 5,
            'timeout': 1800,
            'enabled': True,
        },
        {
            'name': 'business',
            'description': '业务任务队列：数据处理、导入导出、审计维护',
            'priority': 50,
            'max_workers': 3,
            'timeout': 300,
            'enabled': True,
        },
        {
            'name': 'background',
            'description': '后台低优先级队列：统计分析、日志清理、归档',
            'priority': 100,
            'max_workers': 2,
            'timeout': 600,
            'enabled': True,
        },
    ]

    count = 0
    for q in queues:
        try:
            existing = data_source.query(
                "SELECT id FROM task_queues WHERE name = ?",
                (q['name'],)
            )
            if existing:
                data_source.execute(
                    """UPDATE task_queues SET
                        description = ?, priority = ?, max_workers = ?,
                        timeout = ?, enabled = ?
                    WHERE name = ?""",
                    [q['description'], q['priority'], q['max_workers'],
                     q['timeout'], 1 if q['enabled'] else 0, q['name']]
                )
            else:
                data_source.execute(
                    """INSERT INTO task_queues
                    (name, description, priority, max_workers, timeout,
                     enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    [q['name'], q['description'], q['priority'],
                     q['max_workers'], q['timeout'], 1 if q['enabled'] else 0]
                )
            count += 1
        except Exception as e:
            logger.error("Failed to init queue %s: %s", q['name'], e)

    data_source.commit()
    logger.info("Task queues seeded: %d queues", count)


def init_scheduled_tasks(data_source):
    tasks = [
        {
            'code': 'db_analyze',
            'name': '数据库统计信息更新',
            'category': 'system',
            'handler': 'db_analyze',
            'trigger_mode': 'cron',
            'schedule': '0 3 * * *',
            'queue': 'background',
            'priority': 100,
            'timeout': 300,
            'max_retries': 3,
            'handler_config': '{}',
            'description': '每天凌晨3点执行 ANALYZE 更新统计信息',
            'enabled': True,
        },
        {
            'code': 'db_vacuum',
            'name': '数据库空间回收',
            'category': 'system',
            'handler': 'db_vacuum',
            'trigger_mode': 'cron',
            'schedule': '0 4 * * 0',
            'queue': 'background',
            'priority': 100,
            'timeout': 600,
            'max_retries': 2,
            'handler_config': '{}',
            'description': '每周日凌晨4点执行 VACUUM 回收空间',
            'enabled': True,
        },
        {
            'code': 'db_integrity_check',
            'name': '数据库完整性检查',
            'category': 'system',
            'handler': 'db_integrity_check',
            'trigger_mode': 'cron',
            'schedule': '0 6 * * *',
            'queue': 'background',
            'priority': 100,
            'timeout': 120,
            'max_retries': 2,
            'handler_config': '{}',
            'description': '每天凌晨6点执行 PRAGMA integrity_check',
            'enabled': True,
        },
        {
            'code': 'db_checkpoint',
            'name': 'WAL检查点',
            'category': 'system',
            'handler': 'db_checkpoint',
            'trigger_mode': 'cron',
            'schedule': '*/5 * * * *',
            'queue': 'critical',
            'priority': 10,
            'timeout': 60,
            'max_retries': 5,
            'handler_config': '{}',
            'description': '每5分钟执行 WAL checkpoint 防止WAL文件过大',
            'enabled': True,
        },
        {
            'code': 'audit_failure_retry',
            'name': '审计日志失败重试',
            'category': 'audit',
            'handler': 'audit_failure_retry',
            'trigger_mode': 'cron',
            'schedule': '*/10 * * * *',
            'queue': 'business',
            'priority': 50,
            'timeout': 120,
            'max_retries': 3,
            'handler_config': '{"batch_size": 100, "max_retries": 3}',
            'description': '每10分钟重试写入失败的审计日志',
            'enabled': True,
        },
        {
            'code': 'audit_log_cleanup',
            'name': '审计日志清理',
            'category': 'audit',
            'handler': 'audit_log_cleanup',
            'trigger_mode': 'cron',
            'schedule': '0 2 * * *',
            'queue': 'background',
            'priority': 100,
            'timeout': 300,
            'max_retries': 2,
            'handler_config': '{"retention_days": {"business": 365, "security": 2555, "operation": 90, "performance": 30, "system": 90}}',
            'description': '每天凌晨2点按分类清理过期审计日志',
            'enabled': True,
        },
        {
            'code': 'import_queue_processor',
            'name': '导入队列处理器',
            'category': 'business',
            'handler': 'import_queue_processor',
            'trigger_mode': 'cron',
            'schedule': '*/2 * * * *',
            'queue': 'business',
            'priority': 50,
            'timeout': 300,
            'max_retries': 2,
            'handler_config': '{}',
            'description': '每2分钟检查导入队列并处理',
            'enabled': True,
        },
    ]

    count = 0
    for task in tasks:
        try:
            existing = data_source.query(
                "SELECT id FROM scheduled_tasks WHERE code = ?",
                (task['code'],)
            )
            if existing:
                data_source.execute(
                    """UPDATE scheduled_tasks SET
                        name = ?, category = ?, handler = ?,
                        trigger_mode = ?, schedule = ?, queue = ?,
                        priority = ?, timeout = ?, max_retries = ?,
                        handler_config = ?, description = ?,
                        enabled = ?
                    WHERE code = ?""",
                    [task['name'], task['category'], task['handler'],
                     task['trigger_mode'], task['schedule'], task['queue'],
                     task['priority'], task['timeout'], task['max_retries'],
                     task['handler_config'], task['description'],
                     1 if task['enabled'] else 0, task['code']]
                )
            else:
                data_source.execute(
                    """INSERT INTO scheduled_tasks
                    (code, name, category, handler, trigger_mode,
                     schedule, queue, priority, timeout, max_retries,
                     handler_config, description, enabled,
                     created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    datetime('now'))""",
                    [task['code'], task['name'], task['category'],
                     task['handler'], task['trigger_mode'],
                     task['schedule'], task['queue'],
                     task['priority'], task['timeout'],
                     task['max_retries'], task['handler_config'],
                     task['description'], 1 if task['enabled'] else 0]
                )
            count += 1
        except Exception as e:
            logger.error("Failed to init task %s: %s", task['code'], e)

    data_source.commit()
    logger.info("Scheduled tasks seeded: %d tasks", count)