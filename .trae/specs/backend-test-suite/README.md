# 后端测试套件

> **目标**: 为后端元数据驱动模型创建完整的测试用例，从底层到API层
>
> **总计**: 295个测试用例

---

## 文档结构

```
backend-test-suite/
├── README.md           # 测试套件总览
├── spec.md            # 测试规范和架构
└── test-cases.md      # 测试用例清单
```

---

## 一、测试分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    API层 (50个测试)                          │
│  bo_api.py, user_api.py, role_api.py, association_api.py  │
├─────────────────────────────────────────────────────────────┤
│                    服务层 (20个测试)                          │
│  view_config_service, import_export_service, permission_    │
├─────────────────────────────────────────────────────────────┤
│                    拦截器层 (50个测试)                       │
│  PersistenceInterceptor, QueryInterceptor, CascadeInterceptor  │
├─────────────────────────────────────────────────────────────┤
│                    核心引擎 (60个测试)                        │
│  BOFramework, QueryBuilder, AssociationEngine              │
├─────────────────────────────────────────────────────────────┤
│                    数据访问层                               │
│  DataSource, SQLAdapters                                 │
├─────────────────────────────────────────────────────────────┤
│                    模型层 (45个测试)                        │
│  MetaObject, MetaField, FieldType, ActionContext          │
├─────────────────────────────────────────────────────────────┤
│                    YAML加载层 (40个测试)                    │
│  YAML解析, 元数据注册, 配置验证                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、测试用例统计

| 层级 | 测试用例数 | 占比 |
|------|-----------|------|
| 模型层 (models.py) | 45 | 15% |
| YAML加载层 (yaml_loader.py) | 40 | 14% |
| 核心引擎 (bo_framework.py) | 60 | 20% |
| 拦截器层 (interceptors/) | 50 | 17% |
| AssociationEngine | 30 | 10% |
| API层 (api/) | 50 | 17% |
| 视图配置服务 (view_config_service) | 20 | 7% |
| **总计** | **295** | **100%** |

---

## 三、测试用例清单

详细测试用例请查看 [test-cases.md](test-cases.md)

### 3.1 模型层测试 (45个)

#### MetaObject测试 (15个)
- ✅ 创建基本MetaObject
- ✅ 创建带associations的MetaObject
- ✅ 创建persistent对象
- ✅ MetaObject验证

#### MetaField测试 (15个)
- ✅ 所有FieldType类型创建
- ✅ 字段属性配置
- ✅ 字段验证

#### FieldType枚举测试 (5个)
- ✅ 枚举值验证
- ✅ 类型判断方法

#### ActionContext/Result测试 (10个)
- ✅ 上下文创建和结果设置

### 3.2 YAML加载层测试 (40个)

#### 文件解析测试 (10个)
- ✅ 加载所有YAML文件
- ✅ 编码处理

#### 字段定义测试 (10个)
- ✅ 所有字段属性映射

#### 关联定义测试 (5个)
- ✅ M2M/Reference/Composition

#### 配置解析测试 (10个)
- ✅ list/actions/import_export配置

#### Registry测试 (5个)
- ✅ 单例和注册方法

### 3.3 BOFramework核心测试 (60个)

#### CRUD操作测试 (30个)
- ✅ Create/Read/Update/Delete
- ✅ 必填字段验证
- ✅ 时间戳自动设置
- ✅ 唯一性验证

#### 过滤排序分页测试 (30个)
- ✅ 所有过滤器类型
- ✅ 升序/降序/多列排序
- ✅ 分页和OFFSET

### 3.4 拦截器层测试 (50个)

#### PersistenceInterceptor (15个)
- ✅ 前后置处理
- ✅ 时间戳和版本控制
- ✅ 业务键生成

#### QueryInterceptor (10个)
- ✅ 分页/过滤/排序应用
- ✅ 数据权限过滤

#### CascadeInterceptor (5个)
- ✅ 级联创建/更新/删除

#### AuditInterceptor (5个)
- ✅ 审计日志记录

#### LockInterceptor (5个)
- ✅ 悲观锁/乐观锁

#### DataPermissionInterceptor (5个)
- ✅ 数据权限过滤

#### 其他拦截器 (5个)
- ✅ ContextInterceptor
- ✅ ValidationInterceptor

### 3.5 AssociationEngine测试 (30个)

#### 查询关联 (10个)
- ✅ M2M/1NM/NM1查询
- ✅ 过滤/排序/分页

#### 分配关联 (5个)
- ✅ M2M分配
- ✅ 重复检查

#### 取消关联 (5个)
- ✅ M2M取消
- ✅ 权限检查

#### 批量操作 (5个)
- ✅ 批量分配/取消

#### 关联计数 (5个)
- ✅ 计数查询
- ✅ 缓存和性能

### 3.6 API层测试 (50个)

#### v2 BO API测试 (20个)
- ✅ CRUD端点
- ✅ 过滤/排序/分页
- ✅ 权限和认证

#### Association API测试 (15个)
- ✅ 查询/分配/取消
- ✅ 批量操作

#### 导出导入API测试 (10个)
- ✅ 导出/导入/预览
- ✅ 模板下载

#### Schema/Config API (5个)
- ✅ Schema/UIConfig/ViewConfig

### 3.7 视图配置服务测试 (20个)

- ✅ list/detail/form视图配置
- ✅ 列和操作配置
- ✅ CRUD操作自动添加
- ✅ 权限和可见性

---

## 四、测试工具

### 4.1 测试框架

```bash
# pytest
pytest tests/

# 带覆盖率
pytest --cov=meta tests/

# 带标记
pytest -m "unit" tests/
pytest -m "integration" tests/
```

### 4.2 测试配置

```python
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = --strict-markers --tb=short
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
```

### 4.3 Fixtures

```python
@pytest.fixture
def clean_db():
    """清理数据库"""
    yield
    # cleanup

@pytest.fixture
def sample_user():
    """示例用户"""
    return {
        'username': 'testuser',
        'email': 'test@example.com'
    }
```

---

## 五、测试覆盖率目标

| 层级 | 目标覆盖率 | 关键指标 |
|------|----------|---------|
| 模型层 | 95%+ | 所有模型 |
| YAML加载层 | 95%+ | 解析/验证 |
| BOFramework | 90%+ | CRUD/过滤/排序 |
| 拦截器层 | 90%+ | 每个拦截器 |
| AssociationEngine | 90%+ | 关联操作 |
| API层 | 90%+ | 所有端点 |

---

## 六、快速开始

### 6.1 运行所有测试

```bash
cd meta
pytest tests/ -v
```

### 6.2 运行特定模块测试

```bash
# 模型层测试
pytest tests/test_core_models.py -v

# YAML加载测试
pytest tests/test_yaml_loader.py -v

# BOFramework测试
pytest tests/test_bo_framework.py -v

# 拦截器测试
pytest tests/test_*interceptor*.py -v

# API测试
pytest tests/test_*api*.py -v
```

### 6.3 生成覆盖率报告

```bash
pytest tests/ --cov=meta --cov-report=html
```

---

## 七、测试用例编写规范

### 7.1 命名规范

```python
def test_{module}_{scenario}_{expected_result}():
    """
    测试用例命名: test_模块_场景_预期结果
    
    示例:
    test_boframework_create_returns_success()
    test_yaml_loader_loads_user_yaml()
    """
    pass
```

### 7.2 测试结构

```python
def test_module_function():
    """
    测试用例结构:
    1. Arrange - 准备测试数据
    2. Act - 执行被测试的函数
    3. Assert - 验证结果
    """
    # Arrange
    input_data = {...}
    
    # Act
    result = function_under_test(input_data)
    
    # Assert
    assert result == expected
```

### 7.3 Mock外部依赖

```python
def test_with_mock():
    """使用mock测试"""
    with patch('external_service.call') as mock:
        mock.return_value = expected
        
        result = function_under_test()
        
        assert result == expected
        mock.assert_called_once()
```

---

## 八、持续集成

### 8.1 CI配置

```yaml
# .github/workflows/test.yml
name: Backend Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-mock
          pip install -e meta
      - name: Run tests
        run: |
          cd meta
          pytest tests/ -v --cov=meta --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

### 8.2 覆盖率检查

- 所有核心模块覆盖率 ≥ 90%
- 新代码覆盖率 ≥ 80%
- 覆盖率下降阻止合并

---

## 九、相关文档

- [test-cases.md](test-cases.md) - 295个测试用例清单
- [spec.md](spec.md) - 测试规范和架构
