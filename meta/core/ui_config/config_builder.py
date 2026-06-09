from meta.core.models import registry as _model_registry
from meta.core.ui_config.field_extractor import FieldExtractor
from meta.core.ui_config.association_extractor import AssociationExtractor
from meta.core.ui_config.value_help_formatter import value_help_to_dict, _make_json_safe


class UIConfigBuilder:

    def __init__(self, display_name_service, infer_navigation_fn):
        self._dns = display_name_service
        self._field_extractor = FieldExtractor()
        self._assoc_extractor = AssociationExtractor()
        self._infer_navigation = infer_navigation_fn

    def build(self, object_type, view_name=None):
        cache_key = "{0}:{1}".format(object_type, view_name or 'default')
        cached = _model_registry.get_ui_config(cache_key)
        if cached is not None:
            return cached

        meta_obj = _model_registry.get(object_type)
        if not meta_obj:
            return {}

        config = {
            'object_type': meta_obj.id,
            'label': meta_obj.name,
            'table_name': getattr(meta_obj, 'table_name', ''),
            'aspects': getattr(meta_obj, 'aspects', []) or [],
        }

        ui_view_config = getattr(meta_obj, 'ui_view_config', None)
        if ui_view_config:
            config['ui_view_config'] = _make_json_safe(ui_view_config)

        fields_info = []
        field_constraints = []

        for f in meta_obj.fields:
            field_info = self._field_extractor.extract(f)

            field_type_str = f.field_type.value if (
                hasattr(f, 'field_type') and hasattr(f.field_type, 'value')
            ) else 'string'

            enum_values = getattr(f, 'enum_values', None)
            if enum_values and len(enum_values) > 0:
                normalized = _make_json_safe(enum_values)
                if field_type_str == 'boolean':
                    for opt in normalized:
                        raw_val = opt.get('value')
                        if isinstance(raw_val, bool):
                            opt['value'] = 1 if raw_val else 0
                        elif isinstance(raw_val, str) and raw_val.lower() in ('true', 'false'):
                            opt['value'] = 1 if raw_val.lower() == 'true' else 0
                field_info['enum_values'] = normalized

            default_value = getattr(f, 'default', None)
            if default_value is not None:
                if field_type_str == 'boolean' and enum_values:
                    if isinstance(default_value, bool):
                        default_value = 1 if default_value else 0
                    elif isinstance(default_value, str) and default_value.lower() in ('true', 'false'):
                        default_value = 1 if default_value.lower() == 'true' else 0
                field_info['default'] = default_value

            constraints = getattr(f, 'constraints', None)
            if constraints:
                field_info['constraints'] = _make_json_safe(constraints)
                for c in constraints:
                    if isinstance(c, dict):
                        field_constraints.append({
                            'field': f.id,
                            'type': c.get('type'),
                            'params': c.get('params', {}),
                            'message': c.get('message', ''),
                        })

            value_help = getattr(f, 'value_help', None)
            if value_help:
                field_info['value_help'] = _make_json_safe(value_help_to_dict(value_help))

            fields_info.append(field_info)

        config['fields'] = fields_info
        if field_constraints:
            config['constraints'] = field_constraints

        self._inject_global_constraints(config, meta_obj)
        self._inject_associations(config, meta_obj)
        self._inject_actions(config, meta_obj)
        self._inject_rules(config, meta_obj)
        self._inject_meta(config, meta_obj)
        self._inject_display_names(config, object_type, meta_obj)

        _model_registry.set_ui_config(cache_key, config)
        return config

    def _inject_global_constraints(self, config, meta_obj):
        global_constraints = getattr(meta_obj, 'constraints', None)
        if global_constraints:
            if 'constraints' not in config:
                config['constraints'] = []
            for c in global_constraints:
                if isinstance(c, dict):
                    config['constraints'].append(c)

    def _inject_associations(self, config, meta_obj):
        assoc_list = self._assoc_extractor.extract(
            meta_obj, _model_registry, _make_json_safe, self._infer_navigation)
        if assoc_list:
            config['associations'] = assoc_list

    def _inject_actions(self, config, meta_obj):
        actions = getattr(meta_obj, 'actions', None)
        if actions:
            actions_list = []
            if isinstance(actions, dict):
                for action_id, action in actions.items():
                    a = _make_json_safe(action)
                    a['id'] = action_id
                    actions_list.append(a)
            elif isinstance(actions, list):
                for action in actions:
                    a = _make_json_safe(action)
                    actions_list.append(a)
            config['actions'] = actions_list

    def _inject_rules(self, config, meta_obj):
        rules = getattr(meta_obj, 'rules', None)
        if rules:
            rules_list = []
            if isinstance(rules, dict):
                for rule_id, rule in rules.items():
                    r = _make_json_safe(rule)
                    r['id'] = rule_id
                    rules_list.append(r)
            elif isinstance(rules, list):
                for rule in rules:
                    r = _make_json_safe(rule)
                    rules_list.append(r)
            config['rules'] = rules_list

    def _inject_meta(self, config, meta_obj):
        authorization = getattr(meta_obj, 'authorization', None)
        if authorization:
            config['authorization'] = _make_json_safe(authorization)

        import_export = getattr(meta_obj, 'import_export', None)
        if import_export:
            config['import_export'] = _make_json_safe(import_export)

        # [FIX] 注入对象级 cascade_select 配置（yaml 顶部声明的 FK 级联关系）。
        # 前端 useFormCascade 依赖此字段启动级联监听（父变 → 清空下游 formData）。
        # 不注入的话前端 metaObject.value.cascade_select 永远为空，initialize() 直接 return。
        cascade_select = getattr(meta_obj, 'cascade_select', None)
        if cascade_select:
            config['cascade_select'] = _make_json_safe(cascade_select)

    def _inject_display_names(self, config, object_type, meta_obj):
        dns = self._dns
        display_field = getattr(meta_obj, 'display_name_field', None) or dns._infer_display_name_field(meta_obj)
        if display_field is None:
            display_field = 'name'
        config['display_name_field'] = display_field
        config['field_display_names'] = dns.get_all_field_names(object_type)

        relation_displays = {}
        for rel in meta_obj.relations:
            if rel.display_format:
                relation_displays[rel.id] = rel.display_format
        config['relation_displays'] = relation_displays
