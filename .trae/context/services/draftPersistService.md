# draftPersistService Context

> **目标文件**: `src/services/draftPersistService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

草稿持久化。自动保存用户的未提交表单数据,防止意外丢失。

**架构位置**: P2 辅助 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `saveDraft` | `(key, data) => Promise<void>` | 保存草稿 |
| `loadDraft` | `(key) => Promise<Draft>` | 加载 |
| `clearDraft` | `(key) => Promise<void>` | 清除 |
| `listDrafts` | `() => Promise<Draft[]>` | 列出所有草稿 |

## 3. 调用方

预期:
- `src/components/common/MetaForm.vue`
- `src/components/common/ObjectPage/`
- `src/components/bo/ActionExecutor.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 草稿过期(>7 天自动清除)
- 草稿冲突(多设备)
- 草稿大小(>1MB 警告)
- 草稿恢复提示

## 6. 易错点

- ⚠️ **表单提交后清除**: 提交成功必须清草稿
- ⚠️ **敏感字段**: 密码类字段不应入草稿
- ⚠️ **localStorage vs 服务端**: 选哪种持久化

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |