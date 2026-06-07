# 测试工具使用指南

## 概述

本目录包含一系列测试优化工具，用于重构和优化测试代码。

---

## 目录结构

```
meta/tests/
├── shared/                           # 共享模块
│   ├── __init__.py
│   ├── base.py                     # 测试基类
│   ├── fixtures.py                 # 共享 fixtures
│   ├── fixtures_api.py            # API fixtures
│   └── mocks.py                    # Mock 类
│
├── split_*.py                      # 测试文件拆分脚本
├── migrate_*.py                   # 框架迁移脚本
├── analyze_tests.py                # 测试分析工具
└── TESTING_TOOLS_GUIDE.md          # 本文档
```

---

## 1. 共享模块

### shared/base.py - 测试基类

```python
from meta.tests.shared.base import AuthenticatedTestCase, IntegrationTestCase

# unittest 风格
class TestMyFeature(AuthenticatedTestCase):
    def test_something(self):
        response = self.client.get('/api/v2/bo/user', headers=self.headers)
        assert response.status_code == 200

# pytest 风格
class TestMyFeature(IntegrationTestCase):
    @pytest.fixture(autouse=True)
    def setup(self):
        ...
```

### shared/fixtures.py - 共享 fixtures

```python
from meta.tests.shared.fixtures import admin_headers, random_suffix

def test_api(admin_headers):
    response = api_client.get('/api/v2/bo/user', headers=admin_headers)
    assert response.status_code == 200
```

### shared/mocks.py - Mock 类

```python
from meta.tests.shared.mocks import MockActionContext, MockResult

context = MockActionContext(action='create', object_type='user')
result = MockResult(success=True, data={'id': 1})
```

### shared/fixtures_api.py - API fixtures

```python
from meta.tests.shared.fixtures_api import api_client, admin_headers

def test_api(api_client, admin_headers):
    response = api_client.get('/api/v2/bo/user', headers=admin_headers)
```

---

## 2. 拆分脚本

### split_import_export_tests.py

将 `test_import_export_api.py` 拆分为多个小型文件。

```bash
# 查看拆分计划
python split_import_export_tests.py

# 执行拆分
python split_import_export_tests.py --execute
```

**拆分后的文件：**
- test_import_export_api_config.py (配置测试)
- test_import_export_api_core.py (核心 API 测试)
- test_import_export_service.py (服务层测试)
- test_import_export_relationship.py (关系导出测试)
- test_import_export_model.py (模型测试)

### split_bo_api_tests.py

将 `test_bo_api.py` 拆分为 V1/V2 两个文件。

```bash
# 查看拆分计划
python split_bo_api_tests.py

# 执行拆分
python split_bo_api_tests.py --execute
```

**拆分后的文件：**
- test_bo_api_v2.py (V2 API 测试)
- test_bo_api_v1.py (V1 API 测试)

### split_import_export_model.py

将 `test_import_export_model.py` 拆分为多个小型文件。

```bash
# 查看拆分计划
python split_import_export_model.py

# 执行拆分
python split_import_export_model.py --execute
```

**拆分后的文件：**
- test_import_export_annotation.py
- test_import_export_excel_structure.py
- test_import_export_data_integrity.py
- test_import_export_templates.py
- test_import_export_options.py
- test_import_export_business_key.py
- test_import_export_field_control.py

---

## 3. 迁移脚本

### migrate_to_pytest.py

单文件迁移工具。

```bash
# 查看迁移计划
python migrate_to_pytest.py test_file.py

# 执行迁移
python migrate_to_pytest.py test_file.py --execute
```

### batch_migrate_to_pytest.py

批量迁移工具。

```bash
# 查看迁移计划
python batch_migrate_to_pytest.py

# 执行迁移
python batch_migrate_to_pytest.py --execute
```

### unified_migrate_to_pytest.py

统一迁移工具，可处理所有测试文件。

```bash
# 查看迁移计划
python unified_migrate_to_pytest.py

# 执行迁移
python unified_migrate_to_pytest.py --execute
```

**迁移规则：**

| Before (unittest) | After (pytest) |
|-------------------|----------------|
| `self.assertEqual(a, b)` | `assert a == b` |
| `self.assertTrue(x)` | `assert x` |
| `self.assertFalse(x)` | `assert not x` |
| `self.assertIn(a, b)` | `assert a in b` |
| `self.assertIsNone(x)` | `assert x is None` |
| `class TestXxx(TestCase)` | `class TestXxx:` |
| `self.skipTest(...)` | `pytest.skip(...)` |

---

## 4. 分析工具

### analyze_tests.py

分析测试目录并生成优化建议报告。

```bash
# 生成报告到控制台
python analyze_tests.py

# 生成报告到文件
python analyze_tests.py --output test_analysis.md
```

**报告内容：**
- 统计摘要
- 需要优化的文件列表
- 大文件列表 (>500行)
- 未迁移的 unittest.TestCase 文件

---

## 5. 目录重组脚本

### migrate_directory_structure.py

按业务域重组测试目录。

```bash
# 查看重组计划
python migrate_directory_structure.py

# 执行重组
python migrate_directory_structure.py --execute
```

**目标目录结构：**
```
meta/tests/
├── api/            # API 端点测试
├── services/      # 服务层测试
├── integration/    # 集成测试
├── interceptors/  # 拦截器测试
└── performance/   # 性能测试
```

---

## 6. 使用示例

### 完整优化流程

```bash
# 1. 分析当前状态
python analyze_tests.py --output analysis.md

# 2. 拆分大文件
python split_import_export_tests.py --execute
python split_bo_api_tests.py --execute
python split_import_export_model.py --execute

# 3. 迁移到 pytest
python unified_migrate_to_pytest.py --execute

# 4. 重组目录结构
python migrate_directory_structure.py --execute

# 5. 再次分析验证
python analyze_tests.py --output final_analysis.md
```

### 单文件优化流程

```bash
# 1. 分析单个文件
python analyze_tests.py --dir test_file.py

# 2. 迁移到 pytest
python migrate_to_pytest.py test_file.py --execute

# 3. 验证语法
python -m py_compile test_file.py
```

---

## 7. 注意事项

### 1. 备份原始文件

在执行拆分或迁移前，建议备份原始文件：

```bash
# 备份
cp test_file.py test_file.py.bak

# 如需恢复
mv test_file.py.bak test_file.py
```

### 2. 验证语法

执行迁移后，必须验证语法：

```bash
python -m py_compile test_file.py
```

### 3. 运行测试

验证迁移后必须运行测试：

```bash
python -m pytest test_file.py -v
```

### 4. 处理语法警告

迁移脚本可能产生语法警告（如 `"is not"` 表达式问题），需要手动修复：

```python
# 修复前
assert value, "message" is not None

# 修复后
assert value is not None, "message"
```

---

## 8. 常见问题

### Q1: 迁移后 self.client 报错？

需要在测试类中添加 `client_and_headers` fixture：

```python
@pytest.fixture
def client_and_headers():
    from meta.tests.conftest import get_shared_app
    app, client = get_shared_app()
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    user = UserInfo(user_id='1', username='admin', ...)
    token, _ = TokenService.create_token(user)
    headers = {'Authorization': f'Bearer {token}', ...}
    return client, headers

def test_api(self, client_and_headers):
    client, headers = client_and_headers
    response = client.get('/api/v2/bo/user', headers=headers)
```

### Q2: 如何使用共享模块？

```python
# 在测试文件顶部添加
from meta.tests.shared.fixtures import admin_headers
from meta.tests.shared.mocks import MockActionContext

# 使用
def test_something(admin_headers):
    ...
```

### Q3: 如何保持向后兼容？

如果需要保持与旧代码的兼容性：

```python
# 使用 conftest.py 自动加载
from meta.tests.conftest import get_shared_app

# 或直接从 shared 导入
from meta.tests.shared.fixtures import admin_headers
```

---

## 9. 相关文档

- [测试优化规格文档](../../docs/testing/test_optimization_spec.md)
- [pytest 官方文档](https://docs.pytest.org/)
