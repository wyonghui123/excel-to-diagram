# Checklist

## Phase 1: 元模型和数据库

- [x] enum_type.yaml 文件已创建，包含所有必需字段定义
- [x] enum_value.yaml 文件已创建，包含所有必需字段定义
- [x] MetaField 类已扩展，包含 enum_type, enum_filter, enum_default_value 属性
- [x] 数据库表 enum_types 和 enum_values 已创建
- [x] 外键约束已正确设置

## Phase 2: 后端 API

- [x] GET /api/v1/enum-types 接口返回正确的枚举类型列表
- [x] POST /api/v1/enum-types 接口只能创建业务枚举（category=business）
- [x] GET /api/v1/enum-types/{type_id}/values 接口支持维度过滤参数
- [x] POST /api/v1/enum-types/{type_id}/values 接口检查 mutability 权限
- [x] DELETE /api/v1/enum-values/{id} 接口检查 is_system 和 mutability
- [x] 可维护性控制逻辑正确：locked 不可修改，extensible 可增不可删系统值，fully_editable 完全可编辑

## Phase 3: 前端管理界面

- [x] 枚举类型列表页正确显示所有枚举类型
- [x] 枚举类型筛选功能正常工作
- [x] 新建业务枚举对话框可以正确创建枚举类型
- [x] 枚举值管理页正确显示枚举值列表
- [x] 维度标签页切换功能正常（多维枚举）
- [x] 枚举值新增/编辑表单可以正确保存数据
- [x] 枚举值删除功能正确检查权限
- [x] 停用的枚举值不在下拉选项中显示

## Phase 4: 集成与迁移

- [x] 现有枚举值（FieldType, RelationType 等）已迁移到 enum_values 表
- [x] 迁移的枚举值 is_system = true
- [x] 字段配置可以关联枚举类型
- [x] 字段配置可以设置维度过滤条件
- [x] 业务表单中枚举字段显示为下拉选择框
- [x] 下拉选项根据维度过滤条件正确显示

## Phase 5: 测试与文档

- [x] 单元测试覆盖枚举类型 CRUD
- [x] 单元测试覆盖枚举值 CRUD
- [x] 单元测试覆盖可维护性控制
- [x] 单元测试覆盖维度过滤
- [x] 集成测试覆盖前端枚举值管理流程
- [x] 集成测试覆盖字段配置枚举关联
- [x] 集成测试覆盖业务表单枚举选择

## Security

- [x] 枚举类型创建接口有权限控制（仅管理员）
- [x] 枚举值删除接口正确检查 is_system 标志
- [x] 系统枚举（category=system）不可通过 API 修改
- [x] 维度过滤参数已做输入验证

## Performance

- [x] 枚举值列表接口支持分页
- [x] 枚举值选择组件支持搜索
- [x] 常用枚举值有缓存机制
