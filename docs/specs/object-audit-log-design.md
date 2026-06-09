## 目录

1. [一、问题分析](#一-问题分析)
2. [二、模型配置设计](#二-模型配置设计)
3. [三、测试框架设计](#三-测试框架设计)
4. [四、实现计划](#四-实现计划)

---
# 对象视角审计日志测试框架设计

> 版本: 1.0
> 日期: 2026-06-02

---

## 一、问题分析

### 1.1 当前 get_object_history 的查询逻辑

```
Layer 1: object_type=X AND object_id=Y     → 对象自身的日志
Layer 2: parent_object_type=X AND parent_object_id=Y → 级联子对象的日志
```

### 1.2 缺失的查询维度

| 维度 | 说明 | 当前是否支持 | 缺失影响 |
|------|------|-------------|---------|
| **关联目标侧日志** | 对象作为 ASSOCIATE 的 target 时 | ❌ 不支持 | 查看角色详情时看不到分配给哪些用户 |
| **关系中的任意一方** | 对象参与 relationship（source/target） | ❌ 不支持 | 查看 BO 详情时看不到与其他 BO 的关系变更 |
| **FK 关联的 many 侧** | 对象是 FK 关联的 many 侧 | ❌ 不支持 | 用户→角色分配时，角色的视角看不到 |
| **模型配置的子对象** | 非级联删除的子对象日志 | ❌ 不支持 | 产品下的版本独立操作日志看不到 |

### 1.3 三层日志模型

```
┌─────────────────────────────────────────────────────────────┐
│               对象视角审计日志 = 三层并集                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: 对象自身日志                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ object_type=X AND object_id=Y                        │   │
│  │ → 包含 CREATE / UPDATE / DELETE / ASSOCIATE 等      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Layer 2: 关联日志                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 2a. FK 关联 — 对象是 target 侧                       │   │
│  │     查询 audit_logs WHERE:                           │   │
│  │       action IN ('ASSOCIATE','DISSOCIATE')            │   │
│  │       AND new_value/old_value JSON 包含 target       │   │
│  │     例: 给用户分配角色 → object_type='user'           │   │
│  │          查看角色的视角需要反向查出这条日志             │   │
│  │                                                      │   │
│  │ 2b. Relationship 关联 — 对象是关系的任意一端          │   │
│  │     查询 audit_logs WHERE:                           │   │
│  │       object_type='relationships'                    │   │
│  │       AND (source_bo_id=Y OR target_bo_id=Y)         │   │
│  │     例: BO_A ↔ BO_B 的关系变更                       │   │
│  │          查看 BO_A 的视角需要查出关系的日志            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Layer 3: 子对象日志（模型配置）                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 3a. 级联删除子对象（已有）                            │   │
│  │     parent_object_type=X AND parent_object_id=Y     │   │
│  │                                                      │   │
│  │ 3b. 模型声明包含的子对象（新增）                       │   │
│  │     例: product 声明 include_children=['version']    │   │
│  │     查询 versions WHERE product_id=Y 的 audit logs  │   │
│  │     但不包含 domain（因为 hierarchy 中 domain 属于    │   │
│  │     version，而非 product 直接子对象）                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、模型配置设计

### 2.1 对象子对象包含配置

```yaml
# meta/schemas/audit_object_perspective.yaml (新增)

object_child_config:
  # 产品线：包含版本的日志
  product:
    include_children:
      - version           # 子对象类型
      - business_object   # 业务对象（跨层级）
    exclude_children:
      - domain            # 领域属于版本级，不直接包含
  
  # 版本：包含领域、子领域、业务对象、关系
  version:
    include_children:
      - domain
    child_chain:           # 链式子对象
      - type: domain
        children:
          - sub_domain
          - business_object
          - relationship
  
  # 用户：包含角色分配日志
  user:
    include_children:
      - user_roles         # FK 关联
    # FK 关联的 target 侧（用户是角色的 target）
    # 当查看角色时，role.associated_from: [user]
  
  # 角色：包含被哪些用户/用户组使用
  role:
    associated_from:
      - user               # 角色分配给哪些用户
      - user_group         # 角色分配给哪些用户组
    include_children:
      - role_permissions
  
  # 业务对象：包含关系日志和备注
  business_object:
    include_children:
      - annotation
    associations:
      - relationships      # 关系中的源/目标
```

### 2.2 子对象查询策略

| 关系类型 | 查询方式 | 示例 |
|---------|---------|------|
| **FK 层级子对象** | `SELECT * FROM <child_table> WHERE <fk_field> = <parent_id>` → 用 child IDs 查 audit_logs | product→versions: versions WHERE product_id=X |
| **FK 关联 target 侧** | `SELECT * FROM audit_logs WHERE action IN (ASSOCIATE,DISSOCIATE) AND new_value LIKE '%target_id%'` | 查看角色的视角查谁分配了这个角色 |
| **Relationship 关联** | `SELECT * FROM audit_logs WHERE object_type='relationships' AND (source_bo_id=X OR target_bo_id=X)` | BO 参与的关系变更 |
| **级联子对象** | `parent_object_type=X AND parent_object_id=Y` | 已有实现 |

---

## 三、测试框架设计

### 3.1 ObjectAuditLogVerifier 类

```python
class ObjectAuditLogVerifier(AuditLogVerifier):
    """
    对象视角审计日志验证器
    
    扩展 AuditLogVerifier，增加：
    1. 三层日志完整性验证
    2. 关联方向验证
    3. 子对象覆盖验证
    """
    
    # 对象子对象配置
    OBJECT_CHILD_CONFIG = {
        'products': {
            'children': ['versions'],
            'child_chain': ['versions.business_objects', 'versions.domains'],
        },
        'versions': {
            'children': ['domains'],
            'child_chain': ['domains.sub_domains', 'domains.business_objects'],
        },
        'users': {
            'associated_to': ['roles', 'user_groups'],  # 对象被哪些实体关联
        },
        'roles': {
            'associated_from': ['users', 'user_groups'],  # 哪些实体关联到此对象
        },
        'business_objects': {
            'associations': ['relationships'],  # 关系中的参与方
            'children': ['annotations'],
        },
    }
    
    def verify_object_perspective(
        self, object_type: str, object_id: Any
    ) -> ObjectPerspectiveResult:
        """
        验证对象视角的审计日志完整性
        
        1. 获取自身日志 → 验证通用内容
        2. 获取关联日志 → 验证关联双方信息
        3. 获取子对象日志 → 验证子对象覆盖
        """
        pass
    
    def get_association_logs(
        self, object_type: str, object_id: Any
    ) -> Tuple[List, List]:
        """
        获取关联日志
        
        返回:
        - as_source: 对象作为 source 的 ASSOCIATE 日志
        - as_target: 对象作为 target 的 ASSOCIATE 日志（反向查找）
        """
        pass
    
    def get_children_object_ids(
        self, object_type: str, object_id: Any
    ) -> Dict[str, List]:
        """
        获取子对象 ID 列表（基于模型配置）
        
        返回: {child_type: [child_ids]}
        """
        pass
    
    def verify_layer_coverage(
        self, object_type: str, object_id: Any,
        own_logs: List, assoc_logs: List, child_logs: List
    ) -> Dict:
        """
        验证三层日志的覆盖完整性
        """
        pass
```

### 3.2 验证维度

| 维度 | 验证内容 | 验证方法 |
|------|---------|---------|
| **Layer 1: 自身日志** | 通用内容验证 | `verifier.verify()` |
| | 操作序列完整性 | `verify_object_history()` |
| | 对象标识存在 | `_verify_object_identity()` |
| **Layer 2: 关联日志** | 作为 source 的 ASSOCIATE | 检查 new_value 包含 target 信息 |
| | 作为 target 的 ASSOCIATE | **反向查询**：搜索以本对象为 target 的日志 |
| | 关系参与方 | 查询 object_type='relationships' |
| | 关联双方信息完整 | {target_type, target_id, target_key, target_display} |
| **Layer 3: 子对象日志** | 级联删除子对象 | parent_object_type/parent_object_id |
| | 模型配置子对象 | 按配置查询子对象 ID 列表 |
| | 子对象覆盖完整性 | 实际子对象 vs 期望子对象 |

### 3.3 测试用例

#### 用例: 用户对象视角

```
TC-OBJ-USER-001: 用户自身日志完整性
  - 创建用户 → 应有 CREATE 日志
  - 更新用户 → 应有 UPDATE 日志
  - 删除用户 → 应有 DELETE 日志（含所有字段 old_value）

TC-OBJ-USER-002: 用户角色关联日志（source 侧）
  - 给用户分配角色 → object_type='user', action='ASSOCIATE', field_name='roles'
  - new_value 包含 {target_type:'role', target_id, target_key, target_display}
  
TC-OBJ-USER-003: 用户被分配到的组（target 侧，反向）
  - 将用户加入用户组 → object_type='user_group', action='ASSOCIATE'
  - 查看用户的视角 → 应能反向查出此关联日志
```

#### 用例: 角色对象视角

```
TC-OBJ-ROLE-001: 角色自身日志完整性
TC-OBJ-ROLE-002: 角色分配给用户（target 侧，反向）
  - 角色分配给用户 → object_type='user', field_name='roles'
  - 查看角色视角 → 需要反向查询：哪些 audit_log 的 new_value JSON 中包含此角色
TC-OBJ-ROLE-003: 角色分配给用户组（target 侧，反向）
```

#### 用例: 产品对象视角

```
TC-OBJ-PRODUCT-001: 产品自身日志完整性
TC-OBJ-PRODUCT-002: 产品子对象覆盖（版本）
  - 配置: product.include_children = ['version']
  - 产品下所有版本的 audit logs 应能被获取
  - 但不包含 domain（domain 属于 version 级）
```

#### 用例: 业务对象视角

```
TC-OBJ-BO-001: 业务对象自身日志完整性
TC-OBJ-BO-002: 业务对象关系参与（source/target）
  - 两个 BO 建立了关系 → object_type='relationships'
  - 查看 source BO 的视角 → 应查出关系日志
  - 查看 target BO 的视角 → 同样应查出
TC-OBJ-BO-003: 业务对象备注
  - 给 BO 添加备注 → object_type='annotations'
  - 查看 BO 的视角 → 应查出备注日志
```

---

## 四、实现计划

### 4.1 新增文件

| 文件 | 说明 |
|------|------|
| `test_helpers/object_audit_verifier.py` | 对象视角审计日志验证器 |
| `meta/schemas/audit_object_perspective.yaml` | 对象子对象包含配置 |
| `test_helpers/scripts/test_object_audit.py` | 对象视角测试脚本 |

### 4.2 增强现有文件

| 文件 | 增强内容 |
|------|---------|
| `audit_service.py` | 新增 `get_association_logs()` — 反向查询关联日志 |
| `audit_service.py` | 新增 `get_object_perspective()` — 三层日志查询 |
| `manage_api.py` | 对象详情 API 使用 `get_object_perspective()` |
