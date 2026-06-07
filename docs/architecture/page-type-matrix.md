# page_type 决策矩阵

> 单一事实源原则：本文档交叉引用两个代码权威来源，不重复定义。
> - 组件映射：[src/router/dynamicRoutes.js](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js) `PAGE_TYPE_COMPONENTS`
> - 路由模板：[src/utils/routeTemplate.js](file:///d:/filework/excel-to-diagram/src/utils/routeTemplate.js) `DEFAULT_TEMPLATES`
> - Schema 定义：[meta/schemas/menu.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/menu.yaml) `page_type` 字段

---

## 1. page_type 一览

| page_type | 自动注册 | 渲染组件 | 路由路径 | 关键字段 |
|---|---|---|---|---|
| `object_list` | ✅ | GenericObjectList | `/{primary_object_type}` | `primary_object_type`（必填） |
| `object_detail` | ✅ | ObjectDetailPage | `/{primary_object_type}/:id` | `primary_object_type`（必填） |
| `multi_object_hub` | ✅ | GenericTabContainer | `/{menu_code}` | `object_types`（推荐） |
| `custom_page` | ❌ 需静态路由 | — | `/{menu_path}` | `menu_path`（必填） |
| `dashboard` | ❌ 暂未实现 | — | `/{menu_code}` | — |

---

## 2. 决策树

```
需要展示的对象数量？
├── 1 个 BO
│   ├── 列表视图 → object_list
│   └── 详情视图 → object_detail
│
├── 多个 BO（同属一个业务域）
│   └── multi_object_hub
│       ├── Tab 按 objectType 切换 GenericObjectList
│       └── Tab 来源：API children（菜单层级）→ fallback tabGroupConfigs（静态配置）
│
└── 完全自定义页面（图表、仪表盘、非 CRUD 页面）
    └── custom_page
        └── 在 router/index.js 中注册静态路由
            ├── STATIC_ROUTE_NAMES 中添加 name
            └── STATIC_ROUTE_PATHS 中添加 path 前缀
```

---

## 3. 自动注册流程（object_list / object_detail / multi_object_hub）

```
菜单API → accessibleMenus
    ↓
dynamicRoutes.js: _resolveComponent(menu)
    ├── PAGE_TYPE_COMPONENTS[page_type] 命中 → 返回组件
    ├── page_type=custom_page → console.warn + return null（不注册）
    └── 未知类型 → console.warn + fallback 到 object_list
    ↓
_registerRoute(router, menu)
    ├── component=null → return false
    └── router.addRoute({ path, component, props })
```

---

## 4. multi_object_hub 的 Tab 发现机制

GenericTabContainer 按优先级查找 Tab：

| 优先级 | 数据来源 | 条件 |
|---|---|---|
| 1（API 优先） | `accessibleMenus` 中 `menu_code === group` 的 `children` | children 非空 |
| 2（静态 fallback） | `menuConfig.js` `tabGroupConfigs[group]` | API children 为空 |

**菜单层级与页面内容解耦**：

```
parent_menu → 决定侧边栏展开/收纳层级（导航树）
    ↕ 无直接关系
page_type + page_config → 决定页面内容（渲染组件 + 数据来源）
```

---

## 5. custom_page 静态路由注册示例

```javascript
// router/index.js
import TaskDashboard from '@/views/TaskDashboard.vue'

const routes = [
  {
    path: '/system/task-management',
    name: 'task-management',
    component: TaskDashboard,
    meta: { title: '任务调度', requiresAuth: true },
  },
]

// 同时在 STATIC_ROUTE_NAMES 和 STATIC_ROUTE_PATHS 中注册，
// 防止 dynamicRoutes.js 重复注册
```

---

## 6. page_config 结构（按 page_type）

### object_list

```json
{
  "columns": ["column_name_1", "column_name_2"],
  "defaultFilters": { "status": "active" },
  "pageSize": 20
}
```

### multi_object_hub

```json
{}
```

Tab 配置由 `tabGroupConfigs` 或 API children 决定，不在 `page_config` 中定义。

### custom_page

由各组件自行定义和使用，无统一 Schema。

---

## 7. 与 menu.yaml Schema 的关系

- `menu.yaml` 定义字段结构和有效枚举值
- `dynamicRoutes.js` `PAGE_TYPE_COMPONENTS` 定义运行时组件映射（单一事实源）
- `routeTemplate.js` `DEFAULT_TEMPLATES` 定义路由路径生成规则（单一事实源）
- 本文档是**人类可读的交叉引用索引**，不引入新的定义