# -*- coding: utf-8 -*-
"""
SVC-001: i18n_service 单元测试 (8 用例)

[NEW] 2026-06-07 批次: 补齐 I18nService 工具类测试
- 单例模式
- get_text / get_text_with_fallback
- set_i18n_dir + YAML 加载 (含嵌套字典展平)
- set_current_locale / get_current_locale / get_available_locales
- add_locale_texts / has_locale / get_all_texts
- resolve_i18n_key
- reload_locale / reload_all_locales
"""
import os
import tempfile
import pytest

pytestmark = pytest.mark.unit


class TestI18nService:
    """I18nService 单元测试 (SVC-001)"""

    def test_singleton_pattern(self):
        """I18nService 是单例"""
        from meta.services.i18n_service import I18nService
        s1 = I18nService()
        s2 = I18nService()
        assert s1 is s2

    def test_get_text_with_no_locale(self):
        """无 locale 时返回 key 本身"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()
        svc.set_current_locale('__nonexistent_locale__')
        assert svc.get_text('any.key') == 'any.key'

    def test_get_text_with_default(self):
        """缺 default → 返回 key; 有 default → 返回 default"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()
        svc.add_locale_texts('test_loc_1', {'hello': '你好'})
        svc.set_current_locale('test_loc_1')
        assert svc.get_text('hello') == '你好'
        assert svc.get_text('missing.key') == 'missing.key'
        assert svc.get_text('missing.key', default='默认文本') == '默认文本'

    def test_get_text_with_fallback(self):
        """get_text_with_fallback 缺失时返回 default_text"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()
        svc.add_locale_texts('test_loc_2', {'save': '保存'})
        svc.set_current_locale('test_loc_2')
        assert svc.get_text_with_fallback('save', 'Save') == '保存'
        assert svc.get_text_with_fallback('cancel', 'Cancel') == 'Cancel'

    def test_set_i18n_dir_loads_yaml(self):
        """set_i18n_dir + _load_all_locales 加载 YAML"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 写一个 YAML
            yaml_path = os.path.join(tmpdir, 'test_loc_3.yaml')
            with open(yaml_path, 'w', encoding='utf-8') as f:
                f.write("""
common:
  ok: 确认
  cancel: 取消
nested:
  deep:
    key: 深层 key
""")
            svc.set_i18n_dir(tmpdir)
            # 应加载 test_loc_3
            assert svc.has_locale('test_loc_3')
            assert svc.get_text('common.ok', locale='test_loc_3') == '确认'
            assert svc.get_text('nested.deep.key', locale='test_loc_3') == '深层 key'

    def test_set_current_locale_and_get(self):
        """set_current_locale + get_current_locale"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()
        svc.set_current_locale('ja-JP')
        assert svc.get_current_locale() == 'ja-JP'

    def test_add_locale_texts_and_get_all(self):
        """add_locale_texts 增量添加 + get_all_texts"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()
        svc.add_locale_texts('test_loc_4', {'k1': 'v1'})
        svc.add_locale_texts('test_loc_4', {'k2': 'v2'})
        all_texts = svc.get_all_texts('test_loc_4')
        assert all_texts.get('k1') == 'v1'
        assert all_texts.get('k2') == 'v2'

    def test_resolve_i18n_key(self):
        """resolve_i18n_key 缺 i18n_key 时返回 default_text"""
        from meta.services.i18n_service import I18nService
        svc = I18nService()
        # 空 i18n_key → default_text
        assert svc.resolve_i18n_key('', '默认文本') == '默认文本'
        # i18n_key 在 YAML 中找到 → 返回翻译
        svc.add_locale_texts('test_loc_5', {'welcome': '欢迎'})
        svc.set_current_locale('test_loc_5')
        assert svc.resolve_i18n_key('welcome', 'Welcome') == '欢迎'
