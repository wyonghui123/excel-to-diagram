"""直接seed数据到当前后端数据库"""
import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), 'meta', 'architecture.db')
conn = sqlite3.connect(db_path)

existing = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
if existing > 0:
    print(f"数据库已有 {existing} products，跳过seed")
else:
    print("开始导入测试数据...")

    # products: id, name, code, description, visibility, owner_id, is_active
    conn.execute("""
        INSERT INTO products (id, name, code, description, visibility, owner_id, is_active, created_at) VALUES
        (1, 'YonBIP高级版', 'TTTTT000', 'YonBIP高级版', 'public', 1, 1, datetime('now'))
    """)
    conn.commit()
    print("  products: 1 row")

    # versions: id, product_id, name, description, visibility, owner_id, is_current
    conn.execute("""
        INSERT INTO versions (id, product_id, name, description, visibility, owner_id, is_current, created_at) VALUES
        (1, 1, 'V11', 'V11版本', 'public', 1, 1, datetime('now'))
    """)
    conn.commit()
    print("  versions: 1 row")

    # domains: id, version_id, code, name, description
    domains = [
        (1, 1, 'supply_chain', '供应链云', '供应链云'),
        (2, 1, 'finance', '财务云', '财务云'),
        (3, 1, 'marketing', '营销云', '营销云'),
    ]
    for d in domains:
        conn.execute("""
            INSERT INTO domains (id, version_id, code, name, description, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, d)
    conn.commit()
    print(f"  domains: {len(domains)} rows")

    # sub_domains: id, version_id, domain_id, code, name, description
    sub_domains = [
        (1, 1, 1, 'purchase_supply', '采购供应', '采购供应'),
        (2, 1, 1, 'sales', '销售', '销售'),
        (3, 1, 1, 'supply_chain_plan', '供应链计划', '供应链计划'),
        (4, 1, 1, 'supply_chain_common', '供应链公共', '供应链公共'),
        (5, 1, 1, 'purchase', '采购管理', '采购管理'),
    ]
    for sd in sub_domains:
        conn.execute("""
            INSERT INTO sub_domains (id, version_id, domain_id, code, name, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, sd)
    conn.commit()
    print(f"  sub_domains: {len(sub_domains)} rows")

    # service_modules: id, version_id, domain_id, sub_domain_id, code, name, description
    modules = [
        (1, 1, 1, 1, 'WM', 'PDA仓储作业', 'PDA仓储作业'),
        (2, 1, 1, 2, 'SQ', '销售报价', '销售报价'),
        (3, 1, 1, 2, 'SFCT', '销售预测', '销售预测'),
        (4, 1, 1, 2, 'SCT', '销售合同', '销售合同'),
        (5, 1, 1, 3, 'SCN', '供应网络', '供应网络'),
        (6, 1, 1, 4, 'SCCS', '供应链公共', '供应链公共'),
        (7, 1, 1, 5, 'PUM', '采购管理', '采购管理'),
    ]
    for m in modules:
        conn.execute("""
            INSERT INTO service_modules (id, version_id, domain_id, sub_domain_id, code, name, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, m)
    conn.commit()
    print(f"  service_modules: {len(modules)} rows")

    # business_objects: id, version_id, domain_id, sub_domain_id, service_module_id, code, name, description
    bos = [
        (1, 1, 1, 1, 1, 'WM03', '拣货单', '拣货单'),
        (2, 1, 1, 1, 1, 'WM02', '拣货生单规则', '拣货生单规则'),
        (3, 1, 1, 1, 1, 'WM01', '出入库通知', '出入库通知'),
        (4, 1, 1, 2, 2, 'SQ02', '销售报价变更', '销售报价变更'),
        (5, 1, 1, 2, 2, 'SQ01', '销售报价', '销售报价'),
    ]
    for b in bos:
        conn.execute("""
            INSERT INTO business_objects (id, version_id, domain_id, sub_domain_id, service_module_id, code, name, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, b)
    conn.commit()
    print(f"  business_objects: {len(bos)} rows")

    print("Seed 完成!")

conn.close()
