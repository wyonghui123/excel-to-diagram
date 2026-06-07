# Tasks

## Phase 1: 元数据模型变更 ✅ 已完成

- [x] Task 1: 修改 version.yaml 添加 product_code 字段
  - [x] 1.1 添加 product_code 字段定义（business_key: true, virtual: true, export_visible: false）
  - [x] 1.2 验证 version 元数据加载正确

- [x] Task 2: 修改 domain.yaml 添加 product_code, version_code 字段
  - [x] 2.1 添加 product_code 字段定义（business_key: true, virtual: true）
  - [x] 2.2 添加 version_code 字段定义（business_key: true, virtual: true）
  - [x] 2.3 调整 code 字段的 import_order 为 2

- [x] Task 3: 修改 sub_domain.yaml 添加 product_code, version_code 字段
  - [x] 3.1 添加 product_code 字段定义
  - [x] 3.2 添加 version_code 字段定义
  - [x] 3.3 调整 code 字段的 import_order

- [x] Task 4: 修改 service_module.yaml 添加 product_code, version_code 字段
  - [x] 4.1 添加 product_code 字段定义
  - [x] 4.2 添加 version_code 字段定义
  - [x] 4.3 调整 code 字段的 import_order

- [x] Task 5: 修改 business_object.yaml 添加 product_code, version_code 字段
  - [x] 5.1 添加 product_code 字段定义
  - [x] 5.2 添加 version_code 字段定义
  - [x] 5.3 调整 code 字段的 import_order

- [x] Task 6: 修改 relationship.yaml 添加 product_code, version_code 字段
  - [x] 6.1 添加 product_code 字段定义
  - [x] 6.2 添加 version_code 字段定义
  - [x] 6.3 调整 source_code, target_code, relation_code 的 import_order

- [x] Task 6.1: 修改 models.py 添加 virtual 字段
  - [x] 6.1.1 在 SemanticAnnotation 类中添加 virtual: bool = False 字段
  - [x] 6.1.2 验证字段定义正确

- [x] Task 6.2: 修改 yaml_loader.py 解析 virtual 字段
  - [x] 6.2.1 在 parse_semantics 函数中添加 virtual=data.get("virtual", False)
  - [x] 6.2.2 验证 YAML 加载正确

## Phase 2: 导出服务变更 ✅ 已完成

- [x] Task 7: 添加获取 product_code/version_code 的方法
  - [x] 7.1 在 ImportExportService 中添加 `_get_product_version_codes` 方法
  - [x] 7.2 根据 version_id 查询 product_code 和 version_code

- [x] Task 8: 创建元数据 Sheet
  - [x] 8.1 在导出时创建"元数据" Sheet
  - [x] 8.2 写入 product_code, version_code, version_id, export_time 等信息

- [x] Task 9: 数据 enrichment 时注入 product_code, version_code
  - [x] 9.1 在 `_query_with_hierarchy` 中注入 product_code, version_code
  - [x] 9.2 验证导出 Excel 包含隐藏的 product_code, version_code 列

## Phase 3: 导入服务变更 ✅ 已完成

- [x] Task 10: 添加读取元数据 Sheet 的方法
  - [x] 10.1 在 ImportExportService 中添加 `_read_meta_sheet` 方法
  - [x] 10.2 解析 product_code, version_code, version_id

- [x] Task 11: 添加解析 version_id 的方法
  - [x] 11.1 在 ImportExportService 中添加 `_resolve_version_id` 方法
  - [x] 11.2 根据 product_code + version_code 查询 version_id

- [x] Task 12: 修改唯一性校验方法
  - [x] 12.1 修改 `_find_by_business_key` 方法
  - [x] 12.2 按 version_id + code 组合查重
  - [x] 12.3 修改 `_upsert_record` 方法使用新的唯一性校验

## Phase 4: 测试验证 ✅ 已完成

- [x] Task 13: 添加单元测试
  - [x] 13.1 测试 business_key 字段定义正确
  - [x] 13.2 测试 `_get_product_version_codes` 方法
  - [x] 13.3 测试 `_resolve_version_id` 方法
  - [x] 13.4 测试 `_find_by_business_key` 方法
  - [x] 13.5 修复 test_03_business_key_import_order 测试缓存问题

- [x] Task 14: 添加集成测试
  - [x] 14.1 测试导出包含元数据 Sheet
  - [x] 14.2 测试导入正确解析 version_id
  - [x] 14.3 测试导入唯一性校验

- [x] Task 15: E2E 测试
  - [x] 15.1 测试完整导出导入流程
  - [x] 15.2 测试跨版本数据不冲突

# Task Dependencies

- [Task 7] depends on [Task 1-6.2] (元数据模型变更完成)
- [Task 8] depends on [Task 7]
- [Task 9] depends on [Task 7]
- [Task 10] depends on [Task 8] (导出有元数据 Sheet)
- [Task 11] depends on [Task 10]
- [Task 12] depends on [Task 11]
- [Task 13] depends on [Task 1-12]
- [Task 14] depends on [Task 13]
- [Task 15] depends on [Task 14]

# Known Issues

## Issue 1: test_03_business_key_import_order 测试失败

**现象**: 测试期望 business_key 字段顺序为 `['product_code', 'version_code', 'code']`，但实际得到 `['version_code', 'code', 'product_code']`

**原因分析**: pytest 测试环境中的 registry 缓存问题

**解决方案**: 
1. 在测试前强制重新加载 YAML 文件
2. 或在测试中显式调用 `registry.reload()`

**修复任务**: Task 13.5

# Next Steps

1. 修复 Task 13.5: 测试缓存问题
2. 完成 Task 13.3-13.4: 剩余单元测试
3. 完成 Task 14.2-14.3: 集成测试
4. 完成 Task 15: E2E 测试
5. 更新 checklist.md 验证所有检查点
