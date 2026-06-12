# -*- coding: utf-8 -*-
import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from meta.core.action_context import ActionContext, ActionResult
from meta.core.models import registry
from meta.core.model_utils import get_object_display
from meta.core.association_audit import write_association_audit
from meta.core.association.resolvers import resolve_assoc_meta, get_search_fields
from meta.core.association.validators import (

    validate_source_target_existence,
    check_cardinality_constraint,
    check_fk_required_before_unassign,
    check_m2m_exists,
)
from meta.core.association.fallback import (
    fallback_associate,
    fallback_dissociate,
    fallback_query_associations,
)
from meta.core.enrich_utils import (
    build_computed_count_filter_clause,
    build_computed_count_order_clause,
)
from meta.core.enrichment_engine import EnrichmentEngine

logger = logging.getLogger(__name__)

_DISPATCH_TABLE = {
    'associate': {
        'many_to_many': '_associate_m2m',
        'composition': '_associate_composition',
        'reference': '_associate_reference',
    },
    'dissociate': {
        'many_to_many': '_dissociate_m2m',
        'reference': '_dissociate_reference',
        'composition': None,
    },
    'assign': {
        'many_to_many': '_assign_m2m',
        'composition': '_assign_composition',
        'reference': '_assign_reference',
    },
    'unassign': {
        'many_to_many': '_unassign_m2m',
        'reference': '_unassign_reference',
        'composition': None,
    },
    'query': {
        'many_to_many': '_query_m2m',
        'reference': '_query_reference',
        'composition': '_query_composition',
        'one_to_many': '_query_composition',
        'reverse_many_to_many': '_query_reverse_m2m',
    },
    'count': {
        'many_to_many': '_count_m2m',
        'reference': '_count_reference',
        'composition': '_count_composition',
        'one_to_many': '_count_composition',
    },
}

_COMPOSITION_UNSUPPORTED_MSG = {
    'dissociate': "Composition关联不支持取消关联，请使用删除子对象",
    'unassign': "Composition关联不支持取消关联",
}


# 关联查询保留参数：这些 key 在 params 中出现时不应该作为过滤条件处理
_ASSOC_LIST_SKIP_KEYS = {
    'src_id', 'association_name', 'page', 'page_size', 'pageSize',
    'search', 'keyword', 'ordering', '_order_by', '_limit', '_offset',
    'filters',  # 嵌套 dict 形式 — 不在 SQL 层解析
}

# 标识符校验：只允许字母/数字/下划线（表名/列名安全）
_SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_SAFE_IDENT = _SAFE_IDENT_RE


def _safe_ident(name: str, default: str = 'id') -> str:
    """白名单校验列名/表名，禁止 SQL 注入风险。"""
    if not isinstance(name, str) or not _SAFE_IDENT.match(name):
        return default
    return name


# 不需要别名前缀的 SQL 关键字 / 逻辑词 / 已知别名
_ALIAS_SKIP = {
    't', 'j', 'OR', 'AND', 'NOT', 'LIKE', 'IN', 'NULL', 'IS', 'BETWEEN',
    'EXISTS', 'TRUE', 'FALSE', 'ASC', 'DESC', 'ORDER', 'BY', 'GROUP', 'HAVING',
    'SELECT', 'FROM', 'WHERE', 'INNER', 'LEFT', 'RIGHT', 'JOIN', 'ON', 'AS',
    'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
}


# 缓存：通过表名 → 非 id 列的列表（避免每次查询都查 PRAGMA）
_THROUGH_COLS_CACHE: Dict[str, List[str]] = {}


def _through_non_id_columns(context, through_table: str, exclude_keys: Optional[set] = None) -> List[str]:
    """获取 through 表的非 id、非排除列的列名列表。

    用于 m2m / reverse_m2m 查询显式列出 j 的列（避免 j.id 与 t.id 冲突）。
    """
    if not through_table or not _SAFE_IDENT_RE.match(through_table):
        return []
    cached = _THROUGH_COLS_CACHE.get(through_table)
    if cached is not None:
        return [c for c in cached if c not in (exclude_keys or set())]
    try:
        cursor = context.data_source.execute(f"PRAGMA table_info({through_table})")
        cols = [row[1] for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"[_through_non_id_columns] PRAGMA table_info({through_table}) failed: {e}")
        cols = []
    # 过滤掉 id 列（与目标表 t.id 冲突）和排除键
    cols = [c for c in cols if c != 'id' and c not in (exclude_keys or set())]
    _THROUGH_COLS_CACHE[through_table] = cols
    return cols


# Element Plus 可排序列索引后缀 ":N"（如 "-updated_at:1"）
# 复用了 _do_list 的剥离逻辑，避免后端因 ":1" 后缀将整段作为字段名
# 透传到 ORDER BY 触发 SQL 错误。
try:
    from meta.core.sql_adapters import _SORTABLE_INDEX_SUFFIX
except Exception:  # noqa: BLE001
    _SORTABLE_INDEX_SUFFIX = re.compile(r':\d+$')


# 这些"虚拟/审计"字段在 DB 中可能并不存在（如 user 表没有 updated_at 物理列），
# 默认排序触发时会触发 "no such column" 错误。识别它们并回退到 id 排序。
_VIRTUAL_AUDIT_FIELDS = {'updated_at', 'created_at', 'created_by', 'updated_by'}


def _alias_where_clause(where_sql: str, alias: str) -> str:
    """为 WHERE 子句中的字段名加上表别名（已带别名的字段不动）。

    形如 "col1 LIKE ? AND col2 >= ?"  →  "t.col1 LIKE ? AND t.col2 >= ?"
    形如 "(col1 LIKE ? OR col2 = ?)"  →  "(t.col1 LIKE ? OR t.col2 = ?)"

    [FIX] 子查询（如 computed count 的 "(SELECT COUNT(*) FROM through WHERE ...)"）
    内部不应被加别名；通过 _split_outside_subqueries 切出子查询，仅对外层片段别名化。
    """
    if not where_sql:
        return where_sql

    segments = _split_outside_subqueries(where_sql)
    aliased_segments: List[str] = []
    for seg in segments:
        if seg['in_subquery']:
            # 子查询原样保留（其内部的 FROM/where/列名已在构建时正确处理）
            aliased_segments.append(seg['text'])
            continue
        aliased_segments.append(_alias_identifiers_in_text(seg['text'], alias))
    return ''.join(aliased_segments)


def _alias_identifiers_in_text(text: str, alias: str) -> str:
    """对单段（不含子查询）SQL 文本中的标识符加别名。

    形如 "col1 LIKE ? AND col2 >= ?"  →  "t.col1 LIKE ? AND t.col2 >= ?"
    """
    def replace_ident(m):
        ident = m.group(1)
        if ident in _ALIAS_SKIP or '.' in ident or ident.upper() in _ALIAS_SKIP:
            return m.group(0)
        return f"{alias}.{ident}{m.group(2)}"
    return re.sub(r'\b([A-Za-z_][A-Za-z0-9_]*)(\s|\)|\,|$)', replace_ident, text)


def _split_outside_subqueries(sql: str) -> List[Dict[str, Any]]:
    """把 SQL 切分成 [子查询, 外层片段, 子查询, ...] 序列。

    用于区分哪些片段需要做表别名替换（外层），哪些保持原样（子查询内部）。
    """
    segments: List[Dict[str, Any]] = []
    i = 0
    n = len(sql)
    buf_start = 0
    while i < n:
        if sql[i] == '(':
            # 检查是否是 (SELECT
            m = re.match(r'\(\s*SELECT\b', sql[i:], re.IGNORECASE)
            if m:
                # 先把 buf_start..i 段（非子查询）保存
                if i > buf_start:
                    segments.append({'in_subquery': False, 'text': sql[buf_start:i]})
                # 找匹配的右括号
                end = _find_matching_paren(sql, i)
                if end == -1:
                    # 括号不闭合，把剩余全部当外层处理
                    segments.append({'in_subquery': False, 'text': sql[buf_start:]})
                    return segments
                # 子查询段（包含括号本身）
                segments.append({'in_subquery': True, 'text': sql[i:end + 1]})
                i = end + 1
                buf_start = i
                continue
        i += 1
    if buf_start < n:
        segments.append({'in_subquery': False, 'text': sql[buf_start:]})
    return segments


def _find_matching_paren(sql: str, start: int) -> int:
    """从 start 位置（应为 `(`）找匹配的 `)`，正确处理嵌套和字符串字面量。"""
    depth = 0
    i = start
    n = len(sql)
    in_string = False
    string_quote = ''
    while i < n:
        ch = sql[i]
        if in_string:
            if ch == string_quote:
                # 检查是否是双引号转义（SQL 风格为 '' 而非 \"）
                if i + 1 < n and sql[i + 1] == string_quote:
                    i += 2
                    continue
                in_string = False
        else:
            if ch in ('"', "'"):
                in_string = True
                string_quote = ch
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _alias_order_clause(order_sql: str, alias: str) -> str:
    """为 ORDER BY 子句中的字段名加上表别名（已带别名的字段不动）。

    形如 "ORDER BY name DESC"  →  "ORDER BY t.name DESC"
    """
    if not order_sql or not order_sql.strip():
        return order_sql or ''
    return _alias_where_clause(order_sql, alias)


def _resolve_field_column(target_meta, field_id: str) -> Optional[str]:
    """根据 field_id 找到对应的 DB 列名。

    支持：精确 id 匹配、去掉 _id 后缀匹配（FK 显示字段）、db_column 直接匹配。
    返回 None 表示未找到。
    """
    if target_meta is None:
        return None
    field = target_meta.get_field(field_id) if hasattr(target_meta, 'get_field') else None
    if field is not None:
        return getattr(field, 'db_column', None) or field_id
    # FK 显示字段兜底：例如 manager_id 字段，前端按 manager_id_display 排序
    candidate = field_id
    if field_id.endswith('_display'):
        candidate = field_id[:-8]
    if candidate.endswith('_id'):
        candidate = candidate[:-3]
    field2 = target_meta.get_field(candidate) if hasattr(target_meta, 'get_field') else None
    if field2 is not None:
        return getattr(field2, 'db_column', None) or candidate
    return None


def _build_assoc_filter_plan(target_meta, filters: Dict[str, Any], target_alias: str = '') -> Tuple[str, List[Any]]:
    """把前端过滤 dict 编译成 (where_sql, params)。

    支持的 key 形式（与前端 addFilterParam / useMetaList._buildQueryParams 一致）：
      - field=value                精确匹配
      - field__in=v1,v2,v3         IN 多选
      - field__like=%x%            模糊匹配（已包含通配符）
      - field__gte=v               >=
      - field__lte=v               <=
      - field_start=v              配合 field_end 构成日期区间
      - field_end=v
    未知后缀或未匹配字段会被静默忽略（不抛错，保持与 _do_list 的容错风格一致）。
    """
    if not filters:
        return '', []

    conds: List[str] = []
    cond_params: List[Any] = []

    # 合并日期 start/end 配对
    consumed: set = set()
    pending_starts: Dict[str, str] = {}  # base -> key_start
    pending_ends: Dict[str, str] = {}    # base -> key_end
    for key in filters.keys():
        if key.endswith('_start'):
            base = key[:-6]
            pending_starts[base] = key
        elif key.endswith('_end'):
            base = key[:-4]
            pending_ends[base] = key

    for key, value in filters.items():
        if key in consumed:
            continue
        if value is None or value == '':
            continue

        # 过滤掉保留键
        if key in _ASSOC_LIST_SKIP_KEYS:
            continue

        # [FIX] computed *_count 字段（如 member_count、groups_count）DB 中无物理列，
        # 必须通过子查询走 through 表 COUNT。详见 enrich_utils.build_computed_count_filter_clause。
        computed_clause, computed_params = build_computed_count_filter_clause(
            target_meta, key, value, target_alias=target_alias
        )
        if computed_clause is not None:
            conds.append(computed_clause)
            cond_params.extend(computed_params)
            consumed.add(key)
            # 配对 _start/_end 时避免重复处理
            if key.endswith('_start'):
                base = key[:-6]
                end_key = pending_ends.get(base)
                if end_key:
                    consumed.add(end_key)
            elif key.endswith('_end'):
                base = key[:-4]
                start_key = f"{base}_start"
                consumed.add(start_key)
            continue

        # 日期 start/end 配对
        if key.endswith('_start'):
            base = key[:-6]
            end_key = pending_ends.get(base)
            if end_key is not None and filters.get(end_key):
                col = _resolve_field_column(target_meta, base) or _safe_ident(base)
                conds.append(f"{col} >= ?")
                cond_params.append(value)
                conds.append(f"{col} <= ?")
                cond_params.append(filters[end_key])
                consumed.add(key)
                consumed.add(end_key)
            else:
                col = _resolve_field_column(target_meta, base) or _safe_ident(base)
                conds.append(f"{col} >= ?")
                cond_params.append(value)
                consumed.add(key)
            continue
        if key.endswith('_end'):
            if key in consumed:
                continue
            base = key[:-4]
            col = _resolve_field_column(target_meta, base) or _safe_ident(base)
            conds.append(f"{col} <= ?")
            cond_params.append(value)
            consumed.add(key)
            continue

        # 多选 IN
        if key.endswith('__in'):
            base = key[:-4]
            col = _resolve_field_column(target_meta, base) or _safe_ident(base)
            if isinstance(value, str):
                values = [v.strip() for v in value.split(',') if v.strip() != '']
            elif isinstance(value, (list, tuple)):
                values = [str(v) for v in value if v not in (None, '')]
            else:
                values = [str(value)]
            if not values:
                continue
            placeholders = ', '.join(['?'] * len(values))
            conds.append(f"{col} IN ({placeholders})")
            cond_params.extend(values)
            continue

        # 模糊匹配
        if key.endswith('__like'):
            base = key[:-6]
            col = _resolve_field_column(target_meta, base) or _safe_ident(base)
            conds.append(f"{col} LIKE ?")
            cond_params.append(value)
            continue

        # 数值区间
        if key.endswith('__gte'):
            base = key[:-5]
            col = _resolve_field_column(target_meta, base) or _safe_ident(base)
            conds.append(f"{col} >= ?")
            cond_params.append(value)
            continue
        if key.endswith('__lte'):
            base = key[:-5]
            col = _resolve_field_column(target_meta, base) or _safe_ident(base)
            conds.append(f"{col} <= ?")
            cond_params.append(value)
            continue

        # 精确匹配
        col = _resolve_field_column(target_meta, key) or _safe_ident(key)
        conds.append(f"{col} = ?")
        cond_params.append(value)

    if not conds:
        return '', []
    return ' AND '.join(conds), cond_params


def _build_assoc_order_plan(target_meta, params: Dict[str, Any], target_alias: str = '') -> Tuple[str, List[Any]]:
    """把 ordering 字符串编译成 (order_sql, params)。

    ordering 形如 "name" 或 "-name"，多字段以逗号分隔。

    - 兼容 Element Plus 的 ":N" 列索引后缀（如 "-updated_at:1"），先剥离。
    - 对于 DB 中不存在的虚拟/审计字段（updated_at/created_at 等），回退到 id。
    - 未知字段名一律走 _safe_ident 校验，防止 SQL 注入。
    """
    ordering = (params.get('ordering') or params.get('_order_by') or '')
    if not isinstance(ordering, str) or not ordering.strip():
        return 'ORDER BY id DESC', []

    parts = [p.strip() for p in ordering.split(',') if p.strip()]
    if not parts:
        return 'ORDER BY id DESC', []

    # 收集目标对象的物理列集合，用于判断字段是否在 DB 中真实存在
    physical_columns: set = set()
    if target_meta is not None and hasattr(target_meta, 'fields') and target_meta.fields:
        for f in target_meta.fields:
            db_col = getattr(f, 'db_column', None) or getattr(f, 'name', None) or getattr(f, 'key', None)
            storage = getattr(f, 'storage', None)
            # 虚拟字段（audit_aspect 自动注入的 updated_at 等）DB 中无物理列
            storage_value = storage.value if hasattr(storage, 'value') else str(storage)
            if db_col and storage_value != 'virtual':
                physical_columns.add(db_col)
                physical_columns.add(getattr(f, 'name', None) or getattr(f, 'key', None))

    order_clauses: List[str] = []
    for part in parts:
        is_desc = part.startswith('-')
        field_name = part.lstrip('-+')
        if not field_name:
            continue
        # 去掉 Element Plus 的列索引后缀 ":N"
        field_name = _SORTABLE_INDEX_SUFFIX.sub('', field_name)
        if not field_name:
            continue

        # [FIX] computed *_count 字段（如 member_count、groups_count）DB 中无物理列，
        # 必须通过子查询走 through 表 COUNT。
        computed_order_sql = build_computed_count_order_clause(
            target_meta, field_name, is_desc, target_alias=target_alias
        )
        if computed_order_sql is not None:
            order_clauses.append(computed_order_sql)
            continue

        # 字段必须在白名单内：要么是元数据中的字段，要么是 _safe_ident 校验通过
        col = _resolve_field_column(target_meta, field_name)
        if col is None:
            # 未知字段：尝试用 _safe_ident 兜底（仅允许 [A-Za-z_][A-Za-z0-9_]*）
            if not _SAFE_IDENT_RE.match(field_name):
                logger.warning(
                    f"[AssociationEngine._build_assoc_order_plan] Dropping unsafe ordering field: {field_name!r}"
                )
                continue
            col = field_name

        # 虚拟/审计字段（如 user 表无 updated_at 物理列）→ 回退到 id
        if col in _VIRTUAL_AUDIT_FIELDS and physical_columns and col not in physical_columns:
            logger.debug(
                f"[AssociationEngine._build_assoc_order_plan] "
                f"Field {col!r} is virtual/audit-only in {target_meta.id if target_meta else '?'}; falling back to id"
            )
            col = 'id'
            # 审计默认场景下保持 DESC（默认是 -updated_at）
            is_desc = True

        order_clauses.append(f"{col} {'DESC' if is_desc else 'ASC'}")

    if not order_clauses:
        return 'ORDER BY id DESC', []
    return 'ORDER BY ' + ', '.join(order_clauses), []


def _build_assoc_search_plan(target_meta, search: str) -> Tuple[str, List[Any]]:
    """根据 search 关键词 + 目标对象的文本字段构造 LIKE 条件（OR 拼接）。

    仅在存在可搜索文本字段时返回条件；否则返回空串（与 _do_list 行为一致）。
    """
    if not search or not isinstance(search, str):
        return '', []
    search = search.strip()
    if not search:
        return '', []

    if target_meta is None:
        return '', []
    search_fields = get_search_fields(target_meta)
    if not search_fields:
        return '', []

    like = f"%{search}%"
    conds = [f"{col} LIKE ?" for col in search_fields]
    params = [like] * len(search_fields)
    return '(' + ' OR '.join(conds) + ')', params


def _build_assoc_list_plan(target_meta, params: Dict[str, Any], target_alias: str = '') -> Tuple[str, List[Any], str, List[Any], str, List[Any]]:
    """组合过滤/排序/搜索三个子句。

    返回 (where_sql, where_params, order_sql, order_params, search_sql, search_params)。
    search_sql/search_params 可被调用方用 AND 拼到 WHERE；order_sql 形如 "ORDER BY ..."。

    target_alias: 目标表别名（m2m/reverse_m2m 用 't'，composition 用空串）。
    透传到 computed count 子查询，使 `(SELECT COUNT(*) FROM through WHERE col = t.id)` 中
    的 t.id 能正确指向已别名的目标表。
    """
    raw_filters = params.get('filters') or {}
    if not isinstance(raw_filters, dict):
        raw_filters = {}
    extra_where_sql, extra_where_params = _build_assoc_filter_plan(target_meta, raw_filters, target_alias=target_alias)

    order_sql, order_params = _build_assoc_order_plan(target_meta, params, target_alias=target_alias)

    search = (params.get('search') or params.get('keyword') or '')
    search_sql, search_params = _build_assoc_search_plan(target_meta, search)

    return extra_where_sql, extra_where_params, order_sql, order_params, search_sql, search_params


def _apply_assoc_list_post_filter(records: List[Dict[str, Any]], target_meta, params: Dict[str, Any]) \
        -> Tuple[List[Dict[str, Any]], int]:
    """对内存中的 record 列表应用过滤/搜索/排序 + 分页。

    用于 reference 关联（量小，避免复杂 join）和 m2m（也支持当 SQL 端尚未实现过滤时）。
    返回 (records, total)。过滤/搜索任一失败时静默忽略该条件，避免破坏主流程。
    """
    total = len(records)
    if not records:
        return records, 0

    try:
        raw_filters = params.get('filters') or {}
        if isinstance(raw_filters, dict) and raw_filters:
            for key, value in raw_filters.items():
                if value is None or value == '' or key in _ASSOC_LIST_SKIP_KEYS:
                    continue
                # 把多值/范围归一化成 list of (op, value)
                ops: List[Tuple[str, Any]] = []
                if key.endswith('__in'):
                    base = key[:-4]
                    if isinstance(value, str):
                        vals = [v.strip() for v in value.split(',') if v.strip()]
                    else:
                        vals = list(value) if hasattr(value, '__iter__') else [value]
                    for v in vals:
                        ops.append(('eq', (base, v)))
                elif key.endswith('__like'):
                    base = key[:-6]
                    ops.append(('like', (base, value)))
                elif key.endswith('__gte'):
                    base = key[:-5]
                    ops.append(('gte', (base, value)))
                elif key.endswith('__lte'):
                    base = key[:-5]
                    ops.append(('lte', (base, value)))
                elif key.endswith('_start'):
                    base = key[:-6]
                    end_key = base + '_end'
                    if end_key in raw_filters and raw_filters[end_key]:
                        ops.append(('gte', (base, value)))
                        ops.append(('lte', (base, raw_filters[end_key])))
                    else:
                        ops.append(('gte', (base, value)))
                elif key.endswith('_end'):
                    if key in [k for k in raw_filters.keys() if k.endswith('_start') and k[:-6] == key[:-4]]:
                        continue
                    base = key[:-4]
                    ops.append(('lte', (base, value)))
                else:
                    ops.append(('eq', (key, value)))

                def match(rec: Dict[str, Any], op: str, payload: Tuple[str, Any]) -> bool:
                    field_name, val = payload
                    actual = rec.get(field_name)
                    if actual is None:
                        return False
                    try:
                        if op == 'eq':
                            return str(actual) == str(val)
                        if op == 'like':
                            return str(val).replace('%', '') in str(actual)
                        if op == 'gte':
                            return float(actual) >= float(val)
                        if op == 'lte':
                            return float(actual) <= float(val)
                    except (TypeError, ValueError):
                        return False
                    return False

                records = [r for r in records if any(match(r, op, p) for op, p in ops)]
    except Exception as e:
        logger.warning(f"[AssociationEngine] post-filter failed, returning unfiltered: {e}")

    # 搜索
    try:
        search = params.get('search') or params.get('keyword') or ''
        if isinstance(search, str) and search.strip() and target_meta is not None:
            search_fields = get_search_fields(target_meta)
            if search_fields:
                keyword = search.strip().lower()
                records = [
                    r for r in records
                    if any(keyword in str(r.get(col, '')).lower() for col in search_fields)
                ]
    except Exception as e:
        logger.warning(f"[AssociationEngine] post-search failed, returning unsorted: {e}")

    # 排序
    try:
        ordering = params.get('ordering') or params.get('_order_by') or ''
        if isinstance(ordering, str) and ordering.strip():
            parts = [p.strip() for p in ordering.split(',') if p.strip()]

            def sort_key(r: Dict[str, Any]):
                keys = []
                for part in parts:
                    is_desc = part.startswith('-')
                    field_name = part.lstrip('-+')
                    val = r.get(field_name)
                    if val is None:
                        keys.append((1, ''))
                    else:
                        keys.append((0, str(val).lower() if isinstance(val, str) else val, is_desc))
                return keys

            records = sorted(records, key=sort_key)
    except Exception as e:
        logger.warning(f"[AssociationEngine] post-sort failed, returning unsorted: {e}")

    return records, len(records)


def _store_effective_ids(context: 'ActionContext', effective_ids: list) -> None:
    """[FIX 2026-06-12] 把 _try_bulk_m2m 查到的"实际存在的关联 ID"存入 context.extra,
    供 AuditInterceptor 在事务提交后复用, 避免重复 SELECT 查不到删除前的状态.

    使用 key '_assoc_effective_ids' 是为避免与业务字段冲突 (前面加下划线).
    """
    if not context:
        return
    extra = getattr(context, 'extra', None)
    if extra is None:
        # ActionContext 的 extra 是 dict, 不应 None
        return
    extra['_assoc_effective_ids'] = list(effective_ids) if effective_ids else []


class AssociationEngine:
    def _write_audit_log(self, context: ActionContext, action: str,
                        tgt_type: str, tgt_id: int, association_name: str = None):
        write_association_audit(
            data_source=context.data_source,
            object_type=context.object_type,
            src_id=context.params.get('src_id'),
            tgt_type=tgt_type,
            tgt_id=tgt_id,
            action=action,
            association_name=association_name,
            user_id=context.user_id,
            user_name=context.user_name,
        )

    def _resolve_assoc_meta(self, object_type: str, association_name: str) -> Optional[Dict]:
        return resolve_assoc_meta(object_type, association_name)

    def _dispatch(self, context: ActionContext, operation: str) -> ActionResult:
        params = context.params
        association_name = params.get('association_name', '')
        assoc_meta = resolve_assoc_meta(context.object_type, association_name)

        if assoc_meta is None:
            fallback_map = {
                'associate': lambda ctx: fallback_associate(self, ctx),
                'dissociate': lambda ctx: fallback_dissociate(self, ctx),
                'assign': lambda ctx: fallback_associate(self, ctx),
                'unassign': lambda ctx: fallback_dissociate(self, ctx),
                'query': lambda ctx: fallback_query_associations(ctx, association_name),
                'count': lambda ctx: ActionResult(success=True, data={'count': 0}),
            }
            fallback = fallback_map.get(operation)
            if fallback:
                return fallback(context)
            return ActionResult(success=True, data={'count': 0})

        assoc_type = assoc_meta.get('type', 'many_to_many')
        dispatch_map = _DISPATCH_TABLE.get(operation, {})
        method_name = dispatch_map.get(assoc_type)

        if method_name is None:
            if assoc_type == 'composition' and operation in _COMPOSITION_UNSUPPORTED_MSG:
                return ActionResult(
                    success=False,
                    message=_COMPOSITION_UNSUPPORTED_MSG[operation]
                )
            return ActionResult(
                success=False,
                message=f"Unknown association type: {assoc_type}"
            )

        method = getattr(self, method_name)
        return method(context, assoc_meta)

    def associate(self, context: ActionContext) -> ActionResult:
        return self._dispatch(context, 'associate')

    def dissociate(self, context: ActionContext) -> ActionResult:
        return self._dispatch(context, 'dissociate')

    def query_associations(self, context: ActionContext) -> ActionResult:
        return self._dispatch(context, 'query')

    def assign(self, context: ActionContext) -> ActionResult:
        return self._dispatch(context, 'assign')

    def unassign(self, context: ActionContext) -> ActionResult:
        return self._dispatch(context, 'unassign')

    def _batch_operation(self, context: ActionContext, operation_name: str,
                         operation_method, pass_metadata: bool = False):
        params = context.params
        association_name = params.get('association_name', '')
        target_ids = params.get('target_ids', [])
        metadata = params.get('metadata', {})

        if not target_ids:
            return ActionResult(success=True, message=f"没有需要{operation_name}的目标")

        results = self._try_bulk_m2m(context, target_ids, operation_method, pass_metadata)
        if results is None:
            results = []
            for tgt_id in target_ids:
                op_params = context.params.copy()
                op_params['tgt_id'] = tgt_id
                if pass_metadata:
                    op_params['metadata'] = metadata if isinstance(metadata, dict) else {}
                op_context = ActionContext(
                    object_type=context.object_type,
                    action=f'batch_{operation_name}',
                    params=op_params,
                    data_source=context.data_source,
                )
                result = operation_method(op_context)
                results.append({'target_id': tgt_id, 'success': result.success, 'message': result.message})

        success_count = sum(1 for r in results if r['success'])
        return ActionResult(
            success=success_count == len(results),
            data={'results': results, 'success_count': success_count, 'total_count': len(results)},
            message=f"批量{operation_name}完成: {success_count}/{len(results)}",
        )

    def _try_bulk_m2m(self, context, target_ids, operation_method, pass_metadata):
        if operation_method not in (self.assign, self.unassign):
            return None
        params = context.params
        association_name = params.get('association_name', '')
        assoc_meta = resolve_assoc_meta(context.object_type, association_name)
        if not assoc_meta or assoc_meta.get('type') != 'many_to_many':
            return None

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        if not through or not source_key or not target_key:
            return None

        src_id = params.get('src_id')
        if not src_id:
            return None

        try:
            if operation_method == self.assign:
                placeholders = ','.join(f'(?,?)' for _ in target_ids)
                flat_vals = []
                for tid in target_ids:
                    flat_vals.extend([src_id, tid])
                sql = f"INSERT OR IGNORE INTO {through} ({source_key},{target_key}) VALUES {placeholders}"
                context.data_source.execute(sql, tuple(flat_vals))
                # [FIX 2026-06-12] 把 effective_ids (实际已存在的关联) 传给审计拦截器
                # INSERT OR IGNORE 只插入不存在的, 所以有效 ID 是 tgt_ids
                _store_effective_ids(context, target_ids)
                return [{'target_id': tid, 'success': True, 'message': '批量分配成功'} for tid in target_ids]
            else:
                # [FIX 2026-06-12] 先 SELECT 现有的关联 ID, 再 DELETE.
                # 原实现先 DELETE 再让审计拦截器 SELECT, 但 SQLite WAL 模式下
                # 后续 SELECT 在不同连接上看不到未提交的 DELETE, 导致 existing=set().
                # 必须在 DELETE 前先 SELECT, 然后只删除存在的, 把 effective_ids 传给审计.
                sel_placeholders = ','.join('?' for _ in target_ids)
                sel_sql = (f"SELECT {target_key} FROM {through} "
                           f"WHERE {source_key}=? AND {target_key} IN ({sel_placeholders})")
                existing_rows = context.data_source.execute(
                    sel_sql, tuple([src_id] + target_ids)
                ).fetchall() or []
                existing_ids = [r[0] for r in existing_rows]

                if not existing_ids:
                    # [FIX 2026-06-12] 即便没找到也要存空列表, 审计拦截器看到空就跳过
                    _store_effective_ids(context, [])
                    return [{'target_id': tid, 'success': True, 'message': '批量取消分配成功(无现存关联)'} for tid in target_ids]

                del_placeholders = ','.join('?' for _ in existing_ids)
                del_sql = (f"DELETE FROM {through} WHERE {source_key}=? "
                           f"AND {target_key} IN ({del_placeholders})")
                context.data_source.execute(del_sql, tuple([src_id] + existing_ids))
                # [FIX 2026-06-12] 关键: 把 effective_ids 存入 context, 让审计拦截器复用
                _store_effective_ids(context, existing_ids)
                return [{'target_id': tid, 'success': True, 'message': '批量取消分配成功'} for tid in existing_ids]
        except Exception as e:
            logger.warning(f"[AssociationEngine] bulk m2m failed, falling back to per-item: {e}")
            return None

    def batch_assign(self, context: ActionContext) -> ActionResult:
        return self._batch_operation(context, '分配', self.assign, pass_metadata=True)

    def batch_unassign(self, context: ActionContext) -> ActionResult:
        return self._batch_operation(context, '取消分配', self.unassign)

    def count(self, context: ActionContext) -> ActionResult:
        return self._dispatch(context, 'count')

    def batch_query_associations(self, context: ActionContext) -> ActionResult:
        params = context.params
        source_ids = params.get('source_ids', [])
        association_name = params.get('association_name', '')

        if not source_ids:
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

        assoc_meta = resolve_assoc_meta(context.object_type, association_name)
        if assoc_meta is None:
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

        assoc_type = assoc_meta.get('type', 'many_to_many')

        if assoc_type == 'many_to_many':
            return self._batch_query_m2m(context, assoc_meta, source_ids)
        elif assoc_type in ('composition', 'one_to_many'):
            return self._batch_query_composition(context, assoc_meta, source_ids)
        elif assoc_type == 'reverse_many_to_many':
            return self._batch_query_reverse_m2m(context, assoc_meta, source_ids)

        return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

    def _associate_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')
        metadata = params.get('metadata', {})

        existence_error = validate_source_target_existence(
            self, context, src_id, tgt_type, tgt_id, assoc_meta)
        if existence_error:
            return existence_error

        cardinality_error = check_cardinality_constraint(self, context, src_id, assoc_meta)
        if cardinality_error:
            return cardinality_error

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')

        if not through or not source_key or not target_key:
            return fallback_associate(self, context)

        existing = check_m2m_exists(context, through, source_key, target_key, src_id, tgt_id)
        if existing:
            return ActionResult(success=True, message=f"关联已存在")

        cols = [source_key, target_key]
        vals = [src_id, tgt_id]

        meta_fields = assoc_meta.get('metadata_fields', [])
        if isinstance(meta_fields, list):
            for mf in meta_fields:
                mf_id = mf.get('id') if isinstance(mf, dict) else getattr(mf, 'id', None)
                mf_default = mf.get('default') if isinstance(mf, dict) else getattr(mf, 'default', None)
                if mf_id:
                    cols.append(mf_id)
                    vals.append(metadata.get(mf_id, mf_default))

        placeholders = ','.join(['?'] * len(cols))
        col_names = ','.join(cols)
        sql = f"INSERT OR REPLACE INTO {through} ({col_names}) VALUES ({placeholders})"

        try:
            context.data_source.execute(sql, vals)
            tgt_display = get_object_display(tgt_type, tgt_id, context.data_source)
            return ActionResult(
                success=True,
                message=f"成功关联 {tgt_type}:{tgt_display or tgt_id} 到 {context.object_type}:{src_id}",
            )
        except Exception as e:
            logger.error(f"[AssociationEngine] m2m associate error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _assign_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')
        metadata = params.get('metadata', {})
        association_name = params.get('association_name', '')

        existence_error = validate_source_target_existence(
            self, context, src_id, tgt_type, tgt_id, assoc_meta)
        if existence_error:
            return existence_error

        cardinality_error = check_cardinality_constraint(self, context, src_id, assoc_meta)
        if cardinality_error:
            return cardinality_error

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')

        if not through or not source_key or not target_key:
            return fallback_associate(self, context)

        existing = check_m2m_exists(context, through, source_key, target_key, src_id, tgt_id)
        if existing:
            return ActionResult(success=True, message="已关联，无需重复操作")

        cols = [source_key, target_key]
        vals = [src_id, tgt_id]

        meta_fields = assoc_meta.get('metadata_fields', [])
        if isinstance(meta_fields, list):
            for mf in meta_fields:
                mf_id = mf.get('id') if isinstance(mf, dict) else getattr(mf, 'id', None)
                mf_default = mf.get('default') if isinstance(mf, dict) else getattr(mf, 'default', None)
                if mf_id:
                    cols.append(mf_id)
                    vals.append(metadata.get(mf_id, mf_default))

        placeholders = ','.join(['?'] * len(cols))
        col_names = ','.join(cols)
        sql = f"INSERT INTO {through} ({col_names}) VALUES ({placeholders})"

        try:
            context.data_source.execute(sql, vals)
            self._write_audit_log(context, 'ASSOCIATE', tgt_type, tgt_id, association_name)
            return ActionResult(success=True, message="分配成功")
        except Exception as e:
            if "UNIQUE constraint failed" in str(e) or "duplicate key" in str(e).lower():
                return ActionResult(success=True, message="已关联，无需重复操作")
            logger.error(f"[AssociationEngine] m2m assign error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _unassign_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')
        association_name = params.get('association_name', '')

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')

        if not through or not source_key or not target_key:
            return fallback_dissociate(self, context)

        sql = f"DELETE FROM {through} WHERE {source_key} = ? AND {target_key} = ?"

        try:
            context.data_source.execute(sql, [src_id, tgt_id])
            self._write_audit_log(context, 'DISSOCIATE', tgt_type, tgt_id, association_name)
            return ActionResult(success=True, message="取消分配成功")
        except Exception as e:
            logger.error(f"[AssociationEngine] m2m unassign error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _count_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')

        if not through or not source_key:
            return ActionResult(success=True, data={'count': 0})

        try:
            sql = f"SELECT COUNT(*) FROM {through} WHERE {source_key} = ?"
            cursor = context.data_source.execute(sql, [src_id])
            count = cursor.fetchone()[0]
            return ActionResult(success=True, data={'count': count})
        except Exception as e:
            logger.error(f"[AssociationEngine] m2m count error: {e}")
            return ActionResult(success=True, data={'count': 0})

    def _batch_query_m2m(self, context: ActionContext, assoc_meta: Dict, source_ids: List[int]) -> ActionResult:
        params = context.params
        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not through or not source_key or not target_key or not target_entity:
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

        target_meta = registry.get(target_entity)
        target_table = target_meta.table_name if target_meta else target_entity

        page = params.get('page', 1)
        page_size = params.get('page_size', 20)
        search = params.get('search')

        try:
            placeholders = ','.join(['?'] * len(source_ids))

            count_sql = f"SELECT {source_key}, COUNT(*) as cnt FROM {through} WHERE {source_key} IN ({placeholders}) GROUP BY {source_key}"
            cursor = context.data_source.execute(count_sql, source_ids)
            counts = {row[0]: row[1] for row in cursor.fetchall()}

            target_ids_sql = f"SELECT DISTINCT j.{target_key} FROM {through} j WHERE j.{source_key} IN ({placeholders})"
            cursor = context.data_source.execute(target_ids_sql, source_ids)
            target_ids = [row[0] for row in cursor.fetchall()]

            if not target_ids:
                return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': counts})

            tgt_placeholders = ','.join(['?'] * len(target_ids))
            conditions = [f"t.id IN ({tgt_placeholders})"]
            bind_params = list(target_ids)

            if search:
                search_fields = get_search_fields(target_meta)
                if search_fields:
                    or_clauses = [f"t.{f} LIKE ?" for f in search_fields]
                    conditions.append("(" + " OR ".join(or_clauses) + ")")
                    bind_params.extend([f"%{search}%"] * len(search_fields))

            where_clause = " AND ".join(conditions)

            count_total_sql = f"SELECT COUNT(*) FROM {target_table} t WHERE {where_clause}"
            cursor = context.data_source.execute(count_total_sql, bind_params)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            sql = f"SELECT t.* FROM {target_table} t WHERE {where_clause} ORDER BY t.id LIMIT ? OFFSET ?"
            cursor = context.data_source.execute(sql, bind_params + [page_size, offset])
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            return ActionResult(success=True, data={'items': records, 'total': total, 'page': page, 'page_size': page_size, 'counts': counts})
        except Exception as e:
            logger.error(f"[AssociationEngine] batch_query_m2m error: {e}")
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

    def _batch_query_composition(self, context: ActionContext, assoc_meta: Dict, source_ids: List[int]) -> ActionResult:
        params = context.params
        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not source_key or not target_entity:
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

        if not source_key:
            source_key = f"{context.object_type}_id"

        tgt_meta = registry.get(target_entity)
        tgt_table = tgt_meta.table_name if tgt_meta else target_entity

        page = params.get('page', 1)
        page_size = params.get('page_size', 20)

        try:
            placeholders = ','.join(['?'] * len(source_ids))

            count_sql = f"SELECT {source_key}, COUNT(*) as cnt FROM {tgt_table} WHERE {source_key} IN ({placeholders}) GROUP BY {source_key}"
            cursor = context.data_source.execute(count_sql, source_ids)
            counts = {row[0]: row[1] for row in cursor.fetchall()}

            total_sql = f"SELECT COUNT(*) FROM {tgt_table} WHERE {source_key} IN ({placeholders})"
            cursor = context.data_source.execute(total_sql, source_ids)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            sql = f"SELECT * FROM {tgt_table} WHERE {source_key} IN ({placeholders}) ORDER BY id LIMIT ? OFFSET ?"
            cursor = context.data_source.execute(sql, source_ids + [page_size, offset])
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            return ActionResult(success=True, data={'items': records, 'total': total, 'page': page, 'page_size': page_size, 'counts': counts})
        except Exception as e:
            logger.error(f"[AssociationEngine] batch_query_composition error: {e}")
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

    def _batch_query_reverse_m2m(self, context: ActionContext, assoc_meta: Dict, source_ids: List[int]) -> ActionResult:
        params = context.params
        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not through or not source_key or not target_key or not target_entity:
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

        target_meta = registry.get(target_entity)
        target_table = target_meta.table_name if target_meta else target_entity

        page = params.get('page', 1)
        page_size = params.get('page_size', 20)
        search = params.get('search')

        try:
            placeholders = ','.join(['?'] * len(source_ids))

            count_sql = f"SELECT {target_key}, COUNT(*) as cnt FROM {through} WHERE {target_key} IN ({placeholders}) GROUP BY {target_key}"
            cursor = context.data_source.execute(count_sql, source_ids)
            counts = {row[0]: row[1] for row in cursor.fetchall()}

            reverse_ids_sql = f"SELECT DISTINCT j.{source_key} FROM {through} j WHERE j.{target_key} IN ({placeholders})"
            cursor = context.data_source.execute(reverse_ids_sql, source_ids)
            reverse_ids = [row[0] for row in cursor.fetchall()]

            if not reverse_ids:
                return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': counts})

            rev_placeholders = ','.join(['?'] * len(reverse_ids))
            conditions = [f"t.id IN ({rev_placeholders})"]
            bind_params = list(reverse_ids)

            if search:
                search_fields = get_search_fields(target_meta)
                if search_fields:
                    or_clauses = [f"t.{f} LIKE ?" for f in search_fields]
                    conditions.append("(" + " OR ".join(or_clauses) + ")")
                    bind_params.extend([f"%{search}%"] * len(search_fields))

            where_clause = " AND ".join(conditions)

            count_total_sql = f"SELECT COUNT(*) FROM {target_table} t WHERE {where_clause}"
            cursor = context.data_source.execute(count_total_sql, bind_params)
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            sql = f"SELECT t.* FROM {target_table} t WHERE {where_clause} ORDER BY t.id LIMIT ? OFFSET ?"
            cursor = context.data_source.execute(sql, bind_params + [page_size, offset])
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            return ActionResult(success=True, data={'items': records, 'total': total, 'page': page, 'page_size': page_size, 'counts': counts})
        except Exception as e:
            logger.error(f"[AssociationEngine] batch_query_reverse_m2m error: {e}")
            return ActionResult(success=True, data={'items': [], 'total': 0, 'counts': {}})

    def _assign_reference(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')

        existence_error = validate_source_target_existence(
            self, context, src_id, tgt_type, tgt_id, assoc_meta)
        if existence_error:
            return existence_error

        cardinality_error = check_cardinality_constraint(self, context, src_id, assoc_meta)
        if cardinality_error:
            return cardinality_error

        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type

        if not source_key:
            source_key = f"{target_entity}_id"

        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type

        try:
            sql = f"UPDATE {src_table} SET {source_key} = ? WHERE id = ?"
            context.data_source.execute(sql, [tgt_id, src_id])
            return ActionResult(success=True, message="分配成功")
        except Exception as e:
            logger.error(f"[AssociationEngine] reference assign error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _unassign_reference(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')

        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type

        if not source_key:
            source_key = f"{target_entity}_id"

        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type

        fk_required_error = check_fk_required_before_unassign(
            context, src_meta, source_key
        )
        if fk_required_error:
            return fk_required_error

        try:
            sql = f"UPDATE {src_table} SET {source_key} = NULL WHERE id = ?"
            context.data_source.execute(sql, [src_id])
            return ActionResult(success=True, message="取消分配成功")
        except Exception as e:
            logger.error(f"[AssociationEngine] reference unassign error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _count_reference(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')

        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not source_key or not target_entity:
            return ActionResult(success=True, data={'count': 0})

        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type

        try:
            sql = f"SELECT COUNT(*) FROM {src_table} WHERE id = ? AND {source_key} IS NOT NULL"
            cursor = context.data_source.execute(sql, [src_id])
            count = cursor.fetchone()[0] if cursor.fetchone() else 0
            return ActionResult(success=True, data={'count': count})
        except Exception as e:
            logger.error(f"[AssociationEngine] reference count error: {e}")
            return ActionResult(success=True, data={'count': 0})

    def _assign_composition(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')

        existence_error = validate_source_target_existence(
            self, context, src_id, tgt_type, tgt_id, assoc_meta)
        if existence_error:
            return existence_error

        cardinality_error = check_cardinality_constraint(self, context, src_id, assoc_meta)
        if cardinality_error:
            return cardinality_error

        target_key = assoc_meta.get('target_key')
        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type

        if not source_key:
            source_key = f"{context.object_type}_id"

        tgt_meta = registry.get(target_entity)
        tgt_table = tgt_meta.table_name if tgt_meta else target_entity

        try:
            sql = f"UPDATE {tgt_table} SET {source_key} = ? WHERE id = ?"
            context.data_source.execute(sql, [src_id, tgt_id])
            return ActionResult(success=True, message="分配成功")
        except Exception as e:
            logger.error(f"[AssociationEngine] composition assign error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _count_composition(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')

        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not target_entity:
            return ActionResult(success=True, data={'count': 0})

        if not source_key:
            source_key = f"{context.object_type}_id"

        tgt_meta = registry.get(target_entity)
        tgt_table = tgt_meta.table_name if tgt_meta else target_entity

        try:
            sql = f"SELECT COUNT(*) FROM {tgt_table} WHERE {source_key} = ?"
            cursor = context.data_source.execute(sql, [src_id])
            count = cursor.fetchone()[0]
            return ActionResult(success=True, data={'count': count})
        except Exception as e:
            logger.error(f"[AssociationEngine] composition count error: {e}")
            return ActionResult(success=True, data={'count': 0})

    def _dissociate_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')

        if not through or not source_key or not target_key:
            return fallback_dissociate(self, context)

        sql = f"DELETE FROM {through} WHERE {source_key} = ? AND {target_key} = ?"

        try:
            context.data_source.execute(sql, [src_id, tgt_id])
            tgt_display = get_object_display(tgt_type, tgt_id, context.data_source)
            return ActionResult(
                success=True,
                message=f"成功取消关联 {tgt_type}:{tgt_display or tgt_id} 从 {context.object_type}:{src_id}",
            )
        except Exception as e:
            logger.error(f"[AssociationEngine] m2m dissociate error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _query_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        logger.debug(
            "_query_m2m params: through=%s src_key=%s tgt_key=%s tgt_entity=%s",
            through, source_key, target_key, target_entity
        )

        if not through or not source_key or not target_key or not target_entity:
            logger.warning("_query_m2m: missing required fields, returning empty data")
            return ActionResult(success=True, data=[])

        target_meta = registry.get(target_entity)
        target_table = target_meta.table_name if target_meta else target_entity

        page = params.get('page', 1)
        page_size = params.get('page_size', 50)

        # 构造过滤/排序/搜索的 SQL 片段
        extra_where_sql, extra_where_params, order_sql, order_params, search_sql, search_params = \
            _build_assoc_list_plan(target_meta, params, target_alias='t')

        logger.info(
            f"[AssociationEngine._query_m2m] src={context.object_type}:{src_id} "
            f"target={target_entity} through={through} "
            f"filters={params.get('filters')!r} ordering={params.get('ordering')!r} search={params.get('search')!r} "
            f"extra_where_sql={extra_where_sql!r} order_sql={order_sql!r}"
        )

        where_parts = [f"j.{source_key} = ?"]
        where_params: List[Any] = [src_id]
        if extra_where_sql:
            # 字段名限定到目标表 t（避免与中间表 j 的列冲突）
            aliased = re.sub(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', lambda m: f"t.{m.group(1)}" if m.group(1) not in ('t', 'j', 'OR', 'AND', 'NOT', 'LIKE', 'IN', 'NULL') else m.group(1), extra_where_sql)
            # 简单实现：把 `col op ?` 替换成 `t.col op ?`（不够稳健，回退到基础方案）
            # 由于 extra_where_sql 形如 "col LIKE ?" 这样的简单形式，逐段替换即可
            aliased = _alias_where_clause(extra_where_sql, 't')
            where_parts.append(f"({aliased})")
            where_params.extend(extra_where_params)
        if search_sql:
            aliased_search = _alias_where_clause(search_sql, 't')
            where_parts.append(f"({aliased_search})")
            where_params.extend(search_params)
        where_sql = " AND ".join(where_parts)

        count_sql = f"SELECT COUNT(*) FROM {target_table} t INNER JOIN {through} j ON t.id = j.{target_key} WHERE {where_sql}"
        cursor = context.data_source.execute(count_sql, list(where_params))
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        # 注意：j.* 与 t.* 在 id 列上冲突（target 的 id 被中间表的 id 覆盖），
        # 导致 record.get('id') 拿到的是中间表的 id，进而 enrich_association_counts
        # 计算 COUNT 时按错 id 查，结果全是 0。改为显式列出 j 的非冲突列。
        j_extra_cols = _through_non_id_columns(context, through, exclude_keys={target_key})
        j_select = ''.join(f', j.{c}' for c in j_extra_cols) if j_extra_cols else ''
        aliased_order = _alias_order_clause(order_sql, 't')
        sql = f"""SELECT t.*{j_select} FROM {target_table} t
                  INNER JOIN {through} j ON t.id = j.{target_key}
                  WHERE {where_sql}
                  {aliased_order}
                  LIMIT ? OFFSET ?"""
        query_params: List[Any] = list(where_params) + list(order_params) + [page_size, offset]
        logger.info(f"[AssociationEngine._query_m2m] SQL: {sql!r} params={query_params!r}")
        cursor = context.data_source.execute(sql, query_params)
        columns = [desc[0] for desc in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # 与 _do_list 保持一致：注入 FK display names + computed association counts
        if records and target_meta:
            # [SPR-01 S-01] 委托给 EnrichmentEngine（删除 v1 兼容 shim）
            engine = EnrichmentEngine.for_data_source(context.data_source)
            engine.enrich_fk_display_names(target_meta, records)
            engine.enrich_association_counts(target_meta, records)

        logger.debug("_query_m2m completed: total=%d fetched=%d", total, len(records))

        return ActionResult(success=True, data={'items': records, 'total': total, 'page': page, 'page_size': page_size})

    def _query_reverse_m2m(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        """
        查询 reverse_many_to_many 关联的目标对象

        reverse_many_to_many 关联表示：从源对象出发，查找通过中间表关联的目标对象
        例如：role.assigned_groups 表示"分配了此角色的用户组"

        关联配置：
        - through: 中间表名
        - source_key: 指向源对象的字段
        - target_key: 指向目标对象的字段

        查询逻辑：
        SELECT * FROM target_table WHERE id IN (SELECT target_key FROM through WHERE source_key = src_id)
        """
        params = context.params
        src_id = params.get('src_id')

        through = assoc_meta.get('through')
        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        logger.debug(
            "_query_reverse_m2m params: through=%s src_key=%s tgt_key=%s tgt_entity=%s src_id=%s",
            through, source_key, target_key, target_entity, src_id
        )

        if not through or not source_key or not target_key or not target_entity:
            logger.warning("_query_reverse_m2m: missing required fields, returning empty data")
            return ActionResult(success=True, data={'items': [], 'total': 0, 'page': 1, 'page_size': 50})

        target_meta = registry.get(target_entity)
        target_table = target_meta.table_name if target_meta else target_entity

        page = params.get('page', 1)
        page_size = params.get('page_size', 50)

        # 构造过滤/排序/搜索的 SQL 片段
        extra_where_sql, extra_where_params, order_sql, order_params, search_sql, search_params = \
            _build_assoc_list_plan(target_meta, params, target_alias='t')

        aliased_where = _alias_where_clause(extra_where_sql, 't') if extra_where_sql else ''
        aliased_search = _alias_where_clause(search_sql, 't') if search_sql else ''
        aliased_order = _alias_order_clause(order_sql, 't') if order_sql else ''

        where_parts = [f"t.id IN (SELECT j.{target_key} FROM {through} j WHERE j.{source_key} = ?)"]
        where_params: List[Any] = [src_id]
        if aliased_where:
            where_parts.append(f"({aliased_where})")
            where_params.extend(extra_where_params)
        if aliased_search:
            where_parts.append(f"({aliased_search})")
            where_params.extend(search_params)
        where_sql = " AND ".join(where_parts)

        count_sql = f"SELECT COUNT(*) FROM {target_table} t WHERE {where_sql}"
        cursor = context.data_source.execute(count_sql, list(where_params))
        total = cursor.fetchone()[0]

        # Query target objects
        offset = (page - 1) * page_size
        sql = f"""SELECT t.* FROM {target_table} t
                  WHERE {where_sql}
                  {aliased_order}
                  LIMIT ? OFFSET ?"""

        query_params: List[Any] = list(where_params) + list(order_params) + [page_size, offset]
        cursor = context.data_source.execute(sql, query_params)
        columns = [desc[0] for desc in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # 与 _do_list 保持一致：注入 FK display names + computed association counts
        if records and target_meta:
            # [SPR-01 S-01] 委托给 EnrichmentEngine（删除 v1 兼容 shim）
            engine = EnrichmentEngine.for_data_source(context.data_source)
            engine.enrich_fk_display_names(target_meta, records)
            engine.enrich_association_counts(target_meta, records)

        logger.debug("_query_reverse_m2m completed: total=%d fetched=%d", total, len(records))

        return ActionResult(success=True, data={'items': records, 'total': total, 'page': page, 'page_size': page_size})

    def _associate_reference(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')

        existence_error = validate_source_target_existence(
            self, context, src_id, tgt_type, tgt_id, assoc_meta)
        if existence_error:
            return existence_error

        cardinality_error = check_cardinality_constraint(self, context, src_id, assoc_meta)
        if cardinality_error:
            return cardinality_error

        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type

        if not source_key:
            source_key = f"{target_entity}_id"

        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type

        try:
            sql = f"UPDATE {src_table} SET {source_key} = ? WHERE id = ?"
            context.data_source.execute(sql, [tgt_id, src_id])
            tgt_display = get_object_display(target_entity, tgt_id, context.data_source)
            return ActionResult(
                success=True,
                message=f"成功设置 {context.object_type}:{src_id} 的 {source_key} 为 {target_entity}:{tgt_display or tgt_id}",
            )
        except Exception as e:
            logger.error(f"[AssociationEngine] reference associate error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _dissociate_reference(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')

        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type

        if not source_key:
            source_key = f"{target_entity}_id"

        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type

        fk_required_error = check_fk_required_before_unassign(
            context, src_meta, source_key
        )
        if fk_required_error:
            return fk_required_error

        try:
            sql = f"UPDATE {src_table} SET {source_key} = NULL WHERE id = ?"
            context.data_source.execute(sql, [src_id])
            return ActionResult(
                success=True,
                message=f"成功清除 {context.object_type}:{src_id} 的 {source_key} 引用",
            )
        except Exception as e:
            logger.error(f"[AssociationEngine] reference dissociate error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _query_reference(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')

        source_key = assoc_meta.get('source_key')
        target_key = assoc_meta.get('target_key', 'id')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not source_key or not target_entity:
            return ActionResult(success=True, data={'items': [], 'total': 0})

        src_meta = registry.get(context.object_type)
        src_table = src_meta.table_name if src_meta else context.object_type

        target_meta = registry.get(target_entity)
        target_table = target_meta.table_name if target_meta else target_entity

        try:
            ref_sql = f"SELECT {source_key} FROM {src_table} WHERE id = ?"
            cursor = context.data_source.execute(ref_sql, [src_id])
            row = cursor.fetchone()
            if not row:
                return ActionResult(success=True, data={'items': [], 'total': 0})

            ref_id = row[0]
            if ref_id is None:
                return ActionResult(success=True, data={'items': [], 'total': 0})

            # reference 关联本质上是一对一/反向一对多，先按 ref_id 拉全量再应用过滤/排序/搜索
            base_sql = f"SELECT * FROM {target_table} WHERE {target_key} = ?"
            cursor = context.data_source.execute(base_sql, [ref_id])
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # 应用前端过滤 / 排序 / 搜索（在内存层处理，量小；走 _build_assoc_filter_plan 共享逻辑）
            records, total = _apply_assoc_list_post_filter(
                records, target_meta, params
            )

            # 与 _do_list 保持一致：注入 FK display names + computed association counts
            if records and target_meta:
                # [SPR-01 S-01] 委托给 EnrichmentEngine（删除 v1 兼容 shim）
                engine = EnrichmentEngine.for_data_source(context.data_source)
                engine.enrich_fk_display_names(target_meta, records)
                engine.enrich_association_counts(target_meta, records)

            return ActionResult(success=True, data={'items': records, 'total': total})
        except Exception as e:
            logger.error(f"[AssociationEngine] reference query error: {e}")
            return ActionResult(success=True, data={'items': [], 'total': 0})

    def _associate_composition(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')

        existence_error = validate_source_target_existence(
            self, context, src_id, tgt_type, tgt_id, assoc_meta)
        if existence_error:
            return existence_error

        cardinality_error = check_cardinality_constraint(self, context, src_id, assoc_meta)
        if cardinality_error:
            return cardinality_error

        target_key = assoc_meta.get('target_key')
        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type') or tgt_type

        if not source_key:
            source_key = f"{context.object_type}_id"

        tgt_meta = registry.get(target_entity)
        tgt_table = tgt_meta.table_name if tgt_meta else target_entity

        try:
            sql = f"UPDATE {tgt_table} SET {source_key} = ? WHERE id = ?"
            context.data_source.execute(sql, [src_id, tgt_id])
            tgt_display = get_object_display(target_entity, tgt_id, context.data_source)
            return ActionResult(
                success=True,
                message=f"成功将 {target_entity}:{tgt_display or tgt_id} 添加到 {context.object_type}:{src_id}",
            )
        except Exception as e:
            logger.error(f"[AssociationEngine] composition associate error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _query_composition(self, context: ActionContext, assoc_meta: Dict) -> ActionResult:
        params = context.params
        src_id = params.get('src_id')

        source_key = assoc_meta.get('source_key')
        target_entity = assoc_meta.get('target_entity') or assoc_meta.get('target_type')

        if not target_entity:
            return ActionResult(success=True, data={'items': [], 'total': 0})

        if not source_key:
            source_key = f"{context.object_type}_id"

        tgt_meta = registry.get(target_entity)
        tgt_table = tgt_meta.table_name if tgt_meta else target_entity

        page = params.get('page', 1)
        page_size = params.get('page_size', 50)

        try:
            # 构造过滤/排序/搜索的 SQL 片段（与 _do_list 风格一致）。
            # 过滤支持：field=value、field__in=..、field__like=..、field__gte/field__lte、
            #           field_start/field_end（日期区间）。sort 支持 -field / field。
            extra_where_sql, extra_where_params, order_sql, order_params, search_sql, search_params = \
                _build_assoc_list_plan(tgt_meta, params)

            logger.info(
                f"[AssociationEngine._query_composition] src={context.object_type}:{src_id} "
                f"target={target_entity} source_key={source_key} "
                f"filters={params.get('filters')!r} ordering={params.get('ordering')!r} search={params.get('search')!r} "
                f"extra_where_sql={extra_where_sql!r} order_sql={order_sql!r}"
            )

            where_parts = [f"{source_key} = ?"]
            where_params: List[Any] = [src_id]
            if extra_where_sql:
                where_parts.append(extra_where_sql)
                where_params.extend(extra_where_params)
            if search_sql:
                where_parts.append(search_sql)
                where_params.extend(search_params)
            where_sql = " AND ".join(where_parts)

            count_sql = f"SELECT COUNT(*) FROM {tgt_table} WHERE {where_sql}"
            cursor = context.data_source.execute(count_sql, list(where_params))
            total = cursor.fetchone()[0]

            offset = (page - 1) * page_size
            # 安全保护：排序段必须经过白名单校验（_build_assoc_list_plan 已做）
            sql = (
                f"SELECT * FROM {tgt_table} WHERE {where_sql} "
                f"{order_sql} LIMIT ? OFFSET ?"
            )
            query_params: List[Any] = list(where_params) + list(order_params) + [page_size, offset]
            logger.info(f"[AssociationEngine._query_composition] SQL: {sql!r} params={query_params!r}")
            cursor = context.data_source.execute(sql, query_params)
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # 与 _do_list 保持一致：注入 FK display names + computed association counts
            if records and tgt_meta:
                # [SPR-01 S-01] 委托给 EnrichmentEngine（删除 v1 兼容 shim）
                engine = EnrichmentEngine.for_data_source(context.data_source)
                engine.enrich_fk_display_names(tgt_meta, records)
                engine.enrich_association_counts(tgt_meta, records)

            return ActionResult(success=True, data={'items': records, 'total': total, 'page': page, 'page_size': page_size})
        except Exception as e:
            logger.error(f"[AssociationEngine] composition query error: {e}")
            return ActionResult(success=True, data={'items': [], 'total': 0})
