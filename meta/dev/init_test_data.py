# -*- coding: utf-8 -*-
"""
测试数据初始化脚本
为测试套件创建完整的测试数据
使用绝对路径确保在任何工作目录下都能正常工作
"""

import sqlite3
import os

def get_test_db_path():
    """获取测试数据库的绝对路径

    API 使用 server.py 所在目录的 architecture.db
    即 meta/architecture.db
    """
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')

def init_test_data():
    """初始化完整的测试数据"""
    DB_PATH = get_test_db_path()
    print(f"使用数据库: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("开始初始化测试数据...")

    # 1. 确保有产品数据
    cur.execute('SELECT COUNT(*) FROM products WHERE id = 1')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO products (id, name, code, is_active) VALUES (?, ?, ?, ?)',
                   (1, 'Test Product', 'TEST_PROD', 1))
        print("  - 创建产品数据 (id=1)")

    # 2. 确保有版本数据 (version_id=1 和 version_id=2)
    cur.execute('SELECT COUNT(*) FROM versions WHERE id = 1')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)',
                   (1, 'v1.0', 'V1', 1))
        print("  - 创建版本数据 (id=1)")

    cur.execute('SELECT COUNT(*) FROM versions WHERE id = 2')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)',
                   (2, 'v2.0', 'V2', 1))
        print("  - 创建版本数据 (id=2)")

    # 3. 创建领域数据 - 包括父域和叶子域
    cur.execute('SELECT COUNT(*) FROM domains WHERE id = 1 AND version_id = 2')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)',
                   (1, '供应链云', 'SCM_CLOUD', 2))
        print("  - 创建领域数据 (id=1, version_id=2)")

    cur.execute('SELECT COUNT(*) FROM domains WHERE id = 202 AND version_id = 2')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)',
                   (202, 'TEST', 'TEST', 2))
        print("  - 创建叶子域数据 (id=202, version_id=2)")

    cur.execute('SELECT COUNT(*) FROM domains WHERE id = 204 AND version_id = 2')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO domains (id, name, code, version_id) VALUES (?, ?, ?, ?)',
                   (204, 'LSDKFJSDFsdfsdf', 'LSDKF', 2))
        print("  - 创建叶子域数据 (id=204, version_id=2)")

    # 4. 确保有子领域数据
    cur.execute('SELECT COUNT(*) FROM sub_domains WHERE domain_id = 1 AND version_id = 2')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO sub_domains (name, code, version_id, domain_id) VALUES (?, ?, ?, ?)',
                   ('采购管理', 'PO_MGMT', 2, 1))
        print("  - 创建子领域数据 (domain_id=1, version_id=2)")

    # 5. 确保有服务模块数据
    cur.execute('SELECT COUNT(*) FROM service_modules WHERE sub_domain_id IN (SELECT id FROM sub_domains WHERE domain_id = 1) AND version_id = 2')
    if cur.fetchone()[0] == 0:
        sd_id = cur.execute("SELECT id FROM sub_domains WHERE domain_id = 1 AND version_id = 2 LIMIT 1").fetchone()
        if sd_id:
            cur.execute('INSERT INTO service_modules (name, code, version_id, sub_domain_id) VALUES (?, ?, ?, ?)',
                       ('采购订单', 'PO', 2, sd_id[0]))
            print("  - 创建服务模块数据")

    conn.commit()

    # 验证数据
    print("\n数据验证:")
    for table in ['products', 'versions', 'domains', 'sub_domains', 'service_modules']:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0]
        print(f"  {table}: {count} 条记录")

    conn.close()
    print("\n测试数据初始化完成!")

if __name__ == '__main__':
    init_test_data()
