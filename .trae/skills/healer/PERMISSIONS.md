# Healer 权限边界 (PERMISSIONS)

> **版本**: v0.1.0 (2026-06-13)
> **状态**: **仅文档(documented-only)**,Healer 实际启用延后至 Spec B
> **来源**: Spec v1.1 FR-009 + TBD-4 用户反馈
> **关联**: [`.trae/rules/SESSION_REMINDER.md`](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md)

---

## [!!!] 重要提示

**本文件仅定义 Healer 自愈的边界规则。Healer 实际启用延后至 Spec B。**

**当前阶段(Spec A)**:
- Healer **未启用**
- 任何测试失败均需人工修复
- 本文档用于提前固化安全边界,避免 Spec B 启用时遗漏

**Spec B 启用前必须**:
1. 通过 `.trae/scripts/healer_safety_check.py` 验证配置一致性
2. 灰度策略:仅在 feature 分支启用,主分支仍需人工
3. 监控指标:healer_fix_total、healer_false_positive_rate 等

---

## 1. 权限清单

```yaml
# 默认配置(Spec B 启用前必须 review)
allow:
  # 业务组件
  - src/components/business/**
  # 非安全相关 service
  - src/services/filterVariant.js
  - src/services/dashboard.js
  - src/services/annotation.js
  # 测试自身
  - tests/**

deny:
  # 鉴权(严禁自愈,避免绕过登录)
  - src/utils/auth/**
  - src/services/authService.js
  - src/services/permissionService.js  # 注意:permission 与 auth 同样关键
  # 支付
  - src/services/payment/**
  - src/utils/payment/**
  # 加密
  - src/utils/crypto/**
  - src/services/cryptoService.js
  # 合规
  - src/services/compliance/**
  - src/services/audit.js  # 审计日志本身必须人工
  # 基础设施核心
  - src/utils/httpClient.js  # 关键基础设施,失败即视为真实 bug
  - src/utils/api.js
  # 配置
  - **/*.config.js
  - **/*.config.ts
  - **/vite.config.*
  - **/vitest.config.*
  - **/playwright.config.*

require_human_review:
  # 即使不在 deny 列表,涉及鉴权 token 的修改也必须人工
  - src/utils/auth-token/**
  - src/services/session/**
  # 数据库 schema
  - **/migrations/**
  # 跨 Agent 共享的状态
  - .trae/state/**
```

## 2. 决策流程

```
[Healer 收到失败信号]
   ↓
[1. 读取 PERMISSIONS.md 配置]
   ↓
[2. 检查失败文件路径]
   ├── 命中 deny → 立即停止,通知人工,不修复
   ├── 命中 require_human_review → 生成修复 PR,但标记 needs-human-approval
   └── 命中 allow → 进入自动修复流程
   ↓
[3. 自动修复流程(仅 allow)]
   a. 重跑测试,确认是 flaky 还是真实失败
   b. 若是 flaky → 增加 wait / retry,标记为 flaky
   c. 若是真实失败 → 尝试 Healer 修复(locator/wait/assertion)
   d. 修复后必须重跑 ≥ 3 次,确保稳定通过
   e. 通过 → 自动 commit + 通知
   f. 仍失败 → 通知人工
```

## 3. 护栏指标(Spec B 启用时必须配置)

| 指标 | 类型 | 阈值 | 说明 |
|------|------|------|------|
| `healer_fix_total` | counter | - | 总修复次数 |
| `healer_false_positive_total` | counter | - | 修复后被 revert 次数 |
| `healer_false_positive_rate` | gauge | < 5% | 误判率 |
| `healer_retry_success_rate` | gauge | > 60% | 修复成功率 |
| `healer_avg_retry_count` | gauge | < 3 | 平均重试次数 |

若 `healer_false_positive_rate > 5%`,自动暂停 Healer,等待人工 review。

## 4. 与其他系统的集成

### 4.1 与 .trae/skills/test-gen 的关系

- test-gen 生成测试时,自动跳过 deny 模块
- test-gen 在 allow 模块生成测试后,Healer 后续可修复
- 见 [test-gen/SKILL.md § 4.3 安全硬约束](file:///d:/filework/excel-to-diagram/.trae/skills/test-gen/SKILL.md)

### 4.2 与 multi-agent-coordination 的关系

- 跨 Agent 并行时,Healer 修复必须加 git lock
- AGENT_PORT 隔离的测试,Healer 修复不跨 port

### 4.3 与 SESSION_REMINDER 的关系

- 遵循"硬规则模块禁止"原则(本 Spec TBD-4 用户决策)
- 不修改 `SESSION_REMINDER.md` 中的铁律

## 5. 配置变更流程

1. 修改本文件
2. 在 `.trae/skills/CHANGELOG.md` 追加记录
3. 更新本文件的 version 与 last_updated
4. Spec B 启用前 review 全部配置

## 6. 反模式(Anti-Patterns)

- [X] **不在 deny 列表就放开**: 即使不在列表,敏感模块也应保守处理
- [X] **修复后不验证**: 修复必须重跑 ≥ 3 次
- [X] **silent 修复**: 所有修复必须记录到 agent-runs.jsonl
- [X] **修复 production 代码绕过 deny**: 不允许通过"小修改"绕过 deny
- [X] **Healer 修改 .trae/ 配置**: Healer 只修复测试与业务代码

## 7. 版本历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版,定义 deny/allow 边界 | AI |