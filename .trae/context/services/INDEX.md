# Services Context 注册表 (INDEX)

> **最后更新**: 2026-06-13
> **总数**: 30 services
> **覆盖策略**: 按 TBD-5 全量覆盖
> **规范**: 每个 Context doc 遵循 [.trae/context/_TEMPLATE.md](../_TEMPLATE.md) 7 节 Schema

## 注册表

### P0 - 鉴权与权限(2)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-001 | authService | 用户登录、登出、token 管理 | [authService.md](./authService.md) | ⚠️ 0% |
| SVC-002 | permissionService | 权限规则查询、角色校验 | [permissionService.md](./permissionService.md) | ⚠️ 0% |

### P0 - 核心数据模型(4)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-003 | metaService | 元数据查询与变更 | [metaService.md](./metaService.md) | ⚠️ 0% |
| SVC-004 | objectTypeService | 对象类型管理 | [objectTypeService.md](./objectTypeService.md) | ⚠️ 0% |
| SVC-005 | enumService | 枚举值管理 | [enumService.md](./enumService.md) | ⚠️ 0% |
| SVC-006 | boService | 业务对象操作 | [boService.md](./boService.md) | ⚠️ 0% |

### P1 - 业务功能(6)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-007 | filterService | 筛选器 | [filterService.md](./filterService.md) | ⚠️ 0% |
| SVC-008 | filterVariantService | 筛选变体 | [filterVariantService.md](./filterVariantService.md) | ⚠️ 0% |
| SVC-009 | annotationService | 批注管理 | [annotationService.md](./annotationService.md) | ⚠️ 0% |
| SVC-010 | hierarchyService | 层级关系 | [hierarchyService.md](./hierarchyService.md) | ⚠️ 0% |
| SVC-011 | associationService | 关联关系 | [associationService.md](./associationService.md) | ⚠️ 0% |
| SVC-012 | keyTemplateService | 关键模板 | [keyTemplateService.md](./keyTemplateService.md) | ⚠️ 0% |

### P2 - 变更与协作(5)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-013 | columnOrderService | 列顺序 | [columnOrderService.md](./columnOrderService.md) | ⚠️ 0% |
| SVC-014 | conditionExpressionService | 条件表达式 | [conditionExpressionService.md](./conditionExpressionService.md) | ⚠️ 0% |
| SVC-015 | draftPersistService | 草稿持久化 | [draftPersistService.md](./draftPersistService.md) | ⚠️ 0% |
| SVC-016 | baseService | 通用基类 | [baseService.md](./baseService.md) | ⚠️ 0% |
| SVC-017 | serviceModuleDiagramBuilder | 服务模块图构建 | [serviceModuleDiagramBuilder.md](./serviceModuleDiagramBuilder.md) | ⚠️ 0% |

### P2 - 图与转换(5)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-018 | diagramDataBuilder | 图数据构建 | [diagramDataBuilder.md](./diagramDataBuilder.md) | ⚠️ 0% |
| SVC-019 | archDataConverter | 架构数据转换 | [archDataConverter.md](./archDataConverter.md) | ⚠️ 0% |
| SVC-020 | metaTransformService | 元数据转换 | [metaTransformService.md](./metaTransformService.md) | ⚠️ 0% |
| SVC-021 | relationClassifier | 关系分类 | [relationClassifier.md](./relationClassifier.md) | ⚠️ 0% |
| SVC-022 | dataTransformer | 数据转换 | [dataTransformer.md](./dataTransformer.md) | ⚠️ 0% |

### P3 - 验证与导入(4)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-023 | dataValidator | 数据校验 | [dataValidator.md](./dataValidator.md) | ⚠️ 0% |
| SVC-024 | excelParser | Excel 解析 | [excelParser.md](./excelParser.md) | ⚠️ 0% |
| SVC-025 | zhipuValidator | 智谱 AI 校验 | [zhipuValidator.md](./zhipuValidator.md) | ⚠️ 0% |
| SVC-026 | deepseekValidator | DeepSeek AI 校验 | [deepseekValidator.md](./deepseekValidator.md) | ⚠️ 0% |

### P3 - 集成(4)

| ID | Service | 职责 | 文件 | 测试 |
|----|---------|------|------|------|
| SVC-027 | feishuService | 飞书集成 | [feishuService.md](./feishuService.md) | ⚠️ 0% |
| SVC-028 | graphqlClient | GraphQL 客户端 | [graphqlClient.md](./graphqlClient.md) | ⚠️ 0% |
| SVC-029 | DateFormatService | 日期格式化 | [DateFormatService.md](./DateFormatService.md) | ⚠️ 0% |
| SVC-030 | auditLogService | 审计日志 | [auditLogService.md](./auditLogService.md) | ⚠️ 0% |

## 维护规则

- 新增 service 时,在此 INDEX 追加一行
- 修改 service 时,更新对应 .md 的 last_updated
- 删除 service 时,标记 deprecated,等待 30 天观察期

## 相关链接

- [.trae/context/_TEMPLATE.md](../_TEMPLATE.md) — 通用模板
- [.trae/context/utilities/_TEMPLATE.md](../utilities/_TEMPLATE.md) — utilities 模板
- [.trae/skills/INDEX.md](../../skills/INDEX.md) — Skill 注册表