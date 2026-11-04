# -*- coding: utf-8 -*-
"""批次选择策略服务 —— rule_json v1 白名单、范围存在性与优先级唯一（P5）。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md
      §12.5（字段级）/ §12.6（DSL 与算法）
      docs/specs/p5-routing-branch-parallel-batch-selection/spec.md §5.2

口径:
  · `rule_json` 只允许 batches 物理列；EAV 特性字段一律拒绝（usage_class 红线）。
  · `scope_ref` 存业务编码，保存时校验目标表存在。
  · 同 (scope_type, scope_ref) 下 active 策略的 priority 唯一。
  · 解析 / 白名单错误在保存时立即抛错，不做静默降级。
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

POLICY_TABLE = 'batch_selection_policies'
ATTRIBUTE_DEFINITION_TABLE = 'attribute_definitions'

RULE_VERSION = 1
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
TOP_KEYS = {'version', 'filters', 'sort', 'limit', 'allow_blocked'}

SCOPE_TABLES = {
    'item': 'items',
    'item_group': 'item_groups',
    'org': 'orgs',
}
SCOPES = tuple(SCOPE_TABLES.keys())
STATUS_ACTIVE = 'active'
STATUS_INACTIVE = 'inactive'
STATUSES = (STATUS_ACTIVE, STATUS_INACTIVE)

#: 批次物理列白名单 → 值类型（date 含 datetime 文本）
FIELD_KINDS = {
    'batch_no': 'text',
    'status': 'text',
    'quality_status': 'text',
    'qty': 'numeric',
    'produced_at': 'date',
    'expiry_date': 'date',
    'potency_pct': 'numeric',
    'grade_code': 'text',
    'source': 'text',
    'parent_batch_id': 'integer',
    'created_at': 'date',
}

OPS = ('eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'between',
       'is_null', 'is_not_null')
ORDER_OPS = ('gt', 'gte', 'lt', 'lte', 'between')
FILTER_KEYS = {'field', 'op', 'value'}
SORT_KEYS = {'field', 'dir'}

RULE_TEMPLATES = {
    'FEFO': {
        'version': RULE_VERSION,
        'sort': [{'field': 'expiry_date', 'dir': 'asc'}],
        'limit': DEFAULT_LIMIT,
    },
    'FIFO': {
        'version': RULE_VERSION,
        'sort': [{'field': 'created_at', 'dir': 'asc'}],
        'limit': DEFAULT_LIMIT,
    },
    'GRADE_FIRST': {
        'version': RULE_VERSION,
        'sort': [{'field': 'grade_code', 'dir': 'desc'},
                 {'field': 'expiry_date', 'dir': 'asc'}],
        'limit': DEFAULT_LIMIT,
    },
}


class BatchSelectionPolicyError(Exception):
    """批次选择策略校验错误（拦截器转为 ValidationFailedError）。"""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class BatchSelectionPolicyService:
    """策略保存校验 + rule_json 规范化。"""

    def __init__(self, data_source):
        self.ds = data_source

    def validate_policy(self, payload: Dict[str, Any],
                        existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验策略创建 / 更新，返回规范化合并值。"""
        patch = dict(payload or {})
        old = dict(existing or {})
        merged = dict(old)
        merged.update(patch)

        for field, label, max_length in (
                ('code', '策略编码', 40),
                ('name', '策略名称', 128),
                ('scope_ref', '范围编码', 60)):
            value = merged.get(field)
            if value is None or str(value).strip() == '':
                raise BatchSelectionPolicyError(
                    f'{label}不能为空。', field_name=field,
                    rule='BATCH_SELECTION_FIELD_REQUIRED')
            if len(str(value).strip()) > max_length:
                raise BatchSelectionPolicyError(
                    f'{label}不能超过 {max_length} 个字符。', field_name=field,
                    rule='BATCH_SELECTION_FIELD_TOO_LONG')
        merged['code'] = str(merged['code']).strip()
        merged['name'] = str(merged['name']).strip()
        merged['scope_ref'] = str(merged['scope_ref']).strip()

        scope_type = str(merged.get('scope_type') or '').strip().lower()
        if scope_type not in SCOPE_TABLES:
            raise BatchSelectionPolicyError(
                '范围类型必须为物料 / 物料分类 / 组织。', field_name='scope_type',
                rule='BATCH_SELECTION_SCOPE_INVALID')
        merged['scope_type'] = scope_type
        if not self._scope_exists(scope_type, merged['scope_ref']):
            raise BatchSelectionPolicyError(
                f'范围编码 {merged["scope_ref"]} 在 {SCOPE_TABLES[scope_type]} 中不存在。',
                field_name='scope_ref', rule='BATCH_SELECTION_SCOPE_NOT_FOUND')

        status = str(merged.get('status') or STATUS_ACTIVE).strip().lower()
        if status not in STATUSES:
            raise BatchSelectionPolicyError(
                '策略状态必须为启用 / 停用。', field_name='status',
                rule='BATCH_SELECTION_STATUS_INVALID')
        merged['status'] = status

        priority = merged.get('priority')
        if priority is None or priority == '':
            priority = 1
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 0
        if priority < 1:
            raise BatchSelectionPolicyError(
                '优先级必须 ≥ 1。', field_name='priority',
                rule='BATCH_SELECTION_PRIORITY_INVALID')
        merged['priority'] = priority

        rule = self.validate_rule_json(merged.get('rule_json'))
        merged['rule_json'] = self._canonical(rule)

        if status == STATUS_ACTIVE:
            self._check_priority_unique(merged, old.get('id'))

        return merged

    def validate_rule_json(self, raw: Any) -> Dict[str, Any]:
        """解析并校验 rule_json v1，返回规范化字典。"""
        if isinstance(raw, dict):
            data = raw
        elif raw is None or str(raw).strip() == '':
            raise BatchSelectionPolicyError(
                '选择规则不能为空。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_REQUIRED')
        else:
            try:
                data = json.loads(str(raw))
            except (TypeError, ValueError):
                raise BatchSelectionPolicyError(
                    '选择规则不是合法 JSON。', field_name='rule_json',
                    rule='BATCH_SELECTION_RULE_INVALID_JSON')
        if not isinstance(data, dict):
            raise BatchSelectionPolicyError(
                '选择规则必须是 JSON 对象。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_INVALID_JSON')

        unknown = set(data.keys()) - TOP_KEYS
        if unknown:
            raise BatchSelectionPolicyError(
                f'选择规则含未知键：{", ".join(sorted(unknown))}。',
                field_name='rule_json', rule='BATCH_SELECTION_RULE_UNKNOWN_KEY')

        version = data.get('version')
        if isinstance(version, bool) or not isinstance(version, int) \
                or version != RULE_VERSION:
            raise BatchSelectionPolicyError(
                f'选择规则版本必须为 {RULE_VERSION}。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VERSION')

        filters = data.get('filters', [])
        if not isinstance(filters, list):
            raise BatchSelectionPolicyError(
                'filters 必须是数组。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')
        normalized_filters = [self._validate_filter(item) for item in filters]

        sort = data.get('sort', [])
        if not isinstance(sort, list):
            raise BatchSelectionPolicyError(
                'sort 必须是数组。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')
        normalized_sort = [self._validate_sort(item) for item in sort]

        limit = data.get('limit', DEFAULT_LIMIT)
        if isinstance(limit, bool) or not isinstance(limit, int) \
                or limit < 1 or limit > MAX_LIMIT:
            raise BatchSelectionPolicyError(
                f'limit 必须是 1..{MAX_LIMIT} 的整数。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')

        allow_blocked = data.get('allow_blocked', False)
        if not isinstance(allow_blocked, bool):
            raise BatchSelectionPolicyError(
                'allow_blocked 必须是布尔值。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')

        return {
            'version': RULE_VERSION,
            'filters': normalized_filters,
            'sort': normalized_sort,
            'limit': limit,
            'allow_blocked': allow_blocked,
        }

    @staticmethod
    def rule_hash(rule_json: Any) -> str:
        """稳定规则摘要：sha256(canonical json)[:16]。"""
        data = rule_json
        if not isinstance(data, dict):
            data = json.loads(str(rule_json))
        canonical = json.dumps(
            data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _validate_filter(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            raise BatchSelectionPolicyError(
                'filters 元素必须是对象。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')
        unknown = set(item.keys()) - FILTER_KEYS
        if unknown:
            raise BatchSelectionPolicyError(
                f'过滤器含未知键：{", ".join(sorted(unknown))}。',
                field_name='rule_json', rule='BATCH_SELECTION_RULE_UNKNOWN_KEY')

        field = str(item.get('field') or '').strip()
        if field not in FIELD_KINDS:
            rule = ('BATCH_SELECTION_EAV_FIELD_NOT_ALLOWED'
                    if self._attribute_code_exists(field)
                    else 'BATCH_SELECTION_RULE_UNKNOWN_FIELD')
            raise BatchSelectionPolicyError(
                f'批次选择不允许字段 {field}；只允许批次物理列。',
                field_name='rule_json', rule=rule)
        kind = FIELD_KINDS[field]

        op = str(item.get('op') or '').strip()
        if op not in OPS:
            raise BatchSelectionPolicyError(
                f'未知过滤算子：{op}。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_UNKNOWN_OP')

        normalized = {'field': field, 'op': op}
        if op in ('is_null', 'is_not_null'):
            return normalized
        if 'value' not in item:
            raise BatchSelectionPolicyError(
                f'过滤器 {field}.{op} 缺少 value。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')
        value = item['value']

        if op == 'in':
            if not isinstance(value, list) or not value:
                raise BatchSelectionPolicyError(
                    'in 的 value 必须是非空数组。', field_name='rule_json',
                    rule='BATCH_SELECTION_RULE_VALUE_INVALID')
            for one in value:
                self._check_value(kind, one)
            normalized['value'] = list(value)
        elif op == 'between':
            if (not isinstance(value, list) or len(value) != 2):
                raise BatchSelectionPolicyError(
                    'between 的 value 必须是两个元素。', field_name='rule_json',
                    rule='BATCH_SELECTION_RULE_VALUE_INVALID')
            for one in value:
                self._check_value(kind, one)
            normalized['value'] = list(value)
        else:
            if op in ORDER_OPS and kind not in ('numeric', 'date'):
                raise BatchSelectionPolicyError(
                    f'字段 {field} 不支持 {op} 比较。', field_name='rule_json',
                    rule='BATCH_SELECTION_RULE_VALUE_INVALID')
            self._check_value(kind, value)
            normalized['value'] = value
        return normalized

    def _validate_sort(self, item: Any) -> Dict[str, str]:
        if not isinstance(item, dict):
            raise BatchSelectionPolicyError(
                'sort 元素必须是对象。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')
        unknown = set(item.keys()) - SORT_KEYS
        if unknown:
            raise BatchSelectionPolicyError(
                f'排序含未知键：{", ".join(sorted(unknown))}。',
                field_name='rule_json', rule='BATCH_SELECTION_RULE_UNKNOWN_KEY')
        field = str(item.get('field') or '').strip()
        if field not in FIELD_KINDS:
            rule = ('BATCH_SELECTION_EAV_FIELD_NOT_ALLOWED'
                    if self._attribute_code_exists(field)
                    else 'BATCH_SELECTION_RULE_UNKNOWN_FIELD')
            raise BatchSelectionPolicyError(
                f'批次选择不允许排序字段 {field}；只允许批次物理列。',
                field_name='rule_json', rule=rule)
        direction = str(item.get('dir') or 'asc').strip().lower()
        if direction not in ('asc', 'desc'):
            raise BatchSelectionPolicyError(
                '排序方向必须为 asc / desc。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')
        return {'field': field, 'dir': direction}

    @staticmethod
    def _check_value(kind: str, value: Any) -> None:
        valid = True
        if kind == 'numeric':
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif kind == 'integer':
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif kind == 'text':
            valid = isinstance(value, str)
        elif kind == 'date':
            if isinstance(value, str):
                try:
                    datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    valid = False
            else:
                valid = False
        if not valid:
            raise BatchSelectionPolicyError(
                '过滤值类型与字段不匹配。', field_name='rule_json',
                rule='BATCH_SELECTION_RULE_VALUE_INVALID')

    @staticmethod
    def _canonical(rule: Dict[str, Any]) -> str:
        return json.dumps(
            rule, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

    def _scope_exists(self, scope_type: str, code: str) -> bool:
        table = SCOPE_TABLES[scope_type]
        try:
            rows = self.ds.query(
                f'SELECT 1 AS ok FROM {table} WHERE code = ? LIMIT 1', [code]) or []
        except Exception as exc:  # 表缺失 / 查询失败 → 视为不存在
            logger.warning(f'[batch_selection_policy] 范围查询失败: {exc}')
            return False
        return bool(rows)

    def _attribute_code_exists(self, code: str) -> bool:
        if not code:
            return False
        try:
            rows = self.ds.query(
                f'SELECT 1 AS ok FROM {ATTRIBUTE_DEFINITION_TABLE} '
                'WHERE code = ? LIMIT 1', [code]) or []
        except Exception:
            return False
        return bool(rows)

    def _check_priority_unique(self, policy: Dict[str, Any],
                               self_id: Any) -> None:
        rows = self.ds.query(
            f'SELECT id, code FROM {POLICY_TABLE} '
            "WHERE status = 'active' AND scope_type = ? AND scope_ref = ? "
            'AND priority = ?', [policy['scope_type'], policy['scope_ref'],
                                 policy['priority']]) or []
        self_id = int(self_id) if self_id not in (None, '') else None
        for row in rows:
            row_id = row.get('id')
            try:
                row_id = int(row_id)
            except (TypeError, ValueError):
                continue
            if self_id is None or row_id != self_id:
                raise BatchSelectionPolicyError(
                    f'范围 {policy["scope_ref"]} 下优先级 {policy["priority"]} '
                    f'已被策略 {row.get("code")} 占用。', field_name='priority',
                    rule='BATCH_SELECTION_PRIORITY_DUPLICATE')
