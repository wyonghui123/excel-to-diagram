# 测试编写指南和最佳实践

## 文档信息
- **版本**: v1.0.0
- **创建日期**: 2026-05-29
- **适用范围**: `meta/tests/` 目录下的所有测试文件
- **维护者**: QA团队 + 开发团队

---

## 1. 测试文件命名规范

### 1.1 文件命名格式

```
test_<module>_<feature>.py
```

**示例**:
- `test_auth_api.py` - 认证API测试
- `test_bo_api.py` - 业务对象API测试
- `test_data_permission_api.py` - 数据权限API测试
- `test_boundary_conditions.py` - 边界条件测试
- `test_concurrent_operations.py` - 并发操作测试

### 1.2 文件组织结构

```
meta/tests/
├── conftest.py                    # 根级Fixture配置
├── conftest_common.py             # 公共Fixture库
├── test_<module>_api.py           # API层测试
├── test_<module>_service.py       # 服务层测试
├── test_<module>_integration.py   # 集成测试
├── test_boundary_conditions.py    # 边界条件测试
├── test_concurrent_operations.py  # 并发测试
└── test_transaction_consistency.py # 事务一致性测试
```

---

## 2. 测试类命名规范

### 2.1 类命名格式

```python
class Test<Feature><Type>(unittest.TestCase):
    """
    [TEST CLASS] 测试类描述
    [DESCRIPTION] 详细描述测试内容和范围
    """
```

**示例**:
```python
class TestUserAuthentication(unittest.TestCase):
    """
    [TEST CLASS] 用户认证测试
    [DESCRIPTION] 测试用户登录、登出、token验证等功能
    """

class TestNullAndEmptyValues(unittest.TestCase):
    """
    [TEST CLASS] 空值和Null值测试
    [DESCRIPTION] 测试系统对空值、null值、空字符串的处理能力
    """
```

### 2.2 测试类型分类

| 类型 | 命名前缀 | 描述 |
|------|---------|------|
| API测试 | TestXxxAPI | 测试API端点行为 |
| 服务测试 | TestXxxService | 测试服务层逻辑 |
| 集成测试 | TestXxxIntegration | 测试模块间集成 |
| 边界测试 | TestXxxBoundary | 测试边界条件 |
| 并发测试 | TestXxxConcurrent | 测试并发场景 |
| 性能测试 | TestXxxPerformance | 测试性能指标 |

---

## 3. 测试方法命名规范

### 3.1 方法命名格式

```python
def test_<action>_<condition>_<expected_result>(self):
    """
    [TEST] 测试描述
    [EXPECTED] 预期结果描述
    """
```

**示例**:
```python
def test_create_user_with_null_username_returns_400(self):
    """
    [TEST] 创建用户时username为null
    [EXPECTED] 应返回400错误
    """

def test_concurrent_create_same_username_returns_conflict(self):
    """
    [TEST] 并发创建相同username的用户
    [EXPECTED] 只有一个成功，其他返回冲突错误
    """
```

### 3.2 命名动词参考

| 动作 | 英文 | 示例 |
|------|------|------|
| 创建 | create | test_create_user |
| 更新 | update | test_update_role |
| 删除 | delete | test_delete_domain |
| 查询 | query/list/get | test_list_users |
| 验证 | validate | test_validate_permission |
| 并发 | concurrent | test_concurrent_update |
| 批量 | batch | test_batch_delete |

---

## 4. 测试文档规范

### 4.1 文件级文档

每个测试文件都应该包含文件级docstring：

```python
# -*- coding: utf-8 -*-
"""
[MODULE] 模块名称
[DESCRIPTION] 模块功能描述

测试范围：
1. 功能点1
2. 功能点2
3. 功能点3
"""
```

### 4.2 类级文档

每个测试类都应该包含类级docstring：

```python
class TestXxx(unittest.TestCase):
    """
    [TEST CLASS] 测试类名称
    [DESCRIPTION] 详细描述测试内容和范围
    
    测试范围：
    1. 场景1
    2. 场景2
    3. 场景3
    """
```

### 4.3 方法级文档

每个测试方法都应该包含方法级docstring：

```python
def test_xxx(self):
    """
    [TEST] 测试场景描述
    [EXPECTED] 预期结果描述
    [NOTE] 补充说明（可选）
    [EXAMPLE] 示例（可选）
    """
```

---

## 5. 测试结构规范

### 5.1 标准测试结构

```python
import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.server import create_app
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


def _get_admin_token():
    """获取管理员token的辅助函数"""
    user = UserInfo(
        user_id='1',
        username='admin',
        display_name='Admin',
        email='admin@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    return token


class TestXxx(unittest.TestCase):
    """测试类"""
    
    @classmethod
    def setUpClass(cls):
        """类级别初始化 - 只执行一次"""
        from meta.tests.conftest import get_shared_app
        cls.app, cls.client = get_shared_app()
        cls.token = _get_admin_token()
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}',
            'X-User-Id': '1',
            'X-User-Name': 'admin',
        }
    
    def setUp(self):
        """方法级别初始化 - 每个测试方法执行前都会执行"""
        self.created_ids = []
    
    def tearDown(self):
        """方法级别清理 - 每个测试方法执行后都会执行"""
        for obj_id in self.created_ids:
            try:
                self.client.delete(f'/api/v2/bo/xxx/{obj_id}', headers=self.headers)
            except Exception:
                pass
    
    def test_xxx(self):
        """测试方法"""
        # 1. 准备数据
        data = {'key': 'value'}
        
        # 2. 执行操作
        response = self.client.post('/api/v2/bo/xxx', data=json.dumps(data), headers=self.headers)
        
        # 3. 验证结果
        self.assertIn(response.status_code, [200, 201])
        
        # 4. 记录需要清理的资源
        if response.status_code in [200, 201]:
            result = json.loads(response.data)
            obj_id = result.get('data', {}).get('id')
            if obj_id:
                self.created_ids.append(obj_id)


if __name__ == '__main__':
    unittest.main()
```

### 5.2 使用pytest的结构（推荐）

```python
import pytest
import json

class TestXxx:
    """测试类"""
    
    @pytest.fixture(autouse=True)
    def setup(self, api_client, admin_headers):
        """自动应用的fixture"""
        self.client = api_client
        self.headers = admin_headers
        self.created_ids = []
    
    def test_xxx(self):
        """测试方法"""
        # 测试代码
        pass
```

---

## 6. 断言规范

### 6.1 推荐的断言方式

```python
# [OK] 推荐：使用assertIn验证状态码范围
self.assertIn(response.status_code, [200, 201, 400, 422])

# [OK] 推荐：使用assertEqual验证精确值
self.assertEqual(response.status_code, 200)

# [OK] 推荐：使用assertGreater验证范围
self.assertGreater(success_count, 0)

# [OK] 推荐：使用assertTrue/assertFalse验证布尔值
self.assertTrue(result.get('success'))

# [X] 不推荐：过于严格的断言
self.assertEqual(response.status_code, 200)  # 可能因为API返回201而失败
```

### 6.2 混合验证策略

根据测试的重要性选择验证策略：

**关键路径（严格验证）**:
```python
# 登录、权限、安全等关键功能
self.assertEqual(response.status_code, 200)
self.assertTrue(result.get('success'))
```

**非关键路径（宽松验证）**:
```python
# 列表查询、元数据等非关键功能
self.assertIn(response.status_code, [200, 403, 404])
```

---

## 7. 测试数据管理

### 7.1 使用辅助函数生成测试数据

```python
def _generate_test_user_data():
    """生成测试用户数据"""
    timestamp = int(time.time() * 1000)
    return {
        'username': f'test_user_{timestamp}',
        'password': 'test123',
        'email': f'test_{timestamp}@test.com'
    }

def _generate_test_role_data():
    """生成测试角色数据"""
    timestamp = int(time.time() * 1000)
    return {
        'code': f'test_role_{timestamp}',
        'name': f'Test Role {timestamp}'
    }
```

### 7.2 使用常量管理测试数据

```python
# 测试数据常量
TEST_USER_DATA = {
    'default_password': 'test123',
    'default_email_domain': 'test.com',
    'max_username_length': 255,
    'max_email_length': 255,
}

TEST_ROLE_DATA = {
    'default_permissions': [],
    'system_roles': ['admin', 'user', 'guest'],
}
```

---

## 8. 测试清理规范

### 8.1 使用tearDown清理资源

```python
def tearDown(self):
    """清理测试创建的资源"""
    # 按创建的逆序清理
    for obj_type, obj_id in reversed(self.created_resources):
        try:
            self.client.delete(f'/api/v2/bo/{obj_type}/{obj_id}', headers=self.headers)
        except Exception:
            pass  # 忽略清理失败
```

### 8.2 使用try-finally确保清理

```python
def test_xxx(self):
    """测试方法"""
    user_id = None
    try:
        # 创建资源
        response = self.client.post(...)
        user_id = json.loads(response.data).get('data', {}).get('id')
        
        # 执行测试
        # ...
    finally:
        # 确保清理
        if user_id:
            try:
                self.client.delete(f'/api/v2/bo/user/{user_id}', headers=self.headers)
            except Exception:
                pass
```

---

## 9. 测试执行规范 (v3.18 更新)

> **[!!!] [!!!] [!!!] 铁律: 禁止直接运行 pytest [!!!] [!!!] [!!!]**
>
> **任何时候都禁止使用 `pytest` 或 `python -m pytest` 命令**
>
> **唯一合法入口: `python d:\filework\test.py`**

### 9.1 运行单个测试文件

```bash
# 🆕 v3.18 合规: 走 test.py 入口
python d:\filework\test.py --file meta/tests/test_xxx.py

# 替代旧违规命令:
# [X] python -m pytest meta/tests/test_xxx.py -v  # 违规
```

### 9.2 运行特定测试类

```bash
# 🆕 v3.18: 用 -k 选 test
python d:\filework\test.py --file meta/tests/test_xxx.py --k TestXxx
# 或单测 fast feedback
python d:\filework\test.py --single meta/tests/test_xxx.py
```

### 9.3 运行特定测试方法 (Fast Feedback < 5s)

```bash
# 🆕 v3.18 D.4: 单测快速反馈, 跳过 DB 快照/锁
python d:\filework\test.py --single "meta/tests/test_xxx.py::TestXxx::test_xxx"
```

### 9.4 运行所有测试

```bash
# 走 test.py (DB 快照保护, 锁机制)
python d:\filework\test.py --all --force
# 修复后跑 failed
python d:\filework\test.py --failed
```

### 9.5 并行运行测试

```bash
# test.py --all 默认 -n4 并行 (会有并发假失败, 需再跑 --failed)
python d:\filework\test.py --all --force
```

### 9.6 生成覆盖率报告

```bash
# test.py 暂时不直接支持 cov, 用 pytest 单独跑 (CI 用)
# 临时: pytest-cov
pytest meta/tests/ --cov=meta --cov-report=html  # 走 GitHub Actions
```

### 9.7 AI Coding Agent 友好入口 (v3.18 新增)

```bash
# 🆕 v3.18: Agent 专用入口
python scripts/agent_test.py --single <test_id> --port <port> --json <path>
# 含 trace_id + JSON 输出
```

---

## 10. 测试最佳实践

### 10.1 测试独立性

每个测试应该独立运行，不依赖其他测试的结果：

```python
# [OK] 正确：每个测试都创建自己的数据
def test_create_user(self):
    data = _generate_test_user_data()
    response = self.client.post(...)

# [X] 错误：依赖其他测试的数据
def test_update_user(self):
    # 假设test_create_user已经创建了用户
    response = self.client.put('/api/v2/bo/user/1', ...)
```

### 10.2 测试可重复性

测试应该可以重复执行，结果应该一致：

```python
# [OK] 正确：使用时间戳确保唯一性
username = f'test_user_{int(time.time() * 1000)}'

# [X] 错误：使用固定值可能导致冲突
username = 'test_user'
```

### 10.3 测试清晰性

测试应该清晰表达测试意图：

```python
# [OK] 正确：清晰的测试名称和文档
def test_create_user_with_null_username_returns_400(self):
    """
    [TEST] 创建用户时username为null
    [EXPECTED] 应返回400错误
    """
    data = {'username': None, 'password': 'test123'}
    response = self.client.post(...)
    self.assertIn(response.status_code, [400, 422])

# [X] 错误：不清晰的测试名称
def test_1(self):
    data = {'username': None, 'password': 'test123'}
    response = self.client.post(...)
    self.assertIn(response.status_code, [400, 422])
```

---

## 11. 常见测试场景模板

### 11.1 API CRUD测试模板

```python
class TestXxxAPI(unittest.TestCase):
    """API CRUD测试模板"""
    
    def test_create_success(self):
        """测试创建成功"""
        pass
    
    def test_create_with_invalid_data(self):
        """测试创建失败 - 无效数据"""
        pass
    
    def test_list_success(self):
        """测试列表查询成功"""
        pass
    
    def test_get_by_id_success(self):
        """测试按ID查询成功"""
        pass
    
    def test_update_success(self):
        """测试更新成功"""
        pass
    
    def test_delete_success(self):
        """测试删除成功"""
        pass
```

### 11.2 边界条件测试模板

```python
class TestXxxBoundary(unittest.TestCase):
    """边界条件测试模板"""
    
    def test_with_null_value(self):
        """测试null值"""
        pass
    
    def test_with_empty_value(self):
        """测试空值"""
        pass
    
    def test_with_max_value(self):
        """测试最大值"""
        pass
    
    def test_with_min_value(self):
        """测试最小值"""
        pass
    
    def test_with_invalid_type(self):
        """测试无效类型"""
        pass
```

### 11.3 并发测试模板

```python
class TestXxxConcurrent(unittest.TestCase):
    """并发测试模板"""
    
    def test_concurrent_create(self):
        """测试并发创建"""
        pass
    
    def test_concurrent_update(self):
        """测试并发更新"""
        pass
    
    def test_concurrent_delete(self):
        """测试并发删除"""
        pass
```

---

## 12. 检查清单

在提交测试代码前，请确认以下事项：

- [ ] **命名规范**: 文件、类、方法命名符合规范
- [ ] **文档完整**: 包含文件级、类级、方法级文档
- [ ] **测试独立**: 每个测试可以独立运行
- [ ] **测试可重复**: 测试可以重复执行
- [ ] **资源清理**: 使用tearDown清理测试资源
- [ ] **断言合理**: 使用合理的断言方式
- [ ] **数据管理**: 使用辅助函数或常量管理测试数据
- [ ] **错误处理**: 正确处理异常情况
- [ ] **性能考虑**: 避免不必要的性能开销

---

## 版本历史

| 日期 | 版本 | 更新内容 | 作者 |
|------|------|----------|------|
| 2026-05-29 | v1.0 | 初始版本 | QA团队 |

---

> **维护说明**: 本文档是测试编写的核心指南，所有测试代码都应该遵循本规范。
