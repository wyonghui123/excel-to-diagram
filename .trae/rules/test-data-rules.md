---
alwaysApply: false
description: "测试数据管理规范：Factory 模式、cleanup、fixture 使用"
globs: "meta/tests/**/*,meta/tests/factories/**/*"
---

# 测试数据管理规范

> **智能体必须使用有效的测试数据，禁止猜测或硬编码产品/版本名称。**

## 测试数据获取方式（优先级从高到低）

| 优先级 | 方式 | 适用场景 | 说明 |
|--------|------|---------|------|
| 1 | `test_data_inventory.json` | 所有测试 | 静态清单，记录所有可用的测试数据 |
| 2 | `valid_product` / `valid_version` fixture | pytest 测试 | 自动选择有数据的产品/版本 |
| 3 | API 探测 | PlaywrightCLI 测试 | 动态查询可用的产品/版本 |
| 4 | 数据库查询 | 后端测试 | 直接查询数据库 |

## 测试数据清单文件

**位置**：`meta/tests/test_data_inventory.json`

**格式**：
```json
{
  "products": [
    {
      "id": 1,
      "name": "供应链管理系统",
      "code": "SCM",
      "has_data": true,
      "versions": [
        {"id": 1, "name": "v1.0", "has_domains": true, "domain_count": 3},
        {"id": 2, "name": "v2.0", "has_domains": true, "domain_count": 5}
      ],
      "recommended_for_testing": true
    }
  ],
  "recommended": {
    "product": {"id": 1, "name": "供应链管理系统"},
    "version": {"id": 2, "name": "v2.0"}
  }
}
```

**智能体使用方式**：
```python
# [X] 错误：硬编码产品名称
product_name = "测试产品_TEST_PROD_DBBCAB"  # 可能没有数据

# [OK] 正确：从清单获取
import json
with open('meta/tests/test_data_inventory.json') as f:
    inventory = json.load(f)
product = inventory['recommended']['product']
product_name = product['name']  # "供应链管理系统"
```

## pytest fixture 使用

```python
# 在测试中使用 fixture
def test_product_selection(valid_product, valid_version):
    # valid_product 自动选择有数据的产品
    # valid_version 自动选择有数据的版本
    assert valid_product['has_data'] == True
    assert valid_version['has_domains'] == True

# fixture 定义在 meta/tests/shared/fixtures_v2.py
```

## PlaywrightCLI 使用

```python
# 在 PlaywrightCLI 测试中
with PlaywrightCLI() as cli:
    # 方法 1：读取清单
    inventory = cli.get_test_data_inventory()
    product = inventory['recommended']['product']
    
    # 方法 2：API 探测
    products = cli.request('/api/v2/bo/product?page_size=100')
    valid_products = [p for p in products['data']['items'] 
                      if p.get('version_count', 0) > 0]
    
    # 选择第一个有版本的产品
    if valid_products:
        product = valid_products[0]
```

## 测试数据验证流程

```
测试开始
  ↓
读取 test_data_inventory.json
  ↓
清单存在？
  ├─ 是 → 使用清单中的 recommended 数据
  └─ 否 → API 探测 / 数据库查询
           ↓
       找到有数据的产品/版本？
           ├─ 是 → 使用找到的数据
           └─ 否 → pytest.skip("No valid test data")
                   或 创建测试数据（generate_test_data.py）
```

## 测试数据创建

如果测试数据不存在，使用以下脚本创建：

```bash
# 创建完整的测试数据
python meta/scripts/generate_test_data.py

# 或初始化基础测试数据
python meta/dev/init_test_data.py
```

## 禁止行为

| 禁止 | 后果 |
|------|------|
| 硬编码产品名称 `"测试产品_XXX"` | 可能选择空数据的产品，测试失败 |
| 猜测产品 ID `product_id = 1` | 可能不存在或没有数据 |
| 不验证数据可用性就测试 | 测试失败后难以诊断原因 |
| 选择第一个产品就测试 | 第一个产品可能没有数据 |

## 行业最佳实践参考

| 实践 | 说明 |
|------|------|
| Worker-scoped fixtures | 为每个 worker 创建唯一数据，避免并发冲突 |
| Factory pattern | `UserFactory.createDefault()` 自动填充默认值 |
| Fixture hierarchy | `authenticatedUser`, `cartWithThreeItems` 代表业务前置条件 |
| Test data strategies | Create-Destroy / Transaction Rollback / DB Snapshots |
