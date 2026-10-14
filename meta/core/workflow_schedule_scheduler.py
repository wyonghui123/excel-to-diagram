# -*- coding: utf-8 -*-
"""[C 组编排完整] Workflow 定时调度器 —— 扫已发布的 schedule 声明 → 到点唤起 Run

为什么要有这个模块:
  `trigger_kind='schedule'` 在 `TRIGGER_KINDS` 里早已占位，但 C3 触发管道只实现了
  `event`（`parse_trigger_expr` 对非 event 直接放行、不解释 expr）。于是 `schedule`
  是一个「有值域、无行为」的 kind —— 声明了 cron 也永不触发，属静默失败。

本模块把这条空挂点接上:
  - 定义期：`parse_trigger_expr` 扩展为「schedule 必须声明 JSON 对象含非空 cron」，
    经 `publish_workflow` 的定义期闸门自动生效（写坏 cron 在发布时即被拒）。
  - 运行期：本调度器周期性扫**每个 workflow_key 的最新版**中 `trigger_kind='schedule'`
    的定义，把 `cron` 派生为一条调度作业；到点调 `workflow_engine.start_run()`。

纪律:
  - **不落任务域表**：调度状态全在内存（沿用 `MaintenanceScheduler` 的处置边界）。
    「有哪些 schedule 定义」来自 `workflows` 定义表，属编排域，不是任务域调度表。
  - **不发明第二套 cron**：复用 `meta.core.cron_parser.CronParser`（与运维作业同一口径）。
  - **只唤起 Run，不写对象表**（「不越权」，综合缝合 §5.5）。

与 `MaintenanceScheduler` / `PlatformScheduler` 的分工:
  - 运维 8 个作业 → `MaintenanceScheduler`
  - `platform_tick` → `PlatformScheduler`
  - **workflow 定时** → 本调度器（作业集从定义表派生，而非代码常量）

  三者作业集互不相交；本模块继承基类只为复用 tick/cron/线程骨架，作业集完全由
  已发布定义决定。

对应方案:
  docs/superpowers/specs/2026-10-14-workflow-schedule-and-platform-ops-jobs.md §3.1
  docs/superpowers/specs/2026-09-07-task-model-design.md §12.1 C 组
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from meta.core.maintenance_scheduler import MaintenanceScheduler
from meta.core.workflow_definition import WorkflowDefinitionError
from meta.core.workflow_engine import start_run
from meta.core.workflow_store import list_latest_workflows
from meta.core.workflow_trigger import TRIGGER_SCHEDULE, parse_trigger_expr

logger = logging.getLogger(__name__)

#: 派生日志用的 handler 名（本调度器无外部 handler；仅供作业形状与状态视图对齐）
SCHEDULE_HANDLER = "workflow_schedule"


class WorkflowScheduleScheduler(MaintenanceScheduler):
    """把 `trigger_kind='schedule'` 的定义派生为 cron 作业并到点唤起 Run。

    作业集**不来自代码常量**，而由 `_load_jobs()` 从定义表实时派生：
        code      = workflow_key（定义层「生效版」语义）
        schedule  = 定义声明里解析出的 cron（`trigger_expr.cron`）
        handler   = SCHEDULE_HANDLER（占位；`run_now` 被覆盖为直接 start_run）

    因此定义的新增/改版/删除会在下一次 `tick`（或 `refresh_jobs`）后自动生效，
    无需重启进程。
    """

    def __init__(self, data_source=None, config: Optional[Dict] = None):
        # jobs=[] 起步：邻接表由 _load_jobs 派生（基类 _calculate_next_run 对空集无害）
        super().__init__(data_source=data_source, jobs=[], config=config)
        # 启动即派生一次，让 status()/is_registered() 在首个 tick 前就可用
        self.refresh_jobs()

    # ── 作业集派生 ────────────────────────────────────────────────────────

    def _load_jobs(self) -> List[Dict]:
        """扫每个 workflow_key 最新版中 trigger_kind='schedule' 的定义 → 作业列表。

        单条定义解析失败（历史脏数据）只跳过并告警，不让一条坏定义拖垮整轮派生。
        """
        jobs: List[Dict] = []
        for workflow in list_latest_workflows(self.data_source,
                                              trigger_kind=TRIGGER_SCHEDULE):
            key = workflow.get("workflow_key")
            try:
                spec = parse_trigger_expr(workflow.get("trigger_kind"),
                                          workflow.get("trigger_expr"))
            except WorkflowDefinitionError as e:
                logger.error(
                    "[WorkflowScheduleScheduler] 定义 %s 触发声明非法，跳过: %s",
                    key, e)
                continue
            jobs.append({
                'code': key,
                'handler': SCHEDULE_HANDLER,
                'schedule': spec.cron,
                'trigger_mode': 'cron',
                'enabled': True,
                'workflow_key': key,
                'version': workflow.get("version"),
                'name': workflow.get("name") or "",
            })
        return jobs

    def refresh_jobs(self, now: Optional[datetime] = None) -> List[str]:
        """重派生作业集；**增量**保留 schedule 未变 code 的下次触发时间。

        Returns:
            重派生后的作业 code 列表（按定义表顺序）
        """
        now = now or datetime.now()
        new_jobs = self._load_jobs()
        old = {job['code']: job for job in self._jobs}

        next_run: Dict[str, Optional[datetime]] = {}
        for job in new_jobs:
            code = job['code']
            prev = old.get(code)
            if (prev is not None and prev.get('schedule') == job['schedule']
                    and code in self._next_run):
                # schedule 未变 → 沿用已算好的下次触发（避免每次 tick 都重算漂移）
                next_run[code] = self._next_run[code]
            else:
                next_run[code] = self._safe_next(job['schedule'], now)

        self._jobs = new_jobs
        self._next_run = next_run
        return [job['code'] for job in new_jobs]

    def _safe_next(self, schedule: str, now: datetime) -> Optional[datetime]:
        """计算下次触发；cron 非法返回 None（等下次 tick 再试）。"""
        try:
            return self._cron.get_next(schedule, now)
        except Exception as e:      # noqa: BLE001 —— 坏 cron 不该中断整轮
            logger.error(
                "[WorkflowScheduleScheduler] Bad cron %r: %s", schedule, e)
            return None

    # ── 调度 ──────────────────────────────────────────────────────────────

    def tick(self, now: Optional[datetime] = None) -> List[str]:
        """先重派生作业集，再走基类到期扫描（定义增删在每轮自动生效）。"""
        now = now or datetime.now()
        self.refresh_jobs(now)
        return super().tick(now)

    # ── 执行 ──────────────────────────────────────────────────────────────

    def run_now(self, code: str) -> bool:
        """立即唤起一个 schedule 定义的 Run。返回是否成功派发。

        与基类「派发即 True」语义一致：code 非法 → False；`start_run` 异常
        记入 `_last_result` 并返回 True（异常已在日志与结果里可见）。
        """
        if code not in self.codes():
            logger.warning(
                "[WorkflowScheduleScheduler] %s 不是已发布 schedule 定义，跳过",
                code)
            return False
        try:
            self._last_result[code] = start_run(
                self.data_source, workflow_key=code,
                trigger_kind=TRIGGER_SCHEDULE)
        except Exception as e:      # noqa: BLE001 —— 唤起失败不该杀调度线程
            logger.error(
                "[WorkflowScheduleScheduler] run_now(%s) 唤起失败: %s", code, e)
            self._last_result[code] = e
        return True

    def is_registered(self, code: str) -> bool:
        """该 code 是否为当前派生的 schedule 作业（覆盖基类的 handler 判定）。"""
        return code in self.codes()

    def codes(self) -> Set[str]:
        """当前派生的作业 code 集合。"""
        return {job['code'] for job in self._jobs}
