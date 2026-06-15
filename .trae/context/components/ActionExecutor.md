# ActionExecutor Component Context

> **目标文件**: `src/components/bo/ActionExecutor.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

动作执行器。执行 BO 动作(状态流转、提交、审批等)。

**架构位置**: BO 模块核心组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `boId` | String | `''` | 业务对象 ID |
| `action` | String | `''` | 动作 code |
| `params` | Object | `{}` | 动作参数 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `success` | `{result}` | 执行成功 |
| `fail` | `{error}` | 执行失败 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义执行 UI |

## 3. 调用方(依赖)

- `src/services/boService.js`
- `src/services/permissionService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 权限拒绝
- 状态机非法转换
- 执行超时

## 6. 易错点

- ⚠️ **幂等**: 必须支持重试
- ⚠️ **乐观锁**: 版本冲突处理

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |