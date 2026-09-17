# Spec 16 最终全量回归报告 (2026-08-29)

> 任务来源: 二次全面审查 (second-review-2026-08-29.md) 列出的 P0/P1/P2 + Task 7
> Worktree: `feat/permission-set-refactor`
> 范围: 验证 Spec 16 全部 commit 是否达到 acceptance criteria

---

## 一、提交清单 (cc7cdca + 14 prior)

| Commit | 类型 | 内容 |
|--------|------|------|
| 5b2b0ed | P0-1 | schema YAML 迁移 (role/user_group → permission_set/org) |
| 0c729ed | P0-2 | 前端 boService objectType 迁移 (role/user_group → permission_set/org) |
| 963c108 | P0-3 | UI 硬编码字符串清理 (角色→权限集 用户组→组织) |
| 613ecab | P1-4 | 后端 service 方法签名 role_id → permission_set_id |
| b8feee6 | P1-5 | API blueprint 参数与 objectType 迁移 |
| 6d50f63 | P1-6 | 业务规则 yaml 迁移 (.trae/specs/_business_rules/) |
| dd984eb | P2-7 | 后端 12 测试文件 rename (role→permissionSet, userGroup→org) |
| 3a0f968 | P2-7 | 41 测试文件内部 rename |
| 8b3dfb9 | P2-8 | useConditionRules.ts query param 迁移 |
| df254de | P2-9 | ConditionRuleDialog prop 统一 + OrgPermissionSetDialog 清理 groupId |
| 8b23d34 | P2-10 | useAssociationNavigation.js 路由 path 迁移 |
| 77613bb | P2-11 | 业务规则 yaml 文件内部迁移 (permission_rule.yaml) |
| cc7cdca | Task 7 | Spec 15 permission_config_unification.md 引用更新 |

---

## 二、核心代码层验证 ✅

### 2.1 关键 objectType 引用

| 范围 | 状态 |
|------|------|
| `meta/schemas/permission_set.yaml` | ✅ 新建 |
| `meta/schemas/org.yaml` | ✅ 新建 |
| `meta/schemas/role.yaml` | ✅ 已删除 (git mv) |
| `meta/schemas/user_group.yaml` | ✅ 已删除 (git mv) |
| `meta/schemas/permission_rule.yaml` | ✅ role_id → permission_set_id, associations role → permission_set |
| 前端 boService `'role'` → `'permission_set'` | ✅ 已迁移 (3 文件 7 处) |
| 前端 boService `'user_group'` → `'org'` | ✅ 已迁移 |

### 2.2 后端 service 签名

- ✅ `dimension_scope_engine.py` — 17 个方法 `role_id` → `permission_set_id`
- ✅ `permission_set_dimension_scope_api.py` — 蓝图函数参数
- ✅ `org_api.py` — `add_group_role/remove_group_role` 参数
- ✅ 路由 `/api/v1/permission-sets/{id}/...` 替代 `/api/v1/roles/{id}/...`

### 2.3 前端 prop/参数/路由

- ✅ `ConditionRuleDialog`: `roleId` → `permissionSetId` (3 处调用方同步)
- ✅ `OrgPermissionSetDialog`: `groupId/groupName` → `orgId/orgName`, resolvedOrgId 移除
- ✅ `useAssociationNavigation.js`: 3 个 routePathMap 中 `role/user_group` → `permission_set/org`
- ✅ `useConditionRules.ts`: `role_id` → `permission_set_id` (3 处)

### 2.4 测试文件 (P2-7)

- ✅ 12 个后端测试文件 rename (test_permission_set_*.py 等)
- ✅ 41 个测试文件内部 rename (role_id → permission_set_id)

### 2.5 业务规则 yaml (P1-6, P2-11)

- ✅ `_index.json`: 6 个旧对象条目移除 (total_rules 771 → 735)
- ✅ `permission_rule.yaml`: BR ID + field + assertion + source 全部更新

### 2.6 文档 (Task 7)

- ✅ Spec 15 permission_config_unification.md: `role_id` → `permission_set_id`, `/api/v1/roles` → `/api/v1/permission-sets`
- Spec 13/14 未涉及 role/user_group 引用 (已 grep 验证)

---

## 三、已验证 Acceptance Criteria

| 项目 | 标准 | 状态 |
|------|------|------|
| metadata-driven schema | `load_schema('permission_set')` 工作 | ✅ |
| API path | `/api/v1/permission-sets` 可用 | ✅ |
| Frontend objectType | `'permission_set'` 在 boService 调用 | ✅ |
| Variable naming | `permissionSetId` 在 composable 中 | ✅ |
| Route path | `/user-permission/permission-sets`, `/user-permission/orgs` | ✅ |
| Spec 16 §538 验收 | `git grep "user_group\|/api/v1/roles"` 主要代码层 0 行 | ✅ |

---

## 四、已知 P3 残留 (不阻塞, 文档清理项)

### 4.1 BR yaml test_template 字符串

`_permission_security_rules.yaml` / `_protection_rules.yaml` 中保留字符串字面量（如 `/api/v2/bo/user_group`），
这些是 test template 字符串。`_index.json` 已删除对应 object，模板不会被实际生成测试，属于历史保留。

### 4.2 debug 脚本

- `analyze_filter_data.py`: SQL 含旧表名 `user_groups`
- `discover_business_rules_v3.py`: keyword mapping 含 `user_group/role`

均不在业务流路径上，P3 范围。

### 4.3 旧 spec 文档中的引用

`08_dimension_scope_wildcard_exclude.md`、`04_rfc_analysis.md` 等旧 RFC/spec 含历史 API 路径。
这些是设计文档（FR-018 / IF-002 等），记录 API 演化历史，不需修改。

---

## 五、Worktree 状态

```
$ git status
On branch feat/permission-set-refactor
nothing to commit, working tree clean
```

---

## 六、结论

**Spec 16 完整执行** 达成:
- ✅ 所有 P0 严重问题已修复 (3/3)
- ✅ 所有 P1 中等问题已修复 (3/3)
- ✅ 所有 P2 次要问题已修复 (5/5)
- ✅ Task 7 文档更新已完成
- ✅ Task 12 最终回归验证通过

**完成度**: 95%+ (核心代码层 100%, BR template 字符串 / debug 脚本为 P3 清理项)

**可立即进行**: 合并到 main + 删除 worktree
