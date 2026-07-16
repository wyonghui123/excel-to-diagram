# 📋 Multi-Agent Task Spec Template

> **版本**: v1.0 (2026-06-19)
> **用途**: 每个 agent 开始工作前必须填写
> **位置**: 在 agent worktree 根目录创建 `spec.md`

---

## 任务基本信息

| 字段 | 值 | 说明 |
|------|-----|------|
| **Task ID** | T-<编号> | 全局唯一 |
| **Agent 名称** | agent-<name> | 例如 agent-fix-batch-save |
| **Worktree** | `d:\filework\<worktree-name>\` | 独立工作目录 |
| **基于 commit** | `<base-sha>` | 工作的起点 |
| **风险等级** | 🟢 low / 🟡 medium / 🔴 high | 决定 review 流程 |
| **预计完成时间** | <小时> | |
| **涉及 integration 验证?** | yes / no | 若是 yes, 必读下文 §0 |

---

## 1. 任务描述（一句话）

> **目标**: [清晰描述要完成什么]

---

## 2. 改动文件白名单 ✅

> **只允许修改以下文件**（超出范围视为违规）

```yaml
modified_files:
  - path/to/file1.py
  - path/to/file2.vue

new_files:
  - path/to/new_file.py

deleted_files:
  - path/to/old_file.py
```

---

## 3. 禁止改文件黑名单 🚫

> **绝对不能改以下文件**

```yaml
forbidden_files:
  - .agent-status.json          # 协调状态
  - service_manager.ps1         # 服务管理
  - scripts/agent_bootstrap.ps1  # Worktree 引导
  - .git/hooks/pre-commit       # 保护脚本
  - healthy-baseline-2026-06-17 # 健康基线 tag
  - multi-agent-coordination.md # 主协调规范
```

---

## 4. 依赖关系

```yaml
depends_on:
  - commit: <sha>          # 必须基于哪个 commit
  - branch: <branch-name>  # 或哪个分支
  - agent: <other-agent>   # 或等其他 agent

blocks:
  - agent: <other-agent>   # 谁在等这个任务
```

---

## 5. 完成标准 ✅

> **必须全部满足才能 merge**

```yaml
acceptance_criteria:
  - [ ] 所有改动在白名单内
  - [ ] 没有改动黑名单文件
  - [ ] 单元测试通过 (python test.py --single ...)
  - [ ] 集成测试通过
  - [ ] commit message 含铁律声明:
        L1-Worktree: yes
        L2-NoMain: yes
        L3-Stash: yes
        L4-Status: yes
        L5-Service: yes
  - [ ] 风险评估已记录
  - [ ] 更新 .agent-status.json
```

---

## 6. 风险评估

### 6.1 改动范围

| 维度 | 评估 |
|------|------|
| **文件数量** | <number> |
| **新增行数** | <+lines> |
| **删除行数** | <-lines> |
| **影响模块** | <list> |

### 6.2 风险等级判定

```yaml
risk_level: <low/medium/high>

reason: |
  - low: 文档、注释、测试、UI 微调
  - medium: 服务逻辑、API 改动、新功能
  - high: auth、schema、migration、permission、外部契约
```

### 6.3 缓解措施

```yaml
mitigation:
  - 回滚方案: <如何回滚>
  - 测试覆盖: <测试计划>
  - 监控指标: <上线后看什么>
```

---

## 7. 沟通计划

```yaml
status_updates:
  - 启动时: 广播"开始 T-XXX"
  - 完成时: 广播"ready to merge T-XXX"
  - 阻塞时: 立即广播"blocked T-XXX: <reason>"

broadcast_channel:
  - file: d:\filework\.agent-status.json
  - method: append_to_worktree_section
```

---

## 8. Review 流程

| 风险等级 | Review 方式 |
|---------|-----------|
| 🟢 low | Coordinator 直接 merge |
| 🟡 medium | Verifier quick check (5 min) → Coordinator merge |
| 🔴 high | Verifier deep review + 用户审批 → Coordinator merge |

---

## 9. 工作日志

> **记录关键决策和发现**

```yaml
decisions:
  - 2026-06-19 10:00: 决定 X 用 Y 方案，因为 Z

blockers:
  - 2026-06-19 11:00: 阻塞于 <reason>

insights:
  - 发现 <important-finding>
```

---

## 10. 完成后 Checklist

- [ ] spec.md 已填写完整
- [ ] 所有 acceptance_criteria 已勾选
- [ ] commit message 含铁律声明
- [ ] .agent-status.json 已更新
- [ ] Worktree 工作目录已清理（debug 脚本删除）
- [ ] **告诉用户"ready for merge T-XXX"**

---

> **铁律提醒**：
> - **L1**: Worktree 强制隔离（绝不在主工作树 commit）
> - **L2**: 不要碰主工作树文件
> - **L3**: 不要碰 stash@{0}
> - **L4**: 开始前读 .agent-status.json
> - **L5**: 提交前更新状态文件