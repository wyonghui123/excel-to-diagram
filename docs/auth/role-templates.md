# 角色模板配置操作指南 (v2.1)

> **文档版本**: v2.1
> **创建日期**: 2026-06-15
> **关联 Spec**: `auth-permission-system/write-scope-interceptor-spec.md` v2.1
> **目标读者**: 业务 admin / 权限管理员

---

## 0. 前置准备

### 0.1 确认 UI 入口

登录 admin 账号 → 系统管理 → 用户与权限 → 角色管理 → 选中目标角色 → 权限配置 tab。

**面板顺序** (跟代码一致, `PermissionConfigPanel.vue:4-75`):
1. **管理维度范围** (DimensionScopePanel) — 第一
2. **菜单与功能权限** (MenuPermissionMatrix) — 第二
3. **条件型权限** (ConditionRuleList) — 第三

### 0.2 查询 dim value ID

| 业务名 | 查询 SQL | 说明 |
|--------|---------|------|
| 采购管理领域 | `SELECT id FROM domains WHERE name = '采购管理'` | 假设 ID = 10 (实际查 DB 确认) |
| 销售管理领域 | `SELECT id FROM domains WHERE name = '销售管理'` | 边界对照 |
| 任意 domain | `SELECT id, name FROM domains WHERE name LIKE '%关键词%'` | 用名字搜索 |

---

## 1. R1 (PrivateAuthor) — 私有产品作者

### 业务定位
> 创建并维护自己 owned 的产品及其下所有架构数据

### 1.1 创建角色

```
系统管理 → 角色管理 → 新建角色
  名称: 私有产品作者
  Code:  private_author
  描述:  可创建并维护自己 owned 的产品及其下所有架构数据
```

### 1.2 配置管理维度范围 (DimensionScopePanel)

**保持 4 个维度全部为空** (不选任何 dim value):

| 维度 | dim value | inherit_children | 备注 |
|------|-----------|------------------|------|
| product | **(空)** | - | owner 校验由拦截器 step 2 处理 |
| version | **(空)** | - | 沿 chain 继承 product |
| domain | **(空)** | - | 沿 chain 继承 product |
| sub_domain | **(空)** | - | 沿 chain 继承 product |

**关键**: 不要添加任何 dim value！R1 的权限范围是"自己 owned 的产品树", 由拦截器 owner chain 校验自动覆盖。

点击 **保存维度范围**。

### 1.3 配置菜单与功能权限 (MenuPermissionMatrix)

勾选以下 menu (按此顺序):

| Menu | 派生 functional perm | 用途 |
|------|---------------------|------|
| ✅ 产品线 | `product:read/create/update/delete` | 创建/管理自己 owned 的产品 |
| ✅ 版本 | `version:read/create` | 创建版本 |
| ✅ 领域 | `domain:read/create/update` | 创建/管理领域 |
| ✅ 子领域 | `subdomain:read/create/update` | 创建/管理子领域 |
| ✅ 业务对象 | `businessobject:read/create/update` | 创建/管理业务对象 |
| ✅ 关系 | `relationship:read/create/update` | 创建/管理关系 |
| ❌ 用户/角色/用户组 | - | admin only |
| ❌ 系统管理父菜单 | - | admin only |

点击 **保存全部权限**。

### 1.4 验证 (测试)

```sql
-- 验证 TEST333 属于 R1 后能:
-- 1) 创建 product P1 (owner 自动注入为 TEST333)
POST /api/v2/action/product/create
Body: { "name": "P1", "visibility": "private" }
→ 200 OK, P1.owner_id = 333

-- 2) 修改自己 owned 的 P1
PUT /api/v2/action/product/update
Body: { "id": 1, "name": "P1-updated" }
→ 200 OK (owner chain step 2 命中)

-- 3) 修改他人 owned 的 P2 (user=222 owned)
PUT /api/v2/action/product/update
Body: { "id": 2, "name": "P2-hacked" }
→ 403 ERR_WRITE_SCOPE_DENIED (owner 不匹配, dim scope 空 → 拒绝)

-- 4) 在自己 owned P1 下创建 domain D1
POST /api/v2/action/domain/create
Body: { "name": "D1", "product_id": 1 }
→ 200 OK (owner chain 沿 product 1 命中)
```

### 1.5 给用户分配 R1

```
系统管理 → 用户管理 → 选中 TEST333 → 角色 tab → 勾选 "私有产品作者" → 保存
```

或用 SQL (admin 操作):
```sql
INSERT INTO user_groups (user_id, group_id)
SELECT 333, id FROM groups WHERE role_id = (SELECT id FROM roles WHERE code = 'private_author');
```

---

## 2. R2 (PrivateArchitect) — 私有产品架构师

### 业务定位
> R1 的超集 + 转让 (transfer) 权限, 可把产品 owner 转给别人

### 2.1 创建角色

```
名称: 私有产品架构师
Code:  private_architect
描述:  私有产品作者 + 产品转让权限
```

### 2.2 配置管理维度范围

**与 R1 完全相同** (全空, owner chain 校验)。

### 2.3 配置菜单与功能权限

在 R1 基础上额外勾选:

| Menu (新增) | 派生 functional perm |
|------------|---------------------|
| ✅ 产品线 (含 transfer) | + `product:transfer` |

或单独勾选 menu 中 "产品线 transfer" 独立 action。

### 2.4 验证

R2 能改自己 owned product 的 owner_id 字段 (转让):
```sql
PUT /api/v2/action/product/update
Body: { "id": 1, "owner_id": 444 }
→ 200 OK (product:transfer 权限 + R1 范围)
```

---

## 3. R3 (ProcurementArchitect) — 采购管理架构师

### 业务定位
> 编辑"采购管理"领域及下属所有内容, 不允许编辑其他领域

### 3.1 创建角色

```
名称: 采购管理架构师
Code:  procurement_architect
描述:  可编辑采购管理领域及下属所有架构数据, 产品/版本只读
```

### 3.2 配置管理维度范围 (DimensionScopePanel)

| 维度 | dim value | inherit_children | 备注 |
|------|-----------|------------------|------|
| product | **(空)** | - | R3 对 product 是只读 |
| version | **(空)** | - | R3 对 version 是只读 |
| **domain** | **[10]** (采购管理) | **✅ 勾选** | 关键: 限定 dim scope |
| sub_domain | **(空, 自动继承)** | - | 因 domain 勾 inherit_children, 自动展开 |

**关键步骤**:
1. 找到 `domain` 行
2. 点击"添加领域"按钮 → 弹出 SearchHelpDialog
3. 搜索"采购管理" → 选中 (dim_value_id=10, 假设) → 加为 tag
4. 勾选 **"包含下级"** (子领域自动包含)
5. sub_domain 维度**不要手动添加** (因 inherit_children 启动后自动展开)
6. product / version 维度**不要添加** (R3 对它们只读)
7. 点击 **保存维度范围**

### 3.3 配置菜单与功能权限 (MenuPermissionMatrix)

勾选以下 menu:

| Menu | 派生 functional perm | 说明 |
|------|---------------------|------|
| ✅ 产品线 (read only) | `product:read` (不要勾 create/update/delete) | 只读 |
| ✅ 版本 (read only) | `version:read` (不要勾 create) | 只读 |
| ✅ 领域 | `domain:read`, `domain:update` (**不要勾 create/delete**) | 关键: 不分配 create |
| ✅ 子领域 | `subdomain:read/create/update/delete` | 全权 (因 inherit_children 已限定在采购管理) |
| ✅ 业务对象 | `businessobject:read/create/update/delete` | 同上 |
| ✅ 关系 | `relationship:read/create/update/delete` | 同上 |

**关键**: **不要勾 `domain:create`**! 否则 R3 用户能创建任意领域的 domain (含销售管理), step 2 owner chain 会放行自己创建的 record。PermissionInterceptor 在 functional perm 层先拒绝, 不会到 step 2。

### 3.4 验证

```sql
-- 1) 改采购管理 (domain 10)
PUT /api/v2/action/domain/update
Body: { "id": 10, "name": "采购管理-V2" }
→ 200 OK (dim scope 命中 step 3)

-- 2) 改销售管理 (domain 20)
PUT /api/v2/action/domain/update
Body: { "id": 20, "name": "销售管理-V2" }
→ 403 ERR_WRITE_SCOPE_DENIED
   check_results: {
     owner: false,
     dim_scope: [{role: "procurement_architect", cond: "id IN (10)", matched: false}],
     visibility: "private"
   }

-- 3) 在采购管理下创建子领域
POST /api/v2/action/subdomain/create
Body: { "name": "采购子领域1", "domain_id": 10 }
→ 200 OK (dim scope 继承 + functional perm 全权)

-- 4) 在销售管理下创建子领域
POST /api/v2/action/subdomain/create
Body: { "name": "销售子领域1", "domain_id": 20 }
→ 403 (dim scope 不包含)
```

### 3.5 给用户分配 R3

```
系统管理 → 用户管理 → 选中 TEST333 → 角色 tab → 勾选 "采购管理架构师" → 保存
```

---

## 4. TEST333 三角色联合验证

### 4.1 角色分配

TEST333 同时拥有 R1 + R2 + R3 (验证多 role Union):

| 需求 | 配置 | 行为 |
|------|------|------|
| 1) 创建 owned product | R1 (product:create) | ✅ PermissionInterceptor 通过 |
| 1) 修改 owned product | R1 (product:update) + R2 (product:transfer) | ✅ PermissionInterceptor 通过 + owner chain 通过 |
| 2) 维护 owned product 下领域 | R1 (domain:*) | ✅ owner chain 沿 product 1 命中 |
| 3) 编辑采购管理领域 | R3 (domain:update) + R3 dim scope domain=[10] | ✅ dim scope 命中 step 3 |
| 4) 不能编辑销售管理 | R1 + R3 都不允许 | ✅ 全部不通过, 拒绝 |

### 4.2 多 role Union 行为

```sql
-- TEST333 改 采购管理 (domain 10):
-- step 1: admin? 否
-- step 2: owner chain: 10.owner_id 是系统, ≠ 333 → 不命中
-- step 3: dim scope:
--   - R1: product dim scope 空 → 无 cond → 不命中
--   - R3: domain dim scope "id IN (10)" → 命中 ✅
-- step 4: visibility: private → 不通过
-- 任一通过即放行 → step 3 命中 → 放行
```

---

## 5. 常见问题

### Q1: 为什么 R1 dim scope 留空？

A: R1 的权限是"自己 owned 的产品树"。这是动态谓词 (任何 owner=self 的 record), 不是固定 dim value 列表。拦截器 step 2 owner chain 校验自动覆盖。

### Q2: TEST333 拥有 R1 + R3, 改 product 1 (自己 owned) 能成功吗？

A: 能。step 2 owner chain 命中 (product 1.owner_id == 333) → 放行。即使 R3 dim scope 没配 product 也无所谓。

### Q3: TEST333 拥有 R1 + R3, 想改他人 product 2 (user=222 owned) 能成功吗？

A: 不能。step 2 owner chain 不命中 (222 ≠ 333), step 3 dim scope R1 空 / R3 没配 product → 全部不命中 → 拒绝。

### Q4: R3 用户想创建 domain 20 (销售管理) 能成功吗？

A: 不能。FR-009 R3 没分配 `domain:create` 权限, PermissionInterceptor 步骤已拒绝, 不会到 WriteScopeInterceptor。

### Q5: 多 role 时是 AND 还是 OR？

A: OR (Union), 任一 role 满足即放行。FR-002 step 3 明确描述。

### Q6: 升级到硬拒模式后所有用户都被拒, 如何回滚？

A: 设环境变量 `WRITE_SCOPE_AUDIT_ONLY=true` 即可软警告模式, 立即生效无需重启。

---

## 6. 升级检查清单

- [ ] R1 角色已创建, dim scope 留空, menu 勾选完毕
- [ ] R2 角色已创建, dim scope 留空, menu 勾选 + product:transfer
- [ ] R3 角色已创建, dim scope domain=[10] + inherit_children, menu 勾选完毕 (domain 缺 create)
- [ ] TEST333 已分配 R1 + R2 + R3
- [ ] 4 业务需求 e2e 测试通过
- [ ] /_diagnostics 端点可访问, 看到 write_scope_warnings 计数
- [ ] 灰度开关 `WRITE_SCOPE_AUDIT_ONLY` 已记录在运维手册

---

## 7. 参考

- `auth-permission-system/write-scope-interceptor-spec.md` — 技术 spec
- `auth-permission-system/write-scope-interceptor.md` — 拦截器技术细节
- `auth-permission-system/role-migration-guide.md` — 现有角色迁移指南
- SAP Authorization Object S_TCODE / Oracle Function Security — 头部产品对照
