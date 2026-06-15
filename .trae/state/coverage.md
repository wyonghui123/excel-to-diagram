# 业务规则覆盖率报告

> **生成时间**: 2026-06-13T09:19:34.581440Z
> **Spec**: v2.0 (FR-012/FR-022)
> **目标**: ≥ 80%

## 概览

| 指标 | 数值 |
|------|------|
| 总业务规则 | **722** |
| 已覆盖 | 160 |
| 未覆盖 | 562 |
| **覆盖率** | **22.2%** |
| 目标达成 | ❌ 否 |

## 按业务对象

| 对象 | 规则 | 已覆盖 | 覆盖率 | 状态 |
|------|------|--------|--------|------|
| AI异步任务 (ai_async_task) | 6 | 6 | 100.0% | ✅ |
| 测试表 (test_table) | 1 | 1 | 100.0% | ✅ |
| 备注信息 (annotation) | 12 | 10 | 83.3% | ✅ |
| 产品线 (product) | 36 | 21 | 58.3% | ⚠️ |
| 用户组成员 (user_group_member) | 2 | 1 | 50.0% | ⚠️ |
| 业务关系 (relationship) | 34 | 14 | 41.2% | ❌ |
| 角色 (role) | 15 | 6 | 40.0% | ❌ |
| 领域 (domain) | 33 | 12 | 36.4% | ❌ |
| 服务模块 (service_module) | 39 | 13 | 33.3% | ❌ |
| 任务队列配置 (task_queue) | 6 | 2 | 33.3% | ❌ |
| 用户组 (user_group) | 9 | 3 | 33.3% | ❌ |
| 业务对象 (business_object) | 37 | 12 | 32.4% | ❌ |
| 子领域 (sub_domain) | 38 | 12 | 31.6% | ❌ |
| 任务定义 (scheduled_task) | 10 | 3 | 30.0% | ❌ |
| 产品版本 (version) | 55 | 15 | 27.3% | ❌ |
| 审计日志 (audit_log) | 49 | 13 | 26.5% | ❌ |
| 变更事件 (change_event) | 12 | 3 | 25.0% | ❌ |
| 枚举值 (enum_value) | 21 | 3 | 14.3% | ❌ |
| 测试对象 (test_objects) | 7 | 1 | 14.3% | ❌ |
| 用户 (user) | 57 | 7 | 12.3% | ❌ |
| 变更订阅 (change_subscription) | 9 | 1 | 11.1% | ❌ |
| 任务执行记录 (task_execution) | 9 | 1 | 11.1% | ❌ |
| 功能权限 (permission) | 41 | 2 | 4.9% | ❌ |
| 枚举类型 (enum_type) | 192 | 2 | 1.0% | ❌ |
| aspects (aspects) | 0 | 0 | 0% | ❌ |
| audit_log_expectations (audit_log_expectations) | 0 | 0 | 0% | ❌ |
| 数据权限 (data_permission) | 4 | 0 | 0.0% | ❌ |
| 管理维度对象映射 (dimension_object_mapping) | 0 | 0 | 0% | ❌ |
| 员工数据权限范围 (employee_data_scope) | 4 | 0 | 0.0% | ❌ |
| 过滤变体 (filter_variant) | 3 | 0 | 0.0% | ❌ |
| 用户组数据权限 (group_data_permission) | 4 | 0 | 0.0% | ❌ |
| 层级定义 (hierarchies) | 0 | 0 | 0% | ❌ |
| 菜单 (menu) | 5 | 0 | 0.0% | ❌ |
| 菜单权限 (menu_permission) | 4 | 0 | 0.0% | ❌ |
| 权限包 (permission_bundle) | 3 | 0 | 0.0% | ❌ |
| 条件权限规则 (permission_rule) | 4 | 0 | 0.0% | ❌ |
| 角色数据权限 (role_data_permission) | 3 | 0 | 0.0% | ❌ |
| 角色维度范围 (role_dimension_scope) | 4 | 0 | 0.0% | ❌ |
| 角色权限 (role_permission) | 3 | 0 | 0.0% | ❌ |
| shared_properties (shared_properties) | 0 | 0 | 0% | ❌ |

## ⚠️ 未覆盖规则 (Top 20)

- `BR-annotation-ASPECT-audit`
- `BR-annotation-VAL-category-valid`
- `BR-audit_log-SRV-ASSERT-CHECK-176`
- `BR-audit_log-SRV-ASSERT-CHECK-177`
- `BR-audit_log-SRV-ASSERT-CHECK-178`
- `BR-audit_log-SRV-ASSERT-CHECK-179`
- `BR-audit_log-SRV-ASSERT-CHECK-180`
- `BR-audit_log-SRV-ASSERT-CHECK-181`
- `BR-audit_log-SRV-ASSERT-CHECK-182`
- `BR-audit_log-SRV-ASSERT-CHECK-185`
- `BR-audit_log-SRV-ASSERT-CHECK-186`
- `BR-audit_log-SRV-ASSERT-CHECK-187`
- `BR-audit_log-SRV-ASSERT-CHECK-188`
- `BR-audit_log-SRV-ASSERT-CHECK-191`
- `BR-audit_log-SRV-ASSERT-CHECK-192`
- `BR-audit_log-SRV-ASSERT-CHECK-193`
- `BR-audit_log-SRV-ASSERT-CHECK-194`
- `BR-audit_log-SRV-ASSERT-CHECK-195`
- `BR-audit_log-SRV-ASSERT-CHECK-196`
- `BR-audit_log-SRV-ASSERT-CHECK-199`

## 📁 业务流 Spec (19 个)

- `e2e\business-flow\all-remaining.spec.js`
- `e2e\business-flow\annotation.spec.js`
- `e2e\business-flow\audit-log-extended.spec.js`
- `e2e\business-flow\audit-log.spec.js`
- `e2e\business-flow\business-object-lifecycle.spec.js`
- `e2e\business-flow\change-event.spec.js`
- `e2e\business-flow\change-subscription.spec.js`
- `e2e\business-flow\composite-and-pm.spec.js`
- `e2e\business-flow\domain.spec.js`
- `e2e\business-flow\enum-management.spec.js`
- `e2e\business-flow\import-export.spec.js`
- `e2e\business-flow\permission-extras.spec.js`
- `e2e\business-flow\permission.spec.js`
- `e2e\business-flow\product-version.spec.js`
- `e2e\business-flow\relationship.spec.js`
- `e2e\business-flow\role.spec.js`
- `e2e\business-flow\service-module.spec.js`
- `e2e\business-flow\sub-domain.spec.js`
- `e2e\business-flow\user.spec.js`
