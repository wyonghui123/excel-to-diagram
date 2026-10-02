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
    MetaDefaultRule,
    MetaStateTransition, MetaTrigger, MetaConstraint, MetaFunction, MetaDerivation,
    RuleType, RuleScope, RuleTrigger, ValidationSeverity, FieldType,
    ObjectType, MetricReference, registry
)
from meta.core.formula_functions import FormulaFunctionRegistry
from meta.core.cross_object_resolver import build_cross_object_locals
from meta.core.rule_provider import get_rule_provider


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


@dataclass
class DefaultLogEntry:
    """属性确定（默认值）规则单条判定日志

    [规则模型 T-12 2026-10-03] 对标 FR-010「可解释性 = 日志」。
    结构按**可回放**设计：含因子值快照，二期 dry-run 直接复用。

    字段语义：
    - ``seq``           排序后序号（先 priority 升序，再 rule.id 字典序）
    - ``hit``           条件是否命中
    - ``skip_reason``   未命中/未写入原因码
    - ``value``         带出的值（命中且写入时）
    - ``overwritten``   apply_mode=override 且覆盖了原有非空值
    - ``factor_snapshot`` condition 引用字段的取值快照
    """
    rule_id: str = ""
    rule_name: str = ""
    target_field: str = ""
    seq: int = 0
    priority: int = 100
    hit: bool = False
    skip_reason: str = ""     # condition_false / target_not_empty / apply_on_mismatch / not_first_match / no_value
    value: Any = None
    source_type: str = ""
    overwritten: bool = False
    factor_snapshot: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "target_field": self.target_field,
            "seq": self.seq,
            "priority": self.priority,
            "hit": self.hit,
            "skip_reason": self.skip_reason,
            "value": self.value,
            "source_type": self.source_type,
            "overwritten": self.overwritten,
            "factor_snapshot": self.factor_snapshot,
            "elapsed_ms": self.elapsed_ms,
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
        # [规则模型 T-08/T-09 2026-10-03] 属性确定规则所需的状态
        # auto_filled_fields: 由 DEFAULT 规则写入的字段集合（用于 RECOMPUTE_CLEAR 只清自动值）
        # change_source: 本次保存的变更来源 user_input / system / both（对标 EBS System vs User Changes）
        self.auto_filled_fields: set = set()
        self.change_source: str = "both"
        self.last_default_log: Optional[DefaultLogEntry] = None
        self.default_logs: List[DefaultLogEntry] = []
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
    | Default | [OK] | [X] | [OK] |
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
        if rule_type == RuleType.DEFAULT:
            return False, "视图对象不支持属性确定规则"
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


class DefaultExecutor(RuleExecutor):
    """属性确定（默认值）规则执行器

    [规则模型 T-07 2026-10-03]

    与 ComputationExecutor 的差异：本执行器**单条**判定一条 DEFAULT 规则，
    不做「分组 + 首个命中」——那是 ``RuleEngine.default_by_priority`` 的职责。
    本执行器只回答：「这条规则，此刻是否命中？命中则带出什么值？是否写入？」

    写入规则（严格遵循 Spec FR-005/FR-006/FR-007）：
    1. ``apply_on`` 不匹配本次 change_source → 跳过（skip_reason=apply_on_mismatch）
    2. ``condition`` 为假 → 跳过（condition_false）
    3. 解析取值；解析不出（None）→ 不写入（no_value）
    4. ``apply_mode=FILL_IF_EMPTY`` 且目标非空 → 不写入（target_not_empty）
    5. 否则写入；``apply_mode=OVERRIDE`` 且原值非空 → 标记 overwritten
    """

    SKIP_REASONS = (
        "condition_false", "target_not_empty", "apply_on_mismatch",
        "not_first_match", "no_value",
    )

    def _do_execute(self, rule: MetaRule, context: RuleContext) -> RuleResult:
        if not isinstance(rule, MetaDefaultRule):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Not a default rule",
            )

        started = datetime.now()
        target_field = rule.target_field
        entry = DefaultLogEntry(
            rule_id=rule.id,
            rule_name=rule.name,
            target_field=target_field,
            priority=rule.priority,
            source_type=rule.source_type,
            factor_snapshot=self._snapshot_factors(rule, context),
        )

        outcome = self._apply(rule, context, entry)
        entry.elapsed_ms = round((datetime.now() - started).total_seconds() * 1000, 3)
        context.last_default_log = entry

        return RuleResult(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            message=outcome,
            data={"default_log": entry.to_dict(), "target_field": target_field},
        )

    def _apply(self, rule: MetaDefaultRule, context: RuleContext,
               entry: DefaultLogEntry) -> str:
        """执行单条默认值规则，就地写回 entry，返回说明文本"""
        # 1) 来源开关
        if not self._apply_on_matches(rule, context):
            entry.skip_reason = "apply_on_mismatch"
            return "apply_on mismatch, skipped"

        # 2) 条件
        if rule.condition:
            if not ExpressionEvaluator.evaluate(rule.condition, context):
                entry.skip_reason = "condition_false"
                return "Condition not met, skipped"

        entry.hit = True

        if not entry.target_field:
            entry.skip_reason = "no_value"
            return "No target field declared"

        # 3) 取值
        try:
            value = self._resolve_source(rule, context)
        except Exception as e:
            entry.skip_reason = "no_value"
            logger.warning("DefaultExecutor source resolve failed: %s - %s", rule.id, str(e))
            return "Source resolve error: {0}".format(str(e))

        if value is None:
            entry.skip_reason = "no_value"
            return "No value derived"

        # 4) 覆盖语义
        current = context.get_field_value(entry.target_field)
        if rule.apply_mode == "fill_if_empty" and not self._is_empty(current):
            entry.skip_reason = "target_not_empty"
            return "Target not empty, skipped (fill_if_empty)"

        # 5) 写入
        entry.value = value
        entry.overwritten = (rule.apply_mode == "override") and not self._is_empty(current)
        context.set_field_value(entry.target_field, value)
        context.auto_filled_fields.add(entry.target_field)
        return "Default applied: {0} = {1!r}".format(entry.target_field, value)

    @staticmethod
    def _is_empty(value: Any) -> bool:
        return value is None or value == "" or (isinstance(value, (list, dict)) and len(value) == 0)

    @staticmethod
    def _apply_on_matches(rule: MetaDefaultRule, context: RuleContext) -> bool:
        rule_apply_on = (rule.apply_on or "both").lower()
        change_source = (getattr(context, "change_source", "both") or "both").lower()
        if rule_apply_on == "both" or change_source == "both":
            return True
        return rule_apply_on == change_source

    @staticmethod
    def _snapshot_factors(rule: MetaDefaultRule, context: RuleContext) -> Dict[str, Any]:
        """记录 condition 引用到的字段取值快照（供日志回放 / 二期 dry-run）"""
        snapshot: Dict[str, Any] = {}
        expr = rule.condition or ""
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr):
            if token in context.data:
                snapshot[token] = context.data.get(token)
        return snapshot

    @staticmethod
    def _resolve_source(rule: MetaDefaultRule, context: RuleContext) -> Any:
        """按 source_type 解析取值（对标 EBS Source 四类）"""
        source_type = (rule.source_type or "constant").lower()
        raw = rule.source_value

        if not raw:
            return None

        if source_type == "constant":
            return DefaultExecutor._literal(raw)

        if source_type == "field":
            return context.get_field_value(raw)

        if source_type in ("expression", "cross_object"):
            return ExpressionEvaluator.evaluate(raw, context)

        logger.warning("DefaultExecutor unknown source_type '%s' on rule %s", source_type, rule.id)
        return None

    @staticmethod
    def _literal(raw: str) -> Any:
        """常量字面量解析：能按 Python 字面量解析则还原类型，否则按原字符串"""
        try:
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return raw


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

        # [FIX Bug 2026-06-09] 状态转换规则 gating 修复
        # 原 bug: 当 status='active' 时, 3 个 state_transition rule (activate/lock/deactivate) 全部满足
        # 原 gating "effective_state == to_state OR effective_state in from_states", 导致
        # 1) 每次 user 普通 PUT update (不改 status) 都会 fire 至少 1 个 rule
        # 2) fire 后强制 set status=to_state + set status_entered_at=NOW(), 产生大量 audit log
        # 3) 多个 rule 串行 fire 时会反复覆盖 status_entered_at
        #
        # 正确语义: state_transition rule 只在状态真的需要变化时才 fire
        # - 显式 action 调用 (POST /actions/{rule_id}): effective_state 会被设为 to_state
        # - 中间状态过渡: effective_state 在 from_states 中但 != current_state
        # - 普通 update 不改 status: data dict 中没有 state_field → 必须跳过所有 rule
        # - 当前状态已经是 to_state: 跳过 (无变化)

        # Case 0: data dict 中没有 state_field 字段 (普通 update 不改 status)
        # 关键判断: 用户在 update 时是否真的请求了状态变化
        # - POST /actions/{rule_id}: action handler 会把 state_field 显式设到 data dict
        # - 普通 PUT /user/{id} (改 display_name 等): data dict 中没有 state_field
        if rule.state_field not in context.data:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="State field '{0}' not in update data, skipped (普通 update 不触发状态转换)".format(rule.state_field),
            )

        # Case 1: 当前已经是 to_state (无变化, 跳过)
        if current_state == rule.to_state:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Already in target state '{0}', skipped".format(rule.to_state),
            )

        # [FIX Bug 2026-06-12] Case 1.5: 用户未改变状态 (effective_state == current_state)
        # 场景: 用户编辑产品其他字段, 前端 form 自动提交当前 is_active=True (v-model 绑到 switch)
        # 期望: 跳过 rule, is_active 保持 True
        # 原 bug: deactivate_product rule 误触发, 把 True 强制改为 False
        # 关键: 只有 effective_state != current_state 时才说明用户改了状态
        # 边界: original_data 必须存在 (有"原始"状态可比较). 新建对象场景 (无 original_data) 跳过此检查
        if context.original_data and effective_state == current_state:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="State not changed by user (effective_state '{0}' == current_state), skipped (form 提交当前值, 非显式状态切换)".format(effective_state),
            )

        # Case 2: 已被其他 rule 改成了别的状态 (不是本 rule 的 to_state)
        if effective_state != current_state and effective_state != rule.to_state:
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="State already changed by another rule to '{0}', skipped".format(effective_state),
            )

        # Case 3: effective_state 必须 == to_state (显式 action) 或 in from_states (中间状态)
        #         关键: 如果 effective_state == current_state (普通 update 不改 status), 在 Case 1 已跳过
        if effective_state != rule.to_state and effective_state not in (rule.from_states or []):
            return RuleResult(
                success=True,
                rule_id=rule.id,
                rule_name=rule.name,
                message="Effective state '{0}' not in from_states or to_state, skipped".format(effective_state),
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
        # [规则模型 T-07 2026-10-03] 属性确定（默认值）规则执行器
        self.default_executor = DefaultExecutor()
    
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
        elif rule.rule_type == RuleType.DEFAULT:
            return self.default_executor.execute(rule, context)
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

    # ------------------------------------------------------------------
    # [规则模型 T-08 2026-10-03] 属性确定（默认值）规则执行
    # ------------------------------------------------------------------

    def default_by_priority(self, meta_object: MetaObject, context: RuleContext,
                            trigger: Optional[RuleTrigger] = RuleTrigger.BEFORE_SAVE
                            ) -> List['DefaultLogEntry']:
        """按「分组 + 首个命中」执行属性确定规则（**不得复用** `_compute_by_priority`）

        与 `_compute_by_priority` 的语义差异（Spec FR-005）：
        - 分组维度：``target_field``（同一目标字段内竞争）
        - 组内排序：``priority`` 升序；同 ``priority`` 以 ``rule.id`` 字典序 tie-break
        - 组内**首个「条件命中且实际写入成功」的规则获胜**，其后同组规则记
          ``skip_reason=not_first_match`` 不再写入
        - 组内无获胜规则时进入「再判定」（FR-007）：仅对已被本引擎标记为自动值的
          字段生效；``recompute=clear`` 清空，``recompute=keep``（默认）保留

        日志（FR-010）写入 ``context.default_logs`` 并返回。

        Args:
            trigger: 触及时机过滤；传 ``None`` 表示不过滤 trigger
        """
        rules = [r for r in get_rule_provider().get_default_rules(meta_object)
                 if getattr(r, 'enabled', True)]
        if trigger is not None:
            rules = [r for r in rules if not r.triggers or trigger in r.triggers]

        # 全局排序 + tie-break（对标 EBS 同序按字母序）
        rules.sort(key=lambda r: (r.priority, r.id))

        groups: Dict[str, List[MetaRule]] = {}
        for rule in rules:
            target = getattr(rule, 'target_field', '') or ''
            groups.setdefault(target, []).append(rule)

        logs: List[DefaultLogEntry] = []
        for target_field, group in groups.items():
            won = False
            for seq, rule in enumerate(group, start=1):
                self.default_executor.execute(rule, context)
                entry = context.last_default_log
                if entry is None:
                    continue
                entry.seq = seq
                if won:
                    entry.hit = False
                    entry.skip_reason = "not_first_match"
                    entry.value = None
                elif entry.hit and entry.value is not None:
                    won = True
                logs.append(entry)

            if not won:
                self._apply_recompute(group[0], target_field, context)

        context.default_logs = logs
        return logs

    @staticmethod
    def _apply_recompute(first_rule: MetaRule, target_field: str,
                         context: RuleContext) -> None:
        """再判定（Spec FR-007 / C10）：组内无获胜规则时处理旧的自动值

        仅清理**本引擎标记为自动值**的字段（``context.auto_filled_fields``），
        用户手工输入值不受影响。

        一期限制：标记不跨请求持久化（TBD-3），故该逻辑对「同一请求内的多次
        掩码/重判」有效；跨请求（历史保存遗留的自动值）暂不处理。
        """
        if not target_field or target_field not in context.auto_filled_fields:
            return
        policy = (getattr(first_rule, 'recompute', 'keep') or 'keep').lower()
        if policy == 'clear':
            context.set_field_value(target_field, None)
            context.auto_filled_fields.discard(target_field)

    def apply_defaults(self, meta_object: MetaObject, data: Dict[str, Any],
                       original_data: Optional[Dict[str, Any]] = None,
                       trigger: RuleTrigger = RuleTrigger.BEFORE_SAVE,
                       change_source: str = "both",
                       changed_fields: Optional[set] = None,
                       previously_auto_filled: Optional[set] = None
                       ) -> Tuple[Dict[str, Any], List['DefaultLogEntry']]:
        """属性确定入口（T-11 供 ``action_executor`` 在 BEFORE_SAVE 调用）

        Args:
            data: 待保存数据（**就地改写**后返回）
            original_data: 更新场景的原始数据
            change_source: ``user_input`` / ``system`` / ``both``（对标 EBS System vs User Changes）
            changed_fields: 本次变更字段（不传则由 RuleContext 自行比对 original_data）
            previously_auto_filled: 历史遗留的自动值字段标记（一期不持久化，默认空）

        Returns:
            ``(data, logs)``
        """
        context = RuleContext(meta_object, data, original_data, data_source=self.data_source)
        if changed_fields is not None:
            context.changed_fields = list(changed_fields)
        context.change_source = change_source
        if previously_auto_filled:
            context.auto_filled_fields.update(previously_auto_filled)

        logs = self.default_by_priority(meta_object, context, trigger=trigger)
        return context.data, logs
    
    def register_trigger_handler(self, handler_name: str, handler: Callable) -> None:
        """注册触发器处理器"""
        self.trigger_executor.register_event_handler(handler_name, handler)
    
    def register_custom_validator(self, rule_id: str, handler: Callable) -> None:
        """注册自定义校验器"""
        self.validation_executor.register_handler(rule_id, handler)
