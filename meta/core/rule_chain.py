# -*- coding: utf-8 -*-
"""
隐式规则链执行器 - 数据流驱动的规则链执行

核心概念：
1. 规则链不只是计算规则，还包括状态转换、校验、触发器
2. 规则之间通过数据流形成隐式依赖
3. 变更传播驱动规则执行
4. 支持跨对象规则链

示例：
    A字段变更 → 计算规则1 → B字段变更 → 计算规则2 → C字段变更
             → 状态转换规则 → 状态变更 → 校验规则 → 触发规则 → 发送通知
"""

from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging
import re

try:
    import simple_eval as _simple_eval_mod
    _HAS_SIMPLE_EVAL = True
except ImportError:
    _simple_eval_mod = None
    _HAS_SIMPLE_EVAL = False

from meta.core.models import (
    MetaObject, MetaRule, MetaComputation, MetaValidation,
    MetaStateTransition, MetaTrigger, MetaConstraint, MetaDerivation,
    RuleType, RuleTrigger
)
from meta.core.safe_expr_evaluator import safe_evaluate

logger = logging.getLogger(__name__)


class RuleNodeType(Enum):
    COMPUTATION = "computation"
    STATE_TRANSITION = "state_transition"
    VALIDATION = "validation"
    TRIGGER = "trigger"
    CONSTRAINT = "constraint"
    DERIVATION = "derivation"


class EdgeType(Enum):
    DATA_FLOW = "data_flow"
    STATE_DEPENDENCY = "state_dependency"
    CONDITION_DEPENDENCY = "condition_dependency"
    CROSS_OBJECT = "cross_object"
    DERIVATION_FLOW = "derivation_flow"


@dataclass
class FieldChange:
    field_id: str
    old_value: Any
    new_value: Any
    source_rule: Optional[str] = None
    object_id: Optional[str] = None


@dataclass
class StateChange:
    state_field: str
    old_state: Any
    new_state: Any
    source_rule: Optional[str] = None


@dataclass
class ValidationResult:
    rule_id: str
    success: bool
    message: str = ""
    field_id: str = ""
    severity: str = "error"


@dataclass
class TriggerResult:
    rule_id: str
    executed: bool
    success: bool = True
    message: str = ""
    async_exec: bool = True


@dataclass
class DerivationResult:
    rule_id: str
    derivation_type: str
    source_object: str
    target_object: str
    status: str = "pending"
    records_processed: int = 0
    records_created: int = 0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleChainContext:
    data: Dict[str, Any]
    original_data: Dict[str, Any]
    changed_fields: Set[str] = field(default_factory=set)
    changed_states: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)
    user_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _field_values: Dict[str, Any] = field(default_factory=dict)
    
    def get_field_value(self, field_id: str) -> Any:
        if field_id in self._field_values:
            return self._field_values[field_id]
        return self.data.get(field_id)
    
    def set_field_value(self, field_id: str, value: Any) -> None:
        self._field_values[field_id] = value
        self.data[field_id] = value
    
    def get_original_value(self, field_id: str) -> Any:
        return self.original_data.get(field_id)
    
    def mark_changed(self, field_id: str, old_value: Any, new_value: Any) -> None:
        if old_value != new_value:
            self.changed_fields.add(field_id)
    
    def is_changed(self, field_id: str) -> bool:
        return field_id in self.changed_fields


@dataclass
class RuleChainResult:
    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    changes: List[FieldChange] = field(default_factory=list)
    state_changes: List[StateChange] = field(default_factory=list)
    validations: List[ValidationResult] = field(default_factory=list)
    triggers: List[TriggerResult] = field(default_factory=list)
    derivations: List[DerivationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)


@dataclass
class RuleNode:
    rule: MetaRule
    node_type: RuleNodeType
    source_fields: Set[str]
    target_fields: Set[str]
    condition_fields: Set[str] = field(default_factory=set)
    dependencies: Set[str] = field(default_factory=set)
    priority: int = 100
    
    def should_execute(self, context: RuleChainContext) -> bool:
        if not self.rule.enabled:
            return False
        
        if self.node_type == RuleNodeType.COMPUTATION:
            for f in self.source_fields:
                if context.is_changed(f):
                    return True
            return False
        
        if self.node_type == RuleNodeType.STATE_TRANSITION:
            if isinstance(self.rule, MetaStateTransition):
                current_state = context.get_field_value(self.rule.state_field)
                if current_state in self.rule.from_states:
                    return True
            return False
        
        if self.node_type == RuleNodeType.VALIDATION:
            for f in self.source_fields:
                if context.is_changed(f):
                    return True
            return len(self.source_fields) == 0
        
        if self.node_type == RuleNodeType.TRIGGER:
            return True
        
        return True


@dataclass
class DependencyEdge:
    from_rule: str
    to_rule: str
    edge_type: EdgeType
    field_name: Optional[str] = None


class DependencyGraph:
    def __init__(self):
        self.nodes: Dict[str, RuleNode] = {}
        self.edges: List[DependencyEdge] = []
        self.field_to_rules: Dict[str, Set[str]] = defaultdict(set)
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)
    
    def add_node(self, node: RuleNode) -> None:
        self.nodes[node.rule.id] = node
        for f in node.source_fields:
            self.field_to_rules[f].add(node.rule.id)
        for f in node.condition_fields:
            self.field_to_rules[f].add(node.rule.id)
    
    def add_edge(self, edge: DependencyEdge) -> None:
        self.edges.append(edge)
        self.adjacency[edge.from_rule].add(edge.to_rule)
        self.reverse_adjacency[edge.to_rule].add(edge.from_rule)
    
    def get_dependents(self, rule_id: str) -> Set[str]:
        return self.adjacency.get(rule_id, set())
    
    def get_dependencies(self, rule_id: str) -> Set[str]:
        return self.reverse_adjacency.get(rule_id, set())
    
    def get_rules_by_field(self, field_id: str) -> Set[str]:
        return self.field_to_rules.get(field_id, set())


class RuleDependencyAnalyzer:
    @staticmethod
    def analyze(meta_object: MetaObject) -> DependencyGraph:
        graph = DependencyGraph()
        
        for rule in meta_object.rules:
            node = RuleDependencyAnalyzer._create_node(rule)
            if node:
                graph.add_node(node)
        
        RuleDependencyAnalyzer._build_edges(graph)
        
        return graph
    
    @staticmethod
    def _create_node(rule: MetaRule) -> Optional[RuleNode]:
        if rule.rule_type == RuleType.COMPUTATION and isinstance(rule, MetaComputation):
            return RuleNode(
                rule=rule,
                node_type=RuleNodeType.COMPUTATION,
                source_fields=set(rule.source_fields),
                target_fields={rule.target_field} if rule.target_field else set(),
                priority=rule.priority
            )
        
        elif rule.rule_type == RuleType.STATE_TRANSITION and isinstance(rule, MetaStateTransition):
            return RuleNode(
                rule=rule,
                node_type=RuleNodeType.STATE_TRANSITION,
                source_fields={rule.state_field},
                target_fields={rule.state_field},
                condition_fields=set(rule.from_states),
                priority=rule.priority
            )
        
        elif rule.rule_type == RuleType.VALIDATION and isinstance(rule, MetaValidation):
            return RuleNode(
                rule=rule,
                node_type=RuleNodeType.VALIDATION,
                source_fields=set(rule.target_fields),
                target_fields=set(),
                priority=rule.priority
            )
        
        elif rule.rule_type == RuleType.TRIGGER and isinstance(rule, MetaTrigger):
            return RuleNode(
                rule=rule,
                node_type=RuleNodeType.TRIGGER,
                source_fields=set(),
                target_fields=set(),
                priority=rule.priority
            )
        
        elif rule.rule_type == RuleType.CONSTRAINT and isinstance(rule, MetaConstraint):
            return RuleNode(
                rule=rule,
                node_type=RuleNodeType.CONSTRAINT,
                source_fields=set(rule.target_fields),
                target_fields=set(),
                priority=rule.priority
            )
        
        elif rule.rule_type == RuleType.DERIVATION and isinstance(rule, MetaDerivation):
            return RuleNode(
                rule=rule,
                node_type=RuleNodeType.DERIVATION,
                source_fields=set(rule.source_fields),
                target_fields=set(rule.get_target_fields()),
                priority=rule.priority
            )
        
        return None
    
    @staticmethod
    def _build_edges(graph: DependencyGraph) -> None:
        nodes_list = list(graph.nodes.values())
        
        for node in nodes_list:
            for target_field in node.target_fields:
                dependent_rules = graph.get_rules_by_field(target_field)
                for dep_rule_id in dependent_rules:
                    if dep_rule_id != node.rule.id:
                        graph.add_edge(DependencyEdge(
                            from_rule=node.rule.id,
                            to_rule=dep_rule_id,
                            edge_type=EdgeType.DATA_FLOW,
                            field_name=target_field
                        ))
        
        computation_nodes = [n for n in nodes_list if n.node_type == RuleNodeType.COMPUTATION]
        other_nodes = [n for n in nodes_list if n.node_type != RuleNodeType.COMPUTATION]
        
        for comp_node in computation_nodes:
            for other_node in other_nodes:
                if other_node.node_type == RuleNodeType.VALIDATION:
                    if comp_node.target_fields & other_node.source_fields:
                        graph.add_edge(DependencyEdge(
                            from_rule=comp_node.rule.id,
                            to_rule=other_node.rule.id,
                            edge_type=EdgeType.DATA_FLOW
                        ))
                
                elif other_node.node_type == RuleNodeType.STATE_TRANSITION:
                    if comp_node.target_fields & other_node.source_fields:
                        graph.add_edge(DependencyEdge(
                            from_rule=comp_node.rule.id,
                            to_rule=other_node.rule.id,
                            edge_type=EdgeType.CONDITION_DEPENDENCY
                        ))
    
    @staticmethod
    def detect_cycle(graph: DependencyGraph) -> Optional[List[str]]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node_id: WHITE for node_id in graph.nodes}
        parent = {}
        
        def dfs(node_id: str) -> Optional[List[str]]:
            color[node_id] = GRAY
            
            for neighbor in graph.get_dependents(node_id):
                if color[neighbor] == GRAY:
                    cycle = [neighbor]
                    current = node_id
                    while current != neighbor:
                        cycle.append(current)
                        current = parent.get(current)
                        if current is None:
                            break
                    cycle.append(neighbor)
                    return list(reversed(cycle))
                
                if color[neighbor] == WHITE:
                    parent[neighbor] = node_id
                    result = dfs(neighbor)
                    if result:
                        return result
            
            color[node_id] = BLACK
            return None
        
        for node_id in graph.nodes:
            if color[node_id] == WHITE:
                result = dfs(node_id)
                if result:
                    return result
        
        return None
    
    @staticmethod
    def _get_type_weight(node_type: RuleNodeType) -> int:
        type_weights = {
            RuleNodeType.COMPUTATION: 10,
            RuleNodeType.DERIVATION: 15,
            RuleNodeType.CONSTRAINT: 20,
            RuleNodeType.VALIDATION: 30,
            RuleNodeType.STATE_TRANSITION: 40,
            RuleNodeType.TRIGGER: 50,
        }
        return type_weights.get(node_type, 100)
    
    @staticmethod
    def topological_sort(graph: DependencyGraph) -> List[str]:
        in_degree = {node_id: 0 for node_id in graph.nodes}
        
        for node_id in graph.nodes:
            for dependent in graph.get_dependents(node_id):
                in_degree[dependent] = in_degree.get(dependent, 0) + 1
        
        queue = deque()
        for node_id, degree in in_degree.items():
            if degree == 0:
                node = graph.nodes.get(node_id)
                if node:
                    type_weight = RuleDependencyAnalyzer._get_type_weight(node.node_type)
                    queue.append((type_weight, node.priority, node_id))
        
        queue = deque(sorted(queue))
        result = []
        
        while queue:
            _, _, node_id = queue.popleft()
            result.append(node_id)
            
            dependents = list(graph.get_dependents(node_id))
            dependent_queue = []
            
            for dependent in dependents:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    node = graph.nodes.get(dependent)
                    if node:
                        type_weight = RuleDependencyAnalyzer._get_type_weight(node.node_type)
                        dependent_queue.append((type_weight, node.priority, dependent))
            
            for item in sorted(dependent_queue):
                queue.append(item)
        
        return result


class ImplicitRuleChainExecutor:
    """
    隐式规则链执行器
    
    核心特性：
    1. 自动分析规则依赖关系
    2. 基于数据变更驱动执行
    3. 支持多种规则类型
    4. 支持变更传播
    """
    
    MAX_PROPAGATION_DEPTH = 100
    
    def __init__(self, meta_object: MetaObject):
        self.meta_object = meta_object
        self.graph = RuleDependencyAnalyzer.analyze(meta_object)
        self._execution_order = None
        self._validate()
    
    def _validate(self) -> None:
        cycle = RuleDependencyAnalyzer.detect_cycle(self.graph)
        if cycle:
            cycle_str = " → ".join(cycle)
            raise ValueError(
                "检测到循环依赖: {0}。请检查规则定义。".format(cycle_str)
            )
    
    def get_execution_order(self) -> List[str]:
        if self._execution_order is None:
            self._execution_order = RuleDependencyAnalyzer.topological_sort(self.graph)
        return self._execution_order
    
    def get_affected_rules(self, changed_fields: Set[str]) -> List[str]:
        if not changed_fields:
            return self.get_execution_order()
        
        affected = set()
        for field_id in changed_fields:
            affected.update(self.graph.get_rules_by_field(field_id))
        
        all_affected = self._get_downstream_rules(affected)
        
        execution_order = self.get_execution_order()
        return [r for r in execution_order if r in all_affected]
    
    def _get_downstream_rules(self, rule_ids: Set[str]) -> Set[str]:
        result = set(rule_ids)
        queue = deque(rule_ids)
        
        while queue:
            current = queue.popleft()
            for dependent in self.graph.get_dependents(current):
                if dependent not in result:
                    result.add(dependent)
                    queue.append(dependent)
        
        return result
    
    def execute(
        self,
        data: Dict[str, Any],
        original_data: Optional[Dict[str, Any]] = None,
        changed_fields: Optional[Set[str]] = None,
        trigger: RuleTrigger = RuleTrigger.BEFORE_SAVE,
        executors: Optional[Dict[RuleNodeType, Callable]] = None
    ) -> RuleChainResult:
        """
        执行规则链
        
        Args:
            data: 当前数据
            original_data: 原始数据（用于变更检测）
            changed_fields: 已变更的字段（可选，会自动检测）
            trigger: 触发时机
            executors: 自定义执行器（可选）
            
        Returns:
            RuleChainResult 执行结果
        """
        result = RuleChainResult(data=data.copy())
        context = RuleChainContext(
            data=data,
            original_data=original_data or data.copy(),
            changed_fields=changed_fields or set()
        )
        
        if changed_fields is None and original_data:
            for key in set(data.keys()) | set(original_data.keys()):
                old_val = original_data.get(key)
                new_val = data.get(key)
                if old_val != new_val:
                    context.changed_fields.add(key)
        
        rules_to_execute = self.get_affected_rules(context.changed_fields)
        
        rules_by_trigger = self._filter_by_trigger(rules_to_execute, trigger)
        
        result.execution_order = rules_by_trigger
        
        propagation_depth = 0
        
        while rules_by_trigger and propagation_depth < self.MAX_PROPAGATION_DEPTH:
            prev_changed_count = len(context.changed_fields)
            
            rules_by_trigger = self._execute_rules_batch(
                rules_by_trigger, context, result, executors
            )
            propagation_depth += 1
            
            if rules_by_trigger:
                new_changed_fields = {c.field_id for c in result.changes}
                context.changed_fields.update(new_changed_fields)
                
                if len(context.changed_fields) == prev_changed_count:
                    break
        
        result.data = context.data.copy()
        result.success = len(result.errors) == 0 and all(v.success for v in result.validations)
        
        return result
    
    def _filter_by_trigger(self, rule_ids: List[str], trigger: RuleTrigger) -> List[str]:
        filtered = []
        for rule_id in rule_ids:
            node = self.graph.nodes.get(rule_id)
            if node and trigger in node.rule.triggers:
                filtered.append(rule_id)
        return filtered
    
    def _execute_rules_batch(
        self,
        rule_ids: List[str],
        context: RuleChainContext,
        result: RuleChainResult,
        executors: Optional[Dict[RuleNodeType, Callable]]
    ) -> List[str]:
        next_rules = []
        
        for rule_id in rule_ids:
            node = self.graph.nodes.get(rule_id)
            if not node:
                continue
            
            if not node.should_execute(context):
                continue
            
            try:
                rule_result = self._execute_single_rule(node, context, executors)
                self._process_rule_result(node, rule_result, context, result)
                
                if rule_result.get('triggered_rules'):
                    next_rules.extend(rule_result['triggered_rules'])
                    
            except Exception as e:
                logger.error("规则执行失败: {0} - {1}".format(rule_id, str(e)))
                result.errors.append("规则 {0} 执行失败: {1}".format(node.rule.name, str(e)))
        
        return next_rules
    
    def _execute_single_rule(
        self,
        node: RuleNode,
        context: RuleChainContext,
        executors: Optional[Dict[RuleNodeType, Callable]]
    ) -> Dict[str, Any]:
        rule = node.rule
        result = {'success': True, 'changes': [], 'triggered_rules': []}
        
        if node.node_type == RuleNodeType.COMPUTATION:
            result.update(self._execute_computation(node, context))
        
        elif node.node_type == RuleNodeType.STATE_TRANSITION:
            result.update(self._execute_state_transition(node, context))
        
        elif node.node_type == RuleNodeType.VALIDATION:
            result.update(self._execute_validation(node, context))
        
        elif node.node_type == RuleNodeType.TRIGGER:
            result.update(self._execute_trigger(node, context))
        
        elif node.node_type == RuleNodeType.CONSTRAINT:
            result.update(self._execute_constraint(node, context))
        
        elif node.node_type == RuleNodeType.DERIVATION:
            result.update(self._execute_derivation(node, context))
        
        return result
    
    def _execute_computation(
        self,
        node: RuleNode,
        context: RuleChainContext
    ) -> Dict[str, Any]:
        rule = node.rule
        if not isinstance(rule, MetaComputation):
            return {'success': False}
        
        result = {'success': True, 'changes': [], 'triggered_rules': []}
        
        target_field = rule.target_field
        old_value = context.get_field_value(target_field)
        
        try:
            new_value = self._evaluate_formula(rule.formula, context)
            
            if old_value != new_value:
                context.set_field_value(target_field, new_value)
                context.mark_changed(target_field, old_value, new_value)
                
                result['changes'].append(FieldChange(
                    field_id=target_field,
                    old_value=old_value,
                    new_value=new_value,
                    source_rule=rule.id
                ))
                
                downstream = self.graph.get_rules_by_field(target_field)
                result['triggered_rules'].extend(downstream - {rule.id})
                
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
        
        return result
    
    def _execute_state_transition(
        self,
        node: RuleNode,
        context: RuleChainContext
    ) -> Dict[str, Any]:
        rule = node.rule
        if not isinstance(rule, MetaStateTransition):
            return {'success': False}
        
        result = {'success': True, 'changes': [], 'triggered_rules': []}
        
        state_field = rule.state_field
        current_state = context.get_field_value(state_field)
        
        if current_state not in rule.from_states:
            return result
        
        old_value = current_state
        new_value = rule.to_state
        
        context.set_field_value(state_field, new_value)
        context.mark_changed(state_field, old_value, new_value)
        
        result['changes'].append(FieldChange(
            field_id=state_field,
            old_value=old_value,
            new_value=new_value,
            source_rule=rule.id
        ))
        
        result['state_change'] = StateChange(
            state_field=state_field,
            old_state=old_state if (old_state := old_value) else None,
            new_state=new_value,
            source_rule=rule.id
        )
        
        downstream = self.graph.get_rules_by_field(state_field)
        result['triggered_rules'].extend(downstream - {rule.id})
        
        return result
    
    def _execute_validation(
        self,
        node: RuleNode,
        context: RuleChainContext
    ) -> Dict[str, Any]:
        rule = node.rule
        if not isinstance(rule, MetaValidation):
            return {'success': False}
        
        try:
            is_valid = self._evaluate_condition(rule.condition, context)
            
            return {
                'success': True,
                'validation': ValidationResult(
                    rule_id=rule.id,
                    success=is_valid,
                    message=rule.message if not is_valid else "",
                    field_id=rule.target_fields[0] if rule.target_fields else "",
                    severity=rule.severity.value
                )
            }
        except Exception as e:
            return {
                'success': False,
                'validation': ValidationResult(
                    rule_id=rule.id,
                    success=False,
                    message=str(e),
                    severity="error"
                )
            }
    
    def _execute_trigger(
        self,
        node: RuleNode,
        context: RuleChainContext
    ) -> Dict[str, Any]:
        rule = node.rule
        if not isinstance(rule, MetaTrigger):
            return {'success': False}
        
        return {
            'success': True,
            'trigger': TriggerResult(
                rule_id=rule.id,
                executed=True,
                async_exec=rule.async_exec
            )
        }
    
    def _execute_constraint(
        self,
        node: RuleNode,
        context: RuleChainContext
    ) -> Dict[str, Any]:
        rule = node.rule
        if not isinstance(rule, MetaConstraint):
            return {'success': False}
        
        try:
            is_valid = self._evaluate_condition(rule.condition, context)
            
            return {
                'success': True,
                'validation': ValidationResult(
                    rule_id=rule.id,
                    success=is_valid,
                    message=rule.message if not is_valid else "",
                    severity="error"
                )
            }
        except Exception as e:
            return {
                'success': False,
                'validation': ValidationResult(
                    rule_id=rule.id,
                    success=False,
                    message=str(e),
                    severity="error"
                )
            }
    
    def _execute_derivation(
        self,
        node: RuleNode,
        context: RuleChainContext
    ) -> Dict[str, Any]:
        """
        执行派生规则
        
        派生规则的执行逻辑：
        1. 根据派生类型选择执行策略
        2. 聚合派生：执行聚合查询，更新目标对象
        3. 转换派生：按字段映射转换数据
        4. 过滤派生：按条件筛选数据
        """
        rule = node.rule
        if not isinstance(rule, MetaDerivation):
            return {'success': False}
        
        result = {'success': True, 'changes': [], 'triggered_rules': [], 'derivation': None}
        
        if rule.derivation_type.value == "aggregation":
            result['derivation'] = {
                'type': 'aggregation',
                'source_object': rule.source_object,
                'target_object': rule.target_object,
                'group_by': rule.group_by,
                'aggregates': [
                    {'target': agg.target_field, 'function': agg.function, 'source': agg.source_field}
                    for agg in rule.aggregates
                ],
                'filter': rule.filter,
                'status': 'pending'
            }
        
        elif rule.derivation_type.value == "transformation":
            result['derivation'] = {
                'type': 'transformation',
                'source_object': rule.source_object,
                'target_object': rule.target_object,
                'mappings': [
                    {'source': m.source_field, 'target': m.target_field, 'transform': m.transform}
                    for m in rule.field_mappings
                ],
                'status': 'pending'
            }
        
        elif rule.derivation_type.value == "filtering":
            result['derivation'] = {
                'type': 'filtering',
                'source_object': rule.source_object,
                'target_object': rule.target_object,
                'filter': rule.filter,
                'status': 'pending'
            }
        
        elif rule.derivation_type.value == "enrichment":
            result['derivation'] = {
                'type': 'enrichment',
                'target_object': rule.target_object,
                'enrichments': rule.target_fields,
                'status': 'pending'
            }
        
        elif rule.derivation_type.value == "materialization":
            result['derivation'] = {
                'type': 'materialization',
                'source_object': rule.source_object,
                'target_object': rule.target_object,
                'status': 'pending'
            }
        
        return result
    
    def _process_rule_result(
        self,
        node: RuleNode,
        rule_result: Dict[str, Any],
        context: RuleChainContext,
        result: RuleChainResult
    ) -> None:
        for change in rule_result.get('changes', []):
            result.changes.append(change)
        
        if 'state_change' in rule_result:
            result.state_changes.append(rule_result['state_change'])
        
        if 'validation' in rule_result:
            result.validations.append(rule_result['validation'])
            if not rule_result['validation'].success:
                result.errors.append(rule_result['validation'].message)
        
        if 'trigger' in rule_result:
            result.triggers.append(rule_result['trigger'])
        
        if 'derivation' in rule_result and rule_result['derivation']:
            deriv_info = rule_result['derivation']
            result.derivations.append(DerivationResult(
                rule_id=node.rule.id,
                derivation_type=deriv_info.get('type', 'unknown'),
                source_object=deriv_info.get('source_object', ''),
                target_object=deriv_info.get('target_object', ''),
                status=deriv_info.get('status', 'pending'),
                details=deriv_info
            ))
    
    def _evaluate_formula(self, formula: str, context: RuleChainContext) -> Any:
        if not formula:
            return None
        
        expr = re.sub(r'\$(\w+)', r'\1', formula)
        
        if _HAS_SIMPLE_EVAL:
            evaluator = _simple_eval_mod.EvalWithCompoundTypes()
            for field_id in context.data.keys():
                evaluator.names[field_id] = context.get_field_value(field_id)
            return evaluator.eval(expr)
        
        field_names = set(re.findall(r'\b([a-zA-Z_]\w*)\b', expr))
        local_vars = {k: context.get_field_value(k) for k in field_names if k in context.data}
        try:
            return safe_evaluate(expr, local_vars)
        except Exception as e:
            logger.warning("公式求值失败: {0} - {1}".format(formula, str(e)))
            return None
    
    def _evaluate_condition(self, condition: str, context: RuleChainContext) -> bool:
        if not condition:
            return True
        
        try:
            result = self._evaluate_formula(condition, context)
            return bool(result)
        except Exception:
            return True
    
    def get_dependency_info(self) -> Dict[str, Any]:
        return {
            "execution_order": self.get_execution_order(),
            "nodes": {
                rule_id: {
                    "type": node.node_type.value,
                    "source_fields": list(node.source_fields),
                    "target_fields": list(node.target_fields),
                    "dependencies": list(self.graph.get_dependencies(rule_id)),
                    "dependents": list(self.graph.get_dependents(rule_id)),
                }
                for rule_id, node in self.graph.nodes.items()
            },
            "field_dependencies": {
                field: list(rules)
                for field, rules in self.graph.field_to_rules.items()
            },
        }


def build_rule_chain(meta_object: MetaObject) -> ImplicitRuleChainExecutor:
    from meta.core.models import registry
    cached = registry.get_rule_chain(meta_object.id)
    if cached is not None:
        return cached
    executor = ImplicitRuleChainExecutor(meta_object)
    registry.set_rule_chain(meta_object.id, executor)
    return executor
