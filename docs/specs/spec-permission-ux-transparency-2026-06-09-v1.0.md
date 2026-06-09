# Spec: 权限派生 UX 透明性 (Permission UX Transparency)

**版本**: v1.0
**日期**: 2026-06-09
**作者**: AI Coding Agent
**关联**: spec-permission-derivation-MASTER-PLAN-2026-06-08

## 1. Background & Objectives

### 1.1 Background

当前项目的权限派生体系（基于 `role_dimension_scopes`）已实现：
- ✅ children 上的实例级权限 (例: `version ∈ [2,11,12]`)
- ✅ 兄弟隔离 (TEST60 看不到 version 1, 即使它是 product 1 的另一个 version)
- ✅ 父 BO 向上扩展 (TEST60 配 version 也能看到 product 列表)
- ✅ 多角色合并 + Owner 过滤 + AND 组合

**剩余问题** (基于 2026-06-08 SPEC §6 优化建议):
1. **配置不透明**: 系统管理员在配置 `dimension scope` 时，不知道这会"级联"到哪些 children，不确定是否会产生兄弟隔离
2. **结果不透明**: 业务用户查列表时，看到 N 条数据，但不知道 "总共有 M 条，我有权限的只有 N 条"；可能误以为系统缺数据
3. **配置粒度繁琐**: 想给 product 1 下所有 versions 权限 → 要在 children (version) 维度逐个勾选；当前 `inherit_children=1` 字段可"级联"但 UI 不直观
4. **未来 DNF 需求**: 业务侧需支持"规则1 OR 规则2 (内部 AND)"，但当前 schema 不支持

### 1.2 Business Objectives

| ID | 目标 | 度量 |
|----|------|------|
| BO-1 | 降低权限配置错误率 | 业务反馈 "我配了但看不到" 案例数 → 0 |
| BO-2 | 提升配置效率 | 配 "product 1 + inherit children" 的操作步骤：从 N 次勾选 → 1 次选择 |
| BO-3 | 用户体验可预测 | 列表页 "可见 X/Y" 提示覆盖 100% 业务对象 |

### 1.3 User / Stakeholder (涉众) Objectives

| 涉众 | 目标 |
|------|------|
| **系统管理员** (SRE/SecOps) | 配置 dimension scope 时有"影响预览"，避免配错 |
| **业务用户** (PM/Dev) | 看到列表时，明确知道 "3 of 8 visible" |
| **审计员** (Compliance) | 看到完整统计，与 audit log 对账 |

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|------------|----------|
| Business | Yes | spec-permission-derivation-MASTER-PLAN §6 |
| User/Stakeholder | Yes | 用户多轮反馈 "看不到/没想到" |
| Solution | Yes | 已存在 dimension_scope / RuntimeDimensionResolver |
| Functional | Yes | FR-001 ~ FR-004 |
| Nonfunctional | Yes | NFR-001 ~ NFR-003 (性能、可观测性) |
| External Interface | Yes | IF-001 (API), IF-002 (UI) |
| Transition | Yes | TR-001 (DB schema 兼容) |

## 3. Functional Requirements

### FR-001: 列表页可见性统计 (按需加载)

- **Description**: 业务对象列表页 (`/api/v2/bo/{type}`) 应支持"显示完整统计" 按钮，点击后返回 `{visible_count, total_count, denied_count}`。**默认不显示，按需展开** (避免每次 list 多发一次 COUNT 查询)。
- **Acceptance Criteria**:
  1. 默认 `GET /api/v2/bo/version` 响应不包含统计字段 (无性能损失)
  2. `GET /api/v2/bo/version?with_stats=true` 响应增加 `meta: {visible_count, total_count, denied_count}`
  3. 列表页 header 在用户点击"显示统计"按钮后渲染 "可见 X/Y (Z 个无权限)" 中文提示
  4. 权限无 dimension scope 配置时，`denied_count = total_count` (全部可见，无受限)
  5. 权限未登录时返回 401，不返回统计
- **Priority**: Must
- **Type Mapping**: User + Functional
- **Source**: 2026-06-08 用户反馈 "我以为系统没数据"

### FR-002: 配置时影响范围预览 (保存前)

- **Description**: 角色权限配置页的 dimension scope 区域，应在用户**保存前**预览"如果保存此 scope，将影响多少个 resources (含 children 展开)"
- **Acceptance Criteria**:
  1. 配 `version ∈ [2,11,12]` 时，预览显示: "将级联到 2 个 products (product 1, 17), 3 个 versions (id 2, 11, 12)"
  2. 配 `product ∈ [1]` + `inherit_children=1` 时，预览显示: "将级联到 product 1 下 2 个 versions"
  3. 预览是**实时计算**（用户改 scope 时同步刷新），**不写入 DB**
  4. 预览失败时降级为"无法预览"，不阻塞保存
- **Priority**: Must
- **Type Mapping**: User + Functional
- **Source**: spec §1.1 (业务目标 BO-2)

### FR-003: "不选 children = 不过滤" 语义明确化

- **Description**: 系统应在配置 UI 上**显式说明**"未选择 children = 看到所有 children"，避免用户误以为"没配 = 没权限"
- **Acceptance Criteria**:
  1. dimension scope 配置区域顶部显示提示: "💡 提示: 未选 = 不过滤 (即 SAP 留空语义)。如需严格隔离，请显式选择具体值。"
  2. 提示支持 i18n key
  3. 不增加 DB schema 变更
- **Priority**: Should
- **Type Mapping**: User + Functional
- **Source**: 用户疑问 "是不是不选择 children 就是不过滤"

### FR-004: DB Schema 兼容 DNF (预留)

- **Description**: `role_dimension_scopes` 表增加 `rule_group_id` 字段，**默认 NULL** (兼容旧数据)；为未来 DNF "OR 规则组" 预留扩展点
- **Acceptance Criteria**:
  1. `rule_group_id` 字段 (INTEGER, nullable, default NULL)
  2. 同一 rule_group 内 AND 组合；不同 rule_group 间 OR 组合 (语义文档化，**本 Spec 不实现** 解析逻辑)
  3. NULL 视为 rule_group = -1 (单规则，行为与现状一致)
  4. 现有所有 scope 行为不变 (向后兼容)
- **Priority**: Should
- **Type Mapping**: Solution + Transition
- **Source**: 用户 "未来支持多个条件规则"

## 4. Nonfunctional Requirements

### NFR-001: 性能 - 按需加载 (默认无开销)

- **Description**: 列表默认请求不增加 COUNT 查询；`with_stats=true` 时单次 COUNT 查询 < 200ms (10K rows)
- **Measurement**:
  - 不带 `with_stats`: 响应时间增量 < 5ms
  - 带 `with_stats`: P95 < 200ms (10K rows)
- **Priority**: Must
- **Source**: 用户 "大数据量 (10K+) 性能" 关注

### NFR-002: 可观测性 - 统计缓存

- **Description**: 同一用户对同一 BO 的 `with_stats=true` 查询，5 分钟内复用缓存 (PermissionCache 复用)
- **Measurement**:
  - 缓存命中 < 0.1ms
  - 缓存 key: `(user_id, bo_id, query_filters_hash)`
- **Priority**: Should

### NFR-003: i18n 支持 (中文优先)

- **Description**: UI 提示文字 (FR-001, FR-002, FR-003) 走 i18n key；当前 Locale = zh-CN
- **Acceptance**: 文案在 `src/locales/zh-CN.json` + `en-US.json` 都注册
- **Priority**: Could

### NFR-004: 可回滚 - Feature Flag

- **Description**: FR-001 ~ FR-003 受 feature flag `PERMISSION_UX_TRANSPARENCY` 控制，默认开启
- **Acceptance**: 关闭后行为退回到 Spec 实施前
- **Priority**: Must (灰度发布)

## 5. External Interface Requirements

### IF-001: 业务对象列表 API 扩展

- **Type**: API
- **Endpoint**: `GET /api/v2/bo/{object_type}?with_stats=true&page=1&page_size=20`
- **Request**: 增加 query param `with_stats: bool` (默认 false)
- **Response Schema (新增)**:
  ```json
  {
    "data": {
      "items": [...],
      "pagination": {...}
    },
    "meta": {
      "visible_count": 3,
      "total_count": 8,
      "denied_count": 5,
      "with_stats": true
    }
  }
  ```
- **Error Handling**:
  - 计算失败 → 返回 `meta: {stats_error: "原因"}`，`items` 仍正常返回 (不阻塞列表)
- **Source**: FR-001

### IF-002: Dimension Scope 预览 API

- **Type**: API
- **Endpoint**: `POST /api/v2/role/{role_id}/dimension-scope/preview`
- **Request Body**:
  ```json
  {
    "scopes": [
      {"dimension_code": "version", "dimension_values": [2, 11, 12], "inherit_children": true}
    ]
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "expanded": {"version": [2,11,12], "product": [1,17]},
      "affected_resources": [
        {"type": "product", "ids": [1, 17]},
        {"type": "version", "ids": [2, 11, 12]}
      ],
      "warnings": []
    }
  }
  ```
- **Source**: FR-002

## 6. Transition Requirements

### TR-001: DB Schema 迁移 - rule_group_id

- **Description**: 给 `role_dimension_scopes` 表增加 `rule_group_id` 列 (nullable)
- **Strategy**:
  - Alembic 迁移: `ALTER TABLE role_dimension_scopes ADD COLUMN rule_group_id INTEGER`
  - 现有数据: rule_group_id = NULL (单规则组)
  - 索引: `CREATE INDEX idx_rds_rule_group ON role_dimension_scopes(role_id, rule_group_id)`
- **Rollback Plan**: `ALTER TABLE role_dimension_scopes DROP COLUMN rule_group_id`
- **Source**: FR-004

### TR-002: Feature Flag 灰度

- **Description**: 灰度发布流程
- **Strategy**:
  1. dev 环境开启 → 验证
  2. staging 环境开启 (1 周)
  3. 生产灰度 10% → 50% → 100% (各 3 天)
- **Rollback Plan**: feature flag 关闭
- **Source**: NFR-004

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- TC-1: 后端基于 Flask + Waitress + SQLite
- TC-2: 前端 Vue 3 + Vite + Pinia
- TC-3: DB schema 改动需 Alembic 迁移
- TC-4: 性能预算: list API P95 < 500ms (10K rows)，本 Spec 不应退化

### 7.2 Business Constraints

- BC-1: 不破坏现有权限语义 (兄弟隔离、向上扩展、Owner 过滤)
- BC-2: 中文 UI (zh-CN 优先)
- BC-3: 现有 7 个用户角色 (含 TEST60) 行为不变

### 7.3 Assumptions

- A-1: 列表分页 size 默认 20，total_count 来自全表 COUNT(*) — **Verified** (现有 `meta_data.permissions` 也有此语义)
- A-2: PermissionCache 已存在 — **Verified** (见 `meta/core/perm_cache.py`)
- A-3: i18n 框架 (vue-i18n) 已配置 — **Assumed** 待确认
- A-4: feature flag 系统 (`feature_flags.py`) 已存在 — **Verified**

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | 列表可见性统计 | Must | 用户最痛点 |
| FR-002 | 配置影响预览 | Must | 配置正确性 |
| FR-003 | "不选=不过滤" 提示 | Should | 语义透明 |
| FR-004 | rule_group_id 字段 | Should | 未来扩展 |
| NFR-001 | 按需加载性能 | Must | 性能不退化 |
| NFR-004 | Feature flag | Must | 可回滚 |

**Suggested Milestones**:

- **M1 (2 days)**: FR-001 + NFR-001 (后端) → E2E 验证列表统计
- **M2 (1 day)**: FR-002 + IF-002 (后端) → E2E 验证预览
- **M3 (1 day)**: FR-003 (前端提示)
- **M4 (0.5 day)**: FR-004 + TR-001 (DB 迁移) + 文档
- **M5 (0.5 day)**: NFR-004 feature flag + 灰度

**总计**: 5 天 (1 周)

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:
  - `meta/services/dimension_scope_engine.py` → 派生数据条件
  - `meta/core/runtime_dimension_resolver.py` → 运行时解析
  - `meta/core/interceptors/data_permission_interceptor.py` → SQL 过滤
  - `meta/api/bo_api_v2.py` → 列表 API
  - `src/views/SystemManagement/components/PermissionConfigPanel.vue` → 配置 UI
  - `src/views/ObjectListPage/MetaListPage.vue` → 列表 UI
  - `meta/core/perm_cache.py` → PermissionCache
- **Current Issues**:
  - 列表 API 不返回 `visible/total/denied` 统计
  - 配置 UI 不预览影响范围
  - "不选=不过滤" 语义未明确告知
  - DB schema 不支持 DNF
- **Relevant Code Paths**:
  - `meta/services/dimension_scope_engine.py:108-173` (derive_data_conditions)
  - `meta/api/bo_api_v2.py:list_objects` (list endpoint)
  - `meta/core/interceptors/data_permission_interceptor.py:_apply_dimension_scope_filter`

### 9.2 Target State

- **Proposed Architecture**:
  - **后端**:
    - `meta/core/dimension_scope_stats.py` (NEW) — 纯函数: 输入 scope + 角色 → 输出 visible/total/denied
    - `meta/api/bo_api_v2.py:list_objects` (MOD) — 支持 `with_stats=true` query param
    - `meta/api/role_api.py` (MOD) — 新增 `POST /dimension-scope/preview` 端点
    - `migrations/versions/xxxx_add_rule_group_id.py` (NEW) — Alembic 迁移
  - **前端**:
    - `src/composables/usePermissionStats.ts` (NEW) — 调用 `with_stats=true` API
    - `src/views/ObjectListPage/MetaListPage.vue` (MOD) — header 增加 "显示统计" 按钮 + 渲染提示
    - `src/views/SystemManagement/components/PermissionConfigPanel.vue` (MOD) — scope 区域增加预览 + 提示
- **Key Changes**:
  1. 后端 list API 加 `with_stats` 开关
  2. 后端新增 preview 端点
  3. 前端 2 个核心页面 UI 增强
  4. DB schema 加 1 列

### 9.3 Detailed Design

#### Module: `meta/core/dimension_scope_stats.py` (NEW)

```python
# -*- coding: utf-8 -*-
"""
Dimension Scope Stats - 维度范围统计 (FR-001 / NFR-001)

职责:
1. 纯函数: 输入 (role_id, bo_id, query_filters) → 输出 (visible_count, total_count, denied_count)
2. 复用 RuntimeDimensionResolver 拿 conditions
3. 一次 SQL: SELECT COUNT(*) FROM {table} WHERE <conditions>
4. 一次 SQL: SELECT COUNT(*) FROM {table}  (total)
5. PermissionCache 缓存: 5 分钟
"""

def get_stats(role_id: int, bo_id: str, filters: dict) -> Dict:
    """返回 {'visible_count': int, 'total_count': int, 'denied_count': int}"""
    pass
```

#### Module: `meta/api/bo_api_v2.py` (MOD)

```python
@bo_bp.route('/<object_type>', methods=['GET'])
def list_objects(object_type):
    with_stats = request.args.get('with_stats', 'false').lower() == 'true'
    # ... 现有逻辑 ...
    response = {
        'data': {'items': items, 'pagination': ...},
    }
    if with_stats:
        try:
            stats = get_stats(current_user.role_id, object_type, filters)
            response['meta'] = {
                'visible_count': stats['visible_count'],
                'total_count': stats['total_count'],
                'denied_count': stats['denied_count'],
                'with_stats': True,
            }
        except Exception as e:
            response['meta'] = {'stats_error': str(e), 'with_stats': False}
    return jsonify(response)
```

#### Module: `meta/api/role_api.py` (MOD)

```python
@role_bp.route('/<int:role_id>/dimension-scope/preview', methods=['POST'])
@login_required
def preview_dimension_scope(role_id):
    """FR-002: 预览 scope 影响范围"""
    scopes = request.get_json().get('scopes', [])
    # 用 DimensionScopeEngine.expand_dimension_values 解析
    # 返回 expanded dict + affected resources
    return jsonify({'data': {
        'expanded': {...},
        'affected_resources': [...],
        'warnings': [...],
    }})
```

#### Data Model: `role_dimension_scopes` (MOD)

```sql
ALTER TABLE role_dimension_scopes ADD COLUMN rule_group_id INTEGER;
-- 默认 NULL = 单规则组 (现状)
-- 未来: 同 rule_group 内 AND, 不同 rule_group 间 OR
```

#### Frontend: `src/composables/usePermissionStats.ts` (NEW)

```typescript
export function usePermissionStats(boId: Ref<string>) {
  const stats = ref<{visible: number, total: number, denied: number} | null>(null)
  const loading = ref(false)

  async function fetchStats(filters: any) {
    loading.value = true
    try {
      const resp = await api.get(`/api/v2/bo/${boId.value}`, {
        params: { ...filters, with_stats: 'true' }
      })
      stats.value = {
        visible: resp.meta.visible_count,
        total: resp.meta.total_count,
        denied: resp.meta.denied_count,
      }
    } finally {
      loading.value = false
    }
  }

  return { stats, loading, fetchStats }
}
```

#### Frontend: `MetaListPage.vue` (MOD)

```vue
<template>
  <div class="meta-list">
    <!-- 新增: 统计行 -->
    <div v-if="stats" class="stats-bar">
      可见 {{ stats.visible }} / {{ stats.total }}
      （{{ stats.denied }} 个无权限）
    </div>
    <el-button @click="onShowStats" :loading="loading">显示统计</el-button>
    <!-- 现有 list -->
  </div>
</template>
```

#### Frontend: `PermissionConfigPanel.vue` (MOD)

```vue
<template>
  <div class="scope-config">
    <!-- 新增: 语义提示 -->
    <el-alert type="info" :closable="false">
      💡 提示: 未选 = 不过滤 (即 SAP 留空语义)。如需严格隔离，请显式选择具体值。
    </el-alert>
    <!-- 现有 scope 编辑 -->
    <ScopeEditor v-model="scopes" @change="onScopeChange" />
    <!-- 新增: 影响预览 -->
    <div v-if="preview" class="preview">
      将级联到 {{ preview.affected_resources }} 个 resources
    </div>
  </div>
</template>
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A. 默认每次 list 都返回统计 | UI 自动显示 | 大数据量 COUNT(*) 慢；用户反馈 "我不需要" | Rejected |
| **B. 按需加载 (with_stats=true)** (推荐) | 默认无开销；用户主动查看 | 需点 1 次按钮 | **Selected** |
| C. WebSocket 推送统计 | 实时 | 复杂度高；本场景不需要 | Rejected |
| D. 独立 stats API (/stats) | 解耦 | 需 2 次 HTTP；不如 query param 简洁 | Rejected |
| E. 客户端 mock 统计 (基于当前 items) | 零后端改动 | 不准 (分页场景) | Rejected |

**关于 DNF (FR-004) 的设计选择**:

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| X. 本 Spec 实现 DNF 解析 | 一次到位 | 复杂度高；当前无明确业务需求 | Rejected (TBD-1) |
| **Y. 只加 rule_group_id 列** (推荐) | 兼容未来；不引入复杂度 | 不立即可用 | **Selected** |
| Z. 完全不改 schema | 无迁移成本 | 未来需大改 | Rejected |

### 9.5 Implementation & Migration Plan

#### Implementation Order

1. **Step 1 (M1, 2 days)**:
   - 后端: `dimension_scope_stats.py` (NEW)
   - 后端: `bo_api_v2.py` 加 `with_stats` 参数
   - 测试: 单测 (`tests/unit/test_dimension_scope_stats.py`)
   - 测试: 集成测 (`tests/integration/test_bo_api_v2_stats.py`)
   - E2E: Playwright 验证 UI 显示

2. **Step 2 (M2, 1 day)**:
   - 后端: `role_api.py` 加 preview 端点
   - 测试: 单测 + 集成测

3. **Step 3 (M3, 1 day)**:
   - 前端: `usePermissionStats.ts` (NEW)
   - 前端: `MetaListPage.vue` 增强
   - 前端: `PermissionConfigPanel.vue` 加提示 + 预览
   - E2E: Playwright 验证

4. **Step 4 (M4, 0.5 day)**:
   - DB 迁移: `migrations/versions/xxxx_add_rule_group_id.py`
   - 文档: 更新 `docs/specs/spec-permission-derivation-MASTER-PLAN.md`

5. **Step 5 (M5, 0.5 day)**:
   - Feature flag 注册: `PERMISSION_UX_TRANSPARENCY`
   - 灰度发布: dev → staging → prod (10% → 50% → 100%)

#### Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| COUNT(*) 慢 (10K+ rows) | Medium | High | 加 NFR-001 限制 200ms；超限返回 `stats_error` 不阻塞 |
| 缓存与 DB 不一致 | Low | Medium | 5min TTL；audit log 触发失效 |
| 预览 API 误用 (高频调用) | Low | Low | 加 rate limit (10/min/user) |
| 现有用户行为变化 | Low | High | Feature flag 灰度；10% 灰度先观察 |

#### Testing Strategy

- **Unit tests** (覆盖率 > 80%):
  - `test_dimension_scope_stats.py`: 各 scope 组合的 visible/total 计算
  - `test_role_api_preview.py`: 预览 API 输出
- **Integration tests**:
  - `test_bo_api_v2_stats.py`: 端到端 list + with_stats
  - `test_e2e_permission_transparency.py`: 配 scope → 看列表统计
- **E2E tests** (Playwright):
  - TEST60 登录 → 访问 /product → 点"显示统计" → 看到 "可见 2/2 (0 个无权限)"
  - 配 scope 后 → 看到 "可见 3/8 (5 个无权限)"

#### Rollback Plan

1. **代码层**: 关闭 feature flag `PERMISSION_UX_TRANSPARENCY` → 行为回退到实施前
2. **DB 层** (最坏): `ALTER TABLE role_dimension_scopes DROP COLUMN rule_group_id` (FR-004 涉及)
3. **API 层**: 移除 `with_stats` query param 支持 (前端配合)

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|---------------------|-----------|
| TBD-1 | **DNF 解析逻辑** (rule_group 内 AND, 组间 OR) | 业务用例确认 (用户提了 "未来") | 暂不实现；schema 预留 (FR-004) |
| TBD-2 | **预览 API rate limit 阈值** | 10/min 是否合理 | 灰度观察后再定 |
| TBD-3 | **i18n key 命名规范** | 现有 vue-i18n key 风格需确认 | 实施前查 `src/locales/zh-CN.json` |
| TBD-4 | **统计缓存 key 维度** | 是否要包含 `query_filters` | 实施时评估: 同一用户不同查询条件是否复用 |
| TBD-5 | **无 dimension scope 配置时的提示文案** | "无 dimension scope 配置" vs "未配置数据权限" | UX review 后定 |
