# -*- coding: utf-8 -*-
"""
test_bug_v020_export_owner_exception.py

覆盖 BUG-V020: dim scope 主路径下 _build_permission_filter 漏 owner exception

根因:
  import_export_service.py:_build_permission_filter 在 dim scope 命中时
  直接 return,绕过 BUG-V014 的 owner exception 叠加逻辑
  → user 自己 owner 的私有产品被 dim scope 严格过滤掉
  → TEST333 导出 product 只返回 dim_scope 命中的 1 条 (供应链),而非 3 条

依据:
  .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export)
  fix 提交: BUG-V020
"""
import pytest
import sqlite3
import os
from pathlib import Path

# 设置 ALLOW_RAW_SQL
os.environ.setdefault('ALLOW_RAW_SQL', '1')


PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'meta' / 'architecture.db'


def _ensure_registry():
    """确保 meta registry 加载了 (用于 is_in_chain 和 registry.get)"""
    from meta.core.models import registry
    if registry.get('product') is None:
        from meta.core.yaml_loader import register_from_directory
        import os
        schemas_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'schemas')
        register_from_directory(schemas_dir)


class TestBugV020DimScopeOwnerException:
    """BUG-V020: dim scope 主路径叠加 owner exception"""

    def test_dim_scope_path_does_not_skip_owner_exception(self):
        """
        _build_permission_filter 在 dim scope 命中时, 仍然必须 OR 上 owner exception
        """
        from meta.services.import_export_service import ImportExportService
        from meta.core.datasource import get_data_source
        import inspect

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = ImportExportService(ds, None, None)

        source = inspect.getsource(service._build_permission_filter)

        # 必须有 BUG-V020 修复标记
        assert 'BUG-V020' in source, "BUG-V020 修复必须存在"

        # dim scope 路径不能再直接 return
        # 检查: 在 dim_scope_conds_to_sql 后, 必须不直接 return
        # 而是设置 dim_scope_applied = True 让 owner exception 后续叠加
        idx_dim_scope = source.find('_dim_scope_conds_to_sql')
        idx_first_return = source.find('return f" AND ({sql_fragment})"', idx_dim_scope)
        if idx_first_return > 0:
            # 不应该再直接 return
            between = source[idx_dim_scope:idx_first_return]
            assert 'return f" AND ({sql_fragment})"' not in between, (
                "dim scope 命中后不应直接 return, 必须叠加 owner exception"
            )

    def test_dim_scope_applied_flag_exists(self):
        """
        必须有 dim_scope_applied 标志控制后续 fallback 跳过
        """
        from meta.services.import_export_service import ImportExportService
        from meta.core.datasource import get_data_source
        import inspect

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = ImportExportService(ds, None, None)
        source = inspect.getsource(service._build_permission_filter)

        assert 'dim_scope_applied' in source, (
            "必须有 dim_scope_applied 标志控制 fallback 路径"
        )
        assert 'dim_scope_applied = True' in source, (
            "dim scope 命中时应设置 dim_scope_applied=True"
        )

    def test_owner_exception_block_preserved(self):
        """
        BUG-V014 owner exception 逻辑必须保留 (产品/子对象 chain 模式)
        """
        from meta.services.import_export_service import ImportExportService
        from meta.core.datasource import get_data_source
        import inspect

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = ImportExportService(ds, None, None)
        source = inspect.getsource(service._build_permission_filter)

        assert 'BUG-V014' in source, "BUG-V014 owner exception 必须保留"
        assert 'is_in_chain' in source, "子对象 chain 检查必须保留"
        assert 'products WHERE owner_id' in source, "子对象 owner exception 必须保留"


class TestBugV020Integration:
    """集成测试: TEST333 实际导出 3 个产品"""

    def setup_method(self):
        """检查 DB 中 TEST333 实际数据"""
        self.conn = sqlite3.connect(str(DB_PATH))
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM users WHERE username='TEST333'")
        row = cur.fetchone()
        self.test333_id = row[0] if row else None

    def teardown_method(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def test_test333_should_see_3_products_in_db(self):
        """
        前置检查: DB 中 TEST333 至少拥有 3 个产品
        (TESTVVVXX/VVVVVV/供应链 之一 + owner 私有)
        """
        if not self.test333_id:
            pytest.skip("TEST333 not in DB")

        cur = self.conn.cursor()
        # 用前端列表的过滤规则 (visibility=public OR owner_id=self)
        cur.execute(
            "SELECT id, name, code, owner_id, visibility FROM products "
            "WHERE visibility='public' OR owner_id=?",
            (self.test333_id,)
        )
        rows = cur.fetchall()
        assert len(rows) >= 3, (
            f"TEST333 (id={self.test333_id}) 应至少看到 3 个产品, 实际: {len(rows)} - {rows}"
        )

    def test_build_permission_filter_includes_owner_for_test333(self):
        """
        关键测试: 调用 _build_permission_filter('product') 应返回
        同时包含 dim_scope OR owner 的 SQL
        """
        if not self.test333_id:
            pytest.skip("TEST333 not in DB")

        from meta.services.import_export_service import ImportExportService
        from meta.core.datasource import get_data_source

        _ensure_registry()  # 必须先加载 yaml,否则 registry.get('product')=None

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = ImportExportService(ds, None, None)

        from meta.services.query_service import set_thread_user, clear_thread_user_id
        try:
            set_thread_user({
                'user_id': self.test333_id,
                'username': 'TEST333',
                'permissions': [],  # 非 admin
                'is_admin': False,
            })
            sql, params = service._build_permission_filter('product')

            # SQL 必须包含 owner_id 检查 (BUG-V020 修复)
            assert 'owner_id' in sql, (
                f"BUG-V020: SQL 必须包含 owner_id 检查. 实际: {sql}"
            )
            # params 必须包含 user_id
            assert self.test333_id in params, (
                f"BUG-V020: params 必须包含 user_id={self.test333_id}. 实际: {params}"
            )
        finally:
            clear_thread_user_id()


class TestBugV020Regression:
    """回归 - 不应破坏其他场景"""

    def test_admin_user_no_filter(self):
        """
        admin 用户仍直接放行 (无 filter)
        """
        from meta.services.import_export_service import ImportExportService
        from meta.core.datasource import get_data_source

        _ensure_registry()

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = ImportExportService(ds, None, None)

        from meta.services.query_service import set_thread_user, clear_thread_user_id
        try:
            set_thread_user({
                'user_id': 1,
                'username': 'admin',
                'permissions': ['*'],
                'is_admin': True,
            })
            sql, params = service._build_permission_filter('product')
            assert sql == '', f"admin 应无 filter, 实际: {sql}"
            assert params == [], f"admin 应无 params, 实际: {params}"
        finally:
            clear_thread_user_id()

    def test_sub_object_owner_exception_preserved(self):
        """
        子对象 (version) 的 owner exception 必须保留
        (version 用 chain_owner_resolver)
        """
        from meta.services.import_export_service import ImportExportService
        from meta.core.datasource import get_data_source

        _ensure_registry()

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = ImportExportService(ds, None, None)

        from meta.services.query_service import set_thread_user, clear_thread_user_id
        try:
            set_thread_user({
                'user_id': 3,
                'username': 'test_user',
                'permissions': [],
                'is_admin': False,
            })
            sql, params = service._build_permission_filter('version')
            # 子对象应使用 chain_owner_resolver
            assert 'product_id IN' in sql, (
                f"version 应使用 product_id IN chain. 实际: {sql}"
            )
            assert 'products WHERE owner_id' in sql, (
                f"version 应追溯到 products.owner_id. 实际: {sql}"
            )
        finally:
            clear_thread_user_id()
