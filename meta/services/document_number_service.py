# -*- coding: utf-8 -*-
"""单据取号唯一入口。

取号必须在开事务前独立完成（NumberSequenceEngine 的硬约束：嵌入调用方
事务会退化为「锁持有到 COMMIT + 回滚把号一并回滚」）。本服务只负责
「解析序列 → 分配」，各调用方自行决定取号失败是静默跳过还是抛域错误。

对象 → 编号列 / 日期列 / 序列来源集中声明在 NUMBERING；新增单据加一行。
"""

import re

NUMBERING = {
    'sales_order': {
        'no_field': 'order_no',
        'date_field': 'order_date',
        'type_table': 'type_definitions',
    },
    'purchase_order': {
        'no_field': 'order_no',
        'date_field': 'order_date',
        'type_table': 'type_definitions',
    },
    'receipt': {
        'no_field': 'receipt_no',
        'date_field': 'receipt_date',
        'type_table': 'type_definitions',
    },
    'transfer_order': {
        'no_field': 'transfer_order_no',
        'date_field': 'transfer_date',
        'type_table': 'type_definitions',
    },
    'transfer_shipment': {
        'no_field': 'shipment_no',
        'date_field': 'ship_date',
        'scope_bo': 'transfer_shipment',
        'fallback_sequence_code': 'TRS',
    },
}

_SEQUENCE_SQL = (
    'SELECT code, pattern, scope_fields, date_field, start_value, on_exhaust '
    'FROM number_sequences WHERE id = ?')


def resolve_document_numbering(object_type):
    """[P1 2026-11-06] 元数据优先的取号绑定解析。

    `document.number_field` 非空即视为该对象参与取号；`type_table` 默认
    `type_definitions`（声明了 `numbering.scope_bo` 的对象走 scope 分支，
    例如调拨发货单），其余键由 `document.numbering` 覆盖。
    未声明 `document:` 的对象回落 `NUMBERING`（存量兼容）。
    """
    try:
        from meta.core.models import registry
        meta_object = registry.get(object_type)
    except Exception:  # noqa: BLE001 - 测试环境 registry 可能未初始化
        meta_object = None

    profile = getattr(meta_object, 'document_profile', None)
    if profile is not None and profile.number_field:
        config = {
            'no_field': profile.number_field,
            'date_field': profile.business_date_field or '',
        }
        numbering = dict(profile.numbering or {})
        if not numbering.get('scope_bo'):
            config['type_table'] = 'type_definitions'
        config.update(numbering)
        return config
    return NUMBERING.get(object_type)


class DocumentNumberError(ValueError):
    """取号失败（序列未配置 / 分配异常）。"""

    code = 'DOCUMENT_NUMBER_UNAVAILABLE'

    def __init__(self, message, field_name='', rule=''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


class DocumentNumberService:
    def __init__(self, data_source):
        self._ds = data_source

    def allocate_for(self, object_type, payload, *, required=False):
        """返回分配到的编号；已带号 / 未挂序列时返回 None。

        required=True 时，序列缺失或分配失败抛 DocumentNumberError。
        """
        config = resolve_document_numbering(object_type)
        if config is None:
            raise DocumentNumberError('未声明取号规则的单据类型: %s' % object_type)
        no_field = config['no_field']
        if payload.get(no_field):
            return None

        date_value = payload.get(config['date_field'])
        if date_value in (None, ''):
            return self._fail(config, required, '缺少取号日期')

        sequence_id = self._resolve_sequence_id(object_type, config, payload)
        if sequence_id in (None, ''):
            return self._fail(config, required, '单据类型未绑定编号序列')

        rows = self._ds.query(_SEQUENCE_SQL, [sequence_id])
        if not rows:
            return self._fail(config, required, '编号序列 %s 不存在' % sequence_id)

        from meta.core.number_sequence_engine import (
            NumberSequenceEngine, NumberSequenceError)
        try:
            return NumberSequenceEngine(self._ds).allocate(
                dict(rows[0]), {},
                {config['date_field']: date_value})
        except NumberSequenceError as error:
            # 序列存在但分配失败（耗尽 / 模式非法）属异常，不受 required 影响
            raise DocumentNumberError(
                str(error), field_name=no_field,
                rule='NUMBER_SEQUENCE_UNAVAILABLE') from error

    def _resolve_sequence_id(self, object_type, config, payload):
        type_table = config.get('type_table')
        document_type_id = payload.get('document_type_id')
        if type_table and document_type_id not in (None, ''):
            rows = self._ds.query(
                'SELECT number_sequence_id FROM %s WHERE id = ?' % type_table,
                [document_type_id])
            return rows[0].get('number_sequence_id') if rows else None

        scope_bo = config.get('scope_bo')
        if scope_bo:
            rows = self._ds.query(
                'SELECT number_sequence_id FROM type_definitions '
                "WHERE scope_bo = ? AND level = 'header' ORDER BY id LIMIT 1",
                [scope_bo])
            sequence_id = rows[0].get('number_sequence_id') if rows else None
            if sequence_id in (None, ''):
                code = config.get('fallback_sequence_code')
                if code:
                    rows = self._ds.query(
                        'SELECT id FROM number_sequences WHERE code = ?', [code])
                    sequence_id = rows[0].get('id') if rows else None
            return sequence_id
        return None

    # ── 外部编号校验（T6.1） ────────────────────────────────────

    def validate_external_number(self, object_type, number, payload=None, *,
                                 table_name=None, exclude_id=None):
        """校验调用方自带单号是否符合序列格式、区间且未重复，返回原值。

        取号与校验是两条路径：已带号时 `allocate_for` 直接返回 None，
        等于绕过全部约束。本方法补上「格式 / 起始值 / 位数上限 / 唯一性」
        四道检查，失败抛 DocumentNumberError（由 API 层转 400）。

        on_exhaust 语义：
          - error  ：流水位数必须恰好等于 {SEQ:n} 的 n，超出容量即拒绝；
          - extend ：允许超过 n 位，只要求不少于 n 位。
        """
        if not isinstance(number, str) or not number.strip():
            raise DocumentNumberError('编号不能为空', rule='NUMBER_FORMAT_INVALID')
        number = number.strip()

        config = resolve_document_numbering(object_type)
        if config is None:
            raise DocumentNumberError(
                '未声明取号规则的单据类型: %s' % object_type,
                rule='NUMBER_SEQUENCE_UNSUPPORTED')
        no_field = config['no_field']
        payload = dict(payload or {})

        sequence_id = self._resolve_sequence_id(object_type, config, payload)
        if sequence_id in (None, ''):
            raise DocumentNumberError(
                '单据类型未绑定编号序列，无法校验外部编号',
                field_name=no_field, rule='NUMBER_SEQUENCE_UNAVAILABLE')
        sequence = self._sequence_row(sequence_id)
        if sequence is None:
            raise DocumentNumberError(
                '编号序列 %s 不存在' % sequence_id,
                field_name=no_field, rule='NUMBER_SEQUENCE_UNAVAILABLE')

        seq_value = self._match_sequence_value(config, sequence, payload, number)
        if seq_value < int(sequence.get('start_value') or 1):
            raise DocumentNumberError(
                '编号流水 %d 小于序列起始值 %s' % (seq_value, sequence.get('start_value')),
                field_name=no_field, rule='NUMBER_OUT_OF_RANGE')

        table = table_name or self._table_for(object_type)
        if not table:
            raise DocumentNumberError(
                '无法解析 %s 的表名，无法校验编号唯一性' % object_type,
                field_name=no_field, rule='NUMBER_TABLE_UNRESOLVED')
        self._assert_unique(table, no_field, number, exclude_id, config)
        return number

    def _sequence_row(self, sequence_id):
        rows = self._ds.query(_SEQUENCE_SQL, [sequence_id])
        return dict(rows[0]) if rows else None

    def _match_sequence_value(self, config, sequence, payload, number):
        """按序列模式把外部编号还原为流水数字；不匹配抛 FORMAT_INVALID。"""
        pattern = sequence.get('pattern') or ''
        padding = self._seq_padding(pattern)
        if padding <= 0:
            raise DocumentNumberError(
                '编号序列缺少 {SEQ:n} 流水段',
                field_name=config['no_field'], rule='NUMBER_SEQUENCE_UNAVAILABLE')

        rendered = self._render_date_tokens(config, sequence, payload, pattern)
        regex, seq_index = self._pattern_regex(
            rendered, payload, padding, sequence.get('on_exhaust') or 'error')
        match = regex.match(number)
        if not match:
            raise DocumentNumberError(
                '编号 %s 不符合序列模式 %s' % (number, pattern),
                field_name=config['no_field'], rule='NUMBER_FORMAT_INVALID')
        return int(match.group(seq_index))

    @staticmethod
    def _seq_padding(pattern):
        found = re.search(r'\{SEQ:(\d+)\}', pattern or '')
        return int(found.group(1)) if found else 0

    @staticmethod
    def _render_date_tokens(config, sequence, payload, pattern):
        """把 {DATE:fmt} 换成 payload 业务日期的实际值；缺日期则拒绝校验。"""
        if not re.search(r'\{DATE:', pattern):
            return pattern
        date_field = sequence.get('date_field') or config['date_field']
        raw = payload.get(date_field)
        if raw in (None, ''):
            raise DocumentNumberError(
                '缺少编号日期字段 `%s`，无法校验外部编号' % date_field,
                field_name=config['no_field'], rule='NUMBER_FORMAT_INVALID')

        from meta.core.number_sequence_engine import (
            _DATE_FORMATS, _DATE_TOKEN_RE, NumberSequenceEngine)

        def _repl(m):
            fmt = m.group(1)
            return NumberSequenceEngine._coerce_date(raw, date_field).strftime(
                _DATE_FORMATS[fmt])

        return _DATE_TOKEN_RE.sub(_repl, pattern)

    @staticmethod
    def _pattern_regex(pattern, payload, padding, on_exhaust):
        """把渲染后的模式转成正则；返回 (regex, 流水分组序号)。"""
        from meta.core.key_template_engine import KeyTemplateParser

        parts = []
        group_index = 0
        seq_index = 0
        for token in KeyTemplateParser().parse(pattern):
            kind = token['type']
            if kind == 'field':
                value = payload.get(token['name'])
                if value in (None, ''):
                    raise DocumentNumberError(
                        '编号模式引用的字段 `%s` 缺少取值' % token['name'],
                        rule='NUMBER_FORMAT_INVALID')
                parts.append(re.escape(str(value).upper()))
            elif kind == 'sequence':
                group_index += 1
                seq_index = group_index
                quantifier = '%d,' % padding if on_exhaust == 'extend' else str(padding)
                parts.append('(\\d{%s})' % quantifier)
            else:
                parts.append(re.escape(token['value']))
        return re.compile('^' + ''.join(parts) + '$'), seq_index

    def _assert_unique(self, table, no_field, number, exclude_id, config):
        sql = 'SELECT id FROM %s WHERE %s = ?' % (table, no_field)
        params = [number]
        if exclude_id not in (None, ''):
            sql += ' AND id <> ?'
            params.append(exclude_id)
        sql += ' LIMIT 1'
        if self._ds.query(sql, params):
            raise DocumentNumberError(
                '编号 %s 已被使用' % number,
                field_name=config['no_field'], rule='NUMBER_DUPLICATE')

    @staticmethod
    def _table_for(object_type):
        from meta.core.models import registry

        meta_obj = registry.get(object_type)
        return getattr(meta_obj, 'table_name', '') if meta_obj else ''

    @staticmethod
    def _fail(config, required, message):
        if not required:
            return None
        raise DocumentNumberError(
            message, field_name=config['no_field'],
            rule='NUMBER_SEQUENCE_UNAVAILABLE')
