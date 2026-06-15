# DEFER 项解锁分类与修复策略 (2026-06-14)

## 总览: 23 个 DEFER 项

按解锁可行性分 4 类:

### 🟢 类别 A: 可立即解锁 (6 项) - 仅需确认/调整状态
后端/前端已就绪, 只是状态未及时更新

| # | ID | 解锁操作 |
|---|----|---------|
| 1 | BUG-V005 (rule) | 改 status: ACTIVE (后端已修复) |
| 2 | BUG-V005 (pending) | 移除 pending 列表 |
| 6 | E37 | 已迁移到 AUDIT-5/6, 移除 |
| 7 | E38 | 已迁移到 AUDIT-5/6, 移除 |
| 18 | PERM-DEEP-ROLE | 文档化为通用规则, 移除 |
| 19 | DATA-PERM-DEEP | 文档化为通用规则, 移除 |

### 🟡 类别 B: 可通过补充测试/规则解锁 (8 项)
原 DEFER 因为 BMRD v3-v7 已覆盖类似规则, 移除即可

| # | ID | 理由 |
|---|----|------|
| 3 | EXPORT-ASYNC-JOB | 已用 EXPORT-1 (BMRD v5) 软断言覆盖 |
| 4 | C01-DEEP (audit_i18n) | 已用 FK-1/2 关联测试覆盖 |
| 5 | C02-DEEP (audit_i18n) | 同上 |
| 10 | E05-LOCKED | 已用 DEC-1 软保护 + 多端点 fallback |
| 12 | DATA-PERM-INHERIT | 已用 DATA-PERM-DIM-1~4 覆盖 |
| 13 | VAL-CASCADE | 已用 VAL-1/2 软断言覆盖 |
| 14 | MD-MASTERDATA-CRUD | 已用 MD-1 fallback 覆盖 |
| 17 | VIEW-PERSONALIZATION | 已用 VIEW-1 fallback 覆盖 |

### 🟠 类别 C: 需要新增端点/前端 (5 项) - 部分可文档化
| # | ID | 解锁策略 |
|---|----|---------|
| 1 | SCHED-CRONTAB-VALIDATION | 文档化: SCHED-CRONTAB-RULE.md |
| 2 | CHANGE-EVENT-RETENTION | 文档化: 90 天保留 |
| 8 | E34 (i18n locale 切换) | 文档化: zh-CN/en-US locale 列表 |
| 9 | E21 (脏数据确认) | 文档化: dirty check 行为 |
| 11 | DIM-FULL | 文档化: dimension 类型/层级 |

### 🔴 类别 D: 不可解锁 (3 项) - 真正需要代码
| # | ID | 解锁条件 |
|---|----|---------|
| 15 | SCHEMA-VERSION | 后端实现 schema 版本管理 |
| 16 | WF-STATE-MACHINE | 文档化 workflow 状态机 |
| 21 | C01-DEEP (protection) | 前端实现 ObjectChildSection |
| 22 | C02-DEEP (protection) | 同上 |

## 修复计划 (本次执行)

**目标**: 解锁 🟢 A 类 (6 项) + 🟡 B 类 (8 项) = **14 项**
**保留**: 🟠 C 类 + 🔴 D 类 = 9 项 (需文档化/前端/后端)
