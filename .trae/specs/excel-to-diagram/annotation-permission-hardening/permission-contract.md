# Annotation 权限契约（设计文档）

> **版本**: v1.0 | **日期**: 2026-06-23 | **状态**: 活跃
> **关联 Spec**: [spec.md](file:///d:/filework/.trae/specs/excel-to-diagram/annotation-permission-hardening/spec.md)

---

## 一、设计原则

### 1.1 核心决策

> **annotation 没有独立的功能权限，数据权限完全 derived from parent（target_type + target_id）。**

### 1.2 与 BO/RELATION 设计对比

| 维度 | BO/RELATION | annotation |
|---|---|---|
| **功能权限** | 有（`{obj}:{create/update/delete}`） | 无 |
| **数据权限 (dim_scope)** | 自身对象参与判定 | **派生自 parent** |
| **visibility 检查** | 自身对象判定（沿 chain 上溯 product） | **继承 parent visibility** |
| **拦截器链** | L1 login → L2 PermissionInterceptor(P30) → L3 WriteScopeInterceptor(P35) | L1 login → L3 WriteScopeInterceptor(P35) 派生 |

### 1.3 设计理由

1. **annotation 是辅助对象**（备注、评论、标签），与业务对象（BO/RELATION）生命周期不同
2. **权限跟随 parent 保持语义一致**：用户对 parent 有权 → 对 annotation 有权（直观）
3. **避免维护双重权限体系**：annotation 的权限完全由 parent 决定，简化权限模型
4. **安全兜底依赖 WriteScopeInterceptor (P35)**：5 步校验严格化（v1.1.6 H13）

---

## 二、annotation 权限判定流程

### 2.1 写权限（create / update / delete）

```
用户操作 annotation
   │
   ├─ step 1: admin check (PermissionInterceptor P30)
   │     └─ admin 通配 → 放行
   │
   ├─ step 2: owner chain check (OwnerChainInterceptor P25)
   │     └─ owner chain 命中 → 放行
   │
   ├─ step 3: dim_scope 检查 (WriteScopeInterceptor._check_dim_scope_for_annotation)
   │     ├─ parent object_type 在 user 直接 dim scope 内 → 命中
   │     ├─ parent 的 ancestor 在 user dim scope 内 → 命中
   │     └─ 都不命中 → 拒绝
   │
   ├─ step 4: visibility 检查 (WriteScopeInterceptor._check_visibility)
   │     ├─ annotation.parent 存在 → 继承 parent visibility
   │     ├─ parent.visibility = public → 允许
   │     ├─ parent.visibility = private → 拒绝
   │     └─ annotation.parent 不存在 (orphan) → 硬拒
   │
   └─ step 5: 严格化判定 (WriteScopeInterceptor line 460)
         └─ dim_scope 命中 AND visibility=public → 放行
         └─ 否则 → 拒绝
```

### 2.2 读权限（list / read）

annotation 的读权限由 `DataPermissionInterceptor` 处理：

- 列表查询：`WHERE target_type = ? AND target_id IN (...)`，其中 `(...)` 是 parent 维度的 dim scope 派生
- 单个读取：parent 的 visibility=public 才返回

---

## 三、与代码实现的对应

| 流程步骤 | 代码位置 |
|---|---|
| step 1 admin check | [permission_interceptor.py:127](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L127) `is_admin(user_info)` |
| step 2 owner chain | [owner_chain_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/owner_chain_interceptor.py) |
| step 3 dim_scope annotation | [write_scope_interceptor.py:861-915](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L861-L915) `_check_dim_scope_for_annotation_create` |
| step 4 visibility 继承 | [write_scope_interceptor.py:1616-1631](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L1616-L1631) `_check_visibility` |
| step 5 严格化判定 | [write_scope_interceptor.py:460](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L460) `if dim_check['matched'] and visibility_check['allow']: return` |

---

## 四、为什么 annotation 端点不挂 `@require_permission`

### 4.1 设计考虑

如果给 annotation 端点加 `@require_permission('annotation:create')`：

```python
# 假设实现
@annotation_bp.route('/annotations', methods=['POST'])
@login_required
@require_permission('annotation:create')
def create_annotation(): ...
```

**问题**：

1. 角色需要额外配 `annotation:create` 权限 → 增加配置负担
2. 权限被硬编码到装饰器 → 失去"derived from parent"的灵活性
3. 即便用户有 `annotation:create` 权限，parent 不在 dim scope 仍会被 P35 拒绝 → 装饰器无意义

### 4.2 现状约定（推荐保持）

```python
# annotation_routes_api.py:189
@annotation_bp.route('/annotations', methods=['POST'])
@login_required    # ← 只有 L1, 没有 L2
def create_annotation(): ...
```

**理由**：P35 已经基于 parent 完成 L2 + L3 校验，annotation 端点不需要重复 L2。

**安全保证**：

- 即便恶意用户绕过前端 → P35 仍会拦截（dim_scope + visibility 双重校验）
- orphan annotation 硬拒（FR-002）
- 严格化要求 `dim_scope AND visibility=public` 同时满足

---

## 五、orphan annotation 处理（FR-002）

### 5.1 现状（修复前）

```python
# write_scope_interceptor.py:1630-1631
# orphan annotation: 无法确定 visibility, 默认放行
return {'allow': True, 'visibility': 'public'}
```

**风险**：orphan annotation（parent 被删除或 target_id 不存在）默认放行写权限

### 5.2 修复后

```python
# write_scope_interceptor.py:1630-1631
# orphan annotation: 无法确定 visibility, 硬拒 (FR-002)
return {'allow': False, 'visibility': 'unknown'}
```

**行为**：

- orphan annotation 写权限被拒绝
- 读权限不受影响（仍可查询历史 annotation）
- 与 P35 严格化要求一致：`visibility != public` → 拒绝

### 5.3 feature flag 灰度（FR-007）

通过环境变量 `PERMISSION_GUARD_MODE` 控制：

```bash
# 默认（硬拒）
export PERMISSION_GUARD_MODE=enforce

# 灰度模式（只 log 不抛异常）
export PERMISSION_GUARD_MODE=audit-only
```

---

## 六、后续工作（不在本次范围）

| ID | 工作 | 优先级 |
|---|---|---|
| FR-003 | `/diagnostics/permissions` 端点 | Should |
| FR-004 | `/permissions/preview` API 给前端用 | Should |
| FR-008 | description 字段审计日志 | Could |

前端 UI 改造（按钮过滤 / handler guard）由后续迭代处理，本次仅完成后端合规闭环。

---

## 七、变更日志

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-06-23 | AI Assistant | 创建文档（v1.0） |