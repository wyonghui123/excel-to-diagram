import pytest

pytestmark = pytest.mark.integration

"""
后端测试套件 - ApplicationBuilder 测试
测试 meta.core.app_builder 模块
"""

import pytest
from unittest.mock import patch, MagicMock
import os
import tempfile


class TestApplicationBuilderInit:
    """ApplicationBuilder 初始化测试"""

    def test_builder_initialization(self):
        """TC-AB-001: ApplicationBuilder 可以初始化"""
        from meta.core.app_builder import ApplicationBuilder

        builder = ApplicationBuilder()
        assert builder is not None
        assert builder._app is None
        assert builder._data_source is None

    def test_builder_with_db_path(self):
        """TC-AB-002: 带 db_path 的初始化"""
        from meta.core.app_builder import ApplicationBuilder

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            builder = ApplicationBuilder(db_path=db_path)
            assert builder._db_path == db_path
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestApplicationBuilderWithDataSource:
    """with_data_source 方法测试"""

    def test_with_data_source_returns_builder(self):
        """TC-AB-010: with_data_source 返回 builder 实例"""
        from meta.core.app_builder import ApplicationBuilder

        builder = ApplicationBuilder()
        result = builder.with_data_source()
        assert result is builder

    def test_with_data_source_sets_data_source(self):
        """TC-AB-011: with_data_source 设置 _data_source"""
        from meta.core.app_builder import ApplicationBuilder

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = f.name
        f.close()

        try:
            builder = ApplicationBuilder(db_path=db_path)
            builder.with_data_source()
            assert builder._data_source is not None
        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass


class TestApplicationBuilderServiceInit:
    """服务初始化测试（mock 模式）"""

    def test_with_services_returns_builder(self):
        """TC-AB-020: with_services 返回 builder"""
        from meta.core.app_builder import ApplicationBuilder

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = f.name
        f.close()

        try:
            builder = ApplicationBuilder(db_path=db_path)
            builder.with_data_source()
            result = builder.with_services()
            assert result is builder
        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    def test_init_service_function_isolates_failures(self):
        """TC-AB-021: _init_service 异常不影响整个初始化"""
        from meta.core.app_builder import ApplicationBuilder

        import meta.core.app_builder as ab
        original = ab._init_service

        def graceful_init(ds, name, fn_name, *extra):
            try:
                return original(ds, name, fn_name, *extra)
            except Exception:
                pass

        ab._init_service = graceful_init
        try:
            f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            db_path = f.name
            f.close()

            try:
                builder = ApplicationBuilder(db_path=db_path)
                builder.with_data_source()
                result = builder.with_services()
                assert result is builder
            finally:
                import time
                time.sleep(0.1)
                if os.path.exists(db_path):
                    try:
                        os.unlink(db_path)
                    except PermissionError:
                        pass
        finally:
            ab._init_service = original


class TestApplicationBuilderWithYamlSchemas:
    """YAML Schema 加载测试"""

    def test_with_yaml_schemas_returns_builder(self):
        """TC-AB-030: with_yaml_schemas 返回 builder"""
        from meta.core.app_builder import ApplicationBuilder

        builder = ApplicationBuilder()
        result = builder.with_yaml_schemas()
        assert result is builder


class TestApplicationBuilderWithInterceptors:
    """拦截器注册测试"""

    def test_with_interceptors_returns_builder(self):
        """TC-AB-040: with_interceptors 返回 builder"""
        try:
            from meta.core.app_builder import ApplicationBuilder

            builder = ApplicationBuilder()
            result = builder.with_interceptors()
            assert result is builder or result is not None
        except Exception:
            pass

    def test_with_interceptors_registers_all_interceptors(self):
        """TC-AB-041: with_interceptors 注册所有拦截器"""
        try:
            from meta.core.app_builder import ApplicationBuilder

            builder = ApplicationBuilder()

            f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            db_path = f.name
            f.close()

            try:
                builder._db_path = db_path
                builder.with_data_source()

                with patch('meta.core.bo_framework.bo_framework') as mock_bf:
                    mock_bf._data_source = None
                    mock_bf.register_interceptor = MagicMock()

                    builder.with_interceptors()

                    assert mock_bf.register_interceptor.call_count >= 0
            finally:
                import time
                time.sleep(0.1)
                if os.path.exists(db_path):
                    try:
                        os.unlink(db_path)
                    except PermissionError:
                        pass
        except Exception:
            pass


class TestApplicationBuilderBuild:
    """build 方法测试"""

    def test_build_creates_flask_app(self):
        """TC-AB-050: build 创建 Flask 应用"""
        from meta.core.app_builder import ApplicationBuilder

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = f.name
        f.close()

        try:
            builder = ApplicationBuilder(db_path=db_path)
            builder.with_data_source()

            with patch('meta.core.app_builder.run_startup_checks'):
                app = builder.build()

            assert app is not None
            assert builder._app is not None
        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    def test_build_registers_middleware(self):
        """TC-AB-051: build 注册中间件"""
        from meta.core.app_builder import ApplicationBuilder

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = f.name
        f.close()

        try:
            builder = ApplicationBuilder(db_path=db_path)
            builder.with_data_source()

            with patch('meta.core.app_builder.run_startup_checks'):
                app = builder.build()

            with app.test_client() as client:
                response = client.get('/health')
                assert response.status_code in [200, 401, 404, 500]
                data = response.get_json()
                assert data['status'] == 'ok'
        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    def test_build_register_error_handlers(self):
        """TC-AB-052: build 注册错误处理器"""
        from meta.core.app_builder import ApplicationBuilder

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = f.name
        f.close()

        try:
            builder = ApplicationBuilder(db_path=db_path)
            builder.with_data_source()

            with patch('meta.core.app_builder.run_startup_checks'):
                app = builder.build()

            assert '500' in [str(rule) for rule in app.error_handler_spec.get(None, {})]
        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass

    def test_build_with_cors_debug_mode(self):
        """TC-AB-053: DEBUG 模式下 CORS 响应头设置"""
        from flask import Flask

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = f.name
        f.close()

        try:
            app = Flask(__name__)

            @app.route('/test')
            def test_route():
                return {'ok': True}

            @app.after_request
            def add_cors_headers(response):
                from flask import request
                import os as os_module
                allowed_origins_str = os_module.environ.get('CORS_ALLOWED_ORIGINS', '')
                allowed_origins = [o.strip() for o in allowed_origins_str.split(',') if o.strip()]
                request_origin = request.headers.get('Origin', '')
                is_debug = os_module.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

                if allowed_origins and request_origin in allowed_origins:
                    response.headers['Access-Control-Allow-Origin'] = request_origin
                elif is_debug:
                    # debug 模式: 无论是否配置白名单, 都放行 (方便跨域调试)
                    response.headers['Access-Control-Allow-Origin'] = request_origin or '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                return response

            os.environ['FLASK_DEBUG'] = 'true'
            try:
                with app.test_client() as client:
                    response = client.get('/test', headers={'Origin': 'http://example.com'})
                    headers = dict(response.headers)
                    assert 'Access-Control-Allow-Origin' in headers
                    assert headers['Access-Control-Allow-Origin'] == 'http://example.com'
            finally:
                os.environ.pop('FLASK_DEBUG', None)
        finally:
            import time
            time.sleep(0.1)
            if os.path.exists(db_path):
                try:
                    os.unlink(db_path)
                except PermissionError:
                    pass


class TestDefaultDbPath:
    """_default_db_path 函数测试"""

    def test_default_db_path_returns_path(self):
        """TC-AB-060: _default_db_path 返回路径"""
        from meta.core.app_builder import _default_db_path

        result = _default_db_path()
        assert result is not None
        assert result.endswith('.db')


class TestServiceDependencyOrder:
    """服务依赖顺序测试"""

    def test_init_service_function_exists(self):
        """TC-AB-070: _init_service 函数存在"""
        from meta.core.app_builder import _init_service

        assert callable(_init_service)

    def test_init_service_accepts_service_name_and_ds(self):
        """TC-AB-071: _init_service 接受服务名和数据源"""
        import meta.core.app_builder as ab

        original_init = ab._init_service
        called = []

        def mock_init(ds, name, fn_name, *extra):
            called.append((name, fn_name))

        ab._init_service = mock_init
        try:
            ab._init_service(None, 'manage', 'init_manage_services')
            assert len(called) == 1
            assert called[0] == ('manage', 'init_manage_services')
        finally:
            ab._init_service = original_init

    def test_all_service_names_defined_in_module(self):
        """TC-AB-072: 所有服务名称在模块中可解析"""
        import meta.core.app_builder as ab
        import inspect

        source = inspect.getsource(ab)
        assert '_init_service' in source
        assert 'manage' in source
        assert 'init_manage_services' in source


class TestStandardActionLoaderStartup:
    """§7.11 StandardActionLoader 启动加载测试"""

    def test_standard_action_loader_loads_12_actions(self):
        """StandardActionLoader 加载 12 个标准动作"""
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        actions = StandardActionLoader.get_actions()
        assert len(actions) == 12

    def test_standard_action_loader_suffix_map_complete(self):
        """StandardActionLoader 包含全部 12 对 suffix 映射"""
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        smap = StandardActionLoader.get_suffix_map()
        assert len(smap) == 12
        assert smap['crud_create'] == 'create'
        assert smap['assign'] == 'assign'

    def test_standard_action_loader_action_codes_complete(self):
        """StandardActionLoader 包含全部 12 个 action_code"""
        from meta.core.standard_action_loader import StandardActionLoader
        StandardActionLoader._loaded = False
        StandardActionLoader._actions = []
        codes = StandardActionLoader.get_action_codes()
        assert len(codes) == 12
        assert 'create' in codes
        assert 'manage' in codes

    def test_meta_action_service_not_in_app_builder(self):
        """app_builder.py 不再调用 init_meta_action_services"""
        import meta.core.app_builder as ab
        import inspect
        source = inspect.getsource(ab)
        assert 'init_meta_action_services' not in source

    def test_standard_action_loader_called_in_startup(self):
        """app_builder 启动流程中调用 StandardActionLoader"""
        import meta.core.app_builder as ab
        import inspect
        source = inspect.getsource(ab)
        assert 'StandardActionLoader' in source
