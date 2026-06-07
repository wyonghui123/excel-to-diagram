# 权限配置流程优化 — 维度驱动 vs 菜单驱动

> 日期：2026-05-16  
> 前置阅读：
> - [权限体系元数据驱动化_细化方案设计.md](./permission-metadata-driven-design.md)
> - [权限体系_单一事实源补充分析.md](./permission-ssot-analysis.md)
> - [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)

---

## 目录

1. [核心问题：权限配置的入口应该是什么](#1-核心问题)
2. [头部企业对比：三种配置流范式](#2-头部企业对比)
3. [当前流程：菜单为中心的配置流及其问题](#3-当前流程)
4. [目标流程：管理维度为入口的配置流](#4-目标流程)
5. [为什么维度优先更好](#5-为什么维度优先更好)
6. [细化设计方案](#6-细化设计方案)
7. [实施建议](#7-实施建议)

---

## 1. 核心问题 {#1-核心问题}

> **权限配置的入口应该是什么？**  
> A. 菜单（用户能看到哪些页面）  
> B. 管理维度/组织范围（用户在哪个组织范围内操作）

项目当前采用 A（菜单中心），但用户之前梳理的方案是 B（维度中心）。这不仅是 UI 交互顺序的差异，而是**权限模型的根本哲学差异**。

---

## 2. 头部企业对比：三种配置流范式 {#2-头部企业对比}

### 2.1 SAP — 组织级别为起点的授权模型

SAP 的权限配置遵循严格的组织优先原则：

```
┌──────────────────────────────────────────────────────────────┐
│  SAP 权限配置流（PFCG 事务码）                                  │
│                                                              │
│  Step 1: 定义组织级别 (Organizational Levels)                  │
│    ├── Company Code ($BUKRS)     ← 公司在哪个法人实体下操作     │
│    ├── Plant ($WERKS)            ← 在哪个工厂                   │
│    ├── Sales Organization        ← 在哪个销售组织               │
│    ├── Purchasing Organization   ← 在哪个采购组织               │
│    └── Controlling Area          ← 在哪个成本控制范围            │
│                                                              │
│  Step 2: 组合为授权对象 (Authorization Objects)                │
│    ├── F_BKPF_BUK: Activity(01/02/03) + Company Code          │
│    └── M_MSEG_WMB: Activity + Plant + Movement Type           │
│                                                              │
│  Step 3: 赋给角色 (Role → Profile)                             │
│    ├── 角色 =  授权对象的集合                                    │
│    └── 派生角色 = 同一角色 × 不同组织级别                         │
│        如：采购员_上海工厂、采购员_北京工厂                        │
│                                                              │
│  Step 4: 角色赋给用户                                          │
│    └── 用户登录后，系统运行时检查 Activity + Org Level           │
│                                                              │
│  核心原则："这个人在哪个组织范围内，能做什么操作"                    │
│  核心概念：组织级别字段是整个授权体系的第一前提                     │
└──────────────────────────────────────────────────────────────┘
```

**SAP 的关键设计**：
- **组织级别是全局共用定义**：Company Code、Plant 等定义一次，所有授权对象引用
- **派生角色**：同一个功能角色可以通过不同的组织级别值派生出多个角色变体
- **组织级别是授权的强制性维度**：没有指定公司代码，就不能执行任何财务操作

### 2.2 Salesforce — 角色层级为骨架的共享模型

```
┌──────────────────────────────────────────────────────────────┐
│  Salesforce 权限配置流                                         │
│                                                              │
│  Step 1: 角色层级 (Role Hierarchy)                             │
│    ├── CEO                                                    │
│    │   ├── VP Sales                                           │
│    │   │   ├── Sales Manager East                             │
│    │   │   └── Sales Manager West                             │
│    │   └── VP Service                                         │
│    └── 上级自动继承下级的数据访问权                              │
│                                                              │
│  Step 2: 组织范围默认值 (OWD)                                  │
│    └── 设置每个对象的基线访问级别：Private / Public Read / R/W   │
│                                                              │
│  Step 3: Profile / Permission Set (对象+字段权限)              │
│    ├── 控制对哪些 Object 有 CRUD 权限                          │
│    └── 控制对哪些 Field 可见/可编辑                             │
│                                                              │
│  Step 4: Sharing Rules / Territory (横向数据共享)              │
│    └── 跨角色层级的数据共享规则                                 │
│                                                              │
│  核心原则："这个人处于组织树的哪个位置"决定了数据可见范围          │
│  核心概念：Role Hierarchy 是权限的骨架，Profile 是血肉            │
└──────────────────────────────────────────────────────────────┘
```

**Salesforce 的关键设计**：
- **角色层级是第一公民**：每个用户必须有角色
- **数据访问是纵向+横向**：角色提供纵向继承，Sharing Rules 提供横向扩展
- **Territory Management**：独立于角色层级的第二个维度（地理/业务区域）

### 2.3 Power Platform / Dataverse — 业务单元为边界

```
┌──────────────────────────────────────────────────────────────┐
│  Power Platform 权限配置流                                     │
│                                                              │
│  Step 1: 业务单元 (Business Units)                             │
│    ├── Root BU (整个组织)                                      │
│    │   ├── 华东事业部                                           │
│    │   │   ├── 上海分公司                                       │
│    │   │   └── 杭州分公司                                       │
│    │   └── 华南事业部                                           │
│    └── 每个用户属于一个 BU                                     │
│                                                              │
│  Step 2: 安全角色 (Security Roles)                             │
│    ├── 定义对每个 Table 的权限级别                              │
│    │   ├── None / User / Business Unit / Parent:Child / Org   │
│    │   ├── Create / Read / Write / Delete / Append / ...      │
│    │   └── 这就是"维度 × 操作"的组合                            │
│    └── 角色赋给用户或团队                                      │
│                                                              │
│  Step 3: 团队 (Teams)                                        │
│    └── 跨 BU 的用户组，可拥有记录或共享访问                     │
│                                                              │
│  核心原则："用户属于哪个业务单元，对这个表有什么级别的访问"         │
│  核心概念：BU 是数据边界，角色定义边界内的操作能力                 │
└──────────────────────────────────────────────────────────────┘
```

### 2.4 三家对比总结

| 维度 | SAP | Salesforce | Power Platform | 我们当前 | 我们目标 |
|------|-----|-----------|----------------|---------|---------|
| **配置入口** | 🔴 组织级别 | 🔴 角色层级 | 🔴 业务单元 | 🟡 菜单 | 🔴 管理维度 |
| **功能权限** | 授权对象(Activity+Org) | Profile/Permission Set | Security Role | BO actions | BO actions |
| **数据权限** | 组织级别字段值 | Role Hierarchy + Sharing | BU + Access Level | permission_rules | data_permission_dimensions |
| **菜单** | 派生结果（T-code在角色内） | 派生结果（App Assignment） | 派生结果（Sitemap） | **配置入口** | 派生结果 |
| **核心哲学** | 组织范围决定一切 | 层级决定数据可见性 | 边界决定访问深度 | 页面入口驱动 | 维度驱动 |

**关键发现**：三巨头无一例外地将"组织/管理维度"作为权限配置的**第一入口**。菜单/T-code/App 只是角色配置的**结果**而非**起点**。

---

## 3. 当前流程：菜单为中心的配置流及其问题 {#3-当前流程}

### 3.1 当前配置流

```
管理员操作                          系统行为
─────────                         ────────
1. 选择一个角色                     
2. 进入 PermissionConfigPanel       
3. 勾选菜单（如"架构数据管理"）     → role_menu_permissions 表记录
                                    → 自动授予 required_permissions 
                                       （如 domain:read, sub_domain:read...）
4. 点开菜单卡片，查看关联的           → 显示已自动授予的功能权限列表
   功能权限（自动同步）
5. 可选：手动增减功能权限            → role_permissions 表记录
6. 切换到"数据权限"Tab              
7. 新建条件规则                     
   - 选择资源类型：domain            
   - 配置维度条件：                   
     domain_id IN (1,2)              
     AND version_id = 8              
   - 选择权限级别：read              
   - 配置继承/传播                   
                                    → permission_rules 表记录
8. 查看影响范围预览                  → ManagementDimensionEngine
                                       .calculate_impact()
```

### 3.2 问题分析

**问题1：配置流与业务逻辑反向**

```
业务逻辑：用户属于某个组织范围 → 在这个范围内有哪些职责 → 需要访问哪些数据 → 需要哪些页面

当前流程：管理员先选页面 → 再想"这个角色能看到哪些数据" → 再去配数据条件
         ↑ 这是反直觉的：
           业务上不会说"给这个人开'架构数据管理'页面的权限"
           而是说"给这个人'华东区领域架构师'的权限"
```

**问题2：菜单和BO权限的关系是声明式的但无感知**

```
当前：勾选"架构数据管理" → 系统自动授予 domain:read, sub_domain:read 等
     但这些权限的含义是什么？管理员看不到它们与菜单的关系说明

理想：角色定义为"product=X, version=Y, domain=Z → role=领域架构师"
      → 系统自动推导：能访问哪些菜单、哪些BO操作、哪些数据
```

**问题3：维度信息存在于两个独立层面，未统一**

```
permission_rules.condition:  "domain_id IN (1,2) AND version_id = 8"
menu_permissions:            仅关联功能权限，不关联维度

这两个层面是独立配置的：
- 菜单决定了"能看到什么页面"（通过 required_permissions）
- 条件规则决定了"能看到哪些数据"（通过 condition）

但它们本应是同一枚硬币的两面：
"领域架构师(domain=1,2, version=8)" → 既是菜单权限的依据，也是数据权限的依据
```

**问题4：当前项目中 ManagementDimension 已经被很好地建模了，但未成为配置入口**

```
当前：management_dimensions 表定义了维度
     ManagementDimensionEngine 计算影响范围
     ConditionRuleDialog 提供维度条件编辑

但：这些维度的作用仅限于 condition 表达式内部
    它们没有成为角色定义的第一级概念
    管理员配置时仍要"先选菜单，再配条件"
```

---

## 4. 目标流程：管理维度为入口的配置流 {#4-目标流程}

### 4.1 目标配置流

```
管理员操作                          系统行为
─────────                         ────────
1. 创建/选择一个角色               
                                   
2. 【新增】配置角色的管理维度范围     
   ┌─ 选择资源层级：                 
   │   □ product: 产品A             
   │   □ version: V3.0, V2.5        
   │   □ domain: 核心领域, 通用领域   
   │   □ sub_domain: ...            
   └─ 系统自动推导数据访问边界        
                                    → 存储为 role_dimension_scopes 表
                                    → 自动生成条件规则 condition
                                    → 自动推导可访问的菜单

3. 系统自动推荐菜单                  
   ┌─ 基于维度范围 + BO依赖关系       → 展示"推荐菜单"列表
   │  自动推导：                      （管理员可增减）
   │  · 领域管理（因为角色有 domain 维度）
   │  · 子领域管理（因为 domain 有下级） 
   │  · 架构数据管理（因为跨BO聚合）   
   │  · 架构图（如果有 AA diagram）
   └─                                

4. 系统自动推导功能权限              → 从菜单的 required_permissions
   （管理员可增减）                    从 BO 的 category_config
                                       自动生成 role_permissions

5. 系统自动推导数据权限              → 从维度范围 + BO 的
   （管理员可微调）                    data_permission_dimensions
                                       自动生成 permission_rules

6. 查看影响范围预览                  → 展示该角色能看到的
                                    全部数据范围和影响
```

### 4.2 核心变化：维度范围声明 → 一切自动推导

```yaml
# 角色定义新增字段
role:
  code: domain_architect_east
  name: 华东区领域架构师
  dimension_scopes:                 # ← 新增核心字段
    - dimension: version
      values: [3]                   # 版本3.0
    - dimension: domain
      values: [1, 2, 5]             # 核心领域、通用领域、华东领域
      inherit_children: true        # 自动包含子领域
    - dimension: product
      values: [1]                   # 产品A
  auto_derive_menu: true            # 自动推导菜单
  auto_derive_permissions: true     # 自动推导功能权限
  auto_derive_data_rules: true      # 自动推导数据规则
```

### 4.3 维度范围的自动推导链

```
role.dimension_scopes:
  version: [3]
  domain: [1, 2, 5] (inherit_children=true)
  product: [1]
          │
          ├──→ 数据权限自动推导
          │      condition: "version_id = 3 AND domain_id IN (1,2,5, 及下级子领域ID)"
          │      自动生成 permission_rules 记录
          │
          ├──→ 菜单自动推导
          │      遍历所有 menu_permissions 表中的 auto_generated=true 菜单
          │      筛选条件：菜单关联的 primary_object_type 或 object_types 
          │      所对应的数据表中有记录落在维度范围内
          │      → 推荐："领域管理"、"子领域管理"、"架构数据管理"、"架构图"
          │
          ├──→ 功能权限自动推导
          │      从推荐菜单的 required_permissions 提取
          │      + 从 BO category_config 提取
          │      → role_permissions: [domain:read, sub_domain:read, ...]
          │
          └──→ 字段级权限推导
                  根据 BO 的 data_permission_dimensions
                  决定哪些字段对所有维度范围内的记录可见/可编辑
```

---

## 5. 为什么维度优先更好 {#5-为什么维度优先更好}

### 5.1 五条理由

| # | 理由 | 说明 |
|---|------|------|
| 1 | **符合业务语言** | 业务方说"给小李华东区架构师的权限"，而不是"给小李开5个菜单" |
| 2 | **对齐行业最佳实践** | SAP/Salesforce/Power Platform 三巨头全部采用组织维度优先 |
| 3 | **减少配置步骤** | 当前需要：选菜单 → 调功能权限 → 配数据条件；目标：选维度范围 → 自动推导一切 |
| 4 | **消除菜单-数据权限不一致** | 当前可能出现"有菜单权限但无数据"或"有数据权限但看不到菜单"；维度驱动统一消除 |
| 5 | **天然支持派生角色** | 同一功能角色 × 不同维度范围 = 多个角色变体，极大减少角色定义数量 |

### 5.2 角色复用的质变

```
当前模式（菜单驱动）：
  华东架构师角色 = {菜单A, 菜单B, 菜单C} + {数据规则1}
  华南架构师角色 = {菜单A, 菜单B, 菜单C} + {数据规则2}
  
  问题：菜单集合完全相同，但因为是两套数据规则，需要两个角色

维度驱动模式：
  架构师角色 = {维度范围声明}  ← 只有这一个角色定义
  
  华东架构师 = 架构师角色 + version=3, domain=华东及下级
  华南架构师 = 架构师角色 + version=3, domain=华南及下级
  
  推导结果：
    华东架构师 → 菜单{领域管理, 子领域管理, ...} + 数据{domain IN 华东范围}
    华南架构师 → 菜单{领域管理, 子领域管理, ...} + 数据{domain IN 华南范围}
```

这与 SAP 的"派生角色（Derived Role）"概念完全对应——**一个功能角色模板 + 不同的组织级别值 = 多个运行时角色**。

### 5.3 数据权限的声明化升级

当前数据权限是**命令式**的（手动编写 `domain_id IN (1,2) AND version_id = 8`），维度驱动后变为**声明式**的：

```
当前（命令式）：
  管理员选 resource_type=domain
  → 选 dimension=domain, operator=IN, values=[1,2,5]
  → 选 dimension=version, operator= =, values=[8]
  → 系统拼出 condition 字符串

目标（声明式）：
  管理员只需声明 role.dimension_scopes:
    version: [8]
    domain: [1, 2, 5]
  → 系统自动：
    · 生成 condition 字符串
    · 处理 inherit_children（自动扩展子域ID）
    · 生成所有 resource_type 的条件规则
    · 关联到菜单和功能权限
```

---

## 6. 细化设计方案 {#6-细化设计方案}

### 6.1 新增 role_dimension_scopes 表

```yaml
# meta/schemas/role_dimension_scope.yaml
id: role_dimension_scope
name: 角色维度范围
table_name: role_dimension_scopes
description: 角色的管理维度范围声明，是权限推导的入口

fields:
  - id: id
    name: ID
    type: integer
    required: true
    unique: true

  - id: role_id
    name: 角色ID
    type: integer
    required: true

  - id: dimension_code
    name: 维度编码
    type: string
    required: true
    description: 对应 management_dimensions.code

  - id: dimension_values
    name: 维度值列表
    type: json
    required: true
    description: 如 [1, 2, 5]

  - id: inherit_children
    name: 包含下级
    type: boolean
    default: true
    description: 是否自动包含该维度值的所有子级（如选domain自动含sub_domain）

  - id: scope_mode
    name: 范围模式
    type: string
    default: include
    enum_values:
      - include
      - exclude
    description: include=包含这些值，exclude=排除这些值（黑名单）
```

### 6.2 维度范围引擎

新建 `meta/services/dimension_scope_engine.py`：

```python
# -*- coding: utf-8 -*-
"""
维度范围引擎

从角色的维度范围声明自动推导：
1. 数据权限条件规则
2. 推荐菜单
3. 功能权限
"""

from typing import Dict, List, Set
from meta.core.models import registry


class DimensionScopeEngine:
    """维度范围推导引擎
    
    职责：将角色声明的维度范围展开为具体的数据条件、菜单、权限
    """

    def __init__(self, data_source):
        self._ds = data_source

    def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
        """展开维度值（处理 inherit_children 等）
        
        Returns: { dimension_code: {all_effective_ids} }
        """
        scopes = self._load_role_scopes(role_id)
        expanded = {}
        
        for scope in scopes:
            code = scope['dimension_code']
            values = set(scope['dimension_values'])
            
            if scope.get('inherit_children'):
                children = self._get_all_child_ids(code, values)
                values.update(children)
            
            if code not in expanded:
                expanded[code] = set()
            expanded[code].update(values)
        
        return expanded

    def derive_data_conditions(self, role_id: int) -> Dict[str, str]:
        """从维度范围推导数据条件
        
        Returns: { resource_type: condition_string }
        """
        expanded = self.expand_dimension_values(role_id)
        dim_meta = self._load_dimension_metadata()
        
        conditions = {}
        for resource_type in self._get_all_resource_types():
            parts = []
            for dim_code, values in expanded.items():
                dim = dim_meta.get(dim_code)
                if not dim:
                    continue
                
                # 检查该维度是否适用于此 resource_type
                applicable_types = dim.get('resource_types', [])
                if resource_type not in applicable_types:
                    continue
                
                field = dim['field']
                if len(values) == 1:
                    parts.append(f"{field} = {list(values)[0]}")
                else:
                    ids_str = ','.join(str(v) for v in sorted(values))
                    parts.append(f"{field} IN ({ids_str})")
            
            if parts:
                conditions[resource_type] = ' AND '.join(parts)
        
        return conditions

    def derive_recommended_menus(self, role_id: int) -> List[str]:
        """从维度范围推导推荐菜单
        
        逻辑：菜单关联的 BO 如果在维度范围内有数据，则推荐
        """
        expanded = self.expand_dimension_values(role_id)
        
        # 获取所有 auto_generated 菜单
        menus = self._ds.execute(
            "SELECT menu_code, primary_object_type, object_types "
            "FROM menu_permissions WHERE auto_generated = 1 AND is_active = 1"
        ).fetchall()
        
        recommended = []
        for menu in menus:
            object_types = menu['object_types'] or [menu['primary_object_type']]
            if self._menu_has_data_in_scope(object_types, expanded):
                recommended.append(menu['menu_code'])
        
        return recommended

    def derive_permissions(self, role_id: int) -> List[str]:
        """从推荐菜单推导功能权限"""
        menus = self.derive_recommended_menus(role_id)
        all_perms = set()
        
        for menu_code in menus:
            menu = self._ds.execute(
                "SELECT required_permissions FROM menu_permissions WHERE menu_code = ?",
                [menu_code]
            ).fetchone()
            if menu and menu['required_permissions']:
                import json
                perms = json.loads(menu['required_permissions'])
                all_perms.update(perms)
        
        return list(all_perms)

    def auto_sync_all(self, role_id: int) -> Dict:
        """一键同步：维度范围 → 菜单 + 权限 + 数据规则"""
        expanded = self.expand_dimension_values(role_id)
        menus = self.derive_recommended_menus(role_id)
        permissions = self.derive_permissions(role_id)
        conditions = self.derive_data_conditions(role_id)
        
        return {
            'dimension_scopes': {k: list(v) for k, v in expanded.items()},
            'recommended_menus': menus,
            'derived_permissions': permissions,
            'data_conditions': conditions,
        }

    def _get_all_child_ids(self, dimension_code: str, parent_ids: Set[int]) -> Set[int]:
        """递归获取所有子级 ID"""
        # 使用 hierarchies.yaml 中定义的 parent-child 关系
        # product → version → domain → sub_domain → service_module → business_object
        hierarchy_chain = ['product', 'version', 'domain', 'sub_domain', 
                          'service_module', 'business_object']
        
        if dimension_code not in hierarchy_chain:
            return set()
        
        idx = hierarchy_chain.index(dimension_code)
        child_ids = set()
        current_ids = parent_ids
        
        for child_dim in hierarchy_chain[idx+1:]:
            dim_meta = self._load_dimension_metadata().get(child_dim)
            if not dim_meta:
                break
            parent_field = dim_meta.get('cascade_parent_field')
            child_table = dim_meta.get('relation_object')
            
            if parent_field and child_table:
                placeholders = ','.join('?' * len(current_ids))
                rows = self._ds.execute(
                    f"SELECT id FROM {child_table} WHERE {parent_field} IN ({placeholders})",
                    list(current_ids)
                ).fetchall()
                current_ids = {row['id'] for row in rows}
                child_ids.update(current_ids)
        
        return child_ids

    def _load_role_scopes(self, role_id: int) -> List[Dict]:
        return self._ds.execute(
            "SELECT * FROM role_dimension_scopes WHERE role_id = ?",
            [role_id]
        ).fetchall()

    def _load_dimension_metadata(self) -> Dict[str, Dict]:
        rows = self._ds.execute(
            "SELECT code, field, relation_object, cascade_parent, resource_types "
            "FROM management_dimensions WHERE is_active = 1"
        ).fetchall()
        result = {}
        for row in rows:
            result[row['code']] = {
                'field': row['field'],
                'relation_object': row['relation_object'],
                'cascade_parent_field': row['cascade_parent'],
                'resource_types': json.loads(row['resource_types'] or '[]'),
            }
        return result

    def _get_all_resource_types(self) -> List[str]:
        """获取所有已注册的 BO resource_type"""
        return [obj_id for obj_id in registry.get_all() if not obj_id.startswith('_')]

    def _menu_has_data_in_scope(self, object_types: List[str], 
                                 expanded: Dict[str, Set[int]]) -> bool:
        """检查菜单关联的 BO 在维度范围内是否有数据"""
        for ot in object_types:
            meta_obj = registry.get(ot)
            if not meta_obj:
                continue
            
            # 构建 WHERE 条件检查是否有数据
            parts = []
            params = []
            for dim_code, values in expanded.items():
                dim_meta = self._load_dimension_metadata().get(dim_code)
                if not dim_meta:
                    continue
                field = dim_meta['field']
                placeholders = ','.join('?' * len(values))
                parts.append(f"{field} IN ({placeholders})")
                params.extend(values)
            
            if not parts:
                return True  # 无维度限制，肯定是推荐的
            
            where = ' AND '.join(parts)
            row = self._ds.execute(
                f"SELECT COUNT(*) as cnt FROM {meta_obj.table_name} WHERE {where}",
                params
            ).fetchone()
            
            if row and row['cnt'] > 0:
                return True
        
        return False


# 全局实例
dimension_scope_engine = None
```

### 6.3 前端：DimensionScopePanel 组件

在 `RolePermissionCenter.vue` 中新增维度范围配置面板，替代当前从菜单开始的配置流程：

```
┌─────────────────────────────────────────────────────────┐
│  角色权限配置                                             │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Step 1: 管理维度范围  [当前步骤]                  │    │
│  │                                                    │    │
│  │  产品: [产品A ▾]                                   │    │
│  │  版本: [V3.0 ✕] [V2.5 ✕]                         │    │
│  │  领域: [核心领域 ✕] [通用领域 ✕] [华东领域 ✕]      │    │
│  │  ☑ 包含下级领域和子领域                             │    │
│  │                                                    │    │
│  │  数据访问预览：                                     │    │
│  │  · 领域: 3个 + 下级15个子领域                       │    │
│  │  · 服务模块: 预估 47 个                             │    │
│  │  · 业务对象: 预估 200+ 个                           │    │
│  │                                                    │    │
│  │  [自动推导菜单和权限]                                │    │
│  └─────────────────────────────────────────────────┘    │
│                         ↓ 自动推导                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Step 2: 菜单权限（自动推导，可调整）               │    │
│  │                                                    │    │
│  │  ☑ 领域管理           (关联: domain:read/write)     │    │
│  │  ☑ 子领域管理         (关联: sub_domain:read)       │    │
│  │  ☑ 架构数据管理       (关联: 多BO聚合)              │    │
│  │  ☐ 产品管理           (关联: product:read)          │    │
│  │  ☐ 架构图            (关联: diagram:generate)       │    │
│  │                                                    │    │
│  │  推导依据：维度范围内存在对应BO的数据                 │    │
│  └─────────────────────────────────────────────────┘    │
│                         ↓                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Step 3: 功能权限详情（自动推导）                   │    │
│  │                                                    │    │
│  │  domain:read       ✓  来自"领域管理"菜单            │    │
│  │  domain:update     ✓  来自"领域管理"菜单            │    │
│  │  sub_domain:read   ✓  来自"子领域管理"菜单          │    │
│  │  ...更多                                           │    │
│  └─────────────────────────────────────────────────┘    │
│                         ↓                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Step 4: 数据权限规则（自动生成）                   │    │
│  │                                                    │    │
│  │  资源: domain                                      │    │
│  │  条件: domain_id IN (1,2,5, 子领域关联ID...)       │    │
│  │  级别: read                                        │    │
│  │  继承: ☑ 向下传播                                  │    │
│  │                                                    │    │
│  │  资源: service_module                              │    │
│  │  条件: (推导自 domain → sub_domain → service_module)│    │
│  │  级别: read                                        │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 6.4 与现有体系的兼容

维度驱动是**增强**而不是**替换**：

```
                    角色配置入口
                   /            \
          【维度驱动模式】    【菜单驱动模式】(当前，保留)
          快速标准配置         精细手动配置
              │                    │
              └────────┬───────────┘
                       │
                  role_permissions
                  role_menu_permissions
                  permission_rules
                       │
                       ▼
                 用户有效权限
```

两种模式写入同一套底层表，可以混合使用。维度驱动是一个"快速配置层"，菜单驱动作为"精细调整层"。

---

## 7. 实施建议 {#7-实施建议}

### 7.1 与之前细化方案的整合

维度驱动方案与之前5个方案的关系：

| 之前的方案 | 整合方式 |
|-----------|---------|
| 方案1：Menu BO 元数据化 | Menu 仍然是 BO，但菜单推荐由维度引擎驱动 |
| 方案2：权限自动同步 | 从维度范围推导的菜单自动触发权限同步 |
| 方案3：数据权限声明化 | data_permission_dimensions 与 dimension_scopes 融合 |
| 方案4：前端菜单驱动 | 菜单由维度引擎的推荐结果决定 |
| 方案5：字段级权限 | 作为维度驱动的次级精细化控制 |

### 7.2 新增实施阶段

在现有三阶段基础上增加 Phase 0：

| 阶段 | 周期 | 任务 |
|------|------|------|
| **Phase 0** | Week 1-2 | role_dimension_scopes 表 + DimensionScopeEngine + 维度面板 |
| Phase 1 | Week 3-4 | 原有 Phase 1（Menu BO 元数据化 + 权限自动同步） |
| Phase 2 | Week 5-6 | 原有 Phase 2（前端统一） |
| Phase 3 | Week 7-8 | 原有 Phase 3（增强能力） |

### 7.3 关键风险

| 风险 | 缓解 |
|------|------|
| 维度驱动可能不完全覆盖特殊权限需求 | 保留菜单驱动作为后备，两种模式共存 |
| inherit_children 递归性能 | 使用 hierarchy 缓存（已有 hierarchies.yaml 定义） |
| 角色迁移：现有角色的维度范围如何初始化 | 提供从现有 permission_rules 反向提取维度范围的工具 |

---

## 总结

本次深入分析的核心结论：

1. **配置入口从"菜单"改为"管理维度范围"**，这在 SAP、Salesforce、Power Platform 三巨头中无一例外是标准做法
2. **维度范围声明 → 自动推导菜单+权限+数据规则**，将配置从"手动组合"变为"声明式推导"
3. **与现有体系的整合是增强而非替换**，维度驱动作为快速配置入口，菜单驱动作为精细调整入口
4. **真正实现了权限体系的全链路元数据驱动**：YAML Schema → BO 定义 → 维度声明 → 自动推导一切
5. **天然支持派生角色**（SAP 风格的同一功能角色 × 不同组织范围），极大减少角色定义数量
