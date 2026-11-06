# -*- coding: utf-8 -*-
"""T5.1 元数据影响分析（where-used）测试（纯元数据层，不依赖 DB）。"""

import pytest

from meta.core.models import (
    MetaField,
    MetaIndex,
    MetaObject,
    MetaQuery,
    MetaQueryFilter,
    MetaRelation,
    MetaRule,
    MetaStateFieldPolicy,
    MetaStateTransition,
)
from meta.core.models_enums import RelationType
from meta.core.models_ui_config import (
    UIFormSection,
    UIFormViewConfig,
    UIListViewColumn,
    UIListViewConfig,
    UIViewConfig,
)
from meta.services.meta_impact_service import MetaImpactService


class _FakeRegistry:
    def __init__(self, objects):
        self._objects = {obj.id: obj for obj in objects}

    def get(self, object_id):
        return self._objects.get(object_id)


def _f(field_id, name=None):
    return MetaField(id=field_id, name=name or field_id,
                     field_type="string", db_column=field_id)


def _build_object():
    meta_obj = MetaObject(
        id="po_test",
        name="采购订单测试",
        table_name="po_test",
        fields=[_f("status", "状态"), _f("remark", "备注"), _f("item_id", "物料")],
        rules=[
            MetaStateTransition(
                id="po_submit", name="提交", state_field="status",
                from_states=["draft"], to_state="submitted",
            ),
            MetaRule(
                id="require_remark", name="备注校验",
                condition="status == 'submitted' and remark == ''",
                target_fields=["remark"],
            ),
        ],
        relations=[
            MetaRelation(id="po_item_rel", name="物料关联",
                         relation_type=RelationType.REFERENCE,
                         target_object="item", source_field="item_id"),
        ],
        indexes=[MetaIndex(fields=["status", "item_id"], name="idx_status")],
        queries=[
            MetaQuery(id="q_open", name="未完成订单",
                      filters=[MetaQueryFilter(field="status")],
                      fields=["status", "remark"]),
        ],
        ui_view_config=UIViewConfig(
            list=UIListViewConfig(columns=[UIListViewColumn(key="status")]),
            form=UIFormViewConfig(sections=[UIFormSection(title="备注", fields=["remark"])]),
        ),
        state_field_policies={
            "submitted": MetaStateFieldPolicy(readonly=["item_id"], required=["remark"]),
        },
    )
    return meta_obj


@pytest.fixture()
def service():
    return MetaImpactService(_FakeRegistry([_build_object()]))


def _kinds(result):
    return {ref['kind'] for ref in result['impacts'][0]['references']}


def test_state_field_references_transition_and_matrix(service):
    result = service.analyze("po_test", "status")
    kinds = _kinds(result)
    assert "state_transition" in kinds
    assert "index" in kinds
    assert "query" in kinds
    assert "view" in kinds
    details = {ref['detail'] for ref in result['impacts'][0]['references']}
    assert "state_field" in details


def test_rule_target_field_and_expression(service):
    result = service.analyze("po_test", "remark")
    by_kind = {}
    for ref in result['impacts'][0]['references']:
        by_kind.setdefault(ref['kind'], []).append(ref)
    assert any(ref['detail'].startswith("target_field") for ref in by_kind.get("rule", []))
    assert any(ref['id'].endswith(".required") for ref in by_kind.get("state_field_policy", []))
    assert "form.section" in [ref['detail'] for ref in by_kind.get("view", [])]


def test_relation_source_field(service):
    result = service.analyze("po_test", "item_id")
    refs = result['impacts'][0]['references']
    assert any(ref['kind'] == 'relation' and ref['detail'] == 'source_field' for ref in refs)
    assert any(ref['kind'] == 'state_field_policy' for ref in refs)


def test_object_level_analyze_covers_all_fields(service):
    result = service.analyze("po_test")
    assert result['field'] == ''
    assert [item['field'] for item in result['impacts']] == ['status', 'remark', 'item_id']
    assert result['total'] > 0
    assert set(result['summary']) <= {'rule', 'state_transition', 'state_field_policy',
                                      'relation', 'index', 'query', 'view'}


def test_unknown_object_and_field_raise(service):
    with pytest.raises(KeyError):
        service.analyze("nope")
    with pytest.raises(ValueError):
        service.analyze("po_test", "not_a_field")


def test_field_id_word_boundary(service):
    """`id` 不应命中 `item_id`；只按独立标识符匹配表达式。"""
    meta_obj = _build_object()
    meta_obj.rules.append(MetaRule(
        id="check_item", name="物料必填",
        condition="item_id is not None", target_fields=[]))
    svc = MetaImpactService(_FakeRegistry([meta_obj]))
    result = svc.analyze("po_test", "item_id")
    rule_ids = [ref['id'] for ref in result['impacts'][0]['references'] if ref['kind'] == 'rule']
    assert "check_item" in rule_ids
    # 反向：status 不应因为 "item_id" 里含 id 而被误判
    status_result = svc.analyze("po_test", "status")
    status_rule_ids = [ref['id'] for ref in status_result['impacts'][0]['references']
                       if ref['kind'] == 'rule']
    assert "check_item" not in status_rule_ids


def test_purchase_order_real_schema_status_impact():
    """真实 schema 冒烟：purchase_order.status 应命中状态转换与视图。"""
    import yaml
    from pathlib import Path

    from meta.core.yaml_loader import parse_meta_object

    path = Path(__file__).resolve().parents[1] / "schemas" / "purchase_order.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    obj = parse_meta_object(data, "purchase_order.yaml")

    result = MetaImpactService(_FakeRegistry([obj])).analyze("purchase_order", "status")
    kinds = {ref['kind'] for ref in result['impacts'][0]['references']}
    assert "state_transition" in kinds
    assert "view" in kinds
