# -*- coding: utf-8 -*-
"""
[P2-B5 2026-07-26] 递归操作符单元测试

测试范围:
  1. CHILDREN_OF: 单层向下 (parent → 直接 children)
  2. ANCESTORS_OF: 单层向上 (child → 直接 parent)
  3. DESCENDANTS_OF: 多层向下递归 (parent → 所有层级 children)
  4. ANCESTORS_ALL_OF: 多层向上递归 (child → 所有层级 ancestors)

[Spec 09 §3.2 维度展开]
  - CHILDREN_OF: 单层, 例: domain → 直接 sub_domain
  - DESCENDANTS_OF: 多层, 例: domain → sub_domain → service_module → business_object
  - ANCESTORS_OF: 单层, 例: sub_domain → 直接 domain
  - ANCESTORS_ALL_OF: 多层, 例: business_object → service_module → sub_domain → domain
"""
import os
import sys
import sqlite3
import tempfile

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'
os.environ['ALLOW_RAW_SQL'] = '1'


@pytest.fixture(scope="module")
def hierarchy_db():
    """创建含层级数据的测试 DB"""
    tmp_dir = tempfile.mkdtemp(prefix='hierarchy_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        -- 层级表
        CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE versions (id INTEGER PRIMARY KEY, product_id INTEGER, code TEXT);
        CREATE TABLE domains (id INTEGER PRIMARY KEY, version_id INTEGER, code TEXT);
        CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER, code TEXT);
        CREATE TABLE service_modules (id INTEGER PRIMARY KEY, sub_domain_id INTEGER, code TEXT);
        CREATE TABLE business_objects (id INTEGER PRIMARY KEY, service_module_id INTEGER, code TEXT);

        -- 测试数据 (3 层深度)
        -- product 1
        INSERT INTO products VALUES (1, 'P1');
        -- version 11 (P1)
        INSERT INTO versions VALUES (11, 1, 'V11');
        -- domain 101 (V11), 102 (V11)
        INSERT INTO domains VALUES (101, 11, 'D101'), (102, 11, 'D102');
        -- sub_domain 1001 (D101), 1002 (D101), 1003 (D102)
        INSERT INTO sub_domains VALUES
            (1001, 101, 'SD1001'), (1002, 101, 'SD1002'), (1003, 102, 'SD1003');
        -- service_module 10001 (SD1001)
        INSERT INTO service_modules VALUES (10001, 1001, 'SM10001');
        -- business_object 100001 (SM10001)
        INSERT INTO business_objects VALUES (100001, 10001, 'BO100001');
    ''')
    conn.commit()
    conn.close()
    return db_path


class TestChildrenOf:
    """CHILDREN_OF: 单层向下"""

    def test_children_of_generates_subquery(self, hierarchy_db):
        """CHILDREN_OF domain_id=101 → 子查询查 sub_domains"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # CHILDREN_OF 契约: value 必须是 dict
        #   {parent_field: <子表中的父外键列>, parent_value: <父 id>}
        conditions = [{
            'field': 'sub_domain_id',
            'op': 'CHILDREN_OF',
            'value': {'parent_field': 'domain_id', 'parent_value': 101},
        }]

        sql, params = parser.to_sql(conditions)
        assert 'FROM sub_domains' in sql
        assert 'domain_id' in sql
        assert params == [101]

    def test_children_of_unknown_field_raises(self, hierarchy_db):
        """CHILDREN_OF 未知字段应抛 ValueError 或返回错误"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{
            'field': 'unknown_field',
            'op': 'CHILDREN_OF',
            'value': {'parent_field': 'domain_id', 'parent_value': 1},
        }]

        # 未知维度字段必须抛 ValueError (而非 AttributeError 等意外异常)
        with pytest.raises(ValueError, match='unknown dimension field'):
            parser.to_sql(conditions)


class TestAncestorsOf:
    """ANCESTORS_OF: 单层向上"""

    def test_ancestors_of_generates_parent_query(self, hierarchy_db):
        """ANCESTORS_OF: sub_domain_id=1001 → 查 domains (parent)"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # ANCESTORS_OF 契约: value 必须是 dict
        #   {child_table: 本层表, child_id: 本层 id, parent_col: 指向父的列}
        conditions = [{
            'field': 'domain_id',
            'op': 'ANCESTORS_OF',
            'value': {
                'child_table': 'sub_domains',
                'child_id': 1001,
                'parent_col': 'domain_id',
            },
        }]

        sql, params = parser.to_sql(conditions)
        # 单层向上: 从 sub_domains 取父列, 只出现一次 SELECT
        assert 'FROM sub_domains' in sql
        assert 'SELECT domain_id FROM sub_domains' in sql
        assert params == [1001]


class TestDescendantsOf:
    """DESCENDANTS_OF: 多层向下递归"""

    def test_descendants_of_domain_to_sub_domain(self, hierarchy_db):
        """DESCENDANTS_OF domain_id=101 → 应包含 sub_domain 1001, 1002"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # DESCENDANTS_OF 契约: value 必须是 dict
        #   {parent_dim: 祖先维度名, parent_value: 祖先 id}
        # field=domain_id 属于 sub_domain, 故 parent_dim 取其祖先 domain
        conditions = [{
            'field': 'domain_id',
            'op': 'DESCENDANTS_OF',
            'value': {'parent_dim': 'domain', 'parent_value': 101},
        }]

        sql, params = parser.to_sql(conditions)
        # 自 domain 向下递归到 sub_domain (含 domains 与 sub_domains 两张表)
        assert 'FROM domains' in sql
        assert 'FROM sub_domains' in sql
        assert sql.lower().count('select') >= 2
        assert params == [101]

    def test_descendants_of_generates_recursive_sql(self, hierarchy_db):
        """DESCENDANTS_OF 应生成多层递归 SQL (跨 product→version→domain→...)"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # 从 product=1 向下递归到 business_object
        # field=service_module_id 属于 business_object (链底), parent_dim=product (链顶)
        conditions = [{
            'field': 'service_module_id',
            'op': 'DESCENDANTS_OF',
            'value': {'parent_dim': 'product', 'parent_value': 1},
        }]

        sql, params = parser.to_sql(conditions)
        # 应贯穿整条链: products → versions → domains → sub_domains
        #              → service_modules → business_objects
        for table in ('products', 'versions', 'domains',
                      'sub_domains', 'service_modules', 'business_objects'):
            assert f'FROM {table}' in sql
        # 6 张表 = 6 层嵌套 SELECT
        assert sql.lower().count('select') == 6
        assert params == [1]

    def test_descendants_of_unknown_dim_raises(self, hierarchy_db):
        """DESCENDANTS_OF 未知维度应抛 ValueError"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{
            'field': 'unknown_id',
            'op': 'DESCENDANTS_OF',
            'value': {'parent_dim': 'domain', 'parent_value': 1},
        }]

        # field 无法映射到层级链中的维度
        with pytest.raises(ValueError, match='cannot determine dim for field'):
            parser.to_sql(conditions)


class TestAncestorsAllOf:
    """ANCESTORS_ALL_OF: 多层向上递归"""

    def test_ancestors_all_of_business_object(self, hierarchy_db):
        """ANCESTORS_ALL_OF business_object_id=100001 → 向上到 product"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # ANCESTORS_ALL_OF 契约: value 必须是 dict
        #   {child_dim: 起点维度, child_id: 起点 id, target_dim: 终点维度}
        conditions = [{
            'field': 'product_id',
            'op': 'ANCESTORS_ALL_OF',
            'value': {
                'child_dim': 'business_object',
                'child_id': 100001,
                'target_dim': 'product',
            },
        }]

        sql, params = parser.to_sql(conditions)
        # 自 business_object 上溯至 product, 贯穿整条链
        for table in ('business_objects', 'service_modules',
                      'sub_domains', 'domains', 'versions', 'products'):
            assert f'FROM {table}' in sql
        assert sql.lower().count('select') == 6
        assert params == [100001]

    def test_ancestors_all_of_to_specific_target(self, hierarchy_db):
        """ANCESTORS_ALL_OF 到特定 target_dim (如 sub_domain)"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # 从 business_object 向上到 sub_domain (只上溯 2 层, 不到 product)
        conditions = [{
            'field': 'sub_domain_id',
            'op': 'ANCESTORS_ALL_OF',
            'value': {
                'child_dim': 'business_object',
                'child_id': 100001,
                'target_dim': 'sub_domain',
            },
        }]

        sql, params = parser.to_sql(conditions)
        # 到达 target_dim 即停止: 含 sub_domains, 但不含 domains/versions/products
        assert 'FROM sub_domains' in sql
        for table in ('domains', 'versions', 'products'):
            assert f'FROM {table}' not in sql
        assert params == [100001]

    def test_ancestors_all_of_unknown_dim_raises(self, hierarchy_db):
        """ANCESTORS_ALL_OF 未知 child_dim 应抛 ValueError"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{
            'field': 'product_id',
            'op': 'ANCESTORS_ALL_OF',
            'value': {
                'child_dim': 'unknown_dim',
                'child_id': 1,
                'target_dim': 'product',
            },
        }]

        with pytest.raises(ValueError, match='unknown child_dim'):
            parser.to_sql(conditions)


class TestRecursiveVsSingleLevel:
    """递归操作符 vs 单层操作符对比"""

    def test_descendants_of_more_inclusive_than_children_of(self, hierarchy_db):
        """DESCENDANTS_OF 应比 CHILDREN_OF 包含更多层级"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()

        # CHILDREN_OF: domain → sub_domain (单层)
        children_sql, _ = parser.to_sql([{
            'field': 'sub_domain_id',
            'op': 'CHILDREN_OF',
            'value': {'parent_field': 'domain_id', 'parent_value': 101},
        }])
        # DESCENDANTS_OF: 同一 field, 但自 domain 逐层向下 (多层)
        descendants_sql, _ = parser.to_sql([{
            'field': 'service_module_id',
            'op': 'DESCENDANTS_OF',
            'value': {'parent_dim': 'domain', 'parent_value': 101},
        }])

        # DESCENDANTS 应包含更多 SELECT (递归)
        assert descendants_sql.lower().count('select') > children_sql.lower().count('select')
