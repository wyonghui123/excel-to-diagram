import requests
import json

BASE_URL = "http://localhost:3010/api/v2"

print("="*60)
print("测试后端 API - 树形结构数据诊断 (v2 API)")
print("="*60)

# 登录
print("\n[1] 登录...")
login_response = requests.post(
    "http://localhost:3010/api/v1/auth/login",
    data=json.dumps({"username": "admin", "password": "admin123"}),
    headers={"Content-Type": "application/json"}
)
print(f"登录状态码: {login_response.status_code}")

if login_response.status_code == 200:
    login_data = login_response.json()
    token = login_data.get('data', {}).get('token')
    headers = {"Authorization": f"Bearer {token}"}
    
    # 获取产品列表 - 使用 v2 API
    print("\n[2] 获取产品列表 (v2/bo/product)...")
    products_response = requests.get(
        f"{BASE_URL}/bo/product",
        headers=headers
    )
    print(f"状态码: {products_response.status_code}")
    products_data = products_response.json()
    print(f"响应: {json.dumps(products_data, ensure_ascii=False)[:500]}")
    
    raw_products = products_data.get('data', {})
    if isinstance(raw_products, dict):
        products = raw_products.get('items', []) or []
    elif isinstance(raw_products, list):
        products = raw_products
    else:
        products = []
    
    print(f"\n产品数量: {len(products)}")
    
    if products:
        first_product = products[0]
        print(f"第一个产品: {json.dumps(first_product, ensure_ascii=False)}")
        product_id = first_product.get('id')
        
        # 获取版本列表
        print("\n[3] 获取版本列表...")
        versions_response = requests.get(
            f"{BASE_URL}/bo/version",
            params={"product_id": product_id},
            headers=headers
        )
        versions_data = versions_response.json()
        
        raw_versions = versions_data.get('data', {})
        if isinstance(raw_versions, dict):
            versions = raw_versions.get('items', []) or []
        elif isinstance(raw_versions, list):
            versions = raw_versions
        else:
            versions = []
        
        print(f"版本数量: {len(versions)}")
        
        if versions:
            first_version = versions[0]
            print(f"第一个版本: {json.dumps(first_version, ensure_ascii=False)}")
            version_id = first_version.get('id')
            
            # 获取所有层级数据
            print("\n[4] 获取 domain 数据...")
            domain_response = requests.get(
                f"{BASE_URL}/bo/domain",
                params={"version_id": version_id, "pageSize": 1000},
                headers=headers
            )
            domain_data = domain_response.json()
            raw_domains = domain_data.get('data', {})
            domains = raw_domains.get('items', []) if isinstance(raw_domains, dict) else raw_domains
            print(f"Domain 数量: {len(domains)}")
            if domains:
                print(f"第一个 Domain: {json.dumps(domains[0], ensure_ascii=False)}")
            
            print("\n[5] 获取 sub_domain 数据...")
            sd_response = requests.get(
                f"{BASE_URL}/bo/sub_domain",
                params={"version_id": version_id, "pageSize": 1000},
                headers=headers
            )
            sd_data = sd_response.json()
            raw_sd = sd_data.get('data', {})
            sub_domains = raw_sd.get('items', []) if isinstance(raw_sd, dict) else raw_sd
            print(f"Sub-domain 数量: {len(sub_domains)}")
            if sub_domains:
                print(f"第一个 Sub-domain: {json.dumps(sub_domains[0], ensure_ascii=False)}")
                sd_with_domain_id = sum(1 for s in sub_domains if s.get('domain_id'))
                print(f"有 domain_id 的 Sub-domain: {sd_with_domain_id}")
            
            print("\n[6] 获取 service_module 数据...")
            sm_response = requests.get(
                f"{BASE_URL}/bo/service_module",
                params={"version_id": version_id, "pageSize": 5000},
                headers=headers
            )
            sm_data = sm_response.json()
            raw_sm = sm_data.get('data', {})
            service_modules = raw_sm.get('items', []) if isinstance(raw_sm, dict) else raw_sm
            print(f"Service Module 数量: {len(service_modules)}")
            if service_modules:
                print(f"第一个 Service Module: {json.dumps(service_modules[0], ensure_ascii=False)}")
                sm_with_sd_id = sum(1 for s in service_modules if s.get('sub_domain_id'))
                print(f"有 sub_domain_id 的 Service Module: {sm_with_sd_id}")
            
            print("\n[7] 获取 business_object 数据...")
            bo_response = requests.get(
                f"{BASE_URL}/bo/business_object",
                params={"version_id": version_id, "pageSize": 5000},
                headers=headers
            )
            bo_data = bo_response.json()
            raw_bo = bo_data.get('data', {})
            business_objects = raw_bo.get('items', []) if isinstance(raw_bo, dict) else raw_bo
            print(f"Business Object 数量: {len(business_objects)}")
            if business_objects:
                print(f"第一个 Business Object: {json.dumps(business_objects[0], ensure_ascii=False)}")
                bo_with_sm_id = sum(1 for b in business_objects if b.get('service_module_id'))
                print(f"有 service_module_id 的 Business Object: {bo_with_sm_id}")
            
            print("\n" + "="*60)
            print("总结:")
            print("="*60)
            print(f"Domains: {len(domains)}")
            print(f"Sub-domains: {len(sub_domains)}")
            print(f"Service Modules: {len(service_modules)}")
            print(f"Business Objects: {len(business_objects)}")
            
            # 检查数据关联
            if len(sub_domains) > 0 and sd_with_domain_id == 0:
                print("\n[X] 警告: Sub-domains 没有 domain_id 字段!")
                print("   这可能是后端数据问题，或者字段名不同")
            if len(service_modules) > 0 and sm_with_sd_id == 0:
                print("\n[X] 警告: Service Modules 没有 sub_domain_id 字段!")
            if len(business_objects) > 0 and bo_with_sm_id == 0:
                print("\n[X] 警告: Business Objects 没有 service_module_id 字段!")
else:
    print(f"登录失败: {login_response.text}")
