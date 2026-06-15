# Context 顶层索引

> **最后更新**: 2026-06-13
> **目的**: Agent 启动时快速定位项目上下文,最小化 Token 消耗
> **规范**: 所有 Context 文档遵循 [_TEMPLATE.md](./_TEMPLATE.md) 7 节 Schema

---

## 1. 子索引

| 目录 | 用途 | 文件数 | 索引 |
|------|------|--------|------|
| [utilities/](./utilities/) | 工具函数 | 2 | [_TEMPLATE.md](./utilities/_TEMPLATE.md) |
| [services/](./services/) | 业务服务 | 31 | [INDEX.md](./services/INDEX.md) |
| [components/](./components/) | Vue 组件 | 73 | [INDEX.md](./components/INDEX.md) |
| [architect/](./architect/) | 架构文档 | 3 | - |
| [developer/](./developer/) | 开发者指南 | 4 | - |
| [pm/](./pm/) | 产品文档 | 4 | - |
| [reviewer/](./reviewer/) | 审查规范 | 2 | - |
| [decisions/](./decisions/) | ADR 决策记录 | 4 | [README.md](./decisions/README.md) |

---

## 2. 顶层文档

| 文件 | 用途 |
|------|------|
| [_TEMPLATE.md](./_TEMPLATE.md) | 通用 Context 文档模板(7 节 Schema) |
| [README.md](./README.md) | Context 层说明 |
| [business-view.md](./business-view.md) | 业务视图概览 |
| [module-map.md](./module-map.md) | 模块地图 |

---

## 3. 关键 Context (Agent 必读)

按优先级排序,Agent 启动时按需加载:

### P0 - 基础设施

| Context | 文件 | 说明 |
|---------|------|------|
| httpClient | [utilities/httpClient.md](./utilities/httpClient.md) | 所有 HTTP 请求的统一入口 |
| authService | [services/authService.md](./services/authService.md) | 用户认证与会话管理 |
| permissionService | [services/permissionService.md](./services/permissionService.md) | 权限规则查询 |

### P0 - 核心数据模型

| Context | 文件 | 说明 |
|---------|------|------|
| metaService | [services/metaService.md](./services/metaService.md) | 元数据查询与变更 |
| boService | [services/boService.md](./services/boService.md) | 业务对象操作 |
| enumService | [services/enumService.md](./services/enumService.md) | 枚举值管理 |

### P0 - 应用主框架

| Context | 文件 | 说明 |
|---------|------|------|
| AADiagramApp | [components/AADiagramApp.md](./components/AADiagramApp.md) | 架构图主应用 |
| AppShell | [components/AppShell.md](./components/AppShell.md) | 应用 Shell |
| AppLayout | [components/AppLayout.md](./components/AppLayout.md) | 应用 Layout |

### P0 - YonDesign 组件(已测试)

| Context | 文件 | 测试用例数 |
|---------|------|-----------|
| AppButton | [components/AppButton.md](./components/AppButton.md) | 43 |
| AppInput | [components/AppInput.md](./components/AppInput.md) | 59 |
| AppSelect | [components/AppSelect.md](./components/AppSelect.md) | 50 |
| AppDatePicker | [components/AppDatePicker.md](./components/AppDatePicker.md) | 53 |
| AppCard | [components/AppCard.md](./components/AppCard.md) | 61 |
| AppModal | [components/AppModal.md](./components/AppModal.md) | 60 |
| AppTabs | [components/AppTabs.md](./components/AppTabs.md) | 42 |
| AppIcon | [components/AppIcon.md](./components/AppIcon.md) | 55 |
| AppCollapse | [components/AppCollapse.md](./components/AppCollapse.md) | 60 |
| AppAlert | [components/AppAlert.md](./components/AppAlert.md) | 17 |
| AppSideNav | [components/AppSideNav.md](./components/AppSideNav.md) | 21 |

---

## 4. 统计

| 维度 | 数量 |
|------|------|
| 总 Context 文件 | 120+ |
| utilities | 2 |
| services | 31 (INDEX + 30) |
| components | 73 (INDEX + 72) |
| architect | 3 |
| developer | 4 |
| pm | 4 |
| reviewer | 2 |
| decisions | 4 |
| 顶层文档 | 3 |
| **YonDesign 组件测试** | **13 个,561 用例全部通过** |

---

## 5. Agent 加载流程

```
Step 1: 读本文档 (本文件, ~2K)
Step 2: 按任务类型选择子索引
  ├── 工具函数 → utilities/
  ├── 服务层 → services/INDEX.md
  ├── 组件层 → components/INDEX.md
  └── 架构/产品 → architect/ pm/
Step 3: 读具体 Context 文档
```

---

## 6. 维护规则

1. 新增 Context 文档时,必须同步更新对应子索引
2. 子索引更新时,本文件的"统计"节需同步
3. Context 文档遵循 7 节 Schema,见 [_TEMPLATE.md](./_TEMPLATE.md)
4. 测试覆盖状态更新时,同步更新子索引和"关键 Context"表
