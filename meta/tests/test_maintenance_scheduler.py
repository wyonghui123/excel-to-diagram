# -*- coding: utf-8 -*-
"""运维调度器解耦回归 —— 运维作业不应挂在任务体系上

背景（P1 任务体系替换路径 第7 项）:
  server.py 启动遗留 TaskScheduler，其上注册 9 个 handler。其中**只有platform_tick
  属于任务域**（A5 平台心跳：派工 + 认领超时回收 + SLA 升级扫描）；其余 8 个是
  与任务模型无关的运维作业，只是「借调度器跑 cron」：

    - DB 维护4 个：db_analyze / db_vacuum / db_integrity_check / db_checkpoint
    - 审计运维 3 个：audit_failure_retry / audit_log_cleanup / audit_log_archive
    - 导入队列 1 个：import_queue_processor

  这层耦合是「替换遗留任务体系」的隐性阻塞：删scheduled_tasks 等表会连带拖垮
  DB 维护与审计归档，而它们本不该依赖任务域。

方案:
  新增 meta/core/maintenance_scheduler.py —— 独立的 cron 调度器，配置内置于代码
  （DEFAULT_JOBS），**不读scheduled_tasks / task_queues / task_executions 任何表**。
  与遗留调度器并存迁移，运维作业从此与任务体系解耦；遗留调度器只剩 platform_tick。

本测试锁定:
  1. 内置配置覆盖原DB 中 8 条 cron 作业的 code / handler / schedule（行为等价）；
  2. 不触碰任何 task 域表；
  3. 与遗留调度器的分工：运维归新调度器，platform_tick 留遗留（待 task.v1 接管）；
  4. 执行上下文兼容 —— handler 只依赖 context['data_source'] / ['handler_config']。
"""
import inspect
import re

import pytest

from meta.core.maintenance_scheduler import (
    DEFAULT_JOBS,
    JOB_CODES,
    MaintenanceScheduler,
    OPS_JOB_CODES,
)

#: 原 architecture.db `scheduled_tasks` 表中的 8 条运维作业（code → cron）。
#: 搬迁必须行为等价：改了 cron 就等于改了运维 SLA。
LEGACY_DB_JOBS = {
    'db_analyze': '0 3 * * *',
    'db_vacuum': '0 4 * * 0',
    'db_integrity_check': '0 6 * * *',
    'db_checkpoint': '*/5 * * * *',
    'audit_failure_retry': '*/10 * * * *',
    'audit_log_cleanup': '0 2 * * *',
    'import_queue_processor': '*/2 * * * *',
}

#: 任务域专属作业：不属于运维调度器管辖
TASK_DOMAIN_CODES = {'platform_tick'}


@pytest.mark.unit
class Test运维作业内置配置:
    """运维作业的配置内嵌在代码里，不再依赖 scheduled_tasks 表"""

    def test_覆盖原库全部八条作业(self):
        """[解耦-1] 8 条运维作业必须全部内置，一条不能漏"""
        for code in LEGACY_DB_JOBS:
            assert code in OPS_JOB_CODES, f"运维作业 {code} 未内置到 maintenance_scheduler"

    def test_cron_表达式与原库等价(self):
        """[解耦-2] cron 必须与原 scheduled_tasks 行一致（改 cron = 改运维 SLA）"""
        for code, cron in LEGACY_DB_JOBS.items():
            job = next(j for j in DEFAULT_JOBS if j['code'] == code)
            assert job['schedule'] == cron, (
                f"{code} cron 被改动: {job['schedule']!r} != {cron!r}")

    def test_不收录platform_tick(self):
        """[解耦-3] platform_tick 属任务域，不进运维调度器"""
        assert 'platform_tick' not in OPS_JOB_CODES, (
            "platform_tick 是 A5 平台心跳（任务域），不应由运维调度器管辖")

    def test_每个作业声明_handler_名(self):
        """[解耦-4] 每作业必须有 handler（与原 handler 字段同名，server.py 注册名对齐）"""
        for job in DEFAULT_JOBS:
            assert job.get('handler'), f"{job['code']} 缺 handler"
            assert job['handler'] == job['code'], (
                f"{job['code']} 的 handler 应与 code 同名（原表即如此）")

    def test_作业默认启用且合法(self):
        """[解耦-5] 迁移不能静默停用运维作业"""
        for job in DEFAULT_JOBS:
            assert job.get('enabled', True) is True, f"{job['code']} 被默认停用"


@pytest.mark.unit
class Test不依赖任务域表:
    """新调度器不得读写任何 task 域表"""

    def test_源码不查询任务域表(self):
        """[解耦-6] 不得对任务域表发起 SQL（文档注释提及表名不算）"""
        src = inspect.getsource(inspect.getmodule(MaintenanceScheduler))
        # 剥离注释与文档字符串后再检查，避免把「说明为何解耦」的注释误判为违规
        code = '\n'.join(
            line for line in src.splitlines()
            if not line.strip().startswith('#')
        )
        code = re.sub(r'"""[\s\S]*?"""', '', code)
        for table in ('scheduled_tasks', 'task_queues', 'task_executions',
                      'task_workers', 'task_definitions'):
            assert table not in code, f"maintenance_scheduler 不应查询 {table}"

    def test_不注册平台心跳(self):
        """[解耦-7] 分工边界：运维归本调度器，platform_tick 归遗留（待 task.v1 接管）"""
        assert TASK_DOMAIN_CODES.isdisjoint(OPS_JOB_CODES), (
            "platform_tick 与运维作业集合不应有交集")

    def test_全部作业均为_cron_触发(self):
        """[解耦-8] 运维作业一律cron（无事件驱动/手动），与原表 trigger_mode 一致"""
        for job in DEFAULT_JOBS:
            assert job['trigger_mode'] == 'cron', (
                f"{job['code']} trigger_mode 应为 cron")


@pytest.mark.unit
class Test执行契约兼容:
    """handler 只依赖 context 字典的两个键，调度器须按该形状投递"""

    def test_上下文含_data_source_与_handler_config(self):
        """[解耦-9] 上下文形状须兼容现有 8 个 handler 的 context.get(...) 用法"""
        class _DS:
            def __init__(self):
                self.log = []

            def execute(self, *a, **k):
                self.log.append(a)

            def commit(self):
                pass

            def query(self, *a, **k):
                return []

        ds = _DS()
        sched = MaintenanceScheduler(data_source=ds)
        seen = {}

        class _Probe:
            def execute(self, params, context):
                seen.update(context)
                from meta.core.task_handler import TaskResult
                return TaskResult(success=True)

        sched.register_handler('db_analyze', _Probe())
        sched.run_now('db_analyze')

        assert seen.get('data_source') is ds, "上下文须带 data_source（8 个 handler 都依赖它）"
        assert 'handler_config' in seen, "上下文须带 handler_config（审计类 handler 读配置）"
        assert sched._last_result.get('db_analyze') is not None, "执行结果须被记录"


@pytest.mark.unit
class Test作业集合常量:
    """JOB_CODES 是运维 + 任务域的并集，供自检/文档引用"""

    def test_job_codes_含两类(self):
        assert OPS_JOB_CODES <= JOB_CODES
        assert TASK_DOMAIN_CODES <= JOB_CODES
        assert len(JOB_CODES) == len(OPS_JOB_CODES) + len(TASK_DOMAIN_CODES)