# -*- coding: utf-8 -*-
"""编号序列取号内核（number_sequence）

依据: docs/superpowers/specs/2026-10-25-number-sequence-implementation-spec.md

与平台 key_template 的关系:
  复用 KeyTemplateParser 的词法（{field} / {SEQ:n} / 分隔符 / 字面量）与
  `_sequences` 状态表定义；**不复用** SequenceEngine.next_value —— 它每一步
  commit()，与「独立短事务取号」契约冲突；也不复用 KeyTemplateInterceptor
  （目标列硬编码 code、取系统时钟、仅用于 create）。

取号语义:
  独立短事务（BEGIN IMMEDIATE）内 自增 + 读回 + 立即提交。
  等价于 SAP 缓冲取号（buffer=1）/ Oracle 数据库序列:
  取号即提交、业务失败不回退、允许空号；唯一性由调用表唯一索引兜底，
  内核不做预查重（预查是 TOCTOU），撞索引由调用方重取重试。
"""
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.key_template_engine import (
    _CREATE_TABLE_SQL,
    _SEQUENCES_TABLE,
    KeyTemplateParser,
)

logger = logging.getLogger(__name__)

_DATE_TOKEN_RE = re.compile(r'\{DATE:(yyyy|yyyymm|yyyymmdd)\}')
_ANY_TOKEN_RE = re.compile(r'\{([^{}]+)\}')
_SEQ_TOKEN_RE = re.compile(r'^SEQ:(\d+)$')
_FIELD_TOKEN_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

_DATE_FORMATS = {
    'yyyy': '%Y',
    'yyyymm': '%Y%m',
    'yyyymmdd': '%Y%m%d',
}


class NumberSequenceError(ValueError):
    """编号序列配置或取号失败（消息直接面向用户）"""


class NumberSequenceEngine:
    """编号序列取号内核。

    config 为规则字典（YAML 行或 DB 行均可），至少含:
    code / pattern / start_value / on_exhaust / date_field / scope_fields
    """

    def __init__(self, data_source):
        self._ds = data_source
        self._parser = KeyTemplateParser()
        self._ensure_state_table()

    # ────────────────────────────────────────
    # 状态表
    # ────────────────────────────────────────
    def _ensure_state_table(self) -> None:
        """幂等确保 _sequences 存在（与 key_template 共用同一张状态表）"""
        try:
            self._ds.execute(_CREATE_TABLE_SQL)
            if not getattr(self._ds, 'in_transaction', False):
                self._ds.commit()
        except Exception as e:  # pragma: no cover - 表已存在属正常路径
            logger.warning('[NumberSequenceEngine] ensure _sequences failed: %s', e)

    # ────────────────────────────────────────
    # pattern 校验
    # ────────────────────────────────────────
    def validate_pattern(self, pattern: str) -> Dict[str, Any]:
        """结构校验，返回 {'padding', 'fields', 'has_date'}

        抛 NumberSequenceError：空模式 / 无 SEQ / 多个 SEQ /
        padding 非正 / 未知令牌 / 日期令牌格式非法。
        """
        if not pattern or not str(pattern).strip():
            raise NumberSequenceError('编号模式不能为空')
        pattern = str(pattern)

        seq_count = 0
        padding = 0
        fields: List[str] = []
        has_date = False

        for m in _ANY_TOKEN_RE.finditer(pattern):
            body = m.group(1)
            seq_match = _SEQ_TOKEN_RE.match(body)
            if seq_match:
                seq_count += 1
                padding = int(seq_match.group(1))
                continue
            if body.startswith('DATE:'):
                fmt = body[len('DATE:'):]
                if fmt not in _DATE_FORMATS:
                    raise NumberSequenceError(
                        '编号模式含未知日期令牌 {%s}，仅支持 '
                        'yyyy / yyyymm / yyyymmdd' % m.group(0)
                    )
                has_date = True
                continue
            if _FIELD_TOKEN_RE.match(body):
                fields.append(body)
                continue
            raise NumberSequenceError('编号模式含未知令牌 %s' % m.group(0))

        if seq_count == 0:
            raise NumberSequenceError('编号模式缺少 {SEQ:n} 流水段')
        if seq_count > 1:
            raise NumberSequenceError('编号模式只能包含一个 {SEQ:n} 流水段')
        if padding <= 0:
            raise NumberSequenceError('流水位数必须为正整数')

        return {'padding': padding, 'fields': fields, 'has_date': has_date}

    # ────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────
    def allocate(self, config: Dict[str, Any],
                 field_values: Optional[Dict[str, Any]] = None,
                 date_values: Optional[Dict[str, Any]] = None) -> str:
        """原子取号并立即提交，返回渲染后的编号。"""
        tokens, values, sequence_key, info = self._prepare(
            config, field_values, date_values
        )
        start_value = self._start_value(config)
        on_exhaust = config.get('on_exhaust') or 'error'

        # 取号必须独立成事务：嵌入调用方事务会退化为 SAP 非缓冲号段
        # （锁持有到调用方 COMMIT），且回滚会把号一并回滚 —— 与「允许空号」相反。
        if getattr(self._ds, 'in_transaction', False):
            raise NumberSequenceError(
                '取号必须在独立事务中执行，不能嵌入调用方事务'
            )

        seq_value = self._next_value_in_tx(sequence_key, start_value)
        self._check_exhaust(seq_value, info['padding'], on_exhaust)
        return self._parser.resolve(tokens, values, seq_value)

    def peek(self, config: Dict[str, Any],
             field_values: Optional[Dict[str, Any]] = None,
             date_values: Optional[Dict[str, Any]] = None) -> str:
        """预览下一个号，不写状态、不建行。"""
        tokens, values, sequence_key, info = self._prepare(
            config, field_values, date_values
        )
        start_value = self._start_value(config)
        on_exhaust = config.get('on_exhaust') or 'error'

        row = self._ds.execute(
            'SELECT current_value FROM %s WHERE sequence_name = ?' % _SEQUENCES_TABLE,
            (sequence_key,),
        ).fetchone()
        if row is None:
            seq_value = start_value
        else:
            current = self._row_value(row, 'current_value')
            seq_value = max(int(current) + 1, start_value)

        self._check_exhaust(seq_value, info['padding'], on_exhaust)
        return self._parser.resolve(tokens, values, seq_value)

    # ────────────────────────────────────────
    # 内部实现
    # ────────────────────────────────────────
    def _prepare(self, config: Dict[str, Any],
                 field_values: Optional[Dict[str, Any]],
                 date_values: Optional[Dict[str, Any]]
                 ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str, Dict[str, Any]]:
        """校验 + 日期渲染 + 字段校验 + 生成 _sequences 键。"""
        if not isinstance(config, dict):
            raise NumberSequenceError('编号序列配置缺失')
        code = config.get('code')
        if not code:
            raise NumberSequenceError('编号序列缺少 code')

        info = self.validate_pattern(config.get('pattern'))
        values: Dict[str, Any] = dict(field_values or {})
        dates: Dict[str, Any] = dict(date_values or {})

        # 1) 日期令牌 → 实际日期串；周期键由日期令牌派生（不用系统时钟）
        period_key = None
        pattern = str(config.get('pattern'))
        if info['has_date']:
            date_field = config.get('date_field') or 'order_date'
            raw_date = dates.get(date_field)
            if raw_date is None or raw_date == '':
                raise NumberSequenceError(
                    '编号模式需要业务日期字段 `%s`，但未提供' % date_field
                )
            rendered_dates: List[str] = []

            def _repl(m):
                fmt = m.group(1)
                rendered = self._coerce_date(raw_date, date_field).strftime(
                    _DATE_FORMATS[fmt]
                )
                rendered_dates.append(rendered)
                return rendered

            pattern = _DATE_TOKEN_RE.sub(_repl, pattern)
            period_key = '|'.join(rendered_dates)

        # 2) 词法解析 + 字段必填校验（parser.resolve 会静默跳过缺值，这里必须拦截）
        tokens = self._parser.parse(pattern)
        for token in tokens:
            if token['type'] != 'field':
                continue
            name = token['name']
            if values.get(name) is None or values.get(name) == '':
                raise NumberSequenceError(
                    '编号模式引用的字段 `%s` 缺少取值' % name
                )

        # 3) 分段键（空 = 全局唯一）
        scope_fields = self._normalize_scope_fields(config.get('scope_fields'))
        if not scope_fields:
            scope_key = 'default'
        else:
            scope_values: List[str] = []
            for name in scope_fields:
                val = values.get(name)
                if val is None or val == '':
                    raise NumberSequenceError(
                        '编号分段字段 `%s` 缺少取值' % name
                    )
                scope_values.append(str(val).upper())
            scope_key = '|'.join(scope_values)

        sequence_key = '%s:%s' % (code, scope_key)
        if period_key:
            sequence_key = '%s:%s' % (sequence_key, period_key)

        return tokens, values, sequence_key, info

    def _next_value_in_tx(self, sequence_key: str, start_value: int) -> int:
        """独立短事务内自增并读回。

        不用 RETURNING（仓库零处使用，避免 SQLite >= 3.35 依赖）；
        BEGIN IMMEDIATE 由 DataSource.transaction() → begin_transaction() 提供。
        """
        start_baseline = start_value - 1
        with self._ds.transaction():
            self._ds.execute(
                'INSERT OR IGNORE INTO %s (sequence_name, current_value) '
                'VALUES (?, ?)' % _SEQUENCES_TABLE,
                (sequence_key, start_baseline),
            )
            # 历史行可能低于 start_value（如手工改过起始值）—— 抬到基线
            self._ds.execute(
                'UPDATE %s SET current_value = ? '
                'WHERE sequence_name = ? AND current_value < ?' % _SEQUENCES_TABLE,
                (start_baseline, sequence_key, start_baseline),
            )
            self._ds.execute(
                'UPDATE %s SET current_value = current_value + 1 '
                'WHERE sequence_name = ?' % _SEQUENCES_TABLE,
                (sequence_key,),
            )
            row = self._ds.execute(
                'SELECT current_value FROM %s WHERE sequence_name = ?'
                % _SEQUENCES_TABLE,
                (sequence_key,),
            ).fetchone()

        if row is None:  # pragma: no cover - INSERT OR IGNORE 后不应发生
            raise NumberSequenceError('编号状态行写入失败：%s' % sequence_key)
        return int(self._row_value(row, 'current_value'))

    def _start_value(self, config: Dict[str, Any]) -> int:
        raw = config.get('start_value')
        try:
            start_value = int(raw) if raw is not None else 1
        except (TypeError, ValueError):
            raise NumberSequenceError('起始值必须为正整数')
        if start_value < 1:
            raise NumberSequenceError('起始值必须为正整数')
        return start_value

    def _check_exhaust(self, seq_value: int, padding: int,
                       on_exhaust: str) -> None:
        if len(str(seq_value)) <= padding:
            return
        if on_exhaust == 'extend':
            return
        raise NumberSequenceError(
            '编号流水已超出 %d 位，请调整模式或改为 extend' % padding
        )

    @staticmethod
    def _normalize_scope_fields(raw: Any) -> List[str]:
        if raw is None or raw == '':
            return []
        if isinstance(raw, (list, tuple)):
            return [str(x) for x in raw if str(x)]
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = [x.strip() for x in text.split(',') if x.strip()]
            if isinstance(parsed, (list, tuple)):
                return [str(x) for x in parsed if str(x)]
            raise NumberSequenceError('分段字段必须为字段名列表')
        raise NumberSequenceError('分段字段必须为字段名列表')

    @staticmethod
    def _coerce_date(value: Any, field_name: str) -> date:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            raise NumberSequenceError(
                '业务日期字段 `%s` 缺少取值' % field_name
            )
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            pass
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise NumberSequenceError(
                '业务日期字段 `%s` 的取值 `%s` 无法解析为日期'
                % (field_name, text)
            )

    @staticmethod
    def _row_value(row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return row[0]
