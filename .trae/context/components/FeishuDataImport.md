# FeishuDataImport Component Context

> **目标文件**: `src/components/FeishuDataImport.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

飞书数据导入。从飞书电子表格导入数据到本系统。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `targetObjectType` | String | `''` | 目标对象类型 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `success` | `{count}` | 导入成功 |
| `cancel` | - | 取消 |

### Slot
无

## 3. 调用方(依赖)

- `src/services/feishuService.js`
- `src/components/DataPreview.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 feishu flow 验证 |

## 5. 边界场景

- 飞书表格权限不足
- 大量数据导入
- 字段类型不匹配

## 6. 易错点

- ⚠️ **OAuth**: 必须走飞书 OAuth 鉴权
- ⚠️ **进度**: 必须显示导入进度

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |