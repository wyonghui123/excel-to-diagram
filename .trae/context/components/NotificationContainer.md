# NotificationContainer Component Context

> **目标文件**: `src/components/NotificationContainer.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

通知容器。全局通知(Message/Notification)挂载点。

**架构位置**: AppRootLayout 内部

## 2. Props/Emit/Slot

### Props
无(基于全局 store)

### Slot
无

## 3. 调用方(依赖)

- `src/stores/notification.js`
- Element Plus `<el-notification>` / `<el-message>`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 70%

## 5. 边界场景

- 大量通知同时弹出
- 通知持久化
- 通知优先级

## 6. 易错点

- ⚠️ **去重**: 相同通知去重
- ⚠️ **关闭**: 自动关闭 + 手动关闭
- ⚠️ **位置**: 右上角常用

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |