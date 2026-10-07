# -*- coding: utf-8 -*-
"""MetadataDrivenValidator 单测的临时库播种辅助

DDL + DML 集中在此 —— `meta/tests/conftest.py` 的 `_check_raw_sql_in_tests()`
会 skip 含 `INSERT INTO` / `UPDATE ... SET` / `DELETE FROM` 的**测试文件**,
`meta/tests/factories/` 是唯一白名单目录。

[TBD-13 2026-10-06] 此前建表+播种写在 test_metadata_driven_validator.py 内,
整个文件被门控 skip, FK 用例的存量失败被掩盖; 移入本助手后默认口径即运行。
"""


def seed_validator_test_db(ds) -> None:
    """在给定数据源上建 4 张临时表并播种固定数据（供 validator 单测使用）。"""
    ds.execute("""
        CREATE TABLE test_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            code TEXT,
            department_id INTEGER,
            status TEXT
        )
    """)
    ds.execute(
        "INSERT INTO test_users (id, username, email, code, department_id, status) VALUES (1, 'alice', 'alice@test.com', 'A001', 10, 'active')"
    )
    ds.execute(
        "INSERT INTO test_users (id, username, email, code, department_id, status) VALUES (2, 'bob', 'bob@test.com', 'B001', 20, 'inactive')"
    )

    ds.execute("""
        CREATE TABLE test_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    """)
    ds.execute("INSERT INTO test_departments (id, name) VALUES (10, 'Engineering')")
    ds.execute("INSERT INTO test_departments (id, name) VALUES (20, 'Sales')")

    ds.execute("""
        CREATE TABLE test_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT,
            version_id INTEGER
        )
    """)
    ds.execute("INSERT INTO test_products (id, code, name, version_id) VALUES (1, 'PROD-001', 'Product A', 100)")

    ds.execute("""
        CREATE TABLE test_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_code TEXT,
            product_code TEXT,
            amount INTEGER,
            version_id INTEGER
        )
    """)
    ds.execute("INSERT INTO test_orders (id, customer_code, product_code, amount, version_id) VALUES (1, 'CUST-001', 'PROD-001', 100, 100)")

    # [C-T0-12 2026-10-07] 声明式取值集校验(_check_value_set)的目标表。
    # 用**真实对象** factor_catalog 的表名/列名(registry 已加载), 使用例校验的是
    # 真实 wiring —— 即 key_schema.key_fields 的元素须取自 factor_catalogs.field_id。
    ds.execute("""
        CREATE TABLE factor_catalogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id TEXT
        )
    """)
    ds.execute("INSERT INTO factor_catalogs (id, field_id) VALUES (1, 'customer')")
    ds.execute("INSERT INTO factor_catalogs (id, field_id) VALUES (2, 'material')")