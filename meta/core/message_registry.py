# -*- coding: utf-8 -*-
"""统一文案注册表（spec-error-warning-framework FR-006）。

单一真源：validation / auth / permission / data / file / system / alert。
默认 locale ``zh_CN``；``en_US`` 与 zh 保持 key 集合对齐（仅保证 key 覆盖）。
缺失 key 先回退 zh_CN，仍缺失则返回 key 本身并记 warning。

用法::

    from meta.core.message_registry import t
    t('validation.field.required', field_name='客户编号')
    t('validation.field.required', locale='en_US', field_name='Customer No.')
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "zh_CN"

_ZH_CN: Dict[str, str] = {
    # ---------- HTTP 状态通用文案 ----------
    "error.http.400": "请求参数有误",
    "error.http.401": "请先登录后再操作",
    "error.http.403": "您没有执行该操作的权限",
    "error.http.404": "请求的资源不存在",
    "error.http.405": "请求方法不被允许",
    "error.http.413": "请求内容过大",
    "error.http.422": "请求数据无法处理",
    "error.http.429": "请求过于频繁，请稍后重试",
    "error.http.500": "系统内部错误，请稍后重试",
    "error.http.503": "服务暂时不可用，请稍后重试",
    # ---------- 认证 / 权限 ----------
    "error.auth.unauthorized": "请先登录后再操作",
    "error.auth.token_expired": "登录已过期，请重新登录",
    "error.auth.token_blacklisted": "登录凭证已失效，请重新登录",
    "error.auth.stale_session": "登录状态已变更，请重新登录",
    "error.auth.service_error": "认证服务异常，请稍后重试",
    "auth.admin_required": "您没有执行此操作的权限，需要管理员权限",
    "auth.session_expired": "会话已过期，请重新登录",
    "user.not_found": "用户不存在",
    "error.permission.forbidden": "您没有执行该操作的权限",
    "error.permission.admin_required": "该操作仅管理员可执行",
    "error.permission.action_permission_denied": "您没有执行该动作的权限",
    # ---------- 数据 / 文件 / 系统 ----------
    "error.data.not_found": "记录不存在或已被删除",
    "error.data.conflict": "数据状态冲突，请刷新后重试",
    "error.data.invalid": "提交的数据不合法",
    "error.file.too_large": "文件过大，请压缩后重试",
    "error.file.unsupported_type": "不支持的文件类型",
    "error.system.internal": "系统内部错误，请稍后重试",
    "error.system.timeout": "请求超时，请稍后重试",
    "error.system.unavailable": "服务暂时不可用，请稍后重试",
    # ---------- 告警 ----------
    "alert.title": "系统告警",
    "alert.level.critical": "严重",
    "alert.level.warning": "警告",
    "alert.summary": "错误码 {error_code} 在 {window} 内发生 {count} 次",
    "alert.recovered": "错误码 {error_code} 已恢复",
    # ---------- 校验：字段 ----------
    "validation.field.required": "{field_name} 不能为空",
    "validation.field.mandatory": "{field_name} 是业务必填字段",
    "validation.field.business_key_required": "{field_name} 是业务关键字，不能为空",
    "validation.field.unique": "{field_name} 已存在",
    "validation.field.pattern_mismatch": "{field_name} 格式不正确，要求匹配 {pattern}",
    "validation.field.max_length_exceeded": "{field_name} 长度不能超过 {max_length} 个字符",
    "validation.field.enum_value_invalid": "{field_name} 的值 '{value}' 不在有效选项中，有效值为：{valid_values}",
    "validation.field.immutable": "{field_name} 创建后不可修改",
    "validation.field.no_delete": "{field_name} 为 {value} 时不可删除",
    "validation.field.unique_scope": "{field_name} 在范围内不唯一",
    "validation.field.conditional_required": "{field_name}为条件必填字段",
    "validation.field.fk_not_found": "引用的{target_name} '{value}' 不存在（字段：{field_name}）",
    "validation.field.value_set_invalid": "{field_name} 含无效取值：{invalid}（须取自{target_name}的既有取值）",
    "validation.field.value_set_shape": "{field_name} 须为取值数组（形如 [\"customer\",\"material\"]）",
    # ---------- 校验：数值范围 ----------
    "validation.numeric.not_a_number": "{field_name}必须是数值",
    "validation.numeric.not_finite": "{field_name}必须是有限数值",
    "validation.numeric.gt": "{field_name}必须大于 {limit}",
    "validation.numeric.gte": "{field_name}不能小于 {limit}",
    "validation.numeric.lt": "{field_name}必须小于 {limit}",
    "validation.numeric.lte": "{field_name}不能大于 {limit}",
    "validation.numeric.decimal_places": "{field_name}最多允许 {max_places} 位小数（当前 {places} 位）",
    # ---------- 校验：对象 / 关联 ----------
    "validation.object.business_key_single": "编号「{field_name}」值已存在：{value}",
    "validation.object.business_key_composite": "编号「{field_names}」组合值已存在：{values}",
    "validation.object.index_unique_single": "唯一性冲突：{field_name} 值已存在",
    "validation.object.index_unique": "唯一性冲突：{field_names} 组合值已存在",
    "validation.object.addability_denied": "{message}",
    "validation.object.deletability_denied": "{message}",
    "validation.object.restrict_on_delete": "无法删除：{child_name} 的 {field_name} 引用了此记录（{count}条）",
    "validation.object.has_children": "无法删除：存在 {count} 个子元素",
    "validation.object.parent_field_immutable": "父元素字段 [{field_name}] 不允许修改",
    "validation.association.source_not_found": "源记录不存在",
    "validation.association.target_not_found": "目标记录不存在",
    "validation.association.readonly": "关联 '{assoc_name}' 为只读，不允许{operation}",
    "validation.association.composition_unassign": "组合关联不支持取消关联，请使用删除子对象",
    "validation.association.cardinality_exceeded": "关联数量超出限制：{assoc_name} 最多允许 {cardinality} 个关联",
    "validation.association.fk_required": "无法取消关联：{field_name} 为必填字段，不能为空",
    "validation.association.permission_denied": "没有权限执行此关联操作",
    "validation.association.already_exists": "关联已存在",
    # ---------- 校验：扩展属性 ----------
    "validation.attribute.attribute_code_conflict_field": "属性编码 '{code}' 与对象 {owner} 的字段重名",
    "validation.attribute.attribute_code_conflict_platform": "属性编码 '{code}' 已被平台层定义占用",
    "validation.attribute.attribute_usage_class_not_allowed": "使用分级 '{usage_class}' 的属性不能启用",
    "validation.attribute.attribute_configurable_data_type": "可配置特征不支持数据类型 '{data_type}'",
    "validation.attribute.attribute_configurable_requires_scope": "可配置特征缺少物料范围声明，暂不能启用",
    "validation.attribute.attribute_scope_object_missing": "范围引用 '{scope_ref}' 不是已注册对象",
    "validation.attribute.attribute_scope_object_not_persistent": "对象 '{scope_ref}' 不能承载属性值",
    "validation.attribute.attribute_scope_item_group_missing": "物料分类 '{scope_ref}' 不存在",
    "validation.attribute.attribute_scope_type_invalid": "未知的范围类型 '{scope_type}'",
    # ---------- 校验：销售订单 ----------
    "validation.sales_order.field_frozen_after_draft": "订单已离开草稿态（{status}），不允许修改 {field_name}",
    "validation.sales_order.order_not_fulfilled": "订单尚未履约完成（当前 {status}），不能关闭",
    "validation.sales_order.order_billing_incomplete": "订单仍有未开票金额（billing_status=partial），不能关闭",
    "validation.sales_order.exchange_rate_frozen": "订单已确认，汇率快照已冻结，不可修改",
    # ---------- 校验：单据类型 ----------
    "validation.document_type.required": "单据类型不能为空",
    "validation.document_type.immutable_after_draft": "单据类型离开草稿后不可修改",
    "validation.document_type.not_found": "单据类型不存在",
    "validation.document_type.scope_mismatch": "单据类型不属于{object_name}（须 scope_bo={object_name} / level=header）",
    "validation.document_type.inactive": "单据类型已停用",
    # ---------- 校验：配置实例 ----------
    "validation.configuration.replaced_immutable": "已被替代的实例不再接受修改",
    "validation.configuration.status_transition_invalid": "状态不能从 {old_status} 变为 {status}",
    "validation.configuration.frozen_locked": "已冻结实例不可修改: {fields}",
    "validation.configuration.hash_immutable": "config_hash 在 solved 后不可修改；变更请生成新实例",
    "validation.configuration.delete_locked": "{status} 状态的配置实例不可删除",
}

_EN_US: Dict[str, str] = {
    "error.http.400": "Bad request",
    "error.http.401": "Please log in first",
    "error.http.403": "You do not have permission to perform this operation",
    "error.http.404": "The requested resource was not found",
    "error.http.405": "Method not allowed",
    "error.http.413": "Request entity too large",
    "error.http.422": "The request data could not be processed",
    "error.http.429": "Too many requests, please try again later",
    "error.http.500": "Internal server error, please try again later",
    "error.http.503": "Service temporarily unavailable, please try again later",
    "error.auth.unauthorized": "Please log in first",
    "error.auth.token_expired": "Your session has expired, please log in again",
    "error.auth.token_blacklisted": "Your credentials are no longer valid, please log in again",
    "error.auth.stale_session": "Your session has changed, please log in again",
    "error.auth.service_error": "Authentication service error, please try again later",
    "auth.admin_required": "You do not have permission to perform this operation; administrator privileges are required",
    "auth.session_expired": "The session has expired, please log in again",
    "user.not_found": "User does not exist",
    "error.permission.forbidden": "You do not have permission to perform this operation",
    "error.permission.admin_required": "Only administrators can perform this operation",
    "error.permission.action_permission_denied": "You do not have permission to run this action",
    "error.data.not_found": "The record does not exist or has been deleted",
    "error.data.conflict": "Data state conflict, please refresh and retry",
    "error.data.invalid": "The submitted data is invalid",
    "error.file.too_large": "The file is too large, please compress it and retry",
    "error.file.unsupported_type": "Unsupported file type",
    "error.system.internal": "Internal server error, please try again later",
    "error.system.timeout": "Request timed out, please try again later",
    "error.system.unavailable": "Service temporarily unavailable, please try again later",
    "alert.title": "System alert",
    "alert.level.critical": "critical",
    "alert.level.warning": "warning",
    "alert.summary": "Error {error_code} occurred {count} times within {window}",
    "alert.recovered": "Error {error_code} has recovered",
    "validation.field.required": "{field_name} is required",
    "validation.field.mandatory": "{field_name} is a mandatory business field",
    "validation.field.business_key_required": "{field_name} is a business key and cannot be empty",
    "validation.field.unique": "{field_name} already exists",
    "validation.field.pattern_mismatch": "{field_name} has an invalid format, expected to match {pattern}",
    "validation.field.max_length_exceeded": "{field_name} must not exceed {max_length} characters",
    "validation.field.enum_value_invalid": "Value '{value}' of {field_name} is not in the allowed options: {valid_values}",
    "validation.field.immutable": "{field_name} cannot be changed after creation",
    "validation.field.no_delete": "{field_name} cannot be deleted when it is {value}",
    "validation.field.unique_scope": "{field_name} is not unique within its scope",
    "validation.field.conditional_required": "{field_name} is conditionally required",
    "validation.field.fk_not_found": "Referenced {target_name} '{value}' does not exist (field: {field_name})",
    "validation.field.value_set_invalid": "{field_name} contains invalid values: {invalid} (must come from existing {target_name} values)",
    "validation.field.value_set_shape": "{field_name} must be an array of values",
    "validation.numeric.not_a_number": "{field_name} must be a number",
    "validation.numeric.not_finite": "{field_name} must be a finite number",
    "validation.numeric.gt": "{field_name} must be greater than {limit}",
    "validation.numeric.gte": "{field_name} must be at least {limit}",
    "validation.numeric.lt": "{field_name} must be less than {limit}",
    "validation.numeric.lte": "{field_name} must be at most {limit}",
    "validation.numeric.decimal_places": "{field_name} allows at most {max_places} decimal places (currently {places})",
    "validation.object.business_key_single": "Business key '{field_name}' value already exists: {value}",
    "validation.object.business_key_composite": "Business key '{field_names}' combination already exists: {values}",
    "validation.object.index_unique_single": "Unique constraint violation: {field_name} value already exists",
    "validation.object.index_unique": "Unique constraint violation: {field_names} combination already exists",
    "validation.object.addability_denied": "{message}",
    "validation.object.deletability_denied": "{message}",
    "validation.object.restrict_on_delete": "Cannot delete: {field_name} of {child_name} references this record ({count} rows)",
    "validation.object.has_children": "Cannot delete: {count} child elements exist",
    "validation.object.parent_field_immutable": "Parent field [{field_name}] cannot be changed",
    "validation.association.source_not_found": "Source record not found",
    "validation.association.target_not_found": "Target record not found",
    "validation.association.readonly": "Association '{assoc_name}' is read-only, {operation} is not allowed",
    "validation.association.composition_unassign": "Composition associations cannot be unassigned; delete the child instead",
    "validation.association.cardinality_exceeded": "Association limit exceeded: {assoc_name} allows at most {cardinality} links",
    "validation.association.fk_required": "Cannot unassign: {field_name} is required",
    "validation.association.permission_denied": "No permission to perform this association operation",
    "validation.association.already_exists": "The association already exists",
    "validation.attribute.attribute_code_conflict_field": "Attribute code '{code}' conflicts with a field of {owner}",
    "validation.attribute.attribute_code_conflict_platform": "Attribute code '{code}' is already used by a platform definition",
    "validation.attribute.attribute_usage_class_not_allowed": "Attributes with usage class '{usage_class}' cannot be enabled",
    "validation.attribute.attribute_configurable_data_type": "Configurable attributes do not support data type '{data_type}'",
    "validation.attribute.attribute_configurable_requires_scope": "Configurable attribute is missing an item scope declaration",
    "validation.attribute.attribute_scope_object_missing": "Scope reference '{scope_ref}' is not a registered object",
    "validation.attribute.attribute_scope_object_not_persistent": "Object '{scope_ref}' cannot hold attribute values",
    "validation.attribute.attribute_scope_item_group_missing": "Item group '{scope_ref}' does not exist",
    "validation.attribute.attribute_scope_type_invalid": "Unknown scope type '{scope_type}'",
    "validation.sales_order.field_frozen_after_draft": "Order has left draft ({status}); {field_name} cannot be changed",
    "validation.sales_order.order_not_fulfilled": "Order fulfillment is incomplete ({status}); it cannot be closed",
    "validation.sales_order.order_billing_incomplete": "Order still has uninvoiced amounts (billing_status=partial) and cannot be closed",
    "validation.sales_order.exchange_rate_frozen": "Order is confirmed; the exchange-rate snapshot is frozen",
    "validation.document_type.required": "Document type is required",
    "validation.document_type.immutable_after_draft": "Document type cannot be changed after leaving draft",
    "validation.document_type.not_found": "Document type does not exist",
    "validation.document_type.scope_mismatch": "Document type does not belong to {object_name} (scope_bo={object_name} / level=header)",
    "validation.document_type.inactive": "Document type is inactive",
    "validation.configuration.replaced_immutable": "Replaced instances can no longer be modified",
    "validation.configuration.status_transition_invalid": "Status cannot change from {old_status} to {status}",
    "validation.configuration.frozen_locked": "Frozen instance cannot be modified: {fields}",
    "validation.configuration.hash_immutable": "config_hash cannot be changed after solved; create a new instance instead",
    "validation.configuration.delete_locked": "Configuration instance in status {status} cannot be deleted",
}


class MessageRegistry:
    """文案注册表（进程级单例）。"""

    _messages: Dict[str, Dict[str, str]] = {
        DEFAULT_LOCALE: _ZH_CN.copy(),
        "en_US": _EN_US.copy(),
    }
    _locale: str = DEFAULT_LOCALE

    @classmethod
    def get(cls, key: str, locale: Optional[str] = None, **params) -> str:
        """取文案；缺失先回退 zh_CN，仍缺失返回 key 并记 warning。"""
        target = locale or cls._locale
        template = cls._messages.get(target, {}).get(key)
        if template is None:
            template = cls._messages.get(DEFAULT_LOCALE, {}).get(key)
        if template is None:
            logger.warning("[MessageRegistry] 未注册文案 key: %s (locale=%s)",
                           key, target)
            return key
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            logger.warning("[MessageRegistry] 文案参数缺失 key=%s params=%s",
                           key, sorted(params))
            return template

    @classmethod
    def register(cls, locale: str, messages: Dict[str, str]) -> None:
        cls._messages.setdefault(locale, {}).update(messages)

    @classmethod
    def set_locale(cls, locale: str) -> None:
        cls._locale = locale

    @classmethod
    def get_locale(cls) -> str:
        return cls._locale

    @classmethod
    def keys(cls, locale: Optional[str] = None) -> set:
        return set(cls._messages.get(locale or cls._locale, {}))

    @classmethod
    def locales(cls) -> set:
        return set(cls._messages)


def t(key: str, locale: Optional[str] = None, **params) -> str:
    """模块级别名，便于守卫/服务最小改动接入。"""
    return MessageRegistry.get(key, locale=locale, **params)


# 兼容旧名（validation_messages.ValidationMessageRegistry 内部委托）
ValidationMessageRegistry = MessageRegistry