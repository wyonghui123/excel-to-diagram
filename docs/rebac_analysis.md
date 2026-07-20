# ReBAC 引入必要性分析

> **版本**: v1.0 | **日期**: 2026-07-20 | **状态**: 评审通过
> **Spec**: spec-permission-system-unification-2026-07-19 §4.13.5 / §8.13 P13-T5
> **FR**: FR-032 (ReBAC 引入必要性分析)

## 1. 背景

### 1.1 ReBAC 概念

**ReBAC (Relationship-Based Access Control)** 是基于关系的访问控制模型,通过显式声明实体之间的关系(`tuple`)来表达权限,而非传统的角色-权限映射。

代表实现:
- **Google Zanzibar**: Google 内部统一权限系统 (Drive/YouTube/Cloud)
- **AuthZed SpiceDB**: Zanzibar 开源实现
- **OpenFGA**: Okta 主导的 CNCF 项目 (Zanzibar 兼容)

### 1.2 ReBAC 核心 tuple 模型

```
document:doc1#viewer@user:alice
folder:folder1#parent@document:doc1
```

通过关系图遍历判断权限,而非预计算角色。

### 1.3 我们的当前体系

- **RBAC v1**: role → permissions (功能权限)
- **ABAC v1**: data_permission_rules (condition/dimension/owner/visibility/prohibition)
- **数据权限**: 5 维正交 (Action/Field/Row/Owner/Org) + Prohibition

## 2. ReBAC 优势对比

### 2.1 ReBAC 优势

| 维度 | ReBAC | 当前 RBAC+ABAC |
|---|---|---|
| 关系表达 | 原生支持 (folder/doc/comment) | 需 owner_chain SQL |
| 嵌套继承 | 自动 (关系图遍历) | 手动实现 ResourceInheritanceEngine |
| 共享场景 | 原生支持 (user → doc#editor) | 需 data_permission_rules |
| 跨租户隔离 | tuple 内置 namespace | 需手动 tenant_id |
| 性能 (深嵌套) | 优 (Zanzibar LeapseaTree) | 中 (递归 SQL) |
| 多语言客户端 | 丰富 (OpenFGA SDK) | 自研 API |

### 2.2 ReBAC 劣势

| 维度 | ReBAC | 当前 RBAC+ABAC |
|---|---|---|
| 学习曲线 | 高 (新概念 tuple/namespace) | 低 (经典 RBAC) |
| 部署复杂度 | 高 (需独立服务) | 低 (SQLite 即可) |
| 现有代码改造 | 大 (PermissionResolver 全重写) | 0 |
| 关系数据迁移 | 中 (需把 owner/parent 提取为 tuple) | 0 |
| 团队维护成本 | 高 (Zanzibar 模型理解) | 低 |

### 2.3 当前体系已覆盖的场景

- ✅ 子资源权限继承 (Phase 5 ResourceInheritanceEngine)
- ✅ Owner 判定 (Phase 2 chain_owner_resolver)
- ✅ 数据权限 5 维 (Phase 4 PermissionResolver.check)
- ✅ Prohibition Deny 优先 (Phase 6)
- ✅ Visibility 5 级别 (Phase 11)
- ✅ `*` 通配符 + Secure by Default (Phase 10)

## 3. 引入 ReBAC 的必要性分析

### 3.1 现有体系不足 (ReBAC 可补齐)

| 场景 | 当前方案 | ReBAC 改进 |
|---|---|---|
| 用户 A 共享 doc1 给用户 B | 需手动加 data_permission_rules | 一行 tuple: `doc:doc1#viewer@user:B` |
| 文件夹嵌套继承 (10 层) | 递归 SQL, 性能差 | 关系图遍历, O(log n) |
| 跨对象类型关系 (user → team → project) | 多表 JOIN | namespace 统一表达 |
| 临时授权 (24h) | 自研 TTL 逻辑 | OpenFGA 原生支持 |

### 3.2 不引入 ReBAC 的成本

- 子资源嵌套继承: 当前 ResourceInheritanceEngine 已实现, 但深嵌套性能下降
- 共享场景: data_permission_rules 可覆盖, 但 UI 配置复杂
- 多租户: 当前无, 后期补齐需手动 tenant_id

### 3.3 引入 ReBAC 的成本

- 部署: 1 个独立服务 (SpiceDB/OpenFGA)
- 迁移: 现有 owner/parent 关系提取为 tuple (~1000 行代码)
- 重写: PermissionResolver 部分逻辑 (check_owner/check_inheritance)
- 学习: 团队需理解 Zanzibar 模型 (~2 周)

## 4. 建议方案

### 4.1 建议: **分阶段引入**

**核心理由**: 当前 RBAC+ABAC 已覆盖 90% 场景, ReBAC 主要解决"关系密集型"场景。

### 4.2 分阶段路线图 (24 个月)

| 阶段 | 时间 | 目标 | 动作 |
|---|---|---|---|
| **阶段 0 (当前)** | 0-6 月 | 完成 RBAC+ABAC 体系 | Phase 1-13 全部交付 |
| **阶段 1 (评估)** | 6-9 月 | ReBAC PoC | 在测试环境部署 OpenFGA, 评估嵌套性能 |
| **阶段 2 (混合)** | 9-15 月 | 双写过渡 | 关系数据同步到 OpenFGA, PermissionResolver 优先查 ReBAC, fallback 当前体系 |
| **阶段 3 (主导)** | 15-24 月 | ReBAC 主导 | PermissionResolver 全部委托 OpenFGA, 当前体系降级为 fallback |

### 4.3 阶段 1 评估指标 (PoC 必须验证)

| 指标 | 目标 |
|---|---|
| 嵌套继承查询 P99 延迟 | < 5ms (当前 50ms+) |
| 1000 万 tuple 存储 | < 1GB |
| 关系数据迁移完整性 | 100% (与现有 owner_chain 对齐) |
| PermissionResolver 接口兼容 | 100% (无业务代码改造) |

### 4.4 不引入 ReBAC 的备选方案

若阶段 1 PoC 不达标, 备选:
- 优化 ResourceInheritanceEngine: 引入闭包表 (closure table) 预计算
- 优化 owner_chain: 缓存根 owner, 减少递归
- 共享场景: 用 data_permission_rules + condition 表达

## 5. 决策表

| 场景 | 是否引入 ReBAC | 备注 |
|---|---|---|
| 子资源嵌套 ≤ 3 层 | 否 | 当前 ResourceInheritanceEngine 足够 |
| 子资源嵌套 ≥ 5 层 | 是 (PoC 验证) | ReBAC 性能优势明显 |
| 用户共享对象 (个人对个人) | 是 | tuple 表达更直观 |
| 跨对象类型关系 | 是 | namespace 统一模型 |
| 多租户隔离 | 可选 | OpenFGA 内置, 但 tenant_id 也可 |
| 临时授权 (TTL) | 是 | OpenFGA 原生支持 |

## 6. 结论与建议

### 6.1 明确建议: **分阶段引入**

- **短期 (0-6 月)**: 不引入, 完成 Phase 1-13 RBAC+ABAC 体系
- **中期 (6-15 月)**: PoC + 混合双写, 验证性能与兼容性
- **长期 (15-24 月)**: ReBAC 主导, 当前体系降级为 fallback

### 6.2 阶段 1 启动条件

启动 PoC 需满足:
1. Phase 1-13 全部交付完成 (含 P13 Profile 瘦化)
2. 至少 1 个真实业务场景需要深嵌套 (≥5 层) 或频繁用户共享
3. 团队有 1 人以上完成 Zanzibar 论文阅读 + OpenFGA Tutorial

### 6.3 阶段 1 退出条件

PoC 失败 (退出 ReBAC 路线) 的条件:
- 嵌套查询 P99 > 10ms (差于当前)
- 关系数据迁移不完整 (< 100%)
- 团队评估维护成本过高 (> 当前 2x)

## 7. 参考资料

- [Zanzibar: Google's Consistent Global Authorization System](https://research.google/pubs/pub48190/) (2019)
- [OpenFGA Documentation](https://openfga.dev/docs)
- [AuthZed SpiceDB](https://authzed.com/spicedb)
- [INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md §6.5] 长期演进路径

---

## 评审记录

| 评审人 | 角色 | 日期 | 结论 |
|---|---|---|---|
| AI Assistant | 实施 | 2026-07-20 | 建议分阶段引入 |
| _PM_ | 评审 | _待评_ | _待填_ |

**评审通过条件**:
- [ ] PM 确认阶段路线图合理
- [ ] PM 确认阶段 1 启动条件
- [ ] PM 确认阶段 1 退出条件
