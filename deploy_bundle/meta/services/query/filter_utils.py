import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from meta.core.models import MetaObject
from meta.core.table_name_validator import validate_table_name

logger = logging.getLogger(__name__)


def parse_filter_value(filter_value: Any) -> Tuple[Optional[str], Optional[Any]]:
    if isinstance(filter_value, (int, float)):
        return ('=', filter_value)

    if isinstance(filter_value, str):
        filter_value = filter_value.strip()

        patterns = [
            (r'^>=\s*(\d+(?:\.\d+)?)$', '>='),
            (r'^<=\s*(\d+(?:\.\d+)?)$', '<='),
            (r'^>\s*(\d+(?:\.\d+)?)$', '>'),
            (r'^<\s*(\d+(?:\.\d+)?)$', '<'),
            (r'^!=\s*(\d+(?:\.\d+)?)$', '!='),
            (r'^=\s*(\d+(?:\.\d+)?)$', '='),
            (r'^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$', 'between'),
            (r'^(\d+(?:\.\d+)?)$', '='),
        ]

        for pattern, op in patterns:
            match = re.match(pattern, filter_value)
            if match:
                if op == 'between':
                    return ('between', (float(match.group(1)), float(match.group(2))))
                else:
                    return (op, float(match.group(1)))

        logger.warning(f"[ComputedFieldFilter] Cannot parse filter value: {filter_value}")
        return (None, None)

    if isinstance(filter_value, list):
        if len(filter_value) == 2:
            return ('between', (float(filter_value[0]), float(filter_value[1])))
        else:
            return ('in', [float(v) for v in filter_value])

    return (None, None)


def build_computed_where_clause(count_expr: str, op: str, value: Any) -> Optional[str]:
    if op == '=':
        return f"{count_expr} = {int(value)}"
    elif op == '!=':
        return f"{count_expr} != {int(value)}"
    elif op == '>':
        return f"{count_expr} > {int(value)}"
    elif op == '>=':
        return f"{count_expr} >= {int(value)}"
    elif op == '<':
        return f"{count_expr} < {int(value)}"
    elif op == '<=':
        return f"{count_expr} <= {int(value)}"
    elif op == 'between':
        min_val, max_val = value
        return f"{count_expr} >= {int(min_val)} AND {count_expr} <= {int(max_val)}"
    elif op == 'in':
        values = ', '.join([str(int(v)) for v in value])
        return f"{count_expr} IN ({values})"
    else:
        logger.warning(f"[ComputedFieldFilter] Unknown operator: {op}")
        return None


def build_virtual_field_filter_exists(
    meta_obj: MetaObject,
    field_id: str,
    filter_value: Any,
    red_def,
) -> Tuple[Optional[str], List[Any]]:
    try:
        if not red_def.join_path:
            return None, []

        table_name = validate_table_name(meta_obj.table_name)
        alias = 'bo'
        if hasattr(meta_obj, 'analytical_model') and meta_obj.analytical_model:
            fact_config = meta_obj.analytical_model.get('fact', {})
            alias = fact_config.get('alias', 'bo')

        join_parts = []
        last_alias = alias
        target_field = None

        for idx, step in enumerate(red_def.join_path):
            join_alias = f"_vf{idx}"

            to_field = step.to_field if step.to_field else 'id'
            join_sql = (
                f"LEFT JOIN {step.table} AS {join_alias} "
                f"ON {last_alias}.{step.from_field} = {join_alias}.{to_field}"
            )

            if step.fixed_conditions:
                for fc in step.fixed_conditions:
                    fc_field, fc_op, fc_val = fc
                    if isinstance(fc_val, str):
                        join_sql += f" AND {join_alias}.{fc_field} {fc_op} '{fc_val}'"
                    else:
                        join_sql += f" AND {join_alias}.{fc_field} {fc_op} {fc_val}"

            join_parts.append(join_sql)
            last_alias = join_alias
            target_field = step.select

        if not target_field:
            return None, []

        select_field = target_field.split(' as ')[0] if ' as ' in target_field else target_field

        params = []
        where_clause = ""

        if isinstance(filter_value, list):
            placeholders = ', '.join(['?' for _ in filter_value])
            where_clause = f"{last_alias}.{select_field} IN ({placeholders})"
            params.extend(filter_value)
        elif isinstance(filter_value, str) and '%' in filter_value:
            where_clause = f"{last_alias}.{select_field} LIKE ?"
            params.append(filter_value)
        else:
            where_clause = f"{last_alias}.{select_field} = ?"
            params.append(filter_value)

        join_clause = " ".join(join_parts)

        exists_sql = f"""
            SELECT 1 FROM {table_name} AS {alias}
            {join_clause}
            WHERE {alias}.id = bo.id
            AND {where_clause}
        """.strip()

        logger.info(f"[VirtualFieldFilter] Built EXISTS SQL for {field_id}: {exists_sql[:100]}...")

        return exists_sql, params

    except Exception as e:
        logger.error(f"[VirtualFieldFilter] Failed to build EXISTS for {field_id}: {e}")
        return None, []


def build_exists_subquery(
    meta_obj: MetaObject,
    association: Dict[str, Any],
    filter_values: Dict[str, str],
) -> Tuple[Optional[str], List[Any]]:
    try:
        target_table = association.get('target_table')
        target_alias = association.get('target_alias', 't')
        on_conditions = association.get('on_conditions', [])
        where_conditions = association.get('where_conditions', [])

        if not target_table or not on_conditions:
            return None, []

        on_parts = []
        for cond in on_conditions:
            left = cond.get('left_field', '')
            operator = cond.get('operator', 'eq')
            right = cond.get('right_field', '')

            if left.startswith("'") and left.endswith("'"):
                left = left
            else:
                left = left

            if right.startswith("'") and right.endswith("'"):
                right = right

            sql_op = '=' if operator == 'eq' else operator
            on_parts.append(f"{left} {sql_op} {right}")

        on_clause = " AND ".join(on_parts)

        where_parts = []
        params = []

        for cond in where_conditions:
            field = cond.get('field', '')
            operator = cond.get('operator', 'eq')
            parameter = cond.get('parameter', '')

            if parameter not in filter_values:
                continue

            value = filter_values[parameter]

            if operator == 'in':
                if isinstance(value, str):
                    values = [v.strip() for v in value.split(',')]
                else:
                    values = value if isinstance(value, list) else [value]

                placeholders = ', '.join(['?' for _ in values])
                where_parts.append(f"{field} IN ({placeholders})")
                params.extend(values)

            elif operator == 'like':
                where_parts.append(f"{field} LIKE ?")
                params.append(f'%{value}%')

            else:
                where_parts.append(f"{field} = ?")
                params.append(value)

        if not where_parts:
            return None, []

        where_clause = " AND ".join(where_parts)

        exists_sql = f"""
            SELECT 1 FROM {target_table} {target_alias}
            WHERE {on_clause}
            AND {where_clause}
        """.strip()

        return exists_sql, params

    except Exception as e:
        logger.error(f"[CrossTableFilter] Failed to build EXISTS subquery: {e}")
        return None, []
