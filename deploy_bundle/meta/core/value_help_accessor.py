"""value_help 获取 SSOT (Single Source of Truth)

统一 import_export_service / manage_service / EnrichmentEngine 中的
value_help 获取逻辑。

优先级：field.value_help → field.ui.value_help（fallback）

背景：
- import_export_service._get_value_help: 先 field.value_help → fallback field.ui.value_help
- manage_service._validate_value_helps: 只查 field.ui.value_help
- EnrichmentEngine.enrich_fk_display_names: 只查 field.value_help

三处不一致，统一后行为为：先 field.value_help，fallback field.ui.value_help。
"""


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
