# SQLite 生产环境 P0 保护手册 (v3.18+)

> ⚠️ **重要**: 本项目**生产环境也使用 SQLite** (architecture.db)。
> 多进程并发写 SQLite 是 **P0 数据损坏风险**。
> 本文档说明所有 P0 保护措施和运维红线。

---

## 1. 损坏根因 (Why)

SQLite WAL 模式虽然支持多进程并发**读**，但**写必须串行**：

- 多个进程同时打开同一个 SQLite DB
- 每个进程都有自己的写连接（WriteQueue）
- 进程 A 持有写锁时被 `taskkill /F` 强制杀死
- 进程 B 启动时看到不完整的 WAL → `database disk image is malformed`
- 恢复时 `architecture_recovered.db` 仍然带 stale -wal/-shm

**触发场景**:
- 多 CI/session 并发运行 `service_manager.ps1 restart`
- 手动 `python waitress_server.py` 与 `service_manager` 启动的后端并存
- gunicorn 配置 `workers > 1`（单 worker 是硬性要求）

---

## 2. P0 保护机制 (v3.18+)

### 2.1 跨进程文件锁

**文件**: `meta/.architecture.lock`

- 所有后端启动器（gunicorn/waitress/pytest）在启动时获取文件锁
- Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` (非阻塞)
- Linux: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`
- 锁文件内容: `<PID>\n<timestamp>\n`
- 持有锁的进程退出时（atexit/SIGTERM）释放锁
- 启动器检测到 stale lock（PID 已死）会自动清理

**实施位置**:
- `gunicorn_conf.py::on_starting()` → `_acquire_db_lock()`
- `waitress_server.py::_on_starting()` → `_acquire_db_lock()`
- `service_manager.ps1::Stop-Service()` → 删除 lock（兜底）

### 2.2 启动时完整性校验 (fail-fast)

**位置**:
- `gunicorn_conf.py::_check_db_integrity_at_startup()`
- `waitress_server.py::_check_db_integrity_at_startup()`

**行为**:
```
$ python d:\filework\test.py
或
$ gunicorn -c gunicorn_conf.py meta.server:app
→ 启动时执行 PRAGMA integrity_check
→ 若 DB 损坏: 打印修复方案并 sys.exit(1)
```

### 2.3 gunicorn workers 硬性限制

**位置**: `gunicorn_conf.py::_check_workers_safe()`

```python
if workers > 1:
    sys.stderr.write('║  [P0 启动失败] workers=2 会导致 SQLite 损坏!  ║')
    sys.exit(1)
```

**禁止**:
- ❌ 改 `gunicorn_conf.py::workers = 2`
- ❌ 启动时传 `gunicorn --workers 2`
- ❌ 用 `gunicorn` 多进程模式（fork 模式不兼容 SQLite）

**必须**:
- ✅ `workers = 1` + `worker_class = 'gthread'` + `threads = 8`
- ✅ 用 threads 而非 processes 处理并发
- ✅ 需要更高并发 → 部署多个独立实例 + 外部 LB，但**不能**共享同一个 DB

### 2.4 Snapshot 机制使用 SQLite Backup API

**位置**: `d:\filework\test.py::_sqlite_backup_copy()`

**改进**:
- 旧: `shutil.copy2()` 简单文件复制（不原子，多进程下不一致）
- 新: `sqlite3.Connection.backup()` 内部处理 WAL + 跨连接一致性

### 2.5 WAL Checkpoint 调优

**位置**: `meta\core\sql_write_queue.py::WriteQueueConfig`

| 参数 | 旧值 | 新值 | 说明 |
|------|------|------|------|
| `checkpoint_interval` | 50 | **10** | 更频繁地 flush WAL |
| `checkpoint_mode` | "FULL" | **"TRUNCATE"** | 不阻塞读、不会因 SQLITE_BUSY 失败 |

**FULL vs TRUNCATE**:
- `FULL`: 阻塞所有读连接执行 checkpoint, 容易失败
- `TRUNCATE`: 截断 WAL 到 0, 不会阻塞读
- `PASSIVE`: 不阻塞, 但可能不真正 flush

### 2.6 服务管理器杀孤儿进程

**位置**: `scripts\service_manager.ps1::Kill-AllOrphanBackends()`

**行为**:
- 每次 `start` / `restart` / `stop` 前扫描所有 python.exe
- 识别 cmd 含 `meta\server.py` / `waitress_server.py` 的进程
- 跳过 service_manager 已知 PID（status.json）
- `taskkill /F /PID` 其余孤儿 backend
- 等待 3s 让 SQLite 释放文件锁

### 2.7 启动器 PID 互斥 (test.py)

**位置**: `d:\filework\test.py::_kill_orphan_backends()`

每次 `_restart_backend_safe()` 调用前后杀孤儿进程，防止多 session 并发重启。

---

## 3. 运维红线 (DO NOT)

### ❌ 禁止操作

1. **禁止** 在生产同时跑 2 个 `meta.server.py`
2. **禁止** 改 `gunicorn_conf.py::workers` 为 > 1
3. **禁止** 用 `fork` 模式（gunicorn `sync` worker 等）
4. **禁止** 手动 `taskkill /F` 持有 DB 锁的进程（先 `service_manager stop`）
5. **禁止** 直接 `rm meta/architecture.db*`（先 `service_manager stop`）
6. **禁止** 多个 session 同时跑 `service_manager restart`
7. **禁止** 把 `meta/architecture.db` 放到网络文件系统（NFS/SMB）
8. **禁止** 同时把 backend 跑在多台机器共享同一 DB

### ✅ 必须操作

1. ✅ **必须** 用 `service_manager.ps1 start/stop/restart` 而非手动启停
2. ✅ **必须** 监控 `meta/.architecture.lock` 是否存在（应随服务启停）
3. ✅ **必须** 监控 `meta/architecture.db-wal` 大小（应 < 10MB）
4. ✅ **必须** 定期跑 `python d:\filework\test.py --force-recover-db` 做灾难恢复演练
5. ✅ **必须** 部署前修改 `gunicorn_conf.py::bind` 为 `0.0.0.0:3010`（或反向代理到 80/443）
6. ✅ **必须** 部署多实例时用 **外部 PostgreSQL**（不能用本地 SQLite）

---

## 4. 故障排查

### 4.1 "database disk image is malformed"

**症状**:
```
sqlite3.DatabaseError: database disk image is malformed
```

**紧急恢复** (按顺序尝试):
```powershell
# 1. 停止所有后端
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop

# 2. 删除所有 -wal/-shm 残留（这些是损坏源）
Remove-Item d:\filework\excel-to-diagram\meta\architecture.db-wal -Force
Remove-Item d:\filework\excel-to-diagram\meta\architecture.db-shm -Force

# 3. 尝试从快照恢复
python d:\filework\test.py --restore-snapshot

# 4. 启动后端
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start

# 5. 验证
python -c "import sqlite3; c=sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db',timeout=5); print(c.execute('PRAGMA integrity_check').fetchone()[0])"
# 应输出: ok
```

### 4.2 "P0 启动失败: DB 锁被占用"

**症状**:
```
[WAITRESS][P0 启动失败] DB 锁被占用, 退出
  锁文件: D:\filework\excel-to-diagram\meta\.architecture.lock
```

**原因**: 另一个实例已持有锁

**排查**:
```powershell
# 查看锁文件中的 PID
Get-Content d:\filework\excel-to-diagram\meta\.architecture.lock
# 输出: <PID>\n<timestamp>\n

# 检查该 PID 是否存活
Get-Process -Id <PID> -ErrorAction SilentlyContinue

# 如果是 stale 锁（PID 已死）:
# 选项 A: 让 service_manager 自动清理（启动时检测 stale）
# 选项 B: 手动删除
Remove-Item d:\filework\excel-to-diagram\meta\.architecture.lock -Force
```

### 4.3 "P0 启动失败: workers=2 会导致 SQLite 损坏!"

**原因**: 有人改了 `gunicorn_conf.py::workers`

**修复**:
```python
# gunicorn_conf.py
workers = 1  # 必须保持 1
threads = 8  # 用 threads 并发
worker_class = 'gthread'
```

### 4.4 WAL 文件持续增长 (>100MB)

**症状**: `meta/architecture.db-wal` 越来越大

**排查**:
```python
import sqlite3
c = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db', timeout=5)
# 强制 checkpoint
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.close()
```

**根治**:
- 确认 `WriteQueueConfig.checkpoint_interval = 10` (已修复)
- 确认 `WriteQueueConfig.checkpoint_mode = "TRUNCATE"` (已修复)
- 确认没有孤儿 backend 进程（`Kill-AllOrphanBackends` 已修复）

---

## 5. 监控指标 (Production Monitoring)

```yaml
# 推荐监控项
- name: db_lock_exists
  check: file_exists("meta/.architecture.lock")
  alert_if: not check  # 服务在跑时锁必须存在

- name: db_wal_size
  check: file_size("meta/architecture.db-wal") < 10*1024*1024
  alert_if: not check  # WAL > 10MB 是异常

- name: db_integrity
  check: run("python -c 'import sqlite3; c=sqlite3.connect(\"meta/architecture.db\"); r=c.execute(\"PRAGMA integrity_check\").fetchone()[0]; c.close(); assert r==\"ok\"'")
  alert_if: not check  # 每日跑一次

- name: backend_count
  check: process_count("python.exe", cmd~="meta.server.py") == 1
  alert_if: not check  # 严格 = 1

- name: temp_file_count
  check: file_count_glob("test_temp/*db-wal") < 100
  alert_if: not check
```

---

## 6. 灾难恢复流程 (DR)

### 6.1 DB 完全损坏且无快照

**最坏情况**: 没有任何可恢复的快照

**恢复步骤**:
1. 停止所有后端
2. 保留损坏的 DB 作为事故证据（不要删）
3. 从 Git 仓库 `meta/architecture.db.baseline` 恢复
4. 重新生成测试数据
5. **复盘根因** - 写事故报告，更新本文档

### 6.2 baseline 文件

`meta/architecture.db.baseline` 是**只读**的基础快照，应该:
- ✅ 每次生产部署前备份
- ✅ Git 跟踪
- ❌ 永远不要直接用 .db 文件覆盖 baseline

---

## 7. 迁移到 PostgreSQL (未来)

当需要更高并发时（>100 RPS）:

1. 修改 `DataSourceType.POSTGRESQL` 适配器为生产可用（当前为预留实现）
2. 部署 PostgreSQL 14+ (推荐主从)
3. 用 `pg_dump` 迁移数据
4. 部署多 gunicorn 实例 + 共享 PG
5. 关闭 `gunicorn_conf.py::_check_workers_safe()` 限制
6. 移除 `meta/.architecture.lock` 机制

**风险**:
- PostgreSQL 适配器目前**未经生产验证**，预计需要 2-3 周适配
- 数据迁移需 downtime
- 所有 SQL 需验证 PG 兼容性（特别是 M7 抽象的 FTS、JSONB）

---

## 8. 变更日志

| 日期 | 版本 | 变更 | 作者 |
|------|------|------|------|
| 2026-06-07 | v3.18 | 初始 P0 修复：跨进程文件锁、fail-fast、gunicorn 防御、WAL 调优、Snapshot API 化 | fix_workflow |

---

**联系**: 任何 DB 损坏事件必须在 1 小时内报告 + 写事故报告。
