# -*- coding: utf-8 -*-
"""属性值服务 —— 值表的写入校验与读回。

依据: docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md §4（R2）
      meta/schemas/_attribute_value_template.yaml（列口径）

三条硬约束（DSL 没有 CHECK，只能由服务强制）:
  1. 一行只有一列值非空 —— 互斥填充；
  2. 非空的那一列必须与 attribute_definition.data_type 对应；
  3. 单值属性 seq 恒为 1，多值属性才允许 seq > 1。

租户边界：租户私有属性（tenant_id > 0）只能被同租户的行使用；平台层属性（tenant_id = 0）全租户可用。
停用 / 已废弃的属性不再接受新增写入（历史值仍可读）。
"""

import importlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: data_type → 承载列
VALUE_COLUMN_BY_TYPE = {
    'string': 'value_text',
    'number': 'value_number',
    'integer': 'value_number',
    'boolean': 'value_boolean',
    'date': 'value_date',
    'datetime': 'value_datetime',
}

#: 全部值列（互斥填充）
VALUE_COLUMNS = ('value_text', 'value_number', 'value_boolean',
                 'value_date', 'value_datetime')


class AttributeValueError(ValueError):
    """属性值不满足类型 / 归属 / 多值约束 —— 拒绝写入。"""

    def __init__(self, message: str, rule: str, field_name: str = ''):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name


class AttributeValueService:
    """值表写入校验与读回（默认业务伙伴值表）。"""

    DEFINITION_TABLE = 'attribute_definitions'
    VALUE_TABLE = 'party_attribute_values'
    OWNER_FIELD = 'party_id'

    #: 对象 → 专用服务类（延迟导入，避免与 batch 服务循环依赖）。
    #: 专用类承载额外业务校验（如 item 只允许平台层定义、batch 的列互斥）。
    _SPECIALIZED = {
        'item': ('meta.services.attribute_value_service', 'ItemAttributeValueService'),
        'batch': ('meta.services.batch_attribute_value_service', 'BatchAttributeValueService'),
    }

    def __init__(self, data_source, value_table: Optional[str] = None,
                 owner_field: Optional[str] = None):
        self.ds = data_source
        if value_table:
            self.VALUE_TABLE = value_table
        if owner_field:
            self.OWNER_FIELD = owner_field

    @classmethod
    def for_object(cls, object_type: str, data_source):
        """[T3.1] 按对象派生值服务，取代「每个对象硬编码一张值表」。

        命名约定（与 party / item / batch 三张现存表一致）：
          value_table = `<object_type>_attribute_values`
          owner_field = `<object_type>_id`
        以对象 id（单数）为基准而非 table_name：`parties` 去复数会得到
        `partie`，只有对象 id 才是稳定单数。

        有专用子类的对象（item / batch）返回子类实例，其余返回基类实例。
        新对象要接扩展属性，只需建一张符合约定的值表，无需改本文件。
        """
        module_path, class_name = cls._SPECIALIZED.get(object_type, ('', ''))
        if module_path:
            module = importlib.import_module(module_path)
            return getattr(module, class_name)(data_source)
        return cls(data_source,
                   value_table=f'{object_type}_attribute_values',
                   owner_field=f'{object_type}_id')

    # ---------- 写入校验 ----------

    def validate_write(self, data: Dict[str, Any]) -> None:
        attribute_id = data.get('attribute_id')
        if attribute_id is None:
            return  # 缺属性归 required / 外键校验

        definition = self.load_definition(attribute_id)
        if definition is None:
            raise AttributeValueError(
                f'属性定义 {attribute_id} 不存在。',
                rule='attribute_missing',
                field_name='attribute_id',
            )

        row_tenant = _as_int(data.get('tenant_id'), default=0)
        def_tenant = _as_int(definition.get('tenant_id'), default=0)
        if def_tenant != 0 and def_tenant != row_tenant:
            raise AttributeValueError(
                '租户私有属性不能用于其他租户的值行。',
                rule='attribute_tenant_mismatch',
                field_name='attribute_id',
            )

        status = (definition.get('status') or 'active')
        if status != 'active':
            raise AttributeValueError(
                f"属性已{('停用' if status == 'inactive' else '废弃')}，不再接受新增写入；历史值仍可读。",
                rule='attribute_not_active',
                field_name='attribute_id',
            )

        # 已提升（attribute_promotion active）：物理列是唯一 owner，值表只读
        object_type = self._object_type()
        if object_type and self._is_promoted(object_type,
                                             definition.get('code')):
            raise AttributeValueError(
                '该属性已提升为业务表物理字段，值表只剩历史副本，'
                '请通过业务对象更新该字段。',
                rule='attribute_promoted',
                field_name='attribute_id',
            )

        filled = [c for c in VALUE_COLUMNS if not _is_blank(data.get(c))]
        if len(filled) != 1:
            raise AttributeValueError(
                f'一行只能有一列值非空，当前有 {len(filled)} 列。',
                rule='attribute_value_column_count',
                field_name=filled[0] if filled else 'value_text',
            )

        column = filled[0]
        data_type = (definition.get('data_type') or 'string')
        expected = VALUE_COLUMN_BY_TYPE.get(data_type, 'value_text')
        if column != expected:
            raise AttributeValueError(
                f"属性类型为 {data_type}，值应写入 {expected}，而不是 {column}。",
                rule='attribute_value_type_mismatch',
                field_name=column,
            )

        seq = _as_int(data.get('seq'), default=1)
        if not _as_bool(definition.get('multi_value_flag')) and seq != 1:
            raise AttributeValueError(
                '该属性为单值属性，seq 只能为 1。',
                rule='attribute_seq_not_allowed',
                field_name='seq',
            )
        if seq < 1:
            raise AttributeValueError(
                'seq 必须大于等于 1。',
                rule='attribute_seq_invalid',
                field_name='seq',
            )

    # ---------- 读回 ----------

    def read_values(self, tenant_id: int, owner_id: int) -> List[Dict[str, Any]]:
        """读回某归属对象的全部属性值（附带定义编码、名称与类型）。"""
        sql = (
            f'SELECT v.id, v.{self.OWNER_FIELD} AS owner_id, v.attribute_id, v.seq, '
            'v.value_text, v.value_number, v.value_boolean, v.value_date, v.value_datetime, '
            'd.code AS attribute_code, d.name AS attribute_name, d.data_type '
            f'FROM {self.VALUE_TABLE} v '
            f'JOIN {self.DEFINITION_TABLE} d ON d.id = v.attribute_id '
            f'WHERE v.tenant_id = ? AND v.{self.OWNER_FIELD} = ? '
            'ORDER BY d.code, v.seq'
        )
        try:
            return self.ds.query(sql, [_as_int(tenant_id), owner_id]) or []
        except Exception as e:
            logger.warning(f'[attribute_value] 读取属性值失败: {e}')
            return []

    # ---------- 查询辅助（可覆写注入）----------

    def _object_type(self) -> str:
        """从值表名反推对象类型（`<object>_attribute_values`）。"""
        suffix = '_attribute_values'
        table = str(self.VALUE_TABLE or '')
        return table[:-len(suffix)] if table.endswith(suffix) else ''

    def _is_promoted(self, object_type: str, code: Any) -> bool:
        if not code:
            return False
        from meta.services.attribute_promotion_service import (
            AttributePromotionService,
        )
        return str(code) in AttributePromotionService.active_codes(
            self.ds, object_type, [str(code)])

    def load_definition(self, attribute_id: Any) -> Optional[Dict[str, Any]]:
        sql = (f'SELECT id, tenant_id, code, name, data_type, multi_value_flag, status '
               f'FROM {self.DEFINITION_TABLE} WHERE id = ? LIMIT 1')
        try:
            rows = self.ds.query(sql, [attribute_id]) or []
        except Exception as e:  # 定义查询失败 → 无法判定，按缺失处理（宁可拒写）
            logger.warning(f'[attribute_value] 属性定义查询失败: {e}')
            return None
        return rows[0] if rows else None


class ItemAttributeValueService(AttributeValueService):
    """物料分层参数值：通用值校验之上，收敛「引用哪本字典、attr_code 必须与它一致」。

    物料参数是平台级主数据（本表无 tenant_id），因此只允许引用平台层定义
    （tenant_id = 0）；租户私有属性不得挂到物料上。
    """

    VALUE_TABLE = 'item_attribute_values'
    OWNER_FIELD = 'item_id'

    def __init__(self, data_source):
        super().__init__(data_source, value_table=self.VALUE_TABLE,
                         owner_field=self.OWNER_FIELD)

    def validate_write(self, data: Dict[str, Any]) -> None:
        attribute_id = data.get('attribute_id')
        if attribute_id is None:
            raise AttributeValueError(
                '物料参数值必须通过 attribute_id 引用属性定义。',
                rule='attribute_id_required',
                field_name='attribute_id',
            )

        definition = self.load_definition(attribute_id)
        if definition is not None and _as_int(definition.get('tenant_id'), 0) != 0:
            raise AttributeValueError(
                '物料参数值只能引用平台层属性（tenant_id = 0）；租户私有属性请挂在业务伙伴等租户对象上。',
                rule='attribute_platform_only',
                field_name='attribute_id',
            )

        super().validate_write(data)

        code = data.get('attr_code')
        if not code:
            raise AttributeValueError(
                '物料参数值必须同时给出 attr_code（该表的物理唯一键）。',
                rule='attr_code_required',
                field_name='attr_code',
            )
        if definition is not None and code != definition.get('code'):
            raise AttributeValueError(
                f"attr_code={code} 与属性定义 {attribute_id} 的编码 "
                f"{definition.get('code')} 不一致；两者必须指向同一属性。",
                rule='attribute_code_mismatch',
                field_name='attr_code',
            )


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y')
    return bool(value)
