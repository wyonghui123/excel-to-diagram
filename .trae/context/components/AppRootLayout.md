# AppRootLayout Component Context

> **目标文件**: `src/components/common/AppRootLayout.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

根布局。最外层布局,处理主题、国际化、通知容器。

**架构位置**: 顶级布局,被 App.vue 直接使用

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `theme` | String | `'light'` | light / dark |
| `locale` | String | `'zh-CN'` | zh-CN / en-US |

### Slot
| Name | Description |
|------|-------------|
| `default` | 应用主体 |

## 3. 调用方(依赖)

- `src/components/NotificationContainer.vue`
- `src/utils/i18n.ts`
- `src/utils/theme.ts`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 主题切换
- 语言切换
- 通知中心挂载

## 6. 易错点

- ⚠️ **全局状态**: 必须在 setup 中初始化
- ⚠️ **主题持久化**: 应存 localStorage

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |