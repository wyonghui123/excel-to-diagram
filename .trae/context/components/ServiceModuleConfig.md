# ServiceModuleConfig Component Context

> **目标文件**: `src/components/ServiceModuleConfig.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

服务模块配置。展示与配置服务模块(如元数据同步规则、模板应用等)。

**架构位置**: ConfigApp 内部模块

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `moduleId` | String | `''` | 模块 ID |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `save` | `{config}` | 保存 |
| `reset` | - | 重置 |

## 3. 调用方(依赖)

- `src/services/keyTemplateService.js`
- `src/services/objectTypeService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 配置变更影响
- 回滚

## 6. 易错点

- ⚠️ **二次确认**: 配置变更必须确认

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |