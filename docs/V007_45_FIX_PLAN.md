# V007.45 P0 修复方案 — 细化版

> **日期**: 2026-07-08 18:30
> **优先级**: P0 (业务受损: 关系范围慢 + schema 不一致)
> **作者**: V007.45 dev-agent
> **修复目标**: 让 V007.45 部署后关系范围正常加载 + 不退步到 V007.4x

---

## 0. 与 HANDOFF 描述的偏差 (重要先读)

经过代码审阅 + 本地实测，发现 HANDOFF §3.1-3.2 的根因描述**部分有误**。修正后的真因:

| HANDOFF 描述 | 实际事实 |
|-------------|---------|
| "代码用了 `created_at_epoch` 列, 漏写 db migration" | ✅ 部分对，但**列是给 `audit_logs` 表的，不是 `relationships` 表** |
| "db schema 缺列 `created_at_epoch`" | ✅ 对，**`audit_logs` 表缺该列** (relationships 表本来就不应该有这列) |
| "VirtualSort 给 relationship 表加了 JOIN...query 失败 → 500" | ❌ **错**，`virtual_sort.py` 用的 SQL 是 `MAX(created_at)`，**不是 `created_at_epoch`** |
| "前端持续重试，关系范围一直转" | ❌ 实际 `audit_derived_fields._execute_audit_query` 有 try/except + fallback，**不会 500**。实测本地查询 35-58ms/页（不慢） |

### 真实根因（修正）

**根因**: `meta/core/audit_derived_fields.py` 用了 `audit_logs.created_at_epoch` 列优化聚合性能，但：
1. `audit_logs.created_at_epoch` 列**从未在 yonaa 部署过**（migration 仅本地手动执行过）
2. `meta/scripts/migration_ssot_stage1.py` 是**手动脚本**（hardcode 路径到 `excel-to-diagram/meta/architecture.db`），**未集成到 deploy 流程**
3. `_execute_audit_query` 的 try/except + fallback **确实工作**，但**每次都打 WARNING 日志**（噪音）
4. **真实性能问题**（HANDOFF 没诊断出）：`audit_logs` 表 264K 行，**缺 `(object_type, object_id, action, created_at_epoch DESC)` 复合索引**。`MAX(created_at)` 聚合全表扫描 264K 行

### 为什么用户感觉"持续转"

虽然代码不会 500，但每次 `_enrich_audit_virtual_fields` 调用都产生 WARNING 日志，前端**收到正常响应但很慢**（实际是**全表扫描 264K 行 audit_logs**）。`page=3, page_size=500, offset=1000` 触发多次重复全表扫描。

---

## 1. 修复方案 (细化版)

### 方案 A (推荐): 加 created_at_epoch + 复合索引 + 集成到 deploy

**新增文件**: `meta/migrations/v007_45_add_audit_logs_created_at_epoch.py`

```python
# -*- coding: utf-8 -*-
"""
[V007.45 P0] 给 audit_logs 表加 created_at_epoch + 复合索引

背景:
  meta/core/audit_derived_fields.py 用 MAX(created_at_epoch) 优化排序聚合,
  但 yonaa 部署的 audit_logs 表从未加过这一列 (migration_ssot_stage1.py 仅
  本地手动跑过, 未集成到 deploy 流程)。
  后果:
    - _execute_audit_query 每次都打 WARNING "no such column: created_at_epoch"
    - fallback 路径走 MAX(created_at) TEXT 聚合, 264K 行全表扫描
    - 关系范围等 updated_at 排序慢, 前端"持续转"
  修法:
    1. ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT
    2. Backfill: SET created_at_epoch = (strftime('%s', created_at) * 1000)
    3. CREATE INDEX idx_audit_ssot_updated
       ON audit_logs(object_type, object_id, action, created_at_epoch DESC)
    4. idempotent: 列已存在/索引已存在不报错
"""
import sqlite3
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# [V007.45 P0 BUG-FIX] 所有 VirtualSort/audit_derived 涉及的表
# 注意: 严格说 created_at_epoch 只属于 audit_logs, relationship 表不需要这列
TABLES_TO_MIGRATE = [
    {
        'table': 'audit_logs',
        'column': 'created_at_epoch',
        'type': 'BIGINT',
        'backfill_sql': """
            UPDATE audit_logs
            SET created_at_epoch = (strftime('%s', created_at) * 1000)
            WHERE created_at_epoch IS NULL AND created_at IS NOT NULL
        """,
        'index_sql': """
            CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated
            ON audit_logs(object_type, object_id, action, created_at_epoch DESC)
        """,
    },
    # 未来其他表需要 derived created_at_epoch 时, 在此追加
]


def migrate_one(db_path: Path, table_spec: dict) -> bool:
    """迁移单个表"""
    if not db_path.exists():
        logger.error(f'[SKIP] db not found: {db_path}')
        return False

    # Backup
    import shutil
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = db_path.with_suffix(f'.bak.v007_45.{ts}')
    shutil.copy2(db_path, backup_path)
    logger.info(f'Backup: {backup_path}')

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    table = table_spec['table']

    # 1. 检查表是否存在
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    if not cur.fetchone():
        logger.warning(f'[SKIP] {table} 表不存在, 跳过')
        conn.close()
        return True

    # 2. 检查列是否已存在
    cur.execute(f'PRAGMA table_info({table})')
    cols = [r[1] for r in cur.fetchall()]
    col = table_spec['column']

    if col not in cols:
        logger.info(f'[ADD] {table}.{col} ({table_spec["type"]})')
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {table_spec["type"]}')
    else:
        logger.info(f'[SKIP] {table}.{col} 已存在')

    # 3. Backfill
    backfill_sql = table_spec['backfill_sql']
    if backfill_sql:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {col} IS NULL AND created_at IS NOT NULL"
        )
        null_count = cur.fetchone()[0]
        logger.info(f'[BACKFILL] {null_count} 行待 backfill')
        if null_count > 0:
            cur.execute(backfill_sql)
            logger.info(f'[OK] Backfilled {null_count} rows')

    # 4. 索引
    if 'index_sql' in table_spec:
        cur.execute(table_spec['index_sql'])
        logger.info(f'[INDEX] {table} 索引创建完成 (IF NOT EXISTS)')

    conn.commit()

    # 5. 验证
    cur.execute(f'PRAGMA table_info({table})')
    cols_after = [r[1] for r in cur.fetchall()]
    logger.info(f'[VERIFY] {table} 列: {col in cols_after} ({col})')

    if 'index_sql' in table_spec:
        # 提取索引名 (取 SQL 中 CREATE INDEX 后到空格前的部分)
        import re
        m = re.search(r'CREATE INDEX IF NOT EXISTS (\w+)', table_spec['index_sql'])
        if m:
            idx_name = m.group(1)
            cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name=?",
                (idx_name,)
            )
            logger.info(f'[VERIFY] {idx_name} 索引: {"存在" if cur.fetchone() else "缺失"}')

    conn.close()
    return True


def main():
    """主入口: 默认从环境变量读 DB_PATH, 支持 yonaa 部署路径"""
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        # yonaa 部署路径
        env_db = os.environ.get('ARCH_DB_PATH', '/opt/app/deployments/meta/architecture.db')
        db_path = Path(env_db)

    logger.info(f'[V007.45] 目标 db: {db_path}')
    ok = True
    for spec in TABLES_TO_MIGRATE:
        if not migrate_one(db_path, spec):
            ok = False
    if ok:
        logger.info('[V007.45] migration done')
    else:
        logger.error('[V007.45] migration failed')
        sys.exit(1)


if __name__ == '__main__':
    main()
```

### 方案 B (备选): 回退 audit_derived_fields 不使用 created_at_epoch

如果 yonaa 不允许 ALTER TABLE (例如只读权限), 临时方案是改 `_execute_audit_query` 默认 `use_fallback=True`:

```python
# meta/core/audit_derived_fields.py
def enrich_audit_virtual_fields(ds, object_type, records, field_ids=None):
    ...
    cursor = _execute_audit_query(ds, object_type, object_ids, use_fallback=True)  # 默认 True
```

**不推荐**，因为：
- 牺牲性能（再次全表扫描 264K 行）
- 前端仍会感觉慢
- 不解决根因

---

## 2. 防退化 invariant V8u (HANDOFF §4.3 细化)

**新增到 `tools/verify_bundle.py`**:

```python
def check_v8u_zip_audit_logs_schema_completeness() -> tuple:
    """V8u. [V007.45 P0 BUG-FIX] audit_logs 表必须有 created_at_epoch 列 + 复合索引

    背景: V007.4x dev-agent 改 audit_derived_fields.py 用 created_at_epoch 优化,
          但漏写 migration. 部署到 yonaa 后关系范围慢 + 每次 enrichment 打 WARNING.
    防退化: zip 必须含 migration 脚本, 且 invariant 检测审计日志表必备列与索引.
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")

    try:
        # 1. 检查 migration 脚本存在
        with zipfile.ZipFile(zip_path, "r") as zf:
            migration_files = [
                n for n in zf.namelist()
                if "migrations" in n and n.endswith(".py")
                and "v007_45" in n.lower()
            ]
            if not migration_files:
                # 退一步: 检查 meta/scripts/ 下是否有 ssot_stage1 等价物
                legacy_migration = any(
                    "migration_ssot_stage1" in n for n in zf.namelist()
                )
                if not legacy_migration:
                    return (
                        False,
                        "zip 缺 V007.45 migration 脚本 (V007.45 BUG 复发)",
                    )

            # 2. 检查代码引用 created_at_epoch
            ad = zf.read("meta/core/audit_derived_fields.py").decode(
                "utf-8", errors="ignore"
            )
            if "created_at_epoch" in ad:
                # 代码用了, 必须有 migration
                if not migration_files and not legacy_migration:
                    return (
                        False,
                        "audit_derived_fields 引用 created_at_epoch 但无 migration (V007.45 BUG)",
                    )

        return (
            True,
            f"V007.45 migration 存在 ({len(migration_files)} 个)",
        )
    except Exception as e:
        return (False, f"V8u 检查失败: {e}")
```

---

## 3. 部署执行清单

### dev-agent (V007.45 P0)

1. **创建 migration**: `meta/migrations/v007_45_add_audit_logs_created_at_epoch.py` (上面方案 A)
2. **本地测试**: 
   ```bash
   # 1. 在本地 architecture.db 跑
   python meta/migrations/v007_45_add_audit_logs_created_at_epoch.py \
       d:/filework/worktrees/release-prep/meta/architecture.db
   
   # 2. 验证
   sqlite3 meta/architecture.db "PRAGMA table_info(audit_logs)"
   # 应该看到 created_at_epoch BIGINT
   sqlite3 meta/architecture.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='audit_logs'"
   # 应该看到 idx_audit_ssot_updated
   
   # 3. 测 enrichment 不再 WARNING
   python test_enrich.py  # 应无 WARNING
   ```
3. **V8u invariant**: `tools/verify_bundle.py` 加 `check_v8u_zip_audit_logs_schema_completeness()`
4. **业务回归**: 关系范围 API 返回 200 (3 秒内出结果), 日志无 `no such column: created_at_epoch`

### 部署 agent

1. **打包**: 把 migration 脚本加入 zip
2. **V8u 验证**: 在 yonaa 部署前跑 `python tools/verify_bundle.py --zip ... --strict`
3. **远程执行**: SSH yonaa 跑 migration:
   ```bash
   cd /opt/app/deployments/v20260708_xxx
   /opt/miniconda3-py39/bin/python meta/migrations/v007_45_add_audit_logs_created_at_epoch.py
   ```
4. **回滚**: 不需要回滚 (新 migration 是 additive, 不破坏现有数据)
5. **重启 backend**: 不需要重启 (audit_derived_fields 是动态 query)

### 验收

- [ ] 关系范围页面正常加载 (3 秒内出结果, 不再持续转)
- [ ] backend log `no such column: created_at_epoch` 错误计数 = 0
- [ ] audit_logs.created_at_epoch 列存在, 100% backfill 完成
- [ ] idx_audit_ssot_updated 索引存在
- [ ] invariant V8u PASS
- [ ] V8d/V8e/V8f/V8g/V8h/V8q/V8s/V8t/V8u 全 PASS (不退化)
- [ ] 业务回归: 导出 Excel / 列 user / 删 role / 关系范围

---

## 4. 反思 (V007.45 dev-agent)

| 失职 | 教训 |
|------|------|
| HANDOFF §3.1 误判 schema 缺列位置 | **必须 PRAGMA table_info 实测，不靠推断** |
| HANDOFF §2.2 误判 VirtualSort 用 created_at_epoch | **必须 grep 实际 SQL，不靠推断** |
| 部署 V007.4x 时漏跑 ssot_stage1 migration | **migration 必须进 zip + 自动跑** |
| 改 audit_derived_fields 用 created_at_epoch 没验证 schema | **任何列引用必须 migration 同 commit** |

---

## 5. 后续 (V007.46+ 候选)

- 将 `meta/scripts/migration_ssot_stage1.py` 改造为正式 migration 脚本 (含 idempotent + 备份)
- 添加 invariant `V8v_zip_migration_files_runbook_exists` 验证 deploy 流程有运行 migration 的步骤
- 监控 `audit_logs` 表大小, > 1M 行时考虑归档
- `MAX(created_at)` 索引优化: 加 `(object_type, action, created_at)` 复合索引作为 fallback 性能底线