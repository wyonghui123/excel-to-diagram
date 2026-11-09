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

    def get_rules_by_trigger(self, meta_object: Optional[MetaObject],
                             trigger: Any) -> List[MetaRule]:
        """按触发时机过滤，且仅取已启用规则（保持原顺序）

        [SSOT 2026-10-29] 语义与 ``MetaObject.get_rules_by_trigger`` 完全一致
        （``trigger in rule.triggers and rule.enabled``），抽到本入口是为了让
        BO 保存热路径 ``RuleEngine.execute_rules`` 也走统一读取门面。
        """
        return [rule for rule in self.get_rules(meta_object)
                if trigger in getattr(rule, 'triggers', [])
                and getattr(rule, 'enabled', True)]

    def get_default_rules(self, meta_object: Optional[MetaObject]) -> List[MetaRule]:
        """仅属性确定（默认值）类规则（保持原顺序）

        [规则模型 T-06 2026-10-03]
        按 ``rule_type == RuleType.DEFAULT`` 判定，兼容 YAML 解析出的
        ``MetaDefaultRule`` 与其它来源构造的等价对象。
        """
        return self.get_rules_by_type(meta_object, RuleType.DEFAULT)

    # ------------------------------------------------------------------
    # DB 规则门面（FR-010）：业务调用方不直连各域 store
    # 懒 import 以避免 rule_provider ↔ store/DAO 的循环依赖。
    # ------------------------------------------------------------------

    def list_doc_flow_rules(self, data_source) -> list:
        """读取全部单据流规则（DB 载体）。"""
        from meta.core.doc_flow_rule_store import list_rules
        return list_rules(data_source)

    def get_doc_flow_rule(self, data_source, rule_id: str) -> Optional[dict]:
        """按 rule_id 读取单据流规则（DB 载体）。"""
        from meta.core.doc_flow_rule_store import get_rule
        return get_rule(data_source, rule_id)

    def upsert_doc_flow_rules(self, data_source, rules) -> int:
        """写入/更新单据流规则（DB 载体）。"""
        from meta.core.doc_flow_rule_store import upsert_rules
        return upsert_rules(data_source, rules)

    def ensure_doc_flow_rule_table(self, data_source) -> None:
        """确保单据流规则表存在。"""
        from meta.core.doc_flow_rule_store import ensure_doc_flow_rule_table
        ensure_doc_flow_rule_table(data_source)

    def set_doc_flow_rule_status(self, data_source, rule_id: str, status: str) -> bool:
        """启停单据流规则。"""
        from meta.core.doc_flow_rule_store import set_rule_status
        return set_rule_status(data_source, rule_id, status)

    def list_permission_rules(self, db_path: str, resource_type: Optional[str] = None):
        """读取权限规则（DB 载体）。"""
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO
        return PermissionRuleV2DAO(db_path).list_all(resource_type)


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


def list_doc_flow_rules(data_source) -> list:
    """模块级便捷函数：单据流规则全量读取。"""
    return get_rule_provider().list_doc_flow_rules(data_source)


def get_doc_flow_rule(data_source, rule_id: str) -> Optional[dict]:
    """模块级便捷函数：单据流规则读取。"""
    return get_rule_provider().get_doc_flow_rule(data_source, rule_id)


def upsert_doc_flow_rules(data_source, rules) -> int:
    """模块级便捷函数：单据流规则写入。"""
    return get_rule_provider().upsert_doc_flow_rules(data_source, rules)


def ensure_doc_flow_rule_table(data_source) -> None:
    """模块级便捷函数：单据流规则表初始化。"""
    return get_rule_provider().ensure_doc_flow_rule_table(data_source)


def set_doc_flow_rule_status(data_source, rule_id: str, status: str) -> bool:
    """模块级便捷函数：单据流规则启停。"""
    return get_rule_provider().set_doc_flow_rule_status(data_source, rule_id, status)


def list_permission_rules(db_path: str, resource_type: Optional[str] = None):
    """模块级便捷函数：权限规则读取。"""
    return get_rule_provider().list_permission_rules(db_path, resource_type)
