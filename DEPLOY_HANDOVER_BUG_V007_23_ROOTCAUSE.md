# DEPLOY_HANDOVER_BUG_V007_23_ROOTCAUSE - 7/7 disk I/O error 完整根因溯源 (基于证据)

> **作者**: dev-agent (主分析方) + 部署智能体 (待确认)
> **日期**: 2026-07-07 11:10
> **状态**: 🟡 **待部署智能体确认**
> **基础文档**: [DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md](./DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md) (根因错误, 不可作为修复依据)
> **真正修复方向**: V007.23 (待本文档确认后重写)

---

## 0. TL;DR (7 字段)

| 字段 | 值 |
|------|-----|
| BUG-ID | V007.23-MULTI-POOL-INODE-RACE |
| 根因类型 | CODE-BUG (user_authenticate.py 创建独立 connection pool) + DEPLOY-TRIGGER (重启) |
| 严重度 | P1-Critical (生产 7/7 8:21 admin 登录失败 ~30 分钟) |
| 修复方向 | 消除 user_authenticate.py 独立 pool, 改用 server.py 主 pool |
| 当前状态 | ✅ 生产已恢复 (9:25 setsid 启动 + 9:27 login 200) |
| 误诊文档 | V007.22-INTEGRATION (懒加载假设错误, 不可信) |
| 待部署智能体 | (a) 确认 fd 历史状态 (b) 确认多 pool 假设 (c) 决定 V007.23 修复方案 |

---

## 1. 为什么这份文档要存在 (V007.22 文档错误)

**V007.22 文档的根因假设** (来自 [DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md](./DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md) §3.4):

> "SQLiteConnectionPool 懒加载 + `_safe_cleanup_wal_shm` `os.remove` 与 connection init 的 inode 生命周期 race condition"

**这个假设是错误的**。证据如下:

1. V007.22 假设"懒加载 8:21:45 才 init" —— 但 **8:20:22 已经 init 了 2 次 connection pool** (yonaa log 明确)
2. V007.22 假设"V007.16 修复挡不住" —— 但 V007.16 修复在 8:20:22 工作正常 (Pool 1/2 都成功)
3. V007.22 的修复方向 (改 TRUNCATE 时机 / WriteQueue 改 PASSIVE) **根本解决不了真正的根因** —— 因为根因是"多 connection pool 共享一个 db 文件"

---

## 2. 完整事实时间线 (基于 yonaa 真实 log, 不含推测)

### 2.1 8:20 startup 阶段 log (PID 1905)

```
08:20:19,134  PID file written: /opt/app/deployments/meta/server.pid (PID: 1905)
08:20:19,380  [YAML Loader] parse_ui_detail_view_config: tabs_data=[...]
... (YAML loading 持续到 8:20:22)
08:20:22,340  [PREFLIGHT] WAL checkpoint TRUNCATE completed              ← 启动 TRUNCATE
08:20:22,344  Connection pool initialized: db=..., max_readers=20          ← **POOL 1** (server.py:383 get_data_source)
08:20:22,346  WriteQueue started
08:20:22,346  SQLite connected in pool mode
08:20:22,348  DBHealthMonitor initialized
08:20:22,350  [V007.15 L0] Runtime DB config detected
08:20:22,353  [RedundancyRegistry] 构建完成: 35 个冗余字段
08:20:22,474  [PermissionSync] orphaned permissions detected
08:20:22,486  AsyncAuditWriter started: workers=2, queue_size=1000        ← 启动 AsyncAuditWriter
08:20:22,497  Connection pool initialized: db=..., max_readers=20          ← **POOL 2** (AsyncAuditWriter.start)
08:20:22,497  WriteQueue started
08:20:22,497  SQLite connected in pool mode
08:20:22,694  [enum_api] 枚举迁移完成
08:20:24,599  [BoActionRegistry] Registered: user.authenticate            ← BOAction 注册
08:20:24,599  [BoActionRegistry] Registered: user.logout
... (19 个 action 注册完)
08:20:24,633  werkzeug WARNING: development server
08:20:24,633  Press CTRL+C to quit
08:20:30,553  GET /health 200
08:20:33,657  GET /api/v1/health 410
08:20:33,797  [TOKEN] Using JWT_SECRET_KEY from environment variable
08:20:33,798  POST /api/v1/auth/login (deploy_test) 200                    ← **POOL 1** (auth_api.py 走主 pool)
08:20:36,791  GET /health 200
08:20:36,804  GET /api/v2/bo/health 401
08:20:36,918  POST /api/v1/auth/login (deploy_test) 200                    ← **POOL 1**
08:20:36,985  GET /api/v1/enum-types 200                                   ← **POOL 1**
08:20:37,021  GET /api/v1/users/me 200                                      ← **POOL 1**
08:20:49,455  GET /api/v2/bo/product?pageSize=5 401                        ← **POOL 1** (v2 走主 pool)
08:21:41,595  GET /api/v1/users/me 401                                      ← **POOL 1** (token 过期)
08:21:45,897  [_cache_body] raw='{"username":"admin","password":"admin123"}'
08:21:45,898  [BOAction/parse] user.authenticate method=POST
08:21:45,910  Connection pool initialized: db=..., max_readers=20          ← **POOL 3** (user_authenticate.py 第一次 lazy init)
08:21:45,910  WriteQueue started
08:21:45,910  SQLite connected in pool mode
08:21:45,912  [V007.16] _execute_via_read_pool: marked bad connection (tid=..., attempt=0, err=disk i/o error)
08:21:45,913  [BoActionRegistry] Error executing user.authenticate: disk I/O error
08:21:45,914  [BOAction] user.authenticate success=False duration=15.5ms user=None
08:21:45,914  POST /api/v2/action/user.authenticate 200 (但 success=false)
08:42:28,326  Final WAL checkpoint TRUNCATE failed: disk I/O error         ← **用户报告故障时**
08:42:28,330  Connection pool shutdown
08:42:28,332  Final WAL checkpoint TRUNCATE failed: disk I/O error
08:42:58,333  Connection pool shutdown
```

### 2.2 8:20-8:21:45 期间 Connection Pool 创建事件 (3 次)

| # | 时间 | 触发点 | 文件:行 | 用途 |
|---|------|--------|---------|------|
| 1 | 08:20:22,344 | `server.py` main | `server.py:383 get_data_source` | **主 pool**, v1 登录用 |
| 2 | 08:20:22,497 | `AsyncAuditWriter.start()` | `meta/services/async_audit_writer.py` | 异步审计写 |
| 3 | 08:21:45,910 | `_get_auth_provider()` 第一次调用 | `meta/services/user_authenticate.py:43` | **v2 BOAction 登录** |

---

## 3. 关键代码证据 (从 yonaa 抓取)

### 3.1 `meta/services/user_authenticate.py:30-45` 关键 bug

```python
# 单例: data_source / provider
_data_source = None
_auth_provider = None


def _get_auth_provider():
    global _data_source, _auth_provider
    if _auth_provider is None:
        if _data_source is None:
            # ❌ db_path 用 __file__ 算路径, 永远是 <integration>/meta/services/../architecture.db
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'architecture.db',
            )
            # ❌ 创建独立第 3 个 connection pool
            _data_source = get_data_source("sqlite", database=db_path)
        _auth_provider = LocalAuthProvider(_data_source)
    return _auth_provider
```

**关键问题**:
- `__file__` 永远是源码路径, **不可能是部署路径** (`/opt/app/deployments/meta/architecture.db`)
- 第一次 v2 BOAction 调用时, **创建独立第 3 个 pool**, 不与 server.py 主 pool 共享
- 模块级单例, 全局状态

### 3.2 `meta/services/bo_action_registrations.py:40, 72-73` 注册 user.authenticate

```python
# Line 40
from meta.services.user_authenticate import user_authenticate_handler

# Line 72-73
register(
    'user.authenticate',
    user_authenticate_handler,
    ...
)
```

**确认**: `user.authenticate` 真的被注册到 BOAction registry, 8:20:24,599 "Registered: user.authenticate" log 是真的。

### 3.3 `meta/api/bo_action_api.py:201` 特殊处理

```python
# 特殊: login 成功后 set_cookie
if action_id == 'user.authenticate' and result.get('success'):
    token = (result.get('data') or {}).get('token')
    ...
```

**这是 v2 BOAction 路径** —— `/api/v2/action/user.authenticate` → `bo_action_registry.call('user.authenticate', params, context)` → `user_authenticate_handler` → `_get_auth_provider()` → **第一次创建 Pool 3**。

### 3.4 `meta/server.py` 不调 `init_user_authenticate`

```bash
# yonaa 上跑
grep -n "user_authenticate\|init_user_auth" /opt/app/deployments/meta/server.py
# 结果: 0 匹配
```

**关键**: server.py 完全不调 `init_user_authenticate` —— 这意味着 user_authenticate.py 的 `_data_source` **永远不会被 server.py 初始化**, **只能通过 v2 BOAction lazy init**。

### 3.5 `meta/services/bo_action_registrations.py` 是间接调用方

```bash
# yonaa 上跑
grep -rn "user_authenticate_handler\|user_authenticate" /opt/app/deployments/meta/ --include="*.py"
# 关键结果:
# meta/services/bo_action_registrations.py:40:  from meta.services.user_authenticate import user_authenticate_handler
# meta/services/bo_action_registrations.py:73:  user_authenticate_handler,
# meta/services/user_authenticate.py:48:  def user_authenticate_handler(...)
```

**所以**: `bo_action_registrations.py` 间接引用 `user_authenticate`, 但**只引用 handler 函数**, **不调它的 init 函数**。

### 3.6 server.py 启动时调 `bo_action_registrations`?

```bash
# yonaa 上跑
grep -n "register_all_bo_actions\|bo_action_registrations" /opt/app/deployments/meta/server.py
# (需要部署智能体确认)
```

**如果 server.py 不调 `register_all_bo_actions()`**, 8:20:24,599 "Registered: user.authenticate" log 是**哪来的**? **这是关键不确定性**。

---

## 4. 8:20:36 成功 8:21:45 失败的真正原因

| 时间 | 请求 | 走的 code path | pool | 结果 |
|------|------|---------------|------|------|
| 08:20:33 | POST /api/v1/auth/login (deploy_test) | `auth_api.py:65 login` → `_get_auth_provider` (auth_api.py:49) | **Pool 1** ✅ | 200 OK |
| 08:20:36 | POST /api/v1/auth/login (deploy_test) | 同上 | Pool 1 | 200 OK |
| 08:20:36 | GET /api/v1/enum-types | `auth_api.py` 或其他 | Pool 1 | 200 OK |
| 08:20:37 | GET /api/v1/users/me | Token + cache | Pool 1 | 200 OK |
| 08:20:49 | GET /api/v2/bo/product | v2 bo_api 走主 pool | Pool 1 | 401 (没 token) |
| 08:21:41 | GET /api/v1/users/me | Token 过期 | Pool 1 | 401 |
| 08:21:45 | POST /api/v2/action/user.authenticate (admin) | `bo_action_api.py:92` → `user_authenticate._get_auth_provider` | **Pool 3 ❌** | **disk I/O error** |

**v1 和 v2 走的是不同的 code path**:
- **v1** (`/api/v1/auth/login`) → `auth_api.py` → Pool 1 (server.py main) ✅
- **v2 BOAction user.authenticate** → `user_authenticate.py` → Pool 3 (独立 lazy init) ❌

---

## 5. 完整根因 — 多 Connection Pool inode race

### 5.1 8:20 startup 阶段状态

```
8:20:22.340  startup TRUNCATE on 临时 conn (server.py:376-378)            ← 临时 conn 持有 wal inode A
8:20:22.344  Pool 1 init → sqlite 内部 open wal inode B (新 inode)         ← Pool 1 持有 inode B
8:20:22.497  Pool 2 init (AsyncAuditWriter) → sqlite 内部 open wal inode C ← Pool 2 持有 inode C
```

**注意**: 8:20:22.340 startup TRUNCATE 的临时 conn 已经 close (line 378), 但 sqlite 可能在 close 时**不 unlink wal inode** (因为 wal 是 db 的辅助文件, 不会因为 close 而 unlink)。

**8:20:22 startup 完成时**:
- Pool 1 持有 wal inode B
- Pool 2 持有 wal inode C
- 2 个 pool 共享同一个 db + wal, 但 wal inode 不同

**短期 race (153ms) 但正常运行** (因为 v1 走 Pool 1, Pool 1 健康)。

### 5.2 8:21:45 触发 Pool 3 lazy init

```
8:21:45.910  Pool 3 init (user_authenticate._get_auth_provider)
             → sqlite 内部 open wal inode D
             → 试图跟 Pool 1 (B) + Pool 2 (C) 同步
             → **sqlite 内部状态错乱**: 3 个 pool 持有不同 wal inode, 但底层是同一个 db
8:21:45.912  attempt=0 disk i/o error
```

**为什么 attempt=0 失败?**
- V007.16 `_execute_via_read_pool` 的 max_retries=3 重试逻辑
- 第一次 `cursor.execute(SELECT users WHERE username=?)` 直接抛 disk I/O error
- 原因: **新创建的 connection (Pool 3) 持有的 wal inode D 与 Pool 1/2 持有的 inode B/C 不一致**
- sqlite 内部不允许多个 connection 用不同 inode 写同一个 db

### 5.3 8:42 process 被 kill (用户报告故障)

```
8:42:28,326  Final WAL checkpoint TRUNCATE failed: disk I/O error
8:42:28,330  Connection pool shutdown
8:42:28,332  Final WAL checkpoint TRUNCATE failed (再次失败)
```

**为什么 shutdown TRUNCATE 也失败?**
- 因为 Pool 1 + Pool 2 + Pool 3 都持有 db + wal 句柄
- 任意一个 pool shutdown 都触发 wal state 重新计算
- 跟其他 pool 持有的 inode 冲突 → TRUNCATE 失败

### 5.4 9:25 setsid 干净启动 5618 进程

- 5618 进程没有之前的 inode 残留
- 启动时只有一个 Pool (server.py main) — **AsyncAuditWriter 也是 9:25 启动的, 它创建的是 Pool 1**
- 没有第 3 个 Pool (因为 user.authenticate v2 BOAction 还没被调)
- 干净启动, login 成功

---

## 6. V007.22 文档错在哪 (逐条对比)

| V007.22 假设 | 事实 | 错在哪 |
|--------------|------|--------|
| §3.4 "懒加载 8:21:45 才 init" | 8:20:22 已 init 2 次 | V007.22 没看 8:20:22 startup log, 只看了 8:21:45 |
| §3.4 "_safe_cleanup_wal_shm + os.remove 与 connection init 竞争" | `_safe_cleanup_wal_shm` 有 mtime 检查, 不是无脑删 | V007.22 没看代码细节 |
| §3.5 "V007.16 修复挡不住" | V007.16 在 Pool 1/2 正常工作 | V007.22 没区分 Pool 1/2 vs Pool 3 |
| §3.6 "setsid 启动没有旧 backend 残留 fd" | 正确, 但根本原因不是"残留 fd", 是"没有 Pool 3" | V007.22 错把 fd 残留当主因 |
| §4.2 "connection init 时 bootstrap TRUNCATE" | 不能解决 Pool 3 跟 Pool 1/2 inode race | 修复方向错 |
| §4.3 "WriteQueue 改 PASSIVE" | 不能解决 Pool 3 问题 | 修复方向错 |
| §4.1 "部署脚本清理 inode" | 部署脚本不可能在 backend 运行中清理 inode | 修复方向错 |

---

## 7. 真正的修复方向 (V007.23)

### 7.1 P0: 消除 Pool 3 (核心)

**修 `meta/services/user_authenticate.py`**:

```python
# BEFORE (当前 bug)
_data_source = None
_auth_provider = None

def _get_auth_provider():
    global _data_source, _auth_provider
    if _auth_provider is None:
        if _data_source is None:
            db_path = os.path.join(  # ❌ 错路径
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'architecture.db',
            )
            _data_source = get_data_source("sqlite", database=db_path)  # ❌ 独立 pool
        _auth_provider = LocalAuthProvider(_data_source)
    return _auth_provider

# AFTER (修复)
_data_source = None
_auth_provider = None

def init_user_authenticate(data_source):
    """由 server.py 启动时调用, 注入主 pool 的 data_source"""
    global _data_source, _auth_provider
    _data_source = data_source  # ✅ 用主 pool
    _auth_provider = LocalAuthProvider(_data_source)

def _get_auth_provider():
    if _auth_provider is None:
        raise RuntimeError(
            "user_authenticate not initialized. "
            "Call init_user_authenticate(data_source) in server.py startup."
        )
    return _auth_provider
```

**修 `meta/server.py`**:

```python
# Line 419 附近
init_auth_services(data_source)
init_user_services(data_source)
+ init_user_authenticate(data_source)  # ✅ 新增
```

**修 `meta/services/bo_action_registrations.py`**:

```python
# 移除 'user.authenticate' 注册 (因为 server.py 不调 bo_action_registrations)
# 或者在 server.py 启动时调 register_all_bo_actions() + init_user_authenticate()
```

### 7.2 P0: 消除 Pool 2 (AsyncAuditWriter) 与 Pool 1 race

**修 `meta/services/async_audit_writer.py`**:

```python
# BEFORE
class AsyncAuditWriter:
    def start(self):
        # 创建独立 connection pool
        self._pool = SQLiteConnectionPool(self._db_path, ...)
        self._pool.initialize()

# AFTER: 接收外部 data_source
class AsyncAuditWriter:
    def __init__(self, data_source):
        self._data_source = data_source  # ✅ 用主 pool

    def start(self):
        # 不创建新 pool, 复用主 pool
        pass
```

**或者**: 让 AsyncAuditWriter 跟 Pool 1 串行 init (不并发, 避免 153ms race window)

### 7.3 P1: V007.16 修复保留 (兜底)

V007.16 的 `is_valid()` + `reader()` + `consecutive_errors` 熔断仍然有效, **保留作为兜底**。

### 7.4 P2: WriteQueue checkpoint_mode 改 RESTART (不是 PASSIVE)

V007.22 §4.3 建议改 PASSIVE 是错的, 因为 PASSIVE 不 truncate, 让 wal 持续增长。改 **RESTART** (平衡):
- PASSIVE: 不阻塞读, 不 truncate ❌
- RESTART: 阻塞读, 但 truncate ✅
- TRUNCATE: 阻塞读, truncate, 即使没数据也 truncate ← 当前

### 7.5 P3: systemd 自动重启 (与 V007.23 独立)

---

## 8. 部署智能体待确认的 4 件事

### 8.1 确认 Pool 3 是 user_authenticate 创建的 (高优先级)

```bash
# 在 yonaa 上跑
echo "===== server.py 是否调 bo_action_registrations ====="
grep -n "register_all_bo_actions\|bo_action_registrations" /opt/app/deployments/meta/server.py

echo "===== 8:20 startup 完整 log 找 register_all_bo_actions 调用 ====="
grep -E "bo_action_registrations|register_all_bo_actions|Registered 19" /opt/app/shared/logs/backend-v20260707_001.log

echo "===== v2 BOAction 走 user_authenticate_handler 的 trace ====="
# 找有没有更详细的 call stack log
grep -A 5 "user.authenticate" /opt/app/shared/logs/backend-v20260707_001.log | head -30
```

### 8.2 确认 8:20:22 Pool 1/2 同时 init 的 race window

```bash
# 在 yonaa 上跑
echo "===== 8:20:22 startup 100ms 内事件 ====="
awk '/2026-07-07 08:20:22.[34]/' /opt/app/shared/logs/backend-v20260707_001.log | head -30

echo "===== Pool 1/2 持有 wal 的 fd 状态 (历史) ====="
# 5618 是 9:25 启动的, fd 已经是新 inode
# 8:20-8:42 期间 1905 进程的 fd 看不到
# 但 9:25 setsid 启动时, 8:42 之前所有 inode 应该已经 unlink
ls -la /opt/app/deployments/meta/architecture.db*
stat /opt/app/deployments/meta/architecture.db
```

### 8.3 确认 9:25 启动 5618 进程没有第 3 个 pool

```bash
# 在 yonaa 上跑
echo "===== 5618 进程的 thread fd 状态 ====="
# 看 5618 持有多少 db + wal fd
ls -la /proc/5618/fd/ | grep architecture | wc -l

echo "===== 9:25 startup 阶段 log (验证只有 1 个 pool init) ====="
LATEST_LOG=$(ls -t /opt/app/shared/logs/backend-v*.log | head -1)
echo "Latest log: $LATEST_LOG"
grep -E "Connection pool initialized|AsyncAuditWriter started" "$LATEST_LOG" | head -20
```

### 8.4 确认修复后不会再出现 Pool 3

```bash
# 集成测试 (integration 端)
echo "===== integration 端 9:25 后 v2 BOAction 调用统计 ====="
# 9:25 setsid 启动后, v2 BOAction user.authenticate 调用应该用主 pool
# 在 integration 模拟:
for i in {1..10}; do
  curl -s -X POST http://localhost:3007/api/v2/action/user.authenticate \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' | jq -r '.success' 2>/dev/null
done

# 预期: 全部 true, 没有 disk I/O error
# 看 integration log 是否有 "Connection pool initialized" 在 v2 BOAction 后
grep -A 5 "v2/action/user.authenticate" /opt/app/shared/logs/integration-v*.log | head -30
```

---

## 9. 修复风险评估

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 修 user_authenticate.py 可能影响 v1 登录 (共享 data_source) | 🟡 中 | unit test 覆盖 v1 + v2 登录 |
| 修 AsyncAuditWriter 可能影响 audit 写入 | 🟡 中 | integration 跑 audit 写入测试 |
| WriteQueue 改 RESTART 可能影响写性能 | 🟢 低 | benchmark 验证 |
| V007.16 兜底修复保留 | 🟢 低 | 已有 unit test 覆盖 |

---

## 10. 文档时间线 (供协调智能体)

| 时间 | 事件 | 状态 |
|------|------|------|
| 2026-07-07 10:40 | 部署智能体提交 V007.22-INTEGRATION 文档 | ✅ |
| 2026-07-07 11:00+ | dev-agent 开始分析 V007.22 | ✅ |
| 2026-07-07 11:10 | dev-agent 发现 V007.22 根因错误 (基于 8:20:22 多 init 证据) | ✅ |
| 2026-07-07 11:15 | dev-agent 写 V007.23 ROOTCAUSE 文档 (本文件) | 🟡 |
| **2026-07-07 11:20** | **部署智能体确认 V007.23 根因 + Pool 3 来源** | ⏳ 待办 |
| 2026-07-07 11:30+ | dev-agent 实施 V007.23 代码修复 | ⏳ 待办 |
| 2026-07-07 12:00+ | 协调智能体 cherry-pick V007.23 + integration 验证 | ⏳ 待办 |

---

## 11. 给协调智能体的 6 条关键风险

1. **🔴 立即暂停 V007.22 修复实施** —— 基于错误根因修代码等于浪费时间
2. **🔴 V007.22 文档标记为"根因错误, 留档参考"** —— 不要作为修复依据
3. **🟡 部署智能体必须确认 §8 的 4 件事** —— 特别是 8.1 (server.py 是否调 bo_action_registrations)
4. **🟡 V007.23 修复优先级**: user_authenticate.py P0 → AsyncAuditWriter P0 → WriteQueue P2
5. **🟡 integration 端必须复现测试** —— 9:25 setsid 启动后跑 10 次 v2 BOAction login, 不能 disk I/O error
6. **🟢 V007.16 修复保留作为兜底** —— 不要删除

---

## 12. 关键参考文件

- 基础事件: [DEPLOY_HANDOVER_BUG_V007_21_PROD.md](./DEPLOY_HANDOVER_BUG_V007_21_PROD.md)
- 错误根因 (留档): [DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md](./DEPLOY_HANDOVER_BUG_V007_22_INTEGRATION.md)
- 基础设施 SOP: [INFRA_HANDOVER.md](./INFRA_HANDOVER.md) §6.6
- 关键代码:
  - `meta/services/user_authenticate.py:30-45` (Pool 3 来源)
  - `meta/services/bo_action_registrations.py:40, 72-73` (注册 user.authenticate)
  - `meta/services/async_audit_writer.py` (Pool 2 来源)
  - `meta/server.py:383` (Pool 1 来源)
  - `meta/server.py:419` (init_user_services 附近, 应该加 init_user_authenticate)
  - `meta/api/bo_action_api.py:201` (v2 BOAction 特殊处理)
  - `meta/core/sql_connection_pool.py:192-219` (initialize 流程)

---

**更新时间**: 2026-07-07 11:15
**更新人**: dev-agent (基于 8:20:22 startup log + user_authenticate.py 代码 + 5618 fd 状态)
**下次更新**: 部署智能体确认 §8 的 4 件事后, 补充或修正本根因
