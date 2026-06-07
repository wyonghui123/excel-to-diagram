# 9. 变更/设计提案 (RFC)

## 9.1 As-Is 分析

### 当前架构

```
YAML Schema → MetaRegistry → BOFramework → REST API → 前端Dynamic UI
                                                    ↘ 前端静态menuConfig.js
权限: init_auth.py(硬编码) → permissions表
菜单: init_menu_permissions.py(硬编码) → menu_permissions表
      前端: menuConfig.js + useMenuPermissions.js(并行维护)
```

### 当前问题

| # | 问题 | 影响文件 |
|---|------|---------|
| 1 | `category_config` 未消费 | models.py → DB |
| 2 | `seed_permissions()` 硬编码5个BO | init_auth.py |
| 3 | `required_permissions` 手动JSON | init_menu_permissions.py |
| 4 | 前端5套并行菜单定义 | menuConfig.js, useMenuPermissions.js, init_menu_permissions.py |
| 5 | 业务BO无 `category_config` | domain.yaml, sub_domain.yaml 等6文件 |
| 6 | 路由仅 `isAdmin` 判断 | router/index.js, authStore.js |
| 7 | `PERMISSION_LABELS` 字典 (30+条目) | role_menu_api.py |
| 8 | `MENU_DISPLAY_NAMES` 字典 (5条目) | role_menu_api.py |
| 9 | `_resource_name/_action_name` 字典 | init_auth.py |
| 10 | `_get_resource_name` 字典 | data_permission_api.py |

### 关键代码路径

- `meta/schemas/*.yaml` — BO定义（事实源）
- `meta/core/models.py` — MetaObject, MetaAction, BoCategoryConfig, registry
- `meta/core/bo_framework.py` — BOFramework, get_ui_config()
- `meta/scripts/init_auth.py` — seed_permissions()
- `meta/scripts/init_menu_permissions.py` — 菜单初始化
- `meta/api/role_menu_api.py` — 角色菜单API, PERMISSION_LABELS
- `meta/schemas/management_dimension.yaml` — 管理维度定义
- `meta/services/management_dimension_engine.py` — ImpactPreview
- `src/config/menuConfig.js` — 静态菜单
- `src/composables/useMenuPermissions.js` — menuIconMap, getDefaultMenus
- `src/stores/authStore.js` — isAdmin 判断
- `src/views/SystemManagement/RolePermissionCenter.vue` — 权限配置中心
- `src/views/SystemManagement/components/PermissionConfigPanel.vue` — 权限面板
- `src/views/SystemManagement/components/MenuPermissionMatrix.vue` — 菜单矩阵
- `src/views/SystemManagement/components/ConditionRuleDialog.vue` — 条件规则

## 9.2 目标状态

### 目标架构

```
          meta/schemas/*.yaml (唯一真相源)
         /        |          \
    actions   ui_view_config  category_config  data_permission_dimensions
       |          |               |                    |
       v          v               v                    v
  permissions表  menu表       data规则          字段级权限覆盖
       |          |               |                    |
       +----+-----+------+--------+                    |
            |            |                             |
            v            v                             v
     role_permissions  role_menu_permissions  role_dimension_scopes
            |            |               |
            +-----+------+               |
                  |                      |
                  v                      v
           用户有效权限           DimensionScopeEngine
                                     /          \
                              推荐菜单+权限    数据条件
```

### 关键变更

| 变更 | 类型 | 影响 |
|------|------|------|
| 新增 `menu.yaml` | Schema | Menu 成为一等BO |
| 新增 `role_dimension_scope.yaml` | Schema | 维度范围声明表 |
| 新增 `PermissionSyncService` | Service | 替代 init_auth.py 硬编码 |
| 新增 `MenuAutoGenerator` | Service | 菜单自动生成引擎 |
| 新增 `DimensionScopeEngine` | Service | 维度范围推导引擎 |
| `MetaAction` 增加类级常量 `ACTION_SUFFIX_MAP` | Model | 唯一映射源 |
| `MetaObject` 增加 `get_action_by_suffix/get_permission_label` | Model | 动态标签推导 |
| `MetaObject` 增加 `data_permission_dimensions` | Model | 数据权限维度声明 |
| 激活 `PermissionAnnotation` | Model | 字段级权限 |
| 新增 `GET /api/v1/menu/visible` | API | 统一菜单端点 |
| 新增 `POST /api/v1/roles/{id}/dimension-scopes` | API | 维度范围端点 |
| 新增 `GET /api/v1/roles/{id}/derived-permissions` | API | 推导预览端点 |
| 前端新增 `DimensionScopePanel` | Component | 维度配置面板 |
| 前端 `menuConfig.js` → deprecated | Frontend | 废除静态菜单 |
| 前端路由守卫增加细粒度权限检查 | Frontend | 安全增强 |
| `role_menu_api.py` 移除 `PERMISSION_LABELS`/`MENU_DISPLAY_NAMES` | API | 消除硬编码 |
| `init_auth.py` 移除 `seed_permissions()` (改为委托) | Script | 消除硬编码 |
| `menu_permissions` 表新增 color, description, page_type, object_types, auto_generated | DB | Schema 扩展 |

### 设计备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: 维度驱动替换菜单驱动 | 配置流完全统一 | 风险大，不适应特殊场景 | 拒绝 |
| B: 维度驱动 + 菜单驱动共存 | 向后兼容，灵活 | 实现复杂度略高 | **选择** |
| C: 保持菜单驱动 | 零变更风险 | 不解决根本问题 | 拒绝 |
| D: 维度范围存为 JSON (单一字段) | 简单 | 无法利用DB索引和关联查询 | 拒绝 |
| E: 维度范围独立表 | 可索引，可关联，可扩展 | 多一张表 | **选择** |
