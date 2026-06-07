# Checklist: BOFramework Product/Version 架构数据管理 BO 集成

## Phase 0: 前置工作

### Enrichment 机制统一化

- [x] JoinStep dataclass 扩展 fixed_conditions 字段
- [x] _parse_enum_ref 方法正确解析 semantics.enum_type_ref
- [x] RedundancyRegistry 同时注册 redundancy 和 enum_type_ref 字段
- [x] EnrichmentEngine._build_lookup_query 支持固定条件
- [x] manage_api.py EnumJoinBuilder 硬编码保持兼容（EnumJoinBuilder 独立运行，不依赖 RedundancyRegistry）
- [x] Relationship 列表 enum 字段通过 RedundancyRegistry 注册（28个字段，包含 relation_type_name）
- [x] 62 个现有测试全部通过

### Phase 13 DisplayName

- [x] DisplayNameService 后端测试通过
- [x] DisplayNameService 前端测试通过
- [x] API 响应包含 display_name_field
- [x] API 响应包含 field_display_names
- [x] API 响应包含 relation_displays

## Phase A: 顶层 BO

### Product BO

- [x] product.yaml 字段定义完整
- [x] product.yaml display_name_field: name 已配置
- [x] ProductVersionApp 处理 Product 管理
- [x] Product CRUD 操作正常
- [x] deletability 规则生效（存在 version 不能删除）
- [x] Product 单元测试通过

### Version BO

- [x] version.yaml 字段定义完整
- [x] version.yaml display_name_field: name 已配置
- [x] version.yaml parent_key: product_id 配置正确
- [x] ProductVersionApp 处理 Version 管理
- [x] Version CRUD 操作正常
- [x] 层级关联正确（version → product）
- [x] 列表按 product 过滤正常
- [x] deletability 规则生效
- [x] Version 单元测试通过

## Phase B: 中间层级 BO

### Domain BO

- [x] domain.yaml 字段定义完整
- [x] domain.yaml display_name_field: name 已配置
- [x] domain.yaml parent_key: version_id 配置正确
- [x] ArchDataManageApp 处理 Domain 管理
- [x] Domain CRUD 操作正常
- [x] 层级关联正确（domain → version → product）
- [x] 列表按 version 过滤正常
- [x] deletability 规则生效
- [x] Domain 单元测试通过

### SubDomain BO

- [x] sub_domain.yaml 字段定义完整
- [x] sub_domain.yaml display_name_field: name 已配置
- [x] sub_domain.yaml parent_key: domain_id 配置正确
- [x] ArchDataManageApp 处理 SubDomain 管理
- [x] SubDomain CRUD 操作正常
- [x] 层级关联正确
- [x] 列表按 domain 过滤正常
- [x] deletability 规则生效
- [x] SubDomain 单元测试通过

### ServiceModule BO

- [x] service_module.yaml 字段定义完整
- [x] service_module.yaml display_name_field: name 已配置
- [x] service_module.yaml parent_key: sub_domain_id 配置正确
- [x] ArchDataManageApp 处理 ServiceModule 管理
- [x] ServiceModule CRUD 操作正常
- [x] 层级关联正确
- [x] 列表按 sub_domain 过滤正常
- [x] deletability 规则生效
- [x] ServiceModule 单元测试通过

## Phase C: 底层 BO

### BusinessObject BO

- [x] business_object.yaml 字段定义完整
- [x] business_object.yaml display_name_field: name 已配置
- [x] business_object.yaml parent_key: service_module_id 配置正确
- [x] ArchDataManageApp 处理 BusinessObject 管理
- [x] BusinessObject CRUD 操作正常
- [x] 层级关联正确（BO → service_module → sub_domain → domain → version → product）
- [x] 列表按 service_module 过滤正常
- [x] deletability 规则生效
- [x] BusinessObject 单元测试通过

### Relationship BO

- [x] Relationship 列表 relation_type_name 通过 RedundancyRegistry 注册
- [x] Relationship 列表 annotation_category_name 通过 RedundancyRegistry 注册
- [x] Generic query flow 支持 relationship enum 填充
- [x] Relationship 集成测试通过

## Phase D: Excel 导入导出

- [ ] Product Excel 导入正常
- [ ] Product Excel 导出正常
- [ ] Version Excel 导入（含 product 层级关系）
- [ ] Version Excel 导出正常
- [ ] Domain Excel 导入（含 version 层级关系）
- [ ] Domain Excel 导出正常
- [ ] BusinessObject Excel 导入（含 service_module 层级关系）
- [ ] BusinessObject Excel 导出正常
- [ ] 导入时层级关系正确维护
- [ ] Excel 导入导出集成测试通过

## 回归测试

- [ ] 现有 BO（user/role/user_group/enum）功能不受影响
- [ ] 62 个现有测试全部通过
- [ ] 端到端测试：创建完整层级 Product → Version → Domain → SubDomain → ServiceModule → BusinessObject
- [ ] 删除层级数据 deletability 规则正确生效

## 文档

- [ ] 架构数据管理文档更新
- [ ] BOFramework 使用指南更新