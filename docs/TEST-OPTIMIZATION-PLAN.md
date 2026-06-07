# 测试体系优化方案

## 一、目录结构重组

### 建议的新结构

```
meta/
├── tests/
│   ├── unit/                    # 单元测试 (快速、无外部依赖)
│   │   ├── core/               # 核心模型测试
│   │   │   ├── test_models.py
│   │   │   ├── test_yaml_loader.py
│   │   │   └── test_schema_generator.py
│   │   ├── services/           # 服务层测试
│   │   │   ├── test_change_notification_service.py
│   │   │   ├── test_webhook_service.py
│   │   │   └── test_websocket_manager.py
│   │   └── utils/              # 工具类测试
│   │       └── test_utils.py
│   │
│   ├── integration/             # 集成测试 (需要数据库)
│   │   ├── api/                # API 集成测试
│   │   │   ├── test_meta_api.py
│   │   │   ├── test_auth_api.py
│   │   │   └── test_notification_api.py
│   │   ├── services/           # 服务集成测试
│   │   │   ├── test_manage_service.py
│   │   │   └── test_hierarchy_filter_service.py
│   │   └── database/           # 数据库集成测试
│   │       └── test_foreign_key_resolution.py
│   │
│   ├── e2e/                     # 端到端测试 (完整流程)
│   │   ├── test_import_export_flow.py
│   │   ├── test_user_scenario.py
│   │   └── test_real_data_scenario.py
│   │
│   ├── conftest.py              # 共享 fixtures
│   └── pytest.ini               # pytest 配置
│
├── scripts/                     # 脚本移出测试目录
│   ├── debug/                   # 调试脚本
│   │   ├── debug_condition.py
│   │   ├── debug_field.py
│   │   └── debug_resolve.py
│   ├── data/                    # 数据脚本
│   │   ├── init_test_data.py
│   │   ├── add_test_data.py
│   │   └── check_products.py
│   └── tools/                   # 工具脚本
│       ├── quick_replace.py
│       └── fix_test_paths.py
```

## 二、pytest 配置优化

### pytest.ini

```ini
[pytest]
testpaths = meta/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 标记定义
markers =
    unit: 单元测试 (无外部依赖)
    integration: 集成测试 (需要数据库)
    e2e: 端到端测试 (完整流程)
    slow: 慢速测试 (>1s)
    api: API 测试
    db: 数据库测试

# 默认选项
addopts = 
    -v
    --tb=short
    --strict-markers
    -p no:warnings

# 环境变量
env =
    JWT_SECRET_KEY=test-secret-key
    FLASK_ENV=testing
```

### conftest.py 增强

```python
import pytest
from pathlib import Path

def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "unit: 单元测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "e2e: 端到端测试")

def pytest_collection_modifyitems(config, items):
    """根据文件路径自动添加标记"""
    for item in items:
        path = Path(item.fspath)
        
        if "unit" in str(path):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(path):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(path):
            item.add_marker(pytest.mark.e2e)
```

## 三、分层执行策略

### 开发阶段 (快速反馈)
```bash
# 只运行单元测试 (~10s)
pytest -m unit

# 运行单元测试 + 当前模块集成测试
pytest -m "unit or (integration and api)"
```

### 提交前 (完整验证)
```bash
# 运行单元测试 + 集成测试 (~1min)
pytest -m "unit or integration"

# 排除慢速测试
pytest -m "unit or integration" -m "not slow"
```

### CI/CD (完整覆盖)
```bash
# 运行所有测试
pytest

# 并行执行
pytest -n auto
```

## 四、测试整合建议

### 整合方案

| 原文件 | 整合到 | 说明 |
|--------|--------|------|
| test_change_notification_config.py | unit/services/test_change_notification.py | 合并配置测试 |
| test_change_notification_service.py | unit/services/test_change_notification.py | 合并服务测试 |
| test_change_notification_integration.py | integration/services/test_change_notification.py | 集成测试 |
| test_analytics_p0_adaptation.py | unit/core/test_analytics.py | 合并 P0/P1 |
| test_analytics_p1_adaptation.py | unit/core/test_analytics.py | 合并 P0/P1 |
| test_hierarchy_filter_api.py | integration/api/test_hierarchy.py | API 测试 |
| test_hierarchy_filter_service.py | integration/services/test_hierarchy.py | 服务测试 |

### 整合后结构

```
unit/
├── core/
│   ├── test_models.py          # 合并 test_core_models, test_unified_meta_model
│   ├── test_yaml_loader.py     # 保持
│   ├── test_analytics.py       # 合并 P0/P1 analytics
│   └── test_schema_generator.py
├── services/
│   ├── test_change_notification.py  # 合并 config + service
│   ├── test_webhook_service.py
│   └── test_websocket_manager.py
└── utils/
    └── test_utils.py

integration/
├── api/
│   ├── test_meta_api.py
│   ├── test_auth_api.py
│   └── test_hierarchy_api.py   # 合并 API 测试
└── services/
    ├── test_change_notification.py  # 集成测试
    └── test_hierarchy.py            # 合并服务测试

e2e/
├── test_import_export_flow.py
└── test_user_scenario.py
```

## 五、执行效率优化

### 1. 并行执行
```bash
# 安装 pytest-xdist
pip install pytest-xdist

# 并行执行
pytest -n auto
```

### 2. 测试隔离优化
- 使用内存数据库 :memory: 替代文件数据库
- 减少数据库初始化次数
- 使用 fixture 作用域优化

### 3. 慢测试标记
```python
@pytest.mark.slow
def test_import_large_file():
    """超过 1s 的测试标记为 slow"""
    pass
```

### 4. 失败重试
```bash
# 安装 pytest-rerunfailures
pip install pytest-rerunfailures

# 失败重试 2 次
pytest --reruns 2
```

## 六、迁移步骤

### Phase 1: 创建新结构 (1天)
1. 创建 unit/, integration/, e2e/ 目录
2. 创建 pytest.ini 配置
3. 更新 conftest.py

### Phase 2: 迁移测试 (2天)
1. 迁移单元测试到 unit/
2. 迁移集成测试到 integration/
3. 迁移 E2E 测试到 e2e/
4. 移动脚本到 scripts/

### Phase 3: 整合优化 (1天)
1. 合并相似测试文件
2. 添加测试标记
3. 更新 CI/CD 配置

### Phase 4: 验证 (0.5天)
1. 运行完整测试套件
2. 修复失败的测试
3. 更新文档

## 七、预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 测试文件数 | 78 | ~40 |
| 目录层级 | 1 | 3 |
| 单元测试执行 | ~2min | ~10s |
| 集成测试执行 | 包含在全部 | ~1min |
| CI 反馈时间 | ~2min | ~30s (分层) |
| 维护难度 | 高 | 低 |
