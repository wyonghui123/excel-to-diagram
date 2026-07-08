# -*- coding: utf-8 -*-
"""
跨对象规则链执行器

支持跨对象的隐式规则链：
- 对象A的字段变更 → 规则1 → 更新对象B的字段 → 规则2 → 更新对象C的状态

核心概念：
1. 跨对象依赖图：分析不同对象之间的规则依赖关系
2. 对象关系映射：通过 MetaRelation 确定对象间的关联
3. 变更传播：跨对象的变更传播机制
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging

from meta.core.models import (
    MetaObject, MetaRule, MetaRelation, MetaComputation,
    RuleType, RuleTrigger, RelationType
)
from meta.core.rule_chain import (
    ImplicitRuleChainExecutor, RuleChainContext, RuleChainResult,
    FieldChange, StateChange, ValidationResult, TriggerResult,
    RuleNodeType, DependencyEdge, EdgeType
)

logger = logging.getLogger(__name__)


@dataclass
class CrossObjectDependency:
    source_object: str
    source_field: str
    target_object: str
    target_field: str
    relation_id: str
    relation_type: RelationType


@dataclass
class CrossObjectChange:
    source_object: str
    source_change: FieldChange
    target_object: str
    affected_rules: List[str]


@dataclass
class CrossObjectRuleChainResult:
    success: bool = True
    object_results: Dict[str, RuleChainResult] = field(default_factory=dict)
    cross_object_changes: List[CrossObjectChange] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class CrossObjectDependencyAnalyzer:
    
    @staticmethod
    def analyze(
        objects: Dict[str, MetaObject],
        registry=None
    ) -> Dict[str, List[CrossObjectDependency]]:
        dependencies = defaultdict(list)
        
        for obj_id, meta_obj in objects.items():
            for relation in meta_obj.relations:
                if relation.relation_type in (RelationType.REFERENCE, RelationType.PARENT_CHILD):
                    cross_dep = CrossObjectDependency(
                        source_object=obj_id,
                        source_field=relation.source_field,
                        target_object=relation.target_object,
                        target_field=relation.target_field,
                        relation_id=relation.id,
                        relation_type=relation.relation_type
                    )
                    dependencies[obj_id].append(cross_dep)
        
        for obj_id, meta_obj in objects.items():
            for rule in meta_obj.rules:
                if rule.rule_type == RuleType.COMPUTATION and isinstance(rule, MetaComputation):
                    for source_field in rule.source_fields:
                        for other_id, other_obj in objects.items():
                            if other_id == obj_id:
                                continue
                            for other_relation in other_obj.relations:
                                if other_relation.target_object == obj_id:
                                    if other_relation.source_field == source_field:
                                        cross_dep = CrossObjectDependency(
                                            source_object=other_id,
                                            source_field=source_field,
                                            target_object=obj_id,
                                            target_field=rule.target_field,
                                            relation_id=other_relation.id,
                                            relation_type=other_relation.relation_type
                                        )
                                        dependencies[other_id].append(cross_dep)
        
        return dict(dependencies)
    
    @staticmethod
    def get_affected_objects(
        source_object: str,
        source_field: str,
        dependencies: Dict[str, List[CrossObjectDependency]]
    ) -> List[CrossObjectDependency]:
        affected = []
        for dep in dependencies.get(source_object, []):
            if dep.source_field == source_field:
                affected.append(dep)
        return affected


class CrossObjectRuleChainExecutor:
    """
    跨对象规则链执行器
    
    执行流程：
    1. 执行源对象的规则链
    2. 分析跨对象依赖
    3. 传播变更到相关对象
    4. 递归执行受影响对象的规则链
    """
    
    MAX_CROSS_OBJECT_DEPTH = 10
    
    def __init__(
        self,
        objects: Dict[str, MetaObject],
        registry=None
    ):
        self.objects = objects
        self.registry = registry
        self.executors = {
            obj_id: ImplicitRuleChainExecutor(obj)
            for obj_id, obj in objects.items()
        }
        self.cross_dependencies = CrossObjectDependencyAnalyzer.analyze(objects, registry)
        
        self._validate_cross_object_cycles()
    
    def _validate_cross_object_cycles(self) -> None:
        visited = set()
        rec_stack = set()
        
        def has_cycle(obj_id: str) -> bool:
            visited.add(obj_id)
            rec_stack.add(obj_id)
            
            for dep in self.cross_dependencies.get(obj_id, []):
                target = dep.target_object
                if target not in visited:
                    if has_cycle(target):
                        return True
                elif target in rec_stack:
                    return True
            
            rec_stack.remove(obj_id)
            return False
        
        for obj_id in self.objects:
            if obj_id not in visited:
                if has_cycle(obj_id):
                    raise ValueError(
                        "检测到跨对象循环依赖，涉及对象: {0}".format(obj_id)
                    )
    
    def execute(
        self,
        object_id: str,
        data: Dict[str, Any],
        original_data: Optional[Dict[str, Any]] = None,
        changed_fields: Optional[Set[str]] = None,
        trigger: RuleTrigger = RuleTrigger.BEFORE_SAVE,
        depth: int = 0
    ) -> CrossObjectRuleChainResult:
        """
        执行跨对象规则链
        
        Args:
            object_id: 起始对象ID
            data: 当前数据
            original_data: 原始数据
            changed_fields: 变更字段
            trigger: 触发时机
            depth: 当前递归深度
            
        Returns:
            CrossObjectRuleChainResult
        """
        result = CrossObjectRuleChainResult()
        
        if depth > self.MAX_CROSS_OBJECT_DEPTH:
            result.errors.append("超过最大跨对象传播深度")
            result.success = False
            return result
        
        executor = self.executors.get(object_id)
        if not executor:
            result.errors.append("未找到对象: {0}".format(object_id))
            result.success = False
            return result
        
        obj_result = executor.execute(
            data=data,
            original_data=original_data,
            changed_fields=changed_fields,
            trigger=trigger
        )
        result.object_results[object_id] = obj_result
        
        if not obj_result.success:
            result.success = False
            result.errors.extend(obj_result.errors)
            return result
        
        if obj_result.changes:
            cross_changes = self._propagate_changes(
                object_id, obj_result.changes, trigger, depth
            )
            result.cross_object_changes.extend(cross_changes)
            
            for cross_change in cross_changes:
                target_result = self.object_results.get(cross_change.target_object)
                if target_result and not target_result.success:
                    result.success = False
                    result.errors.extend(target_result.errors)
        
        return result
    
    def _propagate_changes(
        self,
        source_object: str,
        changes: List[FieldChange],
        trigger: RuleTrigger,
        current_depth: int
    ) -> List[CrossObjectChange]:
        cross_changes = []
        
        for change in changes:
            affected = CrossObjectDependencyAnalyzer.get_affected_objects(
                source_object, change.field_id, self.cross_dependencies
            )
            
            for dep in affected:
                target_obj = self.objects.get(dep.target_object)
                if not target_obj:
                    continue
                
                cross_change = CrossObjectChange(
                    source_object=source_object,
                    source_change=change,
                    target_object=dep.target_object,
                    affected_rules=[]
                )
                
                target_executor = self.executors.get(dep.target_object)
                if target_executor:
                    affected_rules = target_executor.get_affected_rules({dep.target_field})
                    cross_change.affected_rules = affected_rules
                
                cross_changes.append(cross_change)
                
                if change.new_value is not None:
                    target_data = {dep.target_field: change.new_value}
                    target_result = self.execute(
                        object_id=dep.target_object,
                        data=target_data,
                        trigger=trigger,
                        depth=current_depth + 1
                    )
                    
                    self._merge_results(dep.target_object, target_result)
        
        return cross_changes
    
    def _merge_results(self, target_object: str, target_result: CrossObjectRuleChainResult) -> None:
        pass
    
    def get_cross_object_dependency_info(self) -> Dict[str, Any]:
        return {
            "objects": list(self.objects.keys()),
            "cross_dependencies": {
                source: [
                    {
                        "source_field": dep.source_field,
                        "target_object": dep.target_object,
                        "target_field": dep.target_field,
                        "relation_type": dep.relation_type.value
                    }
                    for dep in deps
                ]
                for source, deps in self.cross_dependencies.items()
            },
            "execution_orders": {
                obj_id: executor.get_execution_order()
                for obj_id, executor in self.executors.items()
            }
        }


class CrossObjectRuleChainBuilder:
    
    def __init__(self, registry=None):
        self.registry = registry
    
    def build(self, object_ids: Optional[List[str]] = None) -> CrossObjectRuleChainExecutor:
        if self.registry is None:
            from meta.core.models import registry as global_registry
            self.registry = global_registry
        
        if object_ids:
            objects = {
                obj_id: self.registry.get(obj_id)
                for obj_id in object_ids
                if self.registry.get(obj_id)
            }
        else:
            objects = self.registry.get_all()
        
        return CrossObjectRuleChainExecutor(objects, self.registry)


def build_cross_object_chain(
    objects: Optional[Dict[str, MetaObject]] = None,
    object_ids: Optional[List[str]] = None,
    registry=None
) -> CrossObjectRuleChainExecutor:
    if objects:
        return CrossObjectRuleChainExecutor(objects, registry)
    
    builder = CrossObjectRuleChainBuilder(registry)
    return builder.build(object_ids)
