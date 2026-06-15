# baseService Context

> **目标文件**: `src/services/baseService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2(基础类)
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

通用服务基类。被所有具体 service 继承,提供通用 CRUD 与缓存能力。

**架构位置**: 基础类,所有 service 的父类

## 2. 关键类/方法

| 方法 | 签名 | 用途 |
|------|------|------|
| `BaseService` | class | 基类 |
| `this.list` | `(params) => Promise<T[]>` | 列表查询 |
| `this.get` | `(id) => Promise<T>` | 详情 |
| `this.create` | `(data) => Promise<T>` | 创建 |
| `this.update` | `(id, data) => Promise<T>` | 更新 |
| `this.delete` | `(id) => Promise<void>` | 删除 |
| `this.batchSave` | `(items) => Promise<BatchResult>` | 批量保存 |
| `this.cache` | `Map` | 实例缓存 |

## 3. 调用方(继承)

预期:
- metaService, objectTypeService, enumService, boService 等大部分 service 继承此类

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过子类间接验证 |

## 5. 边界场景

- 缓存失效策略
- 批量部分失败
- 并发同 key 写
- 大数据量分页

## 6. 易错点

- ⚠️ **缓存一致性**: 写后必须 invalidate
- ⚠️ **子类覆盖**: 子类覆盖方法必须保留 super 调用
- ⚠️ **错误传播**: 子类错误必须透传

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |