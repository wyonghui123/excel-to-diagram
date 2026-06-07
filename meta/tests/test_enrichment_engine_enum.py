import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
EnrichmentEngine 单元测试 - Phase X Enrichment 机制统一化

测试范围：
- enrich_one / enrich_batch: 公共 API
- _resolve_join_path / _resolve_join_path_batch: 内部 JOIN 解析
"""

import pytest
import tempfile
import os
from meta.core.enrichment_engine import EnrichmentEngine, init_enrichment_engine, enrich_record, enrich_records
from meta.core.redundancy_registry import RedundancyRegistry, JoinStep


def _get_test_db_path():
    """获取测试用临时数据库路径"""
    # 使用项目数据库作为测试数据源（只读操作）
    return os.path.join(os.path.dirname(__file__), '..', '..', 'architecture.db')


class TestEnrichmentEngineJoinPathResolution:
    """EnrichmentEngine JOIN 路径解析测试"""

    @pytest.fixture
    def engine(self):
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', path=_get_test_db_path())
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return EnrichmentEngine(ds, rr)

    def test_resolve_join_path_with_fixed_conditions(self, engine):
        """TC-EEJ-001: _resolve_join_path 支持固定条件"""
        join_step = JoinStep(
            table='enum_values',
            from_field='relation_code',
            to_field='code',
            select='name',
            fixed_conditions=[
                ('enum_type_id', '=', 'relation_type'),
                ('is_active', '=', 1),
            ]
        )

        result = engine._resolve_join_path([join_step], 'COMPOSITION')
        assert result is None or isinstance(result, str)

    def test_resolve_join_path_batch_with_fixed_conditions(self, engine):
        """TC-EEJ-002: _resolve_join_path_batch 支持固定条件"""
        join_step = JoinStep(
            table='enum_values',
            from_field='relation_code',
            to_field='code',
            select='name',
            fixed_conditions=[
                ('enum_type_id', '=', 'relation_type'),
                ('is_active', '=', 1),
            ]
        )

        result = engine._resolve_join_path_batch(
            [join_step],
            ['COMPOSITION', 'REFERENCE', 'INHERITANCE']
        )
        assert isinstance(result, dict)


class TestEnrichmentIntegration:
    """EnrichmentEngine 集成测试"""

    @pytest.fixture
    def engine(self):
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', path=_get_test_db_path())
        rr = RedundancyRegistry()
        rr.build_from_registry()
        return EnrichmentEngine(ds, rr)

    def test_registry_and_engine_work_together(self):
        """TC-EEI-001: RedundancyRegistry 和 EnrichmentEngine 协同工作"""
        from meta.core.enrichment_engine import init_enrichment_engine
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', path=_get_test_db_path())
        rr = RedundancyRegistry()
        rr.build_from_registry()
        engine = EnrichmentEngine(ds, rr)
        rel_reds = rr.get_object_redundancies('relationship')
        assert len(rel_reds) > 0

    def test_enum_and_regular_associations_coexist(self):
        """TC-EEI-002: enum 和普通关联共存"""
        rr = RedundancyRegistry()
        rr.build_from_registry()
        version_reds = rr.get_object_redundancies('version')
        assert 'product_name' in version_reds
        rel_reds = rr.get_object_redundancies('relationship')
        assert len(rel_reds) > 0

    def test_multiple_fixed_condition_values(self):
        """TC-EEI-003: 多个固定条件值都能正确处理"""
        rr = RedundancyRegistry()
        rr.build_from_registry()
        rel_reds = rr.get_object_redundancies('relationship')
        
        bo_join_fields = [
            (fid, rdef) for fid, rdef in rel_reds.items()
            if rdef.join_path and rdef.join_path[0].table == 'business_objects'
        ]
        assert len(bo_join_fields) > 0, "Should have business_objects JOIN fields"
        
        for field_id, red_def in bo_join_fields:
            for step in red_def.join_path:
                if step.table == 'business_objects':
                    assert step.fixed_conditions == [], \
                        f"{field_id} should not have fixed_conditions for BO join"


class TestEnrichmentAPI:
    """EnrichmentEngine 公共 API 测试"""

    def test_enrich_one_api(self):
        """TC-EEA-001: enrich_record API 存在"""
        result = enrich_record('relationship', {})
        assert isinstance(result, dict)

    def test_enrich_records_api(self):
        """TC-EEA-002: enrich_records API 存在"""
        result = enrich_records('relationship', [])
        assert isinstance(result, list)


class TestEnrichmentEngineInit:
    """EnrichmentEngine 初始化测试"""

    def test_init_enrichment_engine(self):
        """TC-EEI-001: 初始化函数存在"""
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', path=_get_test_db_path())
        engine = init_enrichment_engine(ds)
        assert engine is not None

    def test_engine_has_registry(self):
        """TC-EEI-002: Engine 有 registry 属性"""
        from meta.core.datasource import get_data_source
        ds = get_data_source('sqlite', path=_get_test_db_path())
        engine = init_enrichment_engine(ds)
        assert hasattr(engine, 'registry')
        assert engine.registry is not None
