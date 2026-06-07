# 后端元数据驱动模型测试规范

> **目标**: 为后端元数据驱动模型创建完整的测试用例，从底层到API层
>
> **范围**: models → yaml_loader → BOFramework → interceptors → services → API

---

## 一、后端架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                    API层 (api/)                             │
│  bo_api.py, user_api.py, role_api.py, association_api.py  │
├─────────────────────────────────────────────────────────────┤
│                    服务层 (services/)                      │
│  view_config_service, import_export_service, permission_    │
├─────────────────────────────────────────────────────────────┤
│                    拦截器层 (interceptors/)                 │
│  PersistenceInterceptor, QueryInterceptor, CascadeInterceptor  │
├─────────────────────────────────────────────────────────────┤
│                    核心引擎 (core/)                         │
│  BOFramework, QueryBuilder, AssociationEngine              │
├─────────────────────────────────────────────────────────────┤
│                    数据访问层                               │
│  DataSource, SQLAdapters                                 │
├─────────────────────────────────────────────────────────────┤
│                    模型层 (models.py, enums/)              │
│  MetaObject, MetaField, FieldType, ActionContext          │
├─────────────────────────────────────────────────────────────┤
│                    YAML加载层 (yaml_loader.py)              │
│  YAML解析, 元数据注册, 配置验证                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、测试用例清单

### TC-BE-001: 模型层 (models.py)

#### MetaObject测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-01 | 创建基本MetaObject | 验证name,label,table_name | [DONE] |
| TC-BE-001-02 | 创建带associations的MetaObject | 验证associations属性 | [DONE] |
| TC-BE-001-03 | 创建persistent对象 | persistent=True | [DONE] |
| TC-BE-001-04 | 创建非persistent对象 | persistent=False | [DONE] |
| TC-BE-001-05 | 创建带list配置的MetaObject | list配置正确 | [DONE] |
| TC-BE-001-06 | 创建带actions的MetaObject | actions配置正确 | [DONE] |
| TC-BE-001-07 | 创建带import_export的MetaObject | import_export配置 | [DONE] |
| TC-BE-001-08 | 创建带business_key的MetaObject | business_key配置 | [DONE] |
| TC-BE-001-09 | 创建带层级配置的MetaObject | hierarchy配置 | [DONE] |
| TC-BE-001-10 | MetaObject验证-缺少table_name | persistent=True但无table_name | [DONE] |
| TC-BE-001-11 | MetaObject验证-无效name | name包含特殊字符 | [DONE] |
| TC-BE-001-12 | MetaObject验证-重复name | 已有同名对象 | [DONE] |
| TC-BE-001-13 | MetaObject字段访问 | 正确访问字段 | [DONE] |
| TC-BE-001-14 | MetaObject序列化 | to_dict方法 | [DONE] |
| TC-BE-001-15 | MetaObject反序列化 | from_dict方法 | [DONE] |

#### MetaField测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-16 | 创建STRING类型字段 | FieldType.STRING | [DONE] |
| TC-BE-001-17 | 创建INTEGER类型字段 | FieldType.INTEGER | [DONE] |
| TC-BE-001-18 | 创建DATETIME类型字段 | FieldType.DATETIME | [DONE] |
| TC-BE-001-19 | 创建BOOLEAN类型字段 | FieldType.BOOLEAN | [DONE] |
| TC-BE-001-20 | 创建ENUMERATION类型字段 | FieldType.ENUMERATION | [DONE] |
| TC-BE-001-21 | 创建ASSOCIATION类型字段 | FieldType.ASSOCIATION | [DONE] |
| TC-BE-001-22 | 字段required验证 | required=True | [DONE] |
| TC-BE-001-23 | 字段unique验证 | unique=True | [DONE] |
| TC-BE-001-24 | 字段default值 | default配置 | [DONE] |
| TC-BE-001-25 | 字段computed配置 | computed=True | [DONE] |
| TC-BE-001-26 | 字段validation配置 | validation规则 | [DONE] |
| TC-BE-001-27 | 字段ui配置 | visible,editable | [DONE] |
| TC-BE-001-28 | 字段semantics配置 | meaning配置 | [DONE] |
| TC-BE-001-29 | 字段indexes配置 | 索引配置 | [DONE] |
| TC-BE-001-30 | 字段完整配置 | 所有属性配置 | [DONE] |

#### FieldType枚举测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-31 | FieldType值验证 | 所有枚举值正确 | [DONE] |
| TC-BE-001-32 | FieldType.from_string | 字符串转换 | [DONE] |
| TC-BE-001-33 | FieldType.is_numeric | 数值类型判断 | [DONE] |
| TC-BE-001-34 | FieldType.is_text | 文本类型判断 | [DONE] |
| TC-BE-001-35 | FieldType.is_date | 日期类型判断 | [DONE] |

#### ActionContext测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-36 | ActionContext创建 | 基本创建 | [DONE] |
| TC-BE-001-37 | ActionContext设置结果 | set_result方法 | [DONE] |
| TC-BE-001-38 | ActionContext获取结果 | get_result方法 | [DONE] |
| TC-BE-001-39 | ActionContext错误处理 | 设置错误 | [DONE] |
| TC-BE-001-40 | ActionContext序列化 | to_dict方法 | [DONE] |

#### ActionResult测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-41 | ActionResult成功结果 | success=True | [DONE] |
| TC-BE-001-42 | ActionResult错误结果 | success=False | [DONE] |
| TC-BE-001-43 | ActionResult带数据 | data属性 | [DONE] |
| TC-BE-001-44 | ActionResult带消息 | message属性 | [DONE] |
| TC-BE-001-45 | ActionResult带错误详情 | errors属性 | [DONE] |

**models.py 小计**: 45个测试用例

---

## 三、YAML加载层测试 (yaml_loader.py) (40个)

### 文件解析测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-01 | 加载user.yaml | 基本加载 | [DONE] |
| TC-BE-002-02 | 加载role.yaml | 关联加载 | [DONE] |
| TC-BE-002-03 | 加载user_group.yaml | 用户组加载 | [DONE] |
| TC-BE-002-04 | 加载permission.yaml | 权限加载 | [DONE] |
| TC-BE-002-05 | 加载层级对象 | domain/sub_domain加载 | [DONE] |
| TC-BE-002-06 | 加载枚举类型 | enum_type/enum_value | [DONE] |
| TC-BE-002-07 | 加载关系对象 | relationship加载 | [DONE] |
| TC-BE-002-08 | 加载不存在的对象 | 抛出异常 | [DONE] |
| TC-BE-002-09 | 加载损坏的YAML | 抛出异常 | [DONE] |
| TC-BE-002-10 | 加载带中文的YAML | UTF-8编码 | [DONE] |

### 字段定义测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-11 | 字段id映射 | id正确 | [DONE] |
| TC-BE-002-12 | 字段name映射 | name正确 | [DONE] |
| TC-BE-002-13 | 字段type映射 | type转换FieldType | [DONE] |
| TC-BE-002-14 | 字段db_column映射 | db_column正确 | [DONE] |
| TC-BE-002-15 | 字段required映射 | required正确 | [DONE] |
| TC-BE-002-16 | 字段unique映射 | unique正确 | [DONE] |
| TC-BE-002-17 | 字段default映射 | default正确 | [DONE] |
| TC-BE-002-18 | 字段indexes映射 | indexes正确 | [DONE] |
| TC-BE-002-19 | 字段validation映射 | validation正确 | [DONE] |
| TC-BE-002-20 | 字段ui映射 | ui配置正确 | [DONE] |

### 关联定义测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-21 | many_to_many关联 | 中间表配置 | [DONE] |
| TC-BE-002-22 | reference关联 | 外键引用配置 | [DONE] |
| TC-BE-002-23 | composition关联 | 组合关系配置 | [DONE] |
| TC-BE-002-24 | 关联target_object | 目标对象映射 | [DONE] |
| TC-BE-002-25 | 关联actions | 操作配置 | [DONE] |

### 配置解析测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-26 | list配置解析 | title,columns | [DONE] |
| TC-BE-002-27 | list columns解析 | column配置 | [DONE] |
| TC-BE-002-28 | actions配置解析 | CRUD操作 | [DONE] |
| TC-BE-002-29 | batch_actions解析 | 批量操作 | [DONE] |
| TC-BE-002-30 | import_export解析 | 导入导出配置 | [DONE] |
| TC-BE-002-31 | business_key解析 | 业务键配置 | [DONE] |
| TC-BE-002-32 | hierarchy配置解析 | 层级配置 | [DONE] |
| TC-BE-002-33 | parent_key配置解析 | 父级键 | [DONE] |
| TC-BE-002-34 | validation配置解析 | 验证规则 | [DONE] |
| TC-BE-002-35 | semantics配置解析 | 语义配置 | [DONE] |

### Registry测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-36 | Registry单例 | 单例模式 | [DONE] |
| TC-BE-002-37 | Registry.get | 获取对象 | [DONE] |
| TC-BE-002-38 | Registry.list_objects | 列出所有对象 | [DONE] |
| TC-BE-002-39 | Registry.reload | 重新加载 | [DONE] |
| TC-BE-002-40 | Registry清除缓存 | 清除缓存 | [DONE] |

**yaml_loader.py 小计**: 40个测试用例

---

## 四、BOFramework核心测试 (bo_framework.py) (60个)

### 初始化测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-01 | BOFramework初始化 | 基本初始化 | [DONE] |
| TC-BE-003-02 | 注册拦截器 | register_interceptor | [DONE] |
| TC-BE-003-03 | 拦截器优先级 | priority排序 | [DONE] |
| TC-BE-003-04 | 执行空操作 | 无操作处理 | [DONE] |
| TC-BE-003-05 | 执行未知操作 | 未知操作处理 | [DONE] |

### CRUD操作测试 (30个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-06 | 创建user | 基本创建 | [DONE] |
| TC-BE-003-07 | 创建带必填字段 | required字段 | [DONE] |
| TC-BE-003-08 | 创建缺必填字段 | 抛出异常 | [DONE] |
| TC-BE-003-09 | 创建带默认值 | default值 | [DONE] |
| TC-BE-003-10 | 创建自动生成ID | ID自动生成 | [DONE] |
| TC-BE-003-11 | 创建设置created_at | 时间戳 | [DONE] |
| TC-BE-003-12 | 创建设置updated_at | 时间戳 | [DONE] |
| TC-BE-003-13 | 创建重复unique | 抛出异常 | [DONE] |
| TC-BE-003-14 | 创建不存在的对象 | 抛出异常 | [DONE] |
| TC-BE-003-15 | 创建返回结果 | ActionResult | [DONE] |
| TC-BE-003-16 | 读取存在的记录 | 返回数据 | [DONE] |
| TC-BE-003-17 | 读取不存在的记录 | 返回空 | [DONE] |
| TC-BE-003-18 | 读取关联字段 | 关联展开 | [DONE] |
| TC-BE-003-19 | 读取计算字段 | 计算值 | [DONE] |
| TC-BE-003-20 | 读取不存在的对象 | 抛出异常 | [DONE] |
| TC-BE-003-21 | 更新存在的记录 | 更新成功 | [DONE] |
| TC-BE-003-22 | 更新不存在的记录 | 抛出异常 | [DONE] |
| TC-BE-003-23 | 更新设置updated_at | 时间戳更新 | [DONE] |
| TC-BE-003-24 | 更新只读字段 | 抛出异常 | [DONE] |
| TC-BE-003-25 | 更新违反约束 | 抛出异常 | [DONE] |
| TC-BE-003-26 | 部分更新 | 只更新指定字段 | [DONE] |
| TC-BE-003-27 | 更新重复unique | 抛出异常 | [DONE] |
| TC-BE-003-28 | 乐观锁更新 | version字段 | [DONE] |
| TC-BE-003-29 | 更新返回结果 | ActionResult | [DONE] |
| TC-BE-003-30 | 批量更新 | batch_update | [DONE] |
| TC-BE-003-31 | 删除存在的记录 | 删除成功 | [DONE] |
| TC-BE-003-32 | 删除不存在的记录 | 抛出异常 | [DONE] |
| TC-BE-003-33 | 删除级联删除 | 子记录删除 | [DONE] |
| TC-BE-003-34 | 删除软删除 | soft_delete | [DONE] |
| TC-BE-003-35 | 删除硬删除 | hard_delete | [DONE] |

### 过滤器排序分页测试 (25个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-36 | 列出所有记录 | 无过滤 | [DONE] |
| TC-BE-003-37 | 列出分页数据 | page,page_size | [DONE] |
| TC-BE-003-38 | 列出带过滤 | filters | [DONE] |
| TC-BE-003-39 | 列出带排序 | ordering | [DONE] |
| TC-BE-003-40 | 列出升序排序 | ascending | [DONE] |
| TC-BE-003-41 | 列出降序排序 | descending | [DONE] |
| TC-BE-003-42 | 列出多列排序 | multiple | [DONE] |
| TC-BE-003-43 | 列出等于过滤 | equals | [DONE] |
| TC-BE-003-44 | 列出LIKE过滤 | like | [DONE] |
| TC-BE-003-45 | 列出范围过滤 | range | [DONE] |
| TC-BE-003-46 | 列出IN过滤 | in | [DONE] |
| TC-BE-003-47 | 列出NULL过滤 | is_null | [DONE] |
| TC-BE-003-48 | 列出AND组合过滤 | and | [DONE] |
| TC-BE-003-49 | 列出OR组合过滤 | or | [DONE] |
| TC-BE-003-50 | 列出返回总数 | total | [DONE] |
| TC-BE-003-51 | 字符串等于过滤 | string equals | [DONE] |
| TC-BE-003-52 | 字符串LIKE过滤 | string like | [DONE] |
| TC-BE-003-53 | 数字等于过滤 | number equals | [DONE] |
| TC-BE-003-54 | 数字范围过滤 | number range | [DONE] |
| TC-BE-003-55 | 日期等于过滤 | date equals | [DONE] |
| TC-BE-003-56 | 日期范围过滤 | date range | [DONE] |
| TC-BE-003-57 | 枚举过滤 | enum in | [DONE] |
| TC-BE-003-58 | 布尔过滤 | boolean | [DONE] |
| TC-BE-003-59 | 关联过滤 | association | [DONE] |
| TC-BE-003-60 | 复合过滤 | complex | [DONE] |

**bo_framework.py 小计**: 60个测试用例

---

## 五、拦截器层测试 (interceptors/) (50个)

### PersistenceInterceptor测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-01 | create拦截-before | 前置处理 | [DONE] |
| TC-BE-004-02 | create拦截-after | 后置处理 | [DONE] |
| TC-BE-004-03 | update拦截-before | 前置处理 | [DONE] |
| TC-BE-004-04 | update拦截-after | 后置处理 | [DONE] |
| TC-BE-004-05 | delete拦截-before | 前置处理 | [DONE] |
| TC-BE-004-06 | delete拦截-after | 后置处理 | [DONE] |
| TC-BE-004-07 | 设置created_at | 自动时间戳 | [DONE] |
| TC-BE-004-08 | 设置updated_at | 自动时间戳 | [DONE] |
| TC-BE-004-09 | 设置created_by | 自动用户 | [DONE] |
| TC-BE-004-10 | 设置updated_by | 自动用户 | [DONE] |
| TC-BE-004-11 | 生成business_key | 自动生成 | [DONE] |
| TC-BE-004-12 | 版本控制增量 | version++ | [DONE] |
| TC-BE-004-13 | 软删除设置 | deleted_at | [DONE] |
| TC-BE-004-14 | 唯一性检查 | unique验证 | [DONE] |
| TC-BE-004-15 | 必填字段检查 | required验证 | [DONE] |

### QueryInterceptor测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-16 | 添加默认分页 | page,page_size | [DONE] |
| TC-BE-004-17 | 应用filters | 过滤器应用 | [DONE] |
| TC-BE-004-18 | 应用ordering | 排序应用 | [DONE] |
| TC-BE-004-19 | 数据权限过滤 | permission | [DONE] |
| TC-BE-004-20 | 层级过滤 | hierarchy | [DONE] |
| TC-BE-004-21 | 字段权限过滤 | field permission | [DONE] |
| TC-BE-004-22 | 软删除过滤 | deleted过滤 | [DONE] |
| TC-BE-004-23 | SQL注入防护 | injection | [DONE] |
| TC-BE-004-24 | NULL值处理 | null handling | [DONE] |
| TC-BE-004-25 | 结果转换 | result transform | [DONE] |

### CascadeInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-26 | 级联创建 | cascade create | [DONE] |
| TC-BE-004-27 | 级联更新 | cascade update | [DONE] |
| TC-BE-004-28 | 级联删除 | cascade delete | [DONE] |
| TC-BE-004-29 | composition关系 | 父删子删 | [DONE] |
| TC-BE-004-30 | many_to_many关系 | 中间表 | [DONE] |

### AuditInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-31 | 记录create审计 | create日志 | [DONE] |
| TC-BE-004-32 | 记录update审计 | update日志 | [DONE] |
| TC-BE-004-33 | 记录delete审计 | delete日志 | [DONE] |
| TC-BE-004-34 | 审计记录字段变更 | field changes | [DONE] |
| TC-BE-004-35 | 审计记录关联变更 | association changes | [DONE] |

### LockInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-36 | 悲观锁 | pessimistic lock | [DONE] |
| TC-BE-004-37 | 乐观锁 | optimistic lock | [DONE] |
| TC-BE-004-38 | 锁超时 | lock timeout | [DONE] |
| TC-BE-004-39 | 锁释放 | lock release | [DONE] |
| TC-BE-004-40 | 死锁检测 | deadlock | [DONE] |

### DataPermissionInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-41 | 数据权限过滤 | permission filter | [DONE] |
| TC-BE-004-42 | 字段权限过滤 | field permission | [DONE] |
| TC-BE-004-43 | 行级权限 | row permission | [DONE] |
| TC-BE-004-44 | 权限继承 | permission inherit | [DONE] |
| TC-BE-004-45 | 权限缓存 | permission cache | [DONE] |

### 其他拦截器测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-46 | ContextInterceptor | 上下文注入 | [DONE] |
| TC-BE-004-47 | HierarchyValidationInterceptor | 层级验证 | [DONE] |
| TC-BE-004-48 | OwnerAutoPermissionInterceptor | 所有者权限 | [DONE] |
| TC-BE-004-49 | ValidationInterceptor | 验证拦截 | [DONE] |
| TC-BE-004-50 | ExceptionInterceptor | 异常处理 | [DONE] |

**interceptors 小计**: 50个测试用例

---

## 六、AssociationEngine测试 (association_engine.py) (30个)

### 查询关联 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-01 | 查询many_to_many | M2M查询 | [DONE] |
| TC-BE-005-02 | 查询one_to_many | 1NM查询 | [DONE] |
| TC-BE-005-03 | 查询many_to_one | NM1查询 | [DONE] |
| TC-BE-005-04 | 查询reference | 引用查询 | [DONE] |
| TC-BE-005-05 | 查询带过滤 | with filters | [DONE] |
| TC-BE-005-06 | 查询带排序 | with ordering | [DONE] |
| TC-BE-005-07 | 查询带分页 | with pagination | [DONE] |
| TC-BE-005-08 | 查询返回总数 | with total | [DONE] |
| TC-BE-005-09 | 查询不存在的关联 | not found | [DONE] |
| TC-BE-005-10 | 查询递归关联 | recursive | [DONE] |

### 分配关联 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-11 | 分配M2M | many_to_many assign | [DONE] |
| TC-BE-005-12 | 分配检查重复 | duplicate check | [DONE] |
| TC-BE-005-13 | 分配创建中间表 | intermediate table | [DONE] |
| TC-BE-005-14 | 分配不存在的目标 | target not found | [DONE] |
| TC-BE-005-15 | 分配权限检查 | permission check | [DONE] |

### 取消关联 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-16 | 取消M2M | many_to_many dissociate | [DONE] |
| TC-BE-005-17 | 取消不存在的关联 | not found | [DONE] |
| TC-BE-005-18 | 取消删除中间表记录 | intermediate delete | [DONE] |
| TC-BE-005-19 | 取消权限检查 | permission check | [DONE] |
| TC-BE-005-20 | 取消composition | 不允许 | [DONE] |

### 批量操作 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-21 | 批量分配 | batch assign | [DONE] |
| TC-BE-005-22 | 批量取消 | batch dissociate | [DONE] |
| TC-BE-005-23 | 批量分配部分失败 | partial failure | [DONE] |
| TC-BE-005-24 | 批量分配性能 | performance | [DONE] |
| TC-BE-005-25 | 批量分配事务 | transaction | [DONE] |

### 关联计数 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-26 | 计数M2M | count many_to_many | [DONE] |
| TC-BE-005-27 | 计数1NM | count one_to_many | [DONE] |
| TC-BE-005-28 | 计数带过滤 | count with filter | [DONE] |
| TC-BE-005-29 | 计数缓存 | count cache | [DONE] |
| TC-BE-005-30 | 计数性能 | count performance | [DONE] |

**association_engine.py 小计**: 30个测试用例

---

## 七、API层测试 (api/) (50个)

### v2 BO API测试 (20个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-01 | GET /bo/{entity} | 列表API | [DONE] |
| TC-BE-006-02 | GET /bo/{entity} 带分页 | pagination | [DONE] |
| TC-BE-006-03 | GET /bo/{entity} 带过滤 | filters | [DONE] |
| TC-BE-006-04 | GET /bo/{entity} 带排序 | ordering | [DONE] |
| TC-BE-006-05 | GET /bo/{entity}/{id} | 读取API | [DONE] |
| TC-BE-006-06 | POST /bo/{entity} | 创建API | [DONE] |
| TC-BE-006-07 | POST /bo/{entity} 验证 | validation | [DONE] |
| TC-BE-006-08 | PUT /bo/{entity}/{id} | 更新API | [DONE] |
| TC-BE-006-09 | PUT /bo/{entity}/{id} 验证 | validation | [DONE] |
| TC-BE-006-10 | DELETE /bo/{entity}/{id} | 删除API | [DONE] |
| TC-BE-006-11 | GET /bo/{entity} 权限 | permission | [DONE] |
| TC-BE-006-12 | POST /bo/{entity} 权限 | permission | [DONE] |
| TC-BE-006-13 | PUT /bo/{entity}/{id} 权限 | permission | [DONE] |
| TC-BE-006-14 | DELETE /bo/{entity}/{id} 权限 | permission | [DONE] |
| TC-BE-006-15 | GET /bo/{entity} 认证 | auth | [DONE] |
| TC-BE-006-16 | POST /bo/{entity} 认证 | auth | [DONE] |
| TC-BE-006-17 | GET /bo/{entity} 404 | not found | [DONE] |
| TC-BE-006-18 | POST /bo/{entity} 400 | bad request | [DONE] |
| TC-BE-006-19 | PUT /bo/{entity}/{id} 404 | not found | [DONE] |
| TC-BE-006-20 | DELETE /bo/{entity}/{id} 404 | not found | [DONE] |

### Association API测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-21 | GET $associations/{assoc} | 查询关联 | [DONE] |
| TC-BE-006-22 | GET $associations/{assoc} 带过滤 | with filters | [DONE] |
| TC-BE-006-23 | POST $associations/{assoc}/assign | 分配 | [DONE] |
| TC-BE-006-24 | POST $associations/{assoc}/unassign | 取消分配 | [DONE] |
| TC-BE-006-25 | POST $associations/{assoc}/batch_assign | 批量分配 | [DONE] |
| TC-BE-006-26 | POST $associations/{assoc}/batch_unassign | 批量取消 | [DONE] |
| TC-BE-006-27 | GET $associations/{assoc}/count | 计数 | [DONE] |
| TC-BE-006-28 | GET $associations/{assoc}/{target_id} | 目标详情 | [DONE] |
| TC-BE-006-29 | assign权限检查 | permission | [DONE] |
| TC-BE-006-30 | unassign权限检查 | permission | [DONE] |
| TC-BE-006-31 | assign认证检查 | auth | [DONE] |
| TC-BE-006-32 | assign不存在目标 | target not found | [DONE] |
| TC-BE-006-33 | assign重复 | duplicate | [DONE] |
| TC-BE-006-34 | unassign不存在 | not found | [DONE] |
| TC-BE-006-35 | 查询不存在的关联 | not found | [DONE] |

### 导出导入API测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-36 | POST /export | 导出 | [DONE] |
| TC-BE-006-37 | GET /export/download/{file} | 下载 | [DONE] |
| TC-BE-006-38 | GET /import/template/{type} | 下载模板 | [DONE] |
| TC-BE-006-39 | POST /import | 导入 | [DONE] |
| TC-BE-006-40 | POST /import/preview | 导入预览 | [DONE] |
| TC-BE-006-41 | export权限检查 | permission | [DONE] |
| TC-BE-006-42 | import权限检查 | permission | [DONE] |
| TC-BE-006-43 | export不存在对象 | not found | [DONE] |
| TC-BE-006-44 | import无效文件 | invalid file | [DONE] |
| TC-BE-006-45 | import校验失败 | validation failed | [DONE] |

### Schema/Config API测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-46 | GET /schema/{type} | 获取Schema | [DONE] |
| TC-BE-006-47 | GET /ui-config/{type} | 获取UI配置 | [DONE] |
| TC-BE-006-48 | GET /view-config/{type} | 获取视图配置 | [DONE] |
| TC-BE-006-49 | GET /actions/{type} | 获取操作配置 | [DONE] |
| TC-BE-006-50 | GET /meta/{type} | 获取完整元数据 | [DONE] |

**api 小计**: 50个测试用例

---

## 八、视图配置服务测试 (view_config_service.py) (20个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-007-01 | 获取list视图配置 | list_config | [DONE] |
| TC-BE-007-02 | 获取detail视图配置 | detail_config | [DONE] |
| TC-BE-007-03 | 获取form视图配置 | form_config | [DONE] |
| TC-BE-007-04 | 列从YAML加载 | from yaml | [DONE] |
| TC-BE-007-05 | 操作从YAML加载 | from yaml | [DONE] |
| TC-BE-007-06 | CRUD操作自动添加 | auto add | [DONE] |
| TC-BE-007-07 | 批量操作自动添加 | auto add | [DONE] |
| TC-BE-007-08 | 导入导出自动添加 | auto add | [DONE] |
| TC-BE-007-09 | 持久化对象标记 | persistent flag | [DONE] |
| TC-BE-007-10 | 非持久化对象标记 | virtual flag | [DONE] |
| TC-BE-007-11 | 列宽度推断 | width inference | [DONE] |
| TC-BE-007-12 | 列排序 | sort order | [DONE] |
| TC-BE-007-13 | 列可见性 | visibility | [DONE] |
| TC-BE-007-14 | 操作可见性 | visibility | [DONE] |
| TC-BE-007-15 | 操作权限 | permission | [DONE] |
| TC-BE-007-16 | 过滤配置生成 | filter config | [DONE] |
| TC-BE-007-17 | 排序配置生成 | sort config | [DONE] |
| TC-BE-007-18 | 验证配置完整性 | validation | [DONE] |
| TC-BE-007-19 | 缓存配置 | cache | [DONE] |
| TC-BE-007-20 | 配置热重载 | hot reload | [DONE] |

**view_config_service 小计**: 20个测试用例

---

## 九、测试覆盖率目标

| 层级 | 目标覆盖率 | 关键测试点 |
|------|----------|----------|
| 模型层 | 95%+ | 所有模型 |
| YAML加载层 | 95%+ | 解析、注册、验证 |
| BOFramework | 90%+ | CRUD、过滤器、排序、分页 |
| 拦截器层 | 90%+ | 每个拦截器的before/after逻辑 |
| AssociationEngine | 90%+ | M2M、一对多、引用 |
| API层 | 90%+ | 所有端点的成功/失败路径 |

---

## 十、性能测试

### 查询性能基准

| 测试场景 | 目标性能 | 状态 |
|---------|---------|------|
| 列表查询100条记录 | < 100ms | [DONE] |
| 带过滤查询 | < 200ms | [DONE] |
| 关联查询 | < 150ms | [DONE] |
| 分页查询 | < 50ms | [DONE] |

### 并发测试

| 场景 | 并发数 | 目标 | 状态 |
|------|--------|------|------|
| 读操作并发 | 100 | 100%成功 | [DONE] |
| 写操作并发 | 10 | 100%成功 | [DONE] |
| 混合负载 | 50读/10写 | 95%+成功 | [DONE] |

---

## 十一、测试数据管理

### Fixtures清单

| Fixture | 作用域 | 用途 |
|--------|--------|------|
| db_connection | function | 数据库连接 |
| sample_user_data | function | 用户测试数据 |
| sample_role_data | function | 角色测试数据 |
| multiple_users | function | 批量用户数据 |
| user_with_role | function | 用户角色关联 |
| user_in_group | function | 用户组成员 |
| authenticated_client | session | 已认证客户端 |

---

## 十二、Mock和Stub策略

### 外部依赖Mock

| 依赖 | Mock方法 | 状态 |
|------|---------|------|
| email_service | patch | [DONE] |
| audit_writer | patch | [DONE] |
| cache_service | patch | [DONE] |
| notification_service | patch | [DONE] |

---

## 十三、测试用例统计

| 模块 | 测试用例数 | 状态 |
|------|-----------|------|
| models.py | 45 | [DONE] |
| yaml_loader.py | 40 | [DONE] |
| bo_framework.py | 60 | [DONE] |
| interceptors | 50 | [DONE] |
| association_engine | 30 | [DONE] |
| api | 50 | [DONE] |
| view_config_service | 20 | [DONE] |
| **总计** | **295** | [DONE] |

---

## 十四、快速开始

### 运行命令

```bash
# 运行所有测试
cd meta
pytest tests/ -v

# 运行特定模块
pytest tests/test_core_models.py -v
pytest tests/test_yaml_loader.py -v
pytest tests/test_bo_framework.py -v
pytest tests/test_interceptors.py -v
pytest tests/test_api.py -v
pytest tests/test_association_engine.py -v
pytest tests/test_view_config.py -v

# 生成覆盖率报告
pytest tests/ --cov=meta --cov-report=html
```

---

## 十五、测试文件结构

```
meta/tests/
├── conftest.py              # pytest fixtures和配置
├── test_core_models.py      # 模型层测试
├── test_yaml_loader.py       # YAML加载测试
├── test_bo_framework.py     # 核心引擎测试
├── test_interceptors.py       # 拦截器测试
├── test_api.py              # API层测试
├── test_association_engine.py # 关联引擎测试
└── test_view_config.py       # 视图配置测试
```
