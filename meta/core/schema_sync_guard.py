"""启动期 Schema 同步的声明哈希守卫（TEST-EFF P1-1）

背景
----
`manage_api.init_services()` 每次 create_app() 都会整轮 `sync_schema_from_meta()`：
逐对象比较表/列 → 逐条 `CREATE INDEX IF NOT EXISTS`（每条独立 commit）→ 清理过时
索引。实测单进程约 2.9s，802 个测试文件各起一次进程，累计成本极高。

设计（与 `init_menu_permissions.menu_sync_guard` 同一套「声明内容哈希」范式）
------------------------------------------------------------------
1. 哈希覆盖「期望 Schema 的完整生成结果」——按对象 id 排序后逐个生成
   CREATE TABLE / CREATE VIEW 语句与索引语句，连同声明版本号一起 sha256。
   即：YAML/代码声明不变 ⇒ 哈希不变（不是版本号相等就跳过）。
2. 守卫记录写在同一目标 DB 的 `schema_sync_guard` 表，并按「对象集合」分键：
   新库/快照库无记录 ⇒ 自动全量；对象集合变化（新增 BO）⇒ 新键 ⇒ 自动全量。
3. 命中前提是「声明哈希一致」**且**「期望的表/视图在 sqlite_master 中全部存在」
   （一次查询）。任何一方不满足都回落全量同步，保留自愈能力。
4. 全量同步抛异常时不写守卫 ⇒ 下次启动重试。

刻意不校验索引是否存在：`SchemaMigrator` 对索引创建失败是刻意吞错的
（部分唯一索引遇上存量重复数据属正常降级），把索引纳入前提会让守卫永久失效。
索引缺失只会在声明变更后的下一次全量同步中补回。

维护约定
--------
`_DECLARATION_VERSION` 必须在 `SchemaMigrator` / `SchemaGenerator` 的生成语义
发生变化时 +1，否则老库的守卫会错误地继续命中。
"""

import hashlib
import logging
import re
from typing import Any, List, Set, Tuple

logger = logging.getLogger(__name__)

# 生成语义版本：SchemaGenerator / SchemaMigrator 行为变化时必须递增
_DECLARATION_VERSION = 1

_GUARD_TABLE = "schema_sync_guard"

_INDEX_NAME_RE = re.compile(
    r"INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`\[]?(\w+)", re.IGNORECASE
)


def _persistent_objects(meta_objects: List[Any]) -> List[Any]:
    from meta.core.models import ObjectType
    return [
        obj for obj in meta_objects
        if obj is not None
        and obj.object_type in (ObjectType.ENTITY, ObjectType.VIEW)
        and getattr(obj, "table_name", None)
    ]


def _fingerprint(meta_objects: List[Any], dialect: str) -> Tuple[str, str, Set[str]]:
    """返回 (scope_key, declaration_hash, expected_tables)"""
    from meta.core.schema_generator import SchemaGenerator

    objects = sorted(_persistent_objects(meta_objects), key=lambda o: o.id)
    generator = SchemaGenerator(dialect=dialect)

    scope = hashlib.sha256(
        ("|".join(o.id for o in objects) + f"#{dialect}").encode("utf-8")
    ).hexdigest()[:40]

    hasher = hashlib.sha256()
    hasher.update(f"schema-sync-v{_DECLARATION_VERSION}#{dialect}\n".encode("utf-8"))
    expected_tables: Set[str] = set()
    for obj in objects:
        table = obj.table_name
        expected_tables.add(table)
        hasher.update(
            f"{obj.id}|{table}|{obj.object_type.value}\n".encode("utf-8")
        )
        create_sql = generator.generate_create_table(obj) or ""
        hasher.update(create_sql.encode("utf-8"))
        for index_sql in generator.generate_create_index(obj):
            hasher.update(index_sql.encode("utf-8"))

    return scope, hasher.hexdigest(), expected_tables


def _query_names(data_source, kind_sql: str) -> Set[str]:
    cursor = data_source.execute(
        f"SELECT name FROM sqlite_master WHERE type IN ({kind_sql})"
    )
    rows = cursor.fetchall() if cursor is not None else []
    names = set()
    for row in rows:
        names.add(row[0] if isinstance(row, (tuple, list)) else row["name"])
    return names


def _lookup_guard(data_source, scope_key: str) -> str:
    try:
        cursor = data_source.execute(
            f"SELECT declaration_hash FROM {_GUARD_TABLE} WHERE scope_key = ?",
            (scope_key,),
        )
        row = cursor.fetchone() if cursor is not None else None
        if row is None:
            return ""
        return row[0] if isinstance(row, (tuple, list)) else row["declaration_hash"]
    except Exception:
        return ""


def _write_guard(data_source, scope_key: str, declaration_hash: str) -> None:
    from datetime import datetime
    data_source.execute(
        f"CREATE TABLE IF NOT EXISTS {_GUARD_TABLE} ("
        "scope_key VARCHAR(80) PRIMARY KEY,"
        "declaration_hash VARCHAR(64) NOT NULL,"
        "applied_at DATETIME)"
    )
    data_source.execute(
        f"INSERT OR REPLACE INTO {_GUARD_TABLE} "
        "(scope_key, declaration_hash, applied_at) VALUES (?, ?, ?)",
        (scope_key, declaration_hash, datetime.now().isoformat(timespec="seconds")),
    )
    data_source.commit()


def _guard_hit(data_source, scope_key: str, declaration_hash: str,
               expected_tables: Set[str]) -> bool:
    try:
        data_source.execute(
            f"CREATE TABLE IF NOT EXISTS {_GUARD_TABLE} ("
            "scope_key VARCHAR(80) PRIMARY KEY,"
            "declaration_hash VARCHAR(64) NOT NULL,"
            "applied_at DATETIME)"
        )
        data_source.commit()
        if _lookup_guard(data_source, scope_key) != declaration_hash:
            return False
        actual = _query_names(data_source, "'table', 'view'")
        missing = expected_tables - actual
        if missing:
            logger.info(
                "[SchemaGuard] 声明未变但缺失表/视图 %d 个，回落全量同步: %s",
                len(missing), sorted(missing)[:10],
            )
            return False
        return True
    except Exception as e:
        logger.warning("[SchemaGuard] 守卫检查失败，回落全量同步: %s", e)
        return False


def guarded_sync_schema(data_source, meta_objects: List[Any], dry_run: bool = False):
    """带声明哈希守卫的 sync_schema_from_meta。

    命中守卫时直接返回 []（与"同步完成、无 DDL"的返回值同构），调用方无需区分。
    dry_run 永远执行完整比较（守卫只服务于真实启动路径）。
    """
    from meta.core.schema_generator import sync_schema_from_meta

    if data_source is None or dry_run:
        return sync_schema_from_meta(data_source, meta_objects, dry_run)

    try:
        dialect = getattr(data_source, "dialect", "sqlite") or "sqlite"
        scope_key, declaration_hash, expected_tables = _fingerprint(
            meta_objects, dialect)
    except Exception as e:
        logger.warning("[SchemaGuard] 指纹计算失败，回落全量同步: %s", e)
        return sync_schema_from_meta(data_source, meta_objects, dry_run)

    if _guard_hit(data_source, scope_key, declaration_hash, expected_tables):
        logger.info(
            "[SchemaGuard] 声明未变且表结构齐全，跳过 schema sync（%d 对象）",
            len(expected_tables),
        )
        return []

    executed = sync_schema_from_meta(data_source, meta_objects, dry_run)
    try:
        _write_guard(data_source, scope_key, declaration_hash)
    except Exception as e:
        logger.warning("[SchemaGuard] 守卫写入失败（下次将重跑全量）: %s", e)
    return executed


def warm_guard_for_db(db_path: str, schema_dir: str = None) -> bool:
    """在指定 DB 上跑一次「守卫感知」的平台 schema 同步（供 base_test.db 预热）。

    test.py 用 SQLite backup 生成 base_test.db 后调用本函数，使该快照带上
    守卫记录；各 worker 复制出的库因此可直接命中，省掉每进程约 2.9s 的全量同步。
    返回 True 表示本次命中或落地成功。
    """
    import os

    from meta.core.datasource import get_data_source
    from meta.core.models import registry
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    register_from_directory(schema_dir or get_yaml_schema_dir())
    objects = [registry.get(t) for t in registry.list_types()]
    objects = [obj for obj in objects if obj is not None]
    if not objects:
        raise RuntimeError("schema registry 为空，无法预热守卫")

    data_source = get_data_source("sqlite", database=db_path)
    guarded_sync_schema(data_source, objects)
    return True


def _main(argv=None) -> int:
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="在指定 DB 上预热 schema_sync_guard（用于 base_test.db）")
    parser.add_argument("--db", required=True, help="目标 SQLite 库路径")
    parser.add_argument("--schema-dir", default=None, help="meta/schemas 目录")
    args = parser.parse_args(argv)
    warm_guard_for_db(args.db, args.schema_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())