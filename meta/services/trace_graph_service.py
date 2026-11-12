# -*- coding: utf-8 -*-
"""统一追溯读面查询服务（阶段 4）

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.10 / §6 阶段 4

职责边界:
- 只读 `v_demand_trace_graph`（view 元模型），不写任何表；
- 视图只做列投影与分层，方向/深度遍历由本服务实现（不把运行时条件写进 SQL 视图）；
- 视图缺失（doc_flow 未启用 / 缺基表迁移 [SKIP]）时返回空，不阻断业务。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VIEW_NAME = 'v_demand_trace_graph'

_COLUMNS = (
    'layer', 'id', 'relation',
    'source_object_type', 'source_object_id', 'source_line_id',
    'target_object_type', 'target_object_id', 'target_line_id',
    'qty', 'signed_qty', 'status',
    'peg_type', 'plan_version', 'valid_from', 'valid_to', 'occurred_at',
)

_LAYERS = ('execution', 'plan')


def _text(value: Any) -> str:
    return '' if value is None else str(value)


class TraceGraphService:
    """在统一追溯视图上做列表与逐跳遍历（只读）。"""

    def __init__(self, ds):
        self.ds = ds

    # ── 基础查询 ────────────────────────────────────────────────────────────

    def list_links(
        self,
        *,
        source_object_type: Optional[str] = None,
        source_object_id: Any = None,
        target_object_type: Optional[str] = None,
        target_object_id: Any = None,
        layer: Optional[str] = None,
        relation: Optional[str] = None,
        active_only: bool = False,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """按端点/分层/关系过滤追溯关系（视图可能不存在 → 空列表）。"""
        where: List[str] = []
        params: List[Any] = []

        if source_object_type:
            where.append('source_object_type = ?')
            params.append(source_object_type)
        if source_object_id is not None:
            where.append('source_object_id = ?')
            params.append(_text(source_object_id))
        if target_object_type:
            where.append('target_object_type = ?')
            params.append(target_object_type)
        if target_object_id is not None:
            where.append('target_object_id = ?')
            params.append(_text(target_object_id))
        if layer:
            if layer not in _LAYERS:
                raise ValueError('layer must be one of %s' % (_LAYERS,))
            where.append('layer = ?')
            params.append(layer)
        if relation:
            where.append('relation = ?')
            params.append(relation)
        if active_only:
            where.append("status = 'active'")

        sql = 'SELECT {0} FROM {1}'.format(', '.join(_COLUMNS), VIEW_NAME)
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY occurred_at DESC, id'
        sql += ' LIMIT ?'
        params.append(max(1, min(int(limit), 1000)))

        try:
            rows = self.ds.execute(sql, params).fetchall()
        except Exception as exc:  # noqa: BLE001 - 视图缺失/半迁移按空读处理
            logger.debug('[TraceGraphService] view unavailable: %s', exc)
            return []

        return [dict(zip(_COLUMNS, row)) for row in rows]

    # ── 方向/深度遍历 ───────────────────────────────────────────────────────

    def trace(
        self,
        object_type: str,
        object_id: Any,
        *,
        direction: str = 'down',
        max_depth: int = 3,
        layer: Optional[str] = None,
        active_only: bool = True,
        max_nodes: int = 200,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """从指定对象出发逐跳遍历。

        direction='down' 沿 source→target（正向追溯）；
        direction='up'   沿 target→source（反查来源）。
        """
        if direction not in ('down', 'up'):
            raise ValueError("direction must be 'down' or 'up'")

        depth_limit = max(1, min(int(max_depth), 10))
        node_limit = max(1, min(int(max_nodes), 1000))
        start = (object_type, _text(object_id))

        nodes: Dict[tuple, Dict[str, Any]] = {
            start: {'object_type': object_type, 'object_id': start[1], 'depth': 0}
        }
        links: Dict[str, Dict[str, Any]] = {}
        frontier = [(start, 0)]

        while frontier and len(nodes) < node_limit:
            next_frontier = []
            for (obj_type, obj_id), depth in frontier:
                if depth >= depth_limit:
                    continue

                if direction == 'down':
                    rows = self.list_links(
                        source_object_type=obj_type, source_object_id=obj_id,
                        layer=layer, active_only=active_only, limit=node_limit)
                else:
                    rows = self.list_links(
                        target_object_type=obj_type, target_object_id=obj_id,
                        layer=layer, active_only=active_only, limit=node_limit)

                for row in rows:
                    if row['id'] not in links:
                        links[row['id']] = row
                    if direction == 'down':
                        nxt = (row['target_object_type'], row['target_object_id'])
                    else:
                        nxt = (row['source_object_type'], row['source_object_id'])
                    if nxt not in nodes:
                        if len(nodes) >= node_limit:
                            break
                        nodes[nxt] = {
                            'object_type': nxt[0],
                            'object_id': nxt[1],
                            'depth': depth + 1,
                        }
                        next_frontier.append((nxt, depth + 1))
            frontier = next_frontier

        return {
            'nodes': sorted(nodes.values(),
                            key=lambda n: (n['depth'], n['object_type'], n['object_id'])),
            'links': sorted(links.values(),
                            key=lambda r: (r.get('occurred_at') or '', r['id'])),
        }
