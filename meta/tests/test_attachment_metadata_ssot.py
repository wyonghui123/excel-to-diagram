# -*- coding: utf-8 -*-
"""[平台附件] 元数据驱动 / SSOT 一致性测试（spec §19.5 T-SSOT-1..7）

把「附件分类码值 / 权限矩阵归属 / 级联语义 / 前端下拉」的单一事实源固化：
码值只允许出现在 models_enums.AttachmentCategory（及 v269/ENUM_VALUE_NAME_MAP 派生），
任何文件再次手写第二份码值表都必须让本测试失败。

行为回归（T-SSOT-8：目标删除不物理删除链接行）位于 test_attachment.py 的 TC-AT-21。
"""

import sqlite3
from pathlib import Path

import yaml

from meta.core.models import AttachmentCategory
from meta.migrations import v269__platform_attachment as v269
from meta.scripts import migrate_enums
from meta.services import attachment_service
from meta.services.resource_inheritance_engine import RESOURCE_METADATA_MAP
from meta.tests.test_attachment import db_path  # noqa: F401  复用最小码表骨架 + v269 迁移

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PROJECT_ROOT / 'meta' / 'schemas'
FRONTEND_SERVICE = PROJECT_ROOT / 'src' / 'services' / 'attachmentService.js'
FRONTEND_SECTION = (
    PROJECT_ROOT / 'src' / 'components' / 'common' / 'ObjectPage' / 'AttachmentSection.vue'
)

ENUM_TYPE_ID = 'attachment_category'
EXPECTED_CODES = {member.value for member in AttachmentCategory}
# 附件专属码值（不在 LINK_ROLES 中），不得在后端服务里硬编码
CATEGORY_ONLY_CODES = ('delivery_note', 'drawing', 'inspection', 'approval')
SYSTEM_FIELDS = (
    'original_file_name', 'mime_type', 'size_bytes', 'storage_backend',
    'status', 'scan_status', 'uploaded_by', 'uploaded_at',
)


def _load_schema(name):
    with (SCHEMA_DIR / name).open(encoding='utf-8') as fp:
        return yaml.safe_load(fp)


# ---------------------------------------------------------------- T-SSOT-1

def test_t_ssot_1_attachment_category_registered_as_enum():
    """码值唯一真源：models_enums.AttachmentCategory 且已注册进枚举迁移。"""
    assert migrate_enums.get_enum_type_name(AttachmentCategory) == ENUM_TYPE_ID
    assert AttachmentCategory in migrate_enums.ENUM_CLASSES

    config = migrate_enums.ENUM_DIMENSION_CONFIG[ENUM_TYPE_ID]
    assert config['category'] == 'business'
    assert config['mutability'] == 'extensible'

    name_map = migrate_enums.ENUM_VALUE_NAME_MAP[ENUM_TYPE_ID]
    assert set(name_map) == EXPECTED_CODES
    assert all(label for label in name_map.values())


# ---------------------------------------------------------------- T-SSOT-2

def test_t_ssot_2_migrated_db_matches_enum(db_path):
    """v269 落库的码值 / 中文名与 Enum + ENUM_VALUE_NAME_MAP 完全一致。"""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            'SELECT code, name FROM enum_values WHERE enum_type_id = ?',
            [ENUM_TYPE_ID],
        ).fetchall()
    finally:
        conn.close()

    assert {code for code, _ in rows} == EXPECTED_CODES
    labels = dict(rows)
    expected_labels = migrate_enums.ENUM_VALUE_NAME_MAP[ENUM_TYPE_ID]
    for code in EXPECTED_CODES:
        assert labels[code] == expected_labels[code]


# ---------------------------------------------------------------- T-SSOT-3

def test_t_ssot_3_backend_has_no_second_code_list():
    """后端不再持有手写 CATEGORIES，校验统一走 enum_resolver（fail-closed）。"""
    assert not hasattr(attachment_service, 'CATEGORIES')
    assert attachment_service.CATEGORY_ENUM_TYPE_ID == ENUM_TYPE_ID

    source = Path(attachment_service.__file__).read_text(encoding='utf-8')
    assert 'CATEGORIES = (' not in source
    assert 'validate_enum_value(' in source
    for code in CATEGORY_ONLY_CODES:
        assert code not in source, '后端服务残留硬编码分类码值: %s' % code


# ---------------------------------------------------------------- T-SSOT-4

def test_t_ssot_4_frontend_options_come_from_enum_api():
    """前端分类下拉唯一来源 = metaEnumService.getEnum('attachment_category')。"""
    js = FRONTEND_SERVICE.read_text(encoding='utf-8')
    assert 'ATTACHMENT_CATEGORIES' not in js
    assert "getEnum('%s')" % ENUM_TYPE_ID in js

    vue = FRONTEND_SECTION.read_text(encoding='utf-8')
    assert 'ATTACHMENT_CATEGORIES' not in vue
    assert 'getAttachmentCategories' in vue


# ---------------------------------------------------------------- T-SSOT-5

def test_t_ssot_5_cascade_soft_and_permission_matrix_absent():
    """级联语义：链接不随目标硬删；附件不产生独立权限矩阵行。"""
    target = next(
        assoc for assoc in _load_schema('attachment_link.yaml')['associations']
        if assoc['name'] == 'target'
    )
    assert target['cascade_delete'] is False

    resources = _load_schema('resource_types.yaml')
    assert 'attachment' not in resources
    assert 'attachment_link' not in resources

    assert RESOURCE_METADATA_MAP['attachment']['table'] == 'attachments'


# ---------------------------------------------------------------- T-SSOT-6

def test_t_ssot_6_generated_schema_contains_attachment_tables():
    """对象结构真源：yaml → generated_schema.sql 已包含两张表。"""
    sql = (SCHEMA_DIR / 'generated_schema.sql').read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS attachments' in sql
    assert 'CREATE TABLE IF NOT EXISTS attachment_links' in sql


# ---------------------------------------------------------------- T-SSOT-7

def test_t_ssot_7_system_fields_readonly():
    """系统字段（字节 / 指纹 / 上传信息）在表单中只读，避免被业务侧改写。"""
    fields = {field['id']: field for field in _load_schema('attachment.yaml')['fields']}
    for field_id in SYSTEM_FIELDS:
        ui = fields[field_id].get('ui') or {}
        assert ui.get('readonly') is True, '系统字段缺少 ui.readonly: %s' % field_id