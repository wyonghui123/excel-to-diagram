# -*- coding: utf-8 -*-
"""
Schema 生成器 - 从元数据对象生成数据库 Schema

支持：
- 从 MetaObject 生成 CREATE TABLE 语句
- 从 MetaField 生成列定义
- 从 MetaRelation 生成外键约束
- 生成索引创建语句
- Schema 差异比较和增量更新
- 多数据源支持（通过 DataSource 抽象）
"""

import logging

logger = logging.getLogger(__name__)

from typing import List, Dict, Tuple, Optional
from meta.core.models import (
    MetaObject, MetaField, MetaRelation, FieldType, RelationType,
    ObjectType, FieldStorage, ViewConfig, IndexType, IndexSource
)
from meta.core.datasource import DataSource, DataSourceType, get_data_source
from meta.core.sql_adapters import SQLDataSource


class SchemaGenerator:
    """Schema 生成器"""
    
    TYPE_MAPPING = {
        FieldType.STRING: "VARCHAR(200)",
        FieldType.INTEGER: "INTEGER",
        FieldType.FLOAT: "REAL",
        FieldType.BOOLEAN: "INTEGER",
        FieldType.DATETIME: "DATETIME",
        FieldType.TEXT: "TEXT",
        FieldType.JSON: "TEXT",
    }
    
    def __init__(self, dialect: str = "sqlite"):
        self.dialect = dialect
    
    def generate_create_table(self, meta_object: MetaObject) -> str:
        """生成 CREATE TABLE 或 CREATE VIEW 语句"""
        if meta_object.object_type == ObjectType.VIRTUAL:
            return ""
        
        if not meta_object.table_name:
            return ""
        
        if meta_object.object_type == ObjectType.VIEW:
            return self._generate_create_view(meta_object)
        
        columns = []
        foreign_keys = []
        seen_db_columns = set()
        
        for field in meta_object.get_persistent_fields():
            if field.db_column in seen_db_columns:
                continue
            seen_db_columns.add(field.db_column)
            col_def = self._generate_column_definition(field)
            columns.append(col_def)
        
        for relation in meta_object.relations:
            if relation.relation_type == RelationType.PARENT_CHILD:
                fk_def = self._generate_foreign_key(relation)
                if fk_def:
                    foreign_keys.append(fk_def)
        
        all_columns = columns + foreign_keys
        
        sql = "CREATE TABLE IF NOT EXISTS {0} (\n    {1}\n)".format(
            meta_object.table_name,
            ",\n    ".join(all_columns)
        )
        
        return sql
    
    def _generate_create_view(self, meta_object: MetaObject) -> str:
        """生成 CREATE VIEW 语句"""
        if meta_object.view_config and meta_object.view_config.sql_definition:
            return "CREATE VIEW IF NOT EXISTS {0} AS {1}".format(
                meta_object.table_name,
                meta_object.view_config.sql_definition
            )
        
        if meta_object.view_definition:
            return "CREATE VIEW IF NOT EXISTS {0} AS {1}".format(
                meta_object.table_name,
                meta_object.view_definition
            )
        
        if meta_object.view_config:
            return self._generate_view_from_config(meta_object)
        
        return ""
    
    def _generate_view_from_config(self, meta_object: MetaObject) -> str:
        """从 view_config 生成 VIEW SQL"""
        config = meta_object.view_config
        if not config or not config.sources:
            return ""
        
        parts = []
        
        select_fields = []
        for field in meta_object.fields:
            if field.source:
                select_fields.append("{0} as {1}".format(field.source, field.db_column))
            else:
                select_fields.append(field.db_column)
        
        parts.append("SELECT {0}".format(", ".join(select_fields)))
        
        from_parts = []
        for src in config.sources:
            if src.alias:
                from_parts.append("{0} as {1}".format(src.object, src.alias))
            else:
                from_parts.append(src.object)
        parts.append("FROM {0}".format(", ".join(from_parts)))
        
        for join in config.joins:
            join_type = join.type.upper()
            parts.append("{0} JOIN {1} ON {2}".format(
                join_type, join.target, join.condition
            ))
        
        if config.filters:
            filter_parts = []
            for f in config.filters:
                if f.value is not None:
                    if isinstance(f.value, str):
                        filter_parts.append("{0} {1} '{2}'".format(f.field, f.operator.upper(), f.value))
                    else:
                        filter_parts.append("{0} {1} {2}".format(f.field, f.operator.upper(), f.value))
                else:
                    filter_parts.append("{0} {1}".format(f.field, f.operator.upper()))
            parts.append("WHERE {0}".format(" AND ".join(filter_parts)))
        
        if config.group_by:
            parts.append("GROUP BY {0}".format(", ".join(config.group_by)))
        
        if config.having:
            parts.append("HAVING {0}".format(config.having))
        
        if config.order_by:
            parts.append("ORDER BY {0}".format(", ".join(config.order_by)))
        
        sql = "CREATE VIEW IF NOT EXISTS {0} AS {1}".format(
            meta_object.table_name,
            " ".join(parts)
        )
        
        return sql
    
    def _generate_column_definition(self, field: MetaField) -> str:
        """生成列定义"""
        parts = [field.db_column]
        
        col_type = self.TYPE_MAPPING.get(field.field_type, "TEXT")
        parts.append(col_type)
        
        if field.unique and field.id == "id":
            if field.field_type == FieldType.INTEGER:
                parts.append("PRIMARY KEY AUTOINCREMENT" if self.dialect == "sqlite" else "PRIMARY KEY AUTO_INCREMENT")
            else:
                parts.append("PRIMARY KEY")
        elif field.unique:
            parts.append("UNIQUE")
        
        if field.required and field.id != "id":
            parts.append("NOT NULL")
        
        if field.default is not None:
            if isinstance(field.default, bool):
                parts.append("DEFAULT {0}".format(1 if field.default else 0))
            elif isinstance(field.default, str):
                parts.append("DEFAULT '{0}'".format(field.default))
            else:
                parts.append("DEFAULT {0}".format(field.default))
        
        return " ".join(parts)
    
    def _generate_foreign_key(self, relation: MetaRelation) -> Optional[str]:
        """生成外键约束"""
        if relation.cardinality not in ["N:1", "1:1"]:
            return None
        
        fk_column = "{0}_id".format(relation.target_object)
        from meta.core.models import registry
        target_obj = registry.get(relation.target_object)
        ref_table = target_obj.table_name if target_obj and target_obj.table_name else relation.target_object
        ref_column = "id"
        
        return "FOREIGN KEY ({0}) REFERENCES {1}({2})".format(
            fk_column, ref_table, ref_column
        )
    
    def generate_create_index(self, meta_object: MetaObject) -> List[str]:
        """生成 CREATE INDEX 语句（增强版：元数据驱动 + 规则引擎推导）
        
        索引来源优先级（借鉴 SAP CDS @AbapCatalog.index 体系）：
        1. YAML 显式定义（source=SCHEMA）
        2. 规则引擎从语义标注推导（source=RULE_ENGINE）
        3. 查询分析推荐（source=QUERY_ANALYSIS）
        """
        if meta_object.object_type in [ObjectType.VIEW, ObjectType.VIRTUAL]:
            return []
        
        from meta.core.index_rule_engine import IndexRuleEngine
        rule_engine = IndexRuleEngine()
        all_indexes = rule_engine.derive_indexes(meta_object)
        
        indexes = []
        for index in all_indexes:
            if not index.auto_create:
                continue
            
            if index.index_type == IndexType.FTS:
                fts_sqls = self._generate_fts_index(meta_object, index)
                indexes.extend(fts_sqls)
                continue
            
            idx_name = index.name if index.name else "idx_{0}_{1}".format(
                meta_object.table_name, "_".join(index.fields)
            )
            
            columns = index.db_columns or []
            if not columns:
                for field_name in index.fields:
                    field = next((f for f in meta_object.fields if f.id == field_name), None)
                    if field:
                        columns.append(field.db_column)
            
            if not columns:
                continue
            
            columns_str = ", ".join(columns)
            
            if index.index_type == IndexType.PARTIAL and index.condition:
                unique_clause = "UNIQUE " if index.unique else ""
                indexes.append(
                    "CREATE {0}INDEX IF NOT EXISTS {1} ON {2}({3}) WHERE {4}".format(
                        unique_clause, idx_name, meta_object.table_name, columns_str, index.condition
                    )
                )
            elif index.unique:
                indexes.append(
                    "CREATE UNIQUE INDEX IF NOT EXISTS {0} ON {1}({2})".format(
                        idx_name, meta_object.table_name, columns_str
                    )
                )
            else:
                indexes.append(
                    "CREATE INDEX IF NOT EXISTS {0} ON {1}({2})".format(
                        idx_name, meta_object.table_name, columns_str
                    )
                )
        
        return indexes
    
    def _generate_fts_index(self, meta_object: MetaObject, index: MetaIndex) -> List[str]:
        """生成 FTS5 全文索引 SQL"""
        columns = index.db_columns or []
        if not columns:
            for field_name in index.fields:
                field = next((f for f in meta_object.fields if f.id == field_name), None)
                if field:
                    columns.append(field.db_column)
        
        if not columns:
            return []
        
        fts_table = "{0}_fts".format(meta_object.table_name)
        columns_str = ", ".join(columns)
        
        return [
            "CREATE VIRTUAL TABLE IF NOT EXISTS {0} USING fts5({1}, content='{2}')".format(
                fts_table, columns_str, meta_object.table_name
            )
        ]
    
    def generate_full_schema(self, meta_objects: List[MetaObject]) -> str:
        """生成完整的 Schema 定义"""
        statements = []
        
        persistent_objects = [obj for obj in meta_objects 
                            if obj.object_type in [ObjectType.ENTITY, ObjectType.VIEW]]
        
        sorted_objects = sorted(
            persistent_objects,
            key=lambda x: x.semantics.hierarchy_level
        )
        
        for obj in sorted_objects:
            sql = self.generate_create_table(obj)
            if sql:
                statements.append("-- {0}: {1}".format(obj.name, obj.description))
                statements.append(sql)
                statements.append("")
        
        for obj in sorted_objects:
            indexes = self.generate_create_index(obj)
            if indexes:
                statements.append("-- Indexes for {0}".format(obj.name))
                statements.extend(indexes)
                statements.append("")
        
        return "\n".join(statements)
    
    def generate_column_dict(self, field: MetaField) -> Dict:
        """将 MetaField 转换为 DataSource 使用的列定义字典"""
        return {
            "type": self.TYPE_MAPPING.get(field.field_type, "TEXT"),
            "required": field.required,
            "unique": field.unique,
            "default": field.default,
        }


class SchemaComparator:
    """Schema 比较器 - 比较元数据定义和实际数据库结构"""
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
    
    def compare(self, meta_object: MetaObject) -> Dict:
        """比较元数据定义和实际数据库结构"""
        report = {
            "object_id": meta_object.id,
            "table_name": meta_object.table_name,
            "exists": False,
            "missing_columns": [],
            "extra_columns": [],
            "type_mismatches": [],
        }
        
        if meta_object.object_type == ObjectType.VIRTUAL:
            return report
        
        if not meta_object.table_name:
            return report
        
        if not self.ds.table_exists(meta_object.table_name):
            report["exists"] = False
            report["missing_columns"] = [f.db_column for f in meta_object.get_persistent_fields()]
            return report
        
        report["exists"] = True
        existing_columns = self.ds.get_table_columns(meta_object.table_name)
        meta_columns = {f.db_column: f for f in meta_object.get_persistent_fields()}
        
        for col_name, field in meta_columns.items():
            if col_name not in existing_columns:
                report["missing_columns"].append(col_name)
        
        for col_name in existing_columns:
            if col_name not in meta_columns:
                report["extra_columns"].append(col_name)
        
        return report


class SchemaMigrator:
    """Schema 迁移器 - 执行 Schema 变更"""
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
        self.generator = SchemaGenerator(dialect=getattr(data_source, 'dialect', 'sqlite'))
        self.comparator = SchemaComparator(data_source)
    
    def migrate(self, meta_objects: List[MetaObject], dry_run: bool = False) -> List[str]:
        """执行 Schema 迁移"""
        executed_sql = []
        
        persistent_objects = [obj for obj in meta_objects 
                            if obj.object_type in [ObjectType.ENTITY, ObjectType.VIEW]]
        
        sorted_objects = sorted(
            persistent_objects,
            key=lambda x: x.semantics.hierarchy_level
        )
        
        for obj in sorted_objects:
            report = self.comparator.compare(obj)
            
            if not report["exists"]:
                sql = self.generator.generate_create_table(obj)
                if sql:
                    executed_sql.append(sql)
                    if not dry_run:
                        self.ds.execute(sql)
                        self.ds.commit()
                    print("[CREATE] {0}: {1}".format(obj.table_name, obj.name))
            else:
                if report["missing_columns"]:
                    for col_name in report["missing_columns"]:
                        field = next((f for f in obj.get_persistent_fields() if f.db_column == col_name), None)
                        if field:
                            col_def = self.generator._generate_column_definition(field)
                            sql = "ALTER TABLE {0} ADD COLUMN {1}".format(obj.table_name, col_def)
                            executed_sql.append(sql)
                            if not dry_run:
                                try:
                                    self.ds.execute(sql)
                                    self.ds.commit()
                                except Exception as e:
                                    logger.warning("[SchemaMigrator] ALTER TABLE ADD COLUMN failed: %s | SQL: %s", e, sql)
                            print("[ALTER] {0}: ADD COLUMN {1}".format(obj.table_name, col_name))
        
        for obj in sorted_objects:
            indexes = self.generator.generate_create_index(obj)
            for sql in indexes:
                executed_sql.append(sql)
                if not dry_run:
                    try:
                        self.ds.execute(sql)
                        self.ds.commit()
                    except Exception as e:
                        pass
        
        # 清理不再需要的过时索引（基于当前 YAML 定义，删除多余的 UNIQUE 索引）
        self._cleanup_stale_indexes(sorted_objects, dry_run)
        
        return executed_sql
    
    def _cleanup_stale_indexes(self, sorted_objects, dry_run=False):
        """删除基于过时 metadata 创建的 UNIQUE 索引"""
        import re
        for obj in sorted_objects:
            expected_indexes = self.generator.generate_create_index(obj)
            expected_names = set()
            for sql in expected_indexes:
                m = re.search(r'INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', sql, re.IGNORECASE)
                if m:
                    expected_names.add(m.group(1))
            
            try:
                cursor = self.ds.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
                    (obj.table_name,)
                )
                actual_rows = cursor.fetchall() if cursor else []
                for row in actual_rows:
                    idx_name = row[0] if isinstance(row, tuple) else row['name']
                    if idx_name.startswith('uidx_') and idx_name not in expected_names:
                        drop_sql = f"DROP INDEX IF EXISTS {idx_name}"
                        print(f"[CLEANUP] Dropping stale UNIQUE index: {idx_name} on {obj.table_name}")
                        if not dry_run:
                            try:
                                self.ds.execute(drop_sql)
                                self.ds.commit()
                            except Exception as e:
                                print(f"[CLEANUP] Failed to drop {idx_name}: {e}")
            except Exception as e:
                print(f"[CLEANUP] Error processing {obj.table_name}: {e}")


def sync_schema_from_meta(data_source: DataSource, meta_objects: List[MetaObject], dry_run: bool = False):
    """从元数据同步数据库 Schema"""
    migrator = SchemaMigrator(data_source)
    return migrator.migrate(meta_objects, dry_run)
