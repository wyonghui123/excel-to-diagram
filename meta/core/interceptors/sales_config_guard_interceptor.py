# -*- coding: utf-8 -*-
"""销售配置守卫拦截器 —— 控制参数与行类型确定的写入入口。

覆盖范围:
  control_parameter_def       创建 / 更新 —— 值类型与值集/目标对象一致、默认值可解释、
                                           已有取值后语义不可改
  control_parameter_value     创建 / 更新 —— 取值按值类型校验、维度组合 + 具体度唯一
  line_type_assignment  创建 / 更新 —— 单据类型下「物料组 + 具体度」唯一
  任意对象                     删除       —— ref 型参数的取值里不能还有指向该记录的引用

优先级 46（在 HierarchyValidationInterceptor 45 之后）：维度引用的父子关系先由
层级校验确认，再判唯一性。其余对象 / 动作零开销短路。

写入成功后调用 `get_control_parameter_resolver().invalidate()`：解析器是进程级单例
+ 内存缓存，不失效则配置改动要到重启才生效。

判定口径见 meta/services/sales_config_guard_service.py（D1-D4 / V1-V2 / A1 / X1）。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 payment_term / uom_conversion 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.sales_config_guard_service import (
    SalesConfigGuardError,
    SalesConfigGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

DEF_OBJECT = 'control_parameter_def'
VALUE_OBJECT = 'control_parameter_value'
ASSIGNMENT_OBJECT = 'line_type_assignment'
#: 身份对象本身不做守卫，但其写入会让行类型确定缓存失效
DOC_TYPE_OBJECT = 'document_type'
LINE_TYPE_OBJECT = 'line_type'

_CACHE_OBJECTS = (DEF_OBJECT, VALUE_OBJECT, ASSIGNMENT_OBJECT,
                  DOC_TYPE_OBJECT, LINE_TYPE_OBJECT)
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class SalesConfigGuardInterceptor(Interceptor):
    """销售配置写前守卫（3 张配置表 + 删除引用扫描）。"""

    @property
    def priority(self) -> int:
        return 46

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id in _CACHE_OBJECTS:
            # 身份对象（单据类型 / 行类型）本身不校验，但写后要失效确定缓存
            return context.action in _WRITE_ACTIONS
        # 删除：任何对象都可能被 ref 型参数引用（参数取值存在 value 文本列里，
        # 数据库外键表达不了），故统一在删除前扫一次参数定义表（无 ref 参数时开销极小）。
        return context.action == 'crud_delete'

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        params = dict(context.params or {})
        service = SalesConfigGuardService(context.data_source)

        try:
            if context.action == 'crud_delete':
                record_id = context.object_id or params.get('id')
                service.assert_no_ref_values(object_id, record_id)
                return

            # 更新可能是部分字段：与旧行合并还原「更新后的有效行」
            merged = dict(context.old_data or {})
            merged.update(params)
            exclude_id = None
            if context.action == 'crud_update':
                exclude_id = context.object_id or params.get('id')

            if object_id == DEF_OBJECT:
                service.validate_parameter_def_write(merged, exclude_id=exclude_id)
            elif object_id == VALUE_OBJECT:
                service.validate_parameter_value_write(merged, exclude_id=exclude_id)
            elif object_id == ASSIGNMENT_OBJECT:
                service.validate_assignment_write(merged, exclude_id=exclude_id)
        except SalesConfigGuardError as e:
            from meta.core.exceptions import ValidationFailedError

            raise ValidationFailedError(
                message=str(e),
                details=[{
                    'field_name': e.field_name,
                    'rule': e.rule,
                    'message': str(e),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in _CACHE_OBJECTS:
            return
        if context.action not in _WRITE_ACTIONS:
            return
        # 两个解析器都是进程级单例 + 内存缓存，不失效则配置改动要到重启才生效
        try:
            from meta.services.control_parameter_service import (
                get_control_parameter_resolver,
            )
            get_control_parameter_resolver().invalidate()
        except Exception as e:  # 缓存失效失败不应回滚已成功的写入
            logger.warning(f'[sales_config_guard] 参数缓存失效失败: {e}')
        try:
            from meta.services.line_type_service import (
                get_line_type_resolver,
            )
            get_line_type_resolver().invalidate()
        except Exception as e:
            logger.warning(f'[sales_config_guard] 行类型确定缓存失效失败: {e}')
