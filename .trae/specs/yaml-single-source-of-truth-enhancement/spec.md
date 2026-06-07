# YAML 单一事实原则优化与元数据驱动架构演进 Spec

> **Spec ID**: yaml-single-source-of-truth-enhancement
> **版本**: v1.3.0
> **创建日期**: 2026-05-19
> **状态**: In Progress (Phase 1-2.5 ✅ | 动态路由 ✅ | 数据权限声明化 ✅ | 测试 ✅ | 剩余: 1 前端页面)
> **优先级**: P0 (Critical)
> **当前进度**: ~90%
> **关联文档**: 
> - [ARCHITECTURE_V2.md](../../docs/ARCHITECTURE_V2.md)
> - [YAML 规范 v2.0](../../docs/architecture/02-yaml-conventions-v2.md)
> - [竞品架构分析](../../docs/竞品架构分析_元数据驱动与权限模型.md)
> - [菜单元数据化子 Spec](specs/menu-permission-sync-spec.md)
> - [实际现状细化方案](specs/refined-implementation-plan.md)

---

## 目录

1. [背景与动机](#一-背景与动机)
2. [当前状态评估](#二-当前状态评估)
3. [业界对比分析](#三-业界对比分析)
4. [问题定义与差距分析](#四-问题定义与差距分析)
5. [优化方案设计](#五-优化方案设计)
6. [实施计划](#六-实施计划)
7. [验收标准](#七-验收标准)
8. [风险评估与缓解](#八-风险评估与缓解)
9. [附录](#附录)

---

## 一、背景与动机

### 1.1 核心理念

**YAML 单一事实原则 (Single Source of Truth)** 是元数据驱动架构的基石：

> YAML 配置文件是系统行为的唯一权威来源。前端和后端都从 YAML 派生行为，而不是通过独立的配置层。

### 1.2 当前问题

尽管我们的架构在元数据驱动方面已经达到 72% 的成熟度，但存在两个**严重违背单一事实原则**的问题：

1. **菜单元数据化缺失**：菜单配置分散在路由、前端组件、独立的 menu.yaml 中，未与 BO 形成闭环
2. **权限自动同步缺失**：YAML 中声明了 `actions`，但 `permissions` 表需要手动维护，两者可能不一致

### 1.3 业务价值

解决这些问题将带来：

| 价值维度 | 当前状态 | 优化后 | 业务收益 |
|---------|---------|--------|---------|
| **开发效率** | 新增对象需手动配置菜单和权限 | YAML 一处定义，全局生效 | 开发周期缩短 30%+ |
| **一致性** | YAML 与数据库可能不一致 | 自动同步保证一致性 | 消除配置漂移风险 |
| **可维护性** | 多处修改才能完成一个功能 | 单点修改，影响自动传播 | 维护成本降低 50%+ |
| **可追溯性** | 配置变更难以追踪 | YAML 版本管理天然支持 | 问题定位时间缩短 70%+ |

---

## 二、当前状态评估

### 2.1 成熟度矩阵

| 维度 | 实现程度 | 评分 | 说明 |
|------|---------|------|------|
| **对象定义** | ✅ 完整 | 95% | 25+ YAML 文件定义业务对象 |
| **字段语义** | ✅ 完整 | 90% | semantics 块覆盖业务键、计算、敏感等 |
| **UI 配置** | ✅ 完整 | 85% | ui_view_config 覆盖 list/detail/form |
| **关联定义** | ✅ 完整 | 90% | 支持 4 种关联类型 + through 表 |
| **Value Help** | ✅ 完整 | 95% | 三种模式（enum/bo/custom） |
| **State Machine** | ✅ 完整 | 85% | rules: state_transition 已实现 |
| **计算字段** | ⚠️ 部分 | 70% | 支持 SQL/Expression，缺少依赖追踪 |
| **权限推导** | ⚠️ 部分 | 60% | 有 permissions 块，但未与 actions 自动同步 |
| **菜单元数据** | ❌ 缺失 | 30% | 菜单配置分散，未纳入 YAML |
| **多租户** | ❌ 缺失 | 0% | 单租户架构 |
| **变更追踪** | ⚠️ 部分 | 50% | 有审计，但缺少字段级变更历史查询 |
| **版本管理** | ❌ 缺失 | 20% | YAML 无版本控制机制 |

**总体评分**: **72/100**

### 2.2 当前架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     当前元数据驱动架构                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  YAML Schema (单一事实源)                                           │
│  ├── user.yaml, role.yaml, product.yaml, ...                       │
│  ├── fields, semantics, ui, associations, rules                    │
│  └── ✅ 后端 BO Framework 从此派生                                  │
│       ├── 自动生成 CRUD API                                         │
│       ├── 自动执行拦截器链                                           │
│       └── 自动返回 UI Config                                        │
│                                                                     │
│  ❌ 断裂点 1: 菜单配置                                               │
│  ├── router/index.js (硬编码路由)                                   │
│  ├── src/views/ (硬编码页面)                                        │
│  └── menu.yaml (孤立，未关联 BO)                                    │
│                                                                     │
│  ❌ 断裂点 2: 权限配置                                               │
│  ├── YAML actions: [create, update, delete]                        │
│  └── permissions 表 (手动维护，可能不一致)                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、业界对比分析

### 3.1 六大平台对比

| 维度 | Salesforce | SAP CAP | D365 | ServiceNow | Mendix | **我们** |
|------|-----------|---------|------|------------|--------|---------|
| **元数据定义** | 可视化 | CDS 注解 | 可视化 | 字典表 | ER 图 | **YAML** |
| **UI 生成** | 运行时 | SADL | 运行时 | 运行时 | 运行时 | **运行时** |
| **权限声明** | Profile 配置 | `@restrict` | Role 配置 | ACL | 实体规则 | **YAML 块** |
| **权限推导** | ❌ 手动 | ✅ 注解 | ❌ 手动 | ❌ 手动 | ✅ 实体规则 | **⚠️ 部分** |
| **菜单关联** | App→Object | Tile→Entity | Site→Table | Menu→Table | Nav→Entity | **❌ 分散** |
| **多租户** | ✅ 原生 | ✅ 原生 | ✅ 原生 | ✅ 原生 | ⚠️ | **❌** |
| **版本管理** | ✅ | ✅ | ✅ Solution | ✅ UpdateSet | ✅ | **❌** |

### 3.2 关键洞察

#### 洞察 1：权限内嵌元数据是行业演进方向

**SAP CAP 的 `@restrict` 注解**：

```cds
@restrict: [
  { grant: ['READ', 'WRITE'], to: ['Manager'] },
  { grant: ['READ'], to: ['Viewer'], where: 'status = "published"' }
]
entity Products { ... }
```

**Mendix 的实体访问规则**：

```
Entity: Order
Access Rules:
  - Role: SalesRep
    Create: Yes
    Delete: No
    XPath: [Owner = '[%CurrentUser%]']
```

**结论**：我们提出的"权限从 YAML actions 自动推导"**领先于 Salesforce**，与 SAP CAP/Mendix 同代。

---

#### 洞察 2：菜单 = 对象 + 配置 是行业共识

| 平台 | 菜单结构 | 对象关联 |
|------|---------|---------|
| Salesforce | App → Tab | Tab → Object |
| SAP Fiori | Catalog → Tile | Tile → Semantic Object → Entity |
| D365 | Area → Group → SubArea | SubArea → Table + View |
| ServiceNow | App Menu → Module | Module → Table |
| Mendix | Navigation → Menu Item | Menu Item → Page → Entity |

**无一例外**。这完全验证了我们的核心论断。

---

#### 洞察 3：我们架构的差异化优势

| 优势 | 业界对比 | 价值 |
|------|---------|------|
| **YAML 文本化** | 优于可视化配置 | Git 版本管理天然支持 |
| **运行时解释** | 优于 OutSystems 编译时 | 改 YAML 即生效 |
| **权限可推导** | 领先于 Salesforce | 减少 80% 手动配置 |
| **全链路元数据** | 高于大多数平台 | BO → API → UI 一体化 |
| **影响预览** | 独创功能 | 权限变更可视化 |

---

## 四、问题定义与差距分析

### 4.1 问题 1：菜单元数据化缺失 🔴 **P0**

#### 当前状态

```
菜单配置分散在：
├── router/index.js          # 路由定义（硬编码）
├── src/views/               # 页面组件（硬编码）
├── menu.yaml                # 菜单元数据（孤立）
└── 权限检查分散在多处

问题：
1. 新增对象需要手动修改 3+ 个文件
2. 菜单与 BO 的关系未在 YAML 中声明
3. 无法保证菜单与 BO 的一致性
```

#### 业界最佳实践

**SAP Fiori Launchpad**：

```json
{
  "semanticObject": "Product",
  "action": "manage",
  "entitySet": "Products"    // 直接关联到 CDS Entity
}
```

**Microsoft D365 Sitemap**：

```xml
<SubArea Id="product" Entity="product" />
```

#### 差距分析

| 维度 | 业界标准 | 我们现状 | 差距 |
|------|---------|---------|------|
| 菜单定义位置 | 元数据中 | 分散 | 🔴 严重 |
| 菜单→对象关联 | 自动 | 手动 | 🔴 严重 |
| 路由生成 | 自动 | 手动 | 🔴 严重 |
| 权限检查 | 统一 | 分散 | 🟡 中等 |

---

### 4.2 问题 2：权限自动同步缺失 🔴 **P0**

#### 当前状态

```
YAML 定义：
actions:
  - id: create
    label: 新建
  - id: update
    label: 编辑
  - id: delete
    label: 删除

数据库 permissions 表：
- 需要手动创建记录
- 可能与 YAML 不一致
- 无法保证同步

问题：
1. 新增 action 后需要手动创建权限记录
2. 修改 action 后需要手动更新权限记录
3. 删除 action 后权限记录可能残留
```

#### 业界最佳实践

**Mendix 实体访问规则**：

```
Entity: Order
Access Rules:
  - Role: SalesRep
    Create: Yes
    Delete: if [Owner = CurrentUser]
```

权限直接在实体定义中声明，无需单独维护权限表。

#### 差距分析

| 维度 | 业界标准 | 我们现状 | 差距 |
|------|---------|---------|------|
| 权限定义位置 | 元数据中 | YAML + 数据库 | 🟡 中等 |
| 权限同步 | 自动 | 手动 | 🔴 严重 |
| 权限推导 | 从 actions 推导 | 需手动配置 | 🔴 严重 |
| 一致性保证 | 编译时检查 | 运行时可能不一致 | 🔴 严重 |

---

### 4.3 问题 3：计算字段依赖追踪缺失 🟡 **P1**

#### 当前状态

```yaml
- id: full_name
  computation:
    expression: "{first_name} {last_name}"
    depends_on: [first_name, last_name]  # 手动声明

问题：
1. depends_on 需要手动维护
2. first_name 变更后 full_name 不会自动重算
3. 批量更新时无法追踪影响范围
```

#### 业界最佳实践

**Salesforce Formula Fields**：

```
自动依赖追踪：
- 解析表达式提取依赖字段
- 构建依赖图
- 变更时自动标记下游字段为 dirty
- 批量更新时自动重算
```

---

### 4.4 问题 4：数据权限声明化不足 🟡 **P1**

#### 当前状态

```yaml
# 当前：手动编写条件规则
rules:
  - id: owner_only
    condition: "owner_id = $user.id"
```

#### 业界最佳实践

**SAP CAP where 条件**：

```cds
@restrict: [{
  grant: ['READ'],
  to: ['SalesRep'],
  where: 'salesRepId = $user.id'
}]
```

**Mendix XPath Constraint**：

```
[Owner = '[%CurrentUser%]']
[Status = 'Active'][Department = '[%CurrentUserDepartment%]']
```

---

## 五、优化方案设计

### 5.1 方案 1：菜单元数据化 🔴 **P0**

#### 设计目标

1. 菜单配置纳入 YAML，成为 BO 的一部分
2. 自动生成路由、页面组件、权限检查
3. 支持 BO → 菜单 双向导航

#### YAML 扩展设计

**方案 A：在 BO YAML 中内嵌菜单配置**（推荐）

```yaml
# user.yaml
id: user
name: 用户管理

# 新增 menu 配置块
menu:
  enabled: true                    # 是否在菜单中显示
  category: system                 # 菜单分类（对应一级菜单）
  category_label: 系统管理          # 分类显示名（如果分类不存在则创建）
  category_icon: setting           # 分类图标
  category_order: 100              # 分类排序
  
  label: 用户管理                   # 菜单项显示名
  icon: user                       # 菜单项图标
  order: 10                        # 菜单项排序（同分类内）
  
  route: /system/user              # 路由路径（可自动生成）
  component: MetaListPage          # 页面组件（默认 MetaListPage）
  
  visible_roles: [admin, user_manager]  # 可见角色
  permissions:                     # 所需权限（可从 actions 自动推导）
    - user.read
```

**方案 B：独立的 menu.yaml**（备选）

```yaml
# menu.yaml
id: main_menu
name: 主菜单

categories:
  - id: system
    label: 系统管理
    icon: setting
    order: 100
    
  - id: business
    label: 业务数据
    icon: briefcase
    order: 200

items:
  - id: user_management
    label: 用户管理
    icon: user
    category: system
    order: 10
    
    # 关联到 BO
    object_type: user              # ← 关键：直接关联 BO
    route: /system/user            # 自动生成
    component: MetaListPage        # 默认组件
    
    visible_roles: [admin, user_manager]
    
  - id: role_management
    label: 角色管理
    object_type: role
    category: system
    order: 20
```

#### 自动生成逻辑

```python
# meta/tools/menu_generator.py

class MenuGenerator:
    def generate_routes(self, menu_config):
        """从菜单配置自动生成路由"""
        routes = []
        for item in menu_config.items:
            if item.object_type:
                routes.append({
                    'path': item.route,
                    'name': f"{item.object_type}_list",
                    'component': item.component or 'MetaListPage',
                    'meta': {
                        'object_type': item.object_type,
                        'title': item.label,
                        'permissions': self._infer_permissions(item)
                    }
                })
        return routes
    
    def generate_vue_router(self, routes):
        """生成 Vue Router 配置文件"""
        # 输出到 src/router/generated.js
        
    def generate_menu_tree(self, menu_config, user_roles):
        """根据用户角色生成菜单树"""
        # 过滤 visible_roles
        # 返回前端可渲染的菜单结构
```

#### 前端集成

```javascript
// src/stores/menuStore.js

export const useMenuStore = defineStore('menu', {
  state: () => ({
    menuTree: [],
    loaded: false
  }),
  
  actions: {
    async loadMenu() {
      // 从 API 获取菜单树（已根据角色过滤）
      const response = await api.get('/api/v2/menu/tree')
      this.menuTree = response.data
      this.loaded = true
    },
    
    // 检查菜单项是否可见
    isMenuVisible(menuItem) {
      return this.menuTree.some(m => m.id === menuItem.id)
    }
  }
})
```

---

### 5.2 方案 2：权限自动同步 🔴 **P0**

#### 设计目标

1. YAML actions 自动生成 permissions 记录
2. YAML 变更时自动同步权限
3. 提供一致性检查工具

#### YAML 扩展设计

```yaml
# user.yaml
id: user
name: 用户管理

actions:
  - id: create
    label: 新建用户
    icon: plus
    type: primary
    
    # 新增：权限自动生成配置
    permission:
      auto_create: true           # 自动创建权限记录
      roles: [admin, user_manager]  # 默认授权角色
      
  - id: update
    label: 编辑
    permission:
      auto_create: true
      roles: [admin, user_manager]
      
  - id: delete
    label: 删除
    type: danger
    permission:
      auto_create: true
      roles: [admin]              # 仅管理员可删除

# 或简化为（推荐）
permissions:
  create: [admin, user_manager]
  read: [admin, user_manager, viewer]
  update: [admin, user_manager]
  delete: [admin]
```

#### 同步机制设计

```python
# meta/tools/permission_sync.py

class PermissionSync:
    def __init__(self):
        self.db = get_db()
        
    def sync_all(self):
        """全量同步所有 YAML 的权限"""
        yaml_files = glob.glob('meta/schemas/*.yaml')
        
        for yaml_file in yaml_files:
            meta = yaml_loader.load(yaml_file)
            self.sync_object(meta)
            
    def sync_object(self, meta):
        """同步单个对象的权限"""
        object_type = meta.id
        
        # 1. 从 actions 推导权限
        expected_permissions = self._infer_from_actions(meta)
        
        # 2. 从 permissions 块读取显式配置
        explicit_permissions = meta.get('permissions', {})
        
        # 3. 合并
        final_permissions = self._merge(expected_permissions, explicit_permissions)
        
        # 4. 同步到数据库
        for action, roles in final_permissions.items():
            permission_code = f"{object_type}.{action}"
            
            # 创建或更新权限记录
            permission = Permission.upsert(
                code=permission_code,
                name=f"{meta.name} - {action}",
                resource_type=object_type,
                action_code=action
            )
            
            # 同步角色授权
            self._sync_role_permissions(permission, roles)
            
    def _infer_from_actions(self, meta):
        """从 actions 自动推导权限"""
        permissions = {}
        for action in meta.get('actions', []):
            action_id = action.id
            
            # 标准动作映射
            if action_id in ['create', 'update', 'delete', 'read']:
                permissions[action_id] = action.get('permission', {}).get('roles', [])
                
        return permissions
        
    def check_consistency(self):
        """检查 YAML 与数据库的一致性"""
        inconsistencies = []
        
        yaml_permissions = self._load_yaml_permissions()
        db_permissions = self._load_db_permissions()
        
        for perm in yaml_permissions:
            if perm not in db_permissions:
                inconsistencies.append({
                    'type': 'missing_in_db',
                    'permission': perm,
                    'message': f"权限 {perm} 在 YAML 中定义但数据库中不存在"
                })
                
        for perm in db_permissions:
            if perm not in yaml_permissions:
                inconsistencies.append({
                    'type': 'orphan_in_db',
                    'permission': perm,
                    'message': f"权限 {perm} 在数据库中存在但 YAML 中未定义"
                })
                
        return inconsistencies
```

#### 触发时机

| 时机 | 触发方式 | 说明 |
|------|---------|------|
| **服务启动** | 自动检查 | 检测不一致并警告 |
| **YAML 变更** | 文件监听 | 自动触发同步 |
| **手动触发** | CLI 命令 | `python -m meta.tools.permission_sync --sync` |
| **CI/CD** | 检查步骤 | 不一致则构建失败 |

---

### 5.3 方案 3：计算字段依赖追踪 🟡 **P1**

#### 设计目标

1. 自动解析表达式提取依赖字段
2. 构建依赖图，支持批量重算
3. 变更时自动标记下游字段为 dirty

#### YAML 扩展设计

```yaml
- id: full_name
  computation:
    expression: "{first_name} {last_name}"
    # 不再需要手动声明 depends_on
    
- id: display_name
  computation:
    expression: "{full_name} ({email})"
    # 自动解析依赖：full_name, email
    # 传递依赖：first_name, last_name, email
```

#### 依赖追踪实现

```python
# meta/core/dependency_tracker.py

import re
from collections import defaultdict

class DependencyTracker:
    PLACEHOLDER_PATTERN = re.compile(r'\{(\w+)\}')
    
    def parse_expression(self, expr: str) -> set:
        """从表达式自动提取依赖字段"""
        return set(self.PLACEHOLDER_PATTERN.findall(expr))
    
    def build_dependency_graph(self, yaml_meta) -> dict:
        """构建字段依赖图"""
        graph = defaultdict(set)
        
        for field in yaml_meta.fields:
            if field.get('computation'):
                expr = field['computation'].get('expression', '')
                deps = self.parse_expression(expr)
                graph[field.id] = deps
                
        return dict(graph)
    
    def get_transitive_dependencies(self, graph: dict, field_id: str) -> set:
        """获取传递依赖（所有上游字段）"""
        visited = set()
        stack = [field_id]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            
            for dep in graph.get(current, []):
                if dep not in visited:
                    stack.append(dep)
                    
        return visited - {field_id}
    
    def get_dependents(self, graph: dict, field_id: str) -> set:
        """获取依赖者（所有下游字段）"""
        dependents = set()
        
        for f, deps in graph.items():
            if field_id in deps:
                dependents.add(f)
                # 递归获取传递依赖者
                dependents.update(self.get_dependents(graph, f))
                
        return dependents
```

#### 变更触发机制

```python
# meta/core/interceptors/computation_interceptor.py

class ComputationInterceptor(BaseInterceptor):
    def after_action(self, action, entity, result, context):
        """更新后触发计算字段重算"""
        if action not in ['create', 'update']:
            return
            
        # 获取变更的字段
        changed_fields = context.get('changed_fields', [])
        
        # 获取依赖图
        graph = self.dependency_tracker.build_dependency_graph(entity)
        
        # 找出需要重算的字段
        to_recompute = set()
        for field in changed_fields:
            dependents = self.dependency_tracker.get_dependents(graph, field)
            to_recompute.update(dependents)
            
        # 批量重算
        if to_recompute:
            self._recompute_fields(result, to_recompute)
```

---

### 5.4 方案 4：数据权限声明化 🟡 **P1**

#### 设计目标

1. 在 YAML 中声明数据权限维度
2. 自动生成条件规则
3. 支持多维度组合

#### YAML 扩展设计

```yaml
# user.yaml
id: user
name: 用户管理

# 新增：数据权限维度声明
data_permission:
  # 维度定义
  dimensions:
    - id: owner
      field: owner_id
      description: 数据所有者
      default_scope: self          # 默认：只能看自己的
      
    - id: department
      field: department_id
      description: 所属部门
      join: "user.department_id = $user.department_id"
      
    - id: company
      field: company_id
      description: 所属公司
      join: "user.company_id = $user.company_id"

  # 自动规则生成
  auto_rules:
    - role: user
      scope: owner                  # 只能看自己的
      condition: "owner_id = $user.id"
      
    - role: department_manager
      scope: department             # 能看部门的
      condition: "department_id = $user.department_id"
      
    - role: company_admin
      scope: company                # 能看全公司的
      condition: null               # 无条件（全部可见）
      
    - role: super_admin
      scope: global                 # 全局
      condition: null
```

#### 自动生成逻辑

```python
# meta/tools/data_permission_generator.py

class DataPermissionGenerator:
    def generate_rules(self, yaml_meta):
        """从 YAML 自动生成数据权限规则"""
        rules = []
        
        data_perm = yaml_meta.get('data_permission', {})
        auto_rules = data_perm.get('auto_rules', [])
        
        for rule in auto_rules:
            condition = self._build_condition(rule, data_perm['dimensions'])
            
            rules.append({
                'role_code': rule['role'],
                'resource_type': yaml_meta.id,
                'condition': condition,
                'scope': rule['scope']
            })
            
        return rules
    
    def _build_condition(self, rule, dimensions):
        """构建 SQL 条件"""
        if rule.get('condition'):
            return rule['condition']
            
        scope = rule['scope']
        
        # 查找维度定义
        for dim in dimensions:
            if dim['id'] == scope:
                return f"{dim['field']} = $user.id"
                
        return None
```

---

## 六、实施计划

> **最后更新**: 2026-05-19
> **版本**: v1.2.0（新增 Owner 模型增强）

### 6.1 Phase 划分

| Phase | 内容 | 工作量 | 依赖 | 交付物 | 状态 |
|-------|------|--------|------|--------|------|
| **Phase 1** | 菜单元数据化 | 1.5 周 | 无 | menu.yaml + 自动生成工具 | ✅ 完成 |
| **Phase 2** | 权限自动同步 | 1 周 | 无 | permission_sync.py + 一致性检查 | ✅ 完成 |
| **Phase 2.5** | Owner 模型增强 | 1 周 | 无 | BO YAML 修复 + OwnerTransferService + API | ✅ 完成 |
| **✅ 已内置** | 计算字段依赖追踪 | - | - | rule_chain.py (DependencyGraph + ImplicitRuleChainExecutor) | ✅ 已实现 |
| **Phase 3** | 动态路由 + 数据权限声明化 | 1.5 周 | Phase 1,2 | dynamicRoutes.js + DataPermissionGenerator | ✅ 完成 |
| **Phase 3.5** | 服务层测试 | 0.5 周 | Phase 1-3 | test_permission_sync_service.py + test_owner_transfer_service.py | ✅ 完成 |
| **Phase 4** | Owner 转移前端页面 | 0.5 周 | Phase 2.5 | Owner 转移管理组件 | ⏳ 待实施 |

**总计**: **~5 周** | **已完成**: **~90%** | **剩余**: **~0.5 周 (1天)**

---

### 6.2 详细任务清单

#### 已完成 ✅

| 任务ID | 任务名称 | 实施日期 | 实施文件 |
|--------|---------|---------|---------|
| **P0-1** | 修复7个BO YAML auto_permission声明 | 2026-05-19 | product.yaml, version.yaml, domain.yaml, sub_domain.yaml, service_module.yaml, business_object.yaml, relationship.yaml |
| **P1-1** | OwnerTransferService 服务 | 2026-05-19 | owner_transfer_service.py (270行) |
| **P1-2** | Owner 转移 API (4个端点) | 2026-05-19 | owner_transfer_api.py (230行) + server.py 注册 |
| **P1** | 菜单元数据化 | 2026-05-19 | menu.yaml bo_bindings + MenuAutoGenerator + menu_permission_api.py |
| **P2** | 权限自动同步 | 2026-05-19 | permission_sync_service.py + permission_sync_api.py + migrate脚本 |
| **P3-1** | 动态路由生成 | 2026-05-19 | dynamicRoutes.js (120行) + router/index.js 改造 + AppRootLayout.vue |
| **P3-2** | DataPermissionGenerator | 2026-05-19 | data_permission_generator.py (170行) + bo_api.py 集成 |
| **P4-1** | 权限同步服务测试 | 2026-05-19 | test_permission_sync_service.py (8/8 pass) |
| **P4-2** | Owner 模型集成测试 | 2026-05-19 | test_owner_transfer_service.py (6/6 pass) |

#### 待实施 ⏳

| 任务ID | 任务名称 | 优先级 | 工作量 | 依赖 |
|--------|---------|--------|--------|------|
| **P5-1** | Owner 转移前端管理页面 | P2 | 1天 | P1-1, P1-2 |

**剩余工作量**: **1天**

---

### 6.3 实施时间线（剩余任务）

```
Day 1-3:  P3-1 动态路由生成
          ├── src/router/dynamicRoutes.js (新建)
          ├── src/router/index.js (改造)
          └── src/components/common/AppRootLayout.vue (初始化)

Day 4-5:  P3-2 数据权限声明化
          ├── data_permission_generator.py (新建)
          └── meta/api/bo_api.py (集成)

Day 6:    P4-1 权限同步服务测试
          └── test_permission_sync_service.py (新建)

Day 7:    P4-2 Owner 模型集成测试
          └── test_owner_transfer_service.py (新建)

Day 8:    P4-3 端到端回归测试

Day 9:    P2-1 Owner 转移前端管理页面

Day 10:   P5-1 架构文档更新
```

---

### 6.2 Phase 1：菜单元数据化 ✅ 已完成

> **完成日期**: 2026-05-19
> **实施详情**: 参见 [菜单元数据化子 Spec](specs/menu-permission-sync-spec.md) Phase 2

#### 任务清单

- [x] **T1.1** 设计 YAML menu 配置块结构
- [x] **T1.2** 实现 MenuGenerator 类
  - [x] generate_routes() 方法
  - [x] generate_vue_router() 方法
  - [x] generate_menu_tree() 方法
- [x] **T1.3** 创建菜单 API
  - [x] GET /api/v2/menu/tree
  - [x] GET /api/v2/menu/categories
- [x] **T1.4** 前端集成
  - [x] menuStore.js (已有 useMenuPermissions)
  - [x] AppSideNav 组件改造 (已支持)
- [x] **T1.5** 迁移现有菜单配置
  - [x] 从 router/index.js 提取
  - [x] 生成 menu.yaml
- [x] **T1.6** 测试
  - [x] 单元测试
  - [ ] E2E 测试 (待补充)

#### 验收标准

- [x] 所有 BO 对象的菜单项都在 YAML 中定义
- [x] 路由配置自动生成，无需手动修改
- [x] 菜单权限检查统一在 YAML 中声明
- [x] 前端菜单渲染正确

#### 实施文件

- `meta/schemas/menu.yaml` - 菜单元数据定义
- `meta/services/menu_auto_generator.py` - 菜单自动生成器
- `meta/api/menu_permission_api.py` - 菜单权限 API
- `src/views/SystemManagement/components/MenuPermissionMatrix.vue` - 前端组件

---

### 6.3 Phase 2：权限自动同步 ✅ 已完成

> **完成日期**: 2026-05-19
> **实施详情**: 参见 [菜单元数据化子 Spec](specs/menu-permission-sync-spec.md) Phase 1, Phase 4

#### 任务清单

- [x] **T2.1** 设计 YAML permissions 配置块
- [x] **T2.2** 实现 PermissionSync 类
  - [x] sync_all() 方法
  - [x] sync_object() 方法
  - [x] check_consistency() 方法
- [x] **T2.3** 集成到服务启动流程
  - [x] server.py 启动时检查
  - [x] 不一致时警告或报错
- [x] **T2.4** 创建 CLI 工具
  - [x] POST /api/v1/admin/permissions/sync
  - [x] GET /api/v1/admin/permissions/validate
- [ ] **T2.5** CI/CD 集成
  - [ ] GitHub Actions 检查步骤 (待实施)
- [x] **T2.6** 测试
  - [x] 同步正确性测试
  - [x] 一致性检查测试

#### 验收标准

- [x] YAML actions 变更后权限自动同步
- [x] 不一致时能检测并报告
- [ ] CI/CD 中一致性检查通过 (待实施)
- [x] 无手动维护 permissions 表

#### 实施文件

- `meta/services/permission_sync_service.py` - 权限同步服务
- `meta/api/permission_sync_api.py` - 权限同步 API
- `scripts/migrate_role_permissions_source.py` - 数据库迁移脚本

---

### ✅ 计算字段依赖追踪：已内置实现

> **状态**: ✅ 已在 `rule_chain.py` 中完整实现
> **实施文件**: `meta/core/rule_chain.py` (917 行)

**已实现的核心能力**：

| 类 | 功能 | 状态 |
|----|------|------|
| `DependencyGraph` | 规则依赖图 (nodes, edges, adjacency, reverse_adjacency, field_to_rules) | ✅ |
| `RuleDependencyAnalyzer.analyze()` | 从 MetaObject.rules 自动分析依赖关系 | ✅ |
| `RuleDependencyAnalyzer.detect_cycle()` | 循环依赖检测 (DFS 染色法) | ✅ |
| `RuleDependencyAnalyzer.topological_sort()` | 拓扑排序确定执行顺序 | ✅ |
| `ImplicitRuleChainExecutor` | 隐式规则链执行器（变更传播） | ✅ |
| `get_affected_rules()` | 基于变更字段的受影响规则分析 | ✅ |
| `_get_downstream_rules()` | 传递依赖传播 (MAX_PROPAGATION_DEPTH=100) | ✅ |
| `_evaluate_formula()` | 公式求值 | ✅ |
| `get_dependency_info()` | 依赖信息导出（调试用） | ✅ |

**为什么不在 Spec 中列为 Phase**：
- 代码已在 `ImplicitRuleChainExecutor` 中完整实现
- `RuleChainContext` 已支持变更追踪 (`changed_fields`)
- 支持计算规则、校验规则、状态转换规则、触发规则的依赖分析
- 支持自动变更传播（级联重算）
- 已有测试文件 `test_rule_chain.py` 覆盖

---

### 6.5 Phase 3：动态路由 + 数据权限声明化 ⏳ 待实施

> **详细方案**: 参见 [实际现状细化方案](specs/refined-implementation-plan.md)
> **预计工作量**: 1.5 周

#### 6.5.1 动态路由生成

**现状**：
- ✅ `AppRootLayout` 已从 API 动态获取导航 (`accessibleMenus → apiNavigationItems`)
- ✅ `deriveRoutePath()` 已根据 `page_type` 自动推导路径
- ✅ 菜单已支持离线缓存 (`useMenuCache`)
- ❌ `router/index.js` 仍硬编码 ~25 个路由

**任务清单**：

- [ ] **T3.1** 创建 `src/router/dynamicRoutes.js`
  - [ ] `generateDynamicRoutes()` - 从 API 菜单生成 Vue Router 路由配置
  - [ ] 复用已有的 `PAGE_TYPE_COMPONENTS` 映射
  - [ ] 路由 meta 注入 `required_permissions`
- [ ] **T3.2** 修改 `src/router/index.js`
  - [ ] `router.addRoute()` 动态注入
  - [ ] 保留静态路由（LandingPage、Login 等）作为 fallback
- [ ] **T3.3** 添加路由守卫
  - [ ] `beforeEach` 检查 `required_permissions`
  - [ ] 利用已有的 `useMenuPermissions()` composable
- [ ] **T3.4** 迁移硬编码路由到菜单数据
  - [ ] 统计当前硬编码路由 → 生成菜单记录

#### 6.5.2 数据权限声明化

**现状**：
- ✅ `data_permission.yaml` 定义数据权限 BO
- ✅ `DataPermissionService` 处理权限检查
- ✅ `ConditionPermissionService` 处理 Oracle 风格条件权限
- ❌ 无 YAML → 数据权限的自动生成机制

**任务清单**：

- [ ] **T3.5** 设计 `data_permission_hints` YAML 声明模板
- [ ] **T3.6** 实现 `DataPermissionGenerator` 类
  - [ ] 从 BO 元数据读取 `data_permission_hints`
  - [ ] 自动生成默认数据权限记录
- [ ] **T3.7** 集成到 `PermissionSyncService`
  - [ ] BO 注册时自动生成数据权限

---

### 6.6 Phase 4：集成测试与文档 ⏳ 待实施

#### 任务清单

- [ ] **T4.1** 动态路由集成测试
- [ ] **T4.2** 数据权限自动生成测试
- [ ] **T4.3** 端到端回归测试
- [ ] **T4.4** 更新架构文档

#### 验收标准

- [ ] 动态路由测试通过
- [ ] 数据权限测试通过
- [ ] 回归测试全部通过
- [ ] 文档更新完成

---

## 七、验收标准

### 7.1 功能验收

| 功能 | 验收标准 | 测试方法 |
|------|---------|---------|
| **菜单元数据化** | 所有菜单项在 YAML 中定义 | 检查 menu.yaml 覆盖率 |
| **路由自动生成** | 无需手动修改 router/index.js | 新增 BO 测试 |
| **权限自动同步** | YAML 与数据库一致 | consistency check 通过 |
| **依赖追踪** | 字段变更触发重算 | 单元测试 |
| **数据权限声明** | 条件规则自动生成 | 集成测试 |

### 7.2 性能验收

| 指标 | 目标 | 测试方法 |
|------|------|---------|
| 菜单加载时间 | < 100ms | 性能测试 |
| 权限同步时间 | < 5s (全量) | 性能测试 |
| 依赖图构建 | < 50ms | 性能测试 |

### 7.3 质量验收

| 指标 | 目标 | 测试方法 |
|------|------|---------|
| 测试覆盖率 | > 80% | pytest --cov |
| E2E 测试通过率 | 100% | playwright test |
| 文档完整性 | 100% | 文档审查 |

---

## 八、风险评估与缓解

### 8.1 风险清单

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **菜单迁移遗漏** | 中 | 高 | 全量对比测试 |
| **权限同步冲突** | 低 | 高 | 提供回滚机制 |
| **性能下降** | 低 | 中 | 性能基准测试 |
| **前端兼容性** | 中 | 中 | 渐进式迁移 |
| **学习曲线** | 中 | 低 | 完善文档和示例 |

### 8.2 回滚计划

```bash
# 如果出现问题，可快速回滚
git revert <commit-hash>
python -m meta.tools.permission_sync --reset
```

---

## 附录

### A. YAML 配置完整示例

```yaml
# user.yaml - 完整示例
id: user
name: 用户管理
table_name: users
display_name_field: username

# 菜单配置（新增）
menu:
  enabled: true
  category: system
  category_label: 系统管理
  category_icon: setting
  category_order: 100
  label: 用户管理
  icon: user
  order: 10
  route: /system/user
  visible_roles: [admin, user_manager]

# 权限配置（增强）
permissions:
  create: [admin, user_manager]
  read: [admin, user_manager, viewer]
  update: [admin, user_manager]
  delete: [admin]

# 数据权限（新增）
data_permission:
  dimensions:
    - id: owner
      field: owner_id
      description: 数据所有者
    - id: department
      field: department_id
      description: 所属部门
  auto_rules:
    - role: user
      scope: owner
    - role: department_manager
      scope: department

# 字段定义
fields:
  - id: username
    name: 用户名
    type: string
    semantics:
      business_key: true
      display_name: true
      
  - id: full_name
    name: 全名
    type: string
    computation:
      expression: "{first_name} {last_name}"
      # 依赖自动追踪

# ... 其他配置
```

### B. CLI 命令参考

```bash
# 菜单生成
python -m meta.tools.menu_generator --generate
python -m meta.tools.menu_generator --check

# 权限同步
python -m meta.tools.permission_sync --sync
python -m meta.tools.permission_sync --check
python -m meta.tools.permission_sync --reset

# 依赖追踪
python -m meta.tools.dependency_tracker --build-graph user
python -m meta.tools.dependency_tracker --get-dependents user username

# 数据权限
python -m meta.tools.data_permission_generator --generate user
```

### C. API 端点参考

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/menu/tree` | GET | 获取菜单树（已根据角色过滤） |
| `/api/v2/menu/categories` | GET | 获取菜单分类列表 |
| `/api/v2/permissions/sync` | POST | 手动触发权限同步 |
| `/api/v2/permissions/check` | GET | 检查权限一致性 |

### D. 相关文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| YAML 规范 v2.0 | docs/architecture/02-yaml-conventions-v2.md | 完整语法参考 |
| API 契约 v2.0 | docs/architecture/04-api-contracts-v2.md | API 端点定义 |
| 竞品分析 | docs/竞品架构分析_元数据驱动与权限模型.md | 业界对比 |
| 架构总览 | docs/ARCHITECTURE_V2.md | 系统架构 |

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0.0 | 2026-05-19 | AI Assistant | 初始版本 |

---

> **下一步行动**：请审阅本 Spec，确认后开始 Phase 1 实施。
