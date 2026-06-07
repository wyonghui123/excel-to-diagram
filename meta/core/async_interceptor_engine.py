# -*- coding: utf-8 -*-
"""
异步拦截器执行引擎

基于 Spec §9.2.1 事务一致性分析，将拦截器分为四组：
- Group A (PURE_READONLY): 仅读取 context，ThreadPoolExecutor 并行执行
- Group B (READ_MODIFY_WRITE): 读取后修改 context.result/filters，串行执行
- Group C (WRITE): 数据库写入操作，事务内串行执行
- Group D (ASYNC): 事务提交后异步执行（审计日志、安全日志、通知、索引更新）

环境变量:
    BO_INTERCEPTOR_MODE=sync|async  默认 sync（向后兼容）
    BO_INTERCEPTOR_TIMEOUT=5        只读拦截器超时（秒）
    BO_INTERCEPTOR_MAX_WORKERS=4    线程池大小
"""

import os
import logging
import concurrent.futures
from typing import List, Optional

logger = logging.getLogger(__name__)

BO_INTERCEPTOR_MODE = os.environ.get('BO_INTERCEPTOR_MODE', 'sync')
BO_INTERCEPTOR_TIMEOUT = float(os.environ.get('BO_INTERCEPTOR_TIMEOUT', '5.0'))
BO_INTERCEPTOR_MAX_WORKERS = int(os.environ.get('BO_INTERCEPTOR_MAX_WORKERS', '4'))
BO_INTERCEPTOR_ASYNC_ENABLED = BO_INTERCEPTOR_MODE == 'async'


PURE_READONLY_INTERCEPTOR_NAMES = {
    'context',
    'versioncontext',
    'computation',
    'format',
    'enrichment',
}

READ_MODIFY_WRITE_INTERCEPTOR_NAMES = {
    'datapermission',
    'validation',
    'derivation',
    'transform',
}

WRITE_INTERCEPTOR_NAMES = {
    'lock',
    'persistence',
    'cascade',
}

ASYNC_INTERCEPTOR_NAMES = {
    'audit',
    'securitylog',
    'notification',
    'index',
}


def _interceptor_type_name(interceptor) -> str:
    return interceptor.__class__.__name__.lower().replace('interceptor', '')


class AsyncInterceptorEngine:

    def __init__(self, interceptors: List, async_audit_writer=None):
        self._all = interceptors
        self._async_audit_writer = async_audit_writer

        self._pure_readonly: List = []
        self._read_modify_write: List = []
        self._write: List = []
        self._async_group: List = []

        for interceptor in interceptors:
            type_name = _interceptor_type_name(interceptor)
            if type_name in PURE_READONLY_INTERCEPTOR_NAMES:
                self._pure_readonly.append(interceptor)
            elif type_name in ASYNC_INTERCEPTOR_NAMES:
                self._async_group.append(interceptor)
            elif type_name in READ_MODIFY_WRITE_INTERCEPTOR_NAMES:
                self._read_modify_write.append(interceptor)
            elif type_name in WRITE_INTERCEPTOR_NAMES:
                self._write.append(interceptor)
            else:
                self._read_modify_write.append(interceptor)
                logger.debug(
                    "Interceptor '%s' not classified, defaulting to READ_MODIFY_WRITE group",
                    type_name
                )

        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=BO_INTERCEPTOR_MAX_WORKERS
        )

        logger.info(
            "AsyncInterceptorEngine initialized: pure_readonly=%d, read_modify_write=%d, "
            "write=%d, async_group=%d (mode=%s, timeout=%s, workers=%d)",
            len(self._pure_readonly), len(self._read_modify_write),
            len(self._write), len(self._async_group),
            BO_INTERCEPTOR_MODE, BO_INTERCEPTOR_TIMEOUT, BO_INTERCEPTOR_MAX_WORKERS
        )

    def execute_before(self, context) -> None:
        self._run_readonly_before(context)
        self._run_read_modify_write_before(context)
        self._run_write_before(context)

    def execute_after(self, context) -> None:
        self._run_write_after(context)
        self._run_read_modify_write_after(context)
        self._run_readonly_after(context)
        self._run_async_after(context)

    def execute_error(self, context, error: Exception) -> None:
        for interceptor in reversed(self._all):
            try:
                if hasattr(interceptor, 'on_error'):
                    interceptor.on_error(context, error)
            except Exception as e:
                logger.error("Error in %s.on_error: %s", interceptor.name, str(e))

    def _run_readonly_before(self, context) -> None:
        if not self._pure_readonly:
            return
        futures = []
        for interceptor in self._pure_readonly:
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if hasattr(interceptor, 'before_action'):
                futures.append(
                    self._executor.submit(interceptor.before_action, context)
                )
        for f in futures:
            try:
                f.result(timeout=BO_INTERCEPTOR_TIMEOUT)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Readonly interceptor before_action timed out after %ss, proceeding",
                    BO_INTERCEPTOR_TIMEOUT
                )

    def _run_readonly_after(self, context) -> None:
        if not self._pure_readonly:
            return
        futures = []
        for interceptor in reversed(self._pure_readonly):
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if hasattr(interceptor, 'after_action'):
                futures.append(
                    self._executor.submit(interceptor.after_action, context)
                )
        for f in futures:
            try:
                f.result(timeout=BO_INTERCEPTOR_TIMEOUT)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Readonly interceptor after_action timed out after %ss, proceeding",
                    BO_INTERCEPTOR_TIMEOUT
                )

    def _run_read_modify_write_before(self, context) -> None:
        for interceptor in self._read_modify_write:
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if hasattr(interceptor, 'before_action'):
                interceptor.before_action(context)

    def _run_read_modify_write_after(self, context) -> None:
        for interceptor in reversed(self._read_modify_write):
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if hasattr(interceptor, 'after_action'):
                interceptor.after_action(context)

    def _run_write_before(self, context) -> None:
        for interceptor in self._write:
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if hasattr(interceptor, 'before_action'):
                interceptor.before_action(context)

    def _run_write_after(self, context) -> None:
        for interceptor in reversed(self._write):
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if hasattr(interceptor, 'after_action'):
                interceptor.after_action(context)

    def _run_async_after(self, context) -> None:
        if not self._async_group or not self._async_audit_writer:
            for interceptor in reversed(self._async_group):
                if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                    continue
                if hasattr(interceptor, 'after_action'):
                    interceptor.after_action(context)
            return

        for interceptor in reversed(self._async_group):
            if hasattr(interceptor, 'should_execute') and not interceptor.should_execute(context):
                continue
            if not hasattr(interceptor, 'after_action'):
                continue

            def make_audit_fn(ic=interceptor, ctx=context):
                def audit_fn(trace_id=None, transaction_id=None):
                    ic.after_action(ctx)
                return audit_fn

            trace_id = getattr(context, 'trace_id', None)
            success = self._async_audit_writer.submit(
                make_audit_fn(), trace_id=trace_id
            )
            if not success:
                logger.warning(
                    "Async audit write rejected, executing sync for %s",
                    _interceptor_type_name(interceptor)
                )
                interceptor.after_action(context)

    def shutdown(self):
        self._executor.shutdown(wait=True, cancel_futures=False)
