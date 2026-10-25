# -*- coding: utf-8 -*-
"""配置结果层守卫 —— 实例头 / 特征值 / 组件的写入与删除。

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §6 / §8.4 / R10 / R11 / R13 / R14

口径:
  ① configuration 一旦 solved，config_hash 不可改；frozen 后除 status（转
     superseded）外任何字段不得修改；superseded 全锁；仅 draft 可删除（R10）。
  ② configuration_value / configuration_component 只在父实例 draft 时可增删改
     —— 求解产物由服务写入，人工只应编辑草稿。
  ③ configuration_value：三列值恰好一列非空；source ∈ {default, rule} 必须带
     source_rule_id；source 只接受 user / default / rule / derived。
  ④ configuration_component：component_key 必须是行号路径（L0001 / L0012.L0003）；
     父键必须能在同一实例内找到；selection_source = rule 必须带 source_rule_id；
     用量不得为负。
查询失败一律 fail-open + WARNING（与既有守卫同口径）。
"""

import logging
import re
from typing import Any, Dict, Mapping, Optional

from meta.services.item_structure_guard_service import _is_blank, _to_decimal

logger = logging.getLogger(__name__)

_HEAD_TABLE = 'configurations'
_VALUE_TABLE = 'configuration_values'
_COMPONENT_TABLE = 'configuration_components'

_STATUSES = ('draft', 'solved', 'invalid', 'frozen', 'superseded')
_VALUE_SOURCES = ('user', 'default', 'rule', 'derived')
_COMPONENT_SOURCES = ('auto', 'user', 'rule')
_VALUE_COLUMNS = ('value_text', 'value_number', 'value_boolean')
_COMPONENT_KEY_RE = re.compile(r'^L\d{4}(\.L\d{4})*$')

# 状态允许的后续状态
_TRANSITIONS = {
    'draft': {'draft', 'solved', 'invalid'},
    'invalid': {'invalid', 'draft', 'solved'},
    'solved': {'solved', 'frozen', 'superseded'},
    'frozen': {'frozen', 'superseded'},
    'superseded': {'superseded'},
}

_MISSING = object()


class ConfigurationGuardError(ValueError):
    """配置结果层写入被拒。`rule` / `field_name` 供调用方定位。"""

    def __init__(self, message: str, rule: str = '', field_name: str = ''):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    if left is None or right is None:
        return left is None and right is None
    return str(left) == str(right)


class ConfigurationGuardService:
    """结果层的状态锁与字段完整性校验。查询方法可覆写。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- configuration ----------

    def validate_head_write(self, data: Mapping[str, Any],
                            exclude_id: Any = None) -> None:
        status = str(data.get('status') or 'draft')
        if status not in _STATUSES:
            raise ConfigurationGuardError(
                f'状态 {status} 不在 draft / solved / invalid / frozen / superseded 内',
                rule='configuration_status_invalid', field_name='status')

        if exclude_id is None:
            if status in ('frozen', 'superseded'):
                raise ConfigurationGuardError(
                    f'不能直接创建 {status} 状态的配置实例',
                    rule='configuration_create_status_invalid',
                    field_name='status')
            if status in ('solved', 'invalid') and _is_blank(data.get('config_hash')):
                raise ConfigurationGuardError(
                    '求解产出的实例必须带 config_hash',
                    rule='configuration_hash_required', field_name='config_hash')
            return

        old = self._fetch_head(exclude_id)
        if old is None:
            return
        old_status = str(old.get('status') or 'draft')

        if old_status == 'superseded':
            raise ConfigurationGuardError(
                '已被替代的实例不再接受修改',
                rule='configuration_locked', field_name='status')

        if status not in _TRANSITIONS.get(old_status, {old_status}):
            raise ConfigurationGuardError(
                f'状态不能从 {old_status} 变为 {status}',
                rule='configuration_status_transition_invalid',
                field_name='status')

        if old_status == 'frozen':
            changed = self._changed_fields(data, old)
            if changed - {'status'}:
                raise ConfigurationGuardError(
                    f"已冻结实例不可修改: {sorted(changed - {'status'})}",
                    rule='configuration_frozen_locked', field_name='status')
            return

        if old_status == 'solved':
            if 'config_hash' in data and not _same(data.get('config_hash'),
                                                   old.get('config_hash')):
                raise ConfigurationGuardError(
                    'config_hash 在 solved 后不可修改；变更请生成新实例',
                    rule='configuration_hash_immutable', field_name='config_hash')

    def validate_head_delete(self, configuration_id: Any) -> None:
        head = self._fetch_head(configuration_id)
        if head is None:
            return
        status = str(head.get('status') or '')
        if status != 'draft':
            raise ConfigurationGuardError(
                f'{status} 状态的配置实例不可删除',
                rule='configuration_delete_locked', field_name='id')

    # ---------- configuration_value ----------

    def validate_value_write(self, data: Mapping[str, Any],
                             exclude_id: Any = None) -> None:
        parent_id = data.get('configuration_id')
        if _is_blank(parent_id):
            raise ConfigurationGuardError(
                '特征值必须归属一个配置实例',
                rule='configuration_value_parent_required',
                field_name='configuration_id')
        self._require_draft_parent(parent_id, 'configuration_value')

        if _is_blank(data.get('attribute_code')):
            raise ConfigurationGuardError(
                '特征值必须给出 attribute_code',
                rule='configuration_value_code_required',
                field_name='attribute_code')

        source = str(data.get('source') or 'user')
        if source not in _VALUE_SOURCES:
            raise ConfigurationGuardError(
                f'取值来源 {source} 不在 user / default / rule / derived 内',
                rule='configuration_value_source_invalid', field_name='source')
        if source in ('default', 'rule') and _is_blank(data.get('source_rule_id')):
            raise ConfigurationGuardError(
                f'来源为 {source} 时必须带 source_rule_id，用于解释取值',
                rule='configuration_value_rule_required',
                field_name='source_rule_id')

        filled = [column for column in _VALUE_COLUMNS
                  if not _is_blank(data.get(column))]
        if len(filled) != 1:
            raise ConfigurationGuardError(
                f'value_text / value_number / value_boolean 必须恰好一列有值，当前 {filled}',
                rule='configuration_value_column_exclusive',
                field_name='value_text')

    def validate_value_delete(self, value_id: Any) -> None:
        row = self._fetch_value(value_id)
        if row is None:
            return
        self._require_draft_parent(row.get('configuration_id'),
                                   'configuration_value', delete=True)

    # ---------- configuration_component ----------

    def validate_component_write(self, data: Mapping[str, Any],
                                 exclude_id: Any = None) -> None:
        parent_id = data.get('configuration_id')
        if _is_blank(parent_id):
            raise ConfigurationGuardError(
                '组件必须归属一个配置实例',
                rule='configuration_component_parent_required',
                field_name='configuration_id')
        self._require_draft_parent(parent_id, 'configuration_component')

        key = str(data.get('component_key') or '').strip()
        if not key:
            raise ConfigurationGuardError(
                '组件必须给出 component_key',
                rule='configuration_component_key_required',
                field_name='component_key')
        if not _COMPONENT_KEY_RE.match(key):
            raise ConfigurationGuardError(
                f'component_key {key!r} 不是行号路径（形如 L0001 或 L0012.L0003）',
                rule='configuration_component_key_invalid',
                field_name='component_key')

        for field in ('structure_line_id', 'component_item_id', 'uom_code'):
            if _is_blank(data.get(field)):
                raise ConfigurationGuardError(
                    f'组件缺少必填项 {field}',
                    rule='configuration_component_field_required',
                    field_name=field)

        if _is_blank(data.get('qty')):
            raise ConfigurationGuardError(
                '组件缺少必填项 qty',
                rule='configuration_component_field_required', field_name='qty')
        qty = _to_decimal(data.get('qty'))
        if qty < 0:
            raise ConfigurationGuardError(
                f'组件用量 {data.get("qty")} 不能为负',
                rule='configuration_component_qty_invalid', field_name='qty')

        source = str(data.get('selection_source') or 'auto')
        if source not in _COMPONENT_SOURCES:
            raise ConfigurationGuardError(
                f'选择来源 {source} 不在 auto / user / rule 内',
                rule='configuration_component_source_invalid',
                field_name='selection_source')
        if source == 'rule' and _is_blank(data.get('source_rule_id')):
            raise ConfigurationGuardError(
                'selection_source = rule 时必须带 source_rule_id',
                rule='configuration_component_rule_required',
                field_name='source_rule_id')

        parent_key = str(data.get('parent_component_key') or '').strip()
        if parent_key and not self._component_key_exists(parent_id, parent_key):
            raise ConfigurationGuardError(
                f'父组件键 {parent_key!r} 在同一次配置内不存在',
                rule='configuration_component_parent_missing',
                field_name='parent_component_key')

    def validate_component_delete(self, component_id: Any) -> None:
        row = self._fetch_component(component_id)
        if row is None:
            return
        self._require_draft_parent(row.get('configuration_id'),
                                   'configuration_component', delete=True)

    # ---------- 内部 ----------

    def _require_draft_parent(self, parent_id: Any, prefix: str,
                              delete: bool = False) -> None:
        head = self._fetch_head(parent_id)
        if head is None:
            return
        status = str(head.get('status') or 'draft')
        if status != 'draft':
            action = '删除' if delete else '修改'
            raise ConfigurationGuardError(
                f'{status} 状态的实例不允许{action}明细，只有 draft 可编辑',
                rule=f'{prefix}_parent_not_draft',
                field_name='configuration_id')

    @staticmethod
    def _changed_fields(data: Mapping[str, Any], old: Mapping[str, Any]) -> set:
        changed = set()
        for key, value in data.items():
            if key in ('id', 'created_at', 'updated_at', 'created_by', 'updated_by'):
                continue
            previous = old.get(key, _MISSING)
            if previous is _MISSING or not _same(value, previous):
                changed.add(key)
        return changed

    def _fetch_head(self, configuration_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f"SELECT * FROM {_HEAD_TABLE} WHERE id = ?", [configuration_id])
        except Exception as e:
            logger.warning(f'[configuration_guard] 读取配置实例失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_value(self, value_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f"SELECT * FROM {_VALUE_TABLE} WHERE id = ?", [value_id])
        except Exception as e:
            logger.warning(f'[configuration_guard] 读取配置特征值失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_component(self, component_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f"SELECT * FROM {_COMPONENT_TABLE} WHERE id = ?", [component_id])
        except Exception as e:
            logger.warning(f'[configuration_guard] 读取配置组件失败: {e}')
            return None
        return rows[0] if rows else None

    def _component_key_exists(self, configuration_id: Any, key: str) -> bool:
        try:
            rows = self.ds.query(
                f"SELECT 1 FROM {_COMPONENT_TABLE} "
                "WHERE configuration_id = ? AND component_key = ? LIMIT 1",
                [configuration_id, key])
        except Exception as e:
            logger.warning(f'[configuration_guard] 校验父组件键失败: {e}')
            return True
        return bool(rows)
