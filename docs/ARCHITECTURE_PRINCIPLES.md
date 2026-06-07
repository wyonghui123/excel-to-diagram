# 语义模型驱动架构原则

> 本文档定义了项目的核心架构原则，所有代码修改必须遵循这些原则。
> AI Coding 助手必须首先阅读并理解本文档。

## 核心原则

### 1. 单一事实源（Single Source of Truth）

**定义**：每个业务概念或规则只在一个地方定义，其他地方通过引用获取。

**示例**：
```yaml
# ✅ 正确：hierarchies.yaml 是规则的唯一权威来源
# hierarchies.yaml
hierarchy_scopes:
  - id: cross_domain
    rule: source.domain_id != target.domain_id
    name: 跨领域

# relationship.yaml - 通过引用获取，不重复定义
semantics:
  scope_rules_ref: hierarchies.hierarchy_scopes  # 引用权威定义

# ❌ 错误：在多处重复定义同一规则
semantics:
  filter_transform:
    sql_expr: CASE WHEN source_domain_id != target_domain_id THEN '跨领域' ...  # 重复定义！
```

**检查清单**：
- [ ] 新增规则时，是否确定了唯一的权威来源？
- [ ] 其他地方是否通过引用获取，而不是复制粘贴？
- [ ] 修改规则时，是否只需要修改一处？

### 2. 声明式优于命令式（Declarative over Imperative）

**定义**：通过元数据声明"是什么"，而不是编写代码描述"怎么做"。

**示例**：
```yaml
# ✅ 正确：声明式 - 描述字段的语义和行为
- id: category_label
  storage: virtual
  semantics:
    computed_by: hierarchy_scope
    scope_rules_ref: hierarchies.hierarchy_scopes

# ❌ 错误：命令式 - 在代码中硬编码逻辑
if field == 'category_label':
    if source_domain != target_domain:
        return '跨领域'
```

**检查清单**：
- [ ] 是否通过 YAML 元数据定义字段行为？
- [ ] 是否避免了在代码中硬编码业务规则？
- [ ] 新增字段时，是否只需修改 YAML 文件？

### 3. 元数据驱动（Metadata Driven）

**定义**：系统行为由元数据决定，代码只是元数据的解释器。

**架构层次**：
```
┌─────────────────────────────────────────────────────────────┐
│                    元数据层 (YAML)                           │
│  定义：字段、规则、关系、约束、UI配置                         │
│  文件：meta/schemas/*.yaml                                  │
├─────────────────────────────────────────────────────────────┤
│                    元模型层 (Python)                         │
│  解析：MetaObject, MetaField, SemanticAnnotation            │
│  文件：meta/core/models.py, yaml_loader.py                  │
├─────────────────────────────────────────────────────────────┤
│                    服务层 (Python)                           │
│  执行：QueryService, EnrichmentEngine, TransformEngine      │
│  文件：meta/services/*.py, meta/core/*.py                   │
├─────────────────────────────────────────────────────────────┤
│                    API层 (Flask)                             │
│  暴露：REST API 端点                                         │
│  文件：meta/api/*.py                                         │
└─────────────────────────────────────────────────────────────┘
```

**检查清单**：
- [ ] 新功能是否优先考虑通过元数据配置实现？
- [ ] 代码是否是通用的元数据解释器？
- [ ] 是否避免了为特定业务场景编写特殊代码？

### 4. 字段存储策略（Field Storage Strategy）

**定义**：明确区分字段的存储方式，确保数据一致性。

| 存储类型 | 说明 | 一致性保障 | 示例 |
|---------|------|-----------|------|
| `STORED` | 物理存储 | WriteGuard 写入时同步 | `source_code`, `target_code` |
| `VIRTUAL` | 不存储 | EnrichmentEngine 查询时计算 | `category_label`, `source_bo_name` |
| `COMPUTED` | 物理存储 + 计算 | ComputedFieldHandler 保存时计算 | （已废弃，改用 VIRTUAL） |

**决策树**：
```
字段是否需要排序/过滤？
├── 是 → 字段值是否可从其他字段派生？
│   ├── 是 → 使用 VIRTUAL + scope_rules_ref
│   └── 否 → 使用 STORED
└── 否 → 使用 VIRTUAL
```

**检查清单**：
- [ ] 新增字段时，是否明确指定了 `storage` 类型？
- [ ] VIRTUAL 字段是否声明了 `computed_by` 或 `scope_rules_ref`？
- [ ] STORED 冗余字段是否在 `semantics.redundancy` 中声明？

### 5. 引用机制（Reference Mechanism）

**定义**：通过 `ref` 引用权威定义，避免重复。

**支持的引用类型**：

| 引用类型 | 格式 | 说明 |
|---------|------|------|
| `scope_rules_ref` | `hierarchies.hierarchy_scopes` | 引用层级范围规则 |
| `resolve_from_field` | `source_bo_id` | 从关联字段解析值 |
| `resolve_to_object` | `business_object` | 解析到目标对象 |

**检查清单**：
- [ ] 是否优先使用 `ref` 引用而不是复制定义？
- [ ] 引用路径是否正确（`文件名.键名`）？
- [ ] 被引用的定义是否存在且正确？

---

## 常见错误及修复

### 错误1：规则重复定义

**问题**：
```yaml
# hierarchies.yaml 定义了规则
hierarchy_scopes:
  - rule: source.domain_id != target.domain_id

# relationship.yaml 又重复定义
filter_transform:
  sql_expr: CASE WHEN source_domain_id != target_domain_id ...
```

**修复**：
```yaml
# relationship.yaml - 使用引用
semantics:
  scope_rules_ref: hierarchies.hierarchy_scopes
```

### 错误2：在代码中硬编码业务规则

**问题**：
```python
# 硬编码规则
if source_domain_id != target_domain_id:
    category = '跨领域'
```

**修复**：
```python
# 从元数据读取规则
rules = load_scope_rules_from_ref('hierarchies.hierarchy_scopes')
category = evaluate_scope_rules(rules, relation)
```

### 错误3：存储类型选择错误

**问题**：
```yaml
# category_label 不应该存储
- id: category_label
  db_column: category_label  # 错误：会存储到数据库
```

**修复**：
```yaml
- id: category_label
  storage: virtual  # 正确：不存储，查询时计算
```

---

## 参考架构

本架构参考以下业界最佳实践：

| 来源 | 借鉴概念 |
|------|---------|
| SAP S/4HANA CDS View | `$projection` 表达式复用、Virtual Element |
| Salesforce | Formula Field、Cross-Object Field |
| Palantir Ontology | Derived Property、Object Type |
| SAP SADL | Sort Transform、Filter Transform |

---

## 修改前必读

在修改以下文件前，必须确保理解相关架构原则：

| 文件 | 相关原则 |
|------|---------|
| `meta/schemas/*.yaml` | 单一事实源、声明式、元数据驱动 |
| `meta/core/models.py` | 元模型定义、字段存储策略 |
| `meta/core/virtual_field_transform.py` | 引用机制、单一事实源 |
| `meta/services/query_service.py` | VIRTUAL 字段处理 |
| `meta/api/manage_api.py` | 避免硬编码规则 |

---

## 快速检查命令

```bash
# 检查是否有重复的规则定义
grep -r "source_domain_id != target_domain_id" meta/

# 检查 VIRTUAL 字段是否正确声明
grep -A5 "storage: virtual" meta/schemas/*.yaml

# 检查是否有硬编码的业务规则
grep -r "跨领域\|同服务模块" meta/ --include="*.py"
```
