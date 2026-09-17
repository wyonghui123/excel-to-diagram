# -*- coding: utf-8 -*-
"""[V007.50] 创建 v_audit_all VIEW，统一审计日志热/冷查询入口

背景:
  archive_audit_logs.py 将 >180 天的记录从 audit_logs (热) 移入
  audit_logs_archive (冷)，但全项目 10+ 个文件 22+ 处 SQL 只查
  audit_logs，归档后这些查询返回空，导致:
    1. updated_at / current_state_entered_at 虚拟字段返回 None
    2. 等保 2.0 要求归档数据可查询，当前归档=不可见
    3. tools/audit_recovery.py 对象恢复框架因 DELETE/DISSOCIATE 记录
       被归档，永久找不到数据 (P0 数据丢失风险)

修法 (Phase 1):
  1. 确保 audit_logs_archive 表存在；若存在则补齐缺失列
  2. 补充归档表索引 (object_type, action, created_at) 和 (object_type, object_id, action)
  3. 动态检测两表列并集，生成 v_audit_all VIEW SQL
     - 缺失列补 NULL
     - 已有列直接 SELECT
  4. idempotent: VIEW 已存在则 DROP + CREATE (列结构可能变)

部署:
  SSH yonaa:
    cd /opt/app/deployments/v20260714_xxx
    /opt/miniconda3-py39/bin/python meta/migrations/v007_50_add_audit_union_view.py

  本地:
    python meta/migrations/v007_50_add_audit_union_view.py d:/filework/worktrees/release-prep/meta/architecture.db

回滚:
  DROP VIEW IF EXISTS v_audit_all
  (索引和补列保留，不影响现有功能)
"""
import sqlite3
import os
import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# 归档表必须补充的索引 (object_type, action, created_at) 用于 _enrich_updated_at / virtual_sort
ARCHIVE_INDEXES = [
    """
    CREATE INDEX IF NOT EXISTS idx_audit_archive_type_action_created
        ON audit_logs_archive(object_type, action, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_archive_type_id_action
        ON audit_logs_archive(object_type, object_id, action)
    """,
    # 已有索引 (来自 v2_001_audit_log_v2.sql)，IF NOT EXISTS 保证幂等
    """
    CREATE INDEX IF NOT EXISTS idx_audit_archive_retention
        ON audit_logs_archive(retention_until)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_archive_object
        ON audit_logs_archive(object_type, object_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_archive_user
        ON audit_logs_archive(user_id, created_at)
    """,
]


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return bool(cur.fetchone())


def _view_exists(cur, view: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name=?",
        (view,),
    )
    return bool(cur.fetchone())


def _table_columns(cur, table: str) -> list:
    """返回表的列名列表 (按声明顺序)"""
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _table_column_types(cur, table: str) -> dict:
    """返回 {列名: 声明类型} 字典 (类型大写)

    用于判断哪些列是 INTEGER/BIGINT 类型，VIEW 中对归档表分支做 CAST
    避免 TEXT 存储与 INTEGER 查询参数不匹配 (SQLite 类型亲和性规则)
    """
    cur.execute(f"PRAGMA table_info({table})")
    result = {}
    for r in cur.fetchall():
        # r = (cid, name, type, notnull, dflt_value, pk)
        col_name = r[1]
        col_type = (r[2] or "").upper()
        result[col_name] = col_type
    return result


def _is_integer_type(type_str: str) -> bool:
    """判断声明类型是否是 INTEGER/BIGINT (SQLite 类型亲和性规则: 包含 'INT')"""
    return "INT" in type_str


def _ensure_archive_table(cur) -> None:
    """步骤 1: 确保 audit_logs_archive 表存在

    若不存在，按 audit_logs 当前列结构 + archived_at 列创建 (保持列类型一致)。
    若存在但缺列，ALTER TABLE 补齐 (类型统一用 TEXT，SQLite ALTER 不支持改类型)。

    **类型一致性**: 新建归档表时，对 id 列保留 INTEGER PRIMARY KEY，对其他 INTEGER 列
    保留 INTEGER 类型，避免 VIEW 中 WHERE col=? 因 INTEGER vs TEXT 不匹配而漏行。
    """
    if not _table_exists(cur, "audit_logs"):
        # audit_logs 自身不存在，跳过
        logger.warning("[SKIP] audit_logs 表不存在，跳过归档表创建")
        return

    hot_cols = _table_columns(cur, "audit_logs")
    hot_types = _table_column_types(cur, "audit_logs")
    logger.info(f"[INFO] audit_logs 列数: {len(hot_cols)}")

    if not _table_exists(cur, "audit_logs_archive"):
        # 创建归档表: 与 audit_logs 列一致 (含类型) + archived_at
        col_defs = []
        for col in hot_cols:
            col_type = hot_types.get(col, "")
            if col == "id":
                # id 必须是 INTEGER PRIMARY KEY 才能用 rowid 索引
                col_defs.append("    id INTEGER PRIMARY KEY")
            elif _is_integer_type(col_type):
                col_defs.append(f"    {col} INTEGER")
            else:
                # TEXT / VARCHAR / DATETIME / CHAR 等统一用 TEXT (SQLite 动态类型)
                col_defs.append(f"    {col} TEXT")
        col_defs.append("    archived_at TEXT NOT NULL")

        create_sql = (
            "CREATE TABLE audit_logs_archive (\n"
            + ",\n".join(col_defs)
            + "\n)"
        )
        logger.info("[CREATE] audit_logs_archive (镜像 audit_logs 类型 + archived_at)")
        cur.execute(create_sql)
    else:
        # 已存在，补齐缺失列
        archive_cols = _table_columns(cur, "audit_logs_archive")
        logger.info(f"[INFO] audit_logs_archive 列数: {len(archive_cols)}")

        missing = [c for c in hot_cols if c not in archive_cols]
        if missing:
            logger.info(f"[ALTER] audit_logs_archive 补 {len(missing)} 列: {missing}")
            for col in missing:
                # SQLite ALTER TABLE ADD COLUMN 不支持 NOT NULL 无默认值
                # 类型用热表类型 (如果 INTEGER) 否则 TEXT
                hot_type = hot_types.get(col, "")
                if _is_integer_type(hot_type):
                    cur.execute(
                        f"ALTER TABLE audit_logs_archive ADD COLUMN {col} INTEGER"
                    )
                else:
                    cur.execute(
                        f"ALTER TABLE audit_logs_archive ADD COLUMN {col} TEXT"
                    )
        else:
            logger.info("[OK] audit_logs_archive 列已对齐 audit_logs")

        # 确保 archived_at 存在 (旧版归档表必有，但保险起见)
        if "archived_at" not in _table_columns(cur, "audit_logs_archive"):
            logger.warning("[ALTER] audit_logs_archive 补 archived_at 列")
            cur.execute(
                "ALTER TABLE audit_logs_archive ADD COLUMN archived_at TEXT"
            )


def _create_archive_indexes(cur) -> None:
    """步骤 2: 补充归档表索引 (idempotent)"""
    if not _table_exists(cur, "audit_logs_archive"):
        logger.warning("[SKIP] audit_logs_archive 不存在，跳过索引创建")
        return

    for idx_sql in ARCHIVE_INDEXES:
        cur.execute(idx_sql)
    logger.info(f"[INDEX] audit_logs_archive {len(ARCHIVE_INDEXES)} 索引就绪 (IF NOT EXISTS)")


def _build_view_sql(cur) -> str:
    """步骤 3: 动态生成 v_audit_all VIEW SQL

    取两表列并集，按 audit_logs 顺序排列，archived_at 和 created_at_epoch 互用 NULL 补齐。

    **类型对齐**: 对热表中声明为 INTEGER/BIGINT 的列，归档表分支做 CAST(col AS INTEGER)
    避免 SQLite 类型亲和性导致 WHERE col=? 漏匹配 (INTEGER vs TEXT 存储不匹配)
    """
    hot_cols = _table_columns(cur, "audit_logs") if _table_exists(cur, "audit_logs") else []
    archive_cols = (
        _table_columns(cur, "audit_logs_archive")
        if _table_exists(cur, "audit_logs_archive")
        else []
    )

    if not hot_cols:
        raise RuntimeError("audit_logs 表不存在，无法构建 v_audit_all")

    # 热表列类型 (用于判断是否需要 CAST)
    hot_types = _table_column_types(cur, "audit_logs")

    # 并集: hot_cols 优先 (保持顺序), 再加 archive 独有的列 (archived_at)
    union_cols = list(hot_cols)
    for c in archive_cols:
        if c not in union_cols:
            union_cols.append(c)

    logger.info(
        f"[VIEW] 列并集: hot={len(hot_cols)} archive={len(archive_cols)} "
        f"union={len(union_cols)}"
    )

    # 热表 SELECT 子句: hot 有则取，hot 无则 NULL AS col
    hot_selects = []
    for col in union_cols:
        if col in hot_cols:
            hot_selects.append(f"    {col}")
        else:
            hot_selects.append(f"    NULL AS {col}")

    # 归档表 SELECT 子句: archive 有则取，archive 无则 NULL AS col
    # 对热表中声明为 INTEGER/BIGINT 的列做 CAST(col AS INTEGER) 以保证类型一致
    archive_selects = []
    for col in union_cols:
        if col in archive_cols:
            hot_type = hot_types.get(col, "")
            if _is_integer_type(hot_type):
                archive_selects.append(f"    CAST({col} AS INTEGER) AS {col}")
            else:
                archive_selects.append(f"    {col}")
        else:
            archive_selects.append(f"    NULL AS {col}")

    view_sql = (
        "CREATE VIEW v_audit_all AS\n"
        "SELECT\n"
        + ",\n".join(hot_selects)
        + "\nFROM audit_logs\n"
        "UNION ALL\n"
        "SELECT\n"
        + ",\n".join(archive_selects)
        + "\nFROM audit_logs_archive"
    )
    return view_sql


def _create_view(cur) -> None:
    """步骤 3 (执行): DROP IF EXISTS + CREATE VIEW"""
    view_sql = _build_view_sql(cur)

    if _view_exists(cur, "v_audit_all"):
        logger.info("[DROP] v_audit_all (重建以应用新列结构)")
        cur.execute("DROP VIEW IF EXISTS v_audit_all")

    cur.execute(view_sql)
    logger.info("[CREATE] v_audit_all VIEW")


def _verify(cur) -> bool:
    """步骤 5: 验证 VIEW 可查询且列结构正确"""
    ok = True

    if not _view_exists(cur, "v_audit_all"):
        logger.error("[VERIFY][FAIL] v_audit_all 不存在")
        return False

    # 列结构
    cur.execute("PRAGMA table_info(v_audit_all)")
    view_cols = [r[1] for r in cur.fetchall()]
    logger.info(f"[VERIFY] v_audit_all 列数: {len(view_cols)}")

    # 关键列必须存在 (audit_recovery.py 依赖)
    required = ["id", "object_type", "object_id", "action", "field_name",
                "extra_data", "user_name", "created_at", "retention_until",
                "old_value", "created_at_epoch"]
    missing = [c for c in required if c not in view_cols]
    if missing:
        logger.error(f"[VERIFY][FAIL] v_audit_all 缺关键列: {missing}")
        ok = False
    else:
        logger.info(f"[VERIFY][OK] 关键列齐全: {required}")

    # 计数 (不报错即可)
    try:
        cur.execute("SELECT COUNT(*) FROM v_audit_all")
        cnt = cur.fetchone()[0]
        logger.info(f"[VERIFY][OK] SELECT COUNT(*) = {cnt}")
    except Exception as e:
        logger.error(f"[VERIFY][FAIL] SELECT COUNT(*) 报错: {e}")
        ok = False

    # EXPLAIN QUERY PLAN 验证 WHERE 下推 (audit_derived_fields 典型查询)
    try:
        cur.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT MAX(created_at_epoch) FROM v_audit_all "
            "WHERE object_type=? AND object_id=? AND action='UPDATE'",
            ("enum_type", 1),
        )
        plan = cur.fetchall()
        plan_str = " | ".join(str(p) for p in plan)
        if "SCAN" in plan_str and "INDEX" not in plan_str and "SEARCH" not in plan_str:
            logger.warning(f"[VERIFY][WARN] 查询计划全表扫描: {plan_str}")
        else:
            logger.info(f"[VERIFY][OK] 查询计划走索引: {plan_str}")
    except Exception as e:
        logger.warning(f"[VERIFY][WARN] EXPLAIN 失败: {e}")

    return ok


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """主迁移流程 (idempotent)

    Args:
        db_path: SQLite 数据库路径
        skip_backup: 跳过 backup (用于 app_builder 启动时调用，
            避免 backend 每次启动都拷贝 100MB+ DB)
    """
    if not db_path.exists():
        logger.error(f"[SKIP] db not found: {db_path}")
        return False

    # Backup: 仅在 VIEW 不存在时执行 (首次创建)
    # 避免每次 backend 启动都拷贝 100MB+ DB 文件
    need_backup = not skip_backup
    if skip_backup:
        # 检查 VIEW 是否已存在，已存在则不需要 backup
        try:
            conn_check = sqlite3.connect(str(db_path))
            cur_check = conn_check.cursor()
            cur_check.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name='v_audit_all'"
            )
            if cur_check.fetchone():
                need_backup = False
            conn_check.close()
        except Exception:
            pass

    if need_backup:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = db_path.with_suffix(f'.bak.v007_50.{ts}')
        try:
            shutil.copy2(db_path, backup_path)
            logger.info(f'[BACKUP] {backup_path}')
        except Exception as e:
            logger.warning(f'[WARN] backup failed: {e}, continue without backup')

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    try:
        # 检查 audit_logs 是否存在
        if not _table_exists(cur, "audit_logs"):
            logger.warning("[SKIP] audit_logs 表不存在，无需迁移")
            conn.close()
            return True

        # Step 1: 确保 audit_logs_archive 存在且列对齐
        logger.info("[STEP 1] 确保归档表存在且列对齐")
        _ensure_archive_table(cur)

        # Step 2: 补充归档表索引
        logger.info("[STEP 2] 补充归档表索引")
        _create_archive_indexes(cur)

        # Step 3: 创建 v_audit_all VIEW
        logger.info("[STEP 3] 创建 v_audit_all VIEW")
        _create_view(cur)

        conn.commit()

        # Step 4: 验证
        logger.info("[STEP 4] 验证")
        ok = _verify(cur)

        if ok:
            logger.info("[V007.50] migration done [OK]")
        else:
            logger.error("[V007.50] migration completed but verification FAILED")
        return ok

    except Exception as e:
        conn.rollback()
        logger.error(f"[V007.50] migration failed: {e}", exc_info=True)
        return False
    finally:
        conn.close()


def main():
    """主入口: 默认从环境变量读 DB_PATH，支持 yonaa 部署路径"""
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        env_db = os.environ.get(
            'ARCH_DB_PATH', '/opt/app/deployments/meta/architecture.db'
        )
        db_path = Path(env_db)

    logger.info(f'[V007.50] 目标 db: {db_path}')
    ok = migrate(db_path)
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
