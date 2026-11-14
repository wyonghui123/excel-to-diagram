# -*- coding: utf-8 -*-
"""站内收件箱服务（P1-b）

依据 docs/specs/spec-message-platform-change-event-2026-11-14.md §5/§6:
  - 唯一收件箱：`in_app` 投递落 `notification_inbox`，UI 只读这张表
  - 收件箱按**事件**聚合（不是按任务）；`task_id` 是可执行附件的弱引用
  - 读取隔离：非管理员只能看到自己的收件箱行

本服务只负责收件箱的读写；投递事实由 `ChangeEventDispatcher` 写入
`notification_deliveries`，两者通过 `delivery_id` 一对一关联。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from meta.core.change_event_types import (
    DEFAULT_RETENTION_DAYS,
    EVENT_TYPE_LABELS,
    normalize,
)

logger = logging.getLogger(__name__)

INBOX_TABLE = 'notification_inbox'
DELIVERIES_TABLE = 'notification_deliveries'

#: 收件箱保留期（与 change_events 一致，归档任务按该列清理）
RETENTION_DAYS = DEFAULT_RETENTION_DAYS


def _now() -> str:
    return datetime.now().isoformat()


def _rows(cursor) -> List[Dict[str, Any]]:
    if cursor is None:
        return []
    rows = cursor.fetchall()
    cols = [d[0] for d in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in rows]


def _scalar(cursor) -> int:
    row = cursor.fetchone() if cursor is not None else None
    if not row:
        return 0
    return int(row[0] or 0)


def _to_object_id(value: Any) -> int:
    """object_id 在收件箱中为 INTEGER；非数字对象退化为 0（仍可凭 object_type 定位）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class NotificationInboxService:
    """`notification_inbox` 的唯一读写入口。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------ 写入
    def create_for_event(
        self, user_id: Any, delivery_id: Any, event: Dict[str, Any]
    ) -> Optional[int]:
        """为一次 in_app 投递写一行收件箱；幂等（UNIQUE(user_id, delivery_id)）。

        Returns:
            inbox 行 id；无法写入时返回 None（fail-open，不影响事件事实）。
        """
        if self.ds is None or user_id is None or delivery_id is None:
            return None

        try:
            user_id = int(user_id)
            delivery_id = int(delivery_id)
        except (TypeError, ValueError):
            logger.warning(
                "[inbox] 非法 user_id/delivery_id: user_id=%s delivery_id=%s",
                user_id, delivery_id,
            )
            return None

        try:
            existing = self._find_by_user_delivery(user_id, delivery_id)
            if existing:
                return existing.get('id')
        except Exception as e:
            logger.warning("[inbox] 幂等检查失败: %s", e)
            return None

        event_type = normalize(event.get('event_type')) or (event.get('event_type') or '')
        created_at = event.get('created_at') or _now()
        retention_until = event.get('retention_until') or (
            datetime.now() + timedelta(days=RETENTION_DAYS)
        ).isoformat()

        row = {
            'user_id': user_id,
            'delivery_id': delivery_id,
            'event_id': int(event.get('id') or 0),
            'object_type': event.get('object_type') or '',
            'object_id': _to_object_id(event.get('object_id')),
            'event_type': event_type,
            'title': self._build_title(event, event_type)[:250],
            'body': self._build_body(event)[:2000],
            'link': (event.get('link') or None),
            'task_id': event.get('task_id') or None,
            'read_at': None,
            'dismissed_at': None,
            'created_at': created_at,
            'retention_until': retention_until,
        }

        try:
            return self.ds.insert(INBOX_TABLE, row)
        except Exception as e:
            # 并发下的唯一键冲突：回读已存在行，保证幂等
            logger.warning("[inbox] 写入失败（按已存在处理）: %s", e)
            try:
                existing = self._find_by_user_delivery(user_id, delivery_id)
                return existing.get('id') if existing else None
            except Exception:
                return None

    def _find_by_user_delivery(
        self, user_id: int, delivery_id: int
    ) -> Optional[Dict[str, Any]]:
        """幂等键 (user_id, delivery_id) 回读单行。"""
        rows = self.ds.find(
            INBOX_TABLE,
            filters={'user_id': user_id, 'delivery_id': delivery_id},
            limit=1,
        )
        return rows[0] if rows else None

    @staticmethod
    def _meta_object(object_type: str):
        """从元数据注册表取对象定义；未注册时返回 None（保持原始值降级）。"""
        try:
            from meta.core.models import registry
            return registry.get(object_type)
        except Exception:
            return None

    @classmethod
    def _object_label(cls, object_type: str) -> str:
        obj = cls._meta_object(object_type)
        return (getattr(obj, 'name', None) or object_type or '')

    @classmethod
    def _field_label(cls, object_type: str, field_name: str) -> str:
        obj = cls._meta_object(object_type)
        for field in (getattr(obj, 'fields', None) or []):
            if field.id == field_name or getattr(field, 'db_column', None) == field_name:
                return field.name or field_name
        return field_name

    @classmethod
    def _build_title(cls, event: Dict[str, Any], event_type: str) -> str:
        payload = event.get('payload')
        if isinstance(payload, dict):
            for key in ('title', 'name', 'subject'):
                if payload.get(key):
                    return str(payload[key])
        label = EVENT_TYPE_LABELS.get(event_type, event_type or '通知')
        object_type = event.get('object_type') or ''
        return '%s: %s #%s' % (label, cls._object_label(object_type), event.get('object_id'))

    @classmethod
    def _build_body(cls, event: Dict[str, Any]) -> str:
        payload = event.get('payload')
        if isinstance(payload, dict):
            for key in ('summary', 'message', 'body', 'content', 'note'):
                if payload.get(key):
                    return str(payload[key])

        object_type = event.get('object_type') or ''
        lines: List[str] = []
        old_values = event.get('old_values') or {}
        new_values = event.get('new_values') or {}
        for field_name in (event.get('changed_fields') or [])[:10]:
            if field_name in old_values or field_name in new_values:
                label = cls._field_label(object_type, field_name)
                lines.append(
                    '%s: %s → %s'
                    % (label, old_values.get(field_name), new_values.get(field_name))
                )
        if not lines and isinstance(payload, dict):
            for key, value in list(payload.items())[:10]:
                lines.append(
                    '%s: %s' % (cls._field_label(object_type, key), value)
                )
        return '\n'.join(lines)

    # ------------------------------------------------------------------ 查询
    def list(
        self,
        user_id: Any,
        *,
        unread_only: bool = False,
        object_type: Optional[str] = None,
        event_type: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """当前用户收件箱分页。`unread_only` 只返回未读且未忽略的行。"""
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        offset = (page - 1) * page_size

        where = ['user_id = ?']
        params: List[Any] = [int(user_id)]
        if unread_only:
            where.append('read_at IS NULL')
            where.append('dismissed_at IS NULL')
        if object_type:
            where.append('object_type = ?')
            params.append(object_type)
        if event_type:
            where.append('event_type = ?')
            params.append(normalize(event_type) or event_type)
        if keyword:
            where.append('(title LIKE ? OR body LIKE ?)')
            params.extend(['%' + keyword + '%', '%' + keyword + '%'])

        where_sql = ' AND '.join(where)
        total = _scalar(self.ds.execute(
            'SELECT COUNT(*) FROM %s WHERE %s' % (INBOX_TABLE, where_sql),
            tuple(params),
        ))
        cursor = self.ds.execute(
            'SELECT * FROM %s WHERE %s ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?'
            % (INBOX_TABLE, where_sql),
            tuple(params + [page_size, offset]),
        )
        return _rows(cursor), total

    def unread_count(self, user_id: Any) -> int:
        """未读数（排除已忽略）。"""
        return _scalar(self.ds.execute(
            'SELECT COUNT(*) FROM %s WHERE user_id = ? '
            'AND read_at IS NULL AND dismissed_at IS NULL' % INBOX_TABLE,
            (int(user_id),),
        ))

    # ------------------------------------------------------------------ 状态
    def mark_read(self, user_id: Any, inbox_id: Any) -> Optional[Dict[str, Any]]:
        """标记单条已读；返回更新后的行，不存在返回 None。"""
        row = self.ds.find_by_id(INBOX_TABLE, int(inbox_id))
        if not row or row.get('user_id') != int(user_id):
            return None
        if not row.get('read_at'):
            self.ds.update(INBOX_TABLE, int(inbox_id), {'read_at': _now()})
            row['read_at'] = _now()
        return row

    def mark_all_read(
        self,
        user_id: Any,
        *,
        object_type: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> int:
        """批量标记已读（只影响未读行），返回影响行数。"""
        where = ['user_id = ?', 'read_at IS NULL']
        params: List[Any] = [int(user_id)]
        if object_type:
            where.append('object_type = ?')
            params.append(object_type)
        if event_type:
            where.append('event_type = ?')
            params.append(normalize(event_type) or event_type)
        cursor = self.ds.execute(
            'UPDATE %s SET read_at = ? WHERE %s' % (INBOX_TABLE, ' AND '.join(where)),
            tuple([_now()] + params),
        )
        return int(getattr(cursor, 'rowcount', 0) or 0)

    def dismiss(self, user_id: Any, inbox_id: Any) -> Optional[Dict[str, Any]]:
        """忽略单条（保留在「全部」列表，不计入未读）。"""
        row = self.ds.find_by_id(INBOX_TABLE, int(inbox_id))
        if not row or row.get('user_id') != int(user_id):
            return None
        if not row.get('dismissed_at'):
            self.ds.update(INBOX_TABLE, int(inbox_id), {'dismissed_at': _now()})
            row['dismissed_at'] = _now()
        return row