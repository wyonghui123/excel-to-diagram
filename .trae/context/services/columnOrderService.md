# columnOrderService Context

> **目标文件**: `src/services/columnOrderService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

列顺序管理。维护表格列的显示顺序、宽度、可见性配置。

**架构位置**: P2 辅助 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getColumnConfig` | `(tableKey, userId) => Promise<Config>` | 获取列配置 |
| `saveColumnConfig` | `(tableKey, config) => Promise<void>` | 保存 |
| `resetColumnConfig` | `(tableKey) => Promise<void>` | 重置默认 |

## 3. 调用方

预期:
- `src/components/common/MetaTable.vue`
- `src/components/common/MetaListPage/`
- `src/components/common/TableHeaderFilter/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 用户自定义 vs 系统默认
- 列冻结(固定首列/末列)
- 列宽自适应
- 跨设备同步

## 6. 易错点

- ⚠️ **本地缓存**: 列顺序应在 localStorage 缓存
- ⚠️ **列添加**: 新列时的默认位置

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |