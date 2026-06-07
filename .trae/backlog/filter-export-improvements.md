# 过滤与导出功能改进 Backlog

> 记录过滤与导出功能的改进项
>
> **最后更新**: 2026-04-25

---

## 已完成项

| 日期 | 项 | 说明 |
|------|-----|------|
| 2026-04-24 | P1.3 | 自身类型过滤自动转换 |
| 2026-04-24 | P1.1 部分 | `manage_api.py` 添加虚拟字段过滤逻辑 |
| 2026-04-24 | P1.1 部分 | `import_export_service.py` 添加层级过滤逻辑 |
| 2026-04-24 | P3.1 | `list_relationships` 支持 `domain_id` 过滤 |
| 2026-04-24 | P2.2 | 节点 ID 解析重构 |
| 2026-04-24 | P2.1 部分 | 过滤参数分维度存储 |
| 2026-04-25 | P2.1 | 过滤状态分离架构 |
| 2026-04-25 | P3.2 部分 | 关系树分类从名称比较改为 ID 比较 |
| 2026-04-25 | P3.1 扩展 | `list_relationships` 支持 `sub_domain_id` 和 `service_module_id` 过滤 |
| 2026-04-25 | TD-3 | 修复 `handleScopeChange` bug |
| 2026-04-25 | TD-1 | ✅ 移除硬编码层级链，所有代码从 `hierarchies.yaml` 读取 |
| 2026-04-25 | TD-2 | ✅ 前端过滤条件构建统一，支持从 API 获取配置 |
| 2026-04-25 | TD-4 | ✅ 关系过滤语义统一，`scope_mode` 参数支持 |
| 2026-04-25 | P2.5 | ✅ 字段控制属性统一，前后端逻辑一致 |
| 2026-04-25 | P4.1 | ✅ 元数据 API 增强，4 个新端点 |
| 2026-04-25 | P4.4 | ✅ 字段控制属性 API |
| 2026-04-25 | 测试 | ✅ 153 个测试用例（前端 43 + 后端 110） |

---

## P0 - 战略方向（暂不执行）

### P0.1: Aspects 机制

**状态**: 待处理

### P0.2: 关系类型增强

**状态**: 待处理

### P0.3: 标准化派生规则

**状态**: 待处理

---

## P1 - 虚拟字段过滤（已完成）

| 任务 | 状态 |
|------|------|
| P1.1 抽取公共虚拟字段过滤模块 | ✅ 已完成（配置驱动重构） |
| P1.2 增强虚拟字段过滤错误处理 | ✅ 已完成 |
| P1.3 自身类型过滤自动转换 | ✅ 已完成 |

---

## P2 - 前端过滤状态管理（已完成）

| 任务 | 状态 |
|------|------|
| P2.1 统一过滤状态管理 | ✅ 已完成 |
| P2.2 节点 ID 解析重构 | ✅ 已完成 |
| P2.3 过滤参数持久化 | 🔶 可选（暂不执行） |

---

## P3 - 关系过滤增强（已完成核心）

| 任务 | 状态 |
|------|------|
| P3.1 domain_id 过滤 | ✅ 已完成 |
| P3.1 扩展 sub_domain/service_module 过滤 | ✅ 已完成 |
| P3.2 关系树与列表一致性 | ✅ 已完成（通过 scope_mode） |
| P3.3 外部关系识别改进 | 🔶 可选 |

---

## P4 - 元数据驱动架构（已完成核心）

**基于 SAP One Model 和 Analytics Query View 最佳实践**

详见 `.trae/specs/metadata-driven-refactoring/spec.md`

| 任务 | 状态 | 说明 |
|------|------|------|
| P4.1 元数据 API 增强 | ✅ 已完成 | 4 个新端点 |
| P4.2 AnalyticsConfig 支持 | 🔶 可选 | 暂不执行 |
| P4.3 Aspects 机制 | 🔶 可选 | 暂不执行 |
| P4.4 字段控制属性 API | ✅ 已完成 | `/meta/objects/<type>/field_controls` |
| P4.5 context_field 导入增强 | 🔶 可选 | 暂不执行 |

---

## 技术债务（已完成）

| 任务 | 状态 |
|------|------|
| TD-1 硬编码层级链 | ✅ 已完成 |
| TD-2 重复过滤条件构建 | ✅ 已完成 |
| TD-3 名称匹配失败 | ✅ 已完成 |
| TD-4 scope_mode 语义 | ✅ 已完成 |

---

## 测试结果

| 类型 | 数量 | 状态 |
|------|------|------|
| 后端单元测试 | 110 | ✅ 全部通过 |
| 前端单元测试 | 43 | ✅ 全部通过 |
| **总计** | **153** | ✅ |

### 新增测试文件

- `meta/tests/test_meta_api.py` - 18 个 API 测试
- `meta/tests/test_cascade_service.py` - 30 个配置驱动测试
- `meta/tests/test_config_integration.py` - 13 个集成测试
- `meta/tests/test_field_controls.py` - 15 个字段控制测试
- `meta/tests/test_scope_mode.py` - 9 个 scope_mode 测试
- `src/.../__tests__/hierarchyFilterBuilder.spec.js` - 43 个前端测试

---

## 新增 API 端点

| 端点 | 说明 |
|------|------|
| `GET /api/v1/meta/hierarchies` | 获取完整层级配置 |
| `GET /api/v1/meta/hierarchies/<id>/levels` | 获取指定层级的级别定义 |
| `GET /api/v1/meta/hierarchies/config` | 获取前端专用配置格式 |
| `GET /api/v1/meta/objects/<type>/field_controls` | 获取字段控制属性 |
| `GET /api/v1/relationships?scope_mode=internal` | 关系过滤语义控制 |

---

## 待执行测试

### 手动测试清单

1. **层级过滤一致性测试**
   - [ ] 选择领域节点，关系树与列表数量一致
   - [ ] 选择子领域节点，关系树与列表数量一致
   - [ ] 选择服务模块节点，关系树与列表数量一致
   - [ ] 选择业务对象节点，关系树与列表数量一致

2. **导出测试**
   - [ ] 导出数据与前端选择一致
   - [ ] 导出包含正确的层级信息

3. **scope_mode 测试**
   - [ ] `scope_mode=involved` 返回包含外部关系
   - [ ] `scope_mode=internal` 不包含外部关系

4. **字段控制测试**
   - [ ] business_key 字段编辑时只读
   - [ ] parent_key 字段编辑时可改
   - [ ] immutable 字段编辑时只读

---

## 参考资料

- [SAP CDS View Documentation](https://help.sap.com/docs/ABAP_PLATFORM_NEW/abap-cds/abap-cds-documentation)
- [SAP Analytics Query](https://community.sap.com/t5/technology-blogs-by-sap/sap-fiori-elements-for-odata-building-analytical-list-page/ba-p/13335765)
- [元数据驱动架构重构方案](../specs/metadata-driven-refactoring/spec.md)
