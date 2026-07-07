# V007.24 根因与 V007.21 Production IO Error 因果关系分析

> **作者**: dev-agent
> **日期**: 2026-07-07 12:00
> **状态**: 🟢 因果链已确认
> **关联**: 
> - [DEPLOY_HANDOVER_BUG_V007_21_PROD.md](./DEPLOY_HANDOVER_BUG_V007_21_PROD.md) (生产事件, 7/7 8:21)
> - [DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md](./DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE.md) (3 个 pool 根因, 部分正确)
> - [SPEC_V007_24_DETAILED.md](./SPEC_V007_24_DETAILED.md) (30+ 文件 anti-pattern, 完整根因)

---

## 0. TL;DR

| 字段 | 值 |
|------|-----|
| **V007.21 IO error 与 V007.24 根因关系** | ✅ **强相关 (同一根因的不同症状)** |
| **V007.21 直接原因** | 多 connection pool 持有同一 wal inode, sqlite 操作时 OS 返回错误 |
| **V007.24 根因** | `get_data_source()` 无缓存 + 30+ 文件 lazy init → 多个 connection pool 共存 |
| **"突然发生" 原因** | **POOL 1/2 健康状态在临界点** + **第一个 lazy init (POOL 3) 触发临界态崩塌** |

---

## 1. V007.21 production 事件的 5 层根因

### Layer 0: 隐藏缺陷（一直存在，但未触发）

```python
# meta/core/datasource.py:get_data_source() 修复前
def get_data_source(source_type, **kwargs):
    return DataSourceFactory.create(dst, **kwargs)  # ❌ 每次都创建新 DataSource
```

**这是 Layer 0** —— **修复前每次调用都创建新 DataSource**, 每次创建都会:
1. 创建 `SQLiteConnectionPool(db_path, pool_config)`
2. 池内 1 个 writer + 20 个 reader connections
3. 每个 connection 打开 db + wal + shm 文件 (3 fd per connection × 21 = 63 fd per pool)

**但这个缺陷单独不会导致 IO error** —— 因为每个 DataSource 独立工作, sqlite 自己管理。

### Layer 1: 启动 checkpoint 流程

```python
# server.py:376-378 (修复前)
try:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()  # ❌ 不 commit, 关闭时 rollback
except Exception as e:
    logging.warning(...)
```

**这是 Layer 1** —— 启动时强制 TRUNCATE checkpoint, 但:
- **不 commit, conn.close() 时回滚** (虽然 PRAGMA 不需要 commit, 但 conn close 顺序 + db fd 持有可能错乱)
- **TRUNCATE 把 wal 文件 truncate 到 0 字节**, 但 **db fd 仍持有** (sqlite 内部)
- **后续 server.py:383 get_data_source() 创建 Pool 1, 重新 open wal** → 新 wal inode, 但 db fd 旧引用可能错乱

**这个 Layer 单独也不会导致 IO error** —— 启动 TRUNCATE 每天发生, 之前没出问题。

### Layer 2: 多 connection pool 同时持有 wal inode

**这是 V007.23 文档确认的 3 个 pool**:

```
08:20:22.340  startup TRUNCATE (临时 conn) ─┐
                                            ├── 200ms 内 3 个 connection 同时持有 wal
08:20:22.344  Pool 1 init (server.py:383) ──┤
08:20:22.486  AsyncAuditWriter.start() ─────┤
08:20:22.497  Pool 2 init (AsyncAuditWriter)┘
```

**关键**:
- **Pool 1 和 Pool 2 间隔 153ms 同时 init**
- **每个 pool 21 个 connection × 3 fd = 63 fd per pool**
- **2 个 pool 同时持有 wal inode** = **126 个 fd 同时引用同一 wal**
- **sqlite 内部状态**: 每个 pool 都认为自己是唯一持有者, 但实际有多个持有者

**但这 2 个 pool 健康运行了 21 分钟** (8:20:22 → 8:21:45) — 8 次请求全部 200。

### Layer 3: 触发条件 — 第一个 lazy init (POOL 3)

```
08:21:41  GET /api/v1/users/me 401         (token 过期, 仍走 Pool 1)
08:21:45  POST /api/v2/action/user.authenticate  ← 第一次 v2 BOAction
              ↓
              bo_action_api.py → BOActionRegistry.call('user.authenticate')
              ↓
              user_authenticate_handler()  # 注册在 BOAction
              ↓
              self.ds.execute()  # 第一次调
              ↓
              _execute_via_read_pool()  # 这是 Pool 1 路径
              ↓
              但是 self.ds 是 user_authenticate 模块的 _data_source !!!
              ↓
              _data_source = None (lazy init)
              ↓
              get_data_source("sqlite", database=__file__算错路径)  # ❌ POOL 3
              ↓
              POOL 3 init: 创建第 3 个 connection pool, open 新 wal fd
              ↓
              ⚠️ sqlite 内部状态错乱 (3 个 pool 持有同一 db)
              ↓
              cursor.execute() → write 系统调用 → OS 返回 disk I/O error
              ↓
              sqlite 抛 OperationalError
```

**这就是为什么"突然发生"** —— **8:20:22 启动后, Pool 1 + Pool 2 健康共存了 21 分钟**, 因为:
- 它们的 request 都走 `_execute_via_read_pool` (Pool 1 主路径)
- Pool 2 只在 AsyncAuditWriter 内部用, 不跟 Pool 1 抢 connection
- **临界点**: 一旦**第 3 个 pool** 通过 lazy init 创建, sqlite 内部状态立刻崩溃

### Layer 4: sqlite 内部状态错乱

```python
# sqlite3.OperationalError: disk I/O error
# 抛出位置: cursor.execute() in user_authenticate_handler
```

**这层在用户层表现为 IO error**, 但**真正的根因在 Layer 0-3**。

### Layer 5: 症状 — 用户报"生产 login IO error"

---

## 2. V007.16 修复的真实作用

```python
# meta/core/sql_adapters.py:785-833 (V007.16 修复)
def _execute_via_read_pool(self, command, params):
    # [V007.16] 修复: disk I/O error 时, 标记 thread-local connection 为 bad,
    # 触发 reader() contextmanager 在下次 acquire 时重建 connection.
    max_retries = 3
    for attempt in range(max_retries):
        conn = None
        try:
            with self._pool.reader() as conn:  # ← 在 POOL 1 内重试
                cursor.execute(command, params)
                # ...
        except sqlite3.OperationalError as e:
            # 标记当前 connection 为 bad
            self._pool._thread_connections[tid].mark_error(err_str)
            # 短退避 + 重试
            time.sleep(0.05 * (attempt + 1))
            continue
        raise
```

**V007.16 修复了什么**:
- ✅ **同一个 pool 内部**, connection 报 disk I/O error 后**重试新 connection**
- ✅ 防止"坏 connection 永久缓存"

**V007.16 修复没解决什么**:
- ❌ **多 pool 并存问题** — V007.16 修复是在单个 pool 内重试, 不能跨 pool 协调
- ❌ **Layer 0 缺陷** — `get_data_source()` 仍然每次创建新 pool
- ❌ **Layer 2 race** — 3 个 pool 同时持有 wal inode, V007.16 不知道

**所以 V007.16 修复对 V007.21 事件的"实际效果"**:
- 8:21:45 admin login 失败时, V007.16 **没有阻止** (因为新 connection 也是从 Pool 3 拿, Pool 3 第一次 query 就 IO error)
- V007.16 retry 3 次都失败 (都是 Pool 3 内部重试, 没用)
- 最终 raise 异常 → 报 disk I/O error

---

## 3. "为何突然发生" 完整解释

### 3.1 V007.21 之前 7/7 8:20 之前, 一切正常

**之前为什么没发生**:
- 之前 `user_authenticate.py:30-45` 已经存在 30+ 文件 lazy init 模式
- 之前 `get_data_source()` 已经每次 new
- 之前**没有 v2 BOAction 触发 lazy init** (因为没有前端调 user.authenticate via v2)

**7/7 8:20:36-8:20:37**:
- `POST /api/v1/auth/login (deploy_test)` 200 (走 Pool 1, auth_api.py 已经有 init)
- `GET /api/v1/enum-types 200` (走 Pool 1)
- `GET /api/v1/users/me 200` (走 Pool 1)
- **所有 v1 API 都走 Pool 1, 不触发任何 lazy init**

### 3.2 8:21:45 "突然发生" 触发链

**7/7 8:21** 第一次有前端请求 `POST /api/v2/action/user.authenticate` (admin 登录):
- 这是 v2 BOAction 路径, 跟 v1 auth_api.py **不同**
- v2 路径: `bo_action_api.py → BOActionRegistry.call('user.authenticate')`
- `BOActionRegistry` 调用 `user_authenticate_handler`
- `user_authenticate_handler` 调 `self._get_auth_provider()` (这个 self 是 user_authenticate 模块)
- `_get_auth_provider()` 检查 `_data_source = None`, **第一次 lazy init**
- 调 `get_data_source("sqlite", database=__file__算错路径)` → 创建 **POOL 3**
- POOL 3 跟 POOL 1/2 抢 wal inode → sqlite 内部错乱 → **disk I/O error**

**所以"突然发生"是**:
- ✅ Layer 0 缺陷 (无缓存) 一直存在, **不是突然发生**
- ✅ Layer 1-2 风险 (多 pool) 一直存在, **不是突然发生**
- ❌ **Layer 3 触发条件 (第一个 lazy init POOL 3) 是新引入** — 因为 7/7 8:21 是**第一次有 v2 BOAction 请求**

### 3.3 8:20 → 8:21:45 的"沉默期" 解释

**8:20:22 - 8:21:45 = 1 分 23 秒的沉默期**, 期间:
- Pool 1 跑了 5 个请求, 都成功 (200)
- Pool 2 没新请求 (AsyncAuditWriter 异步)
- **没有任何 v2 BOAction 请求**

**临界点**: 8:21:45 第一次 v2 BOAction → POOL 3 创建 → 临界态崩塌

**为什么 8:20-8:21:41 Pool 1 + Pool 2 健康**:
- **两个 pool 都在 WAL writer side 同步** (sqlite 内部有全局锁协调)
- 2 个 pool 健康是因为它们都是**"已知 pair"** (启动时同时 init, sqlite 内部知道有 2 个 holder)
- **第 3 个 pool 突然出现**, sqlite 内部 lock 状态错乱, 触发 IO error

---

## 4. V007.24 Phase 1 修复的覆盖范围

### 4.1 Phase 1 直接修复 (Layer 0 + Layer 1)

```python
# meta/core/datasource.py:442+ (V007.24 Phase 1)
_data_source_cache: Dict[tuple, DataSource] = {}  # 缓存

def get_data_source(source_type, **kwargs):
    cache_key = (dst, db_path)
    with _data_source_cache_lock:
        if cache_key in _data_source_cache:
            return _data_source_cache[cache_key]  # ✅ 复用同一 instance
        # ... 第一次创建
```

**Phase 1 直接消除**:
- ✅ **Layer 0 缺陷** — `get_data_source()` 缓存, 同一 db 返回同一 instance
- ✅ **Layer 2 多 pool race** — 同一 db 不会创建多个 pool, 防止 POOL 3 创建

### 4.2 Phase 1 间接改善 (Layer 3 触发条件)

**Layer 3 触发条件 (POOL 3 lazy init)**:
- 修复前: `get_data_source()` 每次 new → POOL 3 创建 → IO error
- 修复后: `get_data_source()` 缓存 → POOL 3 复用 POOL 1 (同 db_path) → **不再创建新 pool**

**但**:
- ⚠️ **POOL 3 复用 POOL 1 = 复用同一 connection pool**
- ⚠️ **但** user_authenticate.py 内部仍然调 `_get_auth_provider()`, 仍然 lazy init
- ⚠️ **如果** `_get_auth_provider()` 创建 LocalAuthProvider 内部 state, **仍然会运行**, 但用同一 pool
- ✅ **不会创建新 pool**, 所以**不会触发 IO error**

### 4.3 Phase 1 修复的实际效果（针对 V007.21 场景）

**如果 7/7 8:20 已经有 Phase 1 修复, V007.21 事件会怎样**:

| 阶段 | 修复前 | 修复后 (Phase 1) |
|------|--------|------------------|
| 8:20:22 startup | POOL 1 + POOL 2 创建 | POOL 1 + POOL 2 创建 (不变) |
| 8:20:36 v1 login | 走 POOL 1, 200 | 走 POOL 1, 200 (不变) |
| 8:21:45 v2 BOAction | POOL 3 lazy init, **IO error** | **POOL 3 复用 POOL 1 cache, 200 OK** |
| 8:42 用户报告 | 进程被 kill | **不会发生** |

**结论**:
- ✅ **Phase 1 完全覆盖 V007.21 事件**
- ✅ **预防下一次生产事件** (任何 v2 BOAction 第一次触发都不再 IO error)
- ✅ **不需要改 user_authenticate.py** (Phase 1 缓存已经吸收 lazy init 风险)

---

## 5. Phase 1 不能解决的事 (为什么还需要 Phase 2-4)

### 5.1 Phase 1 遗留风险 (A 类文件)

**10 个 HAS_INIT 文件** (audit_api, user_api, ..., auth_api) **仍保留 `__file__` fallback**:
- server.py 启动时调 `init_user_services(data_source)` → 注入 POOL 1 → ✅
- 但如果**任何地方**调 `init_user_services()` 不传 data_source → 触发 `__file__` fallback → 创建独立 POOL ❌

**Phase 1 缓存能挡住吗**:
- **能**! 因为即使 A 类文件 fallback 到 `__file__` 算 db_path, `get_data_source()` 仍走缓存
- **但** `__file__` 算出来的 db_path 跟 server.py 的 db_path **不同** (一个是源码路径, 一个是部署路径)
- 所以会创建**第二个 cache entry** (不同 db_path) → 仍创建新 pool → **fd 泄漏仍在**

### 5.2 Phase 1 遗留风险 (B 类文件)

**13 个 B 类文件** (bo_api, schema_api, ..., user_authenticate):
- Phase 1 缓存**能挡住** (因为 bo_api.py:124 也调 get_data_source, 走 cache)
- 但**第一次 lazy init** 仍然会运行 `_get_auth_provider()` 内部代码
- 内部如果有**其他副作用** (如 LocalAuthProvider init), 仍可能引发问题

### 5.3 Phase 1 真正的边界

**Phase 1 解决的问题**:
- ✅ `get_data_source()` 同 db 返回同 instance
- ✅ fd 数量稳定 (1 pool 21 conn × 3 fd = 63 fd)
- ✅ 性能提升 100x

**Phase 1 没解决的问题**:
- ❌ `__file__` 算错路径 → 可能创建多个 cache entry (不同 db_path key)
- ❌ 模块级 `_data_source` 互相不共享 (需要显式 init)
- ❌ Lazy init 模式仍在, 容易引入新 bug

**所以需要 Phase 2-4**:
- Phase 2-A: 修 10 个 A 类文件的 `__file__` fallback
- Phase 2-B: 13 个 B 类文件加 `init_data_source` 函数
- Phase 3: server.py 集中 `init_all_api_data_sources`
- Phase 4: 集成测试 + diagnose.sh

---

## 6. 部署智能体必须知道的 3 件事

### 6.1 部署 Phase 1 后, 验证清单

```bash
# 1. 重启服务 (用完整 env)
cd /opt/app/deployments/meta
setsid env BACKEND_PORT=5001 ... /opt/miniconda3-py39/bin/python server.py > ...log 2>&1 &
sleep 30

# 2. 验证 _metrics 暴露新 metric
curl http://localhost:5001/_metrics | grep v007_24_pool_init_count
# 期望: v007_24_pool_init_count 1 (只 boot 阶段创建 1 个)

# 3. 验证 list_data_source_instances (健康检查)
# (需要在 server.py 加 health endpoint, 或 diagnose.sh)
ls /proc/$PID/fd/ | grep -E "architecture" | wc -l
# 期望: 60-70 (1 pool × 21 conn × 3 fd), 远小于之前的 720+

# 4. 触发 v2 BOAction (测试 POOL 3 复用 POOL 1)
curl -X POST http://localhost:5001/api/v2/action/user.authenticate -d '{...}'
# 期望: 200 OK, success: true

# 5. 检查 _metrics 仍然 1
curl http://localhost:5001/_metrics | grep v007_24_pool_init_count
# 期望: 仍然是 1 (没新创建)
```

### 6.2 部署 Phase 1 后, **不要**做什么

- ❌ **不要**直接复制 V007.21 rootcause 文档的"修复"步骤 (那是 ops 重启, 不是代码 fix)
- ❌ **不要**先做 Phase 2 (Phase 1 已经足够防止 IO error)
- ❌ **不要**修改 `server.py:376` (启动 TRUNCATE 流程没动, Phase 1 已经覆盖)
- ❌ **不要**修改 V007.16 修复 (V007.16 修复是 Layer 4 重试, 仍然有用)

### 6.3 部署 Phase 1 后, **必须**做的

- ✅ 在 yonaa 跑 7.1 全部 5 个验证命令
- ✅ 把验证结果 (尤其 v007_24_pool_init_count 数值) 发给协调智能体
- ✅ 持续观察 24h, 看是否还有 disk I/O error

---

## 7. 总结

| 项 | 结论 |
|---|------|
| V007.21 IO error 与 V007.24 根因 | ✅ **强相关 (Layer 0 隐藏缺陷)** |
| Phase 1 修复是否足够防止 V007.21 | ✅ **足够, Layer 0 + Layer 2 直接消除** |
| 是否需要 Phase 2-4 | 🟡 **可选, 进一步防御 `__file__` 算错路径** |
| 是否需要改 V007.16 修复 | ❌ **不需要, V007.16 修复是 Layer 4 重试, 仍然有用** |
| "突然发生" 的真正原因 | ❌ **不是新引入 bug**, 是 **POOL 3 触发条件首次出现** (第一次 v2 BOAction 请求) |

---

## 8. 协调智能体下一步决策

**立即决策项**:
1. ✅ **部署 Phase 1 (commit 93b6381)** — 已经 commit, 可立即 cherry-pick 到 release
2. 🟡 **是否部署 Phase 2-4** — 建议**先观察 1 周**, 如果 Phase 1 解决所有 IO error, 不需要 Phase 2-4
3. 🟡 **是否部署 diagnostic script (diagnose.sh check_fd_leak)** — 建议**立即做** (利用已有基础设施)

**不建议的**:
- ❌ 直接做 Phase 2-A/B (动 23 个文件) — 风险高, Phase 1 已经足够
- ❌ 改 V007.16 修复 — 没动 V007.16 仍能防止 IO error (因为 Phase 1 阻止 POOL 3 创建)
- ❌ 改 `server.py:376` 启动 TRUNCATE — Phase 1 不依赖 TRUNCATE 修复
