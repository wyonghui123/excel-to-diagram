# -*- coding: utf-8 -*-
import logging

from meta.core.task_handler import TaskHandler, TaskResult
from meta.core.task_tick import platform_tick

logger = logging.getLogger(__name__)


class PlatformTickHandler(TaskHandler):
    """[A5 挂载 2026-10-02] 平台心跳：一次调度触发 = 派工 + 超时回收 + SLA 升级扫描。

    编排逻辑在 meta.core.task_tick.platform_tick；本类只做调度设施适配
    （context['data_source'] → platform_tick → TaskResult）。
    """

    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            result = platform_tick(ds)
            success = not result.get('errors')
            if not success:
                logger.warning(
                    "platform_tick finished with %d error(s): %s",
                    len(result['errors']), result['errors'],
                )
            return TaskResult(success=success, data=result)
        except Exception as e:
            logger.error("platform_tick handler failed: %s", e)
            return TaskResult(success=False, error=str(e))