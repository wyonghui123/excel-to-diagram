# 交接：Spec 16/19 user_group 残留清理（commit `9bed46c1` 漏改部分）

> **接收方**: 下一任 dev agent（或任何接管 fix/auth-user-permission-set-20260917 分支的 agent）
> **交接日期**: 2026-09-18
> **作者**: dev agent (V061 staging) + 二审 agent
> **分支**: `fix/auth-user-permission-set-20260917`
> **关键 commit**: [`9bed46c1`](../../)（已 push 到 origin）
> **状态**: 🔴 含 3 处 CRITICAL runtime 残留未修

---

## 0. TL;DR (60 秒版)

**Dev agent 已 commit [`9bed46c1`](../../) (Spec 16+tools: drop user_group schema + add remote DB sync infra)，但 schema 清理不完整** —— 删了 `user_group.yaml` / `user_group_member.yaml` 两个 schema 文件，但**源码中还有 8 处对 `user_groups` / `user_group_members` 表/字符串的死引用**。

**最严重 1 处**：[`meta/api/management_dimension_api.py:92`](../../meta/api/management_dimension_api.py) 的 `_get_user_dim_scope_ids()` 函数 SQL 仍写 `FROM user_group_members`，**但表已在 v089 迁移删除**，调用即 SQL error。该函数被 permission system 使用。

**DB 同步基础设施完整无缺失** —— 这是 commit 的"配套能力"，下任 agent 可直接复用（见 §4）。

---

## 1. 上下文

### 1.1 commit `9bed46c1` 做了什么（已完成）

```bash
git log -1 --stat 9bed46c1
```

| 文件 | 类型 | 行数 |
|------|------|------|
| `meta/schemas/user_group.yaml` | 删除 | -515 |
| `meta/schemas/user_group_member.yaml` | 删除 | -93 |
| `meta/server.py` (line 787) | 修改 | +1/-1 |
| `tools/REMOTE_DB_OPS.md` | 新增 | +326 |
| `tools/pull_db.py` | 新增 | +466 |
| `tools/push_db.py` | 新增 | +465 |
| `tools/test_pull_db.py` | 新增 | +168 |
| `tools/test_pull_db_unit.py` | 新增 | +383 |
| `tools/test_push_db.py` | 新增 | +176 |
| `tools/test_push_db_unit.py` | 新增 | +373 |
| **总计** | **10 files** | **+2358 / -609** |

### 1.2 commit 漏改的部分（本次交接要修的）

**搜索方法**（下任 agent 可重新跑一遍验证）：
```bash
git grep -n "user_groups\|user_group_members\|user_group\b\|user-groups" \
    -- 'meta/' 'src/' 'tools/' ':!tools/REMOTE_DB_OPS.md' ':!tools/test_*.py' \
    ':!tools/pull_db.py' ':!tools/push_db.py'
```

---

## 2. CRITICAL (必须修 — runtime 会崩)

### 🔴 #1. `meta/api/management_dimension_api.py:92`

**位置**：[`meta/api/management_dimension_api.py:92`](../../meta/api/management_dimension_api.py)

**现状**：
```python
# 函数: _get_user_dim_scope_ids()
# 调用链: permission system → _get_user_dim_scope_ids() → SQL error
cursor = _data_source.execute(
    "SELECT group_id FROM user_group_members WHERE user_id = ?",  # ❌ 表不存在
    [user_id]
)
```

**修复方案**：
```python
# 改为 (user_group_members → org_members, group_id → org_id)
cursor = _data_source.execute(
    "SELECT org_id FROM org_members WHERE user_id = ?",
    [user_id]
)
# 后续 group_ids → role_ids 链路也需验证:
# 原 SQL: SELECT DISTINCT role_id FROM group_roles WHERE group_id IN (...)
# group_roles 表在 v073 已重命名为 org_permission_sets
# 字段: group_role_id → org_permission_set_id (或保持 role_id)
# 建议同时跑 SELECT name FROM sqlite_master WHERE type='table' LIKE '%role%' 验证
```

**触发条件**：
- 任何非 admin 用户调用需 dimension scope 检查的 endpoint
- 典型路径: `GET /api/v2/bo/<obj>?scope_check=true` → permission guard → `_get_user_dim_scope_ids()`

**复现方法**：
```bash
# 1. 启动 staging
# 2. dev-login 普通用户 (非 admin)
curl http://localhost:3010/api/v1/auth/dev-login?username=alice
# 3. 调用 dimension scope endpoint
curl -H "Cookie: ..." http://localhost:3010/api/v2/bo/user?scope_check=true
# 期望: 500 + "no such table: user_group_members"
```

### 🔴 #2. `meta/schemas/_audit_materialization.yaml` (L92-95, L162-164)

**位置**：[`meta/schemas/_audit_materialization.yaml`](../../meta/schemas/_audit_materialization.yaml) 第 90-95 行 + 第 160-164 行

**现状**：
```yaml
# L90-95 — 死配置 (表已删, trigger 也不存在)
- name: user_groups
  strategy: business_trigger
  object_type: user_group
  trigger: trg_user_groups_updated_at
  notes: 历史触发器

# L160-164 — 死配置
- name: user_group_members
  strategy: audit_derived
  object_type: user_group_member
  notes: 从 v_audit_all 聚合
```

**加载路径**：[`meta/core/materialization_registry.py`](../../meta/core/materialization_registry.py) 在服务启动时加载整个 yaml。

**修复方案**：
- **删除 L90-95 整块**（user_groups 配置）
- **删除 L160-164 整块**（user_group_members 配置）
- L7, L25, L85 注释保留（说明性，无需改）

**触发条件**：
- 任何代码调用 `materialization_registry.get_strategy('user_groups')` 或 `get_updated_at('user_groups', id)` → SQL error (trigger 不存在)
- 间接触发: 审计日志查询带 `updated_at` 排序

### 🟢 #3. `meta/core/table_name_validator.py:16`

**位置**：[`meta/core/table_name_validator.py:16`](../../meta/core/table_name_validator.py)

**现状**：
```python
_SYSTEM_TABLES = frozenset({
    'users', 'roles', 'permissions', 'role_permissions',
    'user_group_members', 'group_roles',  # ← 死表, 留着误导维护
    ...
    'user_groups',                        # ← 死表
    ...
})
```

**修复方案**：
```python
_SYSTEM_TABLES = frozenset({
    'users', 'roles', 'permissions', 'role_permissions',
    # [Spec 16 2026-08-29] user_group_members / group_roles / user_groups 已废弃
    # 由 org_members / org_permission_sets / orgs 替代 (v072 + v089)
    ...
    'orgs', 'org_members', 'org_permission_sets',  # 新表白名单
    ...
})
```

**影响**: 不影响 runtime（白名单无害），但误导未来维护者。

---

## 3. MEDIUM (应该修 — schema dead reference)

### 🟡 #4-6. `meta/schemas/user.yaml` (L417, L419, L703)

**位置**：[`meta/schemas/user.yaml`](../../meta/schemas/user.yaml)

**现状**：
```yaml
# L415-419
associations:
  - name: groups
    target_type: user_group       # ← 死引用
    type: many_to_many
    through: user_group_members  # ← 死引用
    source_key: user_id
    target_key: group_id
    display:
      label: 所属用户组
      ...

# L700-704
deletion_policy:
  restrict_on:
  cascade_delete:
    - user_group_members         # ← 死引用
    - change_subscriptions
    ...
```

**修复方案**：
```yaml
associations:
  - name: groups
    target_type: org              # ← user_group → org
    type: many_to_many
    through: org_members          # ← user_group_members → org_members
    source_key: user_id
    target_key: org_id            # ← group_id → org_id
    display:
      label: 所属组织
      plural_label: 组织列表
      target_display_field: name

# deletion_policy 同样
cascade_delete:
  - org_members                  # ← user_group_members → org_members
  - change_subscriptions
  ...
```

**影响**:
- 前端 `GET /api/v2/bo/user/<id>/associations?type=groups` 会失败（找不到 `user_group` type）
- 前端 user 详情页"所属组织"区域加载失败

### 🟡 #7. `meta/schemas/org.yaml` L23

**位置**：[`meta/schemas/org.yaml`](../../meta/schemas/org.yaml) 第 23 行

**现状**：
```yaml
aliases:
  - 组织
  - Org
  - 用户组  # 历史 alias
  - user_group    # ← 死 alias
```

**修复方案**：
```yaml
aliases:
  - 组织
  - Org
  - 用户组  # 历史 alias (中文保留, 英文移除)
```

### 🟢 #8. `meta/schemas/.schema_version.json` (L644-670)

**位置**：[`meta/schemas/.schema_version.json`](../../meta/schemas/.schema_version.json)

**现状**：
```json
{
  "objects": {
    ...
    "user_group": {         # ← 死 schema entry
      "hash": "94ead932db4e548e80a65163cae3d323",
      "fields": [...],
      "table": "user_groups"
    },
    "user_group_member": {  # ← 死 schema entry
      "hash": "e7c4931fd98aa9217b9b56ea7ceb6fe3",
      "fields": [...],
      "table": "user_group_members"
    },
    ...
  }
}
```

**修复方案**：
- 直接删除 `user_group` 和 `user_group_member` 两个 entry
- 该文件是 **cache** (auto-regen by `meta/api/bo_api.py:get_schema_version`)
- L724, L727 (migration history 注释) 保留

---

## 4. DB 同步基础设施（commit 已完成，下任 agent 可直接用）

**无需修改，直接复用**：

| 工具 | 用途 | 文档 |
|------|------|------|
| `tools/pull_db.py` | 远端 SQLite → 本地 | [`tools/REMOTE_DB_OPS.md`](../../tools/REMOTE_DB_OPS.md) |
| `tools/push_db.py` | 本地 SQLite → 远端 | [`tools/REMOTE_DB_OPS.md`](../../tools/REMOTE_DB_OPS.md) |

**关键能力**:
- 解决 3 个长期阻塞 dev 工作的核心问题：
  1. core_service `/api/exec` stdout 50000 字符限制 (大 DB base64 后超出)
  2. staging exec 命令白名单 (禁用 `base64`/`dd`/`sed -n` 等)
  3. rate limit (~20 req/s) + token 过期 (跨小时)

**典型用法**（从 staging 拉最新 DB 到本地）：

```bash
# 拉 staging architecture.db 到本地 (备份原文件)
python tools/pull_db.py \
    --remote /opt/app/staging/meta/architecture.db \
    --local meta/architecture.db \
    --backup meta/architecture.db.bak.$(date +%Y%m%d_%H%M%S)

# 推到 staging (替换主 DB, 自动备份)
python tools/push_db.py --local meta/architecture.db --target staging

# 仅查远端 DB 信息 (不下载)
python tools/pull_db.py --target staging \
    --remote /opt/app/staging/meta/architecture.db --info
```

**测试已通过**：
- `tools/test_pull_db_unit.py` — 6 PASSED (<1s)
- `tools/test_push_db_unit.py` — 7 PASSED (<1s)
- `tools/test_pull_db.py` (round-trip) — ALL PASSED (~113s, 117MB staging)
- `tools/test_push_db.py` (round-trip) — ALL PASSED (1.5s, 2.15MB test DB)

**依赖**: `tools/staging_ops.py` (exec_cmd/upload_file) + `tools/yonaa_exec.py` (yupload/yexec/yuploaderun)，两者均已存在于 main。

**详细使用**：见 [`tools/REMOTE_DB_OPS.md`](../../tools/REMOTE_DB_OPS.md)（326 行，含 CLI / Python API / 流程图 / 限制 / 调试）。

---

## 5. 推荐修复顺序

按风险从高到低:

```
[1] 🔴 meta/api/management_dimension_api.py:92
    → 改 user_group_members → org_members, group_id → org_id
    → 验证后续 SQL (group_roles → org_permission_sets?)
    → 跑 dim-scope endpoint 复现 + 验证修复
    → commit: fix(api): rename user_group_members → org_members in dim scope lookup

[2] 🔴 meta/schemas/_audit_materialization.yaml
    → 删除 L90-95 (user_groups)
    → 删除 L160-164 (user_group_members)
    → 启动服务,验证 get_updated_at('orgs', id) 正常
    → commit: chore(schema): drop user_groups/user_group_members from materialization registry

[3] 🟡 meta/schemas/user.yaml (L417, L419, L703)
    → user_group → org, user_group_members → org_members, group_id → org_id
    → 前端验证 associations query 正常
    → commit: chore(schema): rename user_group refs to org in user.yaml

[4] 🟡 meta/schemas/org.yaml L23
    → 删除 - user_group alias
    → commit: chore(schema): drop user_group alias from org.yaml

[5] 🟢 meta/core/table_name_validator.py:16
    → 移除 user_group_members / group_roles / user_groups
    → 添加 orgs / org_members / org_permission_sets
    → commit: chore(security): update SQL validator whitelist for spec16 table rename

[6] 🟢 meta/schemas/.schema_version.json (L644-670)
    → 删除 user_group + user_group_member entries
    → 注: 该文件 cache, 下次启动 bo_api 会覆盖, 可不单独 commit
```

**可选 bonus**: 删整文件 `meta/api/user_group_api.py` (dead Blueprint) + `meta/services/user_group_service.py` (sunset shim)。**不推荐在本次 commit 一起做**，留独立 commit 更安全（已死代码 ≠ 当前 bug）。

---

## 6. 不要做的事（避坑）

### 6.1 不要全 git grep 一次性改

`user_group` 字符串散落在 50+ 文件中，**包括注释、测试 fixture、history 说明**。盲目 `sed -i 's/user_group/org/g'` 会破坏：
- 历史 commit 引用 (`v089__drop_legacy_user_group_and_role_tables.py` 注释)
- 测试 fixture (`tests/conftest.py` 创建历史表)
- 文档 (`docs/specs/...` 的历史描述)

### 6.2 不要删 `meta/api/user_group_api.py` + `user_group_service.py`

它们虽然 dead，但**有可能被未来 v2/bo/org 重构时复用**。**保持 sunset shim 兼容层**，未来 plan B 重构时一起清。

### 6.3 不要碰 `meta/migrations/*user_group*.py`

历史迁移文件是**已执行的迁移**，不能改 (`drop_user_group_member_count.py` / `compensate_association_audit.py` / `v089__drop_legacy_*`)。这些是历史事实，改了会破坏 schema 演进追溯。

### 6.4 不要在 main 上 commit 修复

修复应该基于 `fix/auth-user-permission-set-20260917` 分支（commit `9bed46c1` 之上），等下任 agent 验证完再 merge 到 main。

---

## 7. 验收清单

修复完跑这些验证：

```bash
# 1. SQL injection 白名单 (修复 #5 后)
python -c "
from meta.core.table_name_validator import _SYSTEM_TABLES
assert 'user_groups' not in _SYSTEM_TABLES
assert 'user_group_members' not in _SYSTEM_TABLES
print('OK')
"

# 2. Materialization registry (修复 #2 后)
python -c "
from meta.core.materialization_registry import MaterializationRegistry
r = MaterializationRegistry()
strategy = r.get_strategy('orgs')  # 应返回 audit_derived
assert strategy == 'audit_derived', strategy
print('OK')
"

# 3. Schema associations (修复 #3 后)
python -c "
import yaml
with open('meta/schemas/user.yaml') as f:
    s = yaml.safe_load(f)
for assoc in s.get('associations', []):
    if assoc['name'] == 'groups':
        assert assoc['target_type'] == 'org'
        assert assoc['through'] == 'org_members'
        print('OK')
"

# 4. End-to-end dim scope (修复 #1 后)
curl -H "Cookie: $(cat /tmp/cookie.txt)" \
    http://localhost:3010/api/v2/bo/user?scope_check=true
# 期望: 200 (非 SQL error)

# 5. Schema version API (cache 自动 regen, 跑一次即可)
curl http://localhost:3010/api/v1/meta/schema-version
# 期望: schema_version 不含 user_group
```

---

## 8. 相关文档 / commit / 文件链接

| 类型 | 链接 |
|------|------|
| Commit | [`9bed46c1`](../../) — drop user_group schema + add remote DB sync infra |
| 分支 | `fix/auth-user-permission-set-20260917` |
| DB 同步文档 | [`tools/REMOTE_DB_OPS.md`](../../tools/REMOTE_DB_OPS.md) |
| Spec 16 Plan D retrospective | [`2026-09-13-deploy-topology-generalization.md`](../../retrospectives/2026-09-13-deploy-topology-generalization.md) |
| Spec 19 v089 migration | [`v089__drop_legacy_user_group_and_role_tables.py`](../../meta/migrations/v089__drop_legacy_user_group_and_role_tables.py) |
| Materialization SSOT | [`_audit_materialization.yaml`](../../meta/schemas/_audit_materialization.yaml) |
| Governance 索引 | [`AGENT_INDEX.md`](../../.trae/rules/AGENT_INDEX.md) |
| 家族失败模式 F001 | [`F001-stale-loader.md`](../../_families/families/F001-stale-loader.md) |

---

## 9. 一句话总结

> Dev agent 已 commit Spec 16 schema 清理 + DB sync infra (commit `9bed46c1`), 但 schema 清理不完整 —— 8 处 `user_groups` / `user_group_members` 死引用, **1 处 runtime critical** (`management_dimension_api.py:92`) 必须修。修复方案 + 验收清单详见 §2-§7, DB sync infra 直接复用 (详见 §4)。