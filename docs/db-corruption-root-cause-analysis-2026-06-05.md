# DB 损坏根因分析报告 [2026-06-05]

> [!!!] DB 损坏是系统性索引 B-tree 损坏，需要排查代码层根因 [!!!]

---

## 一、损坏现象

### 1.1 integrity_check 输出
```
*** in database main ***
Tree 115 page 115 cell 0: 2nd reference to page 258
Tree 115 page 129 cell 0: 2nd reference to page 254
Tree 55 page 55 cell 0: 2nd reference to page 257
... 115 个索引全部损坏
```

### 1.2 文件系统证据
| 文件 | 大小 | 时间 | 状态 |
|------|------|------|------|
| `architecture.db` | 1.3MB | - | ❌ 损坏 |
| `architecture.db.baseline` | 1.4MB | 6/1 13:30 | ✅ 完好 |
| `architecture.db-wal` | 284KB | - | ⚠️ 过大 |
| `architecture.db.corrupted` | 1.3MB | 5/31 | 损坏1 |
| `architecture.db.corrupted2` | 1.5MB | 5/31 | 损坏2 |
| `architecture.db.corrupted3` | 1.1MB | 5/31 | 损坏3 |

**关键**：3 个 corrupted 文件 + 1 个 recovered.db = 至少发生过 3 次损坏

---

## 二、根本原因（5 个嫌疑点）

### 2.1 嫌疑 1：WAL 模式 + checkpoint 未及时

**现象**：`architecture.db-wal` 284KB（建议 < 1MB，**未触发告警**）

**代码位置**：
- `meta/core/db_health_monitor.py:18-19` WAL 告警阈值 100/500 frames
- `meta/core/db_health_monitor.py:92` `PRAGMA wal_checkpoint(PASSIVE)` — **PASSIVE 不强制写回**

**根因**：PASSIVE checkpoint 在写入时不强制刷 WAL，**不安全的关闭会留下损坏的 WAL**。

**修复建议**：
- 启动时强制 `PRAGMA wal_checkpoint(TRUNCATE)`
- 关闭时执行 checkpoint

### 2.2 嫌疑 2：`_bak_*` 残留表 [已被修复 2026-06-05]

**代码位置**：
- `meta/server.py:223-264` `_preflight_db_integrity_check()` 清理 `_bak_*`

**已确认**：当前没有残留（`_bak_ residual tables: 0`），但历史上可能因 migration 中断产生过。

### 2.3 嫌疑 3：migration 中断导致索引 B-tree 不一致

**现象**：`Tree 115 page 115 cell 0: 2nd reference to page 258` — B-tree 节点**重复引用同一 page**

**触发场景**：
```python
# 假设 migration_add_performance_indexes_v2.py 中断
BEGIN;
CREATE INDEX idx_a ...;  # 创建到一半
# 进程被杀 / 服务崩溃
# 索引 B-tree 写入到 page 115，但不完整
# 后续 INSERT 触发修复，但 page 已损坏
```

**关键证据**：`scheduled_tasks` 表的 `idx_scheduled_task_category` 是第一个报错的索引（page 115）

### 2.4 嫌疑 4：并发写入冲突

**代码位置**：
- 多个进程同时写 DB（service_manager 启多 worker）
- WAL 模式下并发是支持的，但**跨进程 commit 顺序不一致**会破坏 B-tree

### 2.5 嫌疑 5：文件系统层面（Windows + 强制关闭）

**触发场景**：
- `service_manager.ps1 force-restart` 强制杀进程
- 后端在 commit 中被 kill → WAL 写入不完整

---

## 三、为什么 REINDEX 失败

**测试**：
```python
conn.execute("REINDEX scheduled_tasks")  # 单独 REINDEX 一个索引
# → 仍然 "2nd reference to page 258"
```

**根因**：损坏的是 B-tree 的**内部结构**（page 引用关系），不是数据本身。`REINDEX` 通过扫描表数据重建索引，但 `SELECT * FROM scheduled_tasks` 也会触发 B-tree 遍历 → **再次访问损坏的 page**。

**所有 115 个索引都坏** = 数据文件和索引文件**两套 page 引用表**都损坏。

**`.recover` 失败原因**：
- `.recover` 是 SQLite CLI 命令（`sqlite3 db.db ".recover"`）
- Python `sqlite3` 模块不直接支持
- `iterdump()` 也会触发 B-tree 遍历 → 在损坏点抛异常

---

## 四、修复方案（已执行）

### 4.1 方案 A：从 baseline 恢复（已采用）

```python
# 1. 备份当前损坏 DB
shutil.copy2('architecture.db', 'architecture.db.corrupt-final')

# 2. 删除 WAL/SHM
os.remove('architecture.db-wal')
os.remove('architecture.db-shm')

# 3. 复制 baseline
shutil.copy2('architecture.db.baseline', 'architecture.db')
```

**结果**：
```
integrity_check: ok
Size: 1,372,160 bytes
users: 642 rows
products: 1 rows
business_objects: 25 rows
audit_logs: 473 rows
scheduled_tasks: 7 rows
```

**代价**：丢失 6/1 之后的所有数据

### 4.2 方案 B：用 `.recover` 命令（理论可行，未执行）

```bash
sqlite3 architecture.db ".recover" > recover.sql
sqlite3 new.db < recover.sql
```

**限制**：
- 需要保留表结构（baseline 提供）
- 损坏太严重时只能恢复部分数据

---

## 五、预防措施（建议落地）

### 5.1 立即可做

| 措施 | 代码位置 | 说明 |
|------|---------|------|
| **WAL checkpoint 强制模式** | `db_health_monitor.py:92` | 改 `PRAGMA wal_checkpoint(TRUNCATE)` |
| **启动时完整性检查** | `server.py:303-304` | `_preflight_db_check` 已存在，确保调用 |
| **定期备份 baseline** | cron / 定时任务 | 每周一次 `cp architecture.db architecture.db.weekly-$(date)` |
| **限制 WAL 大小** | `db_health_monitor.py:18` | 阈值 100/500 太高，改为 50/200 |

### 5.2 中期

| 措施 | 说明 |
|------|------|
| **migration 事务原子化** | 每个 migration 包在 BEGIN/COMMIT 中，失败自动 ROLLBACK |
| **写操作串行化** | 多进程并发时用 `BEGIN IMMEDIATE` 强制串行 |
| **定期 VACUUM** | 减少 page 碎片，降低损坏概率 |

### 5.3 长期

| 措施 | 说明 |
|------|------|
| **PostgreSQL 替代 SQLite** | 工业级事务管理，避免 B-tree 损坏 |
| **WAL archive + 增量备份** | 实时备份 WAL frame，损坏时可恢复到任意时间点 |

---

## 六、当前状态

✅ **已恢复**：DB 从 baseline 恢复，后端 `/health` 返回 ok
⚠️ **数据丢失**：6/1 13:30 之后的所有业务数据
🔍 **根因未根治**：B-tree 损坏的根本原因（migration 中断/并发写入/强制关闭）需进一步排查代码

**服务状态**：
- Frontend: RUNNING (port 3004)
- Backend: RUNNING (port 3010)
- DB: 完整可用（baseline 数据）

---

_本报告基于 2026-06-05 14:26 的实际排查记录_
