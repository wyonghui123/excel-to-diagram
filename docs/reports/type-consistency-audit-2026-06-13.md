# 类型一致性审计报告 - 2026-06-13 (W4 PR-4.3)

## 扫描工具

- `d:/filework/scan_types.py`（~50 行）
- 范围：`src/` 下所有 `.ts` 和 `.js` 文件

## 扫描结果

| 指标 | 数值 | 评估 |
|------|:---:|------|
| `.ts` 文件数 | 13 | 🟡 少数 |
| `.js` 文件数 | 313 | 🟢 主流 |
| TS:JS 比例 | **4.15%** | 🔴 极低（项目主体是 JS） |
| 显式 `any` 使用 | 7 | 🟡 集中在 3 文件 |
| tsconfig strict | **未启用** | 🟡 不强制类型 |
| 共享类型文件 | ❌ 缺失 | 🟢 本 PR 新增 |

## 显式 any 分布

| 文件 | 数量 | 状态 |
|------|:---:|------|
| `src/composables/useOverlaps.ts` | 5 | 🔴 5 处需细化 |
| `src/stores/appStore.ts` | 1 | 🟡 1 处 |
| `src/stores/chartArchDataStore.ts` | 1 | 🟡 1 处 |

**建议**（不在本 PR 范围）：
- `useOverlaps.ts` 5 处 `any` 应改为 `unknown` + 类型守卫
- 2 个 store 中的 `any` 可改为 `Record<string, unknown>` 或具体类型

## 本 PR 改动

### 新增文件
- ✅ `src/types/common.d.ts`（~150 行）- 共享类型定义

### 共享类型覆盖范围

| 模块 | 类型 |
|------|------|
| 基础 | `ID`, `Code`, `ISODateString`, `Nullable<T>`, `Optional<T>` |
| 业务对象 | `Domain`, `SubDomain`, `ServiceModule`, `BusinessObject`, `Relationship` |
| 联合类型 | `AnyBusinessObject = Domain \| SubDomain \| ...` |
| 图表配置 | `ChartConfig`, `LayoutConfig`, `ColorConfig` |
| API | `ApiResponse<T>`, `PaginatedResponse<T>`, `PaginationParams` |
| 审计 | `AuditLogEntry` |
| 用户 | `UserContext` |
| 选中配置 (FR-008 v2) | `SelectionConfig`, `SelectionSource` |

### 使用示例

**`.ts` 文件中**：
```ts
import type { BusinessObject, ApiResponse } from '@/types/common'

async function fetchBO(id: number): Promise<ApiResponse<BusinessObject>> {
  return await httpClient.get(`/api/v2/bo/business_object/${id}`)
}
```

**`.js` 文件中（JSDoc）**：
```js
/** @type {import('@/types/common').BusinessObject} */
const bo = await boService.findById('business_object', 1)
```

## 后续 W5+ 建议

1. **渐进式 TS 迁移**（每个 store 1 PR，1 个 release 1-2 个）
   - 优先级：`composables/useMetaList.js` → `useMetaList.ts`（最常被引用）
   - 优先级：`stores/diagramConfigStore.js` → `diagramConfigStore.ts`（W3 已重构，最易转换）
2. **启用 strict 模式**（tsconfig.json）
3. **用 `unknown` 替代 `any`**（特别是 `useOverlaps.ts` 5 处）
4. **CI 加 `tsc --noEmit` 检查**（渐进式，不必 strict）

## 测试

- ✅ 仅文档与类型文件改动
- ✅ 无运行时影响
- ✅ 不需要新测试
