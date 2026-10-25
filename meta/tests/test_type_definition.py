# -*- coding: utf-8 -*-
"""类型字典（type_definition）测试

依据: docs/superpowers/specs/2026-10-25-type-definition-generalization-spec.md
      meta/schemas/type_definition.yaml 头注释「层级与字段适用」

覆盖:
  A. YAML / 视图面（T2）
  B. DDL 投影与复合唯一索引（T1）
  C. 服务层不变量 I1–I4 / I6（T5.3 / T5.4）
  D. 设计期校验 I1–I3 的形状检查（T5.1）
  E. 拦截器接线与缓存失效（T5）
  F. 迁移 v110 幂等与数据映射（T3）
"""

import importlib.util
import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.unit

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')
_MIGRATION_PATH = os.path.join(_META_DIR, 'migrations',
                               'v110__type_definitions.py')

_TYPE_DEF_YAML = os.path.join(_SCHEMA_DIR, 'type_definition.yaml')
_NUMBER_SEQ_YAML = os.path.join(_SCHEMA_DIR, 'number_sequence.yaml')
_DOC_VIEW_YAML = os.path.join(_SCHEMA_DIR, 'document_type.yaml')
_LINE_VIEW_YAML = os.path.join(_SCHEMA_DIR, 'line_type.yaml')


def _raw(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _td_obj():
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml
    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    return load_yaml_file(_TYPE_DEF_YAML, aspects_defs=aspects)


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    """只实现守卫的 `SELECT * FROM type_definitions WHERE id = ?` 形态。"""

    def __init__(self, rows=None, raise_on_query=False):
        self.rows = rows or {}          # id -> 行
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        p = list(params or [])
        if 'FROM type_definitions WHERE id' in sql:
            row = self.rows.get(p[0])
            return [row] if row else []
        return []


def _svc(rows=None, raise_on_query=False):
    from meta.services.type_definition_guard_service import (
        TypeDefinitionGuardService,
    )
    return TypeDefinitionGuardService(_FakeDS(rows, raise_on_query))


def _header(**overrides):
    data = {
        'code': 'TA',
        'name': '标准销售订单',
        'scope_bo': 'sales_order',
        'level': 'header',
        'document_category': 'standard',
    }
    data.update(overrides)
    return data


def _line(**overrides):
    data = {
        'code': 'STD',
        'name': '标准物料行',
        'scope_bo': 'sales_order',
        'level': 'line',
        'line_category': 'material',
    }
    data.update(overrides)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# A. YAML / 视图面
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaFace:
    def test_object_identity(self):
        d = _raw(_TYPE_DEF_YAML)
        assert d['id'] == 'type_definition'
        assert d['table_name'] == 'type_definitions'
        assert d['semantics']['business_key'] == ['scope_bo', 'level', 'code']

    def test_compound_unique_index(self):
        indexes = _raw(_TYPE_DEF_YAML)['indexes']
        hits = [i for i in indexes
                if i.get('name') == 'idx_type_definition_scope_code']
        assert len(hits) == 1
        assert hits[0]['fields'] == ['scope_bo', 'level', 'code']
        assert hits[0]['unique'] is True

    def test_code_not_globally_unique(self):
        fields = {f['id']: f for f in _raw(_TYPE_DEF_YAML)['fields']}
        assert fields['code'].get('unique') is not True

    def test_scope_bo_and_level_immutable(self):
        fields = {f['id']: f for f in _raw(_TYPE_DEF_YAML)['fields']}
        assert fields['scope_bo']['semantics']['immutable'] is True
        assert fields['level']['semantics']['immutable'] is True
        assert {v['value'] for v in fields['level']['enum_values']} == {
            'header', 'line'}

    def test_level_only_fields_nullable(self):
        fields = {f['id']: f for f in _raw(_TYPE_DEF_YAML)['fields']}
        for fid in ('document_category', 'default_type_id',
                    'number_sequence_id', 'line_category'):
            assert fields[fid].get('required') is not True, fid

    def test_deletion_policy_covers_old_references(self):
        restrict = _raw(_TYPE_DEF_YAML)['deletion_policy']['restrict_on']
        pairs = {(r['table'], r['foreign_key']) for r in restrict}
        assert ('control_parameter_values', 'line_type_id') in pairs
        assert ('control_parameter_values', 'document_type_id') in pairs
        assert ('line_type_assignments', 'line_type_id') in pairs
        assert ('line_type_assignments', 'document_type_id') in pairs
        assert ('type_definitions', 'default_type_id') in pairs

    @pytest.mark.parametrize('path,predicate', [
        (_DOC_VIEW_YAML, "level = 'header'"),
        (_LINE_VIEW_YAML, "level = 'line'"),
    ])
    def test_slice_views_are_readonly(self, path, predicate):
        d = _raw(path)
        assert d['object_type'] == 'view'
        assert d['import_export']['auto_crud'] is False
        assert 'scope_bo' not in d['view_definition']
        assert predicate in d['view_definition']
        action_ids = {a['id'] for a in d.get('actions') or []}
        assert all(a.endswith('_read') or a.endswith('_list')
                   for a in action_ids)

    def test_document_view_keeps_legacy_columns(self):
        sql = _raw(_DOC_VIEW_YAML)['view_definition']
        assert 'document_category AS category' in sql
        assert 'default_type_id AS default_line_type_id' in sql


# ─────────────────────────────────────────────────────────────────────────────
# B. DDL 投影与视图
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def type_db(tmp_path):
    from meta.core.datasource import (
        _clear_data_source_cache_for_testing, get_data_source,
    )
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml

    aspects = parse_aspects_yaml(_SCHEMA_DIR)
    objs = [
        load_yaml_file(p, aspects_defs=aspects)
        for p in (_NUMBER_SEQ_YAML, _TYPE_DEF_YAML,
                  _DOC_VIEW_YAML, _LINE_VIEW_YAML)
    ]
    assert all(o is not None for o in objs)

    ds = get_data_source('sqlite', database=str(tmp_path / 'type_definition.db'))
    sync_schema_from_meta(ds, objs)   # 表先于视图
    yield ds
    _clear_data_source_cache_for_testing()


class TestPhysicalSchema:
    def test_columns(self, type_db):
        cols = [c[1] for c in type_db.execute(
            'PRAGMA table_info(type_definitions)').fetchall()]
        for expected in ('id', 'code', 'name', 'scope_bo', 'level',
                         'document_category', 'default_type_id',
                         'number_sequence_id', 'line_category', 'status',
                         'description', 'created_at', 'created_by', 'updated_by'):
            assert expected in cols, '缺失列 %s' % expected

    def test_unique_index_enforced(self, type_db):
        from meta.tests.factories._raw_sql_bridge import insert
        row = {'name': '标准订单', 'scope_bo': 'sales_order', 'level': 'header',
               'document_category': 'standard', 'status': 'active'}
        insert(type_db, 'type_definitions', code='TA', **row)
        with pytest.raises(Exception):
            insert(type_db, 'type_definitions', code='TA',
                   **dict(row, name='重复编码'))

    def test_same_code_allowed_across_levels(self, type_db):
        from meta.tests.factories._raw_sql_bridge import insert
        insert(type_db, 'type_definitions', code='TA', name='标准订单',
               scope_bo='sales_order', level='header',
               document_category='standard', status='active')
        insert(type_db, 'type_definitions', code='TA', name='同一编码的行类型',
               scope_bo='sales_order', level='line',
               line_category='material', status='active')

    def test_views_slice_by_level(self, type_db):
        from meta.tests.factories._raw_sql_bridge import insert
        insert(type_db, 'type_definitions', id=101, code='STD', name='标准物料行',
               scope_bo='sales_order', level='line',
               line_category='material', status='active')
        # 自引用 FK 为立即约束：被指向的行必须先存在
        insert(type_db, 'type_definitions', id=1, code='TA', name='标准订单',
               scope_bo='sales_order', level='header',
               document_category='standard', default_type_id=101,
               status='active')

        headers = type_db.query('SELECT * FROM document_types')
        lines = type_db.query('SELECT * FROM line_types')
        assert len(headers) == 1 and len(lines) == 1
        assert headers[0]['category'] == 'standard'
        assert headers[0]['default_line_type_id'] == 101
        assert lines[0]['category'] == 'material'


# ─────────────────────────────────────────────────────────────────────────────
# C. 服务层不变量
# ─────────────────────────────────────────────────────────────────────────────

class TestInvariants:
    def test_header_requires_document_category(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc().validate_write(_header(document_category=None))
        assert '单据类别' in str(ei.value)

    def test_line_rejects_document_category(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc().validate_write(_line(document_category='standard'))
        assert ei.value.field_name == 'document_category'

    def test_line_requires_line_category(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc().validate_write(_line(line_category=None))
        assert '行类别' in str(ei.value)

    def test_header_rejects_line_category(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        with pytest.raises(TypeDefinitionGuardError):
            _svc().validate_write(_header(line_category='material'))

    def test_line_rejects_header_only_refs(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc().validate_write(_line(number_sequence_id=1))
        assert ei.value.field_name == 'number_sequence_id'
        with pytest.raises(TypeDefinitionGuardError) as ei2:
            _svc().validate_write(_line(default_type_id=101))
        assert ei2.value.field_name == 'default_type_id'

    def test_default_type_must_share_scope(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        rows = {101: {'id': 101, 'scope_bo': 'purchase_order', 'level': 'line'}}
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc(rows).validate_write(_header(default_type_id=101))
        assert ei.value.rule == 'default_type_scope_mismatch'

    def test_default_type_must_be_line(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        rows = {2: {'id': 2, 'scope_bo': 'sales_order', 'level': 'header'}}
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc(rows).validate_write(_header(default_type_id=2))
        assert ei.value.rule == 'default_type_level_mismatch'

    def test_default_type_ok_when_same_scope_line(self):
        rows = {101: {'id': 101, 'scope_bo': 'sales_order', 'level': 'line'}}
        _svc(rows).validate_write(_header(default_type_id=101))

    def test_scope_and_level_immutable_on_update(self):
        from meta.services.type_definition_guard_service import (
            TypeDefinitionGuardError,
        )
        old = {'id': 1, 'scope_bo': 'sales_order', 'level': 'header'}
        with pytest.raises(TypeDefinitionGuardError) as ei:
            _svc({1: old}).validate_write(
                _header(scope_bo='purchase_order'), exclude_id=1)
        assert ei.value.field_name == 'scope_bo'
        with pytest.raises(TypeDefinitionGuardError) as ei2:
            _svc({1: old}).validate_write(_header(level='line'), exclude_id=1)
        assert ei2.value.field_name == 'level'

    def test_unknown_scope_bo_only_warns(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            _svc().validate_write(_header(scope_bo='not_registered_bo'))
        assert any('未注册为业务对象' in r.message for r in caplog.records)

    def test_query_failure_fails_open(self):
        # 旧行读不到 → I6 跳过；默认行类型读不到 → I4 跳过（外键兜底）
        _svc(raise_on_query=True).validate_write(
            _header(default_type_id=999), exclude_id=1)


# ─────────────────────────────────────────────────────────────────────────────
# D. 设计期校验
# ─────────────────────────────────────────────────────────────────────────────

class TestDesignTimeValidation:
    def test_valid_schema_has_no_errors(self):
        from meta.core.metadata_validator import MetadataValidator, ValidationReport
        report = ValidationReport()
        MetadataValidator()._validate_type_definition(_td_obj(), report)
        assert not report.errors, report.errors

    def test_required_level_only_field_is_error(self):
        from meta.core.metadata_validator import MetadataValidator, ValidationReport
        obj = _td_obj()
        next(f for f in obj.fields if f.id == 'document_category').required = True
        report = ValidationReport()
        MetadataValidator()._validate_type_definition(obj, report)
        assert any(r.field_id == 'document_category' for r in report.errors)

    def test_missing_immutable_is_warning(self):
        from meta.core.metadata_validator import MetadataValidator, ValidationReport
        obj = _td_obj()
        next(f for f in obj.fields if f.id == 'level').semantics.immutable = False
        report = ValidationReport()
        MetadataValidator()._validate_type_definition(obj, report)
        assert any(r.field_id == 'level' for r in report.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# E. 拦截器
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(object_id='type_definition', action='crud_create', params=None,
         old_data=None, record_id=None):
    meta_object = SimpleNamespace(id=object_id, fields=[])
    return SimpleNamespace(
        meta_object=meta_object,
        action=action,
        params=params or {},
        old_data=old_data,
        object_id=record_id,
        data_source=_FakeDS(),
    )


class TestInterceptor:
    def test_priority(self):
        from meta.core.interceptors.type_definition_guard_interceptor import (
            TypeDefinitionGuardInterceptor,
        )
        assert TypeDefinitionGuardInterceptor().priority == 47

    def test_should_execute_scope(self):
        from meta.core.interceptors.type_definition_guard_interceptor import (
            TypeDefinitionGuardInterceptor,
        )
        ic = TypeDefinitionGuardInterceptor()
        assert ic.should_execute(_ctx(action='crud_create'))
        assert ic.should_execute(_ctx(action='crud_update'))
        # D1：删除前必须检查引用，否则会静默留下悬空引用
        assert ic.should_execute(_ctx(action='crud_delete'))
        assert not ic.should_execute(_ctx(object_id='line_type'))

    def test_before_action_raises_validation_error(self):
        from meta.core.exceptions import ValidationFailedError
        from meta.core.interceptors.type_definition_guard_interceptor import (
            TypeDefinitionGuardInterceptor,
        )
        with pytest.raises(ValidationFailedError):
            TypeDefinitionGuardInterceptor().before_action(
                _ctx(params=_line(document_category='standard')))

    def test_before_action_accepts_valid_line(self):
        from meta.core.interceptors.type_definition_guard_interceptor import (
            TypeDefinitionGuardInterceptor,
        )
        TypeDefinitionGuardInterceptor().before_action(_ctx(params=_line()))

    def test_after_action_invalidates_resolver(self, monkeypatch):
        from meta.core.interceptors.type_definition_guard_interceptor import (
            TypeDefinitionGuardInterceptor,
        )
        import meta.services.line_type_service as lts

        calls = []

        class _R:
            def invalidate(self):
                calls.append(True)

        monkeypatch.setattr(lts, 'get_line_type_resolver', lambda: _R())
        TypeDefinitionGuardInterceptor().after_action(_ctx(params=_line()))
        assert calls == [True]


# ─────────────────────────────────────────────────────────────────────────────
# F. 迁移 v110
# ─────────────────────────────────────────────────────────────────────────────

def _load_migration():
    spec = importlib.util.spec_from_file_location('v110_type_definitions',
                                                  _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_NAMING_MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', 'v114__type_definition_naming.py')


def _load_naming_migration():
    spec = importlib.util.spec_from_file_location('v114_type_definition_naming',
                                                  _NAMING_MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_old_tables(db_path):
    from meta.tests.factories._raw_sql_bridge import insert

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sales_line_types (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "code VARCHAR(200) UNIQUE NOT NULL, name VARCHAR(200) NOT NULL, "
        "category VARCHAR(200) NOT NULL DEFAULT 'material', "
        "status VARCHAR(200) NOT NULL DEFAULT 'active', description TEXT, "
        "created_at DATETIME)")
    conn.execute(
        "CREATE TABLE sales_document_types (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "code VARCHAR(200) UNIQUE NOT NULL, name VARCHAR(200) NOT NULL, "
        "category VARCHAR(200) NOT NULL DEFAULT 'standard', "
        "default_line_type_id INTEGER, number_sequence_id INTEGER, "
        "status VARCHAR(200) NOT NULL DEFAULT 'active', description TEXT, "
        "created_at DATETIME)")
    for i, code in enumerate(('STD', 'SVC', 'RET', 'FOC', 'TXT'), start=1):
        insert(conn, 'sales_line_types', id=i, code=code, name=code,
               category='material')
    insert(conn, 'sales_document_types', id=1, code='TA', name='标准订单',
           category='standard', default_line_type_id=1)
    insert(conn, 'sales_document_types', id=2, code='RE', name='退货订单',
           category='return', default_line_type_id=3)

    # 引用旧表的两张子表（物理外键指向旧表名），各留一行存量
    conn.execute(
        "CREATE TABLE sales_line_type_assignments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "sales_document_type_id INTEGER NOT NULL, item_group_id INTEGER, "
        "specificity_rank INTEGER NOT NULL DEFAULT 100, "
        "sales_line_type_id INTEGER NOT NULL, "
        "status VARCHAR(200) NOT NULL DEFAULT 'active', description TEXT, "
        "created_at DATETIME, "
        "FOREIGN KEY (sales_document_type_id) REFERENCES sales_document_types(id), "
        "FOREIGN KEY (sales_line_type_id) REFERENCES sales_line_types(id))")
    conn.execute(
        "CREATE TABLE control_parameter_values ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "control_parameter_id INTEGER NOT NULL, org_id INTEGER, "
        "sales_document_type_id INTEGER, sales_line_type_id INTEGER, "
        "item_group_id INTEGER, "
        "specificity_rank INTEGER NOT NULL DEFAULT 100, "
        "value TEXT NOT NULL, "
        "status VARCHAR(200) NOT NULL DEFAULT 'active', description TEXT, "
        "created_at DATETIME, "
        "FOREIGN KEY (sales_document_type_id) REFERENCES sales_document_types(id), "
        "FOREIGN KEY (sales_line_type_id) REFERENCES sales_line_types(id))")
    insert(conn, 'sales_line_type_assignments', id=1, sales_document_type_id=1,
           sales_line_type_id=1, specificity_rank=100)
    insert(conn, 'control_parameter_values', id=1, control_parameter_id=1,
           sales_document_type_id=1, sales_line_type_id=1, value='Y')
    conn.commit()
    conn.close()


class TestMigration:
    def test_migrate_maps_ids_and_is_idempotent(self, tmp_path):
        db = tmp_path / 'migrate.db'
        sqlite3.connect(str(db)).close()
        _seed_old_tables(db)

        mig = _load_migration()
        assert mig.migrate(db) is True
        assert mig.migrate(db) is True   # 重复执行不产生重复行

        conn = sqlite3.connect(str(db))
        try:
            total = conn.execute('SELECT count(1) FROM type_definitions').fetchone()[0]
            headers = conn.execute(
                "SELECT count(1) FROM type_definitions WHERE level = 'header'"
            ).fetchone()[0]
            lines = conn.execute(
                "SELECT count(1) FROM type_definitions WHERE level = 'line'"
            ).fetchone()[0]
            assert (total, headers, lines) == (7, 2, 5)

            ta = conn.execute(
                "SELECT default_type_id FROM type_definitions "
                "WHERE level = 'header' AND code = 'TA'").fetchone()[0]
            re_ = conn.execute(
                "SELECT default_type_id FROM type_definitions "
                "WHERE level = 'header' AND code = 'RE'").fetchone()[0]
            assert (ta, re_) == (101, 103)

            std = conn.execute(
                "SELECT id FROM type_definitions "
                "WHERE level = 'line' AND code = 'STD'").fetchone()[0]
            assert std == 101

            for name in ('sales_document_types', 'sales_line_types'):
                assert conn.execute(
                    "SELECT count(1) FROM sqlite_master WHERE name = ? AND type = 'table'",
                    (name,)).fetchone()[0] == 0

            # 引用子表：外键已改指 type_definitions，且行类型引用只搬一次
            for name in ('sales_line_type_assignments',
                         'control_parameter_values'):
                refs = {r[2] for r in conn.execute(
                    'PRAGMA foreign_key_list(%s)' % name).fetchall()}
                assert 'type_definitions' in refs, refs
                assert not refs & {'sales_document_types', 'sales_line_types'}, refs
                assert conn.execute(
                    'SELECT sales_line_type_id FROM %s WHERE id = 1'
                    % name).fetchone()[0] == 101
                assert conn.execute(
                    'SELECT sales_document_type_id FROM %s WHERE id = 1'
                    % name).fetchone()[0] == 1
        finally:
            conn.close()

    def test_child_insert_works_after_migration(self, tmp_path):
        db = tmp_path / 'migrate2.db'
        sqlite3.connect(str(db)).close()
        _seed_old_tables(db)
        assert _load_migration().migrate(db) is True

        from meta.tests.factories._raw_sql_bridge import insert
        conn = sqlite3.connect(str(db))
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            insert(conn, 'sales_line_type_assignments', id=2,
                   sales_document_type_id=2, sales_line_type_id=103)
            conn.commit()
            assert conn.execute(
                'SELECT sales_line_type_id FROM sales_line_type_assignments '
                'WHERE id = 2').fetchone()[0] == 103
        finally:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# G. 迁移 v114（列名去 sales_ 前缀）
# ─────────────────────────────────────────────────────────────────────────────

class TestNamingMigration:
    def test_rename_columns_and_idempotent(self, tmp_path):
        db = tmp_path / 'naming.db'
        sqlite3.connect(str(db)).close()
        _seed_old_tables(db)
        assert _load_migration().migrate(db) is True

        naming = _load_naming_migration()
        assert naming.migrate(db) is True
        assert naming.migrate(db) is True   # 重复执行不报错、不改数据

        conn = sqlite3.connect(str(db))
        try:
            for table in ('control_parameter_values',
                          'sales_line_type_assignments'):
                cols = {r[1] for r in conn.execute(
                    'PRAGMA table_info(%s)' % table).fetchall()}
                assert {'document_type_id', 'line_type_id'} <= cols, cols
                assert not cols & {'sales_document_type_id',
                                   'sales_line_type_id'}, cols
                row = conn.execute(
                    'SELECT document_type_id, line_type_id FROM %s WHERE id = 1'
                    % table).fetchone()
                assert tuple(row) == (1, 101)
        finally:
            conn.close()

        assert naming.verify(db) is True


# ─────────────────────────────────────────────────────────────────────────────
# H. 迁移 v115（对象标识去 sales_ 前缀）
# ─────────────────────────────────────────────────────────────────────────────

_OBJECT_NAMING_MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', 'v115__type_definition_object_naming.py')


def _load_object_naming_migration():
    spec = importlib.util.spec_from_file_location(
        'v115_type_definition_object_naming', _OBJECT_NAMING_MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestObjectNamingMigration:
    def test_rename_table_and_drop_legacy_views(self, tmp_path):
        db = tmp_path / 'object_naming.db'
        sqlite3.connect(str(db)).close()
        _seed_old_tables(db)
        assert _load_migration().migrate(db) is True
        assert _load_naming_migration().migrate(db) is True

        # 测试未经过 schema sync，手工补建旧视图以验证 v115 的清理
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "CREATE VIEW sales_document_types AS "
                "SELECT * FROM type_definitions WHERE level = 'header'")
            conn.execute(
                "CREATE VIEW sales_line_types AS "
                "SELECT * FROM type_definitions WHERE level = 'line'")
            conn.commit()
        finally:
            conn.close()

        naming = _load_object_naming_migration()
        assert naming.migrate(db) is True
        assert naming.migrate(db) is True   # 幂等

        conn = sqlite3.connect(str(db))
        try:
            objs = {r[0]: r[1] for r in conn.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view')").fetchall()}
            assert objs.get('line_type_assignments') == 'table'
            assert objs.get('sales_line_type_assignments') is None
            assert objs.get('sales_document_types') is None
            assert objs.get('sales_line_types') is None
            assert conn.execute(
                'SELECT line_type_id FROM line_type_assignments '
                'WHERE id = 1').fetchone()[0] == 101
        finally:
            conn.close()

        assert naming.verify(db) is True
