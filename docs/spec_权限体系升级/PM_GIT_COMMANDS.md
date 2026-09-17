# PM Terminal 4 Git 执行清单

> **工作流**: PM 在 terminal 4 (idle) 执行 git 命令, 我用 Read 验证
> **目标**: release-prep → main (squash merge + tag)
> **生成日期**: 2026-07-22

---

## 步骤 1: Stage 核心代码 (Modify)

请 PM 在 terminal 4 复制粘贴执行:

```bash
cd d:\filework\worktrees\release-prep
git add \
  meta/services/dimension_scope_engine.py \
  meta/core/interceptors/write_scope_interceptor.py \
  meta/api/bo_api.py \
  meta/api/manage_api.py \
  meta/api/permission_dimension_api.py \
  meta/api/special_routes_api.py \
  meta/api/diagnostics_api.py \
  meta/api/role_dimension_scope_api.py \
  meta/server.py \
  meta/services/import_export_service.py \
  meta/services/query_service.py \
  meta/core/interceptors/data_permission_interceptor.py \
  src/views/SystemManagement/components/DimensionScopePanel.vue
```

---

## 步骤 2: Stage 新增测试文件

```bash
cd d:\filework\worktrees\release-prep
git add \
  meta/tests/test_dim_scope_conflict.py \
  meta/tests/e2e_spec_08_wildcard_exclude.py \
  meta/tests/e2e_spec_08_read_write_regression.py \
  meta/tests/e2e_spec_08_permission_regression.py \
  meta/tests/e2e_spec_08_value_help_regression.py \
  meta/tests/e2e_spec_08_parent_children_derivation.py
```

---

## 步骤 3: Stage spec + 文档

```bash
cd d:\filework\worktrees\release-prep
git add \
  docs/spec_权限体系升级/08_dimension_scope_wildcard_exclude.md \
  docs/spec_权限体系升级/PROMOTION_CHECKLIST.md \
  docs/auth/write-scope-interceptor.md \
  docs/permission-config-optimization.md
```

---

## 步骤 4: Commit

```bash
cd d:\filework\worktrees\release-prep
git commit -m "[Spec 08] 维度范围通配与排除功能 (Phase 13 权限升级)

实现 Spec 08 全部 10 FR + 4 NFR + 3 IF + 3 TR:
- FR-001~003: DimensionScopeEngine 升级 (Dict[str, Dict[str, Set]] 结构 + wildcard/exclude 派生)
- FR-004: DimensionScopePanel UI (wildcard/exclude 复选框 + _ui_hint 字段)
- FR-005: 多角色 Union 防冲突校验 (PM 选项 C: 禁止同时出现 wildcard + exclude)
- FR-006: /api/v2/_feature_flags 端点
- FR-007: 审计日志 (wildcard_enabled/disabled, exclude_set/unset)
- FR-008: 诊断端点扩展 (dim_scope 统计 + conflict_users)
- FR-009: API 向后兼容 (_ui_hint 字段 + 通配符响应)
- FR-010: 仅 admin 限制 (wildcard/exclude functional permission)

测试覆盖 (98/98 通过):
- 单元测试: 24 个 (test_dim_scope_conflict.py)
- e2e 配置: 15 个 (e2e_spec_08_wildcard_exclude.py)
- e2e 读/编辑: 13 个 (e2e_spec_08_read_write_regression.py)
- e2e 全权限: 16 个 (e2e_spec_08_permission_regression.py)
- e2e ValueHelp: 14 个 (e2e_spec_08_value_help_regression.py)
- e2e Parent/Children: 16 个 (e2e_spec_08_parent_children_derivation.py)

测试用户覆盖: admin, wyonghui(10006), wyonghui2(10007), wyonghui3(10008), wyonghui4(10009), DEMO(10010)

PM 决策: 选项 C (禁止同一用户的所有角色同时出现 * 通配和 exclude)
行业最佳实践: SAP PFCG + Salesforce View All Data 思路"
```

---

## 步骤 5: Push 到 remote (如 PM 同意)

```bash
cd d:\filework\worktrees\release-prep
git push origin release/pre-2026-06-29
```

---

## 步骤 6: Promote 到 main (需 PM 审批)

### 选项 A: 创建 PR (推荐, 走审计)

```bash
cd d:\filework\worktrees\release-prep
gh pr create --base main --head release/pre-2026-06-29 \
  --title "[Spec 08] 维度范围通配与排除功能" \
  --body "## Spec 08 完整实施

### 实现 10 FR + 4 NFR + 3 IF + 3 TR

**核心文件 (13 个)**:
- meta/services/dimension_scope_engine.py (90 处 Spec 08 标记)
- meta/core/interceptors/write_scope_interceptor.py (49 处适配)
- meta/api/diagnostics_api.py (27 处 FR-006/008 标记)
- meta/api/role_dimension_scope_api.py (37 处 FR-005/007/009/010 标记)
- 等等

**新增测试 (6 个, 98/98 通过)**:
- test_dim_scope_conflict.py: 24/24
- e2e_spec_08_wildcard_exclude.py: 15/15
- e2e_spec_08_read_write_regression.py: 13/13
- e2e_spec_08_permission_regression.py: 16/16
- e2e_spec_08_value_help_regression.py: 14/14
- e2e_spec_08_parent_children_derivation.py: 16/16

**文档**:
- docs/spec_权限体系升级/08_dimension_scope_wildcard_exclude.md (600+ 行, 54 处 FR/PM 标记)
- docs/spec_权限体系升级/PROMOTION_CHECKLIST.md
- docs/auth/write-scope-interceptor.md (v2.2 升级, 39 处)
- docs/permission-config-optimization.md (附录, 38 处)

### PM 决策

- 选项 C: 禁止同一用户的所有角色同时出现 * 通配和 exclude
- 行业最佳实践: SAP PFCG + Salesforce View All Data 思路

### 验证方法

1. 单测: \`python -m pytest meta/tests/test_dim_scope_conflict.py -v\`
2. e2e: \`python meta/tests/e2e_spec_08_wildcard_exclude.py\` (需后端在 3011)
3. 所有 6 个测试脚本 100% 通过

### Promote 后验证

\`\`\`bash
curl http://localhost:3011/api/v2/_feature_flags
# 期望: {\"dim_scope_wildcard_enabled\":true,\"dim_scope_exclude_enabled\":true}
\`\`\`

### 回滚方案

\`\`\`bash
# 1. 关闭 feature flag (无需重启服务)
#    环境变量: DIM_SCOPE_WILDCARD_ENABLED=false
# 2. git revert <commit-hash>
# 3. 注: 无 schema 迁移, 无需 DB 回滚
\`\`\`"
```

### 选项 B: 本地 squash merge (如果 PM 同意跳过 PR)

```bash
cd d:\filework
git checkout main
git pull origin main
git merge --squash release/pre-2026-06-29
git commit -m "[Spec 08] Promote from release/pre-2026-06-29"
git tag -a v2.2.0-spec08 -m "Spec 08 维度范围通配与排除功能"
git push origin main
git push origin v2.2.0-spec08
```

---

## 完成清单 (供 PM 逐项打勾)

- [ ] 步骤 1: Stage 核心代码 (13 文件)
- [ ] 步骤 2: Stage 新增测试 (6 文件)
- [ ] 步骤 3: Stage spec + 文档 (4 文件)
- [ ] 步骤 4: Commit
- [ ] 步骤 5: Push 到 remote (可选)
- [ ] 步骤 6: Promote (选项 A 或 B)

---

## 我会用 Read 验证

执行完成后, 我会读以下文件确认成功:

1. **HEAD log**:
   `D:/filework/excel-to-diagram/.git/worktrees/release-prep-worktree/logs/HEAD`
   - 期望最后一行包含 "commit: [Spec 08]"

2. **HEAD SHA**:
   `D:/filework/excel-to-diagram/.git/worktrees/release-prep-worktree/refs/heads/release/pre-2026-06-29`
   - 期望 SHA 变化

3. **origin/main SHA** (若 push):
   `D:/filework/excel-to-diagram/.git/refs/remotes/origin/main`
   - 期望 SHA 变化

4. **PR URL** (若选项 A):
   `https://github.com/wyonghui123/excel-to-diagram/pull/<N>`

---

生成时间: 2026-07-22 17:30
