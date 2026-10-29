# -*- coding: utf-8 -*-
"""文档版本服务（M2）

职责（spec §4）：
  · record(...)           —— 版本数据的**唯一写入口**（快照 + 字段级差异）
  · diff(...)             —— 两个版本之间的结构化差异
  · restore_payload(...)  —— 由快照还原「内容字段」（永不还原 status / 履约派生字段）
  · update_with_revision(...) —— FR-010 的 M2 等价实现：UPDATE ... WHERE id=? AND revision_no=?
  · apply(...)            —— M3 变更申请生效编排（只编排，目标表仍经 ActionExecutor 写）

约束：
  · 不写目标对象表（目标表仍由 ActionExecutor._do_update 写，见 spec D3）
  · 版本表 append-only：本模块不提供 update / delete
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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


@dataclass
class RevisionOwner:
    """行写路径的版本归属（M4）：版本挂父单据，行信息只落 line_key"""
    object_type: str = ""            # 父对象 id（版本归属）
    object_id: Any = None            # 父单据主键
    object: Any = None               # 父 MetaObject（取表名 / 快照用）
    policy: Any = None               # 父 revision_policy
    line_key: Any = None             # 子对象时 = 行主键
    line_object: str = ""            # 子对象 id
    editable: List[str] = field(default_factory=list)
    via_change_request: List[str] = field(default_factory=list)
    gate_record: Dict[str, Any] = field(default_factory=dict)

    @property
    def line_fields(self) -> Dict[str, List[str]]:
        return {
            'editable': list(self.editable),
            'via_change_request': list(self.via_change_request),
        }


def resolve_owner(ds, metas, object_type: str,
                  record: Dict[str, Any]) -> Optional[RevisionOwner]:
    """行写路径的父析取（spec §4）。

    遍历所有声明了 `revision_policy.lines` 且 `child_object == object_type`
    的对象，按 `parent_field` 取父 id → 读父行 → 按 `line_type_field` 分档。
    未命中（无父策略 / 父 id 为空 / 父行不存在）返回 None（行为不变）。
    """
    if not record:
        return None
    candidates = metas.values() if isinstance(metas, dict) else (metas or [])
    for parent in candidates:
        policy = getattr(parent, 'revision_policy', None)
        lines = getattr(policy, 'lines', None) if policy else None
        if lines is None or not getattr(policy, 'enabled', False):
            continue
        if lines.child_object != object_type:
            continue
        parent_id = record.get(lines.parent_field)
        if parent_id in (None, ''):
            return None
        try:
            gate_record = ds.find_by_id(parent.table_name, parent_id)
        except Exception:  # noqa: BLE001 - 表不存在按无归属处理
            gate_record = None
        if not gate_record:
            return None
        tier = lines.policy_for(record)
        return RevisionOwner(
            object_type=parent.id,
            object_id=parent_id,
            object=parent,
            policy=policy,
            line_key=record.get('id'),
            line_object=object_type,
            editable=list(tier.editable or []),
            via_change_request=list(tier.via_change_request or []),
            gate_record=gate_record,
        )
    return None


def find_revision_by_change_set(ds, object_type: str, object_id: Any,
                                change_set_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """同一 change_set 内已写的版本行（M4 合并单版本用）"""
    if not change_set_id:
        return None
    ensure_table_names_registered()
    rows = ds.find(REVISIONS_TABLE, {
        'object_type': object_type,
        'object_id': str(object_id),
        'change_set_id': change_set_id,
    }) or []
    return rows[0] if rows else None


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
    change_request_id: Optional[int] = None,
    owner_object_type: Optional[str] = None,
    owner_object_id: Any = None,
    line_key: Any = None,
) -> int:
    """写入一个版本 + 该版本的字段级差异行，返回 revision_no。

    调用方负责把目标行的 revision_no 推进到 `revision_no`（同一事务内）。

    [M4] owner_* 参数用于行写路径：版本行归属父单据（`document_revisions`），
    行差异以 `line_key` 区分（头字段 `line_key = NULL`）。默认 None ⇒ 行为不变。
    同一 `change_set_id` 内已存在版本行时，**不新建版本**，只追加差异并把快照
    刷新为最新状态（父单据 `revision_no` 只 +1，见 spec §4）。
    """
    policy = getattr(meta_object, 'revision_policy', None)
    if (policy is None or not policy.enabled) and owner_object_type is None:
        return revision_no

    ensure_table_names_registered()
    object_type = owner_object_type or meta_object.id
    object_id_value = owner_object_id if owner_object_type else object_id
    payload = snapshot if snapshot is not None else collect_snapshot(
        ds, meta_object, object_id)

    existing = find_revision_by_change_set(
        ds, object_type, object_id_value, change_set_id)
    if existing is not None:
        revision_id = existing['id']
        revision_no = existing.get('revision_no') or revision_no
        try:
            ds.update(REVISIONS_TABLE, revision_id, {
                'snapshot': json.dumps(payload, ensure_ascii=False),
            })
        except Exception:  # noqa: BLE001 - 同一版本的快照刷新失败不影响差异入库
            pass
    else:
        revision_id = ds.insert(REVISIONS_TABLE, {
            'object_type': object_type,
            'object_id': str(object_id_value),
            'revision_no': int(revision_no),
            'snapshot': json.dumps(payload, ensure_ascii=False),
            'change_request_id': change_request_id,
            'reason_code': reason_code,
            'change_set_id': change_set_id,
            'created_by': _user_ref(user),
            'created_at': _now(),
        })

    if line_key is not None:
        # 行写路径：差异字段来自行对象自身（父 policy.fields 不含行字段）；
        # 行主键本身不是内容变更，必须剔除（payload 里 id 常以字符串回传）
        wanted = set(content_changed(changed_fields)) - {'id'}
    else:
        wanted = diff_fields(meta_object) & set(changed_fields or ())
    for field_name in sorted(wanted):
        ds.insert(CHANGES_TABLE, {
            'revision_id': revision_id,
            'line_key': None if line_key is None else str(line_key),
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


def _mark_change_request_failed(ds, cr_row: Dict[str, Any], reason: str) -> None:
    """把变更申请落 `failed`（best-effort，不改目标表）。

    优先走 `change_request_service.transition`（校验 approved → failed 合法边）；
    任何异常再退化为直接 `UPDATE`，保证「生效失败」这件事本身不被静默丢掉。
    """
    cr_id = (cr_row or {}).get('id')
    if cr_id is None:
        return
    reason = (reason or '')[:200]
    try:
        from meta.services.change_request_service import CR_TABLE, transition
        transition(ds, cr_row, 'failed', '', {'fail_reason': reason})
        return
    except Exception:  # noqa: BLE001 - 兜底落库，避免失败态丢失
        pass
    try:
        from meta.services.change_request_service import CR_TABLE
        ds.update(CR_TABLE, cr_id, {'status': 'failed', 'fail_reason': reason})
    except Exception:  # noqa: BLE001
        pass


def apply(ds, cr_row: Dict[str, Any], *, actor: str = '') -> Dict[str, Any]:
    """[M3 T5] 变更申请生效编排（只编排，不写目标表）。

    步骤（docs/superpowers/specs/2026-10-29-m3-change-request/spec.md §6.1）：
      ① 幂等短路：`status == 'applied'` 且 `applied_revision_no` 非空 → 返回首次回执；
      ② 状态守卫：`status != 'approved'` → CHANGE_REQUEST_NOT_APPROVED(409)；
      ③ 行 → payload：`line_key` 为空 = 头字段，非空 = 目标行字段；
      ④ 乐观锁预检：目标当前 `revision_no` != `target_revision_no` → 落 failed + 409；
      ⑤ 调用漏斗：`ActionExecutor.update_via_change_request`（D5 唯一写路径）；
      ⑥ 回写申请：`applied` / `applied_at` / `applied_revision_no` / `change_set_id`；
      ⑦ 返回回执 `{'status','revision_no','applied_at'}`。

    约束：本函数**不写目标对象表**（目标表只经 ActionExecutor 漏斗写，见 spec D5）。
    """
    from meta.core.models import registry
    from meta.services.change_request_service import (
        CRL_TABLE,
        ChangeRequestError,
        _ensure_tables,
        transition,
    )

    if not cr_row or cr_row.get('id') is None:
        raise ChangeRequestError('CHANGE_REQUEST_NOT_FOUND', '变更申请不存在', 404)

    # ① 幂等短路：已生效且回执版本存在 → 不再写任何版本
    if cr_row.get('status') == 'applied' \
            and cr_row.get('applied_revision_no') not in (None, ''):
        try:
            revision_no = int(cr_row['applied_revision_no'])
        except (TypeError, ValueError):
            revision_no = cr_row['applied_revision_no']
        return {
            'status': 'applied',
            'revision_no': revision_no,
            'applied_at': cr_row.get('applied_at'),
        }

    # ② 状态守卫：只有 approved 才能生效
    if cr_row.get('status') != 'approved':
        raise ChangeRequestError(
            'CHANGE_REQUEST_NOT_APPROVED',
            '变更申请未审批通过（当前状态 %s），不能生效' % (cr_row.get('status') or '(空)'),
            409,
        )

    _ensure_tables(ds)

    target_type = (cr_row.get('target_object_type') or '').strip()
    target_id = cr_row.get('target_object_id')
    target_revision_no = cr_row.get('target_revision_no')

    meta_object = registry.get(target_type) if target_type else None
    if meta_object is None:
        reason = '目标对象不存在: %s' % (target_type or '(空)')
        _mark_change_request_failed(ds, cr_row, reason)
        raise ChangeRequestError('INVALID_TARGET_OBJECT', reason, 400)

    # ③ 行 → payload（头字段 / 行字段两段式，禁止 JSON blob）
    rows = ds.find(CRL_TABLE, {'change_request_id': cr_row['id']}) or []
    header_payload: Dict[str, Any] = {}
    line_payloads: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        field_name = (row.get('field_name') or '').strip()
        if not field_name:
            continue
        line_key = row.get('line_key')
        if line_key in (None, ''):
            header_payload[field_name] = row.get('new_value')
        else:
            line_payloads.setdefault(str(line_key), {})[field_name] = row.get('new_value')

    if not header_payload and not line_payloads:
        reason = '变更申请没有可生效的变更明细'
        _mark_change_request_failed(ds, cr_row, reason)
        raise ChangeRequestError('INVALID_CHANGE_REQUEST', reason, 400)

    # ④ 乐观锁预检：目标版本必须仍是提交时冻结的版本（不写任何版本）
    try:
        target_row = ds.find_by_id(meta_object.table_name, target_id)
    except Exception:  # noqa: BLE001 - 表不存在 / 目标非法
        target_row = None
    if not target_row:
        reason = '目标单据不存在: %s#%s' % (meta_object.id, target_id)
        _mark_change_request_failed(ds, cr_row, reason)
        raise ChangeRequestError('TARGET_NOT_FOUND', reason, 400)

    if target_row.get('revision_no') != target_revision_no:
        reason = '目标已被他人修改，请重新提交申请'
        _mark_change_request_failed(ds, cr_row, reason)
        raise ChangeRequestError('REVISION_CONFLICT', reason, 409)

    from meta.core.action_executor import ActionExecutor

    # 行主键存在性预检：line_key 必须能定位到目标行（缺失 → INVALID_LINE_KEY）
    if line_payloads:
        line_object = None
        try:
            line_object = ActionExecutor._resolve_line_object(target_type)
        except Exception:  # noqa: BLE001
            line_object = None
        if line_object is not None:
            for line_id in sorted(line_payloads, key=str):
                try:
                    exists = ds.find_by_id(line_object.table_name, line_id)
                except Exception:  # noqa: BLE001
                    exists = None
                if not exists:
                    reason = '变更行主键不存在: %s#%s' % (line_object.id, line_id)
                    _mark_change_request_failed(ds, cr_row, reason)
                    raise ChangeRequestError('INVALID_LINE_KEY', reason, 400)

    # ⑤ 调用漏斗（RevisionGuard → 乐观锁 → 版本 → 审计，全部在 _do_update 内）
    payload: Dict[str, Any] = {'header': header_payload, 'lines': line_payloads} \
        if line_payloads else dict(header_payload)
    try:
        result = ActionExecutor(ds).update_via_change_request(
            target_type,
            target_id,
            payload,
            expected_revision=target_revision_no,
            change_request_id=cr_row['id'],
            reason_code=cr_row.get('reason_code'),
            change_set_id=cr_row.get('change_set_id'),
            user=actor,
        )
    except Exception as e:  # noqa: BLE001 - 漏斗意外异常按生效失败处理
        reason = '变更生效异常: %s' % e
        _mark_change_request_failed(ds, cr_row, reason)
        raise ChangeRequestError('APPLY_FAILED', reason, 400)

    if not getattr(result, 'success', False):
        code = getattr(result, 'error', '') or 'APPLY_FAILED'
        message = getattr(result, 'message', '') or '变更生效失败'
        if code in ('REVISION_CONFLICT', 'CONCURRENT_MODIFICATION'):
            reason = '目标已被他人修改，请重新提交申请'
            _mark_change_request_failed(ds, cr_row, reason)
            raise ChangeRequestError('REVISION_CONFLICT', reason, 409)
        if str(code).startswith('REVISION_'):
            _mark_change_request_failed(ds, cr_row, message)
            raise ChangeRequestError('REVISION_NOT_ALLOWED', message, 409)
        if code in ('LINE_NOT_FOUND', 'INVALID_LINE_KEY'):
            reason = message or '变更行不存在'
            _mark_change_request_failed(ds, cr_row, reason)
            raise ChangeRequestError('INVALID_LINE_KEY', reason, 400)
        _mark_change_request_failed(ds, cr_row, message)
        raise ChangeRequestError(
            str(code), message,
            getattr(result, 'status_code', None) or 400,
        )

    # ⑥ 回写申请：新版本号取漏斗落库后的目标行 revision_no
    data = getattr(result, 'data', None) or {}
    new_revision_no = data.get('revision_no') if isinstance(data, dict) else None
    if new_revision_no is None:
        new_revision_no = int(target_revision_no or 0) + 1
    try:
        new_revision_no = int(new_revision_no)
    except (TypeError, ValueError):
        pass

    change_set_id = getattr(result, 'change_set_id', None) or cr_row.get('change_set_id')
    extra: Dict[str, Any] = {'applied_revision_no': new_revision_no}
    if change_set_id:
        extra['change_set_id'] = change_set_id
    updates = transition(ds, cr_row, 'applied', actor, extra)

    # ⑦ 回执（幂等键：status + applied_revision_no）
    return {
        'status': 'applied',
        'revision_no': new_revision_no,
        'applied_at': updates.get('applied_at'),
    }


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
