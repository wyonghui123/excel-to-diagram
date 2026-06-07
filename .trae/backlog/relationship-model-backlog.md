# 关系模型改进 Backlog

> 记录未来需要实施的关系模型改进项
> 
> **最后更新**: 2026-04-21

---

## P2 - 完善关系模型（价值高但不紧急）

### P2.1: 外键关系显式定义

**描述**: 创建 `foreign_keys.yaml` 显式定义所有外键关系

**状态**: 待处理

**原因**: 当前通过 fields 隐式定义外键，未来可能需要更明确的关系定义

**预估工作量**: 2 天

**依赖**: P1 完成

```yaml
# 预期结构
foreign_keys:
  - id: fk_subdomain_domain
    source_object: sub_domain
    source_field: domain_id
    target_object: domain
    target_field: id
    cardinality: N:1
    on_delete: RESTRICT
    on_update: CASCADE
```

---

### P2.2: 聚合/组合关系区分

**描述**: 在父子关系中区分 aggregation 和 composition

**状态**: 待处理

**原因**: 当前都用 aggregation，未来可能需要区分生命周期依赖

**预估工作量**: 1 天

**依赖**: P1 完成

```yaml
parent_child_relations:
  - id: pc_sm_bo
    meta_relation: composition  # vs aggregation
    description: 服务模块包含业务对象（强依赖，不可单独存在）
```

---

### P2.3: 传递性关系支持

**描述**: 支持关系的传递性定义，用于图计算

**状态**: 待处理

**原因**: 当前 DEPENDS_ON 等关系无传递性，未来图计算需要

**预估工作量**: 3 天

**依赖**: 图数据库引入

```yaml
relation_types:
  - id: DEPENDS_ON
    transitive: false  # A依赖B，B依赖C ≠ A依赖C
  - id: SIMILAR_TO
    transitive: true  # A类似B，B类似C ⇒ A类似C
```

---

### P2.4: 关系范围动态计算

**描述**: 将 `category_type` 计算逻辑移到元模型定义

**状态**: 待处理

**原因**: 当前在代码中硬编码计算逻辑

**预估工作量**: 1 天

**依赖**: P1 完成

```yaml
derived_fields:
  - id: category_type
    type: hierarchy_scope
    rule: |
      cross_domain: source.domain_id != target.domain_id
      same_domain_cross_subdomain: source.domain_id == target.domain_id AND source.sub_domain_id != target.sub_domain_id
    depends_on:
      - source_bo_id
      - target_bo_id
```

---



## P3 - 研究性质（可以暂缓）

### P3.1: 多种层级结构支持

**描述**: 支持同一对象参与多个层级结构

**状态**: 研究中

**原因**: 当前只有一种层级，未来可能需要功能视角、组织视角等

**预估工作量**: 未知

---

### P3.2: 外部主数据系统集成

**描述**: 支持从 SAP、Salesforce 等系统同步主数据

**状态**: 规划中

**原因**: 暂无外部系统集成需求

**预估工作量**: 未知

---

### P3.3: 复杂关系推导

**描述**: 基于基础关系推导复合关系

**状态**: 研究中

**示例**: A调用B，B调用C ⇒ A间接依赖C

**预估工作量**: 未知

---

## 已完成项

| 日期 | 项 | 说明 |
|------|-----|------|
| 2026-04-21 | P1.1 | 扩展 relationship.yaml - 添加 relation_types 注册表 |
| 2026-04-21 | P1.2 | 扩展 relationship.yaml - 添加关系分类定义 |
| 2026-04-21 | P1.3 | 创建 hierarchies.yaml - 定义层级结构 |
| 2026-04-21 | P1.4 | 重构 hierarchyFilterBuilder.js 使用 hierarchies.yaml |
| 2026-04-21 | P1.5 | 更新 meta-model-schema-sync.md 规则 |
| 2026-04-21 | **P2.5** | ** hierarchies.yaml 添加 delete_behavior 定义** |
| 2026-04-21 | **P2.5** | **规则 8-9: 父子关系校验与层级定义整合** |

---

## P2 - 未来规划

### P2.Future: 父子关系删除行为策略扩展

**描述**: 支持更多删除策略（CASCADE/SET_NULL）

**状态**: 未来考虑

**原因**:
- 当前默认不支持删除有子节点的父节点（RESTRICT）
- 未来可能需要级联删除（CASCADE）场景
- 需要在 `delete_behavior.policy` 中扩展支持

**预估工作量**: 待定

```yaml
# 未来扩展
delete_behavior:
  policy: CASCADE  # 新增支持
  # RESTRICT: 不允许删除
  # CASCADE: 级联删除子节点
  # SET_NULL: 删除时子节点引用置空
```

---

## 参考资料

- [SAP MDG Data Modeling](https://help.sap.com)
- [ArchiMate Relation Types](https://www.opengroup.org/archimate-forum)
- [Palantir Ontology Modeling](https://www.palantir.com/docs/foundry/ontology/)
- [语义网 OWL Relations](https://www.w3.org/TR/owl2-syntax/)
