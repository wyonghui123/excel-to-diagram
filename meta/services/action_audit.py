# -*- coding: utf-8 -*-
"""[E3 2026-11-11] BO Action 写审计

职责：
- `write_action_audit(entry)`：把 `BoActionRegistry.call()` 的治理结果落 `audit_logs`，
  复用 `AuditService.log`（审计字段/脱敏/派生逻辑不做第二套）。
- `resolve_action_data_source()`：审计/组织校验共用的数据源解析出口
  （请求已绑定应用库则跟随；否则平台库）。
- 去重键 `(trace_id, action_id)`：同一次调用重试/双写只落一行。
- **审计失败不得阻断业务**：任何异常只告警，返回 False。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def resolve_action_data_source() -> Optional[Any]:
    """解析业务数据源（不依赖 Flask 请求上下文）。"""
    try:
        from meta.core.datasource import get_platform_data_source, resolve_data_source
        return resolve_data_source(get_platform_data_source())
    except Exception as exc:  # noqa: BLE001 - 解析失败交由调用方决定是否跳过
        logger.warning('[ActionAudit] 数据源解析失败：%s', exc)
        return None


def _already_audited(data_source: Any, trace_id: str, action_id: str) -> bool:
    """按 (trace_id, action_id) 去重；查询异常视为未审计（不阻断业务）。"""
    try:
        row = data_source.execute(
            'SELECT 1 FROM audit_logs WHERE trace_id = ? AND action = ? LIMIT 1',
            [trace_id, action_id],
        ).fetchone()
        return bool(row)
    except Exception as exc:  # noqa: BLE001 - 表缺失/连接异常均降级为继续写
        logger.debug('[ActionAudit] 去重查询失败，按未审计处理：%s', exc)
        return False


def write_action_audit(entry: Dict[str, Any]) -> bool:
    """写入一条 action 治理审计；返回是否真正落库。"""
    action_id = entry.get('action_id')
    trace_id = entry.get('trace_id')
    business_ds = entry.get('data_source')
    if not business_ds:
        business_ds = resolve_action_data_source()
    if not action_id or not trace_id or business_ds is None:
        logger.warning(
            '[ActionAudit] 审计要素缺失，跳过：action=%s trace_id=%s ds=%s',
            action_id, trace_id, business_ds is not None,
        )
        return False

    try:
        from meta.core.datasource import resolve_audit_data_source
        from meta.services.audit_service import AuditService

        audit_ds = resolve_audit_data_source(business_ds)
        if _already_audited(audit_ds, trace_id, action_id):
            return False

        status = entry.get('status') or 'ok'
        object_id = entry.get('object_id')
        if object_id in (None, ''):
            object_id = 0  # audit_logs.object_id NOT NULL

        return AuditService(audit_ds).log(
            object_type=entry.get('object_type') or '_unknown',
            object_id=object_id,
            action=action_id,
            user_id=entry.get('user_id'),
            user_name=entry.get('user_name'),
            ip_address=entry.get('ip_address'),
            trace_id=trace_id,
            outcome='success' if status == 'ok' else 'failure',
            status=status,
            extra_data={
                'params_hash': entry.get('params_hash'),
                'governance': entry.get('governance'),
                'governance_status': status,
            },
        )
    except Exception as exc:  # noqa: BLE001 - 审计失败不得阻断业务
        logger.warning('[ActionAudit] 审计写入失败（不阻断业务）action=%s: %s', action_id, exc)
        return False