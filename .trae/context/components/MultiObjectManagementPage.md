# MultiObjectManagementPage Component Context

> **目标文件**: `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

多对象管理页。在同一页面管理多个对象类型的列表(类似数据模型的统一视图)。

**架构位置**: 高阶页面组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectTypes` | String[] | `[]` | 对象类型列表 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义内容 |
| `tab-<key>` | 每个 Tab 内容 |

## 3. 调用方(依赖)

- `src/components/common/MetaListPage/`
- `src/components/common/NavigationSourceInfo.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多对象类型并行加载
- Tab 切换性能

## 6. 易错点

- ⚠️ **缓存**: 切换 Tab 不应重载

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |