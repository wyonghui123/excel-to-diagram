# Phase 18.2: 顶层对象迁移 — Product & Version Management v2

> **状态**: ✅ 已完成
> **依赖**: M18.1 ✅ (YAML Schema + BOF 核心能力)
> **完成日期**: 2025-01-09
> **预估工时**: 1 天
> **实际工时**: 0.5 天

---

## 1. 背景与目标

### 1.1 问题描述

ProductManagement.vue 和 VersionManagement.vue 当前使用旧的 `/api/v1/manage/*` API，需要迁移到新的 v2 API 架构。

### 1.2 迁移目标

| 对象 | 迁移前 | 迁移后 | 状态 |
|------|--------|--------|------|
| product | MetaListPage + 旧 API | ✅ v2 API | ✅ 完成 |
| version | MetaListPage + 旧 API | ✅ v2 API + product_id 过滤 | ✅ 完成 |

### 1.3 迁移收益

- ✅ ProductManagement.vue 已使用 v2 API
- ✅ VersionManagement.vue 已增加 product_id 过滤
- ✅ 统一的 API 架构，便于后续维护

---

## 2. 实现状态

### 2.1 已完成

| 任务 | 文件 | 状态 | 验证日期 |
|------|------|------|----------|
| useVersionContext.js | `src/composables/useVersionContext.js` | ✅ | 2025-01-09 |
| VersionContextSelector.vue | `src/components/VersionContextSelector/` | ✅ | 2025-01-09 |
| ProductManagement v2 API | ProductManagement.vue | ✅ | 2025-01-09 |
| VersionManagement v2 API | VersionManagement.vue | ✅ | 2025-01-09 |
| VersionManagement product_id 过滤 | VersionManagement.vue | ✅ | 2025-01-09 |

### 2.2 API 验证结果

| API | 方法 | 状态 | 响应 |
|-----|------|------|------|
| `/api/v2/bo/product` | GET | ✅ | 返回 5 个产品 |
| `/api/v2/bo/version` | GET | ✅ | 返回 11 个版本 |
| `/api/v2/bo/version?product_id=1` | GET | ✅ | 返回 1 个版本（过滤正常） |
| `/api/v2/meta/product/schema` | GET | ✅ | Schema 包含 11 个字段 |
| `/api/v2/meta/version/schema` | GET | ✅ | Schema 包含 14 个字段 + hierarchy 配置 |
| `/api/v1/menu-permission/menus` | GET | ✅ | productversion 菜单可见 |

---

## 3. 技术细节

### 3.1 API 映射

| 操作 | 旧 API | 新 API | 状态 |
|------|--------|--------|------|
| 产品列表 | GET /api/v1/manage/products | GET /api/v2/bo/product | ✅ |
| 版本列表 | GET /api/v1/manage/versions | GET /api/v2/bo/version | ✅ |
| 创建产品 | POST /api/v1/manage/products | POST /api/v2/bo/product | ✅ |
| 创建版本 | POST /api/v1/manage/versions | POST /api/v2/bo/version | ✅ |
| 更新产品 | PUT /api/v1/manage/products/{id} | PUT /api/v2/bo/product/{id} | ✅ |
| 更新版本 | PUT /api/v1/manage/versions/{id} | PUT /api/v2/bo/version/{id} | ✅ |
| 删除产品 | DELETE /api/v1/manage/products/{id} | DELETE /api/v2/bo/product/{id} | ✅ |
| 删除版本 | DELETE /api/v1/manage/versions/{id} | DELETE /api/v2/bo/version/{id} | ✅ |

### 3.2 数据格式

**v2 API 响应格式**:
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "pageSize": 20
  }
}
```

### 3.3 VersionManagement 的 product_id 过滤

```javascript
// 通过 VersionContextSelector 选择产品后，自动注入 product_id 过滤
const contextFilters = computed(() => ({
  product_id: selectedProductId.value
}))
```

---

## 4. 权限配置

### 4.1 菜单权限

| 菜单 | 所需权限 | 状态 |
|------|---------|------|
| productversion | product:read, version:read | ✅ 已配置 |

### 4.2 数据库变更

```sql
-- 添加权限
INSERT INTO permissions (code, name, resource_type, action) VALUES
  ('product:read', '产品查看', 'product', 'read'),
  ('version:read', '版本查看', 'version', 'read');

-- 分配给 admin 角色
INSERT INTO role_permissions (role_id, permission_id) VALUES
  (1, <product:read_id>),
  (1, <version:read_id>);
```

---

## 5. 后续计划

| 里程碑 | 内容 | 依赖 |
|---------|------|------|
| M18.3 | 级联下拉 cascade_select | M18.1 ✅ |
| M18.4 | ObjectTreePanel 树形导航 | M18.2 ✅ + YAML hierarchies |

---

## 6. 变更记录

| 日期 | 变更内容 | 操作人 |
|------|---------|--------|
| 2025-01-09 | 初始创建 | AI |
| 2025-01-09 | M18.2 完成，useVersionContext + ContextSelector 已创建 | AI |
| 2025-01-09 | API 验证通过，Phase 18.2 标记为完成 | AI |
