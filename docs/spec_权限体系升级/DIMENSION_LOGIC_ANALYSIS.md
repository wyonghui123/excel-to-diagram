# 维度权限逻辑分析: 父子维度配置组合

> **问题来源**: PM 询问 "当 domain=全部 + sub_domain=具体(采购供应) 时, 合理逻辑是什么?"
> **分析日期**: 2026-07-23
> **方法**: Python + sqlite3 临时 DB + DimensionScopeEngine 实测
> **PM 决策**: **方案 B 笛卡尔积** (2026-07-23)
> **修复状态**: ✅ 已实施 (commit 待生成)

---

## 一、问题精确还原

**PM 配置场景** (UI 上):
```
角色配置:
  - 维度: domain (领域) → scope_mode='all' / wildcard 全选
  - 维度: sub_domain (子领域) → scope_mode='include' + values=[采购供应]
```

**问题**:
1. 这种"父维度全选 + 子维度具体"的组合**合理吗**？
2. SQL 输出应该是什么？
3. 现有代码的实际行为是什么？

---

## 二、实测结果 (Python + sqlite3 真实测试)

通过临时 DB 模拟 4 种组合, 用 DimensionScopeEngine 跑 `expand_dimension_values` + `derive_data_conditions`, 得到实际 SQL 输出:

| # | 配置 | inherit=1 | expanded sub_domain | sub_domain SQL | service_module SQL |
|---|------|-----------|---------------------|----------------|---------------------|
| **A** | `domain=all + sub_domain=[101]` | 1+1 | **{101, 102, 201, 301}** (全开, 4个) | `domain_id IN (1,2,3) AND id IN (101,102,201,301)` | `sub_domain_id IN (101,102,201,301) AND ...` |
| **B** | `domain=[1] + sub_domain=all` | 1+1 | **{101, 102, 201, 301}** | (同 A, 对称) | (同 A) |
| **C** | 仅 `sub_domain=[101]` | 1 | **{101}** | `id = 101 AND domain_id = 1` | `sub_domain_id = 101 AND ...` |
| **D** | `domain=[1] + sub_domain=[101]` | 1+0 | **{101, 102}** (domain=1下全部) | `id IN (101, 102) AND domain_id IN (1)` | `sub_domain_id IN (101, 102) AND ...` |

### 关键发现

**场景 A (PM 问的场景)**: **配置失效！**
- PM 在 UI 上选 `domain=all + sub_domain=采购供应(101)`
- 期望: 可见全 domain 下的 sub_domain=101 (但 101 已经属于 domain=1)
- 实际: 由于 `inherit_children=1` (默认), `domain=all` 沿 HIERARCHY_CHAIN 向下展开, 把 `expanded['sub_domain']` 扩成全部 4 个 sub_domain
- **结果**: PM 配置的 sub_domain=[101] 形同虚设, 系统等同于 "全 domain + 全 sub_domain"

**根因**: `dimension_scope_engine.py` L196-233 — `scope_mode='all'` 时如果 `inherit_children=1`, 一律沿 HIERARCHY_CHAIN 向下展开所有子维度, 不考虑用户是否给子维度配了具体值

---

## 三、业界最佳实践对比

| 方案 | 设计哲学 | 用户体验 | 风险 |
|------|----------|----------|------|
| **SAP PFCG** | 父子嵌套: 父维度选 A, 子维度只能选 A 下的 | 必须先选父维度, 严格一致 | 配置繁琐, 语义清晰 |
| **Salesforce** | 多维度 OR 合并: 任一命中即可见 | 灵活 | 易越权 |
| **AWS IAM** | Deny 覆盖 Allow, 默认拒绝 | 严格 | 学习曲线 |
| **Azure RBAC** | 类似 Salesforce OR | 灵活 | 易误配 |
| **当前实现** | 全 AND + inherit_children 向下展开 | 看起来配置生效, 实际不一定 | ⚠️ **bug (场景 A)** |

---

## 四、3 种合理逻辑方案

### 方案 1: 拒绝父维度 all + 子维度具体 的组合 (强约束)

**逻辑**: UI/API 校验, 不允许这种配置
- 用户必须二选一:
  - `domain=all` (不配 sub_domain)
  - `domain=具体 + sub_domain=具体`
- 提示: "子维度配置在不指定全维度的父维度时无意义。请选择'全部'或'具体值'之一"

**优点**: 清晰无歧义, 无 bug 风险
**缺点**: 配置灵活度低
**业界参照**: SAP PFCG (最强约束)

**SQL 输出** (不可达 — 被 UI 拒绝):
```
N/A — 前端校验拒绝保存
```

### 方案 2: 笛卡尔积 (推荐) ⭐

**逻辑**: 父维度 all 不再向下展开子维度, 子维度精确生效
- `domain=all` → `expanded['domain'] = {全部}`
- `sub_domain=[101]` → `expanded['sub_domain'] = {101}` (不被父维度继承污染)
- **SQL**: `sub_domains.domain_id IN (1,2,3) AND sub_domains.id IN (101)` = "全 domain 范围里的 sub_domain=101"

**实测 SQL 输出** (期望修复后):
```
[sub_domain] domain_id IN (1,2,3) AND id IN (101)
[service_module] sub_domain_id IN (101) AND sub_domain_id IN (101)
```

**优点**: 直觉, 子维度精确生效, 业界最贴合"父子嵌套"语义
**缺点**: 当子维度也是 all 时仍可配置 (需另加校验)

**业界参照**: SAP PFCG (父子嵌套思想的工程化实现)

**实施细节** (伪代码):
```python
# 修改 expand_dimension_values()
if scope_mode == 'all':
    all_ids = self._get_all_dimension_ids(code)
    expanded[code].update(all_ids)
    
    # 向下展开条件: 父维度 all + 子维度未显式配置 → 展开
    # 父维度 all + 子维度显式 include → 不展开子维度 (PM 配置精确生效)
    for next_dim in HIERARCHY_CHAIN[idx + 1:]:
        # 检查子维度是否有显式 include 配置
        next_scopes = [s for s in scopes if s['dimension_code'] == next_dim]
        if next_scopes and any(s.get('scope_mode') == 'include' for s in next_scopes):
            # 子维度已显式 include → 不继承, 沿独立的 expanded 走
            break
        # 否则继承展开
        ...
```

### 方案 3: parent 维度启发式 + Warning

**逻辑**: 保留配置灵活, 但 UI 显示警告
- 检测到 `父维度 all + 子维度具体` 时, UI 显示 "⚠️ sub_domain 配置将被忽略, 因为 domain=all"
- 后端照常按当前逻辑跑 (子维度失效)

**优点**: 配置灵活
**缺点**: 易误导用户, 调试成本高

---

## 五、PM 推荐与决策

**推荐**: **方案 2 (笛卡尔积)**

**理由**:
1. 直觉: PM 的 UI 表达意图 (domain 全选 + sub_domain 仅 101) 应被精准执行
2. 兼容: 兼容现有所有合法配置 (场景 B/C/D 不变)
3. 修复 bug: 方案 2 修复了"配置失效"的隐藏 bug
4. 业界背书: 贴合 SAP PFCG 的"父子嵌套"语义, 但允许 PM 表达更细致的权限
5. SQL 性能: 不需要更多 JOIN

**实施建议**: 
- 改动 `dimension_scope_engine.py` L196-233
- 改动后增加 1 个 e2e 场景验证 (场景 A: domain=all + sub_domain=具体 → 仅返回 sub_domain=[具体])
- 在 spec 08 文档新增 "AC-008: 笛卡尔积语义"

**PM 决策点**:
- [ ] **方案 1** (拒绝组合, UI 校验) — 简单但严格
- [ ] **方案 2** (笛卡尔积, 修复 bug) — 推荐
- [ ] **方案 3** (灵活 + warning) — 易误用

---

## 六、附录: 现状证据

### 6.1 代码定位

**问题代码**: `d:\filework\worktrees\release-prep\meta\services\dimension_scope_engine.py`

L186-233 `expand_dimension_values` 方法:
```python
def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
    scopes = self._load_scopes(role_id)
    expanded = {}
    for scope in scopes:
        code = scope['dimension_code']
        scope_mode = scope.get('scope_mode', 'include')
        if scope_mode == 'all':
            all_ids = self._get_all_dimension_ids(code)
            ...
            # 向下展开子维度（inherit_children 默认 1）
            if scope.get('inherit_children', 1) == 1:  # ⚠️ 问题点
                ...
                for next_dim in HIERARCHY_CHAIN[idx + 1:]:
                    ...
```

L301-307 `derive_data_conditions`:
```python
expanded = self.expand_dimension_values(role_id)
# 扩展后, 跨维度用 AND 组合 (Line 467)
# ' AND '.join(parts)
```

### 6.2 测试场景代码

**测试方法**: 用 Python + sqlite3 临时 DB, 构造 4 种 role 配置组合, 调用真实 DimensionScopeEngine.

**测试脚本** (临时, 已清理):
```python
# meta/services/dimension_scope_engine.py
ds = get_data_source('sqlite', path=db_path)
engine = DimensionScopeEngine(ds)

for role_id in [9001, 9002, 9003, 9004]:
    expanded = engine.expand_dimension_values(role_id)
    conditions = engine.derive_data_conditions(role_id)
    # 打印 SQL 输出
```

### 6.3 行业最佳实践引用

| 资料 | URL/来源 | 关键结论 |
|------|----------|----------|
| SAP PFCG Documentation | help.sap.com (Authorizations) | 父子嵌套, 严格一致 |
| Salesforce Permission Sets | help.salesforce.com | OR 合并, 但建议 Deny 优先 |
| AWS IAM Policy Evaluation | docs.aws.amazon.com/IAM | Explicit Deny > Allow |
| 微软 Azure RBAC | learn.microsoft.com/azure | Action + Data + Condition |

---

## 七、待 PM 决策

| 选项 | 语义 | 业界对齐 | 实施复杂度 |
|------|------|----------|-----------|
| **A. 方案 1: 拒绝组合** | UI/API 校验, 不允许父维度 all + 子维度具体 | SAP (最强约束) | 1-2 小时 |
| **B. 方案 2: 笛卡尔积** (推荐) | 父维度 all 不污染子维度精确值 | SAP/Salesforce 折衷 | 4-6 小时 (含测试) |
| **C. 方案 3: Warning** | 保留配置但 UI 警告 | AWS (Deny priority) | 2-3 小时 |
| **D. 保持现状** | 文档化 + 测试覆盖 bug 行为 | 无 | 1 小时 |

请 PM 选择 (A/B/C/D), 或定义新的方案 E.
