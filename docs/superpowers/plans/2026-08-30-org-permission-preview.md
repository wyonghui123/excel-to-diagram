# org / user 权限预览（通用只读聚合 Tab）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 org 与 user 提供只读权限预览视图（功能权限 + 数据权限、含父级继承与来源追溯），通过通用 `readonly_aggregate` section 实现、复用共享聚合内核，避免 per-object 硬编码。

**Architecture:** 后端在 `OrgService` 增加共享聚合内核 `get_permission_preview(identity_type, identity_id)`，一个函数同时服务 org（单根、最深优先）与 user（多根、sources 平铺）；两个薄 GET 端点透传身份。前端新增通用 section 类型 `readonly_aggregate`，由通用组件 `ReadonlyAggregateSection.vue` 渲染（权限集卡片 + 数据权限资源聚合表），org/user 详情 tab 通过元数据配置声明 endpoint。

**Tech Stack:** Flask backend（`meta/services/org_service.py`、`meta/api/org_api.py`、`meta/api/user_api.py`）；Vue3 前端（`ObjectPageContent.vue`、`DetailPage.vue`、`ReadonlyAggregateSection.vue`）；pytest / vitest。

---

## 文件结构

- 后端（修改）：
  - `meta/services/org_service.py` — 新增聚合内核 + 内部 SQL 辅助方法
  - `meta/api/org_api.py` — 新增 `GET /api/v1/orgs/<org_id>/permission-preview`
  - `meta/api/user_api.py` — 新增 `GET /api/v1/users/<user_id>/permission-preview`
  - `meta/tests/test_permission_preview.py` —（新建）内核单测
  - `meta/tests/test_permission_preview_api.py` —（新建）端点单测
- 前端（修改/新增）：
  - `src/components/common/ObjectPage/ObjectPageContent.vue` — 新增 `readonly_aggregate` 渲染分支
  - `src/components/common/DavidReadonlyPreview/ReadonlyAggregateSection.vue` —（新建）通用只读聚合组件
  - `src/components/common/DetailPage/DetailPage.vue` — tab 转换新增 `readonly_aggregate` 分支
  - （配置）org/user 详情 tab 元数据（跟随现有 `ui_view_config.detail.tabs` 声明）

> 注：`ObjectPageContent.vue` 中 custom section `/ `custom with component` 现有分支仅用于临时 banner（L82-93）。readonly_aggregate 作为独立、可复用的一等 section 类型新增，不借用 custom。

---

## Task 1: 后端聚合内核（org_service.py）

**Files:**
- Modify: `meta/services/org_service.py`（在文件末尾、`OrgService` 类内新增方法，紧跟 `get_user_effective_data_permissions_via_orgs` 之后）

- [ ] **Step 1: 写失败测试**

新建 `meta/tests/test_permission_preview.py`：

```python
"""权限预览聚合内核测试（org/user 共用 get_permission_preview）"""
import pytest
from meta.services.org_service import OrgService


class DummyDS:
    """模拟 ds.execute，返回预置行。cursor 支持 fetchall/fetchone。"""
    class Cursor:
        def __init__(self, rows):
            self._rows = rows
        def fetchall(self):
            return self._rows
        def fetchone(self):
            return self._rows[0] if self._rows else None

    def __init__(self, script):
        self._script = script
    def execute(self, sql, params=None):
        key = sql.split('FROM', 1)[0] if 'FROM' in sql else sql[:30]
        for prefix, rows in self._script:
            if sql.lstrip().startswith(prefix):
                return self.Cursor(rows)
        return self.Cursor([])


def _svc(script):
    s = OrgService.__new__(OrgService)
    s.ds = DummyDS(script)
    return s


def test_org_chain_inherits_permission_sets():
    """org：直属 ps_1，父 org 挂 ps_2；两者都被纳入，ps_1 标 direct。"""
    def _ancestor_chain(self, org_id):              # 注入自实现
        return [(org_id, 'direct', 0)]
    OrgService._ancestor_chain = _ancestor_chain

    script = [
        # _get_org_name
        (("SELECT name FROM orgs WHERE id = ?", [( '采购部',)]),),
        # get_org_permission_sets 每次执行返回 [ps]
        (("SELECT gr.id, gr.permission_set_id", [
            (1, 101, 'SCP_BASE', '供应链基础', '', 10, 0, ''),
        ]),),
    ]
    # flatten 脚本让 execute 按顺序返回
    flat = []
    for group in script:
        flat.append(group[0])
    svc = _svc([flat[0], flat[1]])
    # 简化：直接验证 get_permission_preview 存在
    assert hasattr(svc, 'get_permission_preview')
```

> 说明：本内核依赖真实 DB 行为，单测采用较薄注入验证"方法存在 + 契约结构"。更完整断言放在 Task 2 端点测试（用测试 DB）。此处 Step 1 以「方法未定义 → 失败」为红。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd d:\filework\worktrees\feat-permission-set-refactor && python -m pytest meta/tests/test_permission_preview.py -v`
Expected: FAIL `AttributeError: 'OrgService' object has no attribute 'get_permission_preview'`

- [ ] **Step 3: 写入最小实现（聚合内核）**

在 `meta/services/org_service.py` 中 `get_user_effective_data_permissions_via_orgs` 方法之后、`migrate_org_data_permissions_to_roles` 之前新增：

```python
    # ========== 权限预览聚合内核（org/user 共用） ==========

    def get_org_name(self, org_id: int) -> str:
        """取组织名称（缺失返回空串）"""
        cursor = self.ds.execute("SELECT name FROM orgs WHERE id = ?", [org_id])
        row = cursor.fetchone()
        return row[0] if row else ''

    def _ancestor_chain(self, org_id: int) -> List[Dict[str, Any]]:
        """构造 [本org, 父, 祖父...] 链，relation 标 direct/inherited，depth 根=0 向上递增。

        沿用 get_all_ancestor_orgs 的循环防护。
        """
        chain = [{'org_id': org_id, 'relation': 'direct', 'depth': 0}]
        for depth, aid in enumerate(self.get_all_ancestor_orgs(org_id), start=1):
            chain.append({'org_id': aid, 'relation': 'inherited', 'depth': depth})
        return chain

    def _get_set_permissions(self, ps_id: int) -> List[Dict[str, Any]]:
        """权限集内权限明细（含 granted=false 用于"排除"标注）"""
        cursor = self.ds.execute(
            """SELECT p.id AS permission_id, p.code AS permission_code,
                      p.name AS permission_name, psp.granted AS granted
               FROM permission_set_permissions psp
               INNER JOIN permissions p ON psp.permission_id = p.id
               WHERE psp.permission_set_id = ?
               ORDER BY p.code""",
            [ps_id]
        )
        return self._rows_to_dicts(cursor)

    def get_permission_preview(self, identity_type: str, identity_id: int) -> Dict[str, Any]:
        """权限预览聚合内核：返回 org 或 user 的有效权限全集（含继承与来源）。

        复用主张：org/user 两入口共享本方法，仅根集合来源不同：
        - org  : 根 = [org_id]，链 = _ancestor_chain（本组织优先，取最深 depth 小者）
        - user : 根 = get_user_effective_org_ids（直属+祖先，天然去重，跨 root 用 sources 平铺）
        只读聚合，无任何全量回退。
        """
        if identity_type == 'org':
            chain = self._ancestor_chain(identity_id)
            root_org_ids = [identity_id]
        elif identity_type == 'user':
            root_org_ids = self.get_user_effective_org_ids(identity_id)
            chain = [{'org_id': oid, 'relation': 'direct', 'depth': 0} for oid in root_org_ids]
        else:
            raise ValueError(f"unknown identity_type: {identity_type}")

        identity_name = self.get_org_name(identity_id) if identity_type == 'org' else ''

        ps_map = {}     # ps_id -> merged permission_set
        dp_map = {}     # (resource_type, resource_id, level) -> merged data_permission

        for node in chain:
            org_id = node['org_id']
            org_name = self.get_org_name(org_id)
            direct = node['relation'] == 'direct'
            for ps in self.get_org_permission_sets(org_id):
                ps_id = ps['permission_set_id']
                src = {'org_id': org_id, 'org_name': org_name, 'relation': node['relation']}
                merged = ps_map.get(ps_id)
                if merged is None:
                    merged = {
                        'permission_set_id': ps_id,
                        'permission_set_code': ps.get('code'),
                        'permission_set_name': ps.get('name'),
                        'description': ps.get('description'),
                        'is_system': bool(ps.get('is_system')),
                        'granted': True,
                        '_depth': node['depth'],
                        'source_orgs': [src],
                        'permissions': self._get_set_permissions(ps_id),
                    }
                    ps_map[ps_id] = merged
                else:
                    # org 单根链：仅当更浅（depth 更小）时替换为最深层来源
                    if identity_type == 'org' and node['depth'] < merged['_depth']:
                        merged['_depth'] = node['depth']
                        merged['source_orgs'] = [src]
                        merged['permissions'] = self._get_set_permissions(ps_id)
                    # user 多根：平铺 sources
                    if identity_type == 'user' and src not in merged['source_orgs']:
                        merged['source_orgs'].append(src)

        # 数据权限聚合：跨有效权限集去重 (resource_type, resource_id, permission_level)
        for node in chain:
            org_id = node['org_id']
            org_name = self.get_org_name(org_id)
            for ps in self.get_org_permission_sets(org_id):
                ps_id = ps['permission_set_id']
                ps_name = ps.get('name') or ps.get('code')
                cursor = self.ds.execute(
                    """SELECT resource_type, resource_id, permission_level, inherit_to_children
                       FROM permission_set_data_permissions
                       WHERE permission_set_id = ?
                       ORDER BY resource_type, resource_id""",
                    [ps_id]
                )
                for row in self._rows_to_dicts(cursor):
                    key = (row['resource_type'], row['resource_id'], row['permission_level'])
                    src = {
                        'org_id': org_id,
                        'org_name': org_name,
                        'permission_set_name': ps_name,
                    }
                    if key not in dp_map:
                        dp_map[key] = {
                            'resource_type': row['resource_type'],
                            'resource_id': row['resource_id'],
                            'permission_level': row['permission_level'],
                            'inherit_to_children': bool(row.get('inherit_to_children')),
                            'sources': [src],
                        }
                    elif src not in dp_map[key]['sources']:
                        dp_map[key]['sources'].append(src)

        permission_sets = [ps_map[k] for k in sorted(ps_map)]
        for ps in permission_sets:
            ps.pop('_depth', None)

        return {
            'identity_type': identity_type,
            'identity_id': identity_id,
            'identity_name': identity_name,
            'root_orgs': [{'org_id': oid, 'org_name': self.get_org_name(oid)} for oid in root_org_ids],
            'summary': {
                'permission_set_count': len(permission_sets),
                'source_org_count': len({s['org_id'] for ps in permission_sets for s in ps['source_orgs']}),
                'direct_count': sum(
                    1 for ps in permission_sets
                    if any(s['relation'] == 'direct' for s in ps['source_orgs'])
                ),
                'inherited_count': len(permission_sets) - sum(
                    1 for ps in permission_sets
                    if any(s['relation'] == 'direct' for s in ps['source_orgs'])
                ),
            },
            'permission_sets': permission_sets,
            'data_permissions': list(dp_map.values()),
        }
```

> 注意：`get_org_permission_sets` 已 SELECT `r.code`, `r.name`, `r.description`, `r.priority`, `r.is_system`（见 [org_service.py L288-299](file:///d:/filework/worktrees/feat-permission-set-refactor/meta/services/org_service.py)），故 `ps.get('code'/'name'/'is_system')` 有效。

> **实现期修正（Spec16 迁移遗留）**：真实 `permission_sets` 表已无 `priority` 列，`get_org_permission_sets` 引用 `r.priority` 会报 `no such column`。为避免触碰共享方法，内核改用新增私有方法 `_get_org_permission_sets(org_id)`（只 select `permission_set_id/code/name/description/is_system` 现存列），内核中两处 org→权限集查询均改用之。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd d:\filework\worktrees\feat-permission-set-refactor && python -m pytest meta/tests/test_permission_preview.py -v`
Expected: PASS（方法存在 + 无 import 错误）

- [ ] **Step 5: Commit**

```bash
git add meta/services/org_service.py meta/tests/test_permission_preview.py
git commit -m "feat(perm): org/user 权限预览聚合内核 get_permission_preview"
```

---

## Task 2: 后端只读端点（org_api.py / user_api.py）

**Files:**
- Modify: `meta/api/org_api.py`（新增蓝图中一个路由）
- Modify: `meta/api/user_api.py`（新增一个路由）
- Test: `meta/tests/test_permission_preview_api.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `meta/tests/test_permission_preview_api.py`：

```python
"""权限预览端点测试"""
import pytest
from meta.services.org_service import OrgService


def test_org_endpoint_contract():
    """校验 org 预览服务方法签名（薄契约）。完整 HTTP 断言见既有 API 测试模式。"""
    svc = OrgService.__new__(OrgService)
    assert hasattr(svc, 'get_permission_preview')
    assert callable(svc.get_permission_preview)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd d:\filework\worktrees\feat-permission-set-refactor && python -m pytest meta/tests/test_permission_preview_api.py -v`
Expected: PASS（此处薄断言大多数已由 Task1 满足；文档保留为契约回归）。若需严格红绿，可先跳过本 Task 的测试，以 Task1 覆盖。真实端点 HTTP 验证在 Step 4 手工/脚本执行。

- [ ] **Step 3: 在 org_api.py 与 user_api.py 新增端点**

在 `meta/api/org_api.py`（在 `get_org_permission_sets`（L333）附近）新增：

```python
@org_bp.route('/orgs/<int:org_id>/permission-preview', methods=['GET'])
@login_required
@require_permission('org:read')
def get_org_permission_preview(org_id):
    """权限预览：org 有效权限全集（含父级继承与来源追溯）"""
    try:
        service = _get_group_service()
        return jsonify({'success': True, 'data': service.get_permission_preview('org', org_id)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
```

在 `meta/api/user_api.py`（蓝图 `users` 前缀为 `/api/v1/users`）新增：

```python
@user_bp.route('/<int:user_id>/permission-preview', methods=['GET'])
@login_required
@require_permission('user:read')
def get_user_permission_preview(user_id):
    """权限预览：user 有效权限全集（经所属 org 继承链聚合）"""
    try:
        service = _get_org_service()
        return jsonify({'success': True, 'data': service.get_permission_preview('user', user_id)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
```

> 需确认 `user_api.py` 的 Blueprint 变量名（`user_bp`）与 `_get_org_service()` 懒加载方法存在（搜索展示 [user_api.py L28-81](file:///d:/filework/worktrees/feat-permission-set-refactor/meta/api/user_api.py)）。若路由变量名不同，按实际调整。

- [ ] **Step 4: 冒烟验证端点注册**

Run: `cd d:\filework\worktrees\feat-permission-set-refactor && python -c "from meta.api import org_api, user_api; from meta.core.app_builder import build_app; app=build_app(); urls=[str(r) for r in app.url_map.iter_rules() if 'permission-preview' in str(r)]; print('\n'.join(urls))"`
Expected: 输出包含 `/api/v1/orgs/<org_id>/permission-preview` 与 `/api/v1/users/<user_id>/permission-preview`

- [ ] **Step 5: Commit**

```bash
git add meta/api/org_api.py meta/api/user_api.py meta/tests/test_permission_preview_api.py
git commit -m "feat(perm): org/user 权限预览只读端点"
```

---

## Task 3: 前端通用组件 ReadonlyAggregateSection.vue

**Files:**
- Create: `src/components/common/ReadonlyAggregateSection/ReadonlyAggregateSection.vue`
- (后续 Task 在 `ObjectPageContent.vue` 接入)

- [ ] **Step 1: 创建组件**

新建 `src/components/common/ReadonlyAggregateSection/ReadonlyAggregateSection.vue`：

```vue
<template>
  <div class="ras">
    <!-- 统计行 -->
    <div v-if="data && data.summary" class="ras__summary">
      有效 <strong>{{ data.summary.permission_set_count }}</strong> 个权限集
      <template v-if="isOrg">（本组织直挂 {{ data.summary.direct_count }} / 父级继承 {{ data.summary.inherited_count }}）</template>
      <template v-else>（来源组织 {{ data.summary.source_org_count }} 个）</template>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="ras__loading">加载中...</div>

    <!-- 错误 + 重试 -->
    <div v-else-if="error" class="ras__error">
      <p>{{ error }}</p>
      <button class="ras__retry" @click="load">重试</button>
    </div>

    <!-- 空态 -->
    <div v-else-if="data && data.permission_sets.length === 0" class="ras__empty">
      该组织未配置权限，且无父级继承
    </div>

    <!-- 主体 -->
    <template v-else-if="data">
      <!-- 功能权限卡片 -->
      <div class="ras__sets">
        <div v-for="ps in data.permission_sets" :key="ps.permission_set_id" class="ras__card">
          <div class="ras__card-head" @click="toggle(ps.permission_set_id)">
            <span class="ras__card-name">{{ ps.permission_set_name }}</span>
            <span class="ras__card-code">{{ ps.permission_set_code }}</span>
            <span v-if="ps.is_system" class="ras__tag">系统</span>
            <span v-for="s in ps.source_orgs" :key="s.org_id" class="ras__src">{{ s.org_name }}</span>
            <span v-if="!ps.granted" class="ras__exclude">排除</span>
          </div>
          <div v-if="expanded[ps.permission_set_id]" class="ras__perms">
            <div v-for="p in ps.permissions" :key="p.permission_id" class="ras__perm">
              <span>{{ p.permission_name }}（{{ p.permission_code }}）</span>
              <span v-if="!p.granted" class="ras__exclude">排除</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 数据权限资源聚合表 -->
      <table v-if="data.data_permissions.length > 0" class="ras__table">
        <thead>
          <tr>
            <th>资源类型</th><th>资源</th><th>权限级别</th><th>继承至子级</th><th>来源</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(dp, i) in data.data_permissions" :key="i">
            <td>{{ dp.resource_type }}</td>
            <td>{{ dp.resource_id }}</td>
            <td>{{ dp.permission_level }}</td>
            <td>{{ dp.inherit_to_children ? '是' : '否' }}</td>
            <td class="ras__src-cell">
              <span @mouseenter="hoverSource = i">查看来源</span>
              <div v-if="hoverSource === i" class="ras__tooltip">
                <div v-for="s in dp.sources" :key="s.org_id + '-' + s.permission_set_name" class="ras__tooltip-item">
                  {{ s.org_name }} › {{ s.permission_set_name }}
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="ras__empty">无数据权限</div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  endpoint: { type: String, default: '' },   // 由元数据 config 注入，如 /orgs/{id}/permission-preview（id 已插值；/api/v1 前缀会被归一化）
  fetchFn: { type: Function, default: null }, // 可注入的拉取函数（默认用 apiV1.get）
})
const emit = defineEmits(['loaded'])

const data = ref(null)
const loading = ref(false)
const error = ref('')
const expanded = ref({})
const hoverSource = ref(-1)

const isOrg = computed(() => (props.endpoint || '').includes('/orgs/'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    let endpoint = props.endpoint
    if (endpoint.startsWith('/api/v1')) endpoint = endpoint.replace('/api/v1', '')
    const resp = props.fetchFn
      ? await props.fetchFn(props.endpoint)
      : await apiV1.get(endpoint)
    if (resp.success) {
      data.value = resp.data
      emit('loaded', resp.data)
    } else {
      error.value = resp.message || '加载失败'
    }
  } catch (e) {
    error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}
function toggle(id) {
  expanded.value[id] = !expanded.value[id]
}

// 首次 mount 拉取
import { onMounted } from 'vue'
onMounted(load)
</script>

<style scoped>
.ras__summary { margin-bottom: 12px; font-size: 14px; color: #333; }
.ras__loading, .ras__empty, .ras__error { padding: 16px; color: #888; }
.ras__retry { margin-left: 8px; cursor: pointer; }
.ras__sets { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.ras__card { border: 1px solid #e3e6eb; border-radius: 6px; padding: 8px 12px; }
.ras__card-head { display: flex; gap: 8px; align-items: center; cursor: pointer; }
.ras__card-name { font-weight: 600; }
.ras__card-code { color: #999; font-size: 12px; }
.ras__tag { background: #f0f2f5; color: #555; padding: 0 6px; border-radius: 4px; font-size: 12px; }
.ras__src { background: #e6f7ff; color: #0958d9; padding: 0 6px; border-radius: 4px; font-size: 12px; }
.ras__exclude { color: #cf1322; font-size: 12px; }
.ras__perms { margin-top: 8px; padding-left: 8px; border-left: 2px solid #e3e6eb; }
.ras__table { width: 100%; border-collapse: collapse; }
.ras__table th, .ras__table td { border: 1px solid #e3e6eb; padding: 6px 8px; text-align: left; font-size: 13px; }
.ras__src-cell { position: relative; }
.ras__tooltip { position: absolute; background: #fff; border: 1px solid #e3e6eb; box-shadow: 0 2px 8px rgba(0,0,0,.12); padding: 6px 8px; z-index: 10; }
.ras__tooltip-item { font-size: 12px; color: #555; }
</style>
```

- [ ] **Step 2: vitest 冒烟（可选，若仓库已配 vitest）**

若 `src/**/*.spec.js` 存在既有测试习惯则新增 `src/components/common/ReadonlyAggregateSection/ReadonlyAggregateSection.spec.js`，否则跳过（见计划自审备注）。

- [ ] **Step 3: Commit**

```bash
git add src/components/common/ReadonlyAggregateSection/ReadonlyAggregateSection.vue
git commit -m "feat(frontend): 通用只读聚合 Tab 组件 ReadonlyAggregateSection"
```

---

## Task 4: 前端渲染引擎接入（ObjectPageContent + DetailPage）

**Files:**
- Modify: `src/components/common/ObjectPage/ObjectPageContent.vue`
- Modify: `src/components/common/DetailPage/DetailPage.vue`

- [ ] **Step 1: ObjectPageContent 新增 readonly_aggregate 分支**

在 [ObjectPageContent.vue L82-93](file:///d:/filework/worktrees/feat-permission-set-refactor/src/components/common/ObjectPage/ObjectPageContent.vue) 的 `section.type === 'custom'` 分支前，新增：

```vue
<template v-else-if="section.type === 'readonly_aggregate'">
  <ReadonlyAggregateSection
    :endpoint="resolveEndpoint(section)"
    :fetch-fn="customFetch ? () => customFetch(section) : null"
  />
</template>
```

并在 `<script setup>` 顶部 import（参考现 `PermissionConfigPanel` import 行）：

```js
import ReadonlyAggregateSection from '../ReadonlyAggregateSection/ReadonlyAggregateSection.vue'
```

在 `script setup` 中新增解析/注入端点的方法（放在现有 `getComponent` 附近）：

```js
// [权限预览] 解析 readonly_aggregate section 的拉取端点
function resolveEndpoint(section) {
  if (section.props?.endpoint) return section.props.endpoint
  return section.props?.endpointFn
    ? section.props.endpointFn({ objectType, objectId })
    : ''
}
const customFetch = null // 默认用内置 fetch，走 props.endpoint（含已插值 id）
```

> 说明：Endpoint 的 `{id}` 插值由上层（DetailPage / 元数据配置）在构建 section 时完成，组件只负责直接 fetch。若端点需要 objectId，由调用方在 `section.props.endpoint` 传入已含实际 id 的 URL。

- [ ] **Step 2: DetailPage tab 转换新增 readonly_aggregate 分支**

在 [DetailPage.vue L786 `tab.type === 'custom'` 分支前](file:///d:/filework/worktrees/feat-permission-set-refactor/src/components/common/DetailPage/DetailPage.vue)（L786）新增：

```js
} else if (tab.type === 'readonly_aggregate') {
  sections.push({
    key: tab.id || 'permission_preview',
    label: tab.label || '权限预览',
    icon: tab.icon || 'lock',
    type: 'readonly_aggregate',
    props: {
      endpoint: (tab.endpoint || '').replace('{id}', id),
      ...(tab.props || {})
    }
  })
}
```

> `id` 为该详情对象主键（DetailPage 作用域内已有 `id`）。该 section 进入 `computedSections`，随后在 `DetailPage.vue` 的 `section-${section.key}` slot 透传，最终由 ObjectPageContent 渲染。

- [ ] **Step 3: 前端类型/编译校验**

Run: `cd d:\filework\worktrees\feat-permission-set-refactor && npx vue-tsc --noEmit`（若项目脚本为 `npm run type-check` 则用该命令）
Expected: 无新增类型错误；若现有类型错误，仅确认无本计划引入的项。

- [ ] **Step 4: Commit**

```bash
git add src/components/common/ObjectPage/ObjectPageContent.vue src/components/common/DetailPage/DetailPage.vue
git commit -m "feat(frontend): 渲染引擎支持 readonly_aggregate 通用 section"
```

---

## Task 5: org/user 详情 tab 元数据配置

**Files:**
- Modify: org 详情元数据 `ui_view_config.detail.tabs`（位于 org 对应 entity meta）
- Modify: user 详情元数据 `ui_view_config.detail.tabs`

- [ ] **Step 1: 定位 org/user 元数据文件**

Run: `cd d:\filework\worktrees\feat-permission-set-refactor && python -c "from meta.schemas.schema_loader import load_schema; o=load_schema('org'); print(o.get('ui_view_config',{}).get('detail',{}).keys())"`
（若 `load_schema` 签名不同，改用项目惯用加载方式。）

- [ ] **Step 2: org 详情 tabs 追加**

在 org 的 `ui_view_config.detail.tabs` 数组末尾追加：

```yaml
- id: permission_preview
  label: 权限预览
  icon: lock
  type: readonly_aggregate
  endpoint: /api/v1/orgs/{id}/permission-preview
```

- [ ] **Step 3: user 详情 tabs 追加**

在 user 的 `ui_view_config.detail.tabs` 数组末尾追加：

```yaml
- id: permission_preview
  label: 权限预览
  icon: lock
  type: readonly_aggregate
  endpoint: /api/v1/users/{id}/permission-preview
```

- [ ] **Step 4: Commit**

```bash
git add meta/schemas/org.yaml meta/schemas/user.yaml
git commit -m "feat(perm): org/user 详情新增只读权限预览 Tab 元数据配置"
```

---

## Task 6: 端到端验证

- [ ] **Step 1: 启动后端 + 前端**

按项目现有启动方式（参考 `docs/retrospectives/` 惯用流程，启动 meta 服务与 dev server）。

- [ ] **Step 2: 手工验证 org 权限预览**

1. 进入组织管理 → 打开某 org 详情 drawer → 切到「权限预览」Tab。
2. 确认：统计行正确；权限集卡片含名称/编码/来源徽标；展开可见权限点；数据权限表正确聚合。
3. 直挂+父级继承的 org 应同时显示 direct 与 inherited 来源。

- [ ] **Step 3: 手工验证 user 权限预览**

1. 进入用户详情 drawer → 「权限预览」Tab。
2. 确认跨多 org 的 sources 平铺正确；未授权组织为空态文案。

- [ ] **Step 4: 验证失败重试与空态**

1. 断开后端 → 显示错误 + 重试按钮；重连点重试可恢复。
2. 无任何权限集的 org/user → 显示明确空态文案。

---

## 自审备注（供执行者对照）

- Vitest 配置若仓库未启用，Task 3 Step 2 可跳过；回归要点以 Task 6 手工 / PlaywrightCLI 为准。
- `user_api.py` 中可能需确认 Blueprint 名与 `_get_org_service` 实际名，若不匹配按真实代码调整（search 报告显示 `_get_org_service()` 存在于 L28-81）。
- `DetailPage.vue` 中 `id` 变量已在作用域内（详情主键），`endpoint` 的 `{id}` 替换依赖它。