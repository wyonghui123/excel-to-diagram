# Tasks: 统一日期格式配置

> **Spec**: [spec.md](./spec.md)
> **创建日期**: 2026-05-24
> **更新日期**: 2026-05-24

---

## Milestone 1: 核心能力 (P0)

### Task 1.1: 数据模型更新

**优先级**: P0
**预估工作量**: 1h
**依赖**: 无

**任务描述**:
在 user.yaml 中新增 5 个偏好配置字段。

**验收标准**:
- `user.yaml` 包含 locale, timezone, date_style, time_style, hour_cycle 字段
- Schema 同步成功新增数据库列
- 现有用户自动填充默认值

**相关文件**:
- `meta/schemas/user.yaml` (修改)

---

### Task 1.2: 后端日期格式化服务

**优先级**: P0
**预估工作量**: 2h
**依赖**: Task 1.1

**任务描述**:
创建后端日期格式化服务，支持时区转换和配置合并。

**验收标准**:
- `DateFormatService` 类实现完整
- 支持配置优先级合并
- 支持时区转换
- 单元测试通过

**相关文件**:
- `meta/services/date_format_service.py` (新建)

---

### Task 1.3: 前端日期格式化服务

**优先级**: P0
**预估工作量**: 2h
**依赖**: 无

**任务描述**:
创建前端日期格式化服务，使用浏览器原生 Intl API。

**验收标准**:
- `DateFormatService` 类实现完整
- 使用 `Intl.DateTimeFormat` API
- 支持 `format()`, `formatDate()`, `formatTime()` 方法
- 单元测试通过

**相关文件**:
- `src/services/DateFormatService.js` (新建)

---

### Task 1.4: 前端用户偏好 Store

**优先级**: P0
**预估工作量**: 1.5h
**依赖**: Task 1.1

**任务描述**:
创建 Pinia Store 管理用户偏好状态，通过 `/api/v1/users/me` 接口同步。

**验收标准**:
- `useUserPreferencesStore` 实现完整
- 支持加载和更新偏好
- 与后端 API 正确同步
- 本地缓存正常工作

**相关文件**:
- `src/stores/userPreferences.js` (新建)

---

### Task 1.5: 语言默认配置

**优先级**: P0
**预估工作量**: 0.5h
**依赖**: 无

**任务描述**:
定义各语言的默认日期格式配置。

**验收标准**:
- 中文（zh-CN）配置正确
- 美式英语（en-US）配置正确
- 英式英语（en-GB）配置正确

**相关文件**:
- `src/services/DateFormatService.js` (修改)
- `meta/services/date_format_service.py` (修改)

---

## Milestone 2: 完整体验 (P1)

### Task 2.1: 用户设置界面 - Tab 结构

**优先级**: P1
**预估工作量**: 1.5h
**依赖**: Task 1.4

**任务描述**:
在账户设置页面新增"偏好设置"Tab。

**验收标准**:
- Tab 导航正确显示
- Tab 切换正常工作
- 布局与现有 Tab 一致

**相关文件**:
- `src/views/AccountSettings/index.vue` (修改)

---

### Task 2.2: 用户设置界面 - 表单组件

**优先级**: P1
**预估工作量**: 3h
**依赖**: Task 2.1

**任务描述**:
实现偏好设置表单的各个组件。

**验收标准**:
- 语言区域选择正常工作
- 时区选择支持搜索
- 日期格式选择正常工作
- 时间格式选择正常工作
- 时间制式选择正常工作

**相关文件**:
- `src/views/AccountSettings/index.vue` (修改)

---

### Task 2.3: 用户设置界面 - 实时预览

**优先级**: P1
**预估工作量**: 1h
**依赖**: Task 2.2

**任务描述**:
实现偏好设置的实时预览功能。

**验收标准**:
- 预览区域显示当前配置效果
- 配置变更时预览实时更新
- 预览格式正确

**相关文件**:
- `src/views/AccountSettings/index.vue` (修改)

---

### Task 2.4: 用户设置界面 - 保存功能

**优先级**: P1
**预估工作量**: 1h
**依赖**: Task 2.2

**任务描述**:
实现偏好设置的保存功能。

**验收标准**:
- 保存按钮正常工作
- 保存成功显示提示
- 保存失败显示错误
- 保存后设置立即生效

**相关文件**:
- `src/views/AccountSettings/index.vue` (修改)

---

### Task 2.5: 时区自动检测

**优先级**: P1
**预估工作量**: 1h
**依赖**: Task 1.4

**任务描述**:
实现首次登录时自动检测用户时区。

**验收标准**:
- 使用 `Intl.DateTimeFormat().resolvedOptions().timeZone` 检测
- 首次登录时自动设置
- 用户可手动覆盖

**相关文件**:
- `src/stores/userPreferences.js` (修改)

---

### Task 2.6: 代码迁移

**优先级**: P1
**预估工作量**: 2h
**依赖**: Task 1.3

**任务描述**:
迁移现有 `formatDate` 调用到新服务。

**验收标准**:
- `useMetaList.js` 中的 `formatDate` 已更新
- `MetaListPage` 组件使用新服务
- 所有日期显示正常
- 旧函数标记为 deprecated

**相关文件**:
- `src/composables/useMetaList.js` (修改)
- `src/components/MetaListPage/*.vue` (修改)

---

## 任务依赖图

```
Task 1.1 (数据模型)
    ├── Task 1.2 (后端服务)
    └── Task 1.4 (前端 Store)
            ├── Task 2.1 (Tab 结构)
            │       ├── Task 2.2 (表单组件)
            │       │       ├── Task 2.3 (实时预览)
            │       │       └── Task 2.4 (保存功能)
            │       └── ...
            └── Task 2.5 (时区检测)

Task 1.3 (前端服务)
    ├── Task 1.5 (语言配置)
    └── Task 2.6 (代码迁移)
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 浏览器兼容性 | 部分浏览器不支持 Intl API | 提供降级方案，使用 ISO 格式 |
| 数据迁移失败 | 现有用户无偏好字段 | 新增列有默认值，自动填充 |
| 性能退化 | 日期格式化变慢 | 使用原生 API，性能有保障 |
| 回归问题 | 现有功能受影响 | 保留兼容层，逐步迁移 |
