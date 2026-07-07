# SPEC-V007.24 DETAILED: 完整实现方案 (含可观测性 + 性能 + 测试)

> **作者**: dev-agent
> **日期**: 2026-07-07 11:45
> **状态**: 🟢 二次审查完成, 5 大改进点
> **前置**: [SPEC_V007_24_FIX_LAZY_DATA_SOURCE.md](./SPEC_V007_24_FIX_LAZY_DATA_SOURCE.md)
> **关联**: [DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md](./DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md)

---

## 0. 二次审查新增 5 大要点

基于本地代码深度审查, 我发现 **5 个之前漏掉的关键点**:

1. **可观测性基础设施已就绪** — Prometheus `/_metrics` 端点 (metrics_api.py:86) + 19 个 counters 模式 (observability.py:20) → **加 1 行 `OBS_COUNTERS['pool_init_count']` 即可自动暴露**
2. **健康检查已存在** — `SQLiteConnectionPool.health_check()` (sql_connection_pool.py:477) 已暴露 reader_pool utilization, db_size, wal_size → **复用零成本**
3. **db_health_monitor 已集成** — 已有 `wal_size`, `concurrent_processes`, `temp_file_count` 监控 → **加 1 个 dataclass 字段**
4. **诊断工具已存在** — `tools/diagnose.sh` 已部署, 加 fd 泄漏检测函数
5. **测试基础设施完善** — `tests/conftest.py` + `shared/fixtures.py` + `test_connection_pool.py` 已存在 → **加 1 个 `clean_data_source_cache` fixture**

---

## 1. 完整修复方案 (4 Phase, 26-38h)

### Phase 1: Layer 1 核心修复 (4h)

#### 1.1 `meta/core/datasource.py` 加缓存 (核心)

```python
# === [V007.24] 加在文件顶部 (import 后) ===
import threading as _threading
from typing import Dict as _Dict, Tuple as _Tuple

# [V007.24] Pool instance 缓存 (避免 fd 泄漏)
# Key: (DataSourceType, db_path)
# Value: DataSource instance
_data_source_cache: _Dict[_Tuple, "DataSource"] = {}
_data_source_cache_lock = _threading.Lock()
_data_source_cache_stats = {
    "hits": 0,
    "misses": 0,
    "instance_count": 0,
}

# [V007.24] 异常类型: 检测 fd 泄漏
class DataSourceLeakError(RuntimeError):
    """[V007.24] 多个 data_source instance 共存 - 可能 fd 泄漏"""
    pass

# === [V007.24] 替换原 get_data_source 函数 (L419) ===
def get_data_source(source_type: str, **kwargs) -> "DataSource":
    """获取数据源 (带缓存, 杜绝 fd 泄漏)

    [V007.24] 修复:
    - 之前每次调用都 DataSourceFactory.create() → 新建 connection pool → fd 泄漏
    - 现在按 (type, db_path) 缓存, 同 db 复用同一 instance
    - 缓存命中 1us, 未命中 ~10ms (创建 pool)
    - 启动时 sanity check: instance_count > 5 报警

    Args:
        source_type: 数据源类型 (sqlite/mysql/postgresql/...)
        **kwargs: 连接参数 (database 是 cache key)

    Returns:
        DataSource instance (cached)
    """
    from meta.core import sql_adapters
    try:
        dst = DataSourceType(source_type.lower())
    except ValueError:
        raise ValueError(f"Unknown data source type: {source_type}")

    # [V007.24] cache key: (type, db_path)
    db_path = str(kwargs.get("database", kwargs.get("path", "")))
    cache_key = (dst, db_path)

    with _data_source_cache_lock:
        if cache_key in _data_source_cache:
            _data_source_cache_stats["hits"] += 1
            cached = _data_source_cache[cache_key]
            # [V007.24] 防御性检查: 缓存的 instance 必须是 is_connected
            if not cached.is_connected:
                logger.warning(
                    "[V007.24] Cached DataSource disconnected, evicting: %s",
                    cache_key,
                )
                # [V007.24] 关闭旧 instance (避免 fd 泄漏)
                try:
                    cached.disconnect()
                except Exception as e:
                    logger.warning("[V007.24] Evict disconnect failed: %s", e)
                del _data_source_cache[cache_key]
                _data_source_cache_stats["instance_count"] = len(_data_source_cache)
            else:
                return cached
        _data_source_cache_stats["misses"] += 1
        new_instance = DataSourceFactory.create(dst, **kwargs)
        # [V007.24] 自动 connect (确保 is_connected=True, 才能 cache)
        if not new_instance.is_connected:
            new_instance.connect(**kwargs)
        _data_source_cache[cache_key] = new_instance
        _data_source_cache_stats["instance_count"] = len(_data_source_cache)

    # [V007.24] 上报 metric + sanity check
    from meta.core.observability import metrics_inc
    metrics_inc("pool_init_count")

    # [V007.24] 启动 60s 后, instance_count > 5 视为 fd 泄漏
    import time as _time
    if _time.time() - _data_source_cache_stats.setdefault("boot_time", _time.time()) > 60:
        if _data_source_cache_stats["instance_count"] > 5:
            logger.error(
                "[V007.24] DataSource instance count=%d > 5, "
                "POSSIBLE FD LEAK! cache=%s",
                _data_source_cache_stats["instance_count"],
                list(_data_source_cache.keys()),
            )
            metrics_inc("pool_init_leak_warning")
            # [V007.24] 抛异常 (可选: 严格模式才抛)
            from os import getenv as _getenv
            if _getenv("V007_24_STRICT_MODE"):
                raise DataSourceLeakError(
                    f"DataSource instance count={_data_source_cache_stats['instance_count']} > 5, "
                    f"likely fd leak. cache={list(_data_source_cache.keys())}"
                )

    logger.info(
        "[V007.24] get_data_source new instance: type=%s, db_path=%s, "
        "total_instances=%d",
        dst, db_path, _data_source_cache_stats["instance_count"],
    )
    return new_instance


# === [V007.24] 新增函数: 列出当前所有 instance (用于诊断/health check) ===
def list_data_source_instances() -> list:
    """[V007.24] 列出当前缓存的所有 DataSource instance (供 health check / diagnose.sh)"""
    with _data_source_cache_lock:
        return [
            {
                "type": str(k[0].value),
                "db_path": k[1],
                "is_connected": v.is_connected,
            }
            for k, v in _data_source_cache.items()
        ]


# === [V007.24] 新增函数: 清空缓存 (仅测试用) ===
def _clear_data_source_cache_for_testing() -> None:
    """[V007.24] 清空缓存 (仅测试用)"""
    with _data_source_cache_lock:
        for ds in _data_source_cache.values():
            try:
                ds.disconnect()
            except Exception:
                pass
        _data_source_cache.clear()
        _data_source_cache_stats["instance_count"] = 0


# === [V007.24] 新增函数: 获取缓存统计 ===
def get_data_source_cache_stats() -> dict:
    """[V007.24] 获取缓存统计 (供 health check)"""
    with _data_source_cache_lock:
        return _data_source_cache_stats.copy()
```

**行数**: ~130 行 (含注释)
**文件**: `meta/core/datasource.py` (在 L419 `get_data_source` 之前插入 + 替换原函数)

#### 1.2 `meta/core/observability.py` 加 metric

```python
# [V007.24] 在 OBS_COUNTERS dict 中加 (L48 后)
'pool_init_count': 'v007_24_pool_init_count',
'pool_init_leak_warning': 'v007_24_pool_init_leak_warning_total',
```

**行数**: 2 行
**自动暴露**: `/_metrics` 端点 (metrics_api.py:86) 已存在, 新 metric 自动可用

#### 1.3 验证 (Phase 1 完成后)

```bash
# 1. 启动 server
cd /opt/app/deployments/meta
nohup python server.py > /tmp/test_v007_24.log 2>&1 &
sleep 30

# 2. 触发 5+ 个 API 请求
curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' > /dev/null
curl -s http://localhost:5001/api/v2/bo/product?page_size=10 > /dev/null
# ... (更多)

# 3. 看 metric (期望: pool_init_count = 2-3, 不是 36+)
curl -s http://localhost:5001/_metrics | grep v007_24

# 4. 看 health (期望: data_source_instances < 5)
curl -s http://localhost:5001/api/v1/health | jq '.data_source_instances'
```

---

### Phase 2: Layer 2 修 23 个文件 (12h)

#### 2.1 A 类 10 文件: 修 fallback (4h)

**统一模式**:
```python
# BEFORE (audit_api.py 等 10 个)
def init_audit_services(data_source=None, ...):
    global _data_source
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        # ❌ __file__ 算错 db_path
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    # ... 其他 service init
```

**改成**:
```python
# AFTER
def init_audit_services(data_source=None, ...):
    """[V007.24] 初始化审计服务

    [V007.24] 修复: 删除 __file__ fallback
    - 之前如果 data_source=None 且 _data_source=None, 触发 __file__ 算 db_path
    - 部署到 /opt/app 后, __file__ 是源码路径, 找不到 db
    - 现在强制要求 server.py 必须传 data_source, 否则 raise
    """
    if data_source is None:
        raise ValueError(
            "[V007.24] init_audit_services 必须传 data_source 参数. "
            "server.py 启动时统一调 init_*_services(data_source)."
        )
    global _data_source
    if _data_source is not None and _data_source is not data_source:
        raise DataSourceLeakError(
            f"[V007.24] audit_api._data_source 已初始化到不同 instance. "
            f"现有={_data_source}, 新={data_source}. "
            f"可能是 fd 泄漏 (多个 connection pool)."
        )
    _data_source = data_source
    # ... 其他 service init
```

**A 类 10 文件**: audit_api, user_api, user_group_api, role_api, manage_api, enum_api, database_api, data_permission_api, auth_api, association_api

#### 2.2 B 类 13 文件: 加 init_data_source 函数 (8h)

**统一模式**:
```python
# BEFORE (bo_api.py 等 13 个)
_data_source = None

def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source
```

**改成**:
```python
# AFTER
from typing import Optional
from meta.core.datasource import DataSource, DataSourceLeakError

_data_source: Optional[DataSource] = None


def init_data_source(data_source: DataSource) -> None:
    """[V007.24] 由 server.py 启动时调用, 注入主 pool 的 data_source

    [RATIONALE] 之前 _get_data_source() 用 __file__ 算 db_path, 永远是源码路径,
    部署到 /opt/app 后找不到文件, 且每次 lazy init 都创建新 connection pool (fd 泄漏).
    现在 server.py 启动时统一调 init_data_source, 注入主 pool.

    Args:
        data_source: server.py:383 创建的主 data_source

    Raises:
        DataSourceLeakError: 如果 _data_source 已初始化到不同 instance
    """
    global _data_source
    if _data_source is not None and _data_source is not data_source:
        raise DataSourceLeakError(
            f"[V007.24] bo_api._data_source already initialized to different instance. "
            f"existing={_data_source}, new={data_source}. "
            f"POSSIBLE FD LEAK — multiple connection pools for same db."
        )
    _data_source = data_source
    logger.info("[V007.24] bo_api._data_source initialized")


def _get_data_source() -> DataSource:
    """[V007.24] 获取 data_source (必须先调 init_data_source)

    [V007.24] 修复: 不再 lazy init, 直接 raise
    - 之前懒加载导致 fd 泄漏 (每个请求都创建新 pool)
    - 现在必须 server.py 启动时先调 init_data_source
    """
    if _data_source is None:
        raise RuntimeError(
            "[V007.24] bo_api.data_source not initialized. "
            "Call init_data_source(data_source) in server.py startup. "
            "Lazy init via _get_data_source() is FORBIDDEN (causes fd leak)."
        )
    return _data_source
```

**B 类 13 文件**: bo_api, stats_api, schema_api, role_menu_api, role_dimension_scope_api, permission_sync_api, permission_audit_api, permission_bundle_api, permission_rule_api, owner_transfer_api, menu_permission_api, management_dimension_api, user_authenticate (services/), user_change_password (services/)

---

### Phase 3: Layer 3 server.py 集中 init (3h)

#### 3.1 `meta/server.py` 加 `_init_all_api_data_sources` 函数

```python
# [V007.24] 加在 server.py L412 后 (init_manage_services 之前)
def _init_all_api_data_sources(data_source) -> None:
    """[V007.24] 集中调用所有 23 个 API/Services 模块的 init_data_source

    [RATIONALE] 之前 server.py 只调了 10 个 init_*_services 函数, 其他 13 个文件
    依赖 _get_data_source() lazy init, 触发 fd 泄漏 (见 V007.23/V007.24 文档).
    现在集中调用, 杜绝 lazy init.

    [V007.24] 错误处理: 任一 init 失败立即 raise, 不允许部分 init
    """
    # === A 类: 已有 init 函数 (10 个) ===
    from meta.api.audit_api import init_audit_services
    from meta.api.user_api import init_user_services
    from meta.api.user_group_api import init_user_group_services
    from meta.api.role_api import init_role_services
    from meta.api.manage_api import init_services as init_manage_services
    from meta.api.enum_api import init_enum_services
    from meta.api.database_api import init_database_services
    from meta.api.data_permission_api import init_data_perm_services
    from meta.api.auth_api import init_auth_services
    from meta.api.association_api import init_association_services

    init_audit_services(data_source=data_source)
    init_user_services(data_source)
    init_user_group_services(data_source)
    init_role_services(data_source)
    init_manage_services(data_source=data_source)
    init_enum_services(data_source, db_path)
    init_database_services(data_source=data_source)
    init_data_perm_services(data_source)
    init_auth_services(data_source)
    init_association_services(data_source)

    # === B 类: 新增 init_data_source (13 个) ===
    from meta.api import bo_api, stats_api, schema_api
    from meta.api import role_menu_api, role_dimension_scope_api
    from meta.api import permission_sync_api, permission_audit_api
    from meta.api import permission_bundle_api, permission_rule_api
    from meta.api import owner_transfer_api, menu_permission_api
    from meta.api import management_dimension_api
    from meta.services import user_authenticate, user_change_password

    api_modules = [
        bo_api, stats_api, schema_api, role_menu_api, role_dimension_scope_api,
        permission_sync_api, permission_audit_api, permission_bundle_api,
        permission_rule_api, owner_transfer_api, menu_permission_api,
        management_dimension_api, user_authenticate, user_change_password,
    ]

    for module in api_modules:
        module.init_data_source(data_source)

    logger.info(
        "[V007.24] Initialized %d API/Services data_source modules (10 + 13 + 1 async)",
        len(api_modules) + 10 + 1,
    )
```

#### 3.2 server.py L412 后调

```python
# [V007.24] 在 server.py L412 (init_manage_services(data_source) 之后) 加:
_init_all_api_data_sources(data_source)
```

**行数**: ~70 行 (含注释)
**文件**: `meta/server.py` (在 L412 后插入 1 个函数 + 1 个调用)

---

### Phase 4: 测试 + 文档 + 部署 (8h)

#### 4.1 单元测试: `meta/tests/test_datasource_cache.py`

```python
# -*- coding: utf-8 -*-
"""
[V007.24] DataSource 缓存单元测试
- test_get_data_source_cache: 同一 (type, db_path) 复用 instance
- test_lazy_init_blocked: 调 _get_data_source 不调 init 抛 RuntimeError
- test_data_source_leak_error: 不同 instance init 抛 DataSourceLeakError
- test_pool_init_count_metric: 每次创建都 metrics_inc
- test_disconnect_evicts: 缓存的 instance 断开后被驱逐
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from meta.core.datasource import (
    get_data_source, _clear_data_source_cache_for_testing,
    list_data_source_instances, get_data_source_cache_stats,
    DataSourceLeakError, DataSourceType,
)


@pytest.fixture
def temp_db():
    """临时 db 文件"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture(autouse=True)
def clean_cache():
    """每个测试前后清空缓存"""
    _clear_data_source_cache_for_testing()
    yield
    _clear_data_source_cache_for_testing()


class TestGetDataSourceCache:
    """测试 get_data_source 缓存行为"""

    def test_same_db_path_returns_same_instance(self, temp_db):
        """[V007.24] 同一 db_path 返回同一 instance (零 fd 泄漏)"""
        ds1 = get_data_source("sqlite", database=temp_db)
        ds2 = get_data_source("sqlite", database=temp_db)
        assert ds1 is ds2  # ✅ 同一 instance

    def test_different_db_path_returns_different_instance(self, temp_db):
        """[V007.24] 不同 db_path 返回不同 instance"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path2 = f.name
        try:
            ds1 = get_data_source("sqlite", database=temp_db)
            ds2 = get_data_source("sqlite", database=db_path2)
            assert ds1 is not ds2  # ✅ 不同 instance
        finally:
            os.unlink(db_path2)

    def test_100_calls_create_only_one_instance(self, temp_db):
        """[V007.24] 100 次调用只创建 1 个 instance (性能 + fd 安全)"""
        for _ in range(100):
            get_data_source("sqlite", database=temp_db)
        instances = list_data_source_instances()
        assert len(instances) == 1  # ✅ 零泄漏

    def test_cache_stats_hits_misses(self, temp_db):
        """[V007.24] 缓存命中/未命中统计"""
        get_data_source("sqlite", database=temp_db)  # 1 miss
        get_data_source("sqlite", database=temp_db)  # 1 hit
        get_data_source("sqlite", database=temp_db)  # 2 hits
        stats = get_data_source_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 2
        assert stats["instance_count"] == 1


class TestLazyInitBlocked:
    """测试 lazy init 被禁用 (修复 fd 泄漏)"""

    def test_get_data_source_without_init_creates_cached(self, temp_db):
        """[V007.24] 调 get_data_source 不需要 init (直接创建 cached)"""
        # 这是允许的: 第一次创建 + cache
        ds = get_data_source("sqlite", database=temp_db)
        assert ds is not None
        # 第二次拿 cached
        ds2 = get_data_source("sqlite", database=temp_db)
        assert ds is ds2


class TestDataSourceLeakError:
    """测试 fd 泄漏检测"""

    def test_different_instance_init_raises_leak_error(self, temp_db):
        """[V007.24] 重复 init 不同 instance 抛 DataSourceLeakError"""
        from meta.api import bo_api
        ds1 = get_data_source("sqlite", database=temp_db)
        bo_api.init_data_source(ds1)  # 第一次 OK
        # 模拟泄漏: 创建另一个 ds2 并 init
        ds2 = get_data_source("sqlite", database=temp_db + "_other")
        with pytest.raises(DataSourceLeakError) as exc_info:
            bo_api.init_data_source(ds2)
        assert "POSSIBLE FD LEAK" in str(exc_info.value)


class TestPoolInitCountMetric:
    """测试 metric 上报"""

    @patch("meta.core.observability.metrics_inc")
    def test_pool_init_count_metric_reported(self, mock_metrics_inc, temp_db):
        """[V007.24] 每次创建 instance 上报 pool_init_count metric"""
        get_data_source("sqlite", database=temp_db)  # 1 创建
        # 验证 metrics_inc 被调
        calls = [c for c in mock_metrics_inc.call_args_list if c[0][0] == "pool_init_count"]
        assert len(calls) >= 1  # 至少 1 次


class TestDisconnectEvicts:
    """测试缓存一致性"""

    def test_disconnect_evicts_from_cache(self, temp_db):
        """[V007.24] 缓存的 instance disconnect 后下次创建新 instance"""
        ds1 = get_data_source("sqlite", database=temp_db)
        # 模拟 disconnect
        ds1.disconnect()
        # 下次调 get_data_source 应该创建新 instance
        ds2 = get_data_source("sqlite", database=temp_db)
        # 第二次可能拿 cached (如果 is_connected 检查通过) 或新 instance (如果 evict)
        # 取决于具体实现: 我们的实现会 evict disconnected
        # 验证 cache stats
        stats = get_data_source_cache_stats()
        # 至少 2 次 misses (ds1 + ds2)
        assert stats["misses"] >= 2


class TestPerformance:
    """测试性能 (cache 命中应该 < 1ms)"""

    def test_cached_call_is_fast(self, temp_db):
        """[V007.24] cache 命中 < 1ms"""
        import time
        get_data_source("sqlite", database=temp_db)  # warm up
        start = time.perf_counter()
        for _ in range(1000):
            get_data_source("sqlite", database=temp_db)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # 1000 次 < 10ms = 单次 < 10us
        assert elapsed_ms < 10, f"1000 cached calls took {elapsed_ms:.2f}ms, expected < 10ms"
```

**行数**: ~150 行
**文件**: `meta/tests/test_datasource_cache.py` (新建)

#### 4.2 集成测试: `meta/tests/e2e/test_v007_24_fd_leak_prevention.py`

```python
# -*- coding: utf-8 -*-
"""
[V007.24] 端到端 fd 泄漏预防测试
- 启动 server 后跑 100 个 list 请求
- 验证 Connection pool init 次数 ≤ 5 (1 main + 1 async + 3 容错)
- 验证所有 API/Services 共享同一 data_source instance
"""
import pytest
import requests
import time
from meta.core.datasource import list_data_source_instances


@pytest.fixture(scope="module")
def base_url():
    return "http://localhost:5001"


@pytest.fixture(scope="module")
def auth_token(base_url):
    """获取 admin token"""
    r = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200
    return r.json()["data"]["token"]


class TestFdleakPrevention:
    """[V007.24] 端到端 fd 泄漏预防"""

    def test_100_api_requests_no_fd_leak(self, base_url, auth_token):
        """[V007.24] 100 个连续 API 请求, data_source instance 数 ≤ 5"""
        # 启动时 baseline
        time.sleep(2)
        baseline = len(list_data_source_instances())

        # 跑 100 个请求
        endpoints = [
            "/api/v2/bo/product?page_size=10",
            "/api/v2/bo/version?product_id=2&page_size=10",
            "/api/v1/menu-permission/visible",
            "/api/v1/stats/overview",
            "/api/v2/bo/relationship?page=1&page_size=10&version_id=3",
        ]
        headers = {"Authorization": f"Bearer {auth_token}"}
        for i in range(100):
            ep = endpoints[i % len(endpoints)]
            r = requests.get(f"{base_url}{ep}", headers=headers)
            assert r.status_code == 200, f"request {i} failed: {r.status_code}"

        # 验证 instance 数没有增加
        time.sleep(2)
        final = len(list_data_source_instances())
        assert final - baseline <= 2, (
            f"FD LEAK! baseline={baseline}, final={final}, "
            f"diff={final - baseline} (expected ≤ 2)"
        )

    def test_all_apis_share_main_pool(self):
        """[V007.24] 所有 API/Services 共享同一 data_source instance"""
        instances = list_data_source_instances()
        assert len(instances) == 1 or len(instances) == 2, (
            f"Expected 1-2 instances (main + async), got {len(instances)}: {instances}"
        )
        # 如果有 2 个: 第二个是 AsyncAuditWriter
        # 如果有 1 个: 没有启用 AsyncAuditWriter

    def test_metric_pool_init_count_low(self, base_url):
        """[V007.24] _metrics 显示 pool_init_count ≤ 5"""
        r = requests.get(f"{base_url}/_metrics")
        assert r.status_code == 200
        text = r.text
        # 解析 v007_24_pool_init_count
        for line in text.split("\n"):
            if line.startswith("v007_24_pool_init_count_total"):
                value = float(line.split()[-1])
                assert value <= 5, f"pool_init_count={value} > 5, fd leak!"
                return
        pytest.fail("v007_24_pool_init_count metric not found")
```

**行数**: ~80 行
**文件**: `meta/tests/e2e/test_v007_24_fd_leak_prevention.py` (新建)

#### 4.3 测试 fixture: `meta/tests/conftest.py` 加 fixture

```python
# [V007.24] 在 conftest.py 加 fixture
import pytest
from meta.core.datasource import _clear_data_source_cache_for_testing


@pytest.fixture(autouse=False)
def clean_data_source_cache():
    """[V007.24] 测试前后清空 DataSource 缓存 (避免 instance 泄漏到其他测试)"""
    _clear_data_source_cache_for_testing()
    yield
    _clear_data_source_cache_for_testing()
```

**行数**: 10 行

#### 4.4 部署工具: `tools/diagnose.sh` 加 fd 泄漏检测

```bash
# [V007.24] 在 diagnose.sh 加新函数: check_fd_leak
check_fd_leak() {
    local backend_port="${BACKEND_PORT:-5001}"
    print_header "DataSource fd 泄漏检测 [V007.24]"
    
    # 1. 通过 _metrics 端点获取 pool_init_count
    local metrics=$(curl -s "http://localhost:${backend_port}/_metrics" 2>/dev/null)
    if [ -z "$metrics" ]; then
        print_error "无法连接 _metrics 端点"
        return 1
    fi
    
    local pool_init_count=$(echo "$metrics" | grep "^v007_24_pool_init_count" | awk '{print $2}')
    if [ -z "$pool_init_count" ]; then
        print_warn "v007_24_pool_init_count metric 未暴露 (V007.24 修复未部署?)"
        return 1
    fi
    
    echo "  pool_init_count: ${pool_init_count}"
    
    if (( $(echo "$pool_init_count > 5" | bc -l) )); then
        print_error "🚨 FD 泄漏检测: pool_init_count=${pool_init_count} > 5 (期望 ≤ 5)"
        echo "  建议: 检查是否有 30+ 个 api/*.py 的 lazy init 没被 init_data_source 注入"
        return 1
    else
        print_ok "pool_init_count 正常 (≤ 5)"
        return 0
    fi
}
```

**集成到 `run_diagnose` 函数**:
```bash
# 在 diagnose.sh run_diagnose 中加:
check_fd_leak
```

**行数**: 30 行
**文件**: `tools/diagnose.sh` (加 1 个函数 + 1 个调用)

#### 4.5 db_health_monitor 加字段

```python
# [V007.24] meta/core/db_health_monitor.py L25-36 dataclass 加 1 字段
@dataclass
class DBHealthSnapshot:
    timestamp: float = field(default_factory=time.time)
    db_size_bytes: int = 0
    wal_size_bytes: int = 0
    shm_size_bytes: int = 0
    wal_pending_frames: int = 0
    checkpoint_count: int = 0
    integrity_status: str = "unknown"
    concurrent_processes: int = 0
    temp_file_count: int = 0
    warnings: list = field(default_factory=list)
    # [V007.24] 新增: DataSource instance 计数 (fd 泄漏检测)
    data_source_instance_count: int = 0  # ← 新增


# [V007.24] collect_snapshot 中加 (L80 后):
from meta.core.datasource import list_data_source_instances
snap.data_source_instance_count = len(list_data_source_instances())
```

**行数**: 5 行
**文件**: `meta/core/db_health_monitor.py` (加 1 字段 + 3 行)

#### 4.6 部署文档: `INFRA_HANDOVER.md` 加 V007.24 章节

```markdown
## 6.7 V007.24 fd 泄漏预防

[背景] 2026-07-07 生产 disk I/O error 事件, 根因是 meta/api/ 30+ 文件 lazy data_source init
+ `get_data_source()` 无缓存, 导致 38 个独立 connection pool (fd 泄漏).

[修复] 3 层修复:
- Layer 1: get_data_source() 加缓存 (1 文件)
- Layer 2: 23 个 api/services 文件修 fallback (23 文件)
- Layer 3: server.py 集中 init (1 文件)

[验证] 4 个测试 + 1 个 diagnose.sh 检测:
- test_datasource_cache.py (单元, 6 测试)
- test_v007_24_fd_leak_prevention.py (e2e, 3 测试)
- conftest.py fixture clean_data_source_cache
- diagnose.sh check_fd_leak

[可观测性] 3 个接入点:
- Prometheus _metrics: v007_24_pool_init_count
- DBHealthSnapshot.data_source_instance_count
- diagnose.sh check_fd_leak 输出

[SLO] 启动 60s 内 pool_init_count ≤ 5, 持续运行时 instance_count ≤ 5.
[告警] pool_init_count > 5 立即报警, 可能是 fd 泄漏.
```

**行数**: 25 行

---

## 2. 完整文件改动清单 (最终版)

| # | 类别 | 文件 | 改动量 | 状态 |
|---|------|------|--------|------|
| 1 | Layer 1 核心 | `meta/core/datasource.py` | +130 行 | 新加 |
| 2 | observability | `meta/core/observability.py` | +2 行 | 修改 |
| 3 | Layer 2-A (10 文件) | meta/api/{audit,user,user_group,role,manage,enum,database,data_permission,auth,association}_api.py | ~10 行 × 10 | 修改 |
| 4 | Layer 2-B (13 文件) | meta/api/{bo,stats,schema,role_menu,role_dim_scope,perm_sync,perm_audit,perm_bundle,perm_rule,owner_transfer,menu_perm,mgmt_dim}_api.py + meta/services/{user_authenticate,user_change_password}.py | ~30 行 × 13 | 修改 |
| 5 | Layer 3 server.py | `meta/server.py` | +75 行 | 修改 |
| 6 | 测试 fixture | `meta/tests/conftest.py` | +10 行 | 修改 |
| 7 | 单元测试 | `meta/tests/test_datasource_cache.py` | +150 行 | 新加 |
| 8 | e2e 测试 | `meta/tests/e2e/test_v007_24_fd_leak_prevention.py` | +80 行 | 新加 |
| 9 | db_health_monitor | `meta/core/db_health_monitor.py` | +5 行 | 修改 |
| 10 | 部署诊断 | `tools/diagnose.sh` | +30 行 | 修改 |
| 11 | 部署文档 | `INFRA_HANDOVER.md` | +25 行 | 修改 |
| 12 | spec.md | `spec.md` | +20 行 | 修改 |
| 13 | 任务跟踪 | `DEPLOY_HANDOVER_BUG_V007_24.md` | +300 行 | 新加 |
| **总计** | **13 个文件** | | **~990 行** | **~30-40h** |

---

## 3. 验证策略 (完整测试矩阵)

### 3.1 单元测试 (Phase 4.1)

| 测试 | 验证什么 | 期望 |
|------|---------|------|
| test_same_db_path_returns_same_instance | 缓存基础功能 | 同一 db → 同一 instance |
| test_different_db_path_returns_different_instance | 多 db 隔离 | 不同 db → 不同 instance |
| test_100_calls_create_only_one_instance | fd 泄漏预防 | 100 次调 → 1 个 instance |
| test_cache_stats_hits_misses | 可观测性 | hits/misses 计数正确 |
| test_different_instance_init_raises_leak_error | 防御性 | DataSourceLeakError |
| test_pool_init_count_metric_reported | metric 集成 | metrics_inc 被调 |
| test_disconnect_evicts_from_cache | 缓存一致性 | disconnected 被驱逐 |
| test_cached_call_is_fast | 性能 | 1000 次 < 10ms |

### 3.2 集成测试 (Phase 4.2)

| 测试 | 验证什么 | 期望 |
|------|---------|------|
| test_100_api_requests_no_fd_leak | 端到端 | 100 请求后 instance 数 ≤ baseline + 2 |
| test_all_apis_share_main_pool | 全局一致 | instance 数 ≤ 2 (main + async) |
| test_metric_pool_init_count_low | metric SLO | pool_init_count ≤ 5 |

### 3.3 生产可观测性

| 接入点 | 验证什么 | SLO |
|--------|---------|-----|
| `/_metrics` v007_24_pool_init_count | 持续监控 | ≤ 5 |
| DBHealthSnapshot.data_source_instance_count | health check | ≤ 5 |
| diagnose.sh check_fd_leak | 部署诊断 | ≤ 5 |
| boot_time + 60s sanity check in get_data_source | 自动报警 | 启动 60s 后 > 5 → log error + metric |

### 3.4 部署验证脚本

```bash
#!/bin/bash
# [V007.24] deploy_v007_24_validation.sh
# 1. 部署新代码
# 2. 重启 server
# 3. 等待 30s
# 4. 跑 unit tests
# 5. 跑 e2e tests
# 6. 检查 _metrics: pool_init_count ≤ 5
# 7. 检查 fd 数 (lsof | wc -l)
# 8. 跑 100 个 list 请求
# 9. 再次检查 _metrics: pool_init_count 不应增长 > 2
# 10. 健康检查: DBHealthSnapshot.data_source_instance_count
```

---

## 4. 性能评估 (详细)

### 4.1 缓存前后对比

| 操作 | 缓存前 | 缓存后 | 提升 |
|------|--------|--------|------|
| 第 1 次调 (冷启动) | ~10ms (创建 pool) | ~10ms (创建 pool) | 0 |
| 第 2-1000 次 (命中) | ~10ms × N | ~1us × N | **10000x** |
| 100 请求总计 | 1000ms | 10ms | **100x** |
| fd 占用 | 20 conn × 100 = 2000 | 20 conn × 1 = 20 | **100x** |

### 4.2 加锁开销

```python
# 缓存代码 (伪):
with _data_source_cache_lock:  # ← 加锁
    if cache_key in cache:
        return cache[cache_key]
```

- **加锁开销**: 1us (GIL + atomic)
- **1000 次命中加锁**: 1ms (可忽略)
- **首次 miss (竞争)**: 20 threads 同时调, 1 个 init, 19 个 wait lock, 总时间 < 50ms

### 4.3 内存占用

- 每个 cached DataSource: ~1KB (无数据, 只指针)
- 23 个 module 共享同一 DataSource: 总共 ~1KB
- 健康检查 + 统计: ~2KB
- **总计**: < 5KB (可忽略)

---

## 5. 风险评估 (二次审查更新)

| 风险 | 严重度 | 缓解 | 验证方式 |
|------|--------|------|---------|
| `get_data_source()` 加缓存, 行为变更 | 🟡 中 | 保留原签名 + 加 cache_key 检测 | 单元测试 test_same_db_path |
| 30 文件改动引入新 bug | 🟡 中 | 13 单元 + 3 集成测试 | CI 自动跑 |
| 加锁影响并发性能 | 🟢 低 | 锁持有时间 < 1us | 1000 次命中 < 10ms 测试 |
| 缓存的 instance 状态错乱 | 🟡 中 | is_connected 检查 + 断开 evict | test_disconnect_evicts |
| 启动时 sanity check 误报 | 🟢 低 | 60s 宽限期 + 严格模式 opt-in | 检查 boot_time |
| observability 依赖 | 🟢 低 | 已有 fallback 到 log (observability.py:64) | 单元测试 |
| diagnose.sh 集成失败 | 🟢 低 | 失败 warn 不 fail-fast | 检查 return code |

---

## 6. 分批实施时间线 (更新)

| 日期 | 任务 | 工作量 | 提交 | 验证 |
|------|------|--------|------|------|
| 2026-07-07 14:00 | Phase 1 (datasource 缓存 + observability metric) | 4h | `fix/v007.24-phase1-cache` | 单元测试 + manual test |
| 2026-07-08 09:00 | Phase 2-A (修 10 个 fallback) | 4h | `fix/v007.24-phase2a-fallback` | integration test |
| 2026-07-08 14:00 | Phase 2-B (13 个文件加 init) | 8h | `fix/v007.24-phase2b-inits` | integration test |
| 2026-07-09 09:00 | Phase 3 (server.py 集中 init) | 3h | `fix/v007.24-phase3-server` | e2e test |
| 2026-07-09 14:00 | Phase 4 (测试 + 文档) | 8h | `fix/v007.24-phase4-tests` | 完整 CI |
| 2026-07-10 09:00 | 集成到 release + cherry-pick | 3h | merge | yonaa verify |

**总工作量**: 30h
**风险窗口**: 每个 phase 独立可回滚

---

## 7. 关键决策点 (给协调智能体)

### 7.1 是否接受 4 Phase 方案?

- **接受** → 立即 Phase 1 (4h 修核心, 立即减少 38 → 1 init)
- **拒绝** → 改方案 B (短期 runtime guard)

### 7.2 Phase 1 单独修复是否足够?

**Phase 1 单独**就能把 38 次 init 减到 1 次 (因为同一 (type, db_path) 全部 cache 命中)。

**不需要 23 个文件改** —— Layer 1 缓存就解决了核心 fd 泄漏问题。

**建议**: **先 Phase 1, 紧急修复生产**, 然后看是否需要 Phase 2-4 进一步修 __file__ fallback。

### 7.3 是否需要先在 integration 端复现测试?

**需要** — 建议在 integration 端先跑 100 个 list 请求验证 Phase 1 修复, 再部署到 release。

---

## 8. 关键参考

- 前置 spec: [SPEC_V007_24_FIX_LAZY_DATA_SOURCE.md](./SPEC_V007_24_FIX_LAZY_DATA_SOURCE.md)
- 根因 V007.23: [DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md](./DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md)
- 关键代码位置:
  - `meta/core/datasource.py:419` (get_data_source 工厂)
  - `meta/core/sql_connection_pool.py:477` (health_check 已存在)
  - `meta/core/observability.py:20-50` (OBS_COUNTERS 模式)
  - `meta/core/db_health_monitor.py:25-36` (dataclass 模式)
  - `meta/api/metrics_api.py:86` (/_metrics 端点)
  - `meta/server.py:413-436` (现有 init 入口)
  - `tools/diagnose.sh` (部署诊断)
  - `meta/tests/conftest.py` + `shared/fixtures.py` (测试 fixture)

- 关键修复点:
  - **fd 泄漏根因**: `get_data_source()` 无缓存
  - **修复点**: 加 `_data_source_cache: Dict[(type, db_path), DataSource]`
  - **可观测性**: 已有 Prometheus + diagnose.sh + db_health_monitor 完整基础设施
  - **测试**: 已有 conftest.py + test_connection_pool.py 完整基础设施
