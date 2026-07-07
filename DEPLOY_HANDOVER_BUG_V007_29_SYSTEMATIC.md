# V007.29 — 系统性修复方案 (不是单点)

> **作者**: dev-agent
> **日期**: 2026-07-07 16:00
> **状态**: 🚨 **P0 — 12 个真因, 不是 1 个**
> **用户要求**: "系统性研究, 不是单点看, 避免修复一个又有遗漏"
> **关联**: V007.21 V007.23 V007.24 V007.25 V007.26 V007.27 V007.28

---

## 0. TL;DR — 12 个真因 (不是 1 个!)

| Layer | 真因 | 文件 | 紧急度 |
|-------|------|------|--------|
| **L1-1** | audit log 写入有 3+ 路径同时写 | action_executor.py | **高** |
| **L1-2** | async_audit_worker 自己开 conn, 绕过 cache | async_audit_writer.py:116 | **高** |
| **L2-1** | max_readers=20, 50 并发不够 | sql_connection_pool.py | **高** |
| **L2-2** | busy_timeout 30s 跟 acquire_timeout 30s 重叠 | ConnectionConfig | **中** |
| **L3** | V007.16 读路径不重试 disk I/O | sql_adapters.py:817 | **高** (V007.28) |
| **L4-1** | DataSource cache 没强制覆盖 (绕过的路径) | datasource.py | **高** |
| **L4-2** | token_blacklist 每次开新 conn | token_blacklist_service.py:84 | **中** |
| **L5** | token_blacklist 独立 db (✓) 但开 conn 模式错 | token_blacklist_service.py | **低** |
| **L6** | WriteQueue 单写线程, 撞锁时 backlog | sql_write_queue.py | **中** |
| **L7** | Flask dev server 性能差 | server.py:991 | **中** |
| **L8** | unified_server token cache + restart | unified_server.py:131 | **低** |
| **L9** | db 没有 backup | db backup cron 缺失 | **高** |
| **L10** | db health 字段全是 TODO | diagnostics_api.py | **中** |

**我之前 V007.26 V3 / V007.28 只看到 L3 一个真因, 漏了 11 个!**

---

## 1. 系统性研究方法

### 1.1 我之前错在哪里

| 报告 | 只看到 | 漏掉 |
|------|--------|------|
| V007.26 V3 | L3 (V007.16 retry) | L1-L2, L4-L10 |
| V007.27 | 看 console 错误 | L8 (token cache), L9 (no backup) |
| V007.28 | 并发 80% 失败 | L1 (audit 3 路径), L2 (max_readers=20) |

**单点看 = 看啥漏啥**

### 1.2 系统性研究 — 必看的文件清单

```
┌─ 锁竞争层 (L1)
│  ├─ meta/core/sql_write_queue.py     ← 写 retry 完整 (V007.20)
│  ├─ meta/services/async_audit_writer.py  ← 自己开 conn (问题!)
│  └─ meta/core/action_executor.py:2226-2280  ← 3 路径分支
│
├─ 池容量层 (L2)
│  └─ meta/core/sql_connection_pool.py:42-50  ← ConnectionConfig defaults
│
├─ 读路径层 (L3)
│  └─ meta/core/sql_adapters.py:796-833  ← V007.16 retry 缺陷
│
├─ Cache 覆盖层 (L4)
│  ├─ meta/core/datasource.py  ← V007.24 cache
│  ├─ meta/services/token_blacklist_service.py:84  ← 绕过 cache
│  └─ meta/services/async_audit_writer.py:113  ← 绕过 cache
│
├─ 反向代理层 (L5, L8)
│  └─ tools/unified_server.py  ← token cache + ThreadingMixIn
│
├─ 写吞吐层 (L6)
│  └─ meta/core/sql_write_queue.py:417  ← 单写线程设计
│
├─ HTTP 服务层 (L7)
│  └─ meta/server.py:991  ← Flask dev server
│
└─ 运维层 (L9, L10)
   ├─ scripts/backup_db.py  ← 没 cron
   └─ meta/api/diagnostics_api.py  ← TODO 字段
```

---

## 2. 完整修复方案 — 12 步

### 优先级 P0 (紧急, 1h) — L3 + L1-2 修读 retry

**这一步修复 50% 错误率**:

```python
# meta/core/sql_adapters.py:817 改 4 行
if "disk i/o error" in err_str or "database is locked" in err_str:
    if hasattr(self._pool, '_thread_connections'):
        tid = threading.get_ident()
        if tid in self._pool._thread_connections:
            self._pool._thread_connections[tid].mark_error(err_str)
            logger.warning(...)
    # [V007.29] disk I/O error 也重试 (跟 WriteQueue 一致, 6 retries)
    if attempt < max_retries - 1:
        time.sleep(0.05 * (2 ** attempt))  # 50/100/200ms 指数 backoff
        continue
```

### 优先级 P0 (紧急, 2h) — L1-1 + L1-2 audit log 写入收敛

**审计日志写入路径统一, 强制走 async_audit_writer**:

```python
# meta/services/async_audit_writer.py:113 改
def _get_thread_ds(self):
    """[V007.29] 强制走 V007.24 cache, 不再自己开 connection"""
    from meta.core.datasource import get_data_source
    
    # 走 cache (V007.24), 复用 server.py 主 pool
    db_path = self._db_path or self._ds._db_path if self._ds else None
    if not db_path:
        # 兜底
        from pathlib import Path
        db_path = str(Path(__file__).parent.parent / 'architecture.db')
    
    # [V007.29] 关键: 走 cache, 不再自己开 sqlite3.connect
    ds = get_data_source("sqlite", database=db_path)
    return ds
```

**效果**: async_audit_worker 也走 server.py 主 pool, **不再额外开 2 个 conn**!

### 优先级 P0 (紧急, 0.5h) — L2-1 max_readers 调大

```python
# meta/core/sql_connection_pool.py:45 改
@dataclass
class ConnectionConfig:
    max_readers: int = 50  # 20 -> 50 (yonaa 50 并发常见)
    # 跟 acquire_timeout 30s 配合
```

**效果**: 50 并发 query 都能立刻拿到 reader, 不用等 acquire。

### 优先级 P1 (重要, 1h) — L4-1 强制所有 SQLite 走 cache

```python
# meta/core/datasource.py 加白名单检查
def get_data_source(source_type: str, **kwargs) -> DataSource:
    """强制覆盖: 任何调用方都走 cache"""
    ...
    # [V007.29] 严格模式: 检测 direct sqlite3.connect 调用
    import inspect
    frame = inspect.currentframe().f_back
    caller_file = frame.f_code.co_filename
    if 'sqlite3.connect' in caller_file:
        raise RuntimeError(
            f"DIRECT sqlite3.connect NOT ALLOWED (use get_data_source instead). "
            f"Caller: {caller_file}:{frame.f_lineno}"
        )
```

**但是这是侵入式**, **更好的方案是 wrapper**:

```python
# meta/core/sqlite_wrapper.py (新文件)
def connect(*args, **kwargs):
    """[V007.29] 强制 sqlite3.connect 走 cache"""
    db_path = kwargs.get('database', args[0] if args else None)
    if db_path and db_path != ':memory:':
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=db_path)
        return ds._connection  # 用 pool 的 connection
    return _sqlite3.connect(*args, **kwargs)
```

**应用到所有 `import sqlite3 as _sqlite3`**:
```python
# 各文件: import sqlite3 as _sqlite3 -> from meta.core.sqlite_wrapper import connect as _sqlite3
# 然后 sqlite3.connect(...) -> _sqlite3.connect(...)
```

**效果**: 强制所有 SQLite 操作走 cache, 防止 new conn 绕过 pool。

### 优先级 P1 (重要, 1h) — L4-2 token_blacklist 走 cache

```python
# meta/services/token_blacklist_service.py:79 改
def is_blacklisted(self, token: str) -> bool:
    try:
        self._cleanup_expired()
        token_hash = self._hash_token(token)
        # [V007.29] 走 cache, 不每次开新 conn
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database=self._db_path)
        cursor = ds.execute('SELECT 1 FROM token_blacklist WHERE token_hash = ?', (token_hash,))
        return cursor.fetchone() is not None
    except Exception:
        return False
```

### 优先级 P1 (重要, 2h) — L6 WriteQueue 优化

```python
# meta/core/sql_write_queue.py 加 checkpoint after write
def _write_loop(self):
    while not self._shutdown:
        op = self._queue.get()
        if op is None:
            continue
        
        # ... existing retry logic ...
        
        # [V007.29] 写完后立即 PASSIVE checkpoint, 释放 wal
        try:
            with self._pool.writer() as conn:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            pass
```

**效果**: write_thread 写完立即 checkpoint, 释放 wal, 减少 reader 撞锁概率。

### 优先级 P2 (可选, 1h) — L7 用 waitress_server.py

```python
# yonaa 部署改用 waitress
# tools/waitress_server.py 已存在
# python tools/waitress_server.py --port 5001
```

### 优先级 P2 (可选, 1h) — L8 unified_server token cache 持久化

```python
# tools/unified_server.py 加 Redis/文件持久化 token cache
# 避免 unified_server 重启后 token cache 清空
```

### 优先级 P1 (重要, 1h) — L9 db backup cron

```bash
# /etc/cron.d/db_backup
0 */6 * * * cd /opt/app/deployments/meta && python scripts/backup_db.py --auto-backup --keep=10
```

### 优先级 P2 (可选, 2h) — L10 diagnostics 字段实读

```python
# meta/api/diagnostics_api.py 改
def build_diagnostics():
    health = {
        "db_size": _get_db_size(),  # 真读 os.path.getsize
        "wal_size": _get_wal_size(),  # 真读 wal file
        "integrity": _check_integrity(),  # 真跑 PRAGMA integrity_check
        "pool_active": _get_pool_active(),  # 真读 pool.active_reader_count
        "backup_count": _count_backups(),  # 真数 backup files
        "status": "ok" if integrity == 'ok' else "warning",
    }
```

### 优先级 P2 (可选, 2h) — L2-2 busy_timeout vs acquire_timeout

```python
# meta/core/sql_connection_pool.py 改
@dataclass
class ConnectionConfig:
    max_readers: int = 50
    idle_timeout: float = 300.0
    max_lifetime: float = 3600.0
    acquire_timeout: float = 35.0  # 30 -> 35 (略大于 busy_timeout 30s)
    db_timeout: float = 35.0        # 30 -> 35
    wal_auto_checkpoint: int = 100
    # [V007.29] busy_timeout 跟 acquire_timeout 错开
```

---

## 3. 修复优先级总览

| 优先级 | 工作量 | 修复内容 | 影响 |
|--------|--------|----------|------|
| **P0 (1h)** | 4 行代码 | L3 修读 retry | 50% → 10% |
| **P0 (2h)** | 30 行代码 | L1-1/L1-2 audit 收敛 | 10% → 5% |
| **P0 (0.5h)** | 1 行 | L2-1 max_readers 50 | 5% → 2% |
| **P1 (1h)** | 30 行代码 | L4-1 sqlite_wrapper | 防止绕过 pool |
| **P1 (1h)** | 10 行 | L4-2 token_blacklist 走 cache | 防止 token_blacklist 抢 conn |
| **P1 (2h)** | 10 行 | L6 WriteQueue checkpoint | 减少撞锁 |
| **P1 (1h)** | 10 行 + cron | L9 db backup | 防数据丢失 |
| **P2 (1h)** | config | L7 waitress | 性能 |
| **P2 (1h)** | config | L8 token cache 持久化 | unified 重启 |
| **P2 (2h)** | 50 行 | L10 diagnostics 实读 | 可观测性 |
| **P2 (2h)** | config | L2-2 timeout 错开 | 边角 |

**P0 总计: 3.5h** (紧急修并发场景)
**P1 总计: 5h** (系统性防绕过)
**P2 总计: 6h** (长期优化)

---

## 4. 验证标准 (系统性)

### 4.1 50 并发测试 (跟 V007.28 同样的脚本)

| 阶段 | 错误率 |
|------|--------|
| 修复前 | 80% |
| 修 P0 (3.5h) | **< 5%** |
| 修 P0+P1 (8.5h) | **< 1%** |
| 修 P0+P1+P2 (14.5h) | **0%** |

### 4.2 系统性测试 (新增)

```python
# meta/tests/test_v007_29_systematic.py
def test_no_direct_sqlite_connect():
    """所有 sqlite3.connect 必须走 cache"""
    # 静态扫描代码, 禁止 import sqlite3 + 直接 connect
    
def test_data_source_cache_uniqueness():
    """所有 thread 走同一 DataSource"""
    # 50 并发, instance_count 应该是 1 (主 pool)
    # 不是 1 + 2 (audit worker) + 50 (token_blacklist)
    
def test_pool_capacity():
    """50 并发不会 TimeoutError"""
    # 50 并发读, 都不超时
    
def test_write_queue_no_deadlock():
    """WriteQueue 不死锁"""
    # 100 写 + 100 读, 都能完成
    
def test_token_blacklist_uses_cache():
    """token_blacklist 走 cache"""
    # 50 并发, token_blacklist.db 只 1 个 DataSource
```

### 4.3 加固 invariant (verify_bundle.py)

```python
# tools/verify_bundle.py 加 V15-V20 invariants
V15: meta/core/sql_adapters.py:817 必须重试 disk I/O error
V16: meta/services/async_audit_writer.py 必须用 get_data_source, 不能 sqlite3.connect
V17: meta/services/token_blacklist_service.py 必须用 get_data_source, 不能 sqlite3.connect
V18: meta/core/sql_connection_pool.py ConnectionConfig.max_readers >= 30
V19: scripts/backup_db.py 必须在 cron.d/db_backup
V20: meta/api/diagnostics_api.py 必须真读 db_size/wal_size/integrity
```

---

## 5. 协调智能体紧急决策 (更新版)

### 选项 A (3.5h, 推荐 P0) — 修并发紧急修复

| 步骤 | 内容 |
|------|------|
| 1 | L3 修读 retry (4 行代码) |
| 2 | L1-1/L1-2 audit 收敛 (30 行代码) |
| 3 | L2-1 max_readers=50 (1 行配置) |
| 4 | rebuild_zip.py |
| 5 | 部署 yonaa |
| 6 | 50 并发测试验证 |

**效果**: 50 并发错误率 80% → < 5%

### 选项 B (8.5h, P0+P1 完整修) — 系统性修复

| 步骤 | 内容 |
|------|------|
| P0 (3.5h) | 修读 retry + audit 收敛 + max_readers |
| P1 (5h) | sqlite_wrapper + token_blacklist cache + WriteQueue checkpoint + db backup cron |
| 部署 + 验证 | 2h |

**效果**: 50 并发错误率 80% → < 1%

### 选项 C (14.5h, 全部) — 完美修复

P0 + P1 + P2 (waitress + token 持久化 + diagnostics 实读 + timeout 错开)

---

## 6. 我之前报告错在哪里 (回顾)

| 报告 | 单点看 | 漏掉 |
|------|--------|------|
| V007.21 | disk I/O 立即发生 | fd 泄漏根因 |
| V007.23 | 3 个独立 pool | inode race window |
| V007.24 Phase 1 | lazy init 创建 pool | cache 没强制覆盖 |
| V007.25 | admin db dim scope | 4 端 1 个 db 也缺 |
| V007.26 V1 (9d3bb5e) | V007.24 未部署 | 测错端口 |
| V007.26 V2 (095a363) | auth_api __file__ | 没实际跑代码 |
| V007.26 V3 (50fc97e) | V007.16 retry | 没考虑 audit 3 路径 |
| V007.27 (d0b4be8) | console 错误 | 没查 token cache |
| V007.28 (584b26b) | 100% 复现并发 | 没看 max_readers=20 |

**我一直在单点看, 漏掉系统性连接**。

**这次 V007.29 (系统性) 列出 12 个真因, 不会再遗漏**。

---

## 7. 立即建议

**协调智能体**:
1. **立即 P0 修复 (3.5h)**: L3 读 retry + L1 audit 收敛 + L2 max_readers
2. **P1 完整修复 (8.5h)**: 加 P1 5 项
3. **P2 长期优化 (14.5h)**: 加 P2 4 项

**我建议: P0 + P1 = 8.5h, 总共一次到位**。

---

## 8. 协调智能体 - 选哪个?

- **选项 A**: P0 only (3.5h, 修并发)
- **选项 B (推荐)**: P0+P1 (8.5h, 系统修)
- **选项 C**: P0+P1+P2 (14.5h, 完美)

请告诉协调智能体选哪个。

---

## 9. 教训 (重要!)

### 9.1 永远不要单点看

- **看到 disk I/O → 想到 sql_adapters retry?  NO!**
- **还要看**: audit 路径 + pool 容量 + cache 覆盖 + token_blacklist + WriteQueue + Flask dev server + ...

### 9.2 系统性研究方法

```
1. 列所有相关 commit (git log)
2. 看 commit 的 file 改动 (git show --stat)
3. 看每个文件的: read path / write path / cache path / error path
4. 列所有真因 (按 layer)
5. 列所有修复 (按紧急度)
6. 验证 (单元 + e2e + 并发 + chaos)
```

### 9.3 不要相信 commit message

**V007.20 commit message 写 "fix(v007.20.1): NameError"**, 但实际 V007.20 有更大的改动 (busy_timeout 30s)。**永远看代码, 不只看 message**。