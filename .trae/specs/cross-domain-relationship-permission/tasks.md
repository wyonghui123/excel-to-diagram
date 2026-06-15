# -*- coding: utf-8 -*-
# 跨领域关系权限建模 - 实施任务分解

> **Version**: v1.0 | **Date**: 2026-06-15 | **配套 Spec**: [spec.md](./spec.md)
> **实施模式**: 灰度上线 (Phase 1-4, 4-5 周)

---

## Phase 1: 后端基础 (1.5 周)

### 1.1 WriteScopeInterceptor functional perm 校验 (软警告)

- [ ] **T1.1.1** 在 `write_scope_interceptor.py:483+` 的 `_check_relationship_ancestor_dim_scope` 中, 增加 functional perm 校验 (BO:edit)
  - 校验位置: 既有 ancestor 反推逻辑**之后**, 最终 return True 之前
  - 校验方式: 调 `meta.services.perm_service.get_user_perms(user_id, 'business_object')` 检查 'edit'/'update'/'delete' 任一
  - **Phase 1 仅 log warn, 不实际拒绝**
  - 文件: `meta/core/interceptors/write_scope_interceptor.py`
  - 验证: `python -c "import ast; ast.parse(open('meta/core/interceptors/write_scope_interceptor.py', encoding='utf-8').read())"`

- [ ] **T1.1.2** 单元测试: 写权限软警告 (不拒绝)
  - 创建 `meta/tests/test_cross_domain_relation_perm.py`
  - 测试场景:
    - U01-U06 (6 个基础场景, 软警告, 全部通过)
    - U07: 软警告模式下, viewer 类角色创建关系**成功** (log warn)
  - 运行: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py`
  - 期望: 全部通过

- [ ] **T1.1.3** 部署到 dev 环境, 收集 1 周日志
  - 监控指标: log warn 中 "应被拒但未拒" 的请求
  - 验证: 无历史角色配置被误拒

### 1.2 BO Pick by Code API

- [ ] **T1.2.1** 新建 `meta/api/value_help_api.py`
  - 实现 `GET /api/v2/bo/business_object/pick_by_code?code=&product_id=`
  - 不应用 read scope 过滤, 校验 BO 存在性
  - 返回 200 / 404 BO_NOT_FOUND
  - 验证: `python -c "import ast; ast.parse(open('meta/api/value_help_api.py', encoding='utf-8').read())"`

- [ ] **T1.2.2** 在 `meta/server.py` 注册 blueprint
  - `app.register_blueprint(value_help_api.bp)`
  - 验证: `python dev.py` 启动后, `curl http://localhost:3010/api/v2/bo/business_object/pick_by_code?code=BO_B_001` 返回正确

- [ ] **T1.2.3** 新建 `meta/services/bo_pick_service.py`
  - 封装 `pick_by_code(code, product_id)`, `pick_by_id(bo_id)`, `pick_by_name_fuzzy(name, product_id)`
  - 被 ValueHelpAPI 调用, 也供未来 service 层复用

- [ ] **T1.2.4** 单元测试: Pick by Code API
  - 场景: 存在/不存在/空 code/跨 product
  - 文件: `meta/tests/test_value_help_api.py`
  - 运行: `python d:\filework\test.py --file meta/tests/test_value_help_api.py`

### 1.3 角色配置示例文档

- [ ] **T1.3.1** 在 `rls_rules/role.yaml` 中新增 3 个示例角色
  - D1_MANAGER
  - D2_MANAGER
  - CROSS_DOMAIN_ARCHITECT
  - 配置格式: 跟现有 role.yaml 风格一致

- [ ] **T1.3.2** 文档同步: `docs/auth/role-templates.md`
  - 增加"跨域关系" 章节, 引用 role.yaml 示例
  - 步骤说明: 如何为 D1/D2 负责人配置角色, 如何验证

---

## Phase 2: 硬拒绝启用 (1 周)

> **2026-06-15 实施状态**: ✅ 已切硬拒绝 (env var default `false`)
> 实施方式: env var flip, 不需要重写代码逻辑, 保留软警告日志能力 (回退/审计双友好)

### 2.1 functional perm 校验 → 硬拒绝

- [x] **T2.1.1** ✅ (2026-06-15) 翻转 `_WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN` 默认值 `true → false`
  - 文件: `meta/core/interceptors/write_scope_interceptor.py:120-122`
  - **不**移除 log warn 代码, 而是 env var 控制: `soft_warn=True` 走 log+继续; `soft_warn=False` (Phase 2 默认) 走 log+`return False`
  - 失败时: `_log_rel_func_perm_warning(..., 'hard_reject', ...)` + `return False` 触发 `WriteScopeDenied`
  - 错误码: `INSUFFICIENT_PERMISSION` (由 WriteScopeDenied 抛出)

- [x] **T2.1.2** ✅ (2026-06-15) 单元测试更新
  - `TestDefaultPhaseConfig` 新增 `test_default_is_hard_reject` (断言默认 False)
  - `TestDefaultPhaseConfig` 新增 `test_env_true_switches_to_soft_warn` (env=true → 软警告)
  - `TestU05ViewerRoleSoftWarnVsHardReject` 维持双模式测试 (patch 切 True/False)
  - 全部 26 测通过

- [ ] **T2.1.3** ⏳ (部署后) 监控 1 周 403 错误率
  - 关键指标: 跨域关系创建的 403 错误率 (`rel_func_perm_hard_reject` log 计数)
  - 阈值: > 5% 触发回滚
  - **回滚方法**: `os.environ['WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN'] = 'true'` + restart server (1 行 env, 不改代码)

### 2.2 审计日志增强

- [ ] **T2.2.1** 在 `meta/services/audit_service.py` 增加跨域关系审计字段
  - 字段: `cross_domain: bool`, `source_domain_id: int`, `target_domain_id: int`
  - 用于后续的"跨域关系 dashboard" 报表

- [ ] **T2.2.2** 单元测试: 审计日志字段
  - 验证: 创建跨域关系后, audit_log 表有 cross_domain=true 记录

---

## Phase 3: 前端 BoSelectorDualMode 上线 (2 周)

> **2026-06-15 实施状态**: ✅ **元数据驱动重构完成** (用户采纳)
> 关键决策: 不用 Relationship 专用 view, 改造 MetaForm 识别 `dual_mode: true` → 任何 FK 字段 YAML 加 1 行即生效

### 3.1 通用组件开发 (已完成)

- [x] **T3.1.1** ✅ `src/components/common/ValueHelp/BoListSelector.vue`
  - 现有 List 模式组件, 抽离为独立组件
  - 集成 4 级级联 + 跨域浏览 toggle (Option B)
  - Props: productId, allowCrossDomain, modelValue
  - Emits: update:selected, cross-domain-toggled

- [x] **T3.1.2** ✅ `src/components/common/ValueHelp/BoCodeSelector.vue`
  - 新组件, Pick by Code 模式
  - Props: productId, disabled, placeholder
  - Emits: update:selected, error
  - 错误处理: MISSING_CODE / BO_NOT_FOUND / UNAUTHORIZED / NETWORK_ERROR
  - Vitest 8 测全绿

- [x] **T3.1.3** ✅ `src/components/common/ValueHelp/BoSelectorDualMode.vue`
  - 顶层组件, 包含 Tabs 切换 (List / By Code)
  - 通过 ref.open() / clearSelection() 暴露给父组件
  - Vitest 8 测全绿

- [x] **T3.1.4** ✅ `src/services/boService.js` 新增 `pickBoByCode(code, productId, options)` 方法
  - URL: `/bo/business_object/pick_by_code` (经 apiV2 拼接)
  - Method: GET
  - 处理 200/400/401/404
  - 支持 `include_out_of_scope` (跨域 toggle) + `reason` 审计参数

### 3.2 元数据驱动集成 (✅ 替代原 Relationship 专用 view)

- [x] **T3.2.1** ✅ `src/components/common/MetaForm.vue` 加 `dual_mode` 识别
  - `isDualMode(field)` 检查 `valueHelp.dual_mode === true`
  - 识别后渲染 `BoSelectorDualMode` 替代 `ValueHelpField`
  - 转发 `cross-domain-toggled` / `code-error` 事件
  - Vitest 5 测全绿 (含 ui.dual_mode 路径, event forwarding)

- [x] **T3.2.2** ✅ `src/components/common/DetailPage/DetailPage.vue` 透传 `dual_mode`
  - 从 `f.value_help.dual_mode` 或 `f.ui.dual_mode` 派生
  - 合并到 field defs 的 `valueHelp` 块
  - 0 回归 (无 DetailPage 专用测试)

- [x] **T3.2.3** ✅ `meta/schemas/relationship.yaml` 加 `dual_mode: true`
  - `source_bo_id.ui.dual_mode: true` + `value_help.dual_mode: true`
  - `target_bo_id.ui.dual_mode: true` + `value_help.dual_mode: true`
  - **任何对象类型的 FK 字段** 加这两行即生效, **零代码改动**

- [x] **T3.2.4** ✅ ~~删除~~ `src/views/RelationshipFormView.vue` (回滚错误方案)
  - 原方案违反元数据驱动原则, 已删除

### 3.3 E2E 测试

- [ ] **T3.3.1** 新建 `e2e/features/relationship-cross-domain.spec.js`
  - E01: U1 选 source BO, 默认 List 模式显示 D1 BO ✅
  - E02: U1 切换到 Pick by Code 模式, 输入 D2 BO_B 编码 ✅
  - E03: U1 输入不存在的 BO 编码 ❌ 错误提示
  - E04: U1 通过 Pick by Code 选 D2 BO_B + target D1 BO_A, 创建关系 ✅
  - 运行: `python d:\filework\test.py --file e2e/features/relationship-cross-domain.spec.js`

- [ ] **T3.3.2** 新建 `e2e/features/value-help-dual-mode.spec.js`
  - V01: 切换 Tab 行为正常
  - V02: Pick by Code 模式不应用 read scope 过滤
  - 运行: 同上

### 3.4 灰度发布

- [ ] **T3.4.1** 配置灰度开关 (env var: `CROSS_DOMAIN_VH_DUAL_MODE`)
  - 默认: `false` (旧版 List 模式)
  - 灰度比例: 10% → 50% → 100%

- [ ] **T3.4.2** 监控 1 周关键指标
  - 跨域关系创建成功率
  - 用户反馈 (NPS / 客服工单)
  - 异常回滚: 把开关置 false

---

## Phase 4: 文档同步 + 培训 (1 周)

### 4.1 文档更新

- [ ] **T4.1.1** `docs/auth/role-templates.md` 增加"跨域关系" 章节
- [ ] **T4.1.2** `docs/PERMISSION_SYSTEM_INDEX.md` 增加 cross-domain 链接
- [ ] **T4.1.3** `docs/specs/spec-backlog.md` 标记本 spec 为 [DONE]
- [ ] **T4.1.4** `docs/spec_权限体系升级/05_rfc_detailed_design.md` 同步跨域关系章节

### 4.2 培训材料

- [ ] **T4.2.1** 制作"跨域关系权限" 5 分钟短视频
  - 内容: 配置 D1 Manager 角色 / 创建跨域关系演示
  - 位置: `docs/training/cross-domain-relation.mp4`

- [ ] **T4.2.2** 写 FAQ 文档
  - Q: "为什么我看不到 D2 的 BO?"
  - A: 切到 "按编码选择" 模式, 输入 BO 编码
  - Q: "我创建了 D1→D2 关系, D2 负责人会看到吗?"
  - A: 是, 因为 OR-read 语义

- [ ] **T4.2.3** 内部 release note
  - 版本号: v1.2.0
  - Release date: 2026-07-15 (暂定)
  - Breaking change: viewer 类角色 (有 dim_scope 但无 BO:edit) 不再能创建关系

---

## 推迟项 / 后续 TODO (2026-06-15 用户决定)

> 以下任务**非阻塞**, 当前 Phase 1+2+3 已完整交付, 跨域关系创建可用 (走 By Code 模式 + OR-edit 闸)。
> 推迟理由: Phase 1+2 OR-edit 闸已保障写路径安全, Phase 3 By Code 模式 + read scope 已保障读路径默认安全。
> 推迟项是 UX 增强 (B.1+B.2) 和合规增强 (B.3), 缺它们不破坏安全模型, 视产品反馈再排期。

### B.1 + B.2 (联合: 跨域浏览 toggle 后端支持) [TODO, 暂估 1 天]

- [ ] **TB.1** 后端 `business_object` 列表 API 支持 `?include_out_of_scope=true&reason=...` 参数
  - 文件: `meta/api/bo_api.py` (query 端点)
  - 当 `include_out_of_scope=true` 且用户拥有 `cross_domain_relationship:browse` functional perm 时, **绕过** `DataPermissionInterceptor` 的 read scope 过滤
  - 当用户**没有**该 perm 但带 `include_out_of_scope=true` → 403 PERMISSION_DENIED (不静默忽略, 明确拒绝)
  - 注: 不引入新 perm 的简化方案不可取, 会导致信息泄露

- [ ] **TB.2** 新增 functional perm: `cross_domain_relationship:browse`
  - YAML 改动: `meta/objects/role.yaml` 或 `rls_rules/role.yaml` 加 perm 定义
  - 默认仅授予: 跨域架构师角色 (R-CROSS-ARCH) + 业务 admin
  - 与 `cross_domain_relationship:create` (或 `business_object:edit`) 是**正交**权限
  - 测试: 3 测 (有 perm 可见 / 无 perm 403 / 审计记录)

- [ ] **TB.3** 单元测试: B.1 + B.2 行为
  - `meta/tests/test_bo_list_include_out_of_scope.py` (新)
  - 6 测: perm 校验 / reason 必填 / 审计写入 / 不影响 List 模式默认行为 / 错误码格式

### B.3 (审计: toggle 使用追溯) [TODO, 暂估 0.5 天]

- [ ] **TB.4** 写路径审计: `/_diagnostics` 记录跨域 toggle 使用情况
  - 字段: `{ user_id, ts, object_type, field_key, reason, bo_ids_visited }`
  - 写入时机: 用户在 BoListSelector 切换 `crossDomainEnabled = true` 时
  - 触发方式: BoSelectorDualMode emit `cross-domain-toggled` → MetaForm emit → ObjectDetailPage 捕获 → 调 audit API
  - 关联后端: `meta/api/audit_api.py` 加 `record_toggle_usage` 端点
  - 测试: 3 测 (toggle 写 / reason 必填 / 频率限制: 单用户 100 次/小时)

### 关联的元数据

- 前端代码: [BoListSelector.vue:crossDomainEnabled](file:///d:/filework/excel-to-diagram/src/components/common/ValueHelp/BoListSelector.vue) 已实现 toggle UI + 透传 `include_out_of_scope` + `reason` query params, **后端支持是缺口**
- 后端 B.1 缺失时: 用户开 toggle → 后端忽略参数 → 用户看不到 D2 BO → 体验困惑但安全无虞
- 何时启动: 用户反馈 "By Code 模式太累" 或有产品需求希望 D1 manager 直接在 List 模式看到 D2

### 推迟决策记录

- 2026-06-15: 用户与 Agent 讨论, 决定推迟 B.1-B.3
- 理由: 写路径已安全 (OR-edit), 读路径默认安全 (read scope), UX 增强 (跨域 toggle) 是 nice-to-have
- 重新评估触发条件: 1) 跨域关系创建量 > 50/天; 2) 客服收到 ≥3 个 "By Code 模式太累" 反馈; 3) 合规审计要求 toggle 追溯

---

## 总览: 任务依赖图

```
Phase 1 (后端基础)
├─ T1.1 functional perm 校验 (软警告)
├─ T1.2 Pick by Code API
└─ T1.3 角色配置文档
            ↓
Phase 2 (硬拒绝)
├─ T2.1 functional perm 校验 (硬拒绝)
└─ T2.2 审计日志增强
            ↓
Phase 3 (前端上线)
├─ T3.1 BoSelectorDualMode 组件
├─ T3.2 关系表单改造
├─ T3.3 E2E 测试
└─ T3.4 灰度发布
            ↓
Phase 4 (文档 + 培训)
├─ T4.1 文档同步
└─ T4.2 培训材料
```

---

## 工作量估算 (待 user 确认)

> ⚠️ 工作量未与用户确认, 仅作为实施参考

| Phase | 子任务数 | 预估 (人天) | 备注 |
|-------|---------|------------|------|
| Phase 1 | 9 | 5 | 1 工程师 × 1 周 |
| Phase 2 | 4 | 3 | 监控 + 1 工程师 × 3 天 |
| Phase 3 | 9 | 8 | 1 前端 + 1 后端 × 2 周 |
| Phase 4 | 7 | 3 | 1 工程师 × 3 天 |
| **合计** | **29** | **19** | 约 4 周 |

---

## 风险登记

| ID | 风险 | 概率 | 影响 | 缓解措施 |
|----|------|------|------|---------|
| R1 | 现有 viewer 类角色被误拒 | 中 | 中 | Phase 1 软警告 1 周 + Phase 2 监控 1 周 |
| R2 | Pick by Code 被滥用, 误选错误产品 BO | 低 | 中 | product_id 限定 + UI 提示 |
| R3 | 前端双模式用户学习成本 | 中 | 低 | 用户培训 + 内置引导 |
| R4 | 性能: 写路径 +1 query | 低 | 低 | 缓存 user_perm 5s |
| R5 | 灰度发布不彻底 | 低 | 中 | env var 强制 + 监控 |

---

## CHANGELOG

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v1.0 | 2026-06-15 | AI Coding Agent | Initial task breakdown from spec.md |
