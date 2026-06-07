# Service 索引（services/README.md）

> **目的**：索引所有 service 文档 + 测试 + 用途
> **创建日期**: 2026-06-06
> **维护者**: AI Agent (Trae)
> **关联文档**: [parent_spec_refs.md](file:///d:/filework/excel-to-diagram/docs/specs/parent_spec_refs.md)

---

## 1. Service 列表（按业务域）

### 1.1 useMetaList 相关（PR 4 重构）

| Service | 文档 | 测试 | 业务域 | PR |
|---------|------|------|:-----:|:-:|
| [keyTemplateService](./keyTemplateService.md) | ✅ | [15 PASS](file:///d:/filework/excel-to-diagram/src/services/__tests__/keyTemplateService.spec.js) | 键模板推导 | PR 4 |
| [draftPersistService](./draftPersistService.md) | ✅ | [17 PASS](file:///d:/filework/excel-to-diagram/src/services/__tests__/draftPersistService.spec.js) | 草稿持久化 | PR 4 |
| [useMetaList composable](./useMetaList.md) | ✅ | [75 PASS](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.*) | 元数据列表 | PR 4-5 |

### 1.2 已有 Service（无需重构）

| Service | 路径 | 用途 | 测试 |
|---------|------|------|------|
| `authService` | `src/services/authService.js` | 认证 | ✅ |
| `boService` | `src/services/boService.js` | BO CRUD | ✅ |
| `boService.advanced` | `src/services/bo/boBaseService.js` 等 5 个 | BO 子模块 | ✅ |
| `conditionExpressionService` | `src/services/conditionExpressionService.js` | 条件表达式 | ✅ |
| `dataTransformer` | `src/services/dataTransformer.js` | 数据转换 | ✅ |
| `dataValidator` | `src/services/dataValidator.js` | 数据验证 | ✅ |
| `enumService` | `src/services/enumService.js` | 枚举 | ✅ |
| `excelParser` | `src/services/excelParser.js` | Excel 解析 | ✅ |
| `filterService` | `src/services/filterService.js` | 过滤 | ✅ |
| `hierarchyService` | `src/services/hierarchyService.js` | 层级 | ✅ |
| `metaService` | `src/services/metaService.js` | 元数据 | ✅ |
| `objectTypeService` | `src/services/objectTypeService.js` | 实体类型 | ✅ |
| `permissionService` | `src/services/permissionService.js` | 权限 | ✅ |
| `serviceModuleDiagramBuilder` | `src/services/serviceModuleDiagramBuilder.js` | 服务模块图 | ✅ |
| `DateFormatService` | `src/services/DateFormatService.js` | 日期格式化 | ✅ |
| `archDataConverter` | `src/services/archDataConverter.js` | 架构数据转换 | ✅ |

## 2. Service 设计原则

### 2.1 分层

```
┌─────────────────────────────────────────┐
│ Page Layer (路由页面) — 编排、生命周期   │
├─────────────────────────────────────────┤
│ Composable Layer — 响应式 + 编排         │  ← useMetaList (300+ 行)
├─────────────────────────────────────────┤
│ Service Layer — 业务规则 + API 单一事实源│  ← 17+ service (50-500 行)
└─────────────────────────────────────────┘
```

### 2.2 Service 设计准则

1. **纯函数优先**（不依赖 Vue 响应式）
2. **注入式依赖**（boService / callPost / showMessage 注入）
3. **错误返回 `{success, error}`**（非抛异常）
4. **响应式更新由调用方负责**（service 不直接 set ref）
5. **测试覆盖率 ≥ 90%**（CI 强制）

### 2.3 Service 文档模板

每个 service 都应有：

```markdown
# serviceName

> 服务路径 / 创建日期 / 创建者 / 关联 PR / 关联 spec / 测试覆盖

## 1. 服务目的
## 2. 公开 API
### 2.1 functionName(...)
## 3. 业务规则
## 4. 注入式依赖
## 5. 单测矩阵
## 6. 调用方
## 7. 设计决策
## 8. 错误处理
## 9. 未来扩展
## 10. 变更记录
```

## 3. 测试规范

### 3.1 测试文件命名

- `src/services/__tests__/{serviceName}.spec.js`
- 100% 覆盖 public API
- 包含正向 + 反向 + 边界条件

### 3.2 测试结构

```javascript
import { describe, it, expect, vi } from 'vitest'
import { publicApi } from '@/services/serviceName'

describe('serviceName', () => {
  describe('functionName', () => {
    it('TC-1: 正向用例', () => { ... })
    it('TC-2: 反向用例', () => { ... })
    it('TC-3: 边界条件', () => { ... })
  })
})
```

### 3.3 覆盖率要求

- Statements ≥ 90%
- Branches ≥ 85%
- Functions ≥ 90%
- Lines ≥ 90%

## 4. v3 引擎迁移路径

### 4.1 v1 (HTTP) → v3 (GraphQL) 迁移

| Service | v1 实现 | v3 迁移 |
|---------|---------|---------|
| `boService` | HTTP POST `/api/v2/action/{name}` | GraphQL `query / mutation` |
| `metaService` | HTTP GET `/api/v2/meta/...` | GraphQL `meta` field |
| `filterService` | 客户端转换 + 拼接参数 | GraphQL `where` clause |
| `conditionExpressionService` | 客户端 DSL | GraphQL filter expression |

### 4.2 迁移策略

- **阶段 1**（v1.0-PR 4-7）：保守衔接，**0d 切换**
- **阶段 2**（PR 9-10）：CDC + ETag 桥接，**3-5d**
- **阶段 3**（PR 11+）：完全 GraphQL 切换，**7-10d**

详见 [spec-fr-ui-003-004-005 v1.5.0 §18](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md)。

## 5. 维护规则

### 5.1 添加新 Service 时

1. 在 `src/services/{name}.js` 创建
2. 在 `src/services/__tests__/{name}.spec.js` 创建测试
3. 在 `docs/services/{name}.md` 创建文档
4. 在本 README.md 索引中添加
5. 覆盖率 ≥ 90%

### 5.2 修改现有 Service 时

1. 优先纯函数设计（不破坏可测试性）
2. 保持 API 向后兼容（deprecate 而非删除）
3. 更新文档 + 测试
4. 重要变更记录到文档变更记录

### 5.3 删除 Service 时

1. 先确认 0 引用（grep）
2. 删除 service + 测试 + 文档
3. 更新本 README.md 索引

## 6. 关键决策

| ID | 决策项 | 推荐答案 |
|----|-------|---------|
| D-SVC-1 | service 内是否触发响应式？ | ❌ 否（保持纯函数）|
| D-SVC-2 | service 内是否调用其他 service？ | ✅ 是（同层调用）|
| D-SVC-3 | service 内是否 import composable？ | ❌ 否（避免循环依赖）|
| D-SVC-4 | service 文档模板是否强制？ | ✅ 是（统一规范）|
| D-SVC-5 | service 测试覆盖率阈值？ | 90%（CI 卡点）|

## 7. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；建立 service 索引 + 17 已有 + 3 PR 4 新增 | AI Agent (Trae) |
