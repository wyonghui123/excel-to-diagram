# -*- coding: utf-8 -*-
"""party 治理域服务 —— intra_trade 受控放行入口位（桩）

依据: docs/superpowers/specs/2026-10-04-f1-governance-domain-design.md
      §6（内部交易例外放行）/ §7.2-6（验收项）/ §9.2（步 2 收口方案）

语义钉死（§6）：
  1. 门禁两把：**功能码**（内部交易 / 内部开票，任一）× **单据上下文**
     （用户对单据组织域的可见性）——缺一不放行；
  2. 读取形态：按 `party_id` **直读**（detail 粒度），**不进入 archive 列表**
     —— 对外档案"恒排除 source='org'"语义不受影响；
  3. 审计留痕（放行解析行为）；
  4. 边界（P3 纪律）：放行的是"对 `source=org` 表示的引用解析"，
     不是"source=org 记录进入档案"。

**当前状态：桩**（§6-5「步 2 仅需预留解析入口位」）——门禁与审计已就位，
解析体待 F2+IV 接入（`NotImplementedError`）。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class IntraTradeGateError(PermissionError):
    """intra_trade 门禁未通过（缺功能码 或 单据上下文组织域不可见）—— 缺一不放行。"""


class PartyScopeService:
    """party 治理域的服务入口（步 2 仅含 intra_trade 放行位）。"""

    #: 门禁一：功能码（内部交易 / 内部开票，任一满足即可）
    #: [桩] 占位码 —— F2+IV 接入时按实际注册的功能权限码校准
    FUNCTION_KEYS = ('internal_trade:read', 'internal_invoice:read')

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 公开入口 ----------

    def resolve_party_for_intra_trade(
        self,
        party_id: int,
        *,
        user_id: int,
        doc_context: Optional[Dict[str, Any]] = None,
    ):
        """内部交易链路：对 `source=org` 表示的受控放行解析（§6）。

        门禁两把缺一不放行；双门禁通过后写审计留痕，再进入解析体。
        **解析体当前为桩**（§9.2）——待 F2+IV 接入。

        Args:
            party_id: 目标身份记录 ID（内部交易对手侧的 `source=org` 表示）
            user_id: 发起用户
            doc_context: 单据上下文（至少含 `org_id` —— 单据组织域）

        Raises:
            IntraTradeGateError: 功能码 或 单据上下文门禁未通过（不放行、不审计）
            NotImplementedError: 双门禁通过但解析体未接入（桩）
        """
        if not self._has_function_key(user_id):
            raise IntraTradeGateError('缺少内部交易/内部开票功能权限')

        target_org_id = (doc_context or {}).get('org_id')
        if not self._context_visible(user_id, target_org_id):
            raise IntraTradeGateError('单据上下文组织域不可见')

        self._audit(party_id, user_id, doc_context)
        raise NotImplementedError(
            'F1 §9.2 桩：intra_trade 受控放行解析体待 F2+IV 接入（门禁与审计已就位）'
        )

    # ---------- 门禁（可覆写，便于 F2 接线与单测注入） ----------

    def _has_function_key(self, user_id: int) -> bool:
        """门禁一：功能码（内部交易 / 内部开票）。

        权限查询异常 → fail-closed（视为无权限）。
        """
        from meta.services.permission_service import PermissionService

        svc = PermissionService(self.ds)
        for code in self.FUNCTION_KEYS:
            try:
                if svc.has_permission(user_id, code):
                    return True
            except Exception as e:  # 表缺失 / 查询异常 → fail-closed
                logger.warning(
                    f'[intra_trade] 功能码检查失败 user={user_id} code={code}: {e}')
        return False

    def _context_visible(self, user_id: int, target_org_id: Any) -> bool:
        """门禁二：单据上下文 —— 用户对单据组织域的可见性。

        [桩] 当前以**组织委托范围**（钥匙二）为可见性代理；精确口径随 F2+IV
        细化（§6-5）。查询异常 / 目标为空 → fail-closed。
        """
        if target_org_id is None:
            return False
        from meta.services.org_admin_scope_service import OrgAdminScopeService

        try:
            ok, _reason = OrgAdminScopeService(self.ds).check_org_scope(
                user_id, int(target_org_id), action='read')
            return bool(ok)
        except Exception as e:
            logger.warning(
                f'[intra_trade] 单据上下文档检查失败 user={user_id} '
                f'org={target_org_id}: {e}')
            return False

    # ---------- 审计留痕 ----------

    def _audit(self, party_id: int, user_id: int, doc_context) -> None:
        """放行解析行为留痕（§6-3）。

        表缺失 / 写入失败**不阻断**（门禁已过、放行不因审计失败而回退），仅告警。
        覆写本方法可注入测试收集器。
        """
        try:
            self.ds.insert('audit_logs', {
                'object_type': 'party',
                'object_id': int(party_id),
                'action': 'intra_trade_resolve',
                'status': 'success',
            })
        except Exception as e:
            logger.warning(f'[intra_trade] 审计留痕失败 party={party_id}: {e}')