## 目录

1. [一、现有应用组件使用分析](#一-现有应用组件使用分析)
2. [二、兼容性策略](#二-兼容性策略)
3. [三、详细迭代计划](#三-详细迭代计划)
4. [四、对现有应用的影响评估](#四-对现有应用的影响评估)
5. [五、迭代时间表](#五-迭代时间表)
6. [六、验收标准](#六-验收标准)

---
# UI组件优化迭代计划

> **版本**: v1.0  
> **日期**: 2026-05-07  
> **目的**: 细化组件优化方案，评估对现有应用的影响

---

## 一、现有应用组件使用分析

### 1.1 应用概览

| 应用 | 路径 | 主要功能 | 使用公共组件 |
|------|------|---------|-------------|
| **ArchDataManageApp** | `views/ArchDataManageApp/` | 架构数据管理 | AuditLog, EmptyState |
| **SystemManagement** | `views/SystemManagement/` | 系统管理 | ConfirmDialog, AppButton, AppInput, AuditLog |
| **ProductVersionApp** | `views/ProductVersionApp/` | 产品版本管理 | MetaTable, MetaForm, MetaDialog |
| **AADiagramApp** | `views/AADiagramApp/` | 图表生成 | AppButton, AppInput, AppSelect |

### 1.2 组件使用详情

#### ArchDataManageApp（主应用）

```
自有组件：
├── DataTable.vue          # 自定义表格（样式硬编码）
├── EditForm.vue           # 自定义表单（业务耦合）
├── DetailPanel.vue        # 自定义详情面板
├── DynamicView.vue        # 动态视图
├── ExportDialog.vue       # 导出对话框
├── ImportDialog.vue       # 导入对话框
└── ConfirmDialog.vue      # 重复的确认对话框

使用公共组件：
├── AuditLog               # 变更日志
└── EmptyState             # 空状态
```

#### SystemManagement（系统管理）

```
使用公共组件：
├── ConfirmDialog          # 确认对话框
├── AppButton              # 按钮
├── AppInput               # 输入框
├── AppIcon                # 图标
└── AuditLog               # 变更日志

自有组件：
├── UserFormDialog.vue     # 用户表单对话框
├── RoleDetailDrawer.vue   # 角色详情抽屉
├── EnumValueFormDialog.vue # 枚举值表单对话框
└── ...其他对话框
```

#### ProductVersionApp（产品版本）

```
使用公共组件：
├── MetaTable              # 数据表格
├── MetaForm               # 表单组件
└── MetaDialog             # 表单对话框

自有组件：
├── VersionTable.vue       # 版本表格（使用MetaTable）
├── ProductFormDialog.vue  # 产品表单对话框
└── VersionFormDialog.vue  # 版本表单对话框
```

#### AADiagramApp（图表应用）

```
使用公共组件：
├── AppButton              # 按钮
├── AppInput               # 输入框
├── AppSelect              # 选择器
└── AppIcon                # 图标
```

---

## 二、兼容性策略

### 2.1 改进原则

| 原则 | 说明 | 实施方式 |
|------|------|---------|
| **向后兼容** | 新增功能不破坏现有API | 新增可选属性，默认值保持原行为 |
| **增量增强** | 新功能采用增量方式 | 新增组件或属性，不修改现有 |
| **渐进迁移** | 提供迁移路径而非强制升级 | 废弃标记 + 迁移指南 |
| **版本控制** | 重大变更通过版本号管理 | v1 → v2，提供迁移文档 |

### 2.2 API变更策略

#### 新增功能（无影响）

```vue
<!-- ✅ 新增可选属性，默认值保持原行为 -->
<MetaTable
  :data="data"
  :columns="columns"
  <!-- 🆕 新增属性，默认 false -->
  :selectable="false"
  <!-- 🆕 新增属性，默认 null -->
  :pagination="null"
/>
```

#### 行为变更（需谨慎）

```vue
<!-- ⚠️ 行为变更需要提供开关 -->
<MetaTable
  :data="data"
  :columns="columns"
  <!-- 🆕 新增属性控制新行为 -->
  :server-side="false"
  <!-- 默认 false，保持客户端排序 -->
/>
```

#### 废弃功能（提供迁移路径）

```vue
<!-- ❌ 废弃的用法 -->
<DataTable :data="data" />

<!-- ✅ 推荐的新用法 -->
<MetaTable :data="data" />

<!-- 迁移期间两者并存 -->
```

---

## 三、详细迭代计划

### Phase 1：基础增强（第1-2周）

#### 迭代 1.1：MetaTable 多选功能

| 项目 | 说明 |
|------|------|
| **目标** | 为 MetaTable 添加行选择功能 |
| **工作量** | 2天 |
| **影响范围** | 仅影响使用 `selectable` 属性的页面 |
| **兼容性** | ✅ 向后兼容，默认不启用 |

**实施细节**：

```vue
<!-- 新增API -->
<MetaTable
  :data="data"
  :columns="columns"
  <!-- 🆕 新增属性 -->
  :selectable="true"
  :selected-keys="selectedKeys"
  :row-key="id"
  @selection-change="handleSelectionChange"
/>
```

**影响评估**：

| 应用 | 影响 | 需要修改 |
|------|------|---------|
| ArchDataManageApp | ❌ 无影响 | 使用自定义 DataTable |
| SystemManagement | ❌ 无影响 | 未使用 MetaTable |
| ProductVersionApp | ⚠️ 可选升级 | VersionTable 可选择性启用多选 |
| AADiagramApp | ❌ 无影响 | 未使用 MetaTable |

---

#### 迭代 1.2：MetaTable 完整分页

| 项目 | 说明 |
|------|------|
| **目标** | 为 MetaTable 添加完整分页功能 |
| **工作量** | 1天 |
| **影响范围** | 仅影响使用 `pagination` 属性的页面 |
| **兼容性** | ✅ 向后兼容，默认显示总数 |

**实施细节**：

```vue
<!-- 新增API -->
<MetaTable
  :data="data"
  :columns="columns"
  <!-- 🆕 新增属性 -->
  :pagination="{
    current: 1,
    pageSize: 20,
    total: 100,
    showSizeChanger: true,
    showQuickJumper: true
  }"
  @page-change="handlePageChange"
  @page-size-change="handlePageSizeChange"
/>
```

**影响评估**：

| 应用 | 影响 | 需要修改 |
|------|------|---------|
| ProductVersionApp | ⚠️ 可选升级 | 可选择性启用完整分页 |
| 其他应用 | ❌ 无影响 | 未使用 MetaTable |

---

#### 迭代 1.3：MetaForm 条件显示

| 项目 | 说明 |
|------|------|
| **目标** | 为 MetaForm 添加字段条件显示功能 |
| **工作量** | 1天 |
| **影响范围** | 仅影响使用 `fieldVisibility` 属性的表单 |
| **兼容性** | ✅ 向后兼容，默认所有字段显示 |

**实施细节**：

```vue
<!-- 新增API -->
<MetaForm
  :fields="fields"
  v-model="formData"
  <!-- 🆕 新增属性 -->
  :field-visibility="{
    'end_date': (form) => form.status === 'active',
    'reason': (form) => form.action === 'reject'
  }"
/>
```

**影响评估**：

| 应用 | 影响 | 需要修改 |
|------|------|---------|
| ProductVersionApp | ⚠️ 可选升级 | 可选择性使用条件显示 |
| 其他应用 | ❌ 无影响 | 未使用 MetaForm |

---

#### 迭代 1.4：MetaForm 字段联动

| 项目 | 说明 |
|------|------|
| **目标** | 为 MetaForm 添加字段联动功能 |
| **工作量** | 1天 |
| **影响范围** | 仅影响使用 `fieldDependencies` 属性的表单 |
| **兼容性** | ✅ 向后兼容，默认无联动 |

**实施细节**：

```vue
<!-- 新增API -->
<MetaForm
  :fields="fields"
  v-model="formData"
  <!-- 🆕 新增属性 -->
  :field-dependencies="{
    'product_id': {
      onChange: (val, form, { setFieldValue }) => {
        setFieldValue('version_id', '')
        // 可选：触发加载版本列表
      }
    }
  }"
/>
```

**影响评估**：

| 应用 | 影响 | 需要修改 |
|------|------|---------|
| ArchDataManageApp | ⚠️ 可选迁移 | EditForm 可迁移到此功能 |
| ProductVersionApp | ⚠️ 可选升级 | 可选择性使用字段联动 |
| 其他应用 | ❌ 无影响 | 未使用 MetaForm |

---

### Phase 2：组件增强（第3-4周）

#### 迭代 2.1：AppSelect 选项分组

| 项目 | 说明 |
|------|------|
| **目标** | 为 AppSelect 添加选项分组功能 |
| **工作量** | 1天 |
| **影响范围** | 仅影响使用分组选项的选择器 |
| **兼容性** | ✅ 向后兼容，支持扁平选项 |

**实施细节**：

```vue
<!-- 新增API -->
<AppSelect
  v-model="value"
  <!-- 🆕 支持分组选项 -->
  :options="[
    { label: '常用', options: [{ label: '选项1', value: '1' }] },
    { label: '其他', options: [{ label: '选项2', value: '2' }] }
  ]"
/>
```

---

#### 迭代 2.2：AppTabs 溢出处理

| 项目 | 说明 |
|------|------|
| **目标** | 为 AppTabs 添加溢出处理功能 |
| **工作量** | 1天 |
| **影响范围** | 仅影响 Tab 数量超过容器宽度的场景 |
| **兼容性** | ✅ 向后兼容，自动处理溢出 |

**实施细节**：

```vue
<!-- 新增API -->
<AppTabs
  v-model="activeTab"
  :tabs="tabs"
  <!-- 🆕 新增属性 -->
  :overflow-mode="'dropdown'"
  <!-- 可选：'scroll' | 'dropdown' -->
/>
```

---

#### 迭代 2.3：AppSideNav 折叠功能

| 项目 | 说明 |
|------|------|
| **目标** | 为 AppSideNav 添加折叠功能 |
| **工作量** | 1天 |
| **影响范围** | 仅影响使用 `collapsible` 属性的导航 |
| **兼容性** | ✅ 向后兼容，默认不折叠 |

**实施细节**：

```vue
<!-- 新增API -->
<AppSideNav
  v-model="currentMenu"
  :items="items"
  <!-- 🆕 新增属性 -->
  :collapsible="true"
  :collapsed="collapsed"
  @collapse-change="handleCollapseChange"
/>
```

---

#### 迭代 2.4：AppInput 密码显示切换

| 项目 | 说明 |
|------|------|
| **目标** | 为 AppInput 添加密码显示切换功能 |
| **工作量** | 0.5天 |
| **影响范围** | 仅影响 type="password" 的输入框 |
| **兼容性** | ✅ 向后兼容，自动添加切换按钮 |

**实施细节**：

```vue
<!-- 新增API -->
<AppInput
  v-model="password"
  type="password"
  <!-- 🆕 新增属性，默认 true -->
  :show-password-toggle="true"
/>
```

---

### Phase 3：新增组件（第5-6周）

#### 迭代 3.1：MasterDetailLayout 布局组件

| 项目 | 说明 |
|------|------|
| **目标** | 创建左右布局组件 |
| **工作量** | 2天 |
| **影响范围** | 新组件，无影响 |
| **兼容性** | ✅ 完全兼容，新组件 |

**实施细节**：

```vue
<!-- 新组件 -->
<MasterDetailLayout
  :sidebar-width="280"
  :sidebar-collapsible="true"
>
  <template #master>
    <MetaTable :data="list" />
  </template>
  <template #detail>
    <DetailPanel :data="selected" />
  </template>
</MasterDetailLayout>
```

**影响评估**：

| 应用 | 影响 | 建议 |
|------|------|------|
| ArchDataManageApp | ⚠️ 可选迁移 | 可迁移到新布局组件 |
| 其他应用 | ❌ 无影响 | 可选择性使用 |

---

#### 迭代 3.2：Pagination 分页组件

| 项目 | 说明 |
|------|------|
| **目标** | 创建独立分页组件 |
| **工作量** | 1天 |
| **影响范围** | 新组件，无影响 |
| **兼容性** | ✅ 完全兼容，新组件 |

**实施细节**：

```vue
<!-- 新组件 -->
<Pagination
  v-model:current="currentPage"
  :total="100"
  :page-size="20"
  :show-size-changer="true"
  :show-quick-jumper="true"
  @change="handlePageChange"
/>
```

---

#### 迭代 3.3：Drawer 抽屉组件

| 项目 | 说明 |
|------|------|
| **目标** | 创建右侧抽屉组件 |
| **工作量** | 1.5天 |
| **影响范围** | 新组件，无影响 |
| **兼容性** | ✅ 完全兼容，新组件 |

**实施细节**：

```vue
<!-- 新组件 -->
<Drawer
  v-model="visible"
  title="详情"
  :width="600"
  :placement="'right'"
>
  <DetailPanel :data="selected" />
  <template #footer>
    <AppButton @click="visible = false">关闭</AppButton>
  </template>
</Drawer>
```

---

### Phase 4：可访问性增强（第7周）

#### 迭代 4.1：ARIA 属性完善

| 项目 | 说明 |
|------|------|
| **目标** | 为所有组件添加完整的 ARIA 属性 |
| **工作量** | 3天 |
| **影响范围** | 所有组件，但仅影响可访问性 |
| **兼容性** | ✅ 向后兼容，无功能变更 |

**实施细节**：

| 组件 | 需要添加的 ARIA 属性 |
|------|---------------------|
| MetaTable | `role="grid"`, `aria-sort`, `aria-selected` |
| MetaForm | `aria-invalid`, `aria-describedby` |
| AppSelect | `aria-expanded`, `aria-activedescendant` |
| AppModal | `role="dialog"`, `aria-modal`, Focus Trap |
| AppTabs | `role="tablist"`, `aria-selected` |

---

### Phase 5：迁移与清理（第8周）

#### 迭代 5.1：DataTable 迁移指南

| 项目 | 说明 |
|------|------|
| **目标** | 提供从 DataTable 迁移到 MetaTable 的指南 |
| **工作量** | 1天 |
| **影响范围** | ArchDataManageApp |
| **兼容性** | ⚠️ 需要手动迁移 |

**迁移对照表**：

| DataTable 属性 | MetaTable 属性 | 说明 |
|---------------|---------------|------|
| `rows` | `data` | 数据源 |
| `columns` | `columns` | 列配置 |
| `onRowClick` | `@row-click` | 行点击事件 |
| `sortable` | `columns[].sortable` | 排序配置 |

---

#### 迭代 5.2：重复组件清理

| 项目 | 说明 |
|------|------|
| **目标** | 清理重复的组件实现 |
| **工作量** | 2天 |
| **影响范围** | ArchDataManageApp |
| **兼容性** | ⚠️ 需要迁移 |

**清理清单**：

| 重复组件 | 位置 | 替代方案 |
|---------|------|---------|
| `ConfirmDialog.vue` | ArchDataManageApp/components/ | 使用公共 ConfirmDialog |
| `ExportDialog.vue` | ArchDataManageApp/components/ | 迁移到公共组件 |
| `ImportDialog.vue` | ArchDataManageApp/components/ | 迁移到公共组件 |

---

## 四、对现有应用的影响评估

### 4.1 影响矩阵

| 应用 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|------|---------|---------|---------|---------|---------|
| **ArchDataManageApp** | ❌ 无影响 | ❌ 无影响 | ⚠️ 可选迁移 | ❌ 无影响 | ⚠️ 需迁移 |
| **SystemManagement** | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 |
| **ProductVersionApp** | ⚠️ 可选升级 | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 |
| **AADiagramApp** | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 | ❌ 无影响 |

### 4.2 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| API 变更导致现有代码失效 | 低 | 所有变更采用增量方式，默认值保持原行为 |
| 性能回归 | 低 | 新增功能不影响现有性能路径 |
| 样式冲突 | 低 | 使用 scoped CSS，不修改全局样式 |
| 测试覆盖不足 | 中 | 每个迭代完成后运行完整测试套件 |

### 4.3 回滚策略

| 场景 | 回滚方式 |
|------|---------|
| 新功能有问题 | 禁用新属性即可回滚 |
| 性能问题 | 使用 feature flag 控制启用 |
| 严重问题 | 通过 Git 回滚到上一版本 |

---

## 五、迭代时间表

```
Week 1-2: Phase 1 - 基础增强
├── Day 1-2: MetaTable 多选功能
├── Day 3: MetaTable 完整分页
├── Day 4: MetaForm 条件显示
└── Day 5: MetaForm 字段联动

Week 3-4: Phase 2 - 组件增强
├── Day 1: AppSelect 选项分组
├── Day 2: AppTabs 溢出处理
├── Day 3: AppSideNav 折叠功能
└── Day 4-5: 其他增强

Week 5-6: Phase 3 - 新增组件
├── Day 1-2: MasterDetailLayout
├── Day 3: Pagination
├── Day 4-5: Drawer
└── Day 5: 单元测试

Week 7: Phase 4 - 可访问性增强
├── Day 1-2: ARIA 属性完善
├── Day 3: 键盘导航增强
└── Day 4-5: 测试验证

Week 8: Phase 5 - 迁移与清理
├── Day 1-2: 迁移指南编写
├── Day 3-4: 重复组件清理
└── Day 5: 文档更新
```

---

## 六、验收标准

### 每个迭代验收

- [ ] 新功能单元测试覆盖率 > 80%
- [ ] 现有测试全部通过
- [ ] 无 TypeScript 类型错误
- [ ] 无 ESLint 警告
- [ ] 文档更新完成

### 最终验收

- [ ] 所有新功能可用
- [ ] 现有应用无回归
- [ ] 可访问性测试通过
- [ ] 性能无明显下降
- [ ] 文档完整

---

**最后更新**: 2026-05-07
