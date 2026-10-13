# -*- coding: utf-8 -*-
"""平台调度器回归 —— platform_tick 从遗留调度器迁到进程内调度器

背景（P1 任务体系替换路径 第 1 项，解锁项）:
  遗留 TaskScheduler 原本挂 9 个 handler。第 7 项已把 8 个运维作业迁到
  MaintenanceScheduler；本项把**任务域**的 platform_tick（A5 平台心跳：
  direct 派工 + 认领超时回收 + SLA 升级扫描 + 决策-生效对账）也迁出，改由
  独立的进程内调度器驱动 —— 调度配置内嵌代码（PLATFORM_JOBS），不再依赖
  scheduled_tasks 表。

  迁完后遗留 TaskScheduler 不再承载任何 cron 作业，仅保留队列与手工触发
  基础设施；scheduled_tasks 表退化为历史行（其清理属替换路径第 3 项，
  待新调度器稳定后单独做，本轮不动）。

本测试锁定:
  1. platform_tick 的 cron 与原表行等价（* * * * *，每分钟）；
  2. 迁移期遗留调度器对未注册 handler 静默跳过，不刷 error 噪声；
  3. 执行契约兼容（context 带 data_source，handler 被正确调用）。
"""
import logging

import pytest

from meta.core.platform_scheduler import (
    PLATFORM_JOB_CODES,
    PLATFORM_JOBS,
    PlatformScheduler,
)

#: 第7 项已迁到 MaintenanceScheduler 的运维作业（不得进入平台调度器）
OPS_CODES = ('db_analyze', 'db_vacuum', 'db_integrity_check', 'db_checkpoint',
             'audit_failure_retry', 'audit_log_cleanup', 'audit_log_archive',
             'import_queue_processor')

#: 迁移后遗留调度器不再注册 handler 的作业全集
MIGRATED_CODES = OPS_CODES + ('platform_tick',)


@pytest.mark.unit
class Test平台作业配置:
    def test_覆盖平台心跳作业(self):
        assert 'platform_tick' in PLATFORM_JOB_CODES

    def test_cron_与原表行等价(self):
        """原 scheduled_tasks 的 platform_tick 行是 '* * * * *'（每分钟）"""
        job = next(j for j in PLATFORM_JOBS if j['code'] == 'platform_tick')
        assert job['schedule'] == '* * * * *'
        assert job['trigger_mode'] == 'cron'

    def test_不收录运维作业(self):
        """运维作业归 MaintenanceScheduler，不得混入平台调度器"""
        for code in OPS_CODES:
            assert code not in PLATFORM_JOB_CODES, f"{code} 应归运维调度器"

    def test_handler_名与_code_同名(self):
        """与遗留表 handler 字段同名，server.py 注册名对齐"""
        for job in PLATFORM_JOBS:
            assert job['handler'] == job['code']


@pytest.mark.unit
class Test调度引擎复用:
    def test_是进程内调度器的子类(self):
        """复用既有 in-process cron 引擎，不重复实现 tick/cron 计算"""
        from meta.core.maintenance_scheduler import MaintenanceScheduler
        assert issubclass(PlatformScheduler, MaintenanceScheduler)

    def test_不引用任务域表(self):
        """调度器本身不读写任何任务域表（platform_tick 的内务由 handler 自理）"""
        import inspect
        import re
        src = inspect.getsource(inspect.getmodule(PlatformScheduler))
        code = '\n'.join(ln for ln in src.splitlines()
                         if not ln.strip().startswith('#'))
        code = re.sub(r'"""[\s\S]*?"""', '', code)
        for table in ('scheduled_tasks', 'task_queues', 'task_executions'):
            assert table not in code, f"platform_scheduler 不应引用 {table}"

    def test_run_now_触发并投递上下文(self):
        """执行契约与原调度器一致：context 是 dict 且带 data_source"""
        seen = {}

        class _Probe:
            def execute(self, params, context):
                from meta.core.task_handler import TaskResult
                seen.update(context)
                return TaskResult(success=True)

        sched = PlatformScheduler(data_source=object(), config={'check_interval': 60})
        sched.register_handler('platform_tick', _Probe())

        assert sched.run_now('platform_tick') is True
        assert 'data_source' in seen, "context 须带 data_source"
        assert 'handler_config' in seen, "context 须带 handler_config"
        assert sched._last_result.get('platform_tick') is not None

    def test_未注册handler_时_run_now_返回假(self):
        sched = PlatformScheduler(data_source=object())
        assert sched.run_now('platform_tick') is False


@pytest.mark.unit
class Test遗留调度器静默跳过:
    """迁移期：作业行仍在 scheduled_tasks 表，但 handler 已不在遗留调度器注册"""

    def test_未注册handler_不刷错误日志(self, caplog):
        from meta.core.task_scheduler import TaskScheduler
        sched = TaskScheduler(data_source=None)

        with caplog.at_level(logging.DEBUG):
            # handler 未注册 → 应在建执行记录**之前**返回（不留孤儿记录）
            assert sched._execute_task(1, {'handler': 'platform_tick'}) is None

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not errors, f"迁移期不应刷 error 噪声: {[r.getMessage() for r in errors]}"

    def test_同作业只告警一次(self):
        """每分钟一次的平台心跳不应每轮刷日志"""
        from meta.core.task_scheduler import TaskScheduler
        sched = TaskScheduler(data_source=None)

        for _ in range(5):
            sched._execute_task(1, {'handler': 'platform_tick'})

        assert sched._unregistered_warned == {'platform_tick'}

    def test_静默跳过不影响已注册作业(self):
        """真正的 handler 缺失才告警；已注册作业照常执行路径不变"""
        from meta.core.task_scheduler import TaskScheduler
        sched = TaskScheduler(data_source=None)

        class _H:
            def execute(self, params, context):
                from meta.core.task_handler import TaskResult
                return TaskResult(success=True)

        sched.register_handler('platform_tick', _H())
        assert 'platform_tick' in sched._handlers
        assert sched._unregistered_warned == set()