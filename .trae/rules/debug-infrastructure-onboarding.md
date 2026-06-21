---
alwaysApply: true
description: "调试基础设施 onboarding - 强制所有 Agent 升级到最新 V2.2 调试工具链"
---

# 调试基础设施 Onboarding (强制)

> **所有 Agent 必读** - 2026-06-21 调试事故复盘发现：
> 其他 worktree Agent 仍在用手动 taskkill / 反复 Read backend.out / 直接 SQL 查询，
> **完全没有用 V1/V2/V2.2 调试基础设施工具**。
>
> 这导致 2026-06-21 调试过程出现 7 大痛点（详见末尾事故库）。

---

## 🚨 必须升级（3 个 worktree 都落后）

`agent_bootstrap.ps1 -Doctor` 显示当前有 3 个 worktree 分支：

| Worktree | 分支 | 当前 HEAD | 落后 main |
|----------|------|-----------|-----------|
| excel-to-diagram | main | **e5b1d14** | 0（最新）|
| agent-help-entry-worktree | feat/help-entry-p0 | 9c8ec75 | -4 commits |
| biz-msg-ux-v2-worktree | feat/biz-msg-ux-v2 | fb95257 | -4 commits |
| fix-import-msg-worktree | fix/import-msg-v1.2.30 | f7cb187 | **-4 commits**（最近调试的）|

**落后 4 个 commit** = 缺失所有 V1/V2/V2.2 调试工具。

---

## 🔧 升级步骤（每个 worktree 必做）

### 步骤 1：进入 worktree

```bash
cd d:/filework/<worktree-name>
```

### 步骤 2：Rebase 到 main

```bash
git fetch origin
git rebase main
# 或：git merge main
```

**冲突处理**：如果你的 commit 改了 `scripts/debug/`，解决冲突后保留两边修改。

### 步骤 3：验证升级

```bash
ls scripts/debug/                          # 应该看到 9 个工具
python scripts/debug/dashboard.py --brief  # 应该能用
```

### 步骤 4：测试关键工具

```bash
# 应该能跑
python scripts/debug/env/diagnose.py
python scripts/debug/log/extractor.py --pattern "WriteScope" --tail 5
python scripts/debug/inspect/code_map.py --topic "_check_write_scope" --type function
python scripts/debug/restart/restart_safe.py verify
```

---

## 🛠️ V1/V2/V2.2 调试工具完整清单（9 工具）

```
scripts/debug/
├── dashboard.py                            # V2.2: 调试控制台 + markdown 导出
├── env/
│   └── diagnose.py                         # V1: 综合诊断
├── inspect/
│   ├── user_context.py                     # V1: 用户上下文查询
│   ├── table_schema.py                     # V1: 表结构 + 字段映射检测
│   └── code_map.py                         # V2.2: 支持 import + reference 8 种类型
├── log/
│   ├── extractor.py                        # V1: 日志提取（关键字/级别/时间）
│   └── reader.py                           # V2: tail -f 实时跟踪
├── restart/
│   └── restart_safe.py                     # V1: 杀所有 waitress 后重启
├── verify/
│   └── run_interceptor_tests.sh            # V1: 一键验证
└── sessions/
    └── auto_record.py                      # V2: 调试会话自动记录
```

---

## 🚨 调试铁律 4（必读）

> **调试前必跑 6 步**：
> 1. `python scripts/debug/env/diagnose.py` - 综合诊断
> 2. `python scripts/debug/restart/restart_safe.py verify` - 后端状态
> 3. `python scripts/debug/log/extractor.py --level ERROR --tail 50` - 最近错误
> 4. `python scripts/debug/inspect/user_context.py <test_user>` - 用户上下文
> 5. `python scripts/debug/inspect/table_schema.py <表> --check-code-fields` - 字段映射
> 6. `git status --short | wc -l` - 工作树文件数（必须 ≤ 5）
>
> **调试中禁止 5 件事**：
> - ❌ 手动 `taskkill /F /IM pythonw.exe`（用 restart_safe.py）
> - ❌ `git diff > file.patch`（用 Read 工具）
> - ❌ `echo > file.txt`（用 Write 工具）
> - ❌ 反复 Read 整个 backend.out（用 extractor.py --pattern X）
> - ❌ 反复查 user_roles（用 user_context.py）
>
> **调试后必做 5 件事**：
> - ✅ `bash scripts/debug/verify/run_interceptor_tests.sh`
> - ✅ 清理 `# [DEBUG]` 代码
> - ✅ `python scripts/check_fix_completeness.py`
> - ✅ 写 `.trae/debug/sessions/*.yaml`
> - ✅ `python scripts/decision_log.py violate --pm-authorized`

---

## 📚 完整规范文档

- [.trae/rules/debug-infrastructure-v20260621.md](./debug-infrastructure-v20260621.md) - 完整规范
- [d:\filework\.trae\rules\debug-infrastructure-v20260621.md](file:///d:/filework/.trae/rules/debug-infrastructure-v20260621.md) - 全局同步版
- [d:\filework\.trae\rules\SESSION_REMINDER.md](file:///d:/filework/.trae/rules/SESSION_REMINDER.md) - 铁律 4

---

## 🔍 调试事故库（2026-06-21）

**不升级的后果**（最近调试过程的 7 大痛点）：

| 事故 | 描述 | V2.2 解决方案 |
|------|------|--------------|
| **D-001** | service_module 被误拦（反复查 user_roles）| `user_context.py` |
| **D-002** | 字段映射错误（反复 3 轮修复）| `table_schema.py --check-code-fields` |
| **D-003** | 旧 python.exe 进程残留 | `restart_safe.py restart` |
| **D-004** | 代码修改不生效（反复重启）| `debug_backend.py check` + `verify_backend_owner.py` |
| **D-005** | ActionResult 多处定义不一致 | `code_map.py --type reference` |
| **D-006** | flask.g RuntimeError 静默吞错 | （V3 待实施）|
| **D-007** | 调试过程没进度反馈 | （V3 待实施）|

**不升级 = 继续重复这些事故**！

---

## ⚠️ 例外情况（无法 rebase 时）

如果你的分支跟 main 有大量冲突，**暂不能 rebase**，则：

### 方案 A：Cherry-pick V2.2 commit

```bash
cd d:/filework/<worktree-name>
# 备份当前未提交修改
git stash
# Cherry-pick V1+V2+V2.2 三个 commit
git cherry-pick 5b38ce3 6d0e08e e5b1d14
# 如果失败，手动从 main 复制 scripts/debug/ 整个目录
cp -r ../excel-to-diagram/scripts/debug/ scripts/
# 还原备份
git stash pop
```

### 方案 B：合并 main（不 rebase）

```bash
git fetch origin
git merge main --no-ff
# 处理冲突
```

### 方案 C：手动同步脚本目录

```bash
# 复制 main 分支的 scripts/debug/ 到你的 worktree
cd d:/filework/<worktree-name>
rsync -av --exclude='__pycache__' \
  ../excel-to-diagram/scripts/debug/ \
  scripts/debug/
```

---

## 📋 升级检查清单

升级完后，对照这个清单确认：

- [ ] worktree HEAD 不再落后 main（`git log --oneline HEAD..main` 应该为空）
- [ ] `scripts/debug/` 目录有 9 个工具文件
- [ ] `python scripts/debug/dashboard.py --brief` 运行成功
- [ ] `python scripts/debug/env/diagnose.py` 返回 0 或 1（不是异常）
- [ ] `python scripts/debug/restart/restart_safe.py verify` 能跑
- [ ] `.trae/debug/sessions/` 目录存在
- [ ] 已读 `.trae/rules/debug-infrastructure-v20260621.md`

---

## 🤝 升级后的协作建议

1. **调试会话记录**：用 `python scripts/debug/sessions/auto_record.py start --agent <your-name>`
2. **dashboard 监控**：调试时开 `python scripts/debug/dashboard.py monitor --interval 30`
3. **问题反馈**：发现问题就改 commit，加 V3 工具
4. **保持同步**：定期 `git fetch origin && git rebase main`

---

## 📜 版本历史

| 版本 | 日期 | 主要内容 |
|------|------|----------|
| V1 | 2026-06-21 | 5 工具 + 1 规范（5b38ce3）|
| V2 | 2026-06-21 | + dashboard + tail -f + auto_record + SESSION_REMINDER（6d0e08e）|
| V2.2 | 2026-06-21 | + dashboard export + code_map imports/references（e5b1d14）|
| V3 | 2026-06-21 | + check_silent_exceptions + check_class_consistency（待提交）|

---

_本文件由元反馈建立（2026-06-21），目的是让所有 worktree Agent 立即升级到最新调试工具链_