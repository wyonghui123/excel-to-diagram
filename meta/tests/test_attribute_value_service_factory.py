# -*- coding: utf-8 -*-
"""T3.1 扩展属性值服务的对象派生（命名约定）。"""

from meta.services.attribute_value_service import (
    AttributeValueService,
    ItemAttributeValueService,
)
from meta.services.batch_attribute_value_service import BatchAttributeValueService


def test_party_keeps_existing_names():
    svc = AttributeValueService.for_object('party', data_source=object())
    assert svc.VALUE_TABLE == 'party_attribute_values'
    assert svc.OWNER_FIELD == 'party_id'


def test_new_object_follows_naming_convention():
    svc = AttributeValueService.for_object('purchase_order', data_source=object())
    assert svc.VALUE_TABLE == 'purchase_order_attribute_values'
    assert svc.OWNER_FIELD == 'purchase_order_id'


def test_specialized_subclasses_are_resolved():
    assert isinstance(
        AttributeValueService.for_object('item', data_source=object()),
        ItemAttributeValueService)
    assert isinstance(
        AttributeValueService.for_object('batch', data_source=object()),
        BatchAttributeValueService)


def test_derived_service_keeps_base_behaviour():
    svc = AttributeValueService.for_object('purchase_order', data_source=object())
    assert isinstance(svc, AttributeValueService)
    assert svc.DEFINITION_TABLE == 'attribute_definitions'
