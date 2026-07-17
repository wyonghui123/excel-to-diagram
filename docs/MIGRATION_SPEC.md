# SPEC: Migration 能力模块升级 (V1)

> **版本**: v1.1 | **创建**: 2026-07-14 | **最后更新**: 2026-07-15 | **状态**: DRAFT
> **基于**: 3 轮研究（现状分析 + 行业最佳实践 + SAP/Oracle/Salesforce/ServiceNow 头部产品对比）
> **v1.1 变更**: 补充 P0.5 历史 migration 补登记 + Expand-Contract 模式 + schema_migrations 表增强 + 多实例 migration_lock + 回滚机制 + CI lint + 失败告警 + 实施细节

---

## 0. 任务基本信息

| 字段 | 值 | 说明 |
|------|-----|------|
| **Task ID** | T-MIGRATION-V1 | 全局唯一 |
| **Agent 名称** | agent-migration-upgrade | |
| **Worktree** | `d:\filework\worktrees/release-prep\` | 复用现有 worktree |
| **基于 commit** | `42ae0aa` (NSFOCUS-L4 收尾) | 工作的起点 |
| **风险等级** | 🔴 high | 涉及 schema/migration, 影响数据完整性 |
| **预计完成时间** | 分阶段: P0(1d) + P1(3d) + P2(5d) | |
| **涉及 integration 验证？**  | yes | 必须在 staging + prod 双环境验证 |

---

## 1. 任务描述（一句话）

> **目标**: 把当前"有框架但不用、靠 server.py 硬编码 import 调用"的 migration 系统, 升级为"激活 MigrationRunner + 版本追踪 + Checksum + Preview + 依赖检查 + CI/CD 集成 + 审计日志"的生产级系统, 对齐头部产品 (SAP HDI / Oracle EBS / Salesforce / ServiceNow) 的 8 个共同模式.

---

## 2. 现状分析（带证据）

### 2.1 框架存在但几乎不被使用 [RISK]

**证据**:

[meta/core/migration_runner.py](file:///d:/filework/worktrees/release-prep/meta/core/migration_runner.py) 提供了完整框架:

| 行号 | 内容 | 评估 |
|------|------|------|
| L19-26 | `CREATE TABLE IF NOT EXISTS schema_migrations` | OK - 版本表定义存在 |
| L29 | `class MigrationRunner:` | OK - 框架类存在 |
| L51 | `ensure_migrations_table()` | OK - 表初始化 |
| L58 | `get_executed_migrations()` | OK - 查询历史 |
| L65 | `is_migration_executed()` | OK - 幂等检查 |
| L71 | `record_migration(migration_name, checksum=None)` | WARN - 有 checksum 参数但... |
| L161 | `self.record_migration(migration_name)` | **RISK - 调用时没传 checksum!** |
| L166 | `run_pending_migrations()` | OK - 自动扫描入口 |
| L182 | `if f.endswith('.sql')` | **RISK - 只扫描 .sql, 不扫描 .py!** |
| L220 | `run_all_migrations()` | OK - 便捷函数存在 |
| L234 | `return runner.run_pending_migrations()` | **RISK - 从未被 server.py 调用** |

**结论**: 框架 90% 完整, 但实际只用了 5% (仅 `init_change_notification_tables` 跑 1 个 SQL).

### 2.2 实际执行模式: server.py 硬编码 import [RISK]

**证据**: [meta/server.py:482-515](file:///d:/filework/worktrees/release-prep/meta/server.py#L482-L515)

```python
# L482-483: 硬编码 import + 调用 (绕过 runner)
from meta.scripts.migrate_system_admin import run_migration
run_migration()

# L492: 唯一通过 runner 的 migration (只跑 1 个 SQL)
init_change_notification_tables(data_source)

# L497-498: 硬编码 import + 调用 (绕过 runner)
from meta.migrations.enhance_audit_log_v2 import enhance_audit_log
enhance_audit_log(db_path)

# L503-505: 硬编码 import + 调用 (绕过 runner)
from meta.migrations.v007_50_add_audit_union_view import migrate as v007_50_migrate
v007_50_migrate(Path(db_path), skip_backup=True)

# L511-513: 硬编码 import + 调用 (绕过 runner)
from meta.migrations.v007_51_add_updated_at_materialized import migrate as v007_51_migrate
v007_51_migrate(Path(db_path), skip_backup=True)
```

**问题**:
- 每加一个 migration 都要改 server.py
- 5 个 migration 中只有 1 个写 `schema_migrations` 表 (其余 4 个无版本追踪)
- 没有 checksum 验证
- 没有统一的事务/备份/验证流程

### 2.3 deploy.sh 完全不调用 migration [RISK]

**证据**: [deploy_bundle/deploy.sh](file:///d:/filework/worktrees/release-prep/deploy_bundle/deploy.sh) grep 结果

| 行号 | 内容 | 说明 |
|------|------|------|
| L166 | `ps -ef \| grep -E "python.*server\.py..."` | 只检查进程, **无 migration 调用** |
| L329 | `ps -ef \| grep -E "python.*server\.py..."` | 同上 |

**结论**: 所有 migration 依赖 server.py 启动时自动跑. 部署后第一次启动 backend 才跑 migration, 失败时 backend 启动失败但无回滚, 无法 dry-run 验证.

### 2.4 文件结构混乱 [WARN]

[meta/migrations/](file:///d:/filework/worktrees/release-prep/meta/migrations) 目录有 30 个文件, **5 种命名风格混用**:

| 命名风格 | 示例 | 数量 |
|---------|------|------|
| `v<NNN>_<desc>.py` (版本号前缀) | `v007_45_add_audit_logs_created_at_epoch.py` | 3 |
| `add_/drop_/rename_<desc>.py` (动词前缀) | `add_performance_indexes.py`, `drop_user_roles_table.py` | 12 |
| `fix_/compensate_<desc>.py` (修复类) | `fix_version_consistency.py` | 4 |
| `YYYY_MM_DD_<desc>.sql` (日期前缀) | `2026_06_28_bug_v031_sm_domain_id_trigger.sql` | 1 |
| **`_*.py` (测试/工具脚本, 不该在此)** | `_e2e_real_archive.py`, `_check_dbs.py` | 3 |

### 2.5 脚本入口签名混乱 (4 种签名) [WARN]

Grep 结果显示 migrations 目录有 4 种入口签名:

| 签名 | 示例 | 问题 |
|------|------|------|
| `def migrate()` 无参 | `add_relationship_columns.py:39` | 内部硬编码 DB 路径, 无法测试 |
| `def migrate(conn)` 接收 connection | `fix_version_unique_index.py:40` | 与其他不兼容 |
| `def migrate(db_path, skip_backup=False) -> bool` | `v007_50_add_audit_union_view.py:327` | **新规范, 质量高** |
| `def main()` CLI 入口 | 多个文件 | 不能被 server.py 调用 |

### 2.6 v007_50/v007_51 是项目内部最佳实践模板 [OK]

[v007_50_add_audit_union_view.py](file:///d:/filework/worktrees/release-prep/meta/migrations/v007_50_add_audit_union_view.py) 质量:

- 完整 docstring (L1-32): 背景、方案、部署、回滚说明
- 幂等性: `IF NOT EXISTS`、`DROP IF EXISTS`、检查 VIEW 是否存在
- Backup 机制 (L327-363): `skip_backup` 选项
- Verify 步骤 (L274-324): 列结构检查 + COUNT + EXPLAIN QUERY PLAN
- 事务包裹 (L368-404): try/except + `conn.rollback()`
- 支持 CLI + 函数调用 (L327, L407-420)

**结论**: 这是项目内部最佳实践模板, 可应用到所有新 migration.

### 2.7 历史 migration 补登记问题 [CRITICAL - P0 前置]

**问题**: 现有 5 个 migration 已在 prod 执行过, 但只有 1 个写了 `schema_migrations` 表.

| Migration | 入口 | 已在 prod 执行？ | 已写 schema_migrations? |
|-----------|------|----------------|------------------------|
| `migrate_system_admin.run_migration()` | server.py L482 硬编码 | YES | **NO** |
| `add_change_notification_tables.sql` (init_change_notification_tables) | server.py L492 通过 runner | YES | YES |
| `enhance_audit_log_v2.enhance_audit_log()` | server.py L497 硬编码 | YES | **NO** |
| `v007_50_add_audit_union_view.migrate()` | server.py L503 硬编码 | YES | **NO** |
| `v007_51_add_updated_at_materialized.migrate()` | server.py L511 硬编码 | YES | **NO** |

**风险**: 如果直接激活 `run_all_migrations`, runner 会把这 4 个已执行的 migration 当作 pending 重新执行:
- `migrate_system_admin` / `enhance_audit_log_v2`: 入口签名是 `()` 无参, 与新规范 `migrate(db_path, skip_backup)` 不兼容, 调用会 TypeError
- `v007_50` / `v007_51`: 虽然幂等 (有 `IF NOT EXISTS` + 列存在检查), 但会:
  - 浪费时间重新跑 Backfill (v007_51 在 265K 行 audit_logs 上跑 MAX+GROUP BY)
  - 重新备份 DB (每次 ~500MB)
  - 误导监控 (PHASE 2.5 日志显示 "executed 4 migrations" 但实际没做任何变更)

**结论**: P0 之前必须做 **P0.5 历史 migration 补登记** (详见 §7.1.5):
1. 检测 prod 的 `schema_migrations` 表现有记录
2. 把 4 个未登记的 migration 用当前文件 checksum 补登记为 SUCCESS
3. 验证: `SELECT count(*) FROM schema_migrations` 应 = 5

### 2.8 多实例并发执行风险 [CRITICAL - P0 前置]

**问题**: 项目有多实例部署 (staging 1 实例 + prod 多实例). 如果 2 个实例同时启动:
- 实例 A 启动 → 跑 migration v007 → 写 schema_migrations
- 实例 B 同时启动 → 也检测到 v007 pending → 也跑 → 冲突!

SQLite 的文件锁 (`PRAGMA busy_timeout`) 只保护单条 SQL, 不保护整个 migration 流程:
- 实例 A 在 v007 第 3 步 (ALTER TABLE) 时, 实例 B 可能已开始第 1 步 (备份 DB)
- 实例 A commit 后, 实例 B 重复执行第 3 步 → "duplicate column name" 错误
- 实例 B 误判 migration 失败, 但实际 schema 已变更

**头部产品参考**:
- Oracle EBS: adop 有专门的 `adctrl` 维护模式锁定
- Salesforce: 部署期间强制维护窗口, 只允许单实例
- ServiceNow: Update Set commit 时自动加系统级锁

**结论**: P0 必须实现 **migration lock** (详见 §3.7), 防止多实例并发执行.

---

## 3. 目标设计（参考头部产品 8 个共同模式）

### 3.1 头部产品共同模式对标

基于对 SAP HANA HDI / Oracle EBS R12.2 / Salesforce Metadata API / ServiceNow Update Sets 的研究, 头部产品都遵循 8 个共同模式:

| # | 模式 | 头部产品参考 | 当前项目目标 |
|---|------|------------|------------|
| 1 | **声明式优先** | SAP HDI / Salesforce | P2: 用 .yaml 描述目标 schema (长期) |
| 2 | **强制版本追踪** | 所有产品 | P0: 所有 migration 必须写 schema_migrations 表 + checksum |
| 3 | **环境分层强制** | Salesforce Dev→UAT→Prod | P1: 强化 staging 为 UAT 角色 |
| 4 | **Preview/Dry-run** | ServiceNow Preview / Salesforce checkDeployStatus | P1: `migrate --dry-run` 只打印 SQL |
| 5 | **依赖检查** | Oracle Codelevel / Salesforce Pre-flight | P1: 每个 migration 声明 prerequisites |
| 6 | **审计日志** | 所有产品 | P1: 写入 logs/migrations.log |
| 7 | **测试强制** | Salesforce Apex tests 75%+ | P2: migration 配套 verify 函数 |
| 8 | **CI/CD 集成** | Salesforce DX / Oracle adop | P0: deploy.sh 增加 PHASE 2.5 显式调用 |

### 3.2 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                    deploy.sh (PHASE 2.5)                     │
│  python -m meta.core.migration_runner --dry-run  # 预览      │
│  python -m meta.core.migration_runner             # 执行     │
└─────────────────────┬─────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              MigrationRunner (增强版)                         │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  1. ensure_migrations_table()                       │  │
│  │  2. scan_migrations() → .sql + .py (扩展)           │  │
│  │  3. check_prerequisites() (新增)                    │  │
│  │  4. compute_checksum() (新增)                       │  │
│  │  5. is_migration_executed() + checksum 对比 (增强)  │  │
│  │  6. backup_db() (新增)                              │  │
│  │  7. execute_migration() (统一入口, 支持 .sql + .py) │  │
│  │  8. verify_migration() (新增, 可选)                 │  │
│  │  9. record_migration(name, checksum) (修复)        │  │
│  │ 10. log_audit() (新增)                              │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────┬─────────────────────┬─────────────────────┬─────┘
            │                     │                     │
            ▼                     ▼                     ▼
    ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
    │ schema_     │       │ migrations/ │       │ logs/       │
    │ migrations  │       │ v<NNN>__*.  │       │ migrations  │
    │ (版本表)    │       │ {py,sql}    │       │ .log        │
    │ + checksum  │       │ (统一命名)  │       │ (审计日志)  │
    └─────────────┘       └─────────────┘       └─────────────┘
```

### 3.3 统一命名规范 (参考 Flyway)

所有 migration 文件必须遵循:

```
meta/migrations/v<NNN>__<description>.{py,sql}

示例:
  v001__create_users_table.sql
  v002__add_audit_logs.py
  v003__add_change_notification_tables.sql
  v004__enhance_audit_log_v2.py
  v005__add_audit_union_view.py
  v006__add_updated_at_materialized.py
```

**规则**:
- `v<NNN>`: 3 位版本号, 零填充 (v001, v002, ..., v999)
- `__`: 双下划线分隔符 (参考 Flyway)
- `<description>`: 蛇形命名, 简洁描述 (create_users_table, add_audit_logs)
- 扩展名: `.sql` 纯 SQL, `.py` 需要 Python 逻辑

### 3.4 统一入口签名 (参考 v007_50)

所有 `.py` migration 必须提供:

```python
def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    <_migration 描述>

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (测试环境可跳过)

    Returns:
        True 如果成功执行或已执行 (幂等)

    Raises:
        MigrationError: 如果执行失败
    """
```

**可选** (推荐但非强制):

```python
def verify(db_path: Path) -> bool:
    """验证 migration 是否已正确执行"""

def prerequisites() -> list:
    """声明依赖的其他 migration name, 如 ['v004__enhance_audit_log_v2']"""
```

### 3.5 Expand-Contract 模式 (参考 Oracle EBS Edition-Based Redefinition)

**头部产品参考**: Oracle EBS R12.2 的 Online Patching 用 edition-based redefinition 实现"零停机打补丁", 本质就是 Expand-Contract 模式的极致.

**模式定义**: 对于 breaking change 的 schema 变更 (删列/改类型/重命名), 必须分 2-3 个版本部署, 不能一次完成:

```
版本 N (Expand):   新增列/表, 应用层双写 (旧+新)
                  ↓ 部署 → 验证 → 运行一段时间
版本 N+1 (Migrate): Backfill 历史数据从旧列→新列
                  ↓ 部署 → 验证
版本 N+2 (Contract): 应用层切到只读新列, 删除旧列 (可选, 也可保留)
```

**项目应用**: v007_51 已经实践了 Expand-Contract (添加 `updated_at` 物化列 + Backfill, 不删旧列). 后续 breaking change 必须遵循:

| 变更类型 | Expand (版本 N) | Migrate (版本 N+1) | Contract (版本 N+2) |
|---------|----------------|-------------------|---------------------|
| 删列 | 标记 deprecated, 应用层停止写入 | - | DROP COLUMN |
| 改类型 | 新增列 (新类型) | Backfill + 双写 | 删旧列 |
| 重命名 | 新增新名列, 双写 | Backfill | 删旧名列 |
| 改约束 | 放宽旧约束 (如 NOT NULL→NULL) | Backfill 默认值 | 加新约束 |

**禁止操作** (除非确认无 prod 流量):
- 单次 migration 内 `DROP TABLE` / `DROP COLUMN` (除非确认无引用)
- 单次 migration 内改列类型 (SQLite 不支持原生 `ALTER COLUMN`, 需重建表)

**示例** (参考 v007_51 的 Expand 阶段):
```python
def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    [Expand] v008: 给 users 表添加 user_code 新列 (准备替换 username)
    
    本版本只添加列 + 双写, 不删除 username. 应用层 (user_api.py) 改为同时写入.
    下个版本 v009 会 Backfill + 切换读取.
    """
    # ALTER TABLE ADD COLUMN user_code TEXT  (幂等: 检查列是否存在)
    # 不动 username 列
```

### 3.6 schema_migrations 表结构增强

**现状** (L19-26): 4 列 (id, migration_name, executed_at, checksum). 不足以支持审计/回滚/故障排查.

**增强设计** (向后兼容, 不破坏现有数据):

```sql
-- Phase 1: 在现有表上 ALTER ADD COLUMN (向后兼容)
ALTER TABLE schema_migrations ADD COLUMN executed_by VARCHAR(64);      -- 'deploy.sh' / 'server.py' / 'manual'
ALTER TABLE schema_migrations ADD COLUMN execution_time_ms INTEGER;    -- 耗时
ALTER TABLE schema_migrations ADD COLUMN backup_path VARCHAR(512);     -- 备份文件路径
ALTER TABLE schema_migrations ADD COLUMN status VARCHAR(16) DEFAULT 'SUCCESS';  -- SUCCESS/FAILED/ROLLED_BACK
ALTER TABLE schema_migrations ADD COLUMN error_message TEXT;           -- 失败原因
ALTER TABLE schema_migrations ADD COLUMN environment VARCHAR(16);      -- 'staging' / 'prod'
```

**头部产品对标**:

| 字段 | Oracle EBS (ad adop) | Salesforce (DeployResult) | 本项目 |
|------|---------------------|--------------------------|--------|
| 执行人 | `APPLYSERVER` | `deployedBy` | `executed_by` |
| 耗时 | `elapsedTime` | `-` | `execution_time_ms` |
| 状态 | `SUCCESS/FAILED` | `Succeeded/Failed` | `status` |
| 错误信息 | `log files` | `failureMessage` | `error_message` |
| 环境 | `PATCH context` | `sandbox/prod` | `environment` |
| 备份 | `db snapshot` | `-` | `backup_path` |

**用途**:
- `executed_by`: 区分是 deploy.sh PHASE 2.5 跑的还是 server.py 启动兜底跑的
- `execution_time_ms`: 监控慢 migration (Backfill 在大表上可能跑几分钟)
- `backup_path`: 失败时快速定位备份文件回滚
- `status`: FAILED 的记录不阻止后续 migration, 但触发告警
- `environment`: 区分 staging/prod 执行历史 (多实例共用同一 DB 时尤其重要)

### 3.7 多实例并发 migration 协调 (migration_lock)

**问题**: 详见 §2.8. 多实例同时启动时可能并发跑 migration 导致冲突.

**方案**: 在 `schema_migrations` 表之外, 新增 `migration_lock` 表 ( advisory lock 模式):

```sql
CREATE TABLE IF NOT EXISTS migration_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单行表, 全局锁
    locked_by VARCHAR(64),                  -- 实例标识 (hostname + pid)
    locked_at TIMESTAMP,
    heartbeat_at TIMESTAMP                  -- 每 10s 更新, 检测僵尸锁
);
```

**加锁流程** (在 `run_pending_migrations` 开头):

```python
def acquire_migration_lock(self, timeout_seconds: int = 60) -> bool:
    """
    获取 migration 锁. 超时返回 False.
    
    策略:
    1. INSERT OR REPLACE, 抢锁
    2. 抢到后立即跑 migration, 跑完释放
    3. 抢不到: 轮询 heartbeat_at, 如果 > 60s 没更新 → 视为僵尸锁, 强制接管
    """
    instance_id = f"{socket.gethostname()}-{os.getpid()}"
    deadline = time.time() + timeout_seconds
    
    while time.time() < deadline:
        # 尝试加锁 (原子操作)
        try:
            self.data_source.execute(
                "INSERT OR REPLACE INTO migration_lock (id, locked_by, locked_at, heartbeat_at) "
                "VALUES (1, ?, ?, ?)",
                (instance_id, datetime.now().isoformat(), datetime.now().isoformat())
            )
            self.data_source.commit()
            logger.info(f"[MigrationLock] Acquired by {instance_id}")
            return True
        except sqlite3.IntegrityError:
            # 已被持有, 检查是否僵尸
            row = self.data_source.execute(
                "SELECT locked_by, heartbeat_at FROM migration_lock WHERE id = 1"
            ).fetchone()
            if row:
                locked_by, heartbeat_str = row
                heartbeat = datetime.fromisoformat(heartbeat_str)
                if (datetime.now() - heartbeat).total_seconds() > 60:
                    logger.warning(
                        f"[MigrationLock] Detected zombie lock by {locked_by}, "
                        f"last heartbeat {heartbeat}, force taking over"
                    )
                    continue  # 重试 INSERT OR REPLACE
            time.sleep(2)  # 等 2s 再试
    return False  # 超时

def release_migration_lock(self):
    """释放锁"""
    self.data_source.execute("DELETE FROM migration_lock WHERE id = 1")
    self.data_source.commit()

def heartbeat(self):
    """更新 heartbeat, 在长 migration 中每 10s 调用一次"""
    instance_id = f"{socket.gethostname()}-{os.getpid()}"
    self.data_source.execute(
        "UPDATE migration_lock SET heartbeat_at = ? WHERE locked_by = ?",
        (datetime.now().isoformat(), instance_id)
    )
    self.data_source.commit()
```

**头部产品参考**:
- ServiceNow: Update Set commit 时 sys_metadata 系统锁
- Oracle EBS: adop `adctrl` 维护模式 + session-level lock
- Salesforce: DeployJobs 表 + status='Pending' 排队

**deploy.sh 配合**: PHASE 2.5 调用 `run_all_migrations` 时, 如果 `acquire_migration_lock` 超时 (60s), deploy.sh 应:
1. 不立即 exit 1 (可能是其他实例正在正常跑 migration)
2. 等待 + 重试 3 次 (每次 60s)
3. 3 次都失败 → exit 1 + 告警

---

## 4. 改动文件白名单 ✅

> **只允许修改以下文件** (超出范围视为违规)

### 4.1 P0 (立即修, 1 天)

```yaml
modified_files:
  - meta/core/migration_runner.py          # 增强: 支持 .py + checksum + 审计日志 + migration_lock + 超时 + 备份
  - meta/server.py                          # 修改: L482-515 改用 run_all_migrations
  - deploy_bundle/deploy.sh                 # 修改: 增加 PHASE 2.5 (7 步流程) 调用 migration
  - deploy_bundle/lib/common.sh             # 修改: 增加 migration 日志路径变量 + ALERT_DIR 变量

new_files:
  - meta/migrations/README.md               # 命名规范 + 执行流程说明
  - meta/migrations/_rename_mapping.yaml    # 旧文件名 → 新文件名映射 (用于迁移)
  - tools/test_migration_runner.py          # 单元测试
  - tools/backfill_schema_migrations.py     # P0.5 历史 migration 补登记脚本 (一次性)
```

### 4.1.5 P0.5 (P0 前置必做, 0.5 天)

```yaml
new_files:
  - tools/backfill_schema_migrations.py     # 历史 migration 补登记脚本 (在 P0 deploy.sh 激活前跑)
```

### 4.2 P1 (短期, 3 天)

```yaml
modified_files:
  - meta/core/migration_runner.py           # 增加: prerequisites 检查 + dry-run + verify + rollback + schema_migrations 表增强
  - meta/server.py                          # 修改: migration 失败时不启动 backend
  - monitor_prod.py                         # 增加: check_migration_alerts + check_schema_migrations_health

new_files:
  - meta/migrations/v001__create_users_table.sql         # 重命名后的标准 migration
  - meta/migrations/v002__add_audit_logs.py              # 重命名
  - meta/migrations/v003__add_change_notification_tables.sql
  - meta/migrations/v004__enhance_audit_log_v2.py
  - meta/migrations/v005__add_audit_union_view.py
  - meta/migrations/v006__add_updated_at_materialized.py
  - tools/migration_status_api.py           # /api/migrations 状态查询 + rollback API (端口 9206)
  - tools/migration_lint.py                 # 8 项 lint 检查 (L1-L8)
  - tools/test_migration_prerequisites.py   # 依赖检查测试
  - .git/hooks/pre-commit                   # 集成 migration_lint (可选, 团队协商)
```

### 4.3 P2 (中期, 5 天)

```yaml
modified_files:
  - meta/core/migration_runner.py           # 增加: 声明式 schema diff (可选)

new_files:
  - meta/migrations/schema.yaml             # 声明式 schema 定义 (长期目标)
  - tools/migration_lint.py                 # migration 质量检查 (命名/签名/幂等)
```

### 4.4 清理 (P0 一起做)

```yaml
deleted_files:
  - meta/migrations/_e2e_real_archive.py    # 移到 meta/tests/migrations/
  - meta/migrations/_e2e_verify.py          # 移到 meta/tests/migrations/
  - meta/migrations/_check_dbs.py           # 移到 tools/

moved_files:
  - meta/migrations/_e2e_real_archive.py → meta/tests/migrations/test_e2e_real_archive.py
  - meta/migrations/_e2e_verify.py → meta/tests/migrations/test_e2e_verify.py
  - meta/migrations/_check_dbs.py → tools/check_dbs.py
```

---

## 5. 禁止改文件黑名单 🚫

> **绝对不能改以下文件**

```yaml
forbidden_files:
  - meta/architecture.db                    # 数据库数据 (只能通过 migration 改)
  - meta/architecture.db.bak*               # 备份文件
  - src/                                    # 前端不改动
  - .agent-status.json                      # 协调状态
  - service_manager.ps1                     # 服务管理
  - scripts/agent_bootstrap.ps1             # Worktree 引导
  - .git/hooks/pre-commit                   # 保护脚本
  - healthy-baseline-2026-06-17             # 健康基线 tag
  - d:\filework\excel-to-diagram\**         # 主工作树
```

**例外**: `meta/server.py` 允许修改 L482-515 (migration 调用段), 但必须用 `run_all_migrations` 替代硬编码 import.

---

## 6. 依赖关系

```yaml
depends_on:
  - commit: 42ae0aa                          # NSFOCUS-L4 收尾 commit
  - branch: worktrees/release-prep            # 当前 worktree

blocks:
  - 后续所有涉及 schema 变更的功能开发        # 必须等 migration 框架就绪
```

---

## 7. 实施计划（P0-P3 优先级）

### 7.1 P0: 激活现有框架 (1 天) — 最高优先级

**目标**: 让 `MigrationRunner` 真正工作, deploy.sh 显式调用 migration.

#### 7.1.1 增强 MigrationRunner

修改 [meta/core/migration_runner.py](file:///d:/filework/worktrees/release-prep/meta/core/migration_runner.py):

```python
# L166-190: run_pending_migrations 扩展支持 .py
def run_pending_migrations(self) -> int:
    self.ensure_migrations_table()
    if not os.path.exists(self.migrations_dir):
        return 0

    executed_count = 0
    # 修改: 同时扫描 .sql 和 .py
    migration_files = sorted([
        f for f in os.listdir(self.migrations_dir)
        if f.endswith('.sql') or f.endswith('.py')
    ])

    for migration_file in migration_files:
        if self.run_migration(migration_file):
            executed_count += 1
    return executed_count

# L140-164: run_migration 增强 checksum
def run_migration(self, migration_name: str) -> bool:
    if self.is_migration_executed(migration_name):
        # 新增: checksum 验证
        recorded_checksum = self._get_recorded_checksum(migration_name)
        current_checksum = self._compute_checksum(migration_name)
        if recorded_checksum != current_checksum:
            logger.error(f"Migration {migration_name} checksum mismatch! recorded={recorded_checksum}, current={current_checksum}")
            return False
        logger.debug(f"Migration {migration_name} already executed (checksum OK)")
        return False  # 已执行, 跳过

    # 新增: 备份 DB
    if not self._backup_db():
        logger.error("Backup failed, abort migration")
        return False

    # 执行 (支持 .sql 和 .py)
    if migration_name.endswith('.sql'):
        success = self.execute_sql_file(...)
    elif migration_name.endswith('.py'):
        success = self._execute_py_migration(migration_name)

    if success:
        # 修复: 调用时传 checksum
        checksum = self._compute_checksum(migration_name)
        self.record_migration(migration_name, checksum)
        # 新增: 审计日志
        self._log_audit(migration_name, "SUCCESS", checksum)
        return True
    else:
        self._log_audit(migration_name, "FAILED", None)
        return False
```

**补充实施细节** (事务边界 / 超时 / checksum 算法):

```python
# === 1. Checksum 算法 (SHA256, 与 backfill_schema_migrations.py 保持一致) ===
import hashlib

def _compute_checksum(self, migration_name: str) -> str:
    """计算 migration 文件的 SHA256 checksum"""
    file_path = os.path.join(self.migrations_dir, migration_name)
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()  # 64 字符十六进制

# === 2. 事务边界 (SQLite DDL 限制) ===
# SQLite 限制:
#   - ALTER TABLE ADD COLUMN 可以在事务中, 但 ROLLBACK 后列还在 (SQLite 特性)
#   - CREATE TABLE / DROP TABLE 可以正常事务回滚
#   - UPDATE / DELETE 可以正常事务回滚
# 策略: 每个 migration 用独立事务, 失败时 rollback (注意: ADD COLUMN 后即使 rollback 列也保留,
#        但这是 SQLite 限制, 不影响幂等性 — 下次重跑会检测列存在并跳过)

def _execute_py_migration(self, migration_name: str) -> bool:
    """执行 .py migration, 统一调用 migrate(db_path, skip_backup)"""
    file_path = os.path.join(self.migrations_dir, migration_name)
    
    # 动态 import
    import importlib.util
    spec = importlib.util.spec_from_file_location(migration_name[:-3], file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    if not hasattr(module, 'migrate'):
        logger.error(f"Migration {migration_name} missing migrate() function")
        return False
    
    db_path = self._get_db_path()  # 从 data_source 获取
    try:
        result = module.migrate(db_path, skip_backup=True)  # runner 已备份, 跳过 migration 内部备份
        if result is None:  # 旧签名 migrate() 无返回值, 视为成功
            return True
        return bool(result)
    except Exception as e:
        logger.error(f"Migration {migration_name} raised: {e}", exc_info=True)
        return False

# === 3. 执行超时 (防卡死) ===
import signal  # Unix only; Windows 用 threading.Timer

MIGRATION_TIMEOUT_SECONDS = 300  # 单个 migration 最多 5 分钟

def _execute_with_timeout(self, func, timeout: int = MIGRATION_TIMEOUT_SECONDS):
    """带超时执行 (Unix: SIGALRM; Windows: 仅日志, 不强制)"""
    if os.name == 'posix':
        def handler(signum, frame):
            raise TimeoutError(f"Migration exceeded {timeout}s")
        old_handler = signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout)
        try:
            return func()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows: 不强制超时, 只记录开始/结束时间
        start = time.time()
        result = func()
        elapsed = time.time() - start
        if elapsed > timeout:
            logger.warning(f"Migration took {elapsed:.1f}s (exceeds {timeout}s soft limit)")
        return result

# === 4. 备份策略 ===
def _backup_db(self) -> bool:
    """备份 DB 到 .bak.YYYYMMDD_HHMMSS"""
    db_path = self._get_db_path()
    if not db_path.exists():
        return True  # 新 DB, 无需备份
    
    # 检查磁盘空间 (至少留 DB 大小 2x)
    free_space = os.statvfs(os.path.dirname(db_path)).f_bavail * os.statvfs(os.path.dirname(db_path)).f_bsize
    db_size = db_path.stat().st_size
    if free_space < db_size * 2:
        logger.error(f"Insufficient disk space: free={free_space//1024//1024}MB, db={db_size//1024//1024}MB")
        return False
    
    bak_path = str(db_path) + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(str(db_path), bak_path)
    
    # 清理旧备份: 只保留最近 5 个
    bak_pattern = str(db_path) + ".bak.*"
    old_baks = sorted(Path(os.path.dirname(db_path)).glob(bak_pattern))
    if len(old_baks) > 5:
        for old_bak in old_baks[:-5]:
            old_bak.unlink()
            logger.info(f"Cleaned old backup: {old_bak}")
    
    return True
```

#### 7.1.2 server.py 改用 runner

修改 [meta/server.py:482-515](file:///d:/filework/worktrees/release-prep/meta/server.py#L482-L515):

```python
# 旧代码 (删除):
# from meta.scripts.migrate_system_admin import run_migration
# run_migration()
# from meta.migrations.enhance_audit_log_v2 import enhance_audit_log
# enhance_audit_log(db_path)
# ...

# 新代码:
from meta.core.migration_runner import run_all_migrations
executed = run_all_migrations(data_source)
logging.getLogger(__name__).info(f"[Migration] Executed {executed} pending migrations")
```

#### 7.1.3 deploy.sh 增加 PHASE 2.5

修改 [deploy_bundle/deploy.sh](file:///d:/filework/worktrees/release-prep/deploy_bundle/deploy.sh), 在 PHASE 2 (解压) 之后, PHASE 3 (启动 backend) 之前增加:

```bash
# ============================================================
# PHASE 2.5: 执行 database migrations (P0 新增)
# ============================================================
echo "[PHASE 2.5] Running database migrations..."
cd $DEPLOY_DIR/current

# 2.5.1: 预检 - DB 完整性
echo "[PHASE 2.5.1] DB integrity pre-check..."
DB_PATH=${DB_PATH:-meta/architecture.db}
if [ -f "$DB_PATH" ]; then
    INTEGRITY=$(python -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
print(conn.execute('PRAGMA integrity_check').fetchone()[0])
conn.close()
")
    if [ "$INTEGRITY" != "ok" ]; then
        echo "[PHASE 2.5.1] FATAL: DB integrity_check FAILED: $INTEGRITY"
        echo "[PHASE 2.5.1] Aborting deployment, manual intervention required"
        exit 1
    fi
    echo "[PHASE 2.5.1] DB integrity OK"
fi

# 2.5.2: 预检 - 磁盘空间 (至少留 DB 大小 3x: 备份+新DB+临时)
echo "[PHASE 2.5.2] Disk space check..."
DB_SIZE=$(du -m "$DB_PATH" 2>/dev/null | cut -f1 || echo "0")
FREE_SPACE=$(df -m . | tail -1 | awk '{print $4}')
REQUIRED=$((DB_SIZE * 3 + 100))  # 3x DB size + 100MB buffer
if [ "$FREE_SPACE" -lt "$REQUIRED" ]; then
    echo "[PHASE 2.5.2] FATAL: Insufficient disk space"
    echo "  DB size: ${DB_SIZE}MB"
    echo "  Free: ${FREE_SPACE}MB"
    echo "  Required: ${REQUIRED}MB (3x DB + 100MB buffer)"
    exit 1
fi
echo "[PHASE 2.5.2] Disk space OK (free: ${FREE_SPACE}MB, required: ${REQUIRED}MB)"

# 2.5.3: 预检 - P0.5 补登记是否已执行 (schema_migrations 表记录数)
echo "[PHASE 2.5.3] Verify P0.5 backfill completed..."
REGISTERED_COUNT=$(python -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('$DB_PATH')
    cur = conn.execute('SELECT count(*) FROM schema_migrations')
    print(cur.fetchone()[0])
    conn.close()
except Exception as e:
    print(0, file=sys.stderr)
    print(0)
" 2>/dev/null || echo "0")
if [ "$REGISTERED_COUNT" -lt 5 ]; then
    echo "[PHASE 2.5.3] FATAL: schema_migrations has only $REGISTERED_COUNT records (< 5)"
    echo "[PHASE 2.5.3] P0.5 backfill_schema_migrations.py must be run first!"
    echo "[PHASE 2.5.3] Run: python tools/backfill_schema_migrations.py --db-path $DB_PATH"
    exit 1
fi
echo "[PHASE 2.5.3] schema_migrations has $REGISTERED_COUNT records (>= 5, OK)"

# 2.5.4: Dry-run 预览 (只打印, 不执行)
echo "[PHASE 2.5.4] Dry-run preview..."
python -m meta.core.migration_runner --dry-run 2>&1 | tee /tmp/migration_dryrun.log
PENDING=$(grep -c "Would execute" /tmp/migration_dryrun.log || echo "0")
echo "[PHASE 2.5.4] Dry-run found $PENDING pending migrations"

# 2.5.5: 执行 migration (带并发锁重试)
echo "[PHASE 2.5.5] Executing migrations (with lock retry)..."
MAX_RETRIES=3
RETRY=0
MIGRATION_SUCCESS=false
while [ $RETRY -lt $MAX_RETRIES ]; do
    RETRY=$((RETRY + 1))
    echo "[PHASE 2.5.5] Attempt $RETRY/$MAX_RETRIES..."
    
    if python -c "
import sys, os
os.environ.setdefault('MIGRATION_ENV', '\${MIGRATION_ENV:-staging}')
from meta.core.migration_runner import run_all_migrations
from meta.core.datasource import get_data_source
ds = get_data_source()
n = run_all_migrations(ds)
print(f'OK: executed {n} migrations')
" 2>&1 | tee /tmp/migration_run.log; then
        MIGRATION_SUCCESS=true
        break
    else
        echo "[PHASE 2.5.5] Attempt $RETRY failed, waiting 60s before retry..."
        # 检查是否是锁冲突
        if grep -q "MigrationLock" /tmp/migration_run.log; then
            echo "[PHASE 2.5.5] Lock conflict detected, will retry"
            sleep 60
        else
            # 非锁冲突, 不重试
            echo "[PHASE 2.5.5] Non-lock failure, no retry"
            break
        fi
    fi
done

if [ "$MIGRATION_SUCCESS" != "true" ]; then
    echo "[PHASE 2.5.5] FATAL: Migration failed after $RETRY attempts"
    echo "[PHASE 2.5.5] Check /tmp/migration_run.log for details"
    
    # 写告警文件 (被 monitor_prod.py 读取)
    ALERT_DIR=\${ALERT_DIR:-/tmp/migration_alerts}
    mkdir -p \$ALERT_DIR
    cat > \$ALERT_DIR/migration_failed.\$(date +%Y%m%d_%H%M%S).alert <<EOF
alert_type: migration_failed
timestamp: \$(date -Iseconds)
host: \$(hostname)
deploy_version: \${VERSION:-unknown}
db_path: $DB_PATH
pending_count: $PENDING
retry_count: $RETRY
log_file: /tmp/migration_run.log
EOF
    echo "[PHASE 2.5.5] Alert written to \$ALERT_DIR/"
    
    exit 1
fi

# 2.5.6: 验证 - schema_migrations 表记录数应增加
echo "[PHASE 2.5.6] Post-migration verification..."
NEW_COUNT=$(python -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
print(conn.execute('SELECT count(*) FROM schema_migrations').fetchone()[0])
conn.close()
")
echo "[PHASE 2.5.6] schema_migrations now has $NEW_COUNT records (was $REGISTERED_COUNT)"

# 2.5.7: 验证 - 无 FAILED 状态的 migration
FAILED_COUNT=$(python -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
try:
    print(conn.execute(\"SELECT count(*) FROM schema_migrations WHERE status='FAILED'\").fetchone()[0])
except sqlite3.OperationalError:
    print(0)  # status 列还不存在 (P1 才加)
conn.close()
" 2>/dev/null || echo "0")
if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "[PHASE 2.5.6] WARN: $FAILED_COUNT migrations have FAILED status"
    echo "[PHASE 2.5.6] Check logs/migrations.log for details"
fi

echo "[PHASE 2.5] Migrations completed successfully"
```

**关键设计**:
1. **7 步流程**: integrity → disk → backfill check → dry-run → execute (retry) → verify count → verify failed
2. **并发锁重试**: 最多 3 次, 每次间隔 60s (应对多实例同时部署)
3. **告警文件**: 失败时写 `/tmp/migration_alerts/*.alert`, 被 monitor_prod.py 读取
4. **预检 P0.5**: 强制检查 `schema_migrations` 记录数 ≥ 5, 防止未跑补登记就激活 runner
5. **dry-run 日志**: 保留到 `/tmp/migration_dryrun.log`, 便于事后排查

#### 7.1.4 创建 README

新建 `meta/migrations/README.md`:

```markdown
# Database Migrations

## 命名规范
v<NNN>__<description>.{py,sql}

## 执行流程
1. 部署时 deploy.sh PHASE 2.5 自动调用
2. server.py 启动时也会调用 (兜底)
3. 所有 migration 记录到 schema_migrations 表

## 新增 migration 步骤
1. 创建文件: meta/migrations/v<NNN>__<desc>.{py,sql}
2. .py 文件必须提供: def migrate(db_path, skip_backup=False) -> bool
3. 推荐: def verify(db_path) -> bool + def prerequisites() -> list
4. 本地测试: python -m meta.core.migration_runner --dry-run
5. staging 验证后才能部署 prod

## 参考
- 行业最佳实践: Flyway / Liquibase
- 项目模板: v005__add_audit_union_view.py (质量最高)
```

### 7.1.5 P0.5: 历史 migration 补登记 (P0 前置必做)

**问题**: 详见 §2.7. 直接激活 `run_all_migrations` 会把已执行的 4 个 migration 重新执行.

**解决方案**: 创建一次性脚本 `tools/backfill_schema_migrations.py`, 在 P0 激活 runner 之前先跑一次, 把已执行的 migration 补登记到 `schema_migrations` 表.

```python
# tools/backfill_schema_migrations.py
"""
一次性脚本: 把已执行但未登记的 migration 补登记到 schema_migrations 表.

使用场景:
  - P0 激活 run_all_migrations 之前
  - 在每个环境 (staging/prod) 各跑一次

执行方式 (在目标环境):
  cd $DEPLOY_DIR/current
  python tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run  # 预览
  python tools/backfill_schema_migrations.py --db-path meta/architecture.db            # 执行
"""
import sqlite3
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

# 已在 prod 执行过但未登记的 migration 清单 (硬编码, 一次性)
LEGACY_MIGRATIONS = [
    # (canonical_name, file_path_relative_to_meta/, executed_by, notes)
    # 注意: canonical_name 必须与 P1 重命名后的文件名一致
    ("v001__migrate_system_admin", "scripts/migrate_system_admin.py", "server.py L482", "无参签名, 已在 prod 执行"),
    ("v003__add_change_notification_tables", "migrations/add_change_notification_tables.sql", "server.py L492 via runner", "已通过 runner 登记, 跳过"),
    ("v004__enhance_audit_log_v2", "migrations/enhance_audit_log_v2.py", "server.py L497", "enhance_audit_log(db_path) 签名"),
    ("v005__add_audit_union_view", "migrations/v007_50_add_audit_union_view.py", "server.py L503", "migrate(db_path, skip_backup=True)"),
    ("v006__add_updated_at_materialized", "migrations/v007_51_add_updated_at_materialized.py", "server.py L511", "migrate(db_path, skip_backup=True)"),
]

def compute_checksum(file_path: Path) -> str:
    """SHA256 of file content (与 MigrationRunner._compute_checksum 保持一致)"""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db-path', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--meta-root', default='.', help='meta/ 目录的父目录')
    args = parser.parse_args()
    
    db_path = Path(args.db_path)
    meta_root = Path(args.meta_root)
    
    if not db_path.exists():
        print(f"FATAL: DB not found: {db_path}")
        return 1
    
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # 1. 确保 schema_migrations 表存在
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name VARCHAR(255) NOT NULL UNIQUE,
            executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum VARCHAR(64)
        )
    """)
    
    # 2. 查询已登记的
    cur.execute("SELECT migration_name FROM schema_migrations")
    already_registered = {row[0] for row in cur.fetchall()}
    
    # 3. 补登记
    to_register = []
    for canonical_name, rel_path, executed_by, notes in LEGACY_MIGRATIONS:
        if canonical_name in already_registered:
            print(f"[SKIP] {canonical_name} already registered ({notes})")
            continue
        
        file_path = meta_root / "meta" / rel_path
        if not file_path.exists():
            # P1 重命名前的路径
            file_path = meta_root / "meta" / rel_path.replace("v001__migrate_system_admin", "migrate_system_admin") \
                                                       .replace("v003__add_change_notification_tables", "add_change_notification_tables") \
                                                       .replace("v004__enhance_audit_log_v2", "enhance_audit_log_v2") \
                                                       .replace("v005__add_audit_union_view", "v007_50_add_audit_union_view") \
                                                       .replace("v006__add_updated_at_materialized", "v007_51_add_updated_at_materialized")
        
        if not file_path.exists():
            print(f"[WARN] {canonical_name}: source file not found at {file_path}, skipping")
            continue
        
        checksum = compute_checksum(file_path)
        to_register.append((canonical_name, checksum, executed_by, notes))
        print(f"[TODO] {canonical_name} -> checksum={checksum[:16]}... ({notes})")
    
    if args.dry_run:
        print(f"\n[DRY-RUN] Would register {len(to_register)} migrations")
        return 0
    
    # 4. 执行登记
    for canonical_name, checksum, executed_by, notes in to_register:
        cur.execute(
            "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)",
            (canonical_name, checksum)
        )
        print(f"[OK] Registered {canonical_name} (executed_by={executed_by})")
    
    conn.commit()
    
    # 5. 验证
    cur.execute("SELECT count(*) FROM schema_migrations")
    count = cur.fetchone()[0]
    print(f"\n[DONE] schema_migrations now has {count} records")
    
    conn.close()
    return 0

if __name__ == '__main__':
    exit(main())
```

**执行顺序** (在每个环境各跑一次):

```bash
# Step 1: 在本地 dev 跑 (验证脚本本身工作)
cd d:/filework/worktrees/release-prep
python tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run

# Step 2: 在 staging 跑
ssh staging "cd /opt/app/staging/meta && python tools/backfill_schema_migrations.py --db-path architecture.db --dry-run"
ssh staging "cd /opt/app/staging/meta && python tools/backfill_schema_migrations.py --db-path architecture.db"

# Step 3: 在 prod 跑 (必须在 P0 deploy.sh PHASE 2.5 激活之前!)
ssh yonaa "cd /opt/app/prod/meta && python tools/backfill_schema_migrations.py --db-path architecture.db --dry-run"
ssh yonaa "cd /opt/app/prod/meta && python tools/backfill_schema_migrations.py --db-path architecture.db"

# Step 4: 验证
sqlite3 /opt/app/staging/meta/architecture.db "SELECT migration_name, substr(checksum,1,16) as checksum FROM schema_migrations ORDER BY id"
# 期望: 5 行 (v001/v003/v004/v005/v006)
```

**关键风险**:
- 必须在 P0 deploy.sh PHASE 2.5 激活 `run_all_migrations` **之前** 跑, 否则 runner 会重复执行
- 脚本本身必须幂等 (重复跑不报错, 已登记的跳过)
- checksum 用当前文件 SHA256, 与 P0 增强后的 `_compute_checksum` 算法保持一致

**完成标准**:
- [ ] staging: `SELECT count(*) FROM schema_migrations` = 5
- [ ] prod: `SELECT count(*) FROM schema_migrations` = 5
- [ ] 所有 checksum 非 NULL
- [ ] 脚本幂等: 重复执行不报错

### 7.2 P1: 补齐能力 (3 天)

#### 7.2.1 重命名现有 migration

按 `_rename_mapping.yaml` 把 30 个文件统一为 `v<NNN>__<desc>.{py,sql}` 格式. 保留旧文件作 soft link (过渡期).

#### 7.2.2 统一入口签名

所有 `.py` migration 改为:
```python
def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    ...
```

旧签名的 migration 包装为兼容层:
```python
# 旧: def migrate()
# 新包装:
def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    from meta.scripts.old_module import migrate as _old_migrate
    _old_migrate()
    return True
```

#### 7.2.3 Prerequisites 检查

每个 migration 声明依赖:
```python
def prerequisites() -> list:
    return ['v004__enhance_audit_log_v2']  # 必须先执行 v004
```

MigrationRunner 在执行前检查 prerequisites 是否已执行.

#### 7.2.4 Dry-run 模式

```bash
python -m meta.core.migration_runner --dry-run
# 输出:
# [DRY-RUN] Would execute: v006__add_updated_at_materialized.py
# [DRY-RUN] Would execute: v007__new_migration.sql
# [DRY-RUN] Total: 2 pending migrations
```

#### 7.2.5 审计日志

写入 `logs/migrations.log`:
```
2026-07-14 10:00:00 [INFO] [migration_runner] Executing v006__add_updated_at_materialized.py
2026-07-14 10:00:01 [INFO] [migration_runner] v006 backup created: architecture.db.bak.20260714_100000
2026-07-14 10:00:02 [INFO] [migration_runner] v006 executed successfully (checksum: a1b2c3...)
2026-07-14 10:00:02 [INFO] [migration_runner] v006 verified: OK
```

#### 7.2.6 Migration Status API

新增 `tools/migration_status_api.py` (端口 9206):
- `GET /api/migrations` - 列出所有 migration + 状态 (executed/pending/failed)
- `GET /api/migrations/<name>` - 单个 migration 详情
- `POST /api/migrations/dry-run` - 触发 dry-run
- `POST /api/migrations/<name>/rollback` - 触发回滚 (需二次确认)

#### 7.2.7 回滚机制设计

**头部产品参考**:
- ServiceNow: Update Set 的 "Back out" 功能, 一键回滚已 commit 的变更
- Oracle EBS: adop phase=abort 放弃当前 patch cycle
- Salesforce: DeployResult 支持 rollbackOnErrors (默认 true)

**设计方案** (Expand-Contract 模式下, 回滚是安全的):

```python
# meta/core/migration_runner.py 新增
def rollback_migration(self, migration_name: str, backup_path: str = None) -> bool:
    """
    回滚单个 migration.
    
    策略 (优先级):
    1. 如果 migration 提供 rollback() 函数 → 调用它 (推荐)
    2. 如果传入 backup_path → 从备份恢复 DB (粗粒度, 影响后续 migration)
    3. 都没有 → 拒绝回滚, 提示手动处理
    
    Args:
        migration_name: 要回滚的 migration 名
        backup_path: 可选, 指定备份文件路径. 不传则查 schema_migrations.backup_path
    
    Returns:
        True 如果回滚成功
    """
    if not self.is_migration_executed(migration_name):
        logger.warning(f"Migration {migration_name} not executed, nothing to rollback")
        return True
    
    # 策略 1: 调用 rollback() 函数
    if migration_name.endswith('.py'):
        try:
            module = self._load_migration_module(migration_name)
            if hasattr(module, 'rollback'):
                logger.info(f"[Rollback] Calling {migration_name}.rollback()")
                success = module.rollback(self._get_db_path())
                if success:
                    self._mark_rolled_back(migration_name)
                    self._log_audit(migration_name, "ROLLED_BACK", None)
                    return True
        except Exception as e:
            logger.error(f"[Rollback] rollback() failed: {e}")
    
    # 策略 2: 从备份恢复 (危险! 会丢失该 migration 之后的所有变更)
    if not backup_path:
        row = self.data_source.execute(
            "SELECT backup_path FROM schema_migrations WHERE migration_name = ?",
            (migration_name,)
        ).fetchone()
        backup_path = row[0] if row else None
    
    if backup_path and os.path.exists(backup_path):
        logger.warning(
            f"[Rollback] Restoring DB from {backup_path}. "
            f"WARNING: This will lose ALL changes after {migration_name}!"
        )
        # 二次确认 (API 调用时必须显式传 --force)
        db_path = self._get_db_path()
        shutil.copy2(backup_path, str(db_path))
        # 从 schema_migrations 删除该 migration 及之后的所有记录
        self.data_source.execute(
            "DELETE FROM schema_migrations WHERE id >= "
            "(SELECT id FROM schema_migrations WHERE migration_name = ?)",
            (migration_name,)
        )
        self.data_source.commit()
        self._log_audit(migration_name, "ROLLED_BACK_VIA_BACKUP", backup_path)
        return True
    
    # 策略 3: 拒绝
    logger.error(
        f"[Rollback] Cannot rollback {migration_name}: "
        f"no rollback() function and no backup_path. Manual intervention required."
    )
    return False
```

**migration 提供 rollback 的标准签名** (可选, 推荐但非强制):

```python
def rollback(db_path: Path) -> bool:
    """
    回滚 migration (安全降级).
    
    设计原则 (与 Expand-Contract 配合):
    - Expand migration 的 rollback: 删除新增的列/表 (如果空)
    - Migrate migration 的 rollback: 清空 Backfill 的数据, 恢复双写
    - Contract migration 的 rollback: 不可逆 (已删的列无法恢复), 拒绝回滚
    
    Returns:
        True 如果回滚成功
    """
```

**API 调用示例**:

```bash
# 安全回滚 (调用 rollback 函数)
curl -X POST http://172.20.59.7:9206/api/migrations/v008__add_user_code/rollback

# 强制从备份恢复 (危险, 需二次确认)
curl -X POST http://172.20.59.7:9206/api/migrations/v008__add_user_code/rollback \
  -H "Content-Type: application/json" \
  -d '{"force_backup_restore": true, "confirm": "I_KNOW_THIS_WILL_LOSE_DATA"}'
```

#### 7.2.8 CI Lint 集成 (PR 时自动检查)

**头部产品参考**:
- Salesforce: DX 部署前强制 Apex tests 75%+ 覆盖率
- ServiceNow: Update Set preview 自动检测冲突
- Oracle EBS: adop phase=apply 前的 prereq check

**设计**: 新增 `tools/migration_lint.py`, 在 PR 时自动运行 (通过 `.git/hooks/pre-commit` 或 CI).

```python
# tools/migration_lint.py
"""
Migration 质量检查工具.

检查项:
  L1: 命名规范 - 必须匹配 v<NNN>__<desc>.{py,sql}
  L2: 入口签名 - .py 必须有 def migrate(db_path, skip_backup=False) -> bool
  L3: 幂等性 - .sql 必须有 IF NOT EXISTS / IF EXISTS; .py 必须有列存在检查
  L4: docstring - .py 必须有模块级 docstring (背景/方案/回滚)
  L5: 无 DROP TABLE/COLUMN (除非有 [ALLOW_DESTRUCTIVE] 标记)
  L6: 版本号唯一 - 不允许两个文件 v<NNN> 相同
  L7: prerequisites - 如果有 def prerequisites() -> list, 检查引用的 migration 存在
  L8: verify - 推荐有 def verify(db_path) -> bool (WARN, 不 FAIL)

退出码:
  0: 所有检查通过
  1: 有 FAIL 级别问题
  2: 只有 WARN 级别问题
"""
import re
import sys
import ast
from pathlib import Path

MIGRATIONS_DIR = Path("meta/migrations")
NAMING_PATTERN = re.compile(r"^v(\d{3})__([a-z][a-z0-9_]*)\.(py|sql)$")

def lint_naming(file_path: Path) -> list:
    """L1: 命名规范"""
    issues = []
    if not NAMING_PATTERN.match(file_path.name):
        issues.append(("FAIL", f"L1 naming: {file_path.name} does not match v<NNN>__<desc>.{{py,sql}}"))
    return issues

def lint_signature(file_path: Path) -> list:
    """L2: 入口签名"""
    if file_path.suffix != '.py':
        return []
    issues = []
    try:
        tree = ast.parse(file_path.read_text())
        has_migrate = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'migrate':
                has_migrate = True
                args = [a.arg for a in node.args.args]
                if args != ['db_path', 'skip_backup']:
                    issues.append(("FAIL", f"L2 signature: migrate() args should be (db_path, skip_backup=False), got {args}"))
        if not has_migrate:
            issues.append(("FAIL", "L2 signature: missing migrate() function"))
    except SyntaxError as e:
        issues.append(("FAIL", f"L2 signature: syntax error: {e}"))
    return issues

def lint_idempotent(file_path: Path) -> list:
    """L3: 幂等性"""
    issues = []
    content = file_path.read_text()
    if file_path.suffix == '.sql':
        # 简单检查: CREATE TABLE 必须有 IF NOT EXISTS
        if re.search(r"CREATE\s+TABLE\s+\w+\s*\(", content, re.IGNORECASE) and \
           not re.search(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS", content, re.IGNORECASE):
            issues.append(("FAIL", "L3 idempotent: CREATE TABLE without IF NOT EXISTS"))
    else:
        # .py: 检查是否有列存在检查 (PRAGMA table_info 或 _column_exists)
        if 'ALTER TABLE' in content.upper() and 'table_info' not in content.lower() and '_column_exists' not in content.lower():
            issues.append(("WARN", "L3 idempotent: ALTER TABLE without column existence check"))
    return issues

def lint_destructive(file_path: Path) -> list:
    """L5: 无 DROP TABLE/COLUMN"""
    issues = []
    content = file_path.read_text()
    if re.search(r"DROP\s+(TABLE|COLUMN)", content, re.IGNORECASE):
        if '[ALLOW_DESTRUCTIVE]' not in content:
            issues.append(("FAIL", "L5 destructive: DROP TABLE/COLUMN without [ALLOW_DESTRUCTIVE] marker"))
    return issues

def lint_version_unique(files: list) -> list:
    """L6: 版本号唯一"""
    issues = []
    versions = {}
    for f in files:
        m = NAMING_PATTERN.match(f.name)
        if m:
            v = m.group(1)
            if v in versions:
                issues.append(("FAIL", f"L6 version: duplicate version v{v} in {f.name} and {versions[v]}"))
            else:
                versions[v] = f.name
    return issues

def main():
    if not MIGRATIONS_DIR.exists():
        print("[SKIP] migrations dir not found")
        return 0
    
    all_issues = []
    files = sorted(MIGRATIONS_DIR.iterdir())
    
    for f in files:
        if f.name.startswith('_') or f.name.startswith('.'):
            continue
        if f.suffix not in ('.py', '.sql'):
            continue
        
        all_issues.extend(lint_naming(f))
        all_issues.extend(lint_signature(f))
        all_issues.extend(lint_idempotent(f))
        all_issues.extend(lint_destructive(f))
    
    all_issues.extend(lint_version_unique(files))
    
    # 输出
    fails = [i for i in all_issues if i[0] == "FAIL"]
    warns = [i for i in all_issues if i[0] == "WARN"]
    
    for level, msg in all_issues:
        print(f"[{level}] {msg}")
    
    print(f"\nSummary: {len(fails)} FAIL, {len(warns)} WARN")
    
    if fails:
        return 1
    if warns:
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
```

**集成点**:
1. **Pre-commit hook** (`.git/hooks/pre-commit`): 开发者提交前自动跑 lint
2. **CI** (如果有): PR 合并前强制 lint 通过
3. **deploy.sh PHASE 2.4** (新增): 部署前最后跑一次 lint, FAIL 则 exit 1

```bash
# .git/hooks/pre-commit 示例
#!/bin/bash
python tools/migration_lint.py
if [ $? -eq 1 ]; then
    echo "Migration lint FAILED, commit rejected"
    exit 1
fi
```

### 7.3 P2: 测试强制 + 声明式 (5 天, 长期)

#### 7.3.1 Verify 步骤强制

每个 migration 必须配套 `verify()` 函数, MigrationRunner 执行后调用 verify, 失败则回滚.

#### 7.3.2 声明式 schema (长期目标)

用 `meta/migrations/schema.yaml` 描述目标 schema, runner 算 diff 生成 SQL (参考 SAP HDI).

#### 7.3.3 Migration Lint

`tools/migration_lint.py` 检查:
- 命名规范
- 入口签名
- 幂等性 (是否有 IF NOT EXISTS)
- 是否有 verify
- 是否有 prerequisites

---

## 8. 完成标准 ✅

> **必须全部满足才能 merge**

```yaml
acceptance_criteria:
  # P0.5 (历史 migration 补登记, P0 前置必做)
  - [ ] tools/backfill_schema_migrations.py 已创建
  - [ ] staging: SELECT count(*) FROM schema_migrations = 5
  - [ ] prod: SELECT count(*) FROM schema_migrations = 5
  - [ ] 所有 checksum 非 NULL
  - [ ] backfill 脚本幂等 (重复跑不报错)

  # P0
  - [ ] MigrationRunner 支持 .py + .sql 双格式扫描
  - [ ] record_migration 调用时传入 checksum (SHA256)
  - [ ] 启动时 checksum 不匹配会拒绝执行
  - [ ] server.py 用 run_all_migrations 替代硬编码 import
  - [ ] deploy.sh PHASE 2.5 显式调用 migration (7 步流程)
  - [ ] PHASE 2.5.1: DB integrity_check 预检
  - [ ] PHASE 2.5.2: 磁盘空间预检 (3x DB size + 100MB)
  - [ ] PHASE 2.5.3: P0.5 补登记预检 (记录数 >= 5)
  - [ ] PHASE 2.5.4: dry-run 预览
  - [ ] PHASE 2.5.5: 执行 + 并发锁重试 (3 次, 60s 间隔)
  - [ ] PHASE 2.5.6: 记录数验证
  - [ ] PHASE 2.5.7: FAILED 状态验证
  - [ ] migration 失败时 deploy.sh exit 1 + 写告警文件
  - [ ] migration_lock 表 + acquire/release/heartbeat 实现
  - [ ] 多实例并发: 第 2 个实例等待第 1 个完成
  - [ ] meta/migrations/README.md 已创建
  - [ ] _e2e_*.py / _check_dbs.py 已移出 migrations 目录

  # P1
  - [ ] 所有 migration 文件统一为 v<NNN>__<desc>.{py,sql} 命名
  - [ ] 所有 .py migration 提供 def migrate(db_path, skip_backup=False) -> bool
  - [ ] schema_migrations 表增强 (executed_by/execution_time_ms/backup_path/status/error_message/environment)
  - [ ] --dry-run 模式工作正常
  - [ ] prerequisites 检查工作正常
  - [ ] logs/migrations.log 写入审计日志 (含 env + status + checksum)
  - [ ] /api/migrations 状态查询 API 可访问
  - [ ] /api/migrations/<name>/rollback 回滚 API (带二次确认)
  - [ ] tools/migration_lint.py 8 项检查工作 (L1-L8)
  - [ ] tools/test_migration_runner.py 测试通过
  - [ ] monitor_prod.py 集成 check_migration_alerts + check_schema_migrations_health

  # 验证
  - [ ] 本地 dry-run: 所有 pending migration 正确识别
  - [ ] staging 部署: PHASE 2.5 执行成功
  - [ ] prod 部署: PHASE 2.5 执行成功
  - [ ] schema_migrations 表有完整记录 + checksum
  - [ ] checksum 验证: 篡改 migration 文件后启动失败
  - [ ] 多实例并发: 2 个实例同时启动, 第 2 个等待第 1 个完成
  - [ ] 失败告警: migration 失败后 /tmp/migration_alerts/ 有 alert 文件

  # 流程
  - [ ] commit message 含铁律声明:
        L1-Worktree: yes
        L2-NoMain: yes
        L3-Stash: yes
        L4-Status: yes
        L5-Service: yes
  - [ ] 风险评估已记录
  - [ ] .agent-status.json 已更新
```

---

## 9. 风险评估

### 9.1 改动范围

| 维度 | 评估 |
|------|------|
| **文件数量** | P0: 4 modified + 3 new; P1: 6+ renamed + 3 new |
| **新增行数** | ~500 (P0+P1) |
| **删除行数** | ~30 (server.py 硬编码 import) |
| **影响模块** | meta/core/, meta/server.py, deploy_bundle/, meta/migrations/ |

### 9.2 风险等级判定

```yaml
risk_level: high

reason: |
  - 涉及 schema/migration, 影响数据完整性
  - 改动 server.py 启动流程, 可能导致 backend 启动失败
  - 改动 deploy.sh, 可能导致部署失败
  - 重命名 migration 文件, 可能导致版本追踪混乱
```

### 9.3 缓解措施

```yaml
mitigation:
  - 回滚方案:
      - 保留旧 migration 文件 (soft link) 作为 fallback
      - server.py 改动前 git tag pre-migration-v1
      - deploy.sh PHASE 2.5 失败时自动回滚到旧流程
  - 测试覆盖:
      - 本地: python -m meta.core.migration_runner --dry-run
      - staging: 完整部署 + migration 执行 + API 验证
      - prod: 灰度部署 (先停 1 个实例, 验证后再全量)
  - 监控指标:
      - schema_migrations 表记录数 (应 = migration 文件数)
      - logs/migrations.log 无 FAILED 记录
      - /api/migrations 返回 0 pending
      - backend 启动成功 + /api/v1/auth/dev-login 200
```

### 9.4 特别注意 (基于历史教训)

```yaml
critical_lessons:
  - V007.50 教训: 替换 SQLite db 前必须先停 backend 释放 connection
    → migration 前 deploy.sh 必须先 stop backend (PHASE 1 已做)
  - V007.66 教训: 部署前必须确认端口无冲突
    → migration 不涉及端口, 但 deploy.sh PHASE 2.5 在 PHASE 1 (stop) 之后
  - 强制 dry-run 铁律: 改任何 backend 代码后必须跑 local_dryrun.py
    → P0 完成后必须跑 6 项 dry-run + 1 步 API 验证
```

### 9.5 失败处理与告警机制

**头部产品参考**:
- Salesforce: DeployResult.failureMessages + 自动 rollbackOnErrors
- Oracle EBS: adop 失败时自动 phase=abort + 写 adworker.log
- ServiceNow: Update Set commit 失败时回滚 + 通知管理员

**失败分级处理**:

| 失败类型 | 级别 | 处理策略 | 是否阻止部署 |
|---------|------|---------|------------|
| DB integrity_check 失败 | FATAL | exit 1, 拒绝部署, 提示从备份恢复 | YES |
| 磁盘空间不足 | FATAL | exit 1, 提示清理 | YES |
| P0.5 补登记未执行 | FATAL | exit 1, 提示跑 backfill 脚本 | YES |
| Migration lock 抢占超时 | RETRY | 重试 3 次, 每次 60s | 3 次都失败则 YES |
| 单个 migration 执行失败 | FATAL | exit 1, 写告警, 提示回滚 | YES |
| Checksum 不匹配 (文件被改) | FATAL | exit 1, 提示检查文件 | YES |
| verify() 返回 False | WARN | 记录但不阻止 (P2 才强制) | NO (P0/P1) / YES (P2) |
| prerequisites 未满足 | SKIP | 跳过该 migration, 继续下一个 | NO |

**告警机制** (3 层):

```python
# 1. 文件告警 (被 monitor_prod.py 轮询)
def _write_alert(self, alert_type: str, details: dict):
    """写告警文件到 /tmp/migration_alerts/"""
    alert_dir = Path(os.environ.get('ALERT_DIR', '/tmp/migration_alerts'))
    alert_dir.mkdir(exist_ok=True)
    alert_file = alert_dir / f"{alert_type}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.alert"
    content = f"alert_type: {alert_type}\n"
    content += f"timestamp: {datetime.now().isoformat()}\n"
    content += f"host: {socket.gethostname()}\n"
    for k, v in details.items():
        content += f"{k}: {v}\n"
    alert_file.write_text(content)

# 2. 日志告警 (logs/migrations.log)
def _log_audit(self, migration_name: str, status: str, checksum: str = None, error: str = None):
    """写审计日志"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "migrations.log"
    timestamp = datetime.now().isoformat()
    env = os.environ.get('MIGRATION_ENV', 'unknown')
    line = f"{timestamp} [{env}] [{status}] {migration_name}"
    if checksum:
        line += f" checksum={checksum[:16]}"
    if error:
        line += f" error={error}"
    with open(log_file, 'a') as f:
        f.write(line + "\n")
    # 同时打到 logger
    if status == "FAILED":
        logger.error(line)
    elif status == "ROLLED_BACK":
        logger.warning(line)
    else:
        logger.info(line)

# 3. schema_migrations 表记录 (查询用)
def _record_failure(self, migration_name: str, error: str):
    """在 schema_migrations 表记录失败 (P1 status 列就绪后)"""
    try:
        self.data_source.execute(
            "INSERT OR REPLACE INTO schema_migrations "
            "(migration_name, checksum, status, error_message, executed_at) "
            "VALUES (?, NULL, 'FAILED', ?, CURRENT_TIMESTAMP)",
            (migration_name, error[:500])  # 截断长错误信息
        )
        self.data_source.commit()
    except Exception as e:
        logger.error(f"Failed to record failure: {e}")
```

**monitor_prod.py 集成** (新增 2 个检查):

```python
# monitor_prod.py 新增
def check_migration_alerts():
    """检查 /tmp/migration_alerts/ 是否有新告警"""
    alert_dir = Path('/tmp/migration_alerts')
    if not alert_dir.exists():
        return {"status": "ok", "alerts": []}
    
    alerts = []
    for alert_file in alert_dir.glob("*.alert"):
        age_seconds = (datetime.now() - datetime.fromtimestamp(alert_file.stat().st_mtime)).total_seconds()
        if age_seconds < 3600:  # 1 小时内的告警
            alerts.append({
                "file": alert_file.name,
                "content": alert_file.read_text(),
                "age_seconds": int(age_seconds)
            })
    
    return {
        "status": "critical" if alerts else "ok",
        "alerts": alerts
    }

def check_schema_migrations_health(db_path: str):
    """检查 schema_migrations 表健康度"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    
    # 总数
    total = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    
    # 失败数 (P1 status 列就绪后)
    try:
        failed = conn.execute("SELECT count(*) FROM schema_migrations WHERE status='FAILED'").fetchone()[0]
    except sqlite3.OperationalError:
        failed = 0  # status 列不存在
    
    # checksum 缺失数
    null_checksum = conn.execute("SELECT count(*) FROM schema_migrations WHERE checksum IS NULL").fetchone()[0]
    
    conn.close()
    
    return {
        "status": "critical" if failed > 0 else ("warn" if null_checksum > 0 else "ok"),
        "total_migrations": total,
        "failed_migrations": failed,
        "null_checksum_migrations": null_checksum
    }
```

**告警通知方式** (按严重度):
- FATAL: 写 alert 文件 + 日志 + schema_migrations 记录 + **deploy.sh exit 1**
- WARN: 只写日志 + schema_migrations 记录
- INFO: 只写日志

---

## 10. 验收清单

### 10.1 P0 验收 (本地 + staging)

```bash
# 1. 本地单元测试
python tools/test_migration_runner.py
# 期望: 所有测试 PASS

# 2. 本地 dry-run
cd d:/filework/worktrees/release-prep
python -c "from meta.core.migration_runner import MigrationRunner; from meta.core.datasource import get_data_source; r = MigrationRunner(get_data_source()); print(r.run_pending_migrations())"
# 期望: 识别所有 pending migration

# 3. staging 部署
bash deploy_bundle/deploy.sh
# 期望: PHASE 2.5 执行成功, backend 启动成功

# 4. staging API 验证
curl http://172.20.59.7:13011/api/v1/auth/dev-login?username=admin
# 期望: 200

# 5. schema_migrations 表检查
sqlite3 /opt/app/staging/meta/architecture.db "SELECT * FROM schema_migrations;"
# 期望: 所有 migration 都有记录 + checksum
```

### 10.2 P1 验收 (staging + prod)

```bash
# 1. 命名规范检查
ls meta/migrations/v*.{py,sql} | wc -l
# 期望: 所有 migration 文件都是 v<NNN>__ 前缀

# 2. 入口签名检查
python tools/migration_lint.py
# 期望: 所有 .py migration 都有 def migrate(db_path, skip_backup=False)

# 3. dry-run 模式
python -m meta.core.migration_runner --dry-run
# 期望: 打印 pending migration 列表, 不执行

# 4. prerequisites 检查
python -c "from meta.core.migration_runner import MigrationRunner; ..."
# 期望: 有依赖的 migration 在 prerequisite 未执行时被跳过

# 5. 审计日志
cat logs/migrations.log
# 期望: 每次执行有 SUCCESS/FAILED 记录

# 6. API
curl http://172.20.59.7:9206/api/migrations
# 期望: 返回 migration 列表 + 状态
```

---

## 11. 工作日志

> **记录关键决策和发现**

```yaml
decisions:
  - 2026-07-14: 决定自研补齐 (选项 A) 而非引入 Alembic, 因为项目用 SQLite + 手写 SQL, Alembic 改造成本高
  - 2026-07-14: 决定参考 Flyway 命名规范 (v<NNN>__<desc>), 因为简洁且行业通用
  - 2026-07-14: 决定以 v007_50 为内部最佳实践模板, 应用到所有新 migration
  - 2026-07-14: 决定 deploy.sh PHASE 2.5 失败时 exit 1, 不允许继续部署

blockers:
  - (待记录)

insights:
  - 发现 MigrationRunner 框架 90% 完整但只用 5%, 是典型的"有框架但不激活"
  - 发现 server.py 硬编码 import 5 个 migration, 其中 4 个绕过 schema_migrations 表
  - 发现 deploy.sh 完全不调用 migration, 是重大隐患
  - 发现 v007_50/v007_51 质量接近行业最佳实践, 可作模板应用
```

---

## 12. 参考资源

### 12.1 头部产品研究

| 产品 | 核心机制 | 借鉴点 |
|------|---------|-------|
| **SAP HANA HDI** | 声明式 + `.hdbmigrationtable` 版本化 | 声明式 schema diff (P2) |
| **Oracle EBS R12.2** | Online Patching + Codelevel 依赖 | prerequisites 检查 (P1) |
| **Salesforce Metadata API** | 声明式 + 强制 Apex tests 75%+ | 测试强制 (P2) |
| **ServiceNow Update Sets** | Preview + Commit + Back out | dry-run 模式 (P1) |

### 12.2 行业工具对比

| 工具 | 模式 | 适用场景 | 是否引入 |
|------|------|---------|---------|
| **Alembic** | ORM autogenerate | Python + SQLAlchemy | ❌ 改造成本高 |
| **Flyway** | SQL-first | Java/polyglot | ❌ 非 Python 生态 |
| **Liquibase** | XML/YAML/SQL | Enterprise 多 DB | ❌ 过重 |
| **golang-migrate** | SQL files | 轻量 CLI | ❌ 不支持 .py |
| **自研补齐** | 基于 MigrationRunner | 当前项目 | ✅ 推荐 |

### 12.3 项目内部参考

- [meta/core/migration_runner.py](file:///d:/filework/worktrees/release-prep/meta/core/migration_runner.py) — 现有框架
- [meta/migrations/v007_50_add_audit_union_view.py](file:///d:/filework/worktrees/release-prep/meta/migrations/v007_50_add_audit_union_view.py) — 内部最佳实践模板
- [meta/server.py:482-515](file:///d:/filework/worktrees/release-prep/meta/server.py#L482-L515) — 现有硬编码调用
- [deploy_bundle/deploy.sh](file:///d:/filework/worktrees/release-prep/deploy_bundle/deploy.sh) — 部署脚本
- [spec_template.md](file:///d:/filework/worktrees/release-prep/spec_template.md) — Spec 写作模板

### 12.4 外部资源

- [Flyway 命名规范](https://documentation.red-gate.com/fd/migrations-184127470.html)
- [Liquibase ChangeLog](https://docs.liquibase.com/concepts/changelogs.html)
- [SAP HDI Schema Evolution](https://cap.cloud.sap/docs/guides/databases/schema-evolution)
- [Oracle EBS Online Patching](https://docs.oracle.com/cd/E26401_01/doc.122/e22949/T120505T120512.htm)
- [Salesforce Metadata API](https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/api_meta.pdf)
- [ServiceNow Update Sets](https://support.servicenow.com/kb?id=kb_article_view&sysparm_article=KB2835949)

---

## 13. 完成后 Checklist

- [ ] spec.md (本文件) 已填写完整
- [ ] 所有 P0 acceptance_criteria 已勾选
- [ ] 所有 P1 acceptance_criteria 已勾选 (如做 P1)
- [ ] commit message 含铁律声明
- [ ] .agent-status.json 已更新
- [ ] Worktree 工作目录已清理 (debug 脚本删除)
- [ ] **告诉用户"ready for merge T-MIGRATION-V1"**

---

> **铁律提醒**:
> - **L1**: Worktree 强制隔离 (绝不在主工作树 commit)
> - **L2**: 不要碰主工作树文件
> - **L3**: 不要碰 stash@{0}
> - **L4**: 开始前读 .agent-status.json
> - **L5**: 提交前更新状态文件
> - **MIGRATION 铁律**: 替换 SQLite db 前必须先停 backend (V007.50 教训)

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-14 | AI Assistant | 创建 v1.0, 基于现状分析 + 行业最佳实践 + 头部产品对比 |
| 2026-07-15 | AI Assistant | v1.1 细化: 补充 P0.5 历史 migration 补登记 + Expand-Contract 模式 + schema_migrations 表增强 + 多实例 migration_lock + 回滚机制 + CI lint + 失败告警 + 事务边界/checksum算法/超时/备份策略实施细节 |
