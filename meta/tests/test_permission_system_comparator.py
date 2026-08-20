# -*- coding: utf-8 -*-
"""
Phase 4 P4.2 TDD 测试 — 新旧权限系统输出对比脚本

[覆盖范围]
  1. 单案例对比: 对相同输入, 新旧系统返回一致的 allowed 结果
  2. 批量对比: 多个测试案例的匹配率统计
  3. 不一致案例检测: 新旧系统结果不同时正确标记
  4. 无配置场景: 新旧系统都无权限配置时的行为
  5. 报告生成: JSON 格式报告输出
  6. 角色全量对比: 遍历所有记录

[对比逻辑]
  - 新系统: IntentScopeAdapter.check_record_allowed (真实)
  - 旧系统: DimensionScopeEngine (mock, 聚焦对比逻辑而非旧系统实现)
"""
import os
import sys
import json
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'
os.environ['ALLOW_RAW_SQL'] = '1'


@pytest.fixture
def comparison_db():
    """创建对比测试 DB: 含新系统 Intent + 业务表"""
    tmp_dir = tempfile.mkdtemp(prefix='p4_cmp_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        -- 新系统: Layer 1 事实表
        CREATE TABLE role_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name)
        );

        -- 业务表
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT,
            owner_id INTEGER, status TEXT
        );
        INSERT INTO products VALUES
            (1, 'P1', 'Product 1', 999, 'active'),
            (2, 'P2', 'Product 2', 888, 'active'),
            (3, 'P3', 'Product 3', 777, 'archived');

        CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO roles VALUES (100, 'Role A');
    ''')
    conn.commit()
    conn.close()
    return db_path


def _mock_old_engine(conditions: dict):
    """创建 mock DimensionScopeEngine, 返回固定的 conditions"""
    mock_engine = MagicMock()
    mock_engine.derive_data_conditions.return_value = conditions
    return mock_engine


# ============================================================================
# 1. 单案例对比
# ============================================================================
class TestCompareSingle:
    """单案例对比测试"""

    def test_both_allow(self, comparison_db):
        """新旧系统都允许 → match=True"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        # 新系统: role 100 对 product read 有 Intent (owner_id=999)
        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        # mock 旧系统: product WHERE owner_id=999 (跟新系统一致)
        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            result = comparator.compare_single(
                role_id=100, bo_id='product', action_name='read',
                record_id=1, user_id=999,  # product 1 owner=999
            )

        assert result['new']['allowed'] is True
        assert result['old']['allowed'] is True
        assert result['match'] is True

    def test_both_deny(self, comparison_db):
        """新旧系统都拒绝 → match=True"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        # mock 旧系统: owner_id=999 (跟新系统一致)
        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            # product 2 owner=888, 新旧系统都拒绝
            result = comparator.compare_single(
                role_id=100, bo_id='product', action_name='read',
                record_id=2, user_id=999,
            )

        assert result['new']['allowed'] is False
        assert result['old']['allowed'] is False
        assert result['match'] is True

    def test_mismatch_new_allow_old_deny(self, comparison_db):
        """新系统允许但旧系统拒绝 → match=False"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        # 新系统: 允许所有 (空 include)
        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{\"include\":[],\"exclude\":[]}')"
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        # mock 旧系统: owner_id=999 (限制, 跟新系统不一致)
        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            # product 2 owner=888
            # 新系统: 空 include = all → 允许
            # 旧系统: owner_id=999 → 不匹配 → 拒绝
            result = comparator.compare_single(
                role_id=100, bo_id='product', action_name='read',
                record_id=2, user_id=999,
            )

        assert result['new']['allowed'] is True
        assert result['old']['allowed'] is False
        assert result['match'] is False

    def test_no_config_both_allow(self, comparison_db):
        """新旧系统都无配置 → 新系统拒绝, 旧系统允许 (已知差异)"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        comparator = PermissionSystemComparator(comparison_db)

        # mock 旧系统: 无 dimension scope (返回空 dict)
        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({})
        ):
            result = comparator.compare_single(
                role_id=100, bo_id='product', action_name='read',
                record_id=1, user_id=999,
            )

        # 新系统无 Intent → 默认拒绝
        # 旧系统无 scope → 默认允许 (无限制)
        assert result['match'] is False
        assert result['new']['allowed'] is False
        assert result['old']['allowed'] is True


# ============================================================================
# 2. 批量对比
# ============================================================================
class TestCompareBatch:
    """批量对比测试"""

    def test_batch_statistics(self, comparison_db):
        """批量对比 → 统计匹配率"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        test_cases = [
            {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
             'record_id': 1, 'user_id': 999},  # 都允许
            {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
             'record_id': 2, 'user_id': 999},  # 都拒绝
            {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
             'record_id': 3, 'user_id': 999},  # 都拒绝
        ]

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            report = comparator.compare_batch(test_cases)

        assert report['total'] == 3
        assert report['matched'] == 3
        assert report['mismatched'] == 0
        assert report['match_rate'] == 1.0

    def test_batch_with_mismatch(self, comparison_db):
        """批量对比含不一致案例"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        # 新系统允许所有, 旧系统限制
        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{\"include\":[],\"exclude\":[]}')"
        )
        conn.commit()
        conn.close()

        test_cases = [
            {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
             'record_id': 1, 'user_id': 999},  # 都允许 (owner=999 匹配)
            {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
             'record_id': 2, 'user_id': 999},  # mismatch: 新允许, 旧拒绝
            {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
             'record_id': 3, 'user_id': 999},  # mismatch: 新允许, 旧拒绝
        ]

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            report = comparator.compare_batch(test_cases)

        assert report['total'] == 3
        assert report['matched'] == 1
        assert report['mismatched'] == 2
        assert report['match_rate'] < 1.0
        assert len(report['mismatched_cases']) == 2

    def test_batch_empty_cases(self, comparison_db):
        """空测试案例列表 → total=0"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        comparator = PermissionSystemComparator(comparison_db)
        report = comparator.compare_batch([])

        assert report['total'] == 0
        assert report['matched'] == 0
        assert report['mismatched'] == 0


# ============================================================================
# 3. 报告生成
# ============================================================================
class TestReportGeneration:
    """报告生成测试"""

    def test_report_to_dict(self, comparison_db):
        """报告可转为 dict"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        comparator = PermissionSystemComparator(comparison_db)
        report = comparator.compare_batch([])

        assert isinstance(report, dict)
        assert 'total' in report
        assert 'matched' in report
        assert 'mismatched' in report
        assert 'match_rate' in report
        assert 'mismatched_cases' in report

    def test_report_json_serializable(self, comparison_db):
        """报告可序列化为 JSON"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({})
        ):
            report = comparator.compare_batch([
                {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
                 'record_id': 1, 'user_id': 999},
            ])

        json_str = json.dumps(report, ensure_ascii=False)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed['total'] == 1

    def test_mismatched_case_contains_details(self, comparison_db):
        """不一致案例包含详细的新旧结果"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        # 新系统允许所有, 旧系统限制
        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{\"include\":[],\"exclude\":[]}')"
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            report = comparator.compare_batch([
                {'role_id': 100, 'bo_id': 'product', 'action_name': 'read',
                 'record_id': 2, 'user_id': 999},
            ])

        mismatched = report['mismatched_cases'][0]
        assert 'case' in mismatched
        assert 'new' in mismatched
        assert 'old' in mismatched
        assert mismatched['case']['record_id'] == 2


# ============================================================================
# 4. 角色全量对比
# ============================================================================
class TestCompareRole:
    """角色全量对比: 对比某个角色的所有配置"""

    def test_compare_role_intents(self, comparison_db):
        """对比角色的所有 Intent 对应的记录"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = 999'})
        ):
            report = comparator.compare_role(
                role_id=100, bo_id='product', action_name='read', user_id=999,
            )

        # 3 个 product, 新旧系统配置一致 (owner_id=999)
        # product 1 (owner=999): 都允许
        # product 2,3 (owner≠999): 都拒绝
        assert report['total'] == 3
        assert report['matched'] == 3

    def test_compare_role_no_records(self, comparison_db):
        """角色无配置 → 对比所有记录的默认行为"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({})
        ):
            # role 999 无任何配置
            report = comparator.compare_role(
                role_id=999, bo_id='product', action_name='read', user_id=999,
            )

        # 新系统无 Intent → 默认拒绝
        # 旧系统无 scope → 默认允许
        assert report['total'] == 3
        assert report['mismatched'] == 3


# ============================================================================
# 5. 运行时变量替换
# ============================================================================
class TestRuntimeVariableReplacement:
    """运行时变量替换测试"""

    def test_user_id_variable_replaced(self, comparison_db):
        """${user.id} 在旧系统 SQL 中被替换"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        # 新系统: owner_id=${user.id}
        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': '${user.id}'}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        # mock 旧系统: owner_id=${user.id} (跟新系统一致)
        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = ${user.id}'})
        ):
            # user_id=999, product 1 owner=999 → 都允许
            result = comparator.compare_single(
                role_id=100, bo_id='product', action_name='read',
                record_id=1, user_id=999,
            )

        assert result['new']['allowed'] is True
        assert result['old']['allowed'] is True
        assert result['match'] is True

    def test_user_id_variable_mismatch(self, comparison_db):
        """${user.id} 替换后, 新旧系统对同一记录结果一致"""
        from meta.core.permission_system_comparator import PermissionSystemComparator

        # 新系统: owner_id=${user.id}
        conn = sqlite3.connect(comparison_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': '${user.id}'}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        comparator = PermissionSystemComparator(comparison_db)

        with patch(
            'meta.core.permission_system_comparator.DimensionScopeEngine',
            return_value=_mock_old_engine({'product': 'owner_id = ${user.id}'})
        ):
            # user_id=999, product 2 owner=888 → 都拒绝
            result = comparator.compare_single(
                role_id=100, bo_id='product', action_name='read',
                record_id=2, user_id=999,
            )

        assert result['new']['allowed'] is False
        assert result['old']['allowed'] is False
        assert result['match'] is True
