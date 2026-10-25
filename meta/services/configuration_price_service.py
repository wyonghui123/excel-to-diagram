# -*- coding: utf-8 -*-
"""配置定价门面（Configuration Price Service）— P4.1

把「配置实例」翻译成定价域可消费的请求，再把定价域结果包装成
Sales Order Spec §5.7 的 `PriceResult`。

[职责边界]
  本模块只做**校验、来源编排与转发**：定价算法、查表、算子、落库全部由
  `PricingService` 承担。配置域不出现第二份价格实现（Spec §8.1）。

[只读]
  `price` 只写 `calc_results` / `calc_details`；不写
  `configurations` / `configuration_values` / `configuration_components`。

[幂等]
  缓存键 = (configuration_id, config_hash, price_source, 规范化 pricing_context)，
  以确定性 `calc_result.code` 承载，命中即回读，不重复定价。
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from meta.core.calc_procedure_executor import CalculationError
from meta.core.lookup_resolver import ResolutionError
from meta.services.item_structure_config_service import (
    ItemStructureConfigError,
    ItemStructureConfigService,
)
from meta.services.pricing_service import PricingError, PricingService

logger = logging.getLogger(__name__)

CONTRACT_VERSION = '1.0'

PRICE_SOURCE_NONE = 'none'
PRICE_SOURCE_COMPONENT = 'component_price'
PRICE_SOURCE_BASE_OPTION = 'base_plus_option'
PRICE_SOURCE_MATRIX = 'attribute_matrix'
PRICE_SOURCE_CALCULATED = 'calculated'

PRICE_SOURCES = (
    PRICE_SOURCE_NONE,
    PRICE_SOURCE_COMPONENT,
    PRICE_SOURCE_BASE_OPTION,
    PRICE_SOURCE_MATRIX,
    PRICE_SOURCE_CALCULATED,
)

# 定价归属（SO Spec §3.6 轴 A）：none 不限，其余按来源唯一归属
PARENT_PRICED_SOURCES = frozenset({
    PRICE_SOURCE_BASE_OPTION, PRICE_SOURCE_MATRIX, PRICE_SOURCE_CALCULATED,
})
ROLLED_UP_SOURCES = frozenset({PRICE_SOURCE_COMPONENT})

# 本期已实现的来源；其余只留字段与错误语义（D4）
ENABLED_SOURCES = frozenset({
    PRICE_SOURCE_NONE, PRICE_SOURCE_COMPONENT, PRICE_SOURCE_BASE_OPTION,
    PRICE_SOURCE_MATRIX,
})

_PRICEABLE_STATUS = ('solved', 'frozen')
_CALC_RESULT_TABLE = 'calc_results'
_CALC_DETAIL_TABLE = 'calc_details'


class ConfigurationPriceService:
    """配置定价门面。构造注入数据源，便于测试用内存 SQLite。"""

    def __init__(self, data_source, pricing_service=None, config_service=None):
        self.ds = data_source
        self.pricing = pricing_service or PricingService(data_source)
        self.config = config_service or ItemStructureConfigService(data_source)

    # ------------------------------------------------------------------
    # 门面
    # ------------------------------------------------------------------
    def price(self, configuration_id: Any, price_source: Optional[str] = None,
              pricing_context: Optional[Dict[str, Any]] = None,
              resolved: Any = None) -> Dict[str, Any]:
        """对配置实例出价，返回 `PriceResult`。

        Args:
            configuration_id: 配置实例 ID
            price_source:     定价来源；缺省 `none`（D2：由调用方显式指定）
            pricing_context:  定价域上下文（过程 / 价目表 / 币种 / 日期 / 槽位键）
            resolved:         可选的调用方展开结果；只用于比对，不一致即拒绝

        Raises:
            ItemStructureConfigError: 对外六个错误码之一
        """
        source = str(price_source or PRICE_SOURCE_NONE).strip().lower()
        if source not in PRICE_SOURCES:
            raise ItemStructureConfigError(
                f'未知定价来源: {price_source}', code='CONFIG_INVALID_VALUE',
                rule='price_source_invalid', field_name='price_source',
                configuration_id=configuration_id)

        context = self._normalize_context(pricing_context)
        head = self.config.read(configuration_id)

        status = str(head.get('status') or '')
        if status not in _PRICEABLE_STATUS:
            raise ItemStructureConfigError(
                f'实例状态 {status} 不允许定价，只有 solved / frozen 可出价',
                code='CONFIG_VERSION_MISMATCH',
                rule='configuration_status_not_priceable', field_name='status',
                configuration_id=configuration_id)

        check = self.config.verify_hash(configuration_id)
        if not check['match']:
            raise ItemStructureConfigError(
                '实例内容与 config_hash 不一致，拒绝定价（R11）',
                code='CONFIG_INVALID_VALUE',
                rule='configuration_hash_mismatch', field_name='config_hash',
                configuration_id=configuration_id)

        self._check_pairing(source, context, configuration_id)
        self._check_resolved(head, resolved, configuration_id)

        if source not in ENABLED_SOURCES:
            raise ItemStructureConfigError(
                f'定价来源 {source} 本期未启用', code='CONFIG_PRICE_MISSING',
                rule='price_source_not_enabled', field_name='price_source',
                configuration_id=configuration_id)

        digest = self._context_digest(context, head.get('config_hash'))
        if source == PRICE_SOURCE_COMPONENT:
            return self._price_components(
                head, configuration_id, source, context, digest)
        if source == PRICE_SOURCE_BASE_OPTION:
            return self._price_base_option(
                head, configuration_id, source, context, digest)
        if source == PRICE_SOURCE_MATRIX:
            return self._price_matrix(
                head, configuration_id, source, context, digest)

        code = self._result_code(configuration_id, source, digest)
        cached = self._find_cached(code)
        if cached:
            return self._build_result(
                head, configuration_id, source, cached, cached=True)

        return self._price_and_cache(head, configuration_id, source, code, context)

    def _price_and_cache(self, head: Dict[str, Any], configuration_id: Any,
                         source: str, code: str,
                         context: Dict[str, Any]) -> Dict[str, Any]:
        """出价并落库；并发撞唯一键时回读已有结果（§2.3）。"""
        try:
            return self._price_none(head, configuration_id, code, context)
        except Exception as exc:
            if not self._is_unique_violation(exc):
                raise
            cached = self._find_cached(code)
            if not cached:
                raise
            logger.info('并发撞键，回读已有结果 code=%s', code)
            return self._build_result(
                head, configuration_id, source, cached, cached=True)

    @staticmethod
    def _is_unique_violation(exc: Exception) -> bool:
        text = str(exc).lower()
        return 'unique' in text or 'duplicate' in text

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_context(pricing_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        context = dict(pricing_context or {})
        currency = str(context.get('currency_code') or '').strip().upper()
        if currency:
            context['currency_code'] = currency
        order_date = str(context.get('order_date') or '').strip()
        if order_date:
            context['order_date'] = order_date[:10]
        return context

    def _check_pairing(self, source: str, context: Dict[str, Any],
                       configuration_id: Any) -> None:
        mode = str(context.get('pricing_mode') or '').strip().lower()
        if not mode:
            return
        mismatch = (
            (source in ROLLED_UP_SOURCES and mode != 'rolled_up')
            or (source in PARENT_PRICED_SOURCES and mode != 'parent_priced')
        )
        if mismatch:
            raise ItemStructureConfigError(
                f'定价来源 {source} 与定价归属 {mode} 不匹配',
                code='CONFIG_CONFLICT', rule='pricing_mode_mismatch',
                field_name='pricing_mode', configuration_id=configuration_id)

    @staticmethod
    def _check_resolved(head: Dict[str, Any], resolved: Any,
                        configuration_id: Any) -> None:
        if resolved is None:
            return
        claimed = resolved.get('components') if isinstance(resolved, dict) else resolved
        if not isinstance(claimed, Sequence):
            raise ItemStructureConfigError(
                'resolved 需为组件列表', code='CONFIG_INVALID_VALUE',
                rule='resolved_invalid', field_name='resolved',
                configuration_id=configuration_id)
        actual = {
            (str(c.get('component_key')), round(float(c.get('qty') or 0), 6))
            for c in head.get('components') or []
        }
        provided = {
            (str(c.get('component_key')), round(float(c.get('qty') or 0), 6))
            for c in claimed if isinstance(c, dict)
        }
        if provided != actual:
            raise ItemStructureConfigError(
                '调用方展开结果与库内组件不一致，拒绝定价',
                code='CONFIG_INVALID_VALUE', rule='resolved_mismatch',
                field_name='resolved', configuration_id=configuration_id)

    # ------------------------------------------------------------------
    # 幂等
    # ------------------------------------------------------------------
    @staticmethod
    def _context_digest(context: Dict[str, Any],
                        config_hash: Any = None) -> str:
        """幂等摘要 = 规范化 `pricing_context` + `config_hash`。

        `config_hash` 必须入键（§2.3）：实例内容变化（改选、改量）后
        `config_hash` 同步变化，若不入键则会命中旧价 —— 缓存键便退化为
        "只看上下文"，价格不再随配置变化。
        """
        payload = json.dumps(
            {'config_hash': config_hash, 'context': context},
            ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _result_code(self, configuration_id: Any, source: str,
                     digest: str) -> str:
        return 'cfg:{}:{}:{}'.format(configuration_id, source, digest[:8])

    def _find_cached(self, code: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            f"SELECT id, code, document_type, document_id, level, rate, base, "
            f"amount, net_amount, currency, status, created_at "
            f"FROM {_CALC_RESULT_TABLE} WHERE code = ? AND status = 'active'",
            [code])
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # 来源：none
    # ------------------------------------------------------------------
    def _price_none(self, head: Dict[str, Any], configuration_id: Any,
                    code: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """以模型物料为 root 行按普通行定价一次；组件不参与计价。"""
        process_code, rate_table_id = self._require_context(
            context, configuration_id)

        self._check_currency(process_code, context, configuration_id)

        base = self._to_number(context.get('base')) or 1.0
        slot_keys = context.get('slot_keys') or []
        try:
            priced = self.pricing.price_line(
                process_code, int(rate_table_id), slot_keys, base,
                sequence_code=context.get('sequence_code') or None,
                document_type='configuration',
                document_id=int(configuration_id),
                level='header',
                valid_on=context.get('order_date') or None,
                persist=True,
                result_code=code,
            )
        except PricingError as exc:
            raise ItemStructureConfigError(
                f'定价域无价: {exc}', code='CONFIG_PRICE_MISSING',
                rule='price_not_found', field_name='price_source',
                configuration_id=configuration_id) from exc
        except (ResolutionError, CalculationError) as exc:
            raise ItemStructureConfigError(
                f'定价过程不可解: {exc}', code='CONFIG_CONFLICT',
                rule='pricing_procedure_invalid', field_name='pricing_context',
                configuration_id=configuration_id) from exc

        net = float(priced.get('net_amount') or 0.0)
        unit_price = round(net / base, 6) if base else net
        detail = {
            'component_no': 'root',
            'unit_price': unit_price,
            'net_amount': net,
            'pricing_trace': self._trace_of(priced),
        }
        return {
            'contract_version': CONTRACT_VERSION,
            'configuration_id': configuration_id,
            'config_hash': head.get('config_hash'),
            'price_source': PRICE_SOURCE_NONE,
            'currency_code': self._currency_of(context, process_code),
            'lines': [detail],
            'total': net,
            'cached': False,
        }

    def _check_currency(self, process_code: str, context: Dict[str, Any],
                        configuration_id: Any) -> None:
        requested = str(context.get('currency_code') or '').strip().upper()
        if not requested:
            return
        process = self.pricing.get_procedure(process_code) or {}
        declared = str(process.get('currency') or '').strip().upper()
        if declared and declared != requested:
            raise ItemStructureConfigError(
                f'定价过程币种 {declared} 与请求币种 {requested} 不一致',
                code='CONFIG_INVALID_VALUE', rule='currency_mismatch',
                field_name='currency_code', configuration_id=configuration_id)

    @staticmethod
    def _currency_of(context: Dict[str, Any], process_code: str) -> str:
        return str(context.get('currency_code') or '').strip().upper()

    @staticmethod
    def _trace_of(priced: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'step_results': priced.get('step_results') or [],
            'traces': priced.get('traces') or [],
            'hit_ids': priced.get('hit_ids') or [],
        }

    # ------------------------------------------------------------------
    # 来源：component_price（P4.2）
    # ------------------------------------------------------------------
    def _price_components(self, head: Dict[str, Any], configuration_id: Any,
                          source: str, context: Dict[str, Any],
                          digest: str) -> Dict[str, Any]:
        """逐组件独立取价，父行 0 + Σ 组件价。

        [口径]
          - 每组件一次 `price_line`：`base` = 组件 qty，宿主行用
            `document_line_id = configuration_component.id`，故重算只作废该行。
          - 组件 `component_key` 作 `component_no`（D7），同物料多键逐键计价、
            不按物料合并（R14）。
          - 缺任一组件价即抛 `CONFIG_PRICE_MISSING`，不返回部分汇总。
            已定价的兄弟组件保留为缓存（各自独立键，属于可复用的局部结果，
            不构成"用其余补齐"）。
          - 取整只在最终 `total` 做一次。
        """
        process_code, rate_table_id = self._require_context(
            context, configuration_id)
        self._check_currency(process_code, context, configuration_id)
        currency = self._currency_of(context, process_code)

        components = sorted(
            head.get('components') or [],
            key=lambda c: (self._to_number(c.get('seq')) or 0.0,
                           str(c.get('component_key') or '')))

        lines: List[Dict[str, Any]] = []
        codes: List[str] = []
        all_cached = True
        for comp in components:
            key = str(comp.get('component_key') or '')
            code = self._line_code(configuration_id, source, key, digest)
            codes.append(code)
            row = self._find_cached(code)
            if row:
                lines.append(self._component_line(row, key))
                continue
            all_cached = False
            lines.append(self._price_single(
                key, code,
                self._fill_item_slot(
                    context.get('slot_keys'), comp.get('component_item_code')),
                self._component_base(comp),
                configuration_id=configuration_id,
                process_code=process_code, rate_table_id=rate_table_id,
                context=context, document_line_id=comp.get('id'),
                level='line', strict=True))

        if codes:
            self._invalidate_stale_components(configuration_id, source, codes)
        return self._assemble_components(
            head, configuration_id, source, currency, lines,
            cached=all_cached and bool(components))

    # ------------------------------------------------------------------
    # 来源：base_plus_option（P4.3）
    # ------------------------------------------------------------------
    def _price_base_option(self, head: Dict[str, Any], configuration_id: Any,
                           source: str, context: Dict[str, Any],
                           digest: str) -> Dict[str, Any]:
        """父行基准价一次 + 每个选中项按选项编码各取一次加价（可为负）。

        [口径]
          - 基准价与选项价用同一套槽位模板；`item_code` 槽位分别在基准取价时
            填模型物料、在选项取价时填组件物料（选项编码 = `item.code`，D3）。
          - 基准价缺失即阻断（无基准时加价无意义）；选项未配加价按 0 计并告警。
          - 减价允许负；`total` 为负时阻断。
        """
        process_code, rate_table_id = self._require_context(
            context, configuration_id)
        self._check_currency(process_code, context, configuration_id)
        currency = self._currency_of(context, process_code)

        base_code = self._result_code(configuration_id, source, digest)
        base_row = self._find_cached(base_code)
        if base_row:
            base_line = self._component_line(base_row, 'root')
        else:
            base_line = self._price_single(
                'root', base_code,
                self._fill_item_slot(
                    context.get('slot_keys'), head.get('model_code')),
                self._to_number(context.get('base')) or 1.0,
                configuration_id=configuration_id,
                process_code=process_code, rate_table_id=rate_table_id,
                context=context, document_line_id=None,
                level='header', strict=True)

        components = sorted(
            head.get('components') or [],
            key=lambda c: (self._to_number(c.get('seq')) or 0.0,
                           str(c.get('component_key') or '')))
        lines: List[Dict[str, Any]] = []
        codes: List[str] = [base_code]
        all_cached = base_row is not None
        for comp in components:
            key = str(comp.get('component_key') or '')
            code = self._line_code(configuration_id, source, key, digest)
            codes.append(code)
            row = self._find_cached(code)
            if row:
                lines.append(self._component_line(row, key))
                continue
            all_cached = False
            lines.append(self._price_single(
                key, code,
                self._fill_item_slot(
                    context.get('slot_keys'), comp.get('component_item_code')),
                self._component_base(comp),
                configuration_id=configuration_id,
                process_code=process_code, rate_table_id=rate_table_id,
                context=context, document_line_id=comp.get('id'),
                level='line', strict=False))

        if codes:
            self._invalidate_stale_components(configuration_id, source, codes)

        warnings = [
            f'选项 {line["component_no"]} 未配加价，按 0 计'
            for line in lines if float(line['net_amount']) == 0.0
        ]
        total = round(
            float(base_line['net_amount'])
            + sum(float(line['net_amount']) for line in lines), 2)
        if total < 0:
            raise ItemStructureConfigError(
                f'配置定价总额为负: {total}', code='CONFIG_INVALID_VALUE',
                rule='price_total_negative', field_name='total',
                configuration_id=configuration_id)

        return {
            'contract_version': CONTRACT_VERSION,
            'configuration_id': configuration_id,
            'config_hash': head.get('config_hash'),
            'price_source': source,
            'currency_code': currency,
            'lines': [base_line] + lines,
            'total': total,
            'warnings': warnings,
            'cached': all_cached,
        }

    # ------------------------------------------------------------------
    # 来源：attribute_matrix（P4.4）
    # ------------------------------------------------------------------
    def _price_matrix(self, head: Dict[str, Any], configuration_id: Any,
                      source: str, context: Dict[str, Any],
                      digest: str) -> Dict[str, Any]:
        """特征组合 → 一次取整机价。

        [口径]
          - 维度 = 查找序列各槽位声明的 `key_schema.key_fields`，按 seq 顺序
            组装 `slot_keys`；值只取自 `configuration_value`，不读调用方的
            `slot_keys`（避免实例与请求两个真相）。
          - 维度缺特征值即 `CONFIG_INCOMPLETE`；矩阵未覆盖该组合即
            `CONFIG_PRICE_MISSING`（strict：不留 0 价 active 行）。
        """
        process_code, rate_table_id = self._require_context(
            context, configuration_id)
        self._check_currency(process_code, context, configuration_id)
        currency = self._currency_of(context, process_code)

        slot_keys = self._matrix_slots(head, context, configuration_id)
        code = self._result_code(configuration_id, source, digest)
        row = self._find_cached(code)
        if row:
            line = self._component_line(row, 'root')
            cached = True
        else:
            line = self._price_single(
                'root', code, slot_keys,
                self._to_number(context.get('base')) or 1.0,
                configuration_id=configuration_id,
                process_code=process_code, rate_table_id=rate_table_id,
                context=context, document_line_id=None,
                level='header', strict=True)
            cached = False

        return {
            'contract_version': CONTRACT_VERSION,
            'configuration_id': configuration_id,
            'config_hash': head.get('config_hash'),
            'price_source': source,
            'currency_code': currency,
            'lines': [line],
            'total': round(float(line['net_amount']), 2),
            'cached': cached,
        }

    def _matrix_slots(self, head: Dict[str, Any], context: Dict[str, Any],
                      configuration_id: Any) -> List[Dict[str, Any]]:
        """按查找序列的槽位声明装配维度键值。"""
        sequence_code = str(context.get('sequence_code') or '').strip()
        sequence = self.pricing.get_sequence(sequence_code) if sequence_code else None
        steps = sorted(
            self._json_list(sequence.get('steps'), []) if sequence else [],
            key=lambda step: step.get('seq') or 0)

        if not steps:
            raise ItemStructureConfigError(
                'attribute_matrix 需要带槽位声明的查找序列',
                code='CONFIG_INCOMPLETE', rule='pricing_context_incomplete',
                field_name='sequence_code',
                configuration_id=configuration_id)

        values = self._value_map(head)
        slots: List[Dict[str, Any]] = []
        for step in steps:
            slot: Dict[str, Any] = {}
            for name in self._key_fields_of(
                    step.get('key_schema_id'), configuration_id):
                value = values.get(name)
                if value is None:
                    raise ItemStructureConfigError(
                        f'矩阵维度 {name} 缺特征值', code='CONFIG_INCOMPLETE',
                        rule='matrix_dimension_missing', field_name=name,
                        configuration_id=configuration_id)
                slot[name] = value
            slots.append(slot)
        return slots

    def _key_fields_of(self, key_schema_id: Any,
                       configuration_id: Any) -> List[str]:
        rows = self.ds.query(
            'SELECT key_fields FROM key_schemas WHERE id = ?', [key_schema_id])
        fields = self._json_list(rows[0].get('key_fields'), []) if rows else []
        if not fields:
            raise ItemStructureConfigError(
                f'键模式 {key_schema_id} 未声明 key_fields',
                code='CONFIG_INCOMPLETE', rule='pricing_context_incomplete',
                field_name='key_schema_id',
                configuration_id=configuration_id)
        return [str(name) for name in fields]

    @classmethod
    def _value_map(cls, head: Dict[str, Any]) -> Dict[str, Any]:
        """`attribute_code → 特征值`；同一特征多行时取首个非空值。"""
        values: Dict[str, Any] = {}
        for row in head.get('values') or []:
            name = str(row.get('attribute_code') or '')
            if not name or name in values:
                continue
            value = cls._value_of(row)
            if value is not None:
                values[name] = value
        return values

    @staticmethod
    def _value_of(row: Dict[str, Any]) -> Any:
        """按 文本 / 数值 / 布尔 的顺序取第一个非空值（三列是互斥载体）。"""
        for column in ('value_text', 'value_number', 'value_boolean'):
            value = row.get(column)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            return bool(value) if column == 'value_boolean' else value
        return None

    @staticmethod
    def _json_list(value: Any, default: List[Any]) -> List[Any]:
        if value in (None, ''):
            return default
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return default
        return parsed if isinstance(parsed, list) else default

    def _price_single(self, key: str, code: str, slot_keys: List[Dict[str, Any]],
                      base: float, *, configuration_id: Any,
                      process_code: str, rate_table_id: Any,
                      context: Dict[str, Any],
                      document_line_id: Any = None, level: str = 'line',
                      strict: bool = False) -> Dict[str, Any]:
        """单行取价并落库。

        `strict=True`：查表无命中即 `CONFIG_PRICE_MISSING`，并作废刚落的 0 价行
        （组件价场景）；`strict=False`：无命中按 0 计，留行待告警（选项加价场景）。
        """
        try:
            priced = self.pricing.price_line(
                process_code, int(rate_table_id), slot_keys, base,
                sequence_code=context.get('sequence_code') or None,
                document_type='configuration',
                document_id=int(configuration_id),
                document_line_id=document_line_id,
                level=level,
                valid_on=context.get('order_date') or None,
                persist=True,
                result_code=code,
            )
        except PricingError as exc:
            raise ItemStructureConfigError(
                f'{key} 无价: {exc}', code='CONFIG_PRICE_MISSING',
                rule='price_not_found', field_name='price_source',
                configuration_id=configuration_id) from exc
        except (ResolutionError, CalculationError) as exc:
            raise ItemStructureConfigError(
                f'{key} 定价过程不可解: {exc}', code='CONFIG_CONFLICT',
                rule='pricing_procedure_invalid', field_name='pricing_context',
                configuration_id=configuration_id) from exc
        except Exception as exc:
            if not self._is_unique_violation(exc):
                raise
            cached = self._find_cached(code)
            if not cached:
                raise
            logger.info('定价并发撞键，回读已有结果 code=%s', code)
            return self._component_line(cached, key)

        if (strict and context.get('sequence_code')
                and not priced.get('hit_ids')):
            # 刚落的 0 价行不能留成 active —— 否则下次调用会命中缓存静默返回 0
            self._invalidate_result(priced.get('result_id'))
            raise ItemStructureConfigError(
                f'{key} 未命中价目表', code='CONFIG_PRICE_MISSING',
                rule='price_not_found', field_name='price_source',
                configuration_id=configuration_id)

        net = float(priced.get('net_amount') or 0.0)
        unit_price = round(net / base, 6) if base else net
        return {
            'component_no': key,
            'unit_price': unit_price,
            'net_amount': net,
            'pricing_trace': self._trace_of(priced),
        }

    def _component_base(self, comp: Dict[str, Any]) -> float:
        qty = self._to_number(comp.get('qty'))
        return 1.0 if qty is None else qty

    @staticmethod
    def _fill_item_slot(slot_keys: Any, item_code: Any) -> List[Dict[str, Any]]:
        """把物料编码填入 `item_code` 槽位（`component_price` 与选项加价共用）。

        调用方在 `slot_keys` 里用占位值声明该槽位（如 `{'item_code': None}`），
        本方法按当前计价对象覆写。未声明 `item_code` 的槽位原样透传——价目表
        按其它维度（如客户）取价时无需物料维度。
        """
        slots: List[Dict[str, Any]] = []
        for slot in slot_keys or []:
            value = dict(slot) if isinstance(slot, dict) else {}
            if 'item_code' in value:
                value['item_code'] = item_code
            slots.append(value)
        return slots

    @staticmethod
    def _line_code(configuration_id: Any, source: str, key: str,
                   digest: str) -> str:
        return 'cfg:{}:{}:{}:{}'.format(
            configuration_id, source, key or 'root', digest[:8])

    @staticmethod
    def _component_line(row: Dict[str, Any], key: str) -> Dict[str, Any]:
        net = float(row.get('net_amount') or 0.0)
        base = float(row.get('base') or 0.0)
        unit_price = float(row.get('rate') or 0.0)
        if not unit_price and base:
            unit_price = round(net / base, 6)
        return {
            'component_no': key,
            'unit_price': unit_price,
            'net_amount': net,
            'pricing_trace': {},
        }

    def _assemble_components(self, head: Dict[str, Any], configuration_id: Any,
                             source: str, currency: str,
                             lines: List[Dict[str, Any]], *,
                             cached: bool) -> Dict[str, Any]:
        root = {
            'component_no': 'root',
            'unit_price': 0.0,
            'net_amount': 0.0,
            'pricing_trace': {},
        }
        total = round(sum(float(line['net_amount']) for line in lines), 2)
        return {
            'contract_version': CONTRACT_VERSION,
            'configuration_id': configuration_id,
            'config_hash': head.get('config_hash'),
            'price_source': source,
            'currency_code': currency,
            'lines': [root] + lines,
            'total': total,
            'cached': cached,
        }

    def _invalidate_stale_components(self, configuration_id: Any, source: str,
                                     codes: List[str]) -> None:
        """作废本实例该来源下已不在当前组件集的 active 结果（组件被删除/替换时）。"""
        placeholders = ', '.join('?' for _ in codes)
        self.ds.execute(
            "UPDATE calc_results SET status = 'invalid', updated_at = ?"
            " WHERE document_type = 'configuration' AND document_id = ?"
            "   AND status = 'active' AND level = 'line'"
            "   AND code LIKE ? AND code NOT IN ({})".format(placeholders),
            [datetime.now().isoformat(timespec='seconds'), int(configuration_id),
             'cfg:{}:{}:%'.format(configuration_id, source), *codes])

    def _invalidate_result(self, result_id: Any) -> None:
        if result_id in (None, ''):
            return
        self.ds.execute(
            "UPDATE calc_results SET status = 'invalid', updated_at = ?"
            " WHERE id = ? AND status = 'active'",
            [datetime.now().isoformat(timespec='seconds'), result_id])

    def _require_context(self, context: Dict[str, Any],
                         configuration_id: Any) -> tuple:
        process_code = str(context.get('pricing_procedure_code') or '').strip()
        rate_table_id = context.get('rate_table_id')
        if not process_code or rate_table_id in (None, ''):
            raise ItemStructureConfigError(
                'pricing_context 缺少 pricing_procedure_code 或 rate_table_id',
                code='CONFIG_INCOMPLETE', rule='pricing_context_incomplete',
                field_name='pricing_context',
                configuration_id=configuration_id)
        return process_code, rate_table_id

    # ------------------------------------------------------------------
    # 缓存回读
    # ------------------------------------------------------------------
    def _build_result(self, head: Dict[str, Any], configuration_id: Any,
                      source: str, row: Dict[str, Any],
                      cached: bool) -> Dict[str, Any]:
        details = self.ds.query(
            f"SELECT seq, element_type, unit_price, extended_amount, "
            f"running_net_amount, subtotal_key FROM {_CALC_DETAIL_TABLE} "
            f"WHERE result_id = ? ORDER BY seq", [row.get('id')]) or []
        net = float(row.get('net_amount') or 0.0)
        base = float(row.get('base') or 0.0)
        unit_price = float(row.get('rate') or 0.0)
        if not unit_price and base:
            unit_price = round(net / base, 6)
        return {
            'contract_version': CONTRACT_VERSION,
            'configuration_id': configuration_id,
            'config_hash': head.get('config_hash'),
            'price_source': source,
            'currency_code': row.get('currency'),
            'lines': [{
                'component_no': 'root',
                'unit_price': unit_price,
                'net_amount': net,
                'pricing_trace': {'steps': details},
            }],
            'total': net,
            'cached': cached,
        }

    # ------------------------------------------------------------------
    # 小工具
    # ------------------------------------------------------------------
    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
