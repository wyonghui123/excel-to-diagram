# -*- coding: utf-8 -*-
"""行类型确定 —— 单据类型 × 物料组 → 行类型。

依据: meta/schemas/line_type_assignment.yaml 头注释「命中规则」

  ① 只在同一单据类型下取候选；
  ② 行匹配 = 记录物料组为空（通配）或等于单据行的物料组；
  ③ 候选按 (specificity_rank, id) 升序，首个命中获胜；
  ④ 全不命中回落单据类型（type_definitions.level='header'）的 default_type_id；
  ⑤ 单据类型不存在或未配置默认行类型 → 返回 None，由调用方决定报错还是放行。

当前使用方只有销售（scope_bo='sales_order'），故单据类型候选按该 scope 过滤；
泛化到其他域时把 scope 提为参数即可。

性能口径: 一次装载全部 active 确定规则 + 单据类型默认值，内存匹配；实例级缓存，
配置写入后 invalidate()（类型字典 / 销售配置拦截器在 after_action 里调用）。
配置表规模是「单据类型数 × 物料组数」，远小于按行查询的机会成本，禁止 N+1。

边界: 本服务只回答「用哪个行类型」，不做行类型本身的行为判定 ——
行为开关统一走 control_parameter_def / control_parameter_value。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_RANK_FALLBACK = 100
_SCOPE_BO = 'sales_order'


class LineTypeError(ValueError):
    """行类型确定失败（当前仅用于参数缺失等硬错误）。"""


class LineTypeResolver:
    """按单据类型 + 物料组确定行类型。

    覆写 `_fetch_assignments` / `_fetch_doc_types` 即可注入测试数据（不依赖真实库）。
    """

    ASSIGNMENT_SQL = (
        "SELECT id, document_type_id, item_group_id, specificity_rank, "
        "line_type_id FROM line_type_assignments "
        "WHERE status = 'active'")
    DOC_TYPE_SQL = (
        "SELECT id, code, default_type_id FROM type_definitions "
        "WHERE scope_bo = '%s' AND level = 'header' AND status = 'active'"
        % _SCOPE_BO)

    def __init__(self, data_source=None):
        self._ds = data_source
        self._by_doc_type: Optional[Dict[Any, List[Dict[str, Any]]]] = None
        self._defaults: Optional[Dict[Any, Any]] = None

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
        self._by_doc_type = None
        self._defaults = None

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def resolve(self, doc_type_id: Any,
                item_group_id: Any = None) -> Dict[str, Any]:
        """确定单据行应使用的行类型。

        Returns:
            {
              'line_type_id': int | None,
              'source': 'assignment' | 'default' | 'missing',
              'assignment_id': int | None,
              'specificity_rank': int | None,
              'doc_type_id': 入参,
              'item_group_id': 入参,
            }
        """
        by_doc_type, defaults = self._ensure_loaded()
        base = {
            'line_type_id': None,
            'source': 'missing',
            'assignment_id': None,
            'specificity_rank': None,
            'doc_type_id': doc_type_id,
            'item_group_id': item_group_id,
        }

        if doc_type_id is None or str(doc_type_id) not in defaults:
            logger.warning('[line_type] 单据类型 %r 不存在或已停用', doc_type_id)
            return base

        hit = self._match(by_doc_type.get(str(doc_type_id), []), item_group_id)
        if hit is not None:
            base.update({
                'line_type_id': hit.get('line_type_id'),
                'source': 'assignment',
                'assignment_id': hit.get('id'),
                'specificity_rank': _rank(hit.get('specificity_rank')),
            })
            return base

        default_line_type = defaults.get(str(doc_type_id))
        if default_line_type is not None:
            base.update({'line_type_id': default_line_type,
                         'source': 'default'})
        return base

    def explain(self, doc_type_id: Any,
                item_group_id: Any = None) -> Dict[str, Any]:
        """返回命中链，供实施排查「为什么这一行用了这个行类型」。"""
        by_doc_type, defaults = self._ensure_loaded()
        rows = by_doc_type.get(str(doc_type_id), [])
        matched = [r for r in rows if _matches(r, item_group_id)]
        result = self.resolve(doc_type_id, item_group_id)
        result['candidates'] = [
            {'assignment_id': r.get('id'),
             'item_group_id': r.get('item_group_id'),
             'specificity_rank': _rank(r.get('specificity_rank')),
             'line_type_id': r.get('line_type_id')}
            for r in matched
        ]
        result['default_type_id'] = defaults.get(str(doc_type_id))
        return result

    # ------------------------------------------------------------------
    # 装载与匹配
    # ------------------------------------------------------------------

    def _ensure_loaded(self):
        if self._by_doc_type is None or self._defaults is None:
            grouped: Dict[Any, List[Dict[str, Any]]] = {}
            defaults: Dict[Any, Any] = {}
            try:
                for row in self._fetch_assignments() or []:
                    grouped.setdefault(str(row.get('document_type_id')), []).append(row)
                for row in self._fetch_doc_types() or []:
                    defaults[str(row.get('id'))] = row.get('default_type_id')
            except Exception as e:
                logger.error(f'[line_type] 装载确定规则失败: {e}')
                grouped, defaults = {}, {}
            for rows in grouped.values():
                rows.sort(key=lambda r: (_rank(r.get('specificity_rank')),
                                         r.get('id') or 0))
            self._by_doc_type = grouped
            self._defaults = defaults
        return self._by_doc_type, self._defaults

    def _fetch_assignments(self) -> List[Dict[str, Any]]:
        return self.ds.query(self.ASSIGNMENT_SQL)

    def _fetch_doc_types(self) -> List[Dict[str, Any]]:
        return self.ds.query(self.DOC_TYPE_SQL)

    @staticmethod
    def _match(rows: List[Dict[str, Any]],
               item_group_id: Any) -> Optional[Dict[str, Any]]:
        for row in rows:
            if _matches(row, item_group_id):
                return row
        return None


def _matches(row: Dict[str, Any], item_group_id: Any) -> bool:
    """物料组为空 = 通配；否则必须与调用方一致。"""
    expected = row.get('item_group_id')
    if expected is None:
        return True
    if item_group_id is None:
        return False
    return str(expected) == str(item_group_id)


def _rank(value: Any) -> int:
    if value is None:
        return _RANK_FALLBACK
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return _RANK_FALLBACK


_resolver: Optional[LineTypeResolver] = None


def get_line_type_resolver() -> LineTypeResolver:
    """进程级单例（懒创建）。"""
    global _resolver
    if _resolver is None:
        _resolver = LineTypeResolver()
    return _resolver
