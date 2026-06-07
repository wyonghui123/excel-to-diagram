# 父子页面路由设计

## 路由约定

父子页面路由遵循以下约定：

```
/{parentObjectType}                    → 父对象列表页
/{parentObjectType}/:id                → 父对象详情页
/{parentObjectType}/:id/{childObjectType}    → 子对象列表页（独立页面）
/product                               → 产品列表页
/product/:id                            → 产品详情页（包含版本列表 Section）
/product/:id/version/:versionId         → 版本详情页
```

## 路由配置示例

### 路由定义（Vue Router）

```javascript
// router/index.js
const routes = [
  // 产品管理
  {
    path: '/product-management',
    name: 'ProductManagement',
    component: () => import('@/views/ProductManagement/ProductListPage.vue'),
    meta: { title: '产品管理' }
  },

  // 产品详情页（包含版本列表）
  {
    path: '/product/:id',
    name: 'ProductDetail',
    component: () => import('@/views/ProductManagement/ProductDetailPage.vue'),
    meta: { title: '产品详情' },
    props: true
  },

  // 枚举管理
  {
    path: '/enum-type/:id',
    name: 'EnumTypeDetail',
    component: () => import('@/views/SystemManagement/EnumTypeDetailV2.vue'),
    meta: { title: '枚举类型详情' },
    props: true
  }
]
```

## 父子页面的 URL 结构

### 模式 A：详情页嵌入子列表（推荐）

```
URL: /product/123
页面: 产品详情页
       ├── 基本信息 Section
       ├── 版本列表 Section（嵌入）
       │     ├── 新增版本按钮
       │     ├── 版本表格
       │     └── 分页
       └── 变更历史 Section
```

**优点**：
- 上下文连续，用户始终在产品详情页
- 适合强归属关系（产品-版本）
- 导航简单

**适用场景**：
- Product ↔ Version
- EnumType ↔ EnumValue

### 模式 B：独立子列表页

```
URL: /product/123/versions
页面: 产品版本管理页
       ├── 产品信息头部
       ├── 版本列表（独立表格）
       └── 返回产品详情按钮
```

**优点**：
- 子列表有独立 URL，可书签分享
- 适合数据量大的场景
- 支持浏览器前进/后退

**适用场景**：
- 需要单独分享版本列表链接
- 版本数量很大（>100）

## 页面跳转示例

### 从产品列表进入产品详情

```javascript
// ProductListPage.vue
function goToProductDetail(product) {
  router.push(`/product/${product.id}`)
}
```

### 从产品详情进入版本详情

```javascript
// ProductDetailPage.vue (ObjectChildSection)
function handleRowClick(row) {
  router.push(`/product/${productId}/version/${row.id}`)
}
```

### 从版本详情返回产品详情

```javascript
// VersionDetailPage.vue
function handleBack() {
  router.push(`/product/${productId}`)
}
```

## MetaListPage 行操作配置

在 YAML 中配置行操作按钮：

```yaml
# product.yaml
ui_view_config:
  list:
    actions:
      - id: manage_versions
        label: 管理版本
        icon: list
        type: primary
        position: row
        container: page          # 页面级跳转
        target: product-detail   # 目标页面标识
        params:
          id: '{id}'             # 传递产品ID
```

或者直接配置路由路径：

```yaml
actions:
  - id: manage_versions
    label: 管理版本
    type: primary
    navigate_to: '/product/{id}'
```

## 面包屑导航

父子页面的面包屑导航示例：

```
产品详情页：
‹ 返回  系统管理  ›  产品管理  ›  供应链系统
                                    ↑
                                  当前页

版本详情页：
‹ 返回  系统管理  ›  产品管理  ›  供应链系统  ›  版本详情
                                                              ↑
                                                            当前页
```

## 路由守卫

建议添加路由守卫来验证父对象是否存在：

```javascript
router.beforeEach(async (to, from, next) => {
  if (to.params.id) {
    const objectType = to.meta?.objectType || extractObjectType(to.path)
    const result = await boService.read(objectType, to.params.id)
    
    if (!result.success) {
      ElMessage.error('对象不存在或已被删除')
      return next('/product-management')
    }
  }
  next()
})
```

## 深度嵌套示例

对于 Domain → SubDomain → ServiceModule → BusinessObject 四级关系：

```
URL: /domain/:domainId
页面: DomainDetailPage
       ├── 基本信息
       ├── SubDomain 列表 Section
       │     └── 点击进入 SubDomain 详情
       │           ├── 基本信息
       │           ├── ServiceModule 列表 Section
       │           │     └── 点击进入 ServiceModule 详情
       │           │           ├── 基本信息
       │           │           └── BusinessObject 列表 Section
```

### 路由定义

```javascript
const routes = [
  { path: '/domain/:id', component: DomainDetailPage },
  { path: '/domain/:domainId/sub-domain/:id', component: SubDomainDetailPage },
  { path: '/domain/:domainId/sub-domain/:subDomainId/service-module/:id', component: ServiceModuleDetailPage },
  { path: '/domain/:domainId/sub-domain/:subDomainId/service-module/:serviceModuleId/business-object/:id', component: BusinessObjectDetailPage }
]
```

## 总结

| 模式 | URL | 适用场景 | 优点 | 缺点 |
|------|-----|----------|------|------|
| A. 内嵌子列表 | `/product/:id` | 强归属关系，数据量小 | 上下文连续 | URL 不包含子对象信息 |
| B. 独立子列表 | `/product/:id/versions` | 数据量大，需分享链接 | URL 可书签 | 上下文切换 |
| C. 深度嵌套 | `/domain/:d/sub/:s/sm/:m` | 多层级结构 | 路径清晰 | URL 较长 |

**推荐**：大多数场景使用模式 A（内嵌子列表），只在必要时使用模式 B 或 C。
