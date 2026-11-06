# -*- coding: utf-8 -*-
"""[P1-4 2026-11-06] schema 版本哈希覆盖非列级元数据。

此前 compute_meta_hash 只看表名 + 列定义 + hierarchy_level，导致只改
document（单据六件套）/ revision_policy 时被 detect_changes 判为「无变化」。
"""

from meta.core.models import (
    FieldType,
    MetaDocumentProfile,
    MetaField,
    MetaObject,
)
from meta.tools.sync_schema import compute_meta_hash


def _obj():
    return MetaObject(
        id='hash_doc_obj',
        name='哈希对象',
        table_name='hash_doc_objs',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER,
                      db_column='id'),
        ],
    )


def test_hash_is_stable_for_same_definition():
    assert compute_meta_hash(_obj()) == compute_meta_hash(_obj())


def test_hash_changes_when_document_declared():
    obj = _obj()
    baseline = compute_meta_hash(obj)

    obj.document_profile = MetaDocumentProfile(
        number_field='obj_no',
        business_date_field='biz_date',
        numbering={'scope_bo': 'hash_doc_objs'},
    )

    assert compute_meta_hash(obj) != baseline


def test_hash_changes_when_numbering_changes():
    obj = _obj()
    obj.document_profile = MetaDocumentProfile(
        number_field='obj_no',
        business_date_field='biz_date',
        numbering={'scope_bo': 'hash_doc_objs', 'fallback_sequence_code': 'A'},
    )
    baseline = compute_meta_hash(obj)

    obj.document_profile.numbering['fallback_sequence_code'] = 'B'

    assert compute_meta_hash(obj) != baseline


def test_hash_is_insensitive_to_mapping_key_order():
    first = _obj()
    first.document_profile = MetaDocumentProfile(
        number_field='obj_no',
        numbering={'scope_bo': 'x', 'fallback_sequence_code': 'S'},
    )
    second = _obj()
    second.document_profile = MetaDocumentProfile(
        number_field='obj_no',
        numbering={'fallback_sequence_code': 'S', 'scope_bo': 'x'},
    )

    assert compute_meta_hash(first) == compute_meta_hash(second)
