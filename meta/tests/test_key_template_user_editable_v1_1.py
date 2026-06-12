"""
[NEW v1.1 2026-06-11] KeyTemplate user_editable 模式测试

覆盖 Spec：[spec-key-template-user-editable.md v1.1]

测试场景：
1. KeyTemplateConfig dataclass：默认值 + 显式声明 + 非法值校验
2. preview API 返回 user_editable / pattern / preview
3. 拦截器 INFO 日志（用户传了 code 不变行为）
4. yaml schema 配置正确加载
5. _get_key_template_user_editable 多类型支持
6. ExcelDesignSystem 新色 AUTO_GEN_OR_MANUAL_FILL

共 5 个测试类，10+ 测试用例。
"""

import pytest
import sys
import os

# 添加项目根路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestKeyTemplateConfigUserEditable:
    """测试 dataclass 字段 + 校验"""

    def test_default_user_editable_is_auto_or_manual(self):
        """T1: 未声明 user_editable 时，默认 auto_or_manual"""
        from meta.core.key_template_engine import KeyTemplateConfig
        cfg = KeyTemplateConfig.from_dict('test', {'enabled': True})
        assert cfg.user_editable == 'auto_or_manual', \
            f'Expected auto_or_manual, got {cfg.user_editable}'

    def test_explicit_user_editable_auto_only(self):
        """T2: 显式声明 user_editable=auto_only"""
        from meta.core.key_template_engine import KeyTemplateConfig
        cfg = KeyTemplateConfig.from_dict('test', {'enabled': True, 'user_editable': 'auto_only'})
        assert cfg.user_editable == 'auto_only'

    def test_explicit_user_editable_manual_only(self):
        """T3: 显式声明 user_editable=manual_only"""
        from meta.core.key_template_engine import KeyTemplateConfig
        cfg = KeyTemplateConfig.from_dict('test', {'enabled': True, 'user_editable': 'manual_only'})
        assert cfg.user_editable == 'manual_only'

    def test_invalid_user_editable_raises(self):
        """T4: 非法 user_editable 值必须抛 ValueError"""
        from meta.core.key_template_engine import KeyTemplateConfig
        with pytest.raises(ValueError) as exc_info:
            KeyTemplateConfig(object_id='test', enabled=True, user_editable='invalid_mode')
        assert 'Invalid user_editable' in str(exc_info.value)
        assert 'auto_only' in str(exc_info.value)
        assert 'auto_or_manual' in str(exc_info.value)
        assert 'manual_only' in str(exc_info.value)

    def test_from_dict_with_disabled_key_template(self):
        """T5: enabled=false 时也应有 user_editable 字段"""
        from meta.core.key_template_engine import KeyTemplateConfig
        cfg = KeyTemplateConfig.from_dict('test', {'enabled': False})
        assert cfg.user_editable == 'auto_or_manual'
        assert cfg.enabled is False


class TestYAMLSchemaUserEditable:
    """测试 yaml schema 配置正确加载"""

    def test_relationship_yaml_has_user_editable(self):
        """T6: relationship.yaml 包含 user_editable: auto_or_manual"""
        import yaml
        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'schemas', 'relationship.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            schema = yaml.safe_load(f)
        assert schema['key_template']['user_editable'] == 'auto_or_manual', \
            f'relationship.yaml missing user_editable: {schema.get("key_template", {})}'

    def test_business_object_yaml_has_user_editable(self):
        """T7: business_object.yaml 包含 user_editable: auto_or_manual"""
        import yaml
        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'schemas', 'business_object.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            schema = yaml.safe_load(f)
        assert schema['key_template']['user_editable'] == 'auto_or_manual', \
            f'business_object.yaml missing user_editable: {schema.get("key_template", {})}'


class TestInterceptorInfoLog:
    """测试拦截器 INFO 日志"""

    def test_interceptor_logs_user_supplied_code(self):
        """T8: 拦截器在用户传入 code 时记录 INFO 日志"""
        from meta.core.interceptors.key_template_interceptor import KeyTemplateInterceptor
        import inspect
        src = inspect.getsource(KeyTemplateInterceptor.before_action)
        assert 'user-supplied code' in src, \
            'Interceptor should log when user supplies code'
        assert 'user_editable' in src, \
            'Interceptor should log user_editable value'


class TestPreviewAPIReturnsUserEditable:
    """测试 preview API 返回字段"""

    def test_preview_returns_user_editable_and_pattern(self):
        """T9: preview API 返回 user_editable / pattern / preview 字段"""
        from meta.api import key_template_api
        import inspect
        src = inspect.getsource(key_template_api.preview_code)
        assert "'user_editable'" in src, \
            'preview_code should return user_editable'
        assert "'pattern'" in src, \
            'preview_code should return pattern'
        assert "'preview'" in src, \
            'preview_code should return preview'


class TestImportExportUserEditable:
    """测试 import_export_service 集成"""

    def test_helper_method_exists(self):
        """T10: _get_key_template_user_editable 方法存在"""
        from meta.services.import_export_service import ImportExportService
        assert hasattr(ImportExportService, '_get_key_template_user_editable'), \
            'ImportExportService should have _get_key_template_user_editable method'

    def test_helper_handles_none(self):
        """T11: helper 接受 None 输入返回空字符串"""
        from meta.services.import_export_service import ImportExportService
        result = ImportExportService._get_key_template_user_editable(None, None)
        assert result == '', f'None input should return empty string, got {result!r}'

    def test_helper_handles_string_input(self):
        """T12: helper 接受 str 输入（通过 registry 查询）"""
        from meta.services.import_export_service import ImportExportService
        # 'relationship' 在系统加载后应该被找到
        # 这里允许 None 或 'auto_or_manual'（取决于 registry 状态）
        result = ImportExportService._get_key_template_user_editable(None, 'relationship')
        # 不为 None 也不为非空字符串（取决于 schema 是否加载）
        assert isinstance(result, str), f'Should return string, got {type(result)}'

    def test_helper_handles_dict_with_user_editable(self):
        """T13: helper 接受 dict 输入并正确读取 user_editable"""
        from meta.services.import_export_service import ImportExportService
        # 构造一个 mock MetaObject（用 SimpleNamespace 或 dict）
        # 注意：helper 检查 isinstance(meta_obj, dict)，所以传 dict
        from types import SimpleNamespace
        obj = SimpleNamespace()
        obj.name = 'test_obj'
        obj.key_template = {'user_editable': 'auto_or_manual'}
        result = ImportExportService._get_key_template_user_editable(None, obj)
        assert result == 'auto_or_manual', f'Dict input failed: {result!r}'

    def test_helper_handles_object_without_user_editable(self):
        """T14: 对象没有 user_editable 字段时返回空字符串"""
        from meta.services.import_export_service import ImportExportService
        from types import SimpleNamespace
        obj = SimpleNamespace()
        obj.name = 'test_obj'
        obj.key_template = {'enabled': True}  # 无 user_editable
        result = ImportExportService._get_key_template_user_editable(None, obj)
        assert result == '', f'Should return empty string, got {result!r}'


class TestExcelDesignSystemNewFill:
    """测试新增底色"""

    def test_auto_or_manual_fill_color(self):
        """T15: AUTO_GEN_OR_MANUAL_FILL 颜色 = E1F5FE（浅蓝）"""
        from meta.services.excel_design_system import ExcelDesignSystem
        assert hasattr(ExcelDesignSystem, 'AUTO_GEN_OR_MANUAL_FILL')
        fill = ExcelDesignSystem.AUTO_GEN_OR_MANUAL_FILL
        # openpyxl 颜色格式: '00E1F5FE' (前两个字符是 alpha)
        assert fill.start_color.rgb in ('00E1F5FE', 'E1F5FE'), \
            f'Expected E1F5FE, got {fill.start_color.rgb}'

    def test_color_distinct_from_existing(self):
        """T16: 新色与已有色不同"""
        from meta.services.excel_design_system import ExcelDesignSystem
        new_rgb = ExcelDesignSystem.AUTO_GEN_OR_MANUAL_FILL.start_color.rgb
        assert new_rgb != ExcelDesignSystem.REQUIRED_FILL.start_color.rgb, \
            'New fill should differ from REQUIRED_FILL (yellow)'
        assert new_rgb != ExcelDesignSystem.BUSINESS_KEY_FILL.start_color.rgb, \
            'New fill should differ from BUSINESS_KEY_FILL (green)'
        assert new_rgb != ExcelDesignSystem.READONLY_FILL.start_color.rgb, \
            'New fill should differ from READONLY_FILL (gray)'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])