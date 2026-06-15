# -*- coding: utf-8 -*-
"""
数据库初始化和测试数据生成脚本

安全保护：
1. 需要 --force 参数才能删除已存在的数据库
2. 删除前自动备份数据库
"""

import sys
import os
import sqlite3
import shutil
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from meta.core.datasource import get_data_source


def backup_database(db_path: str) -> str:
    """备份数据库，返回备份文件路径"""
    if not os.path.exists(db_path):
        return None

    os.makedirs('backups', exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'backups/architecture_{timestamp}.db'

    shutil.copy2(db_path, backup_path)
    print(f"  [备份] 已备份到: {backup_path}")

    backup_size = os.path.getsize(backup_path) / 1024
    print(f"  [备份] 大小: {backup_size:.2f} KB")

    return backup_path


def init_database(force: bool = False):
    db_path = 'meta/architecture.db'
    abs_db_path = os.path.abspath(db_path)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if os.path.exists(db_path):
        if not force:
            print(f"\n{'='*60}")
            print(f"[WARNING]  警告: 数据库已存在")
            print(f"   路径: {abs_db_path}")
            print(f"\n直接运行将删除现有数据库！")
            print(f"\n安全选项:")
            print(f"   1. 使用 --force 参数: python init_and_seed.py --force")
            print(f"   2. 脚本将自动备份现有数据库到 backups/ 目录")
            print(f"{'='*60}\n")
            response = input("是否继续删除并重建数据库? (输入 'yes' 确认): ")
            if response.lower() != 'yes':
                print("操作已取消")
                return None
            print()

        print(f"准备初始化数据库: {db_path}")

        backup_path = backup_database(db_path)
        if backup_path:
            print(f"删除旧数据库: {db_path}")
            os.remove(db_path)
        else:
            print(f"未找到现有数据库，将创建新数据库")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    sql_statements = [
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT,
            description TEXT,
            is_current INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            visibility TEXT DEFAULT 'public',
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            domain_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (domain_id) REFERENCES domains(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            sub_domain_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (sub_domain_id) REFERENCES sub_domains(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            service_module_id INTEGER,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (service_module_id) REFERENCES service_modules(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            source_bo_id INTEGER NOT NULL,
            target_bo_id INTEGER NOT NULL,
            -- Type-A 物理冗余: 业务键/编码（sync_on_write 一致性保证）
            source_code TEXT,
            target_code TEXT,
            code TEXT,
            relation_code TEXT,
            relation_type TEXT,
            relation_desc TEXT,
            -- 注意: source_bo_name, source_domain_id, module_relation 等
            -- 分类字段在 relationship.yaml 中标记为 storage: virtual (Type-B 虚拟冗余)
            -- 这些字段不由 DB 存储，由 computed_utils.py 在查询时通过 JOIN 实时计算
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (source_bo_id) REFERENCES business_objects(id),
            FOREIGN KEY (target_bo_id) REFERENCES business_objects(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT
        )
        """,
    ]

    for sql in sql_statements:
        cursor.execute(sql)

    conn.commit()
    conn.close()

    print(f"[OK] 数据库初始化完成: {db_path}")
    return db_path


def insert_data():
    db_path = 'meta/architecture.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print("\n开始插入测试数据...")

    cursor.execute("""
        INSERT INTO products (name, code, description, is_active, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('供应链管理系统', 'SUPPLY_CHAIN', '企业供应链管理系统，包含采购、库存、销售等核心模块', 1, now, 'system'))
    product_id = cursor.lastrowid
    print(f"创建产品成功: ID={product_id}")

    cursor.execute("""
        INSERT INTO versions (product_id, name, code, description, is_current, visibility, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_id, 'v1.0', 'V1', '第一版供应链系统', 1, 'public', now, 'system'))
    v1_id = cursor.lastrowid
    print(f"创建版本v1.0成功: ID={v1_id}")

    cursor.execute("""
        INSERT INTO versions (product_id, name, code, description, is_current, visibility, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_id, 'v2.0', 'V2', '第二版供应链系统', 0, 'public', now, 'system'))
    v2_id = cursor.lastrowid
    print(f"创建版本v2.0成功: ID={v2_id}")

    domain_ids = {}
    domains = [
        ('采购管理', 'PROCUREMENT', '采购相关业务领域'),
        ('库存管理', 'INVENTORY', '库存相关业务领域'),
        ('销售管理', 'SALES', '销售相关业务领域'),
        ('财务管理', 'FINANCE', '财务相关业务领域'),
    ]
    for name, code, desc in domains:
        cursor.execute("""
            INSERT INTO domains (version_id, name, code, description, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (v1_id, name, code, desc, now, 'system'))
        domain_ids[name] = cursor.lastrowid
        print(f"创建领域{name}成功: ID={domain_ids[name]}")

    sub_domain_ids = {}
    sub_domains = [
        ('采购管理', '采购需求', 'PROC_REQ', '采购需求管理'),
        ('采购管理', '采购订单', 'PROC_ORDER', '采购订单管理'),
        ('库存管理', '库存主数据', 'INV_MASTER', '库存主数据管理'),
        ('库存管理', '库存交易', 'INV_TX', '库存出入库管理'),
        ('销售管理', '销售订单', 'SALES_ORDER', '销售订单管理'),
        ('销售管理', '客户管理', 'CUSTOMER', '客户信息管理'),
        ('财务管理', '应收管理', 'AR', '应收账款管理'),
        ('财务管理', '应付管理', 'AP', '应付账款管理'),
    ]
    for domain_name, sd_name, code, desc in sub_domains:
        domain_id = domain_ids.get(domain_name)
        cursor.execute("""
            INSERT INTO sub_domains (version_id, domain_id, name, code, description, created_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (v1_id, domain_id, sd_name, code, desc, now, 'system', 'system'))
        sub_domain_ids[f"{domain_name}.{sd_name}"] = cursor.lastrowid
        print(f"创建子领域{domain_name}.{sd_name}成功: ID={sub_domain_ids[f'{domain_name}.{sd_name}']}")

    # service_module 列表 + 显式 SM → SD 映射
    # 顺序: 1-2 采购需求, 3-4 采购订单, 5-6 库存主数据, 7-8 库存交易,
    #       9-10 销售订单, 11-12 客户管理, 13-14 应收管理, 15-16 应付管理
    service_modules = [
        ('采购需求', 'PROC_REQ_MNG',    '采购管理.采购需求'),
        ('供应商管理', 'SUPPLIER_MNG',   '采购管理.采购需求'),
        ('采购合同', 'PROC_CONTRACT',    '采购管理.采购订单'),
        ('采购执行', 'PROC_EXEC',        '采购管理.采购订单'),
        ('仓库管理', 'WAREHOUSE_MNG',    '库存管理.库存主数据'),
        ('货位管理', 'LOC_MNG',          '库存管理.库存主数据'),
        ('入库管理', 'INBOUND_MNG',      '库存管理.库存交易'),
        ('出库管理', 'OUTBOUND_MNG',     '库存管理.库存交易'),
        ('订单管理', 'ORDER_MNG',        '销售管理.销售订单'),
        ('价格管理', 'PRICE_MNG',        '销售管理.销售订单'),
        ('客户档案', 'CUSTOMER_PROFILE', '销售管理.客户管理'),
        ('客户信用', 'CUSTOMER_CREDIT',  '销售管理.客户管理'),
        ('应收发票', 'AR_INVOICE',       '财务管理.应收管理'),
        ('收款核销', 'AR_RECEIPT',       '财务管理.应收管理'),
        ('应付发票', 'AP_INVOICE',       '财务管理.应付管理'),
        ('付款计划', 'AP_PAYMENT',       '财务管理.应付管理'),
    ]

    sm_ids = {}
    sm_sub_domain_ids = {}  # sm_id -> sd_id, 供 relationships 分类回填使用
    for sm_name, sm_code, sd_key in service_modules:
        sd_id = sub_domain_ids.get(sd_key)
        if not sd_id:
            print(f"警告: 找不到子领域 {sd_key}，跳过服务模块 {sm_name}")
            continue
        cursor.execute("""
            INSERT INTO service_modules (version_id, sub_domain_id, name, code, description, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (v1_id, sd_id, sm_name, sm_code, '', now, 'system'))
        new_sm_id = cursor.lastrowid
        sm_ids[sm_code] = new_sm_id
        sm_sub_domain_ids[new_sm_id] = sd_id
        print(f"创建服务模块{sm_name}({sm_code})成功: ID={new_sm_id} -> SD={sd_key}")

    business_objects = [
        ('采购申请', 'BO_REQ', '采购申请单，记录采购需求'),
        ('供应商', 'BO_SUPPLIER', '供应商主数据'),
        ('采购合同', 'BO_PROC_CONTRACT', '采购合同信息'),
        ('采购订单', 'BO_PO', '采购订单主表'),
        ('采购订单明细', 'BO_POL', '采购订单明细表'),
        ('仓库', 'BO_WAREHOUSE', '仓库主数据'),
        ('货位', 'BO_LOCATION', '货位主数据'),
        ('库存', 'BO_INVENTORY', '库存余额表'),
        ('库存流水', 'BO_INV_LOG', '库存变动流水'),
        ('入库单', 'BO_INBOUND', '入库单主表'),
        ('入库明细', 'BO_INBOUND_L', '入库单明细'),
        ('出库单', 'BO_OUTBOUND', '出库单主表'),
        ('出库明细', 'BO_OUTBOUND_L', '出库单明细'),
        ('销售订单', 'BO_SO', '销售订单主表'),
        ('销售订单明细', 'BO_SOL', '销售订单明细'),
        ('客户', 'BO_CUSTOMER', '客户主数据'),
        ('客户信用', 'BO_CUST_CREDIT', '客户信用额度'),
        ('价格表', 'BO_PRICE_LIST', '产品价格表'),
        ('销售发票', 'BO_SALES_INV', '销售发票'),
        ('应收发票', 'BO_AR_INV', '应收发票'),
        ('收款单', 'BO_AR_RECEIPT', '收款单'),
        ('应付发票', 'BO_AP_INV', '应付发票'),
        ('付款单', 'BO_AP_PAYMENT', '付款单'),
        ('付款凭单', 'BO_PAYMENT_VOUCHER', '付款凭单'),
        ('付款申请', 'BO_PAYMENT_REQ', '付款申请单'),
    ]

    bo_ids = {}
    for name, code, desc in business_objects:
        # 业务对象 → 服务模块 映射
        # 业务含义：
        #   - BO_REQ（采购申请）属"采购需求"模块 PROC_REQ_MNG
        #   - BO_INV_LOG（库存流水）属"入库管理"模块 INBOUND_MNG
        #   - BO_SALES_INV（销售发票）属"应收发票"模块 AR_INVOICE（因销售发票创建应收）
        sm_code_map = {
            'BO_REQ': 'PROC_REQ_MNG',
            'BO_SUPPLIER': 'SUPPLIER_MNG',
            'BO_PROC_CONTRACT': 'PROC_CONTRACT',
            'BO_PO': 'PROC_EXEC',
            'BO_POL': 'PROC_EXEC',
            'BO_WAREHOUSE': 'WAREHOUSE_MNG',
            'BO_LOCATION': 'LOC_MNG',
            'BO_INVENTORY': 'WAREHOUSE_MNG',
            'BO_INV_LOG': 'INBOUND_MNG',
            'BO_INBOUND': 'INBOUND_MNG',
            'BO_INBOUND_L': 'INBOUND_MNG',
            'BO_OUTBOUND': 'OUTBOUND_MNG',
            'BO_OUTBOUND_L': 'OUTBOUND_MNG',
            'BO_SO': 'ORDER_MNG',
            'BO_SOL': 'ORDER_MNG',
            'BO_CUSTOMER': 'CUSTOMER_PROFILE',
            'BO_CUST_CREDIT': 'CUSTOMER_CREDIT',
            'BO_PRICE_LIST': 'PRICE_MNG',
            'BO_SALES_INV': 'AR_INVOICE',
            'BO_AR_INV': 'AR_INVOICE',
            'BO_AR_RECEIPT': 'AR_RECEIPT',
            'BO_AP_INV': 'AP_INVOICE',
            'BO_AP_PAYMENT': 'AP_PAYMENT',
            'BO_PAYMENT_VOUCHER': 'AP_PAYMENT',
            'BO_PAYMENT_REQ': 'AP_PAYMENT',
        }

        sm_code = sm_code_map.get(code, 'ORDER_MNG')
        sm_id = sm_ids.get(sm_code)

        if sm_id:
            cursor.execute("""
                INSERT INTO business_objects (version_id, service_module_id, code, name, description, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (v1_id, sm_id, code, name, desc, now, 'system'))
            bo_ids[code] = cursor.lastrowid
            print(f"创建业务对象{code}({name})成功: ID={bo_ids[code]}")
        else:
            print(f"警告: 服务模块{sm_code}不存在，跳过业务对象{code}")

    # [v34 fix] 关系数据: (source_code, target_code, rel_code, rel_desc, relation_type, relation_direction)
    #   - rel_code: 关系简称 (Mermaid edge label 显示, 如 PUM01-PUM02-01)
    #   - relation_type: 关系类型 (必须来自 enum: GENERATES/UPDATES/TRIGGERS/REFERENCES)
    #   - relation_direction: 关系方向 (必须来自 enum: PUSH/PULL/BIDIRECTIONAL, 可空)
    relationships = [
        # (source, target, rel_code, description, relation_type, direction)
        ('BO_SUPPLIER', 'BO_REQ', 'PROVIDES', '供应商提供采购申请所需的物料', 'REFERENCES', 'PUSH'),
        ('BO_CUSTOMER', 'BO_SO', 'ORDERS', '客户下达销售订单', 'TRIGGERS', 'PUSH'),
        ('BO_SO', 'BO_SOL', 'CONTAINS', '销售订单包含明细', 'REFERENCES', 'PUSH'),
        ('BO_SOL', 'BO_INVENTORY', 'RESERVES', '订单明细预留库存', 'UPDATES', 'PUSH'),
        ('BO_INVENTORY', 'BO_INV_LOG', 'GENERATES', '库存变动生成流水', 'GENERATES', 'PUSH'),
        ('BO_INV_LOG', 'BO_LOCATION', 'AT', '库存流水记录货位', 'REFERENCES', 'PUSH'),
        ('BO_LOCATION', 'BO_WAREHOUSE', 'LOCATED_AT', '货位位于仓库', 'REFERENCES', 'PUSH'),
        ('BO_WAREHOUSE', 'BO_INVENTORY', 'HOLDS', '仓库持有库存', 'REFERENCES', 'PUSH'),
        ('BO_SUPPLIER', 'BO_PO', 'SUPPLIES', '供应商供货', 'REFERENCES', 'PUSH'),
        ('BO_PO', 'BO_POL', 'CONTAINS', '采购订单包含明细', 'REFERENCES', 'PUSH'),
        ('BO_POL', 'BO_INVENTORY', 'ADDS', '采购入库增加库存', 'UPDATES', 'PUSH'),
        ('BO_PROC_CONTRACT', 'BO_PO', 'GENERATES', '采购合同生成订单', 'GENERATES', 'PUSH'),
        ('BO_SO', 'BO_SALES_INV', 'GENERATES', '销售订单生成发票', 'GENERATES', 'PUSH'),
        ('BO_SALES_INV', 'BO_AR_INV', 'CREATES', '销售发票创建应收', 'GENERATES', 'PUSH'),
        ('BO_CUSTOMER', 'BO_AR_RECEIPT', 'PAYMENTS', '客户付款', 'TRIGGERS', 'PUSH'),
        ('BO_AR_RECEIPT', 'BO_AR_INV', 'RECONCILES', '收款核销应收', 'UPDATES', 'PUSH'),
        ('BO_CUSTOMER', 'BO_CUST_CREDIT', 'HAS', '客户拥有信用额度', 'REFERENCES', 'PUSH'),
        ('BO_CUST_CREDIT', 'BO_SO', 'LIMITS', '信用额度限制订单', 'UPDATES', 'PUSH'),
        ('BO_PRICE_LIST', 'BO_SOL', 'PRICES', '价格表定价', 'REFERENCES', 'PUSH'),
        ('BO_INBOUND', 'BO_INBOUND_L', 'CONTAINS', '入库单包含明细', 'REFERENCES', 'PUSH'),
        ('BO_INBOUND_L', 'BO_INVENTORY', 'INCREASES', '入库增加库存', 'UPDATES', 'PUSH'),
        ('BO_OUTBOUND', 'BO_OUTBOUND_L', 'CONTAINS', '出库单包含明细', 'REFERENCES', 'PUSH'),
        ('BO_OUTBOUND_L', 'BO_INVENTORY', 'DECREASES', '出库减少库存', 'UPDATES', 'PUSH'),
        ('BO_SUPPLIER', 'BO_AP_INV', 'RECEIVES', '供应商收到应付发票', 'REFERENCES', 'PUSH'),
        ('BO_AP_INV', 'BO_PAYMENT_REQ', 'CREATES', '应付发票创建付款申请', 'GENERATES', 'PUSH'),
        ('BO_PAYMENT_REQ', 'BO_PAYMENT_VOUCHER', 'APPROVES', '付款申请审批生成凭单', 'TRIGGERS', 'PUSH'),
        ('BO_PAYMENT_VOUCHER', 'BO_AP_PAYMENT', 'CREATES', '凭单创建付款单', 'GENERATES', 'PUSH'),
        ('BO_AP_PAYMENT', 'BO_SUPPLIER', 'PAYS', '付款单支付供应商', 'TRIGGERS', 'PUSH'),
    ]

    # [v34 fix] 允许同一对 (source, target) 出现多条关系
    # code/relation_code 唯一性: 用 (source_target_idx) 形式, idx 从 01 递增
    # 例: BO_SO -> BO_SOL 出现 2 次, 则 code 分别为 BO_SO_BO_SOL_01 / BO_SO_BO_SOL_02

    # ─── enum 校验 ───
    VALID_RELATION_TYPES = {'GENERATES', 'UPDATES', 'TRIGGERS', 'REFERENCES'}
    VALID_DIRECTIONS = {'PUSH', 'PULL', 'BIDIRECTIONAL'}

    # 注意: 只持久化 source_bo_id + target_bo_id + Type-A 冗余 (source_code/target_code/code)
    # 分类字段 (module_relation, *_name 等) 由 computed_utils.py 运行时 JOIN 计算
    rel_count = 0
    # [v34 fix] 用 dict 统计每个 (source, target) 对应的 idx 计数
    pair_counter = {}
    skipped_invalid_enum = 0
    duplicate_codes = set()
    used_codes = set()

    for rel_tuple in relationships:
        # 兼容旧 4 元组 (无 enum)
        if len(rel_tuple) == 4:
            source_code, target_code, rel_code, rel_desc = rel_tuple
            relation_type = 'RELATION'  # 历史兜底
            relation_direction = None
        elif len(rel_tuple) == 6:
            source_code, target_code, rel_code, rel_desc, relation_type, relation_direction = rel_tuple
        else:
            print(f"  ⚠ 跳过关系 (元组长度错误 {len(rel_tuple)}): {rel_tuple}")
            continue

        # [v34] enum 校验
        if relation_type not in VALID_RELATION_TYPES:
            print(f"  ⚠ 跳过关系 (relation_type '{relation_type}' 不在 enum 中): {rel_code} {source_code}->{target_code}")
            skipped_invalid_enum += 1
            continue
        if relation_direction is not None and relation_direction not in VALID_DIRECTIONS:
            print(f"  ⚠ 跳过关系 (relation_direction '{relation_direction}' 不在 enum 中): {rel_code} {source_code}->{target_code}")
            skipped_invalid_enum += 1
            continue

        source_id = bo_ids.get(source_code)
        target_id = bo_ids.get(target_code)
        if source_id and target_id:
            # [v34 fix] code/relation_code 唯一: 用 idx 计数器
            pair_key = (source_code, target_code)
            pair_counter[pair_key] = pair_counter.get(pair_key, 0) + 1
            idx = pair_counter[pair_key]
            # 格式: {source}_{target}_{idx:02d}, e.g. BO_SO_BO_SOL_01
            rel_unique_code = f"{source_code}_{target_code}_{idx:02d}"

            # 二次校验: 整库唯一
            if rel_unique_code in used_codes:
                duplicate_codes.add(rel_unique_code)
                print(f"  ⚠ 重复 code: {rel_unique_code}")
                continue
            used_codes.add(rel_unique_code)

            cursor.execute("""
                INSERT INTO relationships (version_id, source_bo_id, target_bo_id, source_code, target_code, code, relation_code, relation_type, relation_direction, relation_desc, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v1_id, source_id, target_id, source_code, target_code, rel_unique_code, rel_code, relation_type, relation_direction, rel_desc, now, 'system'))
            rel_count += 1
            dir_str = f", {relation_direction}" if relation_direction else ""
            print(f"创建关系{rel_code}{dir_str}: {source_code} -> {target_code} (code={rel_unique_code})")

    if skipped_invalid_enum > 0:
        print(f"  ⚠ 共跳过 {skipped_invalid_enum} 条 (enum 校验失败)")
    if duplicate_codes:
        print(f"  ⚠ 检测到重复 code: {duplicate_codes}")

    conn.commit()
    conn.close()

    print("\n" + "="*50)
    print("[OK] 测试数据生成完成!")
    print(f"产品: 1个")
    print(f"版本: 2个")
    print(f"领域: {len(domains)}个")
    print(f"子领域: {len(sub_domains)}个")
    print(f"服务模块: {len(sm_ids)}个")
    print(f"业务对象: {len(bo_ids)}个")
    print(f"关系: {rel_count}个")
    print("="*50)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='数据库初始化和测试数据生成脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python init_and_seed.py                  # 安全模式，会提示确认
  python init_and_seed.py --force         # 强制模式，直接删除并重建
  python init_and_seed.py --yes           # 静默模式，自动确认
        """
    )
    parser.add_argument('--force', '-f', action='store_true',
                        help='强制模式: 直接删除现有数据库，无需确认')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='静默模式: 自动确认所有提示')

    args = parser.parse_args()

    force_mode = args.force or args.yes

    db_path = init_database(force=force_mode)
    if db_path:
        insert_data()
