# FeishuBotPanel Component Context

> **目标文件**: `src/components/FeishuBotPanel.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

飞书机器人面板。在应用内嵌入飞书机器人,支持消息收发、命令触发。

**架构位置**: 飞书集成面板

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `botId` | String | `''` | 机器人 ID |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `command` | `{cmd}` | 收到命令 |

## 3. 调用方(依赖)

- `src/services/feishuService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 断线重连
- 长消息分片
- 命令权限

## 6. 易错点

- ⚠️ **WS 重连**: 必须指数退避
- ⚠️ **消息顺序**: 保证一致性

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |