## 目录

1. [一、现有模式分析](#一-现有模式分析)
2. [二、复用策略](#二-复用策略)
3. [三、现有组件清单](#三-现有组件清单)
4. [四、组件使用决策树](#四-组件使用决策树)
5. [四、迁移计划](#四-迁移计划)
6. [五、验证清单](#五-验证清单)
7. [六、相关文档](#六-相关文档)

---
# UI组件复用策略分析

> **版本**: v1.0  
> **日期**: 2026-05-07  
> **目的**: 分析现有模式，制定复用策略，确保UI一致性

---

## 一、现有模式分析

### 1.1 List列表模式

#### 现有实现

| 组件 | 位置 | 特点 | 状态 |
|------|------|------|------|
| `DataTable.vue` | `ArchDataManageApp/components/` | 功能完整（分页、排序、多选） | ⚠️ 样式硬编码 |
| `MetaTable.vue` | `components/common/` | 支持slot、状态标签、时间格式化 | ✅ 使用design tokens |
| `VersionTable.vue` | `ProductVersionApp/components/` | 简单表格 | ❌ 样式未复用 |
| 内联表格 | 各管理页面 | 直接内联HTML | ❌ 不可复用 |

#### 问题诊断

```vue
<!-- DataTable.vue - 硬编码颜色 -->
<style scoped>
th {
  background: #fafafa;        /* ❌ 硬编码 */
  color: #333;               /* ❌ 硬编码 */
}
td {
  color: #333;               /* ❌ 硬编码 */
}
</style>

<!-- MetaTable.vue - 使用design tokens ✅ -->
<style scoped>
.mt-table th {
  background: var(--color-bg-secondary);  /* ✅ 使用变量 */
  color: var(--color-text-secondary);    /* ✅ 使用变量 */
}
</style>
```

#### 复用建议

| 建议 | 说明 | 优先级 |
|------|------|--------|
| **统一使用 MetaTable** | 已有完整功能的表格组件，应作为默认选择 | 🔴 必须 |
| **废弃 DataTable** | 样式硬编码，建议迁移到 MetaTable | 🟡 推荐 |
| **增强 MetaTable** | 添加服务端分页、批量操作支持 | 🟢 可选 |

---

### 1.2 Detail详情模式

#### 现有实现

| 组件 | 位置 | 特点 | 状态 |
|------|------|------|------|
| `DetailPanel.vue` | `ArchDataManageApp/components/` | 包含基本信息、层级路径、关联关系、变更历史 | ⚠️ 硬编码字段 |
| `RoleDetailDrawer.vue` | `SystemManagement/` | 右侧抽屉，包含Tab导航 | ✅ 样式良好 |
| 各种内联详情 | 页面内 | 无统一模式 | ❌ 不可复用 |

#### 问题诊断

```vue
<!-- DetailPanel.vue - 硬编码字段映射 -->
<script>
const basicFields = computed(() => {
  const typeFieldMap = {
    product: [
      { key: 'id', label: 'ID' },
      { key: 'name', label: '产品名称' },  // ❌ 硬编码
      { key: 'code', label: '产品编码' },  // ❌ 硬编码
      // ...
    ],
    // ...
  }
})
</script>

<!-- RoleDetailDrawer.vue - 通用布局 ✅ -->
<template>
  <div class="drawer-content">
    <div class="section basic-info">
      <div class="info-row">
        <span class="label">角色编码：</span>
        <span>{{ role?.code || '-' }}</span>  <!-- ✅ 通用 -->
      </div>
    </div>
  </div>
</template>
```

#### 复用建议

| 建议 | 说明 | 优先级 |
|------|------|--------|
| **创建通用 DetailPanel** | 接收 fields 配置，动态渲染 | 🔴 必须 |
| **抽取布局模式** | 头部 + Tab导航 + 内容区 + 底部操作 | 🟡 推荐 |
| **创建 Drawer 组件** | 封装右侧抽屉布局（已部分实现） | 🟡 推荐 |

---

### 1.3 Edit编辑模式

#### 现有实现

| 组件 | 位置 | 特点 | 状态 |
|------|------|------|------|
| `EditForm.vue` | `ArchDataManageApp/components/` | 复杂表单，包含层级选择联动 | ⚠️ 业务耦合 |
| `DynamicForm.vue` | `ArchDataManageApp/components/` | 动态表单 | ⚠️ 依赖元数据 |
| `*FormDialog.vue` | `SystemManagement/` | 各种表单对话框 | ✅ 可复用部分 |
| `MetaForm.vue` | `components/common/` | 通用表单组件 | ✅ 基础可用 |

#### 问题诊断

```vue
<!-- EditForm.vue - 业务逻辑耦合 -->
<script>
// 硬编码的业务逻辑
function onProductChange() {
  formData.value.version_id = ''
  formData.value.domain_id = ''
  // ... 业务特定逻辑
}
</script>

<!-- *FormDialog.vue - 更好的分离 -->
<template>
  <AppModal v-model="visible" title="用户表单">
    <form @submit.prevent="handleSubmit">
      <!-- 通用表单项 -->
    </form>
    <template #footer>
      <AppButton @click="visible = false">取消</AppButton>
      <AppButton variant="primary" @click="handleSubmit">保存</AppButton>
    </template>
  </AppModal>
</template>
```

#### 复用建议

| 建议 | 说明 | 优先级 |
|------|------|--------|
| **创建通用 FormDialog** | 封装 AppModal + 表单布局 | 🔴 必须 |
| **抽取通用表单项组件** | TextField, SelectField, TextareaField 等 | 🟡 推荐 |
| **分离业务逻辑** | 表单组件只负责渲染，业务逻辑在页面层 | 🟡 推荐 |

---

### 1.4 Master-Detail模式

#### 现有实现

| 组件 | 位置 | 特点 | 状态 |
|------|------|------|------|
| `ArchDataManageApp/index.vue` | 主应用 | 左侧树 + 右侧内容区 + Tab切换 | ✅ 布局良好 |
| `RoleDetailDrawer.vue` | 角色管理 | 右侧抽屉展示详情 | ✅ 布局良好 |
| 各种管理页面 | SystemManagement/ | 内联表格 + Dialog | ❌ 缺少统一模式 |

#### 问题诊断

```vue
<!-- ArchDataManageApp/index.vue - 良好布局 ✅ -->
<div class="adm-body">
  <aside class="adm-sidebar">
    <!-- 左侧边栏 -->
  </aside>
  <main class="adm-content">
    <!-- 主内容区 -->
  </main>
</div>

<!-- 缺少的模式：表格行点击 → 打开详情 -->
<!-- 需要统一的详情打开方式 -->
```

#### 复用建议

| 建议 | 说明 | 优先级 |
|------|------|--------|
| **创建 MasterDetailLayout** | 通用左右布局组件 | 🔴 必须 |
| **统一详情打开方式** | 抽屉/Dialog/内嵌Tab | 🟡 推荐 |
| **创建 ListDetailPage 模板** | 列表+详情完整页面模板 | 🟡 推荐 |

---

### 1.5 Popup弹窗模式

#### 现有实现

| 组件 | 位置 | 特点 | 状态 |
|------|------|------|------|
| `AppModal.vue` | `components/common/` | 功能完整（动画、键盘、背景锁定） | ✅ 良好 |
| `ConfirmDialog.vue` | `components/common/` | 确认对话框 | ✅ 良好 |
| `ExportDialog.vue` | 内联 | 导出对话框 | ❌ 硬编码 |
| `ImportDialog.vue` | 内联 | 导入对话框 | ❌ 硬编码 |
| Teleport内联Dialog | 页面内 | 无封装 | ❌ 不可复用 |

#### 问题诊断

```vue
<!-- AppModal.vue - 良好封装 ✅ -->
<template>
  <Teleport to="body">
    <Transition name="app-modal">
      <div v-if="modelValue" class="app-modal">
        <div class="app-modal__backdrop" @click="handleBackdropClick"></div>
        <div class="app-modal__container">
          <!-- 完整的Modal逻辑 -->
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<!-- 页面内硬编码Dialog ❌ -->
<Teleport to="body">
  <div v-if="showDialog" class="export-dialog-overlay">
    <!-- 重复的Dialog逻辑 -->
  </div>
</Teleport>
```

#### 复用建议

| 建议 | 说明 | 优先级 |
|------|------|--------|
| **使用 AppModal** | 替代所有内联Dialog | 🔴 必须 |
| **创建 ConfirmDialog** | 替代所有确认操作 | 🔴 必须 |
| **创建 FormDialog** | 替代所有表单弹窗 | 🟡 推荐 |
| **创建 ExportDialog/ImportDialog** | 封装导入导出逻辑 | 🟡 推荐 |

---

## 二、复用策略

### 2.1 组件分层

```
┌─────────────────────────────────────────────────────────────┐
│                    页面层 (Pages)                          │
│  负责：业务逻辑、数据获取、状态管理                           │
├─────────────────────────────────────────────────────────────┤
│                    容器层 (Containers)                      │
│  负责：布局组装、组件组合、数据传递                          │
│  例：MasterDetailLayout, ListPageLayout                    │
├─────────────────────────────────────────────────────────────┤
│                    展示层 (Components)                      │
│  负责：UI渲染、用户交互、样式                               │
│  例：MetaTable, DetailPanel, FormDialog                    │
├─────────────────────────────────────────────────────────────┤
│                    基础层 (Primitives)                      │
│  负责：最小UI单元                                           │
│  例：AppButton, AppInput, AppIcon, AppSelect               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 必须使用的组件

| 场景 | 必须使用 | 废弃 |
|------|---------|------|
| 表格列表 | `MetaTable` | `DataTable`、内联表格 |
| 详情展示 | `DetailPanel` 或 `DrawerPanel` | 内联详情HTML |
| 表单弹窗 | `AppModal` + 表单内容 | `<Teleport>` 内联Dialog |
| 确认操作 | `ConfirmDialog` | `window.confirm()` |
| Tab导航 | `AppTabs` | 自定义按钮Tab |
| 侧边导航 | `AppSideNav` | 自定义侧边栏 |

### 2.3 组件使用决策树

```
开始
  │
  ├─ 需要展示列表？
  │     │
  │     └─ 使用 MetaTable
  │
  ├─ 需要展示详情？
  │     │
  │     ├─ 右侧抽屉？→ 使用 DrawerPanel + DetailPanel
  │     ├─ Dialog？→ 使用 AppModal + DetailPanel
  │     └─ 内嵌？→ 使用 DetailPanel
  │
  ├─ 需要编辑数据？
  │     │
  │     ├─ Dialog编辑？→ 使用 FormDialog
  │     └─ 页面内编辑？→ 使用 FormSection
  │
  └─ 需要确认操作？
        │
        └─ 使用 ConfirmDialog
```

---

## 三、现有组件清单

### 3.1 已有组件（直接使用）

| 组件 | 位置 | 功能 | 使用场景 |
|------|------|------|---------|
| `MetaTable` | `components/common/MetaTable.vue` | 数据表格 | 列表展示 |
| `MetaForm` | `components/common/MetaForm.vue` | 表单组件 | 新增/编辑表单 |
| `MetaDialog` | `components/common/MetaDialog.vue` | 表单对话框 | 弹窗表单 |
| `AppModal` | `components/common/AppModal/` | 模态对话框 | 通用弹窗 |
| `ConfirmDialog` | `components/common/ConfirmDialog.vue` | 确认对话框 | 删除确认等 |
| `AppTabs` | `components/common/AppTabs/` | Tab导航 | 页面Tab切换 |
| `AppSideNav` | `components/common/AppSideNav/` | 侧边导航 | 左侧菜单 |
| `AuditLog` | `components/common/AuditLog/` | 变更日志 | 操作日志展示 |
| `AppButton` | `components/common/AppButton/` | 按钮 | 所有按钮 |
| `AppInput` | `components/common/AppInput/` | 输入框 | 文本输入 |
| `AppSelect` | `components/common/AppSelect/` | 下拉选择 | 选择器 |
| `EmptyState` | `components/common/EmptyState.vue` | 空状态 | 无数据提示 |

### 3.2 待创建组件（增量）

| 组件 | 说明 | 是否影响现有代码 |
|------|------|-----------------|
| `MasterDetailLayout` | 左右布局组件 | ❌ 不影响，新页面使用 |

---

## 四、组件使用决策树

```
开始
  │
  ├─ 需要展示列表？
  │     │
  │     └─ 使用 MetaTable ✅ 已有
  │
  ├─ 需要展示详情？
  │     │
  │     ├─ 右侧抽屉？→ 使用 AppModal + 自定义内容 ✅ 已有
  │     ├─ Dialog？→ 使用 AppModal ✅ 已有
  │     └─ 内嵌？→ 自定义布局
  │
  ├─ 需要编辑数据？
  │     │
  │     ├─ Dialog编辑？→ 使用 MetaDialog ✅ 已有
  │     └─ 页面内编辑？→ 使用 MetaForm ✅ 已有
  │
  ├─ 需要确认操作？
  │     │
  │     └─ 使用 ConfirmDialog ✅ 已有
  │
  └─ 需要左右布局？
        │
        └─ 使用 MasterDetailLayout 🆕 待创建
```

---

## 四、迁移计划

### 阶段1：基础组件完善（1天）

| 任务 | 负责人 | 验收标准 |
|------|--------|---------|
| 创建 DrawerPanel 组件 | AI | 支持右滑出、键盘ESC关闭 |
| 增强 DetailPanel 支持 fields 配置 | AI | 可配置字段映射 |
| 创建 FormDialog 组件 | AI | 支持自定义表单内容 |

### 阶段2：迁移现有代码（2天）

| 任务 | 负责人 | 验收标准 |
|------|--------|---------|
| 迁移 UserManagement 到通用组件 | AI | 使用 MetaTable + FormDialog |
| 迁移 RoleManagement 到通用组件 | AI | 使用 MetaTable + DrawerPanel |
| 迁移 EnumValueManagement 到通用组件 | AI | 使用 MetaTable + FormDialog |

### 阶段3：废弃旧组件（1天）

| 任务 | 负责人 | 验收标准 |
|------|--------|---------|
| 废弃 DataTable.vue | AI | 代码中不再引用 |
| 清理重复的Dialog实现 | AI | 统一使用 AppModal |
| 更新组件文档 | AI | 文档与实现一致 |

---

## 五、验证清单

### 开发新页面时

- [ ] 是否使用了 MetaTable 展示列表？
- [ ] 是否使用了 AppModal 或 DrawerPanel 展示详情/编辑？
- [ ] 是否使用了 ConfirmDialog 进行确认操作？
- [ ] 是否避免了内联 `<Teleport>` Dialog？
- [ ] 是否避免了硬编码颜色值？
- [ ] 样式是否使用了 design tokens？

### Code Review 时

- [ ] 是否有可以复用的现有组件？
- [ ] 是否有重复的 Dialog 实现？
- [ ] 是否有内联硬编码的表格？
- [ ] 是否使用了正确的颜色变量？

---

## 六、相关文档

| 文档 | 说明 |
|------|------|
| [UI_COMPONENT_GUIDELINES.md](./UI_COMPONENT_GUIDELINES.md) | UI组件开发规范 |
| [YONYOU_DESIGN.md](../src/styles/YONYOU_DESIGN.md) | yonDesign设计系统 |

---

**最后更新**: 2026-05-07
