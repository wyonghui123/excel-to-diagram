# -*- coding: utf-8 -*-
"""控制参数解析 —— 「参数定义 + 参数取值」两表的唯一读取入口。

依据: meta/schemas/control_parameter_def.yaml / control_parameter_value.yaml 头注释

口径（与 YAML 头注释逐条对应）:
  ① 一次装载全部 active 定义与取值，在内存里匹配 —— 禁止逐参数、逐行发 SQL；
  ② 行匹配 = 本行所有非空维度都等于调用方传入值（调用方缺某维度则含该维度的行不命中）；
  ③ 候选按 (specificity_rank, id) 升序，首个命中获胜；
  ④ 全不命中回落 control_parameter_def.default_value；
  ⑤ 取值按 def.value_type 解释；解释失败记 ERROR 并回落默认值（不打断单据落库）。

性能口径: 实例级缓存 + 写入后 invalidate()。参照 SourcingResolver 的装载方式
（meta/services/sourcing_service.py），配置表小、装载成本低，内存匹配是毫秒级。

边界: 本服务只解析参数，不负责把结果快照到单据 —— 快照由单据写入方完成
（否则调整参数会改变历史单据的执行行为）。
"""

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: 维度列（与 control_parameter_value 的字段一一对应；空 = 通配）
DIMENSION_FIELDS: Tuple[str, ...] = (
    'org_id',
    'document_type_id',
    'line_type_id',
    'item_group_id',
)

_TRUE_VALUES = ('true', '1', 'yes', 'y', '是')
_FALSE_VALUES = ('false', '0', 'no', 'n', '否')


class ControlParameterError(ValueError):
    """参数定义或取值不合法。"""


class ControlParameterResolver:
    """参数解析器。

    `_fetch_defs` / `_fetch_values` 可覆写（单测注入，不依赖真实库）。
    `data_source` 未注入时懒取平台库。
    """

    DEF_SQL = ("SELECT * FROM control_parameter_defs WHERE status = 'active'")
    VALUE_SQL = ("SELECT * FROM control_parameter_values WHERE status = 'active'")

    def __init__(self, data_source=None):
        self._ds = data_source
        self._defs_by_code: Optional[Dict[str, Dict[str, Any]]] = None
        self._values_by_param: Optional[Dict[Any, List[Dict[str, Any]]]] = None

    # ------------------------------------------------------------------
    # 数据源与缓存
    # ------------------------------------------------------------------

    @property
    def ds(self):
        """懒取默认数据源（避免 import 期连库）。"""
        if self._ds is None:
            from meta.core.db_path import get_meta_db_path
            from meta.core.datasource import get_data_source
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    def invalidate(self) -> None:
        """配置写入后调用，丢弃缓存。"""
        self._defs_by_code = None
        self._values_by_param = None

    def _fetch_defs(self) -> List[Dict[str, Any]]:
        return self.ds.query(self.DEF_SQL)

    def _fetch_values(self) -> List[Dict[str, Any]]:
        return self.ds.query(self.VALUE_SQL)

    def _ensure_loaded(self) -> Tuple[Dict[str, Dict[str, Any]], Dict[Any, List[Dict[str, Any]]]]:
        if self._defs_by_code is None:
            try:
                self._defs_by_code = {row['code']: row for row in (self._fetch_defs() or [])}
            except Exception as e:
                logger.error(f'[control_parameter] 装载参数定义失败: {e}')
                self._defs_by_code = {}
        if self._values_by_param is None:
            grouped: Dict[Any, List[Dict[str, Any]]] = {}
            try:
                for row in (self._fetch_values() or []):
                    grouped.setdefault(row.get('control_parameter_id'), []).append(row)
            except Exception as e:
                logger.error(f'[control_parameter] 装载参数取值失败: {e}')
                grouped = {}
            for rows in grouped.values():
                rows.sort(key=lambda r: (_rank(r), r.get('id') or 0))
            self._values_by_param = grouped
        return self._defs_by_code, self._values_by_param

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def resolve(self, code: str, dims: Dict[str, Any]) -> Any:
        """解析单个参数，返回按 value_type 解释后的值（无定义时返回 None）。"""
        return self.resolve_many([code], dims).get(code)

    def resolve_many(self, codes: Iterable[str], dims: Dict[str, Any],
                     domain: Optional[str] = None) -> Dict[str, Any]:
        """批量解析：一次装载、内存匹配，返回 {code: value}。

        `domain` 非空时，不属于该域的参数视为无定义（返回 None）。
        """
        defs, values = self._ensure_loaded()
        result: Dict[str, Any] = {}
        for code in codes:
            definition = defs.get(code)
            if not definition or (domain and definition.get('domain') != domain):
                result[code] = None
                continue
            hit = self._match(values.get(definition.get('id'), []), dims)
            raw = hit.get('value') if hit else definition.get('default_value')
            result[code] = self._convert(definition, raw)
        return result

    def explain(self, code: str, dims: Dict[str, Any]) -> Dict[str, Any]:
        """返回命中链，供实施排查「为什么这个参数取了这个值」。"""
        defs, values = self._ensure_loaded()
        definition = defs.get(code)
        if not definition:
            return {'code': code, 'value': None, 'source': {'type': 'missing'},
                    'candidates': []}

        rows = values.get(definition.get('id'), [])
        matched = [r for r in rows if self._matches(r, dims)]
        hit = matched[0] if matched else None
        raw = hit.get('value') if hit else definition.get('default_value')
        return {
            'code': code,
            'value': self._convert(definition, raw),
            'source': ({'type': 'value', 'value_id': hit.get('id'),
                        'specificity_rank': hit.get('specificity_rank')}
                       if hit else {'type': 'default'}),
            'candidates': [
                {'value_id': r.get('id'),
                 'specificity_rank': r.get('specificity_rank'),
                 'dims': {f: r.get(f) for f in DIMENSION_FIELDS},
                 'value': r.get('value')}
                for r in matched
            ],
        }

    # ------------------------------------------------------------------
    # 匹配与类型解释
    # ------------------------------------------------------------------

    def _match(self, rows: List[Dict[str, Any]], dims: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for row in rows:
            if self._matches(row, dims):
                return row
        return None

    @staticmethod
    def _matches(row: Dict[str, Any], dims: Dict[str, Any]) -> bool:
        for field in DIMENSION_FIELDS:
            expected = row.get(field)
            if expected is None:
                continue  # 该维度通配
            if field not in dims:
                return False  # 行要求该维度，但调用方没提供
            if not _same(dims.get(field), expected):
                return False
        return True

    def _convert(self, definition: Dict[str, Any], raw: Any) -> Any:
        value_type = str(definition.get('value_type') or 'string')
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        try:
            if value_type == 'bool':
                text = str(raw).strip().lower()
                if text in _TRUE_VALUES:
                    return True
                if text in _FALSE_VALUES:
                    return False
                raise ControlParameterError(f'布尔值无法解析: {raw!r}')
            if value_type == 'int':
                return int(str(raw).strip())
            if value_type == 'decimal':
                return float(str(raw).strip())
            if value_type == 'ref':
                return int(str(raw).strip())
            return raw  # enum / string 原样返回
        except (TypeError, ValueError) as e:
            logger.error('[control_parameter] 参数 %s 取值 %r 与值类型 %s 不符: %s',
                         definition.get('code'), raw, value_type, e)
            fallback = definition.get('default_value')
            if fallback is not None and str(fallback) != str(raw):
                return self._convert({**definition, 'value_type': value_type, 'default_value': None}, fallback)
            return None


def _same(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return str(left) == str(right)


def _rank(row: Dict[str, Any]) -> int:
    value = row.get('specificity_rank')
    return int(value) if value is not None else 100


_resolver: Optional[ControlParameterResolver] = None


def get_control_parameter_resolver() -> ControlParameterResolver:
    """进程级单例（懒创建）。"""
    global _resolver
    if _resolver is None:
        _resolver = ControlParameterResolver()
    return _resolver
