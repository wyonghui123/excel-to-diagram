# Spec: Deep Insert 增强 + 多态 Composition 支持

> **创建日期**: 2026-05-21
> **父文档**: spec-phase3-architecture-enhancement.md
> **状态**: 待确认
> **优先级**: P2

---

## 1. Background & Objectives

### 1.1 Background

经过深入分析，发现 **Deep Insert API 已经实现**，但存在关键缺陷；**多态 Composition 尚未实现**。

同时发现 **import_cascade 批量导入功能已实现**，与 Deep Insert 有功能重叠但场景不同。

#### 现有实现状态

| 功能 | 状态 | 实现位置 | 关键缺陷 |
|------|------|---------|---------|
| Deep Insert API | 🟡 **已实现但有缺陷** | `meta/core/deep_insert_engine.py` | **无事务回滚**、不支持 Update |
| import_cascade 批量导入 | 🟡 **已实现但有缺陷** | `meta/services/import_export_service.py` | **无事务回滚**、Sheet 独立导入 |
| 多态 Composition | ❌ **未实现** | - | 无 cascade_delete 配置 |

#### import_cascade vs Deep Insert 对比分析

| 维度 | import_cascade | Deep Insert | 说明 |
|------|---------------|-------------|------|
| **数据来源** | Excel 文件 | JSON 请求 | 不同场景 |
| **对象数量** | 多个 Sheet，每个 Sheet 一个对象类型 | 单个父对象 + 多个子对象类型 | 不同粒度 |
| **导入顺序** | 按层级排序（父对象优先） | 先父后子，外键自动推断 | 类似逻辑 |
| **操作模式** | create/update/delete/skip | 仅 create | import_cascade 更丰富 |
| **冲突策略** | upsert/skip/replace | 无 | import_cascade 更丰富 |
| **进度回调** | ✅ 支持 | ❌ 不支持 | import_cascade 更完善 |
| **异步执行** | ✅ 支持 | ❌ 不支持 | import_cascade 更完善 |
| **事务回滚** | ❌ 无 | ❌ 无 | **共同缺陷** |
| **适用场景** | 数据迁移、批量导入 | API 调用、前端表单提交 | 互补 |

**结论**：
- `import_cascade` 和 `Deep Insert` 是**互补关系**，不是重复
- `import_cascade` 适合数据迁移场景，功能更丰富
- `Deep Insert` 适合 API 调用场景，更轻量
- **两者都需要事务回滚增强**

#### Deep Insert 现有实现分析

**已实现的功能**:
- ✅ `/api/v1/<object_type>/deep` 端点 (`manage_api.py:299-396`)
- ✅ `/api/v2/bo/<object_type>/deep` 端点 (`bo_api.py:197-208`)
- ✅ `DeepInsertEngine` 类 (`deep_insert_engine.py`)
- ✅ 前端 `boService.deepInsert()` 方法 (`src/services/boService.js:338-350`)
- ✅ 单元测试 + E2E 测试

**关键缺陷**:
```python
# deep_insert_engine.py 第 15-16 行注释
"""
事务性保证：父对象创建失败则整体失败，子对象部分失败记录错误但不回滚父对象。
"""
```

| 缺陷 | 说明 | 影响 |
|------|------|------|
| **无事务回滚** | 子对象创建失败时，父对象已创建，不会回滚 | 数据不一致 |
| **不支持 Deep Update** | 只能创建，不能更新已有对象 | 功能不完整 |
| **不支持多层嵌套** | 只支持一层 parent + children | 复杂场景不支持 |
| **外键推断可能错误** | 依赖命名约定，可能推断错误 | 数据关联错误 |

#### 多态 Composition 现有实现分析

**已实现的功能**:
- ✅ Annotation 有多态关联字段 (`target_type`, `target_id`)
- ✅ 多态关联查询支持

**关键缺陷**:
```yaml
# annotation.yaml - 缺少 cascade_delete 配置
associations:
  - name: target
    target_type: polymorphic
    # ❌ 没有 cascade_delete: true
    # ❌ 没有 async_delete 配置
```

| 缺陷 | 说明 | 影响 |
|------|------|------|
| **无 cascade_delete 配置** | 多态关联不支持级联删除配置 | 配置不完整 |
| **无反向级联删除逻辑** | 父对象删除时，annotation 不会被删除 | 孤儿数据 |
| **无审计日志关联** | 删除操作未记录父子关联 | 审计不完整 |

### 1.2 Business Objectives

- **Deep Insert 增强**: 添加事务回滚，支持 Deep Update
- **多态 Composition**: 实现反向级联删除，保证数据一致性

### 1.3 User / Stakeholder (涉众) Objectives

- **开发人员**: 使用事务安全的 Deep Insert API
- **系统管理员**: 配置多态关联的级联删除
- **业务用户**: 数据一致性保证

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence (Source) |
|------|------------|-------------------|
| Business | Yes | 数据一致性是企业应用的基本要求 |
| User/Stakeholder (涉众) | Yes | 开发人员、系统管理员 |
| Solution | Yes | 事务回滚、反向级联删除 |
| Functional | Yes | 详细行为定义 |
| Nonfunctional | Yes | 性能、可靠性 |
| External Interface | Yes | API 兼容性、前端适配 |
| Transition | Yes | 现有 API 兼容 |

---

## 3. Functional Requirements

### FR-001: Deep Insert 事务回滚

- **Description**: 系统 MUST 在 Deep Insert 失败时回滚所有已创建的对象（包括父对象）。
- **Acceptance Criteria**:
  - AC-001: 使用数据库事务包裹整个 Deep Insert 操作
  - AC-002: 父对象创建失败时，返回错误，不创建任何对象
  - AC-003: 子对象创建失败时，回滚父对象和已创建的子对象
  - AC-004: 返回详细的错误信息，包括失败原因
  - AC-005: 记录审计日志（失败时记录回滚操作）
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 数据一致性要求

### FR-002: Deep Update 支持

- **Description**: 系统 MUST 支持通过 Deep Insert API 更新已有对象及其子对象。
- **Acceptance Criteria**:
  - AC-001: 支持通过 ID 或业务键标识已有对象
  - AC-002: 已有对象执行更新操作，新对象执行创建操作
  - AC-003: 子对象支持增量更新（新增、修改、删除）
  - AC-004: 整个操作在同一事务中执行
- **Priority**: Should
- **Type Mapping**: Solution / Functional
- **Source**: SAP OData Deep Update

### FR-002-B: import_cascade 事务回滚（可选增强）

- **Description**: 系统 SHOULD 在 import_cascade 失败时提供事务回滚选项。
- **Acceptance Criteria**:
  - AC-001: 支持配置 `transaction_mode: all_or_nothing` 或 `independent`
  - AC-002: `all_or_nothing` 模式下，任一 Sheet 失败则回滚所有 Sheet
  - AC-003: `independent` 模式下，每个 Sheet 独立提交（当前行为）
  - AC-004: 提供详细的回滚报告
- **Priority**: Could
- **Type Mapping**: Solution / Functional
- **Source**: 数据一致性要求

### FR-003: 多态 Composition cascade_delete 配置

- **Description**: 系统 MUST 支持在多态关联上配置 cascade_delete。
- **Acceptance Criteria**:
  - AC-001: 支持 `cascade_delete: true` 配置
  - AC-002: 支持 `async_delete: true/false` 配置（默认 false）
  - AC-003: YAML 解析器正确解析配置
  - AC-004: 配置存储在 MetaObject.associations 中
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: SAP BOPF Alternative Node

### FR-004: 多态 Composition 反向级联删除

- **Description**: 系统 MUST 在父对象删除时，自动删除通过多态关联绑定到它的子对象。
- **Acceptance Criteria**:
  - AC-001: 检测对象是否有多态 Composition 配置（cascade_delete=true）
  - AC-002: 查询所有匹配的子对象（target_type=parent_type, target_id=parent_id）
  - AC-003: 同步删除：在同一事务中删除子对象
  - AC-004: 异步删除：创建后台任务执行删除
  - AC-005: 记录审计日志，包含父子关联信息
  - AC-006: 支持批量删除时的反向级联
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: SAP BOPF Alternative Node

---

## 4. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: Deep Insert 事务响应时间 < 2s（包含 100 个子对象）
- **Measurement**: 性能测试
- **Priority**: Should
- **Source**: 企业应用性能要求

### NFR-002: 可靠性

- **Description**: Deep Insert 失败时必须全部回滚，不留下部分数据
- **Measurement**: 集成测试，模拟各种失败场景
- **Priority**: Must
- **Source**: 数据一致性要求

### NFR-003: 向后兼容

- **Description**: 新功能不能破坏现有 API 行为
- **Measurement**: 现有测试全部通过
- **Priority**: Must
- **Source**: 渐进式迁移要求

---

## 5. External Interface Requirements

### IF-001: Deep Insert API（现有，需增强）

- **Type**: API
- **Endpoint**: `POST /api/v1/<object_type>/deep`
- **现有实现**: `manage_api.py:299-396`
- **增强内容**:
  - 添加事务回滚
  - 支持 Deep Update（通过 `id` 或业务键）
  - 返回更详细的错误信息

- **Request（增强后）**:
```json
{
  "parent": {
    "id": 1,              // 可选，有则更新，无则创建
    "code": "SO001",
    "customer_id": 1
  },
  "children": {
    "items": [
      { "id": 10, "quantity": 20 },           // 更新
      { "product_id": 102, "quantity": 5 }    // 新增
    ]
  },
  "options": {
    "transaction_mode": "all_or_nothing",     // 默认
    "delete_missing_children": false          // 是否删除未列出的子对象
  }
}
```

- **Response（失败时）**:
```json
{
  "success": false,
  "error_code": "TRANSACTION_ROLLBACK",
  "message": "子对象创建失败，已回滚所有操作",
  "detail": {
    "failed_at": "children.items[2]",
    "reason": "验证失败：quantity 不能为负数",
    "rolled_back": {
      "parent_id": null,
      "children_created": 2,
      "children_rolled_back": true
    }
  }
}
```

### IF-002: 多态 Composition YAML 配置

- **Type**: Configuration
- **文件**: `annotation.yaml`
- **增强内容**:
```yaml
associations:
  - name: target
    target_type: polymorphic
    polymorphic_type_field: target_type
    polymorphic_id_field: target_id
    
    # 新增配置
    cascade_delete: true           # 启用反向级联删除
    async_delete: false            # 默认同步删除
    batch_size: 100                # 异步删除时的批量大小
```

### IF-003: 前端 boService.js（需适配）

- **Type**: Frontend Service
- **文件**: `src/services/boService.js`
- **现有实现**: `deepInsert()` 方法 (第 338-350 行)
- **适配内容**:
  - 处理新的错误响应格式
  - 支持 Deep Update 调用
  - 添加事务状态提示

```javascript
// 增强后的 deepInsert 方法
async deepInsert(objectType, parent, children = {}, options = {}) {
  const response = await fetch(`${this.API_BASE_V2}/bo/${objectType}/deep`, {
    method: 'POST',
    headers: this._getHeaders(),
    body: JSON.stringify({ parent, children, options })
  })

  const result = await this._handleResponse(response)
  
  // 处理事务回滚错误
  if (!result.success && result.error_code === 'TRANSACTION_ROLLBACK') {
    console.warn('Deep Insert rolled back:', result.detail)
  }
  
  if (result.success) {
    this._clearCache(objectType)
  }
  return result
}
```

---

## 6. Transition Requirements

### TR-001: 现有 API 兼容

- **Description**: Deep Insert API 的现有调用方式必须继续工作
- **Strategy**: 
  - 新参数（`options`）为可选
  - 现有请求格式继续支持
  - 错误响应格式向后兼容
- **Rollback Plan**: 恢复原有 DeepInsertEngine
- **Source**: 渐进式迁移

### TR-002: 前端适配

- **Description**: 前端需要适配新的错误处理
- **Strategy**: 
  - 现有调用无需修改
  - 新增错误处理逻辑
- **影响范围**: `src/services/boService.js`
- **Source**: 前端兼容

---

## 7. 现有对象和前端适配影响分析

### 7.1 后端影响分析

#### 受影响的文件

| 文件 | 影响类型 | 说明 |
|------|---------|------|
| `meta/core/deep_insert_engine.py` | **重构** | 添加事务支持，核心逻辑修改 |
| `meta/api/manage_api.py` | **修改** | 增强错误处理，添加 Deep Update 支持 |
| `meta/api/bo_api.py` | **修改** | 同步 manage_api.py 的增强 |
| `meta/services/deletion_service.py` | **扩展** | 添加多态 Composition 反向级联删除 |
| `meta/core/yaml_loader.py` | **扩展** | 解析 cascade_delete 配置 |
| `meta/core/models.py` | **扩展** | 添加 PolymorphicCascadeConfig 模型 |
| `meta/services/import_export_service.py` | **可选扩展** | 添加事务回滚选项（FR-002-B） |

#### 不受影响的文件

| 文件 | 原因 |
|------|------|
| `meta/core/action_executor.py` | Deep Insert 使用独立的 DeepInsertEngine |
| `meta/services/manage_service.py` | 现有 CRUD 逻辑不变 |
| `meta/core/rule_executor.py` | 规则执行逻辑不变 |

### 7.2 前端影响分析

#### 受影响的文件

| 文件 | 影响类型 | 说明 |
|------|---------|------|
| `src/services/boService.js` | **修改** | 适配新的错误响应格式 |
| `src/services/__tests__/boService.spec.js` | **更新** | 更新测试用例 |

#### 不受影响的文件

| 文件 | 原因 |
|------|------|
| 其他 Service 文件 | 不使用 deepInsert |
| UI 组件 | 通过 boService 调用，无直接依赖 |

### 7.3 现有 YAML Schema 影响

#### 受影响的 Schema

| Schema | 影响类型 | 说明 |
|--------|---------|------|
| `annotation.yaml` | **修改** | 添加 cascade_delete 配置 |
| 其他有多态关联的 Schema | **可选修改** | 按需添加 cascade_delete |

#### 不受影响的 Schema

| Schema | 原因 |
|--------|------|
| 无多态关联的 Schema | 不涉及多态 Composition |

### 7.4 数据库影响

| 影响 | 说明 |
|------|------|
| **无结构变更** | 不需要新增表或字段 |
| **可能的数据清理** | 需要清理现有的孤儿 annotation 数据 |

### 7.5 测试影响

#### 需要更新的测试

| 测试文件 | 说明 |
|---------|------|
| `meta/tests/test_deep_insert_engine.py` | 添加事务回滚测试 |
| `meta/tests/test_p2_enhancements.py` | 更新 Deep Insert 测试 |
| `tests/e2e/test_e2e_bo_crud.py` | 添加事务回滚 E2E 测试 |
| `src/services/__tests__/boService.spec.js` | 前端测试更新 |

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | Deep Insert 事务回滚 | Must | 数据一致性关键 |
| FR-003 | 多态 Composition 配置 | Must | 配置基础 |
| FR-004 | 多态 Composition 反向级联删除 | Must | 数据一致性关键 |
| FR-002 | Deep Update 支持 | Should | 功能完善 |

- Suggested Milestones:
  - **Milestone 1**（2天）：FR-001 Deep Insert 事务回滚
  - **Milestone 2**（2天）：FR-003 + FR-004 多态 Composition
  - **Milestone 3**（1天）：FR-002 Deep Update 支持

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:

```
Deep Insert 流程（现有）:
┌─────────────────────────────────────────────────────────────┐
│ 1. 解析请求                                                  │
│ 2. 创建父对象 → 成功则继续，失败则返回                        │
│ 3. 遍历子对象:                                               │
│    - 创建子对象 → 成功则记录，失败则记录错误（不回滚！）       │
│ 4. 返回结果（可能包含部分失败）                               │
└─────────────────────────────────────────────────────────────┘
问题：子对象失败时，父对象已创建，数据不一致！
```

- **Current Issues**:
  1. Deep Insert 无事务回滚
  2. 不支持 Deep Update
  3. 多态关联无 cascade_delete 配置
  4. 多态关联无反向级联删除逻辑

- **Relevant Code Paths**:
  - `meta/core/deep_insert_engine.py:24-87` - execute 方法
  - `meta/api/manage_api.py:299-396` - deep_insert 端点
  - `meta/services/deletion_service.py` - 删除服务
  - `src/services/boService.js:338-350` - 前端 deepInsert

### 9.2 Target State

- **Proposed Architecture**:

```
Deep Insert 流程（增强后）:
┌─────────────────────────────────────────────────────────────┐
│ 1. 解析请求                                                  │
│ 2. 开启数据库事务                                            │
│ 3. 创建/更新父对象                                           │
│ 4. 遍历子对象:                                               │
│    - 创建/更新/删除子对象                                     │
│ 5. 执行规则验证                                              │
│ 6. 提交事务（失败则回滚所有操作）                             │
│ 7. 返回结果                                                  │
└─────────────────────────────────────────────────────────────┘
保证：要么全部成功，要么全部回滚！
```

```
多态 Composition 删除流程:
┌─────────────────────────────────────────────────────────────┐
│ 1. 检查对象是否有多态 Composition 配置                       │
│ 2. 查询匹配的子对象 (target_type=X, target_id=Y)            │
│ 3. 判断 async_delete 配置                                    │
│    - 同步: 在同一事务中删除                                   │
│    - 异步: 创建后台任务                                       │
│ 4. 记录审计日志                                              │
└─────────────────────────────────────────────────────────────┘
```

- **Key Changes**:
  - 重构 `DeepInsertEngine` 添加事务支持
  - 扩展 `DeletionService` 添加多态 Composition 反向级联
  - 扩展 `yaml_loader` 解析 cascade_delete 配置
  - 更新前端 `boService` 适配新错误格式

### 9.3 Detailed Design

#### Module/Component Design

```
meta/
├── core/
│   ├── deep_insert_engine.py       # 重构：添加事务支持
│   ├── models.py                   # 扩展：PolymorphicCascadeConfig
│   └── yaml_loader.py              # 扩展：解析 cascade_delete
├── services/
│   └── deletion_service.py         # 扩展：多态 Composition 反向级联
└── api/
    ├── manage_api.py               # 修改：增强错误处理
    └── bo_api.py                   # 修改：同步增强

src/
└── services/
    └── boService.js                # 修改：适配新错误格式
```

#### Data Model

```python
# PolymorphicCascadeConfig - 多态级联配置
@dataclass
class PolymorphicCascadeConfig:
    cascade_delete: bool = False
    async_delete: bool = False      # 默认同步
    batch_size: int = 100           # 异步删除批量大小
```

#### Deep Insert 事务实现

```python
# deep_insert_engine.py 重构
class DeepInsertEngine:
    def execute(self, object_type: str, params: Dict, data_source) -> ActionResult:
        # 获取数据库连接
        conn = data_source.get_connection()
        
        try:
            # 开启事务
            conn.execute("BEGIN TRANSACTION")
            
            # 创建/更新父对象
            parent_result = self._create_or_update_parent(...)
            if not parent_result.success:
                raise TransactionError(parent_result.message)
            
            # 创建/更新子对象
            for child_type, child_list in children_data.items():
                for child_item in child_list:
                    child_result = self._create_or_update_child(...)
                    if not child_result.success:
                        raise TransactionError(child_result.message)
            
            # 提交事务
            conn.execute("COMMIT")
            return ActionResult(success=True, data=result_data)
            
        except TransactionError as e:
            # 回滚事务
            conn.execute("ROLLBACK")
            return ActionResult(
                success=False,
                error_code="TRANSACTION_ROLLBACK",
                message=f"操作失败，已回滚: {e.message}",
                detail=rollback_detail
            )
```

#### 多态 Composition 反向级联删除

```python
# deletion_service.py 扩展
class DeletionService:
    def _execute_polymorphic_cascade(
        self,
        parent_type: str,
        parent_id: int,
        policy
    ) -> List[Dict]:
        """执行多态 Composition 反向级联删除"""
        deleted = []
        
        # 查找所有配置了 cascade_delete 的多态关联
        for child_meta in registry.get_all():
            for assoc in getattr(child_meta, 'associations', []):
                if not self._is_polymorphic_cascade(assoc):
                    continue
                
                # 查询匹配的子对象
                type_field = assoc.polymorphic_type_field
                id_field = assoc.polymorphic_id_field
                
                query = f"""
                    SELECT id FROM {child_meta.table_name}
                    WHERE {type_field} = ? AND {id_field} = ?
                """
                cursor = self.data_source.execute(query, [parent_type, parent_id])
                child_ids = [row[0] for row in cursor.fetchall()]
                
                # 执行删除
                if child_ids:
                    if assoc.async_delete:
                        self._schedule_async_delete(child_meta.table_name, child_ids)
                    else:
                        self._delete_sync(child_meta.table_name, child_ids)
                    
                    deleted.append({
                        'object_type': child_meta.id,
                        'ids': child_ids,
                        'async': assoc.async_delete
                    })
        
        return deleted
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| 事务: 数据库事务 | 简单可靠 | 依赖数据库支持 | Selected |
| 事务: 应用层补偿 | 不依赖数据库 | 复杂，不可靠 | Rejected |
| 删除: 同步 | 简单，一致性好 | 可能阻塞 | 默认 |
| 删除: 异步 | 不阻塞 | 最终一致性 | 可选 |

### 9.5 Implementation & Migration Plan

- **Implementation Order**:
  1. **Day 1**: 
     - 重构 `DeepInsertEngine` 添加事务支持
     - 更新 `manage_api.py` 错误处理
  2. **Day 2**: 
     - 添加多态 Composition 配置模型
     - 扩展 `yaml_loader` 解析配置
  3. **Day 3**: 
     - 扩展 `DeletionService` 反向级联删除
     - 更新 `annotation.yaml` 配置
  4. **Day 4**: 
     - 更新前端 `boService.js`
     - 添加 Deep Update 支持
  5. **Day 5**: 
     - 测试 + 文档

- **Risk Mitigation**:
  - 事务死锁风险 → 使用短事务，避免嵌套
  - 性能风险 → 添加批量操作优化
  - 兼容性风险 → 现有测试全部通过

- **Testing Strategy**:
  - Unit tests:
    - `DeepInsertEngine` 事务回滚测试
    - `DeletionService` 多态级联删除测试
  - Integration tests:
    - Deep Insert 失败回滚测试
    - 多态 Composition 删除测试
  - E2E tests:
    - 完整 Deep Insert 流程测试

- **Rollback Plan**:
  - 恢复原有 `DeepInsertEngine`
  - 移除 cascade_delete 配置
  - 前端恢复原有错误处理

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|---------------------|-----------|
| TBD-1 | 异步删除任务队列 | 是否已有后台任务机制？ | 确认后实现 |
| TBD-2 | Deep Update 业务键匹配 | 如何确定业务键？ | 使用现有 semantics.business_key |

---

## 11. Summary

### 关键发现

1. **Deep Insert API 已实现**，但存在 **无事务回滚** 的关键缺陷
2. **import_cascade 批量导入已实现**，功能比 Deep Insert 更丰富，但同样 **无事务回滚**
3. **两者是互补关系**：import_cascade 适合数据迁移，Deep Insert 适合 API 调用
4. **多态 Composition 未实现**，需要添加 cascade_delete 配置和反向级联删除逻辑
5. **前端已有 deepInsert 方法**，需要适配新的错误响应格式

### 功能对比

| 功能 | 状态 | 事务回滚 | 适用场景 |
|------|------|---------|---------|
| Deep Insert | 🟡 已实现 | ❌ 无 | API 调用、前端表单 |
| import_cascade | 🟡 已实现 | ❌ 无 | 数据迁移、批量导入 |
| 多态 Composition | ❌ 未实现 | - | 数据一致性 |

### 工作量估算

| 功能 | 工作量 | 优先级 |
|------|--------|--------|
| Deep Insert 事务回滚 | 2天 | Must |
| 多态 Composition | 2天 | Must |
| Deep Update 支持 | 1天 | Should |
| import_cascade 事务回滚 | 1天 | Could |
| **总计** | **5-6天** | |

### 影响范围

| 类型 | 受影响数量 |
|------|-----------|
| 后端文件 | 7 个 |
| 前端文件 | 2 个 |
| YAML Schema | 1+ 个 |
| 测试文件 | 4 个 |

### 建议

1. **优先实现 Deep Insert 事务回滚** - 这是 API 调用场景的关键缺陷
2. **实现多态 Composition** - 这是数据一致性的关键
3. **可选实现 import_cascade 事务回滚** - 数据迁移场景的增强

---

> **文档状态**: 待用户确认
> **下一步**: 用户确认后开始实施
