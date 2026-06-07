# 元数据驱动权限体系 -- 细化方案设计


## 目录

1. [总体设计目标与架构蓝图](#1-总体设计目标与架构蓝图)
2. [方案1：Menu BO 元数据化 -- 菜单纳入元数据模型闭环](#2-方案1)
3. [方案2：Permissions 从 BO Actions 自动同步](#3-方案2)
4. [方案3：BO 字段级数据权限声明化 -- data_permission_dimensions](#4-方案3)
5. [方案4：字段级读写权限控制 -- 参考 Mendix 实体访问规则](#5-方案4)
6. [方案5：多租户架构设计](#6-方案5)
7. [实施路线图](#7-实施路线图)

---

## 1. 总体设计目标与架构蓝图

### 1.1 当前断裂点

```
YAML Schema（元数据定义）
    ↑
    | ⚠️ 断裂：actions 未自动同步到 permissions 表
    | ⚠️ 断裂：菜单配置与 BO 对象无自动关联
    | ⚠️ 断裂：category_config 数据未被权限检查消费
    |
permissions 表  ← 手工 init_auth.py 维护
menu_permissions 表 ← 手工 init_menu_permissions.py 维护
前端 menuConfig.js ← 独立维护
前端 useMenuPermissions.js ← 独立映射
```

### 1.2 目标架构蓝图

```
                        ┌─────────────────────────────┐
                        │    YAML Schema（唯一真实源）    │
                        │  ├── fields                  │
                        │  ├── actions                 │
                        │  ├── ui_view_config           │
                        │  ├── category_config          │
                        │  ├── data_permission_dimensions│
                        │  └── field_permissions        │
                        └──────────────┬──────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ↓                  ↓                  ↓
        ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
        │ 权限自动同步引擎 │ │ 菜单自动生成引擎 │ │ 字段权限推导引擎 │
        │                 │ │                 │ │                 │
        │ actions →       │ │ BO + config →   │ │ fields +        │
        │ permissions 表  │ │ menu_permissions│ │ permissions →   │
        │                 │ │ 前端菜单结构     │ │ 读写控制        │
        └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
                 ↓                   ↓                   ↓
          ┌──────────────────────────────────────────────────┐
          │              运行时权限检查层                      │
          │  ├── 菜单可见性 (基于 menu_permissions)             │
          │  ├── 功能权限 (基于 permissions + role_permissions)│
          │  ├── 数据权限 (基于 permission_rules + dimensions) │
          │  └── 字段权限 (基于 field_permissions)             │
          └──────────────────────────────────────────────────┘
```

### 1.3 总体原则

1. **YAML 是唯一真实源**：所有权限配置只能从 YAML 推导，禁止重复维护
2. **自动同步优先**：系统启动/热重载时自动同步，无需手工脚本
3. **向后兼容**：不影响现有 API 和前端功能
4. **渐进式演进**：按方案顺序分步实施，每步可独立验证

---

## 2. 方案1：Menu BO 元数据化

### 2.1 核心思路

将菜单本身定义为 BO，使其成为元数据模型的一部分：**menu BO 就是"菜单的 BO"**。

这样菜单的创建、修改、权限分配都可以通过 BO Framework 的标准 CRUD 和权限机制来管理，而不是依赖手工 SQL 脚本。

### 2.2 新增 YAML Schema：`menu.yaml`

```yaml
# meta/schemas/menu.yaml
id: menu
name: 菜单
table_name: menus
description: 系统菜单配置，元数据驱动生成
bo_category: configuration

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
    semantics:
      display_name: true

  - id: menu_path
    name: 菜单路径
    type: string
    description: 前端路由路径

  # ── 关键字段：页面组件类型 ──
  - id: page_type
    name: 页面类型
    type: string
    enum_values:
      - value: object_list
        label: 单对象列表页
      - value: object_detail
        label: 单对象详情页
      - value: multi_object_hub
        label: 多对象聚合页
      - value: custom_page
        label: 自定义页面
      - value: parent_menu
        label: 父级菜单（无页面）

  # ── 关键字段：关联的业务对象 ──
  - id: object_types
    name: 关联业务对象
    type: json
    description: |
      关联的 BO 对象 ID 列表。
      - 单对象列表页：1个对象
      - 多对象聚合页：多个对象
      - 自定义页面：空数组
    default: []

  # ── 关键字段：页面配置 ──
  - id: page_config
    name: 页面配置
    type: json
    description: |
      额外的页面配置，从 BO 的 ui_view_config 继承后可由菜单级别覆盖。
      {
        "default_filters": {...},
        "default_sort": {...},
        "page_size": 20,
        "show_create_button": true,
        "show_export_button": true
      }

  # ── 关键字段：是否自动从 BO 推导权限 ──
  - id: auto_permissions
    name: 自动推导