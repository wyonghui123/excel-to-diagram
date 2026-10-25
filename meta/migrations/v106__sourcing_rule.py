# -*- coding: utf-8 -*-
"""[v106 2026-10-24] 供应来源规则（Sourcing Rule）元模型建表

背景:
  供应计划域新增「供应来源」配置对象，共 4 张表：
    1. sourcing_rules             供应来源规则头（业务编码 / 用途 / 有效期 / 状态）
    2. sourcing_rule_lines        来源行（库存组织 / 仓库位置 / 供应商 / 生产 + 优先级）
    3. sourcing_rule_assignments  作用域分配（全局 / 物料组 / 物料 + 目标组织/位置）
    4. sourcing_mode_policies     供应方式策略（物料组/物料 × 组织 → 自制/采购/调拨）

  依据: meta/schemas/sourcing_rule.yaml 等 4 个 schema（SSOT）
  说明: 平台启动不自动迁移 schema；sync_schema.py 只 CREATE 缺表，无法表达
        表达式部分唯一索引 —— 故由本迁移承担建表与两条「启用态唯一」索引。

本迁移做两件事（幂等）:
  1. CREATE TABLE IF NOT EXISTS 4 张表 + 常规索引
  2. 两条表达式部分唯一索引（status='active' 时才唯一），用于约束：
       - 同一 (scope_type, scope_ref_id, 目标组织, 目标位置) 只允许一条启用分配
       - 同一 (物料组, 物料, 组织) 只允许一条启用供应方式策略

为何用 migration 而非 sync_schema.py:
  YAML 的 indexes 只能表达列组合，无法表达 IFNULL(...) 表达式 + WHERE 条件；
  唯一性语义必须落在部分唯一索引上（停用记录允许并存），故在迁移里显式建。

数据影响:
  4 张表均为新建空表；不涉及任何数据迁移（architecture.db 体量大，仅建表）。

幂等性:
  - CREATE TABLE/INDEX: IF NOT EXISTS 天然幂等
  - 重复执行为 no-op；verify 只读检查

回滚:
  逆序 DROP TABLE IF EXISTS（先 policy / assignment / line，最后 rules），
  索引随表自动删除。

DDL 单一事实源:
  下列 DDL 由 meta/schemas/sourcing_rule*.yaml、sourcing_mode_policy.yaml 经
  SchemaGenerator('sqlite') 生成后**冻结**于此（含索引规则引擎推导出的
  idx_sourcing_rules_name / idx_sourcing_mode_policies_item_group_id /
  idx_sourcing_mode_policies_item_id），防止手写漂移。
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v106__sourcing_rule.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

RULE_TABLE = "sourcing_rules"
LINE_TABLE = "sourcing_rule_lines"
ASSIGNMENT_TABLE = "sourcing_rule_assignments"
POLICY_TABLE = "sourcing_mode_policies"

# ---- 冻结 DDL（由 yaml 经 SchemaGenerator('sqlite') 生成，顺序: 头 → 行 → 分配 → 策略）----
RULE_DDL = """CREATE TABLE IF NOT EXISTS sourcing_rules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    rule_usage VARCHAR(200) NOT NULL DEFAULT 'all',
    effectivity_start DATETIME NOT NULL,
    effectivity_end DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)"""

LINE_DDL = """CREATE TABLE IF NOT EXISTS sourcing_rule_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    source_type VARCHAR(200) NOT NULL,
    source_org_id INTEGER,
    source_location_id INTEGER,
    supplier_party_id INTEGER,
    rank INTEGER NOT NULL DEFAULT 1,
    allocation_pct REAL NOT NULL DEFAULT 100,
    blocked INTEGER NOT NULL DEFAULT 0,
    fixed INTEGER NOT NULL DEFAULT 0,
    effectivity_start DATETIME NOT NULL,
    effectivity_end DATETIME,
    note VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (rule_id) REFERENCES sourcing_rules(id),
    FOREIGN KEY (source_org_id) REFERENCES orgs(id),
    FOREIGN KEY (source_location_id) REFERENCES locations(id),
    FOREIGN KEY (supplier_party_id) REFERENCES parties(id)
)"""

ASSIGNMENT_DDL = """CREATE TABLE IF NOT EXISTS sourcing_rule_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    scope_type VARCHAR(200) NOT NULL,
    scope_ref_id INTEGER,
    dest_org_id INTEGER,
    dest_location_id INTEGER,
    specificity_rank INTEGER DEFAULT 60,
    seq INTEGER NOT NULL DEFAULT 1,
    effectivity_start DATETIME NOT NULL,
    effectivity_end DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (rule_id) REFERENCES sourcing_rules(id),
    FOREIGN KEY (dest_org_id) REFERENCES orgs(id),
    FOREIGN KEY (dest_location_id) REFERENCES locations(id)
)"""

POLICY_DDL = """CREATE TABLE IF NOT EXISTS sourcing_mode_policies (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_group_id INTEGER NOT NULL,
    item_id INTEGER,
    org_id INTEGER NOT NULL,
    mode VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (item_group_id) REFERENCES item_groups(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id)
)"""

# ---- 常规索引（与 SchemaGenerator.generate_create_index 输出一致）----
RULE_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sourcing_rule_code "
    "ON sourcing_rules(code)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_rule_status_usage "
    "ON sourcing_rules(status, rule_usage)",
    # 索引规则引擎按 display_name 语义推导
    "CREATE INDEX IF NOT EXISTS idx_sourcing_rules_name "
    "ON sourcing_rules(name)",
)

LINE_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sourcing_line_rule_seq "
    "ON sourcing_rule_lines(rule_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_line_rule_rank "
    "ON sourcing_rule_lines(rule_id, rank, seq)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_line_rule_type "
    "ON sourcing_rule_lines(rule_id, source_type)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_line_source_org "
    "ON sourcing_rule_lines(source_org_id)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_line_supplier "
    "ON sourcing_rule_lines(supplier_party_id)",
)

ASSIGNMENT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sourcing_assign_rule "
    "ON sourcing_rule_assignments(rule_id)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_assign_scope "
    "ON sourcing_rule_assignments(scope_type, scope_ref_id, dest_org_id, "
    "dest_location_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_assign_rank "
    "ON sourcing_rule_assignments(specificity_rank, seq)",
)

POLICY_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sourcing_mode_policies_item_group_id "
    "ON sourcing_mode_policies(item_group_id)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_mode_policies_item_id "
    "ON sourcing_mode_policies(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_mode_key "
    "ON sourcing_mode_policies(item_group_id, item_id, org_id)",
    "CREATE INDEX IF NOT EXISTS idx_sourcing_mode_org "
    "ON sourcing_mode_policies(org_id)",
)

# ---- 表达式部分唯一索引（YAML 无法表达，迁移承担）----
#   空值统一折叠为 0，避免 SQLite 中 NULL 互不相等导致唯一性失效。
PARTIAL_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sourcing_assign_active_key "
    "ON sourcing_rule_assignments(scope_type, scope_ref_id, "
    "IFNULL(dest_org_id,0), IFNULL(dest_location_id,0)) "
    "WHERE status='active'",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sourcing_mode_active_key "
    "ON sourcing_mode_policies(item_group_id, IFNULL(item_id,0), org_id) "
    "WHERE status='active'",
)

PARTIAL_INDEX_NAMES = ("idx_sourcing_assign_active_key", "idx_sourcing_mode_active_key")

# ---- verify 用: 期望列（每表一组）----
EXPECTED_COLUMNS = {
    RULE_TABLE: (
        "created_by", "updated_by", "id", "code", "name", "rule_usage",
        "effectivity_start", "effectivity_end", "status", "description",
        "created_at", "updated_at",
    ),
    LINE_TABLE: (
        "created_by", "updated_by", "id", "rule_id", "seq", "source_type",
        "source_org_id", "source_location_id", "supplier_party_id", "rank",
        "allocation_pct", "blocked", "fixed", "effectivity_start",
        "effectivity_end", "note", "created_at", "updated_at",
    ),
    ASSIGNMENT_TABLE: (
        "created_by", "updated_by", "id", "rule_id", "scope_type", "scope_ref_id",
        "dest_org_id", "dest_location_id", "specificity_rank", "seq",
        "effectivity_start", "effectivity_end", "status", "created_at", "updated_at",
    ),
    POLICY_TABLE: (
        "created_by", "updated_by", "id", "item_group_id", "item_id", "org_id",
        "mode", "status", "created_at", "updated_at",
    ),
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _column_names(conn: sqlite3.Connection, table: str):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v106] DB 不存在: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        print('[v106] 开始: 供应来源规则 4 表建表')

        steps = (
            (RULE_TABLE, RULE_DDL, RULE_INDEXES),
            (LINE_TABLE, LINE_DDL, LINE_INDEXES),
            (ASSIGNMENT_TABLE, ASSIGNMENT_DDL, ASSIGNMENT_INDEXES),
            (POLICY_TABLE, POLICY_DDL, POLICY_INDEXES),
        )
        for table, ddl, indexes in steps:
            existed = _table_exists(conn, table)
            conn.execute(ddl)
            for idx in indexes:
                conn.execute(idx)
            print(f'  - [{"KEEP" if existed else "CREATE"}] {table} + {len(indexes)} 索引')

        for idx in PARTIAL_INDEXES:
            conn.execute(idx)
        print(f'  - [CREATE] 表达式部分唯一索引 × {len(PARTIAL_INDEXES)}')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v106] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """4 表存在且关键列齐全；两条表达式部分唯一索引存在。"""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        for table, expected in EXPECTED_COLUMNS.items():
            if not _table_exists(conn, table):
                print(f'[v106 verify] FAIL: {table} 不存在')
                return False
            actual = _column_names(conn, table)
            missing = [c for c in expected if c not in actual]
            if missing:
                print(f'[v106 verify] FAIL: {table} 缺列 {missing}')
                return False

        missing_idx = [n for n in PARTIAL_INDEX_NAMES if not _index_exists(conn, n)]
        if missing_idx:
            print(f'[v106 verify] FAIL: 缺部分唯一索引 {missing_idx}')
            return False

        counts = {
            t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            for t in EXPECTED_COLUMNS
        }
        print(f'[v106 verify] OK: 4 表列完整, 部分唯一索引齐全, rows={counts}')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """逆序 DROP：策略 → 分配 → 行 → 头（索引随表删除）。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v106] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        print('[v106] 回滚: 逆序 DROP 供应来源规则 4 表')
        for table in (POLICY_TABLE, ASSIGNMENT_TABLE, LINE_TABLE, RULE_TABLE):
            conn.execute(f'DROP TABLE IF EXISTS {table}')
            print(f'  - [DROP] {table}')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v106] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_meta_db_path())
    print(f'[v106] migrating {db}')
    ok = migrate(db)
    print(f'[v106] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v106] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)
