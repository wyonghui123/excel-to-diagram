# -*- coding: utf-8 -*-
"""行语义通用守卫 —— 同一单据内的行号唯一与实物行数量正数。

优先级 54：晚于需求入口守卫（52，行级必填）与单据守卫（51/52/53），
早于持久化（95）。只对白名单内对象生效，避免影响存量对象。

口径:
  · 行号唯一：同一父单据内 `line_no` 不得重复；比较为新值 + 既有兄弟行，
    更新时排除自身。数据库唯一索引仍是最后防线，本守卫只做写前友好拒绝。
  · 实物行数量：`line_type=goods` 时 qty 必须 > 0（事件型 service 行可空）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

#: 白名单：新增接入对象只需登记一条（parent_field 为所属单据外键）
LINE_GUARD_OBJECTS = {
    'service_request_line': {
        'parent_field': 'request_id',
        'qty_rule': 'goods_positive',
    },
}

_WRITE_ACTIONS = ('crud_create', 'crud_update')


class LineGuardError(ValueError):
    """行语义违规。"""

    code = 'LINE_GUARD_VIOLATION'

    def __init__(self, message, field_name='', rule=''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _line_no(value) -> str:
    if value is None:
        return ''
    return str(value).strip()


class LineGuardInterceptor(Interceptor):
    @property
    def priority(self) -> int:
        return 54

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id in LINE_GUARD_OBJECTS \
            and context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        object_type = getattr(context.meta_object, 'id', None)
        config = LINE_GUARD_OBJECTS.get(object_type)
        if not config:
            return
        row = dict(getattr(context, 'old_data', None) or {})
        row.update(context.params or {})
        try:
            self.validate_qty(object_type, row)
            self.validate_batch(object_type, config['parent_field'],
                                self._batch_with_siblings(context, object_type,
                                                          config, row))
        except LineGuardError as error:
            self._raise_validation(error)

    # ---------------------------------------------------------------- 校验
    def after_action(self, context: 'ActionContext') -> None:
        """纯写前守卫，无写后逻辑。"""
        return None

    def validate_batch(self, object_type: str, parent_field: str,
                       payload: dict) -> None:
        """同一父单据内行号不得重复（payload 可带 lines 批量或单行）。"""
        if object_type not in LINE_GUARD_OBJECTS:
            return
        rows = payload.get('lines')
        if not isinstance(rows, list):
            rows = [payload]
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            line_no = _line_no(row.get('line_no'))
            if not line_no:
                continue
            if line_no in seen:
                raise LineGuardError(
                    '行号 %s 在同一单据内重复' % line_no,
                    field_name='line_no', rule='LINE_NO_DUPLICATE')
            seen.add(line_no)

    def validate_qty(self, object_type: str, row: dict) -> None:
        """实物行数量必须大于 0（line_type=goods）。"""
        config = LINE_GUARD_OBJECTS.get(object_type) or {}
        if config.get('qty_rule') != 'goods_positive':
            return
        if (row.get('line_type') or 'service') != 'goods':
            return
        qty = row.get('qty')
        try:
            value = float(qty)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            raise LineGuardError(
                '实物行数量必须大于 0', field_name='qty',
                rule='LINE_QTY_POSITIVE')

    # ---------------------------------------------------------------- 内部
    def _batch_with_siblings(self, context: 'ActionContext', object_type: str,
                             config: dict, row: dict) -> dict:
        parent_field = config['parent_field']
        parent_id = row.get(parent_field)
        line_no = _line_no(row.get('line_no'))
        siblings = []
        if parent_id not in (None, '') and line_no:
            siblings = self._sibling_lines(context.data_source, object_type,
                                          parent_field, parent_id,
                                          row.get('id'))
        return {parent_field: parent_id, 'lines': siblings + [row]}

    @staticmethod
    def _sibling_lines(data_source, object_type: str, parent_field: str,
                       parent_id, exclude_id) -> list:
        from meta.core.models import registry
        meta_object = registry.get(object_type)
        table = getattr(meta_object, 'table_name', '') if meta_object else ''
        if not table:
            return []
        try:
            exclude = int(exclude_id) if exclude_id not in (None, '') else 0
            return data_source.query(
                'SELECT id, line_no FROM %s WHERE %s = ? AND id <> ?'
                % (table, parent_field), [parent_id, exclude])
        except Exception as error:  # noqa: BLE001 - 查询失败不阻断写入
            logger.warning('[LineGuard] 兄弟行号查询失败: %s', error)
            return []

    @staticmethod
    def _raise_validation(error: LineGuardError) -> None:
        raise ValidationFailedError(
            message=str(error),
            details=[{
                'field_name': error.field_name,
                'rule': error.rule or 'line_guard',
                'message': str(error),
                'i18n_key': '',
                'params': {},
            }],
        )
