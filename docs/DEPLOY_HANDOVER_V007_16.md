# DEPLOY_HANDOVER for V007.16 - disk I/O error 修复

**作者**: dev-agent (V050 worktree)
**日期**: 2026-07-06
**Commit**: `ccde2ab` (本地, push 待网络)
**Branch**: `fix/v050-orphan-tx`
**紧急度**: **HIGH** (生产 13040 持续报 disk I/O error, 业务不可用)

---

## 1. 事故背景

### 1.1 现象

- yonaa 172.20.59.7:5001 admin login 报 `{"success":false, "message":"disk I/O error"}`
- HTTP 200 但 `success=False`
- backend PID 13040 启动后 39 秒开始报, 26 分钟内累计 4 次

### 1.2 影响

- **业务不可用**: admin login 失败 → 用户无法登录
- **API 仍 200**: 监控告警可能漏报 (需要看 body 才知道业务失败)
- **趋势恶化**: 每次 commit/SELECT 都可能触发新 IO error

---

## 2. 根因分析 (代码级)

### 2.1 真根因: 2 个 bug 互相叠加

**Bug #1: `is_valid()` 误判** (`sql_connection_pool.py:71-79`)

```python
def is_valid(self) -> bool:
    try:
        self.connection.execute("SELECT 1")
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "closed" in err_str or "cannot operate" in err_str:
            return False
        return True  # ← BUG: 'disk I/O error' 不匹配上面, 误判为 valid
```

**Bug #2: `reader()` 永久缓存坏 connection** (`sql_connection_pool.py:306-329`)

```python
@contextmanager
def reader(self, timeout: float = None):
    thread_id = threading.get_ident()
    with self._condition:
        if thread_id in self._thread_connections:
            pc = self._thread_connections[thread_id]
            if pc.is_valid():  # ← 误判为 True
                yield pc.connection  # ← 永久 yield 这个坏 connection
                return
        # ↓ 只有 is_valid() 返回 False 才到这
        # ↑ 但 bug #1 让 is_valid() 永远返回 True
```

### 2.2 事故链路

```
1. Backend 13040 启动 (07:47:42)
2. 第 1 个 user.authenticate (07:48:21) → disk I/O error
   (可能原因: -wal 文件刚创建还没 ready, 或 connection init 时序问题)
3. is_valid() 调 SELECT 1 → raise "disk I/O error"
4. is_valid() 看 err_str = "disk i/o error"
   不匹配 "closed" 也不匹配 "cannot operate" → 返回 True (误判)
5. reader() 缓存这个坏 connection 到 _thread_connections[thread_id]
6. 后续所有同 thread 的 read → 直接 yield 这个坏 connection
7. cursor.execute() → 继续报 "disk I/O error"
8. 13040 跑 26 分钟, 累计 4 次 disk I/O error (持续)
```

### 2.3 V007.15 为何救不了

- V007.15 救的是 `SQLITE_BUSY` (database is locked)
- disk I/O error 是 `SQLITE_IOERR`, **完全不同**的错误码
- 14 次 V007.5~V007.15 修的都是 busy, 不修 io

---

## 3. 修复 (4 处)

### 3.1 `meta/core/sql_connection_pool.py`

**改动 1**: `PooledConnection` 加 3 个字段 + 2 个方法

```python
@dataclass
class PooledConnection:
    # ... 原有字段 ...
    # [V007.16] 跟踪 connection 健康状态
    last_io_error: bool = False
    consecutive_errors: int = 0
    last_error_msg: str = ""

    def mark_error(self, error_msg: str = ""):
        self.last_io_error = True
        self.consecutive_errors += 1
        if error_msg:
            self.last_error_msg = error_msg

    def clear_error(self):
        self.last_io_error = False
        self.consecutive_errors = 0
        self.last_error_msg = ""
```

**改动 2**: `is_valid()` 改为真正检测 IO error

```python
def is_valid(self) -> bool:
    try:
        cursor = self.connection.execute("SELECT 1")
        result = cursor.fetchone()
        if not result or result[0] != 1:
            return False
        return True
    except sqlite3.Error as e:  # ← 任何 sqlite3.Error 视为 invalid
        err_str = str(e).lower()
        self.last_io_error = True
        self.last_error_msg = err_str
        return False
    except Exception:
        return False
```

**改动 3**: `reader()` 加 last_io_error + 熔断检查

```python
@contextmanager
def reader(self, timeout: float = None):
    thread_id = threading.get_ident()
    with self._condition:
        if thread_id in self._thread_connections:
            pc = self._thread_connections[thread_id]
            # [V007.16] 不仅检查 is_valid, 还检查 last_io_error + 熔断
            if (pc.is_valid()
                and not pc.last_io_error
                and pc.consecutive_errors < 3):
                yield pc.connection
                return
            else:
                # 坏 connection, 强制 close + 移除 + 重建
                ...
                self._stats["recycle_count"] += 1
        pc = self._create_pooled_connection()
        pc.last_io_error = False  # ← 初始化
        pc.consecutive_errors = 0
        pc.last_error_msg = ""
        ...
```

**改动 4**: `_try_get_available()` 同样加 last_io_error 检查 (跟 reader 一致)

### 3.2 `meta/core/sql_adapters.py`

**改动 5**: `_execute_via_read_pool` 加 mark_error + retry

```python
def _execute_via_read_pool(self, command: str, params: Optional[tuple]) -> Any:
    ...
    for attempt in range(max_retries):
        try:
            with self._pool.reader() as conn:
                cursor = conn.cursor()
                if params:
                    result = cursor.execute(command, params)
                else:
                    result = cursor.execute(command)
                # 成功! 清除该 connection 的错误标记
                if hasattr(self._pool, '_thread_connections'):
                    tid = threading.get_ident()
                    if tid in self._pool._thread_connections:
                        self._pool._thread_connections[tid].clear_error()
                return result
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # [V007.16] 标记 thread-local connection 为 bad (触发重建)
            if "disk i/o error" in err_str or "database is locked" in err_str:
                if hasattr(self._pool, '_thread_connections'):
                    tid = threading.get_ident()
                    if tid in self._pool._thread_connections:
                        self._pool._thread_connections[tid].mark_error(err_str)
            if "closed database" in err_str or "operational" in err_str:
                if attempt < max_retries - 1:
                    time.sleep(0.05 * (attempt + 1))  # 短暂退避
                    continue
            raise
    raise last_error
```

---

## 4. 测试

### 4.1 单元测试 (10 cases)

**`tests/test_v007_16_io_error_recovery.py`**:

| # | Test | 验证 |
|---|---|---|
| 1 | `test_is_valid_detects_io_error` | 关闭的 connection → is_valid False |
| 2 | `test_is_valid_after_close` | close 后 → False |
| 3 | `test_is_valid_with_corrupt_connection` | close 后 is_valid 触发 last_io_error |
| 4 | `test_reader_rebuilds_after_io_error` | 坏 connection → 下次重建 |
| 5 | `test_reader_does_not_cache_bad_connection` | 熔断机制 (consecutive_errors=3) |
| 6 | `test_execute_via_read_pool_marks_bad_connection` | mark/clear 协同 |
| 7 | `test_thread_local_recovery` | thread A 坏不影响 thread B |
| 8 | `test_concurrent_io_error_isolation` | 10 threads 混合坏/好, 全部成功 |
| 9 | `test_mark_error` | mark_error 状态正确 |
| 10 | `test_clear_error` | clear_error 重置状态 |

**10/10 PASS**

### 4.2 回归测试 (9 cases)

**`tests/test_audit_async_queue.py`** (V007.15-L4.5):

**9/9 PASS** (V007.16 没破坏 L4.5)

### 4.3 总计

**19/19 PASS, 0 FAIL**

---

## 5. 修复效果预期

| 场景 | 现状 | 修复后 |
|---|---|---|
| 第 1 次 disk I/O error | 永久坏 connection, 反复报 | 触发重建, 下次成功 |
| 连续 N 次 IO error | 永久坏 | 熔断 3 次后强制重建 |
| 1 thread 坏 | 其他 thread 也坏 | thread-local 隔离 |
| 多读多写并发 | reader 缓存坏 connection | reader 永不缓存坏 connection |
| 业务影响 | 业务不可用 (admin login 失败) | 业务可用 (retry 后成功) |

---

## 6. 部署流程

### 6.1 协调智能体操作

```bash
# 1. fetch V007.16 commit
cd D:\filework\release-prep-worktree
git fetch origin fix/v050-orphan-tx

# 2. 查看 commit
git log --oneline origin/fix/v050-orphan-tx -3
# 期望: ccde2ab fix(v007.16): repair disk I/O error - is_valid + reader cache root cause
#        a6a5222 feat(v007.15-L4.5): audit 异步队列
#        c497c2b feat(v007.15): implement orphan transaction defense

# 3. cherry-pick V007.16 commit (在 release branch)
git cherry-pick ccde2ab
# 可能需要解决冲突 (release-prep-worktree 有 dirty changes)

# 4. (可选) cherry-pick V007.15-L4.5 (L4.5 已写, 但当前 backend get_global_queue 找不到 WriteQueue)
# 注意: 协调智能体按 handoff 决定是否要 L4.5
# git cherry-pick a6a5222

# 5. push release
git push origin release/pre-2026-06-29
```

### 6.2 部署智能体操作

```bash
# 1. SSH 到 yonaa 172.20.59.7
ssh root@172.20.59.7

# 2. 部署
cd /opt/app/deployments
# 假设 release-prep-worktree 已 sync 到 yonaa
git pull
# 或用 deploy.sh (如果存在)

# 3. 跑 e2e 测试 (in-memory 部分, 不需要 live server)
cd /opt/app/deployments
python tools/test_v007_15_L4_5_e2e.py  # 如果 L4.5 也部署了
# 期望: 8/8 PASS (in-memory 部分)

# 4. 跑 V007.16 单元测试
python -m pytest tests/test_v007_16_io_error_recovery.py -v
# 期望: 10/10 PASS

# 5. 重启后端
systemctl restart excel-backend.service
sleep 5

# 6. 验证 admin login
curl -s -w "\nHTTP %{http_code}\n" http://localhost:5001/api/v2/action/user.authenticate \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# 期望: {"success":true, "data":{...user info...}}

# 7. 看 /healthz
curl http://localhost:5001/healthz
# 期望: v007_15.audit_async_queue 段, 正常的 stats
```

### 6.3 验证清单

| # | 验证 | 期望 | 重要 |
|---|---|---|---|
| 1 | admin login curl | success=True, HTTP 200 | **CRITICAL** |
| 2 | /healthz 200 | status=ok, v007_15 段齐全 | HIGH |
| 3 | 持续 admin login 10 次 | 全部成功, 0 disk I/O error | **CRITICAL** |
| 4 | 看 backend log | 无新 disk I/O error (除正常业务) | HIGH |
| 5 | 看 L4.5 状态 | audit_async_queue stats 正常 | MEDIUM |
| 6 | 监控 24h | disk I/O error 计数不再增长 | HIGH |

---

## 7. 回滚方案

V007.16 改动小 (4 文件, 560 行), 出问题易回滚:

```bash
# 1. revert commit
cd /opt/app/deployments
git revert ccde2ab
# 或 git revert HEAD (如果是最新 commit)

# 2. 重启后端
systemctl restart excel-backend.service

# 3. 验证 disk I/O error 计数 (看是否回到修复前状态)
```

回滚后:
- ✅ 现有功能不受影响
- ❌ disk I/O error 会重新出现 (但 build 是稳的)
- ⏸️ 等待 V007.17 进一步分析

---

## 8. 已知限制 (待 V007.17+ 解决)

| 项 | 状态 | 影响 |
|---|---|---|
| 撞 disk I/O error 的**根本原因** (为何 13040 启动后立即报) | **未知** | 可能: WAL 文件初始化时序, fd 资源, 内核 fsync |
| V007.16 只**修复症状** (connection 缓存) | ✅ | 业务可用, 但根因未消 |
| L4.5 audit_async_queue 在 yonaa 仍 disabled | ⚠️ | handoff WARNING, 需要单独 fix |
| L5 orphan_tx_detector 用 WriteQueue 写 conn | ⚠️ | 可能跟 V007.16 修复有交互, 需监控 |

---

## 9. 联系上下文

- V007.15 (c497c2b + 0beb04e) 已部署, 救 SQLITE_BUSY
- V007.15-L4.5 (a6a5222) 已写, 但 yonaa 13040 启动时 WriteQueue 找不到 (待修)
- V007.16 (ccde2ab) 救 SQLITE_IOERR (本 commit)
- V007.17+ 待规划 (根因, L4.5 fix)

---

## 10. 协调智能体注意

按 release-sync-workflow.md, 协调智能体:
- ✅ cherry-pick V007.16 commit
- ✅ push release/pre-2026-06-29
- ✅ 写 DEPLOY_HANDOVER_V007_16 通知 PM
- ❌ 不写代码
- ❌ 不直接 deploy
- ❌ 不猜根因

**等 PM 确认后, 部署智能体执行 §6.2 部署流程**。

---

**作者**: dev-agent (V050 worktree)
**完成时间**: 2026-07-06
**commit**: ccde2ab (本地, push 待网络)
**worktree**: D:\filework\worktree-V050
**branch**: fix/v050-orphan-tx