# -*- coding: utf-8 -*-
"""M0：YAML v1.1 variants 合并契约测试（spec-meta-driven-ui §4.7.4）。"""

import pytest

from meta.core.models_ui_config import UIListViewColumn, UIListViewConfig, UIViewConfig
from meta.core.ui_config.variant_merge import apply_variant, merge_patch

pytestmark = pytest.mark.unit


def _base_config() -> UIViewConfig:
    return UIViewConfig(
        version=2,
        list=UIListViewConfig(
            columns=[UIListViewColumn(key='code', title='编号')],
            actions=[{'id': 'create', 'label': '新建', 'position': 'toolbar'}],
        ),
        variants={
            'docs': {
                'title': '单据列表',
                'list': {
                    'columns': [
                        {'key': 'code', 'title': '编号'},
                        {'key': 'status', 'title': '状态'},
                    ],
                },
            },
        },
    )


def test_merge_patch_array_uses_stable_key():
    merged, warnings = merge_patch(
        {'list': {'columns': [{'key': 'a', 'title': 'A'}, {'key': 'b', 'title': 'B'}]}},
        {'list': {'columns': [{'key': 'a', 'title': 'A2'}, {'key': 'c', 'title': 'C'}]}},
    )
    assert [item['key'] for item in merged['list']['columns']] == ['a', 'b', 'c']
    assert merged['list']['columns'][0]['title'] == 'A2'
    assert warnings == []


def test_merge_patch_remove_item():
    merged, _ = merge_patch(
        {'list': {'actions': [{'id': 'a'}, {'id': 'b'}]}},
        {'list': {'actions': [{'id': 'a', '_remove': True}]}},
    )
    assert merged['list']['actions'] == [{'id': 'b'}]


def test_merge_patch_rejects_nested_variants():
    merged, warnings = merge_patch({}, {'variants': {'x': {}}})
    assert 'variants' not in merged
    assert warnings and 'variants' in warnings[0]


def test_apply_variant_merges_columns_and_title():
    base = _base_config()
    config, warnings = apply_variant(base, base.variants['docs'])
    assert warnings == []
    assert config.version == 2
    assert config.variants == {}
    assert [column.key for column in config.list.columns] == ['code', 'status']
    assert config.list.columns[0].title == '编号'
    assert config.list.title == '单据列表'
    # 基础配置不被就地修改
    assert [column.key for column in base.list.columns] == ['code']


def test_apply_variant_keeps_base_actions():
    base = _base_config()
    config, _ = apply_variant(base, base.variants['docs'])
    assert config.list.actions[0]['id'] == 'create'
