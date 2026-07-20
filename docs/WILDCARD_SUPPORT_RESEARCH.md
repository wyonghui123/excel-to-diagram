# Dimension Scope 和 Condition 的 `*` 通配符支持研究

> 创建日期: 2026-07-19
> 状态: 研究完成，待实施
> 关联文档: INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md 6.3.10
> 作者: AI Assistant

---

## 一、核心问题

当前功能权限支持 `*` 通配符（超级管理员），但 dimension scope 和 condition 条件未支持 `*` 或 "all" 表示全量维度，不符合 **Secure by Default + Deny 优先** 原则。

---

## 二、行业产品 `*` 通配符处理对比

| 产品 | `*` 语义 | 默认行为 | Secure by Default |
|------|---------|---------|-------------------|
| **AWS IAM** | `Resource: "*"` / `Action: "*"` = 全量访问 | Implicit Deny（未显式允许=拒绝） | ✅ |
| **SAP CAP** | `@restrict` 无 where 子句 = 全量访问 | 默认无访问 | ✅ |
| **Salesforce** | OWD "Public Read/Write" = 全量 | OWD 默认 "Private" | ✅ |
| **SpiceDB** | `relation view: user:*` = 所有人可访问 | 无关系=无权限 | ✅ |
| **Cedar** | `resource in Group::*` = 组内所有资源 | 默认拒绝 | ✅ |
| **XACML** | `<AnyResource/>` / `<AnyAction/>` = 全量 | Deny-overrides = 默认拒绝 | ✅ |

### 关键发现

1. **所有产品都遵循 Secure by Default** — 默认拒绝，需显式配置 `*` 才全量
2. **`*` 是白名单形式** — 不是默认行为，是 admin 显式授权
3. **功能权限 `*` ≠ 数据权限 `*`** — 需分别配置，互不影响
4. **审计要求** — 配置 `*` 时需记录审计日志

---

## 三、当前实现分析

### 3.1 功能权限（已支持 `*`）

```python
# permission_interceptor.py L85-88
def user_info_has_perm(permissions, required: str) -> bool:
    """支持 * 通配符"""
    if '*' in permissions:
        return True  # ✅ 功能权限支持 *
    return required in permissions
```

### 3.2 Dimension Scope（不支持 `*`）

```python
# dimension_scope_engine.py L148-159
def expand_dimension_values(self, role_id: int):
    raw_dv = scope.get('dimension_values')
    if isinstance(raw_dv, str):
        values = set(json.loads(raw_dv))  # ❌ 只支持 JSON list, 不支持 '*'
```

### 3.3 Condition（不支持 `*`）

```python
# condition_evaluator.py
def evaluate(self, condition: str, resource: Dict[str, Any]) -> bool:
    if not condition or not condition.strip():
        return True  # 空条件 = 全量，但无显式 '*' 支持
    # ❌ 未处理 condition = '*' 的情况
```

### 3.4 写路径（功能权限 `*` 跳过，dimension scope `*` 未处理）

```python
# write_scope_interceptor.py L337-343
if '*' in permissions:
    return  # ✅ 功能权限 * 跳过写路径检查
# ❌ 但未检查 dimension scope 是否为 *
```

### 3.5 Gap 分析汇总

| 层级 | 当前支持 `*` | 需要支持 |
|------|------------|---------|
| 功能权限 (PermissionInterceptor) | ✅ 已支持 | - |
| Dimension Scope (DimensionScopeEngine) | ❌ 不支持 | `scope_mode='all'` 或 `dimension_values='*'` |
| Condition (ConditionEvaluator) | ❌ 不支持 | `condition='*'` 表示全量匹配 |
| 写路径 (WriteScopeInterceptor) | ✅ 功能权限 `*` 跳过 | dimension scope `*` 也需跳过 |

---

## 四、统一方案设计

### 4.1 方案 A：扩展 role_dimension_scopes 表（推荐）

```sql
-- 新增 scope_mode 字段
ALTER TABLE role_dimension_scopes ADD COLUMN scope_mode TEXT DEFAULT 'include';
-- scope_mode: 'include' | 'exclude' | 'all'

-- 示例：admin 角色配 product 维度全量
INSERT INTO role_dimension_scopes (role_id, dimension_code, dimension_values, scope_mode, inherit_children)
VALUES (5, 'product', '*', 'all', 1);
```

```python
def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
    scopes = self._load_scopes(role_id)
    expanded = {}
    for scope in scopes:
        code = scope['dimension_code']

        # 新增：scope_mode='all' 或 dimension_values='*'
        if scope.get('scope_mode') == 'all' or scope.get('dimension_values') == '*':
            all_ids = self._get_all_dimension_ids(code)
            expanded[code] = set(all_ids)
            continue

        # 原有逻辑不变
        raw_dv = scope.get('dimension_values')
        ...
    return expanded
```

### 4.2 方案 B：统一到 data_permission_rules 的 condition 表达式

```json
{
    "rule_type": "dimension",
    "condition": "*",
    "effect": "permit"
}
```

`condition='*'` 表示无条件匹配（全量维度），等价于 SQL `1=1`。

### 4.3 推荐方案：A + B 结合

- `role_dimension_scopes` 支持 `scope_mode='all'`（UI 友好）
- `data_permission_rules` 支持 `condition='*'`（表达式统一）
- 两者在 PermissionResolver 中合并处理

---

## 五、Condition 条件的 `*` 支持

```python
# condition_evaluator.py
def evaluate(self, condition: str, resource: Dict[str, Any]) -> bool:
    if not condition or condition.strip() == '*':
        return True  # * = 无条件匹配
    ...
```

---

## 六、Secure by Default 保证

```
默认行为（未配置任何 scope）:
  功能权限: 无 → 403
  Dimension Scope: 无 → 仅 owner 可访问
  Condition: 无 → 拒绝

显式配置 *:
  功能权限: * → 所有功能放行
  Dimension Scope: * → 所有维度值放行
  Condition: * → 所有数据放行

关键: * 是 admin 显式配置的结果, 不是默认行为
```

---

## 七、AWS IAM `*` 通配符深度分析

### 7.1 `*` 在 AWS IAM 中的 3 种用法

| 位置 | `*` 含义 | 示例 |
|------|---------|------|
| **Action** | 所有操作 | `"Action": "*"` |
| **Resource** | 所有资源 | `"Resource": "*"` |
| **Condition Key** | 任意值 | `"StringLike": {"aws:userid": "*"}` |

### 7.2 AWS 的 `*` 安全约束

1. **Explicit Deny > Explicit Allow > Implicit Deny**
   - `*` 是 Explicit Allow，可被 Explicit Deny 覆盖
   - 我们的设计：`*` 可被 Prohibition（M10）覆盖

2. **Service Control Policies (SCPs)**
   - 组织级 `*` 限制，即使 IAM 策略配 `*` 也受 SCP 约束
   - 我们的设计：org_level 限制 > role `*`

3. **Permission Boundary**
   - 即使有 `*`，也不能突破 permission boundary
   - 我们的设计：visibility scope 独立于 dimension scope `*`

### 7.3 对我们的启示

```
我们的 * 设计应遵循 AWS 的 3 层约束:

Layer 1: Functional * → 所有功能放行，但受 visibility scope 约束
Layer 2: Dimension * → 所有维度值放行，但受 org level 约束
Layer 3: Condition * → 所有数据放行，但受 field mask 约束

即: * 不是绝对的，仍受其他正交维度约束
```

---

## 八、实施清单

### Phase 1: 基础支持（P1，1-2 周）

1. 扩展 `role_dimension_scopes` 表，新增 `scope_mode` 字段
2. `DimensionScopeEngine.expand_dimension_values` 支持 `*` 通配符
3. `ConditionEvaluator.evaluate` 支持 `*` 表示全量
4. 写路径拦截器同步支持

### Phase 2: UI 与审计（P2，1 周）

5. 权限配置 UI 增加"全部"选项
6. 添加审计日志记录 `*` 配置
7. 配置 `*` 时需二次确认

### Phase 3: 约束与边界（P2，1 周）

8. `*` 受 visibility scope 约束（不突破可见性边界）
9. `*` 受 org level 约束（不突破组织边界）
10. `*` 受 field mask 约束（不突破字段级安全）

### Phase 4: 统一入口（P1.1 完成后）

11. 统一到 `data_permission_rules` 的 `condition='*'`
12. PermissionResolver 统一处理 `*`
13. 更新 PERMISSION_TODOS.md

---

## 九、与 PERMISSION_TODOS.md 的关联

本研究发现应补充到 PERMISSION_TODOS.md 的 P1 优先级：

```markdown
### P1.6 Dimension Scope 和 Condition 支持 `*` 通配符
- **现状**: 功能权限支持 `*`（超级管理员），但 dimension scope 和 condition 不支持
- **风险**: 无法表达"全量维度"的合法场景，admin 需逐个配置所有维度值
- **方向**: 扩展 role_dimension_scopes 支持 scope_mode='all'，condition 支持 '*'
- **关联**: INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md 6.3.10, WILDCARD_SUPPORT_RESEARCH.md
- **状态**: 研究完成，待实施
- **优先级**: P1 (中)
```

---

## 十、参考

- [INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md](INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md) — 行业权限架构深度研究
- [CLOUD_IAM_ARCHITECTURE_RESEARCH.md](CLOUD_IAM_ARCHITECTURE_RESEARCH.md) — 云厂商 IAM 架构研究
- [PERMISSION_ACADEMIC_MODELS_RESEARCH.md](PERMISSION_ACADEMIC_MODELS_RESEARCH.md) — 学术理论模型研究
- [PERMISSION_TODOS.md](PERMISSION_TODOS.md) — 权限体系待办
