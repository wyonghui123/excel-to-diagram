"""value_help 获取 SSOT (Single Source of Truth)

统一 import_export_service / manage_service / EnrichmentEngine 中的
value_help 获取逻辑。

优先级：field.value_help → field.ui.value_help（fallback）

背景：
- import_export_service._get_value_help: 先 field.value_help → fallback field.ui.value_help
- manage_service._validate_value_helps: 只查 field.ui.value_help
- EnrichmentEngine.enrich_fk_display_names: 只查 field.value_help

三处不一致，统一后行为为：先 field.value_help，fallback field.ui.value_help。

本模块同时是 value_help 两个子语义的**唯一解释点**（读写两侧共用）：
- `get_validation_flag(vh)`：写入层校验开关（读 behavior.validation，回落旧版顶层 validation）
- `parse_value_filter_conditions(value_filter)`：value_filter → (field, op, value) 三元组
  读侧（候选过滤）与写侧（保存校验）必须调用同一函数，不得各自解析后缀。
"""

from typing import Any, Dict, List, Tuple

# value_filter / 查询请求的键后缀 → 归一操作符。
# 操作符取值直接采用 `QueryOperator` 枚举值（eq/in/not_in/like/ge/le/is_null），
# 不另造一套词汇；后缀剥离只在本模块发生。
_SUFFIX_OPERATORS = (
    ("__notin", "not_in"),
    ("__in", "in"),
    ("__like", "like"),
    ("__gte", "ge"),
    ("__lte", "le"),
)


def get_value_help(meta_field):
    """统一获取字段的 value_help 配置

    优先级：
    1. field.value_help（字段级定义）
    2. field.ui.value_help（UI 级定义，fallback）

    Args:
        meta_field: MetaField 实例

    Returns:
        Optional[ValueHelpConfig]: value_help 配置对象，无则返回 None
    """
    vh = getattr(meta_field, 'value_help', None)
    if not vh:
        ui = getattr(meta_field, 'ui', None)
        if ui:
            vh = getattr(ui, 'value_help', None)
    return vh


def get_validation_flag(vh) -> bool:
    """value_help 的「写入层校验开关」唯一解释点。

    统一三层声明读 `behavior.validation`（缺省 True）；
    旧版声明回落到顶层 `validation`（缺省 False，兼容位）。
    """
    behavior = getattr(vh, 'behavior', None)
    if behavior is not None:
        flag = getattr(behavior, 'validation', None)
        if flag is not None:
            return bool(flag)
    return bool(getattr(vh, 'validation', False))


def _split_values(value: Any) -> List[Any]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(',') if v.strip()]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def parse_value_filter_conditions(value_filter: Dict[str, Any]) -> List[Tuple[str, str, Any]]:
    """value_filter 的唯一解释点：归一成 `(field, op, value)`。

    `op` ∈ {eq, in, not_in, like, ge, le, is_null}（取 `QueryOperator` 枚举值）。
    键后缀由本函数剥离，调用方不得自行解析。

    规则：
    - `xxx__in` / `xxx__notin` → 多值列表（支持 "a,b" 逗号串或 list）
    - `xxx__like` / `xxx__gte` / `xxx__lte` → 对应操作符
    - 无后缀 → `eq`；值为 None → `is_null`
    """
    conditions: List[Tuple[str, str, Any]] = []
    for key, value in (value_filter or {}).items():
        for suffix, op in _SUFFIX_OPERATORS:
            if key.endswith(suffix):
                field = key[:-len(suffix)]
                if op in ('in', 'not_in'):
                    conditions.append((field, op, _split_values(value)))
                else:
                    conditions.append((field, op, value))
                break
        else:
            if value is None:
                conditions.append((key, 'is_null', None))
            else:
                conditions.append((key, 'eq', value))
    return conditions
