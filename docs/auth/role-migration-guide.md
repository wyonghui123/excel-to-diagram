# 角色迁移指南 — 现有角色 dim scope 补全 (v2.1)

> **文档版本**: v2.1
> **创建日期**: 2026-06-15
> **关联 Spec**: `auth-permission-system/write-scope-interceptor-spec.md` v2.1
> **目标读者**: 系统 admin / 权限管理员
> **背景**: WriteScopeInterceptor 上线后, 写操作 (update/delete) 必须感知 dim scope. 现有"无 dim scope"角色需补全.

---

## 0. 背景与决策 (业务 TBD-D)

### 0.1 当前 P0 漏洞

```
现状: 用户只要有 functional perm 就能改任何 record
例: TEST333 加 product:update 后能改 user=222 owned 的 product 2
```

### 0.2 头部产品做法 (3 阶段灰度)

| 阶段 | 持续 | 行为 | admin 行动 |
|------|------|------|-----------|
| 阶段 1 (audit-only) | 1 周 | WARN 不拒, log + /_diagnostics 报告 | 跑诊断, 看哪些用户缺 dim scope |
| 阶段 2 (soft-default) | 1 周 | 缺 dim scope 角色**临时**默认 scope = `all` (宽) | admin 重新配置这些角色 |
| 阶段 3 (hard-reject) | 永久 | 缺 dim scope = 403 | 无 (admin 已配好) |

### 0.3 我推荐: 3 阶段 (跟 SAP SU25 一致)

**理由**:
- 阶段 1 给 admin 时间看影响面 (无需立刻行动)
- 阶段 2 让"没空配 dim scope"的角色暂不阻塞 (admin 仍要补, 但不影响业务)
- 阶段 3 最终强制 (跟头部产品行为一致)

---

## 1. 阶段 1: audit-only (1 周)

### 1.1 启动

```bash
# .env 增加
WRITE_SCOPE_AUDIT_ONLY=true
```

无需重启, env var 在请求内读取 (WriteScopeInterceptor:line ~75)。

### 1.2 admin 行为

- 业务照常运行, 写操作不再"静默越权"
- 越权行为 → log WARNING + `/_diagnostics` 计数
- 响应 header: `X-Write-Scope-Warning: <reason>`

### 1.3 admin 诊断 (跑一周内)

```bash
# 查看 _diagnostics
curl http://localhost:3010/api/v2/action/_diagnostics | jq '.data.write_scope_warnings'
```

输出示例:
```json
[
  {
    "object_type": "product",
    "target_id": 2,
    "user_id": 333,
    "decision": "soft_warn",
    "check_results": {
      "owner": false,
      "dim_scope": [{"role_id": 5, "cond": null, "matched": false}],
      "visibility": "private"
    }
  }
]
```

### 1.4 识别需要补 dim scope 的角色

```sql
-- 列出所有 active 角色
SELECT id, code, name FROM roles WHERE is_active = 1;

-- 列出哪些角色没配 dim scope
SELECT r.id, r.code, r.name
FROM roles r
LEFT JOIN role_dimension_scopes rds ON rds.role_id = r.id
WHERE r.is_active = 1
  AND rds.id IS NULL
  AND r.code NOT IN ('admin', '*');  -- admin 走 step 1 跳过
```

### 1.5 阶段 1 退出条件

- [ ] admin 跑完诊断, 识别出 N 个需补 dim scope 的角色
- [ ] admin 已设计每个角色的 dim scope 配置 (按章节 3 模板)
- [ ] 准备阶段 2 soft-default 切换

---

## 2. 阶段 2: soft-default (1 周)

### 2.1 启动 (保持 audit, 启用 soft-default 临时 scope)

```bash
# 仍保持 audit-only, 软警告模式
WRITE_SCOPE_AUDIT_ONLY=true
```

或完全切到硬拒 (推荐 admin 配好所有角色后再切):

```bash
# 切到硬拒 (无 dim scope 角色会被拒)
WRITE_SCOPE_AUDIT_ONLY=false
```

### 2.2 策略选择

| 策略 | 适合场景 | 风险 |
|------|---------|------|
| **A. 软警告 + 立即硬拒** | admin 已配好所有角色 | 风险最低, 推荐 |
| **B. soft-default (临时 all scope)** | admin 未配完, 想给缓冲期 | 阶段 2 仍允许越权, 需补全角色 |

**推荐 A**: 阶段 1 一周 + 阶段 2 立即硬拒。

### 2.3 实施 B (soft-default, 可选)

如果走 B, 需要在拦截器实现临时 scope: 给无 dim scope 的角色临时派生 `id IS NOT NULL` (全表)。这跟当前 spec 不一致, 需要额外开发。

**当前 spec 未实现 soft-default 模式**, 走 A (立即硬拒) 即可。

---

## 3. 阶段 3: hard-reject (永久)

### 3.1 启动

```bash
WRITE_SCOPE_AUDIT_ONLY=false  # 缺省
```

### 3.2 失败场景处理

如果发现某角色还没配, 用户被 403, admin 临时回滚:

```bash
WRITE_SCOPE_AUDIT_ONLY=true  # 软警告
```

补完角色后切回 false。

---

## 4. 现有角色补 dim scope 模板

### 4.1 admin 角色 (无需配)

```
走 step 1 (is_admin) 跳过, 不需要 dim scope
```

### 4.2 默认 user 角色

**业务定位**: 普通用户, 只能看自己 owned 的内容

**配置** (UI 步骤跟 `role-templates.md` R1 类似):

1. 创建或选中"默认用户"角色
2. DimensionScopePanel: **保持 4 维度全空** (留空)
3. MenuPermissionMatrix: 勾选基础 read menu (按业务需求)

**逻辑**: dim scope 空 → 拦截器 step 2 owner chain 校验只允许改自己 owned

### 4.3 业务角色 (按部门/团队分配)

**业务定位**: 某部门/团队能管理特定产品/领域

**配置**:

1. 创建角色 (e.g. "销售管理架构师", "财务部产品编辑")
2. DimensionScopePanel:
   - product 维度: 选该产品 ID
   - inherit_children: 勾 (自动展开 version/domain/sub_domain)
3. MenuPermissionMatrix: 勾选 CRUD menu

**示例** (财务部):
```
product 维度: [1, 5, 10] (财务部管理的产品 1, 5, 10)
inherit_children: ✅
sub_domain 维度: 不手动配 (自动展开)
```

### 4.4 只读角色 (auditor)

**业务定位**: 只能读, 不能写

**配置**:

1. 创建角色 (e.g. "审计员")
2. MenuPermissionMatrix: **只勾 read action**, 不勾 create/update/delete
3. DimensionScopePanel: 配 product 维度 (按需)

**效果**: PermissionInterceptor 直接拒绝任何写操作 (无 functional perm)。

### 4.5 系统级 admin 操作角色 (e.g. 管理员助手)

**业务定位**: admin 的助手, 全权

**配置**:

1. 创建角色 (e.g. "super_admin")
2. 直接给 `'*'` 通配符 (代码层给 user.permissions 加 `*`)
3. DimensionScopePanel: 不用配 (通配符跳过)

**注意**: `'*'` 跟 `is_admin` 略有不同, `'*'` 在 PermissionInterceptor 步骤已通配所有 functional perm, WriteScopeInterceptor 也走 step 1 跳过。

---

## 5. 迁移 SQL 模板 (admin 备份后批量执行)

### 5.1 备份

```sql
-- 备份原表
CREATE TABLE role_dimension_scopes_backup_20260615 AS
SELECT * FROM role_dimension_scopes;

CREATE TABLE role_permissions_backup_20260615 AS
SELECT * FROM role_permissions;
```

### 5.2 通用模式: 给某角色配某产品的 dim scope

```sql
-- 给 role "财务部" 配 product 维度的 [1, 5, 10]
INSERT INTO role_dimension_scopes (role_id, dimension_code, dimension_values, inherit_children, scope_mode)
VALUES (
  (SELECT id FROM roles WHERE code = 'finance_team'),
  'product',
  '[1, 5, 10]',  -- JSON list
  1,             -- inherit_children = true
  'include'
);
```

### 5.3 批量脚本 (示例)

```sql
-- 给所有"读角色"补 product 维度的 dim scope (假设 dim_value_ids 从某表查)
INSERT INTO role_dimension_scopes (role_id, dimension_code, dimension_values, inherit_children, scope_mode)
SELECT
  r.id,
  'product',
  '[' || GROUP_CONCAT(p.id) || ']',
  1,
  'include'
FROM roles r
JOIN role_products_temp p ON p.role_code = r.code
WHERE r.is_active = 1
GROUP BY r.id;
```

---

## 6. 验证清单

### 阶段 1 退出验证

- [ ] `/_diagnostics.write_scope_warnings` 有数据
- [ ] admin 已识别所有需补 dim scope 的角色
- [ ] admin 已为每个角色设计 dim scope 配置

### 阶段 2 退出验证

- [ ] 所有需补的角色已配完 dim scope
- [ ] e2e 测试通过 (TEST333 4 场景 + 现有用户场景)
- [ ] 无 `_diagnostics.write_scope_warnings` 增长 (无新增越权)

### 阶段 3 验证

- [ ] 切换到 hard-reject 后, 无误拒
- [ ] 7 天稳定运行无新警告
- [ ] 用户无相关工单

---

## 7. 回滚方案

### 7.1 软回滚 (推荐)

```bash
WRITE_SCOPE_AUDIT_ONLY=true
```

立即生效, 无需重启。

### 7.2 硬回滚 (代码)

```bash
# 1. 移除拦截器
git revert <commit_hash>

# 2. 还原拦截器注册
# 编辑 meta/core/interceptors/__init__.py 移除 WriteScopeInterceptor

# 3. 重启服务
powershell -File scripts/service_manager.ps1 restart
```

### 7.3 DB 回滚

```sql
-- 恢复 role_dimension_scopes
DELETE FROM role_dimension_scopes;
INSERT INTO role_dimension_scopes SELECT * FROM role_dimension_scopes_backup_20260615;
```

---

## 8. 头部产品对照

| 阶段 | SAP SU25 | Salesforce Release | Oracle Fusion |
|------|----------|------------------|---------------|
| 阶段 1 (audit) | SU25 预分析 | Health Check 报告 | Security Diagnostics |
| 阶段 2 (soft) | PFCG 临时赋 SAP_ALL | OWD 临时 Public RW | 预定义 data policy 临时 all |
| 阶段 3 (hard) | Transport 强制迁移 | release 升级生效 | Production enforce |

---

## 9. 升级检查清单

- [ ] 备份 role_dimension_scopes 和 role_permissions
- [ ] 阶段 1 启动 WRITE_SCOPE_AUDIT_ONLY=true
- [ ] 观察 /_diagnostics.write_scope_warnings 1 周
- [ ] admin 识别所有需补的角色
- [ ] admin 按章节 4 模板补全
- [ ] e2e 测试 (TEST333 4 场景) 通过
- [ ] 阶段 2 启动 WRITE_SCOPE_AUDIT_ONLY=false (硬拒)
- [ ] 观察 1 周无新警告
- [ ] 阶段 3 稳定运行, 文档完成

---

## 10. 参考

- `auth-permission-system/write-scope-interceptor-spec.md` — 技术 spec
- `auth-permission-system/role-templates.md` — R1/R2/R3 详细配置
- `auth-permission-system/write-scope-interceptor.md` — 拦截器技术细节
- `BACKLOG-Permission-System-Improvement.md` PERM-002/003/004 — 相关 BACKLOG
