# 📋 Task: ImportDialog 全面重构 (Sheet-Grouped UI + 后端错误规范化)

> **Task ID**: T-2026-06-19-import-dialog
> **Agent**: import-dialog-fixes
> **Worktree**: `D:/filework/agent-import-dialog-fixes`
> **Branch**: `import-dialog-fixes-2026-06-19`
> **基于 commit**: c43f7b8 (main HEAD)
> **风险等级**: 🟡 medium
> **日期**: 2026-06-19

---

## 1. 任务描述

按用户视角**重塑 ImportDialog 全部 4 步**的 UI 布局 + **修复后端错误信息**的可读性：

- **步骤 2 (数据校验)**: 总览统计条 (4 列) + Sheet 折叠面板 (按对象类型分) + 错误/告警独立 Tab
- **步骤 4 (导入结果)**: 总览统计条 (6 列) + Sheet 折叠面板 + 失败/告警 Tab + 级联失败 banner
- **后端**: `operation` 字段用 `upsert_result.operation` (实际执行)；`message` 规范化 (去除 "VALIDATION_FAILED - " 代码)
- **修复 e2e 关键 bug**: `set_thread_user(user_dict)` 必须传完整 user dict 含 permissions

---

## 2. 改动文件白名单 ✅

```yaml
modified_files:
  - meta/api/export_import_api.py
  - meta/services/query_service.py
  - src/components/common/ImportDialog/ImportDialog.vue

new_files: []

deleted_files: []
```

---

## 3. 禁止改文件黑名单 🚫

```yaml
forbidden_files:
  - .agent-status.json
  - scripts/service_manager.ps1
  - .git/hooks/pre-commit
  - healthy-baseline-2026-06-17
  - .trae/rules/multi-agent-coordination.md
  - d:\filework\START_HERE.md
  - d:\filework\AGENT_GUIDELINES.md
  - 任何 service_manager 相关文件
```

---

## 4. 依赖关系

```yaml
depends_on:
  - commit: c43f7b8
  - branch: main

blocks:
  - (无)
```

---

## 5. 完成标准 ✅

```yaml
acceptance_criteria:
  - [x] 所有改动在白名单内 (3 个文件)
  - [x] 没有改动黑名单文件
  - [x] 前端 Vite build 无错误 (port 3004 返回 200)
  - [x] 后端 wait 启动正常 (port 3010)
  - [x] E2E 测试能解析 import result (domain/sub_domain/service_module/business_object/relationship/annotation 6 个对象类型全部处理)
  - [x] operation 字段与 message 一致 (operation=create + message=导入失败)
  - [x] 后端 message 无 "VALIDATION_FAILED" 代码字眼
  - [x] 死代码清理 (cascadeChain / selectedCascadeFields / object-type-selector / cascade_fields)

L1-Worktree: yes
L2-NoMain: yes
L3-Stash: yes
L4-Status: yes
L5-Service: yes
```

---

## 6. 风险评估

### 6.1 改动范围

| 维度 | 评估 |
|------|------|
| **文件数量** | 3 modified |
| **新增行数** | +330 |
| **删除行数** | -120 |
| **影响模块** | ImportDialog UI / 后端 thread-local user |

### 6.2 风险等级

```yaml
risk_level: medium

reason: |
  - medium: 服务逻辑、API 改动、新功能
  - 影响: 6 个对象类型 (domain → annotation) 的导入流程
  - 缓解: 已 E2E 验证导入仍能解析
```

### 6.3 缓解措施

```yaml
mitigation:
  - 回滚方案: git revert <commit> 或 git reset --hard c43f7b8
  - 测试覆盖: E2E 测试 (test_output/e2e_check.py)
  - 监控指标: 后端启动 + Vite 200 OK + 6 个对象类型全部处理
```

---

## 7. 沟通计划

```yaml
status_updates:
  - 启动: "开始 T-2026-06-19-import-dialog (worktree agent-import-dialog-fixes)"
  - 完成: "ready for merge T-2026-06-19-import-dialog"

broadcast_channel:
  - file: d:\filework\.agent-status.json
  - method: append_to_worktree_section
```

---

## 8. Review 流程

🟡 medium → Verifier quick check → Coordinator merge

---

## 9. 工作日志

```yaml
decisions:
  - 2026-06-19 12:00: 重构 UI 为 sheet-grouped layout (用户视角: "按 sheet 看问题")
  - 2026-06-19 12:30: 后端 operation 用 upsert_result.operation (修复 operation/message 不一致)
  - 2026-06-19 12:45: 新增 _clean_import_error_message 规范化 message (4 步清洗)
  - 2026-06-19 13:00: 修复 set_thread_user(user_dict) (传完整 permissions)
  - 2026-06-19 13:30: 清理 8 处死代码 (cascadeChain/selectedCascadeFields/object-type-selector/cascade_fields)

blockers:
  - (无)

insights:
  - 用户期望 UI 按 sheet 分组, 而不是全局混排
  - 后端 operation 应反映实际执行, 而非用户 Excel 中填的
  - 死代码 (cascadeChain 等) 之前没彻底清理, 需要在 worktree 中重做
```

---

## 10. 完成后 Checklist

- [x] spec.md 已填写完整
- [x] 所有改动在白名单内
- [x] 没有改动黑名单文件
- [ ] commit message 含铁律声明
- [ ] .agent-status.json 已更新
- [ ] Worktree 工作目录已清理 (debug 脚本)
- [ ] 告诉用户"ready for merge T-2026-06-19-import-dialog"
