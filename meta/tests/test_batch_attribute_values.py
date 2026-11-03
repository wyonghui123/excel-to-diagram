# -*- coding: utf-8 -*-
"""批次特性值 P4c 测试（spec §11.7）

覆盖:
  · YAML 声明：模板五值列 / 归属列 / 唯一索引。
  · BatchAttributeValueService：类型 ↔ 列对应、互斥单列、停用定义、租户边界、
    单值 / 多值 seq。
  · AttributeGuardInterceptor：batch_attribute_value 纳入受控对象，
    create/update 校验、delete 放行。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pathlib
import sqlite3
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

BASE_SCHEMA = """
CREATE TABLE attribute_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER DEFAULT 0,
    code TEXT,
    name TEXT,
    data_type TEXT DEFAULT 'string',
    multi_value_flag INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
);
CREATE TABLE batches (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_no TEXT);
CREATE TABLE batch_attribute_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL DEFAULT 0,
    batch_id INTEGER NOT NULL,
    attribute_id INTEGER NOT NULL,
    seq INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    value_text TEXT,
    value_number REAL,
    value_boolean INTEGER,
    value_date DATE,
    value_datetime DATETIME,
    created_at DATETIME
);
"""


class MemDS:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


def _build_db(definitions):
    conn = sqlite3.connect(':memory:')
    conn.executescript(BASE_SCHEMA)
    conn.execute("INSERT INTO batches (id, batch_no) VALUES (1, 'B001')")
    for row in definitions:
        conn.execute(
            'INSERT INTO attribute_definitions (id, tenant_id, code, name, '
            'data_type, multi_value_flag, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            row)
    return conn


def _service(conn):
    from meta.services.batch_attribute_value_service import BatchAttributeValueService
    return BatchAttributeValueService(MemDS(conn))


def _expect(service, data, rule):
    from meta.services.attribute_value_service import AttributeValueError
    with pytest.raises(AttributeValueError) as exc:
        service.validate_write(data)
    assert exc.value.rule == rule
    return exc.value


def _load_yaml(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


DEF_TEXT = (1, 0, 'COLOR', '颜色', 'string', 0, 'active')
DEF_NUMBER = (2, 0, 'WEIGHT', '重量', 'number', 0, 'active')
DEF_MULTI = (3, 0, 'TAG', '标签', 'string', 1, 'active')


# ---------------------------------------------------------------------------
# YAML 声明
# ---------------------------------------------------------------------------
def test_value_schema_matches_template_columns():
    doc = _load_yaml('batch_attribute_values.yaml')
    assert doc['table_name'].endswith('_attribute_values')

    columns = {f['db_column'] for f in doc['fields']}
    assert {'tenant_id', 'batch_id', 'attribute_id', 'seq', 'description',
            'value_text', 'value_number', 'value_boolean', 'value_date',
            'value_datetime'} <= columns

    unique = next(i for i in doc['indexes']
                  if i['name'] == 'uidx_batch_attr_value')
    assert unique['unique'] is True
    assert unique['fields'] == ['tenant_id', 'batch_id', 'attribute_id', 'seq']


# ---------------------------------------------------------------------------
# 值服务
# ---------------------------------------------------------------------------
def test_text_value_ok():
    conn = _build_db([DEF_TEXT])
    _service(conn).validate_write({
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 1,
        'value_text': '红色'})


def test_type_column_mismatch_rejected():
    conn = _build_db([DEF_TEXT])
    _expect(_service(conn), {
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 1,
        'value_number': 10}, 'attribute_value_type_mismatch')


def test_multiple_columns_rejected():
    conn = _build_db([DEF_TEXT])
    _expect(_service(conn), {
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 1,
        'value_text': '红色', 'value_date': '2026-11-03'},
        'attribute_value_column_count')


def test_no_value_column_rejected():
    conn = _build_db([DEF_TEXT])
    _expect(_service(conn), {
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 1},
        'attribute_value_column_count')


def test_inactive_definition_rejected():
    conn = _build_db([(1, 0, 'COLOR', '颜色', 'string', 0, 'inactive')])
    _expect(_service(conn), {
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 1,
        'value_text': '红色'}, 'attribute_not_active')


def test_tenant_private_cross_tenant_rejected():
    conn = _build_db([(1, 9, 'COLOR', '颜色', 'string', 0, 'active')])
    _expect(_service(conn), {
        'tenant_id': 2, 'batch_id': 1, 'attribute_id': 1,
        'value_text': '红色'}, 'attribute_tenant_mismatch')


def test_single_value_seq_must_be_one():
    conn = _build_db([DEF_TEXT])
    _expect(_service(conn), {
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 1, 'seq': 2,
        'value_text': '红色'}, 'attribute_seq_not_allowed')


def test_multi_value_allows_seq_above_one():
    conn = _build_db([DEF_MULTI])
    _service(conn).validate_write({
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 3, 'seq': 2,
        'value_text': '标签B'})


def test_seq_must_be_positive():
    conn = _build_db([DEF_MULTI])
    _expect(_service(conn), {
        'tenant_id': 0, 'batch_id': 1, 'attribute_id': 3, 'seq': 0,
        'value_text': '标签'}, 'attribute_seq_invalid')


def test_read_values_uses_batch_owner_field():
    conn = _build_db([DEF_NUMBER])
    conn.execute(
        'INSERT INTO batch_attribute_values (tenant_id, batch_id, attribute_id, '
        'seq, value_number) VALUES (0, 1, 2, 1, 12.5)')
    rows = _service(conn).read_values(0, 1)
    assert rows and rows[0]['owner_id'] == 1
    assert rows[0]['attribute_code'] == 'WEIGHT'


# ---------------------------------------------------------------------------
# 守卫拦截器
# ---------------------------------------------------------------------------
def _context(conn, action, params, old_data=None):
    from meta.core.action_context import ActionContext
    return ActionContext(
        meta_object=SimpleNamespace(id='batch_attribute_value'),
        action=action,
        params=params,
        data_source=MemDS(conn),
        old_data=old_data,
    )


def test_guard_guards_batch_value_writes():
    from meta.core.interceptors.attribute_guard_interceptor import (
        GUARDED_OBJECTS, _DELETE_GUARDED, AttributeGuardInterceptor,
    )
    assert 'batch_attribute_value' in GUARDED_OBJECTS
    assert 'batch_attribute_value' not in _DELETE_GUARDED

    conn = _build_db([DEF_TEXT])
    guard = AttributeGuardInterceptor()
    assert guard.should_execute(_context(
        conn, 'crud_create',
        {'batch_id': 1, 'attribute_id': 1, 'value_text': '红色'})) is True
    assert guard.should_execute(_context(
        conn, 'crud_update', {'attribute_id': 1})) is True
    assert guard.should_execute(_context(
        conn, 'crud_delete', {'id': 1})) is False


def test_guard_rejects_invalid_batch_value():
    from meta.core.exceptions import ValidationFailedError
    from meta.core.interceptors.attribute_guard_interceptor import (
        AttributeGuardInterceptor,
    )
    conn = _build_db([DEF_TEXT])
    guard = AttributeGuardInterceptor()
    context = _context(conn, 'crud_create', {
        'batch_id': 1, 'attribute_id': 1,
        'value_text': '红色', 'value_number': 3})
    with pytest.raises(ValidationFailedError) as exc:
        guard.before_action(context)
    assert exc.value.details[0]['rule'] == 'attribute_value_column_count'


def test_guard_allows_valid_batch_value():
    from meta.core.interceptors.attribute_guard_interceptor import (
        AttributeGuardInterceptor,
    )
    conn = _build_db([DEF_TEXT])
    guard = AttributeGuardInterceptor()
    guard.before_action(_context(conn, 'crud_create', {
        'batch_id': 1, 'attribute_id': 1, 'value_text': '红色'}))
