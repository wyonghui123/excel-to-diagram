# -*- coding: utf-8 -*-
"""[B3 2026-10-02] 决策-生效分离协议 — §9.7 七条规范的引擎固化

职责（§12.1 B3 / §9.7）:
- **先生效后完成**：审批任务的 done 不是决策的终点而是触发器。先调 BO 生效方法
  （`doc.approve()/reject()`）取得**生效回执**（含 `new_status`），任务才归位；
  BO 失败 / 无回执 → **不迁移**、抛 `EffectNotAppliedError`（可重试），
  绝不出现「任务已完成但单据未生效」的静默漂移（R3 唯一护栏）。
- **幂等生效**：BO 侧幂等键 = `{task_id}:{attempt}`（`build_effect_key`），
  作为 `effect_key` 注入 BO 调用上下文，供 BO 侧去重（no-op success）；B3 自身
  再用 A6 `run_idempotent` 按同键包裹整次决策，重放直接返回首次结果。
- **守卫双向独立**：任务侧守卫（A2 `waiting_approval → done/failed/in_progress`）
  与 BO 侧业务守卫各自独立校验、互不信任。任务侧守卫在**调用 BO 之前**预校验
  （`evaluate_transition`），避免「已生效但任务迁移被拒」的反向漂移。
- **拒绝同样要生效**：`reject` 与 `approve` 走同一协议、同一幂等键口径；
  `decision_actions` 必须**同时**配置两个动作，缺一个即报错（机器强制，非文档）。
- **对账兜底**：`reconcile_effects()` 多向扫描（活跃审批任务缺 `decision_actions` 配置 /
  done 无回执 / 回执与单据现状不一致 / 等待中单据无活跃审批任务），产出告警清单。只读，不建告警存储。

分层纪律:
- 落**平台库**（Q1 拍板），与 A1/A3/A6 同库同事务。
- **不发明状态**：迁移一律走 A2 `require_transition`；落账一律走 A3 `record_transition`
  （一事件 + 一工作日志，审核意见进 `detail`）。
- **不越界**：告警入统一收件箱（A8）、`bo.status_changed` 反向事件（D3）不在本模块；
  单据现状由调用方以 `current_statuses` 注入，保持跨库解耦。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.6 / §9.7 / §12.1 B3
  先例: meta/core/bo_action_executor.py（三态）、meta/core/task_idempotency.py（幂等包裹）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# §9.7：「approve / reject 走同一协议」（规范 7）
DECISIONS = ("approve", "reject")

# §9.7 规范 2：BO 侧幂等键口径 = {task_id}:{attempt}
EFFECT_KEY_SEP = ":"

# 生效回执必含字段（§9.7 规范 1：无回执即未生效）
DEFAULT_RECEIPT_KEY = "new_status"

# 本协议适用的业务分类（§7.3；type=approval 受四眼约束，§10.2）
EFFECT_TASK_TYPES = ("approval", "review")

TASK_TABLE = "tasks"
_IDEM_SCOPE = "task_attempt"          # A6 SCOPES 允许值
_INACTIVE_STATES = ("done", "failed", "cancelled", "skipped", "dead")


class DecisionEffectError(Exception):
    """决策前置不满足（任务不存在 / 类型不符 / 守卫未过 / 动作未配置）——**未调用 BO，无副作用**。"""


class EffectNotAppliedError(Exception):
    """BO 未返回生效回执（失败 / 异常 / 缺 `new_status`）——**未迁移，可重试**。"""


# ─────────────────────────────────────────────────────────────────────────────
# 口径与归一化
# ─────────────────────────────────────────────────────────────────────────────

def build_effect_key(task_id: str, attempt: int = 1) -> str:
    """§9.7 规范 2：BO 侧幂等键 = `{task_id}:{attempt}`。"""
    return f"{task_id}{EFFECT_KEY_SEP}{int(attempt or 1)}"


def normalize_decision(decision: str) -> str:
    """校验决策值（approve / reject 同权，不特判）。"""
    value = (decision or "").strip().lower()
    if value not in DECISIONS:
        raise DecisionEffectError(
            f"未知决策: {decision!r}（合法值见 DECISIONS={DECISIONS}）"
        )
    return value


def resolve_decision_action(executor_config: Any, decision: str) -> str:
    """决策 → BO Action 映射（§9.7 规范 7 机器化：两个决策都必须配置）。

    `executor_config['decision_actions'] = {"approve": <action_id>, "reject": <action_id>}`
    缺任一键即报错——「拒绝同样要生效」不靠自觉。
    """
    config = executor_config or {}
    if not isinstance(config, dict):
        raise DecisionEffectError("executor_config 必须是对象")
    mapping = config.get("decision_actions") or {}
    action_id = mapping.get(decision)
    if not action_id:
        raise DecisionEffectError(
            f"executor_config.decision_actions 缺少 {decision!r} 动作"
            f"（approve / reject 必须成对配置，§9.7 规范 7）"
        )
    return action_id


def extract_effect_receipt(result: Any, receipt_key: str = DEFAULT_RECEIPT_KEY) -> Optional[Dict[str, Any]]:
    """从 BO 返回值提取生效回执；缺关键字段视为**未生效**（返回 None）。

    回执 = BO 生效方法的业务事实落点（§9.6：单据侧持有「业务是否生效」）。
    """
    if not isinstance(result, dict) or result.get("success") is False:
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    if receipt_key not in data or data.get(receipt_key) in (None, ""):
        return None
    return dict(data)


def _decision_target(decision: str, allow_rework: bool) -> str:
    """决策 → 任务归位目标态（§7.2 迁移表：通过 → done；拒绝 → failed / 返修 in_progress）。"""
    if decision == "approve":
        return "done"
    return "in_progress" if allow_rework else "failed"


def _json_text(value: Any, fallback: str = "null") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(text: Any, fallback: Any) -> Any:
    if text is None or text == "":
        return fallback
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return fallback


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


_TASK_COLUMNS = (
    "id", "type", "status", "inputs", "outputs", "attempt", "executor_config",
    "workflow_run_id", "trace_id", "agent_session_id", "doc_ref", "line_refs",
    "created_by",
)


def _load_task(data_source, task_id: str) -> Dict[str, Any]:
    rows = data_source.execute(
        f"SELECT {', '.join(_TASK_COLUMNS)} FROM {TASK_TABLE} WHERE id = ?",
        (str(task_id),),
    ).fetchall()
    if not rows:
        raise DecisionEffectError(f"任务不存在：{task_id}")
    r = rows[0]
    return {
        "id": r[0], "type": r[1], "status": r[2],
        "inputs": _load_json(r[3], {}), "outputs": _load_json(r[4], {}),
        "attempt": r[5] or 1, "executor_config": _load_json(r[6], {}),
        "workflow_run_id": r[7] or "", "trace_id": r[8] or "",
        "agent_session_id": r[9] or "", "doc_ref": r[10] or "",
        "line_refs": _load_json(r[11], None), "created_by": r[12] or "",
    }


def _update_task(data_source, task_id: str, **columns: Any) -> None:
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
# 协议执行器
# ─────────────────────────────────────────────────────────────────────────────

class DecisionEffectProtocol:
    """决策-生效协议（§9.7）。

    用法:
        protocol = DecisionEffectProtocol()
        outcome = protocol.decide(
            data_source, task_id, decision='approve', comment='同意',
            actor='u-1001', reviewer_permission=True,
        )
    """

    def __init__(self, registry=None):
        self._registry = registry

    @property
    def registry(self):
        if self._registry is None:
            from meta.core.bo_action_registry import bo_action_registry
            self._registry = bo_action_registry
        return self._registry

    # ---------------------------------------------------------------- decide

    def decide(
        self,
        data_source,
        task_id: str,
        *,
        decision: str,
        comment: str = "",
        actor: str = "",
        actor_kind: str = "human",
        reviewer_permission: Optional[bool] = None,
        four_eyes: Optional[bool] = None,
        submitter_id: str = "",
        run_as: Optional[str] = None,
        allow_rework: bool = False,
    ) -> Dict[str, Any]:
        """提交一次审批决策 → 生效 → 归位（整次决策按 effect_key 幂等）。

        Args:
            reviewer_permission: 审核权限事实（A2 `review_permission` 守卫输入；None = fail-closed）
            four_eyes:  是否强制四眼（默认 type=approval 强制）
            submitter_id: 提交人（四眼比对基准；默认取任务 `created_by`）
            allow_rework: reject 时归位 `in_progress`（驳回返修）而非 `failed`

        Returns:
            {status, task_status, decision, effect_key, action_id, receipt?, replayed}

        Raises:
            DecisionEffectError:  入口/守卫不满足（未调用 BO）
            EffectNotAppliedError: BO 未返回生效回执（未迁移，可重试）
        """
        from meta.core.task_idempotency import run_idempotent

        task = _load_task(data_source, task_id)
        if task["type"] not in EFFECT_TASK_TYPES:
            raise DecisionEffectError(
                f"任务类型不适用决策-生效协议：{task['type']!r}"
                f"（适用 {EFFECT_TASK_TYPES}，§9.7）"
            )

        decision = normalize_decision(decision)
        action_id = resolve_decision_action(task["executor_config"], decision)
        attempt = int(task["attempt"] or 1)
        effect_key = build_effect_key(task["id"], attempt)
        target_state = _decision_target(decision, allow_rework)
        receipt_key = (task["executor_config"] or {}).get("effect_receipt_key") or DEFAULT_RECEIPT_KEY

        from meta.core.task_state_machine import TransitionContext

        ctx = TransitionContext(
            actor=actor or None,
            actor_kind=actor_kind or None,
            actor_has_review_permission=reviewer_permission,
            requires_four_eyes=(
                four_eyes if four_eyes is not None else (task["type"] == "approval")
            ),
            submitter_id=(submitter_id or task["created_by"]) or None,
        )

        def _attempt(ds):
            return self._apply(
                ds, task=task, target_state=target_state, ctx=ctx,
                decision=decision, comment=comment, actor=actor,
                actor_kind=actor_kind, run_as=run_as, action_id=action_id,
                effect_key=effect_key, receipt_key=receipt_key,
            )

        wrapped = run_idempotent(
            data_source, effect_key, _attempt,
            scope=_IDEM_SCOPE, task_id=task["id"],
            workflow_run_id=task["workflow_run_id"], attempt=attempt,
        )
        result = wrapped["result"] or {}
        result["replayed"] = wrapped["status"] == "duplicate"
        result["effect_key"] = effect_key
        return result

    # ------------------------------------------------------------ 单次决策主体

    def _apply(self, data_source, *, task, target_state, ctx, decision, comment,
               actor, actor_kind, run_as, action_id, effect_key, receipt_key) -> Dict:
        from meta.core.task_event_schema import record_transition
        from meta.core.task_state_machine import (
            evaluate_transition, require_transition,
        )

        # 1) 任务侧守卫**先**预校验（fail-closed）：不通过则根本不调 BO，避免反向漂移
        pre = evaluate_transition(task["status"], target_state, ctx)
        if not pre.ok:
            raise DecisionEffectError(
                f"决策迁移被拒（未调用 BO，无副作用）: "
                f"{task['status']} → {target_state}：{pre.reason}"
            )

        # 2) BO 生效（BO 侧守卫独立校验、互不信任；effect_key 供 BO 去重）
        context = {
            "run_as": run_as or actor or "system",
            "actor": actor or "system",
            "actor_kind": actor_kind or "human",
            "task_id": task["id"],
            "workflow_run_id": task["workflow_run_id"],
            "trace_id": task["trace_id"],
            "agent_session_id": task["agent_session_id"],
            "attempt": task["attempt"],
            "effect_key": effect_key,
            "decision": decision,
            "comment": comment,
        }
        try:
            result = self.registry.call(action_id, task["inputs"] or {}, context)
        except Exception as e:  # noqa: BLE001 - 归为「未生效」，可重试
            logger.exception("[DecisionEffect] 生效动作抛异常: %s", action_id)
            raise EffectNotAppliedError(f"生效动作异常: {e}") from e

        # 3) 只在拿到生效回执后才归位（§9.7 规范 1）
        receipt = extract_effect_receipt(result, receipt_key)
        if receipt is None:
            message = (result or {}).get("message") if isinstance(result, dict) else None
            raise EffectNotAppliedError(
                f"BO 未返回生效回执（{receipt_key}）: {message or action_id}"
            )

        require_transition(task["status"], target_state, ctx)
        outputs = {
            "decision": decision,
            "comment": comment,
            "effect_key": effect_key,
            "action_id": action_id,
            "receipt": receipt,
        }
        columns: Dict[str, Any] = {"status": target_state, "outputs": _json_text(outputs)}
        if target_state in ("done", "failed"):
            columns["finished_at"] = _now_iso()
        if target_state == "failed":
            columns["fail_reason"] = f"审核拒绝（decision=reject）：{receipt.get(receipt_key)}"
        _update_task(data_source, task["id"], **columns)

        record_transition(
            data_source, task_id=task["id"],
            from_status=task["status"], to_status=target_state,
            actor=actor or "system", actor_kind=actor_kind or "human",
            reason=f"决策-生效：{decision}",
            summary=f"审核{decision} → 单据 {receipt.get(receipt_key)}",
            payload=receipt,
            detail={"decision": decision, "comment": comment, "effect_key": effect_key},
            workflow_run_id=task["workflow_run_id"], trace_id=task["trace_id"],
            agent_session_id=task["agent_session_id"],
            doc_ref=task["doc_ref"], line_refs=task["line_refs"],
        )
        return {
            "status": "completed", "task_status": target_state, "decision": decision,
            "action_id": action_id, "receipt": receipt,
        }


def decide_and_apply(data_source, task_id: str, **kwargs) -> Dict[str, Any]:
    """模块级便捷入口（等价 `DecisionEffectProtocol().decide(...)`）。"""
    return DecisionEffectProtocol().decide(data_source, task_id, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 对账兜底（§9.7 规范 5）——只读扫描，产出告警清单（入收件箱归 A8）
# ─────────────────────────────────────────────────────────────────────────────

def _norm_pending(item: Any) -> Dict[str, Any]:
    if isinstance(item, str):
        return {"doc_ref": item, "since": None}
    if isinstance(item, dict):
        return {"doc_ref": item.get("doc_ref") or "", "since": item.get("since")}
    return {"doc_ref": "", "since": None}


def _parse_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _active_task_doc_refs(data_source) -> set:
    rows = data_source.execute(
        f"SELECT doc_ref FROM {TASK_TABLE} WHERE type IN (?, ?) AND doc_ref IS NOT NULL "
        f"AND status NOT IN ({', '.join(['?'] * len(_INACTIVE_STATES))})",
        tuple(EFFECT_TASK_TYPES) + _INACTIVE_STATES,
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def reconcile_effects(
    data_source,
    *,
    current_statuses: Optional[Dict[str, str]] = None,
    pending_docs: Optional[List[Any]] = None,
    stale_hours: float = 24,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """对账兜底（§9.7 规范 5）：双向扫描决策-生效漂移，返回告警清单。

    方向:
      0. `approval_without_decision_config` — 活跃审批任务未成对配置 `decision_actions`
                                              （「接线了但没人配」的假闭环护栏）
      1. `done_without_effect`  — 审批任务已 done 但 outputs 无生效回执（R1 漂移）
      2. `effect_mismatch`      — 回执 `new_status` 与单据现状不一致（需注入 `current_statuses`）
      3. `pending_without_task` — 单据等待审批超 `stale_hours` 但无活跃审批任务
                                  （需注入 `pending_docs`，元素为 doc_ref 或 {doc_ref, since}）

    本函数只读、不写库；告警进入统一收件箱属 A8，`bo.status_changed` 反向事件属 D3。
    """
    findings: List[Dict[str, Any]] = []
    now_dt = now or datetime.now()

    rows = data_source.execute(
        f"SELECT id, status, type, outputs, doc_ref, finished_at, executor_config "
        f"FROM {TASK_TABLE} WHERE type IN (?, ?)",
        EFFECT_TASK_TYPES,
    ).fetchall()
    for r in rows:
        task_id, status, task_type, outputs_raw, doc_ref, finished_at, config_raw = r
        outputs = _load_json(outputs_raw, {}) or {}
        receipt = outputs.get("receipt") if isinstance(outputs, dict) else None
        new_status = receipt.get(DEFAULT_RECEIPT_KEY) if isinstance(receipt, dict) else None

        # 方向 0：活跃审批任务缺 decision_actions 配置（「接线了但没人配」的假闭环护栏）
        if status not in _INACTIVE_STATES:
            config = _load_json(config_raw, {}) or {}
            missing = []
            for dec in DECISIONS:
                try:
                    resolve_decision_action(config, dec)
                except DecisionEffectError:
                    missing.append(dec)
            if missing:
                findings.append({
                    "kind": "approval_without_decision_config",
                    "task_id": task_id, "doc_ref": doc_ref or "",
                    "detail": f"缺少 decision_actions 配置: {', '.join(missing)}"
                              f"（approve / reject 必须成对，§9.7 规范 7）",
                })
            continue

        if status == "done" and not new_status:
            findings.append({
                "kind": "done_without_effect", "task_id": task_id,
                "doc_ref": doc_ref or "", "detail": "任务 done 但无生效回执（未落地单据状态）",
            })
            continue
        if status == "done" and new_status and current_statuses is not None and doc_ref:
            current = current_statuses.get(doc_ref)
            if current is not None and current != new_status:
                findings.append({
                    "kind": "effect_mismatch", "task_id": task_id, "doc_ref": doc_ref,
                    "detail": f"回执 {new_status} ≠ 单据现状 {current}",
                })

    if pending_docs is not None:
        active = _active_task_doc_refs(data_source)
        for item in pending_docs:
            info = _norm_pending(item)
            doc_ref = info["doc_ref"]
            if not doc_ref or doc_ref in active:
                continue
            since = _parse_time(info["since"])
            if since is not None and stale_hours is not None:
                if (now_dt - since) < timedelta(hours=float(stale_hours)):
                    continue
            findings.append({
                "kind": "pending_without_task", "task_id": "", "doc_ref": doc_ref,
                "detail": f"单据等待审批超 {stale_hours}h 但无活跃审批任务",
            })

    return findings