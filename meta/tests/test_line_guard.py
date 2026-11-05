# -*- coding: utf-8 -*-
"""行语义通用守卫：行号唯一 + 实物行数量正数 + 白名单边界。"""

from types import SimpleNamespace

import pytest

from meta.core.interceptors.line_guard_interceptor import (
    LineGuardError, LineGuardInterceptor,
)


def _context(object_type, action='crud_create'):
    return SimpleNamespace(meta_object=SimpleNamespace(id=object_type),
                           action=action)


def test_duplicate_line_no_rejected():
    interceptor = LineGuardInterceptor()
    payload = {'parent_id': 1, 'lines': [{'line_no': '10'}, {'line_no': '10'}]}
    with pytest.raises(LineGuardError):
        interceptor.validate_batch('service_request_line', 'parent_id', payload)


def test_distinct_line_no_accepted():
    interceptor = LineGuardInterceptor()
    payload = {'parent_id': 1,
               'lines': [{'line_no': '10'}, {'line_no': '20'},
                         {'line_no': None}]}
    interceptor.validate_batch('service_request_line', 'parent_id', payload)


def test_positive_qty_required_for_goods_line():
    interceptor = LineGuardInterceptor()
    with pytest.raises(LineGuardError):
        interceptor.validate_qty('service_request_line',
                                 {'line_type': 'goods', 'qty': 0})


def test_service_line_allows_blank_qty():
    LineGuardInterceptor().validate_qty(
        'service_request_line', {'line_type': 'service', 'qty': None})


def test_only_whitelisted_objects_execute():
    interceptor = LineGuardInterceptor()
    assert interceptor.should_execute(_context('service_request_line'))
    assert not interceptor.should_execute(_context('sales_order_line'))
    assert not interceptor.should_execute(
        _context('service_request_line', action='crud_delete'))
