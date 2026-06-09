## 目录

1. [一、SAP CAP 的 Deep Authorizations 机制](#一-sap-cap-的-deep-authorizations-机制)
2. [二、SAP CAP 的安全警告](#二-sap-cap-的安全警告)
3. [三、Salesforce 的处理机制](#三-salesforce-的处理机制)
4. [四、对比分析](#四-对比分析)
5. [五、对我们的启示](#五-对我们的启示)
6. [六、最佳实践建议](#六-最佳实践建议)
7. [七、总结](#七-总结)

---
# SAP等企业级产品对部分可见关系的处理机制深度分析

## 一、SAP CAP 的 Deep Authorizations 机制

### 1. 核心概念

SAP CAP (Cloud Application Programming Model) 提供了 **Deep Authorizations** 机制，专门处理关联数据的权限控制。

```
查询请求 → 检查目标实体权限 → 检查所有关联实体权限 → 返回结果
```

### 2. Associations（关联）权限检查

```cds
// CDS 模型定义
@(restrict: [{ grant: 'READ', to: 'Manager' }])
entity Books {...}

@(restrict: [{ grant: 'READ', to: 'Manager' }])
entity Orders {
  key ID: String;
  items: Composition of many {
    key book: Association to Books;
    quantity: Integer;
  }
}
```

**请求示例**：
```
GET Orders(ID='1')/items?$expand=book
```

**权限检查流程**：
1. 检查 `Orders` 实体的 READ 权限
2. 检查 `Books` 实体的 READ 权限（因为是 expand 的目标）
3. 如果 `Books` 有 `where` 条件，会作为过滤条件添加到子查询中

### 3. 关键机制：权限条件传播

```cds
// 实例级权限定义
entity Orders @(restrict: [
  { grant: 'READ', where: (buyer = $user) }
]) {
  items: Composition of many {
    book: Association to Books;
  }
}

entity Books @(restrict: [
  { grant: 'READ', where: (publisher = $user.publisher) }
]) {...}
```

**查询执行时**：
```sql
-- 自动注入权限条件
SELECT * FROM Orders 
WHERE buyer = :current_user

SELECT * FROM Books 
WHERE publisher IN :user_publishers
  AND id IN (SELECT book_id FROM OrderItems WHERE order_id = :order_id)
```

### 4. Exists Predicate（存在谓词）- 关键技术

SAP CAP 使用 `exists` 谓词处理跨实体的权限推导：

```cds
entity Projects @(restrict: [
  { grant: ['READ', 'WRITE'],
    where: (exists members[userId = $user and role = 'Editor']) }
]) {
  members: Association to many Members;
}

@readonly entity Members {
  key userId: User;
  key role: String enum { Viewer; Editor; };
}
```

**含义**：用户可以访问那些自己是 Editor 成员的项目。

### 5. Association Paths（关联路径）

```cds
entity SalesOrders @(restrict: [
  { grant: 'READ',
    where: (product.productType = $user.productType) }
]) {
  product: Association to one Products;
}

entity Products {
  productType: String(32);
}
```

**权限通过关联路径传递**：用户只能看到产品类型匹配的销售订单。

## 二、SAP CAP 的安全警告

### 1. 关联数据泄露风险

SAP 官方文档明确警告：

> "Note that exposed associations (and compositions) can disclose unauthorized data."

**问题场景**：

```cds
entity Employees : cuid {
  name: String;
  team: Association to Teams;
  contract: Composition of Contracts;  // 敏感数据！
}

entity Contracts @(requires:'Manager') : cuid {
  salary: Decimal;  // 只有 Manager 可见
}

service BrowseEmployeesService @(requires:'Employee') {
  @readonly entity Teams as projection on db.Teams;  
  // 问题：Employee 用户可以通过 expand 访问 contract！
}
```

### 2. 解决方案

```cds
service BrowseEmployeesService @(requires:'Employee') {
  @readonly entity Employees
  as projection on db.Employees excluding { contract };  // 隐藏敏感关联！

  @readonly entity Teams as projection on db.Teams;
}
```

**关键点**：通过投影（projection）排除敏感关联，而不是依赖权限检查。

## 三、Salesforce 的处理机制

### 1. 关联记录访问规则

Salesforce 有明确的规则处理父子记录的访问：

```
If you have access to a parent account, you may have access to 
the associated contact, case or opportunity child entities.
```

### 2. 共享传播机制

```
共享一个记录可能会意外共享相关记录：
- 共享 Opportunity 可能会共享其父 Account
- 共享 Case 或 Contact 可能会开放关联的 Account
```

### 3. Master-Detail 关系的权限继承

```
Child objects have their sharing access level and ownership 
dictated by their parent.

子对象没有自己的共享记录，会随主记录一起共享。
```

### 4. 配置控制

Salesforce 提供了 **Related Record Access** 设置来控制这种行为。

## 四、对比分析

### 1. 处理策略对比

| 产品 | 策略 | 实现方式 |
|------|------|---------|
| **SAP CAP** | 权限条件传播 | `where` 条件自动注入到关联查询 |
| **Salesforce** | 共享继承 | 父记录共享自动传播到子记录 |
| **我们的方案** | OR 逻辑 + 脱敏 | 任一端有权限即可见，无权限端脱敏 |

### 2. SAP CAP 的局限性

SAP CAP 文档明确指出：

> "Restrictions of (recursively) expanded or inlined entities of a READ request aren't checked."

```
限制：
- READ 请求的 expand 实体的限制不会被检查
- Deep INSERT 和 UPDATE 只检查根实体
- Composition 的限制不会被运行时检查
```

### 3. 关键差异

| 维度 | SAP CAP | 我们的方案 |
|------|---------|-----------|
| 关系可见性 | 两端都要有权限 | 任一端有权限 |
| 无权限端处理 | 查询被拒绝 | 显示摘要信息 |
| 用户体验 | 可能看不到完整关系 | 能看到关系全貌 |
| 安全性 | 更严格 | 平衡安全与可用性 |

## 五、对我们的启示

### 1. 借鉴 SAP CAP 的技术

#### (1) 权限条件自动注入

```python
# 类似 SAP CAP 的 where 条件注入
def build_query_with_permission(object_type, user_id):
    # 基础查询
    query = f"SELECT * FROM {object_type}"
    
    # 注入权限条件
    permission_filter = get_permission_filter(user_id, object_type)
    if permission_filter:
        query += f" WHERE {permission_filter}"
    
    return query
```

#### (2) Exists 谓词实现

```python
# 类似 SAP CAP 的 exists 谓词
def build_exists_condition(user_id, relation_path):
    """
    构建存在性条件
    
    例如：用户可以访问自己是成员的项目
    where: exists members[userId = $user and role = 'Editor']
    """
    return f"""
        EXISTS (
            SELECT 1 FROM {relation_path.target_table}
            WHERE {relation_path.join_condition}
            AND user_id = {user_id}
            AND role = 'Editor'
        )
    """
```

### 2. 改进我们的方案

#### (1) 关联查询的权限检查

```python
def query_with_expand(base_query, expand_paths, user_id):
    """带 expand 的查询，检查所有关联实体的权限"""
    
    results = execute_query(base_query)
    
    for path in expand_paths:
        # 获取关联实体类型
        related_type = get_related_type(path)
        
        # 检查用户对关联实体的权限
        related_permission = get_permission(user_id, related_type)
        
        if related_permission == 'none':
            # 无权限：隐藏该关联
            for record in results:
                record[path] = None
        elif related_permission == 'read':
            # 只读：应用脱敏
            for record in results:
                record[path] = mask_sensitive_fields(record[path])
        # write/admin: 完整显示
    
    return results
```

#### (2) 投影视图控制

```python
# 类似 SAP CAP 的 projection excluding
class ServiceEntity:
    """服务实体定义"""
    
    def __init__(self, source_entity, excluded_fields=None):
        self.source = source_entity
        self.excluded_fields = excluded_fields or []
    
    def get_projection(self):
        """获取投影定义"""
        all_fields = get_entity_fields(self.source)
        return [f for f in all_fields if f not in self.excluded_fields]

# 使用示例
EmployeeService = ServiceEntity(
    source_entity='Employees',
    excluded_fields=['contract', 'salary']  # 排除敏感关联
)
```

### 3. 综合方案

结合 SAP CAP 和 Salesforce 的优点：

```python
class RelationshipAccessControl:
    """关系访问控制"""
    
    def check_relationship_access(self, user_id, relationship):
        """检查关系访问权限"""
        
        source_perm = self.get_permission(user_id, relationship.source_bo)
        target_perm = self.get_permission(user_id, relationship.target_bo)
        
        # 可见性判定
        if source_perm == 'none' and target_perm == 'none':
            return {'visible': False}
        
        # 构建结果
        result = {
            'visible': True,
            'source': self.process_bo(relationship.source_bo, source_perm),
            'target': self.process_bo(relationship.target_bo, target_perm),
            'can_edit': source_perm in ('write', 'admin') and 
                        target_perm in ('write', 'admin'),
            'can_delete': source_perm == 'admin' and target_perm == 'admin'
        }
        
        return result
    
    def process_bo(self, bo, permission):
        """处理业务对象数据"""
        if permission in ('write', 'admin'):
            return bo  # 完整数据
        elif permission == 'read':
            return self.mask_sensitive(bo)  # 脱敏
        else:
            return self.summary_only(bo)  # 仅摘要
```

## 六、最佳实践建议

### 1. 设计原则

| 原则 | 说明 |
|------|------|
| **最小权限原则** | 默认拒绝，显式授权 |
| **权限分离** | 功能权限与数据权限分离 |
| **透明性** | 用户清楚自己的权限范围 |
| **可追溯** | 权限变更可审计 |

### 2. 实现建议

1. **权限条件注入**：参考 SAP CAP，在查询层自动注入权限条件
2. **投影控制**：通过视图定义控制暴露的字段和关联
3. **脱敏处理**：对无权限数据提供摘要信息
4. **审计日志**：记录权限检查和访问行为

### 3. 安全警告

> **重要**：关联数据可能泄露无权限信息，必须：
> 1. 在服务层定义明确的投影
> 2. 排除敏感关联
> 3. 不要仅依赖运行时权限检查

## 七、总结

### SAP CAP 的核心机制

1. **Deep Authorizations**：查询时检查所有关联实体权限
2. **Where 条件注入**：权限条件自动添加到 SQL
3. **Exists 谓词**：支持跨实体权限推导
4. **投影排除**：通过视图定义隐藏敏感关联

### 我们的方案改进

1. **OR 逻辑**：任一端有权限即可见关系
2. **数据脱敏**：无权限端显示摘要
3. **投影控制**：服务层定义暴露范围
4. **审计追踪**：完整的权限检查日志

### 关键启示

SAP CAP 的文档明确指出：**"Restrictions on compositions are not checked by the runtime"**

这意味着即使是 SAP，也没有完美解决所有关联权限问题。我们的方案通过 **OR 逻辑 + 数据脱敏** 提供了更平衡的解决方案。
