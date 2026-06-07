# 权限模型统一语义迁移检查清单

## Phase 1: 准备阶段

- [x] 数据库已完整备份
- [x] 备份文件已验证完整性
- [x] MetaAction Schema 文件已创建
- [x] Permission Schema 文件已更新
- [x] 新字段定义完整（action_id, action_code, resource_id, scope）

## Phase 2: 数据库迁移

- [x] meta_actions 表已创建
- [x] 标准动作数据已插入（create, read, update, delete, export, import, approve, list, search）
- [x] permissions 表新字段已添加
- [x] 权限数据已迁移（action_id 和 action_code 已填充）
- [x] 索引已创建（idx_permission_action, idx_permission_resource_action, idx_meta_action_code）
- [x] 迁移脚本执行无错误
- [x] 数据验证通过（记录数正确）

## Phase 3: 服务层升级

- [x] PermissionService 已升级
- [x] get_permission_by_resource_and_action() 方法已实现
- [x] check_permission_unified() 方法已实现
- [x] create_permission_unified() 方法已实现
- [x] MetaActionService 已创建
- [x] 权限检查中间件已升级
- [x] @require_permission_unified() 装饰器已实现

## Phase 4: API 层升级

- [x] 权限检查 API 已升级
- [x] 支持新参数（resource_type, action_code）
- [x] 支持旧参数（permission_code）
- [x] 返回模式标识（unified/legacy）
- [x] MetaAction API 已创建
- [x] GET /api/v1/meta-actions 端点已实现
- [x] 权限管理 API 已升级

## Phase 5: 兼容性保障

- [x] 双模式支持已实现
- [x] 旧 API 参数正常工作
- [x] 新 API 参数正常工作
- [x] 混合参数场景正常工作
- [x] 配置项已添加

## Phase 6: 测试验证

- [x] MetaActionService 单元测试通过
- [x] PermissionService 单元测试通过
- [x] 统一语义权限创建测试通过
- [x] 统一语义权限检查测试通过
- [x] 双模式切换测试通过
- [x] 数据库迁移集成测试通过
- [x] 数据完整性测试通过
- [x] 权限检查中间件测试通过
- [x] 回归测试通过
- [x] 性能测试通过

## Phase 7: 文档更新

- [x] API 文档已更新
- [x] MetaAction API 文档已添加
- [x] 迁移指南已添加
- [x] 权限模型文档已更新
- [x] 统一语义使用指南已添加
- [x] 最佳实践示例已添加

## 最终验证

- [x] 所有现有权限功能正常工作
- [x] 新的统一语义功能正常工作
- [x] 向后兼容性验证通过
- [x] 性能无明显下降
- [x] 无数据丢失
- [x] 无安全漏洞引入
- [x] 代码审查通过
- [x] 文档审查通过
