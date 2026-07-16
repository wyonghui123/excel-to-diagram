# -*- coding: utf-8 -*-
"""
测试数据生成脚本

生成供应链系统的完整测试数据：
- 1个产品线
- 2个版本
- 4个领域
- 8个子领域
- 12个服务模块
- 30+个业务对象
- 50+个关系
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.services.manage_service import ManageService, CreateRequest


def get_ms():
    ds = get_data_source('sqlite', db_path='meta/architecture.db')
    return ManageService(ds)


def create_product(ms, name, description, is_active=True):
    req = CreateRequest(
        object_type='product',
        data={
            'name': name,
            'description': description,
            'is_active': is_active,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建产品失败: {result.error}")
    return None


def create_version(ms, product_id, name, description, status='active'):
    req = CreateRequest(
        object_type='version',
        data={
            'product_id': product_id,
            'name': name,
            'description': description,
            'status': status,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建版本失败: {result.error}")
    return None


def create_domain(ms, version_id, name, description, code):
    req = CreateRequest(
        object_type='domain',
        data={
            'version_id': version_id,
            'name': name,
            'description': description,
            'code': code,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建领域失败: {result.error}")
    return None


def create_sub_domain(ms, version_id, domain_id, name, code):
    req = CreateRequest(
        object_type='sub_domain',
        data={
            'version_id': version_id,
            'domain_id': domain_id,
            'name': name,
            'code': code,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建子领域失败: {result.error}")
    return None


def create_service_module(ms, version_id, sub_domain_id, name, code):
    req = CreateRequest(
        object_type='service_module',
        data={
            'version_id': version_id,
            'sub_domain_id': sub_domain_id,
            'name': name,
            'code': code,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建服务模块失败: {result.error}")
    return None


def create_business_object(ms, version_id, service_module_id, code, name, description=''):
    req = CreateRequest(
        object_type='business_object',
        data={
            'version_id': version_id,
            'service_module_id': service_module_id,
            'code': code,
            'name': name,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建业务对象失败: {result.error}")
    return None


def create_relationship(ms, version_id, source_bo_id, target_bo_id, source_code, target_code, relation_code, relation_desc):
    req = CreateRequest(
        object_type='relationship',
        data={
            'version_id': version_id,
            'source_bo_id': source_bo_id,
            'target_bo_id': target_bo_id,
            'source_code': source_code,
            'target_code': target_code,
            'relation_code': relation_code,
            'relation_desc': relation_desc,
            'created_by': 'system',
            'updated_by': 'system',
        }
    )
    result = ms.create(req)
    if result.success:
        return result.data.get('id')
    print(f"创建关系失败: {result.error}")
    return None


def generate_test_data():
    print("开始生成测试数据...")
    ms = get_ms()

    product_id = create_product(
        ms,
        name='供应链管理系统',
        description='企业供应链管理系统，包含采购、库存、销售等核心模块'
    )
    if not product_id:
        print("创建产品失败，退出")
        return
    print(f"创建产品成功: ID={product_id}")

    v1_id = create_version(
        ms,
        product_id=product_id,
        name='v1.0',
        description='第一版供应链系统',
        status='active'
    )
    print(f"创建版本v1.0成功: ID={v1_id}")

    v2_id = create_version(
        ms,
        product_id=product_id,
        name='v2.0',
        description='第二版供应链系统，增加了财务模块',
        status='development'
    )
    print(f"创建版本v2.0成功: ID={v2_id}")

    domains_data = [
        ('采购管理', 'PROCUREMENT', '采购相关业务领域'),
        ('库存管理', 'INVENTORY', '库存相关业务领域'),
        ('销售管理', 'SALES', '销售相关业务领域'),
        ('财务管理', 'FINANCE', '财务相关业务领域'),
    ]
    domain_ids = {}
    for name, code, desc in domains_data:
        domain_id = create_domain(ms, v1_id, name, desc, code)
        domain_ids[name] = domain_id
        print(f"创建领域{name}成功: ID={domain_id}")

    sub_domains_data = [
        ('采购管理', '采购需求', 'PROC_REQ', '采购需求管理'),
        ('采购管理', '采购订单', 'PROC_ORDER', '采购订单管理'),
        ('库存管理', '库存主数据', 'INV_MASTER', '库存主数据管理'),
        ('库存管理', '库存交易', 'INV_TX', '库存出入库管理'),
        ('销售管理', '销售订单', 'SALES_ORDER', '销售订单管理'),
        ('销售管理', '客户管理', 'CUSTOMER', '客户信息管理'),
        ('财务管理', '应收管理', 'AR', '应收账款管理'),
        ('财务管理', '应付管理', 'AP', '应付账款管理'),
    ]
    sub_domain_ids = {}
    for domain_name, sd_name, code, desc in sub_domains_data:
        domain_id = domain_ids.get(domain_name)
        if domain_id:
            sd_id = create_sub_domain(ms, v1_id, domain_id, sd_name, code)
            sub_domain_ids[f"{domain_name}.{sd_name}"] = sd_id
            print(f"创建子领域{domain_name}.{sd_name}成功: ID={sd_id}")

    service_modules_data = [
        ('采购管理.采购需求', '采购申请', 'PROC_REQ_MNG'),
        ('采购管理.采购需求', '供应商管理', 'SUPPLIER_MNG'),
        ('采购管理.采购订单', '采购合同', 'PROC_CONTRACT'),
        ('采购管理.采购订单', '采购执行', 'PROC_EXEC'),
        ('库存管理.库存主数据', '仓库管理', 'WAREHOUSE_MNG'),
        ('库存管理.库存主数据', '货位管理', 'LOC_MNG'),
        ('库存管理.库存交易', '入库管理', 'INBOUND_MNG'),
        ('库存管理.库存交易', '出库管理', 'OUTBOUND_MNG'),
        ('销售管理.销售订单', '订单管理', 'ORDER_MNG'),
        ('销售管理.销售订单', '价格管理', 'PRICE_MNG'),
        ('销售管理.客户管理', '客户档案', 'CUSTOMER_PROFILE'),
        ('销售管理.客户管理', '客户信用', 'CUSTOMER_CREDIT'),
        ('财务管理.应收管理', '应收发票', 'AR_INVOICE'),
        ('财务管理.应收管理', '收款核销', 'AR_RECEIPT'),
        ('财务管理.应付管理', '应付发票', 'AP_INVOICE'),
        ('财务管理.应付管理', '付款计划', 'AP_PAYMENT'),
    ]
    bo_codes = {}
    for sd_key, sm_name, code in service_modules_data:
        sd_id = sub_domain_ids.get(sd_key)
        if sd_id:
            sm_id = create_service_module(ms, v1_id, sd_id, sm_name, code)
            print(f"创建服务模块{sm_name}成功: ID={sm_id}")

    bo_data = [
        ('采购申请', 'BO_REQ', '采购申请单，记录采购需求'),
        ('供应商', 'BO_SUPPLIER', '供应商主数据'),
        ('采购合同', 'BO_PROC_CONTRACT', '采购合同信息'),
        ('采购订单', 'BO_PO', '采购订单主表'),
        ('采购订单明细', 'BO_POL', '采购订单明细表'),
        ('仓库', 'BO_WAREHOUSE', '仓库主数据'),
        ('货位', 'BO_LOCATION', '货位主数据'),
        ('库位', 'BO_STORAGE_BIN', '库位信息'),
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

    sm_mapping = {
        'BO_REQ': 'PROC_REQ_MNG',
        'BO_SUPPLIER': 'SUPPLIER_MNG',
        'BO_PROC_CONTRACT': 'PROC_CONTRACT',
        'BO_PO': 'PROC_EXEC',
        'BO_POL': 'PROC_EXEC',
        'BO_WAREHOUSE': 'WAREHOUSE_MNG',
        'BO_LOCATION': 'LOC_MNG',
        'BO_STORAGE_BIN': 'LOC_MNG',
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
        'BO_SALES_INV': 'ORDER_MNG',
        'BO_AR_INV': 'AR_INVOICE',
        'BO_AR_RECEIPT': 'AR_RECEIPT',
        'BO_AP_INV': 'AP_INVOICE',
        'BO_AP_PAYMENT': 'AP_PAYMENT',
        'BO_PAYMENT_VOUCHER': 'AP_PAYMENT',
        'BO_PAYMENT_REQ': 'AP_PAYMENT',
    }

    for name, code, desc in bo_data:
        sm_code = sm_mapping.get(code, 'ORDER_MNG')
        sm_id = None
        for sd_key, sm_name, sc in service_modules_data:
            if sc == sm_code:
                sd_id = sub_domain_ids.get(sd_key)
                if sd_id:
                    req = CreateRequest(
                        object_type='service_module',
                        data={'version_id': v1_id, 'sub_domain_id': sd_id, 'name': sm_name, 'code': sc}
                    )
                    sm_result = ms.create(req)
                    if sm_result.success:
                        sm_id = sm_result.data.get('id')
                    break
        if not sm_id:
            print(f"获取服务模块{sm_code}失败，跳过业务对象{code}")
            continue
        bo_id = create_business_object(ms, v1_id, sm_id, code, name, desc)
        if bo_id:
            bo_codes[code] = bo_id
            print(f"创建业务对象{code}成功: ID={bo_id}")

    relationships = [
        ('BO_SUPPLIER', 'BO_REQ', 'PROVIDES', '供应商提供采购申请所需的物料'),
        ('BO_CUSTOMER', 'BO_SO', 'ORDERS', '客户下达销售订单'),
        ('BO_SO', 'BO_SOL', 'CONTAINS', '销售订单包含明细'),
        ('BO_SOL', 'BO_INVENTORY', 'RESERVES', '订单明细预留库存'),
        ('BO_INVENTORY', 'BO_INV_LOG', 'GENERATES', '库存变动生成流水'),
        ('BO_INV_LOG', 'BO_LOCATION', 'AT', '库存流水记录货位'),
        ('BO_LOCATION', 'BO_STORAGE_BIN', 'LOCATED_AT', '货位位于库位'),
        ('BO_WAREHOUSE', 'BO_INVENTORY', 'HOLDS', '仓库持有库存'),
        ('BO_WAREHOUSE', 'BO_LOCATION', 'CONTAINS', '仓库包含货位'),
        ('BO_SUPPLIER', 'BO_PO', 'SUPPLIES', '供应商供货'),
        ('BO_PO', 'BO_POL', 'CONTAINS', '采购订单包含明细'),
        ('BO_POL', 'BO_INVENTORY', 'ADDS', '采购入库增加库存'),
        ('BO_PROC_CONTRACT', 'BO_PO', 'GENERATES', '采购合同生成订单'),
        ('BO_SO', 'BO_SALES_INV', 'GENERATES', '销售订单生成发票'),
        ('BO_SALES_INV', 'BO_AR_INV', 'CREATES', '销售发票创建应收'),
        ('BO_CUSTOMER', 'BO_AR_RECEIPT', 'PAYMENTS', '客户付款'),
        ('BO_AR_RECEIPT', 'BO_AR_INV', 'RECONCILES', '收款核销应收'),
        ('BO_CUSTOMER', 'BO_CUST_CREDIT', 'HAS', '客户拥有信用额度'),
        ('BO_CUST_CREDIT', 'BO_SO', 'LIMITS', '信用额度限制订单'),
        ('BO_PRICE_LIST', 'BO_SOL', 'PRICES', '价格表定价'),
        ('BO_INBOUND', 'BO_INBOUND_L', 'CONTAINS', '入库单包含明细'),
        ('BO_INBOUND_L', 'BO_INVENTORY', 'INCREASES', '入库增加库存'),
        ('BO_OUTBOUND', 'BO_OUTBOUND_L', 'CONTAINS', '出库单包含明细'),
        ('BO_OUTBOUND_L', 'BO_INVENTORY', 'DECREASES', '出库减少库存'),
        ('BO_SUPPLIER', 'BO_AP_INV', 'RECEIVES', '供应商收到应付发票'),
        ('BO_AP_INV', 'BO_PAYMENT_REQ', 'CREATES', '应付发票创建付款申请'),
        ('BO_PAYMENT_REQ', 'BO_PAYMENT_VOUCHER', 'APPROVES', '付款申请审批生成凭单'),
        ('BO_PAYMENT_VOUCHER', 'BO_AP_PAYMENT', 'CREATES', '凭单创建付款单'),
        ('BO_AP_PAYMENT', 'BO_SUPPLIER', 'PAYS', '付款单支付供应商'),
        ('BO_AR_INV', 'BO_AR_RECEIPT', 'MATCHES', '应收与收款匹配'),
        ('BO_INVENTORY', 'BO_WAREHOUSE', 'LOCATED_IN', '库存在仓库中'),
        ('BO_SO', 'BO_PRICE_LIST', 'USES', '销售订单使用价格表'),
        ('BO_REQ', 'BO_PROC_CONTRACT', 'LEADS_TO', '采购申请引发合同'),
        ('BO_PROC_CONTRACT', 'BO_SUPPLIER', 'WITH', '合同与供应商签订'),
    ]

    for source_code, target_code, rel_code, rel_desc in relationships:
        source_id = bo_codes.get(source_code)
        target_id = bo_codes.get(target_code)
        if source_id and target_id:
            rel_id = create_relationship(
                ms, v1_id, source_id, target_id,
                source_code, target_code, rel_code, rel_desc
            )
            if rel_id:
                print(f"创建关系{source_code}->{target_code}({rel_code})成功: ID={rel_id}")

    print("\n" + "="*50)
    print("测试数据生成完成!")
    print(f"产品: 1个")
    print(f"版本: 2个")
    print(f"领域: {len(domains_data)}个")
    print(f"子领域: {len(sub_domains_data)}个")
    print(f"服务模块: {len(service_modules_data)}个")
    print(f"业务对象: {len(bo_data)}个")
    print(f"关系: {len(relationships)}个")
    print("="*50)


if __name__ == '__main__':
    generate_test_data()
