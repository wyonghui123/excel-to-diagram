# -*- coding: utf-8 -*-
"""
规则读取统一入口（RuleProvider）

背景
----
历史上业务代码直接遍历 ``meta_object.rules``，散落在 API / 服务 / 拦截器等多处。
一旦要求"规则支持在线配置"（规则不再只来自元数据定义文件），每个读取点都要改。

本模块提供唯一读取入口：

- 一期（透传实现）：行为与历史完全一致——不排序、不过滤、不拷贝语义，
  用于逐点替换 ``for rule in meta_obj.rules``。
- 后期（在线配置）：只需替换 RuleProvider 的实现（文件 / DB / 缓存 / 热加载），
  调用方零改动。

读取语义约定
------------
- ``get_rules``          原样返回（保序、含未启用），对应历史行为，禁止加过滤。
- ``get_enabled_rules``  仅 ``enabled=True``，且保持原顺序。
- ``get_rules_by_type``  按 ``rule_type`` 过滤，且保持原顺序。

注意：不要用 ``get_rules`` 承担过滤/排序职责，否则会改变既有调用点的行为。
"""

from typing import List, Optional, Any

from meta.core.models import MetaObject, MetaRule
from meta.core.models_enums import RuleType


class RuleProvider:
    """规则读取提供者（一期：直读元对象）"""

    def get_rules(self, meta_object: Optional[MetaObject]) -> List[MetaRule]:
        """原样返回对象的全部规则（保序、不过滤）。

        这是历史行为的等价替换，等价于 ``meta_object.rules or []``。
        """
        if not meta_object:
            return []
        return list(meta_object.rules or [])

    def get_enabled_rules(self, meta_object: Optional[MetaObject]) -> List[MetaRule]:
        """返回已启用的规则（保持原顺序）"""
        return [rule for rule in self.get_rules(meta_object) if getattr(rule, 'enabled', True)]

    def get_rules_by_type(self, meta_object: Optional[MetaObject],
                          rule_type: RuleType) -> List[MetaRule]:
        """按规则类型过滤（保持原顺序）"""
        return [rule for rule in self.get_rules(meta_object)
                if getattr(rule, 'rule_type', None) == rule_type]

    def get_default_rules(self, meta_object: Optional[MetaObject]) -> List[MetaRule]:
        """仅属性确定（默认值）类规则（保持原顺序）

        [规则模型 T-06 2026-10-03]
        按 ``rule_type == RuleType.DEFAULT`` 判定，兼容 YAML 解析出的
        ``MetaDefaultRule`` 与其它来源构造的等价对象。
        """
        return self.get_rules_by_type(meta_object, RuleType.DEFAULT)


_default_provider: Optional[RuleProvider] = None


def get_rule_provider() -> RuleProvider:
    """获取全局规则读取提供者"""
    global _default_provider
    if _default_provider is None:
        _default_provider = RuleProvider()
    return _default_provider


def set_rule_provider(provider: Optional[RuleProvider]) -> None:
    """替换全局提供者（供测试注入 / 后期切换在线配置实现）"""
    global _default_provider
    _default_provider = provider
