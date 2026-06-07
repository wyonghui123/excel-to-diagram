# 数据权限继承与关系查询模型设计

## 一、问题分析

### 用户场景

```
用户A 拥有子领域"采购供应"的数据权限

期望：
- 能查询"采购供应"下的所有服务模块
- 能查询"采购供应"下的所有业务对象
- 能查询涉及"采购供应"业务对象的所有关系
```

### 数据层级关系

```
领域 (Domain)
  └── 子领域 (SubDomain) "采购供应"
        ├── 服务模块A "采购申请"
        │     ├── 业务对象A1 "采购申请单"
        │     └── 业务对象A2 "采购订单"
        └── 服务模块B "采购执行"
              ├── 业务对象B1 "采购合同"
              └── 业务对象B2 "供应商"
```

### 关系的特殊性

```
关系 = 源业务对象 → 目标业务对象

示例：
- 采购申请单 → 采购订单 (同子领域内)
- 采购订单 → 采购合同 (同子领域内)
- 采购合同 → 供应商 (同子领域内)
- 采购订单 → 销售订单 (跨子领域)
- 采购合同 → 财务凭证 (跨领域)
```

## 二、权限继承模型

### 1. 向下继承（层级传播）

```
拥有某层级的权限 → 自动拥有该层级下所有子层级的权限

示例：
用户有"采购供应"子领域的数据权限
    ↓ 自动继承
├── 服务模块A "采购申请" ✓
├── 服务模块B "采购执行" ✓
├── 业务对象A1, A2, B1, B2 ✓
```

### 2. 权限级别继承

```
父级权限级别 → 子级权限级别（可降级，不可升级）

示例：
用户对"采购供应"有"编辑"权限
    ↓ 继承
├── 对"采购申请"服务模块有"编辑"权限
├── 对"采购申请单"业务对象有"编辑"权限
```

### 3. 关系权限判定

**核心原则**：关系的访问权限基于两端业务对象的权限

```
关系可见性 = 源端可见 OR 目标端可见

判定逻辑：
1. 用户对源业务对象有权限 → 关系可见
2. 用户对目标业务对象有权限 → 关系可见
3. 两端都有权限 → 关系完全可见
```

## 三、数据模型设计

### 1. 数据权限表结构

```sql
CREATE TABLE data_permissions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    resource_type VARCHAR(50) NOT NULL,  -- domain/sub_domain/service_module/business_object
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(20) NOT NULL, -- read/write/admin
    inherit_to_children BOOLEAN DEFAULT TRUE,  -- 是否继承到子级
    created_at TIMESTAMP
);

-- 唯一约束
CREATE UNIQUE INDEX idx_data_perm_unique ON data_permissions(user_id, resource_type, resource_id);
```

### 2. 权限继承视图

```sql
-- 计算用户的完整权限视图（包含继承的权限）
CREATE VIEW user_effective_permissions AS
WITH RECURSIVE permission_tree AS (
    -- 基础权限（直接授权）
    SELECT 
        dp.user_id,
        dp.resource_type,
        dp.resource_id,
        dp.permission_level,
        dp.inherit_to_children,
        0 as depth
    FROM data_permissions dp
    
    UNION ALL
    
    -- 继承权限（从父级继承）
    SELECT 
        pt.user_id,
        'sub_domain' as resource_type,
        sd.id as resource_id,
        pt.permission_level,
        pt.inherit_to_children,
        pt.depth + 1
    FROM permission_tree pt
    JOIN domains d ON pt.resource_type = 'domain' AND pt.resource_id = d.id
    JOIN sub_domains sd ON sd.domain_id = d.id
    WHERE pt.inherit_to_children = TRUE
    
    UNION ALL
    
    SELECT 
        pt.user_id,
        'service_module' as resource_type,
        sm.id as resource_id,
        pt.permission_level,
        pt.inherit_to_children,
        pt.depth + 1
    FROM permission_tree pt
    JOIN sub_domains sd ON pt.resource_type = 'sub_domain' AND pt.resource_id = sd.id
    JOIN service_modules sm ON sm.sub_domain_id = sd.id
    WHERE pt.inherit_to_children = TRUE
    
    UNION ALL
    
    SELECT 
        pt.user_id,
        'business_object' as resource_type,
        bo.id as resource_id,
        pt.permission_level,
        pt.inherit_to_children,
        pt.depth + 1
    FROM permission_tree pt
    JOIN service_modules sm ON pt.resource_type = 'service_module' AND pt.resource_id = sm.id
    JOIN business_objects bo ON bo.service_module_id = sm.id
    WHERE pt.inherit_to_children = TRUE
)
SELECT DISTINCT ON (user_id, resource_type, resource_id)
    user_id,
    resource_type,
    resource_id,
    permission_level
FROM permission_tree
ORDER BY user_id, resource_type, resource_id, depth;
```

## 四、关系查询权限实现

### 1. 关系查询条件构建

```python
# meta/services/data_permission_service.py

class DataPermissionService:
    
    def get_relationship_filter(self, user_id: int) -> dict:
        """获取用户的关系查询过滤条件"""
        
        # 1. 获取用户有权限的业务对象ID列表
        allowed_bo_ids = self._get_allowed_business_object_ids(user_id)
        
        if not allowed_bo_ids:
            # 无任何权限，返回空条件
            return {'source_bo_id': [-1], 'target_bo_id': [-1]}
        
        # 2. 构建关系过滤条件
        # 关系可见条件：源端在权限内 OR 目标端在权限内
        return {
            'allowed_bo_ids': allowed_bo_ids
        }
    
    def _get_allowed_business_object_ids(self, user_id: int) -> List[int]:
        """获取用户有权限的所有业务对象ID（包含继承）"""
        
        # 查询用户的有效权限
        permissions = self._get_effective_permissions(user_id)
        
        bo_ids = set()
        
        for perm in permissions:
            if perm.resource_type == 'business_object':
                bo_ids.add(perm.resource_id)
            elif perm.resource_type == 'service_module':
                # 查询服务模块下的业务对象
                sm_bos = self._get_business_objects_by_service_module(perm.resource_id)
                bo_ids.update(sm_bos)
            elif perm.resource_type == 'sub_domain':
                # 查询子领域下的业务对象
                sd_bos = self._get_business_objects_by_sub_domain(perm.resource_id)
                bo_ids.update(sd_bos)
            elif perm.resource_type == 'domain':
                # 查询领域下的业务对象
                d_bos = self._get_business_objects_by_domain(perm.resource_id)
                bo_ids.update(d_bos)
        
        return list(bo_ids)
    
    def _get_effective_permissions(self, user_id: int) -> List[DataPermission]:
        """获取用户的有效权限（包含继承）"""
        
        # 直接权限
        direct_perms = self._get_direct_permissions(user_id)
        
        # 继承权限
        inherited_perms = []
        for perm in direct_perms:
            if perm.inherit_to_children:
                inherited_perms.extend(
                    self._get_inherited_permissions(perm)
                )
        
        # 合并去重（保留最高权限级别）
        return self._merge_permissions(direct_perms + inherited_perms)
    
    def _get_inherited_permissions(self, parent_perm: DataPermission) -> List[DataPermission]:
        """获取从父级继承的权限"""
        
        inherited = []
        
        if parent_perm.resource_type == 'domain':
            # 继承到子领域
            sub_domains = self._get_sub_domains_by_domain(parent_perm.resource_id)
            for sd in sub_domains:
                inherited.append(DataPermission(
                    user_id=parent_perm.user_id,
                    resource_type='sub_domain',
                    resource_id=sd.id,
                    permission_level=parent_perm.permission_level,
                    inherited_from=parent_perm.resource_type
                ))
        
        elif parent_perm.resource_type == 'sub_domain':
            # 继承到服务模块
            service_modules = self._get_service_modules_by_sub_domain(parent_perm.resource_id)
            for sm in service_modules:
                inherited.append(DataPermission(
                    user_id=parent_perm.user_id,
                    resource_type='service_module',
                    resource_id=sm.id,
                    permission_level=parent_perm.permission_level,
                    inherited_from=parent_perm.resource_type
                ))
        
        elif parent_perm.resource_type == 'service_module':
            # 继承到业务对象
            business_objects = self._get_business_objects_by_service_module(parent_perm.resource_id)
            for bo in business_objects:
                inherited.append(DataPermission(
                    user_id=parent_perm.user_id,
                    resource_type='business_object',
                    resource_id=bo.id,
                    permission_level=parent_perm.permission_level,
                    inherited_from=parent_perm.resource_type
                ))
        
        return inherited
```

### 2. 关系查询SQL

```python
def build_relationship_query(user_id: int, filters: dict) -> str:
    """构建关系查询SQL"""
    
    # 获取用户有权限的业务对象
    allowed_bo_ids = data_permission_service._get_allowed_business_object_ids(user_id)
    
    if not allowed_bo_ids:
        return "SELECT * FROM relationships WHERE 1=0"  # 无权限
    
    # 构建查询
    # 条件：源端在权限内 OR 目标端在权限内
    sql = f"""
        SELECT r.* 
        FROM relationships r
        WHERE r.source_bo_id IN ({','.join(map(str, allowed_bo_ids))})
           OR r.target_bo_id IN ({','.join(map(str, allowed_bo_ids))})
    """
    
    # 添加其他过滤条件
    if filters.get('relation_code'):
        sql += f" AND r.relation_code = '{filters['relation_code']}'"
    
    return sql
```

### 3. 关系可见性级别

```python
class RelationshipVisibility:
    """关系可见性级别"""
    
    @staticmethod
    def check(relationship, allowed_bo_ids: Set[int]) -> str:
        """
        检查关系的可见性级别
        
        Returns:
            'full': 两端都有权限，完全可见
            'source': 仅源端有权限
            'target': 仅目标端有权限
            'none': 两端都无权限
        """
        source_visible = relationship.source_bo_id in allowed_bo_ids
        target_visible = relationship.target_bo_id in allowed_bo_ids
        
        if source_visible and target_visible:
            return 'full'
        elif source_visible:
            return 'source'
        elif target_visible:
            return 'target'
        else:
            return 'none'
```

## 五、场景示例

### 场景1：用户有子领域权限

```
用户A权限：
- 子领域"采购供应" (read)

自动继承：
- 服务模块"采购申请" (read)
- 服务模块"采购执行" (read)
- 业务对象"采购申请单" (read)
- 业务对象"采购订单" (read)
- 业务对象"采购合同" (read)
- 业务对象"供应商" (read)

关系可见性：
✓ 采购申请单 → 采购订单 (full - 两端都在权限内)
✓ 采购订单 → 采购合同 (full)
✓ 采购合同 → 供应商 (full)
✓ 采购订单 → 销售订单 (source - 仅源端在权限内)
✗ 财务凭证 → 付款单 (none - 两端都不在权限内)
```

### 场景2：用户有跨领域权限

```
用户B权限：
- 子领域"采购供应" (read)
- 子领域"销售服务" (read)

关系可见性：
✓ 采购订单 → 销售订单 (full - 两端都在权限内)
✓ 采购合同 → 供应商 (full)
✓ 销售订单 → 客户 (full)
```

### 场景3：用户仅有服务模块权限

```
用户C权限：
- 服务模块"采购申请" (read)

自动继承：
- 业务对象"采购申请单" (read)
- 业务对象"采购订单" (read)

关系可见性：
✓ 采购申请单 → 采购订单 (full)
✓ 采购订单 → 采购合同 (source - 目标端不在权限内)
✗ 采购合同 → 供应商 (none)
```

## 六、权限配置UI设计

### 数据权限配置界面

```
┌─────────────────────────────────────────────────────────────────┐
│ 数据权限配置 - 用户: 张三                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ☑ 供应链云 (领域)                          [编辑 ▼]           │
│    ├ ☑ 采购供应 (子领域)                    [编辑 ▼]           │
│    │   ├ ☑ 采购申请 (服务模块)              [编辑 ▼]           │
│    │   │   ├ ☑ 采购申请单                   [继承]             │
│    │   │   └ ☑ 采购订单                     [继承]             │
│    │   └ ☑ 采购执行 (服务模块)              [编辑 ▼]           │
│    │       ├ ☑ 采购合同                     [继承]             │
│    │       └ ☑ 供应商                       [继承]             │
│    └ ☐ 销售服务 (子领域)                    [无权限]           │
│                                                                 │
│  [展开全部] [收起全部]                                           │
│                                                                 │
│  说明：勾选表示有权限，[继承]表示从父级继承的权限                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 权限级别说明

| 级别 | 说明 | 业务对象操作 | 关系操作 |
|------|------|-------------|---------|
| 无权限 | 灰色显示 | 不可见 | 不可见相关关系 |
| 只读 | 查看权限 | 可查看 | 可查看相关关系 |
| 编辑 | 创建/修改 | 可创建/修改 | 可创建/修改相关关系 |
| 管理 | 完全控制 | 可删除 | 可删除相关关系 |

## 七、总结

### 核心设计原则

1. **向下继承**：父级权限自动传播到子级
2. **关系端点判定**：关系可见性基于两端业务对象的权限
3. **OR逻辑**：源端或目标端任一有权限，关系即可见

### 实现要点

```python
# 关系查询条件
WHERE source_bo_id IN (allowed_bo_ids) 
   OR target_bo_id IN (allowed_bo_ids)

# allowed_bo_ids = 用户有权限的业务对象 + 继承的业务对象
```

### 权限配置简化

- 用户只需配置高层级权限（如子领域）
- 系统自动计算继承权限
- 支持细粒度覆盖（如单独配置某个业务对象的权限）
