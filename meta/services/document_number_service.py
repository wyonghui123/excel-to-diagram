# -*- coding: utf-8 -*-
"""单据取号唯一入口。

取号必须在开事务前独立完成（NumberSequenceEngine 的硬约束：嵌入调用方
事务会退化为「锁持有到 COMMIT + 回滚把号一并回滚」）。本服务只负责
「解析序列 → 分配」，各调用方自行决定取号失败是静默跳过还是抛域错误。

对象 → 编号列 / 日期列 / 序列来源集中声明在 NUMBERING；新增单据加一行。
"""

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
        config = NUMBERING.get(object_type)
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

    @staticmethod
    def _fail(config, required, message):
        if not required:
            return None
        raise DocumentNumberError(
            message, field_name=config['no_field'],
            rule='NUMBER_SEQUENCE_UNAVAILABLE')
