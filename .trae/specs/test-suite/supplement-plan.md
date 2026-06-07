# 测试用例补齐计划

> **目标**: 补充 Phase 11-14 相关的新测试用例
>
> **范围**: 对象适配测试、Value Help测试、DisplayName增强测试、日志拦截器测试

---

## 一、现有测试覆盖分析

### 1.1 已存在的测试

| 类别 | 文件 | 测试数 | 状态 |
|------|------|--------|------|
| **Phase 13 DisplayName** | test_display_name_service.py | 36 | ✅ 已完成 |
| **Phase 13 BOFramework** | test_bo_framework_display_name.py | 26 | ✅ 已完成 |
| **Phase 12 Value Help** | test_value_help_validation.py | 3 | ⚠️ 基础 |
| **Phase 14 Log Enums** | test_log_enums.py | 18 | ✅ 已完成 |
| **Phase 14 Log Entry** | test_log_entry.py | 18 | ✅ 已完成 |
| **Phase 14 StructuredLogger** | test_structured_logger.py | 18 | ✅ 已完成 |

### 1.2 新创建的测试文件

| 类别 | 文件 | 测试数 | 状态 |
|------|------|--------|------|
| **Phase 11 Role CRUD** | test_object_adaptation_role.py | 20 | ✅ 已创建 (10 YAML元数据通过) |
| **Phase 11 UserGroup CRUD** | test_object_adaptation_user_group.py | 25 | ✅ 已创建 |
| **Phase 11 Association CRUD** | test_association_crud_operations.py | 20 | ✅ 已创建 |
| **Phase 14 Business Log** | test_log_business_interceptor.py | 25 | ✅ 已创建 |
| **Phase 14 Security Log** | test_log_security_interceptor.py | 20 | ✅ 已创建 |
| **Phase 14 Operation/Integration** | test_log_operation_interceptor.py | 20 | ✅ 已创建 |
| **小计** | 6个文件 | **130** | ✅ 已创建 |

### 1.3 测试执行结果

```
Phase 11 Role CRUD 测试:
- test_role_yaml_loaded ✅
- test_role_fields_definition ✅
- test_role_ui_view_config ✅
- test_role_associations_defined ⚠️ (需要 YAML 关联配置)
- test_role_computed_fields ⚠️ (需要 YAML 计算字段配置)
```

### 1.4 缺失的测试

| 类别 | 测试数 | 优先级 |
|------|--------|--------|
| **Phase 12 Value Help** | 30 | 🟡 中 |
| **Phase 13 DisplayName增强** | 15 | 🟡 中 |
| **Phase 14 前端扩展** | 15 | 🟡 中 |

---

## 二、Phase 11 对象适配测试 (45个)

### 2.1 Role CRUD 测试 (15个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-PA-001 | 创建Role - 基本创建 | name, code必填 |
| TC-PA-002 | 创建Role - 带描述 | description字段 |
| TC-PA-003 | 创建Role - 重复code | 唯一性验证 |
| TC-PA-004 | 读取Role - 按ID | 返回完整数据 |
| TC-PA-005 | 读取Role - 包含计算字段 | menu_count, user_count |
| TC-PA-006 | 更新Role - 基本更新 | name更新 |
| TC-PA-007 | 更新Role - 更新描述 | description更新 |
| TC-PA-008 | 更新Role - 禁止更新code | code只读 |
| TC-PA-009 | 删除Role - 基本删除 | 软删除 |
| TC-PA-010 | 删除Role - 有关联用户 | 关联检查 |
| TC-PA-011 | 列表Role - 分页 | page=1, page_size=20 |
| TC-PA-012 | 列表Role - 带过滤 | name包含过滤 |
| TC-PA-013 | 列表Role - 带排序 | name升序 |
| TC-PA-014 | 列表Role - 搜索 | keyword搜索 |
| TC-PA-015 | Role详情 - YAML配置 | ui_view_config.detail |

### 2.2 UserGroup CRUD 测试 (15个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-PA-016 | 创建UserGroup - 基本创建 | name, code必填 |
| TC-PA-017 | 创建UserGroup - 带层级 | parent_id设置 |
| TC-PA-018 | 创建UserGroup - 带管理员 | manager_id设置 |
| TC-PA-019 | 读取UserGroup - 包含计算字段 | member_count |
| TC-PA-020 | 更新UserGroup - 更新层级 | parent_id更新 |
| TC-PA-021 | 更新UserGroup - 更新管理员 | manager_id更新 |
| TC-PA-022 | 删除UserGroup - 基本删除 | 软删除 |
| TC-PA-023 | 删除UserGroup - 有子组 | 层级检查 |
| TC-PA-024 | 删除UserGroup - 有成员 | 成员检查 |
| TC-PA-025 | 列表UserGroup - 树形结构 | parent_id过滤 |
| TC-PA-026 | 列表UserGroup - 顶级组 | parent_id=null |
| TC-PA-027 | 列表UserGroup - 搜索 | keyword搜索 |
| TC-PA-028 | UserGroup详情 - YAML配置 | ui_view_config.detail |
| TC-PA-029 | UserGroup - 层级路径 | hierarchy_path |
| TC-PA-030 | UserGroup - 成员计数 | member_count计算 |

### 2.3 Association CRUD 测试 (15个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-PA-031 | Role分配权限 - 基本分配 | role_permissions |
| TC-PA-032 | Role分配权限 - 重复分配 | 幂等性 |
| TC-PA-033 | Role分配权限 - 批量分配 | batch_assign |
| TC-PA-034 | Role取消权限 - 基本取消 | role_permissions |
| TC-PA-035 | Role取消权限 - 不存在 | 错误处理 |
| TC-PA-036 | UserGroup添加成员 - 基本添加 | user_group_members |
| TC-PA-037 | UserGroup添加成员 - 重复添加 | 幂等性 |
| TC-PA-038 | UserGroup添加成员 - 批量添加 | batch_assign |
| TC-PA-039 | UserGroup移除成员 - 基本移除 | user_group_members |
| TC-PA-040 | UserGroup移除成员 - 不存在 | 错误处理 |
| TC-PA-041 | 查询Role权限列表 | GET $associations/permissions |
| TC-PA-042 | 查询UserGroup成员列表 | GET $associations/members |
| TC-PA-043 | 查询UserGroup角色列表 | GET $associations/roles |
| TC-PA-044 | 权限计数 - Role权限数 | role.permission_count |
| TC-PA-045 | 成员计数 - UserGroup成员数 | user_group.member_count |

---

## 三、Phase 12 Value Help 测试 (30个)

### 3.1 EnumValueHelp 测试 (10个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-VH-001 | 获取枚举值列表 | enum_type查询 |
| TC-VH-002 | 枚举值过滤 | is_active=true |
| TC-VH-003 | 枚举值搜索 | name模糊搜索 |
| TC-VH-004 | 枚举值分页 | 大数据集分页 |
| TC-VH-005 | 枚举值排序 | sort_order排序 |
| TC-VH-006 | 枚举值验证 - 有效值 | validation通过 |
| TC-VH-007 | 枚举值验证 - 无效值 | validation失败 |
| TC-VH-008 | 枚举值缓存 | 重复查询缓存 |
| TC-VH-009 | 多语言枚举值 | i18n支持 |
| TC-VH-010 | 枚举值前端组件 | EnumValueHelp.vue |

### 3.2 AssociationSearchHelp 测试 (10个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-VH-011 | 搜索关联对象 - 基本搜索 | keyword搜索 |
| TC-VH-012 | 搜索关联对象 - 多字段 | code+name搜索 |
| TC-VH-013 | 搜索关联对象 - 精确匹配 | exact match |
| TC-VH-014 | 搜索关联对象 - 前缀匹配 | prefix match |
| TC-VH-015 | 搜索关联对象 - 模糊匹配 | fuzzy match |
| TC-VH-016 | 搜索关联对象 - 分页 | 大数据集分页 |
| TC-VH-017 | 选择关联对象 - 单选 | single select |
| TC-VH-018 | 选择关联对象 - 多选 | multi select |
| TC-VH-019 | 选择关联对象 - 显示字段 | display_fields配置 |
| TC-VH-020 | 搜索结果格式化 | format配置 |

### 3.3 TreeValueHelp & SearchHelpDialog 测试 (10个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-VH-021 | 树形帮助 - 加载根节点 | level=0 |
| TC-VH-022 | 树形帮助 - 懒加载子节点 | expand触发 |
| TC-VH-023 | 树形帮助 - 选择节点 | node select |
| TC-VH-024 | 树形帮助 - 多选 | multi select |
| TC-VH-025 | 树形帮助 - 层级限制 | level_limit |
| TC-VH-026 | 搜索帮助对话框 - 打开 | dialog open |
| TC-VH-027 | 搜索帮助对话框 - 搜索 | search trigger |
| TC-VH-028 | 搜索帮助对话框 - 选择 | item select |
| TC-VH-029 | 搜索帮助对话框 - 确认 | confirm action |
| TC-VH-030 | 搜索帮助对话框 - 取消 | cancel action |

---

## 四、Phase 13 DisplayName 增强测试 (15个)

### 4.1 I18nDisplay 测试 (8个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-DN-001 | 获取多语言字段名称 | zh_CN, en_US |
| TC-DN-002 | 获取多语言对象名称 | i18n object name |
| TC-DN-003 | 多语言回退 - 中文优先 | zh_CN fallback |
| TC-DN-004 | 多语言回退 - 英文 | en_US fallback |
| TC-DN-005 | 多语言回退 - 默认值 | default fallback |
| TC-DN-006 | 多语言格式化 - 带参数 | format with args |
| TC-DN-007 | 多语言缓存 | translation cache |
| TC-DN-008 | 多语言切换 | locale switch |

### 4.2 ContextAwareDisplay 测试 (7个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-DN-009 | 列表上下文显示 | LIST context |
| TC-DN-010 | 详情上下文显示 | DETAIL context |
| TC-DN-011 | 表单上下文显示 | FORM context |
| TC-DN-012 | 过滤上下文显示 | FILTER context |
| TC-DN-013 | 关联上下文显示 | ASSOCIATION context |
| TC-DN-014 | 上下文回退 | fallback to default |
| TC-DN-015 | 上下文格式化 | context-specific format |

---

## 五、Phase 14 日志拦截器测试 (45个)

### 5.1 业务日志拦截器测试 (15个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-LG-001 | 业务操作日志 - 创建 | create action |
| TC-LG-002 | 业务操作日志 - 更新 | update action |
| TC-LG-003 | 业务操作日志 - 删除 | delete action |
| TC-LG-004 | 业务操作日志 - 批量操作 | batch action |
| TC-LG-005 | 业务操作日志 - 字段变更 | field changes |
| TC-LG-006 | 业务操作日志 - 关联变更 | association changes |
| TC-LG-007 | 业务操作日志 - 操作人 | operator info |
| TC-LG-008 | 业务操作日志 - 时间戳 | timestamp |
| TC-LG-009 | 业务操作日志 - 对象类型 | object_type |
| TC-LG-010 | 业务操作日志 - 对象ID | object_id |
| TC-LG-011 | 业务操作日志 - IP地址 | ip_address |
| TC-LG-012 | 业务操作日志 - 用户代理 | user_agent |
| TC-LG-013 | 业务操作日志 - 请求ID | request_id |
| TC-LG-014 | 业务操作日志 - 异步写入 | async write |
| TC-LG-015 | 业务操作日志 - 错误处理 | error handling |

### 5.2 安全日志拦截器测试 (10个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-LG-016 | 安全日志 - 登录成功 | login success |
| TC-LG-017 | 安全日志 - 登录失败 | login failed |
| TC-LG-018 | 安全日志 - 登出 | logout |
| TC-LG-019 | 安全日志 - 密码修改 | password change |
| TC-LG-020 | 安全日志 - 权限变更 | permission change |
| TC-LG-021 | 安全日志 - 敏感操作 | sensitive action |
| TC-LG-022 | 安全日志 - 异常访问 | abnormal access |
| TC-LG-023 | 安全日志 - SQL注入 | sql injection attempt |
| TC-LG-024 | 安全日志 - XSS攻击 | xss attempt |
| TC-LG-025 | 安全日志 - CSRF攻击 | csrf attempt |

### 5.3 操作日志拦截器测试 (10个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-LG-026 | 操作日志 - 导出 | export action |
| TC-LG-027 | 操作日志 - 导入 | import action |
| TC-LG-028 | 操作日志 - 批量删除 | batch delete |
| TC-LG-029 | 操作日志 - 配置修改 | config change |
| TC-LG-030 | 操作日志 - 数据迁移 | data migration |
| TC-LG-031 | 操作日志 - 缓存清除 | cache clear |
| TC-LG-032 | 操作日志 - 系统维护 | system maintenance |
| TC-LG-033 | 操作日志 - 性能监控 | performance log |
| TC-LG-034 | 操作日志 - 错误日志 | error log |
| TC-LG-035 | 操作日志 - 调试日志 | debug log |

### 5.4 日志集成测试 (10个)

| ID | 测试名称 | 测试点 |
|----|---------|--------|
| TC-LG-036 | 日志分类 - category字段 | business/security/operation |
| TC-LG-037 | 日志级别 - level字段 | DEBUG/INFO/WARNING/ERROR |
| TC-LG-038 | 日志过滤 - 按分类 | category filter |
| TC-LG-039 | 日志过滤 - 按级别 | level filter |
| TC-LG-040 | 日志过滤 - 组合过滤 | combined filter |
| TC-LG-041 | 日志搜索 - keyword | keyword search |
| TC-LG-042 | 日志搜索 - 时间范围 | time range |
| TC-LG-043 | 日志导出 - CSV格式 | csv export |
| TC-LG-044 | 日志导出 - JSON格式 | json export |
| TC-LG-045 | 日志归档 - 自动归档 | auto archive |

---

## 六、测试文件清单

### 6.1 已创建的测试文件

```
meta/tests/
├── test_object_adaptation_role.py          # ✅ Phase 11 Role CRUD (20个)
├── test_object_adaptation_user_group.py   # ✅ Phase 11 UserGroup CRUD (25个)
├── test_association_crud_operations.py     # ✅ Phase 11 Association CRUD (20个)
├── test_value_help_enum.py                 # ⏳ Phase 12 EnumValueHelp (待创建)
├── test_value_help_association.py           # ⏳ Phase 12 AssociationSearchHelp (待创建)
├── test_value_help_tree_dialog.py          # ⏳ Phase 12 TreeValueHelp/Dialog (待创建)
├── test_display_name_i18n.py               # ⏳ Phase 13 I18nDisplay (待创建)
├── test_display_name_context.py            # ⏳ Phase 13 ContextAwareDisplay (待创建)
├── test_log_business_interceptor.py       # ✅ Phase 14 业务日志 (25个)
├── test_log_security_interceptor.py      # ✅ Phase 14 安全日志 (20个)
└── test_log_operation_interceptor.py      # ✅ Phase 14 操作/集成日志 (20个)
```

### 6.2 测试统计

| 文件 | 测试数 | Phase | 状态 |
|------|--------|-------|------|
| test_object_adaptation_role.py | 20 | Phase 11 | ✅ 已创建 |
| test_object_adaptation_user_group.py | 25 | Phase 11 | ✅ 已创建 |
| test_association_crud_operations.py | 20 | Phase 11 | ✅ 已创建 |
| test_log_business_interceptor.py | 25 | Phase 14 | ✅ 已创建 |
| test_log_security_interceptor.py | 20 | Phase 14 | ✅ 已创建 |
| test_log_operation_interceptor.py | 20 | Phase 14 | ✅ 已创建 |
| **已完成小计** | **130** | - | ✅ |
| test_value_help_*.py | 30 | Phase 12 | ⏳ 待创建 |
| test_display_name_*.py | 15 | Phase 13 | ⏳ 待创建 |
| **待创建小计** | **45** | - | ⏳ |
| **总计** | **175** | - | - |

---

## 七、实施计划

| 阶段 | 任务 | 优先级 | 状态 |
|------|------|--------|------|
| 1 | Phase 11 对象适配测试 | 🔴 高 | ✅ 已完成 |
| 2 | Phase 14 日志拦截器测试 | 🔴 高 | ✅ 已完成 |
| 3 | Phase 12 Value Help测试 | 🟡 中 | ⏳ 待实施 |
| 4 | Phase 13 DisplayName增强 | 🟡 中 | ⏳ 待实施 |
| 5 | 测试运行与修复 | 🔴 高 | ⏳ 待实施 |

---

## 八、验收标准

- [x] Phase 11: 65个测试已创建 (Role 20 + UserGroup 25 + Association 20)
- [x] Phase 13: 62个测试已创建并通过 (DisplayNameService 36 + BOFramework 26)
- [x] Phase 14: 65个测试已创建 (Business 25 + Security 20 + Operation 20)
- [ ] Phase 12: 30个测试待创建
- [ ] 整体测试覆盖率提升至90%+
