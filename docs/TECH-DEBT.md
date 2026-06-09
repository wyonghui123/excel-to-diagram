---
title: 技术债务清单
version: 1.0.0
date: 2026-06-07
status: 活跃
audience: 开发者
---

# 技术债务跟踪

本文档记录项目中所有已知的技术债务，包括状态、优先级、负责人、截止日期和解决方案。

---

## TD-001: 审计字段冗余存储

**状态**: 🔴 未解决  
**优先级**: P0  
**发现日期**: 2026-05-08  
**负责人**: TBD  
**截止日期**: TBD  

### 问题描述

在 `aspects.yaml` 中，`created_by`/`updated_by` 字段定义了 `source_of_truth: audit_logs`，表示单一事实源是审计日志。但实际实现选择了 `materialization.strategy: redundant_storage`，即在业务表中冗余存储这些字段。

**设计意图**：
```yaml
- id: created_by
  semantics:
    source_of_truth: audit_logs        # 单一事实源
    derivation:
      from: audit_logs
      rule: "user_name WHERE action = 'CREATE'"
  materialization:
    strategy: redundant_storage         # 过渡方案
    description: 冗余存储于业务表，未来可改为虚拟计算
```

**实际实现**：
- ❌ 没有实现 derivation 查询机制
- ❌ 很多业务操作没有写入 audit_logs
- ❌ `source_of_truth: audit_logs` 的设计被忽略
- ❌ "过渡方案"变成了"永久方案"

### 影响

1. **数据一致性风险**：冗余存储可能导致数据不一致
2. **违反设计规范**：`source_of_truth` 定义没有被遵守
3. **维护成本**：需要在多处维护相同的数据

### 解决方案

**Phase 1: 短期修复（已完成）**
- ✅ 实现 `DerivationExecutor` 派生字段查询引擎
- ✅ 实现 `audit_interceptor` 审计日志写入装饰器
- ✅ 实现 `MetadataValidator` 元数据验证器
- ✅ 为 `user_group_service`、`user_api`、`role_api` 添加审计日志

**Phase 2: 中期优化（计划中）**
- [ ] 为所有实体 Schema 统一引用 `audit_aspect`
- [ ] 实现 derivation 查询机制，从 audit_logs 派生 created_by/updated_by
- [ ] 前端元数据自动注入审计字段

**Phase 3: 长期目标（待评估）**
- [ ] 评估是否完全迁移到 virtual 字段模式
- [ ] 移除冗余存储，改为运行时派生

### 相关文件

- `meta/schemas/aspects.yaml` - 审计字段定义
- `meta/core/derivation_executor.py` - 派生字段查询引擎
- `meta/services/audit_interceptor.py` - 审计日志写入装饰器
- `meta/core/metadata_validator.py` - 元数据验证器

### 相关 Spec

- `audit-log-capability-enhancement` - 审计日志能力完善
- `transaction-system` - 事务系统完备性改造

---

## TD-002: 审计日志写入不完整

**状态**: 🟡 部分解决  
**优先级**: P0  
**发现日期**: 2026-05-08  
**负责人**: TBD  
**截止日期**: TBD  

### 问题描述

很多业务操作没有写入 `audit_logs` 表，导致审计日志不完整。

**已修复**：
- ✅ `user_group_service.create_group()` - 添加 @audit_log 装饰器
- ✅ `user_group_service.update_group()` - 添加 @audit_log 装饰器
- ✅ `user_group_service.delete_group()` - 添加 @audit_log 装饰器
- ✅ `user_api.create_user()` - 添加审计日志记录
- ✅ `user_api.delete_user()` - 添加审计日志记录
- ✅ `role_api.create_role()` - 添加审计日志记录
- ✅ `role_api.delete_role()` - 添加审计日志记录

**待修复**：
- [ ] 其他业务操作的审计日志

### 解决方案

使用 `@audit_log` 装饰器或 `AuditInterceptor` 类为所有业务操作添加审计日志。

### 相关文件

- `meta/services/audit_interceptor.py` - 审计日志写入装饰器
- `meta/services/async_audit_writer.py` - 异步审计日志写入器

---

## TD-003: 缺乏强制约束机制

**状态**: 🟡 部分解决  
**优先级**: P1  
**发现日期**: 2026-05-08  
**负责人**: TBD  
**截止日期**: TBD  

### 问题描述

没有代码检查验证 `source_of_truth` 的一致性，导致设计规范容易被违反。

**已实现**：
- ✅ `MetadataValidator` - 元数据验证器

**待实现**：
- [ ] 启动时自动验证
- [ ] CI/CD 集成验证
- [ ] 代码审查检查清单

### 解决方案

1. 在应用启动时运行 `MetadataValidator`
2. 在 CI/CD 流程中集成验证
3. 建立代码审查检查清单

### 相关文件

- `meta/core/metadata_validator.py` - 元数据验证器
- `.trae/rules/audit-compliance.md` - 审计合规规范

---

## 技术债务统计

| 状态 | 数量 |
|------|------|
| 🔴 未解决 | 1 |
| 🟡 部分解决 | 2 |
| ✅ 已解决 | 0 |
| **总计** | **3** |

---

## 定期回顾

### 每周回顾

- [ ] 检查所有 TD-* 状态
- [ ] 更新负责人和截止日期
- [ ] 推进解决方案

### 回顾记录

| 日期 | 回顾人 | 更新内容 |
|------|--------|----------|
| 2026-05-08 | AI Assistant | 创建技术债务跟踪文档 |

---

## 如何添加新的技术债务

1. 复制以下模板：

```markdown
## TD-XXX: [技术债务标题]

**状态**: 🔴 未解决 / 🟡 部分解决 / ✅ 已解决  
**优先级**: P0 / P1 / P2 / P3  
**发现日期**: YYYY-MM-DD  
**负责人**: [姓名]  
**截止日期**: YYYY-MM-DD  

### 问题描述

[详细描述问题]

### 影响

[描述影响]

### 解决方案

[描述解决方案]

### 相关文件

- [文件路径]

### 相关 Spec

- [Spec 名称]
```

2. 填写完整信息
3. 更新技术债务统计
4. 在定期回顾中跟踪进度
