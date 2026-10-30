# -*- coding: utf-8 -*-
"""变式物料化服务（manual 链路）

依据: docs/superpowers/specs/2026-10-30-variant-item-materialization-spec.md
  - D2 前置校验：任一不满足抛 MaterializeError(code)，不静默
  - D3 幂等键 (model_item_id, config_hash)：命中已有变式物料即复用
  - D4 编码 {model_code}-{seq:04d}：超 40 字符不截断，抛 ITEM_CODE_TOO_LONG
  - D5 新物料继承 + 强制字段（structure_role='none' / status='draft' 等）
  - D6 单事务：INSERT items → UPDATE configurations.variant_item_id → commit
  - D7 不复制 BOM、不复制价格；D10 不新增迁移

一句话：把「已求解 / 已冻结的配置实例」固化为 draft 物料，并回写
`configurations.variant_item_id`。物化成功 ≠ 可下单，新物料必须走签发。
"""

import logging
from typing import Any, Dict, Optional

from meta.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_CONFIG_TABLE = 'configurations'
_VALUE_TABLE = 'configuration_values'
_ITEM_TABLE = 'items'

_ITEM_OBJECT = 'item'
_CONFIG_OBJECT = 'configuration'

_CODE_MAX_LENGTH = 40
_NAME_MAX_LENGTH = 60
_SUMMARY_LIMIT = 3

_SOLVED_STATUS = frozenset({'solved', 'frozen'})
_TRADABLE_STATUS = frozenset({'active', 'frozen'})
_MATERIALIZE_POLICIES = frozenset({'manual', 'auto'})


class MaterializeError(Exception):
    """物化被拒绝或失败。`code` 为对外错误码（spec §2 D2 / D4）。"""

    def __init__(self, message: str, code: str, configuration_id: Any = None):
        super().__init__(message)
        self.code = code
        self.configuration_id = configuration_id


class VariantItemMaterializeService:
    """配置实例 → 变式物料（draft）。注入方式同 ConfigurationMatchService。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    def materialize(self, configuration_id: Any) -> Dict[str, Any]:
        """把配置实例固化为 draft 物料，返回 {item_id, item_code, created}。"""
        configuration = self._fetch_configuration(configuration_id)
        if not configuration:
            raise MaterializeError(
                f'配置实例不存在: {configuration_id}',
                'CONFIG_NOT_FOUND', configuration_id)

        status = str(configuration.get('status') or '')
        if status not in _SOLVED_STATUS:
            raise MaterializeError(
                f'实例状态 {status} 不允许物化，只有 solved / frozen 可物化',
                'CONFIG_NOT_SOLVED', configuration_id)

        config_hash = str(configuration.get('config_hash') or '').strip()
        if not config_hash:
            raise MaterializeError(
                '配置实例缺少 config_hash，无法物化',
                'CONFIG_HASH_MISSING', configuration_id)

        model = self._fetch_item(configuration.get('model_item_id'))
        if not model:
            raise MaterializeError(
                f'模型物料不存在: {configuration.get("model_item_id")}',
                'MODEL_NOT_FOUND', configuration_id)

        model_status = str(model.get('status') or '')
        if model_status not in _TRADABLE_STATUS:
            raise MaterializeError(
                f'模型物料状态 {model_status} 不可交易，只有 active / frozen 可物化',
                'MODEL_NOT_TRADABLE', configuration_id)

        policy = str(model.get('config_materialize_policy') or 'off')
        if policy not in _MATERIALIZE_POLICIES:
            raise MaterializeError(
                f'模型物料 config_materialize_policy={policy}，不允许物化',
                'MATERIALIZE_DISABLED', configuration_id)

        existing = self._find_variant_item(
            configuration.get('model_item_id'), config_hash)
        if existing:
            self._link_variant(configuration, existing['id'])
            return {'item_id': existing['id'],
                    'item_code': existing.get('code'),
                    'created': False}

        return self._create_variant(configuration, model)

    # ------------------------------------------------------------------
    # 新建
    # ------------------------------------------------------------------
    def _create_variant(self, configuration: Dict[str, Any],
                        model: Dict[str, Any]) -> Dict[str, Any]:
        configuration_id = configuration.get('id')
        model_item_id = configuration.get('model_item_id')
        model_code = str(model.get('code') or '')

        sequence = self._next_sequence(model_item_id)
        self._check_code_length(model_code, sequence, configuration_id)

        row = self._build_item_row(configuration, model)

        for attempt in range(2):
            code = self._build_code(model_code, sequence)
            row['code'] = code
            try:
                with self.ds.transaction():
                    item_id = self.ds.insert(_ITEM_TABLE, row)
                    self.ds.update(_CONFIG_TABLE, configuration_id,
                                   {'variant_item_id': item_id})
                    self._audit_create_item(item_id, code)
                    self._audit_link(configuration_id, item_id,
                                     configuration.get('variant_item_id'))
                return {'item_id': item_id, 'item_code': code, 'created': True}
            except Exception as exc:
                if not _is_unique_conflict(exc):
                    raise
                if attempt == 1:
                    raise MaterializeError(
                        f'物料编码冲突，重试后仍失败: {code}',
                        'CODE_CONFLICT', configuration_id)
                # 重算序号：并发下 count 可能未变，至少跳过刚冲突的序号
                retry = self._next_sequence(model_item_id)
                sequence = retry if retry != sequence else sequence + 1

        raise MaterializeError(
            f'物料编码冲突，重试后仍失败: {model_code}',
            'CODE_CONFLICT', configuration_id)

    def _build_item_row(self, configuration: Dict[str, Any],
                        model: Dict[str, Any]) -> Dict[str, Any]:
        """D5：继承模型字段 + 强制字段（防递归物化 / 不参与匹配 / draft）。"""
        return {
            'code': '',
            'name': self._build_name(configuration, model),
            'structure_role': 'none',
            'item_type': model.get('item_type'),
            'item_group_id': model.get('item_group_id'),
            'base_uom': model.get('base_uom'),
            'sales_uom': model.get('sales_uom'),
            'tax_classification_id': model.get('tax_classification_id'),
            'config_match_policy': 'no',
            'config_materialize_policy': 'off',
            'status': 'draft',
        }

    def _build_name(self, configuration: Dict[str, Any],
                    model: Dict[str, Any]) -> str:
        model_name = str(model.get('name') or '')
        summary = self._variant_summary(configuration.get('id'))
        name = f'{model_name} / {summary}' if summary else model_name
        return name[:_NAME_MAX_LENGTH]

    def _variant_summary(self, configuration_id: Any) -> str:
        """前 3 条配置值（按字段名排序）的显示值拼接。"""
        rows = self.ds.query(
            f"SELECT attribute_code, value_text, value_number, value_boolean"
            f" FROM {_VALUE_TABLE}"
            " WHERE configuration_id = ?"
            f" ORDER BY attribute_code, seq LIMIT {_SUMMARY_LIMIT}",
            [configuration_id])
        parts = [text for text in (_display_value(row) for row in rows) if text]
        return ', '.join(parts)

    # ------------------------------------------------------------------
    # auto 入口（Phase 2）
    # ------------------------------------------------------------------
    def materialize_on_solve(self, configuration_id: Any) -> Optional[Dict[str, Any]]:
        """求解后自动物化入口。

        仅当模型 `config_materialize_policy='auto'` 时物化；其余策略静默跳过。
        失败只记 warning，**绝不抛出** —— 物化是主数据副作用，不能拖垮配置求解。
        产物仍是 `draft`，须签发才可被单据引用（D8 不变量不变）。
        """
        try:
            configuration = self._fetch_configuration(configuration_id)
            if not configuration:
                return None
            model = self._fetch_item(configuration.get('model_item_id')) or {}
            policy = str(model.get('config_materialize_policy') or 'off')
            if policy != 'auto':
                return None
            return self.materialize(configuration_id)
        except MaterializeError as exc:
            logger.warning(
                '[variant-materialize-auto] 配置 %s 自动物化被拒: %s (%s)',
                configuration_id, exc, exc.code)
            return None
        except Exception:  # noqa: BLE001 - 主数据副作用失败不阻断求解
            logger.exception(
                '[variant-materialize-auto] 配置 %s 自动物化异常', configuration_id)
            return None

    # ------------------------------------------------------------------
    # 复用
    # ------------------------------------------------------------------
    def _link_variant(self, configuration: Dict[str, Any], item_id: Any) -> None:
        configuration_id = configuration.get('id')
        if configuration.get('variant_item_id') == item_id:
            return
        with self.ds.transaction():
            self.ds.update(_CONFIG_TABLE, configuration_id,
                           {'variant_item_id': item_id})
            self._audit_link(configuration_id, item_id,
                             configuration.get('variant_item_id'))

    def _find_variant_item(self, model_item_id: Any,
                           config_hash: str) -> Dict[str, Any]:
        """D3：任一 configuration 的 variant_item_id 指向的物料即映射真源。"""
        rows = self.ds.query(
            f"SELECT i.id AS id, i.code AS code FROM {_CONFIG_TABLE} c"
            f" JOIN {_ITEM_TABLE} i ON i.id = c.variant_item_id"
            " WHERE c.model_item_id = ? AND c.config_hash = ?"
            "   AND c.variant_item_id IS NOT NULL"
            " ORDER BY c.id LIMIT 1",
            [model_item_id, config_hash])
        return rows[0] if rows else {}

    # ------------------------------------------------------------------
    # 序号与编码（D4）
    # ------------------------------------------------------------------
    def _next_sequence(self, model_item_id: Any) -> int:
        rows = self.ds.query(
            f"SELECT COUNT(*) AS n FROM {_CONFIG_TABLE}"
            " WHERE model_item_id = ? AND variant_item_id IS NOT NULL",
            [model_item_id])
        return int(rows[0]['n'] if rows else 0) + 1

    def _build_code(self, model_code: str, sequence: int) -> str:
        return f'{model_code}-{int(sequence):04d}'

    def _check_code_length(self, model_code: str, sequence: int,
                           configuration_id: Any) -> None:
        code = self._build_code(model_code, sequence)
        if len(code) > _CODE_MAX_LENGTH:
            raise MaterializeError(
                f'物料编码 {code} 超过 {_CODE_MAX_LENGTH} 字符，请缩短模型编码',
                'ITEM_CODE_TOO_LONG', configuration_id)

    # ------------------------------------------------------------------
    # 审计（D6：items 新增 1 条 + configuration 更新 1 条）
    # ------------------------------------------------------------------
    def _audit_create_item(self, item_id: Any, item_code: str) -> None:
        AuditService(self.ds).log(
            _ITEM_OBJECT, item_id, 'CREATE',
            field_name='code', new_value=item_code)

    def _audit_link(self, configuration_id: Any, item_id: Any,
                    old_value: Any) -> None:
        AuditService(self.ds).log(
            _CONFIG_OBJECT, configuration_id, 'UPDATE',
            field_name='variant_item_id', old_value=old_value,
            new_value=item_id)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def _fetch_configuration(self, configuration_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            f"SELECT * FROM {_CONFIG_TABLE} WHERE id = ?", [configuration_id])
        return rows[0] if rows else {}

    def _fetch_item(self, item_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            f"SELECT * FROM {_ITEM_TABLE} WHERE id = ?", [item_id])
        return rows[0] if rows else {}


def _display_value(row: Dict[str, Any]) -> str:
    """configuration_value 的显示值：text → number → boolean。"""
    for key in ('value_text', 'value_number', 'value_boolean'):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ''


def _is_unique_conflict(exc: Exception) -> bool:
    """唯一约束冲突（SQLite: 'UNIQUE constraint failed: items.code'）。"""
    message = str(exc).lower()
    return 'unique' in message or 'duplicate' in message
