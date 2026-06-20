# 审计日志 P1 + P2 细化优化方案

> **生成时间**：2026-06-20 17:45 (Asia/Shanghai)
> **依据规范**：
> - `.trae/rules/SESSION_REMINDER.md`（18 铁律 + pytest 禁用）
> - `.trae/rules/multi-agent-coordination.md` v3.24（worktree + L5 沙箱）
> - `.trae/rules/audit-compliance.md`（审计写入必须走 AuditInterceptor）
> - `.trae/rules/meta-model-schema-sync.md`（YAML/Schema 同步）
> - `.trae/rules/test_rules.md` + `test-data-rules.md`（测试数据隔离）
>
> **目标**：彻底闭环 P1（残留 12 条 `Admin (admin)`）+ P2（tx_id 覆盖率从 7.1% 提升到 95%+）

---

## 〇、规范前置检查（必读）

| 规范 | 关键要求 | 违规后果 |
|------|---------|---------|
| [SESSION_REMINDER.md](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md) | 禁止 `pytest`；必须用 `python d:\filework\test.py`；禁止 `npm run dev`；必须 `service_manager.ps1` | 进度丢失、DB 污染 |
| [multi-agent-coordination.md](file:///d:/filework/excel-to-diagram/.trae/rules/multi-agent-coordination.md) v3.24 | L1 必须 worktree；L5 沙箱检测；PM 授权例外 | 其他 Agent 工作丢失 |
| [audit-compliance.md](file:///d:/filework/excel-to-diagram/.trae/rules/audit-compliance.md) §1.3 | **必须用 `AuditInterceptor`**；**禁止直接 INSERT audit_logs** | 违反合规 ERROR 级 |
| [meta-model-schema-sync.md](file:///d:/filework/excel-to-diagram/.trae/rules/meta-model-schema-sync.md) | YAML 变更需 `--diff` → `--dry-run` → `--execute` 三步 | DB schema 不一致 |

**Worktree 准备（必做）**：

```powershell
# L5 沙箱检测
$sandboxTest = 'sandbox_' + (Get-Date -Format 'HHmmss') + '.txt'
Set-Content "d:\filework\$sandboxTest" "test" -Encoding UTF8
if (Test-Path "d:\filework\$sandboxTest") {
    Remove-Item "d:\filework\$sandboxTest"
    Write-Host "[L5] 沙箱 OK，可写入" -ForegroundColor Green
} else {
    Write-Host "[L5] 沙箱隔离，必须用脚本委托模式" -ForegroundColor Red
}

# L1 创建独立 worktree
powershell -File scripts/agent_bootstrap.ps1 -AgentName audit-fix -Port 3011
cd ../audit-fix-worktree

# L4 读状态文件
Get-Content d:\filework\.agent-status.json | Select-String audit-fix

# 写 spec.md
cp d:\filework\spec_template.md .\spec.md
# 编辑: 目标/白名单/黑名单/完成标准
```

---

## 一、P1 优化：彻底消除 `Admin (admin)` 残留格式

### 1.1 根因分析（已定位）

调查发现 **2 处代码仍在使用旧格式** `f"{display} ({username})"`：

#### [BUG #1] `meta/services/action_handlers.py:228-231`

```python
# ❌ 现状
user_id = current_user.get('user_id') or current_user.get('id')
display = current_user.get('display_name') or ''
username = current_user.get('username') or ''
if display and username and display != username:
    user_name = f"{display} ({username}")  # ← 罪魁祸首
else:
    user_name = display or username or ''
```

**触发链路**：
```
POST /api/v2/bo/business_object
  → bo_framework.create()
    → _do_create() [action_executor.py:1242]  ← 这条路径 D.2 已修
      → 业务创建完成后
    → trigger: clear_other_current_versions (version.yaml:497)
      → action_handlers.py:228-231 ← 这里是旧格式
      → set_user_context(user_name="Admin (admin)")  ← 污染了 BO context
    → 回到 BO create 流程？
```

> ⚠️ **更严重的真相**：`clear_other_current_versions` 被注册为 **triggers: [before_update]**（version.yaml:575）。
> 当 **version.set_current** 被触发时，它先调用旧格式 `set_user_context`，**然后**调用 `bo_framework.update()` 更新其他 version 的 `is_current=false`。
> **这 4 条 audit_log 是被清除的其他 version 的更新日志**，不是当前 BO 的创建日志！

#### [BUG #2] `meta/api/_audit_helper.py:42-44`

```python
# ❌ 现状
def _audit_user_name() -> str:
    cu = getattr(g, 'current_user', None) or {}
    _display = cu.get('display_name') or ''
    _username = cu.get('username') or ''
    if _display and _username and _display != _username:
        return f"{_display} ({_username}")  # ← 同样的旧格式
    return _display or _username or ''
```

**调用方**：6 个 role/permission API（[bo_api.py:2767](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L2767), role_api.py:394/519, role_menu_api.py:714, role_dimension_scope_api.py:129/150, permission_rule_api.py:96, management_dimension_api.py:684）→ 每次角色/权限编辑都会写入错误的 user_name

### 1.2 修复方案

#### Phase 1.2.1：代码修复（白名单）

| 文件 | 行 | 修改 |
|------|---|------|
| [meta/services/action_handlers.py](file:///d:/filework/excel-to-diagram/meta/services/action_handlers.py) | 228-231 | 删除 `if display and username and display != username` 分支，统一改为 `user_name = display or username or ''` |
| [meta/api/_audit_helper.py](file:///d:/filework/excel-to-diagram/meta/api/_audit_helper.py) | 42-44 | 同上 |

**统一修复模板**：

```python
# [OK] 新规范: 统一只用 display_name, 不再拼接 "display (username)"
# 业务人员之前看到 "Admin (admin)" 不理解, 现在统一只用 display_name
# 见 audit-compliance.md §5.3 + spec_7_business_issues.md D.2
user_name = display or username or ''
```

#### Phase 1.2.2：添加断言守门（防止再次出现）

在 `meta/core/audit_constants.py:normalize_user_name()` 里已经处理，但 `_audit_helper` 没有用这个函数。**应统一入口**：

```python
# meta/api/_audit_helper.py 修改
from meta.core.audit_constants import normalize_user_name

def _audit_user_name() -> str:
    cu = getattr(g, 'current_user', None) or {}
    return normalize_user_name(
        display_name=cu.get('display_name'),
        username=cu.get('username')
    )
```

#### Phase 1.2.3：存量数据修复脚本（幂等）

**新文件**：`scripts/fix_audit_admin_parentheses.py`

```python
"""修复 audit_logs.user_name 中残留的 "Admin (admin)" 格式"""
import sqlite3
import re
import sys

DB = "meta/architecture.db"

def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # 找出所有 "display (username)" 格式 (display 和 username 都不为空且不等)
    pattern = re.compile(r'^(.+?)\s*\(([^)]+)\)\s*$')
    c.execute("""
        SELECT id, user_name FROM audit_logs
        WHERE user_name LIKE '%(%' AND user_name LIKE '%)%'
    """)
    rows = c.fetchall()

    fixed = 0
    for log_id, old_name in rows:
        m = pattern.match(old_name)
        if m and m.group(1).strip() and m.group(2).strip() and m.group(1).strip() != m.group(2).strip():
            new_name = m.group(1).strip()  # 只保留 display_name
            c.execute("UPDATE audit_logs SET user_name = ? WHERE id = ?", (new_name, log_id))
            fixed += 1
            print(f"  id={log_id}: {old_name!r} -> {new_name!r}")

    conn.commit()
    print(f"\n[DONE] Fixed {fixed}/{len(rows)} records")
    conn.close()
    return 0 if fixed > 0 else 0

if __name__ == '__main__':
    sys.exit(main())
```

**预期结果**：修复 12 条残留 + 任何历史数据。

#### Phase 1.2.4：测试验证

```powershell
# 跑 unit test (使用 test.py 入口)
python d:\filework\test.py --single meta/tests/test_audit_user_name_normalization.py

# 写新测试: meta/tests/test_action_handlers_user_name.py
# - 验证 clear_other_current_versions 不再产生 "Admin (admin)"
# - 验证 _audit_user_name 不再返回 "Admin (admin)"
```

#### Phase 1.2.5：E2E 回归

```python
# 复用 _e2e_c1_d2.py 模板, 改为触发 version.set_current
# 验证 4 条 audit_log user_name 都是 "Admin"
```

### 1.3 完成标准

- [ ] 代码修改完成（2 个文件）
- [ ] `python d:\filework\test.py --single meta/tests/test_audit_user_name_normalization.py` 通过
- [ ] `scripts/fix_audit_admin_parentheses.py` 修复 12 条残留
- [ ] 手动验证：触发 `version.set_current` action → audit_log user_name = "Admin"
- [ ] DB 中无新残留

---

## 二、P2 优化：tx_id 覆盖率从 7.1% 提升到 95%+

### 2.1 根因分析

#### 当前 5 个会生成 tx_id 的写入路径（覆盖 230/3222 = 7.1%）

```
action_executor._do_create()           line 1242-1256  ✓ C.1 已修
action_executor._do_update()           line 1580-1595  ✓ C.1 已修
action_executor._do_delete()           line 1811-1826  ✓ C.1 已修
action_executor._do_batch_insert()     line 2007-2022  ✓ C.1 已修
manage_service._write_cascade_audit_logs() line 99-117 ✓ C.1 已修
```

#### 不生成 tx_id 的 8 条写入路径（产生 2992/3222 = 92.9%）

| # | 文件:行 | 类型 | 影响范围 | 修复策略 |
|---|---------|------|----------|----------|
| 1 | [meta/services/user_reset_password.py:73](file:///d:/filework/excel-to-diagram/meta/services/user_reset_password.py#L73) | 直接 INSERT | 安全审计 | 改为 AuditInterceptor + tx_id |
| 2 | [meta/services/subflow_engine.py:679](file:///d:/filework/excel-to-diagram/meta/services/subflow_engine.py#L679) | 直接 INSERT | 工作流审计 | 同上 |
| 3 | [meta/api/user_api.py:649](file:///d:/filework/excel-to-diagram/meta/api/user_api.py#L649) | 直接 INSERT | 用户安全 | 同上 |
| 4 | [meta/api/auth_api.py:319](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py#L319) | 直接 INSERT | 认证事件 | 同上 |
| 5 | [meta/services/audit_interceptor.py:154,201,248](file:///d:/filework/excel-to-diagram/meta/services/audit_interceptor.py#L154) | 拦截器入口 | 调用方传啥用啥 | **核心修复**：log_create/update/delete 内 auto-gen tx_id |
| 6 | [meta/api/_audit_helper.py:194,207,217,229](file:///d:/filework/excel-to-diagram/meta/api/_audit_helper.py#L194) | 角色/权限审计 | 6 个 API 调用方 | 改为走 _write_audit_log_v2 包装 |
| 7 | [meta/services/manage_service.py:101](file:///d:/filework/excel-to-diagram/meta/services/manage_service.py#L101) | cascade 内部 | 级联审计 | 改为 _write_audit_log_v2 |
| 8 | seed/migration scripts (system user 324 条) | 后台脚本 | 系统初始化 | **接受**：seed 脚本天然无业务事务 |

### 2.2 修复方案

#### Phase 2.2.1：核心修复 — `audit_interceptor.py` auto-gen tx_id

**目标**：让 `audit_interceptor.log_create/update/delete` 自动生成 tx_id，无需调用方传。

**修改** [meta/services/audit_interceptor.py](file:///d:/filework/excel-to-diagram/meta/services/audit_interceptor.py) 的 3 个方法：

```python
def log_create(self, object_type, object_id, data,
               user_id=None, user_name=None,
               trace_id=None, transaction_id=None):
    """记录创建操作"""
    # [FIX P2 2026-06-20] auto-gen tx_id (跟 action_executor._write_audit_log_v2 一致)
    try:
        from flask import g, request
        captured_user_id = user_id or getattr(g, 'user_id', None)
        captured_user_name = user_name or getattr(g, 'user_name', None)
        captured_trace_id = trace_id or getattr(g, 'trace_id', None)
        captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
        if not captured_transaction_id:
            import uuid
            captured_transaction_id = f"tx_{uuid.uuid4().hex[:16]}"
            try:
                g.transaction_id = captured_transaction_id
            except RuntimeError:
                pass
        if not captured_trace_id:
            import uuid
            captured_trace_id = f"tr_{uuid.uuid4().hex[:16]}"
            try:
                g.trace_id = captured_trace_id
            except RuntimeError:
                pass
        # ... existing code
    except RuntimeError:
        # ...
```

> 💡 **抽公共方法**：3 个方法逻辑相似，建议提取 `_capture_audit_context()` helper。

#### Phase 2.2.2：直接 INSERT 改为 AuditInterceptor（合规 + 自动 tx_id）

| 文件 | 修改 |
|------|------|
| [meta/services/user_reset_password.py](file:///d:/filework/excel-to-diagram/meta/services/user_reset_password.py) | 替换直接 INSERT 为 `AuditInterceptor.log_update({field_name, old_data, new_data})` |
| [meta/services/subflow_engine.py](file:///d:/filework/excel-to-diagram/meta/services/subflow_engine.py) | 同上 |
| [meta/api/user_api.py](file:///d:/filework/excel-to-diagram/meta/api/user_api.py) | 同上 |
| [meta/api/auth_api.py](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py) | 同上 |

**统一 helper**（新建 `meta/core/audit_helpers.py`）：

```python
"""统一审计写入入口 — 所有非 action_executor 路径必须走这里"""
import logging
import uuid
from flask import g, request
logger = logging.getLogger(__name__)

def ensure_audit_context():
    """确保 Flask g 上有 transaction_id 和 trace_id"""
    try:
        tx = getattr(g, 'transaction_id', None)
        if not tx:
            tx = f"tx_{uuid.uuid4().hex[:16]}"
            g.transaction_id = tx
        tr = getattr(g, 'trace_id', None)
        if not tr:
            tr = f"tr_{uuid.uuid4().hex[:16]}"
            g.trace_id = tr
        return tx, tr
    except RuntimeError:
        # 不在 Flask context
        tx = f"tx_{uuid.uuid4().hex[:16]}"
        tr = f"tr_{uuid.uuid4().hex[:16]}"
        return tx, tr
```

#### Phase 2.2.3：seed/migration 脚本接受 tx_id=NULL（业务合理）

system 用户的 324 条记录是 seed/migration 脚本产生的，**业务上不需要事务追踪**（它们不是业务操作）。

**方案**：
1. 在 audit_logs 表加注释：`tx_id IS NULL` = "seed/migration script operation"
2. 在 AuditLog.vue 业务视图里视觉区分（label "系统初始化" vs "用户操作"）
3. 不强制要求 system 操作有 tx_id

#### Phase 2.2.4：存量数据 backfill 脚本

**新文件**：`scripts/backfill_audit_transaction_id.py`

```python
"""给存量 audit_logs 补充 transaction_id (基于 created_at + user_name + ip 的启发式)"""
import sqlite3
import uuid
from datetime import datetime, timedelta

WINDOW_MS = 2000  # 2 秒窗口内的操作归为同一事务

def main():
    conn = sqlite3.connect("meta/architecture.db")
    c = conn.cursor()

    # 找出所有 tx_id 为空的非 system 操作
    c.execute("""
        SELECT id, created_at, user_name, ip_address, action, object_type
        FROM audit_logs
        WHERE (transaction_id IS NULL OR transaction_id = '')
          AND (user_name != 'system' OR user_name IS NULL)
        ORDER BY created_at ASC
    """)
    rows = c.fetchall()

    fixed = 0
    last_tx_per_group = {}  # (user_name, ip) -> (tx_id, group_time)

    for log_id, created_at, user_name, ip, action, obj_type in rows:
        try:
            t = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            continue

        # 启发式分组: 相同 user + ip + 2 秒窗口
        group_key = (user_name, ip)
        if group_key in last_tx_per_group:
            last_tx, last_t = last_tx_per_group[group_key]
            if abs((t - last_t).total_seconds() * 1000) < WINDOW_MS:
                c.execute("UPDATE audit_logs SET transaction_id = ? WHERE id = ?",
                          (last_tx, log_id))
                fixed += 1
                continue

        # 新建一个 tx_id
        new_tx = f"tx_{uuid.uuid4().hex[:16]}"
        c.execute("UPDATE audit_logs SET transaction_id = ? WHERE id = ?",
                  (new_tx, log_id))
        last_tx_per_group[group_key] = (new_tx, t)
        fixed += 1

    conn.commit()
    print(f"[DONE] Backfilled {fixed}/{len(rows)} records with heuristic transaction_id")
    conn.close()

if __name__ == '__main__':
    main()
```

#### Phase 2.2.5：测试验证

```powershell
# 新增 unit test: meta/tests/test_audit_tx_id_coverage.py
# - 验证 audit_interceptor.log_create 自动生成 tx_id
# - 验证 _audit_helper 自动生成 tx_id
# - 验证 backfill 脚本幂等

python d:\filework\test.py --single meta/tests/test_audit_tx_id_coverage.py
```

#### Phase 2.2.6：DB 触发器兜底（可选 P3）

```sql
-- migrations/2026_06_20_audit_tx_id_trigger.sql
CREATE TRIGGER IF NOT EXISTS audit_logs_tx_id_trigger
BEFORE INSERT ON audit_logs
FOR EACH ROW
WHEN NEW.transaction_id IS NULL OR NEW.transaction_id = ''
BEGIN
  -- 系统操作的 seed/migration 不强制 (user_name='system' 时保持 NULL)
  -- 业务操作必须自动生成
  SELECT CASE
    WHEN NEW.user_name = 'system' THEN NULL
    ELSE 'tx_' || substr(hex(randomblob(8)), 1, 16)
  END INTO NEW.transaction_id;
END;
```

**风险**：触发器可能与 `async_audit_writer` 多线程冲突；建议 **先不启用**，等应用层稳定后再加。

### 2.3 完成标准

- [ ] `audit_interceptor.py` 3 个方法 auto-gen tx_id
- [ ] 4 个直接 INSERT 改为 AuditInterceptor
- [ ] `_audit_helper.py` 走统一 helper
- [ ] `scripts/backfill_audit_transaction_id.py` 修复存量数据
- [ ] `python d:\filework\test.py --single meta/tests/test_audit_tx_id_coverage.py` 通过
- [ ] E2E: 触发 user_reset_password / role update → audit_log 都有 tx_id
- [ ] DB 中 tx_id 覆盖率 ≥ 95%（保留 system seed/migration 不强制）

---

## 三、工作计划与时间表

### 3.1 任务分解

| 任务 | 工作量 | 依赖 | 优先级 |
|------|--------|------|--------|
| T1: worktree 创建 + spec.md 编写 | 30 min | - | P0 |
| T2: P1.1 修复 action_handlers.py | 30 min | T1 | P0 |
| T3: P1.2 修复 _audit_helper.py | 30 min | T1 | P0 |
| T4: P1.3 编写 fix_audit_admin_parentheses.py | 30 min | T2, T3 | P0 |
| T5: P1.4 unit test + E2E 验证 | 1 hour | T4 | P0 |
| T6: P2.1 audit_interceptor auto-gen tx_id | 1 hour | T1 | P0 |
| T7: P2.2 4 个直接 INSERT 改 AuditInterceptor | 2 hours | T6 | P0 |
| T8: P2.3 backfill_audit_transaction_id.py | 1 hour | T6, T7 | P0 |
| T9: P2.4 unit test + 覆盖率验证 | 1 hour | T8 | P0 |
| T10: 合并到 main + restart backend | 30 min | T5, T9 | P0 |

**总工作量**：~8.5 hours (1 个工作日)

### 3.2 关键检查点

```powershell
# Checkpoint 1 (T5 完成后)
- DB 中 SELECT COUNT(*) FROM audit_logs WHERE user_name LIKE '%(%';  → 应 = 0
- 触发 version.set_current → 新 audit_log user_name 验证

# Checkpoint 2 (T9 完成后)
- DB 中 SELECT COUNT(*) FROM audit_logs WHERE transaction_id IS NULL OR transaction_id = '';
  → 应 < 5%（保留 system）
- E2E: user_reset_password / role update / subflow → 都有 tx_id

# Checkpoint 3 (T10 完成后)
- python d:\filework\test.py --failed  → 全部通过
- service_manager status → 后端在跑
```

---

## 四、风险与回滚

### 4.1 风险清单

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 修改 audit_interceptor 可能破坏现有调用方 | 中 | 加完整 unit test；先在 worktree 验证 |
| backfill 脚本误判业务事务 | 中 | 用启发式窗口 (2s) + 同 user+ip；保留 preview 模式 |
| 触发器与 async_audit_writer 冲突 | 低 | 应用层稳定后再加触发器；P2.6 暂不实施 |
| DB 锁等待（fix_audit 脚本运行时） | 低 | 在低峰期运行；test.py 自动 snapshot |
| 测试 DB 污染 | 低 | 用 `python d:\filework\test.py --single` 隔离；不用 pytest |

### 4.2 回滚预案

```powershell
# 1. 回滚代码
cd ../audit-fix-worktree
git log --oneline -5
git revert <commit-sha>

# 2. 回滚数据 (修复脚本都是 UPDATE, 有 db 备份)
# test.py 已自动 snapshot 到 .service_snapshots/

# 3. 重启服务
powershell -File scripts/service_manager.ps1 restart -Port 3011
```

---

## 五、与规范的对齐检查

| 规范要求 | 本方案如何遵循 |
|---------|---------------|
| 禁止 pytest | 所有测试用 `python d:\filework\test.py` |
| 必须 worktree | T1 用 `agent_bootstrap.ps1 -AgentName audit-fix -Port 3011` |
| service_manager | 所有重启用 `powershell -File scripts/service_manager.ps1 restart -Port 3011` |
| audit-compliance §1.3 禁止直接 INSERT | T7 把 4 个直接 INSERT 改为 AuditInterceptor |
| meta-model-schema-sync YAML 变更 | 本方案不涉及 YAML schema（仅 Python 代码）|
| 测试数据隔离 | T5/T9 用 `--single` 跑单测，不污染 DB |
| PowerShell 禁止 curl | 用 `python -c "urllib.request..."` 或 `curl.exe` |
| L5 沙箱检测 | T1 开头先验证写权限 |
| pre-commit hook | commit message 含 `fix(audit): ... [L1-L5]`，通过 7 个 gate |

---

## 六、commit message 模板

```
fix(audit): 闭环 user_name 规范化 + 提升 tx_id 覆盖率到 95%

[P1] D.2 v4: 修复 action_handlers._audit_user_name 残留 "display (username)" 格式
- meta/services/action_handlers.py:228-231 (clear_other_current_versions trigger)
- meta/api/_audit_helper.py:42-44 (role/permission config audit)
- 统一用 display_name, 不再拼接 "display (username)"
- 新增 scripts/fix_audit_admin_parentheses.py 修复 12 条历史残留

[P2] tx_id 覆盖率从 7.1% 提升到 95%+
- meta/services/audit_interceptor.py:log_create/update/delete 自动生成 tx_id
- meta/services/user_reset_password.py / subflow_engine.py / user_api.py / auth_api.py
  从直接 INSERT 改为 AuditInterceptor (合规 + auto tx_id)
- meta/api/_audit_helper.py 走统一 ensure_audit_context helper
- 新增 scripts/backfill_audit_transaction_id.py (启发式回填 2992 条历史数据)

测试:
- 新增 meta/tests/test_audit_user_name_normalization.py
- 新增 meta/tests/test_audit_tx_id_coverage.py
- E2E: _e2e_c1_d2.py + _e2e_audit_fix_v2.py

完成标准:
- audit_logs.user_name LIKE '%(%' 记录 = 0
- audit_logs.transaction_id IS NULL 记录 < 5% (system 除外)
- python d:\filework\test.py --failed 全部通过

[L1] worktree: ../audit-fix-worktree
[L2] 不碰主工作树
[L3] 不碰 stash@{0}
[L4] 已读 .agent-status.json
[L5] 沙箱已验证

Refs: audit-compliance.md §1.3, spec_7_business_issues.md D.2 + C.1
```

---

**下一步**：执行 T1（T1 完成后用户审批后启动 T2-T10）