# -*- coding: utf-8 -*-
"""读面字段脱敏（PII 字段级安全域 Spec / P2）

背景：UI 把 `password_hash` / `password_history` 藏起来（`ui.visible=False`），
但 GET 单条 / 列表接口此前原样直出 —— 「看不到」不等于「拿不到」。
本模块在**读面**按字段声明决定是否脱敏，与导出链路（
`import_export_service._should_export_field`）共用同一份 `sensitivity` 声明。

脱敏口径（Spec §5）：

  - `secret` 类字段（`sensitive_fields.LOG_REDACT_IDS`）→ `[REDACTED]`
  - `sensitivity: restricted`：
      * 手机号形态（字段名含 mobile/phone/tel，或值形如号码）→ `_mask_phone`（138****8000）
      * 邮箱形态（字段名含 email/mail，或值含 @ 与域名）→ `a***@domain`
      * 其余（如 password_hash / password_history）→ `[REDACTED]`

只做「读面输出」的脱敏，不改变落库值、不改变写面脱敏、不改变 UI 可见性。

详见 docs/superpowers/specs/2026-10-29-pii-field-level-security-spec.md §5
"""

import re
from typing import Any, Dict, List, Optional

from meta.core.models import registry
from meta.core.security.sensitive_fields import LOG_REDACT_IDS
from meta.services.audit_service import _mask_phone

REDACTED = '[REDACTED]'

#: 字段名（小写）中出现即视为手机号 / 邮箱形态
_PHONE_FIELD_HINTS = ('mobile', 'phone', 'tel', 'cell')
_EMAIL_FIELD_HINTS = ('email', 'mail')

#: 值形态兜底判断（字段名不可靠时）
_PHONE_VALUE_RE = re.compile(r'^\+?[\d\s\-()]{7,20}$')
_EMAIL_VALUE_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _mask_email(value: str) -> str:
    """邮箱脱敏：本地部分只留首字符，域名保留（a***@domain）"""
    stripped = value.strip()
    local, sep, domain = stripped.partition('@')
    if not sep or not local or not domain:
        return REDACTED
    return f"{local[0]}***@{domain}"


def _classify_field(field) -> Optional[str]:
    """判定单个字段的读面脱敏类别；无需脱敏返回 None"""
    field_id = (getattr(field, 'id', '') or '').lower()
    if field_id in LOG_REDACT_IDS:
        return 'secret'

    semantics = getattr(field, 'semantics', None)
    sensitivity = (getattr(semantics, 'sensitivity', '') or '').strip().lower()
    if sensitivity != 'restricted':
        return None

    if any(hint in field_id for hint in _PHONE_FIELD_HINTS):
        return 'restricted_phone'
    if any(hint in field_id for hint in _EMAIL_FIELD_HINTS):
        return 'restricted_email'
    return 'restricted'


def _build_plan(object_type: str) -> Dict[str, str]:
    """为某个对象类型构建 {记录键 → 脱敏类别} 映射

    记录键既可能是字段 id，也可能是 db_column（两者通常同名，但不同名时两者都覆盖）。
    """
    meta_obj = registry.get(object_type)
    if meta_obj is None:
        return {}

    plan: Dict[str, str] = {}
    for meta_field in (getattr(meta_obj, 'fields', None) or []):
        category = _classify_field(meta_field)
        if not category:
            continue
        field_id = getattr(meta_field, 'id', '') or ''
        if field_id:
            plan[field_id] = category
        db_column = getattr(meta_field, 'db_column', '') or ''
        if db_column and db_column != field_id:
            plan[db_column] = category
    return plan


def _mask_value(category: str, value: Any) -> Any:
    """按类别脱敏单个值；空值保持原样（不制造额外信息）"""
    if value is None or value == '':
        return value
    if category == 'secret':
        return REDACTED

    text = value if isinstance(value, str) else str(value)
    if category == 'restricted_phone':
        return _mask_phone(text)
    if category == 'restricted_email':
        return _mask_email(text)

    # restricted 通用：按值形态细分，无法识别则整体替换
    stripped = text.strip()
    if _EMAIL_VALUE_RE.match(stripped):
        return _mask_email(stripped)
    if _PHONE_VALUE_RE.match(stripped):
        return _mask_phone(stripped)
    return REDACTED


def _mask_change_history(history: Any, plan: Dict[str, str]) -> Any:
    """返回脱敏后的 change_history 副本

    变更历史同样会带回字段值（写面脱敏只覆盖 LOG_REDACT_IDS，未覆盖 restricted），
    若不处理，单条读接口会经 history 把哈希原样漏出。
    未命中的条目原样返回引用，命中的条目复制后再改，避免改到入参。
    """
    if not isinstance(history, list) or not history:
        return history

    masked_history: List[Any] = []
    for entry in history:
        if not isinstance(entry, dict):
            masked_history.append(entry)
            continue
        category = plan.get((entry.get('field_name') or '').strip())
        if not category:
            masked_history.append(entry)
            continue
        new_entry = dict(entry)
        for key in ('old_value', 'new_value'):
            if key in new_entry:
                new_entry[key] = _mask_value(category, new_entry[key])
        masked_history.append(new_entry)
    return masked_history


def mask_record(object_type: str, record: Any) -> Any:
    """脱敏单条记录（返回副本，不修改入参）"""
    if not isinstance(record, dict) or not record:
        return record
    plan = _build_plan(object_type)
    if not plan:
        return record

    masked = dict(record)
    for key, category in plan.items():
        if key in masked:
            masked[key] = _mask_value(category, masked[key])

    if 'change_history' in masked:
        masked['change_history'] = _mask_change_history(masked['change_history'], plan)
    return masked


def mask_records(object_type: str, records: Any) -> Any:
    """脱敏一批记录（列表读）"""
    if not isinstance(records, list) or not records:
        return records
    plan = _build_plan(object_type)
    if not plan:
        return records

    masked_list: List[Any] = []
    for record in records:
        if not isinstance(record, dict):
            masked_list.append(record)
            continue
        masked = dict(record)
        for key, category in plan.items():
            if key in masked:
                masked[key] = _mask_value(category, masked[key])
        masked_list.append(masked)
    return masked_list
