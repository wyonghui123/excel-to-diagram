## 目录

1. [一、问题场景](#一-问题场景)
2. [二、处理策略对比](#二-处理策略对比)
3. [三、推荐方案：策略B（部分显示）](#三-推荐方案：策略b（部分显示）)
4. [四、前端展示处理](#四-前端展示处理)
5. [五、操作权限控制](#五-操作权限控制)
6. [六、数据安全考虑](#六-数据安全考虑)
7. [七、总结](#七-总结)

---
# 部分可见关系的数据处理策略

## 一、问题场景

### 用户权限配置

```
用户A权限：
- 子领域"采购供应" → 编辑权限

自动继承：
├── 服务模块"采购申请" → 编辑权限
├── 服务模块"采购执行" → 编辑权限
├── 业务对象"采购入库" → 编辑权限
└── ...
```

### 关系示例

```
关系：采购入库 → 成本对象

源端：采购入库（采购执行服务模块，采购供应子领域）
    → 用户有权限 ✓

目标端：成本对象（成本核算服务模块，管理会计子领域）
    → 用户无权限 ✗
```

### 问题

1. 关系是否显示？
2. 目标端业务对象信息如何展示？
3. 是否存在数据泄露风险？

## 二、处理策略对比

### 策略A：完全隐藏（保守）

```
规则：两端都有权限才显示关系

优点：
- 数据安全，无泄露风险
- 逻辑简单

缺点：
- 用户可能错过重要关系
- 不符合"OR逻辑"原则
- 数据不完整

示例：
采购入库 → 成本对象：不显示（因为目标端无权限）
```

### 策略B：部分显示（推荐）

```
规则：任一端有权限就显示关系，无权限端显示摘要信息

优点：
- 用户能看到完整的关系网络
- 知道有哪些外部关联
- 平衡安全性和可用性

缺点：
- 实现稍复杂
- 需要定义"摘要信息"的范围

示例：
采购入库 → 成本对象：显示
  - 源端：完整信息（采购入库）
  - 目标端：摘要信息（成本对象 - 管理会计）
```

### 策略C：完全显示（激进）

```
规则：任一端有权限就显示完整关系

优点：
- 数据最完整

缺点：
- 可能泄露无权限数据
- 不推荐

示例：
采购入库 → 成本对象：显示完整信息
  - 可能暴露成本对象的敏感字段
```

## 三、推荐方案：策略B（部分显示）

### 1. 关系可见性级别定义

```python
class RelationshipVisibility(Enum):
    """关系可见性级别"""
    FULL = 'full'        # 两端都有权限
    SOURCE_ONLY = 'source'  # 仅源端有权限
    TARGET_ONLY = 'target'  # 仅目标端有权限
    NONE = 'none'        # 两端都无权限
```

### 2. 数据脱敏规则

```python
# 无权限端的显示规则
MASKED_FIELDS = {
    # 完全隐藏
    'hidden': ['created_by', 'updated_by', 'internal_notes'],
    
    # 部分脱敏
    'masked': ['description'],  # 显示前50字符
    
    # 显示摘要
    'summary': ['id', 'code', 'name', 'service_module_name', 'sub_domain_name']
}

def mask_business_object(bo: dict, permission: str) -> dict:
    """根据权限级别脱敏业务对象数据"""
    
    if permission in ('write', 'admin'):
        # 完全权限，返回完整数据
        return bo
    
    if permission == 'read':
        # 只读权限，隐藏敏感字段
        result = {}
        for key, value in bo.items():
            if key in MASKED_FIELDS['hidden']:
                result[key] = '***'
            elif key in MASKED_FIELDS['masked']:
                result[key] = mask_value(value)
            else:
                result[key] = value
        return result
    
    # 无权限，仅返回摘要
    return {
        'id': bo.get('id'),
        'code': bo.get('code'),
        'name': bo.get('name'),
        'service_module_name': bo.get('service_module_name'),
        'sub_domain_name': bo.get('sub_domain_name'),
        'domain_name': bo.get('domain_name'),
        '_permission': 'none',  # 标记无权限
        '_masked': True  # 标记已脱敏
    }
```

### 3. 关系查询结果处理

```python
def process_relationship_result(relationships: List[dict], user_id: int) -> List[dict]:
    """处理关系查询结果，应用权限和脱敏"""
    
    # 获取用户权限
    allowed_bos = get_allowed_business_objects(user_id)
    
    results = []
    for rel in relationships:
        source_perm = check_permission(rel['source_bo_id'], allowed_bos)
        target_perm = check_permission(rel['target_bo_id'], allowed_bos)
        
        # 确定可见性级别
        if source_perm and target_perm:
            visibility = RelationshipVisibility.FULL
        elif source_perm:
            visibility = RelationshipVisibility.SOURCE_ONLY
        elif target_perm:
            visibility = RelationshipVisibility.TARGET_ONLY
        else:
            continue  # 跳过无权限的关系
        
        # 构建结果
        result = {
            'id': rel['id'],
            'relation_code': rel['relation_code'],
            'relation_name': rel['relation_name'],
            'visibility': visibility.value,
            
            # 源端处理
            'source_bo_id': rel['source_bo_id'],
            'source_bo_code': rel['source_bo_code'],
            'source_bo_name': rel['source_bo_name'],
            'source_permission': source_perm or 'none',
            'source_bo': mask_business_object(rel.get('source_bo_detail', {}), source_perm),
            
            # 目标端处理
            'target_bo_id': rel['target_bo_id'],
            'target_bo_code': rel['target_bo_code'],
            'target_bo_name': rel['target_bo_name'],
            'target_permission': target_perm or 'none',
            'target_bo': mask_business_object(rel.get('target_bo_detail', {}), target_perm),
        }
        
        results.append(result)
    
    return results
```

### 4. API响应示例

#### 完全可见的关系

```json
{
  "id": 1,
  "relation_code": "PROCURE_TO_CONTRACT",
  "relation_name": "采购申请到采购合同",
  "visibility": "full",
  "source_bo": {
    "id": 101,
    "code": "BO_PROC_REQ",
    "name": "采购申请单",
    "service_module_name": "采购申请",
    "sub_domain_name": "采购供应",
    "description": "采购申请单用于...",
    "_permission": "write"
  },
  "target_bo": {
    "id": 102,
    "code": "BO_CONTRACT",
    "name": "采购合同",
    "service_module_name": "采购执行",
    "sub_domain_name": "采购供应",
    "description": "采购合同用于...",
    "_permission": "write"
  }
}
```

#### 部分可见的关系（仅源端有权限）

```json
{
  "id": 2,
  "relation_code": "INBOUND_TO_COST",
  "relation_name": "采购入库到成本对象",
  "visibility": "source",
  "source_bo": {
    "id": 103,
    "code": "BO_INBOUND",
    "name": "采购入库",
    "service_module_name": "采购执行",
    "sub_domain_name": "采购供应",
    "description": "采购入库单用于...",
    "_permission": "write"
  },
  "target_bo": {
    "id": 201,
    "code": "BO_COST_OBJ",
    "name": "成本对象",
    "service_module_name": "成本核算",
    "sub_domain_name": "管理会计",
    "domain_name": "财务云",
    "_permission": "none",
    "_masked": true
  }
}
```

## 四、前端展示处理

### 1. 关系列表展示

```
┌─────────────────────────────────────────────────────────────────┐
│ 关系列表                                                         │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 采购申请单 → 采购合同                                        │ │
│ │ 采购申请 → 采购执行 | 同子领域                               │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 采购入库 → 成本对象 🔒                                       │ │
│ │ 采购执行 → 管理会计 | 跨子领域                               │ │
│ │ ⚠️ 您没有"成本对象"的访问权限，仅显示基本信息                │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 关系详情弹窗

```
┌─────────────────────────────────────────────────────────────────┐
│ 关系详情：采购入库 → 成本对象                              [×]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  源端业务对象                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 编码: BO_INBOUND          名称: 采购入库                 │   │
│  │ 服务模块: 采购执行        子领域: 采购供应               │   │
│  │ 描述: 采购入库单用于记录物料入库信息...                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  目标端业务对象 🔒                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 编码: BO_COST_OBJ         名称: 成本对象                 │   │
│  │ 服务模块: 成本核算        子领域: 管理会计               │   │
│  │ 领域: 财务云                                             │   │
│  │ ─────────────────────────────────────────────────────── │   │
│  │ ⚠️ 您没有此业务对象的访问权限                            │   │
│  │ 如需查看详情，请联系管理员申请权限                       │   │
│  │                                    [申请权限]            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3. AA图中的处理

```
在AA图中显示部分可见关系：

┌──────────────┐                    ┌──────────────┐
│  采购入库    │ ─────────────────→ │  成本对象 🔒 │
│  采购执行    │                    │  管理会计    │
└──────────────┘                    └──────────────┘
       ↑                                   ↑
   完整显示                          仅显示名称和所属
   可点击查看详情                    点击提示无权限
```

## 五、操作权限控制

### 1. 查看权限

| 场景 | 源端权限 | 目标端权限 | 可查看内容 |
|------|---------|-----------|-----------|
| 完全可见 | ✓ | ✓ | 关系详情 + 两端完整信息 |
| 源端可见 | ✓ | ✗ | 关系详情 + 源端完整 + 目标端摘要 |
| 目标端可见 | ✗ | ✓ | 关系详情 + 目标端完整 + 源端摘要 |
| 不可见 | ✗ | ✗ | 不显示 |

### 2. 创建/编辑权限

```python
def can_create_relationship(user_id: int, source_bo_id: int, target_bo_id: int) -> bool:
    """检查用户是否可以创建关系"""
    
    # 必须对两端都有写权限才能创建关系
    source_perm = get_permission_level(user_id, 'business_object', source_bo_id)
    target_perm = get_permission_level(user_id, 'business_object', target_bo_id)
    
    return (source_perm in ('write', 'admin') and 
            target_perm in ('write', 'admin'))

def can_edit_relationship(user_id: int, relationship_id: int) -> bool:
    """检查用户是否可以编辑关系"""
    
    rel = get_relationship(relationship_id)
    
    # 必须对两端都有写权限才能编辑
    return can_create_relationship(user_id, rel.source_bo_id, rel.target_bo_id)

def can_delete_relationship(user_id: int, relationship_id: int) -> bool:
    """检查用户是否可以删除关系"""
    
    rel = get_relationship(relationship_id)
    
    # 必须对两端都有管理权限才能删除
    source_perm = get_permission_level(user_id, 'business_object', rel.source_bo_id)
    target_perm = get_permission_level(user_id, 'business_object', rel.target_bo_id)
    
    return (source_perm == 'admin' and target_perm == 'admin')
```

### 3. 操作权限矩阵

| 操作 | 源端权限 | 目标端权限 | 是否允许 |
|------|---------|-----------|---------|
| 查看关系 | 任一有权限 | 任一有权限 | ✓ |
| 创建关系 | write/admin | write/admin | ✓ |
| 编辑关系 | write/admin | write/admin | ✓ |
| 删除关系 | admin | admin | ✓ |
| 导出关系 | read | read | ✓ |

## 六、数据安全考虑

### 1. 敏感字段保护

```python
# 不同层级的敏感字段定义
SENSITIVE_FIELDS = {
    'business_object': {
        'high': ['cost_amount', 'profit_margin', 'internal_notes'],
        'medium': ['description', 'owner', 'status_reason'],
        'low': ['code', 'name', 'created_at']
    }
}

def get_visible_fields(bo_type: str, permission_level: str) -> List[str]:
    """根据权限级别返回可见字段"""
    
    if permission_level == 'admin':
        return ['*']  # 所有字段
    
    if permission_level == 'write':
        # 排除高敏感字段
        return [f for f in ALL_FIELDS if f not in SENSITIVE_FIELDS[bo_type]['high']]
    
    if permission_level == 'read':
        # 仅显示低敏感字段
        return SENSITIVE_FIELDS[bo_type]['low']
    
    # 无权限，仅显示标识字段
    return ['id', 'code', 'name']
```

### 2. 防止数据推断

```python
# 防止通过关系推断无权限数据
def safe_get_relationship_stats(user_id: int) -> dict:
    """安全地获取关系统计信息"""
    
    # 只统计用户有权限的关系
    allowed_bos = get_allowed_business_objects(user_id)
    
    stats = {
        'total_visible': 0,
        'full_access': 0,
        'partial_access': 0,
        'by_category': {}
    }
    
    # 不暴露无权限数据的统计
    # ...
    
    return stats
```

## 七、总结

### 核心原则

1. **关系可见性**：源端或目标端任一有权限，关系即可见
2. **数据脱敏**：无权限端仅显示摘要信息（编码、名称、所属）
3. **操作控制**：创建/编辑需要两端都有写权限
4. **安全优先**：宁可少显示，不泄露敏感数据

### 实现要点

```python
# 关系查询
WHERE source_bo_id IN (allowed) OR target_bo_id IN (allowed)

# 数据脱敏
if not has_permission(target_bo):
    target_bo = mask_to_summary(target_bo)

# 操作检查
can_edit = has_write_permission(source) and has_write_permission(target)
```

### 用户体验

- 明确提示哪些数据无权限
- 提供权限申请入口
- 在UI上用图标区分完全可见和部分可见
