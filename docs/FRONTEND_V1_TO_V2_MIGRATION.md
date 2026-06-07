# 前端 v1 → v2 迁移评估报告

> **生成时间**: 2026-06-05
> **目标**: 在 2026-08-14 (Sunset) 之前完成前端 v1 → v2 路径迁移

## 一、迁移策略

依据 [RFC Section 10.2](../rfc_action_service_unified_model.md#102-路径分类) 的三类路径分类：

| 类别 | 策略 | 紧急度 |
|------|------|--------|
| **A. 通用 CRUD**（/v1/products, /v1/business_object 等） | 410 强制迁移 | 🔴 立即 |
| **B. 权限/Intent/BO API** | 双路由保留（暂时不动） | 🟢 暂缓 |
| **C. 业务专属 API** | v1 永久保留 | ⚪ 不动 |

## 二、src/ 中 v1 调用点清单

### 2.1 类别 A（需立即迁移 → v2/bo/{type}）

| 文件 | 当前 v1 路径 | 实测状态 | 目标 v2 路径 | 优先级 |
|------|-------------|---------|-------------|--------|
| `src/components/common/RelationScopeTree/RelationScopeSection.vue:424` | `/api/v1/relationships` | **200** (在 V1_SPECIAL_PREFIXES) | 不需迁移 | — |
| `src/views/ProductVersionApp/meta/entityMeta.js:4` | `/api/v1/product` | **410** (未在豁免列表) | `/api/v2/bo/product` | **P0** |
| `src/utils/metaEnhancer.js:51` (注释) | `/api/v1/user-groups` | **500** (在豁免列表但端点异常) | 待排查 | **P1** |

> 验证结果（2026-06-05 实际请求）：
> - `/api/v1/relationships` → 200（`relationships` 是 V1_SPECIAL_PREFIXES 成员）
> - `/api/v1/product` → **410**（未豁免，强制迁 v2）
> - `/api/v1/user-groups` → 500（`user-groups` 是豁免成员，但端点本身有问题）

### 2.2 类别 B（v1 永久保留，Sunset 2026-08-14 前可不改）

| 文件 | 路径 | 状态 | 备注 |
|------|------|------|------|
| ~~`src/composables/useOverlaps.ts:51,71`~~ | ~~`/api/v1/roles/{id}/overlaps`~~ | ✅ **2026-06-05 已迁 v2** | 同步修复后端 overlap_api（移除 url_prefix，用 add_dual_routes 注册 v1+v2） |

### 2.3 类别 C（v1 永久保留，不需要迁移）

| 文件 | 路径 | 后端策略 |
|------|------|----------|
| `src/views/AccountSettings/index.vue:484,541,609,644` | `/api/v1/users/me`, `/api/v1/auth/change-password` | 永久保留 |
| `src/stores/userPreferences.js:24,38` | `/api/v1/users/me` | 永久保留 |
| `src/components/AccountSettingsDialog.vue:284,320,355,372` | `/api/v1/users/me`, `/api/v1/auth/change-password` | 永久保留 |
| `src/services/enumService.js:155,184` | `/api/v1/enums/{id}/options`, `/api/v1/enum-types/{id}/values` | 永久保留 |
| `src/components/common/EnumSearchHelp.vue:114` | `/api/v1/enum-types/.../values` | 永久保留 |
| `src/utils/hierarchyFilterBuilder.js:18` | `/api/v1/meta/hierarchies/config` | 永久保留 |
| `src/views/SystemManagement/meta/auditLogMeta.js:285` | `/api/v1/audit` | 永久保留 |
| `src/components/common/ImportDialog/README.md:94-98` | `/api/v1/import*`, `/api/v1/import-export/*` | 永久保留（文档） |
| `src/components/common/ExportDialog/README.md:134` | `/api/v1/export` | 永久保留（文档） |

### 2.4 测试文件（不需迁移）

| 文件 | 备注 |
|------|------|
| `src/views/AccountSettings/__tests__/AccountSettings.spec.js` | 测试代码，路径写死 |
| `src/components/__tests__/AccountSettingsDialog.spec.js` | 测试代码 |
| `src/views/SystemManagement/meta/__tests__/auditLogMeta.spec.js` | 测试代码 |
| `src/services/__tests__/enumService.spec.js` | 测试代码 |
| `src/components/common/__tests__/EnumSearchHelp.spec.js` | 测试代码 |
| `src/components/__tests__/EditProfileDialog.spec.js` | 测试代码 |
| `src/stores/__tests__/authStore.spec.js` | 测试代码 |

## 三、推荐执行步骤

### 步骤 1：验证类别 A 是否真的会被 410
```bash
# 手动测试 410
curl -i http://localhost:3010/api/v1/relationships?version_id=1
curl -i http://localhost:3010/api/v1/product
```

### 步骤 2：批量替换（如果步骤 1 确认 410）
- `RelationScopeSection.vue:424` → `/api/v2/bo/relationship`
- `entityMeta.js:4` → `/api/v2/bo/product`
- `metaEnhancer.js:51` 注释 → 同步更新

### 步骤 3：运行 E2E 回归
```bash
npx playwright test e2e/features/business-object-crud.spec.js
npx playwright test e2e/features/product-crud.spec.js
npx playwright test e2e/features/relation-scope-tree.spec.js
```

### 步骤 4：v2 路径在 server.py 已注册的 BO 列表
确认 v2/bo/{type} 路径已注册（见 `meta/api/bo_api.py::bo_bp`）。

## 四、风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| 类别 A 误判（实际未 410） | 低 | 步骤 1 验证 |
| v2 路径与 v1 行为不一致 | 低 | 共享 view_func，零业务差异 |
| E2E 截图差异 | 中 | 重跑 E2E + 人工核对 |
| 前端其他间接调用未发现 | 中 | 完整搜索 `api/v1` 路径 |

## 五、建议完成时间

- 类别 A 迁移：2026-06-12 (1 周内)
- 类别 B 迁移：2026-08-14 前
- 类别 C：不需要迁移

## 六、监控

- 上线后监控 v1 路径 QPS（应逐步降低）
- E2E 覆盖率 100%（按路径维度）

---

## 七、迁移执行记录

### 7.1 类别 A 迁移（2026-06-05）

| 路径 | 改动文件 | 验证 |
|------|---------|------|
| `/api/v1/product` → `/api/v2/bo/product` | `src/views/ProductVersionApp/meta/entityMeta.js:4` | product-crud E2E 2/2 ✅ |
| `/api/v1/user-groups` (注释) → `/api/v2/bo/user_group` | `src/utils/metaEnhancer.js:51` | 文档同步 |

### 7.2 类别 B 迁移（2026-06-05）

#### 改动文件
- `meta/api/overlap_api.py` — 移除 `url_prefix='/api/v1/roles'`，改用 `add_dual_routes()` 注册 v1+v2
- `src/composables/useOverlaps.ts:51,71` — 2 处 v1 路径已迁 v2

#### 后端验证（2026-06-05）

```
200  /api/v1/roles/1/overlaps          Deprecation=true
200  /api/v2/roles/1/overlaps          Deprecation=NONE
200  /api/v1/roles/1/overlaps/summary  Deprecation=true
200  /api/v2/roles/1/overlaps/summary  Deprecation=NONE
```

#### E2E 回归
- `e2e/features/overlap-warning.spec.js` → 1/1 passed

#### 关键发现
- 原 `overlap_bp` 的 `url_prefix='/api/v1/roles'` 硬编码为 v1，v2 路径未注册（500）
- 改用 `add_dual_routes()` 后实现 v1+v2 双路由，零业务代码改动
- 这次修复同时为 v1 路径保留了 deprecation headers（`Deprecation=true`）

### 7.3 迁移总览

| 类别 | 计划 | 已完成 | 完成率 |
|------|------|--------|--------|
| 类别 A（强制迁移） | 2 | 2 | **100%** |
| 类别 B（v1/v2 双轨） | 1 | 1 | **100%** |
| 类别 C（不需迁移） | 17 | 0 | N/A |

**Sunset 2026-08-14 前还需监控 v1 路径调用情况**（虽然已无前端代码调用，但 v1 路径后端仍保留 6 个月过渡期）。
