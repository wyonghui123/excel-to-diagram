# test_helpers - 共享测试基类与工具 (Phase 7 重构)

## 目的

解决 meta/tests/ 中 429 个文件、375 个碎片文件的重复问题:
- 150+ 重复 fixture 定义 (setup/service/client/auth_headers)
- 45+ 重复 CRUD 测试模式
- 9 个 bug regression 分散在多个文件

## 设计原则

1. **100% 向后兼容** - 不修改现有测试, 新代码可选使用
2. **不破坏现有 fixture** - conftest.py 的 shared_app/client 仍然有效
3. **不强制使用** - 现有测试可继续独立运行

## 模块概览

### 基类

| 基类 | 用途 | 替代 |
|------|------|------|
| `BaseAPITestCase` | API 测试通用基类 | 150+ fixture 定义 |
| `BaseCRUDTestCase` | CRUD 完整流程测试 | 45+ 重复 CRUD 模板 |
| `BaseRegressionTestCase` | BUG 回归测试 | 9 个独立 bug 文件 |

### 助手函数

| 函数 | 用途 |
|------|------|
| `assert_api_success(response)` | 断言 2xx 成功 |
| `assert_api_error(response, status, code)` | 断言 4xx/5xx 错误 |
| `assert_data_field(response, field, value)` | 断言 data.field 值 |
| `assert_status_code(response, code)` | 简单状态码断言 |
| `admin_cookie()` | 生成管理员认证头 |
| `user_cookie()` | 生成普通用户认证头 |
| `make_test_user()` | 构造 UserInfo |

## 使用示例

### 1. 简化 API 测试 (替代 30 行 fixture)

```python
# 之前:
@pytest.fixture
def app():
    from meta.server import create_app
    return create_app()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_headers():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    user = UserInfo(user_id='1', username='admin', ...)
    token, _ = TokenService.create_token(user)
    return {'Authorization': f'Bearer {token}', ...}

class TestMyAPI:
    def test_x(self, client, auth_headers):
        ...

# 之后:
from meta.tests.test_helpers import BaseAPITestCase

class TestMyAPI(BaseAPITestCase):
    object_type = 'product'

    def test_x(self):
        response = self.client.get(self.list_url, headers=self.admin_headers)
        self.assert_api_success(response)
```

### 2. 完整 CRUD 测试 (替代 5 个 test_ 方法)

```python
# 之前: 5 个 test_create/read/update/delete/list 方法, ~50 行

# 之后:
from meta.tests.test_helpers import BaseCRUDTestCase

class TestProductCRUD(BaseCRUDTestCase):
    object_type = 'product'

    def make_payload(self):
        return {'name': f'product_{uuid4().hex[:8]}', 'code': 'p1'}
```

自动获得 7 个测试方法 (test_create_success, test_read_success, ...)

### 3. BUG 回归测试

```python
# 之前:
class TestBugV020:
    def test_export_with_owner_id(self): ...

# 之后:
from meta.tests.test_helpers import BaseRegressionTestCase

class TestBugV020(BaseRegressionTestCase):
    bug_id = 'V020'
    bug_title = 'export 包含 owner_id 应被隐藏'
    fixed_in_version = '3.18.0'

    def test_export_with_owner_id(self):
        self.verify_fix(self._check_owner_id_not_exported, 'owner_id 应 export_visible: false')
```

## 推广策略

- **新测试** - 优先使用 BaseAPITestCase / BaseCRUDTestCase
- **现有测试** - 保持原状 (P1 不强制迁移)
- **P2 未来** - 评估用 sed/自动化工具批量迁移

## 验证状态

- [x] conftest.py 兼容性 (使用已有 shared_client)
- [x] 所有基类可被 import
- [x] 不破坏现有 1294 PASS / 55 FAIL 测试 (无变动)
