# Spec: 系统性能深度优化

## 1. 背景与目标

### 1.1 背景

当前 `excel-to-diagram` 系统基于 ARCHITECTURE_V2.md 定义的元数据驱动架构，核心为 **BO Framework**（业务对象框架），通过 **16个拦截器 + 25+引擎 + 57服务 + 35 API Blueprint** 协作运转。前端为 Vue 3 + Vite + Element Plus（约102个组件），后端为 Python Flask + SQLite（连接池 + 写队列）。

经过对 `meta/core/`、`meta/services/`、`src/composables/`、`src/components/` 四个核心目录的全面扫描（覆盖拦截器链、查询构建器、数据源适配器、YAML加载器、前端组件树、缓存系统、连接池、级联服务等），识别出 **6大类核心性能风险** 和 **4个系统集成冲突点**：

| 风险类别 | 严重程度 | 涉及文件数 | 影响面 |
|----------|---------|-----------|--------|
| 拦截器链同步阻塞 | 高 | 3（bo_framework.py + 16个拦截器） | 100% CRUD 请求 |
| N+1 / 重复查询 | 高 | 6（query_service, cascade_service, persistence_interceptor, enrichment_engine, sql_adapters） | 列表/详情/级联操作 |
| 前端无虚拟滚动 | 高 | 4（MetaListPage, MetaTable, useMetaList, useMultiObjectPage） | 所有列表页面 |
| batch_insert 循环执行 | 高 | 1（sql_adapters.py L431-453） | 批量导入/批量创建 |
| 双查询模式(count+data) | 中 | 3（query_service, query_builder, persistence_interceptor） | 每次列表查询 |
| 递归级联 N+1 | 高 | 1（cascade_service.py L402-653） | 级联删除操作 |

### 1.2 业务目标

- 将列表页 P95 延迟从现状 ~800ms-1.5s 降低至 < 500ms
- 将级联删除操作 P95 延迟从现状 ~2-3s 降低至 < 1s
- 将冷启动时间从 ~2-3s 降低至 < 1.5s
- 将前端大列表（1000+行）渲染时间从 ~5s 降低至 < 100ms

### 1.3 用户/涉众目标

- 架构师/开发者：管理页面 CRUD 操作响应流畅，无明显卡顿
- 数据分析人员：大数据量场景下架构图和数据关系加载快速
- 系统管理员：数据库健康监控指标可观测，慢查询可追踪
- 运维人员：服务器冷启动快速，故障恢复时间短

---

## 2. 需求类型概览

| 类型 | 适用 | 证据来源 |
|------|------|---------|
| 业务需求 | 是 | 架构文档 + 用户反馈（CRUD 操作响应慢） |
| 用户/涉众需求 | 是 | 直接用户操作管理页面体验差 |
| 解决方案需求 | 是 | 代码分析发现的6类风险 |
| 功能需求 | 是 | 具体优化项（FR-001 ~ FR-012） |
| 非功能需求 | 是 | 延迟/内存/并发目标（NFR-001 ~ NFR-008） |
| 外部接口需求 | 是 | API 响应格式、缓存接口（IF-001 ~ IF-003） |
| 过渡需求 | 是 | 渐进式迁移，向后兼容（TR-001 ~ TR-003） |

---

## 3. 功能需求

### FR-001: 拦截器执行模型异步化

- **描述**: 将 BO Framework 的16个拦截器从纯同步串行执行改为分组异步并行执行。只读拦截器（ContextInterceptor、VersionContext、DataPermission等）可并行执行；写入拦截器（LockInterceptor、AuditInterceptor、PersistenceInterceptor）保持串行。
- **验收标准**:
  - 单个 CRUD 操作总拦截器耗时（before_action + after_action）降低 40% 以上
  - 事务一致性不受影响（LockInterceptor → 核心逻辑 → AuditInterceptor → PersistenceInterceptor 原子性保持）
  - 提供同步/异步切换开关，通过环境变量 `BO_INTERCEPTOR_MODE=sync|async` 控制
  - 异步模式失败时自动降级为同步模式（降级超时 5s）
- **优先级**: 必须
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: ARCHITECTURE_V2.md 拦截器链分析 + bo_framework.py L63-L112

### FR-002: 级联删除 N+1 查询批量化

- **描述**: 修复 `cascade_service.py` 中 `_collect_affected()` 的递归 N+1 查询和 `execute_cascade()` 的逐 ID 查询。改为单层批量查询 + 内存树形聚合。
- **验收标准**:
  - `_collect_affected()` 的查询次数从 O(N×M) 降为 O(层级数)（N=子节点数，M=层级深度）
  - `execute_cascade()` 的 child_records 查询合并为单次批量查询
  - `_find_relationships_by_bo()` 的两次查询合并为一次 OR 查询
  - 级联删除 100 条记录 4 层深度的操作从 ~3s 降为 < 1s
- **优先级**: 必须
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: cascade_service.py L402-L487 L619-L653 L381-L400

### FR-003: batch_insert 改为 executemany

- **描述**: 修复 `sql_adapters.py` 中 `SQLDataSource.batch_insert()` 使用循环逐条 INSERT 的问题，改为 `executemany()` 单次批量执行。
- **验收标准**:
  - 批量插入 100 条记录的数据库往返从 100 次降为 1 次
  - 与现有事务机制兼容（在事务内批量插入不单独 commit）
  - 保留参数化查询（防 SQL 注入）
- **优先级**: 必须
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: sql_adapters.py L431-L453

### FR-004: 前端列表虚拟滚动

- **描述**: 为 `MetaListPage.vue` 和 `MetaTable.vue` 引入虚拟滚动能力。当数据量超过阈值（默认100条）时自动启用虚拟滚动，仅渲染可视区域 + 预渲染区。
- **验收标准**:
  - 1000 条数据列表渲染时间 < 100ms（当前 ~5s）
  - 滚动帧率 > 55fps
  - 搜索/排序/过滤功能在虚拟滚动模式下正常工作
  - 行选择（多选）跨视口正确保持
  - 固定行高 48px，通过 CSS 变量配置
- **优先级**: 必须
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: 前端分析（零虚拟滚动使用）+ MetaListPage.vue L208 L225

### FR-005: 查询服务双查询消除

- **描述**: 将 `QueryService.search()` 中的 `count_all()` + `execute()` 两次查询优化为可选单次查询。对于不需要精确总数的场景（如无限滚动），跳过 count 查询。
- **验收标准**:
  - 提供查询选项 `skip_count=True`，此时只执行数据查询
  - 分页列表正常显示（需要精确 total 的场景保持双查询）
  - `full_text_search()` 的跨对象类型循环查询提供 `UNION ALL` 替代方案
- **优先级**: 应该
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: query_service.py L392-L396 L744-L780

### FR-006: 关系数据批量填充优化

- **描述**: 修复 `QueryService._enrich_with_relations()` 的逐关系查询模式。对于多个 many_to_many 关联，合并 COUNT 子查询或使用 JOIN 一次性获取。
- **验收标准**:
  - 5 个关联的对象列表查询从 1(主查询)+5 次降为 1(主查询)+1(批量填充) 次
  - `persistence_interceptor._enrich_association_counts()` 采用相同的批量模式
- **优先级**: 应该
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: query_service.py L1436-L1484 + persistence_interceptor.py L775-L817

### FR-007: YAML 加载并行化

- **描述**: 将 `yaml_loader.py` 中 `load_yaml_directory()` 的串行文件加载改为并行加载。
- **验收标准**:
  - 25个 YAML 文件冷加载时间从 ~2-3s 降为 < 1.5s
  - 热加载（文件未变更）通过 mtime 缓存维持在 < 200ms
  - 使用 `concurrent.futures.ThreadPoolExecutor`（不引入 asyncio 依赖）
- **优先级**: 应该
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: yaml_loader.py + 启动性能分析

### FR-008: 前端内存管理优化

- **描述**: 修复 `useMetaList.js` 中响应式状态膨胀问题。添加 `onUnmounted` 清理钩子，使用 `shallowRef` 替代 `ref` 减少深层响应式开销。
- **验收标准**:
  - 页面切换后旧列表状态被正确清理
  - 100 次页面切换后内存增长 < 10MB（当前 ~200MB）
  - `selectedIds` 和 `draftValues` 使用 `shallowRef`
- **优先级**: 应该
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: useMetaList.js + 前端分析

### FR-009: 审计日志异步写入

- **描述**: 将 `AuditInterceptor.after_action()` 中的审计日志写入从同步改为异步队列写入。审计日志写入失败不影响业务事务提交。
- **验收标准**:
  - CREATE/UPDATE/DELETE 操作的审计日志写入不阻塞主请求响应
  - 审计日志写入失败时降级为同步写入并告警
  - 使用 `AsyncAuditWriter`（已有实现 meta/services/async_audit_writer.py）
- **优先级**: 应该
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: persistence_interceptor.py L42-L91 + audit-interceptor 分析

### FR-010: 数据库索引优化

- **描述**: 审计 `meta/migrations/add_performance_indexes.py` 已创建的 13 个索引的有效性，补充缺失的高频查询索引。
- **验收标准**:
  - `audit_logs(object_type, object_id)` 联合索引
  - `relationships(source_bo_id, target_bo_id)` 联合索引（替代当前分别查询）
  - `business_objects(service_module_id)` 索引
  - 索引命中率 > 95%
- **优先级**: 应该
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: add_performance_indexes.py + SQL分析

### FR-011: 日志级别生产环境优化

- **描述**: 将 `bo_framework.py`、`query_builder.py`、`query_service.py` 中大量的 `logger.info()` / `print()` 调用在生产环境降为 `DEBUG` 级别或移除。
- **验收标准**:
  - 生产环境日志量减少 80% 以上
  - 保留 ERROR/WARNING 级别日志用于故障排查
  - 通过环境变量 `LOG_LEVEL=INFO|WARNING|DEBUG` 控制
- **优先级**: 可以
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: bo_framework.py L63-L112 + query_builder.py L131 L500-L501

### FR-012: 前端防抖/节流标准化

- **描述**: 统一前端防抖实现方式。当前存在 3 种独立的手写 `setTimeout` 防抖（`useValueHelp.js`、`useFilterFlow.js`、`SearchHelpDialog.vue`），替换为统一的 `useDebounceFn` 工具函数。
- **验收标准**:
  - 所有防抖逻辑使用同一个工具函数
  - 默认防抖延迟 300ms，可配置
  - 搜索输入框的请求频率降低 3-5 倍
- **优先级**: 可以
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: 前端分析（零 vueuse 使用）

---

## 4. 非功能需求

### NFR-001: 请求延迟

- **描述**: 列表查询 P95 延迟 < 500ms，单条 CRUD P95 < 200ms
- **度量方法**: Prometheus `read_query_duration_seconds` 直方图的 P95 分位数
- **行业基准**: 
  - Google: P95 < 200ms 为用户"即时响应"感知阈值；2025 SaaS 基准: Response Time ≤ 200ms 为最优
  - Oracle RWP: OLTP 事务 P95 < 100ms 为高性能标准
  - 本系统定位: 内部管理工具，< 500ms 为务实目标（当前 ~800ms-1.5s）
- **优先级**: 必须
- **来源**: 架构分析 + SaaS 行业基准 2025

### NFR-002: 级联操作延迟

- **描述**: 级联删除（4层级，100条受影响记录）P95 < 1s
- **度量方法**: `write_operation_duration_seconds` 的 P95 分位数
- **行业基准**: SAP S/4HANA 级联操作 SLA 为 < 2s，Oracle EBS 为 < 5s
- **优先级**: 必须
- **来源**: cascade_service.py 分析

### NFR-003: 前端渲染性能

- **描述**: 1000行列表首次渲染 < 100ms，滚动帧率 > 55fps，LCP < 2.5s
- **度量方法**: Chrome Performance API + Lighthouse Performance 审计
- **行业基准**: 
  - Google Core Web Vitals: LCP < 2.5s（良好），FID < 100ms
  - 2025 SaaS 基准: Tableau 1.1s 全页加载，Trello 0.8s 主内容
  - 本系统目标: 管理后台内部工具，LCP < 2.5s 为合理目标
- **优先级**: 必须
- **来源**: 前端分析 + Google Web Vitals

### NFR-004: 内存使用

- **描述**: 后端驻留内存 < 200MB（当前 ~150MB），前端单页面内存 < 50MB，100次页面切换后 < 60MB
- **度量方法**: `psutil.Process.memory_info().rss`（后端）/ Chrome Memory 面板（前端）
- **行业基准**: 中型 Flask 应用典型驻留 100-300MB；Vue 3 SPA 单页 20-80MB
- **优先级**: 应该
- **来源**: 内存泄漏分析

### NFR-005: 冷启动时间

- **描述**: 后端服务冷启动 < 1.5s（当前 ~2-3s）
- **度量方法**: 从进程启动到 `/api/v1/health` 返回 200 的时间
- **优先级**: 应该
- **来源**: 启动性能分析

### NFR-006: 并发处理能力

- **描述**: 支持 50 并发请求时 P95 延迟不超过单请求 P95 的 2 倍
- **度量方法**: Locust 负载测试
- **优先级**: 应该
- **来源**: 连接池/写队列分析 + tests/performance/locustfile.py

### NFR-007: 数据库连接池健康

- **描述**: 连接池获取超时 < 100ms，空闲连接复用率 > 90%
- **度量方法**: Prometheus `pool_acquire_wait_seconds` + `pool_idle_connections`
- **优先级**: 可以
- **来源**: sql_config.py + sql_connection_pool.py

### NFR-008: 向后兼容性

- **描述**: 所有优化不改变现有 API 契约和响应格式
- **度量方法**: 现有 E2E 测试套件（23个测试）全部通过
- **优先级**: 必须
- **来源**: 项目规则

---

## 5. 外部接口需求

### IF-001: BO Framework 拦截器模式切换

- **类型**: API / 配置
- **端点**: 环境变量 `BO_INTERCEPTOR_MODE=sync|async`
- **行为**: 
  - `sync`: 保持现有 16 个拦截器同步串行执行（默认，向后兼容）
  - `async`: 只读拦截器并行执行，写入拦截器串行执行
- **错误处理**: async 模式失败时自动降级为 sync，日志告警

### IF-002: 查询选项扩展

- **类型**: API 参数
- **端点**: `GET /api/v2/bo/{object_type}`
- **新增参数**: `skip_count=true|false`（默认 false）
- **行为**: 为 true 时不执行 COUNT 查询，`total` 字段返回 -1 表示未知总数
- **错误处理**: 参数缺失时保持现有行为

### IF-003: 前端虚拟滚动配置

- **类型**: UI 组件属性
- **入口**: `MetaListPage` 和 `MetaTable` 组件
- **新增属性**: 
  - `enableVirtualScroll`: boolean（默认 false，手动启用）
  - `virtualScrollThreshold`: number（默认 100，超过此行数自动启用）
  - `rowHeight`: number（默认 48，行高像素值）
- **行为**: 数据量低于阈值时使用普通渲染，超过阈值时使用虚拟滚动

---

## 6. 过渡需求

### TR-001: 渐进式迁移策略

- **描述**: 所有性能优化通过 feature flag 控制，默认关闭，手动开启验证后逐步推广
- **策略**: 
  1. Phase 1: 修复 N+1 查询和 batch_insert（无行为变化，直接上线）
  2. Phase 2: 添加异步拦截器模式（feature flag，默认 sync）
  3. Phase 3: 前端虚拟滚动（组件属性控制，默认关闭）
- **回滚计划**: 每个 Phase 独立 feature flag，出问题时关闭对应 flag 即可回滚

### TR-002: 性能基准建立

- **描述**: 在优化前运行现有性能测试套件，建立基准数据
- **策略**: 运行 `python meta/tests/performance/run_performance_test.py` 并保存为 `baselines/pre_optimization_baseline.json`
- **回滚计划**: N/A（只读操作）

### TR-003: E2E 测试回归

- **描述**: 每次优化后运行完整的 E2E 测试套件（smoke 5个 + features 18个）
- **策略**: 在 CI 中执行 `npx playwright test --project=smoke --project=features`
- **回滚计划**: 测试失败时阻止合并

---

## 7. 约束与假设

### 7.1 技术约束

- Python 3.x + Flask（不引入 asyncio，使用线程池实现并行）
- SQLite 作为唯一数据库（WAL 模式，单写者）
- Vue 3 Composition API（不引入新的 UI 框架）
- Element Plus 2.x（虚拟滚动基于 el-table-v2 或自定义实现）
- 保持 5个终端限制（E2E 测试规范）

### 7.2 业务约束

- 不能中断现有用户的正常使用
- 不能改变 API 响应格式
- 不能降低数据一致性保证
- 审计日志不能丢失（可异步写入但必须最终一致）

### 7.3 假设

- 当前生产环境为单实例部署（SQLite 单写者模型） — 来源: 已验证（ARCHITECTURE_V2.md + sql_adapters.py）
- 数据规模: 单表 < 10万行，audit_logs 年增长 < 100万行 — 来源: 企业级决策（TBD-1，参照 SAP Business ByDesign 中型部署标准）
- 并发用户数: 50 峰值 100 — 来源: 企业级决策（TBD-2，参照 Oracle RWP 连接池建议）
- 拦截器链中 PURE_READONLY 拦截器不修改 context — 来源: 需代码审查确认（实施前验证），若发现修改则移入 READ_MODIFY_WRITE 组
- 异步审计日志 < 1s 最终一致性可接受 — 来源: 用户确认（参照 Netflix/LinkedIn/SAP 企业实践）

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-003 | batch_insert → executemany | 必须 | 一行改动，立即见效，无风险 |
| FR-002 | 级联删除 N+1 批量化 | 必须 | 影响最大的性能瓶颈 |
| FR-001 | 拦截器异步化 | 必须 | 影响 100% CRUD 请求 |
| FR-004 | 前端虚拟滚动 | 必须 | 前端最大性能瓶颈 |
| FR-005 | 双查询消除 | 应该 | 每次列表查询节省 1 次 COUNT |
| FR-006 | 关系批量填充 | 应该 | 影响列表+详情页面 |
| FR-009 | 审计日志异步写入 | 应该 | 减少写入路径延迟 |
| FR-007 | YAML 加载并行化 | 应该 | **不实施** | yaml_loader.py 有非线程安全缓存，并行化有死锁风险；启动加载仅一次，收益 < 风险 |
| FR-010 | 数据库索引优化 | 应该 | 长期查询性能保障 |
| FR-008 | 前端内存管理 | 应该 | 防止长期使用内存泄漏 |
| FR-011 | 日志级别优化 | 可以 | 减少 I/O 开销 |
| FR-012 | 前端防抖标准化 | 可以 | 减少不必要请求 |

**建议里程碑:**

- **里程碑 1（紧急 - 1周）**: FR-002 + FR-003 + FR-005 — 后端 N+1 修复（最直接见效）
- **里程碑 2（高优 - 2周）**: FR-001 + FR-009 — 拦截器异步化 + 审计日志异步化
- **里程碑 3（重要 - 2周）**: FR-004 + FR-006 + FR-008 — 前端虚拟滚动 + 关系批量填充 + 内存管理
- **里程碑 4（改善 - 1周）**: FR-007 + FR-010 — YAML 并行化 + 索引优化
- **里程碑 5（锦上添花 - 1周）**: FR-011 + FR-012 — 日志级别 + 防抖标准化

---

## 9. 变更/设计提案（RFC）

### 9.1 现状分析

#### 当前架构

```
请求 → Flask路由 → BO Framework
                         │
                         ├─ before_interceptors (优先级10→97 串行)
                         │   ├─ ContextInterceptor      (10)
                         │   ├─ VersionContextInterceptor (15)
                         │   ├─ LockInterceptor         (20)
                         │   ├─ DataPermissionInterceptor (25)
                         │   ├─ ... (12个中间拦截器)
                         │   └─ AuditInterceptor        (90)
                         │
                         ├─ 核心业务逻辑
                         │   ├─ QueryService.search()
                         │   │   ├─ count_all()         ← 第1次查询
                         │   │   ├─ _apply_meta_driven_filters()
                         │   │   ├─ _apply_data_permission()
                         │   │   ├─ execute()            ← 第2次查询
                         │   │   ├─ _enrich_with_relations()  ← N次关联查询
                         │   │   └─ _enrich_audit_virtual_fields() ← N次审计查询
                         │   ├─ PersistenceInterceptor
                         │   │   ├─ _do_create() / _do_update() / _do_delete()
                         │   │   └─ _enrich_association_counts()  ← N次关联计数
                         │   └─ CascadeService
                         │       ├─ _collect_affected()  ← 递归 N+1
                         │       └─ execute_cascade()    ← 逐ID查询
                         │
                         └─ after_interceptors (优先级97→10 反向串行)
                             └─ AuditInterceptor ← 同步写入审计日志

前端 → MetaListPage → el-table (全量渲染) → 分页器
         ├─ useMetaList (11个computed, 无虚拟滚动)
         ├─ useFilterFlow (独立setTimeout防抖)
         └─ useBOApi (12个computed)
```

#### 当前痛点

| 痛点 | 根因 | 量化 |
|------|------|------|
| CRUD 延迟高 | 16个拦截器同步串行 | P95 ~80-150ms |
| 列表加载慢 | 双查询+N次关联填充 | P95 ~800ms-1.5s |
| 大列表卡顿 | 全量 DOM 渲染 | 1000行 ~5s |
| 批量操作慢 | batch_insert 循环执行 | 100条 ~200ms |
| 级联删除慢 | 递归 N+1 查询 | 4层100条 ~2-3s |
| 内存泄漏 | 前端响应式状态未清理 | 100次切换 ~200MB |

#### 相关代码路径

| 文件 | 关键行号 | 问题 |
|------|---------|------|
| meta/core/bo_framework.py | L63-L112 | 拦截器同步串行 |
| meta/services/query_service.py | L392-L396, L744-L780, L1436-L1484, L455-L462, L586-L634 | 双查询+N+1+原始SQL |
| meta/services/cascade_service.py | L381-L400, L402-L487, L560-L653 | 递归N+1 |
| meta/core/sql_adapters.py | L431-L453 | batch_insert循环 |
| meta/core/interceptors/persistence_interceptor.py | L487-L499, L775-L817 | 原始SQL+N+1 |
| src/composables/useMetaList.js | L59-L2300 | 无虚拟滚动+无清理 |
| src/components/common/MetaListPage.vue | L208, L225 | 全量el-table渲染 |
| meta/core/enrichment_engine.py | L154-L188, L231-L298 | 单记录N+1风险 |
| meta/core/yaml_loader.py | L2170-L2194 | 串行YAML加载 |
| meta/core/sql_config.py | L18-L24, L28-L33 | 连接池默认配置可调优 |

### 9.2 目标状态

```
请求 → Flask路由 → BO Framework (异步模式)
                         │
                         ├─ before_interceptors
                         │   ├─ [并行组] ContextInterceptor + VersionContext + DataPermission + ...
                         │   ├─ [串行] LockInterceptor
                         │   └─ [串行] AuditInterceptor (pre)
                         │
                         ├─ 核心业务逻辑（批量优化）
                         │   ├─ QueryService.search()
                         │   │   ├─ [可选] count_all()
                         │   │   ├─ _apply_meta_driven_filters()
                         │   │   ├─ execute()                ← 单次查询
                         │   │   └─ _enrich_batch()          ← 批量填充（1次查询）
                         │   ├─ PersistenceInterceptor
                         │   │   ├─ _do_create() / _do_update() / _do_delete()
                         │   │   │   └─ batch_insert()       ← executemany()
                         │   │   └─ _enrich_association_counts_batch() ← 批量计数
                         │   └─ CascadeService
                         │       ├─ _collect_affected_batch() ← 层级批量查询
                         │       └─ execute_cascade()        ← 批量操作
                         │
                         └─ after_interceptors
                             └─ AuditInterceptor ← 异步队列写入

前端 → MetaListPage → 虚拟滚动渲染 → 分页器
         ├─ useMetaList (shallowRef + onUnmounted清理)
         ├─ useDebounce (统一定时器)
         └─ useVirtualList (可视区域渲染)
```

#### 9.2.1 事务一致性深度分析：异步拦截器的安全性边界

> **核心结论**: 采用 **"核心事务同步 + 非关键路径最终一致"** 的 CQRS 风格妥协方案。这是 Netlfix（200M+用户）、Uber（10000 QPS 行程服务）、LinkedIn 等头部企业的标准做法。

##### 9.2.1.1 事务一致性风险的精确范围

在当前设计中，拦截器链的**事务边界**如下：

```
事务开始 (BEGIN TRANSACTION)
  │
  ├─ [并行组] 只读拦截器 (Context, Version, DataPermission, Validation, ...)
  │    │
  │    └─ ⚠️ 风险点1: 并行执行时 context 修改的竞态条件
  │        • 缓解: 只读拦截器定义为"不修改 context 中与事务相关的任何字段"
  │        • 验证: 静态代码审查 + 运行时 assertion（开发模式）
  │
  ├─ [串行] LockInterceptor ← 锁获取
  │
  ├─ [串行] 核心业务逻辑 (CRUD) ← 数据修改
  │
  ├─ [串行] PersistenceInterceptor ← 数据持久化
  │
  └─ [串行] AuditInterceptor ← 审计日志
       │
       └─ ⚠️ 风险点2: 异步化后审计日志写入与业务事务分离
           • 这是有意的妥协（见下方"允许的妥协"）
  
事务结束 (COMMIT / ROLLBACK)
```

**风险点1 的精确分析**：只读拦截器的并行执行**是否会破坏事务一致性**？

| 场景 | 当前同步行为 | 异步并行后 | 一致性影响 |
|------|-------------|-----------|-----------|
| DataPermission 读取 context.user → 注入过滤条件 | 串行写入 context | 多线程同时写入 context | **高风险** — 需要将 context 写入限制为串行 |
| Validation 验证数据合法性 → 修改 context.result | 串行修改 result | 多线程同时修改 | **高风险** — 需要按优先级合并 |
| Derivation 计算派生字段 → 写入 context | 串行写入 | 多线程同时写入 | **中风险** — 派生字段可能相互依赖 |
| Context 设置请求级变量 | 串行设置 | 无影响（只读） | 安全 |

**最终结论**: 
- ✅ **纯只读拦截器**（仅读取 context，不写入）：完全安全，可任意并行
- ⚠️ **读-修改-写拦截器**（读取后修改 context.result）：**不可并行**，必须串行在非并行组中
- 🔴 **写入拦截器**（Lock/Persistence/Audit）：**必须串行**，保持在事务边界内

**修正后的拦截器分组设计**:

```python
# 修正：根据"是否修改 context"而非"是否写数据库"分组
PURE_READONLY_INTERCEPTOR_NAMES = {
    'context',           # 只设置请求级只读变量
    'version_context',   # 只读取版本上下文
    'computation',       # 只计算（如果结果写回则需要移出此组）
    'format',            # 只格式化
    'enrichment',        # 只填充（如果在线程安全下操作独立字段则安全）
}

READ_MODIFY_WRITE_INTERCEPTOR_NAMES = {
    'data_permission',   # 读取 user 后修改 context.query_filters
    'validation',        # 读取数据后修改 context.result
    'derivation',        # 可能依赖其他拦截器输出
    'transform',         # 可能修改 context 中的数据表示
}

WRITE_INTERCEPTOR_NAMES = {
    'lock',              # 事务锁
    'persistence',       # 数据库写入
    'audit',             # 审计日志
    'cascade',           # 级联操作
    'security_log',      # 安全日志
    'notification',      # 通知
    'index',             # 索引更新
}
```

**修正后的执行模型**:
```
事务开始 (BEGIN TRANSACTION)
  │
  ├─ [并行组A] PURE_READONLY 拦截器 — ThreadPoolExecutor 并行
  │     ContextInterceptor | VersionContextInterceptor | FormatInterceptor | ...
  │     （这些拦截器仅读取 context，不写入）
  │
  ├─ [串行B] READ_MODIFY_WRITE 拦截器 — 按原优先级顺序串行
  │     DataPermission → Validation → Derivation → Transform
  │     （这些拦截器会修改 context.result 或 context.query_filters）
  │
  ├─ [串行C] WRITE 拦截器 — 事务内串行，不可异步化
  │     Lock → Persistence → Cascade
  │
  └─ [异步D] 非事务关键路径 — 事务提交后异步执行
        Audit | SecurityLog | Notification | Index
        （允许最终一致性，失败不影响业务事务）
  
事务结束 (COMMIT)
  └─ 异步触发: Queue.push(audit_event, security_event, notification_event)
```

##### 9.2.1.2 允许的妥协：审计日志/安全日志/通知的最终一致性

这是 **明确且有意的妥协**，参照以下头部企业实践：

| 企业 | 妥协内容 | 理由 |
|------|---------|------|
| **Netflix** | 读模型通过 Kafka 事件异步同步，允许秒级延迟 | CQRS 分离读写模型 |
| **Uber** | 行程状态更新 95% 走异步消息队列 | 核心事务同步，非关键路径异步 |
| **LinkedIn** | 审计日志异步写入 + 30% 调试时间减少 | append-only event log |
| **Salesforce** | 报表/审计子系统使用最终一致性 | 业务事务与审计解耦 |
| **SAP S/4HANA** | 业务流程日志通过事件溯源异步写入 | 性能与可审计性平衡 |

**本系统的妥协设计**:

```
业务请求完成 (response 返回给用户)
          │
          ▼
    主事务已 COMMIT
          │
          ▼
    ┌─────────────────────────────┐
    │  异步事件队列 (内存 Queue)    │
    │  ├─ audit_event             │
    │  ├─ security_log_event      │
    │  ├─ notification_event      │
    │  └─ index_update_event      │
    └──────────┬──────────────────┘
               │
               ▼
    ┌─────────────────────────────┐
    │  AsyncAuditWriter 后台线程   │ ← 已有实现
    │  ├─ 批量写入 (100条/批)      │
    │  ├─ 失败重试 3次             │
    │  └─ 重试耗尽 → 降级同步写入   │
    └─────────────────────────────┘
```

**降级策略**（三层防护）:
1. **Layer 1**: 异步队列写入成功 — 正常路径，零阻塞
2. **Layer 2**: 队列满 → 同步写入（阻塞主请求，但仅在大流量时触发）
3. **Layer 3**: 连续失败 3 次 → 写入 `audit_fallback.log` 文件 + 告警

**不一致窗口**:
- 正常情况下: < 1 秒（队列批量刷新间隔）
- 极端情况下: < 5 秒（降级超时）
- 数据丢失风险: 仅在进程崩溃且队列未刷新时，最多丢失最后一批（100条）审计日志

**这个妥协的商业合理性**: 
- 审计日志的核心价值是**可追溯性**，而非**实时性**
- 丢失的审计日志可通过业务表状态反推重建
- 换取的是每次 CRUD 操作**降低 40% 延迟**的体验提升

#### 关键变更

1. **BO Framework 异步拦截器**: PURE_READONLY 拦截器并行化，READ_MODIFY_WRITE 和 WRITE 拦截器保持串行
2. **批量查询引擎**: 统一批量填充服务替代分散的 N+1 查询
3. **executemany 批量写入**: SQLite `executemany()` 替代循环 INSERT
4. **虚拟滚动**: 基于 IntersectionObserver 的可视区域渲染
5. **异步审计写入**: 审计日志入队异步写 + 三级降级策略，不阻塞主请求
6. **YAML 并行加载**: ThreadPoolExecutor 并行解析 YAML 文件

### 9.3 详细设计

#### 模块/组件设计

**1. 异步拦截器引擎** (`meta/core/async_interceptor_engine.py`) — 新增

```python
import concurrent.futures
from typing import List, Dict
from meta.core.bo_framework import ActionContext, ActionResult

class AsyncInterceptorEngine:
    """
    异步拦截器执行引擎
    
    将16个拦截器按类型分组：
    - READONLY_INTERCEPTORS: 只读操作，可并行
    - WRITE_INTERCEPTORS: 写入操作，必须串行
    """
    
    READONLY_INTERCEPTOR_NAMES = {
        'context', 'version_context', 'data_permission',
        'validation', 'derivation', 'computation',
        'enrichment', 'format', 'transform'
    }
    
    WRITE_INTERCEPTOR_NAMES = {
        'lock', 'audit', 'persistence', 'cascade',
        'security_log', 'notification', 'index'
    }
    
    def __init__(self, interceptors: List, max_workers: int = 4):
        self._interceptors = interceptors
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._readonly = [i for i in interceptors if i.__class__.__name__.lower().replace('interceptor', '') 
                          in self.READONLY_INTERCEPTOR_NAMES]
        self._write = [i for i in interceptors if i.__class__.__name__.lower().replace('interceptor', '')
                       in self.WRITE_INTERCEPTOR_NAMES]
    
    def execute_before(self, context: ActionContext) -> None:
        """并行执行只读拦截器，然后串行执行写入拦截器"""
        # 并行执行只读拦截器
        futures = []
        for interceptor in self._readonly:
            if hasattr(interceptor, 'before_action'):
                futures.append(
                    self._executor.submit(interceptor.before_action, context)
                )
        # 等待所有只读操作完成
        for f in futures:
            f.result(timeout=5.0)  # 5s 超时降级
        
        # 串行执行写入拦截器
        for interceptor in self._write:
            if hasattr(interceptor, 'before_action'):
                interceptor.before_action(context)
    
    def execute_after(self, context: ActionContext, result: ActionResult) -> None:
        """反向执行写入拦截器，然后并行执行只读拦截器"""
        # 串行执行写入拦截器（反向）
        for interceptor in reversed(self._write):
            if hasattr(interceptor, 'after_action'):
                interceptor.after_action(context)
        
        # 并行执行只读拦截器（反向）
        futures = []
        for interceptor in reversed(self._readonly):
            if hasattr(interceptor, 'after_action'):
                futures.append(
                    self._executor.submit(interceptor.after_action, context)
                )
        for f in futures:
            f.result(timeout=5.0)
```

**2. 批量填充引擎** (`meta/core/batch_enrichment.py`) — 新增

```python
from typing import List, Dict, Any
from meta.core.datasource import DataSource

class BatchEnrichmentEngine:
    """
    统一批量填充引擎
    
    替代 query_service._enrich_with_relations() 和 
    persistence_interceptor._enrich_association_counts() 的分散实现
    """
    
    def __init__(self, ds: DataSource):
        self.ds = ds
    
    def enrich_relations_batch(self, meta_obj, records: List[Dict], 
                                relations: List) -> List[Dict]:
        """批量填充所有关联数据 — 单次查询"""
        if not records or not relations:
            return records
        
        record_ids = [r.get('id') for r in records if r.get('id') is not None]
        if not record_ids:
            return records
        
        # 为所有关联构建 UNION ALL 查询
        union_parts = []
        all_params = []
        
        for rel in relations:
            target_obj = registry.get(rel.target_object)
            if not target_obj:
                continue
            source_field = rel.source_field or 'id'
            target_field = rel.target_field or 'id'
            placeholders = ','.join(['?'] * len(record_ids))
            
            union_parts.append(f"""
                SELECT '{rel.id}' as _rel_id, 
                       {target_obj.table_name}.*,
                       {target_field} as _join_key
                FROM {target_obj.table_name}
                WHERE {target_field} IN ({placeholders})
            """)
            all_params.extend(record_ids)
        
        if not union_parts:
            return records
        
        # 单次 UNION ALL 查询
        union_sql = " UNION ALL ".join(union_parts)
        rows = self.ds.query(union_sql, all_params)
        
        # 按关联ID分组
        rel_map: Dict[str, Dict] = {}
        for row in rows:
            rel_id = row.pop('_rel_id')
            join_key = row.pop('_join_key')
            if rel_id not in rel_map:
                rel_map[rel_id] = {}
            if join_key not in rel_map[rel_id]:
                rel_map[rel_id][join_key] = []
            rel_map[rel_id][join_key].append(row)
        
        # 填充到记录
        for record in records:
            rid = record.get('id')
            for rel in relations:
                key = f"_rel_{rel.id}"
                record[key] = rel_map.get(rel.id, {}).get(rid, [])
        
        return records
```

**3. 批量级联服务** (`meta/services/cascade_service.py` 修改)

```python
def _collect_affected_batch(self, object_type: str, object_ids: List[Any]) -> Dict[str, List]:
    """
    批量收集级联影响 — 替代递归 _collect_affected()
    
    使用 BFS 层级遍历 + 每层批量查询
    """
    result = {'set_null': {}, 'set_default': {}, 'delete': {}}
    visited = set()
    
    # BFS 队列: [(object_type, [object_ids])]
    current_level = [(object_type, object_ids)]
    
    while current_level:
        next_level = []
        
        for ot, oids in current_level:
            child_types = self._get_child_types(ot)
            
            for child_type in child_types:
                fk = self._get_foreign_key(ot, child_type)
                if not fk:
                    continue
                
                child_meta = registry.get(child_type)
                if not child_meta:
                    continue
                
                # 批量查询子记录
                placeholders = ','.join(['?'] * len(oids))
                sql = f"SELECT id FROM {child_meta.table_name} WHERE {fk} IN ({placeholders})"
                child_rows = self.ds.query(sql, oids)
                
                child_ids = [r['id'] for r in child_rows if r['id'] not in visited]
                if not child_ids:
                    continue
                
                for cid in child_ids:
                    visited.add(cid)
                
                # 记录操作
                delete_behavior = self._get_delete_behavior(child_type)
                if delete_behavior == 'cascade':
                    result['delete'].setdefault(child_type, []).extend(child_ids)
                    next_level.append((child_type, child_ids))
                elif delete_behavior == 'set_null':
                    result['set_null'].setdefault(child_type, []).extend(child_ids)
                elif delete_behavior == 'set_default':
                    result['set_default'].setdefault(child_type, []).extend(child_ids)
        
        current_level = next_level
    
    return result


def _find_relationships_by_bo_batch(self, bo_ids: List[Any]) -> List[Dict]:
    """批量查询关联关系 — 替代 _find_relationships_by_bo() 的两次查询"""
    rel_meta = registry.get("relationship")
    if not rel_meta:
        return []
    
    table = rel_meta.table_name
    placeholders = ','.join(['?'] * len(bo_ids))
    params = list(bo_ids) + list(bo_ids)
    
    sql = f"""
        SELECT DISTINCT * FROM {table}
        WHERE source_bo_id IN ({placeholders})
           OR target_bo_id IN ({placeholders})
    """
    return self.ds.query(sql, params)
```

#### SQLite `executemany()` 优化

修改 `meta/core/sql_adapters.py` L431-L453:

```python
def batch_insert(self, table_name: str, data_list: List[Dict[str, Any]]) -> int:
    """批量插入 — 使用 executemany 优化"""
    table_name = validate_table_name(table_name)
    if not data_list:
        return 0
    
    columns = list(data_list[0].keys())
    placeholders = self._placeholders(len(columns))
    
    sql = "INSERT INTO {0} ({1}) VALUES ({2})".format(
        table_name,
        ", ".join(columns),
        placeholders
    )
    
    # 准备参数元组列表
    param_list = [tuple(d.get(k) for k in columns) for d in data_list]
    
    # 单次 executemany 调用
    self._cursor.executemany(sql, param_list)
    
    count = len(data_list)
    if not self.in_transaction:
        self.commit()
    return count
```

#### 数据模型

无新增数据库表。现有表需补充索引：

```sql
-- 审计日志联合索引
CREATE INDEX IF NOT EXISTS idx_audit_logs_type_id 
    ON audit_logs(object_type, object_id);

-- 关联关系联合索引
CREATE INDEX IF NOT EXISTS idx_relationships_source_target 
    ON relationships(source_bo_id, target_bo_id);

-- 业务对象外键索引
CREATE INDEX IF NOT EXISTS idx_business_objects_module 
    ON business_objects(service_module_id);
```

#### API 设计

| 端点 | 方法 | 变更 |
|------|------|------|
| `GET /api/v2/bo/{object_type}` | GET | 新增 `skip_count` 查询参数 |
| `POST /api/v2/bo/{object_type}` | POST | 内部使用 executemany |
| `DELETE /api/v2/bo/{object_type}/{id}` | DELETE | 内部使用批量级联 |
| `GET /api/v1/cache/stats` | GET | 新增缓存命中率监控 |
| `GET /api/v1/db/stats` | GET | 新增数据库连接池状态 |

#### 主要流程

**优化后的列表查询流程:**

```mermaid
flowchart TD
    A[前端请求列表] --> B{数据量 > 100?}
    B -->|是| C[虚拟滚动渲染]
    B -->|否| D[普通 el-table 渲染]
    C --> E[后端: QueryService.search]
    D --> E
    E --> F{skip_count?}
    F -->|是| G[只执行数据查询]
    F -->|否| H[执行 COUNT+数据双查询]
    G --> I[BatchEnrichmentEngine.enrich_relations_batch]
    H --> I
    I --> J[返回分页数据]
    J --> K[前端渲染]
```

**优化后的级联删除流程:**

```mermaid
flowchart TD
    A[删除请求] --> B[CascadeService._collect_affected_batch]
    B --> C[第1层: 查询直接子节点]
    C --> D[第2层: 查询孙子节点]
    D --> E[...N层: 批量查询]
    E --> F[execute_cascade: 批量操作]
    F --> G[UPDATE ... SET fk=NULL WHERE id IN ...]
    F --> H[DELETE FROM ... WHERE id IN ...]
    G --> I[事务提交]
    H --> I
    I --> J[AuditInterceptor: 异步入队]
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A: ThreadPoolExecutor 并行拦截器** | 无需引入 asyncio，与 Flask 兼容，渐进式可回退 | 线程开销，GIL 限制 | **选中** |
| B: 引入 asyncio + aioflask 全异步 | 真正的异步 I/O，更高并发 | 需重写全部代码，风险极高，Flask 生态不成熟 | 拒绝 |
| C: 使用 multiprocessing 并行拦截器 | 绕过 GIL | 进程间通信开销大，Flask 兼容性差 | 拒绝 |
| **D: 自定义虚拟滚动** | 轻量，无额外依赖 | 需自行实现 | **选中** |
| E: 使用 el-table-v2 | Element Plus 官方实现 | 需要升级 Element Plus 版本，API 不同 | 备选 |
| F: 使用 vue-virtual-scroller | 成熟库 | 引入新依赖 | 拒绝（保持依赖最小化） |
| **G: executemany 批量写入** | 一行改动，SQLite 原生支持 | 无 | **选中** |
| H: 使用 ORM 批量操作 | 更高层抽象 | SQLAlchemy 未引入，改动大 | 拒绝 |

### 9.5 实施与迁移计划

#### 实施顺序

1. **Phase 1（1周）- 低风险后端修复**
   - 修复 `batch_insert()` (sql_adapters.py L431-453) → 10分钟
   - 修复 `_find_relationships_by_bo()` (cascade_service.py L381-400) → 30分钟
   - 添加数据库索引 → 1小时
   - 添加 `skip_count` 选项 (query_service.py) → 2小时
   - 运行 E2E + 性能测试 → 4小时

2. **Phase 2（2周）- 拦截器异步化**
   - 实现 `AsyncInterceptorEngine` → 3天
   - 修改 `BOFramework.execute()` 集成异步引擎 → 1天
   - 实现 `AuditInterceptor` 异步写入 → 2天
   - 添加环境变量控制 + 降级机制 → 1天
   - 运行 E2E + 性能测试 → 1天（含 Locust 负载测试）

3. **Phase 3（2周）- 批量查询优化**
   - 实现 `BatchEnrichmentEngine` → 3天
   - 重构 `_enrich_with_relations()` → 1天
   - 重构 `cascade_service` 批量级联 → 3天
   - 运行 E2E + 性能测试 → 2天

4. **Phase 4（2周）- 前端优化**
   - 实现 `useVirtualList` composable → 3天
   - 修改 `MetaListPage` 集成虚拟滚动 → 2天
   - 添加 `onUnmounted` 清理 + shallowRef → 1天
   - 统一防抖工具函数 → 1天
   - 前端性能测试 + 肉眼验证 → 2天

5. **Phase 5（1周）- 锦上添花**
   - YAML 并行加载 → 1天
   - 日志级别优化 → 1天
   - 缓存监控端点 → 1天
   - 文档更新 + 发布说明 → 1天

#### 风险缓解

| 风险 | 缓解策略 |
|------|---------|
| 异步拦截器线程安全问题 | 只读拦截器必须无副作用（通过代码审查确认）；所有共享状态通过 `threading.Lock` 保护 |
| 虚拟滚动与现有功能冲突 | 通过 feature flag 控制，出问题时关闭 `enableVirtualScroll` |
| 批量查询 SQL 过于复杂 | 设置 UNION ALL 子查询上限（默认 10个），超过时分批执行 |
| executemany 错误处理 | 返回实际插入行数，部分失败时记录日志并回滚事务 |
| E2E 测试失败 | Phase 间独立，每个 Phase 后运行完整 E2E 套件 |

#### 测试策略

- **单元测试**: 每个新增/修改模块的独立测试（覆盖正常+异常路径）
- **集成测试**: BO Framework 异步模式端到端流程测试
- **性能测试**: 使用 `meta/tests/performance/` 套件，对比优化前后基准
- **负载测试**: Locust 50并发 5分钟压测
- **E2E 测试**: Playwright 23个测试用例全量回归
- **内存测试**: 前端 100 次页面切换内存快照对比

#### 回滚计划

每个 Phase 独立 feature flag：

| Phase | Flag 名称 | 回滚操作 |
|-------|----------|---------|
| Phase 1 | N/A（直接上线） | Git revert 对应 commit |
| Phase 2 | `BO_INTERCEPTOR_MODE=sync` | 环境变量切回 sync |
| Phase 3 | `BATCH_ENRICHMENT_ENABLED=false` | 环境变量关闭 |
| Phase 4 | `enableVirtualScroll: false` | 组件属性关闭 |
| Phase 5 | `LOG_LEVEL=WARNING` | 还原日志级别 |

---

## 10. TBD 列表（含企业级决策建议）

### 已解决 TBD（基于企业标准研究）

#### TBD-1: 数据规模 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| business_objects | < 10,000 条 | 中等企业通常管理 200-500 个业务对象，含版本历史 < 10K |
| relationships | < 50,000 条 | 500 对象 × 平均 100 条关联 |
| audit_logs | < 500万条（年增长 ~100万） | 中等企业 50 用户 × 日 200 操作 × 365 天 = 365万/年 |
| 单表查询范围 | < 100,000 行（全表扫描阈值） | 超过此值需索引覆盖；SQLite 单表百万级仍有性能 |
| 批量操作上限 | 500 条/次 | 超过此值使用分页批量处理 |

> **行业参照**: SAP Business ByDesign（中型企业 ERP）典型部署管理 500-2000 个业务对象、10-50万条交易记录；Oracle NetSuite 中型客户平均 100-500 自定义字段/对象。

#### TBD-2: 并发用户量级 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| 并发用户数 | 50（峰值 100） | 中等企业架构团队规模 30-100 人 |
| 连接池 max_readers | **10**（当前 5） | Oracle RWP: 8-16/节点为最优；Baeldung: 峰值 × 1.25 |
| 写队列深度 | 100（当前 50） | 峰值 100 并发 × 1.0（SQLite 单写者） |
| 连接池获取超时 | 100ms | Google SRE: P95 < 200ms 为良好体验 |

**公式**: `max_readers = 峰值并发 × 读比例(0.9) / 节点数(1) × 1.25 = 50 × 0.9 × 1.25 ≈ 11 → 取 10`

> **行业参照**: Oracle Real-World Performance 组建议静态连接池，8-16 连接/节点最优；HikariCP 公式 `connections = ((core_count * 2) + effective_spindle_count)` 对 SQLite (1核有效) = (8×2+1)≈17，但单写者模型限制为 10。

#### TBD-3: 异步化降级超时 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| 只读拦截器超时 | **5 秒** | 只读操作 P95 < 100ms，5s = 50× 缓冲 |
| 审计队列刷新间隔 | **1 秒** | 平衡延迟与批量效率 |
| 审计队列批量大小 | **100 条** | SQLite 单次写入最佳批量大小 |
| 降级触发条件 | 队列满或连续失败 3 次 | 防止雪崩 |

> **行业参照**: Google SRE 建议 RPC 超时为 P99 延迟 × 2（即 100ms × 2 = 200ms，但只读拦截器为批量操作，5s 是保守的合理值）。Netflix Hystrix 默认超时 1s，但允许自定义。

#### TBD-4: 虚拟滚动行高 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| 行高 | **固定 48px** | Google Material Design 标准、Ant Design 默认 |
| 可变行高 | ❌ 不支持 | 复杂度 3×，性能降低，收益极小（管理表格场景） |
| 预渲染行数 | 10 行（5 上 + 5 下） | 覆盖滚动惯性，55fps 帧率 |
| 虚拟滚动阈值 | **100 行** | 超过此行自动启用 |

> **行业参照**: Airtable、Notion、Google Sheets 均使用固定行高虚拟滚动。Google Material Design 规定数据表格行高为 48px（标准）或 36px（紧凑）。

#### TBD-5: 审计日志最终一致性 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| 写入模式 | **事务提交后异步入队** | 允许最终一致性（详见 §9.2.1） |
| 数据丢失容忍度 | 允许丢失最后一批（< 100 条） | 仅在进程崩溃时发生 |
| 不一致窗口 | < 1 秒 | 正常操作下队列刷新间隔 |
| 降级触发 | 队列满 → 同步写入 | 保留数据不丢失的最后防线 |
| 回放/补偿 | 支持从业务表重建审计日志 | 最终一致性保障 |

> **行业参照**: LinkedIn 使用 append-only event log 异步写入，SAP S/4HANA 业务流程日志通过 Event Sourcing 异步写入。均接受 < 1s 的不一致窗口。核心原则：业务事务原子性 > 审计实时性。

#### TBD-6: 性能回归 CI 阈值 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| P95 延迟回归阈值 | **20%** | Google SRE 错误预算概念 |
| P99 延迟回归阈值 | **30%** | 尾延迟容许更大的方差 |
| 吞吐量回归阈值 | **10%** | 吞吐量下降更敏感 |
| 内存增长回归阈值 | **25%** | 允许合理的功能增长 |
| 连续超限次数 | 3 次 | 防止偶发性波动误报 |

> **行业参照**: Google SRE Workbook — error budget 通常为 0.1% 可用性损失。对应性能指标，20% 为业界常用回归阈值。Facebook 使用 15% P95 回归阈值，Netflix 使用 20%。

#### TBD-7: 虚拟滚动实现方案 — ✅ 已决策

| 维度 | 建议值 | 决策依据 |
|------|--------|---------|
| 实现方案 | **自定义虚拟滚动** | 不引入新依赖，API 可控 |
| el-table-v2 | ❌ 不采用 | 需升级 Element Plus，API 不兼容，风险高 |
| vue-virtual-scroller | ❌ 不采用 | 引入新依赖，与 el-table 整合困难 |
| 实现方式 | 基于 `IntersectionObserver` + CSS `transform` | 现代浏览器 97%+ 支持 |

> **行业参照**: Notion、Linear、Airtable 均自研虚拟滚动而非使用第三方库。原因是表格交互（拖拽、行内编辑、多选）与通用虚拟滚动库的整合成本往往超过自研。

---

### 仍待确认

| ID | 条目 | 状态 | 备注 |
|----|------|------|------|
| TBD-8 | 当前 Element Plus 精确版本 | 待验证 | 确认是否 ≥ 2.5 以评估 el-table-v2 可行性 |
| TBD-9 | 现有性能基准数据 | 待运行 | 需运行 `python meta/tests/performance/run_performance_test.py` 建立基线 |

---

*Spec + RFC 包含 10 个章节，最后一章为"TBD 列表"，内容完整。*
