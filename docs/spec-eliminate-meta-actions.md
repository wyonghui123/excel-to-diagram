# Spec: 消除 meta_actions 表，统一动作声明为 YAML

> 日期：2026-05-26
> 状态：Spec 已完成，TBD 全部关闭，待确认后实施
> 前置文档：[MetaAction权限体系深度分析与设计方案.md](./meta-action-permission-analysis.md)

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [需求类型概览](#2-需求类型概览)
3. [功能需求](#3-功能需求)
4. [非功能需求](#4-非功能需求)
5. [外部接口](#5-外部接口)
6. [过渡需求](#6-过渡需求)
7. [约束与假设](#7-约束与假设)
8. [优先级与里程碑](#8-优先级与里程碑)
9. [变更设计（RFC）](#9-变更设计rfc)
10. [TBD 列表](#10-tbd-列表)

---

## 1. 背景与目标

### 1.1 背景

系统中存在两套互不相通的"动作定义"路径，且 `meta_actions` 表存在根本性缺陷：

| 问题 | 证据 |
|------|------|
| **行为不由表决定** | `BOFramework.create()` 硬编码 `self.execute('crud_create')`，删表中 `create` 行不影响框架 |
| **PersistenceInterceptor 硬编码** | `context.is_create_action → self._do_create()`，新增 DB 行不会自动创建分发分支 |
| **ACTION_SUFFIX_MAP 仅 4 对** | `{'crud_create': 'create', ...}` 硬编码在 `models.py`，缺 list/export/import/approve/assign/revoke/manage 共 7 个 |
| **仅 1 个消费点** | `PermissionService.get_meta_action_by_code()` 查询此表 |
| **BP 未注册** | `meta_action_bp` 在 `server.py:L141` 被 import 但从未 `register_blueprint()` |
| **服务初始化静默失败** | `app_builder.py:L65` 的 `_init_service(ds, 'meta_action', 'init_meta_action_services')` 因 `meta_action_service.py` 中无此函数而静默失败 |
| **前端空数据** | "业务配置→元操作"Tab 因表中无数据而展示空列表 |
| **relations / actions 均为空** | `meta_action.yaml` 是一个孤岛 BO，无任何关联关系 |

### 1.2 关键发现：整套 meta_action 功能是僵尸代码

```
meta_action_bp                → 在 server.py 中 import 但未 register_blueprint()
init_meta_action_services     → app_builder._init_service 因函数不存在而静默失败
meta_actions 表               → 表中无数据（前端空 Tab 印证）
PermissionService 校验        → 校验链路因表空/无数据，实际未曾生效
前端 Tab                      → 展示空数据，无任何功能价值
```

### 1.3 目标

- 消除 `meta_actions` 表及相关全部僵尸代码
- 将 12 个标准动作（补全 assign/revoke/manage）统一由 `_standard_actions.yaml` 声明
- 权限校验链路从查 DB 切换为查 MetaRegistry + StandardActionLoader

---

## 2. 需求类型概览

| 类型 | 适用 | 依据 |
|------|------|------|
| 业务需求 | 是 | 消除架构冗余，实现单一事实源 |
| 功能需求 | 是 | FR-001 ~ FR-013 |
| 非功能需求 | 是 | NFR-001 ~ NFR-003 |
| 外部接口 | 是 | IF-001 ~ IF-003 |
| 过渡需求 | 是 | TR-001 ~ TR-003 |

---

## 3. 功能需求

### FR-001：新建 `_standard_actions.yaml`

- **文件路径**：`meta/schemas/_standard_actions.yaml`
- **内容**：12 个标准动作，每个含 id / name / action_type / method / description
- **优先级**：Must

```yaml
# meta/schemas/_standard_actions.yaml
# 纯元数据声明 — 不映射数据库表，独立于 BO Schema 加载链路

standard_actions:
  # ─── CRUD ───
  - id: crud_create
    name: 创建
    action_type: crud
    method: POST
    description: 创建资源
  - id: crud_read
    name: 读取
    action_type: crud
    method: GET
    description: 读取单个资源
  - id: crud_update
    name: 更新
    action_type: crud
    method: PUT
    description: 更新资源
  - id: crud_delete
    name: 删除
    action_type: crud
    method: DELETE
    description: 删除资源
  - id: crud_list
    name: 列表
    action_type: crud
    method: GET
    description: 列表查询

  # ─── 批量 ───
  - id: export
    name: 导出
    action_type: batch
    method: GET
    description: 导出资源
  - id: import
    name: 导入
    action_type: batch
    method: POST
    description: 导入资源

  # ─── 业务 ───
  - id: approve
    name: 审批
    action_type: business
    method: POST
    description: 审批操作
  - id: search
    name: 搜索
    action_type: crud
    method: GET
    description: 搜索查询

  # ─── 管理 ───
  - id: assign
    name: 分配
    action_type: business
    method: POST
    description: 分配资源
  - id: revoke
    name: 撤销
    action_type: business
    method: POST
    description: 撤销资源
  - id: manage
    name: 管理
    action_type: business
    method: POST
    description: 管理操作
```

---

### FR-002：StandardActionLoader 独立加载

- **新文件**：`meta/core/standard_action_loader.py`
- **验收标准**：
  - `load(schemas_dir)` 从 `_standard_actions.yaml` 加载 12 个 MetaAction
  - `get_action_codes()` 返回 `{'create','read','update','delete','list','export','import','approve','search','assign','revoke','manage'}`
  - `get_suffix_map()` 返回 `{crud_create:'create', ..., crud_list:'list', export:'export', import:'import', approve:'approve', search:'search', assign:'assign', revoke:'revoke', manage:'manage'}`
  - 文件缺失时抛 `FileNotFoundError`

```python
# meta/core/standard_action_loader.py（新建）

import yaml
import os
from typing import List


class StandardActionLoader:
    """标准动作加载器 — 独立于 BO Schema 加载链路
    从 _standard_actions.yaml 加载标准动作并注册到运行时内存。
    """

    _actions: List = []
    _suffix_map = {}
    _action_codes = set()

    @classmethod
    def load(cls, schemas_dir: str):
        filepath = os.path.join(schemas_dir, '_standard_actions.yaml')
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"标准动作声明文件缺失: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        from meta.core.models import MetaAction, ActionType

        cls._actions = []
        for item in data.get('standard_actions', []):
            cls._actions.append(MetaAction(
                id=item['id'],
                name=item['name'],
                action_type=ActionType(item.get('action_type', 'crud')),
                method=item.get('method', 'POST'),
                path='',
                description=item.get('description', ''),
            ))

        cls._suffix_map = {}
        for a in cls._actions:
            suffix = a.id.replace('crud_', '')
            cls._suffix_map[a.id] = suffix
        cls._action_codes = set(cls._suffix_map.values())

        return cls._actions

    @classmethod
    def get_actions(cls):
        return cls._actions

    @classmethod
    def get_suffix_map(cls):
        return cls._suffix_map

    @classmethod
    def get_action_codes(cls):
        return cls._action_codes
```

- **优先级**：Must

---

### FR-003：yaml_loader 排除 `_standard_actions.yaml`

- **修改文件**：`meta/core/yaml_loader.py`
- **修改位置**：`load_yaml_directory()` 方法

**代码验证结果**：`load_yaml_directory()` 使用 `dir_path.glob("*.yaml")` 扫描所有 `.yaml` 文件，仅排除 `shared_properties.yaml` 和 `aspects.yaml`。`_` 前缀无过滤，`_template.yaml` 也被错误加载为 `id="new_object"` 的幽灵 BO。如果不排除，`_standard_actions.yaml` 会被 `parse_meta_object()` 解析为残缺 MetaObject，并触发 `ensure_crud_actions()` 追加 CRUD 动作。

- **验收标准**：`_standard_actions.yaml` 不被 `parse_meta_object()` 解析，不产生幽灵 BO

```python
# yaml_loader.py — 修改前
if yaml_file.name in ("shared_properties.yaml", "aspects.yaml"):

# 修改后
if yaml_file.name in ("shared_properties.yaml", "aspects.yaml", "_standard_actions.yaml"):
```

- **优先级**：Must

---

### FR-004：启动时加载标准动作

- **修改文件**：`meta/core/app_builder.py`
- **修改内容**：在 `_init_service` 调用链之前添加 `StandardActionLoader.load()`
- **验收标准**：启动日志打印 `[Init] 标准动作已加载: 12 个`

```python
# app_builder.py — 在 _init_service() 调用之前添加
from meta.core.standard_action_loader import StandardActionLoader

schemas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
actions = StandardActionLoader.load(schemas_dir)
logger.info(f"[Init] 标准动作已加载: {len(actions)} 个")
```

- **优先级**：Must

---

### FR-005：移除 `ACTION_SUFFIX_MAP` 硬编码

- **修改文件**：`meta/core/models.py`
- **修改内容**：移除 `MetaAction.ACTION_SUFFIX_MAP` 类变量，`get_permission_suffix()` 从 `StandardActionLoader` 动态获取
- **验收标准**：12 对映射全部可用，未命中时 fallback 到自身 id

```python
# models.py — MetaAction 类修改
@dataclass
class MetaAction:
    # 移除：ACTION_SUFFIX_MAP: ClassVar[Dict[str, str]] = {
    #     'crud_create': 'create',
    #     'crud_read': 'read',
    #     'crud_update': 'update',
    #     'crud_delete': 'delete',
    # }

    def get_permission_suffix(self) -> str:
        from meta.core.standard_action_loader import StandardActionLoader
        return StandardActionLoader.get_suffix_map().get(self.id, self.id)
```

- **优先级**：Must

---

### FR-006：PermissionService 重写关键方法

- **修改文件**：`meta/services/permission_service.py`

#### 6a. 删除 `get_meta_action_by_code()` 方法

该方法（L107-L114）执行 `SELECT * FROM meta_actions WHERE code = ?`。无外部调用者，仅本类中 `create_permission_unified` 使用。

#### 6b. 新增 `_validate_action_code()` 方法

```python
def _validate_action_code(self, action_code: str) -> bool:
    """校验 action_code 在标准动作或任意 BO YAML actions[] 中"""
    from meta.core.standard_action_loader import StandardActionLoader

    if action_code in StandardActionLoader.get_action_codes():
        return True

    try:
        from meta.core.meta_registry import meta_registry
        for obj in meta_registry.get_all():
            for action in obj.actions:
                if action.get_permission_suffix() == action_code:
                    return True
    except Exception:
        pass

    return False
```

#### 6c. 修改 `create_permission_unified()`（L171-L200）

```python
# 修改前 L183-L197:
meta_action = self.get_meta_action_by_code(action_code)
if not meta_action:
    raise ValueError(f"Action code '{action_code}' not found in meta_actions")
action_id = meta_action['id']
cursor = self.ds.execute(
    """INSERT INTO permissions (code, name, resource_type, action_id, action_code, scope, description)
       VALUES (?, ?, ?, ?, ?, ?, ?)""",
    [code, name, resource_type, action_id, action_code, scope, description]
)

# 修改后:
if not self._validate_action_code(action_code):
    raise ValueError(
        f"Action code '{action_code}' not found in "
        f"standard_actions.yaml or any BO YAML actions[]"
    )
cursor = self.ds.execute(
    """INSERT INTO permissions (code, name, resource_type, action, scope, description)
       VALUES (?, ?, ?, ?, ?, ?)""",
    [code, name, resource_type, suffix, scope, description]
)
```

#### 6d. 删除 `get_permission_by_resource_and_action()`（L116-L125）

该方法执行 `LEFT JOIN meta_actions ma ON p.action_id = ma.id`。该表被删除后此方法不可用。仅被测试文件调用。

#### 6e. 删除 `get_user_permissions_by_resource()`（L127-L138）

同样 JOIN `meta_actions` 表。仅被测试调用。

- **优先级**：Must

---

### FR-007：删除 meta_action 相关文件

| 文件 | 操作 | 原因 |
|------|------|------|
| `meta/api/meta_action_api.py` | **删除** | BP 未注册（server.py L141 import 但 L400-L439 无 register_blueprint），完全僵尸 |
| `meta/services/meta_action_service.py` | **删除** | `init_meta_action_services` 函数不存在，app_builder L65 调用静默失败 |
| `meta/schemas/meta_action.yaml` | **删除** | 孤岛 BO，`relations: []` 和 `actions: []` 均为空 |

- **优先级**：Must

---

### FR-008：删除 permissions 表中 action_id / action_code 字段

- **修改文件**：`meta/schemas/permission.yaml`
- **删除字段**：`action_id`（L60-L65）、`action_code`（L67-L72）
- **修改文件**：`meta/schemas/generated_schema.sql`
- **删除内容**：
  - `permissions` 表的 `action_id INTEGER` 和 `action_code VARCHAR(200)` 列
  - `meta_actions` 表完整 DDL（L242-L251）
  - `meta_actions` 相关索引：`idx_meta_action_code`、`idx_meta_actions_name`（L651-L653）

**安全验证**：`PermissionSyncService.sync_all()` 的 INSERT 语句为：

```sql
INSERT OR IGNORE INTO permissions (code, name, resource_type, action) VALUES (?, ?, ?, ?)
```

**不使用** `action_id` 和 `action_code` 列。删除这两列不影响权限同步。

- **优先级**：Must

---

### FR-009：清理 server.py

| 行号 | 操作 | 内容 |
|------|------|------|
| L141 | **删除** | `from meta.api.meta_action_api import meta_action_bp, init_meta_action_services` |
| L451 | **删除** | `'meta-actions',` from `V1_SPECIAL_PREFIXES` |

**说明**：L400-L439 的 `register_blueprint()` 列表中无 `meta_action_bp` 注册。L141 的 import 是死代码。

- **优先级**：Must

---

### FR-010：清理 app_builder.py

| 行号 | 操作 | 内容 |
|------|------|------|
| L65 | **删除** | `_init_service(ds, 'meta_action', 'init_meta_action_services')` |
| (新增) | **添加** | `StandardActionLoader.load(schemas_dir)` 调用（见 FR-004） |

```python
# 修改前 L65
_init_service(ds, 'meta_action', 'init_meta_action_services')

# 修改后：删除 + 添加 FR-004 的 StandardActionLoader.load() 调用
```

- **优先级**：Must

---

### FR-011：清理迁移脚本

- **文件**：`meta/scripts/migrate_permission_unified_semantic.py`
- **修改内容**：
  - 删除步骤 1（建 meta_actions 表 + INSERT 种子数据，L25-L61）
  - 删除步骤 2 中 `action_id` 和 `action_code` 列的 ALTER TABLE（L71-L83）
  - 删除步骤 4（meta_actions 索引，L110-L124）
  - 删除步骤 5 中 meta_actions 验证逻辑（L130-L132）
- **优先级**：Must

---

### FR-012：前端移除元操作 Tab

- **文件**：`src/config/menuConfig.js`
- **修改**：删除 `business-config` 中的 `meta_action` Tab

```javascript
// 修改前
'business-config': {
    title: '业务配置',
    tabs: [
      { key: 'enum-types', label: '枚举类型', objectType: 'enum_type' },
      { key: 'meta-actions', label: '元操作', objectType: 'meta_action' },
    ],
  },

// 修改后
'business-config': {
    title: '业务配置',
    tabs: [
      { key: 'enum-types', label: '枚举类型', objectType: 'enum_type' },
    ],
  },
```

- **优先级**：Must

---

### FR-013：适配测试文件

- **文件**：`meta/tests/test_permission_unified_semantic.py`

| 原内容 | 操作 | 说明 |
|--------|------|------|
| L15: `from meta.services.meta_action_service import MetaActionService` | **删除** | 模块已删除 |
| L19-L157: `class TestMetaActionService` | **删除整个类** | 测试已删除的服务 |
| L173-L184: `CREATE TABLE meta_actions` | **删除** | 表已删除 |
| L195-L196: `action_id`, `action_code` in permissions CREATE TABLE | **删除** | 字段已删除 |
| L234-L238: `INSERT INTO meta_actions...` | **删除** | 种子数据已迁移到 YAML |
| L258-L263: `test_get_meta_action_by_code` | **重写** | 改为测试 `_validate_action_code()` |
| L279-L280: `test_create_permission_unified` 中的 `action_code` 断言 | **修改** | 移除对 `permissions.action_code` 列的断言 |
| L394-L408: `test_migration_script` 中 meta_actions 相关断言 | **删除** | 迁移不再涉及此表 |

- **优先级**：Must

---

## 4. 非功能需求

| ID | 需求 | 度量 | 优先级 |
|----|------|------|--------|
| **NFR-001** | 兼容性 — 现有权限数据完整可用 | `PermissionSyncService.sync_all()` 输出不变；现有 `permissions` 表数据不丢失 | Must |
| **NFR-002** | 启动性能 — YAML 加载 < 50ms | 单文件 12 条目，yaml.safe_load < 1ms | Should |
| **NFR-003** | 可维护性 — 新增标准动作只改 1 个 YAML | 新增 `archive` 动作只需编辑 `_standard_actions.yaml`，无需改 Python 或 DB | Should |

---

## 5. 外部接口

| ID | 类型 | 入口 | 变更 |
|----|------|------|------|
| **IF-001** | API | `POST /api/v1/permissions`（创建权限） | 内部校验从查 DB 改为查 MetaRegistry，请求/响应格式及错误码不变 |
| **IF-002** | UI | 业务配置 Tab 列表 | 移除"元操作"Tab，只剩下"枚举类型" |
| **IF-003** | Schema | `generated_schema.sql` / `permission.yaml` | 移除 `meta_actions` 表；移除 `permissions.action_id`、`permissions.action_code` |

---

## 6. 过渡需求

| ID | 内容 | 策略 | 回退方案 |
|----|------|------|---------|
| **TR-001** | permissions 表 action_id/action_code 列删除 | 修改 `permission.yaml` → Schema 同步工具自动 `DROP COLUMN` | Git revert `permission.yaml` + 重建列 |
| **TR-002** | 种子数据从 DB 迁移到 YAML | 新建 `_standard_actions.yaml` → 实现 `StandardActionLoader` → 删除 `migrate_permission_unified_semantic.py` 中 meta_actions 代码 | Git revert 脚本 |
| **TR-003** | 测试用例适配 | 删除 `TestMetaActionService` 类，重写 `TestPermissionService` fixture | Git revert 测试文件 |

---

## 7. 约束与假设

### 7.1 技术约束

- SQLite 不支持复杂的在线 DDL 变更，列删除通过 `permission.yaml` Schema 同步工具完成
- 现有拦截器链的顺序不可变更
- `_standard_actions.yaml` 只在系统启动时加载一次，运行时不热更新

### 7.2 假设

- MetaRegistry 是线程安全的，多请求并发查询不会出现竞态条件 — 来源：假定
- 标准动作的数量不会超过 50 个 — 来源：假定

---

## 8. 优先级与里程碑

| 里程碑 | 包含 FR | 说明 |
|--------|--------|------|
| **M1: YAML + 加载** | FR-001 ~ FR-005, FR-010 | 新建 YAML 声明文件、标准动作加载器、排除 glob、启动集成、动态 ACTION_SUFFIX_MAP、清理 app_builder |
| **M2: 校验切换 + 清理** | FR-006 ~ FR-009 | PermissionService 重写、删除 meta_action 文件、删除 permissions 字段/DDL、清理 server.py |
| **M3: 前端 + 测试 + 脚本** | FR-011 ~ FR-013 | 前端 Tab 移除、迁移脚本清理、测试文件适配 |

---

## 9. 变更设计（RFC）

### 9.1 As-Is 完整调用链分析（代码级验证）

```
server.py L141:  import meta_action_bp        → 导入但 L400-L439 未 register_blueprint()
server.py L451:  'meta-actions' in PREFIXES   → 中间件豁免，但路由不存在
app_builder L65: _init_service('meta_action') → try import meta.services.meta_action_service
                                                 → getattr(init_meta_action_services)
                                                 → 函数不存在 → 静默 catch 警告

PermissionService L107: get_meta_action_by_code() → SELECT * FROM meta_actions WHERE code=?
PermissionService L171: create_permission_unified() → 调用 get_meta_action_by_code()
                                                    → 校验 action_code
                                                    → INSERT action_id, action_code
PermissionService L116: get_permission_by_resource_and_action() → LEFT JOIN meta_actions
PermissionService L127: get_user_permissions_by_resource()      → LEFT JOIN meta_actions
PermissionSync L112:   sync_all() INSERT → 只写 code/name/resource_type/action，不写 action_id/action_code

meta_action.yaml:     relations: [], actions: []  → 孤岛 BO

前端 menuConfig.js:   objectType: 'meta_action'  → GenericObjectList → 查询空表 → 空界面
```

**结论：整条链路完全断裂。`meta_action_bp` 从未注册路由，`init_meta_action_services` 不存在，`meta_actions` 表无数据。删除无任何运行时影响。**

### 9.2 目标状态

```
【声明层 — 单一事实源】
  _standard_actions.yaml            各 BO YAML actions[]
  (StandardActionLoader 独立加载)    (yaml_loader 正常加载)
       │                                    │
       └──────────────┬─────────────────────┘
                      │
                      ▼
                MetaRegistry
                (运行时统一动作注册表)
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       ▼              ▼              ▼
  PermissionSync  Permission      BO YAML
  (YAML→perms     Service         actions[]
   表同步，       (_validate       (业务 action
   动态ACTION     _action_code     permission suffix)
   _SUFFIX_MAP)   查标准动作+
                  BO YAML)

【消除】
  ❌ meta_actions 表 + DDL + 索引
  ❌ meta_action.yaml Schema
  ❌ meta_action_api.py（BP 未注册）
  ❌ meta_action_service.py（init 静默失败）
  ❌ permissions.action_id / action_code 列
  ❌ server.py L141 死 import + L451 前缀豁免
  ❌ app_builder.py L65 静默失败调用
  ❌ menuConfig.js 'meta-actions' Tab
  ❌ migrate_permission_unified_semantic.py 中 meta_actions 代码
```

### 9.3 变更文件清单

| # | 文件 | 操作 | 行影响 |
|---|------|------|--------|
| 1 | `meta/schemas/_standard_actions.yaml` | **新建** | +30 |
| 2 | `meta/core/standard_action_loader.py` | **新建** | +45 |
| 3 | `meta/core/yaml_loader.py` | 修改 1 行（排除列表） | L2187 |
| 4 | `meta/core/app_builder.py` | 删 1 行 + 加 4 行 | L65, 新增 |
| 5 | `meta/core/models.py` | 删 4 行 + 改 2 行 | L1342-L1346, L1361-L1362 |
| 6 | `meta/services/permission_service.py` | 删 3 方法 + 改 1 方法 + 加 1 方法 | L107-L200 |
| 7 | `meta/schemas/permission.yaml` | 删 2 字段定义 | L60-L72 |
| 8 | `meta/schemas/generated_schema.sql` | 删 meta_actions 表 + permissions 2 列 + 2 索引 | ~25 行 |
| 9 | `meta/server.py` | 删 1 行 import + 1 行前缀 | L141, L451 |
| 10 | `meta/scripts/migrate_permission_unified_semantic.py` | 删步骤 1/2/4/5 | ~60 行 |
| 11 | `src/config/menuConfig.js` | 删 1 行 Tab 配置 | L15 |
| 12 | `meta/tests/test_permission_unified_semantic.py` | 删类 + 重写 fixture + 改方法/断言 | ~80 行 |
| 13 | `meta/api/meta_action_api.py` | **删除** | -121 行 |
| 14 | `meta/services/meta_action_service.py` | **删除** | -82 行 |
| 15 | `meta/schemas/meta_action.yaml` | **删除** | -112 行 |
| **合计** | **15 文件** | | |

### 9.4 风险矩阵

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| PermissionSync.sync_all() 输出变化 | 低 | 中 | `sync_all()` 只写 code/name/resource_type/action，不写 action_id/action_code，变更无影响 |
| 已有 DB 中 permissions 表有 action_id/action_code 列导致 ORM 报错 | 中 | 低 | Schema 同步工具基于 permission.yaml 自动 DROP COLUMN |
| models.py 硬编码映射与 YAML 不一致 | 低 | 低 | 采用 YAML 单源后无此问题 |
| 测试断言因字段变更失败 | 中 | 低 | FR-013 覆盖全部测试适配，重写的 fixture 不创建 action_id/action_code |
| MetaRegistry 未初始化导致 `_validate_action_code` 崩溃 | 低 | 高 | try/except 兜底，即使 MetaRegistry 不可用，标准动作仍可校验 |

### 9.5 实施步骤

```
Step 1: 新建文件（2 个文件）
  1.1 创建 meta/schemas/_standard_actions.yaml       (FR-001)
  1.2 创建 meta/core/standard_action_loader.py       (FR-002)

Step 2: 修改加载链路（2 个文件）
  2.1 修改 meta/core/yaml_loader.py — 排除列表 + "_standard_actions.yaml"  (FR-003)
  2.2 修改 meta/core/app_builder.py — 添加 StandardActionLoader.load() + 删除 L65 (FR-004, FR-010)

Step 3: 修改消费端（2 个文件）
  3.1 修改 meta/core/models.py — 移除 ACTION_SUFFIX_MAP，get_permission_suffix() 动态获取 (FR-005)
  3.2 修改 meta/services/permission_service.py — 删除/重写/新增 5 个方法  (FR-006)

Step 4: 清理 Schema（2 个文件）
  4.1 修改 meta/schemas/permission.yaml — 删除 action_id/action_code 字段  (FR-008)
  4.2 修改 meta/schemas/generated_schema.sql — 删除 meta_actions DDL + permissions 列 + 索引 (FR-008)

Step 5: 清理启动入口（1 个文件）
  5.1 修改 meta/server.py — 删除 L141 import + L451 前缀豁免  (FR-009)

Step 6: 删除文件（3 个文件）
  6.1 删除 meta/api/meta_action_api.py              (FR-007)
  6.2 删除 meta/services/meta_action_service.py     (FR-007)
  6.3 删除 meta/schemas/meta_action.yaml            (FR-007)

Step 7: 清理脚本（1 个文件）
  7.1 修改 meta/scripts/migrate_permission_unified_semantic.py — 删除 meta_actions 代码 (FR-011)

Step 8: 前端（1 个文件）
  8.1 修改 src/config/menuConfig.js — 删除 meta-actions Tab  (FR-012)

Step 9: 测试（1 个文件）
  9.1 修改 meta/tests/test_permission_unified_semantic.py — 适配全部变更 (FR-013)

Step 10: 验证
  10.1 启动服务 — 确认日志 [Init] 标准动作已加载: 12 个
  10.2 运行 pytest meta/tests/test_permission_unified_semantic.py — 全部通过
  10.3 前端检查 — 业务配置页面仅显示"枚举类型"Tab
  10.4 手动创建权限 — 使用标准 action_code（如 create）通过校验
```

### 9.6 测试策略

| 层级 | 覆盖范围 | 工具 |
|------|---------|------|
| **单元** | `StandardActionLoader.load()` 正常加载 / 文件缺失；`get_permission_suffix()` 12 对映射 + fallback；`_validate_action_code()` 标准动作 / BO 业务 action / 非法 action | pytest |
| **集成** | `PermissionService.create_permission_unified()`；`PermissionSyncService.sync_all()` | pytest |
| **回归** | `test_permission_unified_semantic.py` 全部用例（适配后） | pytest |
| **手动** | 前端"业务配置"页面只显示枚举类型；创建权限时标准 action_code 通过校验 | 浏览器 |

### 9.7 回退方案

1. `git checkout` 恢复 `permission.yaml`、`permission_service.py`、`server.py`、`app_builder.py`、`models.py`
2. `git checkout` 恢复 `meta_action_api.py`、`meta_action_service.py`、`meta_action.yaml`
3. 重新运行 Schema 同步恢复 `meta_actions` 表 + permissions 列
4. 重跑 `migrate_permission_unified_semantic.py`

所有变更独立提交，支持按步骤回退。

---

## 10. TBD 列表

| ID | 状态 | 结论 |
|----|------|------|
| ~~TBD-1~~ | **已关闭** | `yaml_loader.py` 用 `glob("*.yaml")` 扫描，无 `_` 前缀过滤。`_standard_actions.yaml` 必须在 `load_yaml_directory()` 的排除列表中加入，由 `StandardActionLoader` 独立加载。`_template.yaml` 也存在同样的问题但不在本次范围。 |
| ~~TBD-2~~ | **已关闭** | `permissions.action_code` 连同 `action_id` 一起删除。`PermissionSyncService.sync_all()` INSERT 语句不写这两列，删除无任何影响。 |

---

**Spec + RFC 包含 10 个章节，2 个 TBD 均已关闭。** 共涉及 15 个文件变更（3 新增 + 9 修改 + 3 删除），经代码级逐行验证确认全套 `meta_action` 功能为僵尸代码，变更安全性极高。

> ⚠️ Spec + RFC 已完整，待确认后立即按 Step 1-10 实施。
