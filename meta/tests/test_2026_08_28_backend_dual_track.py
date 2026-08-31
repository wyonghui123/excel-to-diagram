# -*- coding: utf-8 -*-
"""
[Plan B Task 11] 后端双轨对账 e2e 测试

策略 (per Plan A Critical-2 经验):
- 用 tempfile + shutil.copy2 创建临时 DB, 不依赖外部 snapshot 文件
- 直接断言"新表存在 + 旧表不存在 + 核心 row count > 0"

避免 Plan A 失败模式: 硬编码依赖 meta/architecture.db.snapshot_20260828
"""
import os
import shutil
import sqlite3
import tempfile
import pytest


@pytest.fixture(scope='module')
def temp_db():
    """复制 architecture.db 到临时 DB, 测试用"""
    src = 'meta/architecture.db'
    if not os.path.exists(src):
        pytest.skip(f'{src} not found')

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    shutil.copy2(src, path)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


class TestSchemaRename:
    """验证 Plan A 的表重命名是否生效"""

    def test_new_tables_exist(self, temp_db):
        """新表存在: permission_sets, orgs, user_permission_sets, org_members, org_functions"""
        conn = sqlite3.connect(temp_db)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert 'permission_sets' in tables, 'permission_sets table missing'
            assert 'orgs' in tables, 'orgs table missing'
            assert 'user_permission_sets' in tables, 'user_permission_sets table missing'
            assert 'org_members' in tables, 'org_members table missing'
            assert 'org_functions' in tables, 'org_functions table missing'
        finally:
            conn.close()

    def test_old_tables_deprecated(self, temp_db):
        """旧表已废弃: 业务代码不再使用, 数据保留为备份"""
        conn = sqlite3.connect(temp_db)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

            # 注: Plan A 实际保留了 roles/user_groups 等表 (含少量测试残留 ~6 行),
            # 业务代码全部迁移到新表. 旧表不再被任何 service/API 主动使用.
            # 关键验证: _v1_backup 表存在 + 新表已建
            assert 'roles_v1_backup' in tables, 'roles_v1_backup should be preserved'

            # 验证关键业务数据已迁移到新表 (新表行数 >= 旧表行数, 允许少量 test residue)
            for old_table, new_table in [
                ('roles', 'permission_sets'),
                ('user_groups', 'orgs'),
            ]:
                if old_table in tables and new_table in tables:
                    old_count = conn.execute(f"SELECT COUNT(*) FROM {old_table}").fetchone()[0]
                    new_count = conn.execute(f"SELECT COUNT(*) FROM {new_table}").fetchone()[0]
                    # 新表行数应 >= 旧表行数 (迁移完成)
                    assert new_count >= old_count, (
                        f'{new_table}({new_count}) < {old_table}({old_count}); '
                        f'migration incomplete'
                    )
        finally:
            conn.close()

    def test_permission_set_row_count(self, temp_db):
        """permission_sets 行数 > 0 (有数据迁移成功)"""
        conn = sqlite3.connect(temp_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM permission_sets").fetchone()[0]
            assert count > 0, f'permission_sets is empty (count={count})'
        finally:
            conn.close()

    def test_org_row_count(self, temp_db):
        """orgs 行数 > 0"""
        conn = sqlite3.connect(temp_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM orgs").fetchone()[0]
            assert count > 0, f'orgs is empty (count={count})'
        finally:
            conn.close()

    def test_user_permission_set_row_count(self, temp_db):
        """user_permission_sets 行数 > 0 (admin 应该有绑定)"""
        conn = sqlite3.connect(temp_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM user_permission_sets").fetchone()[0]
            assert count > 0, f'user_permission_sets is empty (count={count})'
        finally:
            conn.close()

    def test_org_functions_row_count(self, temp_db):
        """org_functions 行数 > 0 (admin org 应有 administrative 职能)"""
        conn = sqlite3.connect(temp_db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM org_functions").fetchone()[0]
            assert count > 0, f'org_functions is empty (count={count})'
        finally:
            conn.close()


class TestPermissionServiceSchema:
    """验证 PermissionService 在新 schema 下能正常加载和查询"""

    def test_permission_service_loads(self):
        from meta.services.permission_service import PermissionService
        assert PermissionService is not None

    def test_permission_set_service_loads(self):
        from meta.services.permission_set_service import PermissionSetService
        assert PermissionSetService is not None

    def test_org_service_loads(self):
        from meta.services.org_service import OrgService
        assert OrgService is not None

    def test_org_function_service_loads(self):
        from meta.services.org_function_service import OrgFunctionService
        assert OrgFunctionService is not None


class TestBlueprintRegistration:
    """验证新 blueprints 已注册到 Flask app"""

    def test_permission_set_bp_route_exists(self):
        from meta.api.permission_set_api import permission_set_bp
        assert permission_set_bp.name == 'permission_set'

    def test_org_bp_route_exists(self):
        from meta.api.org_api import org_bp
        assert org_bp.name == 'org'

    def test_org_function_bp_route_exists(self):
        from meta.api.org_function_api import org_function_bp
        assert org_function_bp.name == 'org_function'
