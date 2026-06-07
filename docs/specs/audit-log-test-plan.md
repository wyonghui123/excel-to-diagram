# 审计日志自动化测试用例设计方案

> 版本: 1.0
> 日期: 2026-06-02
> 状态: Draft

---

## 一、测试范围

### 1.1 测试对象

| 实体类型 | 层级 | 业务键 | 显示名称 | 主要外键 |
|---------|------|--------|---------|---------|
| 用户 (users) | 0 | username | display_name | - |
| 角色 (roles) | 0 | code | name | - |
| 用户组 (user_groups) | 0 | code | name | parent_id, manager_id |
| 产品 (products) | 1 | code | name | owner_id |
| 版本 (versions) | 2 | code | name | product_id, owner_id |
| 领域 (domains) | 3 | code | name | version_id, owner_id |
| 业务对象 (business_objects) | 6 | code | name | service_module_id, owner_id |
| 关系 (relationships) | 7 | code | relation_desc | source_bo_id, target_bo_id |
| 备注 (annotations) | - | - | category+content | target_type, target_id |

### 1.2 消费场景

| 场景 | 说明 | 覆盖操作 |
|------|------|---------|
| **UI 操作** | 通过前端界面的 CRUD 操作 | CREATE, UPDATE, DELETE |
| **API 操作** | 通过 REST API 的 CRUD 操作 | CREATE, UPDATE, DELETE |
| **Import** | Excel 批量导入 | BULK_CREATE |
| **Export** | Excel 导出 | READ_OBJECT |

### 1.3 验证维度

#### 通用内容验证

| 维度 | 验证点 | 期望 |
|------|--------|------|
| **对象标识** | object_key / object_display_name | extra_data 中包含 `audit_object_key` 和 `audit_object_display_name` |
| **对象类型** | object_type | 与操作对象类型一致 |
| **对象 ID** | object_id | 被操作对象的技术主键 |
| **操作人** | user_id, user_name | 触发操作的用户信息 |
| **时间戳** | created_at | ISO 格式时间 |
| **追踪 ID** | trace_id | 链路追踪 ID（如果有） |
| **事务 ID** | transaction_id | 同一事务的多条日志共享 |

#### 特定 Action 验证

| Action | 验证点 | 期望 |
|--------|--------|------|
| **CREATE** | field_name | 业务字段名 |
| | new_value | 有值（创建时的字段值） |
| | old_value | 空 |
| **UPDATE** | field_name | 变更的字段名 |
| | old_value | 变更前的值 |
| | new_value | 变更后的值 |
| | value_changed | old_value ≠ new_value |
| **DELETE** | field_name | 业务字段名 |
| | old_value | 删除前的值 |
| | new_value | 空 |
| | no_system_fields | 不记录系统字段（id, created_at 等） |
| **ASSOCIATE** | field_name | 关联字段名 |
| | new_value | JSON: {target_type, target_id, target_key, target_display} |
| **DISSOCIATE** | field_name | 关联字段名 |
| | old_value | JSON: {target_type, target_id, target_key, target_display} |
| **FK 字段** | value format | 结构化 JSON（如果实现了 FK 结构化） |

---

## 二、测试用例设计

### 2.1 通用内容验证测试用例

#### TC-AUDIT-001: 验证对象标识存在

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-AUDIT-001 |
| **用例名称** | 验证审计日志包含对象标识 |
| **测试目的** | 确保审计日志记录了对象的业务 key 和显示名称 |
| **前置条件** | 系统正常运行，审计日志功能启用 |
| **测试步骤** | 1. 创建/更新/删除任意实体<br>2. 查询审计日志<br>3. 检查 extra_data 字段 |
| **期望结果** | extra_data 中包含 `audit_object_key` 和 `audit_object_display_name` |
| **测试数据** | products 表任意记录 |
| **验证方法** | `verifier.verify_object_identity(log)` |
| **优先级** | Should |

#### TC-AUDIT-002: 验证通用必需字段

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-AUDIT-002 |
| **用例名称** | 验证审计日志包含所有通用必需字段 |
| **测试目的** | 确保每条审计日志都包含必需的标识信息 |
| **前置条件** | 系统正常运行 |
| **测试步骤** | 对所有实体执行 CRUD 操作，检查每条日志 |
| **期望结果** | 每条日志包含：object_type, object_id, action, user_id, created_at |
| **验证方法** | `verifier.verify(log)` 检查 result.errors |
| **优先级** | Must |

#### TC-AUDIT-003: 验证时间戳格式

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-AUDIT-003 |
| **用例名称** | 验证 created_at 格式正确 |
| **测试目的** | 确保时间戳可被正确解析 |
| **前置条件** | 系统正常运行 |
| **测试步骤** | 执行任意操作，检查 created_at 字段 |
| **期望结果** | created_at 为 ISO 8601 格式 |
| **验证方法** | `datetime.fromisoformat(created_at)` |
| **优先级** | Must |

#### TC-AUDIT-004: 验证事务一致性

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-AUDIT-004 |
| **用例名称** | 验证同一事务的审计日志一致性 |
| **测试目的** | 确保级联操作在同一事务中记录 |
| **前置条件** | 执行级联操作（如创建带关联的对象） |
| **测试步骤** | 执行级联操作，按 transaction_id 查询日志 |
| **期望结果** | 同一 transaction_id 的日志有相同的 user_id |
| **验证方法** | `verifier.verify_transaction(txn_id)` |
| **优先级** | Should |

---

### 2.2 用户管理测试用例

#### TC-USER-CREATE: 创建用户

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-USER-CREATE |
| **用例名称** | 创建用户时审计日志记录正确 |
| **前置条件** | 系统正常运行，以管理员身份登录 |
| **测试步骤** | 1. POST /api/v1/users 创建用户<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = users<br>- field_name = 各业务字段<br>- new_value = 创建的值<br>- old_value = 空 |
| **验证点** | 通用内容 + CREATE 验证 |
| **优先级** | Must |

#### TC-USER-UPDATE: 更新用户

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-USER-UPDATE |
| **用例名称** | 更新用户时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待更新的用户 |
| **测试步骤** | 1. PUT /api/v1/users/{id} 更新用户<br>2. 查询审计日志 |
| **期望结果** | - action = UPDATE<br>- field_name = 更新的字段<br>- old_value = 旧值<br>- new_value = 新值 |
| **验证点** | 通用内容 + UPDATE 验证 |
| **优先级** | Must |

#### TC-USER-DELETE: 删除用户

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-USER-DELETE |
| **用例名称** | 删除用户时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待删除的用户 |
| **测试步骤** | 1. DELETE /api/v1/users/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = DELETE<br>- field_name = 业务字段<br>- old_value = 删除前的值<br>- new_value = 空 |
| **验证点** | 通用内容 + DELETE 验证 |
| **优先级** | Must |

---

### 2.3 角色管理测试用例

#### TC-ROLE-CREATE: 创建角色

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-ROLE-CREATE |
| **用例名称** | 创建角色时审计日志记录正确 |
| **前置条件** | 系统正常运行，以管理员身份登录 |
| **测试步骤** | 1. POST /api/v1/roles 创建角色<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = roles<br>- object_key = code<br>- object_display_name = name |
| **验证点** | 通用内容 + CREATE 验证 |
| **优先级** | Must |

#### TC-ROLE-UPDATE: 更新角色

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-ROLE-UPDATE |
| **用例名称** | 更新角色时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待更新的角色 |
| **测试步骤** | 1. PUT /api/v1/roles/{id} 更新角色<br>2. 查询审计日志 |
| **期望结果** | - action = UPDATE<br>- field_name = 更新的字段（name, code, description 等） |
| **验证点** | 通用内容 + UPDATE 验证 |
| **优先级** | Must |

#### TC-ROLE-DELETE: 删除角色

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-ROLE-DELETE |
| **用例名称** | 删除角色时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待删除的角色 |
| **测试步骤** | 1. DELETE /api/v1/roles/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = DELETE<br>- old_value 包含角色的所有业务字段值 |
| **验证点** | 通用内容 + DELETE 验证 |
| **优先级** | Must |

---

### 2.4 产品线管理测试用例

#### TC-PRODUCT-CREATE: 创建产品线

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-PRODUCT-CREATE |
| **用例名称** | 创建产品线时审计日志记录正确 |
| **前置条件** | 系统正常运行，以管理员身份登录 |
| **测试步骤** | 1. POST /api/v1/products 创建产品线<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = products<br>- object_key = code<br>- object_display_name = name<br>- FK 字段 (owner_id) 结构化 |
| **验证点** | 通用内容 + CREATE 验证 + FK 验证 |
| **优先级** | Must |

#### TC-PRODUCT-UPDATE: 更新产品线

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-PRODUCT-UPDATE |
| **用例名称** | 更新产品线时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待更新的产品线 |
| **测试步骤** | 1. PUT /api/v1/products/{id} 更新产品线<br>2. 查询审计日志 |
| **期望结果** | - action = UPDATE<br>- field_name = 更新的字段<br>- FK 字段 (owner_id) 结构化为 {target_type: users, target_id: X, target_display: Y} |
| **验证点** | 通用内容 + UPDATE 验证 + FK 验证 |
| **优先级** | Must |

#### TC-PRODUCT-DELETE: 删除产品线

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-PRODUCT-DELETE |
| **用例名称** | 删除产品线时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待删除的产品线 |
| **测试步骤** | 1. DELETE /api/v1/products/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = DELETE<br>- old_value 包含产品线的所有业务字段值 |
| **验证点** | 通用内容 + DELETE 验证 |
| **优先级** | Must |

#### TC-PRODUCT-IMPORT: 导入产品线

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-PRODUCT-IMPORT |
| **用例名称** | 导入产品线时审计日志记录正确 |
| **前置条件** | 系统正常运行，准备 Excel 导入文件 |
| **测试步骤** | 1. POST /api/v1/products/import 上传 Excel<br>2. 查询审计日志 |
| **期望结果** | - action = BULK_CREATE 或 CREATE（批量或逐条）<br>- new_value 包含导入的记录数或数据摘要 |
| **验证点** | 通用内容 + BULK_CREATE 验证 |
| **优先级** | Should |

---

### 2.5 版本管理测试用例

#### TC-VERSION-CREATE: 创建版本

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-VERSION-CREATE |
| **用例名称** | 创建版本时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在产品线 |
| **测试步骤** | 1. POST /api/v1/versions 创建版本<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = versions<br>- object_key = code<br>- object_display_name = name<br>- FK: product_id 结构化<br>- FK: owner_id 结构化 |
| **验证点** | 通用内容 + CREATE 验证 + FK 验证 |
| **优先级** | Must |

#### TC-VERSION-RELATION: 版本与产品关联

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-VERSION-RELATION |
| **用例名称** | 版本关联产品时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在版本 |
| **测试步骤** | 版本通过 product_id 关联产品，查询审计日志 |
| **期望结果** | FK 字段 product_id 的值包含 {target_type: products, target_id, target_key, target_display} |
| **验证点** | FK 结构验证 |
| **优先级** | Must |

---

### 2.6 领域管理测试用例

#### TC-DOMAIN-CREATE: 创建领域

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-DOMAIN-CREATE |
| **用例名称** | 创建领域时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在版本 |
| **测试步骤** | 1. POST /api/v1/domains 创建领域<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = domains<br>- object_key = code<br>- object_display_name = name<br>- FK: version_id 结构化 |
| **验证点** | 通用内容 + CREATE 验证 + FK 验证 |
| **优先级** | Must |

#### TC-DOMAIN-CASCADE: 领域级联导入

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-DOMAIN-CASCADE |
| **用例名称** | 领域级联导入时审计日志记录正确 |
| **前置条件** | 系统正常运行，准备包含领域、子领域、业务对象的 Excel |
| **测试步骤** | 1. POST /api/v1/domains/import 导入<br>2. 查询审计日志 |
| **期望结果** | 每条记录都有对应的 CREATE 日志，共享 transaction_id |
| **验证点** | 事务完整性验证 |
| **优先级** | Should |

---

### 2.7 业务对象管理测试用例

#### TC-BO-CREATE: 创建业务对象

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-BO-CREATE |
| **用例名称** | 创建业务对象时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在服务模块 |
| **测试步骤** | 1. POST /api/v1/business_objects 创建业务对象<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = business_objects<br>- object_key = code<br>- object_display_name = name<br>- FK: service_module_id 结构化<br>- FK: version_id 结构化 |
| **验证点** | 通用内容 + CREATE 验证 + FK 验证 |
| **优先级** | Must |

#### TC-BO-IMPORT: 导入业务对象

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-BO-IMPORT |
| **用例名称** | 导入业务对象时审计日志记录正确 |
| **前置条件** | 系统正常运行，准备 Excel 导入文件 |
| **测试步骤** | 1. POST /api/v1/business_objects/import<br>2. 查询审计日志 |
| **期望结果** | - action = BULK_CREATE<br>- 包含导入记录数 |
| **验证点** | 通用内容 + BULK_CREATE 验证 |
| **优先级** | Should |

#### TC-BO-EXPORT: 导出业务对象

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-BO-EXPORT |
| **用例名称** | 导出业务对象时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在业务对象 |
| **测试步骤** | 1. GET /api/v1/business_objects/export<br>2. 查询审计日志 |
| **期望结果** | - action = EXPORT 或 READ_OBJECT<br>- new_value 包含导出范围信息 |
| **验证点** | 通用内容 + EXPORT 验证 |
| **优先级** | Should |

---

### 2.8 关系管理测试用例

#### TC-REL-CREATE: 创建关系

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-REL-CREATE |
| **用例名称** | 创建关系时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在至少两个业务对象 |
| **测试步骤** | 1. POST /api/v1/relationships 创建关系<br>2. 查询审计日志 |
| **期望结果** | - action = ASSOCIATE 或 CREATE<br>- FK: source_bo_id 结构化<br>- FK: target_bo_id 结构化 |
| **验证点** | 通用内容 + ASSOCIATE 验证 + FK 验证 |
| **优先级** | Must |

#### TC-REL-UPDATE: 更新关系

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-REL-UPDATE |
| **用例名称** | 更新关系时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待更新的关系 |
| **测试步骤** | 1. PUT /api/v1/relationships/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = UPDATE<br>- field_name = 更新的字段 |
| **验证点** | 通用内容 + UPDATE 验证 |
| **优先级** | Must |

#### TC-REL-DELETE: 删除关系

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-REL-DELETE |
| **用例名称** | 删除关系时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待删除的关系 |
| **测试步骤** | 1. DELETE /api/v1/relationships/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = DISSOCIATE 或 DELETE<br>- old_value 包含关系信息 |
| **验证点** | 通用内容 + DISSOCIATE 验证 |
| **优先级** | Must |

#### TC-REL-IMPORT: 导入关系

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-REL-IMPORT |
| **用例名称** | 导入关系时审计日志记录正确 |
| **前置条件** | 系统正常运行，准备关系导入文件 |
| **测试步骤** | 1. POST /api/v1/relationships/import<br>2. 查询审计日志 |
| **期望结果** | - action = BULK_CREATE 或 ASSOCIATE |
| **验证点** | 通用内容 + BULK_CREATE 验证 |
| **优先级** | Should |

---

### 2.9 关系结构验证

#### TC-REL-STRUCT-SOURCE: 关系源端结构验证

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-REL-STRUCT-SOURCE |
| **用例名称** | 验证关系源端外键结构化 |
| **测试目的** | 确保关系记录了源端业务对象的完整信息 |
| **前置条件** | 存在创建的关系记录 |
| **测试步骤** | 1. 查询关系的审计日志<br>2. 检查 source_bo_id 字段的 new_value |
| **期望结果** | new_value 包含 {target_type: business_objects, target_id, target_key, target_display} |
| **验证点** | FK 结构验证 |
| **优先级** | Must |

#### TC-REL-STRUCT-TARGET: 关系目标端结构验证

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-REL-STRUCT-TARGET |
| **用例名称** | 验证关系目标端外键结构化 |
| **测试目的** | 确保关系记录了目标端业务对象的完整信息 |
| **前置条件** | 存在创建的关系记录 |
| **测试步骤** | 1. 查询关系的审计日志<br>2. 检查 target_bo_id 字段的 new_value |
| **期望结果** | new_value 包含 {target_type: business_objects, target_id, target_key, target_display} |
| **验证点** | FK 结构验证 |
| **优先级** | Must |

---

### 2.10 备注管理测试用例

#### TC-ANN-CREATE: 创建备注

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-ANN-CREATE |
| **用例名称** | 创建备注时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在任意可备注的实体 |
| **测试步骤** | 1. POST /api/v1/annotations 创建备注<br>2. 查询审计日志 |
| **期望结果** | - action = CREATE<br>- object_type = annotations<br>- object_id = 备注 ID<br>- target_type 和 target_id 正确关联到目标实体 |
| **验证点** | 通用内容 + CREATE 验证 |
| **优先级** | Should |

#### TC-ANN-UPDATE: 更新备注

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-ANN-UPDATE |
| **用例名称** | 更新备注时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待更新的备注 |
| **测试步骤** | 1. PUT /api/v1/annotations/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = UPDATE<br>- field_name = 更新的字段（content, category） |
| **验证点** | 通用内容 + UPDATE 验证 |
| **优先级** | Should |

#### TC-ANN-DELETE: 删除备注

| 字段 | 说明 |
|------|------|
| **用例 ID** | TC-ANN-DELETE |
| **用例名称** | 删除备注时审计日志记录正确 |
| **前置条件** | 系统正常运行，存在待删除的备注 |
| **测试步骤** | 1. DELETE /api/v1/annotations/{id}<br>2. 查询审计日志 |
| **期望结果** | - action = DELETE<br>- old_value 包含备注内容 |
| **验证点** | 通用内容 + DELETE 验证 |
| **优先级** | Should |

---

## 三、测试用例汇总表

### 3.1 按实体类型汇总

| 实体 | CREATE | UPDATE | DELETE | IMPORT | EXPORT | 其他 |
|------|--------|--------|--------|--------|--------|------|
| users | TC-USER-CREATE | TC-USER-UPDATE | TC-USER-DELETE | - | - | - |
| roles | TC-ROLE-CREATE | TC-ROLE-UPDATE | TC-ROLE-DELETE | - | - | - |
| user_groups | TC-GROUP-CREATE | TC-GROUP-UPDATE | TC-GROUP-DELETE | - | - | - |
| products | TC-PRODUCT-CREATE | TC-PRODUCT-UPDATE | TC-PRODUCT-DELETE | TC-PRODUCT-IMPORT | - | - |
| versions | TC-VERSION-CREATE | TC-VERSION-UPDATE | TC-VERSION-DELETE | TC-VERSION-IMPORT | - | TC-VERSION-RELATION |
| domains | TC-DOMAIN-CREATE | TC-DOMAIN-UPDATE | TC-DOMAIN-DELETE | TC-DOMAIN-IMPORT | - | TC-DOMAIN-CASCADE |
| business_objects | TC-BO-CREATE | TC-BO-UPDATE | TC-BO-DELETE | TC-BO-IMPORT | TC-BO-EXPORT | - |
| relationships | TC-REL-CREATE | TC-REL-UPDATE | TC-REL-DELETE | TC-REL-IMPORT | - | TC-REL-STRUCT-SOURCE, TC-REL-STRUCT-TARGET |
| annotations | TC-ANN-CREATE | TC-ANN-UPDATE | TC-ANN-DELETE | - | - | - |

### 3.2 按优先级汇总

#### Must（必须实现）

| 用例 ID | 用例名称 | 验证内容 |
|---------|---------|---------|
| TC-AUDIT-002 | 通用必需字段 | object_type, object_id, action, user_id, created_at |
| TC-AUDIT-003 | 时间戳格式 | created_at ISO 格式 |
| TC-USER-CREATE | 创建用户 | CREATE 验证 |
| TC-USER-UPDATE | 更新用户 | UPDATE 验证 |
| TC-USER-DELETE | 删除用户 | DELETE 验证 |
| TC-ROLE-CREATE | 创建角色 | CREATE + 标识验证 |
| TC-ROLE-UPDATE | 更新角色 | UPDATE 验证 |
| TC-ROLE-DELETE | 删除角色 | DELETE 验证 |
| TC-PRODUCT-CREATE | 创建产品线 | CREATE + FK 验证 |
| TC-PRODUCT-UPDATE | 更新产品线 | UPDATE + FK 验证 |
| TC-PRODUCT-DELETE | 删除产品线 | DELETE 验证 |
| TC-VERSION-CREATE | 创建版本 | CREATE + FK 验证 |
| TC-VERSION-RELATION | 版本关联产品 | FK 结构验证 |
| TC-DOMAIN-CREATE | 创建领域 | CREATE + FK 验证 |
| TC-BO-CREATE | 创建业务对象 | CREATE + FK 验证 |
| TC-REL-CREATE | 创建关系 | ASSOCIATE + FK 验证 |
| TC-REL-UPDATE | 更新关系 | UPDATE 验证 |
| TC-REL-DELETE | 删除关系 | DISSOCIATE 验证 |
| TC-REL-STRUCT-SOURCE | 关系源端结构 | FK 结构验证 |
| TC-REL-STRUCT-TARGET | 关系目标端结构 | FK 结构验证 |

#### Should（建议实现）

| 用例 ID | 用例名称 | 验证内容 |
|---------|---------|---------|
| TC-AUDIT-001 | 对象标识存在 | audit_object_key, audit_object_display_name |
| TC-AUDIT-004 | 事务一致性 | transaction_id 一致性 |
| TC-PRODUCT-IMPORT | 导入产品线 | BULK_CREATE 验证 |
| TC-DOMAIN-CASCADE | 领域级联导入 | 事务完整性验证 |
| TC-BO-IMPORT | 导入业务对象 | BULK_CREATE 验证 |
| TC-BO-EXPORT | 导出业务对象 | EXPORT 验证 |
| TC-REL-IMPORT | 导入关系 | BULK_CREATE 验证 |
| TC-ANN-CREATE | 创建备注 | CREATE 验证 |
| TC-ANN-UPDATE | 更新备注 | UPDATE 验证 |
| TC-ANN-DELETE | 删除备注 | DELETE 验证 |

---

## 四、测试数据准备

### 4.1 测试用户

```json
{
  "username": "audit_test_user",
  "display_name": "审计测试用户",
  "email": "audit_test@example.com",
  "password": "Test@123456"
}
```

### 4.2 测试角色

```json
{
  "code": "AUDIT_TEST_ROLE",
  "name": "审计测试角色",
  "description": "用于审计日志测试的角色"
}
```

### 4.3 测试产品线

```json
{
  "code": "TEST_PRODUCT_001",
  "name": "测试产品线001",
  "description": "用于审计日志测试的产品线"
}
```

### 4.4 测试版本

```json
{
  "code": "TEST_VERSION_001",
  "name": "测试版本001",
  "visibility": "public"
}
```

### 4.5 测试领域

```json
{
  "code": "TEST_DOMAIN_001",
  "name": "测试领域001",
  "description": "用于审计日志测试的领域"
}
```

### 4.6 测试业务对象

```json
{
  "code": "TEST_BO_001",
  "name": "测试业务对象001",
  "description": "用于审计日志测试的业务对象"
}
```

### 4.7 测试关系

```json
{
  "code": "TEST_REL_001",
  "relation_type": "association",
  "relation_direction": "bidirectional",
  "relation_desc": "测试关系001"
}
```

---

## 五、测试执行方式

### 5.1 自动化测试框架

```python
import unittest
from test_helpers.audit_log_verifier import AuditLogVerifier

class TestAuditLog(unittest.TestCase):
    verifier = AuditLogVerifier(data_source)
    
    def test_common_fields(self):
        """验证审计日志通用字段"""
        pass
    
    def test_object_identity(self):
        """验证对象标识"""
        pass
    
    def test_fk_structure(self):
        """验证外键结构化"""
        pass
```

### 5.2 测试报告

```python
def run_audit_tests():
    """运行所有审计日志测试"""
    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'details': []
    }
    
    for tc in test_cases:
        result = execute_test_case(tc)
        results['total'] += 1
        if result['passed']:
            results['passed'] += 1
        else:
            results['failed'] += 1
        results['details'].append(result)
    
    return results
```

---

## 六、验证方法映射

| 验证点 | 验证方法 | 说明 |
|--------|---------|------|
| 通用必需字段 | `verifier.verify(log)` | 检查 result.errors |
| 对象标识 | `verifier._verify_object_identity(log, result)` | 检查 extra_data |
| FK 结构 | `verifier._verify_fk_structure(log, result)` | 检查值是否为 JSON |
| CREATE 验证 | `verifier._verify_create_log(log, result)` | 检查 new_value 有值 |
| UPDATE 验证 | `verifier._verify_update_log(log, result)` | 检查值变化 |
| DELETE 验证 | `verifier._verify_delete_log(log, result)` | 检查 old_value 有值 |
| ASSOCIATE 验证 | `verifier._verify_associate_log(log, result)` | 检查目标信息 |
| DISSOCIATE 验证 | `verifier._verify_dissociate_log(log, result)` | 检查目标信息 |
| 事务完整性 | `verifier.verify_transaction(txn_id)` | 检查 user_id 一致性 |
| 对象历史 | `verifier.verify_object_history(type, id)` | 检查操作完整性 |
| 批量验证 | `verifier.verify_batch(logs)` | 统计有效率 |
