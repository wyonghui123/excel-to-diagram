# -*- coding: utf-8 -*-
"""
测试 EnrichmentEngine 的 LRU+TTL 缓存改造 (FR-002 + FR-003)
"""
import time
import pytest
from unittest.mock import MagicMock

from meta.core.cache import LRUTTLCache, is_cache_disabled
from meta.core.enrichment_engine import EnrichmentEngine
from meta.core.redundancy_registry import (
    RedundancyRegistry,
    RedundancyDef,
    RedundancyType,
)


@pytest.fixture
def mock_ds():
    """mock 数据源：模拟 _resolve_simple_batch 的 SQL 返回"""
    ds = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [(1, "name_A"), (2, "name_B"), (3, "name_C")]
    cursor.fetchone.return_value = (1, "name_A")
    ds.execute.return_value = cursor
    return ds


@pytest.fixture
def simple_red_def():
    """构造一个简单 VIRTUAL 冗余定义"""
    return RedundancyDef(
        field_id="user_name",
        redundancy_type=RedundancyType.VIRTUAL,
        source_field="user_id",
        derived_table="user",
        derived_field="name",
    )


class TestLRUTTLCache:
    """LRUTTLCache 单元测试"""

    def test_basic_get_set(self):
        c = LRUTTLCache(max_size=3, ttl_seconds=60)
        c.set("k1", "v1")
        assert c.get("k1") == "v1"
        assert c.get("missing") is None
        assert c.misses == 1
        assert c.hits == 1

    def test_lru_eviction(self):
        c = LRUTTLCache(max_size=2, ttl_seconds=60)
        c.set("k1", "v1")
        c.set("k2", "v2")
        c.set("k3", "v3")  # 触发淘汰
        assert c.get("k1") is None  # 被淘汰
        assert c.get("k2") == "v2"
        assert c.get("k3") == "v3"
        assert c.evictions == 1

    def test_ttl_expiration(self):
        c = LRUTTLCache(max_size=10, ttl_seconds=1)
        c.set("k1", "v1")
        assert c.get("k1") == "v1"
        time.sleep(1.1)
        assert c.get("k1") is None
        assert c.expirations == 1

    def test_stats(self):
        c = LRUTTLCache(max_size=10, ttl_seconds=60)
        c.set("k1", "v1")
        c.get("k1")
        c.get("k1")
        c.get("missing")
        stats = c.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == round(2 / 3, 4)

    def test_clear(self):
        c = LRUTTLCache(max_size=10, ttl_seconds=60)
        c.set("k1", "v1")
        c.set("k2", "v2")
        c.clear()
        assert c.get("k1") is None
        assert c.stats()["size"] == 0


class TestEnrichmentEngineWithCache:
    """EnrichmentEngine 集成测试 - 使用 mock registry"""

    @pytest.fixture
    def engine(self, mock_ds):
        """构造一个带 mock registry 的 engine"""
        registry = MagicMock()
        # 空冗余：避免触发实际 SQL
        registry.get_object_redundancies.return_value = {}
        eng = EnrichmentEngine(mock_ds, registry)
        return eng

    def test_enrich_one_empty_record(self, engine):
        """enrich_one 空记录应直接返回（不调用 batch）"""
        result = engine.enrich_one("order", {})
        assert result == {}

    def test_enrich_one_no_redundancies(self, engine):
        """enrich_one 但无冗余定义：直接返回 record"""
        result = engine.enrich_one("order", {"user_id": 1})
        assert result == {"user_id": 1}

    def test_enrich_one_uses_batch_path(self, engine, mock_ds):
        """[FR-003] enrich_one 走 batch 路径（即使 record 非空）"""
        # 配置 registry 返回 1 个 virtual 冗余
        red_def = MagicMock()
        red_def.redundancy_type = RedundancyType.VIRTUAL
        red_def.source_field = "user_id"
        red_def.derived_table = "user"
        red_def.derived_field = "name"
        red_def.join_path = []
        engine.registry.get_object_redundancies.return_value = {"user_name": red_def}

        # mock SQL 返回：batch 路径用 fetchall，单条也走 batch 后取 [0]
        mock_ds.execute.return_value.fetchall.return_value = [(1, "Alice")]

        result = engine.enrich_one("order", {"user_id": 1, "amount": 100})
        # enrich_one 返回 1 条 dict
        assert "user_id" in result
        assert "amount" in result
        assert result["user_name"] == "Alice"

    def test_get_cache_stats_default(self, engine):
        """[IF-002] get_cache_stats 暴露给 /diagnostics"""
        stats = engine.get_cache_stats()
        assert "name" in stats
        assert "record" in stats
        # 默认情况下应该使用 LRU 缓存
        if isinstance(engine._name_cache, LRUTTLCache):
            assert "size" in stats["name"]

    def test_clear_cache(self, engine):
        """clear_cache 应清空所有缓存"""
        # 写入一些缓存
        if isinstance(engine._name_cache, LRUTTLCache):
            engine._name_cache.set("test_key", {"1": "A"})
        engine.clear_cache()
        stats = engine.get_cache_stats()
        if isinstance(engine._name_cache, LRUTTLCache):
            assert stats["name"]["size"] == 0

    def test_cache_disabled_via_env(self, mock_ds, monkeypatch):
        """[C7] META_ENRICHMENT_CACHE_DISABLED=1 时禁用缓存"""
        monkeypatch.setenv("META_ENRICHMENT_CACHE_DISABLED", "1")
        registry = MagicMock()
        engine = EnrichmentEngine(mock_ds, registry)
        # 此时 _name_cache 应该是 dict（不是 LRUTTLCache）
        assert not isinstance(engine._name_cache, LRUTTLCache)
        assert not isinstance(engine._record_cache, LRUTTLCache)
        # 清理环境变量
        monkeypatch.delenv("META_ENRICHMENT_CACHE_DISABLED")

    def test_cache_disabled_restore_after_unset(self, mock_ds, monkeypatch):
        """环境变量取消后，新建的 engine 应恢复 LRU 缓存"""
        # 先禁用
        monkeypatch.setenv("META_ENRICHMENT_CACHE_DISABLED", "1")
        eng1 = EnrichmentEngine(mock_ds, MagicMock())
        assert not isinstance(eng1._name_cache, LRUTTLCache)
        # 取消禁用
        monkeypatch.delenv("META_ENRICHMENT_CACHE_DISABLED")
        eng2 = EnrichmentEngine(mock_ds, MagicMock())
        # 新 engine 应使用 LRU
        assert isinstance(eng2._name_cache, LRUTTLCache)
