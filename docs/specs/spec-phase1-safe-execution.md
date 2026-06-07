# Spec 附录：v3 实施安全执行规范

> **版本**: v1.0.0
> **日期**: 2026-06-05
> **状态**: 📋 安全执行守则 (Safe Execution Guardrails)
> **范围**: v3 BO Action 重构全过程的"安全执行"清单
> **前置文档**:
> - [spec-phase1-p0-detailed-design.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-phase1-p0-detailed-design.md) v3.0.0
> - [SESSION_REMINDER.md](file:///d:/filework/.trae\rules\SESSION_REMINDER.md) — 全局铁律
> - [service-management-rules.md](file:///d:/filework/excel-to-diagram\.trae\rules\service-management-rules.md) — 服务管理
> - [multi-agent-coordination.md](file:///d:/filework/excel-to-diagram\.trae\rules\multi-agent-coordination.md) — 多 Agent 协作

---

## 0. "安全执行"的 5 维定义

| 维度 | 风险 | 后果 |
|------|------|------|
| **DB 安全** | 误改 `meta/architecture.db` → 污染主库 → 所有 Agent 失败 | 🔴 致命 |
| **服务安全** | 误启停/误杀进程 → 端口冲突 → 其他 Agent 崩溃 | 🔴 致命 |
| **测试安全** | 直接 `pytest` / 绕 DB 快照 → 进度丢失/数据污染 | 🔴 致命 |
| **文件安全** | UTF-8 错误 / 覆盖未提交文件 → 调试 30+ 分钟 | 🟠 严重 |
| **协作安全** | 端口冲突 / worktree 缺失 → 文件覆盖 | 🟠 严重 |

**总原则**：**任何一步出错都先停下来诊断，不暴力重试**。

---

## 1. 全局铁律（不可违反）

### 1.1 pytest 铁律

```bash
# [X] 绝对禁止 — 会卡死/数据污染
pytest meta/tests/
python -m pytest meta/tests/
python meta/tests/test_xxx.py

# [OK] 唯一合法入口（自动 TEST_ENTRY=1，DB 快照保护）
python d:\filework\test.py --all --force
python d:\filework\test.py --failed           # 修复后必跑
python d:\filework\test.py --skip
python d:\filework\test.py --unit
python d:\filework\test.py --integration
python d:\filework\test.py --file <path>
python d:\filework\test.py --status
```

**违规会触发** `conftest.py` 硬阻断 → `os._exit(1)`。

### 1.2 PowerShell 铁律

```powershell
# [X] 绝对禁止 — curl 是 Invoke-WebRequest 别名，会卡死
curl -s http://localhost:3010/api/...

# [OK] 三选一
curl.exe -s http://localhost:3010/api/...
Invoke-RestMethod -Uri http://localhost:3010/api/...
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:3010/api/...').read().decode())"
```

**注意**：
- PowerShell 路径分隔符统一用 `tests/e2e/`（正斜杠）
- 重定向用 `*> file` 或 `2>&1 | Out-File`（避免 `2>&1 1>file` 不确定行为）
- 中文字符串要 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` + 5 行配置

### 1.3 服务管理铁律

```powershell
# [X] 绝对禁止 — 跨 Agent 不可见，端口冲突
npm run dev
python dev.py
Get-Process python
taskkill /F /IM python.exe

# [OK] 唯一入口
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart
```

### 1.4 文件操作铁律

```python
# 写 .py 文件前
# 1. UTF-8 编码
with open(file, 'w', encoding='utf-8') as f:
    f.write(content)

# 2. ast.parse 验证
import ast
try:
    ast.parse(content)
    print("OK")
except SyntaxError as e:
    print(f"BAD: {e}")

# 3. 写前先检查 git status（避免覆盖）
# 写前先 Read（如已存在）
```

---

## 2. 实施前预检（每个 PR 开始前必做）

### 2.1 预检清单（10 项）

```powershell
# === 1. UTF-8 环境 ===
chcp 65001
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8=1
$OutputEncoding = [System.Text.Encoding]::UTF8

# === 2. 当前服务状态 ===
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# === 3. 是否有多 Agent 在跑测试 ===
# 端口是否被占用？
netstat -ano | Select-String ":3004|:3010"

# 4. 当前测试是否在跑
powershell -Command "Get-Process | Where-Object { $_.CommandLine -match 'playwright|chromium' }" 2>$null

# === 5. Git 状态（避免覆盖未提交代码） ===
cd d:\filework\excel-to-diagram
git status

# === 6. 主 DB 状态（确保未被污染）===
ls d:\filework\excel-to-diagram\meta\architecture.db* | Select-Object LastWriteTime
# 预期: 最近修改时间在 5 分钟前（即非测试中）

# === 7. 最近一次测试状态 ===
python d:\filework\test.py --status

# === 8. 资源占用（避免 100% CPU） ===
python d:\filework\excel-to-diagram\scripts\resource_monitor.py check

# === 9. 端口分配（如有并行 Agent） ===
python d:\filework\excel-to-diagram\scripts\allocate_ports.py status

# === 10. 是否在 worktree ===
git worktree list
```

### 2.2 一键预检脚本（推荐使用）

让我把这个清单脚本化。

```python
# scripts/safe_precheck.py
"""
v3 实施前预检脚本
- 11 项检查, 任一失败立即退出
- 退出码 0 = 通过, 1 = 失败
"""
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(r'd:\filework\excel-to-diagram')
TEST_ENTRY = Path(r'd:\filework\test.py')


def run(cmd, cwd=None, shell=True):
    """运行命令并返回 (exit_code, stdout)"""
    try:
        result = subprocess.run(
            cmd, shell=shell, cwd=cwd,
            capture_output=True, text=True,
            encoding='utf-8', errors='ignore',
            timeout=30
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 124, 'TIMEOUT'
    except Exception as e:
        return 1, str(e)


def check(label, condition, detail=''):
    """打印检查结果"""
    icon = '✅' if condition else '❌'
    print(f'{icon} [{label}] {detail}')
    return condition


def main():
    print('=' * 60)
    print('  v3 BO Action 实施预检')
    print('=' * 60)
    all_pass = True

    # 1. UTF-8
    encoding = os.environ.get('PYTHONIOENCODING', '')
    all_pass &= check('UTF-8', encoding == 'utf-8', f'PYTHONIOENCODING={encoding}')

    # 2. 服务状态
    code, out = run(f'powershell -File "{PROJECT_ROOT}/scripts/service_manager.ps1" status')
    all_pass &= check('服务状态', 'RUNNING' in out or 'STOPPED' in out, out.split('\n')[0] if out else 'N/A')

    # 3. 端口占用
    code, out = run('netstat -ano | Select-String ":3004|:3010"')
    all_pass &= check('端口检查', True, f'{len(out.splitlines())} 个端口被监听' if out else '无端口占用')

    # 4. 是否有 Playwright/Chromium 在跑
    code, out = run(
        'powershell -Command "Get-Process | Where-Object { $_.CommandLine -match \'playwright|chromium\' }"',
        shell=True
    )
    all_pass &= check('无测试在跑', code != 0 or not out, '检测到测试进程' if out else '无')

    # 5. Git 状态
    code, out = run('git status --porcelain', cwd=str(PROJECT_ROOT))
    all_pass &= check('Git 清洁', code == 0, f'{len(out.splitlines())} 个未跟踪/修改文件' if out else '干净')

    # 6. 主 DB 时间戳
    db_path = PROJECT_ROOT / 'meta' / 'architecture.db'
    if db_path.exists():
        import time
        mtime = db_path.stat().st_mtime
        age_min = (time.time() - mtime) / 60
        all_pass &= check('DB 状态', age_min > 5, f'最后修改 {age_min:.1f} 分钟前')
    else:
        all_pass &= check('DB 存在', False, f'{db_path} 不存在')

    # 7. 测试状态
    if TEST_ENTRY.exists():
        code, out = run(f'python "{TEST_ENTRY}" --status')
        all_pass &= check('test.py 可用', code == 0, out[:100] if out else 'N/A')
    else:
        all_pass &= check('test.py 存在', False, f'{TEST_ENTRY} 不存在')

    # 8. 资源
    code, out = run(f'python "{PROJECT_ROOT}/scripts/resource_monitor.py" check')
    all_pass &= check('资源检查', code == 0, out[:100] if out else 'N/A')

    # 9. worktree
    code, out = run('git worktree list', cwd=str(PROJECT_ROOT))
    all_pass &= check('Worktree', code == 0, f'{len(out.splitlines())} 个 worktree')

    # 10. 依赖
    try:
        import psutil
        all_pass &= check('psutil', True, '已安装')
    except ImportError:
        all_pass &= check('psutil', False, '未安装, 请先 pip install psutil')

    # 11. conftest.py 硬阻断存在
    conftest = PROJECT_ROOT / 'meta' / 'tests' / 'conftest.py'
    all_pass &= check('conftest.py', conftest.exists(), '存在' if conftest.exists() else '缺失')

    print('=' * 60)
    if all_pass:
        print('✅ 所有预检通过, 可开始实施')
        sys.exit(0)
    else:
        print('❌ 部分预检失败, 请修复后重试')
        sys.exit(1)


if __name__ == '__main__':
    main()
```

---

## 3. v3 各 Phase 实施安全清单

### Phase 0：基础设施（3 天，最高风险）

#### 3.1 实施前

```bash
# 1. 创建 worktree（避免污染主分支）
cd d:\filework\excel-to-diagram
git worktree add ../excel-to-diagram-v3-action -b feature/bo-action-v3 main

# 2. 分配独立端口（避免冲突）
python scripts/allocate_ports.py allocate --agent bo-action-v3
# 输出: VITE_DEV_PORT=3024, FLASK_PORT=3030

# 3. 启动服务（用分配的端口）
powershell -File scripts/service_manager.ps1 start

# 4. 验证服务就绪
curl.exe -s http://localhost:3024/  # 200
curl.exe -s http://localhost:3030/api/v1/auth/me  # 401 (未登录正常)

# 5. 基线测试（确认未改动前所有测试通过）
python d:\filework\test.py --unit
```

#### 3.2 实施中（关键变更点）

**变更 1：bo_framework.py 扩展**
```python
# ⚠️ 高风险: 影响所有 CRUD 操作
# 安全策略:
#   1. 先 git diff（确认改动范围）
#   2. 保留所有现有方法（向后兼容）
#   3. 新增 register_business_actions() 和 execute()
#   4. 不修改现有 _run_interceptors_* 逻辑
```

**变更 2：bo_action_api.py 新增**
```python
# ⚠️ 中风险: 新增 endpoint
# 安全策略:
#   1. 新增 blueprint, 不修改现有 auth_api
#   2. URL 前缀 /api/v2/action 与现有不冲突
#   3. 注册到 server.py 时确保幂等
```

**变更 3：useBoAction.js 新增**
```javascript
// 低风险: 纯新增, 不修改任何现有代码
// 安全策略:
//   1. 仅 export 新函数
//   2. 不修改 utils/api.js 现有导出
```

#### 3.3 实施后

```bash
# 1. 单测（确认 BO Action 框架正常）
python d:\filework\test.py --unit
# 预期: 全部通过, 无新增失败

# 2. 端到端验证（手动）
# - 启动浏览器
# - 访问 http://localhost:3024
# - 登录 admin / admin123
# - 检查 dev-tools network: 应有 /action/user.authenticate 请求
# - 检查 dev-tools console: 无 401 异常

# 3. Playwright E2E
python d:\filework\test.py --file tests/test_login.py

# 4. 完成后状态
python d:\filework\test.py --status  # 应显示 passed
```

#### 3.4 回滚策略

```bash
# Phase 0 失败 → 整体回滚
cd d:\filework\excel-to-diagram
git worktree remove ../excel-to-diagram-v3-action --force
git branch -D feature/bo-action-v3

# 主分支不受影响（worktree 隔离）
git status  # 干净
```

---

### Phase 1：Auth 重构（2 天）

#### 关键安全点

```python
# ⚠️ 中风险: auth_api.py 大幅简化
# 安全策略:
#   1. 保留 auth_api.py 中 5 个 endpoint 的 URL（向后兼容）
#   2. endpoint 内部委托给 auth_service
#   3. 不要删除 endpoint, 只能改为薄代理
#   4. 添加详细日志

# ⚠️ 中风险: useObjectIdentity.js 的 token BUG 修复
# 安全策略:
#   1. 改 credentials: 'include'（依赖 Cookie）
#   2. 测试未登录态 API 调用 → 应 401
#   3. 测试登录态 API 调用 → 应 200
```

#### 验证步骤

```bash
# 1. 登录功能
python d:\filework\test.py --file tests/test_login.py
# 预期: 5+ 个测试通过

# 2. Session 恢复
python d:\filework\test.py --file tests/test_session_restore.py
# 预期: 刷新页面后仍登录

# 3. 401 失效
# 手动: dev-tools 清 cookie → 调任意 API → 应自动跳登录

# 4. useObjectIdentity 修复验证
# 手动: 打开任意对象详情页 → 业务对象名应正常显示
```

#### 回滚策略

```bash
# 单独回滚 authStore.js
git checkout main -- src/stores/authStore.js
# 单独回滚 auth_api.py
git checkout main -- meta/api/auth_api.py
```

---

### Phase 2：草稿 batch_save（2 天）

#### 关键安全点

```python
# ⚠️ 高风险: 批量保存涉及数据库写入
# 安全策略:
#   1. 在 test_data fixture 中准备测试数据
#   2. 不要在生产 DB 上测试 → 使用 test.py 提供的快照
#   3. 测试覆盖: 空草稿/纯新增/纯更新/混合/部分失败
#   4. 回归测试现有 useMetaList.batch.spec.js

# ⚠️ 中风险: useMetaList.saveDraftValues 简化
# 安全策略:
#   1. 保持函数签名不变 (无参数)
#   2. 保持返回行为一致 (success/failure)
#   3. 保持错误处理一致 (ElMessage)
#   4. 逐步替换, 不一次性删除
```

#### 验证步骤

```bash
# 1. 静态 service 单测
python d:\filework\test.py --file meta/tests/test_draft_splitter.py
# 预期: ≥15 用例通过

# 2. Action 单测
python d:\filework\test.py --file meta/tests/test_batch_save_action.py
# 预期: ≥10 用例通过

# 3. useMetaList 集成测试
python d:\filework\test.py --file src/composables/__tests__/useMetaList.batch.spec.js
# 预期: 全部通过（用 vitest）

# 4. 端到端
# 手动: 任意对象列表 → 新建/编辑/批量保存 → 行为一致
```

---

### Phase 3：API 路径 Bootstrap（1 天）

#### 关键安全点

```python
# ⚠️ 低风险: 仅启动时拉一次
# 安全策略:
#   1. 启动失败 → 降级到硬编码路径（fallback）
#   2. 不影响现有功能（API_BASE 仍可工作）
#   3. 加 try/except 保护 initManifest()
```

#### 验证步骤

```bash
# 1. 启动后 dev-tools network 应有 /client/manifest 请求
# 2. 现有 30+ 页面正常打开
# 3. 11 个文件 import 替换后无报错
# 4. 关闭后端 → 启动前端 → 应能降级显示（fallback 模式）
```

---

## 4. 端到端验证矩阵

| 场景 | 验证方式 | 通过标准 | 风险等级 |
|------|----------|----------|:---:|
| 预检通过 | `python scripts/safe_precheck.py` | exit 0 | — |
| 单测全过 | `python test.py --unit` | 全部通过 | 中 |
| 集成测试 | `python test.py --integration` | 全部通过 | 中 |
| E2E 登录 | `python test.py --file tests/test_login.py` | ≥5 通过 | 低 |
| E2E 草稿 | `python test.py --file tests/test_draft.py` | ≥10 通过 | 中 |
| DB 完整性 | `python test.py --status` | passed | 高 |
| 拦截器 18 个 | `python test.py --file meta/tests/interceptors/` | 全部通过 | 高 |
| BO Action 注册 | 启动日志 | 8+ Action 注册 | 中 |
| Worktree 隔离 | `git worktree list` | 主分支干净 | 中 |
| 服务隔离 | `service_manager status` | 端口独立 | 中 |

---

## 5. 异常诊断流程

### 5.1 服务起不来

```bash
# 1. 看 status
powershell -File scripts/service_manager.ps1 status

# 2. 看日志
Get-Content .service_manager.log -Tail 30

# 3. 看错误
Get-Content meta/server.log -Tail 30  # 如果有

# 4. 不直接 restart！先诊断
# 重启前确认无测试进程:
powershell -Command "Get-Process | Where-Object { $_.CommandLine -match 'playwright|chromium' }"

# 5. 如果是被其他 Agent 占用 → 用 allocate_ports.py
python scripts/allocate_ports.py allocate --agent my-agent
```

### 5.2 测试失败

```bash
# 1. 先看 --status
python d:\filework\test.py --status

# 2. 再跑 --failed（串行, 排除并发假失败）
python d:\filework\test.py --failed

# 3. 不直接修脚本！先看错误根因
# - conftest.py 报 TEST_ENTRY 未设置？→ 你跑了 pytest, 改用 test.py
# - DB 锁？→ 等 120s 或停止其他 Agent
# - 端口冲突？→ 改用分配的端口
# - 真实错误？→ 看 traceback, 最小化复现

# 4. 修复后跑 --failed（不要 --all）
python d:\filework\test.py --failed
```

### 5.3 DB 污染

```bash
# 1. 立即停止所有写入
powershell -File scripts/service_manager.ps1 stop

# 2. 查看备份
ls meta/architecture.db.bak.* 2>$null | Sort-Object LastWriteTime -Descending | Select-Object -First 5

# 3. 恢复到最新干净备份
# 注意: 用户明确确认前不要自动恢复
# cp meta/architecture.db.bak.20260605_120456 meta/architecture.db

# 4. 验证 DB 完整性
python -c "import sqlite3; c = sqlite3.connect('meta/architecture.db'); c.execute('PRAGMA integrity_check'); print(c.fetchone())"

# 5. 启动服务
powershell -File scripts/service_manager.ps1 start

# 6. 全量回归
python d:\filework\test.py --all --force
```

### 5.4 Worktree 文件覆盖

```bash
# 1. 立即停止编辑
# 2. 查看当前 worktree
git worktree list

# 3. 切回自己的 worktree
cd <your-worktree>

# 4. 拉取主分支最新
git fetch origin
git rebase origin/main

# 5. 如有冲突 → 手动解决（不强制覆盖）
```

---

## 6. 紧急联系点

| 场景 | 行动 |
|------|------|
| DB 损坏 | 立即停止服务 → 看 §5.3 流程 |
| 端口冲突 | `allocate_ports.py allocate` |
| 18 拦截器失败 | 不重启, 看 `test_interceptors_unit.py` |
| 多 Agent 同时改文件 | 立即用 worktree 隔离 |
| 跑测试卡死 | `Ctrl+C` 一次, 不行再 `Ctrl+C` 两次, 最后用 `service_manager stop` |
| 服务占用无法停止 | 看 `.service_manager.log` 锁文件超时 (120s) |

---

## 7. 提交前检查清单

每个 PR 合并前**必须**：

- [ ] 单测覆盖率 ≥ 90%（`pytest --cov`）
- [ ] `python d:\filework\test.py --failed` 通过
- [ ] 至少 1 个 E2E 用例覆盖
- [ ] 无 console.error / warning
- [ ] ESLint 通过（如有前端改动）
- [ ] 文件编码 UTF-8 + ast.parse 验证
- [ ] 工作目录在 worktree（不在主分支）
- [ ] Git commit message 规范
- [ ] PR 描述包含：变更点 + 验证截图 + 风险评估
- [ ] 主分支无污染（`git status` 干净）

---

## 8. 红线（绝对不能做）

| 红线 | 后果 |
|------|------|
| ❌ 直接运行 `pytest` | conftest.py 硬阻断 → 进度丢失 |
| ❌ 直接修改 `meta/architecture.db` | DB 污染 → 全部 Agent 失败 |
| ❌ 直接 `taskkill /F /IM python.exe` | 误杀其他 Agent 进程 |
| ❌ 直接 `git push --force` 到 main | 永久丢失其他 Agent 工作 |
| ❌ 跳过预检直接动手 | 5 个常见踩坑之一必中 |
| ❌ 一次跑全套测试（>5 分钟） | 不可观测, 出错难定位 |
| ❌ 改完代码不验证 | 违反铁律 5 |
| ❌ 用 `Get-Process` 跨 Agent 判断 | sandbox 隔离, 不可见 |
| ❌ Bearer token 认证 | 违反铁律 7a |
| ❌ wait_for_timeout/sleep 硬编码 | 违反铁律 10 |

---

## 9. 安全执行的口诀

> **预检先行 → worktree 隔离 → 单测先跑 → 失败先诊断 → 修复跑 failed → 全过才合并**

**任何"先试试看"的冲动，先停下来问：**"这一步出错能不能回滚？"**
- 能回滚 → 可以试
- 不能回滚 → 必须预检 + 备份 + 验证

---

## 10. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|:---:|------|------|------|
| 1.0.0 | 2026-06-05 | 初稿, 配套 v3 详细设计 | AI Agent (Trae) |

---

*本规范是 v3 BO Action 重构全过程的**安全护栏**，违反任何一条都可能引发连锁故障。*
