# -*- coding: utf-8 -*-
"""UI 视图变体合并（M0，YAML v1.1）。

契约见 docs/specs/spec-meta-driven-ui-2026-11-16.md §4.7.4：

- 逐层深合并；数组按稳定键合并（同键覆盖、新键追加、`_remove: true` 删除）。
- 禁止在变体 patch 内嵌套 `variants`（不支持跨变体继承，避免环）。
- 纯函数：不依赖 registry，供 view_config_service 与 lint 共用。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

#: 数组稳定键：按合并路径（相对 ui_view_config）取第一命中的键作为身份。
_ARRAY_IDENTITY_KEYS: Dict[str, Tuple[str, ...]] = {
    'list.columns': ('field', 'key'),
    'list.actions': ('id', 'key'),
    'list.batch_actions': ('id', 'key'),
    'detail.sections': ('key',),
    'detail.tabs': ('key',),
    'form.sections': ('key',),
    'form.fields': ('id', 'key'),
    'filter.filters': ('key',),
}


def _identity(item: Any, keys: Tuple[str, ...]) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    for key in keys:
        value = item.get(key)
        if value not in (None, ''):
            return str(value)
    return None


def _normalize_path(where: str) -> str:
    """把 `ui_view_config.list.columns` 归一成 `list.columns`。"""
    prefix = 'ui_view_config.'
    return where[len(prefix):] if where.startswith(prefix) else where


def _merge_array(
    base_list: List[Any],
    patch_list: List[Any],
    identity_keys: Tuple[str, ...],
    where: str,
) -> Tuple[List[Any], List[str]]:
    warnings: List[str] = []
    merged: List[Any] = list(base_list)
    index: Dict[str, int] = {}
    for position, item in enumerate(merged):
        ident = _identity(item, identity_keys)
        if ident is not None:
            index[ident] = position

    def _rebuild() -> None:
        index.clear()
        for position, item in enumerate(merged):
            ident = _identity(item, identity_keys)
            if ident is not None:
                index[ident] = position

    for item in patch_list:
        if not isinstance(item, dict):
            merged.append(item)
            continue
        ident = _identity(item, identity_keys)
        if ident is None:
            warnings.append(f'{where}: 数组项缺少稳定键 {identity_keys}，已追加为独立项')
            merged.append(dict(item))
            continue
        if item.get('_remove') is True:
            if ident in index:
                merged.pop(index[ident])
                _rebuild()
            continue
        payload = {k: v for k, v in item.items() if k != '_remove'}
        if ident in index:
            merged[index[ident]] = {**merged[index[ident]], **payload}
        else:
            index[ident] = len(merged)
            merged.append(payload)
    return merged, warnings


def merge_patch(
    base: Dict[str, Any],
    patch: Dict[str, Any],
    *,
    where: str = '',
    _top_level: bool = True,
) -> Tuple[Dict[str, Any], List[str]]:
    """把 patch 深合并到 base 的副本上（不修改入参）。"""
    warnings: List[str] = []
    if not isinstance(patch, dict):
        return dict(base or {}), warnings

    result: Dict[str, Any] = dict(base or {})
    for key, value in patch.items():
        child_where = f'{where}.{key}' if where else str(key)
        if key == 'variants':
            # 变体不可再携带变体（禁止继承链 ⇒ 天然无环）。
            warnings.append(f'{child_where}: 变体内不允许嵌套 variants，已忽略')
            continue
        base_value = result.get(key)
        if isinstance(value, dict) and (base_value is None or isinstance(base_value, dict)):
            merged_child, child_warnings = merge_patch(
                base_value or {}, value, where=child_where, _top_level=False,
            )
            result[key] = merged_child
            warnings.extend(child_warnings)
            continue
        if isinstance(value, list) and isinstance(base_value, list):
            identity_keys = _ARRAY_IDENTITY_KEYS.get(_normalize_path(child_where))
            if identity_keys:
                merged_list, child_warnings = _merge_array(
                    base_value, value, identity_keys, child_where,
                )
                result[key] = merged_list
                warnings.extend(child_warnings)
            else:
                result[key] = list(value)
            continue
        result[key] = value
    return result, warnings


def apply_variant(base_config: Any, patch: Dict[str, Any]) -> Tuple[Any, List[str]]:
    """基础 UIViewConfig + 变体 patch → 新 UIViewConfig（失败时调用方回退 base）。"""
    if not isinstance(patch, dict):
        return base_config, ['ui_view_config.variants: patch 必须是对象']

    patch = dict(patch)
    # 变体级 title 语义 = 列表标题（UIViewConfig 自身无 title 字段）。
    variant_title = patch.pop('title', None)

    base_dict = asdict(base_config)
    merged, warnings = merge_patch(base_dict, patch, where='ui_view_config')
    if isinstance(variant_title, str) and variant_title:
        merged.setdefault('list', {})['title'] = variant_title
    # 变体不携带文法版本/嵌套变体（保持基础视图的 version）。
    merged['version'] = getattr(base_config, 'version', 1) or 1
    merged['variants'] = {}

    # 延迟 import：yaml_loader 会 import models_ui_config，避免模块级环。
    from meta.core.yaml_loader import parse_ui_view_config

    return parse_ui_view_config(merged, None), warnings
