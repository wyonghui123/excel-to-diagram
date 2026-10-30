import pytest

pytestmark = pytest.mark.unit

# task_queues 无 Factory；按仓库既有惯例走 raw SQL escape hatch（同 test_task_tick.py）。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

# -*- coding: utf-8 -*-
"""
TaskQueueManager 队列配置单源 / 同名去重测试（task-two-generation S2）

覆盖目标：
  1. 同 config 连续 register_queue 两次 → 同名 executor 只有 1 个（旧池被 shutdown）
  2. 临时 SQLite 建 task_queues 并插入 5 行 → load_queues_from_db 后 get_queue_stats 显示 5 队列
"""

from meta.core.task_queue_manager import TaskQueueManager, QueueConfig
from meta.core.task_infra_schema import ensure_task_infra_tables

SEED_QUEUES = (
    ('critical', 10, 2, 600),
    ('ai_high', 20, 3, 1200),
    ('ai_normal', 30, 5, 1800),
    ('business', 50, 3, 300),
    ('background', 100, 2, 600),
)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "queues.db"))
    ensure_task_infra_tables(source)
    yield source


def test_register_queue_duplicate_no_executor_leak():
    """同名队列重复注册：executor 被替换且旧池关闭，不新增条目。"""
    manager = TaskQueueManager()
    config = QueueConfig(name='business', priority=50, max_workers=3, timeout=300, enabled=True)

    manager.register_queue(config)
    first_executor = manager._executors['business']

    manager.register_queue(config)

    assert len(manager._executors) == 1
    assert len(manager._queues) == 1
    assert manager._executors['business'] is not first_executor
    # 旧线程池已被 shutdown（_shutdown 为 True）
    assert first_executor._shutdown is True

    manager.shutdown()


def test_load_queues_from_db_registers_five_queues(ds):
    """DB 播种 5 行 → load_queues_from_db 后 get_queue_stats 有 5 个队列。"""
    for name, priority, max_workers, timeout in SEED_QUEUES:
        ds.execute(
            "INSERT INTO task_queues (name, priority, max_workers, timeout, enabled) "
            "VALUES (?, ?, ?, ?, 1)",
            (name, priority, max_workers, timeout),
        )

    manager = TaskQueueManager(ds)
    manager.load_queues_from_db()

    stats = manager.get_queue_stats()
    assert len(stats) == 5
    assert {s['name'] for s in stats} == {row[0] for row in SEED_QUEUES}
    assert len(manager._executors) == 5

    manager.shutdown()
