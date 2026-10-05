# -*- coding: utf-8 -*-
"""F1 步 2 下游接线：`item_xref.partner_id` → party 对外档案面（value_help）

依据: docs/superpowers/specs/2026-10-04-f1-governance-domain-design.md
      §3.5（对外档案恒排除 source='org'）/ §6（内部表示走 intra_trade 受控放行）/ §9.4(F2)

口径：
  - 外部标识（客户/供应商/制造商件号）的伙伴 = **对外伙伴** ⇒ value_help 目标 = `party_archive`
    （视图谓词 COALESCE(source,'') <> 'org'，结构强制排除内部组织表示）。
  - 不得指向写锚 `party`（无口径）或内部面 `party_internal`（内部表示须走 intra_trade 受控放行）。
  - partner_type（客户/供应商/制造商）属角色层（命名待 F2），未建前不做过滤。
"""
import os
import sys

import pytest
import yaml

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas'
)

pytestmark = pytest.mark.unit


def _load_raw(bo_id):
    with open(os.path.join(_SCHEMA_DIR, bo_id + '.yaml'), 'r',
              encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get('fields') or []:
        if f.get('id') == field_id:
            return f
    return None


class TestPartnerIdValueHelpWiring:
    def test_target_is_archive_face(self):
        """partner_id 的 value_help 目标 = 对外档案面 party_archive。"""
        field = _field(_load_raw('item_xref'), 'partner_id')
        assert field is not None
        source = (field.get('value_help') or {}).get('source') or {}
        assert source.get('type') == 'bo'
        assert source.get('target_bo') == 'party_archive'
        assert source.get('value_field') == 'id'
        assert source.get('display_field') == 'name'
        assert source.get('apply_target_permissions') is True

    def test_display_and_ui_wired(self):
        """关联展示 + 选择控件已接线（不再是裸整数 input）。"""
        field = _field(_load_raw('item_xref'), 'partner_id')
        display = (field.get('semantics') or {}).get('display') or {}
        assert display.get('type') == 'association'
        assert display.get('target_type') == 'party_archive'
        assert display.get('display_field') == 'name'
        ui = field.get('ui') or {}
        assert ui.get('widget') == 'select'
        assert ui.get('relation') == 'party_archive'
        assert ui.get('multiple') is False

    def test_target_bo_not_base_or_internal(self):
        """红线：不得指向写锚 party 或内部面 party_internal（F1 治理分域）。"""
        field = _field(_load_raw('item_xref'), 'partner_id')
        target = (field.get('value_help') or {}).get('source', {}).get('target_bo')
        assert target not in ('party', 'party_internal')

    def test_target_face_is_readonly_view_excluding_org(self):
        """目标面确为对外档案：真视图 + NULL 安全排除 source='org' + 仅读动作。"""
        archive = _load_raw('party_archive')
        assert archive.get('object_type') == 'view'
        view_def = archive.get('view_definition') or ''
        assert 'parties' in view_def
        assert "COALESCE(source, '') <> 'org'" in view_def
        action_ids = {a.get('id') for a in (archive.get('actions') or [])}
        assert action_ids == {'party_archive_read', 'party_archive_list'}
        assert archive.get('import_export', {}).get('auto_crud') is False