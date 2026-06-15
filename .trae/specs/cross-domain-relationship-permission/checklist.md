# -*- coding: utf-8 -*-
# 跨领域关系权限建模 - 验收 Checklist

> **Version**: v1.0 | **Date**: 2026-06-15 | **配套 Spec**: [spec.md](./spec.md) | [tasks.md](./tasks.md)
> **验收方式**: 单元测试 + E2E 测试 + 灰度监控 + 用户反馈

---

## 一、Spec Review Check (脑暴自检)

> 来自 brainstorming skill 的 4 项 self-review

- [x] **Placeholder scan**: 无 TBD / TODO / "待定" 残留
  - 备注: Open Questions 5 项已显式标出, 等待用户确认
- [x] **Internal consistency**: 各 section 一致
  - 备注: OR-edit / OR-read 语义在所有 section 中表述一致
- [x] **Scope check**: 单 spec 可执行
  - 备注: 4 Phase, 4-5 周, 19 人天, 在合理范围
- [x] **Ambiguity check**: 无二义性
  - 备注: 每个 Scenario 都有 WHEN/THEN/AND 明确表述

---

## 二、功能验收 (来自 ADDED Requirements)

### Requirement 1: 关系表写权限采用 OR-edit 语义

- [ ] **CHK-1.1** Scenario 1.1: U1 创建 D1→D1 关系 → ✅ 通过
  - 验证: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py::TestU01`
  - 期望: HTTP 200, audit log 记录 "created relationship under domain=D1"

- [ ] **CHK-1.2** Scenario 1.2: U1 创建 D1→D2 关系 (核心场景) → ✅ 通过
  - 验证: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py::TestU02`
  - 期望: HTTP 200, audit log "cross_domain=true"

- [ ] **CHK-1.3** Scenario 1.3: U3 (D1-Viewer, 无 edit) 创建 D1→D2 关系 → ❌ 403
  - 验证: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py::TestU05`
  - 期望: HTTP 403, error_code=INSUFFICIENT_PERMISSION, hint 含 "您对 D2 的 BO 仅可读"

- [ ] **CHK-1.4** Scenario 1.4: U1 update/delete 关系 D1→D2 → ✅ 通过
  - 验证: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py::TestU07` + `TestU08`
  - 期望: 全部通过

- [ ] **CHK-1.5** Scenario 1.5: Product Owner (U99) 不需 dim_scope 也能 delete → ✅ 通过
  - 验证: 单元测试 TestU06 + 集成测试
  - 期望: OwnerChainInterceptor priority=25 优先放行

### Requirement 2: 关系表读权限采用 OR-read 语义

- [ ] **CHK-2.1** Scenario 2.1: read scope 派生的 SQL 条件
  - 验证: 单元测试 + 手动查 SQL 日志
  - 期望: SQL 含 OR 子查询 + owner exception

- [ ] **CHK-2.2** Scenario 2.2: U1 query, 返回 R1 (D1→D2) 不返回 R2 (D2→D2)
  - 验证: 单元测试
  - 期望: R1 可见, R2 不可见

- [ ] **CHK-2.3** Scenario 2.3: OR-read 也适用 update/delete
  - 复用 CHK-1.4 验证

### Requirement 3: ValueHelp 双模式

- [ ] **CHK-3.1** Scenario 3.1: List 模式默认显示 read scope 内 BO
  - 验证: `python d:\filework\test.py --file e2e/features/relationship-cross-domain.spec.js::E01`
  - 期望: 显示 D1 BO, 不显示 D2 BO

- [ ] **CHK-3.2** Scenario 3.2: 切换到 Pick by Code, 输入 D2 BO 编码
  - 验证: `python d:\filework\test.py --file e2e/features/relationship-cross-domain.spec.js::E02`
  - 期望: 输入 "BO_B_001" 后显示 D2 BO 信息

- [ ] **CHK-3.3** Scenario 3.3: 输入不存在编码, 404 错误
  - 验证: `python d:\filework\test.py --file e2e/features/relationship-cross-domain.spec.js::E03`
  - 期望: 错误提示 "BO 编码 BO_XYZ_999 不存在"

- [ ] **CHK-3.4** Scenario 3.4: Pick by Code 不绕过写权限
  - 验证: 单元测试 + E2E
  - 期望: 即使 Pick by Code 选 D2 BO, 写权限仍按 OR-edit 校验, 不绕过

### Requirement 4: 角色配置示例

- [ ] **CHK-4.1** Scenario 4.1: D1-MANAGER 角色配置
  - 验证: 手动 inspect `rls_rules/role.yaml` + 在 dev 环境创建 D1-MANAGER 角色
  - 期望: 角色可创建, 赋给 U1 后, U1 在 D1 子树有完整 edit 权限

- [ ] **CHK-4.2** Scenario 4.2: D2-MANAGER 角色配置
  - 同上

- [ ] **CHK-4.3** Scenario 4.3: CROSS_DOMAIN_ARCHITECT 角色配置
  - 验证: 角色可创建, 赋给 U3 后, U3 在多个域有 edit 权限

### Requirement 5: 测试覆盖

- [ ] **CHK-5.1** Scenario 5.1: 8 个单元测试全部通过
  - 验证: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py`
  - 期望: 8/8 passed

- [ ] **CHK-5.2** Scenario 5.2: 5 个 E2E 测试全部通过
  - 验证: `python d:\filework\test.py --file e2e/features/relationship-cross-domain.spec.js e2e/features/value-help-dual-mode.spec.js`
  - 期望: 5/5 passed

---

## 三、Code Health Check

### 3.1 文件编码 (来自 file-encoding-rules.md)

- [ ] **CHK-CODE-1** 所有新增 .py 文件首行有 `# -*- coding: utf-8 -*-`
  - 验证: `Get-Content -Encoding UTF8 meta/api/value_help_api.py | Select-Object -First 1`
  - 期望: `# -*- coding: utf-8 -*-`

- [ ] **CHK-CODE-2** 所有新增 .py 文件通过 `ast.parse` 验证
  - 验证: `python -c "import ast; ast.parse(open('FILE', encoding='utf-8').read())"`
  - 期望: 0 退出码, 无错误

- [ ] **CHK-CODE-3** docstring 严格 3 个 `"""` 闭合
  - 验证: 抽查 docstring 末尾
  - 期望: 3 个 `"` 配对

### 3.2 YAML 编码 (来自 meta-model-schema-sync.md)

- [ ] **CHK-CODE-4** rls_rules/role.yaml YAML 格式正确
  - 验证: `python -c "import yaml; yaml.safe_load(open('rls_rules/role.yaml', encoding='utf-8'))"`
  - 期望: 0 错误

- [ ] **CHK-CODE-5** YAML 变更后, 同步到 schema
  - 验证: `python -m meta.tools.sync_schema --diff`
  - 期望: 显示 role.yaml 变更, 无破坏性 schema 变更

### 3.3 服务启动

- [ ] **CHK-CODE-6** 后端启动正常
  - 验证: `powershell -File scripts/service_manager.ps1 status`
  - 期望: Backend RUNNING on :3010

- [ ] **CHK-CODE-7** 前端启动正常
  - 验证: 同上
  - 期望: Frontend RUNNING on :3004

- [ ] **CHK-CODE-8** 新 API 端点可访问
  - 验证: `curl.exe "http://localhost:3010/api/v2/bo/business_object/pick_by_code?code=BO_B_001"`
  - 期望: 200 + JSON 响应

---

## 四、性能验证 (来自 Technical Design §6)

- [ ] **CHK-PERF-1** 关系写权限校验耗时 < 50ms (p99)
  - 验证: 用 ApacheBench 压测 1000 个 create relationship 请求
  - 期望: p99 < 50ms (含新增的 functional perm 校验 query)

- [ ] **CHK-PERF-2** 关系读权限派生耗时 < 100ms (p99)
  - 验证: 同上, 1000 个 query 请求
  - 期望: p99 < 100ms (维持 OR-read 派生性能)

- [ ] **CHK-PERF-3** BO Pick by Code API 耗时 < 30ms (p99)
  - 验证: 1000 个 pick_by_code 请求
  - 期望: p99 < 30ms (单次 DB query, 无派生)

---

## 五、灰度验收 (来自 Technical Design §7)

### Phase 1: 后端 + functional perm 校验 (软警告)

- [ ] **CHK-ROLLOUT-1.1** 代码部署到 dev 环境
  - 验证: `git log --oneline -5` 含本 spec 提交
  - 期望: HEAD 含 functional perm 校验 + log warn

- [ ] **CHK-ROLLOUT-1.2** 软警告 1 周内, 无"应被拒但未拒" 的高风险请求
  - 验证: 收集 log warn 计数 + 安全团队 review
  - 期望: warn 计数 < 100/天, 全部为预期行为

- [ ] **CHK-ROLLOUT-1.3** 单元测试 U01-U06 全部通过 (软警告模式)
  - 验证: `python d:\filework\test.py --file meta/tests/test_cross_domain_relation_perm.py`
  - 期望: 6/6 passed

### Phase 2: 硬拒绝启用

- [ ] **CHK-ROLLOUT-2.1** functional perm 校验改为硬拒绝
  - 验证: 代码 review + dev 环境 e2e
  - 期望: U05 (viewer 创建关系) → 403

- [ ] **CHK-ROLLOUT-2.2** 监控 1 周 403 错误率 < 5%
  - 验证: Grafana dashboard
  - 期望: 跨域关系创建 403 率 < 5%

- [ ] **CHK-ROLLOUT-2.3** 异常回滚演练
  - 验证: 模拟 403 率 > 5%, 确认回滚脚本可用
  - 期望: 回滚耗时 < 5 分钟

### Phase 3: 前端 BoSelectorDualMode 上线

- [ ] **CHK-ROLLOUT-3.1** E2E 测试 5/5 通过
  - 验证: `python d:\filework\test.py --file e2e/features/relationship-cross-domain.spec.js`
  - 期望: 5/5 passed

- [ ] **CHK-ROLLOUT-3.2** 灰度 10% → 50% → 100% 各 1 周, 监控跨域关系创建成功率
  - 验证: Grafana 灰度指标
  - 期望: 成功率 > 95%, 异常回滚

- [ ] **CHK-ROLLOUT-3.3** 用户反馈: NPS 不下降
  - 验证: 用户调研问卷
  - 期望: NPS 变化 < 5

### Phase 4: 文档同步 + 培训

- [ ] **CHK-ROLLOUT-4.1** 4 份文档同步
  - 验证: 文档 review
  - 期望: 全部更新, 链接可点

- [ ] **CHK-ROLLOUT-4.2** 培训材料就绪
  - 验证: 视频上传到 docs/training/
  - 期望: 5 分钟短视频可播放

- [ ] **CHK-ROLLOUT-4.3** Release note 发布
  - 验证: docs/CHANGELOG.md
  - 期望: v1.2.0 entry 含本 spec 描述

---

## 六、风险验收 (来自 tasks.md §风险登记)

- [ ] **CHK-RISK-1** R1 风险: 现有 viewer 类角色被误拒
  - 缓解: Phase 1 软警告 1 周
  - 验收: Phase 1 软警告 + Phase 2 监控, 异常回滚

- [ ] **CHK-RISK-2** R2 风险: Pick by Code 误选错误产品
  - 缓解: product_id 限定 + UI 提示
  - 验收: E2E E03 场景

- [ ] **CHK-RISK-3** R3 风险: 前端双模式学习成本
  - 缓解: 培训 + FAQ
  - 验收: 培训覆盖率 > 80%, FAQ 命中常见问题

- [ ] **CHK-RISK-4** R4 风险: 性能 - 写路径 +1 query
  - 缓解: 缓存 user_perm 5s
  - 验收: p99 性能指标通过

- [ ] **CHK-RISK-5** R5 风险: 灰度发布不彻底
  - 缓解: env var 强制 + 监控
  - 验收: 灰度比例严格匹配

---

## 七、Final Acceptance Gate (用户/PM 签字)

- [ ] **ACCEPT-FINAL** Spec review 通过
  - 验证: 5 个 Open Questions 全部有用户决策
  - 期望: OQ1-OQ5 全部 [x]

- [ ] **ACCEPT-FINAL** Code review 通过
  - 验证: PR 已被至少 1 位 reviewer approve
  - 期望: 4 Phase 全部合并到 main 分支

- [ ] **ACCEPT-FINAL** 测试通过
  - 验证: `python d:\filework\test.py --all --force` 全部通过
  - 期望: passed, no failed, no error

- [ ] **ACCEPT-FINAL** 文档发布
  - 验证: docs/ 目录已更新
  - 期望: spec 状态从 [DRAFT] 改为 [DONE]

- [ ] **ACCEPT-FINAL** 用户/PM 签字
  - 验证: 签字栏含 PM 名字 + 日期
  - 期望: 2026-07-15 之前完成

---

## CHANGELOG

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v1.0 | 2026-06-15 | AI Coding Agent | Initial checklist from spec.md + tasks.md |
