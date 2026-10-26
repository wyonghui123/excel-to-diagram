---
alwaysApply: false
description: "组件配置治理 - 元模型 + API + 枚举 + 验证"
---

# 组件配置治理（v4.0 拆分）

> **拆分自** `component-governance.md` (646 行)
> **本文件覆盖**：§配置核心原则 + §配置类型 + §验证工具 + §开发工作流
> **相关**：[component-lifecycle.md](./component-lifecycle.md)（组件生命周期）/ [component-rules.md](./component-rules.md)（治理规则）

---

## [TARGET] 核心原则（配置）

### 1. 配置契约明确化

- 配置 schema 必须明确（YAML / JSON Schema）
- 类型校验：前端 `PropTypes` + 后端 `pydantic`
- 缺失字段有明确错误信息

### 2. API 规范统一化

- 所有 API 返回统一包装：`{success, data, message}`
- 错误码统一：`UNAUTHORIZED` / `FORBIDDEN` / `NOT_FOUND` / `BAD_REQUEST`
- 分页统一：`page` / `page_size` / `total`

### 3. 验证机制完善化

- 启动时验证所有配置
- 缺失关键配置 → 启动失败
- 配置变更 → 触发 reload

### 4. 代码复用最大化

- 共享 `ConfigValidator`
- 共享 `EnumService`
- 共享 API client

---

## [PACKAGE] 配置类型与契约

### 元模型配置

```yaml
# meta/schemas/domain.yaml
- id: domain
  table: t_domain
  fields:
    - { name: id, type: int, pk: true }
    - { name: name, type: str, required: true }
    - { name: code, type: str, business_key: true }
```

### API 配置

```yaml
# config/api.yaml
endpoints:
  user_list: { method: GET, path: /api/v2/bo/user }
  user_create: { method: POST, path: /api/v2/bo/user }
```

---

## [TOOL] 配置验证工具

### ConfigValidator

```python
from meta.core.config_validator import ConfigValidator

# 启动时验证
ConfigValidator.validate_all()  # 验证所有 YAML 配置

# 运行时验证
ConfigValidator.validate_schema('domain', schema_dict)
```

### EnumService

```python
from meta.services.enum_service import EnumService

# 获取枚举选项
options = EnumService.get_options('USER_STATUS')
# 返回 [{value: 'active', label: '激活'}, ...]
```

---

## [NOTE] 开发工作流（配置）

### 创建新配置 Checklist
- [ ] YAML 格式 + Schema 校验
- [ ] EnumService 注册（如果是枚举）
- [ ] ConfigValidator 验证通过
- [ ] 文档化（字段含义 + 业务规则）

### 使用枚举 Checklist
- [ ] 不硬编码字符串
- [ ] 用 `EnumService.get_options()` 获取选项
- [ ] 缓存 5 分钟（避免频繁 IO）

### 调用 API Checklist
- [ ] 走 `httpClient` 统一入口
- [ ] 错误码统一处理
- [ ] 不直接 axios

---

## [ALERT] 常见问题

### 问题 1：枚举选项为空
- 检查 `EnumService` 是否注册
- 检查 yaml 文件路径是否在 `META_SCHEMA_DIR`
- 检查 cache 是否被清空

### 问题 2：配置不生效
- 检查 `ConfigValidator.validate_all()` 是否调用
- 检查 schema 路径
- 检查字段名拼写

### 问题 3：API 调用失败
- 检查 `httpClient` 错误码映射
- 检查认证（cookie / dev-login）
- 检查 CORS

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 component-governance 拆出配置部分 |