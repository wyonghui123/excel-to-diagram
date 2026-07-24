# -*- coding: utf-8 -*-
"""
[FILE] test_ac008_cartesion.py
[DESCRIPTION] AC-008 PM Option B: 笛卡尔积语义 — 5 个 e2e 单元测试

[PM 决策]
  2026-07-23 PM 决策 B: 笛卡尔积
  修复前: domain=all + sub_domain=[101] 时 sub_domain 自动展开全 4 个 (配置失效)
  修复后: domain=all + sub_domain=[101] 时 sub_domain 保留 {101} (笛卡尔积精确生效)

[覆盖场景]
  AC-008.1: domain=all + sub_domain=[101] → sub_domain = {101} (笛卡尔积)
  AC-008.2: 仅 domain=all → sub_domain = 全 4 个 (沿链展开保留)
  AC-008.3: 仅 sub_domain=[101] → sub_domain = {101} (无变化)
  AC-008.4: domain=[1] + sub_domain=[101] (inherit=0) → sub_domain = {101, 102}
  AC-008.5: 现有 98 个 e2e 场景全部回归通过 (已在 e2e_spec_08_* 中覆盖)

[修复代码位置]
  meta/services/dimension_scope_engine.py
  - expand_dimension_values (L209-232): 加 _has_explicit_include_for_dim 调用
  - _has_explicit_include_for_dim (L868-895): 新增 helper
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ['TEST_ENTRY'] = '1'

import sqlite3
import pytest

from meta.core.datasource import get_data_source
from meta.services.dimension_scope_engine import DimensionScopeEngine


# ============================================================================
# Test DB Fixture — 模拟 4 个 role 配置场景
# ============================================================================
@pytest.fixture(scope="module")
def setup_db():
    """创建临时 SQLite 测试 DB, 包含完整的 HIERARCHY_CHAIN 表结构"""
    tmp_dir = tempfile.mkdtemp(prefix='ac008_cartesion_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript('''
    CREATE TABLE domains (id INTEGER PRIMARY KEY, code TEXT);
    CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER, code TEXT);
    CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT);
    CREATE TABLE versions (id INTEGER PRIMARY KEY, product_id INTEGER, code TEXT);
    CREATE TABLE service_modules (id INTEGER PRIMARY KEY, sub_domain_id INTEGER, code TEXT);
    CREATE TABLE business_objects (id INTEGER PRIMARY KEY, service_module_id INTEGER, code TEXT);

    INSERT INTO domains VALUES (1, 'D1'); INSERT INTO domains VALUES (2, 'D2'); INSERT INTO domains VALUES (3, 'D3');
    INSERT INTO sub_domains VALUES (101, 1, 'SD11');
    INSERT INTO sub_domains VALUES (102, 1, 'SD12');
    INSERT INTO sub_domains VALUES (201, 2, 'SD21');
    INSERT INTO sub_domains VALUES (301, 3, 'SD31');

    CREATE TABLE role_dimension_scopes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER, dimension_code TEXT, scope_mode TEXT,
        dimension_values TEXT, inherit_children INTEGER DEFAULT 1
    );
    ''')

    # 4 种 AC-008 场景
    test_cases = [
        # AC-008.1: domain=all + sub_domain=[101] (PM 关注)
        (9001, 'domain', 'all', None, 1),
        (9001, 'sub_domain', 'include', '[101]', 1),

        # AC-008.2: 仅 domain=all
        (9002, 'domain', 'all', None, 1),

        # AC-008.3: 仅 sub_domain=[101]
        (9003, 'sub_domain', 'include', '[101]', 1),

        # AC-008.4: domain=[1] + sub_domain=[101] (inherit=0)
        (9004, 'domain', 'include', '[1]', 1),
        (9004, 'sub_domain', 'include', '[101]', 0),
    ]

    for role_id, dim, mode, vals, inherit in test_cases:
        cur.execute(
            'INSERT INTO role_dimension_scopes (role_id, dimension_code, scope_mode, dimension_values, inherit_children) '
            'VALUES (?, ?, ?, ?, ?)',
            [role_id, dim, mode, vals, inherit]
        )

    conn.commit()
    conn.close()

    ds = get_data_source('sqlite', path=db_path)
    engine = DimensionScopeEngine(ds)
    return engine


# ============================================================================
# AC-008.1: domain=all + sub_domain=[101] → sub_domain = {101} (笛卡尔积)
# ============================================================================
class TestCartesionAC008:
    """PM Option B 笛卡尔积语义 — AC-008 验收测试"""

    def test_ac008_1_domain_all_sub_domain_specific_keeps_explicit(self, setup_db):
        """AC-008.1: 父维度 all + 子维度 include 不覆盖, 笛卡尔积精确生效"""
        engine = setup_db
        expanded = engine.expand_dimension_values(role_id=9001)

        # 父维度: 全
        assert expanded.get('domain') == {1, 2, 3}, \
            f"AC-008.1 FAIL domain expanded: expected {{1,2,3}}, got {expanded.get('domain')}"

        # 子维度: 仅 {101} (笛卡尔积核心)
        assert expanded.get('sub_domain') == {101}, \
            f"AC-008.1 FAIL sub_domain expanded: expected {{101}} (Cartesion), got {expanded.get('sub_domain')}. " \
            f"修复前会拿到 {{101, 102, 201, 301}}"

    def test_ac008_2_only_domain_all_inherits_chain(self, setup_db):
        """AC-008.2: 仅 domain=all 时, 沿 HIERARCHY_CHAIN 向下展开 sub_domain = 全 4 个"""
        engine = setup_db
        expanded = engine.expand_dimension_values(role_id=9002)

        assert expanded.get('domain') == {1, 2, 3}, \
            f"AC-008.2 FAIL domain expanded: expected {{1,2,3}}, got {expanded.get('domain')}"
        # 仅 domain=all, 没有 explicit sub_domain → 沿链展开
        assert expanded.get('sub_domain') == {101, 102, 201, 301}, \
            f"AC-008.2 FAIL sub_domain expanded: expected {{101,102,201,301}} (chain), got {expanded.get('sub_domain')}"

    def test_ac008_3_only_sub_domain_specific_unchanged(self, setup_db):
        """AC-008.3: 仅 sub_domain=[101] 时, expanded = {101}, 不变"""
        engine = setup_db
        expanded = engine.expand_dimension_values(role_id=9003)

        assert expanded.get('sub_domain') == {101}, \
            f"AC-008.3 FAIL sub_domain expanded: expected {{101}}, got {expanded.get('sub_domain')}"

    def test_ac008_4_domain_specific_sub_domain_specific_inherit_0(self, setup_db):
        """AC-008.4: domain=[1] + sub_domain=[101] (inherit=0) → sub_domain = {101, 102}"""
        engine = setup_db
        expanded = engine.expand_dimension_values(role_id=9004)

        # domain=[1], expand_down: sub_domain=[101, 102] (domain=1 下所有)
        assert expanded.get('domain') == {1}, \
            f"AC-008.4 FAIL domain: expected {{1}}, got {expanded.get('domain')}"
        assert expanded.get('sub_domain') == {101, 102}, \
            f"AC-008.4 FAIL sub_domain: expected {{101, 102}} (domain=1下所有), got {expanded.get('sub_domain')}"

    def test_ac008_helper_method_exists(self):
        """AC-008 helper: DimensionScopeEngine._has_explicit_include_for_dim 存在"""
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        assert hasattr(DimensionScopeEngine, '_has_explicit_include_for_dim'), \
            "AC-008 helper FAIL: _has_explicit_include_for_dim method missing"

    def test_ac008_helper_returns_true_when_explicit(self):
        """AC-008 helper: scopes 含显式 include 配置时返回 True"""
        engine_cls = DimensionScopeEngine
        scopes = [
            {'dimension_code': 'domain', 'scope_mode': 'all', 'dimension_values': None},
            {'dimension_code': 'sub_domain', 'scope_mode': 'include', 'dimension_values': '[101]'},
        ]

        # 创建 fake instance 测 helper
        class FakeEngine:
            _has_explicit_include_for_dim = engine_cls._has_explicit_include_for_dim

        fake = FakeEngine()
        assert fake._has_explicit_include_for_dim(scopes, 'sub_domain') is True, \
            "AC-008 helper FAIL: should detect explicit include [101]"

    def test_ac008_helper_returns_false_when_no_scopes(self):
        """AC-008 helper: 无子维度配置时返回 False (走继承路径)"""
        class FakeEngine:
            _has_explicit_include_for_dim = DimensionScopeEngine._has_explicit_include_for_dim

        scopes = [
            {'dimension_code': 'domain', 'scope_mode': 'all', 'dimension_values': None},
        ]
        fake = FakeEngine()
        assert fake._has_explicit_include_for_dim(scopes, 'sub_domain') is False, \
            "AC-008 helper FAIL: should return False when no sub_domain scope config"


# ============================================================================
# 直接运行入口
# ============================================================================
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
