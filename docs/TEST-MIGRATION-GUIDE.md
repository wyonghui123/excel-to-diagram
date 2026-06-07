# 测试体系目录重组迁移指南

## 概述

本文档提供将现有测试文件重组到分层目录结构的详细步骤。

## 目标结构

```
meta/
├── tests/
│   ├── unit/                    # 单元测试 (快速、无外部依赖)
│   │   ├── core/               # 核心模型测试
│   │   ├── services/           # 服务层测试
│   │   ├── analytics/          # 分析功能测试
│   │   └── utils/             # 工具类测试
│   │
│   ├── integration/             # 集成测试 (需要数据库)
│   │   ├── api/               # API 集成测试
│   │   └── services/          # 服务集成测试
│   │
│   ├── e2e/                   # 端到端测试 (完整流程)
│   │
│   ├── conftest.py            # 共享 fixtures
│   └── pytest.ini             # pytest 配置
│
├── scripts/                   # 脚本移出测试目录
│   ├── debug/                # 调试脚本
│   ├── data/                 # 数据初始化脚本
│   └── tools/               # 工具脚本
```

## 迁移脚本

### 1. 创建目录结构

```bash
# 在 meta 目录下执行
mkdir -p meta/tests/unit/core
mkdir -p meta/tests/unit/services
mkdir -p meta/tests/unit/analytics
mkdir -p meta/tests/unit/utils
mkdir -p meta/tests/integration/api
mkdir -p meta/tests/integration/services
mkdir -p meta/tests/e2e
mkdir -p meta/scripts/debug
mkdir -p meta/scripts/data
mkdir -p meta/scripts/tools
```

### 2. 移动调试脚本

```bash
# 移动调试脚本到 scripts/debug/
mv meta/tests/debug_*.py meta/scripts/debug/
mv meta/tests/pinpoint_*.py meta/scripts/debug/
```

### 3. 移动数据脚本

```bash
# 移动数据脚本到 scripts/data/
mv meta/tests/add_*.py meta/scripts/data/
mv meta/tests/init_*.py meta/scripts/data/
mv meta/tests/check_*.py meta/scripts/data/
mv meta/tests/show_*.py meta/scripts/data/
mv meta/tests/fix_*.py meta/scripts/data/
```

### 4. 移动工具脚本

```bash
# 移动工具脚本到 scripts/tools/
mv meta/tests/quick_*.py meta/scripts/tools/
mv meta/tests/batch_*.py meta/scripts/tools/
```

### 5. 移动测试文件

```bash
# 单元测试 - 核心
mv meta/tests/test_core_models.py meta/tests/unit/core/
mv meta/tests/test_unified_meta_model.py meta/tests/unit/core/
mv meta/tests/test_yaml_loader.py meta/tests/unit/core/
mv meta/tests/test_schema_generator.py meta/tests/unit/core/
mv meta/tests/test_aspect_resolution.py meta/tests/unit/core/

# 单元测试 - 服务
mv meta/tests/test_change_notification_service.py meta/tests/unit/services/
mv meta/tests/test_change_notification_config.py meta/tests/unit/services/
mv meta/tests/test_webhook_service.py meta/tests/unit/services/
mv meta/tests/test_websocket_manager.py meta/tests/unit/services/
mv meta/tests/test_rule_engine.py meta/tests/unit/services/
mv meta/tests/test_rule_chain.py meta/tests/unit/services/

# 单元测试 - 分析
mv meta/tests/test_analytics_aggregation.py meta/tests/unit/analytics/
mv meta/tests/test_analytics_p0_adaptation.py meta/tests/unit/analytics/
mv meta/tests/test_analytics_p1_adaptation.py meta/tests/unit/analytics/
mv meta/tests/test_computation_aggregation.py meta/tests/unit/analytics/

# 集成测试 - API
mv meta/tests/test_meta_api.py meta/tests/integration/api/
mv meta/tests/test_auth_api.py meta/tests/integration/api/
mv meta/tests/test_annotation_api.py meta/tests/integration/api/
mv meta/tests/test_enum_api.py meta/tests/integration/api/
mv meta/tests/test_relation_api.py meta/tests/integration/api/
mv meta/tests/test_relation_endpoints.py meta/tests/integration/api/

# 集成测试 - 服务
mv meta/tests/test_manage_service.py meta/tests/integration/services/
mv meta/tests/test_hierarchy_filter_service.py meta/tests/integration/services/
mv meta/tests/test_hierarchy_filter_api.py meta/tests/integration/services/
mv meta/tests/test_change_notification_integration.py meta/tests/integration/services/
mv meta/tests/test_cascade_service.py meta/tests/integration/services/

# E2E 测试
mv meta/tests/test_import_export_api.py meta/tests/e2e/
mv meta/tests/test_real_data_scenario.py meta/tests/e2e/
mv meta/tests/test_user_scenario_exact.py meta/tests/e2e/
```

## 更新测试引用

迁移后需要更新测试文件中的导入路径：

### 方案 A: 使用相对导入

在移动后的测试文件中添加路径：
```python
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
```

### 方案 B: 更新 pytest.ini

```ini
[pytest]
testpaths = meta/tests/unit meta/tests/integration meta/tests/e2e
```

## 迁移后验证

### 1. 验证目录结构

```bash
# 验证目录创建
ls -la meta/tests/
ls -la meta/tests/unit/
ls -la meta/tests/integration/
ls -la meta/tests/e2e/
```

### 2. 验证测试收集

```bash
# 收集测试（应该显示新的路径）
pytest --collect-only -q | head -20

# 统计测试数量
pytest --collect-only -q | wc -l
```

### 3. 运行分层测试

```bash
# 运行单元测试
pytest meta/tests/unit -m unit -v

# 运行集成测试
pytest meta/tests/integration -m integration -v

# 运行 E2E 测试
pytest meta/tests/e2e -m e2e -v
```

## 回滚方案

如果迁移出现问题，可以按以下步骤回滚：

```bash
# 1. 恢复调试脚本
mv meta/scripts/debug/*.py meta/tests/

# 2. 恢复数据脚本
mv meta/scripts/data/*.py meta/tests/

# 3. 恢复工具脚本
mv meta/scripts/tools/*.py meta/tests/

# 4. 恢复测试文件
mv meta/tests/unit/core/*.py meta/tests/
mv meta/tests/unit/services/*.py meta/tests/
# ... 其他类似

# 5. 删除创建的目录
rmdir meta/tests/unit/core
rmdir meta/tests/unit/services
# ... 其他类似
```

## 常见问题

### Q1: 迁移后测试导入失败

**原因**: Python 路径未正确设置

**解决**: 在 conftest.py 中添加：
```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
```

### Q2: pytest 找不到测试

**原因**: testpaths 配置不正确

**解决**: 更新 pytest.ini:
```ini
[pytest]
testpaths = meta/tests/unit meta/tests/integration meta/tests/e2e
```

### Q3: 文件名冲突

**原因**: 多个测试文件有相同名称

**解决**: 重命名文件添加前缀，如 `unit_test_core_models.py`

## 迁移检查清单

- [ ] 创建目标目录结构
- [ ] 备份现有测试文件
- [ ] 移动调试脚本到 scripts/debug/
- [ ] 移动数据脚本到 scripts/data/
- [ ] 移动工具脚本到 scripts/tools/
- [ ] 移动单元测试到 unit/
- [ ] 移动集成测试到 integration/
- [ ] 移动 E2E 测试到 e2e/
- [ ] 更新 conftest.py
- [ ] 更新 pytest.ini（如需要）
- [ ] 验证目录结构
- [ ] 运行测试收集验证
- [ ] 运行分层测试验证

## 建议的执行顺序

1. **第一阶段**: 创建目录结构 + 移动脚本 (风险低)
2. **第二阶段**: 移动单元测试到 unit/ (高优先级)
3. **第三阶段**: 移动集成测试到 integration/
4. **第四阶段**: 移动 E2E 测试到 e2e/
5. **第五阶段**: 验证所有测试执行正常

每个阶段后都应运行测试验证，确保没有引入问题。
