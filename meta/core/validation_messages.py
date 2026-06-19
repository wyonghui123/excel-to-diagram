# -*- coding: utf-8 -*-
"""
校验消息注册表 - 支持 i18n 的校验消息管理

所有校验消息通过 ValidationMessageRegistry 获取，不直接硬编码。
消息 key 格式：validation.{category}.{rule}
默认 locale 为 zh_CN，所有默认消息为中文。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class ValidationDetail:
    field_id: str = ""
    field_name: str = ""
    rule: str = ""
    message: str = ""
    i18n_key: str = ""
    params: Dict[str, Any] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "rule": self.rule,
            "message": self.message,
            "i18n_key": self.i18n_key,
            "params": self.params,
        }


_ZH_CN_MESSAGES = {
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
    "validation.field.fk_not_found": "引用的{target_name} '{value}' 不存在（字段：{field_name}）",
    # [NEW v1.2.13 2026-06-19] 区分单/多字段业务关键字
    "validation.object.business_key_single": "【业务关键字】{field_name} 值已存在：{value}",
    "validation.object.business_key_composite": "【业务关键字】{field_names} 组合值已存在：{values}",
    # [SIMPLIFIED 2026-06-15 BMRD] 移除括号中的 index_name (技术细节, 用户不关心)
    # [NEW v1.2.13 2026-06-19] 区分单/多字段唯一索引
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
}


class ValidationMessageRegistry:
    _messages: Dict[str, Dict[str, str]] = {"zh_CN": _ZH_CN_MESSAGES.copy()}
    _locale: str = "zh_CN"

    @classmethod
    def get(cls, key: str, **params) -> str:
        template = cls._messages.get(cls._locale, {}).get(key)
        if template is None:
            template = cls._messages.get("zh_CN", {}).get(key, key)
        try:
            return template.format(**params)
        except KeyError:
            return template

    @classmethod
    def register_messages(cls, locale: str, messages: Dict[str, str]):
        if locale not in cls._messages:
            cls._messages[locale] = {}
        cls._messages[locale].update(messages)

    @classmethod
    def set_locale(cls, locale: str):
        cls._locale = locale

    @classmethod
    def get_locale(cls) -> str:
        return cls._locale
