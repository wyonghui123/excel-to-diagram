# -*- coding: utf-8 -*-
"""
[Plan B Task 3] 组织多职能视图服务 (对齐 spec 13 §5.1d)

业务规则:
- 一个 org 可同时是"行政组织"+"成本中心"+"利润中心" (多职能)
- is_primary 标识主职能 (一个 org 最多一个主职能)
- 添加新职能时: 若 is_primary=True, 先把现有主职能降级

DB Schema (Plan A 已建表):
    org_functions (
        id, org_id, function_type,
        is_primary, effective_from, effective_to
    )

[2026-10-20] org → party 内部表示联动:
    org 具备「我方主体」职能（BU/LE，见 SUBJECT_FUNCTIONS）时，须在 parties
    表存在对应的 source='org' 内部表示（party_internal 面的唯一来源，也是
    party_relation 我方侧 party1_id 的候选集）。本服务的读写**绕过 CRUD 管线**
    （见 meta/api/org_function_api.py），故必须在 add_function 内自行挂钩——
    否则通过职能接口授予主体身份时不会建出内部表示。
    口径与「不删除原则」见 meta/services/org_party_mirror_service.py 模块头。
"""
import logging
from typing import List, Dict, Optional

from meta.services.org_party_mirror_service import SUBJECT_FUNCTIONS

logger = logging.getLogger(__name__)


class OrgFunctionService:
    def __init__(self, data_source):
        self.ds = data_source

    def _rows_to_dicts(self, cursor):
        if not cursor.description:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_functions_by_org(self, org_id: int) -> List[Dict]:
        """获取某 org 的所有职能"""
        cursor = self.ds.execute(
            "SELECT id, org_id, function_type, is_primary, effective_from, effective_to "
            "FROM org_functions WHERE org_id = ? ORDER BY is_primary DESC, function_type",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def add_function(self, org_id: int, function_type: str, is_primary: bool = False) -> Optional[int]:
        """给 org 添加新职能

        Args:
            org_id: org id
            function_type: administrative/legal_entity/management_unit/procurement/accounting
                /profit_center/cost_center/sales/warehouse/manufacturing/inventory/storage
            is_primary: 是否主职能

        Returns:
            新职能 id, 失败返回 None
        """
        # [D3 扩白名单 2026-10-05] 蓝图 v2.5 拍板: 供应侧职能一次加齐
        #   (sales / warehouse / manufacturing) + 顺带补齐库存账地职能
        #   (inventory / storage —— location 轴 "账=org" 所需, §3.5.1)。
        valid_types = {
            'administrative', 'legal_entity', 'management_unit',
            'procurement', 'accounting', 'profit_center', 'cost_center',
            'sales', 'warehouse', 'manufacturing', 'inventory', 'storage',
        }
        if function_type not in valid_types:
            return None

        # 若 is_primary=True, 先把现有主职能降级
        if is_primary:
            self.ds.execute(
                "UPDATE org_functions SET is_primary = 0 WHERE org_id = ?",
                [org_id]
            )

        # 插入新职能 (INSERT OR IGNORE 避免重复)
        cursor = self.ds.execute(
            "INSERT OR IGNORE INTO org_functions (org_id, function_type, is_primary) VALUES (?, ?, ?)",
            [org_id, function_type, 1 if is_primary else 0]
        )

        # [2026-10-20] 职能变更后同步 org 的 party 内部表示。
        #   sync_party_for_org 自判我方主体职能（BU/LE，详见 SUBJECT_FUNCTIONS）
        #   ⇒ 非主体职能直接返回 None，故无条件调用即可。
        self._sync_party_internal(org_id)

        return cursor.lastrowid if cursor.lastrowid else None

    def _sync_party_internal(self, org_id: int) -> None:
        """按 org 当前职能对齐其 party 内部表示（失败不阻断职能写入）。"""
        try:
            from meta.services.org_party_mirror_service import OrgPartyMirrorService
            OrgPartyMirrorService(self.ds).sync_party_for_org(org_id)
        except Exception as e:
            logger.warning(
                f"[OrgFunctionService] party 内部表示同步失败 org#{org_id}: {e}"
            )

    def remove_function(self, org_id: int, function_type: str) -> bool:
        """移除 org 的某职能

        [2026-10-20] 移除 legal_entity 时**不删**已建的 party 内部表示:
        party_relations.party1_id / party2_id 是指向 parties.id 的真外键，删除会
        破坏既有关系引用；内部表示一旦被引用即成为历史事实，只能停用不能抹除。

        [2026-10-20 补] 但原实现**无差别**地对所有行套用「不删」，导致「零引用的
        内部表示」永久滞留在 party_internal 候选集中（幽灵主体），而
        org_legal_entity 谓词实时读 org_functions 已不含该 org ⇒ 两个下拉口径分叉。
        故在删除职能后调用 handle_function_revoked 做引用检测并记日志：
          - 有引用 → warning（保留是正确的，历史事实）
          - 零引用 → info（点名该行成为游离行，人工确认后再清理）
        **本步刻意不删数据**：全库 FK 均 on_delete=NO ACTION，无数据库兜底，
        删除动作待真实数据验证引用扫描准确性后再定。
        """
        cursor = self.ds.execute(
            "DELETE FROM org_functions WHERE org_id = ? AND function_type = ?",
            [org_id, function_type]
        )
        removed = cursor.rowcount > 0

        # 仅当撤掉的是「我方主体」职能（BU/LE）时才可能影响内部表示；
        # 其余职能（administrative 等）与 party 镜像无关，不做任何额外动作。
        if removed and function_type in SUBJECT_FUNCTIONS:
            self._handle_party_internal_revoked(org_id)

        return removed

    def _handle_party_internal_revoked(self, org_id: int) -> None:
        """主体职能（BU/LE）被撤销后的引用检测（失败不阻断职能删除）。

        与 add_function 的 _sync_party_internal 成对：那个负责「建」，这个负责
        「查」。两侧都直连服务、绕过 CRUD 管线，故必须各自挂钩。
        """
        try:
            from meta.services.org_party_mirror_service import (
                OrgPartyMirrorService,
            )
            OrgPartyMirrorService(self.ds).handle_function_revoked(org_id)
        except Exception as e:
            logger.warning(
                f"[OrgFunctionService] party 内部表示引用检测失败 org#{org_id}: {e}"
            )

    def get_primary_function(self, org_id: int) -> Optional[Dict]:
        """获取主职能 (is_primary=1)"""
        cursor = self.ds.execute(
            "SELECT id, org_id, function_type, is_primary, effective_from, effective_to "
            "FROM org_functions WHERE org_id = ? AND is_primary = 1 LIMIT 1",
            [org_id]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None
