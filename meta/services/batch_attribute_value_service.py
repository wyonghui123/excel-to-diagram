# -*- coding: utf-8 -*-
"""批次特性值服务 —— 复用通用属性值校验，仅切换值表与归属列。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §11.7
      meta/services/attribute_value_service.py（互斥 / 类型 ↔ 列 / seq / 租户 / active）

继承即生效的约束:
  1. 一行只有一列值非空；
  2. 非空列必须与 attribute_definition.data_type 对应；
  3. 单值属性 seq 恒为 1，多值属性才允许 seq > 1；
  4. 租户私有属性只能被同租户值行引用，平台层属性全租户可用；
  5. 停用 / 已废弃定义不再接受新增写入（历史值仍可读）。

与 ItemAttributeValueService 的差异: 批次是租户对象，**不做** platform-only 限制。
"""

from meta.services.attribute_value_service import AttributeValueService


class BatchAttributeValueService(AttributeValueService):
    """批次特性值表（batch_attribute_values）的写入校验与读回。"""

    VALUE_TABLE = 'batch_attribute_values'
    OWNER_FIELD = 'batch_id'

    def __init__(self, data_source):
        super().__init__(data_source, value_table=self.VALUE_TABLE,
                         owner_field=self.OWNER_FIELD)
