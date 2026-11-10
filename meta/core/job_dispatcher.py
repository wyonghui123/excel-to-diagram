# -*- coding: utf-8 -*-
"""后台作业 dispatcher（P1 影子记账 + P2 claim/lease 执行）。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md
    §6 Dispatcher / §7 Executor / §10 P1–P2

每次 tick 分两步（spec §6.1）:
  1. 记账：读到期触发器 → 建 run（`run_key='<trigger_id>:<scheduled_for>'`
     天然幂等）→ 用"旧值乐观匹配"推进 `next_run_at`；
  2. 执行（仅非 DRY_RUN）：`retrying` 到期放行 → `pending` 领取（claim/lease）
     → 置 `running` → 交给 `ExecutorRegistry` 在受控线程里跑一次 → 写回结果；
     最后回收过期租约（崩溃的 claimed/running）。

`JOB_DISPATCH_DRY_RUN=1` 时只建 run 并立刻置 `skipped`：只记账、不执行、
不产生 pending 堆积，用于与现有进程内 Scheduler 做 24h 次数比对。

执行体不在本模块内联实现：通过 `ExecutorRegistry` 按 `job_definitions.handler`
查找。未传 `executor_pool` 时在 tick 线程内联执行（测试/单进程小作业），
传了则 `submit` 到调用方提供的线程池（生产接 `TaskQueueManager` 的池）。
本模块**不新建线程池**（spec §6.5）。

环境开关（只影响 tick 行为，不改变现有调度）::

    JOB_DISPATCH_ENABLED=1   # 打开 tick（默认 0）
    JOB_DISPATCH_DRY_RUN=1   # 影子模式（默认 0）
"""

import json
import logging
import os
import threading
import time
from datetime import datetime

from meta.core.cron_parser import CronParser
from meta.core.job_executor_registry import (
    DEFAULT_TIMEOUT_SECONDS, ExecutorRegistry, JobContext,
)
from meta.core.job_params import (
    job_params_schema, merge_job_params, sanitize_params,
)
from meta.core.job_run_store import (
    DEFAULT_LEASE_SECONDS, JobRunStore, current_worker_id, utc_epoch,
)

logger = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL = 5.0
DEFAULT_TICK_BATCH = 50


def _env_flag(name: str, default: str = '0') -> bool:
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes')


class JobDispatcher:
    """把到期触发器变成 `task_runs`，并驱动 claim/执行/回收的 dispatcher。"""

    def __init__(self, store: JobRunStore, *, enabled=None, dry_run=None,
                 tick_interval=DEFAULT_TICK_INTERVAL, batch=DEFAULT_TICK_BATCH,
                 clock=None, cron_parser=None, registry=None,
                 executor_pool=None):
        self.store = store
        self.enabled = (_env_flag('JOB_DISPATCH_ENABLED') if enabled is None
                        else bool(enabled))
        self.dry_run = (_env_flag('JOB_DISPATCH_DRY_RUN') if dry_run is None
                        else bool(dry_run))
        self.tick_interval = float(tick_interval)
        self.batch = int(batch)
        self._clock = clock or utc_epoch
        self._cron = cron_parser or CronParser()
        self.registry = registry or ExecutorRegistry()
        self._pool = executor_pool
        self._stop_event = threading.Event()
        self._thread = None

    # ── 单次 tick ─────────────────────────────────────────────────────────

    def tick(self, now=None) -> dict:
        """处理一批到期触发器并驱动执行，返回本次摘要（不抛异常）。"""
        now = self._clock() if now is None else float(now)
        summary = {
            'enabled': self.enabled, 'dry_run': self.dry_run, 'due': 0,
            'recorded': 0, 'skipped': 0, 'advanced': 0,
            'duplicates': 0, 'errors': 0,
            'promoted': 0, 'reclaimed': 0, 'claimed': 0,
            'claim_conflicts': 0,
        }
        if not self.enabled:
            return summary

        # 先放行到期的重试，再建新 run：本轮回收的租约留到下一轮 promote，
        # 使 `retrying` 状态可被观测（spec §10 P2 验收）。
        if not self.dry_run:
            summary['promoted'] = len(self.store.promote_retries(now))

        due = self.store.due_triggers(now, self.batch)
        summary['due'] = len(due)
        for trigger in due:
            try:
                self._process_trigger(trigger, now, summary)
            except Exception as exc:  # 单个触发器失败不影响整批
                summary['errors'] += 1
                logger.warning('[dispatcher] trigger %s 处理失败: %s',
                               trigger.get('id'), exc)

        if not self.dry_run:
            self._dispatch_pending(now, summary)
            summary['reclaimed'] = len(self.store.reclaim_expired(now))
        return summary

    def _process_trigger(self, trigger, now, summary) -> None:
        job = self.store.job_by_id(trigger['job_id'])
        if not job:
            summary['errors'] += 1
            logger.warning('[dispatcher] trigger %s 引用了不存在的 job_id=%s',
                           trigger.get('id'), trigger.get('job_id'))
            return

        scheduled_for = float(trigger['next_run_at'])
        run_key = '%d:%d' % (int(trigger['id']), int(scheduled_for))
        existing = self.store.find_run_by_key(run_key)
        run_id = self.store.create_run(
            job['code'], trigger_id=int(trigger['id']),
            params=merge_job_params(job, self._trigger_params(trigger)),
            scheduled_for=scheduled_for,
            run_key=run_key, now=now)
        if run_id is None:
            summary['errors'] += 1
            return
        if existing:
            summary['duplicates'] += 1
        else:
            summary['recorded'] += 1

        if self.dry_run and not existing:
            if self.store.mark_skipped(run_id, note='dry_run', now=now):
                summary['skipped'] += 1

        next_at = self._next_run_at(trigger, now)
        if next_at is None:
            summary['errors'] += 1
            logger.warning('[dispatcher] trigger %s 无法推算下次时间（cron=%r）',
                           trigger.get('id'), trigger.get('cron_expr'))
            return
        if self.store.advance_trigger(int(trigger['id']), scheduled_for,
                                      next_at, now=now):
            summary['advanced'] += 1

    # ── 执行（P2：claim / lease / executor）─────────────────────────────

    def _dispatch_pending(self, now, summary) -> None:
        """领取一批 `pending` run 并交给 executor（claim 在 tick 线程内完成）。"""
        for run in self.store.pending_runs(now, self.batch):
            run_id = int(run['id'])
            job = self.store.job_by_id(run['job_id'])
            if not job or str(job.get('status') or '').lower() != 'active':
                if self.store.mark_skipped(run_id, note='job_inactive', now=now):
                    summary['skipped'] += 1
                continue

            params, error = sanitize_params(run.get('params'),
                                            job_params_schema(job))
            if error:
                summary['errors'] += 1
                self.store.mark_dead(run_id, error='params 校验失败: %s' % error,
                                     now=now)
                logger.warning('[dispatcher] run=%s 参数被拒: %s',
                               run_id, error)
                continue

            worker_id = '%s#%d' % (current_worker_id(), run_id)
            lease = self._lease_seconds(job)
            if not self.store.claim(run_id, worker_id, lease_seconds=lease,
                                    now=now):
                summary['claim_conflicts'] += 1
                continue
            if not self.store.start(run_id, worker_id, now=now):
                summary['claim_conflicts'] += 1
                continue

            summary['claimed'] += 1
            if self._pool is not None:
                self._pool.submit(self._execute_run, run, job, worker_id,
                                  params)
            else:
                self._execute_run(run, job, worker_id, params)

    def _execute_run(self, run, job, worker_id, params=None) -> None:
        """跑一次尝试并写回账本；executor 抛错/超时均落 `failed` 分支。"""
        run_id = int(run['id'])
        timeout = float(job.get('timeout_seconds') or DEFAULT_TIMEOUT_SECONDS)
        ctx = JobContext(
            run_id=run_id, job_code=job['code'],
            params=params if params is not None else (run.get('params') or {}),
            attempt=int(run.get('attempt') or 1),
            deadline_monotonic=time.monotonic() + timeout,
            cancel_event=threading.Event(),
        )
        result = self.registry.execute(job['handler'], ctx, timeout=timeout)
        try:
            state = self.store.finish(run_id, worker_id, result.success,
                                      result=result.data, error=result.error,
                                      now=self._clock())
        except Exception as exc:  # 账本写失败：run 留在 running，等租约回收
            logger.warning('[dispatcher] run=%s 写回结果失败: %s', run_id, exc)
            return
        if state is None:
            logger.warning('[dispatcher] run=%s 写回被拒（非持有者或已终态）',
                           run_id)
        else:
            logger.info('[dispatcher] run=%s handler=%s → %s',
                        run_id, job['handler'], state)

    @staticmethod
    def _lease_seconds(job) -> int:
        """租约覆盖整个执行窗口，避免长作业被同进程 watchdog 误回收。"""
        return max(DEFAULT_LEASE_SECONDS,
                   int(float(job.get('timeout_seconds') or 0)) + 30)

    # ── 触发器辅助 ───────────────────────────────────────────────────────

    @staticmethod
    def _trigger_params(trigger) -> dict:
        raw = trigger.get('params_override')
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _next_run_at(self, trigger, now: float):
        interval = trigger.get('interval_seconds')
        if interval:
            return now + float(interval)
        expr = (trigger.get('cron_expr') or '').strip()
        if not expr:
            return None
        try:
            base = datetime.fromtimestamp(float(trigger['next_run_at']))
            nxt = self._cron.get_next(expr, base)
        except Exception as exc:
            logger.warning('[dispatcher] cron 解析失败 %r: %s', expr, exc)
            return None
        return nxt.timestamp() if nxt else None

    # ── 常驻循环（server.py 由 JOB_DISPATCH_ENABLED 控制接入）────────────

    def start(self) -> bool:
        if not self.enabled or self._thread is not None:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name='job-dispatcher', daemon=True)
        self._thread.start()
        logger.info('[dispatcher] started (dry_run=%s, interval=%ss)',
                    self.dry_run, self.tick_interval)
        return True

    def stop(self, timeout=5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.wait(self.tick_interval):
            try:
                summary = self.tick()
                if summary['due']:
                    logger.info('[dispatcher] tick %s', summary)
            except Exception as exc:
                logger.warning('[dispatcher] tick 异常: %s', exc)