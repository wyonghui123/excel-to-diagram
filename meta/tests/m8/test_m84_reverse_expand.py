"""M8 VP-4 Reverse Expand 测试。

[M8 2026-06-06] 反向关联展开端点测试。

覆盖：
- find_reverse_association 元数据查找
- one_to_many / reverse_many_to_many
- 关联不存在
- Blueprint 集成
- 元数据 None 兜底
"""
import pytest


class TestFindReverseAssociation:
    """M8 VP-4.1 元数据查找。"""

    def test_one_to_many(self):
        from meta.core.m8_utils import find_reverse_association
        class A:
            name = 'orders'
            type = 'one_to_many'
            target_entity = 'order'
            source_key = 'customer_id'
        class Meta:
            object_type = 'customer'
            associations = [A]
        result = find_reverse_association(Meta(), 'orders')
        assert result['target_entity'] == 'order'
        assert result['source_key'] == 'customer_id'
        assert result['type'] == 'one_to_many'

    def test_reverse_many_to_many(self):
        from meta.core.m8_utils import find_reverse_association
        class A:
            name = 'tags'
            type = 'reverse_many_to_many'
            target_entity = 'tag'
            source_key = 'tag_id'
            through = 'post_tags'
            join_key = 'post_id'
        class Meta:
            object_type = 'post'
            associations = [A]
        result = find_reverse_association(Meta(), 'tags')
        assert result['type'] == 'reverse_many_to_many'
        assert result['through'] == 'post_tags'
        assert result['join_key'] == 'post_id'

    def test_many_to_many_also_works(self):
        from meta.core.m8_utils import find_reverse_association
        class A:
            name = 'friends'
            type = 'many_to_many'
            target_entity = 'user'
        class Meta:
            object_type = 'user'
            associations = [A]
        result = find_reverse_association(Meta(), 'friends')
        assert result['type'] == 'many_to_many'

    def test_association_not_found(self):
        from meta.core.m8_utils import find_reverse_association
        class Meta:
            object_type = 'foo'
            associations = []
        result = find_reverse_association(Meta(), 'nonexistent')
        assert result is None

    def test_meta_is_none(self):
        from meta.core.m8_utils import find_reverse_association
        result = find_reverse_association(None, 'orders')
        assert result is None

    def test_meta_without_associations_attr(self):
        from meta.core.m8_utils import find_reverse_association
        class Meta:
            object_type = 'foo'
        result = find_reverse_association(Meta(), 'orders')
        assert result is None

    def test_target_entity_fallback_to_assoc_name(self):
        from meta.core.m8_utils import find_reverse_association
        class A:
            name = 'orders'
            type = 'one_to_many'
            target_entity = ''  # empty
            target_table = ''  # empty
        class Meta:
            object_type = 'foo'
            associations = [A]
        result = find_reverse_association(Meta(), 'orders')
        assert result['target_entity'] == 'orders'  # fallback

    def test_source_key_fallback(self):
        from meta.core.m8_utils import find_reverse_association
        class A:
            name = 'orders'
            type = 'one_to_many'
            target_entity = 'order'
            source_key = None  # fallback
        class Meta:
            object_type = 'customer'
            associations = [A]
        result = find_reverse_association(Meta(), 'orders')
        # 兜底用 <parent>_id
        assert result['source_key'] == 'customer_id'


class TestReverseExpandBlueprint:
    """M8 VP-4.2 Blueprint 集成。"""

    def test_reverse_blueprint_registered(self):
        from meta.api.m8_api import reverse_bp
        assert reverse_bp.name == 'm8_reverse'
        assert reverse_bp.url_prefix == '/api/v1'

    def test_register_m8_blueprints_function_exists(self):
        from meta.api.m8_api import register_m8_blueprints
        assert callable(register_m8_blueprints)


class TestReverseExpandIntegration:
    """M8 VP-4.3 端点集成（验证 Blueprint 注册到 app）。"""

    def test_all_four_blueprints_exportable(self):
        from meta.api.m8_api import (
            valuehelp_bp, query_dsl_bp, aggregate_bp, reverse_bp,
        )
        assert valuehelp_bp is not None
        assert query_dsl_bp is not None
        assert aggregate_bp is not None
        assert reverse_bp is not None

    def test_with_m8_method_in_app_builder(self):
        from meta.core.app_builder import ApplicationBuilder
        assert hasattr(ApplicationBuilder, 'with_m8')
