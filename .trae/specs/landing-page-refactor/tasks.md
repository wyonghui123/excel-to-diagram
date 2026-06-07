# Tasks

## Phase 1: 创建新组件（不影响原文件）

- [x] Task 1: 创建 ArchWorkspaceNew.vue 新文件
  - [x] 1.1: 复制 ArchWorkspace.vue 内容到 ArchWorkspaceNew.vue
  - [x] 1.2: 修改页面标题为 "BIP应用架构管理"
  - [x] 1.3: 使用设计令牌替换硬编码颜色值
  - [x] 1.4: 使用设计令牌替换硬编码间距和圆角

- [x] Task 2: 创建常用产品版本组件
  - [x] 2.1: 创建 `FrequentProductsSection.vue` 组件
  - [x] 2.2: 创建 `ProductVersionCard.vue` 组件（合并到 FrequentProductsSection）
  - [x] 2.3: 实现空状态展示

- [x] Task 3: 创建访问记录管理 composable
  - [x] 3.1: 创建 `useFrequentProducts.js` composable
  - [x] 3.2: 实现访问记录存储到 localStorage
  - [x] 3.3: 实现访问记录读取和排序
  - [x] 3.4: 实现访问记录更新逻辑

- [x] Task 4: 创建数据概览统计组件
  - [x] 4.1: 创建 `StatsOverview.vue` 组件
  - [x] 4.2: 设计统计卡片布局
  - [x] 4.3: 实现数据加载和展示

## Phase 2: 后端 API 支持

- [x] Task 5: 添加统计数据 API
  - [x] 5.1: 后端添加 `/api/stats/overview` 接口
  - [x] 5.2: 返回产品数、版本数、领域数、业务对象数、关系数

## Phase 3: 集成测试（feature flag 控制）

- [x] Task 6: App.vue 添加 feature flag
  - [x] 6.1: 添加 `useNewLanding` 计算属性
  - [x] 6.2: 通过 URL 参数 `?newLanding=true` 切换新版本
  - [x] 6.3: 默认使用旧版本

- [x] Task 7: 架构数据管理支持参数接收
  - [x] 7.1: 接收 URL 参数 productId 和 versionId
  - [x] 7.2: 自动选中产品和版本（向后兼容：无参数时手动选择）
  - [x] 7.3: 自动加载架构数据

- [x] Task 8: 集成新组件到 ArchWorkspaceNew
  - [x] 8.1: 将 FrequentProductsSection 集成到 ArchWorkspaceNew
  - [x] 8.2: 将 StatsOverview 集成到 ArchWorkspaceNew
  - [x] 8.3: 调整整体布局和间距

## Phase 4: 验证与替换

- [ ] Task 9: 功能验证
  - [ ] 9.1: 验证旧版本功能正常（AA图导入、架构数据管理）
  - [ ] 9.2: 验证新版本功能正常
  - [ ] 9.3: 验证常用产品版本展示和跳转
  - [ ] 9.4: 验证数据概览统计正确性
  - [ ] 9.5: 验证向后兼容性

- [ ] Task 10: 替换原文件
  - [ ] 10.1: 备份原文件为 ArchWorkspace.backup.vue
  - [ ] 10.2: 将新版本内容写入 ArchWorkspace.vue
  - [ ] 10.3: 移除 feature flag
  - [ ] 10.4: 清理临时文件

# Task Dependencies

- [Task 2] depends on [Task 3]
- [Task 6] depends on [Task 1, Task 2, Task 4]
- [Task 7] depends on [Task 6]
- [Task 8] depends on [Task 2, Task 4]
- [Task 9] depends on [Task 7, Task 8]
- [Task 10] depends on [Task 9]

# Parallelizable Work

以下任务可以并行执行：
- Task 1, Task 2, Task 3, Task 4 (组件开发)
- Task 5 (后端 API)

# 安全检查点

每个 Phase 结束后需要验证：
- [ ] AA图导入功能正常
- [ ] 架构数据管理功能正常
- [ ] 原文件未被修改（Phase 1-3）
