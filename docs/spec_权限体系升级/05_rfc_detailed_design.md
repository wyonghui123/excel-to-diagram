## 9.3 详细设计

### 9.3.1 模块/组件设计

```
meta/core/models.py (增强)
  MetaAction
    + ACTION_SUFFIX_MAP: ClassVar[Dict]  ← 唯一映射: crud_create→create, ...
    + get_permission_suffix() → str
    + get_permission_code(object_id) → str
  MetaObject
    + get_action_by_suffix(suffix) → MetaAction
    + get_permission_label(suffix) → str
    + data_permission_dimensions: List[DataPermissionDimension]
  MetaField
    + permission: Optional[PermissionAnnotation]  ← 激活已有字段

meta/services/permission_sync_service.py (新增)
  PermissionSyncService
    + sync_all() → {created, existing, orphaned}
    + sync_for_object(object_id) → List[str]
    + _collect_all_permissions() → Set[str]
    + _derive_permissions_from_object(MetaObject) → List[str]

meta/services/menu_auto_generator.py (新增)
  MenuAutoGenerator
    + generate_object_list_menu(MetaObject) → Dict
    + generate_multi_object_menu(...) → Dict
    + _derive_permissions(MetaObject, read_only) → List[str]
    + _extract_list_config(MetaObject) → Dict
    + generate_all() → List[Dict]

meta/services/dimension_scope_engine.py (新增)
  DimensionScopeEngine
    + expand_dimension_values(role_id) → Dict[str, Set[int]]
    + derive_data_conditions(role_id) → Dict[str, str]
    + derive_recommended_menus(role_id) → List[str]
    + derive_permissions(role_id) → List[str]
    + auto_sync_all(role_id) → Dict
    + _get_all_child_ids(dim_code, parent_ids) → Set[int]
```

### 9.3.2 数据模型变更

**新增表: role_dimension_scopes**

```
| 列名             | 类型    | 说明                    |
|-----------------|---------|------------------------|
| id              | INTEGER | PK                     |
| role_id         | INTEGER | FK → roles.id          |
| dimension_code  | TEXT    | FK → mgmt_dimensions.code |
| dimension_values| TEXT    | JSON: [1,2,5]          |
| inherit_children| INTEGER | 0/1, default 1         |
| scope_mode      | TEXT    | include/exclude        |
```

**扩展表: menu_permissions (ALTER TABLE)**

```
| 新增列              | 类型    | 说明                    |
|--------------------|---------|------------------------|
| color              | TEXT    | 主题色                  |
| description        | TEXT    | 功能描述                |
| page_type          | TEXT    | object_list/multi_object_hub/custom_page |
| primary_object_type| TEXT    | 主BO ID                 |
| object_types       | TEXT    | JSON: 关联BO ID列表     |
| auto_generated     | INTEGER | 0/1, default 0          |
```

**新增表: menus (menu.yaml 对应的数据库表)**

与 menu_permissions 结构一致但独立，menu_permissions 可作为 menus 的视图或别名向后兼容。

**MetaAction 新增常量（无DB变更）**

```python
ACTION_SUFFIX_MAP = {
    'crud_create': 'create',
    'crud_read': 'read',
    'crud_update': 'update',
    'crud_delete': 'delete',
}
```

### 9.3.3 主要流程

**流程1: BO注册 → 权限自动同步**

```
1. YAMLLoader 加载 domain.yaml
2. MetaObject 创建，actions 解析
3. MetaRegistry.register(meta_obj)
4. [新增] PermissionSyncService.sync_for_object('domain')
    4a. 遍历 meta_obj.actions
    4b. action.get_permission_code('domain') → 'domain:create'
    4c. INSERT OR IGNORE INTO permissions
5. [新增] MenuAutoGenerator.generate_object_list_menu(meta_obj)
    5a. _derive_permissions(meta_obj) → ['domain:create','domain:read',...]
    5b. _extract_list_config(meta_obj) → page_config
    5c. INSERT OR IGNORE INTO menu_permissions
```

**流程2: 管理员配置维度范围 → 自动推导**

```
1. 管理员在 DimensionScopePanel 选择:
   - product: [1]
   - version: [3]
   - domain: [1, 2, 5] (inherit_children=true)
2. POST /api/v1/roles/{role_id}/dimension-scopes
3. 后端 Save → role_dimension_scopes 表
4. [新增] 调用 GET /api/v1/roles/{role_id}/derived-permissions 预览
    4a. DimensionScopeEngine.expand_dimension_values() → {product:{1}, version:{3}, domain:{1,2,5, child_ids...}}
    4b. derive_recommended_menus() → 遍历菜单，检查BO在维度内是否有数据
    4c. derive_permissions() → 从推荐菜单提取 required_permissions
    4d. derive_data_conditions() → 生成 condition 字符串
5. 前端展示推导结果，管理员确认/调整
6. PUT 确认 → 批量写入 role_menu_permissions + role_permissions + permission_rules
```

**流程3: 权限标签动态推导（零硬编码）**

```
请求: "sub_domain:create" 的显示名称

旧方式: PERMISSION_LABELS.get('sub_domain:create') → 硬编码字典

新方式:
  1. 解析: resource_type='sub_domain', suffix='create'
  2. meta_obj = registry.get('sub_domain')
  3. meta_obj.name → '子领域'
  4. action = meta_obj.get_action_by_suffix('create')
  5. action.name → '创建子领域'
  6. 返回 → '创建子领域'
```

### 9.3.4 API 设计（补充）

**GET /api/v1/menu/visible**

```
Response:
{
  "menus": [{
    "menu_code": "domain-list",
    "menu_name": "领域管理",
    "menu_path": "/domain",
    "icon": "folder",
    "color": "blue",
    "description": "管理领域数据，包括创建、编辑、删除领域",
    "page_type": "object_list",
    "primary_object_type": "domain",
    "sort_order": 1,
    "children": []
  }]
}
```

**POST /api/v1/roles/{role_id}/dimension-scopes**

```
Request:
[{
  "dimension_code": "domain",
  "dimension_values": [1, 2, 5],
  "inherit_children": true,
  "scope_mode": "include"
}]
```

**GET /api/v1/roles/{role_id}/derived-permissions**

```
Response:
{
  "dimension_scopes": {"domain": [1,2,5,7,8,9], "version": [3]},
  "recommended_menus": ["domain-list", "sub-domain-list", "arch-data"],
  "derived_permissions": ["domain:read", "domain:create", "domain:update", ...],
  "data_conditions": {
    "domain": "version_id = 3 AND domain_id IN (1,2,5,7,8,9)",
    "service_module": "version_id = 3 AND domain_id IN (1,2,5,7,8,9)"
  }
}
```
