# keyTemplateService Context

> **目标文件**: `src/services/keyTemplateService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关键模板管理。维护数据模型中"关键字段"的模板,用于快速生成标准模型。

**架构位置**: P1 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `listTemplates` | `() => Promise<Template[]>` | 列出模板 |
| `getTemplate` | `(id) => Promise<Template>` | 详情 |
| `applyTemplate` | `(templateId, objectType) => Promise<void>` | 应用到对象类型 |
| `createTemplate` | `(data) => Promise<Template>` | 创建 |
| `deleteTemplate` | `(id) => Promise<void>` | 删除 |

## 3. 调用方

预期:
- `src/components/common/ObjectPage/`
- `src/components/ServiceModuleConfig.vue`
- `src/components/common/MetaListPage/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 应用模板冲突(已存在字段)
- 模板版本管理
- 模板参数化
- 应用回滚

## 6. 易错点

- ⚠️ **应用前预览**: 必须给用户预览再应用
- ⚠️ **冲突解决**: 字段冲突时的处理策略
- ⚠️ **事务性**: 应用必须支持回滚

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |