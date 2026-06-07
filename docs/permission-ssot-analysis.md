# 权限体系元数据驱动化 — 单一事实源补充分析

> 日期：2026-05-16
> 前置阅读：[权限体系元数据驱动化_细化方案设计.md](./permission-metadata-driven-design.md)

---

## 目录

1. [方法论：什么构成了单一事实源违反](#1-方法论)
2. [违规清单：当前代码中的10处冗余](#2-违规清单)
3. [根本原因：信息已经在YAML中了](#3-根本原因)
4. [消除方案：10处→1处](#4-消除方案)
5. [对细化方案的修正和补充](#5-对细化方案的修正和补充)

---

## 1. 方法论：什么构成了单一事实源违反 {#1-方法论}

### 1.1 判断准则

```
违反条件：同一个业务信息在 ≥2 个独立位置被定义，且其中一个位置的变更不会自动反映到另一个位置。

反例（不违反）：信息从源读取后在内存中缓存—因为重启后会重新从源读取。
正例（违反）    ：两个独立的 Python dict / JS object / YAML 文件定义了同一组映射关系。
```

### 1.2 本项目的单一事实源层次

```
终极事实源：     meta/schemas/*.yaml     （BO定义）
一级推导源：     MetaRegistry            （YAML的运行时镜像）
二级推导源：     permissions 表           （从 YAML actions 同步）
三级推导源：     menus 表                （从 BO 元数据自动生成）
消费者：         role_menu_api.py, role_api.py, 前端组件   （只读取，不重复定义）
```

**原则**：消费者代码中出现的任何名称映射字典（dict）都是潜在违规。除非该映射关系在 YAML 中无法表达。

---

## 2. 违规清单：当前代码中的10处冗余 {#2-违规清单}

### 违规1：PERMISSION_LABELS（role_menu_api.py L152-174）

```python
# 当前：30+ 条硬编码
PERMISSION_LABELS = {
    'domain:read': '领域查看', 'domain:create': '领域创建',
    'domain:update': '领域编辑', 'domain:delete': '领域删除',
    'sub_domain:read': '子领域查看', ...
    'role:read': '角色查看', 'role:create': '角色创建', ...
    '*': '超级权限',
}

# 事实来源（已存在于 YAML）：
# domain.yaml:
#   id: domain
#   name: 领域
#   actions:
#     - id: crud_read
#       name: 查询领域         ← 这就是权限标签！
#     - id: crud_create
#       name: 创建领域
```

**根因**：BO action 的 `name` 字段已经包含了完整的权限显示名称。`'domain:read'` 的标签应该等于 `MetaRegistry.get('domain').get_action('crud_read').name` → `"查询领域"`。

### 违规2：MENU_DISPLAY_NAMES（role_menu_api.py L176-182）

```python
# 当前：5 条硬编码
MENU_DISPLAY_NAMES = {
    'productversion': '产品版本管理',
    'archdata': '架构数据管理',
    'aadiagram': 'AA图生成',
    'businessconfig': '业务配置',
    'userpermission': '用户权限管理',
}

# 事实来源（已存在于 menupermissions 表）：
# SELECT menu_name FROM menu_permissions WHERE menu_code = ?
```

**根因**：`menu_permissions.menu_name` 列已经存储了菜单名称。这段代码的作用是用 `get()` 做降级，降级值应该是 `menu['menu_name']` 而非再维护一套映射。

### 违规3：menuIconMap（useMenuPermissions.js L13-50）

```javascript
// 当前：6 条硬编码（icon, color, name, desc 全部重复定义）
const menuIconMap = {
    productversion: { icon: 'package', color: 'orange', name: '产品版本管理', desc: '管理产品线和版本' },
    archdata:      { icon: 'database', color: 'blue',   name: '架构数据管理',     desc: '管理领域、业务对象等' },
    aadiagram:     { icon: 'diagram', color: 'purple',  name: 'AA图生成',        desc: '生成业务对象关系图' },
    businessconfig:{ icon: 'settings',color: 'teal',    name: '业务配置',         desc: '枚举类型与系统设置' },
    userpermission:{ icon: 'users',   color: 'indigo',  name: '用户与权限管理',    desc: '用户、角色和权限管理' },
    systemadmin:   { icon: 'setting', color: 'blue',    name: '日志管理',         desc: '审计日志与系统监控' },
}

# 事实来源（应在菜单 YAML/DB 中统一定义）：
# menu_permissions 表已有：menu_name, menu_path, icon
# 需要扩充：color, description
```

**根因**：icon/color/description 应该是菜单 BO 的一部分，从后端 API 统一返回。

### 违规4：getDefaultMenus()（useMenuPermissions.js L91-136）

```javascript
// 当前：第4套菜单定义（code + name + path + icon）
const getDefaultMenus = () => {
  const menus = [
    { menu_code: 'productversion', menu_name: '产品版本管理', menu_path: '/product-management' },
    { menu_code: 'archdata', menu_name: '架构数据管理', menu_path: '/data' },
    // ...
  ]
}

# 已经存在的定义：
# 1. menuConfig.js          → 第1套
# 2. init_menu_permissions.py → 第2套
# 3. useMenuPermissions.js menuIconMap → 第3套（仅name）
# 4. useMenuPermissions.js getDefaultMenus → 第4套（完整定义）
```

### 违规5：menuConfig.js 静态菜单树（L8-92）

```javascript
// 第5套菜单定义，使用不同的 key 命名：
// menuConfig.js:  'arch-data'     → init_menu_permissions.py: 'arch-data'
// useMenuPermissions: 'archdata'  → 三个地方三种写法
```

### 违规6：_resource_name() / _action_name()（init_auth.py L289-310）

```python
def _resource_name(resource):
    return {'domain': '领域', 'sub_domain': '子领域', ...}.get(resource, resource)

def _action_name(action):
    return {'create': '创建', 'read': '查看', 'update': '更新', ...}.get(action, action)

# 事实来源：
# BO YAML: id: domain, name: 领域   → 替代 _resource_name()
# Action YAML: id: crud_read, name: 查询领域 → 替代 _action_name()
```

### 违规7：seed_permissions() 硬编码资源列表（init_auth.py L191）

```python
resources = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
# 这个列表不包含 user, role, permission, menu, user_group, enum_type 等
# 应替换为 MetaRegistry.get_all() 迭代
```

### 违规8：_get_resource_name()（data_permission_api.py L189-220）

```python
# data_permission_api.py 中的另一套资源名称映射
def _get_resource_name(resource_type, resource_id):
    # 按 resource_type 分别查询对应表获取名称
    # 这个逻辑可以统一为 MetaRegistry.get(resource_type).get_display_name(resource_id)
```

### 违规9：方案中的 action_suffix_map 重复

当前细化方案中 `action_suffix_map` 同时出现在：
- `MenuAutoGenerator._derive_permissions()`
- `PermissionSyncService._derive_permissions_from_object()`

两个类各自维护了同样的映射字典。应抽取为 `MetaAction` 的类级常量。

### 违规10：_generate_permission_name() 中的名称映射重复

```python
# PermissionSyncService._generate_permission_name()
resource_names = {'domain': '领域', 'sub_domain': '子领域', ...}
action_names = {'create': '创建', 'read': '查看', ...}
# 这些信息完全可以从 MetaRegistry 动态获取
```

---

## 3. 根本原因：信息已经在 YAML 中了 {#3-根本原因}

### 3.1 以 `domain` BO 为例，YAML 已提供所有必要信息

```yaml
id: domain
name: 领域                          ← 替代所有 _resource_name() 字典

actions:
  - id: crud_create
    name: 创建领域                   ← 替代 'domain:create': '领域创建'
  - id: crud_read
    name: 查询领域                   ← 替代 'domain:read': '领域查看'
  - id: crud_update
    name: 更新领域                   ← 替代 'domain:update': '领域编辑'
  - id: crud_delete
    name: 删除领域                   ← 替代 'domain:delete': '领域删除'

ui_view_config:
  list:
    title: 领域管理                  ← 可推导菜单名称
    columns: [...]                 ← 可推导菜单所需展示列
```

### 3.2 唯一的映射：action_id → permission_suffix

这是从 YAML 推导权限编码时唯一需要的映射，且对所有 BO 通用：

| action id | permission suffix |
|-----------|-------------------|
| `crud_create` | `create` |
| `crud_read` | `read` |
| `crud_update` | `update` |
| `crud_delete` | `delete` |

**这个映射必须只存在一处**（建议放在 `MetaAction` 类中），其他地方通过该方法获取。

### 3.3 完整推导链（零硬编码）

```
用户请求权限标签: 'sub_domain:create'

推导步骤（全部从 MetaRegistry）:
1. 解析: resource_type='sub_domain', suffix='create'
2. MetaRegistry.get('sub_domain').name → '子领域'
3. MetaRegistry.get('sub_domain').find_action_by_suffix('create') → action crud_create
4. action.name → '创建子领域'
5. 返回 → '创建子领域'
```

不需要任何硬编码字典。

---

## 4. 消除方案：10处→1处 {#4-消除方案}

### 4.1 中央化：在 models.py 中定义唯一的映射关系

```python
# models.py — MetaAction 增加类级常量
@dataclass  
class MetaAction:
    # ... 现有字段 ...
    
    # 唯一的 action_id → permission_suffix 映射表
    ACTION_SUFFIX_MAP: ClassVar[Dict[str, str]] = {
        'crud_create': 'create',
        'crud_read': 'read',
        'crud_update': 'update',
        'crud_delete': 'delete',
        # 业务动作使用 action.id 本身作为后缀，不需要映射
    }
    
    def get_permission_suffix(self) -> str:
        """推导权限编码后缀"""
        return self.ACTION_SUFFIX_MAP.get(self.id, self.id)
    
    def get_permission_code(self, object_id: str) -> str:
        """推导完整权限编码: domain:create"""
        return f"{object_id}:{self.get_permission_suffix()}"


# MetaObject 增加便利方法
@dataclass
class MetaObject:
    # ... 现有字段 ...
    
    def get_action_by_suffix(self, suffix: str) -> Optional[MetaAction]:
        """通过权限后缀反查 action"""
        for action in self.actions:
            if action.get_permission_suffix() == suffix:
                return action
        return None
    
    def get_permission_label(self, suffix: str) -> str:
        """获取权限显示标签"""
        action = self.get_action_by_suffix(suffix)
        if action and action.name:
            return action.name
        return f"{self.name}{suffix}"
```

### 4.2 消除各违规点

#### 消除违规1（PERMISSION_LABELS）

```python
# role_menu_api.py — 替换硬编码字典为动态查找
def _get_permission_label(perm_code: str) -> str:
    """从 MetaRegistry 动态获取权限标签"""
    if perm_code == '*':
        return '超级权限'
    parts = perm_code.split(':')
    if len(parts) != 2:
        return perm_code
    resource_type, suffix = parts
    meta_obj = registry.get(resource_type)
    if meta_obj:
        return meta_obj.get_permission_label(suffix)
    return perm_code

# 使用处：
# 将 PERMISSION_LABELS.get(p, p) 替换为 _get_permission_label(p)
```

#### 消除违规2（MENU_DISPLAY_NAMES）

```python
# role_menu_api.py — 直接使用数据库中的 menu_name
# 之前: 'display_name': MENU_DISPLAY_NAMES.get(code.lower(), menu.get('menu_name', code))
# 之后: 'display_name': menu.get('menu_name', code)   # menu_name 已在表中
```

#### 消除违规3/4/5（前端菜单）

```javascript
// useMenuPermissions.js — 菜单的所有属性从后端API获取
// 移除 menuIconMap、getDefaultMenus 中的硬编码

// 后端返回的菜单已包含所有展示信息：
{
  "menu_code": "domain-list",
  "menu_name": "领域管理",        // ← 来自 menus 表
  "menu_path": "/domain",
  "icon": "folder",               // ← 来自 menus 表
  "color": "blue",                // ← menus 表新增字段
  "description": "管理领域数据",    // ← menus 表新增字段
  "page_type": "object_list",
  "primary_object_type": "domain"
}

// menuConfig.js — 废弃，全部改用 API
```

#### 消除违规6（_resource_name / _action_name）

```python
# init_auth.py — 使用 MetaRegistry 替代
def seed_permissions(conn):
    """委托给 PermissionSyncService"""
    from meta.services.permission_sync_service import get_permission_sync_service
    service = get_permission_sync_service(conn)
    result = service.sync_all()
    # 不再需要 _resource_name() 和 _action_name()
```

#### 消除违规7（硬编码资源列表）

```python
# PermissionSyncService 中：
# 之前: resources = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
# 之后: for obj_id, meta_obj in registry.get_all().items():
```

#### 消除违规8（_get_resource_name）

```python
# data_permission_api.py — 使用 MetaRegistry 统一查询
def _get_resource_name(resource_type, resource_id):
    meta_obj = registry.get(resource_type)
    if meta_obj:
        # 查询该对象的 display_name_field 获取显示名
        record = bo_framework.read(resource_type, resource_id)
        if record and meta_obj.display_name_field:
            return record.get(meta_obj.display_name_field, str(resource_id))
    return str(resource_id)
```

#### 消除违规9（action_suffix_map 重复）

```python
# 所有服务类统一使用 MetaAction.ACTION_SUFFIX_MAP
# MenuAutoGenerator._derive_permissions() 中:
suffix = action.get_permission_suffix()  # 而非访问本地字典

# PermissionSyncService 同理
```

#### 消除违规10（_generate_permission_name 中的重复映射）

```python
# PermissionSyncService — 使用 meta_obj.get_permission_label()
def _generate_permission_name(self, resource_type: str, suffix: str) -> str:
    meta_obj = registry.get(resource_type)
    if meta_obj:
        return meta_obj.get_permission_label(suffix)
    return f"{resource_type}:{suffix}"
```

---

## 5. 对细化方案的修正和补充 {#5-对细化方案的修正和补充}

### 5.1 修正1：menu.yaml 增加 color 和 description 字段

原方案缺少 `color` 和 `description` 字段，导致前端 `menuIconMap` 无法消除：

```yaml
# menu.yaml 新增字段
  - id: color
    name: 主题色
    type: string
    db_column: color
    max_length: 50
    description: 菜单卡片主题色

  - id: description
    name: 描述
    type: string
    db_column: description
    max_length: 500
    description: 菜单功能描述
```

### 5.2 修正2：permission.yaml 的 name 字段由同步服务自动填充

当前 `permission.name` 需要手动填充。方案修正为：

```python
# PermissionSyncService.sync_all() 中
# 不仅创建缺失的权限，也更新已有的权限名称（以防 YAML 中 action name 变更）
for perm_code in to_create | to_update:
    resource_type, suffix = parse(perm_code)
    name = meta_obj.get_permission_label(suffix)  # 从 YAML 推导，零硬编码
    cursor.execute("INSERT OR REPLACE INTO permissions ...")
```

### 5.3 修正3：role_api.py 中统一权限视图的 label 推导

```python
# role_menu_api.py get_role_unified_permissions() 中
# 当前：label: PERMISSION_LABELS.get(p, p)
# 修正：label: _get_permission_label(p)
```

### 5.4 修正4：前端 getDefaultMenus 降级逻辑

```javascript
// 当 API 不可用时，降级为从本地缓存的 menu config 读取
// 不再维护第4套硬编码菜单定义
const getDefaultMenus = async () => {
  // 尝试从 localStorage 读取上次缓存的菜单配置
  const cached = localStorage.getItem('menu_config_cache')
  if (cached) {
    return JSON.parse(cached)
  }
  // 最终降级：空列表（用户需要登录或刷新）
  return []
}
```

### 5.5 最终单一事实源架构图

```
                        meta/schemas/*.yaml
                       （唯一事实源 — 永不重复定义）
                              │
                ┌─────────────┼─────────────┐
                │             │             │
          [BO.id + name]  [actions]    [ui_view_config]
                │             │             │
                ▼             ▼             ▼
         resource 名称    permission 名称   menu 配置
                │             │             │
                │      ┌──────┴──────┐      │
                │      │             │      │
                ▼      ▼             ▼      ▼
          permissions 表      menu_permissions 表
                │                    │
                └────────┬───────────┘
                         │
                    role_permissions
                    role_menu_permissions
                         │
                         ▼
                   用户有效权限

所有消费者代码（API、前端）中：
  - 不存在任何 PERMISSION_LABELS / MENU_DISPLAY_NAMES / _resource_name 等字典
  - 不存在任何 menuIconMap / getDefaultMenus 硬编码
  - 所有名称通过 MetaRegistry 动态获取
  - 唯一的映射关系：MetaAction.ACTION_SUFFIX_MAP（一个 dict，5 行）
```

---

## 总结

| 指标 | 当前 | 方案后 |
|------|------|--------|
| 硬编码字典数量 | 10+ 处 | **1 处**（MetaAction.ACTION_SUFFIX_MAP，5条通用映射） |
| 菜单定义位置 | 5 套独立定义 | **1 套**（menus 表 + menu.yaml） |
| 权限标签定义 | 4 处重复 | **0 处**（全部从 actions[].name 动态获取） |
| 新增 BO 需要修改的文件 | 4+ 个文件 | **0 个文件**（完全自动） |
| 权限名称变更步骤 | 改 YAML + 改 3 处硬编码 | **只改 YAML**（自动同步） |

核心原则只有一条：**如果信息可以从 YAML 和 MetaRegistry 推导出来，就绝对不要在代码中再写一遍。**
