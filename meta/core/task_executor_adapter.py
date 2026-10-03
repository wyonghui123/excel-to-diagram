# -*- coding: utf-8 -*-
"""[A5 2026-10-04] Executor 适配层 —— 按 executor_type 派发的统一入口

职责（§7.1 原则 1 / §7.5 适配矩阵 / §12.1 A5）:
- **executor 是维度不是类型**：所有任务共享一个实体、一个状态机、一套审计；
  本模块是**唯一派发点**，业务域不得各写一套（否则语义漂移）。
- **三个真实暂停点归一**：人工（`awaiting_human`）、异步补全（`awaiting_async`）、
  待审（`needs_review`）→ `PAUSE_OUTCOMES`，调用方一套判定。

各 type 的载体（§7.5）:
  human   → 统一收件箱（A8 `task_inbox`）；本层只产出停等信号，**零写库**
  system  → `BOActionExecutor`（B2 三态；自动继承 B4 写权单通道守卫）
  cron    → 同 system 通道（§9.5：复用 BO 引擎入口，不另建执行通道）
  webhook → HTTP 入口受理 + A7 `complete_async` 回调；本层只产出停等信号
  agent   → **未实现**（§9.3 Agent Adapter 属 E 系列）→ fail-closed，显式报错

分层纪律:
- **不发明状态**：A2 的 11 态无 waiting 态；等待以「既有状态 + 暂停信号」表达，
  本模块不代写状态列（归属由 A8 收件箱 / A7 回调裁决）。
- **不越权**：system / cron 分支的写全部经 BO Action（B4 守卫在 B2 内生效）。
- **不假装完成**：未实现的载体抛 `ExecutorAdapterError`，绝不静默返回成功。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.1 / §7.5 / §9.2 / §9.5 / §12.1 A5
  先例: meta/core/bo_action_executor.py（B2 三态）、meta/core/task_inbox.py（A8）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, FrozenSet, Optional, Tuple

logger = logging.getLogger(__name__)

TASK_TABLE = "tasks"

#: §7.5 枚举（唯一权威；executor.type 的封闭取值域）
EXECUTOR_TYPES: Tuple[str, ...] = ("human", "agent", "cron", "system", "webhook")

#: 声明式适配矩阵：type → 载体说明；None = 未实现（fail-closed）
ADAPTER_CARRIERS: Dict[str, Optional[str]] = {
    "human": "task_inbox（A8 统一收件箱）",
    "system": "BOActionExecutor（B2 三态）",
    "cron": "BOActionExecutor（复用 BO 引擎入口，§9.5）",
    "webhook": "HTTP 受理 + task_async.complete_async（A7）",
    "agent": None,  # §9.3 Agent Adapter（LLM + 工具白名单 + eval）未实现
}

#: 委托 BOActionExecutor 的 type
BO_BACKED_TYPES: FrozenSet[str] = frozenset({"system", "cron"})

#: 停等信号（三个真实暂停点 + 人工）
OUTCOME_AWAITING_HUMAN = "awaiting_human"

#: B2 的 awaiting_async / needs_review 同属停等
PAUSE_OUTCOMES: FrozenSet[str] = frozenset({
    OUTCOME_AWAITING_HUMAN, "awaiting_async", "needs_review",
})


class ExecutorAdapterError(Exception):
    """任务不存在 / executor_type 未知 / 载体未实现（fail-closed）。"""


def is_pause(outcome: str) -> bool:
    """该结果是否为停等（等待人 / 外部回调 / 审核）。"""
    return outcome in PAUSE_OUTCOMES


def _load_executor_type(data_source, task_id: str) -> Tuple[str, str]:
    rows = data_source.execute(
        f"SELECT executor_type, status FROM {TASK_TABLE} WHERE id = ?",
        (str(task_id),),
    ).fetchall()
    if not rows:
        raise ExecutorAdapterError(f"任务不存在：{task_id}")
    return (rows[0][0] or ""), (rows[0][1] or "")


def start_task(
    data_source,
    task_id: str,
    *,
    run_as: str = "system",
    registry=None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """统一派发入口：按 executor_type 选载体并归一返回。

    Returns:
        system / cron → B2 结果 dict（补 `executor_type`）
        human         → {status: 'awaiting_human', task_status, task_id, executor_type, message}
        webhook       → {status: 'awaiting_async', task_status, task_id, executor_type, message}

    Raises:
        ExecutorAdapterError: 任务不存在 / 未知 type / 载体未实现（agent）
    """
    executor_type, task_status = _load_executor_type(data_source, task_id)

    if executor_type in BO_BACKED_TYPES:
        from meta.core.bo_action_executor import BOActionExecutor

        outcome = BOActionExecutor(registry).start(data_source, task_id,
                                                   run_as=run_as, **kwargs)
        outcome["executor_type"] = executor_type
        return outcome

    if executor_type == "human":
        # 人工任务：等待收件箱办理（A8）；本层零写库、不改状态
        return {
            "status": OUTCOME_AWAITING_HUMAN,
            "task_status": task_status,
            "task_id": str(task_id),
            "executor_type": executor_type,
            "message": "人工任务：等待统一收件箱办理（A8）",
        }

    if executor_type == "webhook":
        # webhook 任务：受理后等待外部回调 complete_async（A7）
        return {
            "status": "awaiting_async",
            "task_status": task_status,
            "task_id": str(task_id),
            "executor_type": executor_type,
            "message": "webhook 任务：受理后等待外部回调 complete_async（A7）",
        }

    if executor_type == "agent":
        raise ExecutorAdapterError(
            "agent executor 适配器未实现（§9.3 Agent Adapter 属 E 系列）"
        )

    raise ExecutorAdapterError(
        f"未知 executor_type：{executor_type!r}（§7.5 允许 {EXECUTOR_TYPES}）"
    )


def adapter_matrix() -> Dict[str, Optional[str]]:
    """适配矩阵副本（供运维 / 文档 / 自检读取）。"""
    return dict(ADAPTER_CARRIERS)