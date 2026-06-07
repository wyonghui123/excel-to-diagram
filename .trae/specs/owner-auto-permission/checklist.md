# Checklist

## 数据库 Schema

- [x] domains 表添加 owner_id 字段
- [x] sub_domains 表添加 owner_id 字段
- [x] service_modules 表添加 owner_id 字段
- [x] business_objects 表添加 owner_id 字段
- [x] 现有数据 owner_id 迁移完成

## 自身操作白名单

- [x] SELF_SERVICE_WHITELIST 配置完成
- [x] is_self_service() 函数实现
- [x] require_permission 装饰器支持白名单跳过
- [x] GET /api/v1/users/self 端点可用
- [x] PUT /api/v1/users/self 端点可用
- [x] 用户可修改自己的 display_name 和 email

## Owner 自动授权

- [x] _is_owner() 方法实现
- [x] has_access() 优先检查 Owner
- [x] 创建 domain 自动授权
- [x] 创建 sub_domain 自动授权
- [x] 创建 service_module 自动授权
- [x] 创建 business_object 自动授权
- [x] Owner 可访问自己创建的数据

## 测试验证

- [x] 单元测试：_is_owner() 通过
- [x] 单元测试：has_access() Owner 优先通过
- [x] 单元测试：白名单跳过权限检查通过
- [x] 集成测试：创建数据自动授权通过
- [x] 集成测试：自身操作无需权限通过
- [x] 集成测试：非自身操作仍需权限通过
