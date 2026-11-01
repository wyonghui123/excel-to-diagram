# -*- coding: utf-8 -*-
"""需求入口 M1 测试 —— 提交取号、免审批直落、行级必填与 schema 口径。

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §2 M1
  docs/specs/spec-shared-service-center-object-model-2026-10-31.md §3.2 / S-D5
  docs/specs/spec-procurement-task-object-model-2026-10-31.md T1 / T-D13 / T-D13a

测试策略:
  · schema 断言读真实 YAML（口径漂移立即失败）
  · 服务 / 拦截器用内存 SQLite 真 SQL（取号与免审批都依赖真查询）
"""

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.demand_entry_guard_interceptor import (
    DemandEntryGuardInterceptor,
)
from meta.core.interceptors.document_type_guard_interceptor import (
    DocumentTypeGuardInterceptor,
)
from meta.services.demand_entry_service import DemandEntryService

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'

_SCHEMA = """
CREATE TABLE orgs (id INTEGER PRIMARY KEY, code TEXT);
CREATE TABLE service_catalog_items (
    id INTEGER PRIMARY KEY,
    code TEXT,
    status TEXT,
    requires_approval INTEGER DEFAULT 0,
    approval_policy TEXT
);
CREATE TABLE service_requests (
    id INTEGER PRIMARY KEY,
    request_no TEXT UNIQUE,
    title TEXT,
    status TEXT,
    requester_org_id INTEGER,
    provider_org_id INTEGER
);
CREATE TABLE service_request_lines (
    id INTEGER PRIMARY KEY,
    request_id INTEGER,
    line_no INTEGER,
    line_type TEXT,
    catalog_item_id INTEGER,
    item_id INTEGER,
    qty REAL,
    status TEXT
);
CREATE TABLE requisitions (
    id INTEGER PRIMARY KEY,
    requisition_no TEXT UNIQUE,
    document_type_id INTEGER,
    status TEXT,
    requester_org_id INTEGER,
    deliver_to_org_id INTEGER
);
CREATE TABLE type_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    scope_bo TEXT,
    level TEXT,
    status TEXT
);
INSERT INTO type_definitions (id, code, name, scope_bo, level, status)
VALUES (1, 'STD', '标准采购申请', 'requisition', 'header', 'active');
"""


class _MemDS:
    """sqlite3 连接 → DataSource 形状（query / execute）。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    connection.executescript(_SCHEMA)
    yield connection
    connection.close()


@pytest.fixture
def ds(conn):
    return _MemDS(conn)


def _ctx(ds, object_type, action, params, original=None):
    meta_object = SimpleNamespace(id=object_type)
    return SimpleNamespace(
        meta_object=meta_object,
        action=action,
        params=params,
        data_source=ds,
        old_data=original or {},
        extra={},
    )


# ---------------- schema 口径 ----------------------------


def _load(name):
    return yaml.safe_load((_SCHEMA_DIR / name).read_text(encoding='utf-8'))


def test_schema_files_exist():
    for name in ('service_catalog_item.yaml', 'service_request.yaml',
                 'service_request_line.yaml', 'requisition.yaml',
                 'requisition_line.yaml'):
        assert (_SCHEMA_DIR / name).exists(), name


def test_requisition_has_no_type_field():
    """T-D13a：不设 requisition_type；单据类型改由平台切面提供（T-D20）。"""
    schema = _load('requisition.yaml')
    field_ids = {f['id'] for f in schema['fields']}
    assert 'requisition_type' not in field_ids
    # 平台层：字段不在单据 YAML 里重复声明，而是引用切面
    assert 'document_type_id' not in field_ids
    assert 'document_type_aspect' in schema['aspects']


def test_requisition_document_type_scope_filter():
    """单据类型引用必须限定 scope_bo=<本单据> + level=header（切面按对象注入）。"""
    from meta.core.yaml_loader import _resolve_aspects
    schemas = _load('aspects.yaml')
    merged = _resolve_aspects(_load('requisition.yaml'), schemas)
    doc_type = next(f for f in merged['fields'] if f['id'] == 'document_type_id')
    value_filter = doc_type['value_help']['source']['value_filter']
    assert value_filter['scope_bo'] == 'requisition'
    assert value_filter['level'] == 'header'
    assert value_filter['status'] == 'active'


def test_requisition_line_qty_required():
    """T-D13：承诺型 qty 必填。"""
    schema = _load('requisition_line.yaml')
    qty = next(f for f in schema['fields'] if f['id'] == 'qty')
    assert qty.get('required') is True


def test_service_request_line_qty_nullable():
    """事件型 qty 可空。"""
    schema = _load('service_request_line.yaml')
    qty = next(f for f in schema['fields'] if f['id'] == 'qty')
    assert qty.get('nullable') is True
    assert qty.get('required') is not True


def test_service_request_double_org_required():
    schema = _load('service_request.yaml')
    fields = {f['id']: f for f in schema['fields']}
    assert fields['requester_org_id']['required'] is True
    assert fields['provider_org_id']['required'] is True


def test_service_request_state_machine():
    schema = _load('service_request.yaml')
    rules = {r['id']: r for r in schema['rules']}
    assert rules['submit_service_request']['from_states'] == ['draft']
    assert rules['submit_service_request']['to_state'] == 'submitted'
    assert rules['approve_service_request']['from_states'] == ['submitted']
    assert rules['approve_service_request']['to_state'] == 'approved'
    assert set(rules['cancel_service_request']['from_states']) == {
        'draft', 'submitted', 'approved'}
    assert rules['cancel_service_request']['to_state'] == 'cancelled'


def test_requisition_state_machine():
    schema = _load('requisition.yaml')
    rules = {r['id']: r for r in schema['rules']}
    assert rules['submit_requisition']['to_state'] == 'submitted'
    assert rules['approve_requisition']['to_state'] == 'approved'
    assert rules['cancel_requisition']['to_state'] == 'cancelled'


def test_catalog_approval_fields():
    schema = _load('service_catalog_item.yaml')
    fields = {f['id']: f for f in schema['fields']}
    assert fields['requires_approval']['default'] is False
    assert fields['approval_policy']['nullable'] is True


# ---------------- 取号 ----------------------------


def test_document_no_increments(conn, ds):
    service = DemandEntryService(ds)
    first = service.allocate_document_no('service_request', {})
    conn.execute(
        'INSERT INTO service_requests (id, request_no, status) VALUES (1, ?, ?)',
        [first, 'submitted'])
    second = service.allocate_document_no('service_request', {})
    assert first.endswith('-000001')
    assert second.endswith('-000002')
    assert first.startswith('SR-')
    assert second.startswith('SR-')


def test_document_no_not_overwritten(conn, ds):
    service = DemandEntryService(ds)
    assert service.allocate_document_no('service_request', {'request_no': 'MANUAL'}) is None
    assert service.allocate_document_no('requisition', {'requisition_no': 'MANUAL'}) is None


# ---------------- 免审批 ----------------------------


def test_submit_without_approval_policy_is_auto_approved(conn, ds):
    conn.execute(
        "INSERT INTO service_catalog_items (id, code, status, requires_approval, approval_policy) "
        "VALUES (1, 'C1', 'active', 0, NULL)")
    conn.execute(
        "INSERT INTO service_request_lines (id, request_id, line_no, line_type, catalog_item_id, status) "
        "VALUES (1, 10, 1, 'service', 1, 'open')")
    conn.execute(
        "INSERT INTO service_requests (id, title, status, requester_org_id, provider_org_id) "
        "VALUES (10, '搬工位', 'draft', 1, 2)")

    ctx = _ctx(ds, 'service_request', 'crud_update', {'id': 10, 'status': 'submitted'},
               original={'id': 10, 'status': 'draft'})
    DemandEntryGuardInterceptor().before_action(ctx)

    assert ctx.params['status'] == 'approved'
    assert ctx.params['request_no'].startswith('SR-')


def test_submit_with_requires_approval_stays_submitted(conn, ds):
    conn.execute(
        "INSERT INTO service_catalog_items (id, code, status, requires_approval, approval_policy) "
        "VALUES (1, 'C1', 'active', 1, NULL)")
    conn.execute(
        "INSERT INTO service_request_lines (id, request_id, line_no, line_type, catalog_item_id, status) "
        "VALUES (1, 10, 1, 'service', 1, 'open')")
    conn.execute(
        "INSERT INTO service_requests (id, title, status, requester_org_id, provider_org_id) "
        "VALUES (10, '搬工位', 'draft', 1, 2)")

    ctx = _ctx(ds, 'service_request', 'crud_update', {'id': 10, 'status': 'submitted'},
               original={'id': 10, 'status': 'draft'})
    DemandEntryGuardInterceptor().before_action(ctx)

    assert ctx.params['status'] == 'submitted'
    assert ctx.params['request_no'].startswith('SR-')


def test_submit_with_non_empty_policy_stays_submitted(conn, ds):
    conn.execute(
        "INSERT INTO service_catalog_items (id, code, status, requires_approval, approval_policy) "
        "VALUES (1, 'C1', 'active', 0, '{\"approver\":\"org_manager\"}')")
    conn.execute(
        "INSERT INTO service_request_lines (id, request_id, line_no, line_type, catalog_item_id, status) "
        "VALUES (1, 10, 1, 'service', 1, 'open')")
    conn.execute(
        "INSERT INTO service_requests (id, title, status, requester_org_id, provider_org_id) "
        "VALUES (10, '搬工位', 'draft', 1, 2)")

    ctx = _ctx(ds, 'service_request', 'crud_update', {'id': 10, 'status': 'submitted'},
               original={'id': 10, 'status': 'draft'})
    DemandEntryGuardInterceptor().before_action(ctx)

    assert ctx.params['status'] == 'submitted'


def test_requisition_submit_is_auto_approved(conn, ds):
    conn.execute(
        "INSERT INTO requisitions (id, status, requester_org_id, deliver_to_org_id) "
        "VALUES (20, 'draft', 1, 2)")
    ctx = _ctx(ds, 'requisition', 'crud_update', {'id': 20, 'status': 'submitted'},
               original={'id': 20, 'status': 'draft'})
    DemandEntryGuardInterceptor().before_action(ctx)

    assert ctx.params['status'] == 'approved'
    assert ctx.params['requisition_no'].startswith('RQ-')


def test_cancel_is_not_touched(conn, ds):
    conn.execute(
        "INSERT INTO service_requests (id, title, status, requester_org_id, provider_org_id) "
        "VALUES (10, '搬工位', 'approved', 1, 2)")
    ctx = _ctx(ds, 'service_request', 'crud_update', {'id': 10, 'status': 'cancelled'},
               original={'id': 10, 'status': 'approved'})
    DemandEntryGuardInterceptor().before_action(ctx)

    assert 'request_no' not in ctx.params
    assert ctx.params['status'] == 'cancelled'


# ---------------- 行级必填 ----------------------------


def test_service_line_requires_catalog_item(conn, ds):
    ctx = _ctx(ds, 'service_request_line', 'crud_create',
               {'request_id': 10, 'line_no': 1, 'line_type': 'service'})
    with pytest.raises(ValidationFailedError):
        DemandEntryGuardInterceptor().before_action(ctx)


def test_goods_line_requires_item_and_qty(conn, ds):
    ctx = _ctx(ds, 'service_request_line', 'crud_create',
               {'request_id': 10, 'line_no': 1, 'line_type': 'goods',
                'item_id': 1, 'qty': 0})
    with pytest.raises(ValidationFailedError):
        DemandEntryGuardInterceptor().before_action(ctx)


def test_valid_service_line_passes(conn, ds):
    ctx = _ctx(ds, 'service_request_line', 'crud_create',
               {'request_id': 10, 'line_no': 1, 'line_type': 'service',
                'catalog_item_id': 1})
    DemandEntryGuardInterceptor().before_action(ctx)


def test_create_allocates_document_no(conn, ds):
    """业务键在 ActionExecutor 内要求非空 ⇒ 创建即取号。"""
    request_ctx = _ctx(ds, 'service_request', 'crud_create', {'title': '搬工位'})
    DemandEntryGuardInterceptor().before_action(request_ctx)
    assert request_ctx.params['request_no'].startswith('SR-')

    requisition_ctx = _ctx(ds, 'requisition', 'crud_create',
                           {'document_type_id': 1,
                            'requester_org_id': 1, 'deliver_to_org_id': 2})
    DemandEntryGuardInterceptor().before_action(requisition_ctx)
    assert requisition_ctx.params['requisition_no'].startswith('RQ-')


# ---------------- 单据类型规范 ----------------------------


def test_requisition_create_requires_document_type(conn, ds):
    ctx = _ctx(ds, 'requisition', 'crud_create',
               {'requester_org_id': 1, 'deliver_to_org_id': 2})
    with pytest.raises(ValidationFailedError) as exc:
        DocumentTypeGuardInterceptor().before_action(ctx)
    assert '单据类型' in str(exc.value)


def test_requisition_document_type_scope_validated(conn, ds):
    conn.execute(
        "INSERT INTO type_definitions (id, code, name, scope_bo, level, status) "
        "VALUES (2, 'SO_STD', '销售订单类型', 'sales_order', 'header', 'active')")
    ctx = _ctx(ds, 'requisition', 'crud_create',
               {'document_type_id': 2,
                'requester_org_id': 1, 'deliver_to_org_id': 2})
    with pytest.raises(ValidationFailedError) as exc:
        DocumentTypeGuardInterceptor().before_action(ctx)
    assert '不属于采购申请' in str(exc.value)


def test_requisition_document_type_frozen_after_draft(conn, ds):
    ctx = _ctx(ds, 'requisition', 'crud_update',
               {'id': 20, 'document_type_id': 1},
               original={'id': 20, 'status': 'approved', 'document_type_id': 3})
    with pytest.raises(ValidationFailedError) as exc:
        DocumentTypeGuardInterceptor().before_action(ctx)
    assert '离开草稿后不可修改' in str(exc.value)


# ---------------- 真实链路（SchemaGenerator 建表 + BOFramework 持久化） ----------------
#
# 单元用例用 SimpleNamespace 模拟 ActionContext，无法暴露「字段名/生命周期」类缺陷
# （曾用 original_data 访问真实 ActionContext 上不存在的属性）。本节用真实
# BOFramework + PersistenceInterceptor 跑一遍创建 → 提交，验证守卫与落库对齐。


def _ensure_registry():
    from meta.core.models import registry
    if registry.get('service_request') is None:
        registry.reload(str(_SCHEMA_DIR))


@pytest.fixture
def real_framework(tmp_path):
    _ensure_registry()
    from meta.core.bo_framework import BOFramework
    from meta.core.datasource import get_data_source
    from meta.core.db_config_detector import detect_runtime_config
    from meta.core.models import registry
    from meta.core.interceptors.persistence_interceptor import (
        PersistenceInterceptor,
    )
    from meta.core.schema_generator import SchemaGenerator

    db_path = tmp_path / 'm1_pipeline.db'
    connection = sqlite3.connect(str(db_path))
    # v168 的 5 张业务表带真外键，SQLite 要求父表存在（父键须 PK/UNIQUE）；
    # 这里只建最小父表，避免依赖 create_app 全量初始化与仓库 DB。
    connection.executescript(
        'CREATE TABLE IF NOT EXISTS orgs (id INTEGER PRIMARY KEY);'
        'CREATE TABLE IF NOT EXISTS party_internal (id INTEGER PRIMARY KEY);'
        'CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY);'
        'CREATE TABLE IF NOT EXISTS uoms (id INTEGER PRIMARY KEY);'
        'CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY);'
        'CREATE TABLE IF NOT EXISTS number_sequences (id INTEGER PRIMARY KEY);'
        'INSERT INTO orgs (id) VALUES (1),(2);'
        'INSERT INTO items (id) VALUES (1);'
    )
    generator = SchemaGenerator('sqlite')
    # 单据类型父表（requisition.document_type_id 真外键），并种一条默认类型
    type_meta = registry.get('type_definition')
    assert type_meta is not None, 'type_definition 未注册'
    connection.execute(generator.generate_create_table(type_meta))
    for index_sql in generator.generate_create_index(type_meta):
        connection.execute(index_sql)
    connection.execute(
        "INSERT INTO type_definitions "
        "(id, code, name, scope_bo, level, document_category, status) "
        "VALUES (1, 'STD', '标准采购申请', 'requisition', 'header', 'standard', 'active'), "
        "       (2, 'STD', '标准服务请求', 'service_request', 'header', 'standard', 'active')")
    for name in ('service_catalog_item', 'service_request',
                 'service_request_line', 'requisition', 'requisition_line'):
        meta_object = registry.get(name)
        assert meta_object is not None, f'{name} 未注册'
        connection.execute(generator.generate_create_table(meta_object))
        for index_sql in generator.generate_create_index(meta_object):
            connection.execute(index_sql)
    connection.commit()
    connection.close()

    # 动作执行器要求运行时 DB 配置已探测（服务启动期的同一前置）
    detect_runtime_config(str(db_path))
    data_source = get_data_source('sqlite', database=str(db_path))
    framework = BOFramework(data_source=data_source)
    framework.register_interceptor(DemandEntryGuardInterceptor())
    framework.register_interceptor(DocumentTypeGuardInterceptor())
    framework.register_interceptor(PersistenceInterceptor())
    framework.set_user_context(user_id=1, user_name='admin')
    yield framework, data_source
    data_source.disconnect()


def _only_row(data_source, table, **where):
    condition = ' AND '.join(f'{key} = ?' for key in where)
    rows = data_source.query(
        f'SELECT * FROM {table} WHERE {condition}', list(where.values()))
    assert len(rows) == 1, f'{table} 期望 1 行，实际 {len(rows)} 行'
    return rows[0]


def test_real_chain_submit_without_policy_auto_approves(real_framework):
    framework, data_source = real_framework
    catalog = framework.create(
        'service_catalog_item', {'code': 'M1CAT', 'name': '搬工位'})
    assert catalog.success, catalog.message
    catalog_row = _only_row(data_source, 'service_catalog_items', code='M1CAT')

    request = framework.create('service_request', {
        'document_type_id': 2,
        'title': '搬工位', 'requester_org_id': 1, 'provider_org_id': 2})
    assert request.success, request.message
    request_row = _only_row(data_source, 'service_requests', title='搬工位')

    line = framework.create('service_request_line', {
        'request_id': request_row['id'], 'line_no': '10', 'line_type': 'service',
        'catalog_item_id': catalog_row['id']})
    assert line.success, line.message

    submit = framework.update(
        'service_request', request_row['id'], {'status': 'submitted'})
    assert submit.success, submit.message

    final = _only_row(data_source, 'service_requests', id=request_row['id'])
    assert final['status'] == 'approved'
    assert (final['request_no'] or '').startswith('SR-')


def test_real_chain_submit_with_policy_stays_submitted(real_framework):
    framework, data_source = real_framework
    catalog = framework.create('service_catalog_item', {
        'code': 'M1CATAP', 'name': '设备维修', 'requires_approval': True})
    assert catalog.success, catalog.message
    catalog_row = _only_row(data_source, 'service_catalog_items', code='M1CATAP')

    request = framework.create('service_request', {
        'document_type_id': 2,
        'title': '设备维修', 'requester_org_id': 1, 'provider_org_id': 2})
    assert request.success, request.message
    request_row = _only_row(data_source, 'service_requests', title='设备维修')

    framework.create('service_request_line', {
        'request_id': request_row['id'], 'line_no': '10', 'line_type': 'service',
        'catalog_item_id': catalog_row['id']})

    submit = framework.update(
        'service_request', request_row['id'], {'status': 'submitted'})
    assert submit.success, submit.message

    final = _only_row(data_source, 'service_requests', id=request_row['id'])
    assert final['status'] == 'submitted'
    assert (final['request_no'] or '').startswith('SR-')


def test_real_chain_requisition_submit_auto_approves(real_framework):
    framework, data_source = real_framework
    requisition = framework.create('requisition', {
        'document_type_id': 1,
        'requester_org_id': 1, 'deliver_to_org_id': 2, 'need_date': '2026-11-10'})
    assert requisition.success, requisition.message
    row = _only_row(data_source, 'requisitions', deliver_to_org_id=2)

    framework.create('requisition_line', {
        'requisition_id': row['id'], 'line_no': '10', 'item_id': 1, 'qty': 5})

    submit = framework.update('requisition', row['id'], {'status': 'submitted'})
    assert submit.success, submit.message

    final = _only_row(data_source, 'requisitions', id=row['id'])
    assert final['status'] == 'approved'
    assert (final['requisition_no'] or '').startswith('RQ-')


def test_real_chain_service_line_without_catalog_rejected(real_framework):
    framework, data_source = real_framework
    request = framework.create('service_request', {
        'document_type_id': 2,
        'title': '无目录行', 'requester_org_id': 1, 'provider_org_id': 2})
    assert request.success, request.message
    request_row = _only_row(data_source, 'service_requests', title='无目录行')

    rejected = framework.create('service_request_line', {
        'request_id': request_row['id'], 'line_no': '10', 'line_type': 'service'})
    assert rejected.success is False
    assert '目录项' in rejected.message
