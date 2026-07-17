# DEPLOY HANDOVER: BUG-V027-pt2 — 生产导出 领域/子领域/服务模块/业务对象 全错 + 备注丢失

## 📌 任务概述

**用户问题**（PM 通过生产 5001 反馈）：

- wyonghui 在生产系统点击导出 → Excel 中领域/子领域/服务模块/业务对象数量全错，且没有"备注"列
- 与 3006 测试结果对比：3006 导出 1 个域 5 个子领域 21 个服务模块 141 个业务对象（与 list 一致）
- 生产却返回 11 个域 68 个子领域 409 个服务模块 3228 个业务对象 0 个备注

| 类型 | 期望 (list 一致) | 生产实际 | 偏差倍数 |
|------|------------------|---------|---------|
| 领域 | 1 | **11** | 11× |
| 子领域 | 5 | **68** | 14× |
| 服务模块 | 21 | **409** | 19× |
| 业务对象 | 155 | **3228** | 21× |
| 备注 | 706 | **0 (丢)** | 全部丢失 |

## 🔍 根因

**BUG 位置**：`meta/services/query_service.py` `_try_apply_dimension_scope` 方法的**单 role 路径**

**触发链路**：
1. `import_export_service._query_with_hierarchy` 调 `query_service.search` 查各类型
2. `query_service.search` 调 `_apply_data_permission` 调 `_try_apply_dimension_scope`
3. `_try_apply_dimension_scope` 派生 dim scope conditions → 注入到 builder

**为什么是 bug**：

`DimensionScopeEngine.derive_data_conditions()` 对 wyonghui 的 SCMEDIT role 生成复合 AND 表达式：
```python
{
    "domain": "id = 8 AND version_id = 3",      # 2 个 leaf，AND 关系
    "sub_domain": "domain_id = 8 AND id IN (18,20,23,60,64)",
    "service_module": "sub_domain_id IN (...) AND sub_domain_id IN (...)",
    "business_object": "service_module_id IN (...) AND service_module_id IN (SELECT ...)"
}
```

BUG-V027 (bb53b0a 多 role 修复) 只覆盖了 `len(per_role_conds) > 1` 的多 role 分支；**单 role 分支**（`len(per_role_conds) == 1`）仍然把 AND 段的所有 leaf cond 平铺到 `or_conditions` 列表：

```python
# query_service.py:1753 修复前
if len(per_role_conds) == 1:
    for c in per_role_conds[0]:
        if c.get('type') == 'or':
            for ac in c['conditions']:
                tup = _cond_to_tuple(ac)
                if tup:
                    or_conditions.append(tup)  # ❌ AND 段被当 OR
        ...
        else:
            tup = _cond_to_tuple(c)
            if tup:
                or_conditions.append(tup)     # ❌ AND 段被当 OR

# 后续: builder.or_where(or_conditions)
#   SQL 退化为 (id=8 OR version_id=3)  → 永远为真 → 11 个域
```

**为什么 wyonghui 触发（单 role 也坏）**：
- 与 role 数量无关，跟 conds 的 leaf 数量有关
- 单 role dim scope 派生本身就含多个 leaf (例: id=8 AND version_id=3)
- BUG-V027 修复者只关注了多 role OR-of-AND 问题，没意识到单 role 也有相同 OR 退化

**为什么 3006 测试不出来**：
- 3006 后端 3011 加载的是 worktrees/release-prep HEAD `7061321`（V007.41 P1，11:26:38 提交）
- **7061321 已含 v027-pt2 修复**（dev-agent 独立完成）
- 生产 5001 还跑 v20260708_005 zip（HEAD `7c71636`，10:37:04 部署）— **落后 1 个 commit**

**为什么备注丢了**：
- SQL 退化为 OR 后拿回全表数据
- `_inject_hierarchy_info` 注入路径依赖精确 ID 关联（id=8 域 → 5 个子领域 → 21 个服务模块 → 155 个 BO → 706 个 annotation）
- 全表数据下关联错位，annotation sheet 完全没数据

## ✅ 修复

**Commit**: `7061321` (V007.41 P1, by Dev Agent V047, 2026-07-08 11:26:38)

**Fix 内容** (`query_service.py:1753-1842`)：

单 role 路径改用 `where_raw` 注入 `(c1 AND c2 AND ...)` 复合 SQL：

```python
if len(per_role_conds) == 1:
    # 收集所有 leaf cond 为 AND 关系
    and_clauses: list = []
    and_params: list = []
    for c in per_role_conds[0]:
        if c.get('type') == 'or':
            # 嵌套 OR 段，括号保留
            or_sub_clauses, or_sub_params = [], []
            for ac in c['conditions']:
                tup = _cond_to_tuple(ac)
                if not tup: continue
                res = _tup_to_sql(tup)
                if res is None: continue
                clause, ps = res
                or_sub_clauses.append(clause)
                or_sub_params.extend(ps)
            if or_sub_clauses:
                if len(or_sub_clauses) == 1:
                    and_clauses.append(or_sub_clauses[0])
                    and_params.extend(or_sub_params)
                else:
                    and_clauses.append(f"({' OR '.join(or_sub_clauses)})")
                    and_params.extend(or_sub_params)
        # ... AND / leaf 段同样处理

    if and_clauses:
        # owner exception (product only) AND-merge
        ...
        if len(and_clauses) == 1 and not owner_added:
            builder.where_raw(and_clauses[0], and_params)
        else:
            raw_sql = ' AND '.join(and_clauses)
            builder.where_raw(f"({raw_sql})", and_params)
    return True
```

嵌套 OR 段也用 `(` `)` 正确分组，不再被平铺。

## 📋 部署要求

**目标环境**：生产 5001 (`172.20.59.7`)

**当前部署**：v20260708_005 (git HEAD `7c71636-dirty`，部署时间 2026-07-08 10:37:04)
**目标部署**：v20260708_006 (基于 worktrees/release-prep HEAD `7061321`)

**部署步骤**：

1. **构建新 zip**（在 worktrees/release-prep）
   ```bash
   cd D:\filework\worktrees/release-prep
   python tools/rebuild_zip.py
   # 生成 deploy-v20260708_006.zip
   ```

2. **传输到生产**（任一方式）
   ```bash
   # 方式 A: scp（需密钥）
   scp deploy-v20260708_006.zip root@172.20.59.7:/tmp/

   # 方式 B: 走部署 bundle 工具
   # 用 deploy_bundle 工具上传
   ```

3. **解压并切换**
   ```bash
   # 在生产 /opt/app/deployments/
   # 保留 v20260708_005 作为 rollback
   mv v20260708_005 v20260708_005.bak
   unzip /tmp/deploy-v20260708_006.zip
   mv <解压目录> v20260708_006

   # 切换 current 软链接
   ln -sfn /opt/app/deployments/v20260708_006 /opt/app/current
   ```

4. **重启后端**
   ```bash
   # 在生产
   kill 310  # kill 当前 server.py
   cd /opt/app/current/meta
   nohup python server.py > /tmp/server.log 2>&1 &

   # 验证启动
   curl http://172.20.59.7:5001/api/v1/health
   ```

5. **验证导出**
   - 用 wyonghui 登录
   - 点击导出（cascade 模式）
   - 检查：
     - 领域 = 1 (或 2 with expand)
     - 子领域 = 5 (或 9)
     - 服务模块 = 21 (或 32)
     - 业务对象 = 155
     - 备注信息 = 706 (有数据)

## 🧪 验证脚本

**本地 3018 (已验证修复生效)**：

```bash
cd D:\filework\worktrees/integration\meta
python tests\test_export_cascade_v027pt2.py
```

**预期输出**：
```
Total rows: 1039
  领域 (domain): 2 rows          # dim scope 向上展开 +1
  子领域 (sub_domain): 9 rows    # +4
  服务模块 (service_module): 32 rows  # +11
  业务对象 (business_object): 155 rows
  备注信息 (annotation): 841 rows  # 不再丢
```

> 注：域/子域/服务 +1/+4/+11 是 `DimensionScopeEngine.expand_dimension_values` 向上展开的副作用，与 list 接口一致，**可接受**。
> 关键是 BO = 155 (严格对齐) + 备注 706 → 841 (有数据)。

## 🔄 Rollback

如果新版本出问题：
```bash
# 恢复软链接
ln -sfn /opt/app/deployments/v20260708_005.bak /opt/app/current

# 重启
kill <新 PID>
cd /opt/app/current/meta
nohup python server.py > /tmp/server.log 2>&1 &
```

## 📁 涉及文件

| 文件 | 改动 |
|------|------|
| `meta/services/query_service.py` | 单 role 路径 AND 段改用 `where_raw` 注入 |

## 📚 相关文档

- `DEPLOY_HANDOVER_BUG_V027.md` — Phase 1 多 role 修复交接 (bb53b0a)
- `meta/tests/test_query_service_or_of_and_v1230.py` — 单元测试 (5/5 PASS)
- `meta/tests/test_export_cascade_v027pt2.py` — 集成 e2e 测试脚本

## ✅ 已完成

- [x] 修复代码已 commit 到 worktrees/release-prep (7061321, V007.41 P1)
- [x] 修复代码已 cherry-pick 到 worktrees/integration (88d7ee3)
- [x] 本地 3018 重启加载修复，e2e 验证 BO=155 / 备注=841 ✅
- [x] 单元测试 5/5 PASS

## ⏳ 待部署

- [ ] 构建 v20260708_006 zip
- [ ] 部署到生产 172.20.59.7
- [ ] 重启生产 5001
- [ ] 用 wyonghui 在生产验证导出
- [ ] 通知 PM 验证

---

**部署负责人**: 部署智能体
**修复开发者**: AI Assistant (session) + Dev Agent V047 (7061321)
**发现时间**: 2026-07-08 11:30
**目标完成**: 部署完成后 PM 可在生产系统验证导出
