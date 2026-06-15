# feishuService Context

> **目标文件**: `src/services/feishuService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

飞书集成服务。与飞书开放平台对接(消息推送、数据导入、用户同步)。

**架构位置**: P3 集成 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `sendMessage` | `(chatId, msg) => Promise<void>` | 发消息 |
| `importData` | `(spreadsheetToken) => Promise<Sheet[]>` | 导入飞书表格 |
| `syncUser` | `(userId) => Promise<User>` | 同步用户 |
| `getAuthUrl` | `(redirectUri) => string` | 鉴权 URL |

## 3. 调用方

预期:
- `src/components/FeishuBotPanel.vue`
- `src/components/FeishuDataImport.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 FeishuBotPanel 验证 |

## 5. 边界场景

- 鉴权 token 过期
- 飞书 API 限流
- 网络中断
- 数据格式差异

## 6. 易错点

- ⚠️ **鉴权**: 必须管理 access_token
- ⚠️ **回调**: 必须验证回调签名
- ⚠️ **数据转换**: 飞书字段与内部模型差异

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |