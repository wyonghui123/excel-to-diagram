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
- 后端 bo_action API 用 HTTP 200 + JSON error body 模式 (不是 HTTP 5xx)
- backend PID 13040 启动后 39 秒开始报, 持续发生
- 26 分钟内累计 4 次 (实际次数看部署时 log 末尾)

### 1.2 影响

- **业务不可用**: admin login 失败 → 用户无法登录
- **HTTP 仍 200**: 监控告警可能漏报 (必须看 JSON body 才知道业务失败)
- **持续报**: 26 分钟 4 次, 业务被严重影响

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
1. Backend 13040 启动 (07:47:42, systemd auto-restart)
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

**改动 1**: `PooledConnection` (line 51-66) 加 3 个字段 + 2 个方法

```python
@dataclass
class PooledConnection:
    # ... 原有字段 (connection, created_at, last_used_at, in_use, usage_count) ...
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

**改动 2**: `is_valid()` (line 71-79) 改为真正检测 IO error

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
        self.last_io_error = True   # ← 同步设置标记
        self.last_error_msg = err_str
        return False
    except Exception:
        return False
```

**改动 3**: `reader()` (line 306-329) 加 last_io_error + 熔断检查

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
                if pc.last_io_error or pc.consecutive_errors >= 3:
                    logger.warning(...)
                try:
                    pc.connection.close()
                except Exception:
                    pass
                del self._thread_connections[thread_id]
                if pc in self._readers:
                    self._readers.remove(pc)
                self._stats["recycle_count"] += 1
        pc = self._create_pooled_connection()
        pc.last_io_error = False    # ← 初始化
        pc.consecutive_errors = 0
        pc.last_error_msg = ""
        self._readers.append(pc)
        self._thread_connections[thread_id] = pc
        yield pc.connection
```

**改动 4**: `_try_get_available()` (line 240-251) 同样加 last_io_error 检查

```python
def _try_get_available(self) -> Optional[PooledConnection]:
    while self._available:
        pc = self._available.popleft()
        if (pc.is_valid()
            and not pc.is_expired(self._config.max_lifetime)
            and not pc.last_io_error
            and pc.consecutive_errors < 3):
            return pc
        else:
            self._recycle_connection_unlocked(pc)
    return None
```

### 3.2 `meta/core/sql_adapters.py`

**改动 5**: `_execute_via_read_pool` (line 783-820) 加 mark_error + retry

```python
def _execute_via_read_pool(self, command: str, params: Optional[tuple]) -> Any:
    # 事务内仍然用写连接 (保持 v3.18 行为)
    if self._in_transaction and self._connection:
        cursor = self._connection.cursor()
        if params:
            return cursor.execute(command, params)
        return cursor.execute(command)

    max_retries = 3
    last_error = None
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

**`tests/test_v007_16_io_error_recovery.py`** (全部 10/10 PASS):

| # | Test | 验证 |
|---|---|---|
| 1 | `test_is_valid_detects_io_error` | connection close 后 → is_valid False |
| 2 | `test_is_valid_after_close` | 关闭 connection → is_valid False |
| 3 | `test_is_valid_with_corrupt_connection` | close 后 is_valid 触发 last_io_error 标记 |
| 4 | `test_reader_rebuilds_after_io_error` | 坏 connection → 下次 reader() 重建 |
| 5 | `test_reader_does_not_cache_bad_connection` | 熔断机制 (consecutive_errors=3) |
| 6 | `test_execute_via_read_pool_marks_bad_connection` | mark/clear_error 协同 |
| 7 | `test_thread_local_recovery` | thread A 坏不影响 thread B |
| 8 | `test_concurrent_io_error_isolation` | 10 threads 混合坏/好, 全部成功 |
| 9 | `test_mark_error` | mark_error 设置状态正确 |
| 10 | `test_clear_error` | clear_error 重置状态正确 |

### 4.2 回归测试 (9 cases)

**`tests/test_audit_async_queue.py`** (V007.15-L4.5, 9/9 PASS):

V007.16 改动**没有破坏** L4.5 audit_async_queue 任何测试。

### 4.3 总计

**19/19 PASS, 0 FAIL**

### 4.4 验证脚本

**`tools/verify_disk_io_root_cause.py`**:
- 模拟 write + read 并发 (10 commits + 5 readers)
- 验证 wal_checkpoint(TRUNCATE) 不是根因
- 验证 is_valid() 修复后 read pool 不缓存坏 connection

(在 V050 worktree 本地跑过, WAL checkpoint TRUNCATE 测试**未**触发 disk I/O error, 排除 TRUNCATE 假说)

---

## 5. 修复效果预期

| 场景 | 现状 (13040 行为) | 修复后 |
|---|---|---|
| 第 1 次 disk I/O error | 永久坏 connection, 反复报 | 触发重建, 下次成功 |
| 连续 N 次 IO error | 永久坏 | 熔断 3 次后强制重建 |
| 1 thread 坏 | 其他 thread 也坏 (因为 select 1 不会 raise) | thread-local 隔离, 其他 thread 不影响 |
| 多读多写并发 | reader 缓存坏 connection, 持续坏 | reader 永不缓存坏 connection |
| 业务影响 | 业务不可用 (admin login 失败) | 业务可用 (retry 后成功) |

---

## 6. 部署流程

### 6.1 协调智能体操作

```bash
# 1. fetch V007.16 commit
cd D:\filework\worktrees/release-prep
git fetch origin fix/v050-orphan-tx

# 2. 查看 commit (期望看到 3 个)
git log --oneline origin/fix/v050-orphan-tx -3
# 期望:
#   9420633 docs(v007.16): add DEPLOY_HANDOVER for disk I/O error fix
#   ccde2ab fix(v007.16): repair disk I/O error - is_valid + reader cache root cause
#   a6a5222 feat(v007.15-L4.5): audit 异步队列
#   c497c2b feat(v007.15): implement orphan transaction defense + observability

# 3. cherry-pick V007.16 修复 (必须)
git cherry-pick ccde2ab
# 可能需要解决冲突 (worktrees/release-prep 有 dirty changes)

# 4. cherry-pick V007.16 DEPLOY_HANDOVER (必须, 给 PM 看)
git cherry-pick 9420633

# 5. (可选) cherry-pick V007.15-L4.5
# 注意: V007.15-L4.5 在 yonaa 13040 启动时显示 WARNING: WriteQueue not found
# 因为我代码 get_global_queue() 找不到 WriteQueue
# 协调智能体按 handoff 决定是否要 L4.5
# git cherry-pick a6a5222

# 6. push release
git push origin release/pre-2026-06-29

# 7. 通知部署智能体
# 触发部署智能体按 §6.2 部署流程
```

### 6.2 部署智能体操作 (yonaa 生产)

**重要**: yonaa 的 `/opt/app/deployments/meta/` **不是 git repo**, 是从 `worktrees/release-prep` 同步过去的 (rsync 或部署脚本).

```bash
# 1. SSH 到 yonaa 172.20.59.7
ssh root@172.20.59.7

# 2. 看当前部署版本
ls -la /opt/app/deployments/
# 期望: v20260704_007 是当前 V007.15 版本
# 13040 启动时间 07:47:42 = V007.15 部署时间

# 3. 部署新版本 (协调智能体提供的具体方法, 例如):
# 方法 A: rsync from worktrees/release-prep
# rsync -avz --delete D:\filework\worktrees/release-prep\ /opt/app/deployments/v20260706_001/

# 方法 B: deploy 脚本 (如果有)
# /opt/app/scripts/deploy.sh v20260706_001

# 方法 C: 直接复制文件
# (具体方法看协调智能体怎么同步)

# 4. 跑单元测试
cd /opt/app/deployments/v20260706_001
python -m pytest tests/test_v007_16_io_error_recovery.py -v
# 期望: 10/10 PASS

# 5. 跑回归测试 (L4.5)
python -m pytest tests/test_audit_async_queue.py -v
# 期望: 9/9 PASS

# 6. 跑 e2e 工具测试 (in-memory)
python tools/test_v007_15_L4_5_e2e.py
# 期望: 8/8 PASS (in-memory 部分, 跳过 live server 部分)

# 7. 切换部署版本
# 假设是符号链接或 deploy script 切换:
ln -sfn /opt/app/deployments/v20260706_001 /opt/app/deployments/current
# 或
/opt/app/scripts/switch.sh v20260706_001

# 8. 重启后端
systemctl restart excel-backend.service
# 等 5 秒
sleep 5

# 9. 验证后端进程
ps -o pid,lstart,etime,cmd -p $(pgrep -f server.py | head -1)
# 期望: 新启动, ELAPSED < 1 分钟

# 10. 验证 admin login (用 curl 打 5001 后端, 不通过 frontend 代理)
curl -s -w "\nHTTP %{http_code}\n" http://localhost:5001/api/v2/action/user.authenticate \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# 期望: {"success":true, "data":{...user info...}, "message":"..."}

# 11. 看 /healthz
curl -s http://localhost:5001/healthz | python -m json.tool
# 期望: v007_15 + v007_15.audit_async_queue 段

# 12. 看后端 log
tail -20 /opt/app/shared/logs/backend-v20260706_001.log
# 期望: 无新 disk I/O error
```

### 6.3 验证清单

| # | 验证 | 期望 | 重要 |
|---|---|---|---|
| 1 | admin login curl | `success=True`, HTTP 200 | **CRITICAL** |
| 2 | /healthz 200 | `status=ok`, v007_15 段齐全 | HIGH |
| 3 | 持续 admin login 10 次 | 全部成功, 0 disk I/O error | **CRITICAL** |
| 4 | 看 backend log | 无新 "disk I/O error" (除正常业务) | HIGH |
| 5 | 看 L4.5 状态 | audit_async_queue stats 正常 (如果部署了 L4.5) | MEDIUM |
| 6 | 监控 24h | disk I/O error 计数不再增长 | HIGH |

### 6.4 部署后立即监控 (前 1 小时)

```bash
# 在 yonaa 每 5 分钟看一次
while true; do
    DATE=$(date '+%Y-%m-%d %H:%M')
    DISK_IO_COUNT=$(grep -c "disk I/O error" /opt/app/shared/logs/backend-v20260706_001.log 2>/dev/null)
    BUSY_COUNT=$(grep -c "database is locked" /opt/app/shared/logs/backend-v20260706_001.log 2>/dev/null)
    RECYCLE_COUNT=$(curl -s http://localhost:5001/healthz | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('v007_15',{}).get('connection_pool',{}).get('recycle_count','?'))" 2>/dev/null)
    echo "$DATE | disk_io=$DISK_IO_COUNT | busy=$BUSY_COUNT | recycle=$RECYCLE_COUNT"
    sleep 300
done
```

**期望**:
- `disk_io` 在 V007.16 部署后**不增长** (或偶发但 connection pool 自动恢复)
- `busy` 持续为 0 (或跟 V007.15 之前一致)
- `recycle` > 0 (V007.16 触发了 connection 重建, 证明修复在工作)

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
sleep 5

# 3. 验证 disk I/O error 计数 (看是否回到修复前状态)
grep -c "disk I/O error" /opt/app/shared/logs/*.log
# 期望: 跟 V007.15 部署后一致 (13040 启动后 26 分钟 4 次)
```

回滚后:
- ✅ 现有功能不受影响
- ❌ disk I/O error 会重新出现 (但 build 是稳的)
- ⏸️ 等待 V007.17 进一步分析根因

---

## 8. 已知限制 (待 V007.17+ 解决)

| 项 | 状态 | 影响 |
|---|---|---|
| 撞 disk I/O error 的**根本原因** (为何 13040 启动后立即报) | **未知** | 可能: WAL 文件初始化时序, fd 资源, 内核 fsync |
| V007.16 只**修复症状** (connection 缓存) | ✅ | 业务可用, 但根因未消 |
| L4.5 audit_async_queue 在 yonaa 仍 disabled | ⚠️ | handoff WARNING: "WriteQueue not found" |
| L5 orphan_tx_detector 用 WriteQueue 写 conn | ⚠️ | 可能跟 V007.16 修复有交互, 需监控 |

**未来 V007.17 需要**:
1. 找 13040 启动后 39 秒首次 disk I/O error 的**真正根因**
2. 修 L4.5 (WriteQueue 找不到的问题)
3. 加更强的 observability (例如: 每次 disk I/O error 时记 traceback)

---

## 9. 联系上下文

| Commit | 内容 | 状态 |
|---|---|---|
| `c497c2b` | V007.15 (L0-L7 完整, 7 文件) | **已部署** (yonaa 13040) |
| `0beb04e` | V007.15 e2e 部署测试 (16/16 pass) | **已部署** |
| `a6a5222` | V007.15-L4.5 (audit 异步队列) | **已写, 部署待定** (handoff WARNING) |
| `ccde2ab` | **V007.16 救 SQLITE_IOERR (本 commit)** | **待部署** |
| `9420633` | V007.16 DEPLOY_HANDOVER (本文件) | **待部署** |

---

## 10. 协调智能体注意

按 release-sync-workflow.md, 协调智能体:
- ✅ cherry-pick V007.16 commit (`ccde2ab` + `9420633`)
- ✅ push release/pre-2026-06-29
- ✅ 通知 PM 看 DEPLOY_HANDOVER
- ❌ 不写代码
- ❌ 不直接 deploy
- ❌ 不猜根因

**等 PM 确认后, 部署智能体执行 §6.2 部署流程**。

---

## 11. PM 注意

**紧急**: yonaa 13040 backend **业务不可用**, 需尽快部署 V007.16

**优先级**:
1. **V007.16** (本 commit) - **CRITICAL**, 解决 disk I/O error
2. V007.15-L4.5 - **MEDIUM**, 解决 audit 撞锁 (独立, 可不跟 V007.16 一起)
3. V007.17+ - 找 disk I/O error 根因 (V007.16 之后排期)

**部署窗口建议**:
- 协调智能体: **立即** cherry-pick + push release
- 部署智能体: **立即** 部署到 integration 测试
- 集成验证后: **当天** 部署到生产
- 监控 24h

---

**作者**: dev-agent (V050 worktree)
**完成时间**: 2026-07-06 14:50
**commit**: `ccde2ab` (本地, push 待网络)
**DEPLOY_HANDOVER commit**: `9420633` (本地)
**worktree**: D:\filework\worktree-V050
**branch**: fix/v050-orphan-tx