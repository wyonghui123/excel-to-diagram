# MIGRATION_GUIDE.md

> **目标读者**: AI Agent / 工程师 (写/跑 migration 的实战)
> **最后更新**: 2026-07-15
> **设计依据**: [docs/MIGRATION_SPEC.md](file:///d:/filework/worktrees/release-prep/docs/MIGRATION_SPEC.md) (1711 行, 历史 design)
> **本文件用途**: 5 分钟上手 + 实战 cookbook, 不重复 design 细节

---

## §0. 一图全貌

```
┌─────────────────────────────────────────────────────────────────┐
│ 本地 (Windows)                                                    │
│                                                                  │
│  meta/migrations/                                                │
│  ├── v001__audit_log_v2.sql        ← 已存在, legacy              │
│  ├── v045__add_audit_logs.py       ← 已存在                      │
│  ├── v046__add_change_notification.sql                            │
│  ├── v047__...py                                                │
│  └── ...                                                        │
│                                                                  │
│  tools/                                                          │
│  ├── migration_lint.py            ← 写完必跑                     │
│  ├── migration_lint.legacy.yaml   ← 26 个老文件白名单           │
│  ├── backfill_schema_migrations.py ← 老环境首次部署用            │
│  ├── monitor_migrations.py        ← 健康监控 (含 --check-regression) │
│  └── regression_test_suite.py     ← 9 场景 sqlite io error 演练 │
│                                                                  │
│  meta/core/migration_runner.py     ← 实际跑 (deploy.sh PHASE 2.6) │
└─────────────────────────────────────────────────────────────────┘
              │
              │ 部署时: deploy.sh → PHASE 2.6 → migration_runner
              │ 升级时: backfill_schema_migrations.py (一次性)
              │ 跑后:   monitor_migrations.py --check-regression
              │ chaos:  regression_test_suite.py (staging)
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 远端 yonaa:172.20.59.7                                            │
│                                                                  │
│  /opt/app/deployments/meta/architecture.db        (prod)         │
│  /opt/app/staging/deploy/meta/architecture.db     (staging)      │
│  ├── schema_migrations 表                                         │
│  │   id | migration_name | checksum | executed_at | status | env  │
│  │   -- | --             | --       | --          | --     | --  │
│  │   1  | v001__...sql   | <sha256> | 2026-07-15  | SUCCESS| prod│
│  │   2  | v045__...py    | <sha256> | 2026-07-15  | SUCCESS| prod│
│  │   3  | (no migrate()) | <sha256> | 2026-07-15  | SKIP   | prod│
│  └── ...                                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## §1. 写一个 migration (5 步)

### §1.1 命名

**新文件**: `v<NNN>__<desc>.{py,sql}` (NNN = 3 位数字, 全表唯一)

| 描述 | 名字 | 说明 |
|------|------|------|
| 加表 | `v046__add_user_session.sql` | SQL DDL |
| 加列 | `v047__add_user_avatar.py` | Python (有逻辑) |
| 加索引 | `v048__idx_user_email.sql` | SQL 性能优化 |
| 加数据 | `v049__seed_default_roles.py` | Python 业务 |

**老文件**: 见 `tools/migration_lint.legacy.yaml` (26 个, 自动豁免)

### §1.2 SQL 文件模板

```sql
-- v046__add_user_session.sql
-- 用途: 加 user_session 表 (login token 持久化)
-- 依赖: 无
-- 失败容忍: 是 (idempotent)

CREATE TABLE IF NOT EXISTS user_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    ip_address TEXT,
    user_agent TEXT,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_used_at INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_session_token ON user_session(token);
CREATE INDEX IF NOT EXISTS idx_user_session_user_id ON user_session(user_id);
```

**Runner 自动**:
- ✅ `IF NOT EXISTS` 不再幂等错
- ✅ `duplicate column` 自动跳过
- ✅ trigger `BEGIN/END` 块用 executescript 跑

### §1.3 Python 文件模板

```python
# v047__add_user_avatar.py
# 用途: 给 users 表加 avatar_url 列
# 依赖: 无
# 失败容忍: 是 (idempotent)

def migrate(db_conn) -> None:
    """迁移入口 (runner 通过此函数调用)"""
    cur = db_conn.cursor()
    # 幂等: 用 PRAGMA table_info 查列存在性
    cur.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in cur.fetchall()}
    if 'avatar_url' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    if 'avatar_updated_at' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN avatar_updated_at INTEGER")
    db_conn.commit()

def verify(db_conn) -> bool:
    """(可选) runner 跑完后会调用验证, 返回 True=健康"""
    cur = db_conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in cur.fetchall()}
    return 'avatar_url' in cols and 'avatar_updated_at' in cols
```

**Runner 行为**:
- 有 `migrate()` → 调它
- 有 `verify()` → 跑完调
- 都没 → 标记为 `SKIP` (legacy 兼容)

### §1.4 跑 lint

```bash
python tools/migration_lint.py
# 输出: 0 FAIL, 8 WARN, exit 0
```

**5 个 lint 规则**:
- **L1** naming: 必须 `v<NNN>__<desc>.{py,sql}` (legacy 豁免)
- **L2** signature: Python 必须有 `migrate(db_conn)` (legacy 豁免)
- **L3** verify: 推荐 `verify(db_conn) -> bool` (WARN, 不阻塞)
- **L4** docstring: 顶部要有 `# 用途: ...` (WARN, 不阻塞)
- **L5** destructive: 无 `DROP TABLE/COLUMN` (legacy 豁免, 新文件必须用 `IF EXISTS`)

### §1.5 本地测一遍

```bash
# 1. 写测试
python -c "
import sqlite3
import importlib.util
spec = importlib.util.spec_from_file_location('m', 'meta/migrations/v047__add_user_avatar.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c = sqlite3.connect(':memory:')
c.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
m.migrate(c)
print('OK', m.verify(c))
"

# 2. 跑 P0/P1 单元测试
python tests/test_migration_runner_p0.py  # 29/29
python tests/test_migration_runner_p1.py  # 27/27
```

---

## §2. 跑 migration (部署时)

**部署时 deploy.sh 自动跑** (PHASE 2.6):
```bash
python3 -m meta.core.migration_runner
```

**手动跑 (远端)**:
```bash
# 远端 prod
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner --status" 9200
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner" 9200
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 9200
```

**预期输出** (本会话后):
```
executed 18 migrations
  - 13 SUCCESS (含 v001-v045 + 新文件)
  - 0 FAILED
  - 5 SKIP (legacy 无 migrate())

monitor: WARN (0 failed, 3 NULL checksum legacy)
```

---

## §3. 老环境首次部署 (backfill)

**场景**: 新加一台 yonaa 机器, 已有 DB schema 但 schema_migrations 表空。

**步骤**:
```bash
# 1. 跑 dry-run 看看会写什么
python tools/yonaa_exec.py exec "python3 tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run" 9200

# 2. 实际写
python tools/yonaa_exec.py exec "python3 tools/backfill_schema_migrations.py --db-path meta/architecture.db" 9200

# 3. 跑 migration_runner (会跳过已 backfill 的)
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner" 9200
```

**backfill 写什么**:
- 12 条 LEGACY 列表 (含 v001-v051 老 migration)
- 自动修复: 重复名/无后缀/截断名
- 补填 checksum (从源文件算 SHA256)

---

## §4. 监控 & 故障

### §4.1 健康监控

```bash
# [V007.55] 加 --check-regression 跑回归测试 (staging 9 个 sqlite io error 场景)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 19200
# staging: 输出 regression PASS/FAIL/SKIP
# prod:    自动跳过 (db 不含 /staging/), 返回 WARN
# 退出码: 0=OK / 1=FAIL / 2=WARN (CI/告警友好)

# 不带 regression (只看 schema_migrations)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py" 9200
# 输出 3 级:
#   OK    - 健康
#   WARN  - 有 NULL checksum / orphan migration_name (不阻塞)
#   CRIT  - 有 FAILED / 缺失
```

### §4.2 常见问题

| 症状 | 原因 | 解决 |
|------|------|------|
| `duplicate column` | 列已存在 | 改 SQL 加 `IF NOT EXISTS` 或 runner 自动跳过 (idempotent) |
| `near ";": syntax error` | trigger BEGIN/END 块错切分 | runner 已修 (用 executescript); 重跑即可 |
| `No module: pytest` | test_utils 硬依赖 | 已修 (try/except 包装); 重试 |
| `duplicate migration_name` | 同名登记 2 次 | backfill 自动 dedup; 手动 `DELETE FROM schema_migrations WHERE status='FAILED'` |
| `checksum mismatch` | 源文件被改 | 这是**故意**的, 表被改了; 改 `meta/core/migration_runner.py` 加白名单或重命名 |

### §4.3 强制重跑 (回滚后)

```bash
# 1. 删 FAILED 记录
python -c "
import sqlite3
c = sqlite3.connect('/opt/app/deployments/meta/architecture.db')
c.execute(\"DELETE FROM schema_migrations WHERE status='FAILED'\")
c.commit()
print('deleted:', c.total_changes)
"

# 2. 重跑
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner" 9200
```

---

## §5. P0/P1 单元测试 (本地)

```bash
# P0: 框架基础
python tests/test_migration_runner_p0.py   # 29/29 PASS

# P1: 进阶 (version tracking / prereq / lock / skip)
python tests/test_migration_runner_p1.py   # 27/27 PASS

# 远端验证
python tools/yonaa_exec.py exec "python3 -m unittest tests.test_migration_runner_p0" 9200
```

---

## §6. Schema 表结构 (远端 DB)

```sql
CREATE TABLE schema_migrations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name  TEXT    NOT NULL UNIQUE,     -- 文件名 (含后缀)
    checksum        TEXT,                         -- 源文件 SHA256 (legacy 可空)
    executed_at     TEXT    NOT NULL,            -- ISO timestamp
    executed_by     TEXT    DEFAULT 'system',     -- 跑的人 / 系统
    duration_ms     INTEGER,                      -- 跑这条耗时
    status          TEXT    DEFAULT 'SUCCESS',     -- SUCCESS / FAILED / SKIP
    environment     TEXT    DEFAULT 'unknown',     -- prod / staging / dev
    error_message   TEXT                          -- 失败原因
);

CREATE TABLE migration_locks (
    id            INTEGER PRIMARY KEY,
    locked_at     TEXT NOT NULL,
    locked_by     TEXT NOT NULL
);
```

---

## §7. 升级检查清单 (新环境/新版本)

- [ ] 远端 `python3 -c "import yaml"` 通 (migration_runner 间接 import)
  - 不通: `python3 -m pip install pyyaml -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com`
- [ ] DB schema 已应用
  - 不确定: 跑 `backfill_schema_migrations.py --dry-run`
- [ ] schema_migrations 表已建
  - 跑 `python3 -m meta.core.migration_runner --status` (它会 ensure_migrations_table)
- [ ] 跑一次 `python3 -m meta.core.migration_runner` (幂等, 安全)
- [ ] 跑 `python3 tools/monitor_migrations.py --check-regression` (健康 + 回归测试, 仅 staging)
- [ ] 跑 `python3 tools/migration_lint.py` (规范)

---

**详细 design**: 见 [MIGRATION_SPEC.md](file:///d:/filework/worktrees/release-prep/docs/MIGRATION_SPEC.md) (1711 行, 必读时再读)
**总入口**: [DEPLOY_INFRASTRUCTURE.md](file:///d:/filework/worktrees/release-prep/DEPLOY_INFRASTRUCTURE.md)
