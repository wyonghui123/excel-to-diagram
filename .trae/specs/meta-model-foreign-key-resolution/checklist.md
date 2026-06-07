# Checklist

## Phase 1: Schema 层改进

### domain.yaml
- [x] domain.yaml 包含 version_code 虚拟字段
- [x] version_code 字段设置 storage: virtual
- [x] version_code 字段设置 import_visible: true, export_visible: true
- [x] version_id 字段添加 resolve_from_field: version_code
- [x] version_id 字段添加 resolve_to_object: version

### sub_domain.yaml
- [x] sub_domain.yaml 包含 domain_code 虚拟字段
- [x] domain_code 字段设置 storage: virtual
- [x] domain_code 字段设置 import_visible: true, export_visible: true
- [x] domain_id 字段添加 resolve_from_field: domain_code
- [x] domain_id 字段添加 resolve_to_object: domain

### service_module.yaml
- [x] service_module.yaml 包含 sub_domain_code 虚拟字段
- [x] sub_domain_code 字段设置 storage: virtual
- [x] sub_domain_code 字段设置 import_visible: true, export_visible: true
- [x] sub_domain_id 字段添加 resolve_from_field: sub_domain_code
- [x] sub_domain_id 字段添加 resolve_to_object: sub_domain

### business_object.yaml
- [x] business_object.yaml 包含 service_module_code 虚拟字段
- [x] service_module_code 字段设置 storage: virtual
- [x] service_module_code 字段设置 import_visible: true, export_visible: true
- [x] service_module_id 字段添加 resolve_from_field: service_module_code
- [x] service_module_id 字段添加 resolve_to_object: service_module

### Schema 验证
- [x] YAML 文件语法正确，无解析错误

## Phase 2: 服务层改进

### action_executor.py
- [x] 包含 `_resolve_foreign_keys` 方法
- [x] 包含 `_find_by_key` 辅助方法
- [x] `_do_create` 方法调用外键解析
- [x] `_do_update` 方法调用外键解析
- [x] 外键解析失败时返回友好的错误信息
- [x] 错误信息包含父对象名称和业务键

### 服务层验证
- [x] 创建操作时自动解析外键
- [x] 更新操作时允许切换父对象（受 immutable 约束）
- [x] 外键不存在时返回明确的错误提示

## Phase 3: 导入导出改进

### import_export_service.py
- [x] 包含 `_validate_parent_reference` 方法
- [x] 包含 `_check_in_importing_batch` 方法
- [x] 导入验证错误提示包含父对象名称
- [x] 导入验证错误提示包含业务键
- [x] 导入验证错误提示包含解决建议（hint）
- [x] 支持检测父对象是否在当前导入批次中

### 导入导出验证
- [x] 导入数据包含父对象业务键时正确解析
- [x] 导入验证失败时显示友好错误提示
- [x] 跨版本数据不冲突

## Phase 4: 自动化测试

### 单元测试 test_foreign_key_resolution.py
- [x] test_resolve_parent_by_business_key: 测试通过业务键解析父对象
- [x] test_resolve_parent_not_found: 测试父对象不存在时的错误处理
- [x] test_resolve_with_version_isolation: 测试版本隔离下的外键解析
- [x] test_resolve_composite_key: 测试组合业务键解析

### 集成测试 test_import_with_parent_resolution.py
- [x] test_01_create_with_parent_code: 测试通过业务键创建对象
- [x] test_02_update_with_parent_code: 测试父字段不可变约束
- [x] test_03_resolve_with_version_isolation: 测试版本隔离下的外键解析
- [x] test_04_resolve_multiple_levels: 测试多层级外键解析
- [x] test_05_parent_not_found_error: 测试父对象不存在时的错误处理

### 测试运行
- [x] run_all_tests.py 包含外键解析测试模块
- [x] 所有单元测试通过
- [x] 所有集成测试通过

## 功能验收

- [x] 用户可以通过业务键创建对象（无需知道技术ID）
- [x] 用户可以通过业务键更新对象的父对象（受 immutable 约束）
- [x] 导入时可以使用父对象业务键而非技术ID
- [x] 导入验证失败时显示友好的错误提示
- [x] 错误提示包含具体的父对象名称和业务键
- [x] 错误提示包含解决建议

## 代码质量验证

- [x] 无 lint 错误
- [x] 无类型错误
- [x] 代码符合项目规范
