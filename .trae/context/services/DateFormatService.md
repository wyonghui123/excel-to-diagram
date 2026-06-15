# DateFormatService Context

> **目标文件**: `src/services/DateFormatService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

日期格式化服务。统一处理日期/时间的格式化、解析、时区、国际化。

**架构位置**: P3 工具型 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `format` | `(date, pattern) => string` | 格式化 |
| `parse` | `(str, pattern) => Date` | 解析 |
| `toUTC` | `(date) => Date` | 转 UTC |
| `fromUTC` | `(date) => Date` | 转本地 |
| `formatRelative` | `(date) => string` | 相对时间(如"3 小时前") |

## 3. 调用方

预期:
- `src/components/common/AppDatePicker/`
- `src/components/common/DateTimePicker/`
- `src/components/MetaTable.vue`(时间列)
- `src/components/common/AuditLog/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 AppDatePicker 验证 |

## 5. 边界场景

- 跨年/跨月
- 闰年
- 夏令时
- 不同 locale
- 24h vs 12h

## 6. 易错点

- ⚠️ **时区**: 必须明确 UTC vs 本地
- ⚠️ **locale**: 使用 dayjs/luxon 等库
- ⚠️ **无效输入**: 必须容错

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |