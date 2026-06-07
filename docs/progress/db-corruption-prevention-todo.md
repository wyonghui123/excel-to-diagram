# DB 损坏预防 3 大方案 — 待办登记

> **登记日期**: 2026-06-05
> **状态**: 待后续处理（用户明确"这个记录待办后续需要处理"）
> **来源文档**: [docs/db-corruption-prevention-design.md](file:///d:/filework/excel-to-diagram/docs/db-corruption-prevention-design.md)
> **背景**: 2026-06-05 DB 损坏修复 + 3 大方案设计稿

---

## ⚠️ 重要安全提醒

**这 3 大方案涉及 DB schema/行为修改**：
- 方案 1: WAL Checkpoint 模式变更
- 方案 2: Migration 事务原子化
- 方案 3: 写操作串行化 BEGIN IMMEDIATE

**任何一处出错可能再次损坏 DB**。**实施前必须**：
1. 在 worktree 隔离（不是当前 `feature/bo-action-v3` 主分支）
2. 完整 DB 备份（参考 2026-06-05 备份 `meta/architecture.db.pre-corrupt-fix.1780673774.bak`）
3. 端到端验证（写测试、跑批、回滚测试）
4. 监控（db_health_monitor.py 增强）

---

## 📋 待办 1: 方案 1 — WAL Checkpoint 改 TRUNCATE

**目标**: 从 `PASSIVE`（运行时）改 `FULL`（默认）+ 启动/关闭用 `TRUNCATE`

### 实施步骤（来自设计文档 §1.4）

| 步骤 | 操作 | 文件 | 风险 |
|------|------|------|:---:|
| 1 | 修改 `checkpoint_mode` 默认值 `PASSIVE` → `FULL` | `meta/core/sql_adapters.py:857` | 🟢 低 |
| 2 | 启动时添加 TRUNCATE | `meta/server.py:create_app` | 🟢 低 |
| 3 | `_cleanup_resources` 中添加 TRUNCATE | `meta/server.py:267-284` | 🟢 低 |
| 4 | `db_health_monitor.py:92` 改 FULL（强制刷写监控点） | `meta/core/db_health_monitor.py` | 🟡 中 |
| 5 | 添加测试：模拟 WAL 残留 → 启动后是否清理 | `meta/tests/test_wal_checkpoint.py` | 🟢 低 |

### 预期收益
- WAL size: 140KB → 50KB 以下（强制刷写率 100%）
- 防止 B-tree 半创建（migration 中断时数据完整）

### 当前实际现状（与文档差异）
- ✅ `synchronous = 2` (FULL) — 比文档描述更安全
- ⚠️ `busy_timeout = 5000` (5s) — 比文档描述的 30s 更短
- ⚠️ WAL = 140KB — 需主动 checkpoint 清理
- ❌ 启动时未做 TRUNCATE — 残留 WAL 风险存在

---

## 📋 待办 2: 方案 2 — Migration 事务原子化

**目标**: 每个 migration phase 一个事务，失败自动 ROLLBACK，pre/post 完整性检查

### 实施步骤（来自设计文档 §2.4）

| 步骤 | 操作 | 风险 |
|------|------|:---:|
| 1 | 新建 `meta/migrations/base.py` (MigrationBase 基类) | 🟢 低（新增） |
| 2 | 重写 `meta/database/run_ssot_migration.py` 用 `MigrationBase` | 🟡 中（涉及数据） |
| 3 | 重写 `meta/scripts/migration_ssot_stage1.py` | 🟡 中 |
| 4 | 重写 `meta/migrations/add_performance_indexes*.py` | 🟡 中 |
| 5 | 添加测试：`tests/test_migration_atomic.py` | 🟢 低 |

### 关键设计（来自 §2.2.1）
- 启动前自动备份（.bak.migration.<timestamp>）
- 每个 phase 独立事务
- 完整性 pre/post 检查
- 失败自动回滚到备份

### 预期收益
- migration 中断不再产生 `_bak_*` 残留
- B-tree 不再半创建
- 故障可追溯

---

## 📋 待办 3: 方案 3 — 写操作串行化（`BEGIN IMMEDIATE`）

**目标**: 写操作统一入口 `BEGIN IMMEDIATE` + 写后 `PRAGMA wal_checkpoint(FULL)`

### 实施步骤（来自设计文档 §3.6）

| 步骤 | 操作 | 风险 |
|------|------|:---:|
| 1 | 添加 `begin_write()` 方法到 `SqliteAdapter` | 🟢 低 |
| 2 | 替换所有 `BEGIN` / `BEGIN TRANSACTION` 为 `BEGIN IMMEDIATE` | 🟠 中（需全面排查） |
| 3 | 写操作后强制 `PRAGMA wal_checkpoint(FULL)` | 🟡 中 |
| 4 | 应用层处理 `SQLITE_BUSY`（重试 3 次，新增 `meta/core/retry.py`） | 🟢 低 |
| 5 | 添加并发测试：`tests/test_concurrent_write.py` | 🟢 低 |

### 关键设计（来自 §3.3）
```python
def begin_write(self):
    self._connection.execute("BEGIN IMMEDIATE TRANSACTION")
    self._in_transaction = True

def commit(self):
    if self._in_transaction:
        self._connection.execute("COMMIT")
        self._in_transaction = False
        self._connection.execute("PRAGMA wal_checkpoint(FULL)")
```

### 预期收益
- 写并发冲突归零（立即串行化）
- 吞吐稳定（50-200/s）
- 不需要处理 SQLITE_BUSY（简单）

### 性能权衡（来自 §3.4）
| 指标 | DEFERRED + busy_timeout=30s | IMMEDIATE + 全量写锁 |
|------|------------------------------|----------------------|
| 写并发 | 错乱（升级冲突） | **串行**（无错乱） |
| 写延迟 | 0~30s（不确定） | < 1ms（队列串行） |
| 吞吐（写） | 5~20/s | **50~200/s** |

---

## 🛡️ 综合部署时间线（来自设计文档）

| 周 | 任务 | 验收标准 |
|---|------|----------|
| 第 1 周 | 方案 1（WAL Checkpoint） | WAL < 50KB, 强制刷写率 100% |
| 第 2 周 | 方案 3（写串行化） | 写并发冲突归零, 吞吐稳定 |
| 第 3 周 | 方案 2（Migration 原子化） | migration 中断无残留 |
| 第 4 周 | 监控 + 验证 | 集成测试, SOP 文档 |

---

## 🔍 监控指标（来自设计文档 §监控指标）

| 指标 | 阈值 | 来源 | 实施状态 |
|------|------|------|---------|
| WAL size | < 50KB | `db_health_monitor` | 🟡 部分（告警但未强制 checkpoint） |
| Checkpoint 频率 | > 1/min | 新增 | ❌ 待实施 |
| integrity_check 状态 | ok | `_preflight_db_check` | ✅ 已有 |
| 写冲突次数 | < 5/min | 应用层埋点 | ❌ 待实施 |
| migration 失败率 | 0% | migration logger | ❌ 待实施 |

---

## 📦 备份参考

**2026-06-05 实施前备份**：
- 文件: `meta/architecture.db.pre-corrupt-fix.1780673774.bak` (1,380,352 bytes)
- 完整性: `PRAGMA integrity_check` = `ok`
- 创建背景: 启动 BO Action 体系前

**建议新方案实施前再次备份**（格式：`meta/architecture.db.pre-corrupt-fix-v2.<timestamp>.bak`）

---

## 🚦 实施前置条件

- [ ] 在 worktree 隔离（不是 `feature/bo-action-v3`）
- [ ] 完整 DB 备份
- [ ] 准备回滚脚本（恢复 `.bak` 文件）
- [ ] 准备监控脚本（观察 WAL/integrity 实时状态）
- [ ] 准备测试用例（每个方案 5+ 个边界场景）
- [ ] 通知相关开发人员

---

## 📂 相关文件清单

| 路径 | 用途 |
|------|------|
| `meta/core/sql_adapters.py:706-716` | SQLite 适配器（方案 1, 3） |
| `meta/core/sql_adapters.py:850-865` | checkpoint_mode 写入逻辑（方案 1） |
| `meta/core/db_health_monitor.py:90-99` | WAL 监控（方案 1） |
| `meta/database/run_ssot_migration.py` | SSOT migration（方案 2） |
| `meta/scripts/migration_ssot_stage1.py` | Stage 1 migration（方案 2） |
| `meta/migrations/add_performance_indexes*.py` | 索引 migration（方案 2） |
| `docs/db-corruption-prevention-design.md` | 原始设计文档 |
| `docs/progress/bo-action-v3-round1.md` | BO Action Round 1 进度（不相关但同期） |

---

## 变更记录

| 版本 | 日期 | 变更 | 作者 |
|:---:|------|------|------|
| 1.0.0 | 2026-06-05 | 创建待办登记 | AI Agent (Trae) |
