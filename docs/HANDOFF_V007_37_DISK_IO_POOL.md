# DEV-AGENT HANDOFF: V007.37 Disk I/O Error on Excel Export

**接收方**: Dev Agent V047
**发送方**: 部署智能体 (V007.36 已部署)
**时间**: 2026-07-08 07:05
**优先级**: 🔴 P0 (业务阻塞)
**环境**: yonaa (172.20.59.7, log_service 9101)

---

## 1. 现象

用户操作：**导出 Excel** → 立即报 **disk I/O error** (127 次累计)
- 之前 V007.25 时代导出 Excel 正常（无 disk I/O error）
- V007.34 (sql_adapters retry) + V007.35 (sql_connection_pool mmap/cache) 部署后第一次导出 Excel 触发
- V007.34 retry 触发 76 次，3/3 全失败

## 2. 部署状态确认 ✅ (不是部署问题)

| 检查 | 状态 |
|------|------|
| server.py 启动 | ✅ 5001 listening (PID 30999) |
| db integrity | ✅ ok |
| V007.36 BUG-FIX | ✅ startup_checks._is_debug() 默认 'True' |
| V007.34 retry | ✅ 触发了 76 次但 3/3 失败 |
| V007.35 mmap/cache | ✅ 已部署 |
| BUG-V027 pt1+pt2 | ✅ 全部在 zip |
| 9/9 invariant | ✅ PASS |
| log_service 9101 | ✅ 在跑 |

**这不是部署问题，是 V007.35 引入的新 bug。**

## 3. 错误调用栈 (从 yonaa backend-v20260708_001.log)

```
File "/opt/app/deployments/meta/services/auth_provider.py", line 157, in authenticate
    cursor = self.ds.execute(...)
File "/opt/app/deployments/meta/core/sql_adapters.py", line 779, in execute
    result = self._execute_via_read_pool(command, params)
File "/opt/app/deployments/meta/core/sql_adapters.py", line 801, in _execute_via_read_pool
    with self._pool.reader() as conn:
File "/opt/app/deployments/meta/core/sql_connection_pool.py", line 397, in reader
    pc = self._create_pooled_connection()
File "/opt/app/deployments/meta/core/sql_connection_pool.py", line 282, in _create_pooled_connection
    conn = self._create_connection()
File "/opt/app/deployments/meta/core/sql_connection_pool.py", line 254, in _create_connection
    conn.execute("PRAGMA journal_mode=WAL")
sqlite3.OperationalError: disk I/O error
```

**关键错误位置**: `sql_connection_pool.py:254` `PRAGMA journal_mode=WAL`

## 4. 根因分析

### 4.1 之前为什么不发生？
- V007.25 时代，连接池**复用**连接，不频繁重建
- 导出 Excel 走**写路径**（事务），不强制重建连接
- `PRAGMA journal_mode=WAL` 只在连接**首次创建**时执行一次

### 4.2 现在为什么发生？
- V007.35 (mmap/cache) 改了连接池逻辑
- 导出 Excel 时**大量重建连接**（pool 耗尽？长事务释放？）
- 每次**新连接**都执行 `PRAGMA journal_mode=WAL`
- db 已是 WAL 模式 → 重复执行 PRAGMA 写元数据 → 磁盘抖动 → `disk I/O error`

### 4.3 V007.34 retry 为什么不够？
- V007.34 retry 范围: `_execute_via_read_pool` 整体重试
- 但**新连接创建** (`_create_pooled_connection`) 是 pool 内部行为
- 3 次重试都死在 pool 内部 retry 不到

## 5. db 状态 (从 log_service /api/db/health)

```
db_path: /opt/app/deployments/meta/architecture.db
size_mb: 96.2
wal_mb: 0.0          # WAL 空, 所有数据已 flush
shm_mb: 0
journal: wal         # 已经是 WAL 模式
busy_ms: 5000        # busy_timeout 5s (V007.20 已部署)
integrity: ok
users: 6, products: 3, audit_logs: 117908
management_dimensions: 0   # 业务表空 (跟磁盘 I/O 无关, 业务问题)
role_dimension_scopes: 2
```

## 6. 系统健康 (从 log_service /api/system)

```
total_fds: 300   # 健康
load: 0.01       # 负载低
```

## 7. 需要的 Fix (V007.37)

### 7.1 P0 Fix #1: sql_connection_pool.py:254 — PRAGMA 重复执行

**问题**: 每次创建新连接都执行 `PRAGMA journal_mode=WAL`，重复执行触发 IO error

**修法 (建议)**:
```python
def _create_connection(self):
    conn = sqlite3.connect(self.db_path, ...)
    # [V007.37 BUG-FIX] PRAGMA journal_mode=WAL 只在首次创建执行
    # db 已是 WAL 模式时, 重复 PRAGMA 会触发磁盘元数据写入 → IO error
    if not getattr(self, '_journal_mode_set', False):
        conn.execute("PRAGMA journal_mode=WAL")
        self._journal_mode_set = True
    # 其他 PRAGMA 同理 (mmap_size, cache_size)
    conn.execute("PRAGMA mmap_size=...")
    conn.execute("PRAGMA cache_size=...")
    return conn
```

**注意**: mmap_size 和 cache_size 是**每次连接都需要**（不是 db 级），保留；只 journal_mode 去重。

### 7.2 P0 Fix #2: query_service.py — export 路径 retry

**问题**: `query_service._try_apply_dimension_scope` (BUG-V027 pt2 改的位置) 没有 retry 包裹

**修法**: 用 V007.34 同样的 retry 包裹器包裹整个 `_try_apply_dimension_scope` 调用

### 7.3 P1 Fix #3: 加重试次数 + 退避

V007.34 当前 3 次重试 → 改为 **5 次**，backoff 0.05s → 0.5s 指数增长

### 7.4 P1 Fix #4: yonaa 升级 log_service v3.5

dev-agent v3.5 含 `/api/sqlite/load`, `/api/iostat` 端点 — 这些端点 yonaa 还没升级（`not found`），升级后可重现 IO error 场景做更细诊断

## 8. Invariant V8d (新增, 防 PRAGMA 重复执行)

在 `tools/verify_bundle.py` 加：

```python
def check_v8d_zip_pool_pragma_idempotent() -> tuple:
    """V8d. [V007.37 BUG-FIX] sql_connection_pool._create_connection 的 PRAGMA journal_mode=WAL 
    必须只在首次创建时执行 (防止重复执行触发 disk I/O error)
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            pool = zf.read("meta/core/sql_connection_pool.py").decode("utf-8", errors="ignore")
        # 检查 _create_connection 里有 _journal_mode_set 标志 (或类似幂等保护)
        if "journal_mode=WAL" not in pool:
            return (False, "找不到 PRAGMA journal_mode=WAL 调用 (期望保留)")
        if "_journal_mode_set" not in pool and "journal_mode_set" not in pool and "_pragmas_set" not in pool:
            return (False, "PRAGMA journal_mode=WAL 没有幂等保护 (V007.37 BUG 复发)")
        return (True, "PRAGMA journal_mode=WAL 有幂等保护标记 (_journal_mode_set)")
    except Exception as e:
        return (False, f"读 sql_connection_pool.py 失败: {e}")
```

## 9. 验证步骤 (dev-agent 完成后)

```powershell
# 1. 9/9 + V8d invariant PASS
python tools/verify_bundle.py

# 2. deploy.sh 部署 (跟 V007.36 一样流程)

# 3. yonaa 远程验证 (我跑):
$LS = "http://172.20.59.7:9101"
$BE = "http://172.20.59.7:5001"

# 100 次 BOAction (重现场景)
1..100 | ForEach-Object {
    $r = Invoke-RestMethod "$BE/api/v2/action/user.authenticate" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}' -TimeoutSec 15
    $r.success
}

# disk I/O error 计数 (应该 = 0)
$log = Invoke-RestMethod "$LS/api/log?file=/opt/app/shared/logs/backend-v*.log&lines=3000&grep=disk" -TimeoutSec 10
($log.output -split "`n" | Where-Object { $_ -match "disk I/O" }).Count

# export BO 业务测试 (user 报告的具体场景)
$token = (Invoke-RestMethod "$BE/api/v2/action/user.authenticate" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}').data.token
$r = Invoke-RestMethod "$BE/api/v2/bo/business_object?pageSize=1000&export=excel" -Headers @{Authorization="Bearer $token"} -TimeoutSec 60
$r.success
```

## 10. 关键文件路径 (Windows 本地)

| 文件 | 路径 |
|------|------|
| 错误源头 | `D:\filework\release-prep-worktree\meta\core\sql_connection_pool.py` |
| 错误源头 #2 | `D:\filework\release-prep-worktree\meta\core\sql_adapters.py` (retry 已加, 检查是否覆盖 _create_pooled_connection) |
| export 路径 | `D:\filework\release-prep-worktree\meta\services\query_service.py` (BUG-V027 pt2 改的位置) |
| Invariant 验证 | `D:\filework\release-prep-worktree\tools\verify_bundle.py` |
| 当前 HEAD | `d4af6c3` (V007.36 BUG-FIX) |

## 11. yonaa 真实数据 (无需 SSH 跑)

部署智能体会通过 yonaa 9101 log_service 跑以下端点取数：
- `/api/db/health` — db 完整性
- `/api/system` — fd + load
- `/api/log?file=...&grep=disk` — disk I/O error 计数
- `/api/log?file=...&grep=V007.34` — retry 触发计数
- `/api/sqlite/load?count=200&table=users` — 压力测试 (dev-agent v3.5 升级后才能用)

---

**部署智能体已经做完**:
1. ✅ V007.36 BUG-FIX 已部署
2. ✅ 9/9 invariant PASS
3. ✅ 后端 5001 listening, db integrity ok
4. ✅ disk I/O error 真实数据已采集 (127 次)

**dev-agent 请接手**:
1. 写 V007.37 fix (P0 #1 + P0 #2)
2. 加 invariant V8d
3. 跟 V007.36 一样流程: 修改 → 验证 → commit → 通知部署智能体打包

**注意**: V007.36 commit hash `d4af6c3`, branch `release/pre-2026-06-29`