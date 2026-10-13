# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)


def init_task_seed_data(data_source):
    _ensure_task_tables(data_source)
    init_task_queues(data_source)
    cleanup_legacy_scheduled_tasks(data_source)


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


def cleanup_legacy_scheduled_tasks(data_source):
    """清理 scheduled_tasks 中已迁出的 cron 作业行（替换路径 第 3 项，幂等）。

    替换路径 第 1 / 7 项已把 9 个 cron 作业全部迁到进程内调度器
    （`MaintenanceScheduler` 8 个运维 + `PlatformScheduler` 的 platform_tick），
    调度配置内嵌代码、不落库。此前这些作业在 `scheduled_tasks` 表各留一行；
    遗留 `TaskScheduler` 现仅保留队列与手工触发基础设施，不再有 cron 作业行。

    本函数把这些已迁出作业码对应的历史行删除（幂等：重复调用无副作用）。
    只删「已迁出的作业码」（`maintenance_scheduler.JOB_CODES` 为唯一权威边界），
    非迁移行（如遗留手工触发行）保持不变。

    调用时机：`init_task_seed_data` 每次服务启动都会执行本函数 —— 故即便实例曾
    遗留旧的作业行，启动后也会被清掉。
    """
    from meta.core.maintenance_scheduler import JOB_CODES

    codes = sorted(JOB_CODES)
    if not codes:
        return

    placeholders = ','.join('?' * len(codes))
    try:
        rows = data_source.query(
            f"SELECT COUNT(*) AS cnt FROM scheduled_tasks "
            f"WHERE code IN ({placeholders})",
            tuple(codes)
        )
        removed = rows[0]['cnt'] if rows else 0
        if not removed:
            return
        data_source.execute(
            f"DELETE FROM scheduled_tasks WHERE code IN ({placeholders})",
            tuple(codes)
        )
        data_source.commit()
        logger.info("Legacy scheduled tasks cleaned: %d rows", removed)
    except Exception as e:
        logger.error("Failed to clean legacy scheduled tasks: %s", e)
