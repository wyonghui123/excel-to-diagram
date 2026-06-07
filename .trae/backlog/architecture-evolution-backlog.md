# 架构平台化演进 Backlog

> 记录 Phase 3 和 Phase 4 的架构演进计划
>
> **最后更新**: 2026-05-03

---

## Phase 3 - 智能能力（已完成: Phase 1 + Phase 2）

### 已完成明细

| 子阶段 | 内容 | 状态 | 文件 |
|--------|------|------|------|
| 1-A | RedundancyRegistry 冗余字段注册表 | ✅ | `meta/core/redundancy_registry.py` |
| 1-B | WriteGuard / CascadeGuard / RedundancyAuditor | ✅ | `meta/core/consistency_guard.py` |
| 1-C | EnrichmentEngine 元数据驱动 enrichment | ✅ | `meta/core/enrichment_engine.py` |
| 2-A | AnalyticalEngine OLAP 查询引擎 | ✅ | `meta/core/analytical_engine.py` |
| 2-B | AggregateManager 物化聚合管理 | ✅ | `meta/core/aggregate_manager.py` |
| 2-C | 事件驱动聚合刷新 | ✅ | `meta/core/aggregate_refresh_handler.py` |
| 2-D | 层级导航 + 维度发现 + 查询缓存 | ✅ | `meta/core/analytical_engine.py` |

---

## Phase 3 - 智能能力（待处理）

### P1 - 时序模型支持 ⭐

**描述**: 引入时间维度支持，实现版本快照、变更历史和趋势分析能力

**状态**: 待处理

**原因**: 当前模型缺少时间维度，无法支持历史版本对比和变更追踪

**预估工作量**: 5-7 天

**依赖**: Phase 2 完成

**待实现内容**:
- [ ] `temporal_model` YAML schema 扩展
  - [ ] `valid_from` / `valid_to` 时间有效区间字段声明
  - [ ] `version_snapshots` 快照策略定义（full/incremental）
  - [ ] `change_tracking` 变更历史记录策略
- [ ] `TemporalEngine` 时序查询引擎
  - [ ] `as_of(date)` 历史快照查询
  - [ ] `between(start, end)` 区间查询
  - [ ] `track_changes(object_type, record_id)` 变更链
- [ ] 趋势分析 API
  - [ ] `POST /stats/trend/<object_type>` 趋势查询
  - [ ] `GET /stats/history/<object_type>/<id>` 变更历史

---

### P2 - AI 语义层 ⭐⭐

**描述**: 引入自然语言查询和语义推荐能力

**状态**: 待处理

**原因**: 提升用户体验，降低数据分析门槛

**预估工作量**: 10-15 天

**依赖**: Phase 2 完成，LLM API 可用

**待实现内容**:
- [ ] `semantic_layer` YAML schema 扩展
  - [ ] `natural_language_queries` 自然语言查询模板
  - [ ] `semantic_synonyms` 同义词定义
  - [ ] `intent_classification` 意图分类标签
- [ ] `SemanticLayer` 服务
  - [ ] `parse_natural_query(query)` 意图解析
  - [ ] `suggest_dimensions(intent)` 维度推荐
  - [ ] `suggest_measures(intent)` 度量推荐
  - [ ] `generate_olap_from_text(text)` 文本 → OLAP 转换
- [ ] AI 集成 API
  - [ ] `POST /stats/ai/query` 自然语言查询
  - [ ] `GET /stats/ai/suggest` 智能推荐
  - [ ] `POST /stats/ai/explain` 查询结果解释

---

## Phase 4 - 平台化（待处理）

### P1 - 多租户数据隔离 ⭐⭐⭐

**描述**: 实现租户级数据隔离，支持多团队协作

**状态**: 待处理

**原因**: 企业级平台必须支持多租户数据隔离

**预估工作量**: 7-10 天

**依赖**: Phase 2 完成

**待实现内容**:
- [ ] `tenant_model` YAML schema 扩展
  - [ ] `tenant_id` 租户标识字段声明
  - [ ] `isolation_level` 隔离级别（strict/shared）
  - [ ] `cross_tenant_access` 跨租户访问策略
- [ ] `TenantContext` 租户上下文
  - [ ] `set_current_tenant(tenant_id)` 上下文设置
  - [ ] `get_tenant_filter()` 自动注入租户过滤
  - [ ] `validate_tenant_access(record)` 访问校验
- [ ] 中间件层改造
  - [ ] `TenantMiddleware` 请求上下文注入
  - [ ] `TenantAwareDataSource` 租户感知数据源
- [ ] API 端点改造
  - [ ] 所有 CRUD 端点自动注入 tenant_id 过滤
  - [ ] 租户管理 API: `GET/POST /tenants`

---

### P2 - 数据联邦 ⭐⭐

**描述**: 支持跨数据源联合查询

**状态**: 待处理

**原因**: 企业数据分布在多个系统，需要统一查询能力

**预估工作量**: 10-15 天

**依赖**: Phase 2 完成

**待实现内容**:
- [ ] `federation_model` YAML schema 扩展
  - [ ] `external_datasources` 外部数据源定义
  - [ ] `federated_objects` 联邦对象映射
  - [ ] `sync_strategy` 同步策略（realtime/lazy/scheduled）
- [ ] `DataFederationEngine` 联邦引擎
  - [ ] `register_datasource(name, config)` 注册外部数据源
  - [ ] `federated_query(object_type, dims, measures)` 跨源查询
  - [ ] `sync_federated_object(object_type)` 手动同步
- [ ] 外部数据源适配器
  - [ ] `PostgreSQLAdapter` PostgreSQL 适配器
  - [ ] `MySQLAdapter` MySQL 适配器
  - [ ] `RESTAdapter` REST API 适配器
- [ ] API 端点
  - [ ] `GET /stats/federated/<object_type>` 联邦查询
  - [ ] `POST /stats/federation/sync` 手动同步

---

### P3 - 开放 API 生态 ⭐⭐

**描述**: 提供标准化的 Open API 支持和 Webhook 事件通知

**状态**: 待处理

**原因**: 平台需要与外部系统集成

**预估工作量**: 5-7 天

**依赖**: Phase 2 完成

**待实现内容**:
- [ ] `open_api` YAML schema 扩展
  - [ ] `exposed_endpoints` 暴露端点定义
  - [ ] `api_keys` API Key 管理
  - [ ] `rate_limits` 限流策略
- [ ] OpenAPI 3.0 规范生成
  - [ ] `generate_openapi_spec()` 自动生成规范
  - [ ] `serve_openapi_ui()` Swagger UI 托管
- [ ] Webhook 事件通知
  - [ ] `WebhookService` Webhook 管理服务
  - [ ] `POST /webhooks` 注册 Webhook
  - [ ] `GET/DELETE /webhooks/<id>` 管理 Webhook
  - [ ] 变更事件自动触发 Webhook 调用

---

## 附录: Phase 1-2 架构文件索引

### 核心引擎
| 文件 | 职责 |
|------|------|
| `meta/core/redundancy_registry.py` | 冗余字段注册表（Type-A/B/C 分类、级联链） |
| `meta/core/consistency_guard.py` | WriteGuard/CascadeGuard/RedundancyAuditor |
| `meta/core/enrichment_engine.py` | 元数据驱动 enrichment（Joins 路径解析） |
| `meta/core/analytical_engine.py` | OLAP 查询引擎 + 层级导航 + 缓存 |
| `meta/core/aggregate_manager.py` | 物化聚合管理器 |
| `meta/core/aggregate_refresh_handler.py` | 事件驱动聚合刷新处理器 |

### API 层
| 文件 | 端点数 |
|------|--------|
| `meta/api/stats_api.py` | 20+ OLAP/聚合/缓存端点 |
| `meta/api/manage_api.py` | CRUD + enrichment |

### YAML Schema 扩展
| 文件 | 扩展字段 |
|------|----------|
| `meta/schemas/relationship.yaml` | `redundancy` + `analytical_model` |
| `meta/schemas/business_object.yaml` | `redundancy` + `analytical_model` |
| `meta/schemas/version.yaml` | `redundancy` |
| `meta/schemas/domain.yaml` | `redundancy` |
| `meta/schemas/sub_domain.yaml` | `redundancy` |
| `meta/schemas/service_module.yaml` | `redundancy` |

### 测试文件
| 文件 | 测试数 |
|------|--------|
| `meta/tests/test_redundancy_registry.py` | 21 |
| `meta/tests/test_consistency_guard.py` | 6 |
| `meta/tests/test_enrichment_engine.py` | 10 |
| `meta/tests/test_analytical_engine.py` | 20 |
| `meta/tests/test_aggregate_manager.py` | 17 |
| `meta/tests/test_aggregate_refresh_integration.py` | 3 |
| `meta/tests/test_analytical_engine_v2.py` | 33 |
| **合计** | **110** |
