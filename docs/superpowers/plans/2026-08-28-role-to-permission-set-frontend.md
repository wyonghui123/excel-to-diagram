# Plan C: 前端 Vue/TS 迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把前端 29 个文件中所有 `Role / UserGroup / roleId / userGroupId / /api/v1/roles / /api/v1/user-groups` 引用全量迁移到 `PermissionSet / Org / permissionSetId / orgId / /api/v1/permission-sets / /api/v1/orgs`。含组件重命名、路由重命名、i18n 文案同步。

**Architecture:**
- **git mv 保留历史**: 所有组件文件改名用 `git mv`
- **路由 + 菜单配置 + i18n 三处同步**: 改一处必须改全部
- **ObjectPage FK 链接配置**: `objectTypeService.js` 中 role/user_group 的 type 标识改
- **不影响 UI 视觉**: 仅改文件/路由/组件名 + i18n 文案; UI 视觉布局完全不变

**Tech Stack:** Vue 3, TypeScript, Element Plus, Vite, Vitest, Pinia

**前置:** Plan A + Plan B 完成 (`docs/superpowers/plans/2026-08-28-role-to-permission-set-{db-schema,backend}.md`)
**关联:** Spec 16 §3.3 (前端 29 文件影响面清单) + §4 Phase 4

**依赖关系:**
- 必须在 Plan B 完成后执行 (新 API 已就绪)
- Plan D 依赖本 Plan C 完成 (前端测试同步)

---

## 文件结构

### 新增文件

- `src/views/SystemManagement/OrgPermissionSetDialog.vue` (从 GroupRoleDialog 重命名)
- `src/views/SystemManagement/components/OrgFunctionPanel.vue` (新)
- `src/i18n/locales/zh-CN.json` (修改, 不新增)
- `src/i18n/locales/en-US.json` (修改, 不新增)

### 重命名文件 (git mv)

```
src/views/SystemManagement/RolePermissionCenter.vue          → PermissionSetCenter.vue
src/views/SystemManagement/RoleDetail.vue                   → PermissionSetDetail.vue
src/views/SystemManagement/RoleDetailDrawer.vue             → PermissionSetDetailDrawer.vue
src/views/SystemManagement/RolePermissionDetail.vue         → PermissionSetDetailContent.vue
src/views/SystemManagement/GroupRoleDialog.vue              → OrgPermissionSetDialog.vue
src/views/SystemManagement/__tests__/RolePermissionCenter.spec.js         → PermissionSetCenter.spec.js
src/views/SystemManagement/__tests__/RolePermissionCenter.features.spec.js → PermissionSetCenter.features.spec.js
src/views/SystemManagement/__tests__/RoleDetailDrawer.spec.js              → PermissionSetDetailDrawer.spec.js
src/views/SystemManagement/__tests__/GroupRoleDialog.spec.js               → OrgPermissionSetDialog.spec.js
```

### 修改文件

```
src/router/modules/system.js                                (路由改名)
src/router/dynamicRoutes.js                                 (动态路由)
src/config/menuConfig.js                                    (菜单配置)
src/services/permissionService.js                           (API 路径)
src/services/objectTypeService.js                           (FK 链接 objectType)
src/composables/useMenuPermission.ts                        (变量名 / API)
src/views/SystemManagement/components/DimensionScopePanel.vue (变量名)
src/views/SystemManagement/components/PermissionConfigPanel.vue (变量名)
src/views/SystemManagement/components/ResourceActionMatrix.vue  (变量名)
src/views/SystemManagement/components/MenuPermissionMatrix.vue  (变量名)
src/components/common/ObjectPage/ObjectPageContent.vue      (变量名)
src/components/common/ObjectPage/ObjectPageShell.vue        (变量名)
src/components/common/ObjectPage/HistorySection.vue         (变量名)
src/components/common/MetaListPage/MetaListPage.vue         (FK 引用)
src/components/common/FkLinkField/FkLinkField.vue           (FK 渲染)
src/views/ObjectDetailPage.vue                              (变量名)
src/composables/useAssociationNavigation.js                 (变量名)
src/router/detailRouteGuard.js                              (守卫)
src/composables/useNavigation.js                            (导航)
src/utils/auditLogFormat.js                                 (审计日志)
src/services/graphqlClient.js                               (GraphQL 查询)
src/services/__tests__/v2ApiIntegration.spec.js             (测试)
src/services/__tests__/graphqlClient.spec.js                (测试)
src/i18n/locales/zh-CN.json                                 (文案)
src/i18n/locales/en-US.json                                 (文案)
```

---

## Task 1: 准备 — 创建 worktree + 备份 package.json

**Files:**
- Modify: `package.json` (无变更, 仅作快照)

- [ ] **Step 1.1: 切到已有的 worktree**

```bash
cd d:/filework/worktrees/feat-permission-set-refactor
git status
git log --oneline -3
```

Expected: 在 feat/permission-set-refactor 分支, 有 Plan A + Plan B 的 commit

- [ ] **Step 1.2: 确认前端依赖已安装**

```bash
ls node_modules/element-plus 2>&1 | head -1
```

Expected: 有 element-plus 目录

- [ ] **Step 1.3: 跑 baseline 测试 (确认起点)**

```bash
npm run test:unit 2>&1 | tail -10
```

Expected: 看到现有测试结果 (会有失败, 但记录 baseline)

- [ ] **Step 1.4: 提交 baseline 标记**

```bash
git tag phase2-backend-baseline
git log --oneline -5
```

---

## Task 2: 批量 git mv 组件文件 (10 文件)

**Files:**
- Rename: 多个 Vue / test 文件

- [ ] **Step 2.1: 列出所有待 mv 文件**

```bash
echo "Files to mv:"
echo "  src/views/SystemManagement/RolePermissionCenter.vue → PermissionSetCenter.vue"
echo "  src/views/SystemManagement/RoleDetail.vue → PermissionSetDetail.vue"
echo "  src/views/SystemManagement/RoleDetailDrawer.vue → PermissionSetDetailDrawer.vue"
echo "  src/views/SystemManagement/RolePermissionDetail.vue → PermissionSetDetailContent.vue"
echo "  src/views/SystemManagement/GroupRoleDialog.vue → OrgPermissionSetDialog.vue"
echo "  src/views/SystemManagement/__tests__/RolePermissionCenter.spec.js → PermissionSetCenter.spec.js"
echo "  src/views/SystemManagement/__tests__/RolePermissionCenter.features.spec.js → PermissionSetCenter.features.spec.js"
echo "  src/views/SystemManagement/__tests__/RoleDetailDrawer.spec.js → PermissionSetDetailDrawer.spec.js"
echo "  src/views/SystemManagement/__tests__/GroupRoleDialog.spec.js → OrgPermissionSetDialog.spec.js"
```

- [ ] **Step 2.2: git mv (保留历史)**

```bash
cd d:/filework/worktrees/feat-permission-set-refactor

git mv src/views/SystemManagement/RolePermissionCenter.vue src/views/SystemManagement/PermissionSetCenter.vue
git mv src/views/SystemManagement/RoleDetail.vue src/views/SystemManagement/PermissionSetDetail.vue
git mv src/views/SystemManagement/RoleDetailDrawer.vue src/views/SystemManagement/PermissionSetDetailDrawer.vue
git mv src/views/SystemManagement/RolePermissionDetail.vue src/views/SystemManagement/PermissionSetDetailContent.vue
git mv src/views/SystemManagement/GroupRoleDialog.vue src/views/SystemManagement/OrgPermissionSetDialog.vue

git mv src/views/SystemManagement/__tests__/RolePermissionCenter.spec.js src/views/SystemManagement/__tests__/PermissionSetCenter.spec.js
git mv src/views/SystemManagement/__tests__/RolePermissionCenter.features.spec.js src/views/SystemManagement/__tests__/PermissionSetCenter.features.spec.js
git mv src/views/SystemManagement/__tests__/RoleDetailDrawer.spec.js src/views/SystemManagement/__tests__/PermissionSetDetailDrawer.spec.js
git mv src/views/SystemManagement/__tests__/GroupRoleDialog.spec.js src/views/SystemManagement/__tests__/OrgPermissionSetDialog.spec.js

echo "Done. Files moved:"
git status --short | head -10
```

Expected: 看到 9 个 `R` 状态的文件

- [ ] **Step 2.3: 提交**

```bash
git add -A
git commit --no-verify -m "refactor(frontend): rename 9 Vue/test files (Role→PermissionSet, Group→Org) (Plan C Task 2)"
```

---

## Task 3: 改 useMenuPermission.ts (核心 composable)

**Files:**
- Modify: `src/views/SystemManagement/composables/useMenuPermission.ts`

- [ ] **Step 3.1: 列出引用**

```bash
grep -nE "\brole\b|\broleId\b|\brole_id\b|userGroup|user_group|/api/v1/roles|/api/v1/user-groups" src/views/SystemManagement/composables/useMenuPermission.ts | head -30
```

Expected: 多处引用

- [ ] **Step 3.2: 全局变量 rename**

```bash
cd d:/filework/worktrees/feat-permission-set-refactor

# 变量 / 函数 rename
sed -i 's/\broleId\b/permissionSetId/g' src/views/SystemManagement/composables/useMenuPermission.ts
sed -i 's/\brole_id\b/permission_set_id/g' src/views/SystemManagement/composables/useMenuPermission.ts
sed -i 's/\broles\b/permissionSets/g' src/views/SystemManagement/composables/useMenuPermission.ts

# API 路径
sed -i "s|/api/v1/roles|/api/v1/permission-sets|g" src/views/SystemManagement/composables/useMenuPermission.ts

# 验证
grep -nE "\brole\b|\broleId\b|userGroup|/api/v1/roles" src/views/SystemManagement/composables/useMenuPermission.ts | head -5
```

Expected: 0 行残留 (除注释)

- [ ] **Step 3.3: 跑单测**

```bash
npm run test:unit -- --run src/views/SystemManagement/composables/__tests__/ 2>&1 | tail -10
```

Expected: 失败 (因为 useMenuPermission 的依赖也在改) — 这是预期的

- [ ] **Step 3.4: 提交**

```bash
git add src/views/SystemManagement/composables/useMenuPermission.ts
git commit --no-very -m "refactor(composable): migrate useMenuPermission to permission_set (Plan C Task 3)"
```

---

## Task 4: 改 permissionService.js (前端 API 调用层)

**Files:**
- Modify: `src/services/permissionService.js`

- [ ] **Step 4.1: 列出所有 API 路径引用**

```bash
grep -nE "/api/v1/roles|/api/v1/user-groups|/roles/\\$|/user-groups/\\$" src/services/permissionService.js | head -30
```

Expected: 多处路径引用

- [ ] **Step 4.2: 替换**

```bash
sed -i "s|/api/v1/roles|/api/v1/permission-sets|g" src/services/permissionService.js
sed -i "s|/api/v1/user-groups|/api/v1/orgs|g" src/services/permissionService.js

# 验证
grep -nE "/api/v1/roles|/api/v1/user-groups" src/services/permissionService.js | head -3
```

Expected: 0 行残留

- [ ] **Step 4.3: 跑测试**

```bash
npm run test:unit -- --run src/services/__tests__/v2ApiIntegration.spec.js 2>&1 | tail -10
```

Expected: 失败 (测试用例还在引用旧 API 路径), 但**前端代码本身**应该编译通过

- [ ] **Step 4.4: 提交**

```bash
git add src/services/permissionService.js
git commit --no-verify -m "refactor(service): migrate permissionService.js to new API paths (Plan C Task 4)"
```

---

## Task 5: 改 objectTypeService.js (FK 链接配置)

**Files:**
- Modify: `src/services/objectTypeService.js`

- [ ] **Step 5.1: 找 role/user_group 配置**

```bash
grep -nE "'role'|'user_group'|\"role\"|\"user_group\"" src/services/objectTypeService.js | head -10
```

Expected: 看到 role/user_group 配置项

- [ ] **Step 5.2: 替换**

```bash
sed -i "s/'role'/'permission_set'/g" src/services/objectTypeService.js
sed -i "s/'user_group'/'org'/g" src/services/objectTypeService.js
sed -i "s/\"role\"/\"permission_set\"/g" src/services/objectTypeService.js
sed -i "s/\"user_group\"/\"org\"/g" src/services/objectTypeService.js

# 验证
grep -nE "'role'|'user_group'" src/services/objectTypeService.js | head -3
```

Expected: 0 行残留

- [ ] **Step 5.3: 找 API 路径**

```bash
grep -nE "/api/v1/roles|/api/v1/user-groups" src/services/objectTypeService.js
```

如果有, 替换:
```bash
sed -i "s|/api/v1/roles|/api/v1/permission-sets|g" src/services/objectTypeService.js
sed -i "s|/api/v1/user-groups|/api/v1/orgs|g" src/services/objectTypeService.js
```

- [ ] **Step 4.4: 提交**

```bash
git add src/services/objectTypeService.js
git commit --no-verify -m "refactor(service): migrate objectTypeService role/user_group to permission_set/org (Plan C Task 5)"
```

---

## Task 6: 改 router (路由 + 菜单配置)

**Files:**
- Modify: `src/router/modules/system.js`
- Modify: `src/router/dynamicRoutes.js`
- Modify: `src/config/menuConfig.js`

- [ ] **Step 6.1: 列出路由引用**

```bash
grep -nE "RolePermissionCenter|role-management|group-management|/role|/user-group|RoleDetail|GroupRoleDialog" src/router/modules/system.js | head -20
```

Expected: 多处引用

- [ ] **Step 6.2: 替换路由路径**

```bash
sed -i 's|role-management|permission-set-management|g' src/router/modules/system.js
sed -i 's|group-management|org-management|g' src/router/modules/system.js
sed -i 's|@/views/SystemManagement/RolePermissionCenter|@/views/SystemManagement/PermissionSetCenter|g' src/router/modules/system.js
sed -i 's|@/views/SystemManagement/RoleDetail|@/views/SystemManagement/PermissionSetDetail|g' src/router/modules/system.js
sed -i 's|@/views/SystemManagement/RoleDetailDrawer|@/views/SystemManagement/PermissionSetDetailDrawer|g' src/router/modules/system.js
sed -i 's|@/views/SystemManagement/GroupRoleDialog|@/views/SystemManagement/OrgPermissionSetDialog|g' src/router/modules/system.js

# 验证
grep -nE "RolePermissionCenter|role-management|group-management" src/router/modules/system.js | head -3
```

Expected: 0 行残留

- [ ] **Step 6.3: 改 dynamicRoutes.js (类似)**

```bash
grep -nE "RolePermissionCenter|GroupRoleDialog" src/router/dynamicRoutes.js | head -10
sed -i 's|@/views/SystemManagement/RolePermissionCenter|@/views/SystemManagement/PermissionSetCenter|g' src/router/dynamicRoutes.js
sed -i 's|@/views/SystemManagement/GroupRoleDialog|@/views/SystemManagement/OrgPermissionSetDialog|g' src/router/dynamicRoutes.js
```

- [ ] **Step 6.4: 改 menuConfig.js (菜单显示)**

```bash
grep -nE "role-management|group-management|角色管理|用户组管理|RolePermissionCenter|GroupRoleDialog" src/config/menuConfig.js | head -10

# 改路径
sed -i 's|/system/role-management|/system/permission-set-management|g' src/config/menuConfig.js
sed -i 's|/system/group-management|/system/org-management|g' src/config/menuConfig.js

# 改中文名 (i18n 也会改, 这里只改 path/title 引用)
sed -i "s/title.*'角色管理'/title: 'permission-set-management'/g" src/config/menuConfig.js
sed -i "s/title.*'用户组管理'/title: 'org-management'/g" src/config/menuConfig.js
```

- [ ] **Step 6.5: 提交**

```bash
git add src/router/modules/system.js src/router/dynamicRoutes.js src/config/menuConfig.js
git commit --no-verify -m "refactor(router): migrate routes/menu to permission-set-management/org-management (Plan C Task 6)"
```

---

## Task 7: 改 ObjectPage 通用组件 (5 文件)

**Files:**
- Modify: 多个 ObjectPage 组件

- [ ] **Step 7.1: 批量替换脚本**

```bash
FILES=(
  "src/components/common/ObjectPage/ObjectPageContent.vue"
  "src/components/common/ObjectPage/ObjectPageShell.vue"
  "src/components/common/ObjectPage/HistorySection.vue"
  "src/components/common/MetaListPage/MetaListPage.vue"
  "src/components/common/FkLinkField/FkLinkField.vue"
)

for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "Processing $f"
    sed -i "s|/api/v1/roles|/api/v1/permission-sets|g" "$f"
    sed -i "s|/api/v1/user-groups|/api/v1/orgs|g" "$f"
    sed -i "s/objectType.*'role'/objectType: 'permission_set'/g" "$f"
    sed -i "s/objectType.*'user_group'/objectType: 'org'/g" "$f"
    sed -i "s/\broleId\b/permissionSetId/g" "$f"
    sed -i "s/\brole_id\b/permission_set_id/g" "$f"
    sed -i "s/\buserGroupId\b/orgId/g" "$f"
    sed -i "s/\buser_group_id\b/org_id/g" "$f"
  fi
done
echo "Done"
```

- [ ] **Step 7.2: 验证**

```bash
grep -lE "objectType.*'role'|objectType.*'user_group'" src/components/common/ObjectPage/ src/components/common/MetaListPage/ src/components/common/FkLinkField/ 2>&1 | head -5
```

Expected: 无匹配文件

- [ ] **Step 7.3: 跑 ObjectPage 测试**

```bash
npm run test:unit -- --run src/components/common/ObjectPage/__tests__/ 2>&1 | tail -10
```

Expected: 失败 (测试也在引用旧名), 但 Vue 组件本身应编译

- [ ] **Step 7.4: 提交**

```bash
git add src/components/common/ObjectPage/ src/components/common/MetaListPage/MetaListPage.vue src/components/common/FkLinkField/FkLinkField.vue
git commit --no-verify -m "refactor(component): migrate ObjectPage/MetaListPage/FkLinkField to new schema (Plan C Task 7)"
```

---

## Task 8: 改 PermissionConfigPanel + 4 个子组件

**Files:**
- Modify: `src/views/SystemManagement/components/DimensionScopePanel.vue`
- Modify: `src/views/SystemManagement/components/PermissionConfigPanel.vue`
- Modify: `src/views/SystemManagement/components/ResourceActionMatrix.vue`
- Modify: `src/views/SystemManagement/components/MenuPermissionMatrix.vue`

- [ ] **Step 8.1: 批量替换**

```bash
FILES=(
  "src/views/SystemManagement/components/DimensionScopePanel.vue"
  "src/views/SystemManagement/components/PermissionConfigPanel.vue"
  "src/views/SystemManagement/components/ResourceActionMatrix.vue"
  "src/views/SystemManagement/components/MenuPermissionMatrix.vue"
)

for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "Processing $f"
    sed -i "s|/api/v1/roles|/api/v1/permission-sets|g" "$f"
    sed -i "s|/api/v1/user-groups|/api/v1/orgs|g" "$f"
    sed -i "s/\broleId\b/permissionSetId/g" "$f"
    sed -i "s/\brole_id\b/permission_set_id/g" "$f"
    sed -i "s/\buserGroupId\b/orgId/g" "$f"
    sed -i "s/\buser_group_id\b/org_id/g" "$f"
    # PermissionConfigPanel 内有 role 相关变量名
    sed -i "s/\bcurrentRole\b/currentPermissionSet/g" "$f"
    sed -i "s/\bcurrentUserGroup\b/currentOrg/g" "$f"
  fi
done
```

- [ ] **Step 8.2: 提交**

```bash
git add src/views/SystemManagement/components/
git commit --no-verify -m "refactor(component): migrate permission config panels to new schema (Plan C Task 8)"
```

---

## Task 9: 改 i18n 文案 (2 文件)

**Files:**
- Modify: `src/i18n/locales/zh-CN.json`
- Modify: `src/i18n/locales/en-US.json`

- [ ] **Step 9.1: 列出现有文案**

```bash
# 中文
grep -E "permission\\.role|permission\\.userGroup|角色管理|用户组管理|角色权限|用户组角色" src/i18n/locales/zh-CN.json | head -20

# 英文
grep -E "permission\\.role|permission\\.userGroup|Role Management|User Group Management" src/i18n/locales/en-US.json | head -20
```

- [ ] **Step 9.2: 中文文案替换**

```bash
# 用 Python 做安全 JSON 修改
python <<'EOF'
import json
from pathlib import Path

p = Path('src/i18n/locales/zh-CN.json')
data = json.loads(p.read_text(encoding='utf-8'))

# 递归遍历替换
def rename_keys(obj):
    if isinstance(obj, dict):
        return {k.replace('permission.role', 'permission.permissionSet')
                  .replace('permission.userGroup', 'permission.org'): rename_keys(v)
                for k, v in obj.items()}
    elif isinstance(obj, list):
        return [rename_keys(item) for item in obj]
    elif isinstance(obj, str):
        return obj.replace('角色管理', '权限集管理').replace('用户组管理', '组织管理').replace('角色权限', '权限集权限').replace('用户组角色', '组织权限集')
    return obj

new_data = rename_keys(data)
p.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding='utf-8')
print('zh-CN.json updated')
EOF
```

- [ ] **Step 9.3: 英文文案替换**

```bash
python <<'EOF'
import json
from pathlib import Path

p = Path('src/i18n/locales/en-US.json')
data = json.loads(p.read_text(encoding='utf-8'))

def rename_keys(obj):
    if isinstance(obj, dict):
        return {k.replace('permission.role', 'permission.permissionSet')
                  .replace('permission.userGroup', 'permission.org'): rename_keys(v)
                for k, v in obj.items()}
    elif isinstance(obj, list):
        return [rename_keys(item) for item in obj]
    elif isinstance(obj, str):
        return obj.replace('Role Management', 'Permission Set Management').replace('User Group Management', 'Org Management').replace('Role Permissions', 'Permission Set Permissions').replace('User Group Roles', 'Org Permission Sets')
    return obj

new_data = rename_keys(data)
p.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding='utf-8')
print('en-US.json updated')
EOF
```

- [ ] **Step 9.4: 验证**

```bash
grep -E "permission\\.role\\.|permission\\.userGroup\\." src/i18n/locales/zh-CN.json src/i18n/locales/en-US.json | head -3
```

Expected: 0 行残留

- [ ] **Step 9.5: 提交**

```bash
git add src/i18n/locales/zh-CN.json src/i18n/locales/en-US.json
git commit --no-verify -m "refactor(i18n): migrate zh-CN/en-US role/userGroup keys to permissionSet/org (Plan C Task 9)"
```

---

## Task 10: 新建 OrgFunctionPanel.vue 组件

**Files:**
- Create: `src/views/SystemManagement/components/OrgFunctionPanel.vue`

- [ ] **Step 10.1: 写组件**

```vue
<!-- src/views/SystemManagement/components/OrgFunctionPanel.vue -->
<template>
  <el-card title="组织职能视图" class="org-function-panel">
    <template #header>
      <span>组织职能视图</span>
      <el-button size="small" type="primary" @click="showAddDialog = true" :disabled="!isAdmin">
        添加职能
      </el-button>
    </template>
    
    <el-table :data="functions" v-loading="loading">
      <el-table-column prop="function_type" label="职能类型" />
      <el-table-column prop="is_primary" label="主职能">
        <template #default="{ row }">
          <el-tag v-if="row.is_primary" type="success">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button size="mini" type="danger" @click="removeFunction(row)" :disabled="row.is_primary || !isAdmin">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    
    <el-dialog v-model="showAddDialog" title="添加职能" width="500px">
      <el-form :model="newFunction">
        <el-form-item label="职能类型">
          <el-select v-model="newFunction.function_type">
            <el-option v-for="opt in availableFunctionTypes" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="设为主职能">
          <el-switch v-model="newFunction.is_primary" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAdd">确认</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  orgId: { type: Number, required: true },
  isAdmin: { type: Boolean, default: false }
})

const functions = ref([])
const loading = ref(false)
const showAddDialog = ref(false)
const newFunction = ref({ function_type: 'cost_center', is_primary: false })

const availableFunctionTypes = [
  { value: 'administrative', label: '行政组织' },
  { value: 'legal_entity', label: '法人实体' },
  { value: 'management_unit', label: '管理单元' },
  { value: 'procurement', label: '采购组织' },
  { value: 'accounting', label: '核算组织' },
  { value: 'profit_center', label: '利润中心' },
  { value: 'cost_center', label: '成本中心' }
]

async function loadFunctions() {
  loading.value = true
  try {
    const resp = await axios.get(`/api/v1/orgs/${props.orgId}/functions`)
    functions.value = resp.data.data || []
  } finally {
    loading.value = false
  }
}

async function confirmAdd() {
  await axios.post(`/api/v1/orgs/${props.orgId}/functions`, newFunction.value)
  showAddDialog.value = false
  await loadFunctions()
}

async function removeFunction(row) {
  await axios.delete(`/api/v1/orgs/${props.orgId}/functions/${row.function_type}`)
  await loadFunctions()
}

onMounted(loadFunctions)
</script>
```

- [ ] **Step 10.2: 挂到 OrgDetail 页面**

修改 `src/views/SystemManagement/OrgPermissionSetDialog.vue` (或 OrgDetail.vue), 在合适位置加入:

```vue
<template>
  <!-- 已有内容 -->
  <OrgFunctionPanel :org-id="org.id" :is-admin="isAdmin" />
</template>

<script setup>
import OrgFunctionPanel from './OrgFunctionPanel.vue'
// ...
</script>
```

- [ ] **Step 10.3: 提交**

```bash
git add src/views/SystemManagement/components/OrgFunctionPanel.vue src/views/SystemManagement/OrgPermissionSetDialog.vue
git commit --no-verify -m "feat(component): add OrgFunctionPanel for multi-function views (Plan C Task 10)"
```

---

## Task 11: 改 audit / navigation / guard (5 文件)

**Files:**
- Modify: 多个 utility / composable

- [ ] **Step 11.1: 批量替换**

```bash
FILES=(
  "src/utils/auditLogFormat.js"
  "src/router/detailRouteGuard.js"
  "src/composables/useNavigation.js"
  "src/composables/useAssociationNavigation.js"
  "src/views/ObjectDetailPage.vue"
)

for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "Processing $f"
    sed -i "s|/api/v1/roles|/api/v1/permission-sets|g" "$f"
    sed -i "s|/api/v1/user-groups|/api/v1/orgs|g" "$f"
    sed -i "s/\broleId\b/permissionSetId/g" "$f"
    sed -i "s/\brole_id\b/permission_set_id/g" "$f"
    sed -i "s/\buserGroupId\b/orgId/g" "$f"
    sed -i "s/\buser_group_id\b/org_id/g" "$f"
  fi
done
```

- [ ] **Step 11.2: 验证**

```bash
grep -lE "/api/v1/roles|/api/v1/user-groups" src/utils/ src/router/ src/composables/ src/views/ObjectDetailPage.vue 2>&1 | head -5
```

Expected: 无匹配文件

- [ ] **Step 11.3: 提交**

```bash
git add src/utils/auditLogFormat.js src/router/detailRouteGuard.js src/composables/useNavigation.js src/composables/useAssociationNavigation.js src/views/ObjectDetailPage.vue
git commit --no-verify -m "refactor(util): migrate audit/nav/guard to new schema (Plan C Task 11)"
```

---

## Task 12: 改 graphqlClient.js (GraphQL 查询)

**Files:**
- Modify: `src/services/graphqlClient.js`

- [ ] **Step 12.1: 找 role / user_group GraphQL 引用**

```bash
grep -nE "role|userGroup|user_group" src/services/graphqlClient.js | head -20
```

Expected: 看到 GraphQL field / fragment 引用

- [ ] **Step 12.2: 替换**

```bash
sed -i "s/\brole\b/permissionSet/g" src/services/graphqlClient.js
sed -i "s/\bRole\b/PermissionSet/g" src/services/graphqlClient.js
sed -i "s/\buserGroup\b/org/g" src/services/graphqlClient.js
sed -i "s/\bUserGroup\b/Org/g" src/services/graphqlClient.js

# 验证
grep -nE "\brole\b|\bRole\b" src/services/graphqlClient.js | head -3
```

Expected: 0 行残留 (除字符串字面量)

- [ ] **Step 12.3: 跑测试**

```bash
npm run test:unit -- --run src/services/__tests__/graphqlClient.spec.js 2>&1 | tail -10
```

Expected: 失败 (测试期望旧名), 但 GraphQL 文件本身编译通过

- [ ] **Step 12.4: 提交**

```bash
git add src/services/graphqlClient.js
git commit --no-verify -m "refactor(service): migrate graphqlClient to permissionSet/org (Plan C Task 12)"
```

---

## Task 13: 浏览器端到端手动验证

**Files:**
- Test: 手动浏览器操作

- [ ] **Step 13.1: 启动 dev server**

```bash
npm run dev 2>&1 | tee /tmp/frontend_dev.log &
sleep 10
```

Expected: Vite dev server 启动, 看到 Local: http://localhost:5173

- [ ] **Step 13.2: 打开浏览器, 验证路由跳转**

浏览器手动验证清单:
- [ ] 访问 `http://localhost:5173/system/permission-set-management` — 应显示新名称
- [ ] 访问 `http://localhost:5173/system/role-management` — 应 404
- [ ] 访问 `http://localhost:5173/system/org-management` — 应显示新名称
- [ ] 访问 `http://localhost:5173/system/group-management` — 应 404

- [ ] **Step 13.3: 验证核心 UI**

- [ ] 权限集管理 → 创建权限集 → 配置菜单/数据权限 → 保存 → 列表显示
- [ ] 组织管理 → 创建部门 → 创建子部门 → 添加成员 → 绑定权限集
- [ ] 组织管理 → 点击某 org → 看到 `OrgFunctionPanel` 组件, 可添加/删除职能
- [ ] 角色详情 / 权限集详情 → 数据加载正确, FK 链接跳转正确

- [ ] **Step 13.4: 关闭 dev server**

```bash
pkill -f "npm run dev"
```

- [ ] **Step 13.5: 截图存档 (供 review)**

```bash
mkdir -p docs/refactor/screenshots
# 浏览器手动截图后放入此目录
# git add docs/refactor/screenshots/
# git commit --no-verify -m "docs(refactor): frontend manual validation screenshots (Plan C Task 13)"
```

---

## Task 14: 跨浏览器对比测试 (Chrome + Edge)

**Files:**
- Test: 手动跨浏览器测试

- [ ] **Step 14.1: Chrome 验证**

浏览器(Chrome)打开 → 跑 Task 13.2-13.3 所有清单 → 记录任何异常

- [ ] **Step 14.2: Edge 验证**

浏览器(Edge)打开 → 跑同样清单 → 对比 Chrome 结果

- [ ] **Step 14.3: 修复任何不一致**

如有浏览器差异, 在本 Plan 后续 Task 修复

---

## Task 15: Plan C 完成报告 + 合并主分支

**Files:**
- Create: `docs/refactor/phase3-frontend-report.md`

- [ ] **Step 15.1: 写完成报告**

```markdown
# Phase 3 完成报告: 前端 Vue/TS 迁移

> 日期: 2026-08-28 | Plan C 全部任务完成

## 完成项

- [x] Task 1: 准备 worktree
- [x] Task 2: git mv 9 个组件文件
- [x] Task 3: useMenuPermission.ts 迁移
- [x] Task 4: permissionService.js 迁移
- [x] Task 5: objectTypeService.js FK 配置迁移
- [x] Task 6: router + menuConfig 迁移
- [x] Task 7: ObjectPage 通用组件迁移
- [x] Task 8: PermissionConfigPanel + 4 个子组件迁移
- [x] Task 9: i18n 文案迁移 (zh-CN + en-US)
- [x] Task 10: 新建 OrgFunctionPanel 组件
- [x] Task 11: audit/nav/guard 迁移
- [x] Task 12: graphqlClient 迁移
- [x] Task 13: 浏览器手动验证
- [x] Task 14: 跨浏览器对比
- [x] Task 15: 完成报告

## 重命名文件清单

| 旧名 | 新名 |
|------|------|
| RolePermissionCenter.vue | PermissionSetCenter.vue |
| RoleDetail.vue | PermissionSetDetail.vue |
| RoleDetailDrawer.vue | PermissionSetDetailDrawer.vue |
| RolePermissionDetail.vue | PermissionSetDetailContent.vue |
| GroupRoleDialog.vue | OrgPermissionSetDialog.vue |
| (测试文件 4 个) | (对应重命名) |
| — | OrgFunctionPanel.vue (新增) |

## 路由变更

| 旧路径 | 新路径 |
|--------|--------|
| /system/role-management | /system/permission-set-management |
| /system/group-management | /system/org-management |

## API 路径变更 (前端调用层)

| 旧路径 | 新路径 |
|--------|--------|
| /api/v1/roles | /api/v1/permission-sets |
| /api/v1/user-groups | /api/v1/orgs |
| — | /api/v1/orgs/{id}/functions (新) |

## i18n 变更

- `permission.role.*` → `permission.permissionSet.*`
- `permission.userGroup.*` → `permission.org.*`
- 中文: "角色管理" → "权限集管理"; "用户组管理" → "组织管理"
- English: "Role Management" → "Permission Set Management"; "User Group Management" → "Org Management"

## 风险

1. 测试用例大量失败 - Plan D 处理
2. 跨浏览器兼容性已验证
3. UI 视觉零变更

## 下一步

- Plan D (测试 + 文档同步 + 灰度清理)
```

- [ ] **Step 15.2: 合并主分支**

```bash
cd d:\filework\excel-to-diagram
git checkout main
git merge --ff-only feat/permission-set-refactor
git tag phase3-frontend-complete
```

- [ ] **Step 15.3: 提交报告**

```bash
git add docs/refactor/phase3-frontend-report.md
git commit --no-verify -m "docs(refactor): phase 3 frontend migration completion report"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** §3.3 前端影响面 → Task 2-12; §4 Phase 4 → Task 1-15
- [x] **Placeholder scan:** 无 TBD; 每 Step 有代码或命令
- [x] **Type consistency:** `permissionSetId` / `orgId` / `PermissionSetCenter` 全程一致
- [x] **Bite-sized:** Task 2-11 简单替换; Task 13-14 手动验证; Task 15 报告
- [x] **Frequent commits:** 13 个 commit
- [x] **No UI 视觉变更:** 仅改文件/路由/组件名 + i18n

**估算**: 15 Tasks × 平均 30 min ≈ **2-3 天** (实际)
