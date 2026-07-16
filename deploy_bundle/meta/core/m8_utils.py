# -*- coding: utf-8 -*-
"""
M8 工具函数（QE-M8-2026-06-v2）

[M8 2026-06-06] 消费侧能力公共工具。

包含：
- VP-6 Custom Order 解析（FIELD()）
- VP-5 ETag 计算
- VP-1 ValueHelp URL 解析辅助
- VP-4 Reverse Expand 元数据查找
"""
from __future__ import annotations
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# VP-6 Custom Order
# ============================================================
def parse_custom_order(
    ordering: str,
    pk_field: str = 'id',
) -> Optional[Tuple[str, List]]:
    """解析 custom:N,M,K 形式的 ordering → FIELD() SQL。

    Returns:
        None 表示非 custom 模式（走默认 asc/desc 解析）
        (raw_sql, params) 表示 custom 模式
    """
    if not ordering:
        return None
    ordering = ordering.strip()
    if not ordering.startswith('custom:'):
        return None
    ids_str = ordering[len('custom:'):]
    ids: List[int] = []
    for x in ids_str.split(','):
        x = x.strip()
        if not x:
            continue
        try:
            ids.append(int(x))
        except ValueError:
            raise ValueError(
                f'custom order requires int IDs, got {x!r}'
            )
    if not ids:
        raise ValueError('custom order requires at least 1 ID')
    placeholders = ','.join('?' * len(ids))
    return f'FIELD({pk_field}, {placeholders})', ids


def parse_ordering(
    ordering: str,
    pk_field: str = 'id',
) -> Tuple[str, List]:
    """解析普通 ordering → (raw_sql, params)。

    支持：
    - '' → ORDER BY pk ASC
    - 'id' → ORDER BY id ASC
    - '-id' → ORDER BY id DESC
    - 'id,-name' → ORDER BY id ASC, name DESC
    - 'custom:1,3,2' → ORDER BY FIELD(id, 1, 3, 2)
    """
    if not ordering:
        return f'ORDER BY {pk_field} ASC', []
    # custom: 模式
    custom = parse_custom_order(ordering, pk_field)
    if custom is not None:
        return custom
    # 普通模式
    clauses: List[str] = []
    for p in ordering.split(','):
        p = p.strip()
        if not p:
            continue
        if p.startswith('-'):
            clauses.append(f'{p[1:]} DESC')
        else:
            clauses.append(f'{p} ASC')
    if not clauses:
        return f'ORDER BY {pk_field} ASC', []
    return f"ORDER BY {', '.join(clauses)}", []


# ============================================================
# VP-5 ETag
# ============================================================
def compute_etag(data: Any) -> str:
    """计算响应的 ETag（基于 JSON 内容）。"""
    content = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def check_etag_match(etag: str, request_headers: Dict) -> bool:
    """检查 If-None-Match header 与 ETag 是否匹配。

    Returns:
        True 表示客户端缓存有效（应返回 304）
    """
    if_none_match = request_headers.get('If-None-Match', '').strip().strip('"')
    if not if_none_match:
        return False
    # 支持 * 表示任意 ETag 都匹配
    if if_none_match == '*':
        return True
    return if_none_match == etag


# ============================================================
# VP-1 ValueHelp URL 解析辅助
# ============================================================
def parse_valuehelp_args(args: Dict) -> Dict:
    """解析 valuehelp URL 参数。

    Returns:
        {
            'q': str,
            'top': int,
            'display_fields': List[str],
            'locale': str,
            'ordering': str,
            'extra_filters': Dict[str, Any],
        }
    """
    q = (args.get('q') or args.get('search') or '').strip()
    try:
        top = min(int(args.get('top') or args.get('pageSize') or 20), 100)
    except (TypeError, ValueError):
        top = 20
    display = args.get('display') or args.get('display_fields') or ''
    display_fields = [f.strip() for f in display.split(',') if f.strip()]
    locale = args.get('locale', 'zh-CN')
    ordering = args.get('order_by') or args.get('ordering') or ''

    # 收集 filter[k__op]=v
    extra_filters: Dict[str, Any] = {}
    for k, v in args.items():
        if k.startswith('filter[') and k.endswith(']'):
            field = k[len('filter['):-1]
            extra_filters[field] = v

    return {
        'q': q,
        'top': top,
        'display_fields': display_fields,
        'locale': locale,
        'ordering': ordering,
        'extra_filters': extra_filters,
    }


# ============================================================
# VP-4 Reverse Expand 元数据查找
# ============================================================
def find_reverse_association(
    entity_meta: Any,
    assoc_name: str,
) -> Optional[Dict[str, str]]:
    """在 entity 的元数据中查找反向关联定义。

    Returns:
        {
            'target_entity': str,
            'source_key': str,  # 在目标实体上的外键字段
            'type': 'reverse_many_to_many' / 'one_to_many',
        }
    """
    if entity_meta is None:
        return None
    assocs = getattr(entity_meta, 'associations', None) or []
    for a in assocs:
        a_name = getattr(a, 'name', '') or ''
        if a_name != assoc_name:
            continue
        a_type = getattr(a, 'type', '')
        if a_type in ('reverse_many_to_many', 'one_to_many', 'many_to_many'):
            return {
                'target_entity': (
                    getattr(a, 'target_entity', '')
                    or getattr(a, 'target_table', '')
                    or assoc_name
                ),
                'source_key': (
                    getattr(a, 'source_key', None)
                    or f'{getattr(entity_meta, "object_type", assoc_name)}_id'
                ),
                'type': a_type,
                'through': getattr(a, 'through', None),
                'join_key': getattr(a, 'join_key', None),
            }
    return None
