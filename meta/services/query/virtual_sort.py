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
