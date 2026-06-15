# enumService Context

> **目标文件**: `src/services/enumService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

枚举值管理。维护项目所有枚举字典,支持多级枚举、动态加载、国际化。

**架构位置**: P0 基础数据 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getEnums` | `() => Promise<Enum[]>` | 获取所有枚举 |
| `getEnumByCode` | `(code) => Promise<EnumItem[]>` | 按 code 获取枚举项 |
| `getEnumItem` | `(code, value) => EnumItem` | 客户端本地查 |
| `createEnum` | `(data) => Promise<Enum>` | 创建 |
| `updateEnum` | `(code, data) => Promise<Enum>` | 更新 |

## 3. 调用方

预期:
- `src/components/common/EnumSelect.vue`
- `src/components/common/EnumSearchHelp.vue`
- `src/components/common/ValueHelpField.vue`
- `src/components/common/ObjectPage/*`(字段编辑器)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 EnumSelect 验证 |

## 5. 边界场景

- 枚举项禁用(enable=false)
- 多级枚举(父子结构)
- 枚举值翻译(中英文)
- 枚举缓存失效

## 6. 易错点

- ⚠️ **客户端缓存**: 枚举应在启动时一次性加载
- ⚠️ **枚举变更**: 写操作后需全客户端刷新
- ⚠️ **enum_value 类型**: 可能是 string 或 number,需类型校验

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 Context | AI |