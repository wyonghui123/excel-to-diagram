# 后端测试用例清单

> **总计**: 250+ 测试用例
>
> **创建时间**: 2026-05-10

---

## 一、模型层测试 (50个)

### TC-BE-001: models.py (50个)

#### MetaObject测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-01 | 创建基本MetaObject | 验证name,label,table_name | ✅ 已实现 |
| TC-BE-001-02 | 创建带associations的MetaObject | 验证associations属性 | ✅ 已实现 |
| TC-BE-001-03 | MetaObject验证-缺少table_name | persistent=True但无table_name | ✅ 已实现 |
| TC-BE-001-04 | MetaObject验证-无效name | name包含特殊字符 | ✅ 已实现 |
| TC-BE-001-05 | MetaObject验证-重复name | 已有同名对象 | ✅ 已实现 |
| TC-BE-001-06 | MetaObject字段访问 | 正确访问字段 | ✅ 已实现 |
| TC-BE-001-07 | MetaObject序列化 | to_dict方法 | ✅ 已实现 |
| TC-BE-001-08 | MetaObject反序列化 | from_dict方法 | ✅ 已实现 |

#### MetaField测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-16 | 创建STRING类型字段 | FieldType.STRING | ⬜ |
| TC-BE-001-17 | 创建INTEGER类型字段 | FieldType.INTEGER | ⬜ |
| TC-BE-001-18 | 创建DATETIME类型字段 | FieldType.DATETIME | ⬜ |
| TC-BE-001-19 | 创建BOOLEAN类型字段 | FieldType.BOOLEAN | ⬜ |
| TC-BE-001-20 | 创建ENUMERATION类型字段 | FieldType.ENUMERATION | ⬜ |
| TC-BE-001-21 | 创建ASSOCIATION类型字段 | FieldType.ASSOCIATION | ⬜ |
| TC-BE-001-22 | 字段required验证 | required=True | ⬜ |
| TC-BE-001-23 | 字段unique验证 | unique=True | ⬜ |
| TC-BE-001-24 | 字段default值 | default配置 | ⬜ |
| TC-BE-001-25 | 字段computed配置 | computed=True | ⬜ |
| TC-BE-001-26 | 字段validation配置 | validation规则 | ⬜ |
| TC-BE-001-27 | 字段ui配置 | visible,editable | ⬜ |
| TC-BE-001-28 | 字段semantics配置 | meaning配置 | ⬜ |
| TC-BE-001-29 | 字段indexes配置 | 索引配置 | ⬜ |
| TC-BE-001-30 | 字段完整配置 | 所有属性配置 | ⬜ |

#### FieldType枚举测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-31 | FieldType值验证 | 所有枚举值正确 | ⬜ |
| TC-BE-001-32 | FieldType.from_string | 字符串转换 | ⬜ |
| TC-BE-001-33 | FieldType.is_numeric | 数值类型判断 | ⬜ |
| TC-BE-001-34 | FieldType.is_text | 文本类型判断 | ⬜ |
| TC-BE-001-35 | FieldType.is_date | 日期类型判断 | ⬜ |

#### ActionContext测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-36 | ActionContext创建 | 基本创建 | ⬜ |
| TC-BE-001-37 | ActionContext设置结果 | set_result方法 | ⬜ |
| TC-BE-001-38 | ActionContext获取结果 | get_result方法 | ⬜ |
| TC-BE-001-39 | ActionContext错误处理 | 设置错误 | ⬜ |
| TC-BE-001-40 | ActionContext序列化 | to_dict方法 | ⬜ |

#### ActionResult测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-001-41 | ActionResult成功结果 | success=True | ⬜ |
| TC-BE-001-42 | ActionResult错误结果 | success=False | ⬜ |
| TC-BE-001-43 | ActionResult带数据 | data属性 | ⬜ |
| TC-BE-001-44 | ActionResult带消息 | message属性 | ⬜ |
| TC-BE-001-45 | ActionResult带错误详情 | errors属性 | ⬜ |

**models.py 小计**: 45个测试用例

---

## 二、YAML加载层测试 (40个)

### TC-BE-002: yaml_loader.py (40个)

#### 文件解析测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-01 | 加载user.yaml | 基本加载 | ⬜ |
| TC-BE-002-02 | 加载role.yaml | 关联加载 | ⬜ |
| TC-BE-002-03 | 加载user_group.yaml | 用户组加载 | ⬜ |
| TC-BE-002-04 | 加载permission.yaml | 权限加载 | ⬜ |
| TC-BE-002-05 | 加载层级对象 | domain/sub_domain加载 | ⬜ |
| TC-BE-002-06 | 加载枚举类型 | enum_type/enum_value | ⬜ |
| TC-BE-002-07 | 加载关系对象 | relationship加载 | ⬜ |
| TC-BE-002-08 | 加载不存在的对象 | 抛出异常 | ⬜ |
| TC-BE-002-09 | 加载损坏的YAML | 抛出异常 | ⬜ |
| TC-BE-002-10 | 加载带中文的YAML | UTF-8编码 | ⬜ |

#### 字段定义测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-11 | 字段id映射 | id正确 | ⬜ |
| TC-BE-002-12 | 字段name映射 | name正确 | ⬜ |
| TC-BE-002-13 | 字段type映射 | type转换FieldType | ⬜ |
| TC-BE-002-14 | 字段db_column映射 | db_column正确 | ⬜ |
| TC-BE-002-15 | 字段required映射 | required正确 | ⬜ |
| TC-BE-002-16 | 字段unique映射 | unique正确 | ⬜ |
| TC-BE-002-17 | 字段default映射 | default正确 | ⬜ |
| TC-BE-002-18 | 字段indexes映射 | indexes正确 | ⬜ |
| TC-BE-002-19 | 字段validation映射 | validation正确 | ⬜ |
| TC-BE-002-20 | 字段ui映射 | ui配置正确 | ⬜ |

#### 关联定义测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-21 | many_to_many关联 | 中间表配置 | ⬜ |
| TC-BE-002-22 | reference关联 | 外键引用配置 | ⬜ |
| TC-BE-002-23 | composition关联 | 组合关系配置 | ⬜ |
| TC-BE-002-24 | 关联target_object | 目标对象映射 | ⬜ |
| TC-BE-002-25 | 关联actions | 操作配置 | ⬜ |

#### 配置解析测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-26 | list配置解析 | title,columns | ⬜ |
| TC-BE-002-27 | list columns解析 | column配置 | ⬜ |
| TC-BE-002-28 | actions配置解析 | CRUD操作 | ⬜ |
| TC-BE-002-29 | batch_actions解析 | 批量操作 | ⬜ |
| TC-BE-002-30 | import_export解析 | 导入导出配置 | ⬜ |
| TC-BE-002-31 | business_key解析 | 业务键配置 | ⬜ |
| TC-BE-002-32 | hierarchy配置解析 | 层级配置 | ⬜ |
| TC-BE-002-33 | parent_key配置解析 | 父级键 | ⬜ |
| TC-BE-002-34 | validation配置解析 | 验证规则 | ⬜ |
| TC-BE-002-35 | semantics配置解析 | 语义配置 | ⬜ |

#### Registry测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-002-36 | Registry单例 | 单例模式 | ⬜ |
| TC-BE-002-37 | Registry.get | 获取对象 | ⬜ |
| TC-BE-002-38 | Registry.list_objects | 列出所有对象 | ⬜ |
| TC-BE-002-39 | Registry.reload | 重新加载 | ⬜ |
| TC-BE-002-40 | Registry清除缓存 | 清除缓存 | ⬜ |

**yaml_loader.py 小计**: 40个测试用例

---

## 三、BOFramework核心测试 (60个)

### TC-BE-003: bo_framework.py (60个)

#### 初始化测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-01 | BOFramework初始化 | 基本初始化 | ⬜ |
| TC-BE-003-02 | 注册拦截器 | register_interceptor | ⬜ |
| TC-BE-003-03 | 拦截器优先级 | priority排序 | ⬜ |
| TC-BE-003-04 | 执行空操作 | 无操作处理 | ⬜ |
| TC-BE-003-05 | 执行未知操作 | 未知操作处理 | ⬜ |

#### Create操作测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-06 | 创建user | 基本创建 | ⬜ |
| TC-BE-003-07 | 创建带必填字段 | required字段 | ⬜ |
| TC-BE-003-08 | 创建缺必填字段 | 抛出异常 | ⬜ |
| TC-BE-003-09 | 创建带默认值 | default值 | ⬜ |
| TC-BE-003-10 | 创建自动生成ID | ID自动生成 | ⬜ |
| TC-BE-003-11 | 创建设置created_at | 时间戳 | ⬜ |
| TC-BE-003-12 | 创建设置updated_at | 时间戳 | ⬜ |
| TC-BE-003-13 | 创建重复unique | 抛出异常 | ⬜ |
| TC-BE-003-14 | 创建不存在的对象 | 抛出异常 | ⬜ |
| TC-BE-003-15 | 创建返回结果 | ActionResult | ⬜ |

#### Read操作测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-16 | 读取存在的记录 | 返回数据 | ⬜ |
| TC-BE-003-17 | 读取不存在的记录 | 返回空 | ⬜ |
| TC-BE-003-18 | 读取关联字段 | 关联展开 | ⬜ |
| TC-BE-003-19 | 读取计算字段 | 计算值 | ⬜ |
| TC-BE-003-20 | 读取不存在的对象 | 抛出异常 | ⬜ |

#### Update操作测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-21 | 更新存在的记录 | 更新成功 | ⬜ |
| TC-BE-003-22 | 更新不存在的记录 | 抛出异常 | ⬜ |
| TC-BE-003-23 | 更新设置updated_at | 时间戳更新 | ⬜ |
| TC-BE-003-24 | 更新只读字段 | 抛出异常 | ⬜ |
| TC-BE-003-25 | 更新违反约束 | 抛出异常 | ⬜ |
| TC-BE-003-26 | 部分更新 | 只更新指定字段 | ⬜ |
| TC-BE-003-27 | 更新重复unique | 抛出异常 | ⬜ |
| TC-BE-003-28 | 乐观锁更新 | version字段 | ⬜ |
| TC-BE-003-29 | 更新返回结果 | ActionResult | ⬜ |
| TC-BE-003-30 | 批量更新 | batch_update | ⬜ |

#### Delete操作测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-31 | 删除存在的记录 | 删除成功 | ⬜ |
| TC-BE-003-32 | 删除不存在的记录 | 抛出异常 | ⬜ |
| TC-BE-003-33 | 删除级联删除 | 子记录删除 | ⬜ |
| TC-BE-003-34 | 删除软删除 | soft_delete | ⬜ |
| TC-BE-003-35 | 删除硬删除 | hard_delete | ⬜ |

#### List操作测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-36 | 列出所有记录 | 无过滤 | ⬜ |
| TC-BE-003-37 | 列出分页数据 | page,page_size | ⬜ |
| TC-BE-003-38 | 列出带过滤 | filters | ⬜ |
| TC-BE-003-39 | 列出带排序 | ordering | ⬜ |
| TC-BE-003-40 | 列出升序排序 | ascending | ⬜ |
| TC-BE-003-41 | 列出降序排序 | descending | ⬜ |
| TC-BE-003-42 | 列出多列排序 | multiple | ⬜ |
| TC-BE-003-43 | 列出等于过滤 | equals | ⬜ |
| TC-BE-003-44 | 列出LIKE过滤 | like | ⬜ |
| TC-BE-003-45 | 列出范围过滤 | range | ⬜ |
| TC-BE-003-46 | 列出IN过滤 | in | ⬜ |
| TC-BE-003-47 | 列出NULL过滤 | is_null | ⬜ |
| TC-BE-003-48 | 列出AND组合过滤 | and | ⬜ |
| TC-BE-003-49 | 列出OR组合过滤 | or | ⬜ |
| TC-BE-003-50 | 列出返回总数 | total | ⬜ |

#### 过滤器测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-003-51 | 字符串等于过滤 | string equals | ⬜ |
| TC-BE-003-52 | 字符串LIKE过滤 | string like | ⬜ |
| TC-BE-003-53 | 数字等于过滤 | number equals | ⬜ |
| TC-BE-003-54 | 数字范围过滤 | number range | ⬜ |
| TC-BE-003-55 | 日期等于过滤 | date equals | ⬜ |
| TC-BE-003-56 | 日期范围过滤 | date range | ⬜ |
| TC-BE-003-57 | 枚举过滤 | enum in | ⬜ |
| TC-BE-003-58 | 布尔过滤 | boolean | ⬜ |
| TC-BE-003-59 | 关联过滤 | association | ⬜ |
| TC-BE-003-60 | 复合过滤 | complex | ⬜ |

**bo_framework.py 小计**: 60个测试用例

---

## 四、拦截器层测试 (50个)

### TC-BE-004: interceptors/ (50个)

#### PersistenceInterceptor测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-01 | create拦截-before | 前置处理 | ⬜ |
| TC-BE-004-02 | create拦截-after | 后置处理 | ⬜ |
| TC-BE-004-03 | update拦截-before | 前置处理 | ⬜ |
| TC-BE-004-04 | update拦截-after | 后置处理 | ⬜ |
| TC-BE-004-05 | delete拦截-before | 前置处理 | ⬜ |
| TC-BE-004-06 | delete拦截-after | 后置处理 | ⬜ |
| TC-BE-004-07 | 设置created_at | 自动时间戳 | ⬜ |
| TC-BE-004-08 | 设置updated_at | 自动时间戳 | ⬜ |
| TC-BE-004-09 | 设置created_by | 自动用户 | ⬜ |
| TC-BE-004-10 | 设置updated_by | 自动用户 | ⬜ |
| TC-BE-004-11 | 生成business_key | 自动生成 | ⬜ |
| TC-BE-004-12 | 版本控制增量 | version++ | ⬜ |
| TC-BE-004-13 | 软删除设置 | deleted_at | ⬜ |
| TC-BE-004-14 | 唯一性检查 | unique验证 | ⬜ |
| TC-BE-004-15 | 必填字段检查 | required验证 | ⬜ |

#### QueryInterceptor测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-16 | 添加默认分页 | page,page_size | ⬜ |
| TC-BE-004-17 | 应用filters | 过滤器应用 | ⬜ |
| TC-BE-004-18 | 应用ordering | 排序应用 | ⬜ |
| TC-BE-004-19 | 数据权限过滤 | permission | ⬜ |
| TC-BE-004-20 | 层级过滤 | hierarchy | ⬜ |
| TC-BE-004-21 | 字段权限过滤 | field permission | ⬜ |
| TC-BE-004-22 | 软删除过滤 | deleted过滤 | ⬜ |
| TC-BE-004-23 | SQL注入防护 | injection | ⬜ |
| TC-BE-004-24 | NULL值处理 | null handling | ⬜ |
| TC-BE-004-25 | 结果转换 | result transform | ⬜ |

#### CascadeInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-26 | 级联创建 | cascade create | ⬜ |
| TC-BE-004-27 | 级联更新 | cascade update | ⬜ |
| TC-BE-004-28 | 级联删除 | cascade delete | ⬜ |
| TC-BE-004-29 | composition关系 | 父删子删 | ⬜ |
| TC-BE-004-30 | many_to_many关系 | 中间表 | ⬜ |

#### AuditInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-31 | 记录create审计 | create日志 | ⬜ |
| TC-BE-004-32 | 记录update审计 | update日志 | ⬜ |
| TC-BE-004-33 | 记录delete审计 | delete日志 | ⬜ |
| TC-BE-004-34 | 审计记录字段变更 | field changes | ⬜ |
| TC-BE-004-35 | 审计记录关联变更 | association changes | ⬜ |

#### LockInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-36 | 悲观锁 | pessimistic lock | ⬜ |
| TC-BE-004-37 | 乐观锁 | optimistic lock | ⬜ |
| TC-BE-004-38 | 锁超时 | lock timeout | ⬜ |
| TC-BE-004-39 | 锁释放 | lock release | ⬜ |
| TC-BE-004-40 | 死锁检测 | deadlock | ⬜ |

#### DataPermissionInterceptor测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-41 | 数据权限过滤 | permission filter | ⬜ |
| TC-BE-004-42 | 字段权限过滤 | field permission | ⬜ |
| TC-BE-004-43 | 行级权限 | row permission | ⬜ |
| TC-BE-004-44 | 权限继承 | permission inherit | ⬜ |
| TC-BE-004-45 | 权限缓存 | permission cache | ⬜ |

#### 其他拦截器测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-004-46 | ContextInterceptor | 上下文注入 | ⬜ |
| TC-BE-004-47 | HierarchyValidationInterceptor | 层级验证 | ⬜ |
| TC-BE-004-48 | OwnerAutoPermissionInterceptor | 所有者权限 | ⬜ |
| TC-BE-004-49 | ValidationInterceptor | 验证拦截 | ⬜ |
| TC-BE-004-50 | ExceptionInterceptor | 异常处理 | ⬜ |

**interceptors 小计**: 50个测试用例

---

## 五、AssociationEngine测试 (30个)

### TC-BE-005: association_engine.py (30个)

#### 查询关联 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-01 | 查询many_to_many | M2M查询 | ⬜ |
| TC-BE-005-02 | 查询one_to_many | 1NM查询 | ⬜ |
| TC-BE-005-03 | 查询many_to_one | NM1查询 | ⬜ |
| TC-BE-005-04 | 查询reference | 引用查询 | ⬜ |
| TC-BE-005-05 | 查询带过滤 | with filters | ⬜ |
| TC-BE-005-06 | 查询带排序 | with ordering | ⬜ |
| TC-BE-005-07 | 查询带分页 | with pagination | ⬜ |
| TC-BE-005-08 | 查询返回总数 | with total | ⬜ |
| TC-BE-005-09 | 查询不存在的关联 | not found | ⬜ |
| TC-BE-005-10 | 查询递归关联 | recursive | ⬜ |

#### 分配关联 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-11 | 分配M2M | many_to_many assign | ⬜ |
| TC-BE-005-12 | 分配检查重复 | duplicate check | ⬜ |
| TC-BE-005-13 | 分配创建中间表 | intermediate table | ⬜ |
| TC-BE-005-14 | 分配不存在的目标 | target not found | ⬜ |
| TC-BE-005-15 | 分配权限检查 | permission check | ⬜ |

#### 取消关联 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-16 | 取消M2M | many_to_many dissociate | ⬜ |
| TC-BE-005-17 | 取消不存在的关联 | not found | ⬜ |
| TC-BE-005-18 | 取消删除中间表记录 | intermediate delete | ⬜ |
| TC-BE-005-19 | 取消权限检查 | permission check | ⬜ |
| TC-BE-005-20 | 取消composition | 不允许 | ⬜ |

#### 批量操作 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-21 | 批量分配 | batch assign | ⬜ |
| TC-BE-005-22 | 批量取消 | batch dissociate | ⬜ |
| TC-BE-005-23 | 批量分配部分失败 | partial failure | ⬜ |
| TC-BE-005-24 | 批量分配性能 | performance | ⬜ |
| TC-BE-005-25 | 批量分配事务 | transaction | ⬜ |

#### 关联计数 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-005-26 | 计数M2M | count many_to_many | ⬜ |
| TC-BE-005-27 | 计数1NM | count one_to_many | ⬜ |
| TC-BE-005-28 | 计数带过滤 | count with filter | ⬜ |
| TC-BE-005-29 | 计数缓存 | count cache | ⬜ |
| TC-BE-005-30 | 计数性能 | count performance | ⬜ |

**association_engine.py 小计**: 30个测试用例

---

## 六、API层测试 (50个)

### TC-BE-006: api/ (50个)

#### v2 BO API测试 (20个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-01 | GET /bo/{entity} | 列表API | ⬜ |
| TC-BE-006-02 | GET /bo/{entity} 带分页 | pagination | ⬜ |
| TC-BE-006-03 | GET /bo/{entity} 带过滤 | filters | ⬜ |
| TC-BE-006-04 | GET /bo/{entity} 带排序 | ordering | ⬜ |
| TC-BE-006-05 | GET /bo/{entity}/{id} | 读取API | ⬜ |
| TC-BE-006-06 | POST /bo/{entity} | 创建API | ⬜ |
| TC-BE-006-07 | POST /bo/{entity} 验证 | validation | ⬜ |
| TC-BE-006-08 | PUT /bo/{entity}/{id} | 更新API | ⬜ |
| TC-BE-006-09 | PUT /bo/{entity}/{id} 验证 | validation | ⬜ |
| TC-BE-006-10 | DELETE /bo/{entity}/{id} | 删除API | ⬜ |
| TC-BE-006-11 | GET /bo/{entity} 权限 | permission | ⬜ |
| TC-BE-006-12 | POST /bo/{entity} 权限 | permission | ⬜ |
| TC-BE-006-13 | PUT /bo/{entity}/{id} 权限 | permission | ⬜ |
| TC-BE-006-14 | DELETE /bo/{entity}/{id} 权限 | permission | ⬜ |
| TC-BE-006-15 | GET /bo/{entity} 认证 | auth | ⬜ |
| TC-BE-006-16 | POST /bo/{entity} 认证 | auth | ⬜ |
| TC-BE-006-17 | GET /bo/{entity} 404 | not found | ⬜ |
| TC-BE-006-18 | POST /bo/{entity} 400 | bad request | ⬜ |
| TC-BE-006-19 | PUT /bo/{entity}/{id} 404 | not found | ⬜ |
| TC-BE-006-20 | DELETE /bo/{entity}/{id} 404 | not found | ⬜ |

#### Association API测试 (15个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-21 | GET $associations/{assoc} | 查询关联 | ⬜ |
| TC-BE-006-22 | GET $associations/{assoc} 带过滤 | with filters | ⬜ |
| TC-BE-006-23 | POST $associations/{assoc}/assign | 分配 | ⬜ |
| TC-BE-006-24 | POST $associations/{assoc}/unassign | 取消分配 | ⬜ |
| TC-BE-006-25 | POST $associations/{assoc}/batch_assign | 批量分配 | ⬜ |
| TC-BE-006-26 | POST $associations/{assoc}/batch_unassign | 批量取消 | ⬜ |
| TC-BE-006-27 | GET $associations/{assoc}/count | 计数 | ⬜ |
| TC-BE-006-28 | GET $associations/{assoc}/{target_id} | 目标详情 | ⬜ |
| TC-BE-006-29 | assign权限检查 | permission | ⬜ |
| TC-BE-006-30 | unassign权限检查 | permission | ⬜ |
| TC-BE-006-31 | assign认证检查 | auth | ⬜ |
| TC-BE-006-32 | assign不存在目标 | target not found | ⬜ |
| TC-BE-006-33 | assign重复 | duplicate | ⬜ |
| TC-BE-006-34 | unassign不存在 | not found | ⬜ |
| TC-BE-006-35 | 查询不存在的关联 | not found | ⬜ |

#### 导出导入API测试 (10个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-36 | POST /export | 导出 | ⬜ |
| TC-BE-006-37 | GET /export/download/{file} | 下载 | ⬜ |
| TC-BE-006-38 | GET /import/template/{type} | 下载模板 | ⬜ |
| TC-BE-006-39 | POST /import | 导入 | ⬜ |
| TC-BE-006-40 | POST /import/preview | 导入预览 | ⬜ |
| TC-BE-006-41 | export权限检查 | permission | ⬜ |
| TC-BE-006-42 | import权限检查 | permission | ⬜ |
| TC-BE-006-43 | export不存在对象 | not found | ⬜ |
| TC-BE-006-44 | import无效文件 | invalid file | ⬜ |
| TC-BE-006-45 | import校验失败 | validation failed | ⬜ |

#### Schema/Config API测试 (5个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-006-46 | GET /schema/{type} | 获取Schema | ⬜ |
| TC-BE-006-47 | GET /ui-config/{type} | 获取UI配置 | ⬜ |
| TC-BE-006-48 | GET /view-config/{type} | 获取视图配置 | ⬜ |
| TC-BE-006-49 | GET /actions/{type} | 获取操作配置 | ⬜ |
| TC-BE-006-50 | GET /meta/{type} | 获取完整元数据 | ⬜ |

**api 小计**: 50个测试用例

---

## 七、视图配置服务测试 (20个)

### TC-BE-007: view_config_service.py (20个)

| ID | 用例名称 | 测试点 | 状态 |
|----|---------|--------|------|
| TC-BE-007-01 | 获取list视图配置 | list_config | ⬜ |
| TC-BE-007-02 | 获取detail视图配置 | detail_config | ⬜ |
| TC-BE-007-03 | 获取form视图配置 | form_config | ⬜ |
| TC-BE-007-04 | 列从YAML加载 | from yaml | ⬜ |
| TC-BE-007-05 | 操作从YAML加载 | from yaml | ⬜ |
| TC-BE-007-06 | CRUD操作自动添加 | auto add | ⬜ |
| TC-BE-007-07 | 批量操作自动添加 | auto add | ⬜ |
| TC-BE-007-08 | 导入导出自动添加 | auto add | ⬜ |
| TC-BE-007-09 | 持久化对象标记 | persistent flag | ⬜ |
| TC-BE-007-10 | 非持久化对象标记 | virtual flag | ⬜ |
| TC-BE-007-11 | 列宽度推断 | width inference | ⬜ |
| TC-BE-007-12 | 列排序 | sort order | ⬜ |
| TC-BE-007-13 | 列可见性 | visibility | ⬜ |
| TC-BE-007-14 | 操作可见性 | visibility | ⬜ |
| TC-BE-007-15 | 操作权限 | permission | ⬜ |
| TC-BE-007-16 | 过滤配置生成 | filter config | ⬜ |
| TC-BE-007-17 | 排序配置生成 | sort config | ⬜ |
| TC-BE-007-18 | 验证配置完整性 | validation | ⬜ |
| TC-BE-007-19 | 缓存配置 | cache | ⬜ |
| TC-BE-007-20 | 配置热重载 | hot reload | ⬜ |

**view_config_service 小计**: 20个测试用例

---

## 测试用例统计

| 模块 | 测试用例数 | 状态 |
|------|-----------|------|
| models.py | 45 | ⬜ |
| yaml_loader.py | 40 | ⬜ |
| bo_framework.py | 60 | ⬜ |
| interceptors | 50 | ⬜ |
| association_engine | 30 | ⬜ |
| api | 50 | ⬜ |
| view_config_service | 20 | ⬜ |
| **总计** | **295** | ⬜ |

---

## 优先级

### P0 (核心功能)
- BOFramework CRUD操作
- QueryInterceptor过滤器/排序/分页
- PersistenceInterceptor创建/更新/删除
- v2 BO API端点

### P1 (重要功能)
- AssociationEngine关联操作
- AuditInterceptor审计日志
- DataPermissionInterceptor数据权限
- 导出导入API

### P2 (优化功能)
- LockInterceptor锁机制
- CascadeInterceptor级联操作
- 其他拦截器
- Schema/Config API
