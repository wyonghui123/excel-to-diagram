# Tasks

## Phase 1: Schema 层改进

- [x] Task 1.1: 修改 domain.yaml 添加 version_code 虚拟字段
  - [x] SubTask 1.1.1: 添加 version_code 字段定义（storage: virtual, import_visible: true, export_visible: true）
  - [x] SubTask 1.1.2: 为 version_id 字段添加 resolve_from_field: version_code 和 resolve_to_object: version

- [x] Task 1.2: 修改 sub_domain.yaml 添加 domain_code 虚拟字段
  - [x] SubTask 1.2.1: 添加 domain_code 字段定义（storage: virtual, import_visible: true, export_visible: true）
  - [x] SubTask 1.2.2: 为 domain_id 字段添加 resolve_from_field: domain_code 和 resolve_to_object: domain

- [x] Task 1.3: 修改 service_module.yaml 添加 sub_domain_code 虚拟字段
  - [x] SubTask 1.3.1: 添加 sub_domain_code 字段定义（storage: virtual, import_visible: true, export_visible: true）
  - [x] SubTask 1.3.2: 为 sub_domain_id 字段添加 resolve_from_field: sub_domain_code 和 resolve_to_object: sub_domain

- [x] Task 1.4: 修改 business_object.yaml 添加 service_module_code 虚拟字段
  - [x] SubTask 1.4.1: 添加 service_module_code 字段定义（storage: virtual, import_visible: true, export_visible: true）
  - [x] SubTask 1.4.2: 为 service_module_id 字段添加 resolve_from_field: service_module_code 和 resolve_to_object: service_module

## Phase 2: 服务层改进

- [x] Task 2.1: 在 action_executor.py 添加外键解析方法
  - [x] SubTask 2.1.1: 实现 _resolve_foreign_keys 方法
  - [x] SubTask 2.1.2: 实现 _find_by_key 辅助方法
  - [x] SubTask 2.1.3: 添加友好的错误提示（包含父对象名称和业务键）

- [x] Task 2.2: 在 _do_create 方法中调用外键解析
  - [x] SubTask 2.2.1: 在数据准备后、验证前调用 _resolve_foreign_keys
  - [x] SubTask 2.2.2: 处理外键解析失败的错误

- [x] Task 2.3: 在 _do_update 方法中调用外键解析
  - [x] SubTask 2.3.1: 在数据准备后、验证前调用 _resolve_foreign_keys
  - [x] SubTask 2.3.2: 允许通过业务键切换父对象（注意：受 immutable 约束）

## Phase 3: 导入导出改进

- [x] Task 3.1: 增强导入验证的错误提示
  - [x] SubTask 3.1.1: 实现 _validate_parent_reference 方法
  - [x] SubTask 3.1.2: 错误提示包含具体的父对象名称和业务键
  - [x] SubTask 3.1.3: 错误提示包含解决建议（hint）

- [x] Task 3.2: 支持检测父对象是否在当前导入批次中
  - [x] SubTask 3.2.1: 实现 _check_in_importing_batch 方法
  - [x] SubTask 3.2.2: 在 _validate_sheets 中维护导入批次索引

- [x] Task 3.3: 改进导出模板
  - [x] SubTask 3.3.1: 导出模板包含父对象业务键列
  - [x] SubTask 3.3.2: 父对象业务键列标记为可选（非必填）

## Phase 4: 自动化测试

- [x] Task 4.1: 创建单元测试 test_foreign_key_resolution.py
  - [x] SubTask 4.1.1: 测试通过业务键解析父对象（成功场景）
  - [x] SubTask 4.1.2: 测试父对象不存在时的错误处理
  - [x] SubTask 4.1.3: 测试版本隔离下的外键解析
  - [x] SubTask 4.1.4: 测试组合业务键解析

- [x] Task 4.2: 创建集成测试 test_import_with_parent_resolution.py
  - [x] SubTask 4.2.1: 测试导入服务模块时使用子领域编码
  - [x] SubTask 4.2.2: 测试导入验证错误提示
  - [x] SubTask 4.2.3: 测试跨版本数据不冲突

- [x] Task 4.3: 更新 run_all_tests.py
  - [x] SubTask 4.3.1: 添加外键解析测试模块
  - [x] SubTask 4.3.2: 确保所有测试通过

# Task Dependencies

- Task 1.x (Schema 层改进) → Task 2.x (服务层改进)
- Task 2.x (服务层改进) → Task 3.x (导入导出改进)
- Task 3.x (导入导出改进) → Task 4.x (自动化测试)
- Task 1.x (Schema 层改进) → Task 4.1 (单元测试可并行)

# 验证步骤

每个 Task 完成后，执行以下验证：

1. **Schema 层改进验证**
   - 运行 `python -m meta.tools.sync_schema --diff` 确认无数据库变更
   - 检查 YAML 文件语法正确

2. **服务层改进验证**
   - 运行 `python meta/tests/test_action_executor.py`
   - 手动测试创建/更新操作

3. **导入导出改进验证**
   - 导出模板检查包含父对象业务键列
   - 导入测试数据验证错误提示

4. **自动化测试验证**
   - 运行 `python meta/tests/run_all_tests.py`
   - 确认所有测试通过
