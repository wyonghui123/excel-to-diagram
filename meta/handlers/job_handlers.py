# -*- coding: utf-8 -*-
"""默认作业执行器注册（spec §10.1 第 1-2 项）。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md
    §7.1 Executor 接口 / §7.2 白名单 / §7.3 bo_action 桥接 / §7.5 优先级

两类执行体:
  · 运维作业（优先级 1-2）：复用既有 TaskHandler（`meta/handlers/*`），
    失败不影响业务事务；首批只注册 5 个，其余定义保持"未注册即拒跑"；
  · 应用类作业（优先级 3）：单一 `bo_action` 桥接，直接调
    `BoActionRegistry.call`（进程内，不走 HTTP），权限固定 system `['*']`。
"""

import logging

from meta.core.job_executor_registry import ExecutorRegistry, JobResult

logger = logging.getLogger(__name__)

#: `job_definitions.handler` → TaskHandler 类（优先级 1-2）。
DEFAULT_OPS_HANDLERS = (
    ('db_analyze', 'meta.handlers.system_handlers:DBAnalyzeHandler'),
    ('db_vacuum', 'meta.handlers.system_handlers:DBVacuumHandler'),
    ('db_integrity_check', 'meta.handlers.system_handlers:DBIntegrityCheckHandler'),
    ('db_checkpoint', 'meta.handlers.system_handlers:DBCheckpointHandler'),
    ('audit_failure_retry', 'meta.handlers.audit_handlers:AuditFailureRetryHandler'),
)


def build_default_job_registry(data_source, registry=None) -> ExecutorRegistry:
    """构造生产用注册表：运维 handler + `bo_action` 桥接。

    `data_source` 由 server.py 传入，执行时注入 handler 的 context。
    """
    registry = registry or ExecutorRegistry()
    for code, target in DEFAULT_OPS_HANDLERS:
        module_name, class_name = target.split(':', 1)
        module = __import__(module_name, fromlist=[class_name])
        handler = getattr(module, class_name)()
        registry.register(code, _make_ops_executor(code, handler, data_source),
                          supports_cancel=False)
    registry.register('bo_action', make_bo_action_executor(),
                      supports_cancel=False)
    logger.info('[job-handlers] registered: %s', ', '.join(registry.names()))
    return registry


def make_bo_action_executor(action_registry=None):
    """`handler='bo_action'` 的执行体：params `{action_id, payload, permissions}`。"""

    def _run(ctx) -> JobResult:
        params = ctx.params or {}
        action_id = params.get('action_id')
        payload = params.get('payload') or {}
        permissions = params.get('permissions') or ['*']

        if not isinstance(action_id, str) or not action_id:
            return JobResult(False, error='缺少 action_id')
        if not isinstance(payload, dict):
            return JobResult(False, error='payload 必须是 object')
        if ctx.cancel_event.is_set():
            return JobResult(False, error='cancelled')

        registry = action_registry
        if registry is None:
            from meta.core.bo_action_registry import bo_action_registry
            registry = bo_action_registry
        if not registry.has(action_id):
            return JobResult(False, error='未知 action_id: %s' % action_id)

        result = registry.call(action_id, payload, {
            'permissions': list(permissions),
            'source': 'job_dispatcher',
            'run_id': ctx.run_id,
            'job_code': ctx.job_code,
        })
        if not isinstance(result, dict):
            return JobResult(False, error='action 返回非 dict: %r' % (result,))
        if not result.get('success'):
            return JobResult(False,
                             error=result.get('message') or 'action 执行失败')
        return JobResult(True, data={'action_id': action_id,
                                     'data': result.get('data')})

    return _run


def _make_ops_executor(code, handler, data_source):
    def _run(ctx) -> JobResult:
        if ctx.cancel_event.is_set():
            return JobResult(False, error='cancelled')
        result = handler.execute(ctx.params or {}, {
            'data_source': data_source,
            'handler_config': ctx.params or {},
            'run_id': ctx.run_id,
            'job_code': ctx.job_code,
        })
        if getattr(result, 'success', False):
            data = getattr(result, 'data', None)
            if not isinstance(data, dict):
                data = {} if data is None else {'result': data}
            return JobResult(True, data=data)
        return JobResult(False, error=getattr(result, 'error', None)
                         or '%s 执行失败' % code)

    return _run