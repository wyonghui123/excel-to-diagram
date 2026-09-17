# Database Migrations

> 本目录存放所有数据库 migration 脚本 (.sql / .py)

## 命名规范 (P1 目标, P0 过渡期保持现有名称)

```
v<NNN>__<description>.{py,sql}
```

- `v<NNN>`: 3 位版本号, 零填充 (v001, v002, ..., v999)
- `__`: 双下划线分隔符 (参考 Flyway)
- `<description>`: 蛇形命名, 简洁描述 (create_users_table, add_audit_logs)
- `.sql`: 纯 SQL migration
- `.py`: 需要 Python 逻辑的 migration

示例:
```
v001__create_users_table.sql
v002__add_audit_logs.py
v003__add_change_notification_tables.sql
```

## 入口签名规范

所有 `.py` migration 必须提供:

```python
def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """
    <migration 描述>

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 是否跳过备份 (runner 已统一备份, 内部可跳过)

    Returns:
        True 如果成功执行或已执行 (幂等)
    """
```

可选 (推荐):
```python
def verify(db_path: Path) -> bool:
    """验证 migration 是否已正确执行"""

def prerequisites() -> list:
    """声明依赖的其他 migration name, 如 ['v004__enhance_audit_log_v2']"""
```

## 执行流程

1. **部署时**: `deploy.sh` PHASE 2.6 自动调用 `python -m meta.core.migration_runner`
2. **启动兜底**: `server.py` 启动时也调用 `run_all_migrations(data_source)` (兜底)
3. 所有 migration 记录到 `schema_migrations` 表 (含 SHA256 checksum)
4. 审计日志写入 `logs/migrations.log`

## 新增 migration 步骤

1. 创建文件: `meta/migrations/v<NNN>__<desc>.{py,sql}`
2. `.py` 文件必须提供 `def migrate(db_path, skip_backup=False) -> bool`
3. 推荐: `def verify(db_path) -> bool` + `def prerequisites() -> list`
4. 本地测试: `python -m meta.core.migration_runner --dry-run`
5. staging 验证后才能部署 prod

## 重要约束

- **幂等性**: 所有 migration 必须可重复执行 (用 `IF NOT EXISTS` / 列存在检查)
- **无 DROP**: 禁止单次 migration 内 `DROP TABLE` / `DROP COLUMN` (用 Expand-Contract 模式)
- **Breaking change**: 必须分 2-3 版本部署 (Expand → Migrate → Contract)
- **下划线前缀**: `_*.py` 文件被 runner 自动跳过 (测试/工具脚本)

## P0.5 补登记 (一次性)

激活 runner 前必须先跑:
```bash
python tools/backfill_schema_migrations.py --db-path meta/architecture.db --dry-run
python tools/backfill_schema_migrations.py --db-path meta/architecture.db
```

## 参考

- 行业最佳实践: Flyway / Liquibase / SAP HDI / Oracle EBS
- 项目内部最佳实践模板: `v007_50_add_audit_union_view.py` (质量最高)
- Spec 文档: `docs/MIGRATION_SPEC.md`

## Seed Migration 模板（v079 2026-09-02 新增）

> **场景**：从 production 导出基准数据（如角色权限维度配置），在新环境 / 重置环境 / 全新部署时回填。
> **典型案例**：[v079__seed_permission_set_dimension_scopes.py](v079__seed_permission_set_dimension_scopes.py) — 把 production 38 行 dimension scope seed 到 staging。

### 关键设计

| 维度 | 设计 | 原因 |
|---|---|---|
| **幂等** | 按 `permission_set_id+dimension_code` 查重 → 已存在跳过 | 同一 migration 可重复跑 |
| **备份** | `permission_set_dimension_scopes_pre_v079_backup` 整表备份 | rollback 数据可恢复 |
| **防御** | seed 前校验 ps_id 必须存在于 permission_sets | 防 seed 孤儿引用 |
| **JSON 校验** | seed 前 `json.loads(dim_values)` 验合法性 | 防脏数据 |
| **created_by 标记** | seed 行用 `created_by='v079_seed'` | downgrade 可精准删除 |
| **三件套** | `migrate()` + `verify()` + `downgrade()` | 标准化接口 |

### 模板结构

```python
"""[v079 2026-09-02] seed <table_name> from production template."""

import json
import sqlite3
from pathlib import Path

# 1. seed 数据列表 (从 production 导出)
SEED_DATA: List[Tuple[parent_id, child_field, ...]] = [
    (1, 'sub_domain', 'include', '[1,2]', 1),
    (2, 'sub_domain', 'include', '[3]', 1),
    # ...
]

BACKUP_TABLE = '<table>_pre_v079_backup'
TARGET_TABLE = '<table>'

def _table_exists(conn, name): ...
def _create_backup(conn): ...   # 同 v078 备份模式
def _seed_one(conn, ...): ...   # 单行 INSERT OR IGNORE 逻辑
def migrate(db_path, skip_backup=False): ...
def verify(db_path): ...
def downgrade(db_path, skip_backup=False): ...

if __name__ == '__main__':
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta/architecture.db')
    success = migrate(db)
    print(f'success={success}, verify={verify(db)}')
```

### 部署注意

- **权限**：seed migration 需要**root 启动的 server 进程**写 DB，或 staging 上 `chown` 给 nobody
- **dry-run**：先 cp DB 到 `/tmp` 测试：
  ```bash
  cp /opt/app/staging/meta/architecture.db /tmp/_test.db
  python3 /tmp/v079_migration.py /tmp/_test.db
  # 验证 inserted=N, skipped=M, verify=True
  rm /tmp/_test.db
  ```
- **幂等测试**：跑 2 次，第二次应该是 inserted=0, skipped=N
- **verify()**：跑完调一次，确认所有 SEED_DATA 都已落库
