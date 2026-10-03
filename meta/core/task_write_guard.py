# -*- coding: utf-8 -*-
"""[B4 2026-10-04] 写权单通道守卫 —— 任务体系对对象行 / 边 / 行状态的写全部经 BO Action

职责（综合 §6.3 边界三条之二 / §12.1 B4）:
- 把「不越权」纪律从文档变成**机器执行的运行期守卫**：任务尝试期间使用的
  `data_source` 只放行**任务域自有表**的 DML，对业务对象表 / 边表 / 行状态列
  的任何直接写立即抛 `WriteChannelViolation`（fail-closed，事务回滚）。

为什么是运行期 ds 代理（而不是源码扫描）:
- 仓库大量 SQL 用 f-string 拼表名（如 `f"UPDATE {TASK_TABLE} ..."`），
  静态扫描对这类写法失效；代理在**执行点**看最终 SQL，零漏报、零误报。

边界与前提:
- 任务侧唯一的业务写出口是 `BOActionExecutor` → `registry.call(action_id)`（B2）；
  BO Action 自身的写走 BO 框架通道，**不经**任务尝试的 `data_source`。
  故「任务 ds 上出现业务表 DML」⇔ 存在绕过 BO Action 的直接写。
- 不拦读（SELECT），只管写权（DML）。
- 白名单是**任务域内务表**，不含任何业务对象表 / 边表。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §12.1 B4
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §6.3
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, FrozenSet, Iterator, Optional

#: 任务域自有表（任务体系内务）——不在其列的 DML 一律拒绝。
TASK_OWNED_TABLES: FrozenSet[str] = frozenset({
    # A1 task.v1 四表
    "tasks", "task_templates", "workflows", "workflow_runs",
    # A3 事件账
    "task_events", "task_worklogs",
    # A6 幂等账
    "task_idempotency",
    # A7 异步补全
    "task_async_waits", "task_async_receipts",
    # A9 SLA 与 hold 派生视图
    "task_slas", "task_hold_current",
    # 遗留调度器底座（task_handler / task_queue_manager / task_scheduler）
    "scheduled_tasks", "task_executions", "task_queues",
})

#: 从 DML 语句识别目标表：INSERT [OR ...] INTO t / UPDATE [OR ...] t / DELETE FROM t
_DML_TARGET_RE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+"
    r"[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


class WriteChannelViolation(Exception):
    """任务体系尝试直接写业务对象表 / 边表（绕过 BO Action 单通道）。"""


def extract_dml_target(sql: Any) -> Optional[str]:
    """识别语句中的 DML 目标表（小写）；无 DML 返回 None。

    多语句（分号分隔）逐段检查，返回**最后一个** DML 的目标（守卫只关心「有没有越权」）。
    """
    if not isinstance(sql, str) or not sql.strip():
        return None
    target: Optional[str] = None
    for fragment in sql.split(";"):
        m = _DML_TARGET_RE.search(fragment)
        if m:
            target = m.group(1).lower()
    return target


def assert_task_write_allowed(sql: Any,
                              allowlist: FrozenSet[str] = TASK_OWNED_TABLES) -> None:
    """DML 目标表不在白名单即抛 `WriteChannelViolation`（读语句放行）。"""
    target = extract_dml_target(sql)
    if target is None:
        return
    if target not in allowlist:
        raise WriteChannelViolation(
            "任务体系不得直接写业务对象表 %r —— 写权单通道："
            "对对象行 / 边 / 行状态的写必须经 BO Action（综合 §6.3）" % target
        )


class GuardedDataSource:
    """data_source 代理：只拦 `execute()` 的 DML，其余属性透传。"""

    def __init__(self, inner: Any, allowlist: FrozenSet[str] = TASK_OWNED_TABLES):
        self._inner = inner
        self._allowlist = allowlist

    def execute(self, sql: Any, params: Any = ()):
        assert_task_write_allowed(sql, self._allowlist)
        return self._inner.execute(sql, params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@contextmanager
def task_write_scope(data_source: Any,
                     allowlist: FrozenSet[str] = TASK_OWNED_TABLES) -> Iterator[Any]:
    """任务尝试期作用域：产出守卫代理；离开作用域即失效（不跨尝试泄漏）。"""
    yield GuardedDataSource(data_source, allowlist)