# 数据权限对核心业务数据读取逻辑的影响分析

## 一、现有数据读取流程

### 1. 列表查询流程

```
前端请求 → manage_api.list_records()
         → HierarchyFilterService.resolve_conditions()  // 解析过滤条件
         → QueryService.search()                         // 执行查询
         → 返回结果
```

### 2. 核心代码分析

```python
# meta/api/manage_api.py
@manage_bp.route('/<object_type>', methods=['GET'])
def list_records(object_type):
    # 1. 获取请求参数
    args_dict = {}
    for key in request.args.keys():
        args_dict[key] = request.args.getlist(key)
    
    # 2. 解析过滤条件（层级过滤）
    conditions = _get_hierarchy_filter_service().resolve_conditions(object_type, args_dict)
    
    # 3. 构建搜索请求
    search_req = SearchRequest(
        object_type=normalized_type,
        conditions=conditions,  # ← 这里是数据权限注入点
        keyword=keyword,
        order_by=order_by,
        page=page,
        page_size=page_size,
    )
    
    # 4. 执行查询
    result = _get_query_service().search(search_req)
    
    return jsonify({...})
```

### 3. 现有过滤条件来源

| 来源 | 说明 | 示例 |
|------|------|------|
| URL参数 | 前端传递的过滤条件 | `?domain_id=1&sub_domain_id=2` |
| 层级过滤 | 自动解析层级关系 | 选择领域后自动过滤子领域 |
| 关键字搜索 | 模糊匹配 | `?keyword=采购` |

## 二、数据权限影响分析

### 1. 需要数据权限控制的场景

| 场景 | 影响范围 | 权限类型 |
|------|---------|---------|
| 列表查询 | 所有对象类型 | 数据权限 |
| 详情查看 | 单条记录 | 数据权限 |
| 数据导出 | 导出范围 | 数据权限 |
| 关系查询 | 关系两端 | 数据权限 |
| 图表生成 | 中心范围 | 数据权限 |

### 2. 数据权限模型

```
用户 ←→ 角色 ←→ 功能权限
  ↓
数据权限
  ↓
资源类型 + 资源ID + 权限级别
```

**示例**：
- 用户A 对 领域1 有 read 权限
- 用户A 对 领域2 有 write 权限
- 用户B 对 子领域3 有 read 权限

### 3. 数据权限过滤逻辑

```python
# 数据权限过滤伪代码
def apply_data_permission(conditions, user, object_type):
    """应用数据权限过滤"""
    
    # 1. 超级管理员跳过
    if is_admin(user):
        return conditions
    
    # 2. 获取用户对该资源类型的数据权限
    data_perms = get_data_permissions(user.id, object_type)
    
    if not data_perms:
        # 无任何数据权限，返回空结果条件
        return [QueryCondition(field='id', operator='in', values=[-1])]
    
    # 3. 根据资源类型构建过滤条件
    if object_type == 'domain':
        # 领域：直接过滤
        allowed_ids = [p.resource_id for p in data_perms]
        conditions.append(QueryCondition(field='id', operator='in', values=allowed_ids))
    
    elif object_type == 'sub_domain':
        # 子领域：通过 domain_id 过滤
        domain_perms = get_data_permissions(user.id, 'domain')
        if domain_perms:
            allowed_domain_ids = [p.resource_id for p in domain_perms]
            conditions.append(QueryCondition(field='domain_id', operator='in', values=allowed_domain_ids))
        # 加上直接授权的子领域
        sub_domain_perms = get_data_permissions(user.id, 'sub_domain')
        if sub_domain_perms:
            allowed_sub_domain_ids = [p.resource_id for p in sub_domain_perms]
            # 需要OR逻辑...
    
    elif object_type == 'business_object':
        # 业务对象：通过层级路径过滤
        # 需要关联查询 domain → sub_domain → service_module → business_object
        ...
    
    return conditions
```

## 三、实现方案对比

### 方案A：在 resolve_conditions 中注入

```python
# meta/services/hierarchy_filter_service.py
def resolve_conditions(self, object_type: str, args_dict: Dict[str, List[str]], 
                      user_info: Optional[Dict] = None) -> List[QueryCondition]:
    conditions = []
    
    # ... 现有的层级过滤逻辑 ...
    
    # 新增：数据权限过滤
    if user_info:
        conditions = self._apply_data_permission(conditions, user_info, object_type)
    
    return conditions
```

**优点**：
- 改动最小
- 与现有过滤逻辑统一

**缺点**：
- 职责耦合（层级过滤 + 数据权限）
- 需要传递 user_info 参数

### 方案B：在 QueryService.search 中注入

```python
# meta/services/query_service.py
def search(self, request: SearchRequest, user_info: Optional[Dict] = None) -> SearchResult:
    # ... 现有逻辑 ...
    
    # 新增：数据权限过滤
    if user_info:
        request.conditions = self._apply_data_permission(
            request.conditions, user_info, request.object_type
        )
    
    # 执行查询...
```

**优点**：
- 集中在查询层
- 对上层透明

**缺点**：
- 需要修改 SearchRequest 或 search 方法签名

### 方案C：独立的数据权限过滤层（推荐）

```python
# meta/services/data_permission_service.py
class DataPermissionService:
    """数据权限服务"""
    
    def __init__(self, data_source):
        self.ds = data_source
    
    def filter_conditions(self, object_type: str, conditions: List[QueryCondition], 
                          user_info: Dict) -> List[QueryCondition]:
        """根据数据权限过滤条件"""
        
        # 超级管理员跳过
        if self._is_admin(user_info):
            return conditions
        
        # 获取用户数据权限
        permissions = self._get_data_permissions(user_info['user_id'], object_type)
        
        if not permissions:
            # 无权限，返回空条件
            return [QueryCondition(field='id', operator='eq', value=-1)]
        
        # 构建权限条件
        permission_conditions = self._build_permission_conditions(object_type, permissions)
        
        # 合并条件
        return conditions + permission_conditions
    
    def _build_permission_conditions(self, object_type: str, permissions: List) -> List[QueryCondition]:
        """构建权限过滤条件"""
        
        if object_type in ('domain', 'domains'):
            return self._build_domain_conditions(permissions)
        elif object_type in ('sub_domain', 'sub_domains'):
            return self._build_sub_domain_conditions(permissions)
        elif object_type in ('service_module', 'service_modules'):
            return self._build_service_module_conditions(permissions)
        elif object_type in ('business_object', 'business_objects'):
            return self._build_business_object_conditions(permissions)
        elif object_type in ('relationship', 'relationships'):
            return self._build_relationship_conditions(permissions)
        
        return []
    
    def _build_domain_conditions(self, permissions):
        """领域权限条件"""
        allowed_ids = [p.resource_id for p in permissions if p.resource_type == 'domain']
        if allowed_ids:
            return [QueryCondition(field='id', operator='in', values=allowed_ids)]
        return []
    
    def _build_sub_domain_conditions(self, permissions):
        """子领域权限条件 - 支持继承"""
        # 直接授权的子领域
        direct_ids = [p.resource_id for p in permissions if p.resource_type == 'sub_domain']
        # 通过领域授权继承的子领域
        domain_ids = [p.resource_id for p in permissions if p.resource_type == 'domain']
        
        conditions = []
        if direct_ids:
            conditions.append(QueryCondition(field='id', operator='in', values=direct_ids))
        if domain_ids:
            conditions.append(QueryCondition(field='domain_id', operator='in', values=domain_ids))
        
        return conditions  # 需要OR合并
    
    # ... 其他资源类型的条件构建 ...
```

**API层调用**：

```python
# meta/api/manage_api.py
@manage_bp.route('/<object_type>', methods=['GET'])
@login_required  # 新增：登录检查
def list_records(object_type):
    # 获取当前用户
    user_info = g.current_user
    
    # 解析过滤条件
    conditions = _get_hierarchy_filter_service().resolve_conditions(object_type, args_dict)
    
    # 新增：应用数据权限
    conditions = _get_data_permission_service().filter_conditions(
        object_type, conditions, user_info
    )
    
    # 执行查询...
```

**优点**：
- 职责清晰，单一职责
- 易于测试和维护
- 对现有代码改动最小

**缺点**：
- 需要新增服务类

## 四、影响范围评估

### 1. 需要修改的文件

| 文件 | 修改内容 | 影响程度 |
|------|---------|---------|
| `manage_api.py` | 添加 `@login_required` 装饰器，调用数据权限服务 | 中 |
| `query_service.py` | 无需修改 | 无 |
| `hierarchy_filter_service.py` | 无需修改 | 无 |
| 新增 `data_permission_service.py` | 数据权限过滤服务 | 新增 |
| 新增 `auth_middleware.py` | 登录检查装饰器 | 新增 |

### 2. 不需要修改的部分

| 模块 | 原因 |
|------|------|
| 前端过滤逻辑 | 数据权限在后端透明处理 |
| 层级过滤服务 | 数据权限是额外条件，不影响现有逻辑 |
| 查询服务 | 条件注入在API层完成 |
| 导出服务 | 复用相同的过滤逻辑 |

### 3. 兼容性考虑

**无登录状态**：
- 方案1：返回空数据（安全）
- 方案2：返回公开数据（需要定义公开范围）
- 方案3：返回错误提示登录

**建议**：生产环境强制登录，开发环境可配置跳过

## 五、实施建议

### 1. 分阶段实施

| 阶段 | 内容 | 工作量 |
|------|------|--------|
| 阶段1 | 登录检查 + 功能权限 | 2天 |
| 阶段2 | 数据权限框架 | 1天 |
| 阶段3 | 各资源类型数据权限 | 2天 |
| 阶段4 | 测试 + 文档 | 1天 |

### 2. 最小改动方案

```python
# 1. 在 manage_api.py 添加装饰器
@manage_bp.route('/<object_type>', methods=['GET'])
@login_required
def list_records(object_type):
    user_info = g.current_user
    
    # 2. 在解析条件后调用数据权限
    conditions = _get_hierarchy_filter_service().resolve_conditions(object_type, args_dict)
    conditions = apply_data_permission(conditions, user_info, object_type)
    
    # 3. 后续逻辑不变
    ...

# 4. 数据权限函数（可后续扩展为服务类）
def apply_data_permission(conditions, user_info, object_type):
    """应用数据权限过滤"""
    if is_admin(user_info):
        return conditions
    
    # TODO: 实现数据权限逻辑
    return conditions
```

## 六、结论

### 影响程度：**中等**

1. **核心查询逻辑不需要修改**：数据权限通过注入额外条件实现
2. **API层需要添加装饰器**：`@login_required`
3. **新增数据权限服务**：独立的服务类，不影响现有代码
4. **前端无需修改**：数据权限对前端透明

### 关键设计原则

1. **透明性**：数据权限过滤对业务代码透明
2. **可配置**：可按环境配置是否启用
3. **可扩展**：支持不同资源类型的权限逻辑
4. **最小改动**：复用现有的条件机制

### 推荐方案

**方案C：独立的数据权限过滤层**

- 职责清晰
- 改动最小
- 易于测试
- 支持渐进式实施
