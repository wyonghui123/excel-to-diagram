# StateTransitionButton(s) Component Context

> **目标文件**: `src/components/bo/StateTransitionButton.vue`, `StateTransitionButtons.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

状态流转按钮。展示当前 BO 可执行的下一状态动作。

**架构位置**: BO 模块

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `currentState` | String | `''` | 当前状态 |
| `transitions` | Transition[] | `[]` | 可用流转 |
| `size` | String | `'medium'` | 按钮尺寸 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `transition` | `{to, action}` | 选中流转 |

## 3. 调用方(依赖)

- `src/services/boService.js`
- `src/components/bo/ActionExecutor.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 无可用流转
- 多个并发流转
- 权限拦截

## 6. 易错点

- ⚠️ **状态机**: 流转必须合法
- ⚠️ **按钮顺序**: 按业务重要性排序

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |