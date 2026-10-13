# -*- coding: utf-8 -*-
"""[P1 2026-10-13] 平台调度器 —— platform_tick 的独立进程内调度

为什么要有这个模块:
  替换路径第 7 项已把 8 个运维作业从遗留 TaskScheduler 迁到
  `MaintenanceScheduler`。本模块承接**任务域**的 `platform_tick`
  （A5 平台心跳：direct 派工 + 认领超时回收 + SLA 升级扫描 + 决策-生效对账），
  使其同样脱离 `scheduled_tasks` 表 —— 调度配置内嵌代码，不落库。

  迁完后遗留 TaskScheduler 不再承载任何 cron 作业，仅保留队列与手工触发
  基础设施；`scheduled_tasks` 表的历史行已由替换路径第 3 项清理
  （`init_task_seed` 不再播种、改为清理迁移作业行）。

复用而非重写:
  `PlatformScheduler` 直接继承 `MaintenanceScheduler` 的通用 in-process cron
  引擎（同一套 `tick` / `run_now` / `start` / `stop` 与 cron 计算），只换作业集。
  基类名字带 maintenance 是因为运维作业集是它的默认值，引擎本身与领域无关。

处置边界:
  - 本模块**不新增** handler，只复用 `PlatformTickHandler`（`meta/handlers/
    platform_handlers.py`）—— 它是 `platform_tick()` 的调度设施薄适配器。
  - platform_tick 自身的内务（事务 / 事件账 / 守卫）由被调模块自理；
    调度器只负责「何时调用」。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §12.1 A5 / §8.2
"""
from __future__ import annotations

from typing import Dict, List, Optional

from meta.core.maintenance_scheduler import MaintenanceScheduler

#: 任务域作业：platform_tick 每分钟一次（cron 照搬原 scheduled_tasks 行 ——
#: 改 cron 等于改平台心跳频率，故测试对 `* * * * *` 做等值锁定）
PLATFORM_JOBS: List[Dict] = [
    {'code': 'platform_tick', 'handler': 'platform_tick',
     'schedule': '* * * * *', 'trigger_mode': 'cron', 'enabled': True},
]

PLATFORM_JOB_CODES: frozenset = frozenset(j['code'] for j in PLATFORM_JOBS)


class PlatformScheduler(MaintenanceScheduler):
    """任务域调度器：驱动 `platform_tick`（A5 平台心跳）。

    与 `MaintenanceScheduler` 的唯一差别是作业集 —— 本类固定为 `PLATFORM_JOBS`，
    调用方无需再传 `jobs`，避免误把运维作业装进来。
    """

    def __init__(self, data_source=None, config: Optional[Dict] = None):
        super().__init__(data_source=data_source, jobs=PLATFORM_JOBS, config=config)