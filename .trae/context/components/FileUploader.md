# FileUploader Component Context

> **目标文件**: `src/components/FileUploader.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

文件上传组件。支持拖拽上传、多文件、进度条、格式校验。

**架构位置**: 通用上传组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `accept` | String | `''` | 接受类型(如 `.xlsx,.csv`) |
| `multiple` | Boolean | `false` | 多文件 |
| `maxSize` | Number | `10` | 单文件大小限制(MB)
| `uploadUrl` | String | `''` | 上传 URL(可选,默认走 service) |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `upload-success` | `{file, response}` | 成功 |
| `upload-error` | `{file, error}` | 失败 |
| `progress` | `{file, percent}` | 进度 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义触发区 |

## 3. 调用方(依赖)

- `src/services/excelParser.js`(可选)
- `src/services/feishuService.js`(可选)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大文件(>50MB)
- 多文件并发
- 网络中断重传
- 文件类型伪造

## 6. 易错点

- ⚠️ **类型校验**: 必须前端校验 MIME 与扩展名
- ⚠️ **大小限制**: 必须前端 + 服务端双校验
- ⚠️ **进度**: 必须显示真实进度(避免假进度)

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |