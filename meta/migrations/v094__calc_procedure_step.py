# -*- coding: utf-8 -*-
"""[v094 2026-10-13] 定价过程步骤拆表（方案①）: calc_procedures.steps json 列 → calc_procedure_steps 子表

背景:
  定价过程 (calc_procedure) 的计算步骤原存于 calc_procedures.steps 一个 json 列
  (有序数组, 元素形如 {seq, element_type, rate_type_id, condition, params, rolling,
  base_step, subtotal_key})。json 列不可索引、无外键、前端只能渲染只读 popover
  (ui.editable=false), 无法逐行编辑/增删。

  用户拍板「方案①」: 拆为独立子对象 calc_procedure_step (每步一行, 引用回挂父过程)。
    依据: docs/superpowers/specs/2026-10-05-pricing-engine-spec.md §9.3.1 A 表
    yaml: meta/schemas/calc_procedure_step.yaml (SSOT)
    读写: meta/services/pricing_service.py::get_procedure_steps() 按 seq 升序装配
          list[dict] 喂给 meta/core/calc_procedure_executor.execute(steps=...)
          (执行器签名 `execute(steps, base, initial_state)` 不变, 保持纯函数性质)

本迁移做两件事(幂等):
  1. CREATE TABLE IF NOT EXISTS calc_procedure_steps + 两条索引
  2. ALTER TABLE calc_procedures DROP COLUMN steps
     —— 旧列声明为 `steps TEXT NOT NULL`(无 DEFAULT)。拆表后 yaml 已不再声明该列,
        平台通用 BO insert 只写 yaml 字段 ⇒ 新过程 insert 会因 NOT NULL 失败。
        故必须移除该遗留列(SQLite 3.35+ 支持 DROP COLUMN; 本机实测 3.50.4)。

为何用 migration 而非 sync_schema.py:
  SchemaMigrator.migrate 只 CREATE 缺表 + ALTER ADD 列, **从不 DROP 列** ⇒ 遗留
  `steps NOT NULL` 移不掉。且平台启动不自动迁移 schema; 故须 migration 承担。

数据影响:
  拆表时 calc_procedures = 0 行(已实测) ⇒ 无数据迁移; DROP COLUMN 无信息损失。

幂等性:
  - CREATE TABLE/INDEX: IF NOT EXISTS 天然幂等
  - DROP COLUMN: 仅当 steps 列存在才执行(重复执行为 no-op)

回滚:
  重新 ADD steps 列(NOT NULL DEFAULT '[]'); 并从 calc_procedure_steps 反序列化回填
  (每过程聚合为有序 json 数组); 再 DROP 新建子表。

DDL 单一事实源:
  下列 DDL 由 meta/schemas/calc_procedure_step.yaml 经 SchemaGenerator('sqlite')
  生成后**冻结**于此(与 test_pricing_service.py 的建表口径一致, 防漂移)。
"""
import json
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v094__calc_procedure_step.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

STEP_TABLE = "calc_procedure_steps"
PARENT_TABLE = "calc_procedures"

# 由 yaml 经 SchemaGenerator('sqlite') 生成后冻结 (见模块头「DDL 单一事实源」)
STEP_DDL = """CREATE TABLE IF NOT EXISTS calc_procedure_steps (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calc_procedure_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    element_type VARCHAR(200) NOT NULL,
    rate_type_id INTEGER,
    condition INTEGER,
    params TEXT,
    rolling INTEGER NOT NULL DEFAULT 0,
    base_step VARCHAR(200),
    subtotal_key VARCHAR(200),
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)"""

STEP_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_calc_procedure_step_proc_seq "
    "ON calc_procedure_steps(calc_procedure_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_calc_procedure_step_element "
    "ON calc_procedure_steps(element_type)",
)

# verify 用: 期望列
EXPECTED_COLUMNS = (
    "created_by", "updated_by", "id", "calc_procedure_id", "seq", "element_type",
    "rate_type_id", "condition", "params", "rolling", "base_step", "subtotal_key",
    "description", "created_at", "updated_at",
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _column_names(conn: sqlite3.Connection, table: str):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return col in _column_names(conn, table)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v094] DB 不存在: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v094] 开始: 定价过程步骤拆表'
              ' (calc_procedures.steps json 列 → calc_procedure_steps 子表)')

        # 1. 建子表 + 索引 (幂等)
        existed = _table_exists(conn, STEP_TABLE)
        conn.executescript(STEP_DDL)
        for idx in STEP_INDEXES:
            conn.execute(idx)
        print(f'  - [{"KEEP" if existed else "CREATE"}] {STEP_TABLE} + 2 索引')

        # 2. 移除父表遗留 steps 列 (幂等: 仅在存在时)
        if _column_exists(conn, PARENT_TABLE, 'steps'):
            before = len(_column_names(conn, PARENT_TABLE))
            conn.execute(f'ALTER TABLE {PARENT_TABLE} DROP COLUMN steps')
            after = len(_column_names(conn, PARENT_TABLE))
            print(f'  - [DROP COL] {PARENT_TABLE}.steps ({before} → {after} 列)')
        else:
            print(f'  - [SKIP] {PARENT_TABLE}.steps 已不存在')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v094] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """子表存在且列完整; 父表 steps 遗留列已移除。"""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, STEP_TABLE):
            print(f'[v094 verify] FAIL: {STEP_TABLE} 不存在')
            return False
        actual = _column_names(conn, STEP_TABLE)
        missing = [c for c in EXPECTED_COLUMNS if c not in actual]
        if missing:
            print(f'[v094 verify] FAIL: {STEP_TABLE} 缺列 {missing}')
            return False
        if _column_exists(conn, PARENT_TABLE, 'steps'):
            print(f'[v094 verify] FAIL: {PARENT_TABLE}.steps 遗留列仍在')
            return False
        n = conn.execute(f'SELECT COUNT(*) FROM {STEP_TABLE}').fetchone()[0]
        print(f'[v094 verify] OK: {STEP_TABLE} 列完整 ({len(actual)} 列), '
              f'父表 steps 列已移除, 子表 rows={n}')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """子表 → 父表 steps json 列: 回填 + DROP 子表。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v094] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v094] 回滚: calc_procedure_steps → calc_procedures.steps json 列')

        # 1. 若 steps 列不存在则补回 (NOT NULL DEFAULT '[]')
        if not _column_exists(conn, PARENT_TABLE, 'steps'):
            conn.execute(
                f"ALTER TABLE {PARENT_TABLE} "
                f"ADD COLUMN steps TEXT NOT NULL DEFAULT '[]'")
            print(f'  - [ADD COL] {PARENT_TABLE}.steps (NOT NULL DEFAULT \'[]\')')
        else:
            print(f'  - [SKIP] {PARENT_TABLE}.steps 已存在')

        # 2. 从子表反序列化回填(每过程聚合成有序 json 数组)
        if _table_exists(conn, STEP_TABLE):
            rows = conn.execute(
                f"SELECT calc_procedure_id, seq, element_type, rate_type_id, condition, "
                f"params, rolling, base_step, subtotal_key FROM {STEP_TABLE} "
                f"ORDER BY calc_procedure_id, seq"
            ).fetchall()
            grouped = {}
            for (pid, seq, et, rt, cond, params, rolling, base, sub) in rows:
                grouped.setdefault(pid, []).append({
                    "seq": seq,
                    "element_type": et,
                    "rate_type_id": rt,
                    "condition": None if cond is None else bool(cond),
                    "params": json.loads(params) if params else {},
                    "rolling": bool(rolling),
                    "base_step": base,
                    "subtotal_key": sub,
                })
            for pid, steps in grouped.items():
                conn.execute(
                    f"UPDATE {PARENT_TABLE} SET steps = ? WHERE id = ?",
                    (json.dumps(steps, ensure_ascii=False), pid))
            conn.execute(f"DROP TABLE IF EXISTS {STEP_TABLE}")
            print(f'  - [REVERT] {len(grouped)} 个过程的步骤已回填, 并 DROP {STEP_TABLE}')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v094] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_meta_db_path())
    print(f'[v094] migrating {db}')
    ok = migrate(db)
    print(f'[v094] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v094] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)
