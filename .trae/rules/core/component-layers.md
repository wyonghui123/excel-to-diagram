# 组件分层架构

> 最后更新: 2026-06-07 | 状态: 活跃
> 拆分自 project_rules.md（原第 419-479 行）

## 三层组件体系

根据 `docs/architecture/01-principles.md` 中的设计原则，我们建立了**三层组件体系**：

### 1. 页面组件层（Page Layer）

**定位**：面向业务对象的完整页面组件，YAML 驱动

| 组件 | 说明 | 驱动来源 |
|------|------|---------|
| **MetaListPage** | 列表页 | YAML: `ui_view_config.list` |
| **DetailPage** | 详情页 | YAML: `detail.tabs` |
| **AssociationPanel** | 关联面板 | YAML: `associations` |

**使用原则**：

```
[OK] 正确：一个业务对象一个页面，YAML 驱动
<MetaListPage object-type="user" :enable-detail="true" />

[X] 错误：重复实现，不一致
<FilterBar /> + <MetaTable /> + <AddDialog /> + <RoleDialog />
```

### 2. 业务组件层（Business Layer）

**定位**：封装了业务逻辑的基础组件，介于页面组件和基础组件之间

| 组件 | 说明 |
|------|------|
| **MetaTable** | 业务表格 |
| **MetaForm** | 业务表单 |
| **MetaDialog** | 业务弹窗 |

### 3. 基础组件层（Base Layer）

**定位**：纯 UI 组件，不包含业务逻辑，遵循 YonDesign 规范

详见 `src/styles/COMPONENT_STANDARDS.md`

## 组件使用决策树

```
需要开发新功能/页面吗？
    |
    v
是否业务对象页面？
    |
    +-- 是 -> 使用 MetaListPage / DetailPage（YAML 驱动）
    |
    \-- 否 -> 需要自定义组件吗？
              |
          +-- 否 -> 使用 App* 基础组件
          |         \-- AppButton、AppModal 等
          |
          \-- 是 -> 需要封装业务逻辑吗？
                    |
                +-- 否 -> 使用 el-* 组件（全局样式已覆盖）
                |
                \-- 是 -> 创建 Meta* 业务组件
```

**详细规范**：`src/styles/COMPONENT_LAYER_GUIDE.md`

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 从 project_rules.md 拆分 |
