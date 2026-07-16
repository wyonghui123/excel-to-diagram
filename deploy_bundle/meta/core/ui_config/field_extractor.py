from meta.core.ui_config.config_constants import (
    SYSTEM_FIELDS, DATETIME_TYPES, SENSITIVE_FIELDS, DEFAULT_VISIBILITY,
)
from meta.core.ui_config.value_help_formatter import _make_json_safe


class FieldExtractor:

    def extract(self, field):
        ft = field.field_type.value if (
            hasattr(field, 'field_type') and hasattr(field.field_type, 'value')
        ) else 'string'

        info = {
            'id': field.id,
            'name': field.name,
            'type': ft,
            'required': getattr(field, 'required', False),
            'unique': getattr(field, 'unique', False),
        }

        vis = dict(DEFAULT_VISIBILITY)
        self._extract_ui(field, info, vis)
        self._extract_semantics(field, info, vis)
        self._apply_overrides(field.id, ft, vis)

        if getattr(field, 'computed', False) or getattr(field, 'compute_expr', None):
            vis['readonly'] = True
            vis['editable'] = False
            info['computed'] = True

        info.update(vis)
        return info

    def _extract_ui(self, field, info, vis):
        ui = getattr(field, 'ui', None)
        if not ui:
            return

        if isinstance(ui, dict):
            for key in ('visible', 'editable', 'readonly',
                        'hidden_in_detail', 'hidden_in_form', 'hidden_in_list'):
                if key in ui:
                    vis[key] = ui[key]
            info['ui'] = ui
            for key in ('group', 'order', 'width', 'placeholder', 'hint', 'widget'):
                if key in ui:
                    info[key] = ui[key]
        elif hasattr(ui, 'visible'):
            vis['visible'] = ui.visible
            vis['editable'] = getattr(ui, 'editable', True)
            vis['readonly'] = getattr(ui, 'readonly', False)
            vis['hidden_in_detail'] = getattr(ui, 'hidden_in_detail', False)
            vis['hidden_in_form'] = getattr(ui, 'hidden_in_form', False)
            vis['hidden_in_list'] = getattr(ui, 'hidden_in_list', False)
            info['ui'] = _make_json_safe(ui)
            widget = getattr(ui, 'widget', None)
            if widget:
                info['widget'] = widget

    def _extract_semantics(self, field, info, vis):
        semantics = getattr(field, 'semantics', None)
        if not semantics:
            return

        is_dict = isinstance(semantics, dict)
        sdata = {}

        def _get(key, default=False):
            return semantics.get(key, default) if is_dict else getattr(semantics, key, default)

        mapping = [
            ('business_key',    'business_key',    None),
            ('audit_field',     None,              ('readonly', True, 'editable', False, 'visible', False)),
            ('immutable',       'immutable',        None),
            ('readonly_always', None,               ('readonly', True, 'editable', False)),
            ('parent_key',      'parent_key',       None),
            ('context_field',   'context_field',    None),
            ('mandatory',       'mandatory',        None),
            ('display_name',    'display_name',     None),
            ('virtual',         'virtual',          None),
        ]

        for sem_key, info_key, vis_override in mapping:
            if _get(sem_key):
                sdata[sem_key] = True
                if info_key:
                    info[info_key] = True
                if vis_override:
                    it = iter(vis_override)
                    for k, v in zip(it, it):
                        vis[k] = v

        sh_for = _get('search_help_for', None)
        if sh_for:
            sdata['search_help_for'] = sh_for

        if not is_dict:
            ev = getattr(semantics, 'export_visible', None)
            if ev is not None:
                info['export_visible'] = ev
            iv = getattr(semantics, 'import_visible', None)
            if iv is not None:
                info['import_visible'] = iv
        else:
            if 'export_visible' in semantics and semantics['export_visible'] is True:
                info['export_visible'] = True
            if 'import_visible' in semantics and semantics['import_visible'] is False:
                info['import_visible'] = False

        info['semantics'] = sdata

    def _apply_overrides(self, field_id, field_type_str, vis):
        if field_id in SYSTEM_FIELDS:
            vis['readonly'] = True
            vis['editable'] = False
            vis['hidden_in_form'] = True

        if field_type_str in DATETIME_TYPES and field_id in ('created_at', 'updated_at'):
            vis['readonly'] = True
            vis['editable'] = False

        if field_id in SENSITIVE_FIELDS:
            vis['visible'] = False
            vis['hidden_in_detail'] = True
            vis['hidden_in_form'] = True
            vis['hidden_in_list'] = True
