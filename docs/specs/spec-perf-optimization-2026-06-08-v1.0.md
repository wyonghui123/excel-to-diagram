# Spec: 系统性能优化 (非图表部分)

> **日期**: 2026-06-08
> **版本**: v1.0
> **范围**: 排除 MermaidComponent / 图表展示相关, 聚焦构建体积、后端查询、前端数据流、代码质量

---

## 1. Background & Objectives

### 1.1 Background

经过对 `excel-to-diagram` 项目的全面性能分析, 发现以下四类问题:

1. **构建体积过大**: 死依赖 (~6MB) + 缺少分包策略 + ECharts 全量导入, 导致首屏加载 5-10s+
2. **后端查询低效**: N+1 查询 + 内存全量排序 + 缺少索引, 大数据量时 API 响应缓慢
3. **前端数据流串行**: 多处串行 await 可并行化 + 缓存策略不合理, 增加页面切换延迟
4. **前端代码缺陷**: 事件监听器泄漏 + XSS 风险 + deep watcher 过多, 影响稳定性和性能

### 1.2 Business Objectives

- 首屏加载时间从 ~10s 降至 ~3s (3G 网络)
- 构建体积 (gzip) 从 ~2.5MB 降至 ~800KB
- enum_api 列表查询从 N+2 次 SQL 降至 2 次
- 消除已知内存泄漏和 XSS 风险

### 1.3 User / Stakeholder Objectives

- 用户: 页面加载更快, 操作响应更流畅
- 开发者: 构建更快, 依赖更清晰, 更易调试
- 运维: 部署包更小, 服务器负载更低

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 首屏加载时间直接影响用户留存 |
| User/Stakeholder | Yes | 开发者构建体验, 用户页面响应 |
| Solution | Yes | 分包/按需导入/批量查询等技术方案 |
| Functional | Yes | 具体代码修改行为 |
| Nonfunctional | Yes | 性能/安全/可维护性 |
| External Interface | Yes | API 字段投影影响前后端接口 |
| Transition | Yes | 移除依赖需确认无副作用 |

---

## 3. Functional Requirements

### FR-001: 移除死依赖

- **Description**: 系统 MUST 从 `package.json` 中移除未被任何源码引用的依赖包: `monaco-editor`, `@monaco-editor/loader`, `@excalidraw/excalidraw`, `react`, `react-dom`
- **Acceptance Criteria**:
  - `package.json` 中不再包含上述 5 个包
  - `npm run build` 成功
  - 所有页面功能正常
- **Priority**: Must
- **Impact**: 构建体积减少 ~6MB (gzip ~1.5MB)
- **Source**: 代码分析 - src/ 中无任何 import 引用

### FR-002: 添加 manualChunks 分包策略

- **Description**: 系统 MUST 在 `vite.config.js` 中配置 `build.rollupOptions.output.manualChunks`, 将大型依赖拆分为独立 chunk
- **Acceptance Criteria**:
  - 配置至少拆分: vue 全家桶 / element-plus / echarts / xlsx / pdf 导出
  - 单个 chunk 不超过 500KB (gzip)
  - `npm run build` 成功
- **Priority**: Must
- **Impact**: 首屏只加载必要 chunk, 缓存命中率提升
- **分包方案**:
  ```
  vendor-vue: ['vue', 'vue-router', 'pinia']
  vendor-ep: ['element-plus']
  vendor-echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers']
  vendor-xlsx: ['xlsx']
  vendor-pdf: ['html2canvas', 'jspdf']
  ```

### FR-003: 添加 sideEffects 声明

- **Description**: 系统 MUST 在 `package.json` 中添加 `sideEffects` 字段, 声明有副作用的文件类型, 允许 bundler 安全 tree-shake
- **Acceptance Criteria**:
  - `package.json` 包含 `"sideEffects": ["*.css", "*.scss", "*.vue"]`
  - `npm run build` 成功且体积有减少
- **Priority**: Must
- **Impact**: 改善 tree-shaking, 减少未使用代码被打包

### FR-004: ECharts 按需导入

- **Description**: 系统 MUST 将 `AuditLogManagement.vue` 中的 `import * as echarts from 'echarts'` 改为按需导入, 只注册使用的图表类型
- **Acceptance Criteria**:
  - 使用 `echarts/core` + 按需注册 PieChart, LineChart 等
  - 图表功能正常 (饼图 + 趋势折线图)
  - echarts chunk 体积减少 60%+ (从 ~800KB 降至 ~200KB)
- **Priority**: Must
- **Impact**: echarts 体积减少 ~600KB (gzip ~200KB)
- **Source**: 代码分析 - AuditLogManagement.vue:152

### FR-005: CSS 覆盖合并去重

- **Description**: 系统 MUST 合并 `yon-ep.scss` 和 `element-plus-overrides.css` 中的重复/冲突样式, 消除 8 个重复 CSS 变量定义和 6 处组件样式冲突
- **Acceptance Criteria**:
  - `:root` CSS 变量只在一处定义
  - Primary 按钮 hover 颜色统一 (当前 yon-ep 用 #fb923c, overrides 用 #c2410c, 需确认统一值)
  - Link 按钮默认颜色统一
  - Switch 组件样式风格统一 (CSS 变量 vs 硬编码)
  - 总 CSS 体积减少
- **Priority**: Should
- **Impact**: CSS 体积减少 + 消除样式冲突
- **Source**: 代码分析 - yon-ep.scss:44-54 与 element-plus-overrides.css:13-24 完全重复

### FR-006: enum_api N+1 查询修复

- **Description**: 系统 MUST 将 `enum_api.py` 列表接口中的逐行 `_get_enum_value_count()` 调用改为批量查询
- **Acceptance Criteria**:
  - 列表接口 SQL 查询次数从 N+2 降至 2 (1 次列表 + 1 次批量 count)
  - 使用 `SELECT enum_type_id, COUNT(*) FROM enum_values WHERE enum_type_id IN (...) GROUP BY enum_type_id` 批量查询
  - 同理修复 `_get_dimension_count` 的 N+1 问题
  - API 返回结果不变
- **Priority**: Must
- **Impact**: 50 条/页时从 52 次 SQL 降至 2 次
- **Source**: 代码分析 - enum_api.py:252-253

### FR-007: 虚拟字段排序内存全量加载修复

- **Description**: 系统 MUST 修复 `query_service.py` 中虚拟字段排序时先查全部数据再 Python 排序截取的问题
- **Acceptance Criteria**:
  - 虚拟字段排序时, 先查全部 ID + 排序字段, 排序后取当前页 ID, 再查完整数据
  - 不再将全量数据加载到 Python 内存
  - 分页结果不变
- **Priority**: Should
- **Impact**: 10000 条表第 1 页查询内存减少 99%
- **Source**: 代码分析 - query_service.py:425-448

### FR-008: relationships 表添加索引

- **Description**: 系统 MUST 为 `relationships` 表的 `source_bo_id` 和 `target_bo_id` 列添加索引
- **Acceptance Criteria**:
  - 新增迁移脚本添加索引
  - `computed count` 子查询性能提升
- **Priority**: Should
- **Impact**: computed field 子查询加速
- **Source**: 代码分析 - query_service.py:648-653 频繁查询

### FR-009: audit_logs 添加复合索引

- **Description**: 系统 MUST 为 `audit_logs` 表添加 `(object_type, action)` 复合索引
- **Acceptance Criteria**:
  - 新增迁移脚本添加索引
  - `_enrich_updated_at` 查询性能提升
- **Priority**: Should
- **Impact**: updated_at 派生查询加速
- **Source**: 代码分析 - enrichment_engine.py 频繁查询

### FR-010: useAssociation 并行刷新

- **Description**: 系统 MUST 将 `useAssociation.js` 中 `assign()` / `unassign()` / `batchAssign()` / `batchUnassign()` 成功后的串行 `await refresh() + await countAssociations()` 改为并行
- **Acceptance Criteria**:
  - 改为 `await Promise.all([refresh(), countAssociations()])`
  - 功能行为不变 (两个请求都完成后才继续)
  - 刷新延迟减少 ~50%
- **Priority**: Should
- **Impact**: 每次关联操作节省 200-500ms
- **Source**: 代码分析 - useAssociation.js:131-132, 163-164

### FR-011: useRefreshCoordinator 并行刷新

- **Description**: 系统 MUST 将 `useRefreshCoordinator.js` 中 `refreshAll()` 的串行 for-await 改为并行执行
- **Acceptance Criteria**:
  - 改为 `Promise.allSettled()` 并行执行所有回调
  - 单个回调失败不影响其他回调 (与当前 try-catch 行为一致)
  - `isRefreshing` 状态正确管理
- **Priority**: Should
- **Impact**: 5 个回调从 1000ms 降至 ~200ms
- **Source**: 代码分析 - useRefreshCoordinator.js:15-27

### FR-012: useMetaList 缓存策略优化

- **Description**: 系统 MUST 修改 `useMetaList.js` 的 `init()` 方法, 不再每次挂载都清除缓存重新请求
- **Acceptance Criteria**:
  - `init()` 检查 LRU 缓存是否有效, 有效则跳过 `_loadMetaConfig()`
  - 提供强制刷新参数 `init({ force: true })`
  - 从列表页进入详情页再返回时, 利用已有缓存
- **Priority**: Could
- **Impact**: 页面切换时减少 1-2 次网络请求
- **Source**: 代码分析 - useMetaList.js:1727-1729, 337

### FR-013: API 字段投影支持

- **Description**: 系统 SHOULD 在后端查询 API 中支持 `fields` 参数, 允许前端指定只返回需要的字段
- **Acceptance Criteria**:
  - `boCrudService.query()` 支持 `fields` 参数
  - 后端 SELECT 语句只查询指定字段
  - 不传 `fields` 时行为不变 (向后兼容)
  - 前端列表页传 `fields=id,name,code` 等少数字段
- **Priority**: Could
- **Impact**: 列表查询响应体积减少 50-70%
- **Source**: 代码分析 - boCrudService.js:33-58, sql_adapters.py:342

### FR-014: FilterBar 事件监听器泄漏修复

- **Description**: 系统 MUST 修复 `FilterBar.vue` 中 `document.addEventListener('click', ...)` 未在组件卸载时移除的问题
- **Acceptance Criteria**:
  - 使用命名函数替代匿名箭头函数
  - 在 `onBeforeUnmount` 中调用 `document.removeEventListener()`
  - 组件多次挂载/卸载后无监听器累积
- **Priority**: Must
- **Impact**: 消除内存泄漏
- **Source**: 代码分析 - FilterBar.vue:316-321

### FR-015: MetaTable highlightText XSS 修复 + 性能优化

- **Description**: 系统 MUST 修复 `MetaTable.vue` 中 `highlightText()` 函数的 XSS 风险, 并优化正则表达式创建性能
- **Acceptance Criteria**:
  - 对 `text` 参数进行 HTML 转义后再替换高亮标记
  - 缓存正则表达式对象 (基于 searchQuery)
  - 搜索高亮功能正常
  - 不存在 XSS 注入风险
- **Priority**: Must
- **Impact**: 消除 XSS 风险 + 大表格渲染性能提升
- **Source**: 代码分析 - MetaTable.vue:149-155, 412-417

### FR-016: Deep Watcher 审计与优化

- **Description**: 系统 SHOULD 审计 23 处 `deep: true` watcher, 评估是否可改为浅比较或精确依赖
- **Acceptance Criteria**:
  - 逐个评估 23 处 deep watcher 的必要性
  - 可优化的改为 `watchEffect` + 精确依赖 或 版本号机制
  - 无法优化的添加注释说明原因
  - 优化数量 >= 5 处
- **Priority**: Could
- **Impact**: 减少响应式系统开销
- **Source**: 代码分析 - 23 处 deep: true 分布在 19 个文件

### FR-017: 移除 jsdom 冗余依赖

- **Description**: 系统 MUST 从 `devDependencies` 中移除 `jsdom`, 因为项目已选用 `happy-dom` 作为 Vitest 环境
- **Acceptance Criteria**:
  - `package.json` devDependencies 中不再包含 `jsdom`
  - `npm run test:unit` 正常通过
- **Priority**: Should
- **Impact**: npm install 加速
- **Source**: 代码分析 - vitest.config.js:9 使用 happy-dom, jsdom 未被引用

### FR-018: 添加 Bundle 分析工具

- **Description**: 系统 SHOULD 添加 `rollup-plugin-visualizer` 并配置 `analyze` npm script, 便于后续量化优化效果
- **Acceptance Criteria**:
  - `npm run analyze` 生成 bundle 组成可视化报告
  - 报告在 `stats.html` 中可查看
- **Priority**: Could
- **Impact**: 后续优化效果可量化

---

## 4. Nonfunctional Requirements

### NFR-001: 构建体积

- **Description**: 优化后 gzip 总体积 MUST 不超过 1MB (当前 ~2.5MB)
- **Measurement**: `npm run build` 后检查 dist/assets/ 总大小
- **Priority**: Must

### NFR-002: 首屏加载时间

- **Description**: 3G 网络 (1.6Mbps) 下首屏可交互时间 SHOULD 不超过 3s
- **Measurement**: Chrome DevTools Lighthouse Performance 分数
- **Priority**: Should

### NFR-003: API 响应时间

- **Description**: enum_api 列表接口 (50 条/页) MUST 在 200ms 内返回
- **Measurement**: 后端日志 trace_id 响应时间
- **Priority**: Must

### NFR-004: 向后兼容

- **Description**: 所有 API 接口 MUST 保持向后兼容, 新参数均为可选
- **Measurement**: 现有前端功能无回归
- **Priority**: Must

### NFR-005: 安全性

- **Description**: highlightText 函数 MUST 不存在 XSS 注入风险
- **Measurement**: 安全扫描 + 手动测试 `<script>` 注入
- **Priority**: Must

---

## 5. External Interface Requirements

### IF-001: API 字段投影参数 (FR-013)

- **Type**: API
- **Endpoint**: `GET /api/v1/bo/{objectType}`
- **New Parameter**: `fields` (optional, comma-separated field names)
- **Example**: `GET /api/v1/bo/business_object?fields=id,name,code`
- **Backward Compatibility**: 不传 `fields` 时返回全字段 (行为不变)
- **Error Handling**: 无效字段名忽略, 不报错

---

## 6. Transition Requirements

### TR-001: 死依赖移除验证

- **Description**: 移除 monaco-editor / @excalidraw / react / react-dom 前, 需确认无动态引用
- **Strategy**: 先 `npm uninstall`, 再 `npm run build` + 全功能回归
- **Rollback Plan**: `npm install` 恢复依赖

### TR-002: CSS 合并迁移

- **Description**: 合并 yon-ep.scss + element-plus-overrides.css 需确认样式优先级
- **Strategy**: 合并为单一文件, 逐组件视觉验证
- **Rollback Plan**: Git revert 恢复双文件

### TR-003: 数据库索引添加

- **Description**: 新增索引需通过迁移脚本, 不影响现有数据
- **Strategy**: CREATE INDEX IF NOT EXISTS, SQLite 在线添加索引不锁表
- **Rollback Plan**: DROP INDEX IF EXISTS

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- SQLite 数据库, 不支持并发 DDL
- Vite 构建工具, rollup 打包
- Vue 3 + Element Plus 前端框架
- 无 Redis / 分布式缓存基础设施

### 7.2 Business Constraints

- 不修改 MermaidComponent / 图表展示相关代码
- API 变更必须向后兼容
- 不引入新的运行时依赖 (TanStack Query 等留待后续)

### 7.3 Assumptions

- monaco-editor / @excalidraw / react / react-dom 确实无动态引用 (已通过 grep 验证) - Source: Verified
- ECharts 只用于饼图和折线图 (已通过代码确认) - Source: Verified
- Primary 按钮 hover 颜色应统一为浅色 #fb923c (yon-ep 的值) - Source: Assumed, 需确认

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|------------|----------|--------|
| FR-001 | 移除死依赖 | Must | 6MB 纯浪费, 零风险 |
| FR-002 | manualChunks 分包 | Must | 首屏加载核心优化 |
| FR-003 | sideEffects 声明 | Must | tree-shaking 基础 |
| FR-004 | ECharts 按需导入 | Must | 减少 600KB |
| FR-005 | CSS 覆盖合并去重 | Should | 消除冲突, 减少体积 |
| FR-006 | enum_api N+1 修复 | Must | 查询性能核心问题 |
| FR-007 | 虚拟字段排序修复 | Should | 大表性能关键 |
| FR-008 | relationships 索引 | Should | 子查询加速 |
| FR-009 | audit_logs 索引 | Should | 派生查询加速 |
| FR-010 | useAssociation 并行 | Should | 操作响应加速 |
| FR-011 | useRefreshCoordinator 并行 | Should | 批量刷新加速 |
| FR-012 | useMetaList 缓存优化 | Could | 页面切换加速 |
| FR-013 | API 字段投影 | Could | 传输体积优化 |
| FR-014 | FilterBar 泄漏修复 | Must | 内存泄漏 |
| FR-015 | highlightText XSS 修复 | Must | 安全风险 |
| FR-016 | Deep Watcher 优化 | Could | 响应式开销 |
| FR-017 | 移除 jsdom | Should | 构建加速 |
| FR-018 | Bundle 分析工具 | Could | 可观测性 |

### Milestone Plan

**M1: 构建体积优化 (Must, 6 项)**
- FR-001 移除死依赖
- FR-002 manualChunks 分包
- FR-003 sideEffects 声明
- FR-004 ECharts 按需导入
- FR-005 CSS 覆盖合并
- FR-017 移除 jsdom
- FR-018 Bundle 分析工具
- **验证**: `npm run build` + `npm run analyze` 对比体积

**M2: 后端查询优化 (Should, 4 项)**
- FR-006 enum_api N+1 修复
- FR-007 虚拟字段排序修复
- FR-008 relationships 索引
- FR-009 audit_logs 索引
- **验证**: API 响应时间对比 + 回归测试

**M3: 前端数据流与代码质量 (Must+Should, 5 项)**
- FR-010 useAssociation 并行
- FR-011 useRefreshCoordinator 并行
- FR-014 FilterBar 泄漏修复
- FR-015 highlightText XSS 修复
- FR-012 useMetaList 缓存优化
- **验证**: 功能回归 + 内存泄漏检测

**M4: 长期优化 (Could, 2 项)**
- FR-013 API 字段投影
- FR-016 Deep Watcher 优化
- **验证**: 性能对比 + 代码审查

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **构建**: 无分包策略, 死依赖 6MB+, ECharts 全量导入, 无 sideEffects 声明
- **后端**: enum_api N+1 查询, 虚拟字段排序全量加载, 缺少关键索引
- **前端**: 串行 await 可并行化, 事件监听器泄漏, XSS 风险, CSS 覆盖冲突
- **Relevant Code Paths**:
  - `vite.config.js` - 构建配置
  - `package.json` - 依赖管理
  - `meta/api/enum_api.py` - N+1 查询
  - `meta/services/query_service.py` - 内存排序
  - `src/composables/useAssociation.js` - 串行刷新
  - `src/composables/useRefreshCoordinator.js` - 串行刷新
  - `src/components/common/FilterBar/FilterBar.vue` - 事件泄漏
  - `src/components/common/MetaTable.vue` - XSS + 性能

### 9.2 Target State

- **构建**: 分包策略 + 死依赖清除 + 按需导入, gzip 体积 < 1MB
- **后端**: 批量查询 + 索引优化, API 响应 < 200ms
- **前端**: 并行刷新 + 无泄漏 + 无 XSS, 页面切换 < 500ms

### 9.3 Detailed Design

#### FR-001: 移除死依赖

```bash
npm uninstall monaco-editor @monaco-editor/loader @excalidraw/excalidraw react react-dom
```

验证: `npm run build` 成功 + 页面功能正常

#### FR-002: manualChunks 分包

```javascript
// vite.config.js
build: {
  rollupOptions: {
    output: {
      manualChunks(id) {
        if (id.includes('node_modules')) {
          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
            return 'vendor-vue'
          }
          if (id.includes('element-plus')) {
            return 'vendor-ep'
          }
          if (id.includes('echarts')) {
            return 'vendor-echarts'
          }
          if (id.includes('xlsx')) {
            return 'vendor-xlsx'
          }
          if (id.includes('html2canvas') || id.includes('jspdf')) {
            return 'vendor-pdf'
          }
          // 其他第三方库
          return 'vendor-misc'
        }
      }
    }
  }
}
```

#### FR-003: sideEffects 声明

```json
// package.json
{
  "sideEffects": ["*.css", "*.scss", "*.vue"]
}
```

#### FR-004: ECharts 按需导入

```javascript
// AuditLogManagement.vue
import * as echarts from 'echarts/core'
import { PieChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  PieChart, LineChart,
  TitleComponent, TooltipComponent, LegendComponent, GridComponent,
  CanvasRenderer
])
```

#### FR-005: CSS 合并

1. 保留 `element-plus-overrides.css` 作为基础覆盖 (CSS 变量 + 组件样式)
2. 将 `yon-ep.scss` 中不重复的样式合并进去
3. 删除 `yon-ep.scss`
4. 更新 `src/styles/index.scss` 的 import

#### FR-006: enum_api N+1 修复

```python
# 修复前 (N+1):
for row in result:
    row['value_count'] = _get_enum_value_count(ds, row['id'])

# 修复后 (批量):
enum_ids = [row['id'] for row in result]
placeholders = ','.join(['?'] * len(enum_ids))
count_sql = f"SELECT enum_type_id, COUNT(*) as cnt FROM enum_values WHERE enum_type_id IN ({placeholders}) GROUP BY enum_type_id"
cursor = ds.execute(count_sql, enum_ids)
count_map = dict(cursor.fetchall())
for row in result:
    row['value_count'] = count_map.get(row['id'], 0)
```

同理修复 `_get_dimension_count`。

#### FR-007: 虚拟字段排序修复

```python
# 修复前: 全量加载 + Python 排序 + 截取
# 修复后: 两阶段查询
# Phase 1: 查全部 ID + 排序字段, Python 排序后取当前页 ID
# Phase 2: 用当前页 ID 查完整数据
page_ids = sorted_ids[offset:offset+limit]
full_data = ds.find(table, filters={'id': {'in': page_ids}})
```

#### FR-008/009: 索引迁移

```python
# meta/migrations/add_performance_indexes_v3.py
def up():
    execute("CREATE INDEX IF NOT EXISTS idx_relationships_source_bo ON relationships(source_bo_id)")
    execute("CREATE INDEX IF NOT EXISTS idx_relationships_target_bo ON relationships(target_bo_id)")
    execute("CREATE INDEX IF NOT EXISTS idx_audit_type_action ON audit_logs(object_type, action)")

def down():
    execute("DROP INDEX IF EXISTS idx_relationships_source_bo")
    execute("DROP INDEX IF EXISTS idx_relationships_target_bo")
    execute("DROP INDEX IF EXISTS idx_audit_type_action")
```

#### FR-010: useAssociation 并行

```javascript
// 修复前:
await refresh()
await countAssociations()

// 修复后:
await Promise.all([refresh(), countAssociations()])
```

#### FR-011: useRefreshCoordinator 并行

```javascript
// 修复前:
for (const [key, fn] of entries) {
  try { await fn() } catch (e) { console.error(...) }
}

// 修复后:
await Promise.allSettled(
  entries.map(([key, fn]) => fn().catch(e => {
    console.error(`[coordinator] refresh failed for "${key}":`, e)
  }))
)
```

#### FR-014: FilterBar 泄漏修复

```javascript
// 修复前:
document.addEventListener('click', () => { activeMultiSelect.value = null })

// 修复后:
function handleDocumentClick() {
  activeMultiSelect.value = null
}
if (typeof window !== 'undefined') {
  document.addEventListener('click', handleDocumentClick)
}
onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})
```

#### FR-015: highlightText XSS + 性能

```javascript
// 修复后:
const highlightRegex = computed(() => {
  if (!searchQuery.value) return null
  const escaped = searchQuery.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(${escaped})`, 'gi')
})

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

function highlightText(text, keyword) {
  if (!keyword || !text) return escapeHtml(String(text || ''))
  const escaped = escapeHtml(String(text))
  const regex = highlightRegex.value
  if (!regex) return escaped
  return escaped.replace(regex, '<mark class="mt-highlight">$1</mark>')
}
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| ECharts 按需导入 (echarts/core) | 减少 600KB | 需手动注册组件 | Selected |
| ECharts 替换为轻量图表库 | 更小体积 | 重写图表代码 | Rejected (成本高) |
| CSS 合并为单文件 | 消除冲突 | 需视觉验证 | Selected |
| CSS 保持双文件 + 去重 | 风险低 | 仍有优先级问题 | Rejected |
| enum_api 批量查询 | 减少 N 次查询 | 需修改 SQL | Selected |
| enum_api 使用 EnumCacheManager | 有缓存 | async/sync 不兼容 | Rejected (后续) |
| useRefreshCoordinator Promise.allSettled | 并行加速 | 错误处理变化 | Selected |
| useRefreshCoordinator 保持串行 | 行为不变 | 慢 | Rejected |

### 9.5 Implementation & Migration Plan

**Implementation Order (M1 → M2 → M3 → M4)**:

1. **M1 构建体积优化** (FR-001/002/003/004/005/017/018)
   - Step 1: npm uninstall 死依赖 (FR-001)
   - Step 2: 添加 sideEffects (FR-003)
   - Step 3: 添加 manualChunks (FR-002)
   - Step 4: ECharts 按需导入 (FR-004)
   - Step 5: CSS 合并 (FR-005)
   - Step 6: 移除 jsdom (FR-017)
   - Step 7: 添加 Bundle 分析 (FR-018)
   - **验证**: `npm run build` + `npm run analyze` 体积对比

2. **M2 后端查询优化** (FR-006/007/008/009)
   - Step 1: enum_api 批量查询 (FR-006)
   - Step 2: 虚拟字段排序两阶段查询 (FR-007)
   - Step 3: 索引迁移脚本 (FR-008/009)
   - **验证**: API 响应时间 + 回归测试

3. **M3 前端数据流与代码质量** (FR-010/011/012/014/015)
   - Step 1: FilterBar 泄漏修复 (FR-014)
   - Step 2: highlightText XSS 修复 (FR-015)
   - Step 3: useAssociation 并行 (FR-010)
   - Step 4: useRefreshCoordinator 并行 (FR-011)
   - Step 5: useMetaList 缓存优化 (FR-012)
   - **验证**: 功能回归 + 内存泄漏检测

4. **M4 长期优化** (FR-013/016)
   - Step 1: API 字段投影 (FR-013)
   - Step 2: Deep Watcher 审计 (FR-016)
   - **验证**: 性能对比

**Risk Mitigation**:
- FR-001 死依赖移除 → 先 build 验证, 再功能回归 → Risk: 低
- FR-005 CSS 合并 → 逐组件视觉验证 → Risk: 中 (样式冲突)
- FR-007 排序修复 → 对比分页结果一致性 → Risk: 中 (逻辑复杂)
- FR-015 XSS 修复 → 安全扫描 + 功能测试 → Risk: 低

**Testing Strategy**:
- Unit tests: FR-006 批量查询, FR-015 highlightText
- Integration tests: FR-010/011 并行刷新, FR-014 事件清理
- E2E tests: M1 后全功能回归, M2 后 API 响应验证
- Build verification: 每个里程碑后 `npm run build`

**Rollback Plan**:
- M1: `npm install` 恢复依赖 + Git revert 配置
- M2: Git revert 代码 + `DROP INDEX` 回滚索引
- M3: Git revert 代码
- M4: Git revert 代码

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|-------------------|-----------|
| TBD-1 | Primary 按钮 hover 颜色统一值 | yon-ep 用 #fb923c (浅), overrides 用 #c2410c (深), 需确认用哪个 | 实施时与用户确认 |
| TBD-2 | Link 按钮默认颜色统一值 | yon-ep 用 #ea580c (primary), overrides 用 #666666 (灰色), 需确认 | 实施时与用户确认 |
| TBD-3 | FR-007 虚拟字段排序修复范围 | 需确认哪些虚拟字段排序路径受影响 | 代码分析 |
| TBD-4 | FR-012 缓存有效期 | LRU 缓存 TTL 是否足够 (当前 5 分钟) | 实施时评估 |

---

*Spec 包含 10 个章节, 最后一节为 "TBD List", 内容完整。*
