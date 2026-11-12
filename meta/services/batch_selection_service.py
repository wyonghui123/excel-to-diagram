# -*- coding: utf-8 -*-
"""批次选择服务 —— 单一 select_batches：默认可用性谓词 + 逐层策略 + 审计留痕（P5）。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §12.6
      docs/specs/p5-routing-branch-parallel-batch-selection/spec.md §5.3

口径:
  · 策略顺序 item → item_group → org；同层 priority 升序，首条命中即停。
  · 默认谓词先于策略过滤：可用 + 未关闭；allow_blocked 放开冻结/检验中，关闭永远排除。
  · 无策略 / 全部策略 0 条 ⇒ NoBatchMatchError，不静默取第一条。
  · 已落库规则解析失败 ⇒ InvalidSelectionRuleError（立即抛错，不跳下一条）。
  · qty / uom 只透传审计，不参与筛选。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from meta.services.audit_service import AuditService
from meta.services.batch_selection_policy_service import (
    BatchSelectionPolicyError,
    BatchSelectionPolicyService,
)

logger = logging.getLogger(__name__)

POLICY_TABLE = 'batch_selection_policies'
BATCH_TABLE = 'batches'

SCOPE_ORDER = ('item', 'item_group', 'org')

PREDICATE_DEFAULT = "quality_status = 'unrestricted' AND status != 'closed'"
PREDICATE_ALLOW_BLOCKED = "status != 'closed'"


class InvalidSelectionRuleError(Exception):
    """已落库策略的规则解析 / 白名单错误。"""

    def __init__(self, message: str, policy_code: str = ''):
        super().__init__(message)
        self.policy_code = policy_code


class NoBatchMatchError(Exception):
    """无策略或全部策略均无匹配批次。"""

    def __init__(self, message: str,
                 attempted_policy_codes: Optional[List[str]] = None,
                 reason: str = 'no_match'):
        super().__init__(message)
        self.attempted_policy_codes = list(attempted_policy_codes or [])
        self.reason = reason


@dataclass
class BatchSelectionResult:
    batch_ids: List[Any] = field(default_factory=list)
    policy_id: Any = None
    rule_hash: str = ''
    evaluated_policies: List[str] = field(default_factory=list)
    default_predicate: str = PREDICATE_DEFAULT
    allow_blocked: bool = False


class BatchSelectionService:
    """按显式策略挑选批次。"""

    def __init__(self, data_source, audit_service=None):
        self.ds = data_source
        self.audit = audit_service if audit_service is not None \
            else AuditService(data_source)
        self.policy_service = BatchSelectionPolicyService(data_source)

    def select_batches(self, item_id: Any, org_id: Any,
                       qty: Any = None, uom: Any = None,
                       context: Optional[Dict[str, Any]] = None,
                       tenant_id: Any = 0,
                       audit_service=None) -> BatchSelectionResult:
        audit = audit_service if audit_service is not None else self.audit
        item_code, item_group_code, org_code = self._resolve_scopes(item_id, org_id)
        scopes = self._scope_pairs(item_code, item_group_code, org_code)

        attempted: List[str] = []
        last_policy: Optional[Dict[str, Any]] = None
        for scope_type, scope_ref in scopes:
            for policy in self._load_policies(scope_type, scope_ref):
                code = policy.get('code') or ''
                attempted.append(code)
                last_policy = policy
                batch_ids, rule = self._apply_policy(policy, item_id, org_id)
                if not batch_ids:
                    continue
                result = BatchSelectionResult(
                    batch_ids=batch_ids,
                    policy_id=policy.get('id'),
                    rule_hash=self.policy_service.rule_hash(rule),
                    evaluated_policies=list(attempted),
                    default_predicate=PREDICATE_ALLOW_BLOCKED
                    if rule['allow_blocked'] else PREDICATE_DEFAULT,
                    allow_blocked=bool(rule['allow_blocked']),
                )
                self._audit_select(audit, policy, item_code, org_code, qty, uom,
                                   batch_ids, attempted, context, 'success', '',
                                   rule)
                return result

        reason = 'no_policy' if not attempted else 'no_match'
        message = (
            '未找到生效的批次选择策略。' if reason == 'no_policy'
            else '所有生效策略均未匹配到可用批次。')
        self._audit_failure(audit, last_policy, item_code, org_code, qty, uom,
                            attempted, context, reason)
        raise NoBatchMatchError(message, attempted_policy_codes=attempted,
                                reason=reason)

    # ------------------------------------------------------------------
    # 策略执行
    # ------------------------------------------------------------------
    def _apply_policy(self, policy: Dict[str, Any], item_id: Any,
                      org_id: Any) -> Tuple[List[Any], Dict[str, Any]]:
        code = policy.get('code') or ''
        try:
            rule = self.policy_service.validate_rule_json(policy.get('rule_json'))
        except BatchSelectionPolicyError as error:
            raise InvalidSelectionRuleError(
                f'策略 {code} 的规则无效：{error}', policy_code=code)

        clauses = ['item_id = ?', 'org_id = ?']
        params: List[Any] = [item_id, org_id]
        if rule['allow_blocked']:
            clauses.append(PREDICATE_ALLOW_BLOCKED)
        else:
            clauses.append('quality_status = ?')
            params.append('unrestricted')
            clauses.append('status != ?')
            params.append('closed')
        for item in rule['filters']:
            clause = self._filter_clause(item, params)
            if clause:
                clauses.append(clause)
        where = ' AND '.join(clauses)

        sql = f'SELECT id FROM {BATCH_TABLE} WHERE {where}'
        order = self._order_clause(rule['sort'])
        if order:
            sql += f' ORDER BY {order}'
        sql += ' LIMIT ?'
        params.append(rule['limit'])
        rows = self.ds.query(sql, params) or []
        return [row.get('id') for row in rows], rule

    @staticmethod
    def _filter_clause(item: Dict[str, Any], params: List[Any]) -> Optional[str]:
        column = item['field']
        op = item['op']
        if op == 'is_null':
            return f'{column} IS NULL'
        if op == 'is_not_null':
            return f'{column} IS NOT NULL'
        value = item.get('value')
        if op == 'eq':
            params.append(value)
            return f'{column} = ?'
        if op == 'ne':
            params.append(value)
            return f'{column} != ?'
        if op == 'gt':
            params.append(value)
            return f'{column} > ?'
        if op == 'gte':
            params.append(value)
            return f'{column} >= ?'
        if op == 'lt':
            params.append(value)
            return f'{column} < ?'
        if op == 'lte':
            params.append(value)
            return f'{column} <= ?'
        if op == 'in':
            params.extend(list(value))
            return f'{column} IN ({", ".join("?" * len(value))})'
        if op == 'between':
            params.extend([value[0], value[1]])
            return f'{column} BETWEEN ? AND ?'
        return None

    @staticmethod
    def _order_clause(sort: List[Dict[str, Any]]) -> str:
        parts = []
        for item in sort:
            column = item['field']
            direction = 'DESC' if item.get('dir') == 'desc' else 'ASC'
            parts.append(f'({column} IS NULL) ASC')
            parts.append(f'{column} {direction}')
        parts.append('id ASC')
        return ', '.join(parts)

    # ------------------------------------------------------------------
    # 范围解析与策略读取
    # ------------------------------------------------------------------
    def _resolve_scopes(self, item_id: Any,
                        org_id: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        item_code = None
        item_group_code = None
        item_group_id = None
        item = self._row('SELECT code, item_group_id FROM items WHERE id = ?',
                         [item_id])
        if item:
            item_code = item.get('code')
            item_group_id = item.get('item_group_id')
        if item_group_id is not None:
            group = self._row('SELECT code FROM item_groups WHERE id = ?',
                              [item_group_id])
            if group:
                item_group_code = group.get('code')
        org = self._row('SELECT code FROM orgs WHERE id = ?', [org_id])
        org_code = org.get('code') if org else None
        return item_code, item_group_code, org_code

    @staticmethod
    def _scope_pairs(item_code: Optional[str], item_group_code: Optional[str],
                     org_code: Optional[str]) -> List[Tuple[str, str]]:
        pairs = []
        if item_code:
            pairs.append(('item', item_code))
        if item_group_code:
            pairs.append(('item_group', item_group_code))
        if org_code:
            pairs.append(('org', org_code))
        return pairs

    def _load_policies(self, scope_type: str,
                       scope_ref: str) -> List[Dict[str, Any]]:
        return self.ds.query(
            f"SELECT * FROM {POLICY_TABLE} WHERE status = 'active' "
            'AND scope_type = ? AND scope_ref = ? ORDER BY priority, id',
            [scope_type, scope_ref]) or []

    def _row(self, sql: str, params: List[Any]) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(sql, params) or []
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------
    def _audit_select(self, audit, policy: Dict[str, Any], item_code: Any,
                      org_code: Any, qty: Any, uom: Any, batch_ids: List[Any],
                      attempted: List[str], context: Optional[Dict[str, Any]],
                      outcome: str, reason: str,
                      rule: Optional[Dict[str, Any]] = None) -> None:
        if rule is None:
            rule = self.policy_service.validate_rule_json(
                policy.get('rule_json'))
        extra = {
            'item_code': item_code,
            'org_code': org_code,
            'qty': qty,
            'uom': uom,
            'batch_ids': list(batch_ids),
            'policy_code': policy.get('code'),
            'priority': policy.get('priority'),
            'rule_hash': self.policy_service.rule_hash(rule),
            'default_predicate': PREDICATE_ALLOW_BLOCKED
            if rule['allow_blocked'] else PREDICATE_DEFAULT,
            'allow_blocked': bool(rule['allow_blocked']),
            'attempted_policy_codes': list(attempted),
            'context': context,
        }
        if outcome != 'success':
            extra['reason'] = reason
        self._write_audit(audit, policy.get('id'), extra, outcome)

    def _audit_failure(self, audit, last_policy: Optional[Dict[str, Any]],
                       item_code: Any, org_code: Any, qty: Any, uom: Any,
                       attempted: List[str], context: Optional[Dict[str, Any]],
                       reason: str) -> None:
        extra = {
            'item_code': item_code,
            'org_code': org_code,
            'qty': qty,
            'uom': uom,
            'batch_ids': [],
            'policy_code': (last_policy or {}).get('code'),
            'attempted_policy_codes': list(attempted),
            'context': context,
            'reason': reason,
        }
        self._write_audit(audit, (last_policy or {}).get('id'), extra, 'failed')

    def _write_audit(self, audit, policy_id: Any, extra: Dict[str, Any],
                     outcome: str) -> None:
        if audit is None:
            return
        try:
            audit.log(
                object_type='batch_selection_policy',
                object_id=policy_id,
                action='select',
                extra_data=extra,
                outcome=outcome,
            )
        except Exception as exc:  # 审计失败不阻断选择
            logger.warning(f'[batch_selection] 审计写入失败: {exc}')

