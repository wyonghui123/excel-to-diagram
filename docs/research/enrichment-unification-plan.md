# Enrichment 机制统一化实施计划

> 创建时间：2026-05-13
> 关联研究报告：[association-fk-model-research.md](./association-fk-model-research.md)

---

## 一、问题背景

当前系统存在两套独立的 Enrichment 机制：

| 机制 | 声明方式 | 处理字段 | 使用场景 |
|------|---------|---------|---------|
| EnrichmentEngine + RedundancyRegistry | `semantics.redundancy` | service_module_name 等 | ✅ Generic query flow |
| EnumJoinBuilder | `semantics.enum_type_ref` | relation_type_name 等 | ❌ 只有 manage_api.py 硬编码 |

**核心问题**：`RedundancyRegistry` 只解析 `redundancy` 声明，完全忽略 `enum_type_ref` 字段，导致 Generic query flow 中 enum 字段不被填充。

---

## 二、解决方案概述

**核心思路**：扩展 `JoinStep` 支持固定条件，让 `RedundancyRegistry` 同时处理 `redundancy` 和 `enum_type_ref`，实现 Enrichment 机制统一。

```
当前:
  RedundancyRegistry → 只处理 redundancy → 普通 BO 字段被填充
                    → 不处理 enum_type_ref → enum 字段不被填充

统一后:
  RedundancyRegistry → 处理 redundancy → 普通 BO 字段被填充
                     → 处理 enum_type_ref → enum 字段被填充
                     ↓
              EnrichmentEngine 统一填充所有虚拟字段
```

---

## 三、实施阶段

### Phase 1: 扩展 RedundancyRegistry（不破坏现有功能）

**目标**：让 `RedundancyRegistry` 同时注册 `redundancy` 和 `enum_type_ref` 字段，验证输出与 `EnumJoinBuilder` 一致。

#### 步骤 1.1: 扩展 JoinStep dataclass

**文件**: `meta/core/redundancy_registry.py`

```python
@dataclass
class JoinStep:
    table: str           # 目标表
    from_field: str      # 当前表的关联字段
    to_field: str        # 目标表的关联字段
    select: str          # 选择字段

    # 新增: 固定条件（支持 enum 的特殊 JOIN）
    fixed_conditions: List[Tuple[str, str, Any]] = field(default_factory=list)
    # 例: [("enum_type_id", "=", "relation_type"), ("is_active", "=", 1)]
```

#### 步骤 1.2: 新增 _parse_enum_ref 方法

**文件**: `meta/core/redundancy_registry.py`

新增方法将 `semantics.enum_type_ref` 转换为 `RedundancyDef`：

```python
def _parse_enum_ref(
    self,
    object_type: str,
    field_id: str,
    enum_type_ref: str,
    semantics
) -> Optional[RedundancyDef]:
    """
    解析 semantics.enum_type_ref 声明为 RedundancyDef

    将 enum 关联转换为虚拟冗余字段，与普通 BO 关联统一处理
    """
    # 构建 JoinStep with fixed_conditions
    join_step = JoinStep(
        table='enum_values',
        from_field=db_column,
        to_field='code',
        select=f'{select_field} as {field_id}_{select_field}',
        fixed_conditions=[
            ('enum_type_id', '=', enum_type_ref),
            ('is_active', '=', 1),
        ]
    )

    return RedundancyDef(...)
```

#### 步骤 1.3: 修改 build_from_registry

**文件**: `meta/core/redundancy_registry.py`

在循环中同时处理两种声明：

```python
for f in meta_obj.fields:
    # 处理冗余字段（现有逻辑）
    redundancy = getattr(f.semantics, 'redundancy', None)
    if redundancy:
        red_def = self._parse_redundancy(obj_id, f.id, redundancy)
        ...

    # 新增: 处理 enum_type_ref 字段
    enum_type_ref = getattr(f.semantics, 'enum_type_ref', None)
    if enum_type_ref:
        red_def = self._parse_enum_ref(obj_id, f.id, enum_type_ref, f.semantics)
        ...
```

#### 步骤 1.4: 扩展 EnrichmentEngine._build_lookup_query

**文件**: `meta/core/enrichment_engine.py`

SQL 查询增加固定条件：

```python
def _build_lookup_query(self, red_def: RedundancyDef) -> str:
    step = red_def.join_path[0]

    where_clauses = [f"{step.table}.{step.to_field} IN ({self._ids_placeholder})"]

    # 新增: 添加固定条件
    for field, op, value in step.fixed_conditions:
        where_clauses.append(f"{step.table}.{field} {op} {self._format_value(value)}")

    sql = f"SELECT ... FROM {step.table} WHERE {' AND '.join(where_clauses)}"
    return sql
```

#### 验收标准

- [ ] RedundancyRegistry 同时注册 `redundancy` 和 `enum_type_ref` 字段
- [ ] EnrichmentEngine 填充结果与 EnumJoinBuilder 完全一致
- [ ] 所有 62 个现有测试通过
- [ ] 新增单元测试覆盖 `_parse_enum_ref`

---

### Phase 2: 迁移 manage_api.py（消除硬编码）

**目标**：将 `manage_api.py` 中硬编码的 `EnumJoinBuilder` 调用迁移到 `QueryInterceptor`。

#### 步骤 2.1: 修改 relationship 列表查询

**文件**: `meta/api/manage_api.py`

- [ ] 删除 `EnumJoinBuilder` 导入和硬编码调用
- [ ] 改用 `QueryInterceptor`（调用 `EnrichmentEngine`）
- [ ] 验证 relationship 列表功能正常

#### 步骤 2.2: 删除冗余代码

**文件**: `meta/api/manage_api.py`

- [ ] 删除硬编码的 enum JOIN SQL
- [ ] 全面回归测试

#### 验收标准

- [ ] `manage_api.py` 中无 `EnumJoinBuilder` 硬编码
- [ ] relationship 列表页 enum 字段正常显示
- [ ] 所有相关测试通过

---

### Phase 3: 优化 import_export_service（消除 N+1）

**目标**：用批量 JOIN 替代 N+1 单条查询。

#### 步骤 3.1: 识别 N+1 查询点

**文件**: `meta/services/import_export_service.py`

- [ ] 找到所有 `_get_enum_value_info` 调用点
- [ ] 统计 N+1 发生的场景

#### 步骤 3.2: 改用批量查询

**文件**: `meta/services/import_export_service.py`

```python
# Before: N+1 查询
for record in records:
    if relation_code:
        enum_info = self._get_enum_value_info('relation_type', relation_code)  # 每条记录一次查询

# After: 批量查询
enum_codes = [r.get('relation_code') for r in records if r.get('relation_code')]
enum_map = self._batch_get_enum_values('relation_type', enum_codes)  # 一次查询
for record in records:
    record['relation_type_name'] = enum_map.get(record.get('relation_code'), {}).get('name')
```

#### 步骤 3.3: 性能验证

- [ ] 导入 1000 条记录性能 < 5s
- [ ] 导入结果正确（enum 字段正确填充）

#### 验收标准

- [ ] `import_export_service` 无 N+1 查询
- [ ] 导入 1000 条记录性能 < 5s
- [ ] 导入结果正确

---

## 四、详细改动清单

| Phase | 文件 | 改动类型 | 改动内容 |
|--------|------|---------|---------|
| 1 | `meta/core/redundancy_registry.py` | 扩展 | `JoinStep` + `fixed_conditions` |
| 1 | `meta/core/redundancy_registry.py` | 新增 | `_parse_enum_ref()` 方法 |
| 1 | `meta/core/redundancy_registry.py` | 修改 | `build_from_registry()` 处理 enum |
| 1 | `meta/core/enrichment_engine.py` | 修改 | `_build_lookup_query()` 支持固定条件 |
| 1 | `meta/tests/` | 新增 | `_parse_enum_ref` 单元测试 |
| 2 | `meta/api/manage_api.py` | 删除 | `EnumJoinBuilder` 硬编码 |
| 2 | `meta/api/manage_api.py` | 修改 | 使用 `QueryInterceptor` |
| 3 | `meta/services/import_export_service.py` | 重构 | 批量查询替代 N+1 |
| - | `docs/research/association-fk-model-research.md` | 更新 | 记录实施进度 |

---

## 五、工作量估算

| Phase | 任务 | 估算工时 |
|--------|------|---------|
| 1 | 扩展 RedundancyRegistry | 1天 |
| 1 | 验证一致性 | 0.5天 |
| 1 | 新增单元测试 | 0.5天 |
| 2 | 迁移 manage_api.py | 0.5天 |
| 3 | 优化 import_export | 1天 |
| - | 回归测试 | 0.5天 |
| - | 文档更新 | 0.5天 |
| **总计** | | **4.5天** |

---

## 六、风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 现有功能被破坏 | 高 | Phase 1 不删除现有代码，保持向后兼容 |
| 性能回归 | 中 | Phase 3 做性能测试 |
| 测试覆盖不足 | 中 | 新增单元测试 + E2E 测试 |
| 迁移 manage_api.py 遗漏场景 | 中 | 全面回归测试 |

---

## 七、架构健康度提升

| 维度 | 改进前 | 改进后 |
|------|--------|--------|
| Enum Association 填充 | ❌ 只有 manage_api.py | ✅ 所有 generic query |
| Generic Query 覆盖 | 7/10 | ✅ 10/10 |
| Import 性能 | ⚠️ N+1 查询 | ✅ 批量 JOIN |
| 代码简洁性 | 7/10 | ✅ 9/10 |
| **综合评分** | **7.6/10** | **9.5/10** |

---

## 八、后续行动项

| 优先级 | 行动项 | 负责人 | 状态 |
|--------|--------|--------|------|
| P0 | 开始 Phase 1 实施 | 待定 | 待开始 |
| P0 | Phase 1 验收测试 | 待定 | 待开始 |
| P1 | Phase 2 迁移 manage_api.py | 待定 | 待开始 |
| P1 | Phase 3 优化 import_export | 待定 | 待开始 |
| P2 | 更新 association-fk-model-research.md | 待定 | 待开始 |

---

## 九、关键代码位置索引

| 文件 | 行号 | 说明 |
|------|------|------|
| `meta/core/redundancy_registry.py` | L62-70 | `JoinStep` dataclass（待扩展） |
| `meta/core/redundancy_registry.py` | L162-176 | `build_from_registry()`（待修改） |
| `meta/core/redundancy_registry.py` | L186-219 | `_parse_redundancy()`（参考） |
| `meta/core/enrichment_engine.py` | L53-115 | `enrich_batch()`（参考） |
| `meta/core/enrichment_engine.py` | L145-195 | `_enrich_field_batch()`（参考） |
| `meta/core/enum_join_builder.py` | L42-113 | `EnumJoinBuilder`（当前独立逻辑） |
| `meta/api/manage_api.py` | L1080-1086 | 硬编码的 EnumJoinBuilder 调用 |
| `meta/services/import_export_service.py` | L1995 | N+1 查询点 |
