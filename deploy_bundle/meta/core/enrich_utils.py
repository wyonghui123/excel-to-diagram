# -*- coding: utf-8 -*-
"""
computed count filter / order 子句构造器（delegate）。

[SPR-01 S-01 2026-06-10] 删除了 v1 兼容 shim（enrich_fk_display_names /
enrich_association_counts / _get_engine）。

[SPR-02 S-02 2026-06-10] 实际逻辑迁移到 `meta/core/_computed_count_clause.py`，
本文件保留 2 个 1-line delegate 维持向后兼容。
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_computed_count_filter_clause(meta_object, key: str, value: Any,
                                        target_alias: str = ''):
    """[SPR-02 delegate] → _computed_count_clause.build_filter_clause。"""
    from meta.core._computed_count_clause import build_filter_clause
    clause, params = build_filter_clause(meta_object, key, value, target_alias=target_alias)
    if clause is None:
        return None, []
    return clause, params or []


def build_computed_count_order_clause(meta_object, field_name: str, is_desc: bool,
                                       target_alias: str = ''):
    """[SPR-02 delegate] → _computed_count_clause.build_order_clause。"""
    from meta.core._computed_count_clause import build_order_clause
    return build_order_clause(meta_object, field_name, is_desc, target_alias=target_alias)
