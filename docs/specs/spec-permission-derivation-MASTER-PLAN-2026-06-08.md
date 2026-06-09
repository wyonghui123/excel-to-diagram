# 权限 Derivation 体系整体实施计划 (Master Plan) — v1.0.1 整合版

> **日期**: 2026-06-08
> **版本**: v1.0.1（D9-D12 全部 ✅ Accepted 已落地）
> **状态**: 可执行（v1.0 spec + v1.1 spec + v1.2 spec + MASTER PLAN 4 文档齐全）
> **总工期**: 13-17 天（含 buffer）— v1.0.1 增量后
> **3 PR 拆分**: v1.0.1 → v1.1 → v1.2（独立可回滚）
> **人员**: 1 dev + 1 reviewer + 1 业务用户（TEST60 验证）
> **目的**: 整合 [v1.0.1 spec](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) / [v1.1 spec](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md) / [v1.2 spec](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-association-derivation-2026-06-08-v1.0.md) 的所有任务为可执行时间表
>
> **v1.0.1 核心增量（相对 v1.0）**：
> - FR-003 父读校验：硬拒 → **audit-only 模式**（D9）
> - **新增 FR-003b 链中 read 校验**（D10/D11）
> - **新增 §十三 4 层防御**（D12）
> - 实施计划 §11 + Code Review Checklist §12
> - **总工时增量**: 4.5h（spec）+ 9h（实施）= **~13.5h**

---

## 0. 总览 — v1.0.1 增量后

| 阶段 | spec | 解决的核心问题 | 工期 | 关键产出 |
|---|---|---|---|---|
| **Phase A** | [v1.0.1 spec](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | TEST60 角色能 list product（不 403）；菜单不消失；父读 audit-only；链中 read 硬拒 | **5-6.5 天** | 6 FR + FR-003b + read/list 合并 + 父读 advisory + 链中 read + 菜单 2 态 + init + 4 层防御 §13 |
| **Phase B** | [v1.1 spec](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md) | 去硬编码（parent_map / HIERARCHY_CHAIN / PARENT_FIELD_MAP） | **3.5-4.5 天** | yaml 自描述 + BoMetadataRegistry + 启动 fail-fast 校验 |
| **Phase C** | [v1.2 spec](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-association-derivation-2026-06-08-v1.0.md) | 5 种关联 derivation（m2m / polymorphic / self_ref / reverse / sibling） | **4.5-6 天** | 关联拦截器 + cycle CTE + 6 类错码 |
| **合计** | 3 PR | 完整权限 derivation 体系 | **13-17 天** | **15 FR**（FR-001~009 + FR-010~014 + FR-003b） + **7 NFR**（含 NFR-006/007） + **10 IF**（含 IF-006~010） + **6 TR**（含 TR-005） |

**4 层防御交付映射（D12）**：
- **Layer 1 防漏**（init 时）— Phase A FR-004 + FR-006
- **Layer 2 检测**（启动时）— Phase B FR-007 + FR-008
- **Layer 3a 提示-audit**（运行时）— **Phase A FR-003 v1.0.1**（D9）
- **Layer 3b 提示-错码**（运行时）— **Phase A FR-003b v1.0.1**（D10/D11）
- **Layer 3c 提示-关联**（运行时）— Phase C FR-010~014
- **Layer 4 自助**（运维时）— Phase B NFR-005（CLI explain_permissions.py）

---

## 1. Phase A — v1.0.1 基础（5-6.5 天）

**目标**: TEST60 立刻能工作 + 通用 6 FR + 4 层防御落地

**对应 spec**: [v1.0.1 §三 FR-001 ~ FR-006 + FR-003b](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md)

**v1.0.1 增量任务**（D9-D12 落地）：

- **A.5a** `_check_parent_read_advisory()` — audit-only 模式（log + header + diagnostics）
- **A.5b** `_check_chain_read()` — 链中 read 校验（写硬拒 / 读 A2 隐含）
- **A.5c** 集成 env `PARENT_READ_STRICT_MODE` 升级开关
- **A.11+** `error_codes.py` 加 `ERR_CHAIN_READ_DENIED`
- **A.12+** `error_fix_hints.py` 加 2 个 fix_hint
- **A.23** CLI `explain_permissions.py` 落地 NFR-005
- **A.24** `/_diagnostics` 暴露 `parent_read_warnings[]`

**详细实施日级任务见 [v1.0.1 spec §十一](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md)**。

### 1.1 Day 1-2: DB migration + permission_interceptor 改造

| # | Task | 文件 | 估时 | 依赖 |
|---|---|---|---|---|
| A.1 | 备份 `permissions` 表 → `permissions_bak_20260608` | DB | 0.5h | — |
| A.2 | permissions 表加 `deprecated_at` 字段（nullable） | migration script | 0.5h | A.1 |
| A.3 | 把所有 `* :list` 记录 mark deprecated | migration script | 0.5h | A.2 |
| A.4 | `_ACTION_PERMISSION_SUFFIX` 改：crud_list → read，crud_query → read | [permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26) | 1h | — |
| **A.5a** | **[v1.0.1] 新增 `_check_parent_read_advisory()` 函数** | 同上 | 2h | A.4 |
| **A.5b** | **[v1.0.1] 新增 `_check_chain_read()` 函数** | 同上 | 2h | — |
| **A.5c** | **[v1.0.1] 集成 env `PARENT_READ_STRICT_MODE`** | 同上 | 0.5h | A.5a |
| A.6 | integration: 写 action 触发 chain read + parent advisory | 同上 | 1h | A.5a/A.5b |

**Day 1-2 验证**:
```bash
# 单元: list/read/delete 三种 case
python d:\filework\test.py --single meta/tests/test_permission_interceptor.py
```

### 1.2 Day 3: menu 5 动作展开 + 2 态渲染

| # | Task | 文件 | 估时 |
|---|---|---|---|
| A.7 | 写 `scripts/init_role_permissions.py`（幂等，5 动作展开） | 1 file 新 | 2h |
| A.8 | 跑 init 脚本（dry-run → 实际） | 1 script | 0.5h |
| A.9 | useVersionContext 简化 2 态（visible/hidden） | [useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js) | 1h |
| A.10 | GenericObjectList.vue 无权限态 UI | [GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/views/components/GenericObjectList.vue) | 1.5h |
| A.11 | `error_codes.py` 加 `ERR_PARENT_PERMISSION_DENIED` | [error_codes.py](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py) | 0.5h |
| A.12 | `error_fix_hints.py` 加对应 fix_hint | [error_fix_hints.py](file:///d:/filework/excel-to-diagram/meta/core/error_fix_hints.py) | 0.5h |

**Day 3 验证**:
```bash
# 业务验证: TEST60 登录后能看到 product 列表（不再 403）
python d:\filework\excel-to-diagram\scripts\service_manager.ps1 start
# Playwright 登录 TEST60 → /product-management → 不报 403
```

### 1.3 Day 4-5: 测试 + bug 修复

| # | Task | 估时 |
|---|---|---|
| A.13 | 单元：`test_permission_interceptor_v10.py`（read/list 合并 + 父读） | 2h |
| A.14 | 集成：`test_init_role_permissions.py`（幂等 + 全 role 补齐） | 1h |
| A.15 | 集成：`test_menu_visibility_v10.py`（2 态） | 1h |
| A.16 | E2E：Playwright TEST60 完整流程（登录 + 列表 + 详情 + 删除遇 403） | 2h |
| A.17 | 回归：`test.py --all --force` → `--failed` | 1h |
| A.18 | bug 修复（按优先级） | 1-2 天 buffer |

**Day 5 验证**:
```bash
python d:\filework\test.py --all --force
python d:\filework\test.py --failed
# 期望: 0 fail
```

### 1.4 Day 6: 部署 + 灰度

| # | Task | 行动 |
|---|---|---|
| A.19 | feature flag `PERMISSION_DERIVATION_ENABLED=false`（默认） | env var |
| A.20 | admin 内测 1 天 | 验证无 500 |
| A.21 | 全量启用 | 改 flag true |
| A.22 | 监控 1 小时 | 0 错误 |

**Phase A 结束里程碑 (M3)**: ✅ TEST60 业务用户验证通过

---

## 2. Phase B — v1.1 yaml 化（3.5-4.5 天）

**目标**: 去硬编码 + 启动 fail-fast 校验

**对应 spec**: [v1.1 §三 FR-007 ~ FR-009](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md)

### 2.1 Day 1-2: yaml schema 扩展 + BoMetadataRegistry

| # | Task | 文件 | 估时 | 依赖 |
|---|---|---|---|---|
| B.1 | 6 BO yaml 加 `parent_object` + `parent_field`（product/version/domain/sub_domain/service_module/business_object） | 6 files | 2h | — |
| B.2 | 新建 `meta/core/bo_metadata_registry.py`（单例） | 1 file 新 | 2h | B.1 |
| B.3 | 实现 `_build()`：从 yaml 构建 parent_map / child_map / dimension_chain | 同上 | 2h | B.2 |
| B.4 | 实现 `_validate()`：cycle / chain / field reference 3 项校验 | 同上 | 1.5h | B.3 |
| B.5 | `dump()` 方法暴露给 `/_diagnostics` | 同上 | 0.5h | B.3 |

### 2.2 Day 2-3: 替换硬编码 + dry-run 脚本

| # | Task | 文件 | 估时 |
|---|---|---|---|
| B.6 | `data_permission_service.py` 删 `parent_map` 硬编码 → 用 registry | 1 file | 1.5h |
| B.7 | `dimension_scope_engine.py` 删 `HIERARCHY_CHAIN` / `PARENT_FIELD_MAP` 硬编码 → 用 registry | 1 file | 1.5h |
| B.8 | 写 `scripts/check_bo_metadata.py`（dry-run） | 1 file 新 | 1h |
| B.9 | 启动时 BoMetadataRegistry 初始化 | 启动 hook | 1h |
| B.10 | 启动 fail-fast 验证（故意写错 yaml → 启动报错） | 验证 | 0.5h |

**Day 3 验证**:
```bash
python scripts/check_bo_metadata.py --dry-run
# 期望: 6 BO 全部通过
```

### 2.3 Day 4: 测试

| # | Task | 估时 |
|---|---|---|
| B.11 | 单元：`test_bo_metadata_registry_v11.py`（_build / _validate） | 1.5h |
| B.12 | 单元：`test_data_permission_service_v11.py`（无硬编码） | 1h |
| B.13 | 集成：故意配错 yaml → 启动失败 | 1h |
| B.14 | 回归：`test.py --all --force` → `--failed` | 1h |

**Phase B 结束里程碑 (M5)**: ✅ 硬编码全部 yaml 化，加新 BO 改 yaml 一次

---

## 3. Phase C — v1.2 关联 derivation（4.5-6 天）

**目标**: 5 种非 parent 关联的权限 derivation

**对应 spec**: [v1.2 §三 FR-010 ~ FR-014](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-association-derivation-2026-06-08-v1.0.md)

### 3.1 Day 1: yaml schema 扩展（关联字段）

| # | Task | 文件 | 估时 |
|---|---|---|---|
| C.1 | `business_object.yaml` 加 `relations[].type: many_to_many` + `derivation` 块 | 1 file | 1h |
| C.2 | `annotation.yaml` 加 `polymorphic.allowed_types` | 1 file | 0.5h |
| C.3 | `user_group.yaml` 加 `self_reference: { hierarchy_field, max_depth, cycles, orphans, multiple_parents }` | 1 file | 0.5h |
| C.4 | 5 个 BO yaml 加 `sibling_group: arch_data` | 5 files | 0.5h |

### 3.2 Day 1-2: BoMetadataRegistry 扩展

| # | Task | 估时 |
|---|---|---|
| C.5 | `get_self_reference_cfg` / `get_polymorphic_allowed_types` / `get_sibling_group` API | 2h |
| C.6 | `_validate` 扩展（self_ref / polymorphic / sibling 校验） | 1h |
| C.7 | dry-run 验证（`check_bo_metadata.py --dry-run`） | 0.5h |

### 3.3 Day 2-3: 关联拦截器

| # | Task | 文件 | 估时 |
|---|---|---|---|
| C.8 | 新建 `meta/core/interceptors/association_interceptor.py` | 1 file 新 | 2h |
| C.9 | `check_m2m_permission`（FR-010 双向校验） | 同上 | 2h |
| C.10 | `check_polymorphic_permission`（FR-011 type 枚举 + id 存在 + read） | 同上 | 2h |
| C.11 | `check_self_reference_permission`（FR-012 read + cycle CTE） | 同上 | 2h |
| C.12 | `check_sibling_visibility`（FR-014 read 粒度 opt-in） | 同上 | 0.5h |
| C.13 | integration with v1.1 `permission_interceptor`（crud_create/update 触发） | 集成 | 1h |

### 3.4 Day 3-4: 错误码 + cycle 算法

| # | Task | 估时 |
|---|---|---|
| C.14 | `error_codes.py` 加 6 错码（m2m / polymorphic / cycle / self_ref） | 0.5h |
| C.15 | `error_fix_hints.py` 加 6 fix_hint | 0.5h |
| C.16 | cycle 检测 CTE（SQL 递归，10 节点深度内） | 2h |
| C.17 | admin 跳过校验 | 0.5h |

### 3.5 Day 4-5: 测试

| # | Task | 估时 |
|---|---|---|
| C.18 | 单元：`test_association_interceptor_v12.py`（4 FR 全 case） | 3h |
| C.19 | 集成：TEST60 写 m2m / polymorphic / self_ref 业务场景 | 2h |
| C.20 | E2E：Playwright 测前端 6 类错码 toast | 1h |
| C.21 | 回归：`test.py --all --force` → `--failed` | 1h |

### 3.6 Day 5-6: 部署 + 灰度

| # | Task |
|---|---|
| C.22 | feature flag `ASSOCIATION_DERIVATION_ENABLED=false`（默认） |
| C.23 | admin 内测 1 天 |
| C.24 | 全量启用 |
| C.25 | 1 sprint 后删 flag |

**Phase C 结束里程碑 (M7)**: ✅ 5 种关联 derivation 全覆盖

---

## 4. 关键路径（critical path）— v1.0.1 更新

```
Phase A (5.5d) → Phase B (4d) → Phase C (5d)
   |                |               |
   └─ 拦截器        └─ registry    └─ 关联拦截器
      (阻塞测试)      (阻塞 A.6)      (阻塞测试)
   + 4 层防御 §13
```

**总关键路径**: 14.5 天（理论）/ **17 天**（含 1-2 天 buffer + v1.0.1 增量）

---

## 5. 依赖图 — v1.0.1 更新

```
v1.0.1 (Phase A)
├─ FR-001 read/list 合并
├─ FR-002 yaml parent （**同 FR-007！** 推迟到 v1.1）
├─ FR-003 父读 advisory 校验 (audit-only + env 升级) — [v1.0.1 D9]
├─ FR-003b 链中 read 校验 (写硬拒 / 读 A2 隐含) — [v1.0.1 D10/D11] NEW
├─ FR-004 menu 5 动作展开
├─ FR-005 菜单 2 态
├─ FR-006 init 脚本
└─ §13 4 层防御 — [v1.0.1 D12] NEW
        ↓
v1.1 (Phase B) 依赖 v1.0.1
├─ FR-007 yaml 化（parent_map / HIERARCHY_CHAIN / PARENT_FIELD_MAP）
├─ FR-008 启动校验
└─ FR-009 registry dump
        ↓
v1.2 (Phase C) 依赖 v1.1
├─ FR-010 m2m
├─ FR-011 polymorphic
├─ FR-012 self_reference
├─ FR-013 reverse 文档化
└─ FR-014 sibling
```

**注意**: v1.0 FR-002「yaml parent」跟 v1.1 FR-007「yaml 化」是**同一件事**。v1.0 不做 yaml 化（避免 Phase A 工作量爆炸），v1.1 统一做。

---

## 6. 风险与缓解 — v1.0.1 更新

| # | 风险 | 缓解 | 触发 |
|---|---|---|---|
| R1 | 父读校验误伤（无 parent 的 BO） | yaml 缺 parent 即跳过校验 + admin 默认跳 | Phase A |
| R1.1 | **[v1.0.1]** 父读硬拒误伤 admin 漏配场景 | **audit-only 模式**（log + header + 不阻塞）+ env `PARENT_READ_STRICT_MODE` 升级 | Phase A |
| R1.2 | **[v1.0.1]** 链中 read 硬拒误伤长链场景 | D11 A2 模式：读/列表不校验（隐含） | Phase A |
| R2 | 现有角色短期无 menu→BO 展开 | init 脚本幂等全量 | Phase A Day 3 |
| R3 | 错误码变化致前端 toast 失效 | fix_hint 同步 + 前端 httpClient 已统一 | Phase A |
| R4 | yaml 漏配 parent_object 致推导链断 | 启动 fail-fast（v1.1） | Phase B |
| R5 | cycle 检测性能（深 chain） | yaml `max_depth: 10` + CTE 限深 | Phase C |
| R6 | polymorphic 枚举漏配 | 启动 fail-fast + admin 跳过 | Phase C |
| R7 | TEST60 业务验证失败 | Phase A Day 5 加 1 天 buffer | Phase A |
| R8 | 1 PR 全包风险 | 拆 3 PR 独立可回滚 | 整体 |
| **R9 (v1.0.1)** | audit-only 模式被遗忘（一直开） | env var 文档化 + 监控 `/diagnostics` 的 `parent_read_warnings` 计数 | Phase A 部署 |

---

## 7. 里程碑与业务用户验证 — v1.0.1 更新

| 里程碑 | Phase | 业务验证点 | 期望 |
|---|---|---|---|
| **M0** (Day 0.5) | Phase A 准备 | DB 备份 + dry-run 通过 | ✅ |
| **M1** (Day 2) | Phase A 拦截器 | TEST60 能 list product（不再 403） | ✅ |
| **M1.5** (Day 3) | Phase A v1.0.1 增量 | audit-only 模式 + 链中 read 校验生效 | ✅ |
| **M2** (Day 5) | Phase A 测试 | `test.py --all --force` 0 fail | ✅ |
| **M3** (Day 6.5) | Phase A 部署 | admin 内测无 500 + 全量无 500 | ✅ |
| **M4** (Day 10) | Phase B yaml 化 | 故意写错 yaml → 启动 fail-fast | ✅ |
| **M5** (Day 12) | Phase B 测试 | `test.py --failed` 0 fail | ✅ |
| **M6** (Day 15) | Phase C 关联 derivation | TEST60 写 m2m 遇 403 + 写 polymorphic 遇 403 + 写 self_ref 遇 ERR_CYCLE | ✅ |
| **M7** (Day 17) | Phase C 部署 | admin 内测 + 全量 + 1 sprint 后删 flag | ✅ |

---

## 8. 总时间线（甘特图）— v1.0.1 更新

```
Day:  0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17
      |  Phase A v1.0.1  |  |  |  |     |  Phase B  |  |     |  Phase C  |  |  |
      |  6 FR+FR-003b   |  |  |  |     |  v1.1 3 FR  |  |     |  v1.2 5 FR  |  |  |
      |  拦截器 | UI |4层|测|灰|  yaml  | reg | 测 |    |  关联  | 测 |  灰度  |
      ↓                 ↓  ↓   ↓              ↓           ↓                  ↓     ↓
   M0          M1   M1.5 M2  M3          M4          M5                M6    M7
```

**总工期**: 17 天（含 2 天 buffer + v1.0.1 增量）

---

## 9. 立即可做的"前置"（不等 PR）

| 行动 | 时间 | 谁 | 备注 |
|---|---|---|---|
| 1. 加 `product:read` 给 TEST60 角色（先让他能工作） | 5 min SQL | admin | 立即缓解 TEST60 403 |
| 2. 业务用户跑 1 次验证 TEST60 完整流程 | 0.5 天 | TEST60 | 验证基线 |
| 3. 准备 v1.0 worktree 分支 | 0.1 天 | dev | 隔离开发 |
| 4. 写 `permissions_bak_20260608` 备份脚本 | 0.2 天 | dev | 安全网 |

**第 1 项 SQL 示例**:
```sql
-- 立刻消除 TEST60 403
INSERT OR IGNORE INTO permissions (code, name, resource_type, action)
  VALUES ('product:read', 'Product Read', 'product', 'read');
UPDATE role_permissions SET granted=1
  WHERE role_id=1803 AND permission_id=(SELECT id FROM permissions WHERE code='product:read');
```

---

## 10. 决策项（需用户确认）— v1.0.1 全部 Accepted

> **v1.0.1 状态**: D1-D13 全部 ✅ Accepted（v1.0 阶段决策 D1-D8 + v1.0.1 方向性决策 D9-D12 + **D13 v1.0.1 修订新增**）

| # | 决策 | 默认推荐 | 状态 |
|---|---|---|---|
| D1 | Phase A 是否包含 v1.0 FR-002（yaml parent）？ | **否**（推迟到 Phase B）— Phase A 简单 | ✅ Accepted |
| D2 | Phase A 是否加 1 天 buffer？ | **是**（应对 TEST60 业务验证） | ✅ Accepted |
| D3 | Phase C 是否包含 FR-013/014（reverse/sibling）？ | **是**（一起做，单独 PR 工作量小） | ✅ Accepted |
| D4 | 灰度策略：默认全量开还是先 admin？ | **先 admin 1 天** | ✅ Accepted |
| D5 | 删 feature flag 时机 | **1 sprint 后** | ✅ Accepted |
| D6 | 是否需要 ROOT ORPHANS 行为（user_group 父删时子升 ROOT）？ | **是**（SAP CDS ORPHANS ROOT 模式） | ✅ Accepted |
| D7 | polymorphic target_type 校验策略 | **全枚举**（yaml 显式，fail-fast） | ✅ Accepted |
| D8 | m2m 校验默认 mode | **both_ends**（Odoo / Palantir） | ✅ Accepted |
| **D9**   | **父读校验模式?**（v1.0.1 方向性决策） | **audit-only**（log + 告警 + 不阻塞）+ env `PARENT_READ_STRICT_MODE=true` 升级 | ✅ **Accepted** |
| **D10**  | **多跳写校验模式?**（v1.0.1 方向性决策，**v1.0.1 修订**） | **B 链中 audit-only**（链中任一 read 缺失 → log + header + 不阻塞）+ env `CHAIN_DERIVATION_STRICT_MODE=true` 升级 | ✅ **Accepted** |
| **D13**  | **[v1.0.1 增] 链 read 粒度**（D10 粒度错误，业界对比发现）| **类型级 audit-only + 实例级硬拒**（粒度对齐 Oracle RAS / SAP CDS / Snowflake）| ✅ **Accepted** |
| **D11**  | **多跳读校验模式?**（v1.0.1 方向性决策） | **A2**（链中任一 read → 链尾 list 隐含） | ✅ **Accepted** |
| **D12**  | **4 层防御章节加哪个 spec?**（v1.0.1 方向性决策） | **MASTER PLAN 总览** + v1.0 spec §十三 | ✅ **Accepted** |

**v1.0.1 决策落地映射**：

| 决策 | 落地的 spec 章节 | 实施位置 | 修订状态 |
|---|---|---|---|
| D9 | [v1.0 spec §三 FR-003 v1.0.1](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | `_check_parent_read_advisory()` + env var | 不变 |
| D10 | [v1.0 spec §三 FR-003b v1.0.1 修订](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | `_check_chain_read()` 类型级 audit-only + env var | **v1.0.1 修订: 硬拒 → audit-only** |
| D11 | [v1.0 spec §三 FR-003b](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | `_check_chain_read()` 读分支 (A2 隐含) | 不变 |
| D12 | [v1.0 spec §十三 4 层防御](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | §13.1-13.8 完整章节 | 不变 |
| **D13** | [v1.0 spec §三 FR-003b.2 实例级 + §十四 业界对比](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | `_check_chain_read()` 实例级硬拒 + `_resolve_parent_chain()` | **v1.0.1 新增** |

### 10.1 v1.0.1 方向性决策全景（D9-D12）

> **核心思想**：从"严格 + 易误伤"转向"audit-only + 链中硬拒 + 4 层防御"。

| 决策 | 旧方案 | 新方案（v1.0.1 修订） | 影响 |
|---|---|---|---|
| **D9** 父读校验 | crud_delete 父读**硬拒 403** | crud_create/update/delete **audit-only**（log + 告警 + 不阻塞）+ env 升级 | FR-003 改 |
| **D10** 多跳写 | 无 | **链中任一 read audit-only**（log + header + 不阻塞）+ env `CHAIN_DERIVATION_STRICT_MODE` 升级 | FR-003b 类型级改 |
| **D11** 多跳读 | 已隐含 A2 | **明确标注 A2**（链中任一 read → 链尾 list 隐含） | 文字更新 |
| **D12** 4 层防御 | 散落各 spec | **v1.0 spec §十三** + MASTER PLAN | **新加 §十三 章节** |
| **D13** 链 read 粒度 | 类型级硬拒（粒度错误）| **类型级 audit-only + 实例级硬拒**（业界 Oracle RAS / SAP CDS / Snowflake）| FR-003b.2 实例级 + §十四 业界对比 |

**总工作量**: 4.5 小时（spec 修订 + interceptor 改造 + 测试）

**Phase A 任务更新**（v1.0.1 增量）：

| # | Task | 估时 | 替代旧 task |
|---|---|---|---|
| **A.5a** | 新增 `_check_parent_read_advisory()` 函数 | 2h | A.5（旧 2h） |
| **A.5b** | 新增 `_check_chain_read()` 函数（**v1.0.1**） | 2h | — |
| **A.5c** | 集成 env `PARENT_READ_STRICT_MODE` | 0.5h | — |
| **A.5d** | 4 层防御 §十三 章节落 spec | 1h | — |
| A.11+ | error_codes.py 加 `ERR_CHAIN_READ_DENIED`（**v1.0.1**） | 0.5h | A.11 扩展 |
| A.11++ | error_codes.py 加 `ERR_CHAIN_INSTANCE_OUT_OF_SCOPE`（**D13**） | 0.5h | A.11 扩展 |
| A.13  | 测试覆盖 audit-only + chain read 2 套 | 2h | A.13 改 |
| A.13+ | 测试覆盖 chain read 实例级硬拒（**D13**） | 1h | A.13 扩展 |
| **A.23** | **CLI explain_permissions.py 落地 NFR-005** | 1h | — |
| **A.24** | **/_diagnostics 暴露 parent_read_warnings 数组** | 0.5h | — |
| **A.25** | **[_resolve_parent_chain() 实现**（D13 实例级硬拒的 helper） | 1.5h | — |

**Phase A 总工作量**: 从 4.5-6 天 → 5-6.5 天（v1.0.1 增量）→ **5.5-7 天**（+0.5 天 D13 实例级硬拒增量）

### 10.2 4 层防御落地计划

| Layer | 任务 | 阶段 | 估时 |
|---|---|---|---|
| **Layer 1 防漏** | `init_role_permissions.py` 配 menu 自动 5 动作 | Phase A | 2h（已计划） |
| **Layer 2 检测** | BoMetadataRegistry 启动校验 | Phase B | 2h（已计划） |
| **Layer 3a 提示-audit** | 父读 audit-only + /_diagnostics | Phase A | 2.5h（D9） |
| **Layer 3b 类型级-告警** | 链 read 类型级 audit-only + header + /_diagnostics | Phase A | 1.5h（D10 修订后） |
| **Layer 3c 实例级-错码** | 链 read 实例级硬拒 ERR_CHAIN_INSTANCE_OUT_OF_SCOPE + fix_hint | Phase A | 2h（**D13 新增**）|
| **Layer 3d 提示-关联** | 6 错码（m2m/polymorphic/cycle/self_ref） | Phase C | 1h（已计划） |
| **Layer 4 自助** | CLI explain_permissions.py + /_diagnostics | Phase B | 1.5h（已计划） |

**总 Layer 工作量**: 12.5h（D13 拆 3b+3c）
**Phase A 占比**: 8h（4 层防御的 64% 落在 Phase A）

---

## 附录 A: 链接索引

### A.1 Spec 文档

- 📄 [v1.0 spec — 基础 6 FR](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md)
- 📄 [v1.1 spec — yaml 化 3 FR](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md)
- 📄 [v1.2 spec — 关联 derivation 5 FR + 实施时间表 + Review Checklist](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-association-derivation-2026-06-08-v1.0.md)

### A.2 关键代码文件

| 阶段 | 文件 | 作用 |
|---|---|---|
| Phase A | [permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py) | action → perm suffix 映射 + 父读校验 |
| Phase A | [useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js) | 菜单 2 态渲染 |
| Phase A | [GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/views/components/GenericObjectList.vue) | 无权限态 UI |
| Phase A | [error_codes.py](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py) | 错码枚举 |
| Phase A | [error_fix_hints.py](file:///d:/filework/excel-to-diagram/meta/core/error_fix_hints.py) | 错码修复提示 |
| Phase B | [data_permission_service.py](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py) | 删 parent_map 硬编码 |
| Phase B | [dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py) | 删 HIERARCHY_CHAIN 硬编码 |
| Phase B | [bo_metadata_registry.py](file:///d:/filework/excel-to-diagram/meta/core/bo_metadata_registry.py) (新) | yaml registry 单例 |
| Phase C | [association_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/association_interceptor.py) (新) | 4 FR 关联校验 |
| 全部 | [scripts/check_bo_metadata.py](file:///d:/filework/excel-to-diagram/scripts/check_bo_metadata.py) (新) | dry-run 验证 |

### A.3 测试入口

```bash
# 单测（快）
python d:\filework\test.py --single <test_id>

# 全部
python d:\filework\test.py --all --force

# 失败重跑
python d:\filework\test.py --failed

# 状态查看
python d:\filework\test.py --status

# 单文件
python d:\filework\test.py --file <test_path>
```

### A.4 服务管理

```bash
# 启动（多 agent 端口隔离）
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start

# 状态
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# 重启
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart
```

---

## 附录 B: Review Checklist 引用

| Phase | 引用 | 必查项数 |
|---|---|---|
| A | [v1.0 spec §九 风险与缓解](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | ~ 30 项 |
| B | [v1.1 spec §九 风险与缓解](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md) | ~ 25 项 |
| C | [v1.2 spec §十二 Code Review Checklist](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-association-derivation-2026-06-08-v1.0.md) | A-J 10 大类 ~ 50 项 |

**总 Review Checklist**: ~ 105 项

---

## 附录 C: 业务价值回顾

### C.1 解决 TEST60 案例（Phase A 即时）

| 现状 | 改后 |
|---|---|
| TEST60 配 product CRUD 缺 list → 403 | menu 5 动作展开 + read/list 合并 → 自动有 read |
| 菜单缺任一 BO 权限即消失 | 2 态渲染（visible/hidden） + 列表页空白 + 「无权限」 |
| 写子资源无父读校验 | crud_delete 父读强制 + 错码 `ERR_PARENT_PERMISSION_DENIED` |
| 角色 manual 配置繁琐 | init 脚本幂等全 role 补齐 |

### C.2 长期演进（Phase B + C）

| 价值 | 阶段 |
|---|---|
| 加新 BO 改 yaml 一次（去硬编码） | Phase B |
| yaml 错配即启动失败（fail-fast） | Phase B |
| 5 种关联 derivation（m2m / polymorphic / self_ref / reverse / sibling） | Phase C |
| 防成环（SAP CDS Hierarchies 风格） | Phase C |
| 6 类错码（m2m / polymorphic / cycle / self_ref） | Phase C |

---

**Master Plan 完整性自检（v1.0.1）**：
- ✅ 10 章节齐全（0 总览 + 1-3 Phase A/B/C + 4-10 关键路径/依赖/风险/里程碑/时间线/前置/决策）
- ✅ 3 阶段任务清单（Day 1-2 / Day 3 / Day 4-5 / Day 6）
- ✅ 8 个里程碑（M0-M7）
- ✅ 9 项风险与缓解（R1-R9，含 R1.1/R1.2 v1.0.1 增量）
- ✅ **13 项决策项（D1-D13）**：D1-D8 业务性决策 + D9-D12 v1.0.1 方向性决策 + **D13 v1.0.1 修订新增**（**全部 ✅ Accepted**）
- ✅ **§十四 业界对比章节增补**（v1.0 spec，2026-06-09）
- ✅ 4 个附录（链接 / 代码 / 测试 / 业务价值）
- ✅ 可执行 task 表格（70+ 个独立 task，每项有估时 + 依赖 + 验证）
- ✅ **4 层防御总览（D12）** 落在 §0 + v1.0 spec §十三
- ✅ **v1.0.1 增量任务** (A.5a/b/c, A.11+, A.12+, A.23, A.24) 全部在 Phase A 任务清单中
- ✅ D9-D12 → 落地章节的映射表（§10.1）
