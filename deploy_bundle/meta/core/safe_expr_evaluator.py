# -*- coding: utf-8 -*-
"""
Safe Expression Evaluator

Replaces Python built-in `eval()` for evaluating YAML-defined condition expressions
using AST-based parsing with strict whitelist validation.

Usage:
    from meta.core.safe_expr_evaluator import safe_evaluate
    result = safe_evaluate("self.child_count == 0", {"self": field_accessor})

Replaces eval() calls in:
  - condition_evaluator.py    : deletability conditions
  - constraint_engine.py      : unique scope conditions
  - rule_chain.py             : formula evaluation fallback
  - field_policy_engine.py    : field policy conditions
"""

import ast
import operator

_ALLOWED_COMPARE_OPS = frozenset({
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn,
    ast.Is, ast.IsNot,
})

_ALLOWED_BOOL_OPS = frozenset({
    ast.And, ast.Or,
})

_ALLOWED_UNARY_OPS = frozenset({
    ast.Not, ast.UAdd, ast.USub,
})

_ALLOWED_BIN_OPS = frozenset({
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
})

_FORBIDDEN_NAMES = frozenset({
    'import', 'exec', 'eval', 'compile', 'open', 'input',
    '__import__', 'globals', 'locals', 'vars', 'dir',
    'getattr', 'setattr', 'delattr', 'hasattr',
    'property', 'classmethod', 'staticmethod',
    '__builtins__',
})


def safe_evaluate(expr, context=None):
    """
    Safely evaluate a condition expression using AST parsing.

    Args:
        expr: The expression string to evaluate
        context: Dict mapping variable names to their values

    Returns:
        The result of evaluating the expression

    Raises:
        ValueError: If the expression contains forbidden constructs
    """
    if not expr or not isinstance(expr, str) or not expr.strip():
        return True

    ctx = context or {}

    try:
        tree = ast.parse(expr.strip(), mode='eval')
        _validate_node(tree)
        return _eval_node(tree.body, ctx)
    except SyntaxError:
        return False
    except ValueError:
        return False


def _validate_node(node):
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if child.id in _FORBIDDEN_NAMES:
                raise ValueError(
                    "Forbidden name in expression: {0}".format(child.id))
            if child.id.startswith('_') and child.id.endswith('_'):
                raise ValueError(
                    "Forbidden dunder name: {0}".format(child.id))

        elif isinstance(child, ast.Attribute):
            if child.attr.startswith('_'):
                raise ValueError(
                    "Forbidden attribute: {0}".format(child.attr))
            if child.attr in ('__class__', '__bases__', '__subclasses__',
                              '__mro__', '__globals__', '__code__',
                              '__closure__', '__func__', '__self__'):
                raise ValueError(
                    "Forbidden attribute: {0}".format(child.attr))

        elif isinstance(child, ast.Call):
            raise ValueError("Function calls are not allowed")

        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            raise ValueError("Import statements are not allowed")

        elif isinstance(child, ast.BinOp):
            if type(child.op) not in _ALLOWED_BIN_OPS:
                raise ValueError(
                    "Forbidden binary operator: {0}".format(type(child.op).__name__))

        elif isinstance(child, ast.Subscript):
            raise ValueError("Subscript access is not allowed")

        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp,
                                ast.GeneratorExp)):
            raise ValueError("Comprehensions are not allowed")

        elif isinstance(child, ast.Lambda):
            raise ValueError("Lambda expressions are not allowed")

        elif isinstance(child, ast.Dict):
            continue

        elif isinstance(child, ast.List):
            continue

        elif isinstance(child, ast.Tuple):
            continue

        elif isinstance(child, ast.Set):
            continue

        elif isinstance(child, ast.Constant):
            continue

        elif isinstance(child, ast.Compare):
            for op in child.ops:
                if type(op) not in _ALLOWED_COMPARE_OPS:
                    raise ValueError(
                        "Forbidden comparison: {0}".format(type(op).__name__))

        elif isinstance(child, ast.BoolOp):
            if type(child.op) not in _ALLOWED_BOOL_OPS:
                raise ValueError(
                    "Forbidden boolean operator: {0}".format(type(child.op).__name__))

        elif isinstance(child, ast.UnaryOp):
            if type(child.op) not in _ALLOWED_UNARY_OPS:
                raise ValueError(
                    "Forbidden unary operator: {0}".format(type(child.op).__name__))


def _eval_node(node, ctx):
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        return _resolve_name(node.id, ctx)

    if isinstance(node, ast.Attribute):
        obj = _eval_node(node.value, ctx)
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(node.attr)
        try:
            return getattr(obj, node.attr)
        except AttributeError:
            return None

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, ctx)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        return None

    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, ctx) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        return None

    if isinstance(node, ast.Compare):
        return _eval_compare(node, ctx)

    if isinstance(node, ast.BinOp):
        return _eval_binop(node, ctx)

    if isinstance(node, ast.List):
        return [_eval_node(elt, ctx) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, ctx) for elt in node.elts)

    if isinstance(node, ast.Dict):
        keys = [_eval_node(k, ctx) if k else None for k in node.keys]
        values = [_eval_node(v, ctx) for v in node.values]
        return dict(zip(keys, values))

    if isinstance(node, ast.Set):
        return {_eval_node(elt, ctx) for elt in node.elts}

    raise ValueError("Unsupported node type: {0}".format(type(node).__name__))


def _resolve_name(name, ctx):
    if name in ('True', 'False', 'None'):
        return {'True': True, 'False': False, 'None': None}[name]
    if name in ctx:
        return ctx[name]
    raise ValueError("Name '{0}' is not defined in context".format(name))


def _eval_compare(node, ctx):
    left = _eval_node(node.left, ctx)
    for op, comparator in zip(node.ops, node.comparators):
        right = _eval_node(comparator, ctx)
        if isinstance(op, ast.Eq):
            if left != right:
                return False
        elif isinstance(op, ast.NotEq):
            if left == right:
                return False
        elif isinstance(op, ast.Lt):
            if not (left < right):
                return False
        elif isinstance(op, ast.LtE):
            if not (left <= right):
                return False
        elif isinstance(op, ast.Gt):
            if not (left > right):
                return False
        elif isinstance(op, ast.GtE):
            if not (left >= right):
                return False
        elif isinstance(op, ast.In):
            if left not in right:
                return False
        elif isinstance(op, ast.NotIn):
            if left in right:
                return False
        elif isinstance(op, ast.Is):
            if left is not right:
                return False
        elif isinstance(op, ast.IsNot):
            if left is right:
                return False
        else:
            raise ValueError(
                "Forbidden comparison: {0}".format(type(op).__name__))
        left = right
    return True


def _eval_binop(node, ctx):
    left = _eval_node(node.left, ctx)
    right = _eval_node(node.right, ctx)
    
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        return left / right
    if isinstance(node.op, ast.FloorDiv):
        return left // right
    if isinstance(node.op, ast.Mod):
        return left % right
    if isinstance(node.op, ast.Pow):
        return left ** right
    
    raise ValueError("Unsupported binary operator: {0}".format(type(node.op).__name__))
