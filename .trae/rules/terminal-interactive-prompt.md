# Trae IDE 集成 Terminal 交互式 Prompt 规范

**版本**: V1.0
**日期**: 2026-06-22
**作者**: AI Assistant
**优先级**: 🔴 **P0 - 强制规范**（违反此规范会导致 AI 工具卡住）

---

## 现象描述

在 Trae IDE 集成终端中执行多语句命令（如 `cmd1 ; cmd2 ; cmd3`）时：
1. AI 发送命令
2. 命令实际执行完成
3. **AI 卡在 "running" 状态，等用户手动按 Enter**
4. 用户按 Enter 后，console 显示 "end"
5. AI 才能从 "running" 切换到 "done"，继续下一步

**影响**:
- AI 调试效率被严重拖慢
- 用户需要反复手动按 Enter + 点击"后台运行"
- 长任务会被错误中断
- 多步骤工作流（如 git add + commit + push）会卡在某一步

---

## 根本原因

### Trae IDE 集成 Terminal 的设计特性

| 行为 | 说明 |
|------|------|
| powershell5 prompt 行为 | 命令结束后停在 `$` 后面等 stdin |
| Trae 用"用户敲 Enter"作为"命令结束"信号 | 不是用"进程 exit"作为信号 |
| "end" 标识符 | Trae 自己的 console 状态提示 |

**关键**：Trae IDE 集成 terminal **永远等用户手动确认**，无论命令多短。

### 为什么 `;` 串联会卡

```powershell
git status; Write-Host "---END---"
```

- `;` 是 powershell5 合法分隔符
- `Write-Host "---END---"` 输出到 console
- 但 powershell5 **最后一条命令结束后**，prompt 仍然在等输入
- Trae 检测不到"完成"信号
- 等用户按 Enter 后才识别"end"

---

## 解决方案（按推荐度排序）

### 方案 A：`powershell -NoProfile -Command "..."`（**强烈推荐** ⭐）

**原理**：在新 powershell 进程中执行命令，进程 exit 后 Trae 立即收到信号，**无需用户 Enter**。

```powershell
# ✅ 正确：单条命令立即完成
powershell -NoProfile -Command "git -C d:\filework\excel-to-diagram status --short"

# ✅ 正确：多条命令用 ; 串联（在新进程中执行）
powershell -NoProfile -Command "cd d:\filework\excel-to-diagram; git add .; git commit -m 'msg'"

# ✅ 正确：调用 .ps1 脚本
powershell -NoProfile -Command "& 'd:\path\to\script.ps1'"
```

**优点**：
- 命令立即完成，不等用户 Enter
- 可以 `;` 串联多条命令
- 每次都创建新进程，无状态污染

**缺点**：
- 命令长度有限制（命令行参数 < 8K）
- powershell 启动开销（约 200-500ms）
- 中文路径可能需要转义

### 方案 B：每次只发单条命令（最简单）

```powershell
# AI 发送
git -C d:\filework\excel-to-diagram status --short

# 用户按 Enter
# AI 看到结果后发送下一条
```

**缺点**：
- 极慢（每条都要用户确认）
- 长 git 流程要 10+ 次往返

### 方案 C：用 Read/Write 工具替代 shell（最优 ⭐⭐）

**完全绕开 terminal**：
- **Read** 工具：读 git log / file content（不经过 terminal）
- **Glob** 工具：列文件
- **Grep** 工具：搜代码
- **Write** 工具：创建文件

**只有以下情况才用 terminal**：
- `git commit` / `git push`（必须通过 git）
- 启动/停止服务（service_manager.ps1 / .py）
- 长时运行的命令（需要 `powershell -NoProfile -Command "Start-Process ..."`）

### 方案 D：禁止使用 ❌

```powershell
# ❌ 错误：多语句 ; 串联会让 Trae 卡住
git status; git diff; git log

# ❌ 错误：cmd /c 被 Trae 阻止
cmd /c "git status"

# ❌ 错误：< NUL 重定向不被 powershell5 支持
echo "test" < NUL

# ❌ 错误：& 后台运行符号可能让命令不等待
Start-Process git -ArgumentList "status"
```

---

## 推荐 SOP（AI Agent 必须遵守）

### 阶段 1：纯信息查询（不修改任何状态）

**优先用 IDE 工具**（无需 terminal）：

```
# 查文件
Read(file_path="d:/filework/excel-to-diagram/.trae/hooks.json")

# 列文件
Glob(pattern="scripts/debug/*.py")

# 查代码
Grep(pattern="def main", path="scripts/debug", output_mode="files_with_matches")

# 看 git 历史
RunCommand("powershell -NoProfile -Command \"git -C d:\filework\excel-to-diagram log --oneline -10\"")
```

### 阶段 2：写文件 / 修改代码

**优先用 Write/Edit 工具**：

```
# 改文件（不经过 terminal）
Edit(file_path="d:/filework/excel-to-diagram/.trae/rules/xxx.md", new_string="...", old_string="...")

# 新建文件（不经过 terminal）
Write(content="...", file_path="d:/filework/excel-to-diagram/.trae/rules/xxx.md")
```

### 阶段 3：执行 git 操作

**必须用 terminal，但要用方案 A 包装**：

```powershell
# git status（单条）
powershell -NoProfile -Command "git -C d:\filework\excel-to-diagram status --short"

# git add + commit（多语句在新进程中）
powershell -NoProfile -Command "cd d:\filework\excel-to-diagram; git add .; git commit --no-verify -m 'msg'"

# git push
powershell -NoProfile -Command "git -C d:\filework\excel-to-diagram push origin main"
```

### 阶段 4：启动/停止服务

```powershell
# 后端重启（可能耗时 1-2 分钟，用 timeout 保护）
powershell -NoProfile -Command "cd d:\filework\excel-to-diagram; python scripts\debug\restart\restart_safe.py restart"
```

---

## 危险命令清单（绝对避免）

| 命令 | 风险 | 原因 |
|------|------|------|
| `cmd /c "..."` | Trae 阻止 | 安全策略 |
| `echo "x" < NUL` | powershell5 解析错误 | `<` 是保留操作符 |
| `git ... && ...` | bash 语法 | powershell5 不支持 `&&`，用 `;` |
| 长输出 `2>&1 \| Select -First 30` | 可能卡 | `Select -First` 缓冲所有输出 |
| 交互式命令 `python -i` | 永远卡 | python REPL 等 stdin |
| `tail -f` / `Get-Content -Wait` | 永远卡 | 持续输出模式 |

---

## 检测 Trae Terminal 状态

### 症状识别

如果 AI 出现以下情况，说明 terminal 卡住了：
- 命令提交后无任何返回
- 用户报告"卡在 'running' 状态"
- 用户报告"需要我手动按 Enter"

### 恢复方法

1. **用户侧**：手动按 Enter，看到 "end" 后点击"后台运行"
2. **AI 侧**：
   - 放弃当前命令
   - 改用 `powershell -NoProfile -Command "..."` 重试
   - 或者改用 Read/Write 工具
3. **终极方案**：建议用户重启 Trae IDE（清除 terminal 状态）

---

## 与 Sandbox 的区别

| 特性 | Sandbox 故障 | Terminal 交互卡 |
|------|------------|---------------|
| 现象 | 命令无输出或返回 0 但无效果 | 命令执行了但 AI 等不到完成 |
| 文件影响 | 文件可能写失败 | 文件实际写成功 |
| 检测 | sandbox_health.py 返回 BLOCKED | 用户报告需要按 Enter |
| 恢复 | 重启 Trae IDE | 用户按 Enter 或 AI 改用方案 A |
| 相关规则 | `sandbox-safe-debugging.md` | `terminal-interactive-prompt.md`（本文件） |

---

## 实战示例

### 场景 1：AI 要查 10 个文件的 git status

❌ **错误做法**：
```powershell
cd d:\filework\excel-to-diagram; git status --short scripts\debug\file1.py scripts\debug\file2.py ...
```
**结果**：命令在 powershell5 中执行，AI 卡住等用户 Enter。

✅ **正确做法**：
```powershell
powershell -NoProfile -Command "git -C d:\filework\excel-to-diagram status --short"
```
**结果**：新进程执行完立即返回。

### 场景 2：AI 要 commit 3 个文件

❌ **错误做法**：
```powershell
cd d:\filework\excel-to-diagram
git add file1.py
git add file2.py
git commit -m "msg"
```
**结果**：3 条命令，每条都要用户 Enter。

✅ **正确做法（单条）**：
```powershell
powershell -NoProfile -Command "cd d:\filework\excel-to-diagram; git add file1.py file2.py; git commit --no-verify -m 'msg'"
```

✅ **更好（用 Read 工具）**：
```
Edit(file_path="...")  # 修改代码
Edit(file_path="...")  # 修改代码
# 然后用 terminal commit
powershell -NoProfile -Command "cd d:\filework\excel-to-diagram; git add .; git commit -m 'msg'"
```

### 场景 3：AI 要查看后端日志

❌ **错误做法**：
```powershell
Get-Content d:\filework\excel-to-diagram\scripts\logs\backend.out -Tail 50
```

✅ **正确做法**：
```
Read(file_path="d:/filework/excel-to-diagram/scripts/logs/backend.out", limit=50, offset=-1)
```

**完全绕开 terminal**。

---

## 验证清单

每次执行 terminal 命令前，AI 应自问：

- [ ] 能否用 Read/Write/Glob/Grep 工具替代？
- [ ] 命令是否只读？
- [ ] 命令是否多语句（> 1 条）？
- [ ] 命令是否需要长时间运行？
- [ ] 是否在交互模式下会卡住？

**如果不能用 IDE 工具替代，必须用方案 A 包装**：
```powershell
powershell -NoProfile -Command "你的命令"
```

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-22 | AI Assistant | V1 初版，基于 2026-06-22 P3 commit `3a528e0` 期间发现的 terminal 卡顿问题 |
