# metaTransformService Context

> **目标文件**: `src/services/metaTransformService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据转换服务。在不同元数据格式间转换(内部模型 ↔ 外部格式)。

**架构位置**: P2 数据转换 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `toInternal` | `(external) => InternalModel` | 外部 → 内部 |
| `toExternal` | `(internal) => ExternalFormat` | 内部 → 外部 |
| `transformBatch` | `(items, transformer) => Items` | 批量转换 |

## 3. 调用方

预期:
- `src/services/metaService.js`
- `src/services/archDataConverter.js`
- `src/components/common/ImportDialog/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 字段映射缺失
- 类型不兼容
- 数据丢失告警

## 6. 易错点

- ⚠️ **字段映射表**: 必须集中维护
- ⚠️ **数据丢失**: 必须记录并提示
- ⚠️ **版本兼容**: 旧版数据兼容

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |