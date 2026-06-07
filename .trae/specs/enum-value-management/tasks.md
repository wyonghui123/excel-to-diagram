# Tasks

## Phase 1: 元模型和数据库

- [x] Task 1: 创建枚举类型元模型定义
  - [x] 创建 `meta/schemas/enum_type.yaml` 文件
  - [x] 定义字段：id, name, category, mutability, dimension_schema, description
  - [x] 配置 UI 视图：列表、详情、表单

- [x] Task 2: 创建枚举值元模型定义
  - [x] 创建 `meta/schemas/enum_value.yaml` 文件
  - [x] 定义字段：id, enum_type_id, code, name, name_en, dimensions, sort_order, is_active, is_system, parent_code
  - [x] 配置 UI 视图：列表、详情、表单

- [x] Task 3: 扩展 MetaField 元模型
  - [x] 在 `meta/core/models.py` 中 MetaField 类添加 enum_type 属性
  - [x] 添加 enum_filter 属性（Dict 类型）
  - [x] 添加 enum_default_value 属性

- [x] Task 4: 同步数据库 Schema
  - [x] 运行 `python -m meta.tools.sync_schema --diff` 检查变更
  - [x] 运行 `python -m meta.tools.sync_schema --execute` 执行同步

## Phase 2: 后端 API

- [x] Task 5: 创建枚举类型 API
  - [x] 创建 `meta/api/enum_api.py` 文件
  - [x] 实现枚举类型列表接口 GET /api/v1/enum-types
  - [x] 实现枚举类型详情接口 GET /api/v1/enum-types/{id}
  - [x] 实现枚举类型创建接口 POST /api/v1/enum-types（仅业务枚举）
  - [x] 实现枚举类型更新接口 PUT /api/v1/enum-types/{id}
  - [x] 实现枚举类型删除接口 DELETE /api/v1/enum-types/{id}

- [x] Task 6: 创建枚举值 API
  - [x] 在 `meta/api/enum_api.py` 中添加枚举值接口
  - [x] 实现枚举值列表接口 GET /api/v1/enum-types/{type_id}/values（支持维度过滤）
  - [x] 实现枚举值详情接口 GET /api/v1/enum-values/{id}
  - [x] 实现枚举值创建接口 POST /api/v1/enum-types/{type_id}/values
  - [x] 实现枚举值更新接口 PUT /api/v1/enum-values/{id}
  - [x] 实现枚举值删除接口 DELETE /api/v1/enum-values/{id}（检查 is_system）

- [x] Task 7: 实现可维护性控制逻辑
  - [x] 在创建枚举值时检查 mutability 是否为 locked
  - [x] 在删除枚举值时检查 is_system 和 mutability
  - [x] 返回适当的错误消息

## Phase 3: 前端管理界面

- [x] Task 8: 创建枚举类型列表页
  - [x] 创建 `src/views/SystemManagement/EnumTypeManagement.vue`
  - [x] 实现枚举类型列表展示
  - [x] 实现筛选功能（分类、可维护性）
  - [x] 实现新建业务枚举对话框

- [x] Task 9: 创建枚举值管理页
  - [x] 创建 `src/views/SystemManagement/EnumValueManagement.vue`
  - [x] 实现枚举值列表展示
  - [x] 实现维度标签页切换（多维枚举）
  - [x] 实现枚举值新增/编辑表单
  - [x] 实现枚举值删除功能（带权限检查）

- [x] Task 10: 创建枚举值编辑表单
  - [x] 创建 `src/views/SystemManagement/EnumValueFormDialog.vue`
  - [x] 实现基本信息输入（编码、名称、英文名称）
  - [x] 实现维度配置（多维枚举）
  - [x] 实现显示控制（排序、状态）

## Phase 4: 集成与迁移

- [x] Task 11: 迁移现有枚举值
  - [x] 创建迁移脚本 `meta/scripts/migrate_enums.py`
  - [x] 迁移 FieldType 枚举到 enum_values 表
  - [x] 迁移 RelationType 枚举到 enum_values 表
  - [x] 迁移其他系统枚举
  - [x] 设置 is_system = true

- [x] Task 12: 集成到字段配置
  - [x] 修改 `DynamicForm.vue` 支持枚举类型字段
  - [x] 实现维度过滤逻辑
  - [x] 实现默认值填充

- [x] Task 13: 创建枚举选择组件
  - [x] 创建 `src/components/common/EnumSelect.vue`
  - [x] 支持从 API 加载枚举值
  - [x] 支持维度过滤参数
  - [x] 支持搜索和分页

## Phase 5: 测试与文档

- [x] Task 14: 编写单元测试
  - [x] 创建 `meta/tests/test_enum_api.py`
  - [x] 测试枚举类型 CRUD
  - [x] 测试枚举值 CRUD
  - [x] 测试可维护性控制
  - [x] 测试维度过滤

- [x] Task 15: 编写集成测试
  - [x] 测试前端枚举值管理流程
  - [x] 测试字段配置枚举关联
  - [x] 测试业务表单枚举选择

---

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1, Task 2
- Task 4 depends on Task 1, Task 2, Task 3
- Task 5 depends on Task 4
- Task 6 depends on Task 4
- Task 7 depends on Task 5, Task 6
- Task 8 depends on Task 5
- Task 9 depends on Task 6, Task 8
- Task 10 depends on Task 9
- Task 11 depends on Task 4
- Task 12 depends on Task 6, Task 13
- Task 13 depends on Task 6
- Task 14 depends on Task 5, Task 6, Task 7
- Task 15 depends on Task 8, Task 9, Task 10, Task 12, Task 13

# Parallelizable Work

以下任务可以并行执行：
- Task 1, Task 2, Task 3（元模型定义）
- Task 5, Task 6（后端 API）
- Task 8, Task 11（前端页面和迁移脚本）
- Task 14, Task 15（测试）
