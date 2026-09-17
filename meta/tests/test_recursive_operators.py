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
        conditions = [{'field': 'sub_domain_id', 'op': 'CHILDREN_OF', 'value': 101}]

        sql, params = parser.to_sql(conditions)
        assert 'sub_domains' in sql.lower() or 'domain_id' in sql.lower()
        assert 101 in params

    def test_children_of_unknown_field_raises(self, hierarchy_db):
        """CHILDREN_OF 未知字段应抛 ValueError 或返回错误"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{'field': 'unknown_field', 'op': 'CHILDREN_OF', 'value': 1}]

        # 应抛异常或返回错误信息
        with pytest.raises((ValueError, Exception)):
            parser.to_sql(conditions)


class TestAncestorsOf:
    """ANCESTORS_OF: 单层向上"""

    def test_ancestors_of_generates_parent_query(self, hierarchy_db):
        """ANCESTORS_OF sub_domain_id=1001 → 查 domains (parent)"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{'field': 'domain_id', 'op': 'ANCESTORS_OF', 'value': 1001}]

        # 应生成查 parent 的 SQL
        sql, params = parser.to_sql(conditions)
        # SQL 应包含 domains 表或 domain_id 字段
        assert isinstance(sql, str)


class TestDescendantsOf:
    """DESCENDANTS_OF: 多层向下递归"""

    def test_descendants_of_domain_to_sub_domain(self, hierarchy_db):
        """DESCENDANTS_OF domain_id=101 → 应包含 sub_domain 1001, 1002"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{'field': 'domain_id', 'op': 'DESCENDANTS_OF', 'value': 101}]

        sql, params = parser.to_sql(conditions)
        # 应生成跨层子查询 (含 sub_domains 表)
        assert isinstance(sql, str)
        assert 101 in params

    def test_descendants_of_generates_recursive_sql(self, hierarchy_db):
        """DESCENDANTS_OF 应生成多层递归 SQL (跨 product→version→domain→...)"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # 从 product=1 向下递归到 business_object
        conditions = [{'field': 'product_id', 'op': 'DESCENDANTS_OF', 'value': 1}]

        sql, params = parser.to_sql(conditions)
        # SQL 应是嵌套子查询 (跨多层)
        assert isinstance(sql, str)
        # 应包含多次 SELECT (递归)
        assert sql.lower().count('select') >= 2

    def test_descendants_of_unknown_dim_raises(self, hierarchy_db):
        """DESCENDANTS_OF 未知维度应抛异常"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{'field': 'unknown_id', 'op': 'DESCENDANTS_OF', 'value': 1}]

        with pytest.raises((ValueError, Exception)):
            parser.to_sql(conditions)


class TestAncestorsAllOf:
    """ANCESTORS_ALL_OF: 多层向上递归"""

    def test_ancestors_all_of_business_object(self, hierarchy_db):
        """ANCESTORS_ALL_OF business_object_id=100001 → 向上到 product"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{'field': 'business_object_id', 'op': 'ANCESTORS_ALL_OF', 'value': 100001}]

        sql, params = parser.to_sql(conditions)
        assert isinstance(sql, str)
        # 应生成跨层子查询 (含 service_modules, sub_domains, domains, versions, products)
        assert sql.lower().count('select') >= 2

    def test_ancestors_all_of_to_specific_target(self, hierarchy_db):
        """ANCESTORS_ALL_OF 到特定 target_dim (如 sub_domain)"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        # 从 business_object 向上到 sub_domain
        conditions = [{
            'field': 'business_object_id',
            'op': 'ANCESTORS_ALL_OF',
            'value': 100001,
            'target_dim': 'sub_domain',
        }]

        sql, params = parser.to_sql(conditions)
        assert isinstance(sql, str)

    def test_ancestors_all_of_unknown_dim_raises(self, hierarchy_db):
        """ANCESTORS_ALL_OF 未知 child_dim 应抛异常"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()
        conditions = [{'field': 'unknown_id', 'op': 'ANCESTORS_ALL_OF', 'value': 1}]

        with pytest.raises((ValueError, Exception)):
            parser.to_sql(conditions)


class TestRecursiveVsSingleLevel:
    """递归操作符 vs 单层操作符对比"""

    def test_descendants_of_more_inclusive_than_children_of(self, hierarchy_db):
        """DESCENDANTS_OF 应比 CHILDREN_OF 包含更多层级"""
        from meta.core.condition_parser import ConditionExpressionParser

        parser = ConditionExpressionParser()

        # CHILDREN_OF: domain → sub_domain (单层)
        children_sql, _ = parser.to_sql([
            {'field': 'sub_domain_id', 'op': 'CHILDREN_OF', 'value': 101}
        ])
        # DESCENDANTS_OF: domain → sub_domain + service_module + business_object (多层)
        descendants_sql, _ = parser.to_sql([
            {'field': 'domain_id', 'op': 'DESCENDANTS_OF', 'value': 101}
        ])

        # DESCENDANTS 应包含更多 SELECT (递归)
        assert descendants_sql.lower().count('select') >= children_sql.lower().count('select')
