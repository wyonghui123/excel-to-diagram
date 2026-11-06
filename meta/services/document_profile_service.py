# -*- coding: utf-8 -*-
"""[S7.1 2026-11-06] 事实单据六件套声明查询（G13）。

薄封装：只回答「这个对象是不是事实单据、它的编号/时点/状态/行/冲销/快照声明是什么」，
不承载业务逻辑，也不替代各单据自身的 service 层不变量。
"""

from typing import Optional

from meta.core.models import registry, MetaDocumentProfile


class DocumentProfileError(Exception):
    """对象未声明 document: 段却调用了需要该声明的能力。"""


def get_profile(object_type: str) -> Optional[MetaDocumentProfile]:
    """返回对象的 document_profile；未声明或对象不存在时返回 None。"""
    if not object_type:
        return None
    obj = registry.get(object_type)
    if obj is None:
        return None
    return getattr(obj, 'document_profile', None)


def require_profile(object_type: str) -> MetaDocumentProfile:
    """返回对象的 document_profile；未声明时抛 DocumentProfileError。"""
    profile = get_profile(object_type)
    if profile is None:
        raise DocumentProfileError(
            "[S7] 对象 {0!r} 未声明 document: 段".format(object_type))
    return profile


def is_posting_state(object_type: str, state) -> bool:
    """state 是否等于该对象声明的 posting_state（未声明恒为 False）。"""
    profile = get_profile(object_type)
    if profile is None or not profile.posting_state:
        return False
    return str(state or "") == profile.posting_state


def enters_posting_state(object_type: str, old_state, new_state) -> bool:
    """本次状态变化是否「跨入」posting_state（旧值不是、新值是）。"""
    profile = get_profile(object_type)
    if profile is None or not profile.posting_state:
        return False
    return (str(new_state or "") == profile.posting_state
            and str(old_state or "") != profile.posting_state)
