# DEPLOY HANDOVER: BUG-V027 — wyonghui 在 TTTTT000/V11 下看到 13 个域

## 📌 任务概述

**用户问题**（PM 通过 3006 测试反馈）：
- wyonghui 经 TEST888 用户组 → scmgrp 角色（role_dimension_scopes 配置 `domain=[2200]`，即只授权供应链云）
- 期望：TTTTT000/V11 下应仅看到 1 个域（供应链云 = id 2200）
- 实际：**看到 13 个域**（包含财务云、营销云、人力云等所有未授权域）

## 🔍 根因

**BUG 位置**：`meta/core/interceptors/data_permission_interceptor.py`，`_apply_dimension_scope_filter` 方法多 role 分支

**根因代码**（修复前）：

```python
else:
    # 多 role: OR-of-AND
    or_group_conditions = []
    for conds in per_role_conditions:
        or_group_conditions.extend(conds)   # ❌ BUG: 平铺 AND 段, 丢 AND 关系
    context.extra['query_conditions'].append({
        'type': 'or',
        'conditions': or_group_conditions,
    })
```

**为什么是 bug**：
- `per_role_conditions` 形如 `[[{id:703}, {version_id:764}], [{id:2200}, {version_id:863}]]`（外层 list of list）
- 内部 list 是一个 role 的 AND 段（`id=703 AND version_id=764`）
- `extend` 后变成 `[a, b, c, d]` flat — 4 个独立的 OR 元素
- SQL 解析：`id=703 OR version_id=764 OR id=2200 OR version_id=863`（永远为真）
- 期望：`((id=703 AND version_id=764) OR (id=2200 AND version_id=863))` （限定 2 行）

## 🛠️ 修复

**修复后**：

```python
else:
    # 多 role: OR-of-AND
    # 每个 role 的 conds 作为一个 AND 组, 用 {'type': 'and', 'conditions': conds} 包裹
    # 这样 SQL 解析 = (AND 组 1) OR (AND 组 2) OR ...
    context.extra['query_conditions'].append({
        'type': 'or',
        'conditions': [
            {'type': 'and', 'conditions': conds}
            for conds in per_role_conditions
        ],
    })
```

**文件**：
- `meta/core/interceptors/data_permission_interceptor.py` (M)
- `meta/tests/test_data_permission_or_of_and_v1230.py` (A, 3 单测)

## ✅ 验证

### Worktree backend 端到端 (port 3017)
| 测试 | 修复前 | 修复后 |
|------|--------|--------|
| `wyonghui GET /api/v2/bo/domain?version_id=863` | 13 个域 (全部) | **1 个域 (供应链云 2200)** ✓ |
| `admin GET /api/v2/bo/domain?version_id=863` | 13 个域 | 13 个域（未受影响）✓ |

### 单元测试

`meta/tests/test_data_permission_or_of_and_v1230.py` 包含 3 个测试：

1. `test_multi_role_or_of_and_nested_not_flattened` — 验证多 role 时 OR 组里每个 role 的 conds 都被包成 `{type:and, conditions:[...]}`
2. `test_single_role_no_or_group` — 验证单 role 时不包 OR 包裹
3. `test_no_role_returns_false` — 验证无 role 时不注入 query_conditions

**结果**：
- 我新加的 3 个测试：✅ 全部 PASS
- `test_data_permission_interceptor.py` 已有 23 个测试：✅ 全部 PASS
- 整个 data permission 相关测试套件：30 passed, 1 failed, 34 skipped
- **唯一 1 个 failed 是 pre-existing** (`test_before_action_skips_when_admin_flag_true` 在 fix 之前也 fail — 我用 `git stash` 验证过)

## 📊 关联用户/角色数据

| 实体 | ID | 说明 |
|------|----|----|
| User `wyonghui` | 10006 | uid |
| User `TEST888` | 10001 | uid (同组) |
| User Group `TEST888` | 1037 | `供应链小组` |
| Group members | 619 (TEST888), 620 (wyonghui) | 组成员 |
| Role `scmgrp` | 11821 | `role_dimension_scopes[275]: domain=[2200], include, inherit_children=1` |
| Product `TTTTT000` | 507 | visibility=`private`, owner_id=1 (Admin) |
| Version `V11` | 863 | version_id |
| Domain `供应链云` | 2200 | 应该可见 |
| Domains V11 下 | 2198-2210 | 13 个 |

**wyonghui 通过 2 个 role (5970=domain:703, 11821=domain:2200) 走 OR-of-AND**:
- role 5970 的 AND 段：`(id=703 AND version_id=764)` — 不在 V11 下 → 不贡献可见行
- role 11821 的 AND 段：`(id=2200 AND version_id=863)` — 在 V11 下 → 贡献 1 行
- 结果：wyonghui 应仅见 1 个域（2200 供应链云）

## 🚀 部署步骤

协调智能体请按以下步骤发布到 production (3006/3011)：

1. **cherry-pick** 这 1 个 commit 到 release/pre-2026-06-29：
   ```bash
   cd d:\filework\excel-to-diagram
   git cherry-pick 88df99a
   ```
   **如果 cherry-pick 冲突，STOP 并联系 agent-dpiprint**（不强行解决）

2. **运行 check-sha-consistency**：
   ```bash
   powershell -File scripts/check-sha-consistency.ps1
   ```
   必须 exit 0

3. **rebuild dist + restart main-3011**：
   ```bash
   powershell -File scripts/release_to_remote.ps1 -Stage pre
   ```

4. **e2e 验证**（integration agent 跑）：
   ```bash
   # wyonghui 登录 3007 → 测试 TTTTT000/V11/供应链云可见
   ```

5. **通知 PM**：deploy 完成后，在 `.agent-status.json` 更新任务状态为 `merged`

## 📋 关联文档

- spec.md: `d:\filework\agent-dpiprint-worktree\spec.md`
- DPI 代码: `meta/core/interceptors/data_permission_interceptor.py`
- 单测: `meta/tests/test_data_permission_or_of_and_v1230.py`

## ⏱️ 时间戳

- 开始: 2026-07-07 22:30 (UTC+8)
- 定位根因: 2026-07-07 22:50 (print 调试 DPI 路径)
- 修复 + 单测: 2026-07-07 23:00
- Commit: `88df99a` (agent-dpiprint-main)

## ✍️ 作者

agent-dpiprint (port 3017)
worktree: `D:\filework\agent-dpiprint-worktree`
branch: `agent-dpiprint-main`
