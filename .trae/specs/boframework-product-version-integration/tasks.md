# Tasks: BOFramework Product/Version 架构数据管理 BO 集成

## Phase 0: 前置工作（Enrichment 统一 + DisplayName）

- [x] **Task 0.1**: Enrichment 机制统一化
  - [x] Task 0.1.1: 扩展 JoinStep dataclass（增加 fixed_conditions）
  - [x] Task 0.1.2: 新增 _parse_enum_ref 方法
  - [x] Task 0.1.3: 修改 RedundancyRegistry.build_from_registry
  - [x] Task 0.1.4: 扩展 EnrichmentEngine._build_lookup_query
  - [x] Task 0.1.5: 验证 RedundancyRegistry 正确注册 enum_type_ref（验证通过：28个字段，包括 relation_type_name）
  - [x] Task 0.1.6: Relationship enum 字段通过新机制注册（验证通过：13个 relationship 冗余字段）

- [x] **Task 0.2**: Phase 13 DisplayName 收尾
  - [x] Task 0.2.1: 验证 DisplayNameService 测试通过
  - [x] Task 0.2.2: 验证 API 响应包含新字段

---

## Phase A: 顶层 BO 适配（product + version）

- [x] **Task 1.1**: Product BO 适配
  - [x] Task 1.1.1: 确认 product.yaml 完整性（字段、关系、视图配置）
  - [x] Task 1.1.2: 确认 display_name_field: name 已配置
  - [x] Task 1.1.3: ProductVersionApp 处理 Product 管理（使用 MetaListPage）
  - [x] Task 1.1.4: 测试 Product CRUD 操作
  - [x] Task 1.1.5: deletability 规则已定义（存在 version 不能删除）
  - [x] Task 1.1.6: 单元测试覆盖

- [x] **Task 1.2**: Version BO 适配
  - [x] Task 1.2.1: 确认 version.yaml 完整性
  - [x] Task 1.2.2: 确认 display_name_field: name 已配置
  - [x] Task 1.2.3: ProductVersionApp 处理 Version 管理
  - [x] Task 1.2.4: parent_key: product_id 配置正确
  - [x] Task 1.2.5: version 列表按 product 过滤
  - [x] Task 1.2.6: 测试 Version CRUD + 层级关联
  - [x] Task 1.2.7: deletability 规则已定义
  - [x] Task 1.2.8: 单元测试覆盖

---

## Phase B: 中间层级 BO 适配（domain + sub_domain + service_module）

- [x] **Task 2.1**: Domain BO 适配
  - [x] Task 2.1.1: 确认 domain.yaml 完整性
  - [x] Task 2.1.2: 确认 display_name_field: name 已配置
  - [x] Task 2.1.3: ArchDataManageApp 处理 Domain 管理
  - [x] Task 2.1.4: parent_key: version_id 配置正确
  - [x] Task 2.1.5: domain 列表按 version 过滤
  - [x] Task 2.1.6: 测试 Domain CRUD + 层级关联
  - [x] Task 2.1.7: deletability 规则已定义
  - [x] Task 2.1.8: 单元测试覆盖

- [x] **Task 2.2**: SubDomain BO 适配
  - [x] Task 2.2.1: 确认 sub_domain.yaml 完整性
  - [x] Task 2.2.2: 确认 display_name_field: name 已配置
  - [x] Task 2.2.3: ArchDataManageApp 处理 SubDomain 管理
  - [x] Task 2.2.4: parent_key: domain_id 配置正确
  - [x] Task 2.2.5: sub_domain 列表按 domain 过滤
  - [x] Task 2.2.6: 测试 SubDomain CRUD + 层级关联
  - [x] Task 2.2.7: deletability 规则已定义
  - [x] Task 2.2.8: 单元测试覆盖

- [x] **Task 2.3**: ServiceModule BO 适配
  - [x] Task 2.3.1: 确认 service_module.yaml 完整性
  - [x] Task 2.3.2: 确认 display_name_field: name 已配置
  - [x] Task 2.3.3: ArchDataManageApp 处理 ServiceModule 管理
  - [x] Task 2.3.4: parent_key: sub_domain_id 配置正确
  - [x] Task 2.3.5: service_module 列表按 sub_domain 过滤
  - [x] Task 2.3.6: 测试 ServiceModule CRUD + 层级关联
  - [x] Task 2.3.7: deletability 规则已定义
  - [x] Task 2.3.8: 单元测试覆盖

---

## Phase C: 底层 BO 适配（business_object + relationship）

- [x] **Task 3.1**: BusinessObject BO 适配
  - [x] Task 3.1.1: 确认 business_object.yaml 完整性
  - [x] Task 3.1.2: 确认 display_name_field: name 已配置
  - [x] Task 3.1.3: ArchDataManageApp 处理 BusinessObject 管理
  - [x] Task 3.1.4: parent_key: service_module_id 配置正确
  - [x] Task 3.1.5: business_object 列表按 service_module 过滤
  - [x] Task 3.1.6: 测试 BusinessObject CRUD + 层级关联
  - [x] Task 3.1.7: deletability 规则已定义
  - [x] Task 3.1.8: 单元测试覆盖

- [x] **Task 3.2**: Relationship BO 完整集成
  - [x] Task 3.2.1: RedundancyRegistry 正确注册 Relationship enum 字段（13个冗余字段）
  - [x] Task 3.2.2: Generic query flow 支持 relationship enum 填充
  - [x] Task 3.2.3: relation_type_name、annotation_category_name 通过新机制注册
  - [x] Task 3.2.4: 集成测试覆盖

---

## Phase D: 增强功能（Excel 导入导出）

- [x] **Task 4.1**: Excel 导入导出
  - [x] Task 4.1.1: Product Excel 导入导出（product.yaml import_export 配置完整）
  - [x] Task 4.1.2: Version Excel 导入导出（含层级关系）
  - [x] Task 4.1.3: Domain Excel 导入导出（含层级关系）
  - [x] Task 4.1.4: BusinessObject Excel 导入导出

---

## 验证与收尾

- [x] **Task 5.1**: 回归测试
  - [x] Task 5.1.1: 86个核心测试全部通过
  - [x] Task 5.1.2: BOFramework DisplayName + Enrichment 机制验证通过

- [x] **Task 5.2**: 文档更新
  - [x] Task 5.2.1: 已更新研究报告和实施计划文档

---

## Task Dependencies

```
Task 0.1 (Enrichment 统一) ──→ 所有后续 Task
Task 0.2 (DisplayName) ───────→ 所有后续 Task
Task 1.1 (Product) ───────────→ Task 1.2 (Version)
Task 1.2 (Version) ───────────→ Task 2.1 (Domain)
Task 2.1 (Domain) ────────────→ Task 2.2 (SubDomain)
Task 2.2 (SubDomain) ─────────→ Task 2.3 (ServiceModule)
Task 2.3 (ServiceModule) ─────→ Task 3.1 (BusinessObject)
Task 3.1 (BusinessObject) ───→ Task 3.2 (Relationship)
Task 3.2 (Relationship) ──────→ Task 4.1 (Excel)
```