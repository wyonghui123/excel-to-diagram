# excelParser Context

> **目标文件**: `src/services/excelParser.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

Excel 解析器。解析 .xlsx 文件为 JSON,支持多 sheet、表头识别、类型推断。

**架构位置**: P3 数据导入 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `parseFile` | `(file) => Promise<Sheet[]>` | 解析文件 |
| `parseBuffer` | `(buffer) => Sheet[]` | 解析 Buffer |
| `detectHeaders` | `(rows) => HeaderInfo` | 自动识别表头 |
| `toJson` | `(sheet, options) => JsonData` | 转 JSON |

## 3. 调用方

预期:
- `src/components/common/ImportDialog/`
- `src/components/FeishuDataImport.vue`
- `src/services/archDataConverter.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 ImportDialog 验证 |

## 5. 边界场景

- 多 sheet
- 合并单元格
- 公式
- 空行/列
- 大文件

## 6. 易错点

- ⚠️ **大文件性能**: 用流式解析
- ⚠️ **类型推断**: 默认全 string,需明确转换
- ⚠️ **编码**: 兼容性

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |