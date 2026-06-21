---
alwaysApply: true
description: "[DEPRECATED 2026-06-21] 多 Agent 并行工作基础设施 V1 - 已被 V2.1 替代"
---

# [DEPRECATED 2026-06-21] 多 Agent 并行工作基础设施规范 (V1)

> **DEPRECATED**: 此规则已被 **V2.1** 替代。
>
> **请使用**: `.trae/rules/multi-agent-infrastructure-v20260620-v2.md` (V2.1, 13 铁律)
>
> **保留原因**:
> - 作为历史参考（事故复盘记录）
> - AI Agent 决策日志可能引用此规则的旧版本号（V1）
> - 便于追溯规则演进过程
>
> **弃用决策**: 见 `.trae/rules/active/CHANGELOG.md` v2026.06.21

---

# 多 Agent 并行工作基础设施规范 (v2026.06.20)

---

## 🚨 TL;DR - 一页纸速查（AI 必读）

> **基于 2026-06-20 WriteScopeDenied v1.2.25 修复事故**：类改了但 helper 方法未实现，4 测试用例 2 失败。

### 5 条铁律（必须遵守）

| # | 铁律 | 触发场景 |
|---|------|---------|
| 1 | **改类签名 → grep 所有调用方** | 修改 `__init__` / `class XXX` |
| 2 | **小步快跑 commit** | 类签名、helper、调用方、测试分开 commit |
| 3 | **修复 + 测试 + 通过 → 才 commit** | 写完代码立即跑测试 |
| 4 | **Working tree 不超过 5 个未提交文件** | `git status --short \| wc -l > 5` 必须先 commit |
| 5 | **明确 WIP 标记** | 未完成修改用 `# [WIP]` + `TODO`，禁止假装"已完成" |

### 3 步 Commit 前检查清单

```
[1] git diff <file> - 修改范围是否单一？
[2] grep '<ClassName>' meta/ -r - 所有调用方都跟上了吗？
[3] python -m pytest <test> - 测试通过吗？
```

---

## 一、事故概要（5 行看懂）

| 项 | 内容 |
|------|------|
| **事故** | `WriteScopeDenied` v1.2.25 修复不完整 |
| **症状** | 4 测试用例中 2 失败（Test 2 FK scope 400/422, Test 4 AttributeError 500） |
| **根因** | 类签名改了，调用方调用了**未实现**的 `_extract_business_key()` |
| **诊断** | Agent 错误诊断"修复被 stash 覆盖"，实际"修复未完成 + 未提交" |
| **教训** | 缺少修复完整性检查 + commit 频率约束 + agent 间通信 |

---

## 二、5 大基础设施缺陷与修复

### 缺陷 1：修复完整性检查缺失 🔴

**事故**：raise site 调用 `self._extract_business_key()` 但方法未实现 → Test 4 HTTP 500

**修复（1 条命令）**：
```bash
# 修改类签名后强制执行
grep -n '<ClassName>\|<new_param>=' meta/ -r
```

### 缺陷 2：Commit 频率约束缺失 🟡

**事故**：main 有 6 个未提交文件混合多个版本的修复

**修复**：
```bash
# Commit 前检查
N=$(git status --short | wc -l)
if [ $N -gt 5 ]; then
  echo "❌ Working tree has $N files, review and split commits"
  exit 1
fi
```

### 缺陷 3：Agent 间通信缺失 🟡

**事故**：Agent A 改类、Agent B 写测试、Agent C 错误诊断，无人知全局

**修复**：写 `.trae/agent_status.json`：
```json
{
  "agent_name": "agent-X",
  "current_task": "fix(v1.2.25)",
  "locked_files": ["write_scope_interceptor.py"],
  "last_commit": "e420391"
}
```

### 缺陷 4：测试反馈回路缺失 🟡

**事故**：Agent A 修复后没跑测试 → Agent B 跑测试 → 发现失败

**修复**：修复后立即跑相关测试：
```bash
python -m pytest meta/tests/test_v1_2_25_*.py -v
```

### 缺陷 5：Pre-commit Hook 被滥用 🟢

**事故**：最近 6 个 commit 都 `--no-verify`

**修复**：
- 必须 `--no-verify` 时，commit message 注明原因
- 连续 3+ `--no-verify` 触发 hook 修复任务

---

## 三、强化版工作流（5 阶段）

### 3.1 启动时

```bash
# 1. Worktree 隔离（已有 L1）
git worktree add ../agent-X-worktree -b agent/agent-X

# 2. 声明任务（新增）
cat > .trae/agent_status.json <<EOF
{
  "agent_name": "agent-X",
  "current_task": "fix(...)",
  "locked_files": [...]
}
EOF
```

### 3.2 修改时（小步快跑）

| 步骤 | 操作 | Commit |
|------|------|--------|
| 1 | 改类签名 | `fix(...).a add param` |
| 2 | 加 helper 方法 stub | `fix(...).b add stub` |
| 3 | 实现 helper | `fix(...).c implement helper` |
| 4 | 改调用方 | `fix(...).d use helper` |
| 5 | 写测试 | `test(...)` |
| 6 | 跑测试通过 | `chore: mark task done` |

### 3.3 测试时（3 类必须）

```python
def test_unit_business_key_extraction():     # 单元
def test_integration_write_scope_denied():  # 集成
def test_e2e_test333_update_relationship(): # E2E
```

### 3.4 Commit 时（强制检查）

```bash
# [1] 单文件 commit
git add <single_file>

# [2] message 含 NOT YET（如未完成）
git commit --no-verify -m "fix(...).a: ...
NOT YET: raise site update
[pm-authorized]"

# [3] 验证
git log --oneline -1
```

### 3.5 完成时（清理 + 通知）

```bash
# 1. 更新 agent_status.json (status=completed)
# 2. 通知 PM review
# 3. PM 合并后: git worktree remove + git branch -d
```

---

## 四、Agent 角色分工（5 个角色）

| 角色 | 职责 | 工具 |
|------|------|------|
| **Fixer** | 实现修复 | Edit / Write |
| **Tester** | 写测试 + 跑测试 | pytest / test.py |
| **Reviewer** | 验证修复完整性 | git diff + grep |
| **PM** | 合并 worktree → main | git merge |
| **Cleanup** | 清理 stash / worktree | git stash drop / worktree remove |

**工作流**：
```
Fixer → Tester → Reviewer → PM → Cleanup
 ↑                              ↓
 └──── 测试失败 ────────────────┘
```

---

## 五、改进清单（按 ROI 排序）

### 🟢 P0：立即（0 成本）

| # | 改进 | 收益 |
|---|------|------|
| 1 | 小步快跑 commit | 避免修复冲突 |
| 2 | 修复前 grep 调用方 | 避免不完整修复 |
| 3 | 修复后立即测试 | 避免 Test N 500 错误 |
| 4 | Working tree 干净度检查 | 避免 6+ 未提交 |

### 🟡 P1：本周

| # | 改进 | 工作量 |
|---|------|--------|
| 5 | Agent 角色分工 | 30 分钟 |
| 6 | `agent_status.json` | 1 小时 |
| 7 | Pre-commit hook 改造 | 2 小时 |

### 🟡 P2：本月

| # | 改进 | 工作量 |
|---|------|--------|
| 8 | `multi_agent_monitor.py` | 4 小时 |
| 9 | Reviewer agent 流程 | 8 小时 |
| 10 | Worktree 自动清理 | 4 小时 |

---

## 六、修订现有规则（行动项）

### 6.1 `multi-agent-coordination.md` v3.24 → v3.25

在文末追加：
```markdown
## v3.25 (2026-06-20) - 5 大基础设施铁律

### 新增铁律
- ❌ 禁止"修改类签名但调用方未跟上"的 commit
- ❌ 禁止"未跑测试就 commit"
- ❌ 禁止"working tree 超过 5 个未提交文件"
- ✅ 必须"小步快跑 commit"
- ✅ 必须"修复完整性声明"（NOT YET 部分）

详见：.trae/rules/multi-agent-infrastructure-v20260620.md
```

### 6.2 `SESSION_REMINDER.md` 18 铁律 → 19 铁律

在文末追加"19. 修复完整性铁律"（3 条）：
```markdown
## 19. 修复完整性铁律 (2026-06-20)

### 修改类签名时必须
1. grep 所有调用方：`grep -n '<ClassName>' meta/ -r`
2. helper 方法定义和调用方修改分开 commit
3. 测试通过才算修复完成

### Commit 频率铁律
1. 小步快跑（类签名/helper/调用方/测试分开 commit）
2. working tree ≤ 5 个未提交文件
3. 明确 WIP 标记（`# [WIP]` + `TODO`）

### Agent 间通信铁律
1. 启动时写 `.trae/agent_status.json`
2. 任务完成时更新 status=completed
3. 冲突时立即沟通
```

### 6.3 创建 `scripts/check_fix_completeness.py`

```python
"""自动扫描修复完整性"""
import re
import subprocess
from pathlib import Path

def check_class_signature_changed(file: Path, old: str, new: str) -> list:
    """检查类签名修改的所有调用方"""
    result = subprocess.run(
        ['grep', '-rn', old, 'meta/'],
        capture_output=True, text=True
    )
    return result.stdout.splitlines()

def check_helper_method_exists(file: Path, method: str) -> bool:
    """检查 helper 方法是否实现"""
    content = file.read_text(encoding='utf-8')
    return f'def {method}' in content
```

---

## 七、参考

- **事故复盘**: 2026-06-20 WriteScopeDenied v1.2.25 修复不完整
- **现有规则**: `multi-agent-coordination.md` (v3.24) → v3.25
- **现有规则**: `SESSION_REMINDER.md` (18 铁律) → 19 铁律
- **测试结果**: Test 4 HTTP 500 - `_extract_business_key` AttributeError

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-20 | v1.0 | 初版：识别 7 大缺陷，514 行 |
| 2026-06-20 | v1.1 | 优化：TL;DR + 5 铁律 + 精简 514→200 行 |