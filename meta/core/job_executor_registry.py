# -*- coding: utf-8 -*-
"""后台作业执行器插件注册表（P2）。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md §7 Executor 插件接口

职责:
  · 只负责「按 handler 名找到执行体，并在受控线程里跑一次」；
  · 不做重试决策（由 `job_definitions.max_attempts` / `backoff_seconds` 决定），
    不写 `task_runs`（账本写入仍是 `job_run_store` 的唯一职责）；
  · 执行体抛出的任何异常、超时、未知 handler 一律转成 `JobResult(success=False)`，
    不向 dispatcher 抛异常。

取消语义（spec §13 Q3）:
  · Python 执行体协作式取消：必须响应 `ctx.cancel_event`（每 1s 至少检查一次）；
  · 超时时注册表只 `set()` 该事件并返回失败，**不强杀线程**（daemon 线程自行结束）。
"""

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: 未指定 timeout 且 `JobContext.deadline_monotonic` 也不可用时的兜底。
DEFAULT_TIMEOUT_SECONDS = 300.0


@dataclass
class JobContext:
    """一次执行尝试的上下文。"""

    run_id: int
    job_code: str
    params: dict
    attempt: int
    deadline_monotonic: float
    cancel_event: threading.Event


@dataclass
class JobResult:
    """执行结果（`data` 会作为 run.result 落库）。"""

    success: bool
    data: dict = None
    error: str = None


class FunctionExecutor:
    """把普通函数适配成 spec §7 的 executor 形状。"""

    def __init__(self, name: str, func, supports_cancel: bool = True):
        self.name = name
        self.func = func
        self.supports_cancel = supports_cancel

    def run(self, ctx: JobContext):
        return self.func(ctx)


class ExecutorRegistry:
    """handler 名 → executor 的注册表。

    注册仅在启动阶段进行，运行期只读，故不加锁。
    """

    def __init__(self):
        self._executors = {}

    # ── 注册 / 查找 ──────────────────────────────────────────────────────

    def register(self, executor_or_name, func=None, *,
                 supports_cancel: bool = True):
        """注册执行体。

        两种用法::

            registry.register(MyExecutor())          # 对象需有 name / run()
            registry.register('db_analyze', func)    # 普通函数
        """
        if isinstance(executor_or_name, str):
            if func is None:
                raise ValueError('register(name, func) 缺少 func')
            executor = FunctionExecutor(executor_or_name, func,
                                        supports_cancel=supports_cancel)
        else:
            executor = executor_or_name
        name = getattr(executor, 'name', None)
        if not name:
            raise ValueError('executor 必须有非空 name')
        self._executors[name] = executor
        return executor

    def unregister(self, name: str) -> bool:
        return self._executors.pop(name, None) is not None

    def get(self, name: str):
        return self._executors.get(name)

    def names(self) -> list:
        return sorted(self._executors)

    # ── 执行 ──────────────────────────────────────────────────────────────

    def execute(self, name: str, ctx: JobContext, timeout=None) -> JobResult:
        """在受控线程里执行一次，返回 `JobResult`（永不抛异常）。"""
        executor = self.get(name)
        if executor is None:
            logger.warning('[job-exec] run=%s 未注册的 handler: %s',
                           ctx.run_id, name)
            return JobResult(False, error='未注册的 handler: %s' % name)

        if ctx.cancel_event.is_set():
            return JobResult(False, error='cancelled')

        timeout = self._resolve_timeout(ctx, timeout)
        box = {}

        def _target():
            try:
                box['result'] = executor.run(ctx)
            except BaseException as exc:  # noqa: BLE001 - 统一转失败，保留类型信息
                box['error'] = '%s: %s' % (type(exc).__name__, exc)
                logger.warning('[job-exec] run=%s handler=%s 抛错: %s',
                               ctx.run_id, name, exc)

        worker = threading.Thread(
            target=_target, name='job-exec-%s' % ctx.run_id,
            daemon=True)
        worker.start()
        worker.join(timeout)

        if worker.is_alive():
            # 协作式取消：只置位，不 join 第二次（不强杀线程）
            ctx.cancel_event.set()
            logger.warning('[job-exec] run=%s handler=%s 超时 %.3fs',
                           ctx.run_id, name, timeout)
            return JobResult(False, error='timeout after %.3fs' % timeout)

        if 'error' in box:
            return JobResult(False, error=box['error'])
        return self._normalize(box.get('result'), name)

    @staticmethod
    def _resolve_timeout(ctx: JobContext, timeout) -> float:
        if timeout is not None:
            return max(0.0, float(timeout))
        remain = ctx.deadline_monotonic - time.monotonic()
        return max(0.0, remain if remain > 0 else DEFAULT_TIMEOUT_SECONDS)

    @staticmethod
    def _normalize(result, name: str) -> JobResult:
        if isinstance(result, JobResult):
            return result
        if result is None:
            return JobResult(True)
        if isinstance(result, dict):
            return JobResult(True, data=result)
        return JobResult(False,
                         error='handler=%s 返回类型非法: %s'
                               % (name, type(result).__name__))