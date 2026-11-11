# -*- coding: utf-8 -*-
"""
Schema 同步工具 - 从元数据驱动数据库 Schema 更新

支持多数据源：
    python -m meta.tools.sync_schema --diff                    # 查看变更
    python -m meta.tools.sync_schema --execute                 # 执行同步（默认SQLite）
    python -m meta.tools.sync_schema --source sqlite --execute # SQLite
    python -m meta.tools.sync_schema --source mysql --execute  # MySQL
    python -m meta.tools.sync_schema --source postgresql       # PostgreSQL
"""

import argparse
import json
import hashlib
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

from meta import registry, get_meta_object
from meta.core.datasource import DataSource, DataSourceType, get_data_source, DataSourceFactory
from meta.core.schema_generator import (
    SchemaGenerator, SchemaMigrator, sync_schema_from_meta,
    enum_check_values, normalize_sql_type, parse_schema_text,
    rebuild_table_with_checks,
)
from meta.core.models import MetaObject, MetaField, FieldType, ObjectType
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir


SCHEMA_VERSION_FILE = "meta/schemas/.schema_version.json"
GENERATED_SCHEMA_PATH = "meta/schemas/generated_schema.sql"
DEFAULT_CHECK_DB = "meta/architecture.db"


def get_all_meta_objects() -> List:
    """获取所有元数据对象"""
    # [PoC A fix 2026-09-22] 确保 yaml 已加载到 registry
    if not registry.list_objects():
        register_from_directory(get_yaml_schema_dir())
    objects = []
    for obj_id in registry.list_objects():
        obj = get_meta_object(obj_id)
        if obj:
            objects.append(obj)
    return objects


def compute_meta_hash(meta_object: MetaObject) -> str:
    """计算元模型的哈希值（用于变更检测）"""
    content = "{0}|{1}|{2}".format(
        meta_object.table_name,
        "|".join([
            "{0}:{1}:{2}:{3}".format(
                f.db_column or "", f.field_type.value, f.required, f.unique
            ) for f in sorted(meta_object.fields, key=lambda x: (x.db_column or ""))
        ]),
        meta_object.semantics.hierarchy_level
    )
    return hashlib.md5(content.encode()).hexdigest()


def load_schema_version() -> Dict[str, Any]:
    """加载Schema版本信息"""
    version_file = Path(SCHEMA_VERSION_FILE)
    if version_file.exists():
        with open(version_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"objects": {}, "last_sync": None}


def save_schema_version(version_data: Dict[str, Any]):
    """保存Schema版本信息"""
    version_file = Path(SCHEMA_VERSION_FILE)
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_data["last_sync"] = datetime.now().isoformat()
    with open(version_file, "w", encoding="utf-8") as f:
        json.dump(version_data, f, indent=2, ensure_ascii=False)


def detect_changes(meta_objects: List[MetaObject]) -> Dict[str, Any]:
    """检测元模型变更"""
    version_data = load_schema_version()
    stored_objects = version_data.get("objects", {})
    
    changes = {
        "new_objects": [],
        "deleted_objects": list(stored_objects.keys()),
        "modified_objects": [],
        "new_fields": [],
        "deleted_fields": [],
        "modified_fields": [],
        "no_change": [],
    }
    
    for obj in meta_objects:
        obj_id = obj.id
        current_hash = compute_meta_hash(obj)
        
        if obj_id in stored_objects:
            changes["deleted_objects"].remove(obj_id)
            stored_hash = stored_objects[obj_id].get("hash", "")
            stored_fields = stored_objects[obj_id].get("fields", [])
            
            if current_hash != stored_hash:
                current_fields = {f.db_column: f for f in obj.fields}
                stored_field_set = set(stored_fields)
                current_field_set = set(current_fields.keys())
                
                new_cols = current_field_set - stored_field_set
                deleted_cols = stored_field_set - current_field_set
                
                for col in new_cols:
                    changes["new_fields"].append({
                        "object": obj_id,
                        "field": col,
                        "type": current_fields[col].field_type.value,
                    })
                
                for col in deleted_cols:
                    changes["deleted_fields"].append({
                        "object": obj_id,
                        "field": col,
                    })
                
                changes["modified_objects"].append({
                    "object": obj_id,
                    "name": obj.name,
                    "new_fields": list(new_cols),
                    "deleted_fields": list(deleted_cols),
                })
            else:
                changes["no_change"].append(obj_id)
        else:
            changes["new_objects"].append({
                "object": obj_id,
                "name": obj.name,
                "table": obj.table_name,
            })
    
    return changes


def show_diff(meta_objects: List[MetaObject]):
    """显示变更差异"""
    changes = detect_changes(meta_objects)
    
    print("=== 元模型变更分析 ===")
    print()
    
    if changes["new_objects"]:
        print("【新增对象】")
        for obj in changes["new_objects"]:
            print("  + {0}: {1} (表: {2})".format(obj["object"], obj["name"], obj["table"]))
        print()
    
    if changes["deleted_objects"]:
        print("【删除对象】")
        for obj_id in changes["deleted_objects"]:
            print("  - {0}".format(obj_id))
        print()
    
    if changes["new_fields"]:
        print("【新增字段】")
        for f in changes["new_fields"]:
            print("  + {0}.{1} ({2})".format(f["object"], f["field"], f["type"]))
        print()
    
    if changes["deleted_fields"]:
        print("【删除字段】")
        for f in changes["deleted_fields"]:
            print("  - {0}.{1}".format(f["object"], f["field"]))
        print()
    
    if changes["no_change"]:
        print("【无变更】")
        print("  {0}".format(", ".join(changes["no_change"])))
        print()
    
    total_changes = (
        len(changes["new_objects"]) +
        len(changes["deleted_objects"]) +
        len(changes["new_fields"]) +
        len(changes["deleted_fields"])
    )
    
    print("=== 统计 ===")
    print("  新增对象: {0}".format(len(changes["new_objects"])))
    print("  删除对象: {0}".format(len(changes["deleted_objects"])))
    print("  新增字段: {0}".format(len(changes["new_fields"])))
    print("  删除字段: {0}".format(len(changes["deleted_fields"])))
    print("  无变更:   {0}".format(len(changes["no_change"])))
    print()
    
    if total_changes == 0:
        print("[DECORATIVE] Schema已是最新，无需同步")
    else:
        print("! 检测到 {0} 处变更，需要同步Schema".format(total_changes))
    
    return changes


def create_data_source(source_type: str, **kwargs) -> DataSource:
    """
    创建数据源
    
    Args:
        source_type: 数据源类型 (sqlite, mysql, postgresql)
        **kwargs: 连接参数
        
    Returns:
        数据源实例
    """
    return get_data_source(source_type, **kwargs)


def sync_with_datasource(ds: DataSource, dry_run: bool = False):
    """
    使用指定数据源同步 Schema
    
    Args:
        ds: 数据源实例
        dry_run: 是否只预览
    """
    print("=== Schema 同步 ===")
    print("数据源: {0}".format(ds.source_type.value))
    print()
    
    meta_objects = get_all_meta_objects()
    
    changes = show_diff(meta_objects)
    
    total_changes = (
        len(changes["new_objects"]) +
        len(changes["deleted_objects"]) +
        len(changes["new_fields"]) +
        len(changes["deleted_fields"])
    )
    
    if total_changes == 0:
        ds.disconnect()
        return
    
    migrator = SchemaMigrator(ds)
    sql_list = migrator.migrate(meta_objects, dry_run=dry_run)
    
    print("\n=== 执行的 SQL ===")
    for i, sql in enumerate(sql_list, 1):
        print("\n[{0}]".format(i))
        print(sql)
    
    if not dry_run:
        version_data = {"objects": {}}
        for obj in meta_objects:
            version_data["objects"][obj.id] = {
                "hash": compute_meta_hash(obj),
                "fields": [f.db_column for f in obj.fields],
                "table": obj.table_name,
            }
        save_schema_version(version_data)
        print("\n[DECORATIVE] Schema版本已更新")
    
    ds.disconnect()
    print("\n=== 完成 ===")


def sync_local(db_path: str, dry_run: bool = False):
    """同步本地 SQLite 数据库"""
    ds = create_data_source("sqlite", path=db_path)
    sync_with_datasource(ds, dry_run)


def sync_mysql(host: str, port: int, user: str, password: str, database: str, dry_run: bool = False):
    """同步 MySQL 数据库"""
    ds = create_data_source(
        "mysql",
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    sync_with_datasource(ds, dry_run)


def sync_postgresql(host: str, port: int, user: str, password: str, database: str, dry_run: bool = False):
    """同步 PostgreSQL 数据库"""
    ds = create_data_source(
        "postgresql",
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    sync_with_datasource(ds, dry_run)


def generate_schema():
    """生成 Schema 文件"""
    print("=== 生成 Schema ===")
    
    generator = SchemaGenerator()
    meta_objects = get_all_meta_objects()
    
    schema_sql = generator.generate_full_schema(meta_objects)
    
    output_path = "meta/schemas/generated_schema.sql"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("-- 自动生成的 Schema\n")
        f.write("-- 生成时间: {0}\n\n".format(datetime.now()))
        f.write(schema_sql)
    
    print("Schema 已生成: {0}".format(output_path))
    print("\n=== Schema 内容 ===")
    print(schema_sql)


def build_expected_schema(meta_objects: List[MetaObject]) -> Dict[str, Dict[str, Any]]:
    """YAML 期望 DDL：{表: {columns: {列: {type, check}}}}（忽略视图/虚拟对象）。"""
    generator = SchemaGenerator("sqlite")
    expected = {}
    for obj in meta_objects:
        if obj.object_type in (ObjectType.VIRTUAL, ObjectType.VIEW) or not obj.table_name:
            continue
        columns = {}
        for field in obj.get_persistent_fields():
            if field.db_column in columns:
                continue
            columns[field.db_column] = {
                "type": normalize_sql_type(generator._sql_type(field)),
                "check": enum_check_values(field) or None,
            }
        expected[obj.table_name] = {"object": obj.id, "columns": columns}
    return expected


def load_snapshot_schema(path: str = GENERATED_SCHEMA_PATH) -> Dict[str, Dict[str, Any]]:
    """读取 generated_schema.sql 快照。"""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return parse_schema_text(file_path.read_text(encoding="utf-8"))


def load_db_schema(ds: DataSource) -> Dict[str, Dict[str, Any]]:
    """读取真实库结构（SQLite 取 sqlite_master；其他源回退列信息，无 CHECK）。"""
    schema = {}
    for table in ds.list_tables():
        sql_text = ""
        try:
            cursor = ds.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
            row = cursor.fetchone()
            sql_text = row[0] if row else ""
        except Exception:
            sql_text = ""
        columns = {}
        if sql_text:
            for name, info in parse_schema_text(sql_text).items():
                if name.lower() == table.lower():
                    columns = info["columns"]
                    break
        if not columns:
            for name, info in ds.get_table_columns(table).items():
                columns[name] = {"type": normalize_sql_type(info.get("type")), "check": None}
        schema[table] = {"columns": columns}
    return schema


def compare_schema(expected: Dict[str, Dict[str, Any]],
                   actual: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """比对期望与实际：表缺失 / 列缺失 / 类型不符 / CHECK 缺失或不一致。"""
    report = {
        "missing_tables": [],
        "missing_columns": [],
        "type_mismatches": [],
        "check_missing": [],
    }
    for table in sorted(expected):
        spec = expected[table]
        got = actual.get(table)
        if got is None:
            report["missing_tables"].append(table)
            continue
        got_columns = got["columns"]
        for column in sorted(spec["columns"]):
            want = spec["columns"][column]
            if column not in got_columns:
                report["missing_columns"].append("{0}.{1}".format(table, column))
                continue
            have = got_columns[column]
            if normalize_sql_type(have.get("type")) != normalize_sql_type(want.get("type")):
                report["type_mismatches"].append(
                    "{0}.{1}: 期望 {2} / 实际 {3}".format(
                        table, column, want.get("type"), have.get("type")))
            want_check = want.get("check")
            if not want_check:
                continue
            have_check = have.get("check")
            if not have_check:
                report["check_missing"].append("{0}.{1}".format(table, column))
            elif set(have_check) != set(want_check):
                report["check_missing"].append(
                    "{0}.{1}: 期望 {2} / 实际 {3}".format(
                        table, column, want_check, have_check))
    return report


def print_schema_report(report: Dict[str, List[str]], source_label: str) -> int:
    """打印四类差异；返回差异总数。"""
    print("=== Schema 单源比对 ===")
    print("比对目标: {0}".format(source_label))
    print()
    titles = (
        ("missing_tables", "【表缺失】"),
        ("missing_columns", "【列缺失】"),
        ("type_mismatches", "【类型不符】"),
        ("check_missing", "【CHECK 缺失或不一致】"),
    )
    total = 0
    for key, title in titles:
        items = report.get(key, [])
        total += len(items)
        if not items:
            continue
        print(title)
        for item in items:
            print("  - {0}".format(item))
        print()
    print("=== 统计 ===")
    print("  表缺失: {0}".format(len(report["missing_tables"])))
    print("  列缺失: {0}".format(len(report["missing_columns"])))
    print("  类型不符: {0}".format(len(report["type_mismatches"])))
    print("  CHECK:  {0}".format(len(report["check_missing"])))
    print("  合计:   {0}".format(total))
    print()
    return total


def apply_schema_fixes(db_path: str, report: Dict[str, List[str]],
                       expected: Dict[str, Dict[str, Any]]) -> int:
    """按报告补齐：仅 ADD COLUMN 与 CHECK 重建；DROP/类型变更一律拒绝。"""
    if report["missing_tables"] or report["type_mismatches"]:
        print("! 存在表缺失或类型不符，需人工处理（--apply 不处理这两类）")

    applied = 0
    # 1) ADD COLUMN
    for entry in report["missing_columns"]:
        table, _, column = entry.partition(".")
        col_def = expected.get(table, {}).get("columns", {}).get(column)
        if not col_def:
            continue
        conn = sqlite3.connect(str(Path(db_path)), timeout=30)
        try:
            conn.execute("ALTER TABLE {0} ADD COLUMN {1} {2}".format(
                table, column, col_def["type"]))
            conn.commit()
            applied += 1
            print("  + ADD COLUMN {0}.{1} {2}".format(table, column, col_def["type"]))
        finally:
            conn.close()

    # 2) CHECK 补齐（按表聚合，一次重建）
    per_table = {}
    for entry in report["check_missing"]:
        key = entry.split(":", 1)[0]
        table, _, column = key.partition(".")
        values = expected.get(table, {}).get("columns", {}).get(column, {}).get("check")
        if values:
            per_table.setdefault(table, {})[column] = values
    for table, checks in per_table.items():
        if rebuild_table_with_checks(db_path, table, checks):
            applied += 1
            print("  + CHECK {0}: {1}".format(table, ", ".join(sorted(checks))))

    print("  --apply 完成，共 {0} 项".format(applied))
    return applied


def check_schema(args) -> int:
    """--check：比对期望 DDL 与真实库/快照；有差异 exit 1。"""
    meta_objects = get_all_meta_objects()
    expected = build_expected_schema(meta_objects)

    if args.diff:
        show_diff(meta_objects)

    if args.against == "snapshot":
        actual = load_snapshot_schema()
        source_label = GENERATED_SCHEMA_PATH
    else:
        if args.source != "sqlite":
            print("! --check 本轮只支持 SQLite（--source sqlite）")
            return 2
        db_path = args.local or DEFAULT_CHECK_DB
        if not Path(db_path).exists():
            print("! 数据库不存在: {0}".format(db_path))
            return 2
        ds = create_data_source("sqlite", path=db_path)
        try:
            actual = load_db_schema(ds)
        finally:
            ds.disconnect()
        source_label = db_path

    report = compare_schema(expected, actual)
    total = print_schema_report(report, source_label)

    if total and args.apply and args.against == "db":
        apply_schema_fixes(args.local or DEFAULT_CHECK_DB, report, expected)

    if total:
        print("FAIL: 检测到 {0} 处 Schema 漂移".format(total))
        return 1
    print("OK: YAML 期望 DDL 与 {0} 一致".format(source_label))
    return 0


def list_supported_sources():
    """列出支持的数据源"""
    print("=== 支持的数据源 ===")
    for src_type in DataSourceFactory.list_supported():
        print("  - {0}".format(src_type.value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Schema 同步工具")
    parser.add_argument("--dry-run", action="store_true", help="只生成 SQL 不执行")
    parser.add_argument("--execute", action="store_true", help="执行 Schema 变更")
    parser.add_argument("--diff", action="store_true", help="显示变更差异")
    parser.add_argument("--generate", action="store_true", help="生成 Schema 文件")
    parser.add_argument("--list-sources", action="store_true", help="列出支持的数据源")
    parser.add_argument("--check", action="store_true",
                        help="比对 YAML 期望 DDL 与真实库/快照，有漂移则 exit 1")
    parser.add_argument("--against", choices=("db", "snapshot"), default="db",
                        help="--check 的比对目标：db=真实库 / snapshot=generated_schema.sql")
    parser.add_argument("--apply", action="store_true",
                        help="仅补齐 ADD COLUMN 与 CHECK（不处理 DROP / 类型变更）")

    parser.add_argument("--source", type=str, default="sqlite", 
                        help="数据源类型 (sqlite, mysql, postgresql)")
    parser.add_argument("--local", type=str, default=None,
                        help="SQLite 数据库路径（默认 data/app.db；--check 默认 meta/architecture.db）")
    
    parser.add_argument("--host", type=str, default="localhost", help="数据库主机")
    parser.add_argument("--port", type=int, default=3306, help="数据库端口")
    parser.add_argument("--user", type=str, default="root", help="数据库用户")
    parser.add_argument("--password", type=str, default="", help="数据库密码")
    parser.add_argument("--database", type=str, default="", help="数据库名称")
    
    args = parser.parse_args()
    
    if args.list_sources:
        list_supported_sources()
    elif args.generate:
        generate_schema()
    elif args.check:
        return check_schema(args)
    elif args.diff:
        meta_objects = get_all_meta_objects()
        show_diff(meta_objects)
    elif args.source == "sqlite":
        sync_local(args.local or "data/app.db", dry_run=args.dry_run)
    elif args.source == "mysql":
        sync_mysql(args.host, args.port, args.user, args.password, args.database, dry_run=args.dry_run)
    elif args.source == "postgresql":
        sync_postgresql(args.host, args.port, args.user, args.password, args.database, dry_run=args.dry_run)
    else:
        print("不支持的数据源类型: {0}".format(args.source))
        list_supported_sources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
