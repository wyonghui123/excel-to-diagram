# -*- coding: utf-8 -*-
"""过程指令服务 —— 单表双形态（text / parameter）的写前校验。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §10.5 / §10.7
      docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md 附 C.1

口径:
  · `instruction_kind=text` ⇒ `title` / `content` 必填，参数列必须为空。
  · `instruction_kind=parameter` ⇒ `parameter_code` / `parameter_name` /
    `data_type` / `direction` 必填，文本列必须为空。
  · `data_type=numeric` ⇒ `target_value` / `min_value` / `max_value` 必须是
    可解析十进制；`min ≤ target ≤ max`；`uom_id` 仅 numeric 可填。
  · `direction=set` ⇒ `target_value` 必填；`collect` 允许为空。
  · `resource_id` 若填，资源类型须为 `machine` / `facility` / `tool`。
  · 本服务只读校验，不写业务字段；写路径仍走通用 BO API。

覆写 `_load_resource` 即可注入测试数据。
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

RESOURCE_TABLE = 'resources'

KIND_TEXT = 'text'
KIND_PARAMETER = 'parameter'
INSTRUCTION_KINDS = (KIND_TEXT, KIND_PARAMETER)

DATA_TYPE_NUMERIC = 'numeric'
DATA_TYPES = ('numeric', 'text', 'boolean', 'date')

DIRECTION_SET = 'set'
DIRECTION_COLLECT = 'collect'
DIRECTIONS = (DIRECTION_SET, DIRECTION_COLLECT)

#: 绑定资源允许的资源类型
BINDABLE_RESOURCE_KINDS = ('machine', 'facility', 'tool')

#: text 形态必须为空的参数列
_PARAMETER_FIELDS = (
    'parameter_code', 'parameter_name', 'data_type', 'uom_id',
    'target_value', 'min_value', 'max_value', 'direction',
)
#: parameter 形态必须为空的文本列
_TEXT_FIELDS = ('title', 'content')


class ProcessInstructionError(Exception):
    """过程指令业务校验错误（拦截器转为 ValidationFailedError）。"""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _decimal(value: Any, field_name: str, rule: str = '') -> Optional[Decimal]:
    if _blank(value):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ProcessInstructionError(
            '%s 必须是数字' % field_name,
            field_name=field_name, rule=rule or 'PI_NUMERIC_INVALID')


class ProcessInstructionService:
    """过程指令的形态 / 参数矩阵校验。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 主校验
    # ------------------------------------------------------------------
    def validate(self, payload: Dict[str, Any],
                 existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验创建 / 更新，返回归一化的合并值（只读，不落库）。"""
        patch = dict(payload or {})
        old = dict(existing or {})
        merged = dict(old)
        merged.update(patch)

        kind = _text(merged.get('instruction_kind') or KIND_TEXT).lower()
        if kind not in INSTRUCTION_KINDS:
            raise ProcessInstructionError(
                '未知的指令形态 %s' % kind,
                field_name='instruction_kind', rule='PI_KIND_INVALID')

        self._require_operation(merged)
        if kind == KIND_TEXT:
            self._validate_text(merged)
        else:
            self._validate_parameter(merged)

        self._validate_resource(merged)
        normalized = dict(merged)
        normalized['instruction_kind'] = kind
        normalized['is_required'] = bool(merged.get('is_required'))
        return normalized

    # ------------------------------------------------------------------
    # 形态矩阵
    # ------------------------------------------------------------------
    def _validate_text(self, merged: Dict[str, Any]) -> None:
        if _blank(merged.get('title')):
            raise ProcessInstructionError(
                '文本指令必须填写标题',
                field_name='title', rule='PI_TEXT_TITLE_REQUIRED')
        if _blank(merged.get('content')):
            raise ProcessInstructionError(
                '文本指令必须填写指令正文',
                field_name='content', rule='PI_TEXT_CONTENT_REQUIRED')
        self._assert_blank(merged, _PARAMETER_FIELDS,
                           '文本指令不得填写操作参数列',
                           'PI_TEXT_PARAMETER_NOT_ALLOWED')

    def _validate_parameter(self, merged: Dict[str, Any]) -> None:
        self._assert_blank(merged, _TEXT_FIELDS,
                           '操作参数不得填写文本指令列',
                           'PI_PARAMETER_TEXT_NOT_ALLOWED')
        for field in ('parameter_code', 'parameter_name', 'data_type',
                      'direction'):
            if _blank(merged.get(field)):
                raise ProcessInstructionError(
                    '操作参数必须填写 %s' % field,
                    field_name=field, rule='PI_PARAMETER_FIELD_REQUIRED')

        data_type = _text(merged.get('data_type')).lower()
        if data_type not in DATA_TYPES:
            raise ProcessInstructionError(
                '未知的参数数据类型 %s' % data_type,
                field_name='data_type', rule='PI_DATA_TYPE_INVALID')
        direction = _text(merged.get('direction')).lower()
        if direction not in DIRECTIONS:
            raise ProcessInstructionError(
                '未知的参数方向 %s' % direction,
                field_name='direction', rule='PI_DIRECTION_INVALID')

        if data_type != DATA_TYPE_NUMERIC:
            if not _blank(merged.get('uom_id')):
                raise ProcessInstructionError(
                    '仅数值参数可填写单位',
                    field_name='uom_id', rule='PI_UOM_NOT_ALLOWED')
            return

        target = _decimal(merged.get('target_value'), 'target_value',
                          'PI_TARGET_INVALID')
        minimum = _decimal(merged.get('min_value'), 'min_value',
                           'PI_MIN_INVALID')
        maximum = _decimal(merged.get('max_value'), 'max_value',
                           'PI_MAX_INVALID')
        if direction == DIRECTION_SET and target is None:
            raise ProcessInstructionError(
                '下发参数必须填写目标值',
                field_name='target_value', rule='PI_TARGET_REQUIRED')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ProcessInstructionError(
                '参数下限不得大于上限',
                field_name='min_value', rule='PI_RANGE_INVALID')
        if target is not None:
            if minimum is not None and target < minimum:
                raise ProcessInstructionError(
                    '参数目标值不得小于下限',
                    field_name='target_value', rule='PI_TARGET_OUT_OF_RANGE')
            if maximum is not None and target > maximum:
                raise ProcessInstructionError(
                    '参数目标值不得大于上限',
                    field_name='target_value', rule='PI_TARGET_OUT_OF_RANGE')

    # ------------------------------------------------------------------
    # 绑定资源
    # ------------------------------------------------------------------
    def _validate_resource(self, merged: Dict[str, Any]) -> None:
        resource_id = merged.get('resource_id')
        if _blank(resource_id):
            return
        resource = self._load_resource(resource_id) or {}
        if not resource:
            raise ProcessInstructionError(
                '绑定资源 %s 不存在' % resource_id,
                field_name='resource_id', rule='PI_RESOURCE_NOT_FOUND')
        kind = _text(resource.get('resource_kind')).lower()
        if kind not in BINDABLE_RESOURCE_KINDS:
            raise ProcessInstructionError(
                '绑定资源必须是设备 / 设施 / 工装，当前为 %s' % (kind or '未知'),
                field_name='resource_id', rule='PI_RESOURCE_KIND')

    # ------------------------------------------------------------------
    # 通用
    # ------------------------------------------------------------------
    @staticmethod
    def _require_operation(merged: Dict[str, Any]) -> None:
        if _blank(merged.get('operation_id')):
            raise ProcessInstructionError(
                '过程指令必须归属工序',
                field_name='operation_id', rule='PI_OPERATION_REQUIRED')

    @staticmethod
    def _assert_blank(merged: Dict[str, Any], fields, message: str,
                      rule: str) -> None:
        for field in fields:
            if not _blank(merged.get(field)):
                raise ProcessInstructionError(
                    message, field_name=field, rule=rule)

    # ------------------------------------------------------------------
    # 数据访问（测试可覆写）
    # ------------------------------------------------------------------
    def _load_resource(self, resource_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(resource_id):
            return None
        try:
            rows = self.ds.query(
                'SELECT * FROM %s WHERE id = ?' % RESOURCE_TABLE,
                [resource_id]) or []
        except Exception:  # pragma: no cover - 数据源异常交由上层处理
            logger.exception('process instruction resource query failed')
            return None
        return rows[0] if rows else None
