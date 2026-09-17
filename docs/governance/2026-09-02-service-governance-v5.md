---
title: 服务治理 v5.0 总结
date: 2026-09-02
status: 完成
author: AI Assistant
related: 2026-09-01-worktree-cleanup.md, 2026-09-02-rules-qc-round2.md
---

# 服务治理 v5.0 总结

> **背景**：代码库统一到 v4.0 主仓工作流后，用户提出"服务器的使用和管理是否也需要优化"。本文记录方案 A（激进瘦身）的实施过程与成果。

---

## 1. 治理前现状

| 问题 | 严重度 | 证据 |
|------|--------|------|
| `scripts/` 临时文件污染 | 🔴 严重 | 100+ `_xxx.py` / `_xxx.txt` / `_xxx.log` |
| 端口信息散落多处 | 🟡 中 | 文档/规则/代码多处硬编码 3004/3010 |
| AI 调试文件无处归放 | 🔴 严重 | 仓库根 100+ `_xxx.*` |
| 清理工具缺失 | 🟡 中 | 没有 `reset_workspace.ps1` |
| watchdog 碎片化 | 🟡 中 | `watchdog.ps1` / `monitor_v22.py` / `monitor_live.py` 等多版本 |

## 2. v5.0 治理方案

### 2.1 新增 3 个核心文件

| 文件 | 作用 |
|------|------|
| `.ports.yaml` | **所有端口分配单一真相源**（dev/staging/prod 三套） |
| `.tmp/` | **AI 临时文件统一目录**（替代 scripts/ 与 root 的散落） |
| `scripts/reset_workspace.ps1` | **自动清理工具**（7 天阈值 + Force 模式） |

### 2.2 新增规范

| 文件 | 作用 |
|------|------|
| `.trae/rules/service-management-v5.md` | 服务治理 v5.0 规范（alwaysApply=true） |

### 2.3 .gitignore 扩展

新增规则：
```
.tmp/                                    # 临时目录统一
/scripts/_*.py / _*.txt / _*.log ...    # scripts/ 临时文件
/scripts/_tmp_*                          # scripts/_tmp_* 系列
/scripts/logs/_*.log / _*.txt           # scripts/logs/ 临时日志
```

## 3. 治理成果

### 3.1 清理数量

| 项目 | 数量 | 大小 |
|------|------|------|
| `.tmp/` 临时文件 | 12 | ~530 KB |
| `scripts/_*.py` | 27 | ~50 KB |
| `scripts/_*.log` | 6 | ~210 KB |
| `scripts/_tmp_*` | 1 | ~0.4 KB |
| 仓库根 `_*.py` | 11 | ~25 KB |
| 仓库根 `_*.txt` | 17 | ~80 KB |
| 仓库根 `_*.log` | 48 | ~1.4 MB |
| 仓库根 `_*.png` | 2 | ~130 KB |
| **总计** | **181** | **~2.3 MB** |

清理结果：**179 删除 / 2 失败（已被自动删除）**

### 3.2 治理前后对比

| 维度 | 治理前 | 治理后 |
|------|--------|--------|
| `scripts/` 临时文件 | 100+ | 0 |
| 仓库根临时文件 | 80+ | 0 |
| 端口真相源 | 散落 4 处 | **.ports.yaml 单一** |
| 清理工具 | 无 | **reset_workspace.ps1** |
| 临时文件目录 | 散落 | **.tmp/ 统一** |

## 4. 后续建议

### 4.1 PM 每周任务

```powershell
# 每周一次清理（保留活跃会话临时文件）
powershell -File scripts/reset_workspace.ps1 -Clean

# 每月一次彻底清理（仅维护窗口执行）
powershell -File scripts/reset_workspace.ps1 -Clean -Force
```

### 4.2 AI 智能体铁律（v5.0）

1. **端口查询**：永远从 `.ports.yaml` 读取，禁止硬编码
2. **临时文件**：必须放 `.tmp/`，禁止散落到 scripts/ 或 root
3. **服务启动**：必须用 `service_manager.ps1`，禁止直接 `npm run dev`
4. **重启协调**：重启前检查 Playwright/浏览器进程

### 4.3 待办（未来 Phase）

- [ ] 端口 YAML 自动同步到 service_manager.ps1（消除双源）
- [ ] watchdog 整合（目前 watchdog.ps1 与多个 monitor_*.py 并存）
- [ ] .ports.yaml CI 校验（启动时检查端口分配冲突）

## 5. CHANGELOG

| 日期 | 变更 | 评分 |
|------|------|------|
| 2026-09-02 | v5.0 服务治理完成 | **0 个临时文件** |
| 2026-09-02 | 治理前 | **181 个临时文件** |