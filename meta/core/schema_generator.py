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
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

from typing import Any, List, Dict, Tuple, Optional
from meta.core.models import (
    MetaObject, MetaField, MetaRelation, FieldType, RelationType,
    ObjectType, FieldStorage, ViewConfig, IndexType, IndexSource, MetaIndex
)
from meta.core.datasource import DataSource, DataSourceType, get_data_source
from meta.core.sql_adapters import SQLDataSource


# [E2 2026-11-11] STRING 缺省长度；CHECK 只渲染小枚举（大枚举走值帮助）
DEFAULT_STRING_LENGTH = 200
MAX_ENUM_CHECK_VALUES = 50


def _field_max_length(field: MetaField) -> int:
    """字段长度：semantics.max_length 优先，其次顶层 max_length，缺省 200。"""
    return (getattr(field.semantics, 'max_length', None)
            or getattr(field, 'max_length', None)
            or DEFAULT_STRING_LENGTH)


_BOOL_TRUE_LITERALS = {"true", "1", "yes", "on", "y", "t"}
_BOOL_FALSE_LITERALS = {"false", "0", "no", "off", "n", "f"}


def _boolean_check_literal(value) -> str:
    """BOOLEAN 枚举值 → '1'/'0'。

    SQLite 中布尔列实际写入的是 0/1；若把 YAML 里的 true/false 直接渲染成
    'True'/'False'，CHECK 会拦住所有正常写入（enum_values.is_active 存量 336 行
    就是 0/1）。
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    text = str(value).strip().lower()
    if text in _BOOL_TRUE_LITERALS:
        return "1"
    if text in _BOOL_FALSE_LITERALS:
        return "0"
    return str(value)


def enum_check_values(field: MetaField) -> List[str]:
    """枚举列的候选值（按声明顺序去重；BOOLEAN 归一为 1/0）。"""
    enum_values = getattr(field, "enum_values", None) or []
    values = []
    for item in enum_values:
        value = item.get("value") if isinstance(item, dict) else item
        if value is None:
            continue
        text = (_boolean_check_literal(value)
                if field.field_type == FieldType.BOOLEAN else str(value))
        if text not in values:
            values.append(text)
    return values


# 运行时内部状态（审计成败 / 账号冻结）由业务代码写入，不受 YAML 枚举约束；
# 若自动生成 CHECK，会拦截 success/failure/denied 等合法写入，故豁免。
CHECK_EXEMPT_COLUMNS = {
    ("users", "status"),
    ("audit_logs", "status"),
    # 审计日志的分类字段由调用方自由写入：object_type 覆盖 54 张表名，
    # log_level 含 WARN 等内部级别，action / log_category 同理无法穷举。
    ("audit_logs", "action"),
    ("audit_logs", "log_category"),
    ("audit_logs", "log_level"),
    ("audit_logs", "object_type"),
}


def allowed_check_values(table_name: Optional[str], field: MetaField) -> List[str]:
    """该列允许生成的 CHECK 候选值（豁免列返回空 → 不生成 CHECK）。"""
    if table_name and (table_name, field.db_column) in CHECK_EXEMPT_COLUMNS:
        return []
    return enum_check_values(field)


# ==================== DDL 比对 / CHECK 补齐 ====================

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+[\"'`\[]?([A-Za-z_][\w]*)[\"'`\]]?",
    re.IGNORECASE)
_COLUMN_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*\"?([A-Za-z_]\w*)\"?\s+IN\s*\(([^)]*)\)\s*\)", re.IGNORECASE)
_NON_COLUMN_PREFIXES = ("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CONSTRAINT", "CHECK")


def normalize_sql_type(raw: Optional[str]) -> str:
    """类型归一化：去空白 + 大写，便于跨 DDL 风格比较。"""
    if not raw:
        return ""
    return re.sub(r"\s+", "", str(raw).upper())


def sqlite_type_affinity(raw: Optional[str]) -> str:
    """SQLite 类型亲和性（忽略声明长度 / 精度）。

    SQLite 的 `VARCHAR(n)` 不强制长度，存储与比较只取决于亲和性；
    因此 DDL 漂移按亲和性判定「真实类型变化」，纯长度/精度差异不算漂移。
    规则顺序与 SQLite 官方文档一致：INT → CHAR/CLOB/TEXT → BLOB →
    REAL/FLOA/DOUB → NUMERIC。
    """
    text = normalize_sql_type(raw)
    if not text:
        return "BLOB"
    if "INT" in text:
        return "INTEGER"
    if "CHAR" in text or "CLOB" in text or "TEXT" in text:
        return "TEXT"
    if "BLOB" in text:
        return "BLOB"
    if "REAL" in text or "FLOA" in text or "DOUB" in text:
        return "REAL"
    return "NUMERIC"


def iter_create_table_blocks(text: str):
    """依次产出 (表名, 括号内 body)，支持嵌套括号（CHECK IN (...)）。"""
    position = 0
    while True:
        match = _CREATE_TABLE_RE.search(text, position)
        if not match:
            return
        start = text.find("(", match.end())
        if start < 0:
            return
        depth, index = 0, start
        while index < len(text):
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        yield match.group(1), text[start + 1:index]
        position = index + 1


def split_top_level(text: str) -> List[str]:
    """按顶层逗号切分（括号内的逗号不切）。"""
    parts, depth, current = [], 0, []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def parse_column_definition(definition: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """解析单条列定义 → (列名, {type, check})；表级约束返回 (None, None)。"""
    line = definition.strip()
    if not line:
        return None, None
    upper = line.upper()
    for prefix in _NON_COLUMN_PREFIXES:
        if upper.startswith(prefix):
            return None, None
    tokens = line.split()
    if len(tokens) < 2:
        return None, None
    name = tokens[0].strip('"`[]')
    col_type = tokens[1]
    if len(tokens) > 2 and tokens[2].startswith("("):
        col_type = col_type + tokens[2]
    checks = {}
    for match in _COLUMN_CHECK_RE.finditer(line):
        column = match.group(1).strip('"`[]')
        checks[column] = [item.strip().strip("'\"") for item in match.group(2).split(",")]
    return name, {"type": normalize_sql_type(col_type), "check": checks.get(name)}


def parse_schema_text(text: str) -> Dict[str, Dict[str, Any]]:
    """解析 DDL 文本 → {表名: {columns: {列名: {type, check}}}}。"""
    schema = {}
    for table, body in iter_create_table_blocks(text):
        columns = {}
        for definition in split_top_level(body):
            name, info = parse_column_definition(definition)
            if name:
                columns[name] = info
        schema[table] = {"columns": columns}
    return schema


_TRAILING_KEYWORDS = {
    "NOT", "NULL", "PRIMARY", "KEY", "UNIQUE", "DEFAULT", "CHECK",
    "REFERENCES", "COLLATE", "GENERATED", "CONSTRAINT", "AUTOINCREMENT",
}


def _replace_column_type(definition: str, column: str, target_type: str) -> str:
    """替换单条列定义的类型片段，保留其后所有约束。

    列名支持裸名 / 双引号 / 反引号 / 方括号；类型片段取「列名之后、
    第一个约束关键字之前」的部分（可含 `(n,m)`）。
    """
    match = re.match(
        r'^\s*("[^"]+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_]\w*)(\s+)(.*)$',
        definition, re.DOTALL)
    if not match:
        return definition
    if match.group(1).strip('"`[]') != column:
        return definition
    tokens = match.group(3).split()
    cut = len(tokens)
    for index, token in enumerate(tokens):
        if token.upper().strip(",") in _TRAILING_KEYWORDS:
            cut = index
            break
    if cut == 0:
        return definition
    return "{0}\t{1}".format(
        match.group(1), " ".join([target_type] + tokens[cut:]))


def rebuild_table_with_checks(db_path: str, table: str, checks: Dict[str, List[str]],
                              types: Optional[Dict[str, str]] = None,
                              conn: Optional[sqlite3.Connection] = None) -> bool:
    """SQLite：重建表，同时对齐列类型并补齐列级 CHECK。

    类型/CHECK 在同一次 CREATE ... __new 中完成，避免同一张表重建两遍。

    Args:
        db_path: SQLite 数据库路径
        table: 目标表
        checks: {列名: 允许值列表}；已带 CHECK 的列跳过
        types: {列名: 目标类型}；归一化后与现类型相同则不替换
        conn: 可选复用连接（须为 autocommit：isolation_level=None）

    Returns:
        是否发生重建
    """
    owns_conn = conn is None
    if owns_conn:
        conn = sqlite3.connect(str(Path(db_path)), timeout=30)
        conn.isolation_level = None
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not row or not row[0]:
            return False
        create_sql = row[0]
        start = create_sql.find("(")
        if start < 0:
            return False
        depth, index = 0, start
        while index < len(create_sql):
            char = create_sql[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        definitions = split_top_level(create_sql[start + 1:index])

        changed = False
        updated = []
        types = types or {}
        for definition in definitions:
            name, info = parse_column_definition(definition)
            if not name:
                updated.append(definition)
                continue
            target_type = types.get(name)
            if target_type and (info or {}).get("type") != normalize_sql_type(target_type):
                replaced = _replace_column_type(definition, name, target_type)
                if replaced != definition:
                    definition = replaced
                    changed = True
            if name in checks and not (info and info.get("check")):
                quoted = ", ".join("'{0}'".format(v.replace("'", "''")) for v in checks[name])
                definition = definition.rstrip() + " CHECK ({0} IN ({1}))".format(name, quoted)
                changed = True
            updated.append(definition)
        if not changed:
            return False

        index_sqls = [item[0] for item in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type IN ('index','trigger') "
            "AND tbl_name=? AND sql IS NOT NULL", (table,))]
        # 引用本表的视图：DROP TABLE 后视图失效（SQLite 会报
        # "error in view ...: no such table"），必须先降后升。
        view_sqls = [
            (item[0], item[1]) for item in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='view' AND sql IS NOT NULL")
            if re.search(r"\b{0}\b".format(re.escape(table)), item[1], re.IGNORECASE)
        ]
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            for name, _sql in view_sqls:
                conn.execute("DROP VIEW IF EXISTS {0}".format(name))
            conn.execute("CREATE TABLE {0}__new ({1})".format(table, ",".join(updated)))
            conn.execute("INSERT INTO {0}__new SELECT * FROM {0}".format(table))
            conn.execute("DROP TABLE {0}".format(table))
            conn.execute("ALTER TABLE {0}__new RENAME TO {0}".format(table))
            for sql in index_sqls:
                conn.execute(sql)
            for _name, sql in view_sqls:
                conn.execute(sql)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        return True
    finally:
        if owns_conn:
            conn.close()


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

    def _sql_type(self, field: MetaField) -> str:
        """列类型：STRING 按声明长度渲染（其余沿用静态映射）。"""
        if field.field_type == FieldType.STRING:
            return "VARCHAR({0})".format(_field_max_length(field))
        return self.TYPE_MAPPING.get(field.field_type, "TEXT")

    def _sql_check(self, field: MetaField,
                   table_name: Optional[str] = None) -> Optional[str]:
        """列级 CHECK：enum_values 非空且 <=50 时渲染 `CHECK (col IN (...))`。

        本轮只对 SQLite 生效（MySQL/PG 的 CHECK 语法差异留待后续）。
        """
        if self.dialect != "sqlite":
            return None
        values = allowed_check_values(table_name, field)
        if not values or len(values) > MAX_ENUM_CHECK_VALUES:
            return None
        quoted = ", ".join("'{0}'".format(v.replace("'", "''")) for v in values)
        return "CHECK ({0} IN ({1}))".format(field.db_column, quoted)
    
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
            col_def = self._generate_column_definition(field, meta_object.table_name)
            columns.append(col_def)
        
        for relation in meta_object.relations:
            # 【2026-10-06】原仅 PARENT_CHILD 生成 FK。但 yaml 中以 `type: reference`
            # 声明的"逻辑引用"（真 FK 语义）此前被静默丢弃 —— 现把 REFERENCE 一并纳入。
            # 为避免误伤：REFERENCE 必须显式声明 source_field（无 source_field 的旧式
            # `target_entity/source_key` 关系不生成 FK）。
            if relation.relation_type in (RelationType.PARENT_CHILD, RelationType.REFERENCE):
                if relation.relation_type == RelationType.REFERENCE and not relation.source_field:
                    continue
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
    
    def _generate_column_definition(self, field: MetaField,
                                    table_name: Optional[str] = None) -> str:
        """生成列定义"""
        parts = [field.db_column]
        
        col_type = self._sql_type(field)
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

        check = self._sql_check(field, table_name)
        if check:
            parts.append(check)

        return " ".join(parts)
    
    def _generate_foreign_key(self, relation: MetaRelation) -> Optional[str]:
        """生成外键约束"""
        if relation.cardinality not in ["N:1", "1:1"]:
            return None
        
        # 【2026-10-06】优先用显式 source_field 作 FK 列名；未声明时回退
        #   {target_object}_id（保持既有 PARENT_CHILD 关系行为不变 —— 它们均未声明
        #   source_field）。此前 source_field 被完全忽略，导致
        #   "adjustments.original_result_id → calc_result" 只能推出 calc_result_id 的错误列。
        fk_column = relation.source_field or "{0}_id".format(relation.target_object)
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
            "type": self._sql_type(field),
            "required": field.required,
            "unique": field.unique,
            "default": field.default,
        }


def _sqlite_affinity(type_name: str) -> str:
    """把列类型名归一到 SQLite 亲和类型（用于判定真实 drift）。

    YAML 声明 `VARCHAR(200)`、DB 实际 `TEXT` 在语义上是同一种存储，不应报 drift；
    而 `INTEGER` vs `TEXT` 才是真正的类型漂移（历史上 `number`/`timestamp`
    漏登记曾把金额、日期列建成了 VARCHAR）。
    """
    name = (type_name or "").upper()
    if "INT" in name:
        return "INTEGER"
    if "CHAR" in name or "CLOB" in name or "TEXT" in name:
        return "TEXT"
    if not name or "BLOB" in name:
        return "BLOB"
    if "REAL" in name or "FLOA" in name or "DOUB" in name:
        return "REAL"
    return "NUMERIC"


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
                continue
            # [P1-3 2026-11-06] 类型漂移：按 SQLite 亲和类型比较，避免 VARCHAR/TEXT 误报
            declared = SchemaGenerator.TYPE_MAPPING.get(field.field_type, "TEXT")
            actual = (existing_columns.get(col_name) or {}).get("type") or ""
            if _sqlite_affinity(declared) != _sqlite_affinity(actual):
                report["type_mismatches"].append({
                    "column": col_name,
                    "declared": declared,
                    "actual": actual,
                })
        
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
        table_map = {o.id: o.table_name for o in sorted_objects if o.table_name}
        
        for obj in sorted_objects:
            report = self.comparator.compare(obj)
            
            if not report["exists"]:
                sql = self.generator.generate_create_table(obj)
                if sql:
                    executed_sql.append(sql)
                    if not dry_run:
                        try:
                            self.ds.execute(sql)
                            self.ds.commit()
                        except Exception as e:
                            # [2026-11-05] 视图基表可能尚未建（如 doc_flow 未启用）；
                            # 单个 VIEW 失败不应中断整轮 schema sync（与索引同款降级）。
                            if obj.object_type == ObjectType.VIEW:
                                logger.warning(
                                    "[SchemaMigrator] CREATE VIEW skipped: %s | SQL: %s",
                                    e, sql)
                                continue
                            raise
                    print("[CREATE] {0}: {1}".format(obj.table_name, obj.name))
            else:
                if report["missing_columns"]:
                    for col_name in report["missing_columns"]:
                        field = next((f for f in obj.get_persistent_fields() if f.db_column == col_name), None)
                        if field:
                            col_def = self.generator._generate_column_definition(field, obj.table_name)
                            sql = "ALTER TABLE {0} ADD COLUMN {1}".format(obj.table_name, col_def)
                            executed_sql.append(sql)
                            if not dry_run:
                                try:
                                    self.ds.execute(sql)
                                    self.ds.commit()
                                except Exception as e:
                                    logger.warning("[SchemaMigrator] ALTER TABLE ADD COLUMN failed: %s | SQL: %s", e, sql)
                            print("[ALTER] {0}: ADD COLUMN {1}".format(obj.table_name, col_name))

                # [2026-11-08] 补落新增 FK：SQLite 无 ADD CONSTRAINT，只能重建表。
                # 此前表已存在时只走 ADD COLUMN 分支，新增的 relations 永远不会落成真 FK。
                executed_sql.extend(self._sync_missing_fks(obj, table_map, dry_run))
        
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

    def _sync_missing_fks(self, obj, table_map, dry_run=False):
        """表已存在时补落新增 FK。

        SQLite 不支持 ADD CONSTRAINT，唯一合法路径是「建新表 → 拷数据 → 换名」。
        修复前 Migrator 对已存在表只走 ADD COLUMN，新增 relations 永远落不成真 FK。
        """
        if obj.object_type != ObjectType.ENTITY or not obj.table_name:
            return []

        try:
            cursor = self.ds.execute(
                'PRAGMA foreign_key_list("{0}")'.format(obj.table_name))
            actual = set()
            for row in (cursor.fetchall() if cursor else []):
                actual.add(row[3] if isinstance(row, tuple) else row['from'])
        except Exception:
            return []

        clauses, missing = [], []
        for relation in obj.relations:
            if relation.relation_type not in (RelationType.PARENT_CHILD,
                                              RelationType.REFERENCE):
                continue
            if (relation.relation_type == RelationType.REFERENCE
                    and not relation.source_field):
                continue
            if relation.cardinality not in ('N:1', '1:1'):
                continue
            fk_column = relation.source_field or '{0}_id'.format(
                relation.target_object)
            if fk_column in actual:
                continue
            ref_table = table_map.get(relation.target_object,
                                      relation.target_object)
            clauses.append('FOREIGN KEY ({0}) REFERENCES {1}(id)'.format(
                fk_column, ref_table))
            missing.append(fk_column)

        if not clauses:
            return []

        violations = self.ds.execute(
            'PRAGMA foreign_key_check("{0}")'.format(obj.table_name)).fetchall()
        if violations:
            print("[SKIP-FK] {0}: 存在 {1} 条外键违规，跳过重建以免丢数据".format(
                obj.table_name, len(violations)))
            return []

        views = self._dependent_views(obj.table_name)
        sqls = self._rebuild_table_with_fks(obj.table_name, clauses)
        if dry_run:
            return sqls

        # 重建期间必须关闭 FK：新声明的 FK 会校验既有数据，DROP TABLE 也会触发
        # 引用校验。注意 SQLite 的 PRAGMA foreign_keys 在事务内是 no-op，故必须在
        # 无事务状态下设置（写队列连接为 autocommit）。
        self.ds.execute('PRAGMA foreign_keys=OFF')
        # 视图会阻止 DROP/RENAME（schema 重解析报 no such table），重建前后摘挂
        for name, _ in views:
            self.ds.execute('DROP VIEW IF EXISTS "{0}"'.format(name))
        try:
            for sql in sqls:
                self.ds.execute(sql)
            self.ds.commit()
        finally:
            for _, view_sql in views:
                if view_sql:
                    self.ds.execute(view_sql)
            self.ds.execute('PRAGMA foreign_keys=ON')
            self.ds.commit()
        print("[REBUILD] {0}: ADD FK {1}".format(obj.table_name, missing))
        orphans = self.ds.execute(
            'PRAGMA foreign_key_check("{0}")'.format(obj.table_name)).fetchall()
        if orphans:
            print("[FK-ORPHAN] {0}: 历史数据有 {1} 行悬空引用，建议清理".format(
                obj.table_name, len(orphans)))
        return sqls

    def _dependent_views(self, table):
        """返回 SQL 中引用了该表的视图 [(name, sql)]（按创建顺序）。"""
        import re
        pattern = re.compile(
            r'(?<![\w])"?{0}"?(?![\w])'.format(re.escape(table)), re.I)
        views = []
        cursor = self.ds.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='view' ORDER BY rowid")
        for row in (cursor.fetchall() if cursor else []):
            name = row[0] if isinstance(row, tuple) else row['name']
            sql = row[1] if isinstance(row, tuple) else row['sql']
            if sql and pattern.search(sql):
                views.append((name, sql))
        return views

    def _rebuild_table_with_fks(self, table, fk_clauses):
        """把缺失的 FOREIGN KEY 子句补进现有 DDL 并重建表（保留列/数据/触发器）。"""
        import re
        row = self.ds.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()
        ddl = row[0] if isinstance(row, tuple) else row['sql']
        if not ddl or 'CREATE TABLE' not in ddl.upper():
            return []

        triggers = []
        cursor = self.ds.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
            (table,))
        for r in (cursor.fetchall() if cursor else []):
            sql = r[0] if isinstance(r, tuple) else r['sql']
            if sql:
                triggers.append(sql)

        # DROP TABLE 会连带删除该表所有显式索引（sqlite_autoindex_* 随 DDL 重建），
        # 故重建后按原 SQL 补回，避免索引丢失。
        indexes = []
        cursor = self.ds.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=?"
            " AND sql IS NOT NULL", (table,))
        for r in (cursor.fetchall() if cursor else []):
            sql = r[0] if isinstance(r, tuple) else r['sql']
            if sql:
                indexes.append(sql)

        body = ddl.rstrip()
        if not body.endswith(')'):
            return []
        body = body[:-1].rstrip()
        new_ddl = body + ',\n    ' + ',\n    '.join(fk_clauses) + '\n)'

        tmp = '_rebuild_{0}'.format(table)
        new_ddl = re.sub(
            r'(?is)^(\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?:["\[]?\w+["\]]?)',
            lambda m: '{0}"{1}"'.format(m.group(1), tmp),
            new_ddl, count=1)

        columns = []
        cursor = self.ds.execute(
            'PRAGMA table_info("{0}")'.format(table))
        for r in (cursor.fetchall() if cursor else []):
            columns.append(r[1] if isinstance(r, tuple) else r['name'])
        col_list = ', '.join('"{0}"'.format(c) for c in columns)

        sqls = [
            'DROP TABLE IF EXISTS "{0}"'.format(tmp),
            new_ddl,
            'INSERT INTO "{0}" ({1}) SELECT {1} FROM "{2}"'.format(
                tmp, col_list, table),
            'DROP TABLE "{0}"'.format(table),
            'ALTER TABLE "{0}" RENAME TO "{1}"'.format(tmp, table),
        ]
        sqls.extend(indexes)
        sqls.extend(triggers)
        return sqls

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
