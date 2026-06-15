# -*- coding: utf-8 -*-
"""[V1.1.13 2026-06-15] Dim Scope 关系层级包容 (Hierarchical Inclusion via Relationship)

SAP / Oracle EBS 风格的 "hierarchical inclusion" 语义:
    引入 1 个 BO (业务对象) → 引入它的 Service Module
    引入 1 个 SM         → 引入它的 Sub Domain
    引入 1 个 SD         → 引入它的 Domain
    引入 1 个 BO (关系的另一头) → 递归引入它的所有祖先层级

实施背景:
    之前 V1.1.9 关系 OR 派生 (source/target 任一端在 dim scope 内)
    + V1.1.11/12 图表视图补外部 BO/SM (is_external=true)
    → 但 dim scope 派生的 "+N" 统计 (域+0/子+0/服+0/对+3) 仍然偏严
    → SAP 风格应当递归引出完整层级 (域+1~2/子+1~2/服+3/对+3)
    → 这样图表视图的 "+N" 显示与用户预期一致

用法:
    from meta.services.dim_scope_relationship_includer import DimScopeRelationshipIncluder
    includer = DimScopeRelationshipIncluder(ds)
    expanded_scope = includer.expand(
        initial_scope={'domain_ids': [703], 'sub_domain_ids': [], 'sm_ids': [], 'bo_ids': []},
        relationships=relationships_list
    )
    # expanded_scope 含域/子/服/对 4 个 key, 每个是 set[int]
"""
import logging
from typing import Dict, List, Set, Any, Iterable

logger = logging.getLogger(__name__)


class DimScopeRelationshipIncluder:
    """[V1.1.13] SAP 风格 dim scope 层级包容 (通过关系递归引出完整层级)"""

    # 层级顺序 (从下到上): BO -> SM -> SD -> D
    HIERARCHY = ['bo', 'sm', 'sd', 'd']

    def __init__(self, data_source):
        self.ds = data_source

    def expand(
        self,
        initial_scope: Dict[str, Iterable[int]],
        relationships: List[Dict[str, Any]],
    ) -> Dict[str, Set[int]]:
        """[V1.1.13] 扩展 dim scope, 沿关系 + 层级反向 BFS 递归

        Args:
            initial_scope: 初始 dim scope, 含 4 个 key:
                - 'domain_ids': set/list of domain ids
                - 'sub_domain_ids': set/list of sub_domain ids
                - 'sm_ids': set/list of service_module ids
                - 'bo_ids': set/list of business_object ids
            relationships: 关系列表 (TEST333 当前 dim scope 派生可见的),
                每条含 'source_bo_id' / 'target_bo_id'

        Returns:
            扩展后的 dim scope, 4 个 key 均为 set[int]:
                {'domain_ids': {...}, 'sub_domain_ids': {...}, 'sm_ids': {...}, 'bo_ids': {...}}

        算法:
            1. 收集 initial_scope 中所有可见 id, 标记 visited
            2. BFS 队列: 把所有"另一头在 visited 里"的关系的 target/source 加入 visited
            3. 每加入新实体, 沿层级反推 (BO -> SM -> SD -> D) 加入 visited
            4. 重复 2-3 直到不再有新增

        示例 (TEST333, dim scope=domain 703):
            initial_scope = {d:[703], sd:[], sm:[], bo:[]}
            10 条关系, 其中 rel 111 src=471(d=703) tgt=474(库存 d=704)
            → BFS:
              1. 471 在 dim scope (d=703) -> visited
              2. rel 111 另一头 474 -> visited 加入 bo
              3. 474 沿层级: sm 140 (仓库管理) -> visited 加入 sm
              4. 140 沿层级: sd ? -> visited 加入 sd
              5. sd 沿层级: d 704 (库存管理) -> visited 加入 d
              6. 继续 BFS, 直到不再新增
            最终 expanded_scope:
              d = {703, 704, 706}
              sd = {域内 SD, 库存 SD, 财务 SD}
              sm = {域内 SM, 140 仓库管理, 145 应付发票}
              bo = {域内 BO, 474 库存, 488 应付发票, 489 付款单, 492 TEST333}
        """
        # 1. 初始化 visited
        visited = {
            'd': set(initial_scope.get('domain_ids', [])),
            'sd': set(initial_scope.get('sub_domain_ids', [])),
            'sm': set(initial_scope.get('sm_ids', [])),
            'bo': set(initial_scope.get('bo_ids', [])),
        }
        # 同时也按 code 收集, 方便查 (因为 BO/SM 之间靠 sm_id 关联)
        # 这里用 id-based 即可, 因为 relationships 用 bo_id

        # 2. BFS 队列: 收集当前所有已知 entity, 不断扩展
        # 用 frontier 跟踪"本轮新加入的", 每轮基于 frontier 触发"通过关系 + 层级"扩展
        frontier = {  # 初始: 所有 visited 都算 frontier
            'd': set(visited['d']),
            'sd': set(visited['sd']),
            'sm': set(visited['sm']),
            'bo': set(visited['bo']),
        }

        max_iterations = 10  # 防止意外循环
        for iteration in range(max_iterations):
            new_added = False

            # ── Step 1: 通过关系扩展 (另一头加入) ──
            for rel in relationships:
                src = rel.get('source_bo_id') or rel.get('sourceBoId')
                tgt = rel.get('target_bo_id') or rel.get('targetBoId')
                if not src or not tgt:
                    continue
                # 关系的另一头加入 (如果一头已在 visited)
                if src in visited['bo'] and tgt not in visited['bo']:
                    visited['bo'].add(tgt)
                    frontier['bo'].add(tgt)
                    new_added = True
                elif tgt in visited['bo'] and src not in visited['bo']:
                    visited['bo'].add(src)
                    frontier['bo'].add(src)
                    new_added = True

            # ── Step 2: 沿层级反推 (BO -> SM -> SD -> D) ──
            for new_bo_id in list(frontier['bo']):
                # 查 BO 的 service_module_id
                sm_id = self._get_sm_id_for_bo(new_bo_id)
                if sm_id and sm_id not in visited['sm']:
                    visited['sm'].add(sm_id)
                    frontier['sm'].add(sm_id)
                    new_added = True

            for new_sm_id in list(frontier['sm']):
                # 查 SM 的 sub_domain_id
                sd_id = self._get_sub_domain_id_for_sm(new_sm_id)
                if sd_id and sd_id not in visited['sd']:
                    visited['sd'].add(sd_id)
                    frontier['sd'].add(sd_id)
                    new_added = True

            for new_sd_id in list(frontier['sd']):
                # 查 SD 的 domain_id
                d_id = self._get_domain_id_for_sub_domain(new_sd_id)
                if d_id and d_id not in visited['d']:
                    visited['d'].add(d_id)
                    frontier['d'].add(d_id)
                    new_added = True

            # ── 退出条件: 本轮无新增 ──
            if not new_added:
                break

            # 清空 frontier, 下一轮重新计算
            frontier = {k: set() for k in self.HIERARCHY}

        # 4. 返回
        logger.info(
            f'[V1.1.13] DimScopeRelationshipIncluder: '
            f'initial=({len(visited["d"])}d/{len(visited["sd"])}sd/{len(visited["sm"])}sm/{len(visited["bo"])}bo) '
            f'final=({len(visited["d"])}d/{len(visited["sd"])}sd/{len(visited["sm"])}sm/{len(visited["bo"])}bo) '
            f'iterations={iteration + 1}'
        )
        return visited

    def _get_sm_id_for_bo(self, bo_id: int):
        """查 BO 的 service_module_id"""
        try:
            row = self.ds.execute(
                'SELECT service_module_id FROM business_objects WHERE id = ?', [bo_id]
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f'[_get_sm_id_for_bo] bo_id={bo_id} failed: {e}')
            return None

    def _get_sub_domain_id_for_sm(self, sm_id: int):
        """查 SM 的 sub_domain_id"""
        try:
            row = self.ds.execute(
                'SELECT sub_domain_id FROM service_modules WHERE id = ?', [sm_id]
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f'[_get_sub_domain_id_for_sm] sm_id={sm_id} failed: {e}')
            return None

    def _get_domain_id_for_sub_domain(self, sd_id: int):
        """查 SD 的 domain_id"""
        try:
            row = self.ds.execute(
                'SELECT domain_id FROM sub_domains WHERE id = ?', [sd_id]
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f'[_get_domain_id_for_sub_domain] sd_id={sd_id} failed: {e}')
            return None
