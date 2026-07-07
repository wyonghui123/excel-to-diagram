# V007.34 — 详细分析 (系统性研究 + 全面修复方案)

> **作者**: dev-agent
> **日期**: 2026-07-07 19:00
> **状态**: 🎯 **完整诊断 + 实施计划** — 基于 100% 代码 + 现场复现 + log
> **方法**: 系统性研究 (读完整 read+write 路径 + 现场复现 + 验证)

---

## 0. TL;DR

**V007.33 修复方向对 (mark_error 后加 continue), 但不够全面**.

我系统性研究发现:

| 关键发现 | 之前漏的 |
|---------|---------|
| **写路径 V007.20 完美** (6 retries + 指数 backoff + jitter) | ✅ 写路径不需修 |
| **读路径 V007.16 mark_error 后没 continue** | V007.33 提了 |
| **login 100% disk I/O 复现** (BoActionRegistry 转 success=False) | ❌ 之前没看 |
| **busy_timeout 在 yonaa = 5s (V007.20 30s 没部署)** | ❌ 之前没看 |
| **audit_logs 11.7万行 + 4 路径并发写** | ❌ 之前没量化 |
| **`_thread_connections` 是 thread-local, Flask 每个请求一个新 thread** | ❌ 之前没考虑 |

**用户实际现象**:
- login 100% 失败 (20/20 disk I/O)
- 业务 endpoint 顺序 0/8 500, 并发 0% 500 (V007.20 写路径修过)
- 17:42:36 之前 1w+ annotation import 卡 40% (HANDOFF_V007_20)

**完整修复 (3 方面)**:

| P0 | 修 `_execute_via_read_pool` mark_error 后 continue + 指数 backoff (跟 V007.20 写路径完全一致) | 3 行 |
| P1 | 修 `LocalAuthProvider` 异常 → 重试 (V007.16 reader 已 retry, 但 LocalAuthProvider 抛到外层) | 不需, 跟 P0 一致 |
| P1 | busy_timeout 30s 部署 (V007.20 改 30s, yonaa 还 5s) | 1 行 |
| P2 | data_source_cache 数量限制 (5 个超了报警) | 已有 |

---

## 1. 系统性研究 — 完整调用链

### 1.1 login 失败链 (新发现!)

```
[前端] POST /api/v2/action/user.authenticate
    body: {"action": "user.authenticate", "username": "admin", "password": "admin123"}
    ↓
[bo_action_api.execute_action L92]
    L141: params = request.get_json() = {"action":..., "username":..., "password":...}
    L150: logger.info("[BOAction/parse] ... params={'action':..., 'username':..., 'password':...}")
    L157: context = _build_user_context()
    ↓
[bo_action_api] L93+: invoke handler
    ↓
[bo_action_registry.invoke L204] 
    result = meta.handler(params, context or {})
    ↓
[user_authenticate_handler L48]  (params 已经是 dict, params.get('username')='admin')
    L66-67: username='admin', password='admin123'
    L88: provider = _get_auth_provider()  ← lazy init
    L89: user_info = provider.authenticate({'username': 'admin', 'password': 'admin123'})
    ↓
[LocalAuthProvider.authenticate L150]
    L157: cursor = self.ds.execute("SELECT id, username, ... FROM users WHERE username = ?", ['admin'])
    ↓
[sql_adapters.execute L770]
    L775: op_type = _classify_operation(command) = 'read'
    L779: result = self._execute_via_read_pool(command, params)
    ↓
[_execute_via_read_pool L785]
    L787-791: 检查 in_transaction - 跳过
    L796: max_retries = 3
    L798: for attempt in range(3):
    L801: with self._pool.reader() as conn:    ← 第一次进 reader() — thread-local 没有, 建新 conn
            L802-806: cursor.execute(command, ['admin'])
            L807-811: 成功? 清除 last_io_error
            L812: return result
        except Exception as e:
            L817: if "disk i/o error" in err_str:
                L821: pc.mark_error(err_str)  ← 标记
                # ⚠️ 没 continue! 落到下面
            L827: if "operational" in err_str:    ← 因为是 sqlite3.OperationalError
                L828: if attempt < 2:
                    L830: time.sleep(0.05 * (attempt + 1))  ← 50/100ms
                    L831: continue  ← 重试
            L832: raise
    L833: raise last_error
    ↓ (3 次都失败后 raise)
[LocalAuthProvider.authenticate L157] 不 catch, 透传
    ↓
[user_authenticate_handler L89] 不 catch, 透传
    ↓
[bo_action_registry.invoke L204]
    L219-227: except Exception as e:
        return {'success': False, 'data': None, 'message': str(e)}    ← "disk I/O error"
```

### 1.2 关键 — 3 次 retry 是不是有 effect?

让我看 reader() 完整流程:

**第 1 次进 reader() (attempt=0)**:
- thread-local 没有, 走 L389 `_create_pooled_connection()` 建新 conn, yield 新 conn
- cursor.execute() 抛 disk I/O error
- with 块退出, 释放 conn
- L817 mark_error (thread-local 缓存里这个 pc)

**第 2 次进 reader() (attempt=1)**:
- thread-local 缓存有 pc
- L367: if (pc.is_valid() and not pc.last_io_error and pc.consecutive_errors < 3)
- pc.last_io_error = True (mark_error 触发了)
- 走 L372-387: 坏 connection, close + remove + rebuild
- L389: 新 conn, yield
- cursor.execute() **又抛** disk I/O error (db 状态没变, 新 conn 也 fail)
- mark_error 触发了, 落 L827 retry

**第 3 次进 reader() (attempt=2)**:
- 同上, close + rebuild, 又 fail
- 落到 L832 raise

**结果**: 3 次 fail 后 raise, BoActionRegistry 转 success=False, message="disk I/O error"

**核心问题**: **db 状态本身有问题, 重试 100 次都失败**! retry 只是时间浪费.

**真正问题**: db 状态差到任何新 conn 立即 disk I/O error. 这不是 retry 能解决的.

---

## 2. db 状态真实问题 (新发现!)

### 2.1 busy_timeout 在 yonaa = 5s

V007.20 改成 30s (sql_connection_pool.py L264):
```python
conn.execute("PRAGMA busy_timeout = 30000")
```

但 yonaa db 实际 busy_timeout = 5000 (5s)!

**说明 V007.20 修的 busy_timeout 30s 没在 yonaa 部署!**

### 2.2 audit_logs 11.7万行 + 4 路径并发写

- yonaa audit_logs: **117,849 行** (巨大!)
- 4 路径并发写: action_executor sync, async_audit_writer, WriteQueue, audit_async_queue
- WAL 模式: 4 路径都竞争写, 撞锁频繁
- 5s busy_timeout 不够 → 撞锁超时 → 操作失败

### 2.3 17:42:36 disk I/O error 集中爆发

- 10+ 并发 `_do_list` 在 1s 内都 disk I/O error
- 这是**撞锁 + 5s busy_timeout 不够 + 累积延迟** 共同作用

**真正修复 (跟 V007.20 完全一致)**:
1. busy_timeout 5s → 30s (V007.20 已有, **没部署**)
2. 写路径 retry (V007.20 已有)
3. 读路径 retry (V007.33 P0 — 修一半, V007.34 完整修)

---

## 3. 完整修复方案 (V007.34)

### 3.1 P0 修复 — 读路径 retry (3 行, 跟 V007.20 写路径完全一致)

**文件**: `meta/core/sql_adapters.py`
**位置**: L817-825 之间
**改动**: mark_error 后加 retry continue + 指数 backoff + jitter

**V007.33 改法 (3 行)**:
```python
# L817-825 加:
if "disk i/o error" in err_str or "database is locked" in err_str:
    if hasattr(self._pool, '_thread_connections'):
        ...
        self._pool._thread_connections[tid].mark_error(err_str)
        logger.warning(...)
    # [V007.34 FIX] 触发 continue — 跟 V007.20 写路径一致
    if attempt < max_retries - 1:
        import random as _random
        time.sleep(0.05 * (2 ** attempt) + _random.uniform(0, 0.02))  # 50/100/200ms
        continue
```

### 3.2 P0 修复 — busy_timeout 30s 部署 (1 行)

**文件**: `meta/core/sql_connection_pool.py` L264
**改动**: `5000` → `30000` (30s, 跟 V007.20 一致)

### 3.3 P0 修复 — local_auth provider 用 _data_source cache 复用 (1 行)

**文件**: `meta/services/user_authenticate.py` L35
**改动**: `_get_auth_provider` 改成在 server 启动时 init (跟 V007.24 cache 一致)

### 3.4 P1 修复 — audit_async_queue 单写互斥 (4 行)

**文件**: `meta/core/audit_async_queue.py` (待定位)
**改动**: 加 lock, 避免 4 路径并发写 audit_logs

### 3.5 P1 修复 — db backup cron (10 行)

**文件**: 新建 `scripts/backup_db.sh`
**改动**: 每天 03:00 备份 db 到 `/opt/app/shared/backups/`

### 3.6 P2 修复 — BoActionRegistry 不 catch 通用 Exception (5 行)

**文件**: `meta/core/bo_action_registry.py` L219
**改动**: 只 catch disk I/O error / database is locked 重试, 其他透传 (让 werkzeug 500 真实)

---

## 4. 修复实施顺序 (3h, 总计)

| 步骤 | 工作量 | 内容 | 谁做 |
|------|--------|------|------|
| 1 | 10 min | 改 sql_adapters.py:817 (3 行 retry) | 我 |
| 2 | 5 min | 改 sql_connection_pool.py:264 (busy_timeout 5s→30s) | 我 |
| 3 | 5 min | 改 user_authenticate.py:35 (init cache) | 我 |
| 4 | 30 min | 写单元测试 (retry 触发, busy_timeout 验证) | 我 |
| 5 | 15 min | 本地 50 并发测试 (sql_adapters + _do_list) | 我 |
| 6 | 30 min | 重新打包 deploy_bundle | 协调智能体 |
| 7 | 30 min | 部署到 yonaa (scp + 解压) | 协调智能体 |
| 8 | 15 min | 重启 server.py | 协调智能体 |
| 9 | 30 min | 线上 50 并发验证 + 30s busy_timeout 验证 | 我 |
| **总计** | **3h** | | |

---

## 5. 验证方案

### 5.1 单元测试

```python
# test_v007_34_read_retry.py
def test_read_retry_disk_io():
    """验证: 读路径 disk I/O error 重试 3 次后成功"""
    pool = SQLiteConnectionPool(test_db, ConnectionConfig())
    pool.initialize()
    adapter = SQLiteAdapter(pool)
    
    # 模拟: 第 1 次 cursor.execute 抛 disk I/O error, 第 2 次成功
    real_execute = sqlite3.Connection.execute
    fail_count = [0]
    def mock_execute(self, *a, **kw):
        if "SELECT * FROM x" in a[0]:
            if fail_count[0] < 1:
                fail_count[0] += 1
                raise sqlite3.OperationalError("disk I/O error")
        return real_execute(self, *a, **kw)
    
    with patch.object(sqlite3.Connection, 'execute', mock_execute):
        adapter.execute("SELECT * FROM x")
    
    assert fail_count[0] == 1  # 失败 1 次后成功
    assert pool._stats["retry_count"] == 1
```

### 5.2 集成测试 (50 并发 + 30s busy_timeout)

```python
# test_v007_34_50_concurrent.py
def test_50_concurrent_no_500():
    """50 并发 _do_list 不应返回 500 disk I/O error"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        futures = [ex.submit(call_bo_list, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    disk_errors = [r for r in results if r.get('error') == 'disk I/O error']
    assert len(disk_errors) == 0, f"{len(disk_errors)} disk I/O errors"

def test_login_concurrent_no_disk_io():
    """20 并发 login 不应返回 disk I/O error"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(login) for _ in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    disk_errors = [r for r in results if r.get('message') == 'disk I/O error']
    assert len(disk_errors) == 0, f"{len(disk_errors)} login disk I/O errors"
```

### 5.3 线上验证 (50 并发)

```python
# /tmp/verify_50c.py
import concurrent.futures
import urllib.request
import json

URLS = [
    'http://172.20.59.7:5001/api/v2/bo/domain?version_id=3&page_size=1000',
    'http://172.20.59.7:5001/api/v2/bo/service_module?version_id=3&page_size=5000',
    'http://172.20.59.7:5001/api/v2/bo/relationship?page=1&page_size=20&version_id=3',
    'http://172.20.59.7:5001/api/v2/bo/version?product_id=2&page_size=1000',
    'http://172.20.59.7:5001/api/v2/bo/business_object?version_id=3&page_size=100',
    'http://172.20.59.7:5001/api/v2/value-help/enum/relation_type?search_fields=code,name&page=1&page_size=200',
]

def hit(url):
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url), timeout=10)
        return resp.status, ''
    except urllib.error.HTTPError as e:
        body = e.read(200).decode(errors='ignore')
        return e.code, body

# 50 concurrent
results = {'200':0, '400':0, '401':0, '500':0, 'disk_io':0}
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    futures = [ex.submit(hit, URLS[i % len(URLS)]) for i in range(50)]
    for f in concurrent.futures.as_completed(futures):
        code, body = f.result()
        results[str(code)] = results.get(str(code), 0) + 1
        if 'disk I/O' in body: results['disk_io'] += 1

print(results)
assert results.get('500', 0) == 0, "500 errors found"
assert results['disk_io'] == 0, "disk I/O errors found"
print('PASS: 50 concurrent no disk I/O error')
```

### 5.4 线上 login 验证 (20 并发)

```python
# /tmp/verify_login.py
import concurrent.futures
import urllib.request
import json

def login():
    body = json.dumps({
        'action': 'user.authenticate',
        'username': 'admin',
        'password': 'admin123'
    }).encode()
    req = urllib.request.Request(
        'http://172.20.59.7:5001/api/v2/action/user.authenticate',
        data=body,
        headers={'Content-Type': 'application/json'}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        d = json.loads(resp.read())
        return d.get('success', False), d.get('message', '')
    except Exception as e:
        return False, str(e)

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    futures = [ex.submit(login) for _ in range(20)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

disk_io = [r for r in results if 'disk' in r[1].lower()]
print(f'success: {sum(1 for r in results if r[0])}/20, disk_io: {len(disk_io)}/20')
assert len(disk_io) == 0, f"{len(disk_io)} login disk I/O errors"
print('PASS: 20 concurrent login no disk I/O error')
```

---

## 6. 我之前错的地方 (回顾)

| 报告 | 我错的地方 | 正确 |
|------|-----------|------|
| V007.21 | fd 泄漏根因 | ❌ fd 372, 远没到上限 |
| V007.23 | inode race | ❌ 不存在 |
| V007.24 | 完整 cache | ✅ V007.24 cache 实际工作 |
| V007.25 | admin dim scope | ✅ 对 (独立 bug) |
| V007.26 V1 | 测错端口 | ❌ 测 8081 不是 5001 |
| V007.26 V2 | 推测 __file__ bug | ⚠️ 部分对 (lazy init 还在) |
| V007.26 V3 | retry 缺陷方向对, 1 行修复 | ✅ 对, 但漏了 V007.20 busy_timeout 没部署 |
| V007.27 | console 错误 | ✅ 现象正确 |
| V007.28 | 100% 复现并发 | ✅ 现象正确, 50 并发 80% 失败 (但现在 yonaa 业务 endpoint 没 500, 因为写路径修过) |
| V007.29 | 12 真因 | ❌ 太复杂, 1 个主因 |
| V007.33 | 精确根因 + 3 行修复 | ✅ 对方向, 但漏了 5 个细节 |
| **V007.34 (现在)** | **完整 6 个 P0/P1/P2 修复** | — |

---

## 7. 关键风险

| 风险 | 缓解 |
|------|------|
| 部署后 server.py 启动慢 | busy_timeout 30s 改动小, 影响小 |
| 30s busy_timeout 持锁过久 | WriteQueue 单线程, 不会多线程持锁 |
| db backup 占用磁盘 | 30 天后自动清理 |
| BoActionRegistry 不 catch 通用 Exception | 5xx 错误真实, 易调试 |
| 修 _get_auth_provider 改 lazy init | V007.24 cache 已经 lazy, 不破坏 |

---

## 8. Todo

| # | 任务 | 状态 |
|---|------|------|
| 1 | V007.21-V007.33 (13 个报告) | ✅ done |
| 2 | V007.34 详细分析 (本报告) | ✅ done |
| 3 | 改 sql_adapters.py:817 (3 行 retry) | 🚧 P0 |
| 4 | 改 sql_connection_pool.py:264 (busy_timeout 5s→30s) | 🚧 P0 |
| 5 | 改 user_authenticate.py:35 (init cache) | 🚧 P0 |
| 6 | 写单元测试 | 🚧 P0 |
| 7 | 本地 50 并发测试 | 🚧 P0 |
| 8 | 重新打包 + 部署 | 🚧 P0 |
| 9 | 重启 server.py | 🚧 P0 |
| 10 | 线上 50 并发验证 | 🚧 P0 |
| 11 | 线上 20 并发 login 验证 | 🚧 P0 |
| 12 | BoActionRegistry 不 catch 通用 Exception | 🚧 P2 |
| 13 | audit_async_queue 单写互斥 | 🚧 P2 |
| 14 | db backup cron | 🚧 P2 |

---

## 9. log_service v3 价值

**没有 v3, 这次诊断需要 SSH root@yonaa** (做不到).

| 能力 | 价值 |
|------|------|
| /api/fd?pid=26272 | 找 server.py 真实 log 路径 `/opt/app/shared/logs/backend-v20260725_001.log` |
| /api/log?file=全路径&grep=disk | 找 17:42:36 精确时间点 + 24 个 disk I/O 错误 |
| /api/env?pid=26272 | 确认 PWD + FLASK_ENV |
| /api/proc | 确认 server.py 跑 3h+ 没崩 |
| /api/system | 确认系统资源 OK |
| /api/db/health | 确认 db 96MB / wal 0 / integrity ok |

---

## 10. 协调智能体 — 立即决策

**我现在**:
1. 改 sql_adapters.py:817 (3 行, 已分析好)
2. 改 sql_connection_pool.py:264 (1 行 busy_timeout 5s→30s)
3. 改 user_authenticate.py:35 (1 行 lazy init cache)
4. 写单元测试
5. 50 并发本地测试
6. commit + 写部署文档

**协调智能体**:
1. 重新打包 deploy_bundle
2. 部署到 yonaa
3. 重启 server.py

**总计 3h, 6 个修复 (3 个 P0 + 3 个 P1/P2)**。

**是否立即执行?** Yes/No?
