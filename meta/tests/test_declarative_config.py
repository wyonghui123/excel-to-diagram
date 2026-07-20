# -*- coding: utf-8 -*-
"""
[FILE] test_declarative_config.py
[DESCRIPTION] Phase 7 声明式配置 — TDD 测试用例
[SPEC] spec-permission-system-unification-2026-07-19 §3.11 / §4.5 / §8.7

测试覆盖 (P7-T5 验收):
  P7-T1: BO.yaml permission 块 schema 校验通过；示例可解析
  P7-T2: PermissionConfigLoader.load_from_yaml() → upsert 幂等
  P7-T3: 管理维度映射链可正确解析到叶子节点
  P7-T4: 配置校验 — 非法 rule_type/dimension/condition 启动报错

验收门禁:
  1. 所有 BO.yaml permission: 块可加载
  2. 加载幂等：多次执行结果一致
  3. 非法配置启动报错
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os
import sqlite3
import tempfile
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_for_loader():
    """创建含 data_permission_rules 表的测试库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
            resource_type VARCHAR(200),
            dimension_code VARCHAR(200),
            condition TEXT,
            scope_mode VARCHAR(50) DEFAULT 'include',
            permission_level VARCHAR(50) DEFAULT 'read',
            is_denied INTEGER DEFAULT 0,
            inherit_to_children INTEGER DEFAULT 1,
            propagate_to_parents INTEGER DEFAULT 0,
            source_table VARCHAR(100),
            source_id INTEGER,
            created_at VARCHAR(200),
            updated_at VARCHAR(200)
        );
    """)
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

    yield MockDS(conn)
    conn.close()
    os.unlink(db_path)


# ============================================================================
# P7-T1: BO.yaml permission 块设计 — schema 校验 + 可解析
# ============================================================================

class TestP7T1PermissionBlockSchema:
    """P7-T1: BO.yaml permission: 块 schema 设计 + 可解析"""

    def test_permission_config_loader_importable(self):
        """[P7-T1] PermissionConfigLoader 模块可导入"""
        from meta.services.permission_config_loader import PermissionConfigLoader
        assert PermissionConfigLoader is not None

    def test_permission_block_constants_exist(self):
        """[P7-T1] permission 块字段常量已定义"""
        from meta.services.permission_config_loader import (
            PERMITTED_RULE_TYPES,
            PERMITTED_SCOPE_MODES,
        )
        # rule_type 必须覆盖 Spec §3.10/§3.11 所有类型
        assert 'dimension' in PERMITTED_RULE_TYPES
        assert 'condition' in PERMITTED_RULE_TYPES
        assert 'owner' in PERMITTED_RULE_TYPES
        assert 'prohibition' in PERMITTED_RULE_TYPES
        assert 'visibility' in PERMITTED_RULE_TYPES
        # scope_mode include/exclude
        assert 'include' in PERMITTED_SCOPE_MODES
        assert 'exclude' in PERMITTED_SCOPE_MODES

    def test_sample_bo_yaml_permission_block_parseable(self, tmp_path):
        """[P7-T1] 示例 BO.yaml permission 块可解析"""
        sample_yaml = tmp_path / "sample_bo.yaml"
        sample_yaml.write_text("""
id: sample
name: 示例
table_name: sample
aspects: []
permission:
  default:
    rule_type: dimension
    dimension_code: product
    scope_mode: include
    permission_level: read
    inherit_to_children: true
  prohibit_archived:
    rule_type: prohibition
    resource_type: sample
    condition: "status = 'archived'"
    is_denied: true
fields:
  - id: id
    name: ID
    type: integer
    required: true
""", encoding='utf-8')

        from meta.services.permission_config_loader import PermissionConfigLoader
        loader = PermissionConfigLoader(data_source=None)
        # parse_file 返回 dict of rule_name -> rule_dict
        rules = loader.parse_file(str(sample_yaml))
        assert 'default' in rules
        assert 'prohibit_archived' in rules
        assert rules['default']['rule_type'] == 'dimension'
        # is_denied 被规范化为 int (DB 存 int)
        assert rules['prohibit_archived']['is_denied'] == 1


# ============================================================================
# P7-T2: 配置加载器实现 — load_from_yaml() → upsert 幂等
# ============================================================================

class TestP7T2LoadFromYamlUpsert:
    """P7-T2: load_from_yaml() → upsert 幂等"""

    def test_load_from_yaml_inserts_rules(self, db_for_loader, tmp_path):
        """[P7-T2] load_from_yaml 首次加载插入规则到 data_permission_rules"""
        bo_yaml = tmp_path / "sample_bo.yaml"
        bo_yaml.write_text("""
id: sample
name: 示例
table_name: sample
aspects: []
permission:
  default_dim:
    rule_type: dimension
    dimension_code: product
    scope_mode: include
    permission_level: read
fields:
  - id: id
    name: ID
    type: integer
    required: true
""", encoding='utf-8')

        from meta.services.permission_config_loader import PermissionConfigLoader
        loader = PermissionConfigLoader(data_source=db_for_loader)
        loaded = loader.load_from_yaml(str(bo_yaml), role_id=1)

        assert loaded >= 1
        rows = db_for_loader.execute(
            "SELECT rule_type, dimension_code, scope_mode, permission_level "
            "FROM data_permission_rules WHERE role_id=1"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 'dimension'
        assert rows[0][1] == 'product'

    def test_load_from_yaml_idempotent(self, db_for_loader, tmp_path):
        """[P7-T2] 多次执行 load_from_yaml 结果一致 (upsert 幂等)"""
        bo_yaml = tmp_path / "sample_bo.yaml"
        bo_yaml.write_text("""
id: sample
name: 示例
table_name: sample
aspects: []
permission:
  r1:
    rule_type: condition
    resource_type: sample
    condition: "status = 'active'"
    permission_level: read
  r2:
    rule_type: prohibition
    resource_type: sample
    is_denied: true
fields:
  - id: id
    name: ID
    type: integer
    required: true
""", encoding='utf-8')

        from meta.services.permission_config_loader import PermissionConfigLoader
        loader = PermissionConfigLoader(data_source=db_for_loader)

        # 第一次加载
        first_count = loader.load_from_yaml(str(bo_yaml), role_id=1)
        # 第二次加载（幂等：不重复插入）
        second_count = loader.load_from_yaml(str(bo_yaml), role_id=1)

        # 总行数应为 2 (r1 + r2)，不因第二次加载而翻倍
        rows = db_for_loader.execute(
            "SELECT rule_type FROM data_permission_rules WHERE role_id=1"
        ).fetchall()
        assert len(rows) == 2
        # 返回的"新插入数"第二次应为 0
        assert second_count == 0
        assert first_count == 2

    def test_load_from_yaml_multiple_files(self, db_for_loader, tmp_path):
        """[P7-T2] 加载多个 BO.yaml 累积到同一 role_id"""
        yaml_a = tmp_path / "a.yaml"
        yaml_a.write_text("""
id: a
name: A
table_name: a
aspects: []
permission:
  rule_a:
    rule_type: condition
    resource_type: a
    condition: "1=1"
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        yaml_b = tmp_path / "b.yaml"
        yaml_b.write_text("""
id: b
name: B
table_name: b
aspects: []
permission:
  rule_b:
    rule_type: dimension
    dimension_code: product
    scope_mode: include
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import PermissionConfigLoader
        loader = PermissionConfigLoader(data_source=db_for_loader)
        n1 = loader.load_from_yaml(str(yaml_a), role_id=1)
        n2 = loader.load_from_yaml(str(yaml_b), role_id=1)

        assert n1 == 1
        assert n2 == 1
        rows = db_for_loader.execute(
            "SELECT rule_type, resource_type, dimension_code "
            "FROM data_permission_rules WHERE role_id=1 ORDER BY id"
        ).fetchall()
        assert len(rows) == 2


# ============================================================================
# P7-T3: 管理维度映射链明确化 — 链可正确解析到叶子节点
# ============================================================================

class TestP7T3ManagementDimensionChain:
    """P7-T3: 管理维度映射链定义和解析"""

    def test_management_dimension_chain_definition(self):
        """[P7-T3] 管理维度链 HIERARCHY_CHAIN 已定义"""
        from meta.services.management_dimension_engine import (
            MANAGEMENT_DIMENSION_CHAIN,
            resolve_dimension_chain,
        )
        # 4 层链: product → version → domain → sub_domain
        assert MANAGEMENT_DIMENSION_CHAIN == ['product', 'version', 'domain', 'sub_domain']

    def test_resolve_dimension_chain_to_leaf(self):
        """[P7-T3] 链可正确解析到叶子节点"""
        from meta.services.management_dimension_engine import resolve_dimension_chain
        # 从 product 解析到 sub_domain
        chain = resolve_dimension_chain('product', 'sub_domain')
        assert chain == ['product', 'version', 'domain', 'sub_domain']

    def test_resolve_dimension_chain_partial(self):
        """[P7-T3] 部分链解析正确"""
        from meta.services.management_dimension_engine import resolve_dimension_chain
        # 从 version 解析到 domain
        chain = resolve_dimension_chain('version', 'domain')
        assert chain == ['version', 'domain']

    def test_resolve_dimension_chain_invalid(self):
        """[P7-T3] 无效链返回 None 或空"""
        from meta.services.management_dimension_engine import resolve_dimension_chain
        # product 不能解析到不存在的 dimension
        chain = resolve_dimension_chain('product', 'nonexistent')
        assert chain is None or chain == []


# ============================================================================
# P7-T4: 配置校验 — 非法配置启动报错
# ============================================================================

class TestP7T4ConfigValidation:
    """P7-T4: 启动校验 rule_type / dimension / condition"""

    def test_invalid_rule_type_raises(self, tmp_path):
        """[P7-T4] 非法 rule_type 启动报错"""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("""
id: bad
name: Bad
table_name: bad
aspects: []
permission:
  r1:
    rule_type: invalid_type
    resource_type: bad
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import (
            PermissionConfigLoader,
            PermissionConfigValidationError,
        )
        loader = PermissionConfigLoader(data_source=None)
        with pytest.raises(PermissionConfigValidationError) as exc:
            loader.parse_file(str(bad_yaml))
        assert 'invalid_type' in str(exc.value).lower() or 'rule_type' in str(exc.value).lower()

    def test_dimension_rule_requires_dimension_code(self, tmp_path):
        """[P7-T4] dimension 类型规则必须有 dimension_code"""
        bad_yaml = tmp_path / "bad_dim.yaml"
        bad_yaml.write_text("""
id: bad
name: Bad
table_name: bad
aspects: []
permission:
  r1:
    rule_type: dimension
    scope_mode: include
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import (
            PermissionConfigLoader,
            PermissionConfigValidationError,
        )
        loader = PermissionConfigLoader(data_source=None)
        with pytest.raises(PermissionConfigValidationError):
            loader.parse_file(str(bad_yaml))

    def test_condition_rule_requires_condition(self, tmp_path):
        """[P7-T4] condition 类型规则必须有 condition 字段"""
        bad_yaml = tmp_path / "bad_cond.yaml"
        bad_yaml.write_text("""
id: bad
name: Bad
table_name: bad
aspects: []
permission:
  r1:
    rule_type: condition
    resource_type: bad
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import (
            PermissionConfigLoader,
            PermissionConfigValidationError,
        )
        loader = PermissionConfigLoader(data_source=None)
        with pytest.raises(PermissionConfigValidationError):
            loader.parse_file(str(bad_yaml))

    def test_prohibition_rule_must_be_is_denied(self, tmp_path):
        """[P7-T4] prohibition 类型规则 is_denied 必须为 true (或 1)"""
        bad_yaml = tmp_path / "bad_prohib.yaml"
        bad_yaml.write_text("""
id: bad
name: Bad
table_name: bad
aspects: []
permission:
  r1:
    rule_type: prohibition
    resource_type: bad
    is_denied: false
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import (
            PermissionConfigLoader,
            PermissionConfigValidationError,
        )
        loader = PermissionConfigLoader(data_source=None)
        with pytest.raises(PermissionConfigValidationError):
            loader.parse_file(str(bad_yaml))

    def test_valid_config_passes_validation(self, tmp_path):
        """[P7-T4] 合法配置正常通过校验"""
        good_yaml = tmp_path / "good.yaml"
        good_yaml.write_text("""
id: good
name: Good
table_name: good
aspects: []
permission:
  r1:
    rule_type: dimension
    dimension_code: product
    scope_mode: include
  r2:
    rule_type: condition
    resource_type: good
    condition: "1=1"
  r3:
    rule_type: prohibition
    resource_type: good
    is_denied: true
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import PermissionConfigLoader
        loader = PermissionConfigLoader(data_source=None)
        rules = loader.parse_file(str(good_yaml))
        assert len(rules) == 3


# ============================================================================
# P7-T5: 验收 — 综合 (acceptance)
# ============================================================================

class TestP7T5Acceptance:
    """P7-T5: 综合验收 — 加载 + 幂等 + 校验"""

    def test_all_components_integrated(self):
        """[P7-T5] 所有 P7 组件已就位"""
        from meta.services.permission_config_loader import (
            PermissionConfigLoader,
            PermissionConfigValidationError,
            PERMITTED_RULE_TYPES,
            PERMITTED_SCOPE_MODES,
        )
        from meta.services.management_dimension_engine import (
            MANAGEMENT_DIMENSION_CHAIN,
            resolve_dimension_chain,
        )
        assert PermissionConfigLoader is not None
        assert PermissionConfigValidationError is not None
        assert len(PERMITTED_RULE_TYPES) >= 5
        assert MANAGEMENT_DIMENSION_CHAIN

    def test_load_validate_idempotent_combined(self, db_for_loader, tmp_path):
        """[P7-T5] 综合: 加载 → 校验 → 幂等"""
        bo_yaml = tmp_path / "combined.yaml"
        bo_yaml.write_text("""
id: combined
name: Combined
table_name: combined
aspects: []
permission:
  dim_rule:
    rule_type: dimension
    dimension_code: product
    scope_mode: include
    permission_level: read
  cond_rule:
    rule_type: condition
    resource_type: combined
    condition: "status = 'active'"
    permission_level: read
  prohib_rule:
    rule_type: prohibition
    resource_type: combined
    condition: "status = 'deleted'"
    is_denied: true
fields:
  - id: id
    name: ID
    type: integer
""", encoding='utf-8')

        from meta.services.permission_config_loader import PermissionConfigLoader
        loader = PermissionConfigLoader(data_source=db_for_loader)

        # 第一次加载: 3 条规则
        first = loader.load_from_yaml(str(bo_yaml), role_id=1)
        assert first == 3

        # 第二次加载: 幂等, 0 条新增
        second = loader.load_from_yaml(str(bo_yaml), role_id=1)
        assert second == 0

        # 验证表内规则数 = 3
        rows = db_for_loader.execute(
            "SELECT rule_type FROM data_permission_rules WHERE role_id=1"
        ).fetchall()
        assert len(rows) == 3
        rule_types = {r[0] for r in rows}
        assert rule_types == {'dimension', 'condition', 'prohibition'}
