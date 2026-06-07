# Checklist

## YAML Schema 扩展
- [x] yaml_loader.py 能正确解析 deletion_policy 段（restrict_on, cascade_delete, soft_delete）
- [x] yaml_loader.py 能正确解析 associations 段（type, through, actions）
- [x] 解析失败时给出清晰的错误提示
- [x] user.yaml 包含完整的 deletion_policy 配置
- [x] role.yaml 包含完整的 associations 配置
- [x] 修复了 restrict_on 为空时的 NoneType 错误

## DeletionService
- [x] _get_deletion_policy() 正确从 schema registry 获取策略配置
- [x] _check_restrict_rules() 对每个 restrict_on 规则执行 SQL 检查
- [x] 存在关联记录时返回违规详情列表（含表名和数量）
- [x] _hard_delete() 按 cascade_delete 列表顺序删除关联记录
- [x] _hard_delete() 最后删除主记录
- [x] 所有删除操作在同一事务中执行
- [x] 软删除模式正确更新 deleted_at 和 deleted_by 字段
- [x] 删除操作写入审计日志（action=DELETE 或 SOFT_DELETE）

## AssociationService
- [x] assign() 支持多对多关系（插入中间表）
- [x] assign() 支持一对多/多对一关系（更新外键字段）
- [x] assign() 重复分配时返回错误 "关联已存在"
- [x] unassign() 多对多关系删除中间表记录
- [x] unassign() 一对多/多对一关系设置外键为 NULL
- [x] unassign() 关联不存在时返回错误 "关联不存在"
- [x] list_members() 返回正确的关联成员列表
- [x] 所有关联操作写入审计日志（action=ASSIGN 或 REVOKE）

## API 层
- [x] association_api.py 蓝图正确注册到 Flask app
- [x] POST assign 端点返回 201 成功或 400 失败
- [x] DELETE unassign 端点返回 200 成功或 400 失败
- [x] GET list 端点返回关联成员数据
- [x] DELETE 通用删除端点支持所有实体类型
- [x] 所有端点需要认证 (@login_required)
- [x] 错误响应格式统一：{success, message, errors?, details?}

## 重构验证
- [x] user_api.py delete_user() 使用 DeletionService 后功能正常
- [x] 删除用户时自动清理 user_group_members, change_subscriptions, filter_variants, data_permissions, user_roles
- [x] role_api.py 角色分配使用 AssociationService 后功能正常
- [x] 角色分配/取消操作审计日志格式正确

## 边界场景
- [x] 删除不存在的记录返回 404
- [x] RESTRICT 策略违反时返回具体错误信息（非 500）
- [x] 并发删除同一记录的事务安全
- [x] 空的 cascade_delete 列表只删除主记录
- [x] 无 deletion_policy 配置的实体使用默认行为（仅物理删除主记录）

## 集成验证
- [x] Python 导入测试：YAML Loader ✅
- [x] Python 导入测试：DeletionService ✅
- [x] Python 导入测试：AssociationService ✅
- [x] user.yaml deletion_policy 解析成功，包含正确的 cascade_delete 列表
