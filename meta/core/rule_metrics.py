# -*- coding: utf-8 -*-
"""派生度量注册表（L0，spec-rule-model M3 / FR-003）

口径：
  · 一个度量（code / formula / inputs / unit / precision）只定义一次；
  · 校验规则与审批策略按 code 引用，不各自重算；
  · 同一度量在同一张单据内只计算一次（`MetricSession` 缓存），多处引用结果一致；
  · 派生值不写回单据行。如落库缓存，必须带 `derived_cache=True` 标记，
    且不得被其他规则当事实源读取（本模块不做持久化）。

配置期校验（NFR-003）：
  · 结构非法（空 code / 空 formula / precision 越界 / 重复定义）在 `register()` 即报错；
  · 公式引用未声明的输入、引用不存在的度量、度量循环依赖由 `validate()` 汇总报错。
"""

import ast
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from meta.core.rule_executor import ExpressionEvaluator, RuleContext

GLOBAL_SCOPE = '*'
MAX_PRECISION = 12


class MetricError(Exception):
    """度量配置或求值错误。"""


def _apply_precision(value: Any, precision: Optional[int]) -> Any:
    if value is None or precision is None:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return value
    try:
        quant = Decimal(1).scaleb(-int(precision))
        return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return value


@dataclass(frozen=True)
class MetricDefinition:
    """一条派生度量定义（不可变，注册后不可原地修改）。"""

    code: str
    formula: str
    inputs: Tuple[str, ...] = ()
    unit: str = ''
    precision: int = 2
    object_type: str = GLOBAL_SCOPE

    def __post_init__(self) -> None:
        code = str(self.code or '').strip()
        formula = str(self.formula or '').strip()
        if not code:
            raise MetricError('度量 code 不能为空')
        if not formula:
            raise MetricError('度量 {0} 的 formula 不能为空'.format(code))
        raw_inputs = self.inputs or ()
        if isinstance(raw_inputs, str):
            raw_inputs = (raw_inputs,)
        inputs: List[str] = []
        for item in raw_inputs:
            name = str(item or '').strip()
            if not name:
                raise MetricError('度量 {0} 的 inputs 不能含空项'.format(code))
            if name not in inputs:
                inputs.append(name)
        if isinstance(self.precision, bool) or not isinstance(self.precision, int):
            raise MetricError('度量 {0} 的 precision 必须是整数'.format(code))
        if self.precision < 0 or self.precision > MAX_PRECISION:
            raise MetricError(
                '度量 {0} 的 precision 需在 0..{1} 之间'.format(code, MAX_PRECISION))
        object.__setattr__(self, 'code', code)
        object.__setattr__(self, 'formula', formula)
        object.__setattr__(self, 'inputs', tuple(inputs))
        object.__setattr__(self, 'unit', str(self.unit or '').strip())
        object.__setattr__(self, 'object_type', str(self.object_type or GLOBAL_SCOPE).strip())


def _formula_identifiers(formula: str) -> Tuple[Set[str], Set[str], Optional[str]]:
    """返回（声明外的自由变量名、调用的函数名、解析错误）。"""
    try:
        tree = ast.parse(formula, mode='eval')
    except SyntaxError as exc:
        return set(), set(), '公式语法错误：{0}'.format(exc.msg)
    func_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                func_names.add(func.id)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return names - func_names, func_names, None


class MetricRegistry:
    """度量定义表。key = (object_type, code)，`*` 表示跨对象共享定义。"""

    def __init__(self) -> None:
        self._items: Dict[Tuple[str, str], MetricDefinition] = {}

    def register(self, definition: MetricDefinition) -> MetricDefinition:
        if not isinstance(definition, MetricDefinition):
            raise MetricError('注册项必须是 MetricDefinition')
        key = (definition.object_type, definition.code)
        if key in self._items:
            raise MetricError(
                '度量重复定义：{0}.{1}'.format(definition.object_type, definition.code))
        self._items[key] = definition
        return definition

    def replace_scope(self, object_type: str,
                      definitions: Iterable[MetricDefinition]) -> None:
        """整体替换某 ``object_type`` 下的度量定义（加载期幂等重入）。

        场景：YAML ``metrics:`` 段在每次目录加载 / reload 时重新灌入，
        必须覆盖旧定义而不是抛「重复定义」。
        """
        definitions = list(definitions)
        for definition in definitions:
            if definition.object_type != object_type:
                raise MetricError(
                    '度量 {0}.{1} 的 object_type 与替换范围 {2} 不一致'.format(
                        definition.object_type, definition.code, object_type))
        for key in [item for item in self._items if item[0] == object_type]:
            del self._items[key]
        for definition in definitions:
            self.register(definition)

    def get(self, object_type: str, code: str) -> Optional[MetricDefinition]:
        if not code:
            return None
        return (self._items.get((object_type, code))
                or self._items.get((GLOBAL_SCOPE, code)))

    def definitions(self, object_type: Optional[str] = None) -> List[MetricDefinition]:
        if object_type is None:
            return list(self._items.values())
        return [d for (scope, _), d in self._items.items()
                if scope in (object_type, GLOBAL_SCOPE)]

    def codes(self, object_type: str) -> List[str]:
        return sorted(d.code for d in self.definitions(object_type))

    def validate(self, known_fields: Optional[Dict[str, Iterable[str]]] = None
                 ) -> List[str]:
        """整表校验；返回中文错误列表，空列表表示通过。"""
        errors: List[str] = []
        for (scope, _code), definition in sorted(self._items.items()):
            names, func_names, parse_error = _formula_identifiers(definition.formula)
            if parse_error:
                errors.append('{0}.{1}：{2}'.format(scope, definition.code, parse_error))
                continue
            undeclared = sorted(names - set(definition.inputs))
            if undeclared:
                errors.append('{0}.{1}：公式引用未声明的输入 {2}'.format(
                    scope, definition.code, ', '.join(undeclared)))
            fields = None
            if known_fields is not None and scope != GLOBAL_SCOPE:
                fields = set(known_fields.get(scope, ()))
            for name in definition.inputs:
                metric = self.get(scope, name)
                if metric is not None:
                    continue
                if fields is not None and name not in fields:
                    errors.append(
                        '{0}.{1}：输入 {2} 既不是度量也不是该对象字段'.format(
                            scope, definition.code, name))
        errors.extend(self._cycle_errors())
        return errors

    def _cycle_errors(self) -> List[str]:
        """度量之间的循环依赖（A→B→A）在配置期报错。"""
        errors: List[str] = []
        state: Dict[Tuple[str, str], int] = {}  # 0=未访问 1=访问中 2=完成

        def deps(scope: str, code: str) -> List[Tuple[str, str]]:
            definition = self._items[(scope, code)]
            result = []
            for name in definition.inputs:
                key = (scope, name)
                if key not in self._items and (GLOBAL_SCOPE, name) in self._items:
                    key = (GLOBAL_SCOPE, name)
                if key in self._items:
                    result.append(key)
            return result

        def visit(key: Tuple[str, str], path: List[str]) -> None:
            if state.get(key) == 2:
                return
            if state.get(key) == 1:
                errors.append('度量循环依赖：{0}'.format(' → '.join(path + [key[1]])))
                return
            state[key] = 1
            for child in deps(*key):
                visit(child, path + [key[1]])
            state[key] = 2

        for key in self._items:
            if state.get(key, 0) == 0:
                visit(key, [])
        return errors


DEFAULT_METRIC_REGISTRY = MetricRegistry()


def _default_evaluate(formula: str, bindings: Dict[str, Any]) -> Any:
    context = RuleContext(
        SimpleNamespace(id='_metric', fields=[]), dict(bindings))
    return ExpressionEvaluator.evaluate(formula, context)


class MetricSession:
    """一张单据的度量化会话：同一度量只计算一次，多引用结果一致。"""

    def __init__(self, object_type: str, record_id: Any, record: Dict[str, Any],
                 registry: Optional[MetricRegistry] = None,
                 evaluator: Optional[Callable[[str, Dict[str, Any]], Any]] = None):
        self._object_type = object_type
        self._record_id = record_id
        self._record = dict(record or {})
        self._registry = registry if registry is not None else DEFAULT_METRIC_REGISTRY
        self._evaluator = evaluator or _default_evaluate
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._resolving: List[str] = []

    # ------------------------------------------------------------------
    def resolve(self, code: str) -> Any:
        if code in self._cache:
            return self._cache[code]['value']
        definition = self._registry.get(self._object_type, code)
        if definition is None:
            raise MetricError('未注册的度量：{0}.{1}'.format(self._object_type, code))
        if code in self._resolving:
            raise MetricError('度量循环依赖：{0}'.format(
                ' → '.join(self._resolving + [code])))
        self._resolving.append(code)
        try:
            bindings: Dict[str, Any] = {}
            for name in definition.inputs:
                if self._registry.get(self._object_type, name) is not None:
                    bindings[name] = self.resolve(name)
                else:
                    bindings[name] = self._record.get(name)
            value = self._evaluator(definition.formula, bindings)
            value = _apply_precision(value, definition.precision)
        finally:
            self._resolving.pop()
        self._cache[code] = {
            'code': code,
            'value': value,
            'unit': definition.unit,
            'precision': definition.precision,
            # 落库/快照时必须能被识别为派生值，不能当事实源
            'derived_cache': True,
        }
        return value

    def is_metric(self, code: str) -> bool:
        return self._registry.get(self._object_type, code) is not None

    def enrich(self, record: Dict[str, Any], codes: Iterable[str]) -> Dict[str, Any]:
        """返回带派生值的记录副本，只解析被引用的度量；不改动入参。"""
        extra = {code: self.resolve(code)
                 for code in dict.fromkeys(codes) if self.is_metric(code)}
        if not extra:
            return record
        merged = dict(record)
        merged.update(extra)
        return merged

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {code: dict(item) for code, item in sorted(self._cache.items())}

    @property
    def computed_codes(self) -> List[str]:
        return sorted(self._cache)