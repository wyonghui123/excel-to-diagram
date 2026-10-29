# -*- coding: utf-8 -*-
"""文档版本服务（M2）

职责（spec §4）：
  · record(...)           —— 版本数据的**唯一写入口**（快照 + 字段级差异）
  · diff(...)             —— 两个版本之间的结构化差异
  · restore_payload(...)  —— 由快照还原「内容字段」（永不还原 status / 履约派生字段）
  · update_with_revision(...) —— FR-010 的 M2 等价实现：UPDATE ... WHERE id=? AND revision_no=?

约束：
  · 不写目标对象表（目标表仍由 ActionExecutor._do_update 写，见 spec D3）
  · 版本表 append-only：本模块不提供 update / delete
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

REVISIONS_TABLE = 'document_revisions'
CHANGES_TABLE = 'document_revision_changes'

# FR-012：这些字段的变更不产生版本（状态推进 / 履约派生回写）
# updated_by 由 action_executor._prepare_data 的 auto_fill.on_update 回写（无用户上下文时为 ''），
# 属审计元数据而非单据内容；若不剔除，纯状态更新会被误判为内容变更而空推进 revision_no。
NON_CONTENT_FIELDS = frozenset({
    'status',
    'fulfillment_status',
    'fulfillment_derived_at',
    'updated_by',
})

_TABLE_NAMES_REGISTERED = False


def ensure_table_names_registered() -> None:
    """把两张版本表登记进表名安全白名单（table_name_validator）。

    版本表由 v149 迁移建表，不是 YAML BO（不进 registry），默认不在白名单内；
    不登记则 SQLiteAdapter 的 validate_table_name 会在真机读写路径拒绝
    （`Invalid table name: 'document_revisions'`）。单元测试手动
    register_table_name 才通过，故真机必须在此显式登记。
    """
    global _TABLE_NAMES_REGISTERED
    if _TABLE_NAMES_REGISTERED:
        return
    from meta.core.table_name_validator import register_table_name
    register_table_name(REVISIONS_TABLE)
    register_table_name(CHANGES_TABLE)
    _TABLE_NAMES_REGISTERED = True


class RevisionError(Exception):
    """带业务错误码的版本异常（API 层据此映射 HTTP 状态码）"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _as_text(value: Any) -> Optional[str]:
    """统一转 str；None 保持 NULL（便于 SQL 对比）"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def diff_fields(meta_object) -> Set[str]:
    """revision_policy.fields[] 中 diff: true 的字段集合"""
    policy = getattr(meta_object, 'revision_policy', None)
    if policy is None:
        return set()
    return {f.field for f in policy.fields if f.field and f.diff}


def content_changed(changed_fields: Iterable[str]) -> Set[str]:
    """剔除「不产生版本」的字段（FR-012）"""
    return {f for f in (changed_fields or ()) if f not in NON_CONTENT_FIELDS}


def _user_ref(user: Any) -> Optional[str]:
    if not user:
        return None
    if isinstance(user, dict):
        return (user.get('username') or user.get('display_name')
                or user.get('user_id') or user.get('id'))
    return str(user)


def collect_snapshot(ds, meta_object, object_id: Any) -> Dict[str, Any]:
    """整单快照：抬头 + 全部子行（按「子对象 relations 指向本对象」自动发现）"""
    header = ds.find_by_id(meta_object.table_name, object_id) or {}
    lines: Dict[str, List[Dict[str, Any]]] = {}
    try:
        from meta.core.models import registry
        candidates = registry.all()
    except Exception:
        candidates = []

    for child in candidates:
        if child.id == meta_object.id:
            continue
        for rel in getattr(child, 'relations', None) or []:
            if getattr(rel, 'target_object', None) != meta_object.id:
                continue
            source_field = getattr(rel, 'source_field', '') or ''
            if not source_field:
                continue
            try:
                rows = ds.find(child.table_name, {source_field: object_id})
            except Exception:
                rows = []
            if rows:
                lines[child.id] = rows
            break

    return {'header': header, 'lines': lines}


def record(
    ds,
    meta_object,
    object_id: Any,
    before: Dict[str, Any],
    after: Dict[str, Any],
    changed_fields: Iterable[str],
    revision_no: int,
    reason_code: Optional[str] = None,
    change_set_id: Optional[str] = None,
    user: Any = None,
    snapshot: Optional[Dict[str, Any]] = None,
) -> int:
    """写入一个版本 + 该版本的字段级差异行，返回 revision_no。

    调用方负责把目标行的 revision_no 推进到 `revision_no`（同一事务内）。
    """
    policy = getattr(meta_object, 'revision_policy', None)
    if policy is None or not policy.enabled:
        return revision_no

    ensure_table_names_registered()
    payload = snapshot if snapshot is not None else collect_snapshot(
        ds, meta_object, object_id)

    revision_id = ds.insert(REVISIONS_TABLE, {
        'object_type': meta_object.id,
        'object_id': str(object_id),
        'revision_no': int(revision_no),
        'snapshot': json.dumps(payload, ensure_ascii=False),
        'change_request_id': None,
        'reason_code': reason_code,
        'change_set_id': change_set_id,
        'created_by': _user_ref(user),
        'created_at': _now(),
    })

    wanted = diff_fields(meta_object) & set(changed_fields or ())
    for field_name in sorted(wanted):
        ds.insert(CHANGES_TABLE, {
            'revision_id': revision_id,
            'line_key': None,
            'field_name': field_name,
            'old_value': _as_text((before or {}).get(field_name)),
            'new_value': _as_text((after or {}).get(field_name)),
        })

    return int(revision_no)


def list_revisions(ds, object_type: str, object_id: Any) -> List[Dict[str, Any]]:
    """按 revision_no 升序列出版本（IF-001）"""
    ensure_table_names_registered()
    rows = ds.find(
        REVISIONS_TABLE,
        {'object_type': object_type, 'object_id': str(object_id)},
        order_by='revision_no ASC',
    ) or []
    result = []
    for row in rows:
        rev_id = row.get('id')
        changes = ds.find(CHANGES_TABLE, {'revision_id': rev_id}) or []
        result.append({
            'revision_no': row.get('revision_no'),
            'created_at': row.get('created_at'),
            'created_by': row.get('created_by'),
            'reason_code': row.get('reason_code'),
            'change_set_id': row.get('change_set_id'),
            'summary': '%d 个字段变更' % len(changes),
        })
    return result


def _find_revision(ds, object_type: str, object_id: Any,
                   revision_no: int) -> Optional[Dict[str, Any]]:
    ensure_table_names_registered()
    rows = ds.find(REVISIONS_TABLE, {
        'object_type': object_type,
        'object_id': str(object_id),
        'revision_no': revision_no,
    }) or []
    return rows[0] if rows else None


def diff(ds, object_type: str, object_id: Any,
         rev_a: int, rev_b: int) -> Dict[str, List[Dict[str, Any]]]:
    """两个版本的结构化差异（IF-002）。

    a == b → 空差异；任一侧不存在 → RevisionError(REVISION_NOT_FOUND)
    """
    empty = {'header': [], 'lines': []}
    if rev_a == rev_b:
        row = _find_revision(ds, object_type, object_id, rev_a)
        if row is None:
            raise RevisionError('REVISION_NOT_FOUND',
                                '版本 %s 不存在' % rev_a)
        return empty

    row_a = _find_revision(ds, object_type, object_id, rev_a)
    row_b = _find_revision(ds, object_type, object_id, rev_b)
    for rev_no, row in ((rev_a, row_a), (rev_b, row_b)):
        if row is None:
            raise RevisionError('REVISION_NOT_FOUND',
                                '版本 %s 不存在' % rev_no)

    changes = {
        rev_a: ds.find(CHANGES_TABLE, {'revision_id': row_a['id']}) or [],
        rev_b: ds.find(CHANGES_TABLE, {'revision_id': row_b['id']}) or [],
    }

    def _index(rows):
        index = {}
        for r in rows:
            index[(r.get('line_key'), r.get('field_name'))] = r
        return index

    idx_a, idx_b = _index(changes[rev_a]), _index(changes[rev_b])

    header, lines = [], []
    for key in sorted(set(idx_a) | set(idx_b), key=lambda k: (str(k[0]), str(k[1]))):
        old = idx_b.get(key)
        new = idx_a.get(key)
        line_key, field_name = key
        item = {
            'field_name': field_name,
            'old_value': (old or {}).get('new_value'),
            'new_value': (new or {}).get('new_value'),
        }
        if line_key in (None, ''):
            header.append(item)
        else:
            item['line_key'] = line_key
            lines.append(item)

    return {'header': header, 'lines': lines}


def restore_payload(snapshot, diff_field_names: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """由快照还原「内容字段」：永不还原 status / 履约派生字段（spec §4.3）"""
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            return {}
    if not isinstance(snapshot, dict):
        return {}

    header = snapshot.get('header') or {}
    if not isinstance(header, dict):
        return {}
    if diff_field_names is not None:
        allowed = set(diff_field_names)
        header = {k: v for k, v in header.items() if k in allowed}

    return {k: v for k, v in header.items() if k not in NON_CONTENT_FIELDS}


def update_with_revision(ds, table_name: str, id_value: Any,
                         data: Dict[str, Any], expected_revision: int) -> bool:
    """FR-010 的 M2 等价实现：`UPDATE ... WHERE id = ? AND revision_no = ?`

    返回 True = 命中；False = 版本已变（调用方抛 REVISION_CONFLICT）。
    """
    if not data:
        return False
    try:
        placeholder = ds._placeholder()
    except Exception:
        placeholder = '?'

    set_clause = ", ".join(
        f'{k} = {placeholder}' for k in data.keys()
    )
    sql = (f'UPDATE {table_name} SET {set_clause} '
           f'WHERE id = {placeholder} AND revision_no = {placeholder}')
    params = list(data.values()) + [id_value, expected_revision]
    cursor = ds.execute(sql, tuple(params))
    return (getattr(cursor, 'rowcount', 0) or 0) > 0
