# -*- coding: utf-8 -*-
"""
元数据驱动的索引规则引擎

设计参考：
- SAP S/4HANA: CDS @AbapCatalog.index 注解自动推导索引
- Salesforce: IsIndexed 字段标记自动创建 MT_Indexes 记录
- Palantir: Ontology indexed/searchable 属性驱动索引创建
- DataHub: schema-first 元数据模型驱动索引配置

核心职责：
1. 从 MetaObject 的语义标注自动推导索引（规则引擎）
2. 从 MetaField 的 index_hint 推导字段级索引
3. 合并 YAML 显式定义 + 规则推导 + 查询分析推荐的索引
4. 去重和优先级排序
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from meta.core.models import (
    MetaObject,
    MetaField,
    MetaIndex,
    MetaRelation,
    IndexType,
    IndexPriority,
    IndexSource,
    IndexHint,
    FieldStorage,
    FieldType,
    RelationType,
)

logger = logging.getLogger(__name__)


@dataclass
class IndexRule:
    """索引推导规则
    
    借鉴 Salesforce 的 IsIndexed 机制和 SAP CDS 注解体系，
    每条规则对应一种从元数据语义到索引的映射关系。
    """
    rule_id: str
    name: str
    description: str
    priority: IndexPriority = IndexPriority.MEDIUM
    index_type: IndexType = IndexType.BTREE
    unique: bool = False
    auto_create: bool = True


class IndexRuleEngine:
    """索引规则引擎
    
    从元数据模型的语义标注自动推导索引定义。
    
    推导策略（按优先级从高到低）：
    
    1. 显式索引（source=SCHEMA）
       YAML 中 indexes 段显式定义的索引，优先级最高，不会被规则覆盖
    
    2. 字段级索引提示（index_hint）
       字段语义中的 index_hint 标记，类似 Salesforce IsIndexed
    
    3. 语义标注推导
       - business_key=True → 唯一索引（SAP: @ObjectModel.businessKey）
       - parent_key=True → 外键索引（SAP: @ObjectModel.parentKey）
       - display_name=True → 普通索引（SAP: @UI.lineItem）
       - context_field=True → 高优先级索引（高频筛选字段）
       - readonly_always=True + required=True → 索引（不变的高频筛选字段）
    
    4. 关系推导
       - PARENT_CHILD 关系 → 外键索引
       - REFERENCE 关系 → 外键索引
    
    5. UI筛选器推导
       - ui_view_config.filter 中出现的字段 → 筛选索引
       - ui_view_config.list.defaultSort 字段 → 排序索引
    
    6. 复合索引推导
       - 层级字段组合（version_id + domain_id + ...）→ 复合索引
       - 筛选器依赖链 → 复合索引
    """
    
    def __init__(self):
        self._rule_registry: Dict[str, IndexRule] = {}
        self._register_default_rules()
    
    def _register_default_rules(self):
        """注册默认索引推导规则"""
        rules = [
            IndexRule(
                rule_id="business_key_unique",
                name="业务键唯一索引",
                description="business_key=True 的字段自动创建唯一索引（借鉴 SAP @ObjectModel.businessKey）",
                priority=IndexPriority.HIGH,
                index_type=IndexType.UNIQUE,
                unique=True,
            ),
            IndexRule(
                rule_id="parent_key_fk",
                name="父键外键索引",
                description="parent_key=True 的字段自动创建外键索引（借鉴 SAP @ObjectModel.parentKey）",
                priority=IndexPriority.HIGH,
                index_type=IndexType.BTREE,
            ),
            IndexRule(
                rule_id="context_field_index",
                name="上下文字段索引",
                description="context_field=True 的字段自动创建高优先级索引（高频筛选字段）",
                priority=IndexPriority.HIGH,
                index_type=IndexType.BTREE,
            ),
            IndexRule(
                rule_id="display_name_index",
                name="显示名称索引",
                description="display_name=True 的字段自动创建普通索引（借鉴 SAP @UI.lineItem）",
                priority=IndexPriority.MEDIUM,
                index_type=IndexType.BTREE,
            ),
            IndexRule(
                rule_id="relation_fk_index",
                name="关系外键索引",
                description="PARENT_CHILD / REFERENCE 关系自动创建外键索引",
                priority=IndexPriority.HIGH,
                index_type=IndexType.BTREE,
            ),
            IndexRule(
                rule_id="filter_field_index",
                name="筛选器字段索引",
                description="UI 筛选器中出现的字段自动创建索引",
                priority=IndexPriority.MEDIUM,
                index_type=IndexType.BTREE,
            ),
            IndexRule(
                rule_id="sort_field_index",
                name="排序字段索引",
                description="UI 列表默认排序字段自动创建索引",
                priority=IndexPriority.LOW,
                index_type=IndexType.BTREE,
            ),
            IndexRule(
                rule_id="hierarchy_composite",
                name="层级复合索引",
                description="层级字段组合创建复合索引（version_id + parent_id）",
                priority=IndexPriority.HIGH,
                index_type=IndexType.COMPOSITE,
            ),
            IndexRule(
                rule_id="searchable_fts",
                name="可搜索字段全文索引",
                description="render_hints.searchable=True 的文本字段创建全文索引",
                priority=IndexPriority.MEDIUM,
                index_type=IndexType.FTS,
            ),
        ]
        
        for rule in rules:
            self._rule_registry[rule.rule_id] = rule
    
    def derive_indexes(self, meta_obj: MetaObject) -> List[MetaIndex]:
        """从元数据对象推导所有索引
        
        合并策略：
        1. 保留 YAML 中显式定义的索引
        2. 从语义标注推导新索引
        3. 去重（相同字段的索引只保留优先级最高的）
        4. 按优先级排序
        """
        if meta_obj.object_type in ["view", "virtual"]:
            return list(meta_obj.indexes)
        
        all_indexes: List[MetaIndex] = []
        
        explicit_indexes = list(meta_obj.indexes)
        for idx in explicit_indexes:
            if idx.source == IndexSource.SCHEMA:
                all_indexes.append(idx)
        
        derived = self._derive_from_index_hints(meta_obj)
        all_indexes.extend(derived)
        
        derived = self._derive_from_semantics(meta_obj)
        all_indexes.extend(derived)
        
        derived = self._derive_from_relations(meta_obj)
        all_indexes.extend(derived)
        
        derived = self._derive_from_ui_config(meta_obj)
        all_indexes.extend(derived)
        
        derived = self._derive_composite_indexes(meta_obj)
        all_indexes.extend(derived)
        
        all_indexes = self._deduplicate_indexes(all_indexes, meta_obj)
        
        all_indexes.sort(key=lambda idx: self._priority_order(idx.priority))
        
        return all_indexes
    
    def _derive_from_index_hints(self, meta_obj: MetaObject) -> List[MetaIndex]:
        """从字段级 index_hint 推导索引（借鉴 Salesforce IsIndexed）"""
        indexes = []
        
        for f in meta_obj.get_persistent_fields():
            if not f.semantics.index_hint:
                continue
            
            hint = f.semantics.index_hint
            if not hint.indexed and not hint.unique:
                continue
            
            idx_name = hint.unique and "uidx_{0}_{1}".format(meta_obj.table_name, f.db_column) or "idx_{0}_{1}".format(meta_obj.table_name, f.db_column)
            
            indexes.append(MetaIndex(
                fields=[f.id],
                name=idx_name,
                unique=hint.unique,
                description="字段级索引提示推导: {0}".format(f.id),
                index_type=hint.unique and IndexType.UNIQUE or IndexType.BTREE,
                priority=IndexPriority(hint.priority),
                source=IndexSource.RULE_ENGINE,
                auto_create=hint.auto_create,
                db_columns=[f.db_column],
            ))
        
        return indexes
    
    def _get_fields_in_composite_unique(self, meta_obj: MetaObject) -> set:
        """获取已包含在复合唯一索引中的字段ID集合
        
        如果一个 business_key 字段已经属于某个复合唯一索引（如 version_id + code），
        则不需要再为它单独创建单列唯一索引。
        """
        fields_in_composite = set()
        for idx in meta_obj.indexes:
            if idx.unique and len(idx.fields) > 1:
                for field_id in idx.fields:
                    fields_in_composite.add(field_id)
        return fields_in_composite
    
    def _get_equivalent_unique_fields(self, meta_obj: MetaObject) -> set:
        """获取与复合唯一索引字段等价的冗余字段ID集合
        
        如果一个 business_key 字段是复合唯一索引中某个字段的冗余副本
        （如 source_code 是 source_bo_id 的冗余），则不需要为它单独创建唯一索引。
        
        检测方式：
        1. 字段有 redundancy.source_field 指向复合唯一索引中的字段
        2. 字段有 resolve_from_field 指向复合唯一索引中的字段
        """
        fields_in_composite = self._get_fields_in_composite_unique(meta_obj)
        equivalent = set()
        
        field_map = {f.id: f for f in meta_obj.fields}
        
        for f in meta_obj.fields:
            sem = f.semantics
            if not getattr(sem, 'business_key', False):
                continue
            
            redundancy = getattr(sem, 'redundancy', {}) or {}
            source_field = redundancy.get('source_field', '')
            if source_field and source_field in fields_in_composite:
                equivalent.add(f.id)
            
            resolve_from = getattr(sem, 'resolve_from_field', '')
            if resolve_from and resolve_from in fields_in_composite:
                equivalent.add(f.id)
        
        return equivalent
    
    def _derive_from_semantics(self, meta_obj: MetaObject) -> List[MetaIndex]:
        """从语义标注推导索引（借鉴 SAP CDS 注解体系）"""
        indexes = []
        
        existing_unique_fields = self._get_fields_in_composite_unique(meta_obj)
        equivalent_fields = self._get_equivalent_unique_fields(meta_obj)
        
        for f in meta_obj.get_persistent_fields():
            sem = f.semantics
            
            if sem.business_key and not f.unique:
                if f.id in existing_unique_fields:
                    pass
                elif getattr(sem, 'virtual', False):
                    pass
                elif f.id in equivalent_fields:
                    pass
                else:
                    rule = self._rule_registry["business_key_unique"]
                    idx_name = "uidx_{0}_{1}".format(meta_obj.table_name, f.db_column)
                    indexes.append(MetaIndex(
                        fields=[f.id],
                        name=idx_name,
                        unique=True,
                        description=rule.description,
                        index_type=IndexType.UNIQUE,
                        priority=rule.priority,
                        source=IndexSource.RULE_ENGINE,
                        auto_create=rule.auto_create,
                        db_columns=[f.db_column],
                    ))
            
            if sem.parent_key:
                rule = self._rule_registry["parent_key_fk"]
                idx_name = "idx_{0}_{1}".format(meta_obj.table_name, f.db_column)
                indexes.append(MetaIndex(
                    fields=[f.id],
                    name=idx_name,
                    unique=False,
                    description=rule.description,
                    index_type=IndexType.BTREE,
                    priority=rule.priority,
                    source=IndexSource.RULE_ENGINE,
                    auto_create=rule.auto_create,
                    db_columns=[f.db_column],
                ))
            
            if sem.context_field:
                rule = self._rule_registry["context_field_index"]
                idx_name = "idx_{0}_{1}".format(meta_obj.table_name, f.db_column)
                indexes.append(MetaIndex(
                    fields=[f.id],
                    name=idx_name,
                    unique=False,
                    description=rule.description,
                    index_type=IndexType.BTREE,
                    priority=rule.priority,
                    source=IndexSource.RULE_ENGINE,
                    auto_create=rule.auto_create,
                    db_columns=[f.db_column],
                ))
            
            if sem.display_name and not sem.business_key and not sem.parent_key:
                rule = self._rule_registry["display_name_index"]
                idx_name = "idx_{0}_{1}".format(meta_obj.table_name, f.db_column)
                indexes.append(MetaIndex(
                    fields=[f.id],
                    name=idx_name,
                    unique=False,
                    description=rule.description,
                    index_type=IndexType.BTREE,
                    priority=rule.priority,
                    source=IndexSource.RULE_ENGINE,
                    auto_create=rule.auto_create,
                    db_columns=[f.db_column],
                ))
            
            if f.ui and hasattr(f.ui, 'render_hints') and f.ui.render_hints:
                if f.ui.render_hints.searchable and f.field_type in [FieldType.STRING, FieldType.TEXT]:
                    rule = self._rule_registry["searchable_fts"]
                    indexes.append(MetaIndex(
                        fields=[f.id],
                        name="fts_{0}_{1}".format(meta_obj.table_name, f.db_column),
                        unique=False,
                        description=rule.description,
                        index_type=IndexType.FTS,
                        priority=rule.priority,
                        source=IndexSource.RULE_ENGINE,
                        auto_create=False,
                        db_columns=[f.db_column],
                    ))
        
        return indexes
    
    def _derive_from_relations(self, meta_obj: MetaObject) -> List[MetaIndex]:
        """从关系定义推导外键索引（借鉴 Salesforce MT_Indexes 机制）"""
        indexes = []
        
        for rel in meta_obj.relations:
            if rel.relation_type in [RelationType.PARENT_CHILD, RelationType.REFERENCE]:
                if rel.cardinality in ["N:1", "1:1"]:
                    fk_column = "{0}_id".format(rel.target_object)
                    
                    field = None
                    for f in meta_obj.fields:
                        if f.db_column == fk_column:
                            field = f
                            break
                    
                    if field and field.storage == FieldStorage.STORED:
                        rule = self._rule_registry["relation_fk_index"]
                        idx_name = "idx_{0}_{1}".format(meta_obj.table_name, fk_column)
                        indexes.append(MetaIndex(
                            fields=[field.id],
                            name=idx_name,
                            unique=False,
                            description=rule.description + ": {0} -> {1}".format(meta_obj.id, rel.target_object),
                            index_type=IndexType.BTREE,
                            priority=rule.priority,
                            source=IndexSource.RULE_ENGINE,
                            auto_create=rule.auto_create,
                            db_columns=[fk_column],
                        ))
        
        return indexes
    
    def _derive_from_ui_config(self, meta_obj: MetaObject) -> List[MetaIndex]:
        """从 UI 配置推导筛选和排序索引（借鉴 Palantir filterable/sortable）"""
        indexes = []
        indexed_fields: Set[str] = set()
        
        for idx in meta_obj.indexes:
            for f in idx.fields:
                indexed_fields.add(f)
        
        for idx in self._derive_from_semantics(meta_obj):
            for f in idx.fields:
                indexed_fields.add(f)
        
        ui_config = meta_obj.ui_view_config
        if not ui_config:
            return indexes
        
        filter_config = ui_config.filter
        if filter_config and hasattr(filter_config, 'filters'):
            for f_def in filter_config.filters:
                f_key = f_def.key if hasattr(f_def, 'key') else ""
                if f_key and f_key not in indexed_fields:
                    field = meta_obj.get_field(f_key)
                    if field and field.storage == FieldStorage.STORED and field.db_column:
                        rule = self._rule_registry["filter_field_index"]
                        idx_name = "idx_{0}_{1}".format(meta_obj.table_name, field.db_column)
                        indexes.append(MetaIndex(
                            fields=[f_key],
                            name=idx_name,
                            unique=False,
                            description=rule.description + ": {0}".format(f_key),
                            index_type=IndexType.BTREE,
                            priority=rule.priority,
                            source=IndexSource.RULE_ENGINE,
                            auto_create=rule.auto_create,
                            db_columns=[field.db_column],
                        ))
                        indexed_fields.add(f_key)
        
        list_config = ui_config.list
        if list_config and hasattr(list_config, 'defaultSort') and list_config.defaultSort:
            sort_str = list_config.defaultSort
            if isinstance(sort_str, dict):
                sort_field = sort_str.get('field', '')
            else:
                sort_field = sort_str.split()[0] if sort_str else ""
            if sort_field and sort_field not in indexed_fields:
                field = meta_obj.get_field(sort_field)
                if field and field.storage == FieldStorage.STORED and field.db_column:
                    rule = self._rule_registry["sort_field_index"]
                    idx_name = "idx_{0}_{1}".format(meta_obj.table_name, field.db_column)
                    indexes.append(MetaIndex(
                        fields=[sort_field],
                        name=idx_name,
                        unique=False,
                        description=rule.description + ": {0}".format(sort_field),
                        index_type=IndexType.BTREE,
                        priority=rule.priority,
                        source=IndexSource.RULE_ENGINE,
                        auto_create=rule.auto_create,
                        db_columns=[field.db_column],
                    ))
        
        return indexes
    
    def _derive_composite_indexes(self, meta_obj: MetaObject) -> List[MetaIndex]:
        """推导复合索引（借鉴 Palantir Ontology 多属性索引）
        
        策略：
        - 层级对象：version_id + parent_id 复合索引
        - 关系对象：version_id + source_bo_id / target_bo_id 复合索引
        """
        indexes = []
        rule = self._rule_registry["hierarchy_composite"]
        
        persistent_fields = {f.db_column: f for f in meta_obj.get_persistent_fields()}
        
        has_version = "version_id" in persistent_fields
        
        if not has_version:
            return indexes
        
        parent_fk_fields = []
        for f in meta_obj.get_persistent_fields():
            if f.semantics.parent_key and f.db_column != "version_id":
                parent_fk_fields.append(f)
        
        for pf in parent_fk_fields:
            composite_name = "idx_{0}_version_{1}".format(meta_obj.table_name, pf.db_column)
            indexes.append(MetaIndex(
                fields=["version_id", pf.id],
                name=composite_name,
                unique=False,
                description=rule.description + ": version_id + {0}".format(pf.db_column),
                index_type=IndexType.COMPOSITE,
                priority=rule.priority,
                source=IndexSource.RULE_ENGINE,
                auto_create=rule.auto_create,
                db_columns=["version_id", pf.db_column],
            ))
        
        if meta_obj.id == "relationship":
            if "source_bo_id" in persistent_fields:
                indexes.append(MetaIndex(
                    fields=["version_id", "source_bo_id"],
                    name="idx_{0}_version_source".format(meta_obj.table_name),
                    unique=False,
                    description="关系表版本+源端复合索引",
                    index_type=IndexType.COMPOSITE,
                    priority=IndexPriority.HIGH,
                    source=IndexSource.RULE_ENGINE,
                    auto_create=True,
                    db_columns=["version_id", "source_bo_id"],
                ))
            if "target_bo_id" in persistent_fields:
                indexes.append(MetaIndex(
                    fields=["version_id", "target_bo_id"],
                    name="idx_{0}_version_target".format(meta_obj.table_name),
                    unique=False,
                    description="关系表版本+目标端复合索引",
                    index_type=IndexType.COMPOSITE,
                    priority=IndexPriority.HIGH,
                    source=IndexSource.RULE_ENGINE,
                    auto_create=True,
                    db_columns=["version_id", "target_bo_id"],
                ))
        
        return indexes
    
    def _deduplicate_indexes(self, indexes: List[MetaIndex], meta_obj: MetaObject) -> List[MetaIndex]:
        """去重索引
        
        去重规则：
        1. 相同 db_columns 的索引只保留一个
        2. 显式定义（SCHEMA）优先于规则推导（RULE_ENGINE）
        3. 高优先级覆盖低优先级
        4. 唯一索引覆盖普通索引
        """
        seen: Dict[str, MetaIndex] = {}
        
        for idx in indexes:
            columns_key = ",".join(idx.db_columns) if idx.db_columns else ",".join(idx.fields)
            
            if columns_key in seen:
                existing = seen[columns_key]
                
                if self._should_replace(existing, idx):
                    seen[columns_key] = idx
            else:
                seen[columns_key] = idx
        
        return list(seen.values())
    
    def _should_replace(self, existing: MetaIndex, new: MetaIndex) -> bool:
        """判断是否应该用新索引替换已有索引"""
        source_order = {
            IndexSource.SCHEMA: 0,
            IndexSource.RULE_ENGINE: 1,
            IndexSource.QUERY_ANALYSIS: 2,
            IndexSource.MANUAL: 3,
        }
        
        existing_source_order = source_order.get(existing.source, 99)
        new_source_order = source_order.get(new.source, 99)
        
        if existing_source_order != new_source_order:
            return new_source_order < existing_source_order
        
        if new.unique and not existing.unique:
            return True
        
        if self._priority_order(new.priority) < self._priority_order(existing.priority):
            return True
        
        return False
    
    @staticmethod
    def _priority_order(priority: IndexPriority) -> int:
        return {
            IndexPriority.HIGH: 0,
            IndexPriority.MEDIUM: 1,
            IndexPriority.LOW: 2,
        }.get(priority, 1)
    
    def get_derivation_report(self, meta_obj: MetaObject) -> Dict[str, Any]:
        """生成索引推导报告"""
        all_indexes = self.derive_indexes(meta_obj)
        
        explicit = [idx for idx in all_indexes if idx.source == IndexSource.SCHEMA]
        derived = [idx for idx in all_indexes if idx.source == IndexSource.RULE_ENGINE]
        
        high = [idx for idx in all_indexes if idx.priority == IndexPriority.HIGH]
        medium = [idx for idx in all_indexes if idx.priority == IndexPriority.MEDIUM]
        low = [idx for idx in all_indexes if idx.priority == IndexPriority.LOW]
        
        return {
            "object_id": meta_obj.id,
            "table_name": meta_obj.table_name,
            "total_indexes": len(all_indexes),
            "explicit_indexes": len(explicit),
            "derived_indexes": len(derived),
            "by_priority": {
                "high": len(high),
                "medium": len(medium),
                "low": len(low),
            },
            "indexes": [
                {
                    "name": idx.name,
                    "fields": idx.fields,
                    "db_columns": idx.db_columns,
                    "unique": idx.unique,
                    "type": idx.index_type.value,
                    "priority": idx.priority.value,
                    "source": idx.source.value,
                    "auto_create": idx.auto_create,
                    "description": idx.description,
                }
                for idx in all_indexes
            ],
        }
