def value_help_to_dict(vh):
    from meta.core.models import ValueHelpConfig
    if not vh:
        return None
    if isinstance(vh, ValueHelpConfig) and vh.is_unified():
        result = {}
        if vh.source:
            result["source"] = {
                "type": vh.source.type,
                "enum_type_id": vh.source.enum_type_id,
                "filter_by_dimension": vh.source.filter_by_dimension,
                "value_filter": vh.source.value_filter,
                "sort_by": vh.source.sort_by,
                "i18n_join_fields": vh.source.i18n_join_fields,
                "default_value_code": vh.source.default_value_code,
                "target_bo": vh.source.target_bo,
                # [F1 2026-10-20] 展示解析口径（留空 = 与 target_bo 同口径）
                #   前端需透传给 resolve 接口，否则编辑态回显会退化为技术 id。
                "display_target_bo": getattr(vh.source, "display_target_bo", "") or "",
                # [FK 2026-10-22] 跳转落点口径（留空 = 与 target_bo 同口径）
                #   前端 getFkTargetObjectType 优先取它，缺省才回退 target_bo。
                "detail_target_bo": getattr(vh.source, "detail_target_bo", "") or "",
                # 落点 id 的取值列（id 空间不同源时用），留空 = FK 原值即落点 id
                "detail_target_id_field": getattr(vh.source, "detail_target_id_field", "") or "",
                "value_field": vh.source.value_field,
                "display_field": vh.source.display_field,
                "code_field": vh.source.code_field,
                "hierarchy": vh.source.hierarchy,
                "apply_target_permissions": vh.source.apply_target_permissions,
                "endpoint": vh.source.endpoint,
                "params": vh.source.params,
            }
        if vh.behavior:
            # multiple 逻辑：
            # - None（未设置）：详情/表单场景统一默认 False（单选）。list-view filter 走的是
            #   list_view_config.filter_definitions，跟这里的 ui-config 是分开的两套配置，
            #   不受此影响。如果某个 view 真要多选，yaml 必须显式设 multiple: true。
            # - False（显式单选）：尊重用户设置
            # - True（显式多选）：尊重用户设置
            raw_multiple = vh.behavior.multiple
            if raw_multiple is None:
                multiple = False  # 修复：FK 字段默认值由 True 改为 False
            else:
                multiple = raw_multiple  # 显式设置，尊重
            result["behavior"] = {
                "binding_strength": vh.behavior.binding_strength,
                "validation": vh.behavior.validation,
                "search_fields": vh.behavior.search_fields,
                "min_search_length": vh.behavior.min_search_length,
                "debounce_ms": vh.behavior.debounce_ms,
                "multiple": multiple,
                "parameter_bindings": [
                    {
                        "local_field": pb.local_field,
                        "target_field": pb.target_field,
                        "required": pb.required,
                        "constant": pb.constant,
                    }
                    for pb in vh.behavior.parameter_bindings
                ],
                "out_mappings": [
                    {
                        "value_help_field": om.value_help_field,
                        "local_field": om.local_field,
                    }
                    for om in vh.behavior.out_mappings
                ],
                "cascade_select": [
                    {
                        "parent_field": cs.parent_field,
                        "child_field": cs.child_field,
                        "cascade_source": cs.cascade_source,
                        "cascade_field": cs.cascade_field,
                        "required": cs.required,
                    }
                    for cs in vh.behavior.cascade_select
                ],
                "enabled_condition": vh.behavior.enabled_condition,
                # [FIX 2026-09-05 父组织树状 SearchHelp] 自引用层级防环标记
                "exclude_self": vh.behavior.exclude_self,
            }
        if vh.presentation:
            result["presentation"] = {
                "result_type": vh.presentation.result_type,
                "display_mode": vh.presentation.display_mode,
                "display_columns": [
                    {
                        "field": dc.field,
                        "label": dc.label,
                        "width": dc.width,
                        "sortable": dc.sortable,
                    }
                    for dc in vh.presentation.display_columns
                ],
                "sort_by": vh.presentation.sort_by,
                "page_size": vh.presentation.page_size,
                "display_format": vh.presentation.display_format,
                "color_mapping": vh.presentation.color_mapping,
            }
        return result
    return _make_json_safe(vh)


def _make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_safe(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    elif hasattr(obj, '__dict__'):
        return _make_json_safe(obj.__dict__)
    else:
        return str(obj)
