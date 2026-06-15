# boService Context

> **目标文件**: `src/services/boService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

业务对象(Business Object)操作。处理 BO 状态流转、动作执行、版本管理。

**架构位置**: P0 核心业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getBoById` | `(id) => Promise<Bo>` | 详情 |
| `listBos` | `(params) => Promise<Bo[]>` | 列表 |
| `createBo` | `(data) => Promise<Bo>` | 创建 |
| `updateBo` | `(id, data) => Promise<Bo>` | 更新 |
| `executeAction` | `(boId, action, params) => Promise<Bo>` | 执行 BO 动作 |
| `getBoHistory` | `(id) => Promise<History[]>` | 历史 |

## 3. 调用方

预期:
- `src/components/bo/ActionExecutor.vue`
- `src/components/bo/StateTransitionButton(s).vue`
- `src/components/bo/AssociationCell.vue`
- `src/stores/bo.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 ActionExecutor 验证 |

## 5. 边界场景

- 状态机非法转换
- 并发动作执行(乐观锁)
- 动作权限校验
- 动作回滚
- 大对象关联加载

## 6. 易错点

- ⚠️ **动作幂等性**: 客户端应支持重试
- ⚠️ **乐观锁**: updateBo 必须传 version
- ⚠️ **关联预加载**: 详情查询需明确 `with` 参数

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 Context | AI |