# DEFER 4 项深入分析 (2026-06-14)

## 1) E34 (i18n locale 切换 UI) - 🟡 中等

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **后端** | ✅ 已支持 | `user_api.py:412` `preference_fields = ['locale', 'timezone', 'date_style', 'time_style', 'hour_cycle']` |
| **数据库** | ✅ 已存 | `users` 表有 `locale` 列 (UPDATE SQL 验证) |
| **API 读取** | ✅ 已暴露 | `/api/v2/bo/user/1` 返回 `locale` 字段 |
| **API 写入** | ⚠️ 部分 | PATCH 500 (MethodNotAllowed) 但 PUT 应支持 |
| **前端 i18n 资源** | ❌ 无 | `frontend/` 目录**无** `i18n.ts` / `locales/zh-CN.ts` / `en-US.ts` |
| **前端切换 UI** | ❌ 无 | `views/` 目录**无** locale 切换组件 |
| **Vue-i18n 集成** | ❌ 无 | `package.json` 可能未装 `vue-i18n` |

### 解锁方案

#### A. 最小可行 (1-2 天工作量)

```bash
# Step 1: 安装 vue-i18n
cd frontend
npm install vue-i18n@9

# Step 2: 创建 i18n 资源
mkdir -p src/locales
# src/locales/zh-CN.ts
# src/locales/en-US.ts
```

```typescript
// src/locales/zh-CN.ts
export default {
  common: {
    save: '保存',
    cancel: '取消',
    delete: '删除',
    edit: '编辑',
    create: '新建',
    confirm: '确认',
    // ... 50-100 个常用键
  },
  menu: {
    // menu_code -> 翻译
  },
  // ...
}
```

```typescript
// src/i18n.ts
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

export const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('locale') || 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS }
})
```

```vue
<!-- src/components/LocaleSwitcher.vue -->
<template>
  <el-dropdown @command="changeLocale">
    <span>{{ $t('common.currentLocale') }}</span>
    <el-dropdown-menu>
      <el-dropdown-item command="zh-CN">中文</el-dropdown-item>
      <el-dropdown-item command="en-US">English</el-dropdown-item>
    </el-dropdown-menu>
  </el-dropdown>
</template>
```

#### B. 工作量估算
- 创建 2 个 locale 文件 (zh-CN, en-US) - 1-2 天
- 集成 vue-i18n + 切换组件 - 0.5 天
- 改造现有硬编码文本 (50+ 处) - 1-2 天
- 调用 user profile API 同步 - 0.5 天
- **总计**: 3-5 天

#### C. 建议优先级
🟡 **中等** - 真正的产品功能 (国际化)，不是 P0 阻塞

---

## 2) E21 (脏数据确认) - 🟡 中等

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **脏数据状态** | ⚠️ 已定义 | `ObjectDetailPage.vue:175` `const dirty = ref(false)` |
| **弹窗组件** | ✅ 已就绪 | `showConfirmDialog` ref + 处理函数 |
| **setDirty(true) 调用** | ❌ **零调用** | 全工程**没有任何** `setDirty(true)` |
| **beforeunload 监听** | ❌ **零监听** | `window.addEventListener('beforeunload', ...)` **不存在** |
| **close 时检查** | ✅ 有逻辑 | `handleClose()` 检查 `dirty.value` |

### 关键代码 (`ObjectDetailPage.vue`)
```javascript
const dirty = ref(false)  // 默认 false

function handleClose() {
  if (dirty.value) {
    pendingCloseAction = doClose
    showConfirmDialog.value = true  // 弹窗会显示
  } else {
    doClose()  // 直接关闭
  }
}

// 提供给子组件:
defineExpose({
  isDirty: () => dirty.value,
  setDirty: (value) => { dirty.value = !!value }
})
```

### 解锁方案

#### A. 最小可行 (1 天工作量)

```vue
<!-- ObjectPageField.vue 修改 -->
<script setup>
import { inject, onUnmounted } from 'vue'

const dirtyApi = inject('detailDirtyApi', null)

function onFieldChange(newValue, oldValue) {
  if (newValue !== oldValue) {
    dirtyApi?.setDirty(true)  // ✅ 关键: 用户修改字段时设为 true
  }
}
</script>
```

```vue
<!-- ObjectDetailPage.vue 修改 -->
<script setup>
import { onMounted, onUnmounted } from 'vue'

function handleBeforeUnload(e) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = '有未保存的修改, 确定离开?'
  }
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>
```

```vue
<!-- DetailPage.vue 修改 - 保存后重置 -->
function handleSaveSuccess() {
  dirtyApi.setDirty(false)  // ✅ 保存成功后重置
}
```

#### B. 工作量估算
- 在 `ObjectPageField.vue` 加 `setDirty(true)` - 0.5 天
- 添加 `beforeunload` 监听 - 0.5 天
- 测试各种保存/取消路径 - 0.5 天
- **总计**: 1-1.5 天

#### C. 建议优先级
🟡 **中等** - 重要的 UX 改进 (防止数据丢失)，不是 P0 阻塞

---

## 3) C01/C02-DEEP (ObjectChildSection) - 🔴 困难

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **组件** | ✅ 已实现 | `ObjectChildSection.vue` 完整 (含 createLabel, handleCreate) |
| **API** | ✅ 已定义 | `createChild`, `updateChild`, `deleteChild`, `loadChildList` |
| **包装组件** | ✅ 已实现 | `ObjectPageWithChildren.vue` |
| **单元测试** | ✅ 已存在 | `ObjectChildSection.spec.js` |
| **业务页面集成** | ❌ **零集成** | `views/` 目录**无**任何页面 import ObjectChildSection |
| **深插入 API** | ❌ 不存在 | `/api/v2/bo/enum_type/deep_insert` 404, `with_children` 404 |

### 关键代码 (`ObjectChildSection.vue`)
```javascript
function handleCreate() {
  currentRecordId.value = null
  detailReadonly.value = false
  detailTitle.value = `${props.createLabel} - ${parentDetail.value?.name || ''}`
  // ... 显示创建弹窗
}

function createChild(data) {
  // 调用 POST /api/v2/bo/{child_type}
  return fetch(...)
}
```

### 解锁方案

#### A. 最小可行 (3-5 天工作量)

**需要改动 3 个文件**:
1. `ProductDetailPage.vue` - 集成 ObjectChildSection 显示 version 子项
2. `RoleDetailPage.vue` - 集成显示 permission 子项
3. `PermissionDetailPage.vue` - 集成显示 role 子项

**示例**:
```vue
<!-- ProductDetailPage.vue -->
<template>
  <div>
    <ObjectPage
      :object-type="'product'"
      :object-id="productId"
    />
    
    <!-- [NEW] 子项: version 列表 -->
    <ObjectChildSection
      :parent-object-type="'product'"
      :parent-object-id="productId"
      :child-object-type="'product_version'"
      :parent-detail="productDetail"
      :show-create="true"
      :create-label="'新建版本'"
    />
  </div>
</template>
```

**后端 deep_insert 端点 (1-2 天)**:
```python
# meta/api/bo_api.py 添加
@meta_v2_bp.route('/<object_type>/deep_insert', methods=['POST'])
def deep_insert(object_type):
    """深插入: 创建父+子 一起"""
    data = request.get_json()
    parent = data.get('parent', {})
    children = data.get('children', [])
    
    with transaction():
        parent_id = bo_service.create(object_type, parent)
        for child in children:
            child[f'{object_type}_id'] = parent_id  # 关联
            bo_service.create('product_version', child)
    return jsonify({'success': True, 'data': {'parent_id': parent_id}})
```

#### B. 工作量估算
- 后端 deep_insert API - 1-2 天
- 前端 3 个页面集成 - 2-3 天
- 测试 deep insert 端到端 - 0.5-1 天
- **总计**: 3.5-6 天

#### C. 建议优先级
🔴 **困难** - 需要改动业务页面 (影响所有产品/角色/权限详情页)，UI 集成风险较高

---

## 4) DIM-FULL (dimension 业务规则) - 🟡 中等

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **后端实现** | ✅ 完整 | 45 个文件含 dimension 逻辑 |
| **v1 端点** | ✅ 已实现 | `management-dimensions`, `dimension/{id}/instances`, `role/{id}/permission-rules` |
| **v1 迁移** | ✅ 已做 | 410 → `/api/v2/bo/management_dimension` (sunset 2026-06-05) |
| **v2 端点** | ❌ 不工作 | `/api/v2/bo/management_dimension` 400 (Unknown object type) |
| **v2 顶层** | ❌ NotFound | `/api/v2/management-dimensions` 500 |
| **业务规则文档** | ❌ 无 | 没有 DIMENSION_RULES.md |

### 真实阻塞
1. **路由迁移不完整** - v1 已迁移，v2 实际不工作
2. **缺少业务规则文档** - 不知道 dimension 类型/层级/范围的具体规则

### 解锁方案

#### A. 最小可行 (2-3 天工作量)

**Step 1: 写 dimension 业务规则文档** (1 天)

```markdown
# DIMENSION_RULES.md

## 1. Dimension 类型
| 类型 | 说明 | 示例 |
|------|------|------|
| `org` | 组织维度 | 公司/部门/团队 |
| `geo` | 地理维度 | 国家/省/市 |
| `product` | 产品维度 | 产品线/产品/版本 |
| `time` | 时间维度 | 年/季度/月 |
| `user` | 用户维度 | 角色/职位/职级 |

## 2. Dimension 层级
- 树形结构, 通过 `parent_id` 关联
- 支持 N 级嵌套
- 根节点 `parent_id = NULL`

## 3. Dimension 范围
- `private`: 私有 (仅创建者可见)
- `team`: 团队 (本团队可见)
- `org`: 组织 (全公司可见)
- `public`: 公开 (所有人可见)

## 4. 权限规则
- role 通过 `dimension_scope` 限制可访问的 dimension 实例
- `dimension_scope` = `[{dimension_id, instance_ids[]}]`
- `permission_rules` 定义 role 在 dimension 下的具体动作权限

## 5. 范围继承
- 父 dimension 的权限自动继承给子 dimension
- 子 dimension 可覆盖父的权限设置
```

**Step 2: 修复 v2 路由** (1-2 天)

```python
# meta/api/management_dimension_api.py 修改 url_prefix
- url_prefix='/api/v1/management-dimensions'
+ url_prefix='/api/v2/bo/management_dimension'
# 同时加 /instances 等子路径
```

#### B. 工作量估算
- 写 DIMENSION_RULES.md - 0.5-1 天
- 修复 v2 路由 (重新注册 blueprint) - 1-2 天
- 测试 dimension 全链路 - 0.5 天
- **总计**: 2-3.5 天

#### C. 建议优先级
🟡 **中等** - 业务规则文档化是低垂果实，路由修复是中等难度

---

## 总结对比

| DEFER ID | 真实状态 | 工作量 | 优先级 | 推荐实施 |
|----------|---------|--------|--------|----------|
| **E34** | 后端 OK, 前端无资源 | 3-5 天 | 🟡 P2 | 单独 PR |
| **E21** | 后端 OK, 前端 0 调用 | 1-1.5 天 | 🟡 P1 | 快速修复 |
| **C01/C02** | 组件已实现但未集成 | 3.5-6 天 | 🔴 P2 | 跟产品迭代一起做 |
| **DIM-FULL** | 45 文件已实现, 路由未迁移 | 2-3.5 天 | 🟡 P1 | 文档 + 路由修复 |

## 实施建议

### 立即可做 (1-2 天)
1. **E21 脏数据** - 1 天工作量, UX 大幅提升
2. **DIM-FULL 文档** - 0.5 天写 DIMENSION_RULES.md

### 短期 (1-2 周)
3. **E34 i18n** - 分阶段, 先 zh-CN + en-US 两个文件
4. **DIM-FULL 路由修复** - 1-2 天, 完成后 dimension 端点全部 ACTIVE

### 中期 (1 个月)
5. **C01/C02 业务页面集成** - 跟产品迭代同步进行

## BMRD 框架含义

| 实施后解锁 | ACTIVE 规则数 | DEFER 规则数 |
|----------|-------------|-------------|
| **E21 解锁** | +0 (E21 已有, 改 status 即可) | -1 |
| **E34 解锁** | +1 (I18N-LOCALE 规则) | -1 |
| **C01/C02 解锁** | +2 (DEEP-INSERT-1/2) | -2 |
| **DIM-FULL 解锁** | +3 (DIM-TYPE/LEVEL/SCOPE) | -1 |

**总潜在**: DEFER 从 9 → 4, 实际跑的测试 +5
