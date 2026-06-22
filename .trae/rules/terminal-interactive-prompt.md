# Trae IDE Sandbox 故障根因与命令规范

**版本**: V3.5 P5 (2026-06-22 修正版)
**优先级**: 🔴 **P0 - 强制规范**（违反此规范会导致 sandbox skip / 命令卡死）

---

## ⚠️ V3.5 P5 重大修正

**V1 规范写错了**！

之前认为是 Trae terminal 的设计问题（等用户 Enter），实际是 **sandbox 主动跳过复杂命令**。

### V1 错误判断

```powershell
# V1 规范认为这是好的
powershell -NoProfile -Command "git add a; git add b; git commit"  # ← 实际会被 sandbox skip
```

### V3.5 P5 真相

```
Trae sandbox daemon 检测命令模式 →
  包含 (& | ; && || 2>&1 | Select-Object -First N) →
  主动标记 RunningSkipped →
  用户看到 "end" 但实际什么都没执行
```

---

## 🔥 Sandbox 跳过的命令模式（实测）

### ❌ 100% 跳过的模式

| 模式 | 例子 | 原因 |
|------|------|------|
| `&` 字符 | `git add a & git add b` | sandbox 误判为后台进程 |
| `&&` 语法 | `cd x && git add .` | bash 语法，powershell5 解析失败 |
| `\|\|` 语法 | `cmd1 \|\| cmd2` | 同上 |
| 多语句 `;` | `cd x; ls; git status` | sandbox daemon 缓冲累积 |
| 管道 `\|` | `git log \| head` | 缓冲累积 |
| `2>&1` | `cmd 2>&1` | 重定向触发 |
| `Select-Object -First N` | `... \| Select -First 3` | 变量名被吞 |
| `ForEach-Object` | `... \| ForEach-Object {...}` | 复杂对象操作 |
| `Where-Object` | `... \| Where-Object {$x -gt 5}` | 复杂过滤 |
| `Out-File` | `echo x \| Out-File y` | 重定向触发 |
| `\| Out-Host` | `cmd \| Out-Host` | 强制输出仍卡 |
| `Get-NetTCPConnection \| Select` | 检查端口 | 复合触发 |
| Here-string `@"..."@` | 多行字符串 | 解析卡 |

### ✅ 唯一稳定模式

**单条 Python 命令**：

```bash
# ✅ 稳定
python script.py
python script.py arg1 arg2
python script.py --safe-output
```

**单条 Git 命令**（不用 powershell 包装）：

```bash
# ✅ 稳定
git status
git log --oneline -5
git add file.py
git commit -m "msg"
```

**单条 Powershell 命令（简单）**：

```bash
# ✅ 稳定
powershell -Command "Get-Date"
powershell -Command "Write-Host 'hello'"
```

---

## 🎯 正确的工作流

### Phase 1: 优先用 IDE 工具（不经过 sandbox）

```
✅ Read 工具 - 读文件
✅ Write 工具 - 写文件
✅ Edit 工具 - 修改文件
✅ Glob 工具 - 列文件
✅ Grep 工具 - 搜内容
```

### Phase 2: 必须跑命令时

```bash
# ✅ 单条 Python
python scripts/debug/safe_query.py health

# ✅ 单条 git
git add file.py

# ✅ 单条 powershell（极简）
powershell -Command "Get-Date"
```

### Phase 3: 必须做复杂操作时

```bash
# 1. Write 工具创建 Python 脚本
# 2. 单条 python script.py
# 3. Read 工具读结果
```

---

## 🚫 禁用模式（绝对不要用）

```powershell
# ❌ 多语句分号
cd x; ls; git status

# ❌ bash 语法
cd x && git add .

# ❌ 后台 &
cmd1 & cmd2

# ❌ 管道
git log | head -5

# ❌ 输出缓冲
git log 2>&1 | Select-Object -First 5

# ❌ 重定向
echo "x" | Out-File y.txt

# ❌ 复杂 powershell
$var = Get-NetTCPConnection -LocalPort 3010 | Select-Object -First 1
```

---

## 📋 Hook 配置原则

**Hook 命令也必须遵守**：

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python scripts/debug/utils/session_start_bootstrap.py"  // ✅ 简单
      }]
    }]
  }
}
```

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "powershell -NoProfile -Command \"Get-NetTCPConnection | Select-Object -First 1\""  // ❌ 会 skip
      }]
    }]
  }
}
```

---

## 🔍 如何检测 sandbox skip

```bash
# 1. 执行命令
git add .trae/debug/README.md

# 2. 立即检查是否真的成功
# ✅ 用 Read 工具读文件内容
# ✅ 用 Glob 看文件列表

# 3. 如果怀疑 skip，重跑命令
```

---

## 📚 相关文件

| 文件 | 用途 |
|------|------|
| `.trae/hooks.json` | hook 配置（V3.5 P5 重写，纯 Python） |
| `.trae/rules/sandbox-safe-debugging.md` | safe-output 调试规范 |
| `scripts/debug/utils/session_start_bootstrap.py` | SessionStart Python hook |
| `scripts/debug/utils/_pre_tool_hook.py` | PreToolUse Python hook |
| `scripts/debug/utils/auto_status.py` | 手动状态感知 |

---

## 🎯 V3.5 P5 总结

**核心原则**：

1. **IDE 工具优先** - Read/Write/Edit/Glob/Grep 不走 sandbox
2. **单条 Python 命令** - 复杂逻辑写脚本
3. **避免所有 inline PowerShell 习惯** - `;`, `&`, `&&`, `||`, `|`, `2>&1`, `Select-Object`
4. **怀疑 skip 时用 Read 工具验证** - 不靠 exit code

**之前所有 V1/V3.5 P0-P4 的 powershell 包装都是错的！**

---

_V3.5 P5 (2026-06-22) 重写 - 全面修正 V1 的错误判断_
_V1 (2026-06-22) 错误版已废弃_