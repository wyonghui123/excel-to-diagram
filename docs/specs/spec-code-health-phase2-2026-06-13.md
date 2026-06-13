# Spec: Code Health 优化 Phase 2 — 性能/可维护性/依赖治理

> 基于 2026-06-13 全面代码分析，聚焦非安全类问题（安全类单独 spec）
> 前序: spec-code-health-2026-06-12-v1.0.md (W1-W7 已完成)

---

## 1. Background & Objectives

### 1.1 Background

W1-W7 Code Health 已完成：shallowRef 工具创建、inflightCache GC、mermaid 上限、tabStore sessionStorage 迁移、bo_api_preview 拆分、i18n 基础设施、ESLint 加严等。但深度分析发现以下系统性问题尚未解决：

- **前端性能**：29 处 deep watcher、11 处 ref() 应改 shallowRef()、4 处内存泄漏、1 处 computed 聚合 22 个 ref
- **后端性能**：6 处 N+1 查询、1 处全量加载内存分页、1 处生产调试文件写入、page_size 无上限
- **可维护性**：6 个 God 文件（5080/2531/2398/2248/2030/1869 行）、54 行 _api_error 重复、20+ 处 _data_source 模式重复、40+ 处裸 except
- **依赖/构建**：xlsx 许可证风险 + 全量导入 300KB、vite fallback 策略导致 chunk 膨胀、274 处 !important CSS

### 1.2 Business Objectives

- 图表页面交互延迟降低 50%（当前 deep watcher + JSON.stringify 链路 5-13ms/次）
- 列表页大数据量（200+ 行）时 Proxy 创建开销从 5-15ms 降至 <1ms
- 消除内存泄漏（MermaidComponent/useTooltip 事件监听器累积）
- God 文件拆分后单文件 < 800 行，提升可维护性
- 依赖治理后 bundle 减少 ~150KB gzip

### 1.3 User / Stakeholder Objectives

- **开发者**：修改导入逻辑不影响导出；新增 API 模块不需要复制 _data_source 模板
- **用户**：图表拖拽/选择范围时无卡顿；列表页滚动流畅；长时间使用不因内存泄漏变慢

---

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence                          |
| ----------------------- | ---------- | --------------------------------- |
| Business                | Yes        | 性能直接影响用户体验和留存         |
| User/Stakeholder        | Yes        | 开发者维护效率、用户交互流畅度     |
| Solution                | Yes        | shallowRef 迁移、God 文件拆分等   |
| Functional              | Yes        | 内存泄漏修复、page_size 上限等     |
| Nonfunctional           | Yes        | 性能（延迟/内存）、可维护性        |
| External Interface      | No         | 不涉及外部接口变更                 |
| Transition              | Yes        | xlsx→exceljs 迁移、CSS 拆分       |

---

## 3. Functional Requirements

### FR-001: MermaidComponent 旧版事件监听器清理

- **Description**: 删除 MermaidComponent.vue 行 1411-1466 的旧版 zoom/drag 代码（4 个 `document.addEventListener` 匿名函数），这些代码已被 `useInteraction.js` 替代但未清理
- **Acceptance Criteria**:
  - 旧版 `document.addEventListener('wheel/mousedown/mousemove/mouseup', ...)` 全部删除
  - 缩放/拖拽功能仍通过 `useInteraction.js` 正常工作
  - 组件卸载后无残留全局事件监听器
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 — MermaidComponent.vue L1411-1466

### FR-002: useTooltip 事件监听器清理机制

- **Description**: useTooltip.js 的 `addMouseOverTooltips` 为每个 label/path 添加 4 个事件监听器（共 1600+ 个），但无清理函数。图表重渲染时旧监听器泄漏
- **Acceptance Criteria**:
  - `addMouseOverTooltips` 返回清理函数
  - MermaidComponent 在 `renderMermaid` 前调用清理函数
  - 5 次重渲染后监听器数量不累积（验证：`getEventListeners(svg)` 不增长）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 — useTooltip.js L210-288, L449-460

### FR-003: annotationOverlay 事件监听器清理机制

- **Description**: annotationOverlay.js 多处 `addEventListener` 使用匿名函数，无清理
- **Acceptance Criteria**:
  - 所有 addEventListener 改为具名函数或返回清理函数
  - MermaidComponent 卸载或重渲染时清理标注相关监听器
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 — annotationOverlay.js L176-328

### FR-004: FilterBar.vue 全局 click 监听器生命周期管理

- **Description**: FilterBar.vue L318 在模块顶层添加 `document.addEventListener('click', ...)`，组件卸载时无法清理
- **Acceptance Criteria**:
  - 监听器移到 `onMounted` 中添加、`onUnmounted` 中移除
  - 使用具名函数引用
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 — FilterBar.vue L318

### FR-005: useSelectionConfig popstate 监听器清理

- **Description**: useSelectionConfig.js L90 添加 `window.addEventListener('popstate', handler)` 但注释说 "Optional: cleanup on unmount" 实际未清理
- **Acceptance Criteria**:
  - 在 composable 返回的 `cleanup` 函数中移除监听器
  - 或在调用方的 `onUnmounted` 中清理
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — useSelectionConfig.js L90

### FR-006: page_size 上限校验

- **Description**: bo_api.py L333 直接取用户输入的 `page_size` 无上限，攻击者可设 `page_size=999999` 导致 OOM
- **Acceptance Criteria**:
  - 所有接受 `page_size` 参数的端点增加上限校验（MAX_PAGE_SIZE = 500）
  - 超过上限自动截断为 MAX_PAGE_SIZE
  - 影响端点：bo_api.py L333, L695, L724
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 — bo_api.py

### FR-007: audit_interceptor 生产调试代码移除

- **Description**: audit_interceptor.py L87-156 有 5 处 `open(r'd:\filework\_audit_debug.log', 'a')` 文件写入，每次 BO 操作触发 2-3 次，每秒约 20 次无用 I/O
- **Acceptance Criteria**:
  - 删除所有 `open(r'd:\filework\_audit_debug.log', ...)` 调试代码
  - L112 的 `logger.error` 改为 `logger.debug`（非错误场景不应使用 ERROR 级别）
  - 如需临时调试，通过环境变量 `AUDIT_DEBUG=true` 控制
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 — audit_interceptor.py L87-156

### FR-008: audit_api 趋势查询 N+1 修复

- **Description**: audit_api.py L482-490 循环内逐天执行 `SELECT COUNT(*)` 查询（最多 30 次），应改为单条 `GROUP BY DATE(created_at)` 查询
- **Acceptance Criteria**:
  - 趋势数据通过单条 SQL 查询获取
  - 结果格式不变（日期→计数的映射）
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — audit_api.py L482-490

### FR-009: bo_api 权限批量查询修复

- **Description**: bo_api.py L2199-2208 循环内逐条查询权限 ID + 逐条 INSERT，50 个权限 = 100 次 SQL
- **Acceptance Criteria**:
  - 先批量 `SELECT id FROM permissions WHERE code IN (...)`
  - 再批量 `executemany INSERT`
  - 权限数量 50 时 SQL 次数从 100 降至 2
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — bo_api.py L2199-2208

### FR-010: audit_service 全量加载改为数据库分页

- **Description**: audit_service.py L567-588 先 `find()` 加载全部记录到内存，再 Python 层分页。数据量大时 OOM
- **Acceptance Criteria**:
  - 分页参数（page/page_size）下推到 SQL `LIMIT/OFFSET`
  - Python 层不再做内存分页
  - 迁移后 `total` 计数通过 `COUNT(*)` 查询获取
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — audit_service.py L567-588

### FR-011: _api_error / _api_success 提取共享模块

- **Description**: 3 个文件完全相同的 `_api_error` 和 `_api_success` 函数（54 行重复），其他 API 文件内联了类似逻辑
- **Acceptance Criteria**:
  - 创建 `meta/api/_response_helpers.py`，包含 `api_error()` 和 `api_success()`
  - export_import_api.py、manage_api.py、enum_api.py 改为导入共享函数
  - 其他 API 文件逐步迁移（非阻塞）
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — 3 个 API 文件 L39/137/155

### FR-012: _get_db_path() 统一

- **Description**: 9 个文件各自定义 `_get_db_path()` 函数，实现相同但返回类型不一致（str vs Path）
- **Acceptance Criteria**:
  - 在 `meta/core/datasource.py` 中添加 `get_default_db_path() -> Path`
  - 9 个文件改为导入使用
  - 返回类型统一为 `Path`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — 9 个文件

### FR-013: 裸 except 替换

- **Description**: 后端 40+ 处裸 `except:` 会捕获 `KeyboardInterrupt`/`SystemExit`，3 处生产代码 `except Exception as e: pass` 完全静默
- **Acceptance Criteria**:
  - 所有 `except:` 替换为 `except Exception:` 或更具体类型
  - 3 处 `except Exception as e: pass` 至少添加 `logger.warning(str(e))`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码分析 — 40+ 处

### FR-014: xlsx 迁移到 exceljs

- **Description**: xlsx@0.18.5 社区版已停更 + 非标准许可证 + `import * as XLSX` 全量引入 300KB gzip。实际仅使用 6 个函数
- **Acceptance Criteria**:
  - 替换为 `exceljs`（MIT 许可，~150KB gzip）
  - excelParser.js 读取功能用 exceljs API 重写
  - ImpactPreview.vue 导出功能用 exceljs API 重写
  - 所有现有测试通过
- **Priority**: Should
- **Type Mapping**: Functional / Transition
- **Source**: 依赖分析 — package.json + 2 个导入文件

### FR-015: vite manualChunks fallback 修复

- **Description**: vite.config.js L54 将所有未匹配的 node_modules 包归入 `vendor-mermaid`，导致 mermaid chunk 膨胀且缓存失效
- **Acceptance Criteria**:
  - 新增 `vendor-misc` chunk 用于未分类包
  - mermaid chunk 仅包含 mermaid 及其直接依赖
  - 构建后验证各 chunk 大小合理
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 构建分析 — vite.config.js L54

### FR-016: MermaidComponent.css 拆分 + mojibake 修复

- **Description**: 759 行单文件、274 处 `!important`、2 处 mojibake 乱码注释
- **Acceptance Criteria**:
  - 拆分为 4 个文件：基础布局、serviceModule 样式、businessObject 样式、zoneDivider 样式
  - 修复 L732/L745 的 mojibake 注释
  - MermaidComponent.vue 通过 `@import` 引入
  - 视觉回归测试通过
- **Priority**: Could
- **Type Mapping**: Functional / Transition
- **Source**: CSS 分析 — MermaidComponent.css

### FR-017: 未使用依赖清理

- **Description**: `@vitejs/plugin-react`（Vue 项目不需要）和 `concurrently`（无任何文件引用）为残留依赖
- **Acceptance Criteria**:
  - `npm uninstall @vitejs/plugin-react concurrently`
  - 构建正常通过
- **Priority**: Could
- **Type Mapping**: Functional
- **Source**: 依赖分析 — package.json

---

## 4. Nonfunctional Requirements

### NFR-001: 响应式性能 — shallowRef 迁移

- **Description**: 以下 `ref()` 应改为 `shallowRef()` 以避免深度 Proxy 开销
- **Measurement**: 改造前后用 `performance.now()` 测量 `loadList()` / `updateCenterScopeMarkers()` 耗时，目标降低 80%
- **Priority**: Must
- **Source**: 性能分析

**必须改造项（P1）**:

| 文件 | 行号 | 当前 | 目标 |
|------|------|------|------|
| diagramConfigStore.js | L25 | `ref({domains: new Map(), ...})` | `shallowRef()` |
| diagramConfigStore.js | L38 | `ref({})` customColors | `shallowRef()` |
| diagramConfigStore.js | L47 | `ref({...})` layoutControlConfig | `shallowRef()` |
| useMetaList.js | L163 | `ref([])` data | `shallowRef([])` |
| useMetaList.js | L128 | `ref([])` columns | `shallowRef([])` |
| useMetaList.js | L131 | `ref([])` filterFields | `shallowRef([])` |
| useMetaList.js | L1434 | `ref(new Map())` draftValues | `shallowRef(new Map())` |
| useObjectIdentity.js | L13 | `ref(new Map())` | `useShallowMapRef()` |
| useFilterFlow.js | L51 | `ref(new Map())` | `useShallowMapRef()` |

**改造后注意事项**:
- `shallowRef` 只追踪 `.value` 引用变化，内部修改需手动 `triggerRef()`
- `draftValues` 的 `new Map(draftValues.value)` 复制模式可保留（替换引用即可触发更新）
- `centerScopeMarkers` 更新时需替换整个对象引用，不能 `.set()` 后期望自动响应

### NFR-002: Deep Watcher 优化

- **Description**: 29 处 `deep: true` watcher 中，以下为高风险项需优化
- **Measurement**: watcher 触发到回调执行完成的耗时，目标从 5-13ms 降至 <1ms
- **Priority**: Must
- **Source**: 性能分析

**必须优化项**:

| 文件 | 行号 | 问题 | 方案 |
|------|------|------|------|
| MermaidComponent.vue | L717-760 | deep watcher + JSON.stringify 比较 | 移除 deep，改用 renderHash 或精确属性监听 |
| useDiagramData.js | L215-238 | diagramConfig computed 聚合 22 个 ref | 拆分为独立 watcher 直接引用 store 属性 |
| useDiagramData.js | L1959-1973 | watch + watchEffect 双重触发 | 删除 watchEffect，合并到 watch 回调 |
| MetaForm.vue | L223+227+257 | 同一 formData 3 个 deep watcher | 合并为 1 个 watcher 或改用 watchEffect |

**diagramConfig computed 拆分方案**:

当前：
```javascript
const diagramConfig = computed(() => ({
  chartType: configStore.chartType,
  colorScheme: configStore.colorScheme,
  // ... 22 个属性
}))
```

目标：直接在 watcher 中引用 store 属性：
```javascript
// 颜色相关
watch([() => configStore.colorScheme, () => configStore.customColors], () => {
  if (previewData.value) updateColorsOnly()
})

// 布局相关
watch([() => configStore.chartType, () => configStore.layoutEngine], () => {
  if (previewData.value) generateDiagram()
})
```

### NFR-003: 内存泄漏消除

- **Description**: 前端 4 处事件监听器泄漏 + 1 处 setInterval 泄漏
- **Measurement**: Chrome DevTools Memory 面板，路由切换 10 次后 DOM 节点数和事件监听器数不增长
- **Priority**: Must
- **Source**: 性能分析

| 泄漏点 | 类型 | 修复方案 |
|--------|------|---------|
| MermaidComponent.vue L1411-1466 | 4 个 document.addEventListener 匿名函数 | 删除旧代码（已有 useInteraction 替代） |
| useTooltip.js L210-288 | N×4 个 label/path addEventListener | 返回清理函数，渲染前调用 |
| annotationOverlay.js L176-328 | 多个 addEventListener | 返回清理函数 |
| FilterBar.vue L318 | document.addEventListener 模块顶层 | 移到 onMounted/onUnmounted |
| ImportDialog.vue L513 | setInterval 无卸载清理 | 添加 onUnmounted 清理 |

### NFR-004: God 文件拆分 — 后端

- **Description**: 以下文件超过 800 行，需按职责拆分
- **Measurement**: 拆分后单文件 < 800 行，职责单一
- **Priority**: Should
- **Source**: 可维护性分析

| 文件 | 当前行数 | 拆分方案 |
|------|---------|---------|
| import_export_service.py | 5080 | ExportService (~1500) + ImportService (~1300) + HierarchyQueryService (~500) + ExcelStyleService (~400) + FieldMappingService (~500) + DataEnrichmentService (~300) |
| bo_api.py | 2531 | 继续拆分：bo_api_query.py、bo_api_permission.py（preview 已拆分） |
| action_executor.py | 2398 | 按 ActionType 拆分：crud_executor.py、batch_executor.py、business_executor.py + 引入 dispatch table |
| query_service.py | 1710 | 按查询类型拆分：filter_query.py、aggregate_query.py、permission_query.py |

### NFR-005: God 文件拆分 — 前端

- **Description**: 以下前端文件超过 800 行，需按职责拆分
- **Measurement**: 拆分后单文件 < 800 行
- **Priority**: Should
- **Source**: 可维护性分析

| 文件 | 当前行数 | 拆分方案 |
|------|---------|---------|
| useMetaList.js | 2030 | useMetaListCore (~400) + useListFilter (~300) + useListPagination (~150) + useListSelection (~250) + useListAction (~200) + useInlineEdit (~400) + useMetaTransform (~300) |
| useDiagramData.js | 2248 | useDiagramDataCore (~500) + useDiagramPreset (~400) + useDiagramCategoryTree (~300) + useDiagramRender (~500) |
| MermaidComponent.vue | 1869 | 抽取 useMermaidExport composable (~400) + 交互状态合并到 useInteraction |
| MetaListPage.vue | 1978 | 与 useMetaList 拆分同步，模板按功能区域拆分子组件 |

### NFR-006: _data_source 模式统一

- **Description**: 20 个文件声明 `_data_source = None`，12 个 API 文件定义 `_get_data_source()`，12 个定义 `init_*_services()`
- **Measurement**: 统一后新增 API 模块只需 1 行导入
- **Priority**: Could
- **Source**: 代码重复分析

**方案**: 创建 `meta/core/datasource_registry.py`
```python
# meta/core/datasource_registry.py
from meta.core.datasource import get_data_source

_shared_data_source = None

def get_shared_data_source():
    global _shared_data_source
    if _shared_data_source is None:
        from meta.core.datasource import get_default_db_path
        _shared_data_source = get_data_source("sqlite", database=str(get_default_db_path()))
    return _shared_data_source
```

### NFR-007: 测试覆盖补充

- **Description**: 6/10 Store 无测试，8/30 Service 无测试
- **Measurement**: Store 覆盖率从 40% 提升到 80%，Service 覆盖率从 73% 提升到 90%
- **Priority**: Could
- **Source**: 测试覆盖分析

**优先补充**:

| 类别 | 文件 | 优先级 |
|------|------|--------|
| Store | chartArchDataStore.ts | 高（图表核心状态） |
| Store | appStore.ts | 中 |
| Store | notificationStore.ts | 中 |
| Store | userPreferences.js | 中 |
| Service | baseService.js | 高（HTTP 基础层） |
| Service | feishuService.js | 中 |
| Service | diagramDataBuilder.js | 中 |

### NFR-008: 生产代码 console.log 清理

- **Description**: 20+ 处 `console.log` 未包裹 `import.meta.env.DEV`，出现在生产构建中
- **Measurement**: 生产构建中零 console.log（ESLint no-console 已配置 warn）
- **Priority**: Could
- **Source**: 代码质量分析

**主要分布**:
- useDiagramData.js: 7 处
- StepConfig.vue: 8 处
- groupedLayout.js: 6 处
- AADiagramApp/index.vue: 6 处

---

## 5. External Interface Requirements

不涉及外部接口变更。

---

## 6. Transition Requirements

### TR-001: xlsx → exceljs 迁移

- **Description**: 替换 xlsx 库为 exceljs
- **Strategy**:
  1. 安装 exceljs，保留 xlsx 直到迁移完成
  2. 重写 excelParser.js（读取功能）
  3. 重写 ImpactPreview.vue（导出功能）
  4. 更新测试
  5. 卸载 xlsx
- **Rollback Plan**: 保留 xlsx 在 devDependencies 中直到 exceljs 验证通过
- **Source**: 依赖分析

### TR-002: MermaidComponent.css 拆分

- **Description**: 单文件拆分为 4 个文件
- **Strategy**:
  1. 创建 4 个新 CSS 文件
  2. MermaidComponent.vue 改用 `@import` 引入
  3. 修复 mojibake 注释
  4. 视觉回归测试
- **Rollback Plan**: Git revert 即可恢复单文件
- **Source**: CSS 分析

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- Vue 3 shallowRef 不追踪内部变化，改造后需确保所有修改路径都替换 `.value` 引用
- import_export_service.py 拆分需保持 ImportExportService 类的公共 API 不变（server.py 和 API 层依赖）
- action_executor.py 拆分需保持 ActionExecutor.execute() 接口不变
- xlsx → exceljs 迁移需保证 Excel 文件格式兼容性（.xlsx 读写）

### 7.2 Business Constraints

- 安全类问题不在本 spec 范围（单独 spec）
- i18n 迁移继续按 i18n-migration-tracker 推进，不在本 spec 重复
- commit 管理由其他智能体负责

### 7.3 Assumptions

- useInteraction.js 已完全替代旧版 zoom/drag 代码 — Source: 代码审查（旧代码与 useInteraction 功能重叠）
- exceljs 可完整替代 xlsx 的 6 个使用函数 — Source: exceljs 文档确认支持
- shallowRef 迁移后列表页行内编辑仍通过 draftValues 管理，不需要 data 的深层响应式 — Source: 代码分析

---

## 8. Priorities & Milestone Suggestions

| ID     | Requirement | Priority | Reason |
| ------ | ----------- | -------- | ------ |
| FR-001 | MermaidComponent 旧事件监听器清理 | Must | 内存泄漏，每次路由切换累积 |
| FR-002 | useTooltip 事件监听器清理 | Must | 内存泄漏，重渲染累积 1600+ |
| FR-003 | annotationOverlay 事件监听器清理 | Must | 内存泄漏 |
| FR-004 | FilterBar 全局 click 清理 | Must | 内存泄漏 |
| FR-006 | page_size 上限校验 | Must | DoS 风险 |
| FR-007 | audit_interceptor 调试代码移除 | Must | 生产性能影响（20次/秒无用I/O） |
| NFR-001 | shallowRef 迁移 | Must | Proxy 开销 5-15ms，影响核心交互 |
| NFR-002 | Deep Watcher 优化 | Must | 5-13ms/次触发，图表交互卡顿 |
| NFR-003 | 内存泄漏消除 | Must | 长时间使用性能退化 |
| FR-005 | useSelectionConfig popstate 清理 | Should | 低频但无清理 |
| FR-008 | audit_api N+1 修复 | Should | 30 次 SQL → 1 次 |
| FR-009 | bo_api 权限批量查询 | Should | 100 次 SQL → 2 次 |
| FR-010 | audit_service 数据库分页 | Should | OOM 风险 |
| FR-011 | _api_error 共享模块 | Should | 54 行重复 |
| FR-012 | _get_db_path 统一 | Should | 9 文件重复 |
| FR-013 | 裸 except 替换 | Should | Python 反模式 |
| FR-014 | xlsx → exceljs | Should | 许可证 + 体积 |
| FR-015 | vite manualChunks 修复 | Should | chunk 膨胀 |
| NFR-004 | 后端 God 文件拆分 | Should | 可维护性 |
| NFR-005 | 前端 God 文件拆分 | Should | 可维护性 |
| FR-016 | CSS 拆分 + mojibake | Could | 维护性 + 编码修复 |
| FR-017 | 未使用依赖清理 | Could | 清理 |
| NFR-006 | _data_source 模式统一 | Could | 减少模板代码 |
| NFR-007 | 测试覆盖补充 | Could | 回归保护 |
| NFR-008 | console.log 清理 | Could | 生产整洁 |

### Suggested Milestones

**Milestone 1: 内存泄漏 + 紧急修复（Must 全部）**
- FR-001 ~ FR-004, FR-006, FR-007
- NFR-003
- 预计影响：消除 4 处内存泄漏 + 1 处 DoS 风险 + 1 处生产性能浪费

**Milestone 2: 响应式性能优化**
- NFR-001 (shallowRef 迁移)
- NFR-002 (Deep Watcher 优化)
- 预计影响：图表交互延迟降低 50%，列表页大数据量时 Proxy 开销降低 80%

**Milestone 3: 后端性能 + 代码重复**
- FR-008 ~ FR-013
- 预计影响：N+1 查询修复、代码重复消除、裸 except 清理

**Milestone 4: 依赖治理 + 构建优化**
- FR-014, FR-015, FR-016, FR-017
- 预计影响：bundle 减少 ~150KB gzip，CSS 可维护性提升

**Milestone 5: God 文件拆分**
- NFR-004, NFR-005
- 预计影响：6 个超大文件拆分为 20+ 个职责单一的模块

**Milestone 6: 测试补充 + 收尾**
- NFR-006, NFR-007, NFR-008, FR-005
- 预计影响：Store 覆盖率 40%→80%，Service 覆盖率 73%→90%

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**当前架构问题**:

1. **前端响应式链路过长**：
   ```
   store ref() → computed(diagramConfig 聚合 22 个 ref) → props → deep watcher → JSON.stringify 比较 → renderMermaid()
   ```
   任何一个 store 属性变化都触发整条链路重算。

2. **事件监听器无生命周期管理**：
   - MermaidComponent 旧代码：匿名 `document.addEventListener`，无法清理
   - useTooltip：每次渲染新增 1600+ 监听器，无清理函数
   - FilterBar：模块顶层添加全局监听器

3. **后端 N+1 查询模式**：
   - audit_api 趋势：循环 30 天 × 1 次 COUNT = 30 次 SQL
   - bo_api 权限：循环 N 权限 × 2 次 SQL = 2N 次
   - audit_service：全量加载后内存分页

4. **代码重复**：
   - `_api_error` 3 处完全相同
   - `_get_data_source` 12 处相同模式
   - `_get_db_path` 9 处相同函数

5. **God 文件**：
   - import_export_service.py: 5080 行，93 个方法，6 个职责域
   - useMetaList.js: 2030 行，80+ 导出，7 个职责域

### 9.2 Target State

1. **响应式链路精简**：
   ```
   store shallowRef() → 独立 watcher(精确依赖) → renderMermaid()
   ```
   只有真正变化的属性触发对应 watcher。

2. **事件监听器生命周期完整**：
   - 所有 addEventListener 使用具名函数
   - composable 返回清理函数
   - 组件 onUnmounted 中清理

3. **后端查询批量优化**：
   - N+1 → 批量 IN 查询
   - 内存分页 → SQL LIMIT/OFFSET
   - page_size 上限 500

4. **代码去重**：
   - `_response_helpers.py` 共享 API 响应函数
   - `datasource_registry.py` 共享数据源单例
   - `datasource.py` 新增 `get_default_db_path()`

5. **God 文件拆分**：
   - 每个文件 < 800 行
   - 单一职责
   - 公共 API 保持兼容

### 9.3 Detailed Design

#### 9.3.1 shallowRef 迁移模式

**统一迁移模式**：

```javascript
// Before
const data = ref([])

// After
const data = shallowRef([])

// 更新方式
function loadData() {
  data.value = await fetchList()  // 直接替换引用，触发 shallowRef 更新
}

// 内部修改需手动触发
function updateItem(id, field, value) {
  const newList = data.value.map(item =>
    item.id === id ? { ...item, [field]: value } : item
  )
  data.value = newList  // 替换引用
}
```

**draftValues Map 特殊处理**：

```javascript
// Before
const draftValues = ref(new Map())
// 每次编辑复制整个 Map
draftValues.value = new Map(draftValues.value)

// After
const draftValues = shallowRef(new Map())
// 同样复制 Map，但 shallowRef 只追踪引用变化
function updateDraftValue(rowId, fieldName, newValue) {
  const newMap = new Map(draftValues.value)
  let rowDrafts = newMap.get(rowId)
  if (!rowDrafts) { rowDrafts = {}; newMap.set(rowId, rowDrafts) }
  rowDrafts[fieldName] = newValue
  draftValues.value = newMap  // 触发更新
}
```

#### 9.3.2 diagramConfig computed 拆分

**Before** (1 个 computed 聚合 22 个 ref):
```javascript
const diagramConfig = computed(() => ({
  chartType: configStore.chartType,
  colorScheme: configStore.colorScheme,
  // ... 20 more
}))
```

**After** (按功能分组 watcher):
```javascript
// 颜色相关 — 仅更新颜色不重渲染
watch(
  [() => configStore.colorScheme, () => configStore.colorGroupBy,
   () => configStore.customColors, () => configStore.centerScopeColor],
  () => {
    if (previewData.value) updateColorsOnly()
  }
)

// 布局相关 — 需要重新生成图表
watch(
  [() => configStore.chartType, () => configStore.layoutEngine,
   () => configStore.layoutTemplate, () => configStore.layoutControlConfig],
  () => {
    if (previewData.value) generateDiagram()
  }
)

// 中心范围相关
watch(
  () => configStore.centerScope,
  (newScope, oldScope) => {
    if (newScope !== oldScope) {
      if (diagramData.value) diagramData.value = null
      if (newScope?.length > 0 && previewData.value?.domainProducts) {
        updateCenterScopeMarkers()
      }
    }
  }
)
```

#### 9.3.3 useTooltip 清理函数设计

```javascript
// useTooltip.js
export function useTooltip() {
  let _cleanupFns = []

  function addListener(element, event, handler) {
    element.addEventListener(event, handler)
    _cleanupFns.push(() => element.removeEventListener(event, handler))
  }

  const addMouseOverTooltips = (svg, relationDescriptions, diagramType, hideTails) => {
    cleanup()  // 先清理旧监听器

    // ... 现有逻辑，但用 addListener 替代 addEventListener
    labels.forEach(label => {
      addListener(label, 'mouseenter', (e) => { ... })
      addListener(label, 'mousemove', (e) => { ... })
      addListener(label, 'mouseleave', () => { ... })
      addListener(label, 'click', (e) => { ... })
    })

    // SVG click
    addListener(svg, 'click', (e) => { ... })
  }

  function cleanup() {
    _cleanupFns.forEach(fn => fn())
    _cleanupFns = []
  }

  return { addMouseOverTooltips, cleanup }
}
```

#### 9.3.4 import_export_service.py 拆分策略

**保持公共 API 兼容**：

```python
# meta/services/import_export_service.py (facade, ~100 行)
from meta.services.export_service import ExportService
from meta.services.import_service import ImportService
from meta.services.hierarchy_query_service import HierarchyQueryService

class ImportExportService:
    """Facade - 保持原有公共 API 不变"""

    def __init__(self, data_source):
        self._export = ExportService(data_source)
        self._import = ImportService(data_source)
        self._hierarchy = HierarchyQueryService(data_source)
        self.ds = data_source

    # 导出方法委托
    def export_to_excel(self, *args, **kwargs):
        return self._export.export_to_excel(*args, **kwargs)

    # 导入方法委托
    def import_cascade(self, *args, **kwargs):
        return self._import.import_cascade(*args, **kwargs)

    # 层级查询委托
    def get_cascade_object_types(self, *args, **kwargs):
        return self._hierarchy.get_cascade_object_types(*args, **kwargs)
```

#### 9.3.5 action_executor.py dispatch table

**Before** (3 层 if/elif):
```python
if action.action_type == ActionType.CRUD:
    return self._execute_crud(...)
elif action.action_type == ActionType.BATCH:
    return self._execute_batch(...)
```

**After** (dispatch table):
```python
class ActionExecutor:
    _dispatch = {
        ActionType.CRUD: '_execute_crud',
        ActionType.BATCH: '_execute_batch',
        ActionType.BUSINESS: '_execute_business',
    }

    def execute(self, action, params):
        handler_name = self._dispatch.get(action.action_type)
        if not handler_name:
            return ActionResult.fail(error="UNSUPPORTED_ACTION_TYPE")
        handler = getattr(self, handler_name)
        return handler(action, params)
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| shallowRef vs markRaw | shallowRef 保留 .value 响应式 | 需手动 triggerRef | **Selected** — shallowRef 更符合 Vue 3 惯例 |
| diagramConfig 拆分 vs keep-alive | 精确控制触发 | 代码量增加 | **Selected** — 性能收益明确 |
| exceljs vs xlsx-populate | 功能完整、社区活跃 | API 差异较大 | **Selected** — 长期维护性更好 |
| Facade 拆分 vs 直接拆分 | 保持 API 兼容 | 多一层间接 | **Selected** — 降低迁移风险 |
| dispatch table vs Strategy pattern | 简单直接 | 扩展性一般 | **Selected** — 当前 action 类型少，无需过度设计 |

### 9.5 Implementation & Migration Plan

**实施顺序**:

1. **Milestone 1**（内存泄漏 + 紧急修复）:
   - FR-001: 删除 MermaidComponent 旧事件代码
   - FR-002: useTooltip 返回清理函数
   - FR-003: annotationOverlay 返回清理函数
   - FR-004: FilterBar 生命周期管理
   - FR-006: page_size 上限
   - FR-007: audit_interceptor 调试代码移除

2. **Milestone 2**（响应式性能）:
   - NFR-001: 9 处 ref → shallowRef 迁移
   - NFR-002: diagramConfig computed 拆分 + MermaidComponent deep watcher 优化

3. **Milestone 3**（后端性能 + 代码重复）:
   - FR-008 ~ FR-013

4. **Milestone 4**（依赖治理）:
   - FR-014 ~ FR-017

5. **Milestone 5**（God 文件拆分）:
   - NFR-004, NFR-005

6. **Milestone 6**（测试补充）:
   - NFR-006 ~ NFR-008

**Risk Mitigation**:

| Risk | Mitigation |
|------|-----------|
| shallowRef 迁移后遗漏 triggerRef | 每个迁移项编写测试验证响应式更新 |
| diagramConfig 拆分后 watcher 遗漏 | 对比旧 computed 的 22 个依赖，确保全覆盖 |
| import_export_service 拆分后功能回归 | Facade 模式 + 现有测试全部通过 |
| xlsx → exceljs 格式兼容性 | 用现有 Excel 文件做 round-trip 测试 |
| CSS 拆分后视觉回归 | 截图对比测试 |

**Testing Strategy**:

- **Unit tests**: 每个 FR/NFR 对应至少 1 个测试用例
- **Integration tests**: shallowRef 迁移后验证组件交互正常
- **E2E tests**: 图表渲染 + 列表页操作 + 导入导出
- **Performance tests**: shallowRef 前后 `performance.now()` 对比

**Rollback Plan**:

- 每个 Milestone 独立 commit，可单独 revert
- Facade 模式保证公共 API 兼容，拆分失败可回退到 Facade 调用原类
- xlsx 保留在 devDependencies 直到 exceljs 验证完成

---

## 10. TBD List

| ID     | Item | Missing Information | Next Step |
| ------ | ---- | ------------------- | --------- |
| TBD-1 | useInteraction.js 是否完全覆盖旧版 zoom/drag 功能 | 需功能对比验证 | 代码审查 + 手动测试 |
| TBD-2 | shallowRef 迁移后 draftValues 的 watch 是否需要调整 | draftValues 当前被 watch 监听，shallowRef 后行为可能不同 | 实验验证 |
| TBD-3 | exceljs 对现有 Excel 模板的兼容性 | 现有导出模板格式是否完全支持 | 用真实文件测试 |
| TBD-4 | import_export_service 拆分后内部方法交叉引用 | 6 个子服务之间是否有方法互相调用 | 代码依赖分析 |
| TBD-5 | MetaForm.vue 3 个 deep watcher 合并方案 | 合并后是否影响表单双向同步逻辑 | 需详细分析表单数据流 |
| TBD-6 | action_executor.py CUSTOM 类型处理 | ActionType.CUSTOM 已定义但未实现，是否有业务需求 | 确认产品需求 |
