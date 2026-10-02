# -*- coding: utf-8 -*-
"""[B1 2026-10-02] BO Action 注册契约固化（idempotent / 前置条件 / 参数 schema / 返回契约）

职责（§12.1 B1 / §9.2）:
- **固化注册形状**——把 BO Action 注册契约的四个要件固化为机器可校验的字段与规则，
  跨应用复用同一注册形状（任务「出口唯一」= BO Action）：
    1) 幂等声明 `idempotent`       执行器据此决定是否用 §9.2 幂等键去重
    2) 前置条件 `preconditions`     声明式、机器可查；调用 handler 前统一拦截
    3) 参数 schema `input_schema`   JSON Schema 形状（`type=object` / `required ⊆ properties`）
    4) 返回契约 响应信封           handler 返回 `dict` 或 `ActionResult`，统一 `success/data/message`
- **机器校验**——`validate_action_meta` / `validate_registry` / `assert_registry_contracts`
  对**每个已注册 action** 逐条校验并产出违规清单；启动期调用（不靠文档靠代码）。
- **前置条件求值**——`check_preconditions(meta, params, context)` 返回未满足项，
  供注册表 `call()` 与任务执行器（B2）在**调用 handler 之前**统一拦截。

前置条件（封闭 kind 集合，全部可机器判定）:
    {"kind": "input_present", "field": "object_type"}
    {"kind": "input_equals",  "field": "object_type", "value": "version"}
    {"kind": "input_in",      "field": "format", "values": ["xlsx", "csv"]}

边界（B1 只做「契约 + 校验 + 前置条件求值」，不越界）:
- 不实现 `BOActionExecutor` 三态（同步 / 异步补全 / needs_review）= B2；
- 不实现决策-生效分离协议 = B3；不实现写权单通道守卫 = B4；
- 不改既有 19 个 action 的注册值（`preconditions` 默认空 → 零行为变化）。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.1 / §9.2 / §12.1 B1
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 返回契约：统一响应信封（`BoActionRegistry.call` 对 handler 返回值的归一化口径）
RESPONSE_ENVELOPE_KEYS: Tuple[str, ...] = ("success", "data", "message")

# action_id 命名：小写段 + 点分层（如 user.authenticate / batch_save / function.aggregate.query）
ACTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")

# 封闭取值域（与 BusinessActionMeta 默认值一致）
OPERATION_TYPES = ("action", "function")
VISIBILITIES = ("normal", "important", "internal")
PRECONDITION_KINDS = ("input_present", "input_equals", "input_in")

# 布尔型契约字段
_BOOL_FIELDS = ("requires_auth", "requires_admin", "idempotent",
                "async_supported", "cacheable")


class ActionContractError(ValueError):
    """BO Action 注册契约违规（一个或多个 action 未满足固化契约）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 校验：单 action
# ─────────────────────────────────────────────────────────────────────────────

def _validate_schema(schema: Any, label: str) -> List[str]:
    """参数/返回 schema 形状校验：dict + type=object + required ⊆ properties。"""
    errors: List[str] = []
    if not isinstance(schema, dict):
        return [f"{label} 必须是 dict（收到 {type(schema).__name__}）"]
    if schema.get("type") != "object":
        errors.append(f"{label}.type 必须为 'object'（收到 {schema.get('type')!r}）")

    props = schema.get("properties")
    if props is not None and not isinstance(props, dict):
        errors.append(f"{label}.properties 必须是 dict")
        props = None

    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list):
            errors.append(f"{label}.required 必须是 list")
        elif props is None:
            errors.append(f"{label}.required 需同时声明 properties")
        else:
            unknown = [name for name in required if name not in props]
            if unknown:
                errors.append(f"{label}.required 含未声明字段：{unknown}")
    return errors


def validate_preconditions(preconditions: Any) -> List[str]:
    """前置条件声明形状校验（每条须为 dict 且 kind 合法、必备键齐全）。"""
    errors: List[str] = []
    if preconditions is None:
        return errors
    if not isinstance(preconditions, list):
        return [f"preconditions 必须是 list（收到 {type(preconditions).__name__}）"]

    for i, pre in enumerate(preconditions):
        where = f"preconditions[{i}]"
        if not isinstance(pre, dict):
            errors.append(f"{where} 必须是 dict")
            continue
        kind = pre.get("kind")
        if kind not in PRECONDITION_KINDS:
            errors.append(f"{where}.kind 非法：{kind!r}（允许 {PRECONDITION_KINDS}）")
            continue
        if not pre.get("field"):
            errors.append(f"{where} 缺少 field")
        if kind == "input_equals" and "value" not in pre:
            errors.append(f"{where} (input_equals) 缺少 value")
        if kind == "input_in":
            values = pre.get("values")
            if not isinstance(values, list) or not values:
                errors.append(f"{where} (input_in) values 必须是非空 list")
    return errors


def validate_action_meta(meta: Any) -> List[str]:
    """校验单个 `BusinessActionMeta` 是否满足固化契约；返回违规清单（空 = 合规）。"""
    errors: List[str] = []
    action_id = getattr(meta, "action_id", None)

    if not isinstance(action_id, str) or not ACTION_ID_PATTERN.match(action_id):
        errors.append(f"action_id 命名非法：{action_id!r}（须匹配 {ACTION_ID_PATTERN.pattern}）")
    if not getattr(meta, "description", ""):
        errors.append("description 不得为空")
    if not callable(getattr(meta, "handler", None)):
        errors.append("handler 必须可调用")
    if not getattr(meta, "category", ""):
        errors.append("category 不得为空")
    if not getattr(meta, "object_type", None):
        errors.append("object_type 不得为空（无关联对象用 '*'）")

    if getattr(meta, "operation_type", None) not in OPERATION_TYPES:
        errors.append(f"operation_type 非法：{getattr(meta, 'operation_type', None)!r}")
    if getattr(meta, "visibility", None) not in VISIBILITIES:
        errors.append(f"visibility 非法：{getattr(meta, 'visibility', None)!r}")

    for name in _BOOL_FIELDS:
        if not isinstance(getattr(meta, name, None), bool):
            errors.append(f"{name} 必须是 bool")

    input_schema = getattr(meta, "input_schema", None)
    if input_schema is not None:
        errors.extend(_validate_schema(input_schema, "input_schema"))
    output_schema = getattr(meta, "output_schema", None)
    if output_schema is not None:
        errors.extend(_validate_schema(output_schema, "output_schema"))

    ttl = getattr(meta, "cache_ttl", 0)
    if not isinstance(ttl, int) or ttl < 0:
        errors.append(f"cache_ttl 必须是非负整数（收到 {ttl!r}）")
    elif getattr(meta, "cacheable", False) and ttl <= 0:
        errors.append("cacheable=True 时 cache_ttl 必须 > 0")

    errors.extend(validate_preconditions(getattr(meta, "preconditions", None)))
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# 校验：全注册表
# ─────────────────────────────────────────────────────────────────────────────

def validate_registry(registry=None) -> Dict[str, List[str]]:
    """校验注册表内全部 action；返回 {action_id: [违规...]}（仅含违规项）。"""
    if registry is None:
        from meta.core.bo_action_registry import bo_action_registry
        registry = bo_action_registry

    violations: Dict[str, List[str]] = {}
    for meta in registry.list_all():
        errs = validate_action_meta(meta)
        if errs:
            violations[getattr(meta, "action_id", "<unknown>")] = errs
    return violations


def assert_registry_contracts(registry=None) -> None:
    """严格模式：任一 action 违规即抛 `ActionContractError`（供 CI / 测试 / 严格启动）。"""
    violations = validate_registry(registry)
    if violations:
        detail = "; ".join(f"{aid}: {errs}" for aid, errs in violations.items())
        raise ActionContractError(f"BO Action 契约违规 → {detail}")


def report_registry_contracts(registry=None, *, level: str = "warning") -> int:
    """非严格模式：把违规清单打到日志（启动期用），返回违规 action 数（0 = 全合规）。"""
    violations = validate_registry(registry)
    if violations:
        msg = "[BOActionContract] %d 个 action 契约违规: %s" % (len(violations), violations)
        getattr(logger, level, logger.warning)(msg)
    else:
        logger.info("[BOActionContract] 契约校验通过：%d 个 action 全部合规",
                    len(registry.list_all()) if registry is not None else -1)
    return len(violations)


# ─────────────────────────────────────────────────────────────────────────────
# 前置条件求值（调用 handler 之前统一拦截）
# ─────────────────────────────────────────────────────────────────────────────

def _is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _check_one(pre: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
    kind = pre.get("kind")
    field = pre.get("field")
    if kind == "input_present":
        if _is_blank(params.get(field)):
            return f"缺少必填输入 {field}"
    elif kind == "input_equals":
        if params.get(field) != pre.get("value"):
            return f"输入 {field} 须为 {pre.get('value')!r}（实际 {params.get(field)!r}）"
    elif kind == "input_in":
        if params.get(field) not in (pre.get("values") or []):
            return f"输入 {field} 须落在 {pre.get('values')}（实际 {params.get(field)!r}）"
    else:  # 注册期已由 validate_preconditions 拦截；此处兜底
        return f"未知前置条件类型 {kind!r}"
    return None


def check_preconditions(meta: Any, params: Optional[Dict[str, Any]] = None,
                        context: Optional[Dict[str, Any]] = None) -> List[str]:
    """求值 action 声明的前置条件；返回**未满足项**描述清单（空 = 全部满足）。

    纯声明式判定（只看 `params`），不触发 handler、不写库 —— 供 `call()` 与执行器共用。
    `context` 预留给后续扩展（如 run-as 身份类前置条件），当前不求值。
    """
    preconditions = getattr(meta, "preconditions", None) or []
    params = params or {}
    unmet: List[str] = []
    for pre in preconditions:
        if not isinstance(pre, dict):
            continue
        reason = _check_one(pre, params)
        if reason:
            unmet.append(reason)
    return unmet