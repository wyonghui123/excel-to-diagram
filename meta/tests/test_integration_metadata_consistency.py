# -*- coding: utf-8 -*-
"""集成模块投递事实的元数据一致性（单一事实门禁）。

覆盖:
  · `notification_deliveries` 有 YAML 声明，且档位 disabled（不开放通用 CRUD）；
  · YAML 的状态 / 通道枚举 == 投递器运行时常量（代码不得自造字面量）；
  · 可重试策略 `RETRYABLE_STATUSES` ⊆ YAML 状态枚举；
  · `generated_schema.sql` 快照含该表与两个索引（新装库不丢约束）。

依据: docs/specs/plan-integration-p1p2-2026-11-16.md §6.4 S1 / §6.5 门禁
"""

import os

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.yaml_loader import load_yaml_file
from meta.api.integration_module_api import RETRYABLE_STATUSES
from meta.services.change_event_dispatcher import (
    DELIVERY_CHANNELS,
    STATUS_DELIVERED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENDING,
    STATUS_SKIPPED,
)

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(_TESTS_DIR, '..', 'schemas', 'notification_delivery.yaml')
GENERATED_SCHEMA = os.path.join(
    _TESTS_DIR, '..', 'schemas', 'generated_schema.sql')


def _raw_yaml():
    with open(SCHEMA, encoding='utf-8') as handle:
        return yaml.safe_load(handle)


def _enum_values(obj, field_id):
    """取某字段的 enum_values（去重保序）。"""
    for field in obj.fields:
        if field.id == field_id:
            values = []
            for item in (getattr(field, 'enum_values', None) or []):
                value = item.get('value') if isinstance(item, dict) else item
                if value is not None and value not in values:
                    values.append(value)
            return values
    raise AssertionError('字段不存在: %s' % field_id)


# ── 声明本身 ──────────────────────────────────────────────────────────

def test_schema_declares_delivery_fact_table():
    obj = load_yaml_file(SCHEMA)
    assert obj is not None
    assert obj.id == 'notification_delivery'
    assert obj.table_name == 'notification_deliveries'
    assert obj.generic_api_mode == 'disabled'
    assert _raw_yaml()['ui_view_config']['skip_auto_menu'] is True


# ── YAML ↔ 运行时字面量 ───────────────────────────────────────────────

def test_status_enum_matches_dispatcher_constants():
    obj = load_yaml_file(SCHEMA)
    assert set(_enum_values(obj, 'status')) == {
        STATUS_PENDING, STATUS_SENDING, STATUS_DELIVERED,
        STATUS_FAILED, STATUS_SKIPPED,
    }


def test_channel_enum_matches_dispatcher_channels():
    obj = load_yaml_file(SCHEMA)
    assert set(_enum_values(obj, 'channel')) == set(DELIVERY_CHANNELS)


def test_retryable_statuses_are_declared():
    """重试策略只是「枚举子集」，不得出现 YAML 未声明的状态。"""
    obj = load_yaml_file(SCHEMA)
    assert set(RETRYABLE_STATUSES) <= set(_enum_values(obj, 'status'))


# ── 快照（新装库的建表来源）───────────────────────────────────────────

def test_generated_snapshot_contains_table_and_indexes():
    with open(GENERATED_SCHEMA, encoding='utf-8') as handle:
        sql = handle.read()
    assert 'CREATE TABLE IF NOT EXISTS notification_deliveries' in sql
    assert ("CHECK (status IN ('pending', 'sending', 'delivered', "
            "'failed', 'skipped'))") in sql
    assert 'idx_delivery_status_retry' in sql
    assert 'idx_delivery_event' in sql


# ── S4: 菜单展示字段单一事实（YAML ui_view_config.menu）───────────────

_INTEGRATION_MENUS = (
    ('integration-connections', '集成连接', '/system/integration-connections'),
    ('integration-deliveries', '消息运行面', '/system/integration-deliveries'),
    ('integration-imports', '导入交付面', '/system/integration-imports'),
)


def test_menu_presentation_is_declared_in_yaml():
    """init 脚本只留权限码/页面结构，展示字段必须能从 YAML 装配出来。"""
    from meta.scripts.init_menu_permissions import _apply_yaml_menu_declarations

    entries = [{'menu_code': code, 'page_type': 'custom_page'}
               for code, _, _ in _INTEGRATION_MENUS]
    _apply_yaml_menu_declarations(entries)

    for entry, (code, label, route) in zip(entries, _INTEGRATION_MENUS):
        assert entry['menu_name'] == label
        assert entry['menu_path'] == route
        assert entry['parent_menu'] == 'system'
        assert entry['icon']
        assert entry['color'].startswith('#')
        assert isinstance(entry['sort_order'], int)
