# Checklist

## Phase 1: 元数据模型变更

- [x] version.yaml 包含 product_code 字段，business_key=true, virtual=true
- [x] domain.yaml 包含 product_code, version_code 字段，business_key=true
- [x] sub_domain.yaml 包含 product_code, version_code 字段，business_key=true
- [x] service_module.yaml 包含 product_code, version_code 字段，business_key=true
- [x] business_object.yaml 包含 product_code, version_code 字段，business_key=true
- [x] relationship.yaml 包含 product_code, version_code 字段，business_key=true
- [x] 所有新增字段的 export_visible=false, import_visible=false
- [x] 所有新增字段的 ui.visible=false
- [x] code 字段的 import_order 调整为 2（在 product_code, version_code 之后）
- [x] SemanticAnnotation 类包含 virtual 字段
- [x] yaml_loader.py 正确解析 virtual 字段

## Phase 2: 导出服务变更

- [x] ImportExportService 包含 `_get_product_version_codes` 方法
- [x] 导出 Excel 包含"元数据" Sheet
- [x] 元数据 Sheet 包含 product_code, version_code, version_id
- [x] 数据 enrichment 正确注入 product_code, version_code
- [x] 导出的数据 Sheet 不显示 product_code, version_code 列（隐藏列）

## Phase 3: 导入服务变更

- [x] ImportExportService 包含 `_read_meta_sheet` 方法
- [x] ImportExportService 包含 `_resolve_version_id` 方法
- [x] 导入时正确解析 product_code, version_code
- [x] 导入时正确注入 version_id
- [x] `_find_by_business_key` 按 version_id + code 查重
- [x] 不同 version 的同 code 对象不冲突

## Phase 4: 测试验证

### 单元测试
- [x] test_01_domain_has_product_code_field: domain 包含 product_code 字段
- [x] test_02_domain_has_version_code_field: domain 包含 version_code 字段
- [x] test_03_business_key_import_order: business_key 字段顺序正确
- [x] test_04_export_has_meta_sheet: 导出包含元数据 Sheet
- [x] test_05_meta_sheet_has_context: 元数据 Sheet 包含上下文信息
- [x] test_06_get_product_version_codes_method: _get_product_version_codes 方法正确
- [x] test_07_all_objects_have_context_fields: 所有对象都有上下文字段
- [x] test_08_resolve_version_id_method: _resolve_version_id 方法正确
- [x] test_09_find_by_business_key_with_version: _find_by_business_key 方法正确
- [x] test_10_import_injects_version_id: 导入正确注入 version_id

### 集成测试
- [x] 测试导入正确解析 version_id
- [x] 测试导入唯一性校验

### E2E 测试
- [x] 测试完整导出导入流程
- [x] 测试跨版本数据不冲突

## 用户无感知验证

- [x] 前端列表页面不显示 product_code, version_code 列（ui.visible: false）
- [x] 前端创建/编辑表单不包含 product_code, version_code 字段（ui.visible: false）
- [x] Excel 模板下载不包含 product_code, version_code 列（export_visible: false）
- [x] 用户按原有方式操作，无需感知 product_code, version_code

## 代码质量验证

- [x] 所有测试通过
- [x] 无 lint 错误
- [x] 无类型错误

## 已知问题

### Issue 1: test_03_business_key_import_order 测试失败

**状态**: ✅ 已修复

**原因**: pytest 测试环境中的 registry 缓存问题

**解决方案**: 在测试前强制重新加载 YAML 文件，并修复排序逻辑（使用 `is not None` 而非真值判断）

## 下一步行动

✅ 所有任务已完成！
