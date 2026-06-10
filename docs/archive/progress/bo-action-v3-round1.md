# BO Action v3 重构 — Round 1 进度存档

> **日期**: 2026-06-05
> **分支**: `feature/bo-action-v3`（基于 `feature/unified-query-facade` 切出）
> **状态**: Round 1 完成，Round 2 因服务重启拦截暂停
> **下一轮**: 等待 chrome 进程结束后 `service_manager.ps1 restart`，或确认可强制 restart

---

## ✅ Round 1 已完成 (后端基础设施 3 步)

### 新建文件

| 文件 | 行数 | 状态 |
|------|:---:|:---:|
| [meta/core/bo_action_registry.py](file:///d:/filework/excel-to-diagram/meta/core/bo_action_registry.py) | 154 | ✅ 语法 + smoke test 通过 |
| [meta/api/bo_action_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py) | 128 | ✅ 语法通过 |
| [meta/core/app_builder.py](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py) | +2 行 | ✅ import + register 已添加 |

### 验证结果

```
$ python -c "import ast; ast.parse(...)"
OK: meta\core\bo_action_registry.py
OK: meta\api\bo_action_api.py
OK: meta\core\app_builder.py

$ python -c "from meta.core.bo_action_registry import bo_action_registry; ..."
OK: import bo_action_registry
  list_ids (initial): []
  list_ids (after register): ['test.echo']
  call result: {'success': True, 'data': {'echo': 42}, 'message': 'test ok'}
  list_ids (after clear): []
OK: bo_action_registry smoke test passed
```

### 业务影响

- ✅ **现有代码零影响**（3 个新文件 + 1 个文件 +2 行 import/register）
- ✅ **新 endpoint 尚未激活**（后端 Flask 进程未重启）
- ✅ **可安全回滚**：`git checkout feature/unified-query-facade -- meta/core/app_builder.py` + 删除两个新文件

---

## ⚠️ Round 2 状态：被 service_manager.ps1 安全拦截

### 现象
- 试图 `service_manager.ps1 restart` 让新代码生效
- 脚本**正确拒绝**重启：检测到 20 个 chrome 进程（活跃，CPU > 0）
- 脚本提示用 `restart -Force` 强制覆盖（**未执行**）

### 当前服务状态
```
Frontend (Vite)  : RUNNING (port=3004, pid=21116, since=2026-06-05T12:08:27Z)
Backend (Python) : RUNNING (port=3010, pid=23588, since=2026-06-05T10:58:12Z)
Watchdog         : RUNNING (PID=22404)
```
- Backend 是 **10:58:12 启动**，不含我新加的 `/api/v2/action/...` endpoint
- 新代码**已写入磁盘，下次 restart 时激活**

---

## 🚧 Round 3+ 计划（未实施）

| 步骤 | 任务 | 估计工时 |
|------|------|:---:|
| 3 | 后端实现 `meta/services/actions/user_authenticate.py` | 30 min |
| 4 | 后端在 `app_builder.py` 启动时注册 Action | 10 min |
| 5 | 重启后端 + curl 验证 `/api/v2/action/_health` | 10 min |
| 6 | curl 验证 `/api/v2/action/user.authenticate` | 10 min |
| 7 | 前端实现 `src/composables/useBoAction.js` | 20 min |
| 8 | 前端 `utils/api.js` 加 `actionPost` / `actionGet` 工厂 | 10 min |
| 9 | 前端 `main.js` 不必修改（按需） | 5 min |
| 10 | 端到端验证（authStore 调用 Action） | 20 min |
| 11 | 单测 + DB 完整性 | 30 min |

**总估时**: ~2.5 小时

---

## 🔑 关键决策点（需用户确认）

### 决策 A: 何时 restart 后端？
- 选项 1: 等 chrome 进程自然结束（5-30 分钟）
- 选项 2: `service_manager.ps1 restart -Force`（⚠️ 风险：可能误杀其他 Agent 测试/开发者浏览器）
- 选项 3: 仅在 `worktree` 隔离环境操作（需要先开 worktree）

### 决策 B: 是否实现 user.authenticate 作为首个业务 Action？
- 选项 1: 先做 user.authenticate（推荐 - 验证最小可运行 demo）
- 选项 2: 跳过 user.authenticate，先做 useBoAction.js + utils/api.js 改造
- 选项 3: 跳过前端，先做更多后端 Action（condition.evaluate, batch_save）

### 决策 C: 当前进度是否需要保留？
- 选项 1: 保留（不删新文件，等下次启动会话）
- 选项 2: 立即回滚（`git checkout` + 删除新文件）
- 选项 3: 暂存进度（写到文件，方便回溯）

---

## 📂 文件清单（按修改时间倒序）

| 路径 | 状态 | 大小 |
|------|------|------|
| meta/api/bo_action_api.py | 新建 | 4.0 KB |
| meta/core/bo_action_registry.py | 新建 | 4.7 KB |
| meta/core/app_builder.py | 修改 +2 行 | +0.1 KB |

---

## 🔗 相关文档

- [spec-phase1-p0-detailed-design.md v3.0.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-phase1-p0-detailed-design.md) — v3 BO Action 详细设计
- [spec-phase1-safe-execution.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-phase1-safe-execution.md) — 安全执行规范
- [service-management-rules.md](file:///d:/filework/excel-to-diagram/.trae/rules/service-management-rules.md) — 服务管理铁律

---

## 变更记录

| 版本 | 日期 | 变更 | 作者 |
|:---:|------|------|------|
| 1.0.0 | 2026-06-05 | Round 1 完成 + 暂停存档 | AI Agent (Trae) |
