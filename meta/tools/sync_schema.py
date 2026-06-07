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
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from meta import registry, list_meta_objects, get_meta_object
from meta.core.datasource import DataSource, DataSourceType, get_data_source, DataSourceFactory
from meta.core.schema_generator import SchemaGenerator, SchemaMigrator, sync_schema_from_meta
from meta.core.models import MetaObject, MetaField, FieldType


SCHEMA_VERSION_FILE = "meta/schemas/.schema_version.json"


def get_all_meta_objects() -> List:
    """获取所有元数据对象"""
    objects = []
    for obj_id in list_meta_objects():
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
                f.db_column, f.field_type.value, f.required, f.unique
            ) for f in sorted(meta_object.fields, key=lambda x: x.db_column)
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


def list_supported_sources():
    """列出支持的数据源"""
    print("=== 支持的数据源 ===")
    for src_type in DataSourceFactory.list_supported():
        print("  - {0}".format(src_type.value))


def main():
    parser = argparse.ArgumentParser(description="Schema 同步工具")
    parser.add_argument("--dry-run", action="store_true", help="只生成 SQL 不执行")
    parser.add_argument("--execute", action="store_true", help="执行 Schema 变更")
    parser.add_argument("--diff", action="store_true", help="显示变更差异")
    parser.add_argument("--generate", action="store_true", help="生成 Schema 文件")
    parser.add_argument("--list-sources", action="store_true", help="列出支持的数据源")
    
    parser.add_argument("--source", type=str, default="sqlite", 
                        help="数据源类型 (sqlite, mysql, postgresql)")
    parser.add_argument("--local", type=str, default="data/app.db", help="SQLite 数据库路径")
    
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
    elif args.diff:
        meta_objects = get_all_meta_objects()
        show_diff(meta_objects)
    elif args.source == "sqlite":
        sync_local(args.local, dry_run=args.dry_run)
    elif args.source == "mysql":
        sync_mysql(args.host, args.port, args.user, args.password, args.database, dry_run=args.dry_run)
    elif args.source == "postgresql":
        sync_postgresql(args.host, args.port, args.user, args.password, args.database, dry_run=args.dry_run)
    else:
        print("不支持的数据源类型: {0}".format(args.source))
        list_supported_sources()


if __name__ == "__main__":
    main()
