# 权限体系元数据驱动化 — 细化方案设计

> 文档日期：2026-05-16  
> 基于：[竞品架构分析_元数据驱动与权限模型](./competitive-analysis-metadata-permission.md) 及代码库深入分析  
> 目标：将「菜单 = 对象(s) + config + 通用页面组件」的元数据闭环落地到代码级方案

---

## 目录

1. [总体策略："YAML 是单一真相来源"](#1-总体策略)
2. [方案一：Menu BO 元数据化](#2-方案一menu-bo-元数据化)
3. [方案二：权限从 BO Actions 自动同步](#3-方案二权限从-bo-actions-自动同步)
4. [方案三：数据权限维度声明化](#4-方案三数据权限维度声明化)
5. [方案四：多租户架构设计](#5-方案四多租户架构设计)
6. [方案五：字段级读写权限控制](#6-方案五字段级读写权限控制)
7. [实施路线图](#7-实施路线图)

---

## 1. 总体策略："YAML 是单一真相来源" {#1-总体策略}

### 1.1 当前问题全景

经过代码库深入分析，当前权限体系存在 **六处断裂**：

| # | 断裂点 | 表现 |
|---|--------|------|
| 1 | **权限创建与 YAML 断开** | `permissions` 表由 `init_auth.py` 的 `seed_permissions()` 硬编码填充，与 BO YAML 的 `actions`/`category_config` 无关 |
| 2 | **菜单权限与 BO 断开** | `menu_permissions.required_permissions` 在 `init_menu_permissions.py` 中硬编码，不引用 BO 元数据 |
| 3 | **前端菜单三套定义并行** | `menuConfig.js`、`init_menu_permissions.py`、`useMenuPermissions.js` 各自维护一套菜单 |
| 4 | **`category_config` 存而不用** | BO 的 `category_config` 被解析存储但不在运行时消费 |
| 5 | **业务 BO 无 `category_config`** | `domain`、`sub_domain` 等 YAML 完全不声明权限配置 |
| 6 | **API 两套实现混用** | 权限 API 用原始 SQL（`menu_permission_api.py`、`permission_service.py`），业务 API 用 BOFramework |

### 1.2 目标架构

```
                        ┌─────────────────────┐
                        │   BO YAML Schema     │ ← 单一真相来源
                        │   (fields, actions,  │
                        │    relations,        │
                        │    category_config,  │
                        │    data_perm_dims,   │
                        │    ui_view_config)   │
                        └──────────┬──────────┘
                                   │ 注册/变更时触发
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
            ┌──────────────┐ ┌──────────┐ ┌──────────────┐
            │ permissions  │ │  menus   │ │ menu_        │
            │ (功能权限表)  │ │ (菜单表)  │ │ required_    │
            │              │ │          │ │ permissions  │
            └──────────────┘ └──────────┘ │ (关联表)      │
                                          └──────────────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  role_permissions /       │
                    │  role_menu_permissions    │
                    │  (角色授权层)              │
                    └──────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  前端菜单 (完全由后端驱动)  │
                    │  MenuConfig API →        │
                    │  Dynamic Sidebar →       │
                    │  Dynamic Router Guards   │
                    └──────────────────────────┘
```

### 1.3 核心设计原则

1. **YAML 是唯一真相来源**：`permissions` 表、`menus` 表的内容完全由 YAML schema 自动生成
2. **BO 注册时自动同步**：Schema 注册/变更时，`PermissionsSynchronizer` 自动刷新相关权限和菜单
3. **前端菜单零静态配置**：删除 `menuConfig.js`，前端菜单完全由 `/api/v2/bo/menu` 接口驱动
4. **向后兼容**：保留现有 API 接口签名，内部实现迁移到新引擎

---

## 2. 方案一：Menu BO 元数据化 {#2-方案一menu-bo-元数据化}

### 2.1 设计思路

将菜单本身定义为一个 BO（`menu`），其 YAML Schema 直接声明菜单与 BO 的关联关系。菜单的 `required_permissions` 不再硬编码，而是从关联 BO 的 `actions` 中自动推导。

### 2.2 Menu BO Schema 设计

```yaml
# meta/schemas/menu.yaml — 完整定义
id: menu
name: 菜单
table_name: menus
label: 菜单
label_plural: 菜单列表
bo_category: CONFIGURATION
description: |-
  系统菜单定义。
  菜单 = 通用页面组件类型(page_type) × 关联对象(object_types) + 配置(page_config)
  权限自动从关联对象的 actions 推导

fields:
  # === 基础信息 ===
  - id: menu_code
    name: 菜单编码
    type: string
    length: 64
    required: true
    unique: true
    semantics:
      is_display_name: true
    widget: text
    widget_properties:
      placeholder: 如 product-version, arch-data

  - id: menu_name
    name: 菜单名称
    type: string
    length: 64
    required: true
    i18n: true
    widget: text

  - id: icon
    name: 菜单图标
    type: string
    length: 32
    widget: icon_picker

  - id: sort_order
    name: 排序序号
    type: integer
    default: 0

  - id: is_active
    name: 是否启用
    type: boolean
    default: true

  # === 页面类型（通用组件） ===
  - id: page_type
    name: 页面类型
    type: string
    length: 32
    required: true
    enum_values:
      - value: object_list
        label: 单对象列表页
        description: MetaListPage 组件渲染
      - value: object_detail
        label: 单对象详情页
        description: ObjectPage/DetailPage 组件渲染
      - value: multi_object_hub
        label: 多对象聚合页
        description: 多对象导航枢纽页
      - value: custom_page
        label: 自定义页面
        description: 独立开发的页面

  # === 关联对象（核心：菜单=对象+配置） ===
  - id: object_types
    name: 关联对象类型
    type: json
    required: true
    description: |-
      关联的 BO object_type 列表。
      - page_type=object_list 时，通常填写 1 个对象
      - page_type=multi_object_hub 时，填写多个对象
      - page_type=custom_page 时可为空
    widget: multi_select
    widget_properties:
      source: bo_registry
      placeholder: 选择关联的业务对象

  - id: default_object_type
    name: 默认对象类型
    type: string
    length: 64
    description: 多对象页面时的默认聚焦对象

  # === 页面配置 ===
  - id: page_config
    name: 页面配置
    type: json
    description: |-
      额外的页面级配置参数，会与 BO YAML 的 ui_view_config 合并：
      - filters: 全局过滤器列表
      - default_sort: 默认排序
      - enable_export: 是否启用导出
      - enable_import: 是否启用导入
      - show_statistics: 是否显示统计面板
      - hierarchy_context: 多对象页面的层级上下文字段

  # === 权限推导配置 ===
  - id: auto_generate_permissions
    name: 自动生成权限
    type: boolean
    default: true
    description: |-
      若为 true，required_permissions 从关联 BO 的 actions 自动推导。
      若为 false，使用 manual_permissions 字段手动指定。

  - id: manual_permissions
    name: 手动指定权限
    type: json
    description: 当 auto_generate_permissions=false 时使用

  - id: required_permissions
    name: 关联功能权限
    type: json
    readonly: true
    description: |-
      最终有效权限列表（自动推导或手动指定）。
      格式：[{ code: "domain:read", source: "auto"|"manual" }]

  # === 数据权限提示 ===
  - id: data_scope_hint
    name: 数据权限提示
    type: json
    description: |-
      提示需要配置的数据权限类型。
      从关联 BO 的 data_permission_dimensions 自动推导。

  # === 层级结构 ===
  - id: parent_menu
    name: 父菜单
    type: string
    length: 64
    widget: tree_select
    widget_properties:
      source: menus

  # === 路由信息 ===
  - id: route_path
    name: 路由路径
    type: string
    length: 256
    description: 前端路由路径，如 /data/:productId?/:versionId?
    required: true

  - id: route_name
    name: 路由名称
    type: string
    length: 64

  - id: component_name
    name: 组件名称
    type: string
    length: 64
    description: |-
      关联的 Vue 组件名。
      - page_type=object_list → "MetaListPage"
      - page_type=object_detail → "ObjectDetailPage"
      - page_type=multi_object_hub → "ArchWorkspace"
      系统自动推导

# === 关联关系 ===
relations:
  - id: menu_parent
    name: 父子层级
    type: parent_child
    parent_field: parent_menu
    child_field: menu_code
    direction: self

  - id: menu_to_permissions
    name: 菜单关联权限
    description: 菜单的 required_permissions 关联到的功能权限
    type: association
    target: permission
    association_type: many_to_many
    join_table: menu_required_permissions
    join_fields:
      - source_field: menu_code
        target_field: code

# === 操作定义 ===
actions:
  - id: menu_list
    name: 查询菜单列表
    type: crud
    method: GET
    path: /api/v2/bo/menu
    description: 获取所有菜单（含权限过滤）

  - id: menu_read
    name: 查询单个菜单
    type: crud
    method: GET
    path: /api/v2/bo/menu/{id}

  - id: menu_create
    name: 创建菜单
    type: crud
    method: POST
    path: /api/v2/bo/menu

  - id: menu_update
    name: 更新菜单
    type: crud
    method: PUT
    path: /api/v2/bo/menu/{id}

  - id: menu_delete
    name: 删除菜单
    type: crud
    method: DELETE
    path: /api/v2/bo/menu/{id}

  - id: menu_sync_from_bo
    name: 从BO元数据同步菜单
    type: business
    method: POST
    path: /api/v2/bo/menu/sync-from-bo
    description: 扫描所有已注册的BO，自动创建/更新对应菜单

# === 权限配置 ===
category_config:
  create_permission: menu:create
  update_permission: menu:update
  delete_permission: menu:delete
  owner_auto_permission: false

# === UI 视图配置 ===
ui_view_config:
  list:
    columns:
      - field: menu_code
        width: 180
      - field: menu_name
        width: 160
      - field: page_type
        width: 140
      - field: object_types
        width: 200
      - field: route_path
        width: 240
      - field: sort_order
        width: 80
      - field: is_active
        width: 80
      - field: parent_menu
        width: 200
  detail:
    facets:
      - id: basic
        label: 基本信息
        icon: Info
        order: 1
        render_mode: form
        columns: 2
        fields:
          - menu_code
          - menu_name
          - icon
          - sort_order
          - is_active
          - page_type
      - id: objects
        label: 关联对象
        icon: Link
        order: 2
        render_mode: form
        columns: 1
        fields:
          - object_types
          - default_object_type
      - id: routing
        label: 路由配置
        icon: Map
        order: 3
        render_mode: form
        columns: 2
        fields:
          - route_path
          - route_name
          - component_name
          - parent_menu
      - id: permissions
        label: 权限配置
        icon: Lock
        order: 4
        render_mode: form
        columns: 1
        fields:
          - auto_generate_permissions
          - manual_permissions
          - required_permissions
      - id: page_config
        label: 页面配置
        icon: Tools
        order: 5
        render_mode: code
        fields:
          - page_config
```

### 2.3 菜单自动生成引擎

当 BO Schema 注册时，`MenuAutoGenerator` 自动创建对应的菜单记录：

```python
# meta/services/menu_auto_generator.py

from typing import List, Optional
from dataclasses import dataclass
from meta.core.models import MetaObject, BusinessObjectCategory

@dataclass
class AutoMenuRule:
    """菜单自动生成规则"""
    page_type: str             # 页面类型
    object_types: List[str]    # 关联对象
    route_path: str            # 路由路径
    component_name: str        # 组件名称
    permissions_source: str    # 'actions' | 'category_config'
    icon: str                  # 默认图标
    sort_order_base: int       # 排序基数

class MenuAutoGenerator:
    """
    菜单自动生成引擎
    
    规则：当 BO 注册时，自动生成对应菜单。
    菜单编码格式：{object_type}-{page_type_suffix}
    """
    
    # 页面类型 → 路由规则
    PAGE_TYPE_RULES = {
        'object_list': AutoMenuRule(
            page_type='object_list',
            route_path='/system/{object_type_plural}',
            component_name='MetaListPage',
            permissions_source='actions',
            icon='List',
            sort_order_base=100,
        ),
        'multi_object_hub': AutoMenuRule(
            page_type='multi_object_hub',
            route_path='/data/{context}',
            component_name='ArchWorkspace',
            permissions_source='actions',
            icon='DataAnalysis',
            sort_order_base=200,
        ),
    }
    
    @classmethod
    def generate_for_bo(cls, meta_obj: MetaObject) -> Optional[dict]:
        """
        为单个 BO 自动生成菜单定义
        
        Args:
            meta_obj: 已注册的元对象
        
        Returns:
            菜单 dict，如果 BO 不需要自动菜单则返回 None
        """
        # 只有需要用户界面的 BO 才自动生成菜单
        if not cls._should_generate_menu(meta_obj):
            return None
        
        rule = cls.PAGE_TYPE_RULES['object_list']
        objects = [meta_obj.id]
        
        # 生成菜单编码
        menu_code = f"{meta_obj.id}-list"
        
        # 从 actions 自动推导 required_permissions
        required_permissions = cls._derive_permissions(meta_obj, rule)
        
        # 从 BO 的 ui_view_config 推导页面配置
        page_config = cls._derive_page_config(meta_obj)
        
        # 从 BO 的 data_permission_dimensions 推导数据权限提示
        data_scope_hint = cls._derive_data_scope_hint(meta_obj)
        
        return {
            'menu_code': menu_code,
            'menu_name': meta_obj.label_plural or meta_obj.name,
            'icon': cls._infer_icon(meta_obj),
            'sort_order': rule.sort_order_base,
            'page_type': rule.page_type,
            'object_types': objects,
            'route_path': f"/system/{meta_obj.table_name}",
            'route_name': f"{meta_obj.id}List",
            'component_name': rule.component_name,
            'auto_generate_permissions': True,
            'required_permissions': required_permissions,
            'data_scope_hint': data_scope_hint,
            'page_config': page_config,
            'parent_menu': cls._infer_parent_menu(meta_obj),
        }
    
    @classmethod
    def _should_generate_menu(cls, meta_obj: MetaObject) -> bool:
        """判断是否需要为 BO 自动生成菜单"""
        # 跳过纯内部表（以 _ 开头的）
        if meta_obj.id.startswith('_'):
            return False
        # 跳过没有 UI 配置的
        if not meta_obj.ui_view_config:
            return False
        return True
    
    @classmethod
    def _derive_permissions(cls, meta_obj: MetaObject, rule: AutoMenuRule) -> list:
        """
        从 BO actions 自动推导 required_permissions
        
        对于 object_list 页面，默认需要：
        - {bo}:read     (列表查看)
        - {bo}:list     (分页查询)
        - 如果 actions 中有 export，还需要 {bo}:export
        """
        permissions = []
        bo_id = meta_obj.id
        
        # 基础读权限（所有页面都需要）
        permissions.append({
            'code': f'{bo_id}:read',
            'source': 'auto',
            'action_id': 'crud_read'
        })
        permissions.append({
            'code': f'{bo_id}:list',
            'source': 'auto',
            'action_id': 'crud_list'
        })
        
        # 从 actions 中查找其他必要权限
        if meta_obj.actions:
            for action in meta_obj.actions:
                if action.type == 'business' and 'export' in (action.id or ''):
                    permissions.append({
                        'code': f'{bo_id}:export',
                        'source': 'auto',
                        'action_id': action.id
                    })
        
        return permissions
    
    @classmethod
    def _derive_page_config(cls, meta_obj: MetaObject) -> dict:
        """从 BO 的 ui_view_config 推导页面配置"""
        config = {}
        if meta_obj.ui_view_config and meta_obj.ui_view_config.get('list'):
            list_config = meta_obj.ui_view_config['list']
            config['list_columns'] = list_config.get('columns', [])
            config['default_sort'] = list_config.get('default_sort', None)
            config['enable_export'] = list_config.get('enable_export', False)
            config['enable_import'] = list_config.get('enable_import', False)
        return config
    
    @classmethod
    def _derive_data_scope_hint(cls, meta_obj: MetaObject) -> dict:
        """从 BO 的 data_permission_dimensions 推导数据权限提示"""
        if hasattr(meta_obj, 'data_permission_dimensions'):
            dims = meta_obj.data_permission_dimensions
            return {
                'dimensions': [d.get('field') for d in dims],
                'has_owner_scope': any(d.get('type') == 'owner_scope' for d in dims),
                'has_field_filter': any(d.get('type') == 'field_filter' for d in dims),
            }
        return {}
    
    @classmethod
    def _infer_icon(cls, meta_obj: MetaObject) -> str:
        """从 BO 分类推断默认图标"""
        icon_map = {
            BusinessObjectCategory.MASTER_DATA: 'Folder',
            BusinessObjectCategory.TRANSACTIONAL: 'Document',
            BusinessObjectCategory.ANALYTICAL: 'DataAnalysis',
            BusinessObjectCategory.CONFIGURATION: 'Setting',
        }
        return icon_map.get(meta_obj.bo_category, 'List')
    
    @classmethod
    def _infer_parent_menu(cls, meta_obj: MetaObject) -> Optional[str]:
        """推断父菜单"""
        if meta_obj.bo_category == BusinessObjectCategory.CONFIGURATION:
            return 'system'
        return None
    
    @classmethod
    def generate_multi_object_menu(cls, menu_code: str, menu_name: str,
                                    object_types: List[str],
                                    route_path: str,
                                    **kwargs) -> dict:
        """
        生成多对象聚合菜单
        
        Args:
            menu_code: 菜单编码
            menu_name: 菜单名称
            object_types: 关联的多个 BO ID
            route_path: 路由路径
            **kwargs: 额外配置
        
        Returns:
            多对象菜单 dict
        """
        # 合并所有关联 BO 的权限
        all_permissions = []
        for bo_id in object_types:
            all_permissions.append({
                'code': f'{bo_id}:read',
                'source': 'auto',
                'action_id': 'crud_read'
            })
        
        return {
            'menu_code': menu_code,
            'menu_name': menu_name,
            'icon': kwargs.get('icon', 'DataAnalysis'),
            'sort_order': kwargs.get('sort_order', 200),
            'page_type': 'multi_object_hub',
            'object_types': object_types,
            'default_object_type': object_types[0] if object_types else None,
            'route_path': route_path,
            'component_name': 'ArchWorkspace',
            'auto_generate_permissions': True,
            'required_permissions': all_permissions,
            'page_config': kwargs.get('page_config', {}),
            'parent_menu': kwargs.get('parent_menu'),
        }
```

### 2.4 Schema 注册时自动触发

在 BO 注册流程中嵌入菜单同步：

```python
# meta/core/bo_framework.py 或 meta/core/yaml_loader.py

class SchemaLifecycleManager:
    """管理 Schema 的注册后生命周期事件"""
    
    @staticmethod
    def on_schema_registered(meta_obj: MetaObject):
        """Schema 注册后的统一回调"""
        # 1. 同步权限
        PermissionsSynchronizer.sync_from_bo(meta_obj)
        
        # 2. 同步菜单
        MenuSynchronizer.sync_from_bo(meta_obj)
        
        # 3. 清理缓存
        CacheManager.invalidate_permission_cache()


class MenuSynchronizer:
    """菜单同步器"""
    
    @staticmethod
    def sync_from_bo(meta_obj: MetaObject):
        """
        当 BO 注册时，自动创建/更新对应菜单
        
        流程：
        1. 调用 MenuAutoGenerator.generate_for_bo() 生成菜单定义
        2. 检查 menus 表是否已存在对应 menu_code 的记录
        3. 若不存在 → 创建
        4. 若存在且 auto_generate_permissions=true → 更新
        5. 若存在但 auto_generate_permissions=false → 跳过（手动管理）
        """
        menu_def = MenuAutoGenerator.generate_for_bo(meta_obj)
        if not menu_def:
            return
        
        existing = _query_menu_by_code(menu_def['menu_code'])
        if existing:
            if existing['auto_generate_permissions']:
                _update_menu(existing['id'], menu_def)
            # 否则保留手动配置
        else:
            _create_menu(menu_def)
```

### 2.5 前端菜单完全由后端驱动

改造前端，删除 `menuConfig.js`，菜单完全从 API 获取：

```typescript
// 新文件：src/services/menuService.ts

export interface DynamicMenu {
  menu_code: string
  menu_name: string
  icon: string
  page_type: 'object_list' | 'object_detail' | 'multi_object_hub' | 'custom_page'
  object_types: string[]
  route_path: string
  route_name: string
  component_name: string
  required_permissions: PermissionRef[]
  parent_menu: string | null
  sort_order: number
  children?: DynamicMenu[]
}

/**
 * 获取当前用户有权限的菜单树
 * 
 * 后端自动根据当前用户角色过滤：
 * 1. 查询用户的 role_permissions
 * 2. 查询 menu_required_permissions 关联
 * 3. 仅返回用户有权限的菜单
 */
export async function getUserMenus(): Promise<DynamicMenu[]> {
  const response = await api.get('/api/v2/menus/my')
  return buildMenuTree(response.data)
}

function buildMenuTree(flatMenus: DynamicMenu[]): DynamicMenu[] {
  // 按 parent_menu 构建树形结构
  const map = new Map<string, DynamicMenu>()
  const roots: DynamicMenu[] = []
  
  for (const menu of flatMenus) {
    map.set(menu.menu_code, { ...menu, children: [] })
  }
  
  for (const menu of flatMenus) {
    const node = map.get(menu.menu_code)!
    if (menu.parent_menu && map.has(menu.parent_menu)) {
      map.get(menu.parent_menu)!.children!.push(node)
    } else {
      roots.push(node)
    }
  }
  
  // 按 sort_order 排序
  const sortRecursive = (items: DynamicMenu[]) => {
    items.sort((a, b) => a.sort_order - b.sort_order)
    items.forEach(item => item.children && sortRecursive(item.children))
  }
  sortRecursive(roots)
  
  return roots
}
```

**关键改动**：
- **删除** `src/config/menuConfig.js`（静态菜单配置）
- **改造** `src/composables/useMenuPermissions.js` → 直接调用 `getUserMenus()`
- **改造** 侧边栏组件 → 渲染 `DynamicMenu[]` 而非静态配置
- **新增** 后端 API：`GET /api/v2/menus/my` — 根据当前用户返回过滤后的菜单树

### 2.6 迁移策略

| 阶段 | 内容 | 风险 |
|------|------|------|
| **阶段 1** | 创建 `menu` BO YAML，实现 `MenuAutoGenerator`，但不删除旧配置 | 低 |
| **阶段 2** | 后端同时支持新旧菜单接口，对比验证自动生成结果 | 低 |
| **阶段 3** | 前端新增 `getUserMenus()` 驱动侧边栏，保留旧 `menuConfig.js` 作为 fallback | 低 |
| **阶段 4** | 验证通过后，删除 `menuConfig.js`，删除 `init_menu_permissions.py` 的硬编码部分 | 中 |

---

## 3. 方案二：权限从 BO Actions 自动同步 {#3-方案二权限从-bo-actions-自动同步}

### 3.1 当前问题

`permissions` 表由 `init_auth.py` 的 `seed_permissions()` 硬编码填充：

```python
# 当前代码 — 仅覆盖 5 个业务 BO，不包括系统 BO
for resource in ['domain', 'sub_domain', 'service_module',
                  'business_object', 'relationship']:
    for action in ['create', 'read', 'update', 'delete', 'export']:
        # INSERT INTO permissions ...
```

新增一个 BO（如 `api_gateway`）时，需要手动修改 `seed_permissions()` 才能产生对应的权限记录。

### 3.2 解决方案：PermissionsSynchronizer

```python
# meta/services/permission_synchronizer.py

from typing import List, Set
from meta.core.models import MetaObject, MetaAction

class PermissionsSynchronizer:
    """
    权限自动同步器
    
    核心逻辑：
    扫描所有已注册的 MetaObject，将其 actions 和 category_config
    中定义的权限编码同步到 permissions 表。
    
    同步策略：只增不删（已在 role_permissions 中引用的权限不删除）
    """
    
    @classmethod
    def sync_all(cls) -> dict:
        """
        全量同步所有已注册 BO 的权限
        
        Returns:
            { created: [...], updated: [...], skipped: [...] }
        """
        from meta.core.models import MetaRegistry
        
        result = {'created': [], 'updated': [], 'skipped': []}
        existing_permissions = cls._load_existing_permissions()
        
        for bo_id, meta_obj in MetaRegistry()._objects.items():
            bo_result = cls.sync_from_bo(meta_obj, existing_permissions)
            for key in result:
                result[key].extend(bo_result[key])
        
        return result
    
    @classmethod
    def sync_from_bo(cls, meta_obj: MetaObject,
                     existing: Optional[dict] = None) -> dict:
        """
        从单个 BO 定义同步权限到 permissions 表
        
        权限编码来源优先级：
        1. category_config 中的 create/update/delete_permission
        2. actions 中的每个 action（格式：{bo_id}:{action_id}）
        3. 系统自动推导的 read/list 权限
        """
        result = {'created': [], 'updated': [], 'skipped': []}
        bo_id = meta_obj.id
        
        if existing is None:
            existing = cls._load_existing_permissions()
        
        # 收集所有应存在的权限编码
        expected_codes = cls._collect_expected_permissions(meta_obj)
        
        for perm_code, perm_def in expected_codes.items():
            if perm_code in existing:
                # 已存在，检查是否需要更新
                existing_rec = existing[perm_code]
                if cls._needs_update(existing_rec, perm_def):
                    cls._update_permission(perm_code, perm_def)
                    result['updated'].append(perm_code)
                else:
                    result['skipped'].append(perm_code)
            else:
                # 不存在，创建
                cls._create_permission(perm_code, perm_def)
                result['created'].append(perm_code)
        
        return result
    
    @classmethod
    def _collect_expected_permissions(cls, meta_obj: MetaObject) -> dict:
        """
        从 BO 的 YAML 定义收集所有应存在的权限
        
        权限生成规则：
        1. 每个 action 生成 {object_type}:{action_id}
        2. 系统自动补充 {object_type}:read 和 {object_type}:list
        3. category_config 中的 create/update/delete_permission 也会被覆盖
        """
        permissions = {}
        bo_id = meta_obj.id
        bo_name = meta_obj.name
        
        # 1. 从 actions 生成
        if meta_obj.actions:
            for action in meta_obj.actions:
                code = f"{bo_id}:{action.id}"
                permissions[code] = {
                    'code': code,
                    'name': f"{bo_name} - {action.name or action.id}",
                    'resource_type': bo_id,
                    'action_code': action.id,
                    'action_type': action.type or 'crud',
                    'description': action.description or '',
                    'source': 'actions'
                }
        
        # 2. 确保基础 CRUD 权限至少存在
        for base_action in ['create', 'read', 'update', 'delete', 'list']:
            code = f"{bo_id}:{base_action}"
            if code not in permissions:
                permissions[code] = {
                    'code': code,
                    'name': f"{bo_name} - {base_action}",
                    'resource_type': bo_id,
                    'action_code': base_action,
                    'action_type': 'crud',
                    'source': 'auto_derived'
                }
        
        # 3. 如果有 business 类型的 action（如 export），一并加入
        if meta_obj.actions:
            for action in meta_obj.actions:
                if action.type == 'business':
                    code = f"{bo_id}:{action.id}"
                    if code not in permissions:
                        permissions[code] = {
                            'code': code,
                            'name': f"{bo_name} - {action.name or action.id}",
                            'resource_type': bo_id,
                            'action_code': action.id,
                            'action_type': 'business',
                            'source': 'actions'
                        }
        
        return permissions
    
    @classmethod
    def _create_permission(cls, code: str, perm_def: dict):
        """在 permissions 表中创建权限记录"""
        _execute_sql("""
            INSERT INTO permissions (code, name, resource_type, action_code,
                                     action_type, description, is_system, source)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, [
            code, perm_def['name'], perm_def['resource_type'],
            perm_def['action_code'], perm_def.get('action_type', 'crud'),
            perm_def.get('description', ''), perm_def.get('source', 'auto')
        ])
    
    @classmethod
    def _update_permission(cls, code: str, perm_def: dict):
        """更新已存在的权限记录"""
        _execute_sql("""
            UPDATE permissions
            SET name = ?, action_type = ?, description = ?, source = ?
            WHERE code = ? AND is_system = 1
        """, [
            perm_def['name'], perm_def.get('action_type', 'crud'),
            perm_def.get('description', ''), perm_def.get('source', 'auto'),
            code
        ])
    
    @classmethod
    def _load_existing_permissions(cls) -> dict:
        """加载当前 permissions 表中的所有记录"""
        rows = _query_sql("SELECT * FROM permissions")
        return {row['code']: dict(row) for row in rows}
    
    @staticmethod
    def _needs_update(existing: dict, expected: dict) -> bool:
        """判断是否需要更新"""
        return (existing.get('name') != expected.get('name') or
                existing.get('description') != expected.get('description'))
```

### 3.3 BO Schema 中补齐 `category_config`

当前业务 BO（`domain`, `sub_domain`, `service_module`, `business_object`, `product`, `version`）没有 `category_config`，需要补齐：

```yaml
# domain.yaml 末尾补充
category_config:
  create_permission: domain:create
  update_permission: domain:update
  delete_permission: domain:delete
  owner_auto_permission: false

# 新增数据权限维度声明
data_permission_dimensions:
  - field: version_id
    type: context_scope
    description: 按版本过滤
```

对所有业务 BO 进行同样的补充：
- `sub_domain.yaml` → `sub_domain:create/update/delete`
- `service_module.yaml` → `service_module:create/update/delete`
- `business_object.yaml` → `business_object:create/update/delete`
- `product.yaml` → `product:create/update/delete`
- `version.yaml` → `version:create/update/delete`
- `relationship.yaml` → `relationship:create/update/delete`

### 3.4 启动时自动同步

```python
# meta/core/bo_framework.py — BOFramework 初始化

class BOFramework:
    def __init__(self):
        # 注册内置拦截器
        ...
        
    def initialize_system(self):
        """
        系统初始化：
        1. 加载所有 YAML schema → MetaObject → MetaRegistry
        2. 扫描所有已注册 BO，同步 permissions 表
        3. 扫描所有已注册 BO，同步 menus 表
        """
        # 1. 加载 YAML
        YAMLLoader.load_all()
        
        # 2. 同步权限
        sync_result = PermissionsSynchronizer.sync_all()
        logger.info(f"权限同步完成: "
                    f"新建 {len(sync_result['created'])} 个, "
                    f"更新 {len(sync_result['updated'])} 个")
        
        # 3. 同步菜单
        menu_result = MenuSynchronizer.sync_all()
        logger.info(f"菜单同步完成: "
                    f"新建 {len(menu_result['created'])} 个, "
                    f"更新 {len(menu_result['updated'])} 个")
```

### 3.5 处理权限废弃问题

BO 的 action 被删除后，对应的权限记录不自动删除（可能在 role_permissions 中已被引用），而是标记为 `is_deprecated`：

```python
class PermissionsSynchronizer:
    
    @classmethod
    def mark_orphaned_permissions(cls):
        """
        标记孤立的权限记录（其对应的 BO 或 action 已不存在）
        不对它们做物理删除，仅标记 is_deprecated=1
        """
        all_codes = set()
        for bo_id, meta_obj in MetaRegistry()._objects.items():
            for code in cls._collect_expected_permissions(meta_obj):
                all_codes.add(code)
        
        _execute_sql("""
            UPDATE permissions
            SET is_deprecated = 1
            WHERE code NOT IN ({})
            AND is_system = 1
            AND source = 'auto'
        """.format(','.join(['?'] * len(all_codes))), list(all_codes))
```

---

## 4. 方案三：数据权限维度声明化 {#4-方案三数据权限维度声明化}

### 4.1 当前状态

数据权限通过 `permission_rules.condition` 条件表达式手动编写，如 `"owner_id = $user.id"`。这种方式的问题：
- 管理员需要知道字段名和 SQL 表达式的写法
- 无法校验条件的正确性（引用的字段是否存在）
- 无法提示哪些维度可选

### 4.2 解决方案：在 YAML 中声明数据权限维度

参考 SAP CAP 的 `where` 条件和 Mendix 的 XPath Constraint，在 BO YAML 中声明数据权限维度：

```yaml
# role.yaml 末尾补充
data_permission_dimensions:
  - field: created_by
    type: owner_scope
    description: 按创建者过滤
    label: 创建者
    default_condition: "created_by = $user.id"

  - field: role_type
    type: field_filter
    description: 按角色类型过滤
    label: 角色类型
    allowed_values:
      source: enum
      enum_field: role_type
```

```yaml
# domain.yaml 末尾补充
data_permission_dimensions:
  - field: owner_id
    type: owner_scope
    description: 按所有者过滤
    label: 所有者
    
  -