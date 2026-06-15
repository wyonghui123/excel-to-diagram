from meta.core.models import registry as _model_registry
from meta.core.ui_config.field_extractor import FieldExtractor
from meta.core.ui_config.association_extractor import AssociationExtractor
from meta.core.ui_config.value_help_formatter import value_help_to_dict, _make_json_safe


class UIConfigBuilder:

    def __init__(self, display_name_service, infer_navigation_fn, data_source=None):
        self._dns = display_name_service
        self._field_extractor = FieldExtractor()
        self._assoc_extractor = AssociationExtractor()
        self._infer_navigation = infer_navigation_fn
        # [FIX 2026-06-15] data_source 用于从数据库加载 value_help.source.type=='enum' 的动态枚举值
        # 之前只使用字段元数据中静态定义的 enum_values，导致 detail 页显示 key (REFERENCES, BIDIRECTIONAL)
        # 而非中文 name。详见关系详情 bug 报告。
        self._data_source = data_source

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
            else:
                # [FIX 2026-06-15] 字段未静态定义 enum_values 时，从 value_help.source.type='enum' 的
                # enum_type_id 动态查询数据库加载（如 relation_type、direction）。
                # 前端 DetailSection.vue 的 formatEnumValue 依赖 field.enum_values 做 key→name 映射。
                vh_dict = value_help_to_dict(getattr(f, 'value_help', None)) or {}
                vh_source = vh_dict.get('source') or {}
                if vh_source.get('type') == 'enum' and vh_source.get('enum_type_id'):
                    db_enum_values = self._load_enum_values_from_db(
                        vh_source.get('enum_type_id'))
                    if db_enum_values:
                        field_info['enum_values'] = db_enum_values

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

    def _load_enum_values_from_db(self, enum_type_id):
        """从数据库加载指定 enum_type 的所有有效枚举值。

        Returns:
            list[dict]: [{'value': 'CODE', 'label': '名称', 'id': 'CODE', 'name': '名称'}, ...]
            失败或无数据时返回空列表。
        """
        if not enum_type_id or not self._data_source:
            return []
        try:
            ds = self._data_source
            cursor = ds.execute(
                "SELECT code, name, name_en FROM enum_values "
                "WHERE enum_type_id = ? AND is_active = 1 "
                "ORDER BY sort_order, code",
                [enum_type_id],
            )
            rows = cursor.fetchall() if cursor else []
            options = []
            for row in rows:
                # row 可能是 tuple、dict 或 sqlite3.Row
                if isinstance(row, dict):
                    code = row.get('code', '')
                    name = row.get('name', '') or code
                else:
                    code = row[0] if len(row) > 0 else ''
                    name = row[1] if len(row) > 1 else (code or '')
                if not code:
                    continue
                # 同时给 value/label 和 id/name 两种 key 风格，兼容 DetailSection.vue 的
                # getFieldOptions/formatEnumValue（它要 opt.value 或 opt.id）和其它 widget。
                options.append({
                    'value': code,
                    'label': name,
                    'id': code,
                    'name': name,
                })
            return options
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                f"[UIConfigBuilder] _load_enum_values_from_db({enum_type_id}) failed: {exc}")
            return []
