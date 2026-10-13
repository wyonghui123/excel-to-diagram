# -*- coding: utf-8 -*-
"""[P1 2026-10-13] 运维调度器 —— 把运维作业从任务体系上解耦

为什么要有这个模块:
  server.py 启动遗留 `TaskScheduler`，其上注册 9 个 handler。但**只有
  `platform_tick` 属于任务域**（A5 平台心跳：派工 + 认领超时回收 + SLA 升级扫描）；
  其余 8 个是纯运维作业，只是「借调度器跑 cron」：

      DB 维护4 个   db_analyze / db_vacuum / db_integrity_check / db_checkpoint
      审计运维 3 个 audit_failure_retry / audit_log_cleanup / audit_log_archive
      导入队列 1 个 import_queue_processor

  它们与任务模型（11 态、事件账、executor、收件箱）**毫无关系**，却被迫依赖
  `scheduled_tasks` / `task_queues` / `task_executions` 三张任务域表来记录调度。
  这是「用任务体系背运维债」，也是替换遗留任务体系的隐性阻塞：删任务域表会连带
  停掉 DB 维护与审计归档。

本模块的处置:
  运维作业的调度配置**内嵌在代码里**（`DEFAULT_JOBS`），由独立后台线程驱动，
  **不读写任何任务域表**。执行契约与原调度器完全一致（同一批 handler、同一套
  context 形状、cron 表达式照搬），故行为等价、运维 SLA 不变。

与遗留调度器的分工:
  - 运维 8 个 → 本调度器
  - platform_tick → `PlatformScheduler`（`meta/core/platform_scheduler.py`，替换路径第 1 项）

  两类作业都迁出后，遗留 TaskScheduler 不再承载任何 cron 作业，仅保留队列与
  手工触发基础设施；`scheduled_tasks` 的历史行清理属替换路径第 3 项，待新调度器
  稳定运行后单独做。

处置边界:
  - 本模块**不新增** handler，只复用既有 handler 实例（同一批类，不复制逻辑）。
  - handler 签名 `execute(params, context)` 与既有 8 个实现完全兼容：它们只读
    `context['data_source']` 与可选 `context['handler_config']`。
  - 不碰 `scheduled_tasks` 表的既有行（迁移期由 `init_task_seed` 保持幂等）；
    待运维作业在新调度器上稳定运行后，再清理遗留表中的运维行。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md（§12.1A5/A9 与替换路径）
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from meta.core.cron_parser import CronParser

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 内置运维作业配置
#
# cron 表达式照搬原 architecture.db `scheduled_tasks` 表的 8 条运维行 —— 改cron
# 等于改运维 SLA，故测试对本表做逐条等值锁定（test_maintenance_scheduler.py）。
# ─────────────────────────────────────────────────────────────────────────────

#: 运维作业（与任务域无关，由本调度器管辖）
DEFAULT_JOBS: List[Dict] = [
    # ── DB 维护 ──
    {'code': 'db_analyze', 'handler': 'db_analyze',
     'schedule': '0 3 * * *', 'trigger_mode': 'cron', 'enabled': True},
    {'code': 'db_vacuum', 'handler': 'db_vacuum',
     'schedule': '0 4 * * 0', 'trigger_mode': 'cron', 'enabled': True},
    {'code': 'db_integrity_check', 'handler': 'db_integrity_check',
     'schedule': '0 6 * * *', 'trigger_mode': 'cron', 'enabled': True},
    {'code': 'db_checkpoint', 'handler': 'db_checkpoint',
     'schedule': '*/5 * * * *', 'trigger_mode': 'cron', 'enabled': True},
    # ── 审计运维 ──
    {'code': 'audit_failure_retry', 'handler': 'audit_failure_retry',
     'schedule': '*/10 * * * *', 'trigger_mode': 'cron', 'enabled': True},
    {'code': 'audit_log_cleanup', 'handler': 'audit_log_cleanup',
     'schedule': '0 2 * * *', 'trigger_mode': 'cron', 'enabled': True},
    {'code': 'audit_log_archive', 'handler': 'audit_log_archive',
     'schedule': '0 1 * * 0', 'trigger_mode': 'cron', 'enabled': True},
    # ── 导入队列 ──
    {'code': 'import_queue_processor', 'handler': 'import_queue_processor',
     'schedule': '*/2 * * * *', 'trigger_mode': 'cron', 'enabled': True},
]

#: 任务域专属作业 —— **不由本调度器管辖**。
#: platform_tick（A5 平台心跳：派工 / 认领超时回收 / SLA 升级 / 对账）归
#: `PlatformScheduler`（`meta/core/platform_scheduler.py`）。
#: 本常量保留作「分工边界」的自检锚点：运维集合不得混入它。
TASK_DOMAIN_CODES: frozenset = frozenset({'platform_tick'})

OPS_JOB_CODES: frozenset = frozenset(j['code'] for j in DEFAULT_JOBS)

#: 运维 + 任务域的并集（供自检与文档引用）
JOB_CODES: frozenset = OPS_JOB_CODES | TASK_DOMAIN_CODES


class MaintenanceScheduler:
    """独立的运维 cron 调度器（不依赖任务域表）。

    与遗留 `TaskScheduler` 的差别只有一处、也是关键的一处：**调度状态不落库**。
    遗留调度器把「有哪些作业、什么时候跑」存在 `scheduled_tasks` 表里，本调度器
    把它们放在内存常量 `DEFAULT_JOBS` 里。因此本类不 import、不查询任何任务域表。

    执行契约照搬既有 handler 的实际用法（`context` 是 dict 而非 dataclass）：
        handler.execute(params, context)
        context = {'data_source':…, 'handler_config': {…}}
    """

    def __init__(self, data_source=None, jobs: Optional[List[Dict]] = None,
                 config: Optional[Dict] = None):
        self.data_source = data_source
        self.config = config or {}
        self._jobs: List[Dict] = list(jobs if jobs is not None else DEFAULT_JOBS)
        self._cron = CronParser()
        self._handlers: Dict[str, Callable] = {}
        self._next_run: Dict[str, Optional[datetime]] = {}
        self._last_result: Dict[str, object] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval = self.config.get('check_interval', 60)
        self._calculate_next_run()

    # ── 注册 ──────────────────────────────────────────────────────────────

    def register_handler(self, name: str, handler) -> None:
        """注册 handler（接受 TaskHandler 实例或裸 callable）。

        既有 8 个 handler 继承 `TaskHandler`，但真正被调的是它们的
        `.execute(params, context)` —— 与遗留调度器 `register_handler` 的行为一致。
        """
        self._handlers[name] = handler.execute if hasattr(handler, 'execute') else handler
        logger.info("[MaintenanceScheduler] Handler registered: %s", name)

    def is_registered(self, code: str) -> bool:
        """该作业是否已具备可执行的 handler（自检用）。"""
        return code in self._handlers

    # ── 调度 ──────────────────────────────────────────────────────────────

    def _calculate_next_run(self) -> None:
        """按 cron 计算下次触发时间（仅 cron 作业）。"""
        now = datetime.now()
        for job in self._jobs:
            if job.get('trigger_mode', 'cron') != 'cron':
                self._next_run[job['code']] = None
                continue
            try:
                self._next_run[job['code']] = self._cron.get_next(job['schedule'], now)
            except Exception as e:
                logger.error(
                    "[MaintenanceScheduler] Bad cron for %s (%s): %s",
                    job['code'], job.get('schedule'), e)
                self._next_run[job['code']] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name='maintenance-scheduler', daemon=True)
        self._thread.start()
        logger.info(
            "[MaintenanceScheduler] started, %d ops jobs: %s",
            len(self._jobs), sorted(self._handlers))

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("[MaintenanceScheduler] stopped")

    def _loop(self) -> None:
        import time
        while self._running:
            try:
                self.tick()
            except Exception as e:
                logger.error("[MaintenanceScheduler] tick failed: %s", e)
            time.sleep(self._interval)

    def tick(self, now: Optional[datetime] = None) -> List[str]:
        """扫描一次到期作业并触发。返回本次触发的作业 code 列表。"""
        now = now or datetime.now()
        fired: List[str] = []
        for job in list(self._jobs):
            code = job['code']
            if not job.get('enabled', True):
                continue
            due = self._next_run.get(code)
            if due is None or now < due:
                continue
            if self.run_now(code):
                fired.append(code)
            # 重排下次；cron 非法时 get_next 返回 None，等下次 tick 再试
            self._next_run[code] = self._cron.get_next(job['schedule'], now)
        return fired

    # ── 执行 ──────────────────────────────────────────────────────────────

    def run_now(self, code: str) -> bool:
        """立即执行一个作业（不查表、不落任务域表）。返回是否成功派发。"""
        handler = self._handlers.get(code)
        if handler is None:
            logger.warning(
                "[MaintenanceScheduler] no handler registered for %s, skipped", code)
            return False
        job = next((j for j in self._jobs if j['code'] == code), {})
        context = {
            'data_source': self.data_source,
            'handler_config': job.get('handler_config') or {},
        }
        try:
            self._last_result[code] = handler(job.get('handler_config') or {}, context)
        except Exception as e:
            logger.error("[MaintenanceScheduler] job %s raised: %s", code, e)
            self._last_result[code] = e
        return True

    def status(self) -> Dict[str, Dict]:
        """自检视图：作业配置 / 下次触发 / 是否已注册 handler。"""
        return {
            job['code']: {
                'schedule': job['schedule'],
                'next_run_at': self._next_run.get(job['code']).__str__()
                if self._next_run.get(job['code']) else None,
                'handler_registered': self.is_registered(job['code']),
                'enabled': job.get('enabled', True),
            }
            for job in self._jobs
        }