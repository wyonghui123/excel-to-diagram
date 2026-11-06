# -*- coding: utf-8 -*-
"""[S7.4 2026-11-06] 事实单据生命周期默认推导（G16）。

只在对象**未显式声明** `state_field_policies` 时兜底：
- 过账状态下，编号字段 + 快照字段默认只读（posting_lock）；
- 过账状态下不可物理删除（delete_locked）。

显式声明永远优先——不猜业务。会计期间（period_closed）属 D7 待定项，本轮不做。
"""

from typing import Dict, List

from meta.services.document_profile_service import get_profile


def derive_default_state_policy(object_type: str) -> Dict[str, Dict[str, List[str]]]:
    """由 document_profile 推导终端状态的默认只读字段集合。

    返回 `{posting_state: {'readonly': [...]}}`；未声明 posting_state 时返回 {}。
    """
    profile = get_profile(object_type)
    if profile is None or not profile.posting_state:
        return {}
    readonly = []
    for name in [profile.number_field] + list(profile.snapshot_fields or []):
        if name and name not in readonly:
            readonly.append(name)
    if not readonly:
        return {}
    return {profile.posting_state: {'readonly': readonly}}


def derive_deletability(object_type: str, state) -> bool:
    """已过账状态不可物理删除；其余状态不由本函数裁决（返回 True 表示无异议）。"""
    profile = get_profile(object_type)
    if profile is None or not profile.posting_state:
        return True
    return str(state or "") != profile.posting_state
