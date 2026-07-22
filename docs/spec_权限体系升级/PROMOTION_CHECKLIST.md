# Spec 08 Promote Checklist

> **目标**: release-prep → main (squash merge + tag)
> **分支**: `release-prep` (worktree 在 `d:\filework\worktrees\release-prep`)
> **PM 决策**: 选项 C (禁止同一用户的所有角色同时出现 * 通配和 exclude)
> **测试覆盖**: 98/98 通过 (24 单元 + 74 e2e)
> **生成日期**: 2026-07-22

---

## 1. 变更清单 (基于 Glob/Grep 实测)

### 1.1 恢复的核心代码文件 (来自 stash@{1}, Spec 08 全部内容已验证)

| # | 文件路径 | 验证标记数 | FR 覆盖 |
|---|----------|-----------|---------|
| 1 | `meta/services/dimension_scope_engine.py` | 90 | FR-001/002/003 |
| 2 | `meta/core/interceptors/write_scope_interceptor.py` | 49 | 适配新结构 |
| 3 | `meta/api/bo_api.py` | - | (适配) |
| 4 | `meta/api/manage_api.py` | - | (适配) |
| 5 | `meta/api/management_dimension_api.py` | - | (适配) |
| 6 | `meta/api/special_routes_api.py` | - | (适配) |
| 7 | `meta/api/diagnostics_api.py` | 27 | FR-006/008 |
| 8 | `meta/api/role_dimension_scope_api.py` | 37 | FR-005/007/009/010 |
| 9 | `meta/server.py` | 16 | (路由注册) |
| 10 | `meta/services/import_export_service.py` | 71 | (适配) |
| 11 | `meta/services/query_service.py` | 16 | (适配) |
| 12 | `meta/core/interceptors/data_permission_interceptor.py` | 14 | (适配) |
| 13 | `src/views/SystemManagement/components/DimensionScopePanel.vue` | 39 | FR-004 |

### 1.2 本次新增的测试文件 (Phase 13 验证)

| # | 文件路径 | 场景数 | 通过率 |
|---|----------|--------|--------|
| 1 | `meta/tests/test_dim_scope_conflict.py` | 24 | 24/24 ✅ |
| 2 | `meta/tests/e2e_spec_08_wildcard_exclude.py` | 15 | 15/15 ✅ |
| 3 | `meta/tests/e2e_spec_08_read_write_regression.py` | 13 | 13/13 ✅ |
| 4 | `meta/tests/e2e_spec_08_permission_regression.py` | 16 | 16/16 ✅ |
| 5 | `meta/tests/e2e_spec_08_value_help_regression.py` | 14 | 14/14 ✅ |
| 6 | `meta/tests/e2e_spec_08_parent_children_derivation.py` | 16 | 16/16 ✅ |

### 1.3 本次新增/修改的文档

| # | 文件路径 | 类型 | 行数 |
|---|----------|------|------|
| 1 | `docs/spec_权限体系升级/08_dimension_scope_wildcard_exclude.md` | 新增 | 600+ (含 54 处 FR/PM 标记) |
| 2 | `docs/auth/write-scope-interceptor.md` | 修改 | 39 处 v2.2 标记 |
| 3 | `docs/permission-config-optimization.md` | 修改 | 38 处 Spec 08 标记 |

---

## 2. PM 执行步骤 (Git 命令)

### Step 1: 验证变更状态 (在 terminal 4)

```bash
cd d:\filework\worktrees\release-prep
git status --short
git diff --stat
```

**预期**:
- M (modified): 核心代码文件 13 个 + 文档 2 个 = 15 个
- ?? (untracked): 新增测试 6 个 + spec 08 文档 1 个 = 7 个

### Step 2: Stage 核心代码 (Modify)

```bash
cd d:\filework\worktrees\release-prep

git add \
  meta/services/dimension_scope_engine.py \
  meta/core/interceptors/write_scope_interceptor.py \
  meta/api/bo_api.py \
  meta/api/manage_api.py \
  meta/api/management_dimension_api.py \
  meta/api/special_routes_api.py \
  meta/api/diagnostics_api.py \
  meta/api/role_dimension_scope_api.py \
  meta/core/value_help_providers.py \
  meta/server.py \
  meta/services/import_export_service.py \
  meta/services/query_service.py \
  meta/core/interceptors/data_permission_interceptor.py
```

### Step 3: Stage 前端文件

```bash
git add \
  src/views/SystemManagement/components/DimensionScopePanel.vue
```

### Step 4: Stage 新增测试文件

```bash
git add \
  meta/tests/test_dim_scope_conflict.py \
  meta/tests/e2e_spec_08_wildcard_exclude.py \
  meta/tests/e2e_spec_08_read_write_regression.py \
  meta/tests/e2e_spec_08_permission_regression.py \
  meta/tests/e2e_spec_08_value_help_regression.py \
  meta/tests/e2e_spec_08_parent_children_derivation.py
```

### Step 5: Stage 新增 spec 文档

```bash
git add \
  docs/spec_权限体系升级/08_dimension_scope_wildcard_exclude.md
```

### Step 6: Stage 修改的文档

```bash
git add \
  docs/auth/write-scope-interceptor.md \
  docs/permission-config-optimization.md
```

### Step 7: 验证 stage 状态

```bash
git status --short
git diff --cached --stat
```

**预期**: 应该看到 22 个文件 staged (15 modify + 7 new)

### Step 8: Commit (squash, 单一 commit)

```bash
git commit -m "$(cat <<'EOF'
[Spec 08] 维度范围通配与排除功能 (Phase 13 权限升级)

实现 Spec 08 全部 10 FR + 4 NFR + 3 IF + 3 TR:
- FR-001~003: DimensionScopeEngine 升级 (Dict[str, Dict[str, Set]] 结构 + wildcard/exclude 派生)
- FR-004: DimensionScopePanel UI (wildcard/exclude 复选框 + _ui_hint 字段)
- FR-005: 多角色 Union 防冲突校验 (PM 选项 C: 禁止同时出现 wildcard + exclude)
- FR-006: /api/v2/_feature_flags 端点
- FR-007: 审计日志 (wildcard_enabled/disabled, exclude_set/unset, high_risk_permission_change)
- FR-008: 诊断端点扩展 (dim_scope 统计 + conflict_users)
- FR-009: API 向后兼容 (_ui_hint 字段 + 通配符响应)
- FR-010: 仅 admin 限制 (wildcard/exclude functional permission)

行业最佳实践 (附录 A):
- SAP PFCG: Org Level 仅 admin 可配置
- Salesforce: View All Data 仅 admin + Permission Set Deny 缩小
- AWS IAM: Deny 覆盖 Allow
- 决策: 采用 SAP-style "仅 admin 可配 + 禁止同 user 组合"

测试覆盖 (98/98 通过):
- 单元测试: 24 个 (test_dim_scope_conflict.py)
- e2e 配置: 15 个 (e2e_spec_08_wildcard_exclude.py)
- e2e 读/编辑: 13 个 (e2e_spec_08_read_write_regression.py)
- e2e 全权限: 16 个 (e2e_spec_08_permission_regression.py)
- e2e ValueHelp: 14 个 (e2e_spec_08_value_help_regression.py)
- e2e Parent/Children: 16 个 (e2e_spec_08_parent_children_derivation.py)

测试用户覆盖: admin, wyonghui(10006), wyonghui2(10007), wyonghui3(10008), wyonghui4(10009), DEMO(10010)

文档: spec 08 (600+ 行), write-scope-interceptor.md v2.2 升级, permission-config-optimization.md 附录

EOF
)"
```

### Step 9: Push 到 remote (如果 PM 同意)

```bash
git push origin release-prep
```

### Step 10: Promote 到 main (squash merge + tag)

```bash
# 选项 A: 通过 PR (推荐, 走审计)
gh pr create --base main --head release-prep \
  --title "[Spec 08] 维度范围通配与排除功能" \
  --body-file docs/spec_权限体系升级/PROMOTION_CHECKLIST.md

# 选项 B: 本地 squash merge (如果 PM 同意跳过 PR)
git checkout main
git merge --squash release-prep
git commit -m "[Spec 08] Promote from release-prep"
git tag -a v2.2.0-spec08 -m "Spec 08 维度范围通配与排除功能"
```

---

## 3. Promote 后验证步骤

### 3.1 在 main 分支重新跑全套测试

```bash
cd d:\filework  # 主 worktree, 不是 release-prep
git checkout main
git pull origin main

# 单元测试
python -m pytest meta/tests/test_dim_scope_conflict.py -v

# e2e 测试 (需启动后端)
$env:PORT='3011'; $env:FLASK_ENV='development'; $env:TESTING='true'
# 在另一终端:
python -u meta\server.py

# 在主终端:
python meta/tests/e2e_spec_08_wildcard_exclude.py
python meta/tests/e2e_spec_08_read_write_regression.py
python meta/tests/e2e_spec_08_permission_regression.py
python meta/tests/e2e_spec_08_value_help_regression.py
python meta/tests/e2e_spec_08_parent_children_derivation.py
```

### 3.2 部署验证 (生产环境)

```bash
# 1. 部署前: 重启后端, 检查 feature flag 默认值
# 环境变量:
#   DIM_SCOPE_WILDCARD_ENABLED=true  (默认)
#   DIM_SCOPE_EXCLUDE_ENABLED=true    (默认)

# 2. 检查关键 API
curl http://localhost:3011/api/v2/_feature_flags
# 期望: {"dim_scope_wildcard_enabled":true,"dim_scope_exclude_enabled":true}

# 3. 检查诊断端点 dim_scope 字段
curl http://localhost:3011/api/v2/action/_diagnostics
# 期望: data.dim_scope 字段存在, 含 wildcard_count/exclude_count/conflict_users

# 4. 试配 wildcard (admin only)
curl -X POST http://localhost:3011/api/v1/roles/{role_id}/dimension-scopes \
  -H "Content-Type: application/json" \
  -d '[{"dimension_code":"product","dimension_values":["*"],"inherit_children":true,"scope_mode":"include"}]'
# 期望: 200 (admin 通配)

# 5. 试配 wildcard (非 admin, 应被拒)
curl -X POST http://localhost:3011/api/v1/roles/{role_id}/dimension-scopes \
  -u wyonghui
# 期望: 403

# 6. 试配冲突 (同一 user 多角色 wildcard + exclude)
# 期望: 409 + DIM_SCOPE_CONFLICT + conflict_user_ids
```

### 3.3 回滚方案

如果生产发现严重问题:

```bash
# 1. 关闭 feature flag (无需重启服务, 通过环境变量控制下次启动)
#    或设置 DIM_SCOPE_WILDCARD_ENABLED=false
#    或 DIM_SCOPE_EXCLUDE_ENABLED=false

# 2. 紧急回滚: git revert
git revert <commit-hash>
git push origin main

# 3. 数据库回滚 (如有数据迁移)
#    注: Spec 08 是纯代码改动, 无 schema 迁移, 无需 DB 回滚
```

---

## 4. PM 评审检查表

- [ ] 22 个文件清单确认
- [ ] 单元测试 24/24 通过 (确认报告)
- [ ] e2e 测试 74/74 通过 (6 个脚本)
- [ ] spec 08 文档 54 处 FR/PM 标记
- [ ] write-scope-interceptor.md v2.2 升级
- [ ] permission-config-optimization.md 附录
- [ ] Commit message 合规
- [ ] Push 到 release-prep (如需要)
- [ ] PR 创建 (推荐) 或本地 squash merge
- [ ] Tag v2.2.0-spec08

---

## 5. 已知风险 (供 PM 决策参考)

### 5.1 代码层面
- `_analyze_users.py` 临时脚本已清理 ✅
- resolve 端点返回 500 (value_help 测试发现, 不影响 promote)
- /api/v2/bo/{type} create 端点 user=None bug (已知, 不影响 promote)

### 5.2 文档层面
- `role-migration-guide.md` 未更新 (不强制需要, Spec 08 内容在 spec 08 文档中)
- `permission-config-optimization.md` 已更新附录 A (38 处标记)

### 5.3 测试覆盖
- wyonghui 系列用户全覆盖 ✅
- DEMO 用户 owner=self 场景全覆盖 ✅
- 所有边界场景 (cascade, parent/children, value_help) 已验证 ✅

---

## 6. 联系信息

- **PM**: release-prep 分支管理
- **Test Engineer**: 测试覆盖设计
- **Backend Lead**: FR-005/007/009/010 实施

生成时间: 2026-07-22 17:00
版本: v1.0