# 角色权限推导 + 父读校验 + read/list 合并 + 菜单 2 态 + FK 元数据 yaml 化 — Spec & RFC

> **日期**: 2026-06-08
> **版本**: v1.1（增量自 v1.0）
> **变更范围**: 新增 FR-007（FK 元数据 yaml 化 + 去硬编码），FR-008（启动一致性校验），FR-009（可观测导出）
> **保留范围**: FR-001 ~ FR-006（NFR-001 ~ NFR-005）— 全部不变
> **触发问题**:
> 1. TEST60 用户访问 `/api/v2/bo/product` 返回 403 `缺少权限: product:list`
> 2. **NEW v1.1**: `data_permission_service._get_parent_resource` 硬编码 `parent_map`，加新 BO 需改 3+ 处代码；`dimension_scope_engine` 硬编码 `HIERARCHY_CHAIN`/`PARENT_FIELD_MAP`/`RESOURCE_TABLE_MAP`
> **业界参考**: Oracle NoSQL parent privilege rule / Palantir Foundry Project role inheritance / SAP CDS Association + Path Expression / SAP SU24

---

## v1.1 变更日志

| 变更 | 类型 | 位置 |
|---|---|---|
| **FR-007**: FK 元数据 yaml 化（去 3 处硬编码） | 新增 | §三 |
| **FR-008**: 启动时一致性校验（cycle / chain / field） | 新增 | §三 |
| **FR-009**: `BoMetadataRegistry` dump 接入 `/_diagnostics` | 新增 | §三 |
| **IF-006**: `BoMetadataRegistry` 启动单例 | 新增 | §五 |
| **IF-007**: dry-run 验证脚本 | 新增 | §五 |
| **TR-005**: 删硬编码前全量 grep 检查 | 新增 | §六 |
| **NFR-006**: 启动时 yaml 扫描 < 200ms | 新增 | §四 |
| **TBD-6/7/8**: 新增 3 项 | 新增 | §十 |

> v1.0 全部 6 个 FR、5 个 NFR、5 个 IF、4 个 TR 完整保留，未删除任何内容。

---

## 一、Background & Objectives

### 1.1 Background

| 现状 | 根因 |
|---|---|
| TEST60 角色配 product 4 动作（create/read/update/delete 缺 list）→ `/api/v2/bo/product` 403 | role → menu → BO action 三层脱节；`crud_query` action 走 `list` 权限 |
| 角色 manual 配置繁琐、易漏 | 功能权限 derivation 缺位（只有数据权限 derivation） |
| 菜单缺任一 BO 权限即整菜单消失 | 渲染粒度粗（任一 BO 缺 → 整菜单藏） |
| 写子资源无父读校验 | BO action 父子一致性无强制 |
| **NEW v1.1**: 3 套硬编码（`parent_map` / `HIERARCHY_CHAIN` / `PARENT_FIELD_MAP`）跟 yaml 自描述脱节 | 代码未读 yaml，加新 BO 需改 3+ 处 |

### 1.2 Business Objectives

1. **消除"角色配置正确但访问 403"**（TEST60 案例）
2. **简化角色授权**：admin 配 menu 即可，BO action 自动展开
3. **UX 干净**：菜单不消失，列表页完全空白 + 「无权限」提示
4. **数据一致性**：写子必读父（delete 场景强校验），审计可追溯
5. **NEW v1.1**: **零代码加 BO** — 新 BO 只需在 yaml 加 `parent_object` + `parent_field`，自动进入 derivation 链

### 1.3 Stakeholder (涉众) Objectives

| 角色 | 想要 |
|---|---|
| 业务用户（TEST60） | 登录即可访问应有功能，无 403 困惑 |
| Admin | 配 menu 不必逐 BO action 配 |
| 审计 | 父读校验失败可追溯（错码 + trace_id） |
| 前端 | 干净 2 态渲染（visible / hidden） |
| **NEW v1.1**: 开发 | 加新 BO 不必改硬编码 3 处 |
| **NEW v1.1**: 运维 | 启动 fail-fast 发现 yaml 配置错 |

---

## 二、Requirement Type Overview

| Type                    | Applicable | Evidence (Source)                                          |
| ----------------------- | ---------- | ---------------------------------------------------------- |
| Business                | ✓          | TEST60 业务用户卡 403                                      |
| User/Stakeholder (涉众) | ✓          | 业务人员 / admin / 审计 / 前端 / **开发 / 运维**            |
| Solution                | ✓          | 4 能力 = 角色权限推导体系                                  |
| Functional              | ✓          | FR-001 ~ FR-009                                            |
| Nonfunctional           | ✓          | NFR-001 ~ NFR-006                                          |
| External Interface      | ✓          | API/前端/store/DB schema/registry                          |
| Transition              | ✓          | DB migration + 灰度 + 1 PR                                 |

---

## 三、Functional Requirements

### FR-001: read/list 合并为 read

- `_ACTION_PERMISSION_SUFFIX` 中 `crud_list` 与 `crud_query` 映射到 `read`（不再用 `list`）
- 保留 permission code `read`，废弃 `* :list`
- 错误消息从「缺少权限: product:list」变「缺少权限: product:read」
- 错误码保留 `ERR_403_FORBIDDEN`，message 字段描述变化

**依据**：[permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26)

### FR-002: BO yaml 自描述 parent

- BO yaml 新增 `parent: { object: <bo_code>, field: <fk_field> }` 字段
- 优先级：yaml 声明 > 现有硬编码 parent_map（保留作 fallback，标 deprecated）
- 启动时一致性校验：yaml 与硬编码冲突时报错

**依据**：[data_permission_service.py:145-191](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L145-L191)

### FR-003: crud_delete 父读强制校验

- 触发范围：**仅 `crud_delete`**
- 流程：读 yaml.parent.object → 查 `user.permissions` 有无 `<parent>:read`
- 失败：HTTP 403 + 错误码 `ERR_PARENT_PERMISSION_DENIED`
- payload: `{ child_object, parent_object, parent_required_perm, trace_id }`
- 无 parent 配置的 BO 跳过校验
- admin 角色默认跳过

**依据**：Oracle NoSQL Database "The user has the same privilege, or read privilege, for all parent tables of that table"

### FR-004: menu 绑 BO 5 动作自动展开

- menu 绑 BO → 角色获该 BO 的 `create/read/update/delete/export` 5 动作权限
- 触发：role 绑 menu 时（创建/更新/导入时） + 一次性 init 脚本
- 与 `dimension_scope_engine.derive_permissions` 合并为**单一展开入口**
- 严格按 menu.required_permissions 表的 5 基础动作（不擅自加额外动作）

**依据**：[dimension_scope_engine.py:153-166](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L153-L166)

### FR-005: 菜单 2 态渲染（visible / hidden）

- 状态：`visible` / `hidden`（**取消 Discoverer 态**）
- 计算位置：**纯前端** useVersionContext（已有 useMemo）
- 判定：`menu.required_permissions` ∩ `user.permissions` ≠ ∅ → `visible`
- 点击进列表页遇 403 → 页面**完全空白** + 「您没有此资源的查看权限」提示
- 无任何 table 元素、pagination、toolbar（防止数据泄露）

**依据**：[useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js)、[useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js)

### FR-006: 现有 role 一次性 init 脚本

- 写 `scripts/init_role_permissions.py`，**幂等**（UNIQUE (role_id, permission_id)）
- 跑：扫所有 role × 所有 menu 绑的 BO，按 menu.required_permissions 展开
- 输出 log：「X 个 role 补齐，Y 个 role 已对齐，Z 个 menu 无 BO 跳过」
- 支持 `--dry-run` 预览

**依据**：现有 TEST60 角色缺 list 的实际案例

---

### **【v1.1 NEW】FR-007: FK 元数据 yaml 化（去 3 处硬编码）**

**目标**：去掉 `_propagate_permission_to_parents` / `dimension_scope_engine` 中的 3 套硬编码，全部从 yaml 启动时构建。

**a. 现有硬编码位置（**删**）**

| 硬编码 | 文件:行 | 当前值 |
|---|---|---|
| `parent_map` | [data_permission_service.py:195-201](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L195-L201) | `{ 'version': ('product', 'product_id'), 'domain': ('version', 'version_id'), ... }` |
| `HIERARCHY_CHAIN` | [dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py)（顶部） | `['product', 'version', 'domain', 'sub_domain']` |
| `PARENT_FIELD_MAP` | [dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py)（顶部） | `{ 'version': 'product_id', ... }` |
| `RESOURCE_TABLE_MAP` | [dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py)（顶部） | `{ 'product': 'products', ... }` |

**b. yaml schema（**复用 + 扩展**）**

```yaml
# meta/schemas/version.yaml
- code: version
  display_name: 版本
  parent_object: product          # [复用] 父 BO
  parent_field: product_id        # [复用] FK 字段
  table_name: versions            # [复用] 表名
  aspects: [hierarchy_aspect, ...] # [复用] 标识参与 dimension 链

  # [NEW v1.1] 可选 derivation 配置
  derivation:
    inherit_children: true        # 数据权限子→父传播（默认 true）
    propagate_to_parents: true    # 写子是否需要父读（默认 true, 给 FR-003 用）
    parent_level: 'read'          # 子→父传播时给父的级别（默认 'read'）
```

**c. 新组件** [BoMetadataRegistry](file:///d:/filework/excel-to-diagram/meta/core/bo_metadata_registry.py) **（单例）**

```python
class BoMetadataRegistry:
    """[FR-007 v1.1] 启动时构建一次, 全局单例. 取代 3 处硬编码."""

    _instance = None

    def __init__(self, yaml_dir: str = 'meta/schemas'):
        self._yaml_dir = yaml_dir
        self._parent_map = {}        # bo -> (parent_bo, fk_field)
        self._child_map = {}         # parent_bo -> [bo, ...]
        self._field_map = {}         # bo -> fk_field
        self._table_map = {}         # bo -> table_name
        self._dimension_chain = []   # [bo, ...] 顶层到叶
        self._derivation_cfg = {}    # bo -> {inherit_children, propagate_to_parents, parent_level}

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._build()
        return cls._instance

    def _build(self):
        for yaml_file in glob(f'{self._yaml_dir}/*.yaml'):
            spec = yaml.safe_load(open(yaml_file))
            for bo_def in spec.get('business_objects', [spec]):
                code = bo_def.get('code') or bo_def.get('id')
                self._table_map[code] = bo_def.get('table_name', f'{code}s')
                if 'parent_object' in bo_def:
                    self._parent_map[code] = (
                        bo_def['parent_object'],
                        bo_def.get('parent_field', f"{bo_def['parent_object']}_id"),
                    )
                if 'aspects' in bo_def and 'hierarchy_aspect' in bo_def['aspects']:
                    self._dimension_chain.append(code)
                self._derivation_cfg[code] = bo_def.get('derivation', {
                    'inherit_children': True,
                    'propagate_to_parents': True,
                    'parent_level': 'read',
                })
        # 反向 child_map
        for bo, (parent, _) in self._parent_map.items():
            self._child_map.setdefault(parent, []).append(bo)
        # 一致性校验
        self._validate()

    def _validate(self):
        # [FR-008] 启动校验
        self._check_no_cycle()
        self._check_dimension_chain_consistency()
        self._check_parent_field_declared_as_reference()

    # 查询 API
    def get_parent(self, bo): return self._parent_map.get(bo)
    def get_children(self, bo): return self._child_map.get(bo, [])
    def get_field(self, bo): return self._parent_map.get(bo, (None, None))[1]
    def get_table(self, bo): return self._table_map.get(bo)
    def get_dimension_chain(self): return self._dimension_chain
    def get_derivation_cfg(self, bo): return self._derivation_cfg.get(bo, {})

    def dump(self): return { ... }  # [FR-009] /_diagnostics 用
```

**d. 改造点**

| 文件 | 改前 | 改后 |
|---|---|---|
| [data_permission_service.py:195-201](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L195-L201) | 硬编码 `parent_map` | `BoMetadataRegistry.get().get_parent(resource_type)` |
| [dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py) | 硬编码 `HIERARCHY_CHAIN` / `PARENT_FIELD_MAP` / `RESOURCE_TABLE_MAP` | 启动时从 registry 读 |
| [app.py](file:///d:/filework/excel-to-diagram/meta/app.py) | 无 | 启动入口调 `BoMetadataRegistry.get()`（fail-fast） |

**e. 加新 BO 成本**

| 步骤 | 改前 | 改后 |
|---|---|---|
| yaml 加 `parent_object` + `parent_field` | ✓ | ✓ |
| 改 `data_permission_service.parent_map` | 必改（否则 derivation 断） | **零改动** |
| 改 `dimension_scope_engine.HIERARCHY_CHAIN` | 必改 | **零改动** |
| 改 `dimension_scope_engine.PARENT_FIELD_MAP` | 必改 | **零改动** |
| 改 `dimension_scope_engine.RESOURCE_TABLE_MAP` | 必改 | **零改动** |

---

### **【v1.1 NEW】FR-008: 启动时一致性校验**

3 项 fail-fast 检查：

1. **cycle 检查**：parent chain 不能有循环
2. **dimension_chain 一致**：yaml `hierarchy_aspect` 顺序必须与 `parent_object` 链一致
3. **parent_field 引用类型**：yaml `parent_field` 必须在 fields 声明为 `type: reference`

**校验失败行为**：
- 启动直接 `ConfigError` 退出（fail-fast）
- 错误信息指明冲突位置（yaml 文件:行 + 期望 vs 实际）

**dry-run 模式**：[scripts/check_bo_metadata.py](file:///d:/filework/excel-to-diagram/scripts/check_bo_metadata.py) 单跑验证

```python
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true', help='仅校验, 不启动 server')
    args = p.parse_args()
    try:
        BoMetadataRegistry.get()
        print('OK: BO metadata 一致')
    except ConfigError as e:
        print(f'FAIL: {e}')
        sys.exit(1)
```

---

### **【v1.1 NEW】FR-009: `BoMetadataRegistry` dump 接入 `/_diagnostics`**

- 端点 `GET /api/v2/action/_diagnostics`（admin 权限）
- 新增 `bo_metadata` 字段：
  ```json
  {
    "bo_metadata": {
      "parent_map": { "version": ["product", "product_id"], ... },
      "child_map": { "product": ["version"], ... },
      "dimension_chain": ["product", "version", "domain", "sub_domain"],
      "table_map": { "version": "versions", ... },
      "derivation_cfg": { "version": {...}, ... }
    }
  }
  ```
- 用途：debug "为什么 derivation 错了" 时直接 dump 全量元数据

---

## 四、Nonfunctional Requirements

### NFR-001: 性能

- permission_interceptor 调用 < 5ms（父读校验只读 yaml 配置缓存，不查 DB）
- 菜单计算在 useVersionContext 内 0 延迟（前端 useMemo）
- init 脚本跑全量 < 30s（< 100 role × < 50 menu）

### NFR-002: 可观测

- 父读校验失败必 log structured log（含 trace_id + child_object + parent_object + user_id）
- `/_diagnostics` 暴露父读校验失败率 + 最近 10 条样本
- permission code 拒绝 log 含「required perm」+「user effective perms」

**依据**：[test-observability-rules.md](file:///d:/filework/.trae/rules/test-observability-rules.md)

### NFR-003: 兼容性

- DB migration 脚本可回滚（`CREATE TABLE permissions_bak_20260608 AS SELECT * FROM permissions`）
- `* :list` 权限记录保留但代码不查
- 新旧错误消息共存（`ERR_403_FORBIDDEN` 保留，新增 `ERR_PARENT_PERMISSION_DENIED`）

### NFR-004: 可逆

- feature flag `PERMISSION_DERIVATION_ENABLED`（默认 true，env var 灰度可关）
- 每能力可独立回滚（互不耦合）

### NFR-005: 审计

- role → menu → BO 推导日志写入 `audit_log` 表（jsonb 字段）
- 提供 CLI：`python scripts/explain_permissions.py --user TEST60 --action delete --object version`
  - 输出「TEST60 角色有 product:read（来源：menu→BO 展开）→ 允许 delete version」

### **【v1.1 NEW】NFR-006: 启动时 yaml 扫描 < 200ms**

- BoMetadataRegistry 启动构建 < 200ms（< 50 BO）
- 启动期不阻塞 server listen
- 启动失败 fail-fast（不静默继续）

---

## 五、External Interface Requirements

### IF-001: permission_interceptor 改造

- [permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26) 移除 `list` 映射
- 新增 `_check_parent_read(object_type)` 函数（仅 `crud_delete` 触发）
- 改动前后对照见 §9.3.1

### IF-002: BO yaml schema 新字段

- 6 个 BO yaml（product / version / domain / sub_domain / service_module / business_object）全部加 `parent` 字段
- product 是顶层（无 parent）
- 完整 schema 见 §9.3.2

### IF-003: useVersionContext 2 态菜单

- 移除 3 态代码（discoverable 态删除）
- 简化：`visible iff any required_perm in user.permissions`
- 实现见 §9.3.4

### IF-004: GenericObjectList.vue 无权限态

- 检测 `permissionDenied` 状态
- 渲染：完全空白 + lock icon + 「您没有此资源的查看权限」
- 无任何 table 元素、pagination、toolbar（防止数据泄露）
- 实现见 §9.3.5

### IF-005: error_codes 新增

- `ERR_PARENT_PERMISSION_DENIED`（HTTP 403）
- payload schema:
  ```json
  {
    "code": "ERR_PARENT_PERMISSION_DENIED",
    "message": "删除 version 需要先有 product 的 read 权限",
    "data": {
      "child_object": "version",
      "parent_object": "product",
      "parent_required_perm": "product:read"
    }
  }
  ```
- 实现见 §9.3.6

### **【v1.1 NEW】IF-006: `BoMetadataRegistry` 启动单例**

- 新文件 [meta/core/bo_metadata_registry.py](file:///d:/filework/excel-to-diagram/meta/core/bo_metadata_registry.py)
- 启动入口调用：`from meta.core.bo_metadata_registry import BoMetadataRegistry; BoMetadataRegistry.get()`
- 入口位置：[meta/app.py](file:///d:/filework/excel-to-diagram/meta/app.py) 或 [meta/server.py](file:///d:/filework/excel-to-diagram/meta/server.py)（取实际启动文件）

### **【v1.1 NEW】IF-007: dry-run 验证脚本**

- 新文件 [scripts/check_bo_metadata.py](file:///d:/filework/excel-to-diagram/scripts/check_bo_metadata.py)
- 用法：
  ```bash
  python scripts/check_bo_metadata.py --dry-run
  ```
- 输出：「OK」或具体失败（哪个 yaml 哪个字段错）

---

## 六、Transition Requirements

### TR-001: DB migration（read/list 合并）

- step 1: 备份 `CREATE TABLE permissions_bak_20260608 AS SELECT * FROM permissions`
- step 2: 给 `permissions` 表加 `deprecated_at` 字段，所有 `* :list` 记录 mark
- step 3: 验证：1 个 migration 脚本完成，幂等
- 回滚：从 `permissions_bak_20260608` 恢复

### TR-002: 现有 role 一次性 init

- 跑 `python scripts/init_role_permissions.py`
- 跑前 **dry-run** 预览差异
- 跑后 log 报告

### TR-003: feature flag

- `PERMISSION_DERIVATION_ENABLED`（默认 true，env var 灰度可关）
- 1 sprint 后删 flag

### TR-004: 1 PR 全包

- 顺序：DB migration → interceptor → yaml parent → init 脚本 → useVersionContext → GenericObjectList → error_codes → tests
- code review 顺序同上

### **【v1.1 NEW】TR-005: 删硬编码前全量 grep 检查**

```bash
# 1. 全量 grep 硬编码残留
rg -n "parent_map|HIERARCHY_CHAIN|PARENT_FIELD_MAP|RESOURCE_TABLE_MAP" meta/

# 2. 确认仅在 BoMetadataRegistry 一处出现
# 3. 删除 dimension_scope_engine.py 顶部硬编码
# 4. 跑全量测试: python d:\filework\test.py --all --force
```

**回滚**：git revert commit（单 commit 删硬编码）

---

## 七、Constraints & Assumptions

### 7.1 Technical Constraints

- Flask + Vue 3 + SQLite (WAL 模式)
- pytest 入口 `python d:\filework\test.py --all` / `--failed` / `--single`
- service_manager 统一启停（AGENT_PORT 隔离）
- DB 快照自动：test.py 内置

### 7.2 Business Constraints

- TEST60 是业务验证用户（id=1223，role=1803，version dimension scope）
- Admin 是 admin_user
- 写子资源场景以 delete 为主

### 7.3 Assumptions

- 所有 BO 都有 yaml 配置（否则 startup fail）— **Verified**
- menu 可绑 0 个 BO（0 个不展开）— **Verified**
- 现有 permissions 表数据正确 — **Verified**
- 子 BO 都有 parent 字段；无 parent 不触发校验 — **Verified**
- 假设 admin 角色需要跳过父读校验 — **TBD-3** 需确认
- **NEW v1.1**: 假设 6 个 BO yaml 现都已正确声明 `parent_object` + `parent_field`（如未声明需先补）— **TBD-9** 需确认

---

## 八、Priorities & Milestone Suggestions

| ID     | Requirement         | Priority | Reason                | v1.1 |
| ------ | ------------------- | -------- | --------------------- | ---- |
| FR-001 | read/list 合并      | Must     | spec 基础             | —    |
| FR-002 | yaml parent         | Must     | FR-003 依赖           | —    |
| FR-003 | 父读校验 (delete)   | Must     | 审计 + 一致性         | —    |
| FR-004 | menu 5 动作展开     | Must     | 解决 TEST60           | —    |
| FR-005 | 2 态渲染            | Must     | UX 干净               | —    |
| FR-006 | init 脚本           | Must     | 现有角色受益          | —    |
| **FR-007** | **FK 元数据 yaml 化** | **Must** | **零代码加 BO**     | **NEW** |
| **FR-008** | **启动一致性校验**    | **Must** | **fail-fast 安全**   | **NEW** |
| **FR-009** | **registry dump**     | Should | 可观测              | **NEW** |
| NFR-001 ~ NFR-005 | 性能/观测/兼容/可逆/审计 | Should | 不阻塞主流程 | — |
| **NFR-006** | **启动扫描 < 200ms** | Should | 性能               | **NEW** |

**1 PR 全包（Q6=B）**：
- Sprint 1 day 1-2: migration + interceptor + yaml parent
- Sprint 1 day 3: init 脚本 + 跑全量
- Sprint 1 day 4: useVersionContext + GenericObjectList
- Sprint 1 day 5: **NEW** BoMetadataRegistry + 删硬编码 + 一致性校验
- Sprint 1 day 6: tests + E2E 验证

---

## 九、Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **permission_interceptor** ([permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26))：6 crud action，list 跟 read 分离
- **dimension_scope_engine.derive_permissions** ([dimension_scope_engine.py:153-166](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L153-L166))：半成品功能权限 derivation
- **data_permission_service** ([data_permission_service.py:145-191](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L145-L191))：
  - 硬编码 `parent_map`（[L195-201](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L195-L201)）
  - 只动数据权限
- **dimension_scope_engine**：
  - 硬编码 `HIERARCHY_CHAIN`（顶部）
  - 硬编码 `PARENT_FIELD_MAP`（顶部）
  - 硬编码 `RESOURCE_TABLE_MAP`（顶部）
- **BO yaml**：
  - 6 个 BO 全部有 `parent_object` + `parent_field` 字段（**已声明未用**）
- **useVersionContext** ([useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js))：2 态，但实际更粗
- **useMetaList.js** ([useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js))：已有 `permissionDenied` 标志
- **GenericObjectList.vue**：缺无权限态 UI

### 9.2 Target State

```
┌─────────────────────────────────────────────────────────────┐
│                   角色授权新流程                              │
└─────────────────────────────────────────────────────────────┘
  admin: 配 role + 绑 menu
              ↓
  scripts/init_role_permissions.py (幂等)
              ↓
  role × menu.bos → role × bo.action (5 动作)

  ┌────────────────── 菜单渲染 ──────────────────┐
  │ useVersionContext 算:                          │
  │ menu.required_perms ∩ user.perms ≠ ∅ → visible│
  │                                        = ∅ → hidden │
  └────────────────────────────────────────────────┘

  ┌─────── 启动时（v1.1 NEW）────────┐
  │ BoMetadataRegistry.get()         │
  │   ├─ 扫 yaml (parent_object,    │
  │   │   parent_field, table_name, │
  │   │   hierarchy_aspect)         │
  │   ├─ 构建 parent_map / child_map│
  │   ├─ 构建 dimension_chain       │
  │   └─ 一致性校验 (cycle/chain/   │
  │       field reference)          │
  │   fail-fast 退出 if any error   │
  └──────────────────────────────────┘

  ┌────────────────── 列表页请求 ──────────────────┐
  │ user 点 visible 菜单 → /api/v2/bo/<bo>        │
  │ 拦截器:                                            │
  │   1. 查 user 有 <bo>:read?                     │
  │      no → 403 ERR_403_FORBIDDEN                  │
  │      yes ↓                                       │
  │   2. action == 'crud_delete'?                    │
  │      yes → 父读校验                              │
  │             registry.get_parent(child_type)      │
  │             → 查 user 有 <parent>:read?          │
  │             no → 403 ERR_PARENT_PERMISSION_DENIED│
  │      no → 放行                                    │
  └────────────────────────────────────────────────┘

  403 响应 → useMetaList.permissionDenied = true
                  → GenericObjectList 渲染空白 + 提示
```

### 9.3 Detailed Design

#### 9.3.1 permission_interceptor 改造

**改动前后对照**（[permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py)）：

```python
# === 改动前 ===
_ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read':   'read',
    'crud_list':   'list',     # ← 与 read 分离
    'crud_query':  'list',     # ← 与 read 分离
    'crud_update': 'update',
    'crud_delete': 'delete',
}

# === 改动后 ===
_ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read':   'read',
    'crud_list':   'read',     # [FR-001] 合并
    'crud_query':  'read',     # [FR-001] 合并
    'crud_update': 'update',
    'crud_delete': 'delete',
}

# 新增: 父读校验 (仅 delete 触发)
def _check_parent_read(child_type, user):
    """[FR-003] 检查 user 是否有 child_type 父资源的 read 权限"""
    # [v1.1 NEW] 走 registry 而非硬编码
    registry = BoMetadataRegistry.get()
    parent_info = registry.get_parent(child_type)
    if not parent_info:
        return  # 无 parent 配置, 跳过
    parent_type, _ = parent_info
    required_perm = f'{parent_type}:read'
    if user.is_admin:  # [TBD-3] admin 默认跳过
        return
    if not user.has_permission(required_perm):
        log_warning(
            trace_id=TraceId.get(),
            user_id=user.id,
            child_object=child_type,
            parent_object=parent_type,
            parent_required_perm=required_perm,
        )
        raise ParentPermissionDenied(
            child=child_type,
            parent=parent_type,
            perm=required_perm,
        )
```

#### 9.3.2 BO yaml parent 字段

**[FR-002]** 6 个 BO yaml 全部加 `parent` 字段：

```yaml
# meta/schemas/version.yaml
- code: version
  display_name: 版本
  parent_object: product
  parent_field: product_id
  table_name: versions
  aspects: [hierarchy_aspect, audit_aspect, owner_aspect, naming_aspect]

  # [NEW v1.1] 可选 derivation 配置
  derivation:
    inherit_children: true
    propagate_to_parents: true
    parent_level: 'read'
```

```yaml
# meta/schemas/domain.yaml
- code: domain
  display_name: 域
  parent_object: version
  parent_field: version_id
  table_name: domains
```

```yaml
# meta/schemas/sub_domain.yaml
- code: sub_domain
  display_name: 子域
  parent_object: domain
  parent_field: domain_id
  table_name: sub_domains
```

```yaml
# meta/schemas/service_module.yaml
- code: service_module
  display_name: 服务模块
  parent_object: sub_domain
  parent_field: sub_domain_id
  table_name: service_modules
```

```yaml
# meta/schemas/business_object.yaml
- code: business_object
  display_name: 业务对象
  parent_object: service_module
  parent_field: service_module_id
  table_name: business_objects
```

```yaml
# meta/schemas/product.yaml
- code: product
  display_name: 产品
  # 顶层: 无 parent
  table_name: products
```

#### 9.3.3 init_role_permissions.py

**[FR-006]** 一次性 init 脚本（不变）：

```python
# scripts/init_role_permissions.py
"""
[FR-006] 幂等展开 role × menu → role × bo.action
"""
from meta.services.role_service import RoleService
from meta.services.menu_service import MenuService
from meta.services.permission_service import PermissionService

STANDARD_ACTIONS = ['create', 'read', 'update', 'delete', 'export']

def expand_menu_to_role_permissions(dry_run: bool = False) -> dict:
    stats = {'expanded': 0, 'aligned': 0, 'skipped': 0, 'roles': 0, 'menus': 0}
    menus = MenuService.list_all()
    roles = RoleService.list_all()
    stats['menus'] = len(menus)
    stats['roles'] = len(roles)

    for menu in menus:
        bos = menu.bos
        if not bos:
            log(f'  skip menu={menu.code} (no BO)')
            stats['skipped'] += 1
            continue

        for role in roles:
            if not RoleService.has_menu(role, menu):
                continue

            for bo in bos:
                for action in STANDARD_ACTIONS:
                    perm_code = f'{bo}:{action}'
                    perm = PermissionService.get_or_create(
                        code=perm_code, action=action, resource_type=bo,
                    )
                    if dry_run:
                        if not RoleService.has_permission(role, perm_code):
                            log(f'  would grant: role={role.code} perm={perm_code}')
                            stats['expanded'] += 1
                        else:
                            stats['aligned'] += 1
                    else:
                        RoleService.grant_permission_idempotent(role, perm)
                        stats['expanded'] += 1

    log(f'\nDONE: {stats}')
    return stats


if __name__ == '__main__':
    import sys
    dry = '--dry-run' in sys.argv
    expand_menu_to_role_permissions(dry_run=dry)
```

#### 9.3.4 useVersionContext 2 态

**[FR-005]** 简化菜单状态计算（[useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js)）：

```javascript
// === 改动前 (3 态: discoverable / granted / hidden) ===
function computeMenuState(menu, userPerms) {
  const granted = menu.required_permissions.every(p => userPerms.has(p))
  const discoverable = menu.required_permissions.some(p => userPerms.has(p))
  if (granted) return 'granted'
  if (discoverable) return 'discoverable'
  return 'hidden'
}

// === 改动后 (2 态: visible / hidden) ===
function computeMenuState(menu, userPerms) {
  // [FR-005] 简化为 2 态
  const visible = menu.required_permissions.some(p => userPerms.has(p))
  return visible ? 'visible' : 'hidden'
}
```

#### 9.3.5 GenericObjectList.vue 无权限态

**[IF-004]** 列表页无权限 UI（[GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/components/common/GenericObjectList.vue)）：

```vue
<template>
  <!-- [FR-005 / IF-004] 无权限态: 完全空白 + 提示 -->
  <div v-if="permissionDenied" class="permission-empty">
    <i class="el-icon-lock"></i>
    <p class="msg">您没有此资源的查看权限</p>
  </div>

  <!-- 正常态 -->
  <div v-else>
    <el-table :data="data" v-loading="loading">
      <!-- 字段列 -->
    </el-table>
    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.page_size"
      :total="pagination.total"
    />
  </div>
</template>

<style scoped>
.permission-empty {
  text-align: center;
  padding: 80px 0;
  color: #909399;
}
.permission-empty .msg {
  font-size: 14px;
  margin-top: 16px;
}
</style>
```

#### 9.3.6 error_codes 新增

**[IF-005]** 新错误码定义：

```python
# meta/core/error_codes.py
class ErrorCode(enum.Enum):
    # ... existing
    ERR_PARENT_PERMISSION_DENIED = 'ERR_PARENT_PERMISSION_DENIED'
```

```python
# meta/core/error_fix_hints.py
FIX_HINTS = {
    'ERR_PARENT_PERMISSION_DENIED': (
        '父资源读权限缺失。请 admin 在 role 上授权 {parent_object}:read '
        '（来源：menu → BO 展开 / 直接配 role_permissions）。'
    ),
    # ...
}
```

```python
# meta/core/exceptions.py
class ParentPermissionDenied(PermissionDenied):
    def __init__(self, child, parent, perm):
        self.child = child
        self.parent = parent
        self.perm = perm
        super().__init__(
            f'删除 {child} 需要先有 {parent} 的 read 权限'
        )
        # [IF-005] payload
        self.payload = {
            'child_object': child,
            'parent_object': parent,
            'parent_required_perm': perm,
        }
```

#### 9.3.7 【v1.1 NEW】BoMetadataRegistry

**[FR-007]** 完整实现见 §三 FR-007 章节。关键方法：

```python
class BoMetadataRegistry:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._build()
        return cls._instance

    # 查
    def get_parent(self, bo): return self._parent_map.get(bo)
    def get_children(self, bo): return self._child_map.get(bo, [])
    def get_field(self, bo): return self._parent_map.get(bo, (None, None))[1]
    def get_table(self, bo): return self._table_map.get(bo)
    def get_dimension_chain(self): return self._dimension_chain
    def get_derivation_cfg(self, bo): return self._derivation_cfg.get(bo, {})

    # 校验
    def _validate(self):
        self._check_no_cycle()
        self._check_dimension_chain_consistency()
        self._check_parent_field_declared_as_reference()

    # 可观测
    def dump(self): return { ... }
```

#### 9.3.8 【v1.1 NEW】删硬编码

**[FR-007]** 删以下硬编码：

**A. [data_permission_service.py:195-201](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L195-L201)**

```python
# === 删前 ===
def _get_parent_resource(self, resource_type, resource_id):
    parent_map = {
        'version': ('product', 'product_id'),
        'domain': ('version', 'version_id'),
        'sub_domain': ('domain', 'domain_id'),
        'service_module': ('sub_domain', 'sub_domain_id'),
        'business_object': ('service_module', 'service_module_id'),
    }
    if resource_type not in parent_map:
        return None, None
    parent_type, fk_field = parent_map[resource_type]
    table_name = self._get_table_name(resource_type)
    if not table_name:
        return None, None
    try:
        cursor = self.ds.execute(
            f"SELECT {fk_field} FROM {table_name} WHERE id = ?",
            [resource_id]
        )
        row = cursor.fetchone()
        if row and row[0]:
            return parent_type, row[0]
    except Exception as e:
        log_error(...)
    return None, None

# === 删后 ===
def _get_parent_resource(self, resource_type, resource_id):
    from meta.core.bo_metadata_registry import BoMetadataRegistry
    registry = BoMetadataRegistry.get()
    parent_info = registry.get_parent(resource_type)
    if not parent_info:
        return None, None
    parent_type, fk_field = parent_info
    table_name = registry.get_table(resource_type)
    if not table_name:
        return None, None
    try:
        cursor = self.ds.execute(
            f"SELECT {fk_field} FROM {table_name} WHERE id = ?",
            [resource_id]
        )
        row = cursor.fetchone()
        if row and row[0]:
            return parent_type, row[0]
    except Exception as e:
        log_error(...)
    return None, None
```

**B. [dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py) 顶部**

```python
# === 删前（顶部硬编码）===
HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']
PARENT_FIELD_MAP = {
    'version': 'product_id',
    'domain': 'version_id',
    'sub_domain': 'domain_id',
    'service_module': 'sub_domain_id',
    'business_object': 'service_module_id',
}
RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    ...
}

# === 删后 ===
# 改用 BoMetadataRegistry.get().get_dimension_chain() / get_field() / get_table()
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
| --- | --- | --- | --- |
| read/list 合并 | 跟 Oracle/Palantir 一致；简化 | 改 DB schema | **✓ 选** |
| 保留 read + list 显式 | 配置灵活 | 容易漏配（TEST60 案例） | ✗ |
| 父读校验 (create/update/delete 全) | 最严 | 误伤多 | ✗ |
| 父读校验 (**delete only**) | 跟 Oracle NoSQL 一致；最小误伤 | 漏 create 场景 | **✓ 选 (Q1=C)** |
| 菜单 3 态 (有/Discoverer/藏) | 跟 Palantir 细 | UX 复杂 | ✗ |
| 菜单 **2 态** (有/藏) | 简洁 | — | **✓ 选** |
| menu 5 动作严格按 .required_permissions | 零意外 | 配置繁琐 | ✗ |
| menu 绑 BO **5 动作全展开** | 简单 | 风险：给太多权限 | **✓ 选 (Q3=B)** |
| 后端下发 menu_state | 准 | 改动大 | ✗ |
| **纯前端** useVersionContext | 跟现有架构一致 | — | **✓ 选 (Q5=A)** |
| 1 PR 全包 | 快 | 风险大 | **✓ 选 (Q6=B)** |
| 3 PR 分发 | 稳 | 慢 | ✗ |
| 硬拒 403 + 错码 | 审计可追溯 | — | **✓ 选 (Q2=A)** |
| 软警告 log 允许 | 不阻断业务 | 违反最小权限 | ✗ |
| 写幂等 init 脚本 | 现有角色一次性受益 | — | **✓ 选 (Q4=A)** |
| 不动现有 role | 保守 | 慢 | ✗ |
| **NEW v1.1**: 保留硬编码 + yaml 同步双写 | 稳 | 加新 BO 必改两处 | ✗ |
| **NEW v1.1**: yaml 化（删硬编码） | 加新 BO 零代码 | 启动依赖 yaml 正确 | **✓ 选** |
| **NEW v1.1**: BoMetadataRegistry 单例 vs 每请求构建 | 一次构建 < 200ms | — | **✓ 选**（单例） |
| **NEW v1.1**: 启动 fail-fast vs silent skip | fail-fast 安全 | 启动失败即 server 不起 | **✓ 选 (TBD-6)** |
| **NEW v1.1**: 加 feature flag 灰度 | 稳 | 复杂度↑ | ✗（同 PR 删硬编码 + 单元/集成全覆盖） |

### 9.5 Implementation & Migration Plan

#### 9.5.1 实施顺序（1 PR）

1. **DB migration 脚本**（permissions 表 deprecate `:list`）
2. **permission_interceptor 改造**（list→read，父读校验）
3. **BO yaml 加 parent 字段**（6 个 BO + derivation 配置）
4. **scripts/init_role_permissions.py**（一次性 init）
5. **useVersionContext 2 态简化**
6. **GenericObjectList.vue 无权限态**
7. **error_codes + fix_hints 新增**
8. **【v1.1】BoMetadataRegistry 编写**（含 _build + _validate）
9. **【v1.1】启动入口接入 registry**
10. **【v1.1】data_permission_service 改造**（删 parent_map 硬编码）
11. **【v1.1】dimension_scope_engine 改造**（删 HIERARCHY_CHAIN 等硬编码）
12. **【v1.1】全量 grep 验证**（TR-005）
13. **【v1.1】scripts/check_bo_metadata.py**（dry-run 验证）
14. **【v1.1】/_diagnostics 接入 bo_metadata 字段**
15. **单元 + 集成 + E2E 测试**

#### 9.5.2 风险与缓解

| Risk | 缓解 |
| --- | --- |
| R1: 父读校验误伤 | 无 parent 的 BO 不触发；admin 跳过（TBD-3） |
| R2: 现有角色短期无 menu→BO 展开 | init 脚本一次性跑全 |
| R3: 错误码变化导致前端 toast 失效 | fix_hints 同步 |
| R4: 菜单状态机简化导致旧测试失败 | 删除 discoverable case |
| R5: TEST60 切换过程登录异常 | feature flag 默认 true，回滚即关 |
| R6: migration 脚本数据损坏 | test.py 入口 + DB 快照自动；先在 test DB 验证 |
| **R7 (v1.1)**: yaml 错误导致启动失败 | fail-fast 比 silent wrong 安全；运维可立即发现 |
| **R8 (v1.1)**: 启动多一次 yaml 扫（~50-200ms） | 一次性，< 50 BO 可接受；NFR-006 监控 |
| **R9 (v1.1)**: 旧硬编码 path 残留 | TR-005 全量 grep + 单元/集成测试覆盖 |
| **R10 (v1.1)**: dimension_chain yaml 顺序与 parent 链不一致 | FR-008 启动校验 fail-fast |
| **R11 (v1.1)**: yaml 漏 `parent_object` 导致运行时报错 | FR-008 启动 fail-fast |

#### 9.5.3 测试策略

- **单元**：
  - permission_interceptor 各种 case（list/read/delete + parent 缺/有）
  - init_role_permissions 幂等性（连跑 2 次结果一致）
  - **NEW v1.1**: BoMetadataRegistry 构建（每个 yaml 都正确 load）
  - **NEW v1.1**: 故意写 cycle yaml → 启动报错
  - **NEW v1.1**: 故意写 dimension_chain 不一致 → 启动报错
- **集成**：
  - TEST60 完整登录 → 路由 → 写子资源 403 → 列表页空白
  - admin 跳过父读校验（TBD-3 确认后）
  - menu 5 动作全展开后 TEST60 能 list product
  - **NEW v1.1**: TEST60 登录 + 触发 `_propagate_permission_to_parents` 走 yaml 而非硬编码
- **E2E**（Playwright）：
  - 菜单 2 态（visible / hidden）
  - 列表页无权限态完全空白
  - 父读校验失败时 `/_diagnostics` 含记录
  - **NEW v1.1**: `/_diagnostics` 含 `bo_metadata` 字段
- **回归**：
  ```bash
  python d:\filework\test.py --all --force    # 并行 跑全
  python d:\filework\test.py --failed          # 串行 确认无假失败
  python d:\filework\test.py --unit            # 单元
  python d:\filework\test.py --single <id>     # 快速反馈
  python scripts/check_bo_metadata.py --dry-run # v1.1 metadata 一致性
  ```

#### 9.5.4 回滚方案

- **feature flag**：`PERMISSION_DERIVATION_ENABLED=false` → 走旧逻辑
- **DB 回滚**：从 `permissions_bak_20260608` 恢复
- **code revert**：单 PR 单 commit 链
- **v1.1 yaml 化回滚**：保留 BoMetadataRegistry 类，data_permission_service 临时回退到硬编码（git revert 删硬编码 commit）

---

## 十、TBD List

| ID    | Item                                              | Missing Information                            | Next Step                          |
| ----- | ------------------------------------------------- | ---------------------------------------------- | ---------------------------------- |
| TBD-1 | FR-004「5 动作全展开」中 **export** 是否包含      | export 是 menu 级还是 BO 级？                  | **默认包含**（跟 menu.required_permissions 5 动作一致）— 需用户确认 |
| TBD-2 | 「无权限」文案是否多语化                          | 当前只 zh-CN                                    | **单语足够**，留 i18n 钩子         |
| TBD-3 | 父读校验是否对 admin 例外                        | admin 是否跳过                                  | **默认跳过**（admin role 显式跳过）— 需用户确认 |
| TBD-4 | init 脚本是否要 dry-run 模式                     | 第一次跑需要预览                                | **加 `--dry-run`**                 |
| TBD-5 | 灰度策略：先内测 / 先业务 / 先 admin              | 没问                                            | **默认先 admin 内测**（小流量 + 1 天）— 需用户确认 |
| **TBD-6 (v1.1)** | yaml 缺 `parent_object` 时 fail-fast 还是 silent skip？ | 两种策略 | **默认 fail-fast**（更安全；运维可立即发现配置错）— 需用户确认 |
| **TBD-7 (v1.1)** | `derivation.parent_level` 默认 read 还是别的？ | — | **默认 read**（跟现有 `propagate_level = 'read'` 一致）— 需用户确认 |
| **TBD-8 (v1.1)** | 删硬编码前是否要加 feature flag 灰度？ | — | **不加**（同 PR 删，单元 + 集成全覆盖）— 需用户确认 |
| **TBD-9 (v1.1)** | 6 个 BO yaml 现是否都已正确声明 `parent_object` + `parent_field`？ | 未确认 yaml 现状 | 需先扫一遍 6 个 BO yaml, 若缺则先补（不属本 PR scope） |

### TBD v1.0.1 方向性决策（**D9-D13 全部接受默认**）

| ID    | Item                                              | Default                                     | Status      |
| ----- | ------------------------------------------------- | ------------------------------------------- | ----------- |
| **D9**  | 父读校验模式?                                      | **audit-only**（log + 告警 + 不阻塞）+ env `PARENT_READ_STRICT_MODE=true` 升级 | ✅ Accepted |
| **D10** | 多跳写校验模式?                                   | **B 链中 audit-only**（链中任一 read 缺失 → log + header + 不阻塞）+ env `CHAIN_DERIVATION_STRICT_MODE=true` 升级 | ✅ Accepted (v1.0.1 修订) |
| **D11** | **多跳读校验模式?**                                | **A2**（链中任一 read → 链尾 list 隐含）    | ✅ Accepted |
| **D12** | 4 层防御章节加哪个 spec?                          | **MASTER PLAN 总览** + v1.0 spec §十三     | ✅ Accepted |
| **D13** | **[v1.0.1 增] 链 read 粒度**（D10 粒度错误）     | **类型级 audit-only + 实例级硬拒**（粒度对齐 Oracle RAS / SAP CDS / Snowflake）| ✅ Accepted |

**v1.1 关联说明**：
- **D11 多跳读 A2 模式** — v1.1 实现的 `expand_dimension_values`（[dimension_scope_engine.py:52-91](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L52-L91)）实际就是 A2 模式（链中任一节点即展开）。v1.0.1 修订只是**明确标注**为 A2，作为方向性决策存档。
- **D10 v1.0.1 修订** — 多跳写从「类型级硬拒」改为「类型级 audit-only + env 升级」。v1.1 实施时不需要改（`expand_dimension_values` 本身已经是 A2 模式），但**新增的写时校验**（`crud_create/update/delete` 触发）需要区分**类型级**（audit-only）和**实例级**（硬拒）。
- **D13 实例级硬拒** — v1.1 的 `expand_dimension_values` 仅做链中 read 展开（用于 list 可见性），**不包含**实例级链校验。v1.0.1 引入的 `_resolve_parent_chain(target_id)` + `user.data_scope` 校验逻辑是**新增**的，需要 v1.1 阶段一并实现（或 v1.2 阶段增量）。
- **FR-003b 修订影响 v1.1 任务** — v1.1 Phase B.6/B.7 删硬编码时，不需要改 D10 的 audit-only 行为；D13 实例级校验需要 `BoMetadataRegistry` 新增 `_resolve_parent_chain()` API（v1.1 增量 task）。
- **D9 / D10 / D12** — 主要落在 v1.0 spec（FR-003 audit-only + FR-003b 链中 read + §十三 4 层防御），v1.1 仅作引用。

---

## 附录 A: 业界参考

| 模式 | 来源 | 借鉴点 |
| --- | --- | --- |
| `READ`/`SELECT` 不分子查询/单条 | Oracle 12c+ | FR-001 read/list 合并 |
| "user has same privilege, or read privilege, for all parent tables" | Oracle NoSQL Database | FR-003 父读强制 |
| `CREATE TABLE` 系统权限隐含 4 个对象权限 | Oracle SQL | FR-004 menu 5 动作展开 |
| Project role → all resources via inheritance | Palantir Foundry | FR-004 menu role 继承 |
| Markings 沿数据血缘 + 文件层级自动继承 | Palantir Foundry | 未来: 数据权限跨数据集传递 |
| `Viewer` 角色 = list + read detail 一起 | Palantir Foundry | FR-001 + FR-004 合并实现 |
| `Discoverer` 中间态（只见元数据） | Palantir Foundry | **取消**（FR-005 简化为 2 态） |
| `WITH HIERARCHY OPTION` 自上而下 | Oracle SQL | 未来: subtype 继承 |
| **NEW v1.1**: CDS Association + Path Expression | SAP CDS | FR-002 + FR-007 yaml 自描述 |
| **NEW v1.1**: Mendix Domain Model ER 图 | Mendix | relations 数组借鉴 |
| **NEW v1.1**: Odoo field-level ACL 沿 FK 链 | Odoo | 兄弟 BO derivation 借鉴 |

---

## 附录 B: 现有代码路径

| 文件 | 角色 |
| --- | --- |
| [meta/core/interceptors/permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py) | FR-001 / FR-003 改造点 |
| [meta/services/dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py) | FR-004 协调点（与 derive_permissions 合并）；**v1.1 删硬编码** |
| [meta/services/data_permission_service.py](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py) | FR-002 fallback（硬编码保留标 deprecated）；**v1.1 删硬编码** |
| [meta/schemas/*.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/) | FR-002 加 parent 字段；**v1.1 已有字段被利用** |
| [meta/core/error_codes.py](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py) | IF-005 新增错误码 |
| [meta/core/error_fix_hints.py](file:///d:/filework/excel-to-diagram/meta/core/error_fix_hints.py) | IF-005 新增 fix_hint |
| [src/composables/useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js) | FR-005 2 态简化 |
| [src/composables/useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js) | FR-005 配合 |
| [src/components/common/GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/components/common/GenericObjectList.vue) | IF-004 无权限态 UI |
| [scripts/init_role_permissions.py](file:///d:/filework/excel-to-diagram/scripts/init_role_permissions.py)（新建） | FR-006 init 脚本 |
| [scripts/explain_permissions.py](file:///d:/filework/excel-to-diagram/scripts/explain_permissions.py)（新建） | NFR-005 审计 CLI |
| **【v1.1 NEW】** [meta/core/bo_metadata_registry.py](file:///d:/filework/excel-to-diagram/meta/core/bo_metadata_registry.py)（新建） | FR-007 启动单例 |
| **【v1.1 NEW】** [scripts/check_bo_metadata.py](file:///d:/filework/excel-to-diagram/scripts/check_bo_metadata.py)（新建） | IF-007 dry-run 验证 |
| **【v1.1 NEW】** [meta/api/diagnostics_api.py](file:///d:/filework/excel-to-diagram/meta/api/diagnostics_api.py) | FR-009 `_diagnostics` 暴露 bo_metadata |

---

**Spec + RFC 完整性自检**：
- ✅ 10 章节齐全
- ✅ 最后一节是 "TBD List"，内容完整
- ✅ 所有 Q1-Q6 答案已纳入 FR/RFC
- ✅ 风险 + 回滚 + 测试 + 实施顺序明确
- ✅ 业界参考已附录
- ✅ 现有代码路径已附录
- ✅ **v1.1 增量内容明确标注 `[v1.1 NEW]`**
- ✅ **v1.0 全部 6 个 FR + 5 个 NFR + 5 个 IF + 4 个 TR 完整保留**
- ✅ **新增 3 个 FR（FR-007/008/009）+ 1 个 NFR（NFR-006）+ 2 个 IF（IF-006/007）+ 1 个 TR（TR-005）+ 4 个 TBD（TBD-6~9）**
