# -*- coding: utf-8 -*-
"""[平台附件] 服务层 + 迁移测试（spec §15.11：TC-AT-01/02/03/10/12/14/20）"""

import sqlite3
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from meta.core.datasource import get_data_source
from meta.migrations import v269__platform_attachment as v269
from meta.services import attachment_service, attachment_storage
from meta.services.attachment_service import (
    AttachmentError,
    create_link,
    init_attachment_service,
    list_by_target,
    open_content,
    upload_and_link,
)
from meta.services.attachment_storage import KEY_RE

TARGET_TYPE = 'sales_order'
TARGET_TABLE = 'sales_orders'
TARGET_DDL = 'CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY)' % TARGET_TABLE

# 最小码表骨架：让 v269 的 attachment_category 种子与 verify() 可执行
ENUM_DDL = (
    'CREATE TABLE IF NOT EXISTS enum_types ('
    'id VARCHAR(200) PRIMARY KEY, name VARCHAR(200) NOT NULL, '
    "category VARCHAR(200) NOT NULL CHECK (category IN ('system', 'business')), "
    'mutability VARCHAR(200) NOT NULL, description TEXT, created_at DATETIME);'
    'CREATE TABLE IF NOT EXISTS enum_values ('
    'id INTEGER PRIMARY KEY AUTOINCREMENT, enum_type_id VARCHAR(200) NOT NULL, '
    'code VARCHAR(200) NOT NULL, name VARCHAR(200) NOT NULL, '
    'sort_order INTEGER DEFAULT 0, is_system INTEGER DEFAULT 0, '
    'is_active INTEGER DEFAULT 1, created_at DATETIME);'
)

USER = {'user_id': 1, 'user_name': 'tester', 'is_admin': True}


def _pdf(name='contract.pdf', size=1024):
    body = b'%PDF-1.4\n' + b'0' * max(0, size - 9)
    return FileStorage(stream=BytesIO(body), filename=name,
                       content_type='application/pdf')


def _storage_files(root):
    return [p for p in root.rglob('*')
            if p.is_file() and '.tmp' not in p.parts]


def _ensure_registry():
    from meta.core.models import registry
    if not registry._initialized:
        from meta.core.yaml_loader import (register_from_directory,
                                           get_yaml_schema_dir)
        register_from_directory(get_yaml_schema_dir())


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    root = tmp_path / 'storage'
    root.mkdir()
    monkeypatch.setenv('ATTACHMENT_STORAGE_ROOT', str(root))
    monkeypatch.setenv('ATTACHMENT_MAX_FILE_SIZE_MB', '5')
    monkeypatch.setenv('ATTACHMENT_MAX_PER_TARGET', '0')
    attachment_storage.reset()
    yield root
    attachment_storage.reset()


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / 'attachment.db'
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(ENUM_DDL)
        conn.commit()
    finally:
        conn.close()
    assert v269.migrate(path) is True
    return path


@pytest.fixture
def db_snapshot(db_path, storage_root):
    """独立临时库 + 假 BO 目标表 + 附件服务绑定（不触碰 architecture.db）。"""
    _ensure_registry()
    ds = get_data_source('sqlite', database=str(db_path))
    ds.execute(TARGET_DDL)
    ds.commit()
    from meta.tests.factories._raw_sql_bridge import insert
    insert(ds, TARGET_TABLE, rows=[{'id': 1}, {'id': 2}])
    ds.commit()

    attachment_service._table_cache.clear()
    init_attachment_service(ds)
    try:
        yield ds
    finally:
        init_attachment_service(None)
        attachment_service._table_cache.clear()


# ---------------------------------------------------------------- TC-AT-01

def test_tc_at_01_upload_and_link(db_snapshot, storage_root):
    result = upload_and_link(_pdf('合同.pdf'), TARGET_TYPE, 1, user=USER)

    attachment = result['attachment']
    link = result['link']
    assert attachment['status'] == 'active'
    assert attachment['scan_status'] == 'unchecked'
    assert len(attachment['sha256']) == 64
    assert KEY_RE.match(attachment['storage_key'])
    assert attachment['size_bytes'] == 1024
    assert link['status'] == 'active'
    assert link['link_role'] == 'supporting'

    stored = storage_root / attachment['storage_key']
    assert stored.is_file()
    assert stored.stat().st_size == 1024

    listed = list_by_target(TARGET_TYPE, 1, user=USER)
    assert listed['total'] == 1
    assert listed['items'][0]['link_id'] == link['id']
    assert listed['items'][0]['file_name'] == '合同'


# ---------------------------------------------------------------- TC-AT-02

def test_tc_at_02_sha256_dedupe(db_snapshot, storage_root):
    first = upload_and_link(_pdf('a.pdf'), TARGET_TYPE, 1, user=USER)
    second = upload_and_link(_pdf('b.pdf'), TARGET_TYPE, 2, user=USER)

    a1 = first['attachment']
    a2 = second['attachment']
    assert a1['sha256'] == a2['sha256']
    assert a1['storage_key'] == a2['storage_key']
    assert a1['id'] != a2['id']

    files = _storage_files(storage_root)
    assert len(files) == 1

    count = db_snapshot.execute(
        'SELECT COUNT(*) FROM attachments').fetchone()[0]
    assert count == 2


# ---------------------------------------------------------------- TC-AT-03

def test_tc_at_03_duplicate_link(db_snapshot):
    attachment_id = upload_and_link(
        _pdf(), TARGET_TYPE, 1, user=USER)['attachment']['id']

    with pytest.raises(AttachmentError) as exc:
        create_link(attachment_id, TARGET_TYPE, 1, user=USER)
    assert exc.value.code == 'attachment_duplicate_link'
    assert exc.value.status == 200


# ---------------------------------------------------------------- TC-AT-07

def test_tc_at_07_target_delete_invalidates_link(db_snapshot):
    """FR-AT-007：目标对象删除 → 链接转 deleted，附件本体仍 active。"""
    from types import SimpleNamespace

    from meta.core import action_constants
    from meta.core.action_context import ActionContext
    from meta.core.interceptors.cascade_interceptor import CascadeInterceptor

    upload_and_link(_pdf(), TARGET_TYPE, 1, user=USER)
    assert list_by_target(TARGET_TYPE, 1, user=USER)['total'] == 1

    stub = SimpleNamespace(id=TARGET_TYPE, deletion_policy=None, associations={})
    context = ActionContext(meta_object=stub,
                            action=action_constants.CRUD_DELETE,
                            params={'id': 1}, data_source=db_snapshot)
    CascadeInterceptor().before_action(context)

    assert list_by_target(TARGET_TYPE, 1, user=USER)['total'] == 0
    assert db_snapshot.execute(
        'SELECT status FROM attachment_links').fetchone()[0] == 'deleted'
    assert db_snapshot.execute(
        'SELECT status FROM attachments').fetchone()[0] == 'active'


# ---------------------------------------------------------------- TC-AT-12

def test_tc_at_12_path_traversal_filename(db_snapshot, storage_root):
    result = upload_and_link(
        _pdf('../../evil.pdf'), TARGET_TYPE, 1, user=USER)

    attachment = result['attachment']
    assert attachment['original_file_name'] == 'evil.pdf'
    assert KEY_RE.match(attachment['storage_key'])
    assert (storage_root / attachment['storage_key']).is_file()
    assert not (storage_root.parent / 'evil.pdf').exists()
    assert not (storage_root / 'evil.pdf').exists()


# ---------------------------------------------------------------- TC-AT-10

def test_tc_at_10_too_large_no_residue(db_snapshot, storage_root, monkeypatch):
    monkeypatch.setenv('ATTACHMENT_MAX_FILE_SIZE_MB', '1')

    with pytest.raises(AttachmentError) as exc:
        upload_and_link(_pdf('big.pdf', size=1024 * 1024 + 1),
                        TARGET_TYPE, 1, user=USER)
    assert exc.value.code == 'attachment_too_large'

    assert db_snapshot.execute(
        'SELECT COUNT(*) FROM attachments').fetchone()[0] == 0
    assert db_snapshot.execute(
        'SELECT COUNT(*) FROM attachment_links').fetchone()[0] == 0
    assert _storage_files(storage_root) == []


# ---------------------------------------------------------------- TC-AT-14

def test_tc_at_14_missing_file_410(db_snapshot, storage_root):
    result = upload_and_link(_pdf(), TARGET_TYPE, 1, user=USER)
    attachment = result['attachment']

    (storage_root / attachment['storage_key']).unlink()

    with pytest.raises(AttachmentError) as exc:
        open_content(attachment['id'], target_type=TARGET_TYPE,
                     target_id=1, user=USER)
    assert exc.value.code == 'attachment_missing_file'
    assert exc.value.status == 410


# ---------------------------------------------------------------- TC-AT-20

def test_tc_at_20_migration_idempotent(db_path):
    assert v269.migrate(db_path) is True
    assert v269.verify(db_path) is True

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()

    assert {'attachments', 'attachment_links'} <= tables
    assert {'ix_attachments_sha256', 'ix_attachments_status',
            'uq_attachment_link_active', 'uq_attachment_link_primary',
            'ix_attachment_link_target'} <= indexes


# ---------------------------------------------------------------- TC-AT-21

def test_tc_at_21_target_delete_keeps_link_row(db_snapshot):
    """T-SSOT-8 / F-AT-06：目标删除只软失效链接，不得物理删除（D-AT-08）。

    attachment_link.yaml 的 cascade_delete 必须为 false，否则
    DeletionService._delete_polymorphic_children_sync 会硬删 attachment_links 行，
    与 CascadeInterceptor 的软失效形成双写。
    """
    from meta.core.models import registry
    from meta.services.deletion_service import DeletionService

    upload_and_link(_pdf(), TARGET_TYPE, 1, user=USER)

    meta = registry.get('attachment_link')
    associations = meta.associations
    assoc_list = associations.values() if isinstance(associations, dict) else associations
    target = next(
        assoc for assoc in assoc_list
        if (getattr(assoc, 'target_type', '') or getattr(assoc, 'target_entity', ''))
        == 'polymorphic'
    )
    assert target.cascade_delete is False

    deleted = DeletionService(db_snapshot, registry).execute_polymorphic_cascade(
        TARGET_TYPE, 1, operator_id=1, operator_name='tester')
    assert deleted == []
    assert db_snapshot.execute(
        'SELECT COUNT(*) FROM attachment_links').fetchone()[0] == 1
    assert db_snapshot.execute(
        'SELECT status FROM attachment_links').fetchone()[0] == 'active'