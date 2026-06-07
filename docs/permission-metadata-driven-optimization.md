# 权限体系元数据驱动优化 — 细化方案设计

> 文档日期：2026-05-16  
> 前置文档：[竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)  
> 设计目标：将权限体系完全纳入元数据驱动闭环，实现 YAML 为唯一事实源

---

## 目录

1. [当前状态诊断](#1-当前状态诊断)
2. [方案一：Menu BO 元数据化](#2-方案一menu-bo-元数据化)
3. [方案二：权限从 BO actions 自动同步](#3-方案二权限从-bo-actions-自动同步)
4. [方案三：BO 字段级数据权限声明化](#4-方案三bo-字段级数据权限声明化)
5. [方案四：前端菜单完全权限驱动](#5-方案四前端菜单完全权限驱动)
6. [方案五：BEC访问控制统一化](#6-方案五bec访问控制统一化)
7. [实施路线图](#7-实施路线图)

---

## 1. 当前状态诊断

### 1.1 核心断裂点

经过对 `init_auth.py`、`init_menu_permissions.py`、`role_menu_api.py`、`bo_framework.py`、`models.py`、`yaml_loader.py` 的完整阅读，当前存在以下断裂：

```
┌──────────────────────────────────────────────────────────────────┐
│                        【三套独立定义】                              │
│                                                                   │
│  1. YAML Schema (category_config + actions)                       │
│     ├── role.yaml: category_config.create_permission="role:create"│
│     ├── domain.yaml: actions=[domain_create, ...]                 │
│     └── ⚠️ 定义了权限语义，但未被消费                              │
│                                                                   │
│  2. init_auth.py (seed_permissions)                              │
│     ├── 只覆盖 5 个 BO（domain/sub_domain/...）                    │
│     ├── 完全硬编码资源列表                                         │
│     └── ⚠️ role/user/permission 等系统BO没有生成                   │
│                                                                   │
│  3. init_menu_permissions.py                                     │
│     ├── 硬编码每个菜单的 required_permissions                      │
│     ├── 与 YAML actions 无任何关联                                 │
│     └── ⚠️ 新增BO需要手动改两个脚本                               │
│                                                                   │
│  4. role_menu_api.py (get_role_unified_permissions)              │
│     ├── PERMISSION_LABELS 硬编码了全部权限标签                     │
│     ├── MENU_DISPLAY_NAMES 硬编码了菜单显示名                     │
│     └── ⚠️ YAML修改需要同步改API代码                              │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 新增 BO 需要改多少地方

假设新增 `api_gateway` BO，当前需要修改：

| 文件 | 修改内容 | 行数 |
|------|---------|------|
| `meta/schemas/api_gateway.yaml` | 定义 BO 模型 | ~100行 |
| `meta/scripts/init_auth.py` | 在 resources 列表添加 `'api_gateway'` | 1行 |
| `meta/scripts/init_auth.py` | 在 _resource_name 添加名称映射 | 1行 |
| `meta/scripts/init_menu_permissions.py` | 如需菜单则需添加整个菜单配置块 | ~20行 |
| `meta/api/role_menu_api.py` | 在 PERMISSION_LABELS 添加5条权限标签 | 5行 |
| `src/config/menuConfig.js` | 添加静态菜单项 | ~10行 |
| **合计** | **6个文件** | **~130行** |

**理想状态**：只改 `api_gateway.yaml` 一个文件，其余全部自动生成。

---

## 2. 方案一：Menu BO 元数据化

### 2.1 目标

将菜单从硬编码脚本提升为 YAML 驱动的 BO，使菜单定义与 BO 定义在同一元数据体系内闭环。

### 2.2 设计原理

参考 SAP Fiori Catalogs + Salesforce App Menu + ServiceNow Application Menu 的三层模型：

```
Application (应用)
  └── MenuGroup (菜单分组)
        └── MenuItem (菜单项)
              ├── page_type: "object_list" | "object_detail" | "multi_object" | "custom"
              ├── object_types: ["domain", "sub_domain"]    ← BO 列表
              ├── page_config: { filters: {...}, default_sort: {...} }
              ├── required_permissions: [...]               ← 从 BO actions 自动推导
              └── data_permission_hint: { resource_types: [...] }
```

### 2.3 新增 YAML Schema：`menu.yaml`

```yaml
id: menu
name: 菜单
table_name: menus
description: 系统菜单配置，元数据驱动

fields:
  - id: menu_code
    name: 菜单编码
    type: string
    required: true
    unique: true
    semantics:
      business_key: true
    
  - id: menu_name
    name: 菜单名称
    type: string
    required: true
    
  - id: menu_path
    name: 路由路径
    type: string
    description: 前端路由路径，如 /data、/system/domains
    
  - id: page_type
    name: 页面类型
    type: string
    required: true
    enum_values:
      - value: object_list
        label: 单对象列表
      - value: object_detail
        label: 对象详情
      - value: multi_object
        label: 多对象聚合
      - value: custom
        label: 自定义页面

  - id: object_types
    name: 关联业务对象
    type: json
    description: 该菜单关联的 BO ID 列表，如 ["domain","sub_domain"]
    
  - id: page_config
    name: 页面配置
    type: json
    description: |
      从关联 BO 的 ui_view_config 合并而来的页面配置，
      可覆盖默认行为（如默认筛选条件、排序等）
    
  - id: required_permissions
    name: 需要的功能权限
    type: json
    description: |
      JSON 数组，如 ["domain:read","domain:create"]。
      空值时自动从 object_types 关联的 BO actions 推导。
    
  - id: required_any_permission
    name: 满足任一即可
    type: boolean
    default: false
    
  - id: parent_menu
    name: 父菜单
    type: string
    description: 父菜单编码，用于层级结构
    
  - id: icon
    name: 图标
    type: string
    
  - id: sort_order
    name: 排序
    type: integer
    default: 100
    
  - id: is_active
    name: 是否启用
    type: boolean
    default: true
    
  - id: component_path
    name: 前端组件路径
    type: string
    description: 自定义页面对应的 Vue 组件路径

  - id: data_permission_hint
    name: 数据权限提示
    type: json
    description: 需要为该菜单配置的数据权限信息

  - id: visible
    name: 菜单可见性
    type: boolean
    default: true
    description: false 表示隐藏菜单（仅路由可访问）

relations:
  - id: menu_parent
    name: 父菜单关系
    relation_type: parent_child
    target_object: menu
    source_field: parent_menu
    target_field: menu_code

actions:
  - id: menu_create
    name: 创建菜单
    type: crud
    method: POST
    path: /api/v1/menus
  - id: menu_read
    name: 查询菜单
    type: crud
    method: GET
    path: /api/v1/menus
  - id: menu_update
    name: 更新菜单
    type: crud
    method: PUT
    path: /api/v1/menus/{id}
  - id: menu_delete
    name: 删除菜单
    type: crud
    method: DELETE
    path: /api/v1/menus/{id}

category_config:
  create_permission: menu:create
  update_permission: menu:update
  delete_permission: menu:delete
```

### 2.4 菜单自动生成引擎

在 `bo_framework.py` 或新的 `menu_engine.py` 中实现：

```python
# meta/core/menu_engine.py  (新增文件)

from meta.core.models import MetaRegistry, MetaObject, BusinessObjectCategory

class MenuAutoGenerator:
    """菜单自动生成引擎
    
    当 BO Schema 注册后，自动为该 BO 生成标准菜单项。
    借鉴 SAP Fiori Tile Catalog 自动生成机制。
    """
    
    # BO分类对应的默认页面类型
    CATEGORY_PAGE_TYPE = {
        BusinessObjectCategory.TRANSACTIONAL: "object_list",
        BusinessObjectCategory.MASTER_DATA: "object_list",
        BusinessObjectCategory.CONFIGURATION: "object_list",
        BusinessObjectCategory.ANALYTICAL: "object_list",
    }
    
    # BO分类对应的默认菜单位置
    CATEGORY_PARENT_MENU = {
        BusinessObjectCategory.TRANSACTIONAL: "business-data",
        BusinessObjectCategory.MASTER_DATA: "business-data",
        BusinessObjectCategory.CONFIGURATION: "system",
        BusinessObjectCategory.ANALYTICAL: "analytics",
    }
    
    @classmethod
    def generate_menu_for_bo(cls, meta_object: MetaObject) -> dict:
        """为单个 BO 生成菜单定义
        
        返回 menu 字典，对应 menu.yaml 的字段结构。
        核心逻辑：从 BO 的 ui_view_config + actions 自动推导菜单配置。
        """
        bo_id = meta_object.id
        bo_name = meta_object.name
        
        # 从 actions 自动推导 required_permissions
        required_perms = [
            f"{bo_id}:{action.id.replace(f'{bo_id}_', '')}"
            for action in meta_object.actions
        ]
        
        # 从 ui_view_config 自动推导页面配置
        page_config = {
            "list_columns": [
                col.key for col in (meta_object.ui_view_config.list.columns or [])
            ] if meta_object.ui_view_config else [],
            "detail_facets": [
                facet.title for facet in (meta_object.ui_view_config.detail.facets or [])
            ] if meta_object.ui_view_config else [],
        }
        
        menu_code = f"{bo_id}-management"
        parent_menu = cls.CATEGORY_PARENT_MENU.get(
            meta_object.bo_category, "business-data"
        )
        
        return {
            "menu_code": menu_code,
            "menu_name": f"{bo_name}管理",
            "menu_path": f"/{bo_id}s" if not bo_id.endswith('s') else f"/{bo_id}",
            "page_type": cls.CATEGORY_PAGE_TYPE.get(
                meta_object.bo_category, "object_list"
            ),
            "object_types": [bo_id],
            "page_config": page_config,
            "required_permissions": required_perms,
            "parent_menu": parent_menu,
            "icon": cls._infer_icon(bo_id),
            "sort_order": 100,
            "is_active": True,
        }
    
    @classmethod
    def _infer_icon(cls, bo_id: str) -> str:
        """根据 BO ID 推断合适的图标"""
        icon_map = {
            "domain": "folder",
            "product": "goods",
            "user": "user",
            "role": "shield",
            "permission": "key",
            "menu": "menu",
            "audit_log": "file-text",
            "relationship": "connection",
            "version": "layers",
        }
        return icon_map.get(bo_id, "document")
    
    @classmethod
    def generate_all_menus(cls) -> list:
        """为所有已注册的 BO 生成菜单"""
        registry = MetaRegistry()
        menus = []
        for obj in registry.get_all().values():
            # 跳过系统表（如 menu_permissions 关联表）
            if obj.id.startswith("role_") or obj.id.startswith("user_"):
                continue
            menu = cls.generate_menu_for_bo(obj)
            menus.append(menu)
        return menus
    
    @classmethod
    def sync_menus_to_db(cls, menus: list):
        """将生成的菜单同步到 menus 表
        
        策略：UPSERT 模式（存在则更新，不存在则插入）
        保留手动菜单（page_type=custom 的不覆盖）
        """
        from meta.core.datasource import get_data_source
        ds = get_data_source("sqlite", database="meta/architecture.db")
        
        for menu in menus:
            ds.execute("""
                INSERT INTO menus (menu_code, menu_name, menu_path, page_type,
                    object_types, page_config, required_permissions,
                    parent_menu, icon, sort_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(menu_code) DO UPDATE SET
                    menu_name = excluded.menu_name,
                    page_config = excluded.page_config,
                    required_permissions = excluded.required_permissions,
                    updated_at = CURRENT_TIMESTAMP
            """, [
                menu['menu_code'], menu['menu_name'], menu['menu_path'],
                menu['page_type'], json.dumps(menu['object_types']),
                json.dumps(menu['page_config']),
                json.dumps(menu['required_permissions']),
                menu['parent_menu'], menu['icon'], menu['sort_order'],
                menu['is_active']
            ])
```

### 2.5 集成到 YAML Loader 注册流程

在 `yaml_loader.py` 的 `register_from_directory()` 完成后调用：

```python
# meta/core/yaml_loader.py 中增加

def register_from_directory(schema_dir, target=None):
    # ... 现有注册逻辑 ...
    
    # 【新增】自动生成菜单
    try:
        from meta.core.menu_engine import MenuAutoGenerator
        menus = MenuAutoGenerator.generate_all_menus()
        MenuAutoGenerator.sync_menus_to_db(menus)
        logger.info(f"Auto-generated {len(menus)} menus from BO schemas")
    except Exception as e:
        logger.warning(f"Menu auto-generation skipped: {e}")
    
    return count
```

### 2.6 对 role_menu_api.py 的改造

将硬编码的 `PERMISSION_LABELS` 替换为从 `MetaRegistry` 动态生成：

```python
# role_menu_api.py 中替换 PERMISSION_LABELS

def _build_permission_labels():
    """从 MetaRegistry 动态构建权限标签映射
    
    替代原有的硬编码 PERMISSION_LABELS 字典。
    """
    registry = MetaRegistry()
    labels = {}
    
    for obj in registry.get_all().values():
        bo_name = obj.name
        for action in obj.actions:
            # action.id 格式: domain_create → permission code: domain:create
            action_name = action.name or action.id
            # 去掉 bo_id_ 前缀得到纯动作名
            pure_action = action.id.replace(f"{obj.id}_", "")
            perm_code = f"{obj.id}:{pure_action}"
            labels[perm_code] = f"{bo_name}{action_name}"
    
    labels['*'] = '超级权限'
    return labels

PERMISSION_LABELS = _build_permission_labels()
```

### 2.7 对 MenuPermissionMatrix 前端的改造

前端 `MenuPermissionMatrix.vue` 中，菜单列表从 `/api/v1/menus` 获取（通过 BO 框架），而不是从 `menu_permissions` 表查原始 SQL：

```
原流程: GET /api/v1/roles/{roleId}/unified-permissions
        → role_menu_api.py 查 menu_permissions 表（原始SQL）
        
新流程: GET /api/v1/menus (?filter[is_active]=1&sort=sort_order)
        → BO Framework  → menus 表
        + GET /api/v1/role-menus?role_id={roleId}
        → 返回角色已分配的菜单列表
```

---

## 3. 方案二：权限从 BO actions 自动同步

### 3.1 目标

`permissions` 表的内容完全由 `MetaRegistry` 中的 BO actions 定义自动生成，不再需要 `init_auth.py` 中的 `seed_permissions()` 硬编码。

### 3.2 设计原理

```
BO Schema (YAML)                    permissions 表
─────────────────                   ──────────────
domain.yaml:
  actions:                           code               | name      | resource_type | action
    - id: domain_create    ───────→  "domain:create"    | 领域创建   | domain        | create
      name: 创建领域
    - id: domain_read      ───────→  "domain:read"      | 领域查看   | domain        | read
      name: 查询领域
    - id: domain_update    ───────→  "domain:update"    | 领域更新   | domain        | update
      name: 更新领域
    - id: domain_delete    ───────→  "domain:delete"    | 领域删除   | domain        | delete
      name: 删除领域

映射规则:
  permission.code = "{bo_id}:{action_method}"
  permission.name = "{bo_name}{action_name}"
  permission.resource_type = bo_id
  permission.action = action_method
```

### 3.3 实现：新增 `permission_sync_engine.py`

```python
# meta/core/permission_sync_engine.py  (新增文件)

import json
from meta.core.models import MetaRegistry, MetaAction, ActionType

class PermissionSyncEngine:
    """权限同步引擎
    
    负责将 MetaRegistry 中所有 BO 的 actions 定义
    同步到 permissions 表，确保 YAML 是 permissions 表的事实源。
    """
    
    @classmethod
    def extract_permissions_from_registry(cls) -> list:
        """从 MetaRegistry 提取所有权限定义
        
        Returns:
            list[dict]: 每个 dict 包含 code, name, resource_type, action, description
        """
        registry = MetaRegistry()
        permissions = []
        seen_codes = set()
        
        for obj in registry.get_all().values():
            bo_id = obj.id
            bo_name = obj.name
            
            for action in obj.actions:
                # 从 action.id 推导权限编码
                # domain_create → domain:create
                # crud_create  → ?  (回退到 action.method)
                pure_action = cls._extract_action_code(action, bo_id)
                perm_code = f"{bo_id}:{pure_action}"
                
                if perm_code in seen_codes:
                    continue
                seen_codes.add(perm_code)
                
                permissions.append({
                    "code": perm_code,
                    "name": f"{bo_name}{action.name}",
                    "resource_type": bo_id,
                    "action": pure_action,
                    "description": action.description or f"{bo_name} - {action.name}",
                })
            
            # 同时从 category_config 补充权限定义
            if obj.category_config:
                cfg = obj.category_config
                for action_key, action_label in [
                    ("create_permission", "创建"),
                    ("update_permission", "更新"),
                    ("delete_permission", "删除"),
                ]:
                    perm_code = getattr(cfg, action_key, None)
                    if perm_code and perm_code not in seen_codes:
                        seen_codes.add(perm_code)
                        # 解析 resource_type:action
                        if ":" in perm_code:
                            rt, act = perm_code.split(":", 1)
                        else:
                            rt, act = bo_id, action_key.replace("_permission", "")
                        permissions.append({
                            "code": perm_code,
                            "name": f"{bo_name}{action_label}",
                            "resource_type": rt,
                            "action": act,
                            "description": f"自动生成的{bo_name}{action_label}权限",
                        })
        
        # 添加超级权限
        if "*" not in seen_codes:
            permissions.append({
                "code": "*",
                "name": "超级权限",
                "resource_type": "all",
                "action": "all",
                "description": "拥有所有权限",
            })
        
        return permissions
    
    @classmethod
    def _extract_action_code(cls, action: MetaAction, bo_id: str) -> str:
        """从 action.id 提取纯动作编码
        
        例如: domain_create → create
              crud_create → create
              set_current → set_current
        """
        action_id = action.id
        
        # 如果 action_id 以 bo_id_ 开头，去掉前缀
        prefix = f"{bo_id}_"
        if action_id.startswith(prefix):
            return action_id[len(prefix):]
        
        # 如果 action_id 以 crud_ 开头
        if action_id.startswith("crud_"):
            return action_id[5:]
        
        # 如果 action_id 是 batch_ 开头
        if action_id.startswith("batch_"):
            return action_id[6:]
        
        # 否则使用 method 推导
        method_map = {
            "POST": "create",
            "GET": "read",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }
        return method_map.get(action.method, action_id)
    
    @classmethod
    def sync_to_database(cls):
        """将权限同步到数据库
        
        采用 UPSERT 策略：新增 + 更新，不删除已有权限
        （避免误删管理员手工创建的权限）
        """
        from meta.core.datasource import get_data_source
        import os
        
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        ds = get_data_source("sqlite", database=db_path)
        
        permissions = cls.extract_permissions_from_registry()
        
        inserted = 0
        updated = 0
        
        for perm in permissions:
            cursor = ds.execute(
                "SELECT id FROM permissions WHERE code = ?",
                [perm['code']]
            )
            existing = cursor.fetchone()
            
            if existing:
                ds.execute("""
                    UPDATE permissions 
                    SET name = ?, resource_type = ?, action = ?, description = ?
                    WHERE code = ?
                """, [perm['name'], perm['resource_type'], perm['action'],
                       perm['description'], perm['code']])
                updated += 1
            else:
                ds.execute("""
                    INSERT INTO permissions (code, name, resource_type, action, description)
                    VALUES (?, ?, ?, ?, ?)
                """, [perm['code'], perm['name'], perm['resource_type'],
                       perm['action'], perm['description']])
                inserted += 1
        
        logger.info(f"Permission sync: {inserted} inserted, {updated} updated")
        return inserted, updated
    
    @classmethod
    def get_diff_report(cls) -> dict:
        """获取权限差异报告（dry-run 模式）
        
        Returns:
            dict: {
                "to_add": [...],      # 需要新增的权限
                "to_update": [...],   # 需要更新的权限
                "orphaned": [...],    # 数据库中多余（YAML 中已删除的 BO）的权限
            }
        """
        registry = MetaRegistry()
        all_bo_ids = set(registry.list_objects())
        
        from meta.core.datasource import get_data_source
        import os
        
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        ds = get_data_source("sqlite", database=db_path)
        
        cursor = ds.execute("SELECT code, resource_type FROM permissions")
        db_perms = {row[0]: row[1] for row in cursor.fetchall()}
        
        yaml_perms = {p['code']: p for p in cls.extract_permissions_from_registry()}
        
        to_add = [p for code, p in yaml_perms.items() if code not in db_perms]
        to_update = [p for code, p in yaml_perms.items()
                     if code in db_perms]
        
        # 超权限和系统表权限保留
        system_resources = {'all', 'role_menu', 'role_perm'}
        orphaned = [
            code for code, rt in db_perms.items()
            if rt not in all_bo_ids
            and rt not in system_resources
            and code not in yaml_perms
        ]
        
        return {"to_add": to_add, "to_update": to_update, "orphaned": orphaned}
```

### 3.4 改造 init_auth.py

将 `seed_permissions()` 改为调用 `PermissionSyncEngine`：

```python
# init_auth.py 中替换 seed_permissions()

def seed_permissions(conn):
    """从 MetaRegistry 自动同步权限到数据库"""
    # 先确保 MetaRegistry 已加载
    try:
        from meta.core.models import MetaRegistry
        registry = MetaRegistry()
        if not registry.get_all():
            # 需要先加载 YAML
            from meta.core.yaml_loader import register_from_directory
            import os
            schema_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'schemas'
            )
            register_from_directory(schema_dir)
    except Exception:
        pass
    
    from meta.core.permission_sync_engine import PermissionSyncEngine
    inserted, updated = PermissionSyncEngine.sync_to_database()
    print(f"Permissions synced: {inserted} new, {updated} updated")
```

### 3.5 对 role_menu_api.py 的进一步改造

`get_role_unified_permissions()` 中的 `_is_perm_granted()` 和权限标签生成全部从 MetaRegistry 动态读取：

```python
# 完全移除硬编码的 PERMISSION_LABELS 字典
# 改为运行时从 MetaRegistry 构建

def _get_required_permissions_for_menu(menu):
    """从菜单关联的 BO 动态获取 required_permissions
    
    如果菜单的 required_permissions 为空，则从关联的 object_types 推导。
    """
    req_perms = menu.get('required_permissions')
    if req_perms:
        try:
            return json.loads(req_perms) if isinstance(req_perms, str) else req_perms
        except:
            pass
    
    # 从 object_types 自动推导
    object_types = menu.get('object_types', [])
    registry = MetaRegistry()
    auto_perms = []
    for bo_id in object_types:
        obj = registry.get(bo_id)
        if obj:
            for action in obj.actions:
                pure_action = action.id.replace(f"{bo_id}_", "")
                auto_perms.append(f"{bo_id}:{pure_action}")
    return auto_perms
```

---

## 4. 方案三：BO 字段级数据权限声明化

### 4.1 目标

在 YAML Schema 中声明数据权限维度，使条件规则的编写有结构化的字段提示，而非纯手写 SQL-like 表达式。

### 4.2 设计原理

借鉴 **SAP CAP `@restrict.where`** + **Mendix XPath Constraint** 的设计：

```yaml
# SAP CAP 模式
entity SalesOrders @(
  restrict: [{
    grant: ['READ', 'WRITE'],
    to: ['SalesRep'],
    where: 'salesRepId = $user.id'     ← 声明式过滤条件
  }]
)

# Mendix 模式
[SalesRep = '[%CurrentUser%]']         ← XPath 约束
```

### 4.3 YAML Schema 扩展

在 BO Schema 中增加 `data_permission_dimensions` 字段：

```yaml
# 示例: domain.yaml 中增加
data_permission_dimensions:
  # 维度1: 所有者过滤（自动推导）
  - field: owner_id
    type: owner_scope
    description: 按数据所有者过滤
    operator: eq
    value_expression: "$user.id"
    
  # 维度2: 版本上下文过滤
  - field: version_id
    type: context_scope
    description: 按版本过滤
    operator: eq
    value_expression: "$context.version_id"
    
  # 维度3: 状态过滤
  - field: status
    type: field_filter
    description: 按状态过滤
    allowed_operators: [eq, ne, in]
    
  # 维度4: 部门过滤（通过关联路径）
  - field: department_id
    type: hierarchy_scope
    description: 按部门层级过滤
    operator: in
    value_expression: "$user.department_tree"
```

**维度类型枚举**：

| dimension_type | 含义 | 自动行为 |
|---------------|------|---------|
| `owner_scope` | 所有者范围 | 自动添加 `owner_id = $user.id` |
| `context_scope` | 上下文范围 | 从请求上下文注入（如 version_id） |
| `field_filter` | 字段过滤器 | 管理员可配置允许值范围 |
| `hierarchy_scope` | 层级范围 | 按组织层级过滤 |
| `time_scope` | 时间范围 | 按时间窗口过滤 |

### 4.4 模型扩展

在 `models.py` 的 `MetaObject` 中增加字段：

```python
@dataclass
class DataPermissionDimension:
    """数据权限维度声明"""
    field: str                              # 字段ID
    dimension_type: str                     # owner_scope | context_scope | field_filter | hierarchy_scope | time_scope
    description: str = ""
    operator: str = "eq"                    # eq | ne | in | not_in | between
    value_expression: str = ""              # 值表达式，如 "$user.id"
    allowed_operators: List[str] = field(default_factory=list)
    default_enabled: bool = True            # 默认是否启用

@dataclass
class MetaObject:
    # ... 现有字段 ...
    
    # 新增：数据权限维度声明
    data_permission_dimensions: List[DataPermissionDimension] = field(default_factory=list)
```

### 4.5 对 RolePermissionCenter 的影响预览增强

在 `PermissionConfigPanel.vue` 中，条件规则编辑器增加字段级智能提示：

```
当前: 手动输入 condition 表达式 "owner_id = $user.id"
                         ↓ 改进
未来: 下拉选择 dimension → 自动生成 condition
      1. 选择维度: "按所有者过滤 (owner_id)"
      2. 系统自动填充: owner_id = $user.id
      3. 高级模式下仍可手动编写

条件规则编辑器的 UX 变化:
┌─────────────────────────────────────────────────────┐
│  条件规则编辑器                                       │
│                                                      │
│  [选择数据维度 ▼]                                     │
│  ┌──────────────────────────────────────┐            │
│  │ 按所有者过滤 (owner_id = $user.id)    │ ← 来自YAML│
│  │ 按版本过滤 (version_id = $context...)  │            │
│  │ 按状态过滤 (status)                    │            │
│  │ 自定义条件...                          │            │
│  └──────────────────────────────────────┘            │
│                                                      │
│  [高级模式] 手动编写条件表达式                          │
│  ┌──────────────────────────────────────┐            │
│  │ status IN ('active','draft') AND     │            │
│  │ owner_id = $user.id                  │            │
│  └──────────────────────────────────────┘            │
└─────────────────────────────────────────────────────┘
```

### 4.6 数据权限 API 扩展

在 `bo_framework.py` 的查询方法中，增加对 `data_permission_dimensions` 的自动注入：

```python
# bo_framework.py - query() 方法中增加

def _apply_data_permission_filters(self, meta_object: MetaObject, query_params: dict):
    """根据 BO 的 data_permission_dimensions 声明自动注入过滤条件
    
    注意：仅在用户未显式指定该过滤条件时才自动注入。
    """
    for dim in meta_object.data_permission_dimensions:
        if dim.dimension_type == "owner_scope" and dim.field not in query_params:
            # 自动注入 owner_id = $user.id
            current_user_id = self._get_current_user_id()
            if current_user_id:
                query_params[dim.field] = current_user_id
        
        elif dim.dimension_type == "context_scope":
            # 从请求上下文注入
            context_value = self._get_context_value(dim.field)
            if context_value and dim.field not in query_params:
                query_params[dim.field] = context_value
    
    return query_params
```

---

## 5. 方案四：前端菜单完全权限驱动

### 5.1 目标

消除前端多套菜单配置的重复，让前端菜单**完全由后端菜单 API 驱动**。

### 5.2 当前问题

前端存在三套并行的菜单定义：

| 文件 | 用途 | 是否权限过滤 |
|------|------|-------------|
| `src/config/menuConfig.js` | 静态菜单配置 | 否 |
| `src/composables/useMenuPermissions.js` + `getDefaultMenus()` | 降级菜单 | 部分 |
| 后端 `menu_permissions` 表 | 数据库菜单 | 是 |

### 5.3 统一方案

**前端只有一个菜单来源：后端 API 返回的权限过滤后的菜单列表**。

```javascript
// src/composables/useMenuPermissions.js 改造

import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { boApi } from '@/services/boService'

export function useMenuPermissions() {
  const authStore = useAuthStore()
  const menus = ref([])
  const loading = ref(false)

  async function loadMenus() {
    loading.value = true
    try {
      // 从 BO Framework 获取当前用户有权限的菜单
      const resp = await boApi.query('menu', {
        filters: [
          { field: 'is_active', operator: 'eq', value: true }
        ],
        sort: [{ field: 'sort_order', direction: 'asc' }]
      })
      
      if (resp.success && resp.data) {
        // 后端已根据当前用户权限过滤
        menus.value = resp.data.map(menu => ({
          key: menu.menu_code,
          label: menu.menu_name,
          icon: menu.icon,
          to: menu.menu_path,
          parent: menu.parent_menu,
          pageType: menu.page_type,
          objectTypes: menu.object_types,
          pageConfig: menu.page_config,
        }))
      }
    } catch (e) {
      console.warn('Failed to load menus, using cached', e)
      // 降级：使用上次缓存的菜单
    } finally {
      loading.value = false
    }
  }

  // 构建树形菜单结构
  const menuTree = computed(() => {
    const tree = []
    const map = {}
    
    for (const menu of menus.value) {
      map[menu.key] = { ...menu, children: [] }
    }
    
    for (const menu of menus.value) {
      if (menu.parent && map[menu.parent]) {
        map[menu.parent].children.push(map[menu.key])
      } else if (!menu.parent) {
        tree.push(map[menu.key])
      }
    }
    
    return tree
  })

  return { menus, menuTree, loading, loadMenus }
}
```

### 5.4 路由守卫改造

当前 `authStore.isAdmin` 的简单判断改为基于菜单权限的细粒度路由守卫：

```javascript
// src/router/index.js 增加路由守卫

import { useMenuPermissions } from '@/composables/useMenuPermissions'

// 路由 → 菜单编码映射（仅对非动态路由需要）
const ROUTE_MENU_MAP = {
  '/data': 'arch-data',
  '/diagram': 'aa-diagram',
  '/user-permission': 'user-permission',
  '/system-admin': 'audit-log',
  '/business-config': 'business-config',
  '/product-management': 'product-version',
  '/dashboard': 'dashboard',
}

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  
  // 公开路由直接放行
  if (to.meta.public) {
    return next()
  }
  
  // 未登录跳转
  if (!authStore.isLoggedIn) {
    return next('/login')
  }
  
  // 动态路由 /detail/:objectType/:id — 只要登录就放行
  // （权限检查在 API 层完成）
  if (to.path.startsWith('/detail/')) {
    return next()
  }
  
  // 检查菜单权限
  const menuCode = ROUTE_MENU_MAP[to.path]
  if (menuCode) {
    const { menus } = useMenuPermissions()
    const hasAccess = menus.value.some(m => m.key === menuCode)
    if (!hasAccess) {
      return next('/403')
    }
  }
  
  next()
})
```

