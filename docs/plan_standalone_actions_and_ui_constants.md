# 细化方案：standalone 动作补充 + UI 文本 enum

## 重要说明：membership 与 association 的关系

**membership 就是 association 的一种**，两者是同一个概念的不同表述：

- **association**：技术视角的命名，表示 BO 之间的关联关系
- **membership**：业务视角的命名，表示"成员管理"类型的关联

**当前项目统一使用 `associations` 字段**，所有关系都在其中定义：

```yaml
# user_group.yaml - 成员管理通过 associations.members 定义
associations:
  members:
    actions:
      assign:        # 添加成员
        name: add_member
        label: 添加成员
      unassign:      # 移除成员
        name: remove_member
        label: 移除成员
```

**因此**：
- ❌ 不需要单独的 `membership` 配置字段
- ✅ 从 `associations[*].actions` 中识别 `assign`/`unassign`/`associate`/`dissociate`

---

## 一、standalone 动作补充方案

### 1.1 问题根因

standalone 动作始终为空的根本原因：**数据链路断裂**

```
domain.yaml actions 只有 CRUD (无 associate/export 等)
    ↓
menu_auto_generator._derive_bo_bindings() 只收集到 CRUD actions
    ↓
menu_auto_generator._derive_permissions_from_bindings() 只生成 domain:create/read/update/delete
    ↓
init_menu_permissions.py 也硬编码只有 CRUD permissions
    ↓
menus 表的 required_permissions = ['domain:create', 'domain:read', 'domain:update', 'domain:delete']
    ↓
API 解析 required_permissions → resource_perms['domain'] = {'create','read','update','delete'}
    ↓
STANDALONE_ACTIONS 中的 'associate','dissociate','assign','unassign','export','import','grant','revoke'
    全部不在 resource_perms['domain'] 中
    ↓
standalone_perms = []  →  standalone: []
```

### 1.2 方案选择

| 方案 | 描述 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **A. BO YAML 显式定义** | 在 domain.yaml 的 actions 列表中显式添加 associate/export 等动作定义 | 简单直接，立即生效 | 每个 BO 都要手动添加，重复劳动 | ⭐⭐⭐ |
| **B. menu_auto_generator 自动推导** | 修改 `_derive_bo_bindings()`，根据 BO 的 associations/import_export 配置自动补充 standalone actions | 元数据驱动，自动化 | 需要修改推导逻辑 | ⭐⭐⭐⭐⭐ |
| **C. API 层补充** | 修改 `get_role_unified_permissions` API，额外读取 `_action_groups.yaml` 和 BO 配置来补充 standalone actions | 不影响数据层 | API 逻辑复杂，与数据层不一致 | ⭐⭐ |
| **D. init_menu_permissions 硬编码** | 在 `required_permissions` 中手动补充 standalone 权限编码 | 快速修复 | 硬编码，不可扩展 | ⭐ |

**推荐方案 B**：修改 `menu_auto_generator._derive_bo_bindings()` 自动推导 standalone actions

### 1.3 方案 B 详细设计

#### 1.3.1 修改点

**文件**：`meta/services/menu_auto_generator.py`

**方法**：`_derive_bo_bindings()`

**修改逻辑**：

```python
def _derive_bo_bindings(self, meta_obj: MetaObject, role: str = 'primary',
                        read_only: bool = False) -> List[Dict]:
    """从 BO 推导 bo_bindings，包括 CRUD actions + standalone actions"""
    include_actions = []
    read_suffixes = {'read', 'list', 'export'}

    # 1. 收集 CRUD actions（现有逻辑）
    for action in meta_obj.actions:
        suffix = action.get_permission_suffix()
        if read_only and suffix not in read_suffixes:
            continue
        include_actions.append(suffix)

    # 2. 自动推导 standalone actions（新增逻辑）
    # 2a. 从 associations 推导 associate/dissociate 和 assign/unassign
    if hasattr(meta_obj, 'associations') and meta_obj.associations:
        for assoc in meta_obj.associations:
            assoc_actions = assoc.get('actions', {})
            # 如果 association 定义了 assign/unassign action（如 user_group.members）
            if 'assign' in assoc_actions:
                include_actions.append('assign')
            if 'unassign' in assoc_actions:
                include_actions.append('unassign')
            # 如果 association 定义了 associate/dissociate action
            if 'associate' in assoc_actions:
                include_actions.append('associate')
            if 'dissociate' in assoc_actions:
                include_actions.append('dissociate')

    # 2b. 从 import_export 配置推导 export/import
    if hasattr(meta_obj, 'import_export') and meta_obj.import_export:
        if meta_obj.import_export.get('export_enabled', False):
            include_actions.append('export')
        if meta_obj.import_export.get('import_enabled', False):
            include_actions.append('import')

    # 2c. 从 security 配置推导 grant/revoke
    if hasattr(meta_obj, 'security') and meta_obj.security:
        if meta_obj.security.get('permission_delegation', False):
            include_actions.append('grant')
            include_actions.append('revoke')

    # 3. 去重
    include_actions = list(set(include_actions))

    return [{
        'bo_id': meta_obj.id,
        'role': role,
        'include_actions': include_actions,
    }]
```

#### 1.3.2 BO YAML 配置示例

**domain.yaml 添加配置**：

```yaml
# 启用 export/import
import_export:
  export_enabled: true
  import_enabled: true

# associations 中可定义 associate/dissociate action
associations:
  - name: sub_domain
    type: composition
    # 如果需要独立的关联权限，可定义 actions
    # actions:
    #   associate:
    #     name: add_sub_domain
    #     label: 添加子域
    #   dissociate:
    #     name: remove_sub_domain
    #     label: 移除子域

# 如果有权限委托
security:
  permission_delegation: false  # domain 不支持权限委托
```

**user_group.yaml 示例**（已有配置，无需修改）：

```yaml
# 成员管理（通过 associations.members.actions 定义）
associations:
  members:
    actions:
      assign:
        name: add_member
        label: 添加成员
      unassign:
        name: remove_member
        label: 移除成员

# 权限委托
security:
  permission_delegation: true  # 自动推导 grant/revoke
```

#### 1.3.3 兜底方案：BO YAML 显式声明

如果 BO 不想依赖自动推导，可显式声明：

```yaml
actions:
  - id: domain_create
  - id: domain_read
  - id: domain_update
  - id: domain_delete
  - id: domain_list
  # 显式添加 standalone actions
  - id: domain_export
  - id: domain_import
```

#### 1.3.4 实施步骤

1. **修改 menu_auto_generator.py**
   - 在 `_derive_bo_bindings()` 中添加 standalone actions 推导逻辑

2. **修改 domain.yaml**
   - 添加 `import_export` 配置启用 export/import

3. **重新生成菜单权限**
   - 运行 `python meta/scripts/init_menu_permissions.py` 重新生成菜单数据

4. **验证**
   - 调用 API `/api/v2/roles/22/unified-permissions` 确认 standalone 不为空

### 1.4 预期结果

修改后 API 返回（domain BO）：

```json
{
  "bo_permission_groups": [
    {
      "bo_id": "domain",
      "bo_name": "域",
      "groups": {
        "view": { "granted": true, "source": "auto" },
        "edit": { "granted": true, "source": "auto" },
        "manage": { "granted": true, "source": "auto" }
      },
      "standalone": [
        { "action": "export", "label": "导出", "granted": true, "source": "auto" },
        { "action": "import", "label": "导入", "granted": true, "source": "auto" }
      ]
    }
  ]
}
```

修改后 API 返回（user_group BO）：

```json
{
  "bo_permission_groups": [
    {
      "bo_id": "user_group",
      "bo_name": "用户组",
      "groups": {
        "view": { "granted": true, "source": "auto" },
        "edit": { "granted": true, "source": "auto" },
        "manage": { "granted": true, "source": "auto" }
      },
      "standalone": [
        { "action": "assign", "label": "分配", "granted": true, "source": "auto" },
        { "action": "unassign", "label": "取消分配", "granted": true, "source": "auto" },
        { "action": "grant", "label": "授权", "granted": true, "source": "auto" },
        { "action": "revoke", "label": "撤销", "granted": true, "source": "auto" }
      ]
    }
  ]
}
```

---

## 二、UI 文本 enum 方案

### 2.1 问题分析

当前 UI 文本硬编码在多处：

**MenuPermissionMatrix.vue**：
```typescript
const GROUP_LABELS = { view: '查看', edit: '编辑', manage: '管理' }

function sourceLabel(item) {
  if (item.source === 'exclude') return '排除'
  if (item.source === 'include') return '包含'
  if (item.source === 'auto') return '自动'
  return ''
}

function permSourceLabel(perm) {
  if (perm.source === 'exclude') return '排除'
  if (perm.source === 'include') return '包含'
  if (perm.source === 'auto') return '自动'
  return '未分配'
}
```

**问题**：
1. 文本分散在多个函数中，难以维护
2. 不支持国际化（i18n）
3. 测试时需要硬编码字符串匹配

### 2.2 方案选择

| 方案 | 描述 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **A. TypeScript enum** | 使用 `enum PermissionSourceLabel { Auto = '自动', ... }` | 类型安全 | enum 编译后是双向映射，冗余 | ⭐⭐⭐ |
| **B. 常量对象** | `export const PERMISSION_LABELS = { auto: '自动', ... } as const` | 简单，tree-shaking 友好 | 无类型约束 | ⭐⭐⭐⭐ |
| **C. i18n 国际化** | `t('permission.source.auto')` | 支持多语言 | 需要引入 i18n 框架 | ⭐⭐⭐⭐⭐ |
| **D. 混合方案** | 常量对象 + i18n key | 灵活，可渐进迁移到 i18n | 稍复杂 | ⭐⭐⭐⭐ |

**推荐方案 D**：常量对象 + i18n key（可渐进迁移）

### 2.3 方案 D 详细设计

#### 2.3.1 创建 `permissionConstants.ts`

**位置**：`src/views/SystemManagement/constants/permissionConstants.ts`

```typescript
/**
 * 权限相关常量定义
 * 集中管理 UI 文本，便于维护和国际化迁移
 */

// ==================== 权限来源（source） ====================

/**
 * 权限来源类型
 * - auto: 菜单自动派生
 * - include: 手动包含（grant）
 * - exclude: 手动排除（deny）
 * - '': 未分配
 */
export type PermissionSource = 'auto' | 'include' | 'exclude' | ''

/**
 * 权限来源标签（UI 显示文本）
 */
export const SOURCE_LABELS = {
  auto: '自动',
  include: '包含',
  exclude: '排除',
  none: '未分配',
} as const

/**
 * 权限来源 i18n key（用于国际化迁移）
 */
export const SOURCE_I18N_KEYS = {
  auto: 'permission.source.auto',
  include: 'permission.source.include',
  exclude: 'permission.source.exclude',
  none: 'permission.source.none',
} as const

/**
 * 获取权限来源标签
 */
export function getSourceLabel(source: PermissionSource | 'none'): string {
  return SOURCE_LABELS[source] || ''
}

// ==================== 动作分组（action groups） ====================

/**
 * 动作分组类型
 */
export type ActionGroupKey = 'view' | 'edit' | 'manage'

/**
 * 动作分组标签
 */
export const GROUP_LABELS = {
  view: '查看',
  edit: '编辑',
  manage: '管理',
} as const

/**
 * 动作分组 i18n keys
 */
export const GROUP_I18N_KEYS = {
  view: 'permission.group.view',
  edit: 'permission.group.edit',
  manage: 'permission.group.manage',
} as const

/**
 * 动作分组层级依赖
 */
export const GROUP_DEPENDENCIES = {
  manage: ['edit'],
  edit: ['view'],
  view: [],
} as const

// ==================== 动作分组到 actions 映射 ====================

/**
 * 动作分组包含的 actions
 */
export const GROUP_ACTIONS_MAP = {
  view: ['read', 'list'],
  edit: ['read', 'list', 'create', 'update'],
  manage: ['read', 'list', 'create', 'update', 'delete'],
} as const

// ==================== 独立动作（standalone actions） ====================

/**
 * 独立动作定义
 */
export const STANDALONE_ACTIONS = {
  export: { label: '导出', description: '独立权限，不隐含 read' },
  import: { label: '导入', description: '独立权限，不隐含 create' },
  assign: { label: '分配', description: '关联操作（成员管理）' },
  unassign: { label: '取消分配', description: '关联操作（成员管理）' },
  associate: { label: '关联', description: '关联操作（关系建立）' },
  dissociate: { label: '取消关联', description: '关联操作（关系解除）' },
  grant: { label: '授权', description: '关联操作（权限授予）' },
  revoke: { label: '撤销', description: '关联操作（权限撤销）' },
} as const

// ==================== UI 区域标题 ====================

/**
 * UI 区域标题
 */
export const SECTION_TITLES = {
  actionGroups: '功能权限',
  detailedPermissions: '详细权限',
  dataScope: '数据约束',
  dataScopeHint: '建议为此菜单配置',
} as const

// ==================== Badge 文本 ====================

/**
 * Badge 标签文本
 */
export const BADGE_LABELS = {
  capability: '权限',
  hasDataScope: '有数据范围',
  denied: '禁止',
} as const
```

#### 2.3.2 修改 MenuPermissionMatrix.vue

```typescript
import {
  SOURCE_LABELS,
  getSourceLabel,
  GROUP_LABELS,
  SECTION_TITLES,
} from '../constants/permissionConstants'

// 删除原有的 GROUP_LABELS 定义和 sourceLabel/permSourceLabel 函数

// 使用导入的常量
function sourceLabel(item: { granted: boolean; source: PermissionSource } | undefined): string {
  if (!item) return ''
  return getSourceLabel(item.source)
}

function permSourceLabel(perm: Permission): string {
  return getSourceLabel(perm.source || 'none')
}
```

#### 2.3.3 国际化迁移路径

**阶段 1（当前）**：使用常量对象
```typescript
const label = SOURCE_LABELS.auto  // '自动'
```

**阶段 2（引入 i18n 后）**：切换到 i18n
```typescript
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const label = t(SOURCE_I18N_KEYS.auto)  // t('permission.source.auto')
```

**i18n 配置文件**（`src/locales/zh-CN.ts`）：
```typescript
export default {
  permission: {
    source: {
      auto: '自动',
      include: '包含',
      exclude: '排除',
      none: '未分配',
    },
    group: {
      view: '查看',
      edit: '编辑',
      manage: '管理',
    },
  },
}
```

### 2.4 实施步骤

1. **创建常量文件**
   - 创建 `src/views/SystemManagement/constants/permissionConstants.ts`

2. **修改组件**
   - MenuPermissionMatrix.vue 导入并使用常量
   - 删除硬编码的文本

3. **修改测试**
   - 测试脚本使用常量而非硬编码字符串
   - 或直接检查 DOM 元素存在性（更可靠）

### 2.5 后续待办：国际化（i18n）

**阶段 2**（后续实施）：

1. 安装 vue-i18n
2. 创建 locales 文件
3. 切换到 i18n key

**i18n 配置文件**（`src/locales/zh-CN.ts`）：
```typescript
export default {
  permission: {
    source: {
      auto: '自动',
      include: '包含',
      exclude: '排除',
      none: '未分配',
    },
    group: {
      view: '查看',
      edit: '编辑',
      manage: '管理',
    },
  },
}
```

**切换方式**：
```typescript
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const label = t(SOURCE_I18N_KEYS.auto)  // t('permission.source.auto')
```

### 2.6 预期结果

**代码结构**：
```
src/views/SystemManagement/
├── constants/
│   └── permissionConstants.ts  # 集中管理所有权限相关常量
├── components/
│   └── MenuPermissionMatrix.vue  # 导入并使用常量
└── composables/
    └── useMenuPermission.ts  # 导入并使用常量
```

**测试改进**：
```typescript
// 之前：硬编码字符串
expect(text).toContain('自动')

// 之后：使用常量
import { SOURCE_LABELS } from '../constants/permissionConstants'
expect(text).toContain(SOURCE_LABELS.auto)
```

---

## 三、实施优先级

| 优先级 | 任务 | 预估工作量 | 依赖 |
|--------|------|-----------|------|
| **P0** | standalone 动作补充（方案 B） | 2h | 无 |
| **P1** | UI 文本常量提取 | 1h | 无 |
| **P2** | 测试脚本改进 | 0.5h | P1 |
| **后续** | i18n 国际化 | 4h | P1 |

---

## 四、验收标准

### 4.1 standalone 动作

- [ ] API `/api/v2/roles/<id>/unified-permissions` 返回 `standalone` 不为空
- [ ] standalone 包含 export/import（如果 BO 启用了 import_export）
- [ ] 前端 UI 显示 standalone 按钮
- [ ] standalone 权限可以 include/exclude 并持久化

### 4.2 UI 文本常量

- [ ] 创建 `permissionConstants.ts` 文件
- [ ] MenuPermissionMatrix.vue 使用导入的常量
- [ ] 无硬编码文本
- [ ] 测试通过

---

## 五、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 修改 menu_auto_generator 影响现有菜单 | 中 | 先在测试环境验证，重新生成菜单前备份 |
| 常量提取遗漏部分文本 | 低 | 全局搜索硬编码文本，逐步迁移 |
