# -*- coding: utf-8 -*-
"""
规则执行器 - 基于元模型定义执行业务规则

支持：
- 校验规则执行
- 计算规则执行
- 状态转换规则执行
- 触发规则执行
- 规则链式调用
"""

from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import re
import ast
import logging

logger = logging.getLogger(__name__)

from meta.core.models import (
    MetaObject, MetaField, MetaRule, MetaValidation, MetaComputation,
    MetaStateTransition, MetaTrigger, MetaConstraint, MetaFunction, MetaDerivation,
    RuleType, RuleScope, RuleTrigger, ValidationSeverity, FieldType,
    ObjectType, MetricReference, registry
)
from meta.core.formula_functions import FormulaFunctionRegistry
from meta.core.cross_object_resolver import build_cross_object_locals


@dataclass
class RuleResult:
    """规则执行结果"""
    success: bool = True
    rule_id: str = ""
    rule_name: str = ""
    message: str = ""
    severity: ValidationSeverity = ValidationSeverity.ERROR
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "message": self.message,
            "severity": self.severity.value,
            "data": self.data,
        }


@dataclass
class RuleExecutionReport:
    """规则执行报告"""
    trigger: RuleTrigger
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    results: List[RuleResult] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return self.failed == 0
    
    def add_result(self, result: RuleResult) -> None:
        self.results.append(result)
        self.total_rules += 1
        if result.success:
            self.passed += 1
        else:
            if result.severity == ValidationSeverity.WARNING:
                self.warnings += 1
            else:
                self.failed += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger": self.trigger.value,
            "success": self.success,
            "total_rules": self.total_rules,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
        }


class RuleContext:
    """规则执行上下文"""
    
    def __init__(self, meta_object: MetaObject, data: Dict[str, Any],
                 original_data: Optional[Dict[str, Any]] = None,
                 data_source: Any = None):
        self.meta_object = meta_object
        self.data = data
        self.original_data = original_data or {}
        self.data_source = data_source
        self.changed_fields: List[str] = []
        self._field_map = {f.id: f for f in meta_object.fields}
        
        if original_data:
            for key in set(list(data.keys()) + list(original_data.keys())):
                if data.get(key) != original_data.get(key):
                    self.changed_fields.append(key)
    
    def get_field_value(self, field_id: str) -> Any:
        """获取字段值"""
        return self.data.get(field_id)
    
    def set_field_value(self, field_id: str, value: Any) -> None:
        """设置字段值"""
        self.data[field_id] = value
        if field_id not in self.changed_fields:
            self.changed_fields.append(field_id)
    
    def get_original_value(self, field_id: str) -> Any:
        """获取原始值"""
        return self.original_data.get(field_id)
    
    def is_field_changed(self, field_id: str) -> bool:
        """检查字段是否变更"""
        return field_id in self.changed_fields
    
    def get_field_type(self, field_id: str) -> Optional[FieldType]:
        """获取字段类型"""
        field = self._field_map.get(field_id)
        return field.field_type if field else None


class SafeExpressionEvaluator:
    """
    安全表达式求值器 - 基于 AST 解析
    
    使用 AST 解析替代 eval()，通过白名单机制确保表达式执行安全。
    函数白名单由 FormulaFunctionRegistry 动态管理，支持运行时增减函数。
    """
    
    ALLOWED_OPERATORS = frozenset({
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.And, ast.Or, ast.Not,
        ast.In, ast.NotIn,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
        ast.UAdd, ast.USub,
        ast.Is, ast.IsNot,
    })
    
    DANGEROUS_PATTERNS = frozenset({
        'import', 'exec', 'eval', 'compile', 'open', 'input',
        '__import__', 'globals', 'locals', 'vars', 'dir',
        'getattr', 'setattr', 'delattr', 'hasattr',
        'property', 'classmethod', 'staticmethod',
    })
    
    def __init__(self, context: RuleContext):
        self.context = context
        self._locals = self._build_locals()
    
    @property
    def ALLOWED_FUNCTIONS(self) -> frozenset:
        return FormulaFunctionRegistry.get_allowed_functions()
    
    def _build_locals(self) -> Dict[str, Any]:
        locals_dict = dict(self.context.original_data)
        locals_dict.update(self.context.data)
        locals_dict["original"] = self.context.original_data
        locals_dict["changed_fields"] = self.context.changed_fields
        locals_dict["is_changed"] = self.context.is_field_changed
        locals_dict["get_value"] = self.context.get_field_value
        locals_dict["get_original"] = self.context.get_original_value
        
        formula_locals = FormulaFunctionRegistry.build_locals()
        locals_dict.update(formula_locals)
        
        if self.context.data_source is not None:
            cross_locals = build_cross_object_locals(
                self.context.data_source,
                self.context.meta_object,
                self.context.data,
            )
            locals_dict.update(cross_locals)
        
        return locals_dict
    
    def _get_builtin_func(self, name: str) -> Optional[Callable]:
        func = FormulaFunctionRegistry.get(name)
        if func is not None:
            return func
        builtins = {
            'len': len, 'str': str, 'int': int, 'float': float,
            'bool': bool, 'abs': abs, 'min': min, 'max': max,
            'sum': sum, 'any': any, 'all': all,
        }
        return builtins.get(name)
    
    def _validate_node(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                if '__' in child.attr:
                    raise ValueError("Forbidden attribute access: {0}".format(child.attr))
            elif isinstance(child, ast.Name):
                if child.id in self.DANGEROUS_PATTERNS:
                    raise ValueError("Forbidden name: {0}".format(child.id))
                if child.id.startswith('__') and child.id.endswith('__'):
                    raise ValueError("Forbidden dunder name: {0}".format(child.id))
            elif isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    if child.func.id not in self.ALLOWED_FUNCTIONS:
                        raise ValueError("Forbidden function: {0}".format(child.func.id))
                elif isinstance(child.func, ast.Attribute):
                    if not self._is_allowed_attribute_call(child.func):
                        raise ValueError("Method calls not allowed: {0}".format(child.func.attr))
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                raise ValueError("Import statements not allowed")
            elif isinstance(child, ast.Expr):
                pass
            elif hasattr(ast, 'Exec') and isinstance(child, ast.Exec):
                raise ValueError("Exec not allowed")
            elif isinstance(child, ast.BinOp):
                if type(child.op) not in self.ALLOWED_OPERATORS:
                    raise ValueError("Forbidden binary operator: {0}".format(type(child.op).__name__))
            elif isinstance(child, ast.UnaryOp):
                if type(child.op) not in self.ALLOWED_OPERATORS:
                    raise ValueError("Forbidden unary operator: {0}".format(type(child.op).__name__))
            elif isinstance(child, ast.BoolOp):
                if type(child.op) not in self.ALLOWED_OPERATORS:
                    raise ValueError("Forbidden boolean operator: {0}".format(type(child.op).__name__))
            elif isinstance(child, ast.Compare):
                for op in child.ops:
                    if type(op) not in self.ALLOWED_OPERATORS:
                        raise ValueError("Forbidden comparison operator: {0}".format(type(op).__name__))
    
    def _is_allowed_attribute_call(self, func_node: ast.Attribute) -> bool:
        if isinstance(func_node.value, ast.Name):
            root_name = func_node.value.id
            if root_name in ('self', 'parent'):
                return True
        if isinstance(func_node.value, ast.Attribute):
            return self._is_allowed_attribute_call(func_node.value)
        return False
    
    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        elif hasattr(ast, 'Num') and isinstance(node, ast.Num):
            return node.n
        elif hasattr(ast, 'Str') and isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.Name):
            if node.id in self._locals:
                return self._locals[node.id]
            if node.id == 'True':
                return True
            if node.id == 'False':
                return False
            if node.id == 'None':
                return None
            raise NameError("Name '{0}' is not defined".format(node.id))
        elif isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt) for elt in node.elts)
        elif isinstance(node, ast.Dict):
            keys = [self._eval_node(k) if k else None for k in node.keys]
            values = [self._eval_node(v) for v in node.values]
            return dict(zip(keys, values))
        elif isinstance(node, ast.Set):
            return {self._eval_node(elt) for elt in node.elts}
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            ops = {
                ast.Add: lambda a, b: a + b,
                ast.Sub: lambda a, b: a - b,
                ast.Mult: lambda a, b: a * b,
                ast.Div: lambda a, b: a / b,
                ast.Mod: lambda a, b: a % b,
            }
            op_func = ops.get(type(node.op))
            if op_func:
                return op_func(left, right)
            raise ValueError("Unsupported binary operator: {0}".format(type(node.op).__name__))
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            elif isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.Not):
                return not operand
            raise ValueError("Unsupported unary operator: {0}".format(type(node.op).__name__))
        elif isinstance(node, ast.BoolOp):
            values = [self._eval_node(v) for v in node.values]
            if isinstance(node.op, ast.And):
                result = True
                for v in values:
                    result = result and v
                    if not result:
                        break
                return result
            elif isinstance(node.op, ast.Or):
                result = False
                for v in values:
                    result = result or v
                    if result:
                        break
                return result
            raise ValueError("Unsupported boolean operator: {0}".format(type(node.op).__name__))
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                if isinstance(op, ast.Eq):
                    if not left == right:
                        return False
                elif isinstance(op, ast.NotEq):
                    if not left != right:
                        return False
                elif isinstance(op, ast.Lt):
                    if not left < right:
                        return False
                elif isinstance(op, ast.LtE):
                    if not left <= right:
                        return False
                elif isinstance(op, ast.Gt):
                    if not left > right:
                        return False
                elif isinstance(op, ast.GtE):
                    if not left >= right:
                        return False
                elif isinstance(op, ast.In):
                    if not left in right:
                        return False
                elif isinstance(op, ast.NotIn):
                    if not left not in right:
                        return False
                elif isinstance(op, ast.Is):
                    if not left is right:
                        return False
                elif isinstance(op, ast.IsNot):
                    if not left is not right:
                        return False
                else:
                    raise ValueError("Unsupported comparison operator: {0}".format(type(op).__name__))
                left = right
            return True
        elif isinstance(node, ast.Call):
            func_name = node.func.id
            func = self._get_builtin_func(func_name)
            if func is None:
                raise ValueError("Function '{0}' not allowed".format(func_name))
            args = [self._eval_node(arg) for arg in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value) for kw in node.keywords if kw.arg}
            return func(*args, **kwargs)
        elif isinstance(node, ast.Attribute):
            value = self._eval_node(node.value)
            if '__' in node.attr:
                raise ValueError("Forbidden attribute access: {0}".format(node.attr))
            if isinstance(value, dict):
                return value.get(node.attr)
            return getattr(value, node.attr, None)
        elif isinstance(node, ast.Subscript):
            value = self._eval_node(node.value)
            slice_val = self._eval_node(node.slice)
            return value[slice_val]
        elif isinstance(node, ast.Index):
            return self._eval_node(node.value)
        elif isinstance(node, ast.IfExp):
            test = self._eval_node(node.test)
            if test:
                return self._eval_node(node.body)
            else:
                return self._eval_node(node.orelse)
        else:
            raise ValueError("Unsupported AST node type: {0}".format(type(node).__name__))
    
    def evaluate(self, expression: str) -> Any:
        if not expression:
            return True
        try:
            tree = ast.parse(expression, mode='eval')
            self._validate_node(tree)
            return self._eval_node(tree.body)
        except Exception as e:
            logger.error("SafeExpressionEvaluator expression error: %s - %s", expression, str(e))
            return None


class ExpressionEvaluator:
    """表达式求值器 - 使用安全的 AST 解析"""
    
    @staticmethod
    def evaluate(expression: str, context: RuleContext) -> Any:
        """
        安全地求值表达式
        
        Args:
            expression: 表达式字符串
            context: 规则上下文
            
        Returns:
            表达式结果
        """
        if not expression:
            return True
        evaluator = SafeExpressionEvaluator(context)
        return evaluator.evaluate(expression)


def validate_rule_for_object_type(rule: MetaRule, object_type: ObjectType) -> Tuple[bool, str]:
    """
    验证规则是否适用于对象类型
    
    规则与对象类型的约束矩阵：
    | 规则类型 | ENTITY | VIEW | VIRTUAL |
    |---------|--------|------|---------|
    | Validation | [OK] | [WARNING] | [OK] |
    | Constraint | [OK] | [X] | [X] |
    | Computation | [OK] | [X] | [OK] |
    | StateTransition | [OK] | [X] | [X] |
    | Trigger | [OK] | [OK] | [OK] |
    | Derivation | [OK] | [OK] | [X] |
    """
    rule_type = rule.rule_type
    
    if object_type == ObjectType.ENTITY:
        return True, ""
    
    if object_type == ObjectType.VIEW:
        if rule_type == RuleType.CONSTRAINT:
            return False, "视图对象不支持约束规则"
        if rule_type == RuleType.COMPUTATION:
            return False, "视图对象不支持计算规则"
        if rule_type == RuleType.STATE_TRANSITION:
            return False, "视图对象不支持状态转换规则"
        return True, ""
    
    if object_type == ObjectType.VIRTUAL:
        if rule_type == RuleType.CONSTRAINT:
            return False, "虚拟对象不支持约束规则"
        if rule_type == RuleType.STATE_TRANSITION:
            return False, "虚拟对象不支持状态转换规则"
        if rule_type == RuleType.DERIVATION:
            return False, "虚拟对象不支持派生规则"
        return True, ""
    
    return True, ""


def resolve_metric_ref(ref: MetricReference, context: RuleContext) -> Any:
    """
    解析指标引用
    
    Args:
        ref: 指标引用
        context: 规则上下文
        
    Returns:
        指标值
    """
    obj = registry.get(ref.object_id)
    if not obj:
        raise ValueError("Object not found: {0}".format(ref.object_id))
    
    if ref.function_id:
        func = obj.get_function(ref.function_id)
        if not func:
            raise ValueError("Function not found: {0}.{1}".format(ref.object_id, ref.function_id))
        return execute_function(func, context)
    
    if ref.field_id:
        if obj.object_type == ObjectType.VIEW and obj.view_config:
            return _query_view_field(obj, ref.field_id, ref.filter, context)
        return context.get_field_value(ref.field_id)
    
    return None


def execute_function(func: MetaFunction, context: RuleContext) -> Any:
    """
    执行计算函数
    
    Args:
        func: 计算函数
        context: 规则上下文
        
    Returns:
        计算结果
    """
    expression = func.expression
    
    for ref in func.references:
        parts = ref.split(".")
        if len(parts) == 2:
            obj_id, field_id = parts
            metric_ref = MetricReference(object_id=obj_id, field_id=field_id)
            value = resolve_metric_ref(metric_ref, context)
            expression = expression.replace(ref, str(value) if value is not None else "0")
    
    return ExpressionEvaluator.evaluate(expression, context)


def _query_view_field(obj: MetaObject, field_id: str, filter_expr: str, context: RuleContext) -> Any:
    """查询视图字段值"""
    return context.get_field_value(field_id)


class RuleExecutor:
    """规则执行器基类"""
    
    def __init__(self):
        self._custom_handlers: Dict[str, Callable] = {}
    
    def register_handler(self, rule_id: str, handler: Callable) -> None:
        """注册自定义规则处理器"""
        self._custom_handlers[rule_id] = handler
    
    def execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        """执行规则"""
        if not rule.enabled:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Rule is disabled",
            )
        
        valid, msg = validate_rule_for_object_type(rule, context.meta_object.object_type)
        if not valid:
            return RuleResult(
                success=False,
                rule_id=rule.id,
                rule_name=rule.name,
                message=msg,
            )
        
        if rule.metric_refs:
            self._resolve_metric_refs(rule, context)
        
        if rule.id in self._custom_handlers:
            return self._custom_handlers[rule.id](rule, context)
        
        return self._do_execute(rule, context)
    
    def _resolve_metric_refs(self, rule: MetaRule, context: RuleContext) -> None:
        """解析指标引用并注入到上下文"""
        for ref in rule.metric_refs:
            try:
                value = resolve_metric_ref(ref, context)
                key = "{0}.{1}".format(ref.object_id, ref.field_id or ref.function_id)
                context.data["metric_" + key] = value
            except Exception as e:
                logger.warning("RuleExecutor failed to resolve metric ref: %s - %s",
                    ref.object_id, str(e))
    
    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        """子类实现具体执行逻辑"""
        return RuleResult(success=True, rule_id=rule.id, rule_name=rule.name)


class ValidationExecutor(RuleExecutor):
    """校验规则执行器"""
    
    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        if not isinstance(rule, MetaValidation):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Not a validation rule",
            )
        
        if rule.condition:
            condition_result = ExpressionEvaluator.evaluate(rule.condition, context)
            if not condition_result:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Condition not met, skipped",
                )
        
        action_result = ExpressionEvaluator.evaluate(rule.action, context)
        
        if action_result:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Validation passed",
            )
        else:
            return RuleResult(
                success=False,
                rule_id=rule.id,
                rule_name=rule.name,
                message=rule.message or "Validation failed",
                severity=rule.severity,
            )


class ComputationExecutor(RuleExecutor):
    """计算规则执行器"""
    
    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        if not isinstance(rule, MetaComputation):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Not a computation rule",
            )
        
        if rule.compute_on_change and rule.source_fields:
            source_changed = any(
                context.is_field_changed(f) for f in rule.source_fields
            )
            if not source_changed:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Source fields not changed, skipped",
                )
        
        if rule.condition:
            condition_result = ExpressionEvaluator.evaluate(rule.condition, context)
            if not condition_result:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Condition not met, skipped",
                )
        
        try:
            result_value = ExpressionEvaluator.evaluate(rule.formula, context)
            
            if rule.target_field:
                context.set_field_value(rule.target_field, result_value)
            
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Computation executed",
                data={"result": result_value, "target_field": rule.target_field},
            )
        except Exception as e:
            return RuleResult(
                success=False,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Computation error: {0}".format(str(e)),
                severity=ValidationSeverity.ERROR,
            )


class StateTransitionExecutor(RuleExecutor):
    """状态转换规则执行器"""
    
    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        if not isinstance(rule, MetaStateTransition):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Not a state transition rule",
            )

        current_state = context.original_data.get(rule.state_field)
        if current_state is None:
            current_state = context.get_field_value(rule.state_field)

        # 使用 data 中的当前值（而不是原始值）来判断匹配
        # 这样能避免多个 state_transition rules 在同一 trigger 中相互覆盖
        effective_state = context.get_field_value(rule.state_field)
        if effective_state is None:
            effective_state = current_state

        # 允许三种情况触发：
        # 1. effective_state 等于 rule.to_state（前端请求的就是目标状态）
        # 2. effective_state 在 from_states 中（默认值或前端的中间状态）
        if effective_state != rule.to_state and effective_state not in rule.from_states:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Effective state not in from_states or to_state, skipped",
            )

        # 如果已经被其他 rule 改成了别的 to_state，跳过当前 rule
        if effective_state != current_state and effective_state != rule.to_state:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="State already changed by another rule to {0}, skipped".format(effective_state),
            )
        
        if rule.condition:
            condition_result = ExpressionEvaluator.evaluate(rule.condition, context)
            if not condition_result:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Condition not met, skipped",
                )
        
        context.set_field_value(rule.state_field, rule.to_state)
        
        entered_at_field = f"{rule.state_field}_entered_at"
        has_entered_at = any(
            f.id == entered_at_field
            for f in context.meta_object.fields
        )
        if has_entered_at:
            context.set_field_value(entered_at_field, datetime.now())
        
        return RuleResult(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            message="State transitioned from {0} to {1}".format(current_state, rule.to_state),
            data={
                "from_state": current_state,
                "to_state": rule.to_state,
            },
        )


class TriggerExecutor(RuleExecutor):
    """触发规则执行器"""
    
    def __init__(self):
        super().__init__()
        self._handlers: Dict[str, Callable] = {}
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        self._handlers[event_type] = handler
    
    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        if not isinstance(rule, MetaTrigger):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Not a trigger rule",
            )
        
        if rule.condition:
            condition_result = ExpressionEvaluator.evaluate(rule.condition, context)
            if not condition_result:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Condition not met, skipped",
                )
        
        if rule.handler in self._handlers:
            try:
                handler = self._handlers[rule.handler]
                result = handler(context)
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Trigger executed",
                    data={"handler_result": result},
                )
            except Exception as e:
                return RuleResult(
                    success=False,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Trigger error: {0}".format(str(e)),
                    severity=ValidationSeverity.WARNING,
                )
        else:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Handler '{0}' not registered, skipped".format(rule.handler),
                )


class DerivationExecutor(RuleExecutor):
    """派生规则执行器"""
    
    def __init__(self, data_source=None):
        super().__init__()
        self.ds = data_source
    
    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        from meta.core.models import MetaDerivation, DerivationType, DerivationStrategy
        
        if not isinstance(rule, MetaDerivation):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Not a derivation rule",
            )
        
        if not rule.enabled:
            return RuleResult(success=True, rule_id=rule.id, rule_name=rule.name, message="Disabled")
        
        try:
            if rule.derivation_type == DerivationType.AGGREGATION:
                return self._execute_aggregation(rule, context)
            elif rule.derivation_type == DerivationType.TRANSFORMATION:
                return self._execute_transformation(rule, context)
            elif rule.derivation_type == DerivationType.FILTERING:
                return self._execute_filtering(rule, context)
            elif rule.derivation_type == DerivationType.ENRICHMENT:
                return self._execute_enrichment(rule, context)
            else:
                return RuleResult(
                    success=True,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message="Derivation type not implemented: {0}".format(rule.derivation_type.value),
                )
        except Exception as e:
            return RuleResult(
                success=False,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Derivation error: {0}".format(str(e)),
                severity=ValidationSeverity.ERROR,
            )
    
    def _execute_aggregation(self, rule: MetaDerivation, context: RuleContext) -> RuleResult:
        """执行聚合派生"""
        if not self.ds:
            return RuleResult(success=True, rule_id=rule.id, rule_name=rule.name, message="No data source")
        
        from meta import get_meta_object
        source_meta = get_meta_object(rule.source_object)
        target_meta = get_meta_object(rule.target_object)
        
        if not source_meta or not target_meta:
            return RuleResult(success=False, rule_id=rule.id, rule_name=rule.name, message="Source or target object not found")
        
        sql = "SELECT "
        
        select_parts = []
        for agg in rule.aggregates:
            if agg.function == "COUNT":
                select_parts.append("COUNT(*) AS {0}".format(agg.target_field))
            elif agg.function == "SUM":
                select_parts.append("SUM({0}) AS {1}".format(agg.source_field, agg.target_field))
            elif agg.function == "AVG":
                select_parts.append("AVG({0}) AS {1}".format(agg.source_field, agg.target_field))
            elif agg.function == "MAX":
                select_parts.append("MAX({0}) AS {1}".format(agg.source_field, agg.target_field))
            elif agg.function == "MIN":
                select_parts.append("MIN({0}) AS {1}".format(agg.source_field, agg.target_field))
        
        sql += ", ".join(select_parts)
        sql += " FROM {0}".format(source_meta.table_name)
        
        if rule.group_by:
            group_cols = []
            for g in rule.group_by:
                field = next((f for f in source_meta.fields if f.id == g), None)
                if field:
                    group_cols.append(field.db_column)
            if group_cols:
                sql += " GROUP BY " + ", ".join(group_cols)
        
        if rule.filter:
            sql += " WHERE {0}".format(rule.filter)
        
        results = self.ds.query(sql)
        
        return RuleResult(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            message="Aggregation executed: {0} records".format(len(results) if results else 0),
            data={"results": results, "sql": sql},
        )
    
    def _execute_transformation(self, rule: MetaDerivation, context: RuleContext) -> RuleResult:
        """执行转换派生"""
        transformed_data = {}
        
        for mapping in rule.field_mappings:
            source_value = context.get_field_value(mapping.source_field)
            
            if source_value is None and mapping.default is not None:
                transformed_data[mapping.target_field] = mapping.default
            elif mapping.transform:
                expr = mapping.transform
                try:
                    temp_context = RuleContext(
                        context.meta_object,
                        {"source": source_value, **context.data},
                        context.original_data
                    )
                    result = ExpressionEvaluator.evaluate(expr, temp_context)
                    transformed_data[mapping.target_field] = result if result is not None else source_value
                except:
                    transformed_data[mapping.target_field] = source_value
            else:
                transformed_data[mapping.target_field] = source_value
        
        for key, value in transformed_data.items():
            context.set_field_value(key, value)
        
        return RuleResult(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            message="Transformation executed",
            data={"transformed": transformed_data},
        )
    
    def _execute_filtering(self, rule: MetaDerivation, context: RuleContext) -> RuleResult:
        """执行过滤派生"""
        if not self.ds:
            return RuleResult(success=True, rule_id=rule.id, rule_name=rule.name, message="No data source")
        
        from meta import get_meta_object
        source_meta = get_meta_object(rule.source_object)
        
        if not source_meta:
            return RuleResult(success=False, rule_id=rule.id, rule_name=rule.name, message="Source object not found")
        
        sql = "SELECT * FROM {0}".format(source_meta.table_name)
        
        if rule.filter:
            sql += " WHERE {0}".format(rule.filter)
        
        if rule.order_by:
            order_parts = []
            for o in rule.order_by:
                if o.startswith("-"):
                    order_parts.append("{0} DESC".format(o[1:]))
                else:
                    order_parts.append("{0} ASC".format(o))
            sql += " ORDER BY " + ", ".join(order_parts)
        
        results = self.ds.query(sql)
        
        return RuleResult(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            message="Filtering executed: {0} records".format(len(results) if results else 0),
            data={"results": results},
        )
    
    def _execute_enrichment(self, rule: MetaDerivation, context: RuleContext) -> RuleResult:
        """执行增强派生"""
        enriched_data = dict(context.data)
        
        for target_field in rule.target_fields:
            field = next((f for f in context.meta_object.fields if f.id == target_field), None)
            if field and field.compute_expr:
                expr = field.compute_expr
                try:
                    temp_context = RuleContext(
                        context.meta_object,
                        enriched_data,
                        context.original_data
                    )
                    result = ExpressionEvaluator.evaluate(expr, temp_context)
                    if result is not None:
                        enriched_data[target_field] = result
                        context.set_field_value(target_field, result)
                except:
                    pass
        
        return RuleResult(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            message="Enrichment executed",
            data={"enriched_fields": rule.target_fields},
        )


class RuleEngine:
    """
    规则引擎
    
    统一管理所有规则的执行。
    """
    
    def __init__(self, data_source=None):
        self.data_source = data_source
        self.validation_executor = ValidationExecutor()
        self.computation_executor = ComputationExecutor()
        self.state_transition_executor = StateTransitionExecutor()
        self.trigger_executor = TriggerExecutor()
        self.derivation_executor = DerivationExecutor(data_source)
    
    def execute_rules(self, meta_object: MetaObject, trigger: RuleTrigger,
                      data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None
                      ) -> RuleExecutionReport:
        """
        执行指定触发时机的所有规则
        
        Args:
            meta_object: 元模型对象
            trigger: 触发时机
            data: 当前数据
            original_data: 原始数据（更新时使用）
            
        Returns:
            RuleExecutionReport 执行报告
        """
        report = RuleExecutionReport(trigger=trigger)
        context = RuleContext(meta_object, data, original_data,
                              data_source=self.data_source)
        
        rules = meta_object.get_rules_by_trigger(trigger)
        rules = sorted(rules, key=lambda r: r.priority)
        
        for rule in rules:
            result = self._execute_rule(rule, context)
            report.add_result(result)
            
            if not result.success and result.severity == ValidationSeverity.ERROR:
                break
        
        return report
    
    def _execute_rule(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        """根据规则类型选择执行器"""
        if rule.rule_type == RuleType.VALIDATION:
            return self.validation_executor.execute(rule, context)
        elif rule.rule_type == RuleType.COMPUTATION:
            return self.computation_executor.execute(rule, context)
        elif rule.rule_type == RuleType.STATE_TRANSITION:
            return self.state_transition_executor.execute(rule, context)
        elif rule.rule_type == RuleType.TRIGGER:
            return self.trigger_executor.execute(rule, context)
        elif rule.rule_type == RuleType.CONSTRAINT:
            return self.validation_executor.execute(rule, context)
        elif rule.rule_type == RuleType.DERIVATION:
            return self.derivation_executor.execute(rule, context)
        else:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Rule type '{0}' not implemented".format(rule.rule_type.value),
            )
    
    def validate(self, meta_object: MetaObject, data: Dict[str, Any],
                 trigger: RuleTrigger = RuleTrigger.BEFORE_SAVE) -> RuleExecutionReport:
        """
        执行校验
        
        Args:
            meta_object: 元模型对象
            data: 待校验数据
            trigger: 触发时机
            
        Returns:
            RuleExecutionReport
        """
        return self.execute_rules(meta_object, trigger, data)
    
    def compute(self, meta_object: MetaObject, data: Dict[str, Any],
                original_data: Optional[Dict[str, Any]] = None,
                changed_fields: Optional[set] = None,
                use_chain: bool = True) -> Dict[str, Any]:
        """
        执行计算规则
        
        Args:
            meta_object: 元模型对象
            data: 当前数据
            original_data: 原始数据
            changed_fields: 变更的字段（用于增量计算）
            use_chain: 是否使用规则链执行器
            
        Returns:
            计算后的数据
        """
        context = RuleContext(meta_object, data, original_data,
                              data_source=self.data_source)
        
        if use_chain:
            try:
                from meta.core.rule_chain import ImplicitRuleChainExecutor, RuleNodeType
                chain_executor = ImplicitRuleChainExecutor(meta_object)
                chain_result = chain_executor.execute(
                    data=data,
                    original_data=original_data,
                    changed_fields=changed_fields,
                )
                context.data = chain_result.data
                for change in chain_result.changes:
                    if change.field_id not in context.changed_fields:
                        context.changed_fields.append(change.field_id)
            except ValueError as e:
                logger.warning("RuleEngine chain execution failed, falling back to priority order: %s", str(e))
                self._compute_by_priority(meta_object, context)
        else:
            self._compute_by_priority(meta_object, context)
        
        return context.data
    
    def _compute_by_priority(self, meta_object: MetaObject, context) -> None:
        """按优先级顺序执行计算规则"""
        computations = meta_object.get_computations()
        computations = sorted(computations, key=lambda r: r.priority)
        
        for rule in computations:
            if rule.enabled:
                self.computation_executor.execute(rule, context)
    
    def register_trigger_handler(self, handler_name: str, handler: Callable) -> None:
        """注册触发器处理器"""
        self.trigger_executor.register_event_handler(handler_name, handler)
    
    def register_custom_validator(self, rule_id: str, handler: Callable) -> None:
        """注册自定义校验器"""
        self.validation_executor.register_handler(rule_id, handler)
