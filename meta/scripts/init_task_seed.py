# -*- coding: utf-8 -*-
import logging

from meta.core.task_infra_schema import ensure_task_infra_tables

logger = logging.getLogger(__name__)


def init_task_seed_data(data_source):
    # 建表唯一真源：meta/core/task_infra_schema.py（task_queues / task_executions）
    ensure_task_infra_tables(data_source)
    init_task_queues(data_source)


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


