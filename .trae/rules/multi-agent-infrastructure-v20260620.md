---
alwaysApply: true
description: "多 Agent 并行工作基础设施规范 (v2026.06.20) - 基于 2026-06-20 WriteScopeDenied 修复事故复盘。解决 7 个多 Agent 协作基础设施缺陷：修复完整性、commit 频率、agent 间通信、测试反馈、pre-commit hook、agent 角色分工、状态共享。"
---

# 多 Agent 并行工作基础设施规范 (v2026.06.20)

> **本文档基于 2026-06-20 实际事故复盘，发现现有 `multi-agent-coordination.md` (v3.24) 在以下 7 个基础设施层面有重大缺陷。**
>
> **事故概要**：
> - v1.2.25 修复 `WriteScopeDenied` 类加了 `business_key/object_type_name/side_info` 参数
> - 但调用方 (`raise` site) 调用了**未实现的方法** `_extract_business_key`
> - 多个 agent 在**主工作树**做修改，未 commit，跨 agent 互相干扰
> - 4 个测试用例中 2 个失败（Test 2 FK scope 400/422 错误，Test 4 AttributeError 500）
> - Agent 错误诊断为"修复被 stash 覆盖"，实际是"修复未完成 + 未提交"

---

## 一、现有规则 7 大基础设施缺陷

### 缺陷 1：缺少"修复完整性"检查

**事故证据**：

```
v1.2.25 修复内容（partial）：
✅ WriteScopeDenied.__init__ 加了 business_key/object_type_name/side_info 参数
✅ class __init__ 内部 fallback 处理 None 参数
✅ raise site (line 410) 传了 business_key/object_type_name/side_info
❌ 但 raise site 调用了 self._extract_business_key() —— 方法从未实现
❌ raise site 调用了 context.meta_object.name —— 但 _check_target 路径 meta_object 可能为 None
```

**根因**：
- Agent 提交了"看起来完整"的代码，但**没运行测试**验证
- 没有任何机制检查"类签名改了，所有调用方都跟着改了吗"

**改进方案**：
1. **修改前先 grep 所有调用方**：
   ```bash
   # 改类签名后必须 grep
   grep -n "_extract_business_key\|business_key=" meta/ -r
   ```
2. **每个修改文件单独 commit**（不要跨文件混合）：
   - `fix(backend): v1.2.25.a add business_key to WriteScopeDenied.__init__`
   - `fix(backend): v1.2.25.b implement _extract_business_key helper`
   - `fix(backend): v1.2.25.c update raise sites to pass business_key`
3. **测试通过才算修复完成**：
   - 改类签名 → 跑测试 → 测试通过 → 才 commit
   - 测试失败 → 不 commit，先修测试

---

### 缺陷 2：缺少 Commit 频率约束

**事故证据**：

```
当前 main working tree：
  M meta/core/action_executor.py              # v1.2.21 (status_code)
  M meta/core/interceptors/write_scope_interceptor.py  # v1.2.25 (partial)
  M meta/services/import_export_service.py    # v1.2.22 + v1.2.28
  M scripts/logs/frontend.err                 # 自动生成
  M scripts/logs/frontend.out                 # 自动生成
  ?? _restart.ps1                             # 其他 agent 临时文件
```

**根因**：
- 多个 agent 各自修改，没人立即 commit
- 工作树积累 6 个文件的混合修改
- 一个 agent 的未完成修改，可能影响另一个 agent 的工作

**改进方案**：

1. **"小步快跑"原则**：每个逻辑完整的修改立即 commit
   - 改类签名 → commit（即使调用方还没改）
   - 改调用方 → commit
   - 加 helper 方法 → commit
   - 不要"等到所有都改完再 commit"
2. **明确未完成标记**（避免误以为完整）：
   ```python
   # [WIP 2026-06-20] TODO: implement _extract_business_key
   # 临时用 str(target_id) 作为 fallback
   business_key = None  # TODO: self._extract_business_key(object_type, record)
   ```
3. **必须用 `--no-verify` 的文件单独 commit**：
   - pre-commit hook 误判时绕过，但 commit message 必须注明原因

---

### 缺陷 3：缺少 Agent 间通信机制

**事故证据**：
- Agent A 改了 WriteScopeDenied 类（partial）
- Agent B 在写测试
- Agent C 报告"修复被 stash 覆盖"（错误诊断，实际是未提交）
- **没有 Agent 知道其他 Agent 在做什么**

**根因**：
- 没有共享任务板
- 没有"我正在改这个文件"的声明机制
- 没有"我发现了这个问题，请 X 来修"的协作流程

**改进方案**：

1. **每个 Agent 启动时声明**：
   ```markdown
   ## Agent-{name} 工作日志 (started {timestamp})

   ### 当前任务
   - [ ] 修复 WriteScopeDenied.business_key
   - [ ] 添加 _extract_business_key 实现
   - [ ] 跑测试验证

   ### 锁定文件
   - `meta/core/interceptors/write_scope_interceptor.py` (read+write)
   - `meta/services/import_export_service.py` (read+write)

   ### 不修改
   - `meta/core/action_executor.py` (Agent B 在改)

   ### 已完成 commit
   - xxx1: 修改类签名
   - xxx2: 实现 helper 方法
   ```
2. **共享状态文件**（可选）：
   - `.trae/agent_status.json` - 所有 agent 状态
   - 字段：`agent_name, started_at, current_task, locked_files, last_commit`

---

### 缺陷 4：缺少测试反馈回路

**事故证据**：

```
Agent A 修复 v1.2.25（不完整）
   ↓ (没跑测试)
Agent B 写测试用例 1, 2, 3, 4
   ↓ (跑测试)
Test 4 HTTP 500 (AttributeError _extract_business_key)
   ↓ (报告给用户)
User 反馈给 Agent A
   ↓ (Agent A 修复)
```

**根因**：
- 修复和测试不在同一个工作流中
- Agent A 不知道 Test 4 会失败
- Agent A 不知道 _extract_business_key 缺失

**改进方案**：

1. **修复后立即测试**（修复自己跑测试，不等别人测）：
   ```python
   # 测试用例应该和修复一起 commit
   def test_v1_2_25_business_key_extracted():
       # 给一个 record with code="REL_001"
       # 调用 raise
       # 验证 message 包含 "REL_001" 而不是 "21"
   ```
2. **测试失败信息要包含足够 context**：
   ```
   Test 4 FAILED: AttributeError: 'WriteScopeInterceptor' object has no attribute '_extract_business_key'
   File: write_scope_interceptor.py, line 415
   Called from: _check_target (line 410)
   Fix needed: implement _extract_business_key(object_type, record)
   Suggested signature: _extract_business_key(self, object_type: str, record: Dict) -> Optional[str]
   ```

---

### 缺陷 5：Pre-commit Hook 被滥用

**事故证据**：

```
最近 6 个 commit 都用 --no-verify：
  b6f438b fix(audit): [P2 v2] AuditService 入口 tx_id/trace_id auto-gen [pm-authorized]
  7fd2261 fix(backend): v1.2.20 lazy import WriteScopeInterceptor ... [pm-authorized]
  7574b19 fix(backend): v1.2.19 write path dim scope check + Trae hooks simplify [pm-authorized]
  ...
```

**根因**：
- Pre-commit hook 误报太多（MOJIBAKE_CHARS, SIZE_BLOAT）
- Agent 选择 `--no-verify` 绕过
- Hook 失去保护作用

**改进方案**：

1. **优先修复 hook**：
   - MOJIBAKE_CHARS 误报 → 用更严格的 UTF-8 BOM 检查
   - SIZE_BLOAT 误报 → 区分"合理大文件"和"真的 bloat"
2. **避免频繁 --no-verify**：
   - 如果必须 `--no-verify`，commit message 必须说明原因
   - 不要连续 3+ 个 commit 都 `--no-verify`
3. **Pre-commit hook 改为可选检查**：
   - `pre-commit` (必跑): 文件编码、敏感文件
   - `pre-commit-extra` (可选): 文件大小、MOJIBAKE
   - Agent 可以 `--no-verify-extra` 跳过额外检查

---

### 缺陷 6：缺少 Agent 角色分工

**事故证据**：
- 当前所有 agent 角色相同："AI Coding Agent"
- 修复、测试、Review 都由同一个 agent 做
- 没有人专门做"修复完整性验证"

**改进方案**：

| 角色 | 职责 | 工具 |
|------|------|------|
| **Fixer** | 实现修复 | Edit/Write |
| **Tester** | 写测试 + 跑测试 | test.py / scripts/agent_test.py |
| **Reviewer** | 验证修复完整性 | git diff + grep 调用方 |
| **PM** | 合并 worktree → main | git merge |
| **Cleanup** | 清理 stash / 已合并 worktree | git stash drop / worktree remove |

**工作流**：
```
Fixer 实现 → Tester 写测试 → Tester 跑测试
   ↓ (测试失败)
Fixer 修复 → Tester 重跑
   ↓ (测试通过)
Reviewer 验证完整性
   ↓ (通过)
PM 合并到 main → Cleanup 清理 worktree
```

---

### 缺陷 7：缺少工作树清洁度监控

**事故证据**：
- 6 个 uncommitted changes 在 main
- 3 个 stash 残留
- 多个 worktree 已合并但未清理

**根因**：
- 没有定期检查"working tree 干净度"
- 没有"X 个文件未提交就警告"的机制

**改进方案**：

1. **每次 commit 前检查 working tree**：
   ```bash
   # 只 commit 自己的修改
   git status --short | wc -l
   # > 5 个文件？停下来 review，确认是否都是同一个任务
   ```
2. **自动监控脚本**：
   ```python
   # scripts/multi_agent_monitor.py
   def check_working_tree_cleanliness():
       uncommitted = len(run('git status --short'))
       stashes = len(run('git stash list'))
       worktrees = len(run('git worktree list'))
       if uncommitted > 5:
           alert(f'Main working tree has {uncommitted} uncommitted changes')
       if stashes > 0:
           alert(f'{stashes} stashes pending cleanup')
   ```
3. **定期 cleanup**：
   - 每天结束时清理已合并的 worktree
   - 每周清理一次 stash

---

## 二、新工作流规范（修复事故 7 大缺陷）

### 2.1 Agent 启动时（强化版）

```powershell
# Step 1: bootstrap worktree (现有 L1 强制)
powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-X -Port 3010

# Step 2: 声明当前任务 (新增)
Write .trae/agent_status.json '
{
  "agent_name": "agent-X",
  "started_at": "2026-06-20T23:00:00Z",
  "current_task": "fix(v1.2.25): WriteScopeDenied business_key",
  "locked_files": ["meta/core/interceptors/write_scope_interceptor.py"],
  "task_id": "v1.2.25-write-scope-business-key"
}
'

# Step 3: 检查其他 agent 状态
cat .trae/agent_status.json | jq -r '.[] | "\(.agent_name): \(.current_task) (\(.locked_files | join(", ")))"'
```

### 2.2 Agent 修改时（强化版）

```
❌ 错误做法（现有）：
1. 修改类签名
2. 修改调用方
3. 修改 helper 方法
4. 跑测试
5. 失败 → 调试
6. 都通过 → commit 整个

✅ 正确做法（建议）：
1. 修改类签名 → git diff 验证 → commit "fix(v1.2.25.a): add business_key param"
2. 添加 helper 方法（即使暂时返回 None） → commit "fix(v1.2.25.b): add _extract_business_key stub"
3. 实现 helper 方法 → commit "fix(v1.2.25.c): implement _extract_business_key"
4. 修改调用方 → grep 验证 → commit "fix(v1.2.25.d): use _extract_business_key in raise site"
5. 写测试用例 → commit "test(backend): test_v1_2_25_business_key"
6. 跑测试 → 通过 → 标记任务完成
```

### 2.3 Agent 测试时（强化版）

```python
# 必须包含 3 类测试
def test_v1_2_25_unit_business_key_extraction():
    """单元测试: _extract_business_key 行为"""
    pass

def test_v1_2_25_integration_write_scope_denied():
    """集成测试: WriteScopeDenied message 包含 business_key"""
    pass

def test_v1_2_25_e2e_user_scenario():
    """E2E: TEST333 update relationship 21 看到业务键而非 ID"""
    # 这是 Test 1 的场景
    pass
```

### 2.4 Agent Commit 时（强化版）

```bash
# 1. 检查 working tree 干净度
git status --short
# > 5 个文件？停下来 review

# 2. 单文件 commit (不要混合)
git add meta/core/interceptors/write_scope_interceptor.py
git commit --no-verify -m "fix(backend): v1.2.25.a add business_key to WriteScopeDenied

[FIX v1.2.25.a 2026-06-20]
- Add business_key/object_type_name/side_info params to WriteScopeDenied.__init__
- Add fallback to use object_type/target_id if None
- NOT YET: raise site update, _extract_business_key helper

Refs: v1.2.25-1, v1.2.25-2
[pm-authorized]"

# 3. 验证 commit 成功
git log --oneline -1
```

### 2.5 Agent 完成时（强化版）

```bash
# 1. 通知其他 agent
cat .trae/agent_status.json | jq ".[] | select(.agent_name == \"agent-X\") | .status = \"completed\""

# 2. 触发 PM review
echo "Agent-X 任务完成，请 PM review"
# (PM agent 或用户来合并)

# 3. 清理 (PM 合并后)
git worktree remove ../agent-X-worktree
git branch -d agent/agent-X
```

---

## 三、基础设施改进清单（按 ROI 排序）

### 🟢 P0：立即实施（低成本高收益）

| 改进 | 工作量 | 收益 |
|------|--------|------|
| 1. 小步快跑 commit | 0 | 避免修复冲突 |
| 2. 修复前 grep 调用方 | 0 | 避免不完整修复 |
| 3. 修复后立即测试 | 0 | 避免 Test N 500 错误 |
| 4. working tree 干净度检查 | 5 分钟 | 避免 6+ 个未提交修改 |

### 🟡 P1：本周实施

| 改进 | 工作量 | 收益 |
|------|--------|------|
| 5. Agent 角色分工 | 30 分钟 | 明确职责 |
| 6. 共享 agent_status.json | 1 小时 | Agent 间通信 |
| 7. Pre-commit hook 改造 | 2 小时 | 减少误报 |

### 🟡 P2：本月实施

| 改进 | 工作量 | 收益 |
|------|--------|------|
| 8. multi_agent_monitor.py | 4 小时 | 自动监控 |
| 9. Reviewer agent 流程 | 8 小时 | 修复完整性 |
| 10. Worktree 自动清理 | 4 小时 | 减少 27 个分支混乱 |

### 🟢 P3：可选

| 改进 | 工作量 | 收益 |
|------|--------|------|
| 11. Web dashboard | 16 小时 | 可视化 |
| 12. Slack 通知 | 8 小时 | 实时协作 |

---

## 四、本次事故的具体改进

### 4.1 立即可做

1. **修复 v1.2.25 完成版**（其他 agent 在做）：
   - 实现 `_extract_business_key` 方法
   - 验证 `_check_target` 路径下 `meta_object` 可用
   - 测试 4 个用例全部通过

2. **commit 已完成的修复**：
   - v1.2.21 (ActionResult.status_code)
   - v1.2.22 (import_export_service _update_record 返回值处理)
   - v1.2.25 (WriteScopeDenied 完整修复)
   - v1.2.28 (import_export_service virtual field 跳过)

3. **清理 working tree**：
   - 6 个文件 commit 后应该全部清空
   - 3 个 stash 清理（已无价值）

### 4.2 基础设施改进

1. **添加 agent_status.json 跟踪**：
   ```bash
   # .gitignore 添加
   .trae/agent_status.json
   ```

2. **改进 SESSION_REMINDER.md**：
   - 添加"小步快跑 commit"原则
   - 添加"修复完整性检查"清单

3. **创建 scripts/check_fix_completeness.py**：
   - 自动扫描类签名修改
   - 找出所有调用方
   - 列出未实现的 helper 方法

---

## 五、修订现有规则

### 5.1 在 multi-agent-coordination.md v3.24 中追加

```markdown
## v3.25 (2026-06-20): 基于 WriteScopeDenied 修复事故的改进

### 新增铁律

- ❌ **禁止"修改类签名但调用方未跟上"的 commit**（必须 grep 验证所有调用方）
- ❌ **禁止"未跑测试就 commit"**（修复 + 测试 + 通过 → 才 commit）
- ❌ **禁止"working tree 超过 5 个未提交文件"**（commit 频率不足）
- ✅ **必须"小步快跑 commit"**（类签名、helper、调用方、测试分开 commit）
- ✅ **必须"修复完整性声明"**（commit message 写明"NOT YET"部分）

### 新增工作流

见 `.trae/rules/multi-agent-infrastructure-v20260620.md`
```

### 5.2 在 SESSION_REMINDER.md 中追加

```markdown
## 19. 修复完整性铁律 (2026-06-20 新增)

### 修改类签名时必须

1. **grep 所有调用方**：`grep -n 'ClassName' meta/ -r`
2. **helper 方法定义和调用方修改分开 commit**
3. **测试通过才算修复完成**

### Commit 频率铁律

1. **小步快跑**：类签名、helper、调用方、测试分开 commit
2. **不积压**：working tree 超过 5 个文件未提交 = 必须先 commit
3. **明确 WIP**：未完成修改用 [WIP] 标记，禁止假装"已完成"

### Agent 间通信铁律

1. **启动时声明**：写 .trae/agent_status.json
2. **任务完成时通知**：更新 status 为 completed
3. **冲突时沟通**：发现其他 agent 正在改同一文件，立即协调
```

---

## 六、参考与引用

- **事故复盘**: 2026-06-20 WriteScopeDenied v1.2.25 修复不完整
- **现有规则**: `.trae/rules/multi-agent-coordination.md` (v3.24)
- **现有规则**: `.trae/rules/SESSION_REMINDER.md` (18 铁律)
- **修改文件**:
  - `meta/core/action_executor.py` (v1.2.21)
  - `meta/core/interceptors/write_scope_interceptor.py` (v1.2.25 partial)
  - `meta/services/import_export_service.py` (v1.2.22 + v1.2.28)
- **测试结果**:
  - Test 1: ✅ 消息格式 OK（业务键是 ID 不是 code - 因为 helper 未实现）
  - Test 2: ❌ FK scope 422 应返回 422 而非 400
  - Test 3: ✅ admin 跳过正确
  - Test 4: ❌ HTTP 500 - _extract_business_key 不存在导致 AttributeError

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-20 | AI Assistant | 基于 WriteScopeDenied 修复事故复盘，创建本文档。识别 7 大基础设施缺陷，提出改进方案。 |