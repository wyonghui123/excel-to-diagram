# DB 损坏预防：3 大方案细化设计

> [!!!] 本文是基于 2026-06-05 DB 损坏排查的修复方案 [!!!]
> [!!!] 目标：从根本上消除 B-tree 损坏、根因级解决 migration 中断、消除并发写入冲突 [!!!]

---

## 方案 1：WAL Checkpoint 改 TRUNCATE 模式

### 1.1 当前现状

**代码位置**：[sql_adapters.py:857](file:///d:/filework/excel-to-diagram/meta/core/sql_adapters.py#L857)

```python
conn.execute(
    "PRAGMA wal_checkpoint({0})".format(
        self._write_queue._config.checkpoint_mode  # 默认 PASSIVE
    )
)
```

**问题**：
- `PASSIVE` 不强制写回，可能留下未 checkpoint 的 WAL frame
- `db_health_monitor.py:92` 监控也用 `PASSIVE`，**告警时 WAL 已无法挽救**

### 1.2 三种 checkpoint 模式对比

| 模式 | 行为 | 阻塞读 | 阻塞写 | 强制刷写 | 适用场景 |
|------|------|--------|--------|---------|---------|
| **PASSIVE** | 尽力 checkpoint，不阻塞 | ❌ | ❌ | ❌ | 运行时（高并发） |
| **FULL** | 等待读完成，再 checkpoint | ✅ | ✅ | ✅ | 低峰期 |
| **TRUNCATE** | FULL + 截断 WAL 文件 | ✅ | ✅ | ✅ | **关闭时 / 定时任务** |
| **RESTART** | TRUNCATE + 重置 WAL 头 | ✅ | ✅ | ✅ | 极端恢复 |

### 1.3 推荐方案

```python
# meta/core/sql_adapters.py - 3 处配置
# 默认改为 FULL（更安全），关闭时强制 TRUNCATE

# 1. 默认配置（运行时）：FULL 模式
self._write_queue._config.checkpoint_mode = 'FULL'

# 2. 周期任务（每 100 commits）：TRUNCATE
if self._commit_counter >= 100:
    self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    self._commit_counter = 0

# 3. 启动时：先 TRUNCATE 清理残留 WAL
def startup(self):
    self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # 然后才打开连接服务

# 4. 关闭时：最终 TRUNCATE
def shutdown(self):
    self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    self._connection.close()
```

### 1.4 实施步骤

| 步骤 | 操作 | 文件 |
|------|------|------|
| 1 | 修改 `checkpoint_mode` 默认值 `PASSIVE` → `FULL` | `sql_adapters.py:857` |
| 2 | 启动时添加 TRUNCATE | `server.py:create_app` |
| 3 | `_cleanup_resources` 中添加 TRUNCATE | `server.py:267-284` |
| 4 | `db_health_monitor.py:92` 改 FULL（强制刷写监控点） | `db_health_monitor.py` |
| 5 | 添加测试：模拟 WAL 残留 → 启动后是否清理 | `tests/test_wal_checkpoint.py` |

### 1.5 性能影响

| 模式 | 写延迟 | 读延迟 | 磁盘 I/O | 适用 |
|------|--------|--------|---------|------|
| PASSIVE | +0% | +0% | 低 | 高频写 |
| FULL | +5-10ms | +5-10ms | 中 | **生产推荐** |
| TRUNCATE | +20-50ms | +20-50ms | 高（一次性截断） | 关闭 / 周期 |

**权衡**：方案推荐 FULL 模式，**关闭/周期用 TRUNCATE**。高并发场景用 PASSIVE 监控 + 周期 TRUNCATE 兜底。

---

## 方案 2：Migration 事务原子化

### 2.1 当前现状

**代码位置**：`run_ssot_migration.py`

```python
# 问题代码：每个 phase 无独立事务
conn.execute("ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT")
# ... 50 行中间操作 ...
conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated ...")
# 中间任何一行崩溃 → B-tree 半成品 → 损坏
```

**历史证据**：
- `_preflight_db_integrity_check` 专门清理 `_bak_*` 残留表 = **历史上有过 migration 中断**
- 2026-06-05 的损坏：`Tree 115 page 115 cell 0: 2nd reference to page 258` = **索引 B-tree 创建到一半被杀**

### 2.2 原子化设计

#### 2.2.1 Migration 基类

```python
# meta/migrations/base.py (新增)
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)

class MigrationBase:
    """
    Migration 原子化基类：
    1. 操作前：自动备份（.bak.migration.<timestamp>）
    2. 操作中：每个 phase 独立事务
    3. 操作后：完整性检查
    4. 失败：自动回滚到备份
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.backup_path = None

    def run(self):
        """模板方法：子类实现 phases()"""
        self._backup()
        try:
            with self._connect() as conn:
                self._pre_check(conn)
                self.phases(conn)
                self._post_check(conn)
            logger.info(f"[Migration] {self.__class__.__name__} OK")
        except Exception as e:
            logger.error(f"[Migration] {self.__class__.__name__} FAILED: {e}")
            self._rollback()
            raise

    def phases(self, conn):
        """子类必须实现：每个 phase 一个独立事务"""
        raise NotImplementedError

    @contextmanager
    def _phase_transaction(self, conn, phase_name: str):
        """每个 phase 独立事务：失败自动 ROLLBACK"""
        logger.info(f"[Migration] Phase: {phase_name} START")
        conn.execute("BEGIN IMMEDIATE")  # 立即获取写锁（方案 3）
        try:
            yield conn
            conn.execute("COMMIT")
            logger.info(f"[Migration] Phase: {phase_name} OK")
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"[Migration] Phase: {phase_name} FAILED: {e}")
            raise

    def _backup(self):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = f"{self.db_path}.bak.migration.{ts}"
        shutil.copy2(self.db_path, self.backup_path)
        logger.info(f"[Migration] Backup: {self.backup_path}")

    def _rollback(self):
        if self.backup_path and Path(self.backup_path).exists():
            shutil.copy2(self.backup_path, self.db_path)
            logger.warning(f"[Migration] Rolled back to {self.backup_path}")
        else:
            logger.error(f"[Migration] No backup to rollback!")

    def _pre_check(self, conn):
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            raise RuntimeError(f"Pre-check FAILED: {result[0]}")

    def _post_check(self, conn):
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            raise RuntimeError(f"Post-check FAILED: {result[0]}")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield conn
        finally:
            conn.close()
```

#### 2.2.2 示例：重写 run_ssot_migration.py

```python
# meta/database/run_ssot_migration.py (重写)
from meta.migrations.base import MigrationBase

class SSOTMigration(MigrationBase):

    def phases(self, conn):
        # Phase 1: 每个 phase 独立事务
        with self._phase_transaction(conn, "audit_logs_upgrade"):
            self._upgrade_audit_logs(conn)

        with self._phase_transaction(conn, "drop_updated_at"):
            self._drop_updated_at_columns(conn)

        with self._phase_transaction(conn, "create_indexes"):
            self._create_indexes(conn)

    def _upgrade_audit_logs(self, conn):
        """Phase 1: audit_logs 表升级"""
        try:
            conn.execute("ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise

        conn.execute(
            "UPDATE audit_logs SET created_at_epoch = "
            "(strftime('%s', created_at) * 1000) "
            "WHERE created_at_epoch IS NULL AND created_at IS NOT NULL"
        )
        # COMMIT 由 phase_transaction 上下文管理器负责

    def _drop_updated_at_columns(self, conn):
        """Phase 2: 删除 updated_at 列（每个表一个 phase）"""
        tables = ['products', 'versions', 'business_objects']
        for table in tables:
            try:
                # SQLite 不支持 DROP COLUMN，需要重建表
                # 这里简化：只记录需要后续处理
                logger.info(f"  Mark {table} for updated_at removal")
            except Exception:
                raise

    def _create_indexes(self, conn):
        """Phase 3: 创建索引"""
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated "
            "ON audit_logs(object_type, object_id, action, created_at_epoch DESC)"
        )


if __name__ == "__main__":
    import os
    db_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'architecture.db'
    ))
    SSOTMigration(db_path).run()
```

### 2.3 关键特性

| 特性 | 实现 | 防什么 |
|------|------|-------|
| **自动备份** | `_backup()` 启动前 .bak.migration.<ts> | 任何失败可回滚 |
| **Phase 独立事务** | `_phase_transaction` BEGIN/COMMIT/ROLLBACK | 部分成功不污染 |
| **完整性检查** | `_pre_check` + `_post_check` | 立即发现损坏 |
| **自动回滚** | `_rollback()` 用备份覆盖 | 失败自动恢复 |
| **日志追溯** | 每个 phase START/OK/FAILED | 排查根因 |

### 2.4 实施步骤

| 步骤 | 操作 | 风险 |
|------|------|------|
| 1 | 新建 `meta/migrations/base.py` | 低（新增文件） |
| 2 | 重写 `run_ssot_migration.py` 用 `MigrationBase` | 中（涉及数据） |
| 3 | 重写 `meta/scripts/migration_ssot_stage1.py` | 中 |
| 4 | 重写 `meta/migrations/add_performance_indexes*.py` | 中 |
| 5 | 添加测试：`tests/test_migration_atomic.py` | 低 |

---

## 方案 3：写操作串行化（`BEGIN IMMEDIATE`）

### 3.1 当前现状

**代码位置**：`sql_adapters.py:706-709`

```python
self._cursor.execute("PRAGMA journal_mode=WAL")
self._cursor.execute("PRAGMA synchronous=NORMAL")
self._cursor.execute("PRAGMA foreign_keys = ON")
self._cursor.execute("PRAGMA busy_timeout = 30000")
```

**问题**：
- 默认事务模式 = `BEGIN DEFERRED`（延迟获取写锁）
- **多进程并发写** → 第二个写者触发 `SQLITE_BUSY`
- busy_timeout=30s 是**事后补救**，不是预防
- `synchronous=NORMAL` 在断电时**可能丢失最后一次 commit 的数据**（不致损坏，但数据丢失）

### 3.2 SQLite 事务模式对比

| 模式 | 行为 | 锁时机 | 并发写 | 适用 |
|------|------|--------|--------|------|
| **DEFERRED**（默认） | 第一次读时获取 SHARED，第一次写时升级 RESERVED | 延迟 | ⚠️ 升级时冲突 | 读多写少 |
| **IMMEDIATE** | BEGIN 立即获取 RESERVED | 立即 | ✅ 串行写 | **写多并发** |
| **EXCLUSIVE** | BEGIN 立即获取 EXCLUSIVE | 立即 | ✅ 唯一 | 单进程 |

### 3.3 推荐方案

```python
# meta/core/sql_adapters.py - 改写事务开始逻辑

class SqliteAdapter:

    def begin_write(self):
        """所有写操作统一入口：用 IMMEDIATE 模式"""
        # BEGIN IMMEDIATE 立即获取 RESERVED 锁
        # 阻止其他写者（他们会立即收到 SQLITE_BUSY）
        # 读操作不受影响（仍可 SHARED）
        self._connection.execute("BEGIN IMMEDIATE TRANSACTION")
        self._in_transaction = True

    def commit(self):
        if self._in_transaction:
            self._connection.execute("COMMIT")
            self._in_transaction = False
            # 每次 commit 后立即 checkpoint（FULL 模式）
            self._connection.execute("PRAGMA wal_checkpoint(FULL)")
```

**关键改动**：
- 写操作 → `BEGIN IMMEDIATE` 立即抢写锁
- 写完 → `COMMIT` + `PRAGMA wal_checkpoint(FULL)`
- 第二个写者 → 立即收到 `SQLITE_BUSY`（不阻塞 30s）

### 3.4 性能与并发权衡

| 指标 | DEFERRED + busy_timeout=30s | IMMEDIATE + 全量写锁 |
|------|------------------------------|----------------------|
| 写并发 | 错乱（升级冲突） | **串行**（无错乱） |
| 写延迟 | 0~30s（不确定） | < 1ms（队列串行） |
| 读并发 | 不阻塞 | **不阻塞**（WAL 读快照） |
| 吞吐（写） | 5~20/s（受冲突影响） | **50~200/s**（稳定） |
| 复杂度 | 高（要处理 BUSY） | **低**（不需要处理） |

**结论**：对于元数据驱动系统（写少、读多 + 偶发批量），`BEGIN IMMEDIATE` 是**更优选择**。

### 3.5 busy_timeout 保留意义

虽然改用 `BEGIN IMMEDIATE`，仍保留 `busy_timeout` 作为**最后防线**：

```python
# 场景 1：长事务中的写者等待（如 report 生成持有 5s）
# IMMEDIATE 模式下，新写者会立即失败
# 但配合应用层重试，可以接受

# 场景 2：DDL 操作（CREATE INDEX）需要更长时间
# 单独用 BEGIN EXCLUSIVE 模式，临时关闭其他连接
```

### 3.6 实施步骤

| 步骤 | 操作 | 风险 |
|------|------|------|
| 1 | 添加 `begin_write()` 方法到 `SqliteAdapter` | 低 |
| 2 | 替换所有 `BEGIN` / `BEGIN TRANSACTION` 为 `BEGIN IMMEDIATE` | 中（需要全面排查） |
| 3 | 写操作后强制 `PRAGMA wal_checkpoint(FULL)` | 中 |
| 4 | 应用层处理 `SQLITE_BUSY`（重试 3 次） | 低 |
| 5 | 添加并发测试：`tests/test_concurrent_write.py` | 低 |

### 3.7 应用层重试模板

```python
# meta/core/retry.py (新增)
import time
import sqlite3
import logging

logger = logging.getLogger(__name__)

def retry_on_busy(func, max_retries=3, base_delay=0.1):
    """SQLITE_BUSY 自动重试"""
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if 'database is locked' not in str(e):
                raise
            delay = base_delay * (2 ** attempt)  # 指数退避
            logger.warning(
                f"SQLITE_BUSY, retry {attempt+1}/{max_retries} after {delay}s"
            )
            time.sleep(delay)
    raise sqlite3.OperationalError("Max retries exceeded")
```

---

## 三方案联合部署时间线

### 第 1 周：方案 1（WAL Checkpoint）

```
Day 1-2: 修改 sql_adapters.py 默认模式
Day 3:   添加 startup/shutdown checkpoint
Day 4-5: 测试 + 监控 WAL 大小
```

**预期**：WAL 大小从 284KB → 50KB 以下，强制刷写率 100%

### 第 2 周：方案 3（写串行化）

```
Day 1-2: SqliteAdapter.begin_write() 方法
Day 3:   替换所有写事务入口
Day 4-5: 应用层重试 + 并发测试
```

**预期**：写并发冲突归零，吞吐稳定

### 第 3 周：方案 2（Migration 原子化）

```
Day 1-2: MigrationBase 基类
Day 3-4: 重写关键 migration（run_ssot_migration 等）
Day 5:   备份/回滚测试
```

**预期**：migration 中断不再产生 `_bak_*` 残留，B-tree 不再半创建

### 第 4 周：监控与验证

```
- db_health_monitor 添加：WAL 趋势、checkpoint 频率、B-tree 一致性
- 集成测试：模拟各种故障场景
- 文档：SOP for migration / restart / backup
```

---

## 监控指标

| 指标 | 阈值 | 来源 |
|------|------|------|
| WAL size | < 50KB | `db_health_monitor` |
| Checkpoint 频率 | > 1/min | 新增 |
| integrity_check 状态 | ok | `_preflight_db_check` |
| 写冲突次数 | < 5/min | 应用层埋点 |
| migration 失败率 | 0% | migration logger |

---

## 风险与回退

| 方案 | 风险 | 回退方案 |
|------|------|---------|
| 方案 1 | FULL checkpoint 阻塞 5-10ms | 改回 PASSIVE + 周期 TRUNCATE |
| 方案 2 | Migration 备份占磁盘 | 7 天后自动清理旧备份 |
| 方案 3 | 应用层重试增加复杂度 | 监控 `SQLITE_BUSY` 次数，> 10/min 立即回退 |

---

_本文档为设计稿，实施前需在 worktree 中验证_
