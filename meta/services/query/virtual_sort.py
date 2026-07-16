import logging
import re
from typing import Optional, Tuple, List, Any

from meta.core.enrichment_engine import enrich_records, get_enrichment_engine
from meta.core.redundancy_registry import redundancy_registry
from meta.core.table_name_validator import validate_table_name
from meta.core.models import MetaObject, FieldStorage
from meta.core.query_builder import QueryBuilder

logger = logging.getLogger(__name__)


def build_virtual_field_order_join(
    meta_obj: MetaObject,
    sort_field: str,
    sort_direction: str
) -> Optional[Tuple[str, str, str]]:
    logger.debug(f"[VirtualSort] build_virtual_field_order_join: meta_obj={meta_obj.id}, sort_field={sort_field}, direction={sort_direction}")

    field = meta_obj.get_field(sort_field)
    if not field:
        logger.debug(f"[VirtualSort] Field '{sort_field}' not found in {meta_obj.id}")
        return None

    storage = getattr(field, 'storage', None)
    logger.debug(f"[VirtualSort] Field '{sort_field}' storage={storage}, FieldStorage.VIRTUAL={FieldStorage.VIRTUAL}")

    if storage != FieldStorage.VIRTUAL:
        logger.debug(f"[VirtualSort] Field '{sort_field}' is not virtual, using standard sort")
        return None

    red_def = redundancy_registry.get_redundancy(meta_obj.id, sort_field)
    logger.debug(f"[VirtualSort] RedundancyDef for {meta_obj.id}.{sort_field}: {red_def}")

    if not red_def:
        # [FIX 2026-06-08] 路径 2: audit_logs 派生字段（如 updated_at）。
        # 这些字段用 derive_from_object 机制而非 redundancy 注册，
        # 走 audit_logs 子查询聚合 MAX(updated_at)。
        derive_obj = getattr(field, 'derive_from_object', '')
        if derive_obj == 'audit_logs':
            return _build_audit_derived_order_join(
                meta_obj.table_name, meta_obj.id, sort_field, sort_direction
            )

        logger.warning(f"[VirtualSort] No redundancy definition for {meta_obj.id}.{sort_field}")
        return None

    if not red_def.join_path:
        logger.warning(f"[VirtualSort] No join_path for {meta_obj.id}.{sort_field}")
        return None

    logger.debug(f"[VirtualSort] join_path: {red_def.join_path}")

    table_name = validate_table_name(meta_obj.table_name)
    alias_counter = 0
    join_parts = []
    last_alias = table_name
    target_field = None

    for step in red_def.join_path:
        alias_counter += 1
        join_alias = f"_j{alias_counter}"

        to_field = step.to_field if step.to_field else 'id'
        join_sql = (
            f"LEFT JOIN {step.table} AS {join_alias} "
            f"ON {last_alias}.{step.from_field} = {join_alias}.{to_field}"
        )
        join_parts.append(join_sql)
        logger.debug(f"[VirtualSort] JOIN step: {join_sql}")

        last_alias = join_alias
        target_field = step.select

    if not target_field:
        logger.warning(f"[VirtualSort] No target_field from join_path")
        return None

    join_clause = " ".join(join_parts)
    order_field_alias = f"{last_alias}.{target_field}"

    logger.info(f"[VirtualSort] Built JOIN: {join_clause}, order_by: {order_field_alias} {sort_direction}")

    return join_clause, order_field_alias, sort_direction


def _build_audit_derived_order_join(
    table_name: str,
    obj_type: str,
    sort_field: str,
    sort_direction: str,
) -> Optional[Tuple[str, str, str]]:
    """构造 audit_logs 派生虚拟字段（如 updated_at）的排序 JOIN。

    [V007.51 Phase 2] 物化列优先策略：
      如果业务表已有物化 updated_at 列，直接用物化列排序（零 JOIN 开销）。
      否则走 v_audit_all LEFT JOIN 子查询。

    适用场景：field.storage=VIRTUAL 且 field.derive_from_object='audit_logs'。
    这类字段（如 aspects.yaml 中的 updated_at）不存于业务表，而是从
    audit_logs 实时聚合（MAX(created_at) WHERE action='UPDATE'）。

    安全说明：
        - table_name 必须经过 validate_table_name() 校验（白名单）
        - obj_type 来自 YAML 注册表 或 user_api.py 中硬编码的信任值，
          严禁直接拼接用户输入
        - audit_logs 在 meta.core.table_name_validator._SYSTEM_TABLES 白名单中

    Args:
        table_name: 主表名（已通过 validate_table_name 校验）
        obj_type: object_type 标识（来自 YAML 或硬编码信任值）
        sort_field: 排序字段名（仅用于日志）
        sort_direction: 排序方向 ('asc' / 'desc')

    Returns:
        (join_clause, order_alias, sort_direction) 三元组；
        物化列路径时 join_clause 为空字符串
    """
    table_name = validate_table_name(table_name)
    # obj_type 必须是安全标识符（字母数字下划线），非用户输入
    if not obj_type or not obj_type.replace('_', '').isalnum():
        logger.warning(f"[VirtualSort] Invalid obj_type: {obj_type!r}")
        return None

    # [V007.51 Phase 2] 物化列优先：有 updated_at 列的表直接排序
    if _table_has_materialized_updated_at(table_name, obj_type):
        order_alias = f"COALESCE({table_name}.updated_at, {table_name}.created_at)"
        logger.info(
            f"[VirtualSort] Using materialized updated_at for {obj_type}.{sort_field}: "
            f"order_by={order_alias} {sort_direction}"
        )
        # join_clause 为空字符串：execute_virtual_field_query 不需要额外 JOIN
        return "", order_alias, sort_direction

    # 回退：走 v_audit_all LEFT JOIN 子查询
    sub_alias = "_audit_sort"
    join_clause = (
        f"LEFT JOIN ("
        f"SELECT object_id, MAX(created_at) AS _audit_value "
        f"FROM v_audit_all "
        f"WHERE object_type = '{obj_type}' AND action = 'UPDATE' "
        f"GROUP BY object_id"
        f") {sub_alias} ON {sub_alias}.object_id = {table_name}.id"
    )
    order_alias = f"COALESCE({sub_alias}._audit_value, {table_name}.created_at)"

    logger.info(
        f"[VirtualSort] Built audit-derived JOIN for {obj_type}.{sort_field}: "
        f"order_by={order_alias} {sort_direction}"
    )
    return join_clause, order_alias, sort_direction


# [V007.51 V007.52 SSOT] 检查表是否有物化 updated_at 列
# 从 MaterializationRegistry SSOT 读取（_audit_materialization.yaml）
def _table_has_materialized_updated_at(table_name: str, obj_type: str) -> bool:
    """检查表是否有物化 updated_at 列（V007.51 Phase 2）

    [V007.52] SSOT 化：从 MaterializationRegistry 读取，
    支持所有 materialization 策略（business_trigger / audit_callback /
    application_explicit）的表都走物化列路径。

    Args:
        table_name: 业务表名
        obj_type: 审计对象类型（暂未使用，保留接口兼容）

    Returns:
        True 如果该表有物化 updated_at 列
    """
    try:
        from meta.core.materialization_registry import get_registry
        return get_registry().is_materialized(table_name)
    except Exception as e:
        logger.warning("[VirtualSort] SSOT registry load failed: %s", e)
        return False


def execute_virtual_field_query(
    ds,
    builder: QueryBuilder,
    join_clause: str,
    order_alias: str,
    sort_dir: str,
    page: int,
    page_size: int,
    meta_obj: MetaObject = None,
    add_table_alias_fn=None,
) -> Tuple[List[Any], int]:
    logger.info(f"[VirtualSort] execute_virtual_field_query: page={page}, page_size={page_size}, order_alias={order_alias}, sort_dir={sort_dir}")

    table_name = meta_obj.table_name if meta_obj else builder._spec.table_name

    base_sql, params = builder.build_sql()
    logger.debug(f"[VirtualSort] base_sql: {base_sql}")

    base_sql = re.sub(r'\s+ORDER\s+BY\s+\S+\s+(?:ASC|DESC)', '', base_sql, flags=re.IGNORECASE)

    if "WHERE" in base_sql.upper():
        parts = base_sql.split("WHERE", 1)
        where_clause = parts[1]
        if add_table_alias_fn:
            where_clause = add_table_alias_fn(where_clause, table_name)
        where_clause_for_count = where_clause
    else:
        where_clause = None
        where_clause_for_count = None

    count_sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
    if where_clause_for_count:
        count_sql = f"{count_sql} WHERE {where_clause_for_count}"

    try:
        count_result = ds.query(count_sql, params)
        total = count_result[0].get('cnt', 0) if count_result else 0
        logger.debug(f"[VirtualSort] total count: {total}")
    except Exception as e:
        logger.warning(f"Virtual field count query failed: {e}")
        total = 0

    subquery_alias = "_vsq"
    subquery_select = f"SELECT {table_name}.*, {order_alias} AS _sort_val FROM {table_name} {join_clause}"
    if where_clause:
        subquery_select = f"SELECT {table_name}.*, {order_alias} AS _sort_val FROM {table_name} {join_clause} WHERE {where_clause}"

    sql_with_join = f"SELECT {subquery_alias}.* FROM ({subquery_select}) AS {subquery_alias} ORDER BY {subquery_alias}._sort_val {sort_dir}"

    offset = (page - 1) * page_size if page > 0 and page_size > 0 else 0
    if page_size > 0:
        sql_with_join = f"{sql_with_join} LIMIT {page_size} OFFSET {offset}"

    logger.info(f"[VirtualSort] Final SQL: {sql_with_join}")

    try:
        raw_data = ds.query(sql_with_join, params)
        logger.info(f"[VirtualSort] Query returned {len(raw_data)} rows")
    except Exception as e:
        logger.warning(f"Virtual field sort query failed: {e}, falling back to standard query")
        return builder.execute(), builder.count_all()

    if meta_obj and raw_data:
        main_table_fields = set()
        for f in meta_obj.fields:
            if hasattr(f, 'db_column') and f.db_column:
                main_table_fields.add(f.db_column)
            else:
                main_table_fields.add(f.id)

        main_table_fields.update(['id', 'created_at', 'created_by', 'updated_by', 'is_deleted'])

        data = []
        seen_ids = set()
        for row in raw_data:
            row_id = row.get('id')
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            clean_row = {k: v for k, v in row.items() if k in main_table_fields}
            data.append(clean_row)

        logger.debug(f"[VirtualSort] Cleaned data, {len(data)} rows (after dedup)")

        engine = get_enrichment_engine()
        logger.debug(f"[VirtualSort] EnrichmentEngine: {engine}")

        if meta_obj:
            data = enrich_records(meta_obj.id, data)
            logger.info(f"[VirtualSort] After enrich_records, first row sub_domain_name: {data[0].get('sub_domain_name') if data else 'N/A'}")
    else:
        data = raw_data

    return data, total
