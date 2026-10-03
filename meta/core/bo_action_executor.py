# -*- coding: utf-8 -*-
"""[B2 2026-10-02] BOActionExecutor — 三态（同步 / 异步补全 / needs_review）

职责（§12.1 B2 / §9.2）:
- **任务出口唯一**：executor.type ∈ (system, cron) 的底层实现，把任务实例落到
  BO Action 上执行；四表底座（A1）+ 状态机（A2）+ 事件账（A3）+ 幂等账（A6）+
  异步补全（A7）在本模块串成一条可执行链。
- **三态归位**（§9.2）：
    1) 同步        BO Action 立即完成 → `in_progress → done`（守卫 `acceptance_passed`），
                   outputs 回写 + 触发 A3 事件/工作日志
    2) 异步补全    BO Action 声明无法在 timeout 内完成 → 开 A7 等待单，Task **保持
                   `in_progress`**；外部完成后经 `complete_async(token, outputs)` 归位
    3) needs_review BO Action 返回 `needs_review` → `in_progress → waiting_approval`
                   （守卫 `reviewer_configured`），人工复核回到任务侧
- **run-as 治理**（§9.2 规范 4）：`run_as` 注入调用上下文，供 BO Action / 审计追溯。
- **幂等**（§9.2 规范 1）：整尝试用 A6 键 `{run}:{task}:{attempt}` 包裹
  （复用 `build_idem_key` 唯一口径），重放不重复执行、直接返回首次结果。

分层纪律:
- **不发明状态**：状态迁移一律走 A2 `require_transition`（守卫 fail-closed），
  迁移落账一律走 A3 `record_transition`（一事件 + 一工作日志）。
- **不越界**：审核子任务生成（human + type=approval）属编排定义/实例层（A4/C 域），
  本模块只做状态归位与 payload 暂存，不建子任务。
- **写权单通道**（B4）：任务尝试期所有写经 `task_write_scope` 守卫，业务对象表
  DML 一律 fail-closed；业务写只能走 `registry.call(action_id)`。
- 落**平台库**（Q1 拍板），与 A1/A3/A6/A7 同库同事务（F5 不跨库）。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.2 / §9.1 / §9.2 / §12.1 B2
  先例: meta/core/task_idempotency.run_idempotent（幂等包裹）、meta/core/task_async（补全）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# §9.2：「executor.type in (system, cron) 的底层实现」
BO_ACTION_EXECUTOR_TYPES = ("system", "cron")

TASK_TABLE = "tasks"

# 三态 + 失败（失败是 §7.2 的正常出边，不是第四态）
OUTCOME_COMPLETED = "completed"
OUTCOME_ASYNC = "awaiting_async"
OUTCOME_NEEDS_REVIEW = "needs_review"
OUTCOME_FAILED = "failed"


class BOActionExecutionError(Exception):
    """BO Action 执行前置条件不满足（任务不存在 / executor 类型不符 / 状态不可执行）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 任务行读写（只读必要列；JSON 列解析为对象）
# ─────────────────────────────────────────────────────────────────────────────

_TASK_COLUMNS = (
    "id", "status", "executor_type", "executor_config", "inputs", "attempt",
    "workflow_run_id", "trace_id", "agent_session_id", "doc_ref", "line_refs",
    "timeout_seconds",
)


def _load_task(data_source, task_id: str) -> Dict[str, Any]:
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} WHERE id = ?",
        (str(task_id),),
    ).fetchall()
    if not rows:
        raise BOActionExecutionError(f"任务不存在：{task_id}")
    r = rows[0]
    return {
        "id": r[0], "status": r[1], "executor_type": r[2],
        "executor_config": _load_json(r[3], {}),
        "inputs": _load_json(r[4], {}),
        "attempt": r[5] or 1, "workflow_run_id": r[6] or "",
        "trace_id": r[7] or "", "agent_session_id": r[8] or "",
        "doc_ref": r[9] or "", "line_refs": _load_json(r[10], None),
        "timeout_seconds": r[11],
    }


def _load_json(text: Any, fallback: Any) -> Any:
    if text is None or text == "":
        return fallback
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return fallback


def _json_text(value: Any, fallback: str = "null") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _update_task(data_source, task_id: str, **columns: Any) -> None:
    """更新任务列（值 None 的键跳过；JSON 值由调用方预转文本）。不自提交。"""
    sets, params = [], []
    for key, value in columns.items():
        if value is None:
            continue
        sets.append(f"{key} = ?")
        params.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    params.extend([_now_iso(), str(task_id)])
    data_source.execute(
        f"UPDATE {TASK_TABLE} SET {', '.join(sets)} WHERE id = ?", tuple(params)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 结果归一化：BO Action 返回值 → 三态之一
# ─────────────────────────────────────────────────────────────────────────────

def classify_result(result: Any) -> str:
    """把 BO Action 返回值归一化为三态（+失败）。

    识别口径（对齐 §9.2 `result.status == 'needs_review'` 与 B1 响应信封）:
      - `status == 'needs_review'`            → needs_review
      - `status == 'async'` / `async=True`
        / 携带 `async_token`                  → awaiting_async
      - `success is False`                    → failed
      - 其余（含 ActionResult / dict）         → completed
    """
    if isinstance(result, dict):
        status = result.get("status")
        if status == "needs_review":
            return OUTCOME_NEEDS_REVIEW
        if status == "async" or result.get("async") is True or result.get("async_token"):
            return OUTCOME_ASYNC
        if result.get("success") is False:
            return OUTCOME_FAILED
    return OUTCOME_COMPLETED


def _extract_outputs(result: Any) -> Any:
    if isinstance(result, dict):
        if "data" in result:
            return result.get("data")
        if "outputs" in result:
            return result.get("outputs")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 执行器
# ─────────────────────────────────────────────────────────────────────────────

class BOActionExecutor:
    """BO Action 任务执行器（三态）。

    用法:
        executor = BOActionExecutor()
        outcome = executor.start(data_source, task_id, run_as='system')
    """

    def __init__(self, registry=None):
        self._registry = registry

    @property
    def registry(self):
        if self._registry is None:
            from meta.core.bo_action_registry import bo_action_registry
            self._registry = bo_action_registry
        return self._registry

    # ------------------------------------------------------------------ start

    def start(
        self,
        data_source,
        task_id: str,
        *,
        run_as: str = "system",
        acceptance_passed: Optional[bool] = None,
        reviewer_configured: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """执行一次任务尝试（幂等；重放返回首次结果）。

        Returns:
            {status, task_status, task_id, idem_key, action_id, replayed,
             outputs?, async_token?, message?}

        Raises:
            BOActionExecutionError: 任务不存在 / executor_type 不符 / 状态不可执行
        """
        from meta.core.task_idempotency import build_idem_key, run_idempotent

        task = _load_task(data_source, task_id)
        if task["executor_type"] not in BO_ACTION_EXECUTOR_TYPES:
            raise BOActionExecutionError(
                f"executor_type 必须是 {BO_ACTION_EXECUTOR_TYPES} 之一，"
                f"收到 {task['executor_type']!r}（§9.2）"
            )

        config = task["executor_config"] or {}
        action_id = config.get("action_id")
        if not action_id:
            raise BOActionExecutionError("executor_config 缺少 action_id")

        idem_key = build_idem_key(task["workflow_run_id"], task["id"], task["attempt"])

        def _attempt(ds):
            # [B4 2026-10-04] 写权单通道守卫：任务尝试期的 ds 只放行任务域自有表 DML
            from meta.core.task_write_guard import task_write_scope

            with task_write_scope(ds) as guarded:
                return self._run_attempt(
                    guarded, task_id=task["id"], action_id=action_id,
                    run_as=run_as, acceptance_passed=acceptance_passed,
                    reviewer_configured=reviewer_configured,
                )

        wrapped = run_idempotent(
            data_source, idem_key, _attempt,
            scope="task_attempt", task_id=task["id"],
            workflow_run_id=task["workflow_run_id"], attempt=task["attempt"],
        )

        result = wrapped["result"] or {}
        result["replayed"] = wrapped["status"] == "duplicate"
        result["idem_key"] = idem_key
        result["action_id"] = action_id
        result["task_id"] = task["id"]
        return result

    # ------------------------------------------------------------ 单次尝试主体

    def _run_attempt(
        self,
        data_source,
        *,
        task_id: str,
        action_id: str,
        run_as: str,
        acceptance_passed: Optional[bool],
        reviewer_configured: Optional[bool],
    ) -> Dict[str, Any]:
        from meta.core.task_event_schema import record_transition
        from meta.core.task_state_machine import require_transition

        task = _load_task(data_source, task_id)

        # 1) claimed → in_progress（executor 接手；无守卫）
        if task["status"] == "claimed":
            require_transition("claimed", "in_progress")
            _update_task(data_source, task_id, status="in_progress",
                         started_at=_now_iso())
            record_transition(
                data_source, task_id=task_id,
                from_status="claimed", to_status="in_progress",
                actor=run_as, actor_kind="system", reason="executor 接手",
                workflow_run_id=task["workflow_run_id"],
                trace_id=task["trace_id"],
                agent_session_id=task["agent_session_id"],
                doc_ref=task["doc_ref"], line_refs=task["line_refs"],
            )
            task["status"] = "in_progress"
        elif task["status"] != "in_progress":
            raise BOActionExecutionError(
                f"任务状态不可执行：{task['status']}（仅 claimed / in_progress）"
            )

        # 2) 调用 BO Action（B1 契约：前置条件在 call() 内统一拦截）
        context = {
            "run_as": run_as, "actor": run_as, "actor_kind": "system",
            "task_id": task_id, "workflow_run_id": task["workflow_run_id"],
            "trace_id": task["trace_id"], "agent_session_id": task["agent_session_id"],
            "timeout_seconds": task["timeout_seconds"],
        }
        try:
            result = self.registry.call(action_id, task["inputs"] or {}, context)
        except Exception as e:  # noqa: BLE001 - 业务异常归位为 failed（记录后可重试）
            logger.exception("[BOActionExecutor] action 抛异常: %s", action_id)
            result = {"success": False, "message": str(e), "data": None}

        outcome = classify_result(result)

        # 3) 三态归位
        if outcome == OUTCOME_COMPLETED:
            return self._complete(
                data_source, task, result, run_as,
                acceptance_passed=True if acceptance_passed is None else acceptance_passed,
            )
        if outcome == OUTCOME_NEEDS_REVIEW:
            return self._await_review(
                data_source, task, result, run_as,
                reviewer_configured=reviewer_configured,
            )
        if outcome == OUTCOME_ASYNC:
            return self._start_async(data_source, task, result, run_as)
        return self._fail(data_source, task, result, run_as)

    # ---------------------------------------------------------------- 三态归位

    def _complete(self, data_source, task, result, run_as, *, acceptance_passed) -> Dict:
        from meta.core.task_event_schema import record_transition
        from meta.core.task_state_machine import TransitionContext, require_transition

        require_transition(
            "in_progress", "done",
            TransitionContext(acceptance_passed=acceptance_passed),
        )
        outputs = _extract_outputs(result)
        _update_task(data_source, task["id"], status="done",
                     outputs=_json_text(outputs), finished_at=_now_iso())
        record_transition(
            data_source, task_id=task["id"],
            from_status="in_progress", to_status="done",
            actor=run_as, actor_kind="system", reason="BO Action 完成",
            summary=f"BO Action {task['executor_config'].get('action_id')} 完成",
            outputs_hash=str(hash(_json_text(outputs))),
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
        )
        return {
            "status": OUTCOME_COMPLETED, "task_status": "done",
            "outputs": outputs,
            "message": (result or {}).get("message", "completed") if isinstance(result, dict) else "completed",
        }

    def _await_review(self, data_source, task, result, run_as, *,
                      reviewer_configured: Optional[bool]) -> Dict:
        from meta.core.task_event_schema import record_transition
        from meta.core.task_state_machine import TransitionContext, require_transition

        payload = result.get("payload", result.get("data")) if isinstance(result, dict) else None
        # 未配置审核人 → 守卫 `reviewer_configured` 不放行；归位为 failed（可观测，不静默）
        if reviewer_configured is False:
            return self._fail(
                data_source, task,
                {"success": False, "message": "needs_review 但未配置审核人（reviewer_configured=False）"},
                run_as,
            )

        require_transition(
            "in_progress", "waiting_approval",
            TransitionContext(reviewer_configured=True),
        )
        # payload 暂存 outputs（待审核产出）；审核子任务生成属编排域，本模块不建
        _update_task(data_source, task["id"], status="waiting_approval",
                     outputs=_json_text(payload))
        record_transition(
            data_source, task_id=task["id"],
            from_status="in_progress", to_status="waiting_approval",
            actor=run_as, actor_kind="system", reason="BO Action 请求人工复核",
            summary="needs_review → 人工复核",
            payload=payload,
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
        )
        return {
            "status": OUTCOME_NEEDS_REVIEW, "task_status": "waiting_approval",
            "outputs": payload, "message": "needs_review",
        }

    def _start_async(self, data_source, task, result, run_as) -> Dict:
        from meta.core.task_async import open_async_wait

        config = task["executor_config"] or {}
        wait = open_async_wait(
            data_source,
            task_id=task["id"],
            workflow_run_id=task["workflow_run_id"],
            attempt=task["attempt"],
            envelope_key=config.get("envelope_key", ""),
            expected_line_refs=config.get("expected_line_refs"),
            ttl_seconds=config.get("async_ttl_seconds"),
        )
        # Task 保持 in_progress（§9.2 规范 2：11 态中无 waiting 态），仅记录开单时间
        _update_task(data_source, task["id"], started_at=_now_iso())
        return {
            "status": OUTCOME_ASYNC, "task_status": "in_progress",
            "async_token": wait["async_token"],
            "message": "BO Action 异步受理，等待回调 complete_async",
        }

    def _fail(self, data_source, task, result, run_as) -> Dict:
        from meta.core.task_event_schema import record_transition
        from meta.core.task_state_machine import require_transition

        require_transition("in_progress", "failed")
        message = (result or {}).get("message") if isinstance(result, dict) else None
        fail_reason = message or "BO Action 执行失败"
        _update_task(data_source, task["id"], status="failed",
                     fail_reason=fail_reason, finished_at=_now_iso())
        record_transition(
            data_source, task_id=task["id"],
            from_status="in_progress", to_status="failed",
            actor=run_as, actor_kind="system", reason=fail_reason,
            payload=(result or {}).get("data") if isinstance(result, dict) else None,
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
        )
        return {
            "status": OUTCOME_FAILED, "task_status": "failed",
            "message": fail_reason,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 便捷入口
# ─────────────────────────────────────────────────────────────────────────────

def start_bo_action_task(data_source, task_id: str, **kwargs) -> Dict[str, Any]:
    """模块级便捷入口（等价 `BOActionExecutor().start(...)`）。"""
    return BOActionExecutor().start(data_source, task_id, **kwargs)