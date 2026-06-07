import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
关联校验器单元测试

测试 meta/core/association/validators.py 中导出函数的签名和逻辑：
- validate_source_target_existence(engine, context, src_id, tgt_type, tgt_id, assoc_meta)
- check_cardinality_constraint(engine, context, src_id, assoc_meta)
- get_current_association_count(context, src_id, assoc_meta, assoc_type)
- reassign_existing(context, src_id, assoc_meta, assoc_type)
- check_fk_required_before_unassign(context, src_meta, source_key)
- check_m2m_exists(context, through, source_key, target_key, src_id, tgt_id)
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from unittest.mock import MagicMock, Mock, patch
from meta.core.association.validators import (
    validate_source_target_existence,
    check_cardinality_constraint,
    get_current_association_count,
    reassign_existing,
    check_m2m_exists,
)


def _mock_context(object_type='user', action='assign', src_id=1, tgt_id=10, ds=None):
    ctx = MagicMock()
    ctx.object_type = object_type
    ctx.action = action
    ctx.params = {'src_id': src_id, 'tgt_id': tgt_id}
    ctx.data_source = ds or _mock_ds()
    ctx.user_id = 1
    return ctx


def _mock_ds(fetchone_returns=None):
    ds = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_returns
    ds.execute.return_value = cursor
    return ds


class TestValidateSourceTargetExistence:

    def test_source_not_found_returns_error(self):
        ds = _mock_ds(fetchone_returns=None)
        ctx = _mock_context(ds=ds)
        result = validate_source_target_existence(
            engine=MagicMock(), context=ctx,
            src_id=999, tgt_type='role', tgt_id=10,
            assoc_meta={'type': 'many_to_many'}
        )
        assert result is not None
        assert result.success is False
        assert '源记录不存在' in result.message

    def test_target_not_found_returns_error(self):
        cursor1 = MagicMock()
        cursor1.fetchone.return_value = {'id': 1}
        cursor2 = MagicMock()
        cursor2.fetchone.return_value = None
        ds = MagicMock()
        ds.execute.side_effect = [cursor1, cursor2]
        ctx = _mock_context(ds=ds)
        result = validate_source_target_existence(
            engine=MagicMock(), context=ctx,
            src_id=1, tgt_type='role', tgt_id=999,
            assoc_meta={'type': 'many_to_many'}
        )
        assert result is not None
        assert result.success is False
        assert '目标记录不存在' in result.message

    def test_both_exist_returns_none(self):
        ds = _mock_ds(fetchone_returns={'id': 1})
        ctx = _mock_context(ds=ds)
        result = validate_source_target_existence(
            engine=MagicMock(), context=ctx,
            src_id=1, tgt_type='role', tgt_id=10,
            assoc_meta={'type': 'many_to_many'}
        )
        assert result is None


class TestCheckCardinalityConstraint:

    def test_no_max_cardinality_always_allowed(self):
        ctx = _mock_context()
        result = check_cardinality_constraint(
            engine=MagicMock(), context=ctx,
            src_id=1, assoc_meta={'type': 'many_to_many'}
        )
        assert result is None

    def test_within_max_cardinality_allowed(self):
        ds = _mock_ds(fetchone_returns=(0,))
        ctx = _mock_context(ds=ds)
        result = check_cardinality_constraint(
            engine=MagicMock(), context=ctx,
            src_id=1, assoc_meta={'type': 'many_to_many', 'max_cardinality': 5}
        )
        assert result is None

    def test_exceeds_max_cardinality_raises(self):
        ctx = _mock_context()
        with patch('meta.core.association.validators.get_current_association_count', return_value=5) as mock_count:
            result = check_cardinality_constraint(
                engine=MagicMock(), context=ctx,
                src_id=1,
                assoc_meta={'type': 'many_to_many', 'max_cardinality': 5, 'name': 'roles'}
            )
        assert result is not None
        assert result.success is False
        assert '超出限制' in result.message

    def test_max_cardinality_1_with_reassign_clears_existing(self):
        ds = _mock_ds()
        ctx = _mock_context(ds=ds)
        result = check_cardinality_constraint(
            engine=MagicMock(), context=ctx,
            src_id=1,
            assoc_meta={
                'type': 'reference', 'max_cardinality': 1,
                'allow_reassign': True,
                'source_key': 'manager_id', 'name': 'manager'
            }
        )
        assert result is None


class TestGetCurrentAssociationCount:

    def test_many_to_many_count(self):
        ds = _mock_ds(fetchone_returns=(3,))
        ctx = _mock_context(ds=ds)
        count = get_current_association_count(
            context=ctx, src_id=1,
            assoc_meta={'through': 'role_permissions', 'source_key': 'user_id'},
            assoc_type='many_to_many'
        )
        assert count == 3

    def test_reference_count(self):
        ds = _mock_ds(fetchone_returns=(1,))
        ctx = _mock_context(ds=ds)
        count = get_current_association_count(
            context=ctx, src_id=1,
            assoc_meta={'source_key': 'manager_id'},
            assoc_type='reference'
        )
        assert count == 1

    def test_exception_returns_zero(self):
        ds = MagicMock()
        ds.execute.side_effect = Exception("DB error")
        ctx = _mock_context(ds=ds)
        count = get_current_association_count(
            context=ctx, src_id=1,
            assoc_meta={'source_key': 'manager_id'},
            assoc_type='reference'
        )
        assert count == 0


class TestReassignExisting:

    def test_reference_clears_old_value(self):
        ds = MagicMock()
        ctx = _mock_context(ds=ds)
        result = reassign_existing(
            context=ctx, src_id=1,
            assoc_meta={'source_key': 'manager_id', 'type': 'reference'},
            assoc_type='reference'
        )
        assert result is None
        ds.execute.assert_called()

    def test_reference_db_error_returns_failure(self):
        ds = MagicMock()
        ds.execute.side_effect = Exception("DB error")
        ctx = _mock_context(ds=ds)
        result = reassign_existing(
            context=ctx, src_id=1,
            assoc_meta={'source_key': 'manager_id'},
            assoc_type='reference'
        )
        assert result is not None
        assert result.success is False


class TestCheckM2mExists:

    def test_association_exists(self):
        ds = _mock_ds(fetchone_returns=1)
        ctx = _mock_context(ds=ds)
        exists = check_m2m_exists(
            context=ctx, through='role_permissions',
            source_key='user_id', target_key='role_id',
            src_id=1, tgt_id=10
        )
        assert exists is True

    def test_association_not_exists(self):
        ds = _mock_ds(fetchone_returns=None)
        ctx = _mock_context(ds=ds)
        exists = check_m2m_exists(
            context=ctx, through='role_permissions',
            source_key='user_id', target_key='role_id',
            src_id=1, tgt_id=10
        )
        assert exists is False

    def test_exception_returns_false(self):
        ds = MagicMock()
        ds.execute.side_effect = Exception("DB error")
        ctx = _mock_context(ds=ds)
        exists = check_m2m_exists(
            context=ctx, through='role_permissions',
            source_key='user_id', target_key='role_id',
            src_id=1, tgt_id=10
        )
        assert exists is False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
