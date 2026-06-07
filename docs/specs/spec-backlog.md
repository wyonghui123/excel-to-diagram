# Spec Backlog - 架构升级待办清单

> **更新日期**: 2026-05-22
> **架构版本**: ARCHITECTURE_V2.md v2.3.0
> **配置分层**: 三层模型研究完成（开发级/配置级/个性化级）
> **对标产品**: Salesforce · SAP S/4HANA · ServiceNow · Kubernetes · Palantir
> **研究报告**: [research-yaml-config-boundary.md](./research-yaml-config-boundary.md)

---

## 〇、架构研究里程碑 🆕

| # | 研究成果 | 报告 | 完成日期 |
|---|---------|------|---------|
| R1 | 五产品三层配置分层模型 (SF/SAP/SN/K8s/Palantir) | [research-yaml-config-boundary.md](./research-yaml-config-boundary.md) | 2026-05-22 |
| R2 | ALTER TABLE vs 纯元数据硬边界 | [research-yaml-config-boundary.md §4](./research-yaml-config-boundary.md#4-边界模型的两次迭代修正) | 2026-05-22 |
| R3 | YAML/DB 单一事实分工方案 | [research-yaml-config-boundary.md §12-13](./research-yaml-config-boundary.md#12-yaml-承载配置-vs-db-承载配置) | 2026-05-22 |
| R4 | KeyTemplate 引擎设计 + 启用对象确认 | [spec-key-template.md](./spec-key-template.md) | 2026-05-22 |
| R5 | Record Type 设计 | [research-yaml-config-boundary.md §10](./research-yaml-config-boundary.md#10-record-type配置级的核心承载体) | 2026-05-22 |
| R6 | Action Types (AI Agent 操作契约) | [research-yaml-config-boundary.md §14-15](./research-yaml-config-boundary.md#14-palantir-深度分析ai-原生平台的全-gui-配置模式) | 2026-05-22 |
| R7 | AI Agent 原生场景架构演进 | [research-yaml-config-boundary.md §11](./research-yaml-config-boundary.md#11-ai-agent-原生场景下的架构演进) | 2026-05-22 |

### 关键架构决策

| 决策 | v1.0 逻辑 | v1.1 修正 |
|------|---------|---------|
| 配置表命名 | `config_overrides`（默认值+覆盖） | `config_values`（唯一来源） |
| YAML 是否存默认值 | 是 | **否** —— YAML 只定义结构/类型约束 |
| 同一配置项几个来源 | 两个（YAML + DB） | **一个**（DB） |
| 初始值来源 | YAML 内置 | **部署脚本**写入 DB |
| KeyTemplate pattern 在哪 | YAML 存默认值 + DB 覆盖 | 引擎定义 YAML，值 DB（不重叠） |

---

## 一、Phase 3 架构优化 ✅ 已完成

| 功能 | 状态 | Spec 文档 |
|------|------|----------|
| FR-001: Deep Insert/Update API | ✅ 已完成 | [spec-phase3-architecture-enhancement.md](./spec-phase3-architecture-enhancement.md) |
| FR-002: 多态 Composition | ✅ 已完成 | [spec-phase3-architecture-enhancement.md](./spec-phase3-architecture-enhancement.md) |
| FR-003: Formula 增强 | ✅ 已完成 | [spec-phase3-formula-state-schema.md](./spec-phase3-formula-state-schema.md) |
| FR-004: 状态模式定义 | ✅ 已完成 | [spec-phase3-formula-state-schema.md](./spec-phase3-formula-state-schema.md) |
| Phase 3.5: 状态转换按钮组件 | ✅ 已完成 | [spec-phase3-formula-state-schema.md](./spec-phase3-formula-state-schema.md) |

### Phase 3.5 已交付功能

| 组件 | 文件 | 说明 |
|------|------|------|
| 状态转换 API | `meta/api/manage_api.py` | `GET /manage/<object_type>/<id>/state_transitions` |
| 状态转换按钮组件 | `src/components/bo/StateTransitionButtons.vue` | 自动从 API 获取规则并渲染按钮 |
| 详情页集成 | `ObjectPage.vue` + `DetailPage.vue` | 状态字段区域显示转换按钮 |

### Phase 3.5 待办（暂缓）

- [ ] **状态历史时间线组件** - 在详情页或独立抽屉中显示（暂缓实施）

---

## 二、存量对象采纳计划

### 2.1 Formula 采纳 ✅

| 对象 | 场景 | 公式 | 优先级 | 状态 |
|------|------|------|--------|------|
| change_event | 投递延迟计算 | `IF(ISNULL(delivered_at), DATEDIFF(created_at, NOW(), "seconds"), DATEDIFF(created_at, delivered_at, "seconds"))` | 高 | ✅ 已完成 |
| user | 不活跃天数 | `IF(ISNULL(last_login_at), DATEDIFF(created_at, NOW(), "days"), DATEDIFF(last_login_at, NOW(), "days"))` | 高 | ✅ 已完成 |
| user | 账号年龄 | `DATEDIFF(created_at, NOW(), "days")` | 高 | ✅ 已完成 |
| user | 当前状态停留天数 | `IF(ISNULL(status_entered_at), 0, DATEDIFF(status_entered_at, NOW(), "days"))` | 高 | ✅ 已完成 |
| domain/sub_domain/service_module | BO密度计算 | `ROUND(DIVIDE(relation_count, child_count, 0), 2)` | 中 | ✅ 已完成 |
| audit_log | 日志老化计算 | 建议: `DATEDIFF(created_at, NOW(), "hours")` | 中 | 待实施 |
| relationship | 范围标签增强 | 建议: `IF(DATEDIFF(created_at, NOW(), "days") > 90, "stale", "active")` | 低 | 待实施 |

### 2.2 State 采纳 ✅

| 对象 | 状态字段 | 状态值 | 转换规则 | 优先级 | 状态 |
|------|----------|--------|----------|--------|------|
| change_event | status | pending/processing/delivered/failed | 4条: process_event, deliver_event, fail_event, retry_event | 高 | ✅ 已完成 |
| user | status | active/inactive/locked | 3条: activate_user, lock_user, deactivate_user | 高 | ✅ 已完成 |
| audit_log | status | pending/written/failed | 3条: mark_written, mark_failed, retry_write | 中 | ✅ 已完成 |
| product | is_active | true/false | 2条: activate_product, deactivate_product | 低 | ✅ 已完成 |
| version | is_current | true/false | 2条: set_current_version, unset_current_version | 低 | ✅ 已完成 |
| change_subscription | enabled | true/false | 2条: enable_subscription, disable_subscription | 低 | ✅ 已完成 |

### 2.3 已采纳配置详情

#### change_event.yaml

**Formula 字段**:
```yaml
- id: delivery_latency_seconds
  name: 投递延迟秒数
  type: integer
  storage: virtual
  computation:
    formula: 'IF(ISNULL(delivered_at), DATEDIFF(created_at, NOW(), "seconds"), DATEDIFF(created_at, delivered_at, "seconds"))'
```

**State 配置**:
- enum_values: pending(初始), processing, delivered(终态), failed
- 状态转换规则: 4条（开始处理、投递成功、投递失败、重试）
- status_entered_at 字段: 用于计算状态停留时长

#### user.yaml

**Formula 字段**:
```yaml
- id: inactive_days
  computation:
    formula: 'IF(ISNULL(last_login_at), DATEDIFF(created_at, NOW(), "days"), DATEDIFF(last_login_at, NOW(), "days"))'

- id: account_age_days
  computation:
    formula: 'DATEDIFF(created_at, NOW(), "days")'

- id: current_status_duration_days
  computation:
    formula: 'IF(ISNULL(status_entered_at), 0, DATEDIFF(status_entered_at, NOW(), "days"))'
```

**State 配置**:
- enum_values: active, inactive(初始), locked
- 状态转换规则: 3条（激活、锁定、停用）
- status_entered_at 字段: 用于计算状态停留时长

---

## 三、后续 Phase 规划

### Phase 4: 高级元数据能力

| 功能 | 说明 | Spec | 状态 |
|------|------|------|------|
| ~~Soft Delete~~ | ~~逻辑删除~~ → **已替换为 audit_log 恢复** | [spec-soft-delete.md](./spec-soft-delete.md) | ⚠️ 已废弃 |
| Audit Log 恢复 | 从审计日志恢复已删除记录（取代 Soft Delete） | [spec-audit-log-recovery.md](./spec-audit-log-recovery.md) | ✅ 已完成 |
| **KeyTemplate** | 声明式编码模板引擎（business_object/version/relationship） | [spec-key-template.md](./spec-key-template.md) | 设计中 |
| **RecordType** | 记录类型，配置级核心承载体（不同字段集/校验/业务逻辑） | [research-yaml-config-boundary.md §10](./research-yaml-config-boundary.md#10-record-type配置级的核心承载体) | 待设计 |
| Effective Dating | 有效期管理，支持历史数据追踪 | 待设计 | 待定 |
| **Action Types** 🆕 | AI Agent 操作契约与安全护栏 (Palantir/SAP 模式) | [research-yaml-config-boundary.md §14](./research-yaml-config-boundary.md#14-palantir-深度分析ai-原生平台的全-gui-配置模式) | 待设计 |
| **配置分层实现** | Tier 2 config_values 表 + 热加载 + 部署脚本 | [research-yaml-config-boundary.md §9](./research-yaml-config-boundary.md#9-三层配置分层模型开发级--配置级--个性化级) | 待设计 |
| **Schema 热加载** | Schema 变更后不重启生效（配置BO迁移前置条件） | [research-yaml-config-boundary.md §6.2](./research-yaml-config-boundary.md#62-元数据热加载的必要性) | 待设计 |

#### KeyTemplate 设计决策摘要

| 决策项 | 结论 |
|--------|------|
| 启用对象 | business_object / version / relationship（3个，不包括 product/domain/sub_domain/service_module/role/user_group） |
| 交互方式 | auto_suggest（自动建议，用户可变更），非 auto_generate（强制） |
| 存量数据处理 | auto_detect: true，扫描 MAX(已有序号) + 1 |
| relationship code | **需新增字段** — 8个核心对象唯一缺 code |
| SAP 对标位置 | IMG/SNRO（配置级），不在 DDIC（开发级） |
| YAML 承载 | 引擎定义（segments 类型、auto_detect 机制、序列引擎） |
| DB 承载 | 配置值（pattern、start 编号）— 部署脚本写入初始值 |
| 当前策略 | 引擎 + 值暂存 YAML（唯一来源），config_values 就绪后拆分 |

### Phase 5: 企业级扩展（待细化）

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 流程引擎 | BPMN 2.0 兼容的工作流引擎 | 待定 |
| 多租户隔离 | 租户数据隔离与权限控制 | 待定 |
| 审计增强 | 完整的变更追踪与合规报告 | 待定 |

### Phase 未排期：基础设施优化

| 功能 | 说明 | 优先级 |
|------|------|--------|
| Technical ID 优化 | auto_increment→可选UUID/hash，跨环境数据合并安全 | 低 |

---

## 四、近期待办

### 4.1 高优先级 ✅ 已完成

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 1 | change_event Formula采纳 | 投递延迟计算 | ✅ 已完成 |
| 2 | change_event State采纳 | 事件生命周期状态机 | ✅ 已完成 |
| 3 | user Formula采纳 | 不活跃天数 + 账号年龄 + 状态停留天数 | ✅ 已完成 |

### 4.2 中优先级 ✅ 已完成

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 4 | audit_log State采纳 | 写入补偿状态机（pending/written/failed + 3条规则） | ✅ 已完成 |
| 5 | domain/sub_domain/service_module Formula采纳 | BO密度计算 | ✅ 已完成（已实现） |
| 6 | 状态历史时间线组件 | 详情页或独立抽屉显示 | 暂缓 |

### 4.3 低优先级 ✅ 已完成

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 7 | product/version State采纳 | 启用/停用状态机 + 当前版本互斥 | ✅ 已完成 |
| 8 | change_subscription State采纳 | boolean映射语义状态 | ✅ 已完成 |

### 4.4 研究设计 🆕

| # | 任务 | 说明 | Spec | 状态 |
|---|------|------|------|------|
| 9 | KeyTemplate 方案设计 | 声明式编码模板引擎（YAML引擎+DB值） | [spec-key-template.md](./spec-key-template.md) | 设计中 |
| 10 | relationship code 字段 | 新增实例编码字段，补全8个核心对象唯一缺code | [spec-key-template.md §5.1](./spec-key-template.md#51-relationship-为何需要-code-字段) | 待实现 |
| 11 | 配置分层架构研究 | 三层配置模型 + 五产品对标 | [research-yaml-config-boundary.md](./research-yaml-config-boundary.md) | ✅ 已完成 |
| 12 | Record Type 设计 | 配置级核心承载体 | [research-yaml-config-boundary.md §10](./research-yaml-config-boundary.md#10-record-type配置级的核心承载体) | 待设计 |
| 13 | Action Types 设计 | AI Agent 操作契约 | [research-yaml-config-boundary.md §14](./research-yaml-config-boundary.md#14-palantir-深度分析ai-原生平台的全-gui-配置模式) | 待设计 |

---

## 五、下一步动作

### 已完成 ✅

**Phase 3 全部完成**:
- ✅ Deep Insert/Update API
- ✅ 多态 Composition
- ✅ Formula 增强（48个函数）
- ✅ 状态模式定义
- ✅ 状态转换按钮组件

**存量对象采纳全部完成**:
- ✅ change_event: Formula + State
- ✅ user: Formula + State
- ✅ audit_log: State（写入补偿状态机）
- ✅ product: State（启用/停用）
- ✅ version: State（当前版本互斥）
- ✅ change_subscription: State（语义化状态）
- ✅ BO密度计算（已实现）

**架构研究 ✅**:
- ✅ 五产品三层配置分层对标（SF/SAP/SN/K8s/Palantir）
- ✅ ALTER TABLE vs 纯元数据硬边界
- ✅ YAML/DB 单一事实分工方案
- ✅ KeyTemplate 引擎设计 + 启用对象确认
- ✅ Record Type 设计方向
- ✅ Action Types 设计方向
- ✅ AI Agent 原生场景演进分析

### 当前进行中 🔄

1. **KeyTemplate Phase 1** — 声明式编码模板引擎
   - YAML 引擎定义 + pattern 值暂存 YAML（唯一来源）
   - business_object / version / relationship 三个对象
   - relationship 需先新增 `code` 字段
   - Spec: [spec-key-template.md](./spec-key-template.md)

### 待办

1. **短期（Phase 4）**
   - KeyTemplate 实施
   - relationship code 字段新增
   - Record Type 设计 Spec
   - Action Types 设计 Spec

2. **中期（Phase 4-5）**
   - Schema 热加载实现
   - config_values 表设计 + 部署脚本
   - Effective Dating 设计

3. **远期（Phase 5+）**
   - 流程引擎（BPMN 2.0）
   - 多租户隔离
   - 审计增强
   - Technical ID 优化

### 参考文档

| 文档 | 路径 |
|------|------|
| 架构主文档 | [ARCHITECTURE_V2.md](../ARCHITECTURE_V2.md) |
| 配置分层研究报告 | [research-yaml-config-boundary.md](./research-yaml-config-boundary.md) |
| KeyTemplate Spec | [spec-key-template.md](./spec-key-template.md) |
| Audit Log 恢复 Spec | [spec-audit-log-recovery.md](./spec-audit-log-recovery.md) |

---

> **最后更新**: 2026-05-22
