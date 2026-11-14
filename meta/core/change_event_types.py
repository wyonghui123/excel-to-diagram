# -*- coding: utf-8 -*-
"""变更事件词表（canonical vocabulary）——消息平台唯一词表入口。

事件是"已发生的事实"，统一使用过去式：

    created / updated / deleted / state_changed

历史遗留三套词表：
    - 发布端 `ManageService` 写 `create/update/delete`
    - `WebSocketManager` 订阅默认 `created/updated/deleted`
    - `AggregateRefreshHandler` 只认 `created/updated/deleted`
    - 旁路服务（work_order 等）直插 `state_change`
    - 文档写大写 `CREATE/UPDATE/DELETE`

本模块负责把任意别名归一为 canonical，落库 / 广播 / 聚合刷新 / 订阅匹配
全部使用归一后的值，避免继续扩散。
"""
from __future__ import annotations

from typing import Any, Optional

CREATED = 'created'
UPDATED = 'updated'
DELETED = 'deleted'
STATE_CHANGED = 'state_changed'

CANONICAL_EVENT_TYPES = (CREATED, UPDATED, DELETED, STATE_CHANGED)

#: 变更事件 / 收件箱的在线保留天数（归档任务按 retention_until 清理）。
#: 全平台唯一来源：发布写入、收件箱复用、归档审计均引用此处。
DEFAULT_RETENTION_DAYS = 365

#: 事件类型的中文展示名（webhook / 飞书 / 站内收件箱统一复用）。
#: action_required 是通知语义扩展（非 canonical 事件类型），仅用于文案。
EVENT_TYPE_LABELS = {
    CREATED: '新建',
    UPDATED: '更新',
    DELETED: '删除',
    STATE_CHANGED: '状态变更',
    'action_required': '待处理',
}

# 别名 → canonical。键统一小写后比较。
_ALIASES = {
    'create': CREATED,
    'created': CREATED,
    'update': UPDATED,
    'updated': UPDATED,
    'delete': DELETED,
    'deleted': DELETED,
    'state_change': STATE_CHANGED,
    'state_changed': STATE_CHANGED,
    'status_change': STATE_CHANGED,
    'status_changed': STATE_CHANGED,
}


def normalize(event_type: Any) -> Optional[str]:
    """把任意写法的事件类型归一为 canonical。

    未知值原样小写返回（保留可扩展性），空值返回 None。
    """
    if event_type is None:
        return None
    key = str(event_type).strip().lower()
    if not key:
        return None
    return _ALIASES.get(key, key)


def is_canonical(event_type: Any) -> bool:
    return normalize(event_type) in CANONICAL_EVENT_TYPES