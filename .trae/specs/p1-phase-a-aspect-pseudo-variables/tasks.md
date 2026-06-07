# Tasks

## Task 1: Aspect 模型定义与解析
- [x] SubTask 1.1: `meta/core/models.py` - `SemanticAnnotation` 新增 `auto_fill: Dict[str, str]` 属性
- [x] SubTask 1.2: `meta/core/models.py` - `MetaObject` 新增 `aspects: List[str]` 属性，`includes` 保留为兼容别名
- [x] SubTask 1.3: `meta/core/yaml_loader.py` - `parse_semantics()` 新增 `auto_fill` 字段解析
- [x] SubTask 1.4: `meta/core/yaml_loader.py` - `parse_meta_object()` 解析 `aspects` 配置，`includes` 自动合并到 `aspects`
- [x] SubTask 1.5: `meta/core/yaml_loader.py` - 新增 `parse_aspects_yaml()` 函数，加载 aspects.yaml 中的 Aspect 定义（含 fields + semantics + validations + rules）
- [x] SubTask 1.6: `meta/core/yaml_loader.py` - `_resolve_includes()` 升级为 `_resolve_aspects()`，支持 fields + semantics + validations + rules 合并，冲突时后引用覆盖先引用并记录警告
- [x] SubTask 1.7: `meta/core/yaml_loader.py` - Aspect 中的 validations/rules 合并时，rule.id 加 Aspect 名称前缀避免冲突
- [x] SubTask 1.8: 验证：现有 YAML 无 aspects/includes 时加载行为不变；有 aspects 时字段/规则正确展开

## Task 2: Pseudo Variables 伪变量解析器
- [x] SubTask 2.1: `meta/core/action_executor.py` - 新增 `PseudoVariableResolver` 类，支持内置伪变量：`$now`（当前时间 ISO 格式）、`$user.id`（当前用户ID）、`$user.name`（当前用户名）、`$uuid`（自动生成 UUID）
- [x] SubTask 2.2: `meta/core/action_executor.py` - `PseudoVariableResolver` 从 `AuditLogger._current_user` 获取用户上下文
- [x] SubTask 2.3: `meta/core/action_executor.py` - `_prepare_data()` 改为配置驱动：遍历字段检查 `auto_fill` 配置，on_create 时注入 `auto_fill.on_create`，on_update 时注入 `auto_fill.on_update`
- [x] SubTask 2.4: `meta/core/action_executor.py` - 移除 `_prepare_data()` 中 `created_at`/`updated_at` 的硬编码 `datetime.now()` 逻辑
- [x] SubTask 2.5: 验证：有 auto_fill 配置的字段正确注入伪变量值；无 auto_fill 的字段行为不变

## Task 3: 标准 Aspect 库与 YAML 迁移
- [x] SubTask 3.1: 创建 `meta/schemas/aspects.yaml`，定义 4 个标准 Aspect：audit_aspect（含 auto_fill）、hierarchy_aspect、naming_aspect、owner_aspect
- [x] SubTask 3.2: 保留 `meta/schemas/shared_properties.yaml` 不变（向后兼容），aspects.yaml 引用其字段定义
- [x] SubTask 3.3: 迁移 `domain.yaml` - `includes: [hierarchy_fields, audit_fields, owner_fields, naming_fields]` → `aspects: [hierarchy_aspect, audit_aspect, owner_aspect, naming_aspect]`
- [x] SubTask 3.4: 迁移 `sub_domain.yaml`、`service_module.yaml`、`business_object.yaml`、`relationship.yaml` 的 includes → aspects
- [x] SubTask 3.5: 验证：迁移后所有对象的字段列表、semantics、validations 与迁移前完全一致

## Task 4: 测试与端到端验证
- [x] SubTask 4.1: 新增 `test_aspect_resolution.py` - 测试 Aspect 定义加载、字段合并、本地覆盖、多 Aspect 冲突、includes 向后兼容
- [x] SubTask 4.2: 新增 `test_pseudo_variables.py` - 测试 $now/$user/$uuid 注入、无用户上下文时返回空、auto_fill on_create/on_update 触发时机
- [x] SubTask 4.3: 运行现有测试套件，确保所有 569+ 测试通过
- [x] SubTask 4.4: 端到端验证：创建 domain 时 created_at/updated_at 自动填充、created_by/updated_by 自动填充当前用户

# Task Dependencies
- [Task 2] depends on [Task 1] (auto_fill 属性需要先在 SemanticAnnotation 中定义)
- [Task 3] depends on [Task 1, Task 2] (标准 Aspect 库需要 Aspect 模型和 auto_fill 都就绪)
- [Task 4] depends on [Task 1, Task 2, Task 3] (测试需要所有功能就绪)
- [Task 1] 可独立开始
