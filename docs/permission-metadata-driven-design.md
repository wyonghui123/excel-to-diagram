# 权限体系元数据驱动化 — 细化方案设计

> 日期：2026-05-16  
> 状态：方案设计阶段  
> 前置阅读：[竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)

---

## 目录

1. [问题诊断：当前6大断裂点](#1-问题诊断)
2. [方案1：Menu BO 元数据化 — 菜单成为一等BO](#2-方案1)
3. [方案2：权限从 BO actions 自动同步](#3-方案2)
4. [方案3：BO 字段级数据权限声明化](#4-方案3)
5. [方案4：前端菜单完全由后端驱动](#5-方案4)
6. [方案5：字段级读写权限控制](#6-方案5)
7. [实施路线图](#7-实施路线图)

---

## 1. 问题诊断 {#1-问题诊断}

### 1.1 当前6大断裂点

通过深入阅读所有相关代码，识别出以下断裂点：

| # | 断裂点 | 现状 | 影响 |
|---|--------|------|------|
| 1 | `category_config` 未被消费 | YAML 中定义了权限编码，但无代码将其写入 `permissions` 表 | 权限表需手工维护 |
| 2 | `seed_permissions()` 硬编码 | init_auth.py 只覆盖5个BO，新增BO需手动改脚本 | 扩展困难 |
| 3 | 菜单 required_permissions 硬编码 | init_menu_permissions.py 中手动写JSON | 菜单与BO定义脱节 |
| 4 | 前端三套并行菜单 | menuConfig.js + init_menu_permissions.py + useMenuPermissions.js | 改一处忘两处 |
| 5 | 业务BO无 category_config | domain/sub_domain等YAML完全没有权限配置 | 权限信息分散 |
| 6 | 前端路由未联动权限 | authStore 仅判断 isAdmin，无细粒度路由守卫 | 安全性不足 |

### 1.2 目标架构

```
                  YAML Schema (唯一真相源)
                 /        |         \
                /         |          \
        actions       ui_view_config   category_config
           |              |               |
           v              v               v
    permissions 表    menu 菜单定义    数据权限规则
           |              |               |
           +------+-------+-------+-------+
                  |               |
                  v               v
          role_permissions   role_menu_permissions
                  |               |
                  +-------+-------+
                          |
                          v
                   用户有效权限
```

---

## 2. 方案1：Menu BO 元数据化 {#2-方案1}

### 2.1 核心思路

将 `menu_permissions` 表晋升为完整的 YAML Schema 驱动的 BO，菜单通过 YAML 定义并自动关联 BO。

### 2.2 新增 menu.yaml

创建 `meta/schemas/menu.yaml`：

```yaml
id: menu
name: 菜单
table_name: menus
description: 系统菜单配置，由BO元数据驱动
bo_category: configuration
bo_sub_category: customizing

fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true

  - id: menu_code
    name: 菜单编码
    type: string
    db_column: menu_code
    required: true
    unique: true
    max_length: 200
    semantics:
      business_key: true

  - id: menu_name
    name: 菜单名称
    type: string
    db_column: menu_name
    required: true
    max_length: 200

  - id: menu_path
    name: 路由路径
    type: string
    db_column: menu_path
    max_length: 500

  - id: page_type
    name: 页面类型
    type: string
    db_column: page_type
    required: true
    default: object_list
    description: |
      页面类型决定使用哪个通用页面组件渲染：
      - object_list: 单对象列表页 (MetaListPage)
      - object_detail: 单对象详情页 (DetailPage / ObjectPage)
      - multi_object_hub: 多对象聚合页 (ArchDataManageApp)
      - custom_page: 自定义页面
      - dashboard: 仪表盘

  - id: object_types
    name: 关联业务对象
    type: json
    db_column: object_types
    description: JSON数组，关联的BO ID列表，如 ["domain", "sub_domain"]

  - id: primary_object_type
    name: 主业务对象
    type: string
    db_column: primary_object_type
    max_length: 100
    description: 主BO ID，用于单对象页面

  - id: page_config
    name: 页面配置
    type: json
    db_column: page_config
    description: |
      额外的页面级配置（与BO YAML的ui_view_config合并）：
      {
        "default_filter": {"status": "active"},
        "default_sort": {"field": "created_at", "direction": "desc"},
        "enable_create": true,
        "enable_export": true,
        "enable_batch_delete": false,
        "context_required": ["version_id"]
      }

  - id: parent_menu
    name: 父菜单编码
    type: string
    db_column: parent_menu
    max_length: 200

  - id: icon
    name: 图标
    type: string
    db_column: icon
    max_length: 200

  - id: sort_order
    name: 排序
    type: integer
    db_column: sort_order
    default: 0

  - id: is_active
    name: 是否启用
    type: boolean
    db_column: is_active
    default: true

  - id: auto_generated
    name: 是否自动生成
    type: boolean
    db_column: auto_generated
    default: false
    description: true表示从BO元数据自动推导，false表示手动配置

category_config:
  create_permission: menu:create
  update_permission: menu:update
  delete_permission: menu:delete

ui_view_config:
  list:
    title: 菜单管理
    columns:
      - field: menu_code
        width: 160
      - field: menu_name
        width: 160
      - field: page_type
        width: 120
      - field: primary_object_type
        width: 140
      - field: sort_order
        width: 80
      - field: is_active
        width: 80
```

### 2.3 菜单自动生成引擎

新建 `meta/services/menu_auto_generator.py`：

```python
# -*- coding: utf-8 -*-
"""
菜单自动生成引擎

从已注册的 BO 元数据自动推导菜单定义
"""

from typing import Dict, List, Optional
from meta.core.models import MetaObject, MetaAction, registry, BusinessObjectCategory


class MenuAutoGenerator:
    """菜单自动生成器
    
    根据 BO 的 YAML 定义自动生成菜单的 required_permissions 和 data_permission_hint
    """

    def generate_object_list_menu(self, meta_object: MetaObject) -> Dict:
        """为单个BO生成 object_list 类型菜单"""
        menu_code = f"{meta_object.id}-list"
        
        # 从 actions 自动推导 required_permissions
        required_permissions = self._derive_permissions(meta_object)
        
        # 从 ui_view_config 提取列表配置
        page_config = self._extract_list_config(meta_object)
        
        return {
            'menu_code': menu_code,
            'menu_name': f"{meta_object.name}管理",
            'menu_path': f"/{meta_object.id.replace('_', '-')}",
            'page_type': 'object_list',
            'primary_object_type': meta_object.id,
            'object_types': [meta_object.id],
            'page_config': page_config,
            'required_permissions': required_permissions,
            'data_permission_hint': {
                'resource_types': [meta_object.id],
                'message': f'建议分配{meta_object.name}数据权限'
            },
            'auto_generated': True,
        }

    def generate_multi_object_menu(self, menu_code: str, menu_name: str,
                                    object_types: List[str], menu_path: str,
                                    extra_config: Dict = None) -> Dict:
        """生成多对象聚合菜单"""
        all_permissions = []
        for ot in object_types:
            obj = registry.get(ot)
            if obj:
                all_permissions.extend(self._derive_permissions(obj, read_only=True))
        
        return {
            'menu_code': menu_code,
            'menu_name': menu_name,
            'menu_path': menu_path,
            'page_type': 'multi_object_hub',
            'object_types': object_types,
            'page_config': extra_config or {},
            'required_permissions': all_permissions,
            'data_permission_hint': {
                'resource_types': object_types,
                'message': f'建议分配相关数据权限'
            },
            'auto_generated': True,
        }

    def _derive_permissions(self, meta_object: MetaObject,
                            read_only: bool = False) -> List[str]:
        """从 BO 的 actions 推导权限编码列表
        
        规则：
        1. 遍历 meta_object.actions
        2. 生成格式：{object_type}:{action_suffix}
        3. action_suffix 映射：
           - crud_create -> create
           - crud_read -> read
           - crud_update -> update
           - crud_delete -> delete
           - export -> export
           - import -> import
        4. 如果 read_only=True，只包含 read/export
        """
        perms = []
        action_suffix_map = {
            'crud_create': 'create',
            'crud_read': 'read',
            'crud_update': 'update',
            'crud_delete': 'delete',
            'export': 'export',
            'import': 'import',
        }
        
        for action in meta_object.actions:
            suffix = action_suffix_map.get(action.id)
            if not suffix:
                # 对于自定义action，使用 action.id 作为后缀
                suffix = action.id
            
            if read_only and suffix not in ('read', 'export'):
                continue
            
            perms.append(f"{meta_object.id}:{suffix}")
        
        return perms

    def _extract_list_config(self, meta_object: MetaObject) -> Dict:
        """从 BO 的 ui_view_config.list 提取关键配置"""
        list_config = meta_object.ui_view_config.list
        
        config = {}
        if list_config.title:
            config['page_title'] = list_config.title
        if list_config.description:
            config['page_description'] = list_config.description
        if list_config.pageSize:
            config['page_size'] = list_config.pageSize
        
        return config

    def generate_all(self) -> List[Dict]:
        """为所有已注册的BO生成菜单"""
        menus = []
        for obj_id, meta_obj in registry.get_all().items():
            # 跳过系统内部BO（以_开头的模板等）
            if obj_id.startswith('_'):
                continue
            
            # 跳过纯关联表
            if obj_id in ('user_role', 'role_permission', 'user_group_member',
                          'group_data_permission', 'role_data_permissions'):
                continue
            
            # 为每个BO生成 object_list 菜单
            if meta_obj.ui_view_config.list.columns:
                menu = self.generate_object_list_menu(meta_obj)
                menus.append(menu)
        
        return menus


# 全局实例
menu_auto_generator = MenuAutoGenerator()
```

### 2.4 菜单与BO的关联机制

核心原理：`menu_permissions.required_permissions` 不再手动编写，而是通过 `MenuAutoGenerator` 从 `MetaObject.actions` 自动推导。

```python
# 推导链路
BO YAML actions:
  - id: crud_create    →  permission code: "domain:create"
  - id: crud_read      →  permission code: "domain:read"
  - id: crud_update    →  permission code: "domain:update"
  - id: crud_delete    →  permission code: "domain:delete"
  - id: export         →  permission code: "domain:export"
         ↓
Menu.required_permissions: ["domain:create", "domain:read", "domain:update", "domain:delete", "domain:export"]
```

---

## 3. 方案2：权限从 BO actions 自动同步 {#3-方案2}

### 3.1 核心思路

将 `init_auth.py` 中的 `seed_permissions()` 替换为基于 `MetaRegistry` 的自动扫描机制。

### 3.2 新建权限同步服务

新建 `meta/services/permission_sync_service.py`：

```python
# -*- coding: utf-8 -*-
"""
权限同步服务

系统启动时或YAML变更时，自动从 MetaRegistry 同步 permissions 表
"""

import json
import logging
from typing import List, Dict, Set

from meta.core.models import MetaObject, registry

logger = logging.getLogger(__name__)


class PermissionSyncService:
    """权限同步服务
    
    职责：
    1. 扫描所有已注册的 MetaObject
    2. 从 actions 和 category_config 提取权限编码
    3. 与 permissions 表对比差异
    4. 自动创建缺失的权限记录
    """

    def __init__(self, data_source):
        self._ds = data_source

    def sync_all(self) -> Dict:
        """全量同步所有BO的权限到 permissions 表
        
        Returns:
            {'created': [...], 'existing': [...], 'orphaned': [...]}
        """
        expected_perms = self._collect_all_permissions()
        existing_perms = self._load_existing_permissions()
        
        to_create = expected_perms - existing_perms
        orphaned = existing_perms - expected_perms
        
        created = []
        for perm_code in to_create:
            code, resource_type, action = self._parse_permission_code(perm_code)
            name = self._generate_permission_name(resource_type, action)
            self._ds.execute(
                "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
                "VALUES (?, ?, ?, ?)",
                [perm_code, name, resource_type, action]
            )
            created.append(perm_code)
            logger.info(f"[PermissionSync] Created permission: {perm_code}")
        
        return {
            'created': created,
            'existing': list(existing_perms & expected_perms),
            'orphaned': list(orphaned),
        }

    def sync_for_object(self, object_id: str) -> List[str]:
        """为单个BO同步权限"""
        meta_obj = registry.get(object_id)
        if not meta_obj:
            return []
        
        perms = self._derive_permissions_from_object(meta_obj)
        created = []
        for perm_code in perms:
            code, resource_type, action = self._parse_permission_code(perm_code)
            name = self._generate_permission_name(resource_type, action)
            self._ds.execute(
                "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
                "VALUES (?, ?, ?, ?)",
                [perm_code, name, resource_type, action]
            )
            created.append(perm_code)
        return created

    def _collect_all_permissions(self) -> Set[str]:
        """收集所有BO的权限编码"""
        all_perms = set()
        all_perms.add('*')  # 超级权限
        
        for obj_id, meta_obj in registry.get_all().items():
            if obj_id.startswith('_'):
                continue
            perms = self._derive_permissions_from_object(meta_obj)
            all_perms.update(perms)
        
        return all_perms

    def _derive_permissions_from_object(self, meta_obj: MetaObject) -> List[str]:
        """从 MetaObject 推导权限编码"""
        perms = []
        
        # 方式1：从 category_config 推导
        if meta_obj.category_config:
            for key in ['create_permission', 'update_permission', 'delete_permission']:
                val = getattr(meta_obj.category_config, key, None)
                if val:
                    perms.append(val)
        
        # 方式2：从 actions 推导
        action_suffix_map = {
            'crud_create': 'create',
            'crud_read': 'read',
            'crud_update': 'update',
            'crud_delete': 'delete',
        }
        
        for action in meta_obj.actions:
            suffix = action_suffix_map.get(action.id)
            if suffix:
                perms.append(f"{meta_obj.id}:{suffix}")
            else:
                # 业务action：使用 action_type 前缀
                if action.action_type.value in ('business', 'batch', 'custom'):
                    perms.append(f"{meta_obj.id}:{action.id}")
        
        return perms

    def _load_existing_permissions(self) -> Set[str]:
        """从数据库加载已有权限编码"""
        cursor = self._ds.execute("SELECT code FROM permissions")
        return {row[0] for row in cursor.fetchall()}

    def _parse_permission_code(self, code: str) -> tuple:
        """解析权限编码: 'domain:create' -> ('domain:create', 'domain', 'create')"""
        parts = code.split(':')
        resource_type = parts[0] if len(parts) > 0 else code
        action = parts[1] if len(parts) > 1 else 'all'
        return code, resource_type, action

    def _generate_permission_name(self, resource_type: str, action: str) -> str:
        """生成权限名称"""
        resource_names = {
            'domain': '领域', 'sub_domain': '子领域',
            'service_module': '服务模块', 'business_object': '业务对象',
            'relationship': '关系', 'product': '产品', 'version': '版本',
            'user': '用户', 'role': '角色', 'permission': '权限',
            'menu': '菜单', 'user_group': '用户组',
            'annotation': '备注', 'audit_log': '审计日志',
            'enum_type': '枚举类型', 'enum_value': '枚举值',
            'management_dimension': '管理维度',
        }
        action_names = {
            'create': '创建', 'read': '查看', 'update': '更新',
            'delete': '删除', 'export': '导出', 'import': '导入',
        }
        rname = resource_names.get(resource_type, resource_type)
        aname = action_names.get(action, action)
        return f"{rname}{aname}"


permission_sync_service = None


def get_permission_sync_service(data_source=None):
    global permission_sync_service
    if permission_sync_service is None and data_source:
        permission_sync_service = PermissionSyncService(data_source)
    return permission_sync_service
```

### 3.3 集成到系统启动流程

修改 `meta/server.py`，在元数据加载完成后自动同步权限：

```python
# 在 server.py 中 meta reload 或首次启动后调用
from meta.services.permission_sync_service import get_permission_sync_service

def on_meta_loaded():
    """元数据加载完成后的回调"""
    ds = get_data_source('sqlite', database=db_path)
    sync_service = get_permission_sync_service(ds)
    result = sync_service.sync_all()
    if result['created']:
        logger.info(f"Synced {len(result['created'])} new permissions")
    if result['orphaned']:
        logger.warning(f"Found {len(result['orphaned'])} orphaned permissions")
```

### 3.4 改造 init_auth.py

`seed_permissions()` 函数简化为：

```python
def seed_permissions(conn):
    """权限表初始化 - 委托给 PermissionSyncService"""
    from meta.services.permission_sync_service import PermissionSyncService
    service = PermissionSyncService(conn)
    result = service.sync_all()
    print(f"Synced permissions: created={len(result['created'])}, "
          f"existing={len(result['existing'])}, orphaned={len(result['orphaned'])}")
```

---

## 4. 方案3：BO 字段级数据权限声明化 {#4-方案3}

### 4.1 核心思路

参考 SAP CAP `@restrict` + Mendix Access Rules，在 BO YAML 中直接声明数据权限维度。

### 4.2 YAML 新增 data_permission_dimensions

在 `models.py` 和相关 YAML 中增加：

```yaml
# 在 domain.yaml 中增加
data_permission_dimensions:
  - field: owner_id
    type: owner_scope           # 所有者范围
    description: 按创建者过滤数据
    
  - field: version_id
    type: context_scope         # 上下文范围
    description: 按版本上下文过滤
    
  - field: status
    type: field_filter          # 字段值过滤
    description: 按状态过滤
    allowed_filters:
      - active
      - inactive
      - archived
```

### 4.3 对应的 Python 模型扩展

在 `models.py` 中增加：

```python
class DataPermissionDimensionType(Enum):
    OWNER_SCOPE = "owner_scope"
    CONTEXT_SCOPE = "context_scope"
    FIELD_FILTER = "field_filter"
    ORGANIZATION_SCOPE = "organization_scope"


@dataclass
class DataPermissionDimension:
    field: str
    type: DataPermissionDimensionType = DataPermissionDimensionType.FIELD_FILTER
    description: str = ""
    allowed_filters: List[str] = field(default_factory=list)


# 在 MetaObject 中增加字段
@dataclass
class MetaObject:
    # ... 现有字段 ...
    data_permission_dimensions: List[DataPermissionDimension] = field(default_factory=list)
```

### 4.4 前端 ImpactPreview 自动关联

现有的 `RolePermissionCenter.vue` 的 ImpactPreview 功能可以通过读取 BO 的 `data_permission_dimensions` 自动展示哪些字段会受数据权限影响：

```
RolePermissionCenter → GET /api/v2/bo/{objectType}/permission-dimensions
                     → 返回 data_permission_dimensions
                     → ImpactPreview 自动展示影响的字段和范围
```

---

## 5. 方案4：前端菜单完全由后端驱动 {#5-方案4}

### 5.1 核心思路

消除前端三套并行的菜单配置，让 `menuConfig.js` 和 `useMenuPermissions.js` 都从后端 API 获取。

### 5.2 统一菜单API

新增 `GET /api/v1/menu/visible` 端点：

```python
@menu_bp.route('/visible', methods=['GET'])
@login_required
def get_visible_menus():
    """获取当前用户可见的菜单（含层级结构）
    
    返回格式：
    {
        "menus": [
            {
                "menu_code": "domain-list",
                "menu_name": "领域管理",
                "menu_path": "/domain",
                "icon": "domain",
                "page_type": "object_list",
                "primary_object_type": "domain",
                "sort_order": 1,
                "children": []
            }
        ]
    }
    """
    user = get_current_user()
    # 1. 获取用户所有角色
    # 2. 获取角色关联的菜单
    # 3. 检查菜单的 required_permissions 是否满足
    # 4. 构建层级结构（parent_menu 关系）
    # 5. 返回
```

### 5.3 前端改造

```javascript
// menuConfig.js - 改为从API动态加载
let _menuCache = null

export async function loadMenuConfig() {
  if (_menuCache) return _menuCache
  
  const resp = await fetch('/api/v1/menu/visible')
  const data = await resp.json()
  _menuCache = buildMenuTree(data.menus)
  return _menuCache
}

function buildMenuTree(flatMenus) {
  const map = {}
  const tree = []
  
  flatMenus.forEach(m => { map[m.menu_code] = { ...m, children: [] } })
  flatMenus.forEach(m => {
    if (m.parent_menu && map[m.parent_menu]) {
      map[m.parent_menu].children.push(map[m.menu_code])
    } else {
      tree.push(map[m.menu_code])
    }
  })
  
  return tree.sort((a, b) => a.sort_order - b.sort_order)
}
```

### 5.4 路由守卫

```javascript
// router/index.js - 基于权限的路由守卫
router.beforeEach(async (to, from, next) => {
  // 公开页面直接放行
  if (to.meta.public) return next()

  const authStore = useAuthStore()
  if (!authStore.isLoggedIn) return next('/login')

  // 检查用户是否有该菜单的访问权限
  const menus = await loadMenuConfig()
  const hasAccess = checkMenuAccess(menus, to.path)
  
  if (!hasAccess) return next('/403')
  next()
})
```

---

## 6. 方案5：字段级读写权限控制 {#6-方案5}

### 6.1 核心思路

在当前 `permission_rules` + 条件规则基础上，增加字段级的 `visible` / `editable` 控制。

### 6.2 PermissionAnnotation 的激活

当前 `models.py` 中已有 `PermissionAnnotation` 但仅作为预留接口：

```python
@dataclass
class PermissionAnnotation:
    readable: bool = True
    writable: bool = True
    roles: List[str] = field(default_factory=list)
```

方案是将其激活：

```yaml
# 在 BO YAML 的字段级别使用
fields:
  - id: salary
    name: 薪资
    type: float
    permission:
      readable: true
      writable: false        # 永远不可编辑
      roles: ['admin', 'hr_manager']  # 仅特定角色可见
```

### 6.3 BOFramework 中的实现

在 `bo_framework.py` 的 `get_ui_config()` 中，字段的 `editable` 和 `visible` 需要叠加权限判断：

```python
def get_ui_config(self, object_type: str, mode: str = 'detail', record: Dict = None) -> Dict:
    """获取UI配置，叠加字段级权限"""
    meta_obj = registry.get(object_type)
    config = super().get_ui_config(object_type, mode, record)
    
    user_roles = self._get_current_user_roles()
    
    for field_config in config.get('fields', []):
        field_id = field_config['id']
        field_meta = meta_obj.get_field(field_id)
        
        if field_meta and field_meta.permission:
            perm = field_meta.permission
            
            # 角色检查
            if perm.roles:
                has_role = any(r in user_roles for r in perm.roles)
                if not has_role:
                    field_config['visible'] = False
                    continue
            
            # 读写控制
            if mode == 'edit' and not perm.writable:
                field_config['editable'] = False
            
            if not perm.readable:
                field_config['visible'] = False
    
    return config
```

### 6.4 与数据权限的协同

字段级权限与条件规则的协同：

```
请求 → 条件规则过滤（行级） → 字段权限过滤（列级） → 返回数据
         permission_rules         PermissionAnnotation
```

---

## 7. 实施路线图 {#7-实施路线图}

### Phase 1：基础打通（Week 1-2）

| 任务 | 产出 | 影响范围 |
|------|------|---------|
| 1.1 创建 `menu.yaml` | Menu 成为一等 BO | 新增 schema + 建表 |
| 1.2 创建 `permission_sync_service.py` | 权限自动从 actions 同步 | 替代 init_auth.py 硬编码 |
| 1.3 创建 `menu_auto_generator.py` | 菜单自动生成引擎 | 替代 init_menu_permissions.py |
| 1.4 所有业务 BO YAML 增加 `category_config` | domain/sub_domain 等可自动推导权限 | 修改 6+ YAML 文件 |

### Phase 2：前端统一（Week 3-4）

| 任务 | 产出 | 影响范围 |
|------|------|---------|
| 2.1 实现 `GET /api/v1/menu/visible` | 统一菜单 API | 新增后端端点 |
| 2.2 改造 `menuConfig.js` | 从静态配置改为 API 加载 | 修改 layout 组件 |
| 2.3 添加路由守卫 | 基于权限的访问控制 | 修改 router/index.js |
| 2.4 淘汰旧脚本 | 标记 init_auth.py / init_menu_permissions.py 为 deprecated | 文档更新 |

### Phase 3：增强能力（Week 5-6）

| 任务 | 产出 | 影响范围 |
|------|------|---------|
| 3.1 `data_permission_dimensions` | YAML 声明数据权限维度 | models.py + YAML |
| 3.2 ImpactPreview 自动关联 | 根据 dimensions 自动展示影响 | RolePermissionCenter.vue |
| 3.3 字段级 PermissionAnnotation 激活 | BOFramework 叠加字段权限 | bo_framework.py |

### 向后兼容策略

所有改造遵循以下原则：
- `init_auth.py` 保留但标记 deprecated，新增的同步逻辑作为增强
- `menu_permissions` 表现在字段不变，新增字段通过 ALTER TABLE 扩展
- 前端渐进改造：先加 API 加载路径，稳定后再移除静态配置
- 所有现有角色的权限关系不受影响

---

## 参考

- [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)
- [meta/schemas/_template.yaml](../meta/schemas/_template.yaml) — BO Schema 模板
- [meta/scripts/init_auth.py](../meta/scripts/init_auth.py) — 当前权限初始化脚本
- [meta/scripts/init_menu_permissions.py](../meta/scripts/init_menu_permissions.py) — 当前菜单初始化脚本
- [meta/api/role_menu_api.py](../meta/api/role_menu_api.py) — 当前角色菜单API
