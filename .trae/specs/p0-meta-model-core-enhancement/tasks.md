# Tasks

## Task 1: Shared Property 共享属性 - YAML 定义与解析
- [x] SubTask 1.1: 创建 `meta/schemas/shared_properties.yaml`，定义共享字段组（hierarchy_fields, audit_fields, owner_fields, naming_fields）
- [x] SubTask 1.2: `MetaField` 新增 `included_from: str = ""` 可选属性
- [x] SubTask 1.3: `MetaObject` 新增 `includes: List[str]` 属性
- [x] SubTask 1.4: `yaml_loader.py` 新增 `parse_shared_properties()` 函数，加载 shared_properties.yaml
- [x] SubTask 1.5: `yaml_loader.py` 新增 `_resolve_includes()` 函数，将 includes 引用展开合并到 fields 列表
- [x] SubTask 1.6: `yaml_loader.py` 的 `load_schema()` 流程中，在 parse_field 之前调用 `_resolve_includes()`
- [x] SubTask 1.7: 本地字段与共享字段同 id 时，本地覆盖共享，设置 `included_from` 标记
- [x] SubTask 1.8: 验证：现有 YAML 无 includes 时行为不变；有 includes 时字段正确展开

## Task 2: Composition 组合关系 - 模型与解析
- [x] SubTask 2.1: `RelationType` 枚举新增 `COMPOSITION = "composition"`
- [x] SubTask 2.2: `MetaRelation` 新增 `cascade_delete: bool = False` 和 `ownership: bool = False` 属性
- [x] SubTask 2.3: `yaml_loader.py` 的 `RELATION_TYPE_MAP` 新增 `"composition": RelationType.COMPOSITION` 映射
- [x] SubTask 2.4: `parse_relation()` 解析 `cascade_delete` 和 `ownership` 字段
- [x] SubTask 2.5: 验证：现有 YAML 中 `type: parent_child` 行为不变；`type: composition` 正确解析

## Task 3: Composition 组合关系 - CascadeService 集成
- [x] SubTask 3.1: `CascadeService` 新增 `_get_composition_cascade_strategy()` 方法，从 relation 定义读取级联策略
- [x] SubTask 3.2: `CascadeService.get_cascade_strategy()` 修改优先级：relation composition > hierarchies.yaml > 默认 RESTRICT
- [x] SubTask 3.3: `CascadeService._collect_affected()` 支持从 composition relation 收集子对象
- [x] SubTask 3.4: `manage_service.py` 的 delete 流程中，先检查 composition relation 的级联策略再执行
- [x] SubTask 3.5: 验证：composition + cascade_delete=true 时级联删除；cascade_delete=false 时阻止删除

## Task 4: Authorization 声明式权限 - 模型与解析
- [x] SubTask 4.1: `MetaObject` 新增 `authorization: Optional[Dict] = None` 属性
- [x] SubTask 4.2: `yaml_loader.py` 的 `parse_object()` 解析 `authorization` 配置节
- [x] SubTask 4.3: authorization 配置结构：`{check: bool, permissions: {create: str, read: str, update: str, delete: str}, scope: str}`
- [x] SubTask 4.4: 当 `check: true` 但未指定 permissions 时，自动生成 `{object_id}:{action}` 格式权限码
- [x] SubTask 4.5: 验证：现有 YAML 无 authorization 时行为不变

## Task 5: Authorization 声明式权限 - API 端点绑定
- [x] SubTask 5.1: `manage_api.py` 新增 `_get_permission_code(object_type, action)` 函数，从 MetaObject.authorization 读取权限码
- [x] SubTask 5.2: `manage_api.py` 的 CRUD 端点（create/update/delete/get/list）添加权限检查逻辑
- [x] SubTask 5.3: AUTH_ENABLED=false 时跳过权限检查，与当前行为一致
- [x] SubTask 5.4: 行级权限：列表查询时根据 `authorization.scope` 注入过滤条件
- [x] SubTask 5.5: 验证：有 authorization 配置时权限检查生效；无配置时行为不变

## Task 6: YAML Schema 更新与端到端验证
- [x] SubTask 6.1: 选择一个核心对象（如 domain.yaml）添加 `includes: [hierarchy_fields, audit_fields, owner_fields]` 和 `authorization` 配置
- [x] SubTask 6.2: 将 domain.yaml 中重复的共享字段移除，改为 includes 引用
- [x] SubTask 6.3: 为 domain 的 relation 添加 `type: composition` + `cascade_delete: true`（如 domain -> sub_domain）
- [x] SubTask 6.4: 端到端验证：domain 创建/读取/更新/删除流程正常
- [x] SubTask 6.5: 端到端验证：删除 domain 时级联删除 sub_domain
- [x] SubTask 6.6: 端到端验证：权限检查按 authorization 配置生效

# Task Dependencies
- [Task 2] depends on [Task 1] (Composition 关系中的层级字段可通过 Shared Property 复用)
- [Task 3] depends on [Task 2] (CascadeService 需要 Composition 模型先定义)
- [Task 5] depends on [Task 4] (API 绑定需要 Authorization 模型先定义)
- [Task 6] depends on [Task 1, Task 3, Task 5] (端到端验证需要所有功能就绪)
- [Task 1] 和 [Task 4] 可并行
