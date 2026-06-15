# archDataConverter Context

> **目标文件**: `src/services/archDataConverter.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

架构数据转换器。在多种架构数据格式间转换(excel/json/graphml 等)。

**架构位置**: P2 数据转换 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `excelToJson` | `(excelBuffer) => JsonData` | Excel → JSON |
| `jsonToExcel` | `(jsonData) => Buffer` | JSON → Excel |
| `jsonToGraphML` | `(json) => string` | JSON → GraphML |
| `graphMLToJson` | `(xml) => JsonData` | GraphML → JSON |

## 3. 调用方

预期:
- `src/components/common/ImportDialog/`
- `src/components/common/ExportDialog/`
- `src/components/FeishuDataImport.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 ImportDialog 验证 |

## 5. 边界场景

- 大文件(>10MB)
- 格式错误
- 部分数据缺失
- 编码问题(UTF-8 vs GBK)

## 6. 易错点

- ⚠️ **流式处理**: 大文件必须流式,不全加载内存
- ⚠️ **错误恢复**: 部分错误不应中断整体
- ⚠️ **编码检测**: 自动检测编码

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |