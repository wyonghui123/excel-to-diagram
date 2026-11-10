# -*- coding: utf-8 -*-
"""后台作业执行账本（`task_runs`）读写层。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md
    §5 状态机 / §6 Dispatcher / §12 风险 R2

职责:
  · 只管账本：创建 run、claim/lease、开始、续租、结束、回收、人工重试/取消；
  · 不执行任何作业，也不 import 具体 executor；
  · 所有写操作走 `data_source.execute`（写路径），并通过"写后回读"判定结果，
    不依赖 cursor 类型 / `RETURNING` / `lastrowid`（多连接下不可靠）。

状态机（与 spec §5 一致）::

    pending ─claim→ claimed ─start→ running ─→ succeeded
                        │              │
                        │ lease 过期    │ 失败
                        ↓              ↓
                     retrying ←──── failed
                        │              │ attempt >= max_attempts
                        ↓              ↓
                     pending          dead
"""

import json
import os
import socket
import threading
import time
import uuid

from meta.migrations.v246__background_job_infrastructure import (
    JOB_TABLE, TRIGGER_TABLE, RUN_TABLE,
)

#: `task_runs.status` 合法取值（spec §5）。
RUN_STATUSES = frozenset({
    'pending', 'claimed', 'running', 'succeeded',
    'failed', 'retrying', 'dead', 'cancelled', 'skipped',
})

#: 终态：不再被 dispatcher 领取。
TERMINAL_STATUSES = frozenset({'succeeded', 'dead', 'cancelled', 'skipped'})

DEFAULT_LEASE_SECONDS = 60
DEFAULT_BACKOFF_SECONDS = 60


def utc_epoch(now=None) -> float:
    """统一时间源：UTC epoch 秒（spec §12 R3）。"""
    return time.time() if now is None else float(now)


def current_worker_id() -> str:
    """`<hostname>:<pid>:<thread>`，便于排查租约归属。"""
    return '%s:%s:%s' % (socket.gethostname(), os.getpid(),
                         threading.current_thread().name)


class JobRunStore:
    """`task_runs` 的唯一写入者。

    调用方需传入具备 `query(sql, params)` / `execute(sql, params)` /
    `commit()` 的 data_source（生产为 `meta/core/datasource.py`，
    测试为 `meta/tests/inventory_test_doubles.py` 的 MemDS）。
    """

    def __init__(self, data_source, clock=None):
        self.ds = data_source
        self._clock = clock or utc_epoch

    # ── 基础读写 ──────────────────────────────────────────────────────────

    def _now(self, now=None) -> float:
        return self._clock() if now is None else float(now)

    def _commit(self) -> None:
        if not getattr(self.ds, 'in_transaction', False):
            self.ds.commit()

    def _rows(self, sql: str, params=None) -> list:
        return self.ds.query(sql, params or []) or []

    def _one(self, sql: str, params=None):
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    def _job(self, job_code: str):
        return self._one(
            'SELECT * FROM %s WHERE code=?' % JOB_TABLE, [job_code])

    def job_by_id(self, job_id: int):
        """按 id 取作业定义（dispatcher 从触发器反查作业用）。"""
        return self._one(
            'SELECT * FROM %s WHERE id=?' % JOB_TABLE, [int(job_id)])

    @staticmethod
    def _decode(row):
        if not row:
            return row
        raw = row.get('params')
        if raw:
            try:
                row['params'] = json.loads(raw)
            except (TypeError, ValueError):
                row['params'] = {}
        else:
            row['params'] = {}
        return row

    def get_run(self, run_id: int):
        return self._decode(self._one(
            'SELECT * FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)]))

    def find_run_by_key(self, run_key: str):
        """按 `run_key` 查 run（dispatcher 判定重复投递用）。"""
        return self._decode(self._one(
            'SELECT * FROM %s WHERE run_key=?' % RUN_TABLE, [run_key]))

    def list_runs(self, job_code=None, status=None, limit=50, offset=0) -> list:
        sql = 'SELECT * FROM %s WHERE 1=1' % RUN_TABLE
        params = []
        if job_code:
            job = self._job(job_code)
            sql += ' AND job_id=?'
            params.append(int(job['id']) if job else -1)
        if status:
            if status not in RUN_STATUSES:
                raise ValueError('非法 run 状态: %s' % status)
            sql += ' AND status=?'
            params.append(status)
        sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([int(limit), int(offset)])
        return [self._decode(row) for row in self._rows(sql, params)]

    # ── 创建 ──────────────────────────────────────────────────────────────

    def create_run(self, job_code: str, *, trigger_id=None, task_id=None,
                   params=None, scheduled_for=None, run_key=None,
                   max_attempts=None, now=None):
        """创建一个 `pending` run；`run_key` 冲突时返回已存在的 run id。

        返回 run id；作业定义不存在时返回 None（调用方负责告警）。
        """
        job = self._job(job_code)
        if not job:
            return None
        now = self._now(now)
        scheduled = now if scheduled_for is None else float(scheduled_for)
        run_key = run_key or 'manual:%s' % uuid.uuid4().hex
        attempts = int(job['max_attempts'] if max_attempts is None
                       else max_attempts)
        payload = json.dumps(params or {}, ensure_ascii=False, sort_keys=True)
        self.ds.execute(
            'INSERT OR IGNORE INTO %s '
            '(run_key, job_id, trigger_id, task_id, status, params, attempt, '
            ' max_attempts, scheduled_for, created_at, updated_at) '
            "VALUES (?, ?, ?, ?, 'pending', ?, 1, ?, ?, datetime('now'), "
            "datetime('now'))" % RUN_TABLE,
            [run_key, int(job['id']), trigger_id, task_id, payload, attempts,
             scheduled])
        self._commit()
        row = self._one(
            'SELECT id FROM %s WHERE run_key=?' % RUN_TABLE, [run_key])
        return int(row['id']) if row else None

    # ── claim / lease ─────────────────────────────────────────────────────

    def claim(self, run_id: int, worker_id: str,
              lease_seconds=DEFAULT_LEASE_SECONDS, now=None) -> bool:
        now = self._now(now)
        lease_until = now + int(lease_seconds)
        self.ds.execute(
            'UPDATE %s SET status=?, worker_id=?, claimed_at=?, '
            'lease_until=?, updated_at=datetime(\'now\') '
            "WHERE id=? AND status='pending'" % RUN_TABLE,
            ['claimed', worker_id, now, lease_until, int(run_id)])
        self._commit()
        row = self._one(
            'SELECT status, worker_id FROM %s WHERE id=?' % RUN_TABLE,
            [int(run_id)])
        return bool(row and row['status'] == 'claimed'
                    and row['worker_id'] == worker_id)

    def start(self, run_id: int, worker_id: str, now=None) -> bool:
        now = self._now(now)
        self.ds.execute(
            'UPDATE %s SET status=?, started_at=?, updated_at=datetime(\'now\') '
            "WHERE id=? AND status='claimed' AND worker_id=?" % RUN_TABLE,
            ['running', now, int(run_id), worker_id])
        self._commit()
        row = self._one(
            'SELECT status FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)])
        return bool(row and row['status'] == 'running')

    def renew_lease(self, run_id: int, worker_id: str,
                    lease_seconds=DEFAULT_LEASE_SECONDS, now=None) -> bool:
        now = self._now(now)
        lease_until = now + int(lease_seconds)
        self.ds.execute(
            'UPDATE %s SET lease_until=?, updated_at=datetime(\'now\') '
            "WHERE id=? AND status='running' AND worker_id=?" % RUN_TABLE,
            [lease_until, int(run_id), worker_id])
        self._commit()
        row = self._one(
            'SELECT lease_until FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)])
        return bool(row and row['lease_until'] is not None
                    and abs(float(row['lease_until']) - lease_until) < 1e-6)

    # ── 结束 / 重试 / 取消 ────────────────────────────────────────────────

    def finish(self, run_id: int, worker_id: str, success: bool,
               result=None, error=None, now=None):
        """结束一次尝试，返回新状态；非本人持有或已终态则返回 None。"""
        run = self.get_run(run_id)
        if not run or run['status'] not in ('claimed', 'running'):
            return None
        if run['worker_id'] != worker_id:
            return None

        now = self._now(now)
        started = run.get('started_at') or run.get('claimed_at') or now
        duration_ms = int(max(0.0, now - float(started)) * 1000)
        attempt = int(run.get('attempt') or 1)
        max_attempts = int(run.get('max_attempts') or 1)

        next_retry = None
        if success:
            new_status = 'succeeded'
        elif attempt < max_attempts:
            new_status = 'retrying'
            next_retry = now + self._backoff_seconds(run) * attempt
        else:
            new_status = 'dead'

        result_text = None
        if result is not None:
            result_text = (result if isinstance(result, str)
                           else json.dumps(result, ensure_ascii=False))
        self.ds.execute(
            'UPDATE %s SET status=?, finished_at=?, duration_ms=?, result=?, '
            'error=?, next_retry_at=?, lease_until=NULL, worker_id=NULL, '
            "updated_at=datetime('now') "
            "WHERE id=? AND status IN ('claimed','running') AND worker_id=?"
            % RUN_TABLE,
            [new_status, now, duration_ms, result_text, error, next_retry,
             int(run_id), worker_id])
        self._commit()
        row = self._one(
            'SELECT status FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)])
        return row['status'] if row and row['status'] == new_status else None

    def _backoff_seconds(self, run) -> int:
        job = self._one(
            'SELECT backoff_seconds FROM %s WHERE id=?' % JOB_TABLE,
            [int(run['job_id'])])
        if not job or job.get('backoff_seconds') is None:
            return DEFAULT_BACKOFF_SECONDS
        return int(job['backoff_seconds'])

    def retry(self, run_id: int, now=None) -> bool:
        """人工重试：`failed` / `dead` → `pending`，attempt 自增并放宽上限。"""
        run = self.get_run(run_id)
        if not run or run['status'] not in ('failed', 'dead'):
            return False
        now = self._now(now)
        attempt = int(run.get('attempt') or 1) + 1
        max_attempts = max(int(run.get('max_attempts') or 1), attempt)
        self.ds.execute(
            'UPDATE %s SET status=?, attempt=?, max_attempts=?, error=NULL, '
            'finished_at=NULL, next_retry_at=NULL, lease_until=NULL, '
            "worker_id=NULL, updated_at=datetime('now') "
            "WHERE id=? AND status IN ('failed','dead')" % RUN_TABLE,
            ['pending', attempt, max_attempts, int(run_id)])
        self._commit()
        row = self._one(
            'SELECT status FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)])
        return bool(row and row['status'] == 'pending')

    def cancel(self, run_id: int, now=None) -> bool:
        """人工取消（spec §13 Q3：运行中只标记，不强杀线程）。"""
        now = self._now(now)
        self.ds.execute(
            'UPDATE %s SET status=?, finished_at=?, next_retry_at=NULL, '
            "lease_until=NULL, worker_id=NULL, updated_at=datetime('now') "
            "WHERE id=? AND status IN ('pending','claimed','running','retrying')"
            % RUN_TABLE,
            ['cancelled', now, int(run_id)])
        self._commit()
        row = self._one(
            'SELECT status FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)])
        return bool(row and row['status'] == 'cancelled')

    def mark_skipped(self, run_id: int, note=None, now=None) -> bool:
        """`pending` → `skipped`（P1 影子模式记账，不产生可执行堆积）。"""
        now = self._now(now)
        self.ds.execute(
            'UPDATE %s SET status=?, finished_at=?, result=?, '
            "updated_at=datetime('now') "
            "WHERE id=? AND status='pending'" % RUN_TABLE,
            ['skipped', now, note, int(run_id)])
        self._commit()
        row = self._one(
            'SELECT status FROM %s WHERE id=?' % RUN_TABLE, [int(run_id)])
        return bool(row and row['status'] == 'skipped')

    def promote_retries(self, now=None, limit=20) -> list:
        """`retrying` 到期 → `pending`，返回本次放行的 run id（幂等）。"""
        now = self._now(now)
        due = self._rows(
            "SELECT id FROM %s WHERE status='retrying' "
            'AND next_retry_at IS NOT NULL AND next_retry_at <= ? '
            'ORDER BY next_retry_at LIMIT ?' % RUN_TABLE, [now, int(limit)])
        changed = []
        for row in due:
            self.ds.execute(
                "UPDATE %s SET status='pending', attempt=attempt+1, "
                "next_retry_at=NULL, updated_at=datetime('now') "
                "WHERE id=? AND status='retrying'" % RUN_TABLE,
                [int(row['id'])])
            self._commit()
            check = self._one(
                'SELECT status FROM %s WHERE id=?' % RUN_TABLE,
                [int(row['id'])])
            if check and check['status'] == 'pending':
                changed.append(int(row['id']))
        return changed

    # ── 租约回收 ──────────────────────────────────────────────────────────

    def reclaim_expired(self, now=None) -> list:
        """回收过期租约，返回本次真正迁移的 run id 列表（幂等）。"""
        now = self._now(now)
        expired = self._rows(
            'SELECT id, status, attempt, max_attempts, lease_until '
            'FROM %s WHERE status IN (\'claimed\',\'running\') '
            'AND lease_until IS NOT NULL AND lease_until <= ?' % RUN_TABLE,
            [now])
        changed = []
        for row in expired:
            attempt = int(row.get('attempt') or 1)
            max_attempts = int(row.get('max_attempts') or 1)
            if attempt < max_attempts:
                new_status = 'retrying'
                new_attempt = attempt          # 下一个 attempt 号由 promote 时递增
                next_retry = now
            else:
                new_status = 'dead'
                new_attempt = attempt
                next_retry = None
            self.ds.execute(
                'UPDATE %s SET status=?, attempt=?, next_retry_at=?, '
                'error=?, finished_at=?, lease_until=NULL, worker_id=NULL, '
                "updated_at=datetime('now') "
                'WHERE id=? AND status=? AND attempt=? AND lease_until=?'
                % RUN_TABLE,
                [new_status, new_attempt, next_retry, 'lease expired',
                 now if new_status == 'dead' else None,
                 int(row['id']), row['status'], attempt, row['lease_until']])
            self._commit()
            check = self._one(
                'SELECT status FROM %s WHERE id=?' % RUN_TABLE,
                [int(row['id'])])
            if check and check['status'] == new_status:
                changed.append(int(row['id']))
        return changed

    # ── 触发器推进（spec §6.3）────────────────────────────────────────────

    def advance_trigger(self, trigger_id: int, expected_next_run_at: float,
                        next_run_at: float, now=None) -> bool:
        """乐观推进触发器：旧值不匹配说明已被其它 tick 推进，返回 False。"""
        now = self._now(now)
        current = self._one(
            'SELECT next_run_at FROM %s WHERE id=?' % TRIGGER_TABLE,
            [int(trigger_id)])
        if (not current or current['next_run_at'] is None
                or abs(float(current['next_run_at'])
                       - float(expected_next_run_at)) >= 1e-6):
            return False
        self.ds.execute(
            'UPDATE %s SET next_run_at=?, last_run_at=?, '
            "updated_at=datetime('now') "
            'WHERE id=? AND next_run_at=?' % TRIGGER_TABLE,
            [next_run_at, now, int(trigger_id),
             float(expected_next_run_at)])
        self._commit()
        row = self._one(
            'SELECT next_run_at FROM %s WHERE id=?' % TRIGGER_TABLE,
            [int(trigger_id)])
        return bool(row and row['next_run_at'] is not None
                    and abs(float(row['next_run_at']) - next_run_at) < 1e-6)

    def due_triggers(self, now=None, limit=20) -> list:
        now = self._now(now)
        return self._rows(
            'SELECT * FROM %s WHERE enabled=1 '
            "AND trigger_type IN ('cron','interval') "
            'AND next_run_at IS NOT NULL AND next_run_at <= ? '
            'ORDER BY next_run_at LIMIT ?' % TRIGGER_TABLE,
            [now, int(limit)])

    def pending_runs(self, now=None, limit=20) -> list:
        now = self._now(now)
        return [self._decode(row) for row in self._rows(
            'SELECT * FROM %s WHERE status=\'pending\' '
            'AND scheduled_for <= ? ORDER BY scheduled_for LIMIT ?'
            % RUN_TABLE, [now, int(limit)])]