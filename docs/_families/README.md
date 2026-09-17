# 家族失败模式库 (Family Failure Modes)

> 跨多次事故的"家族失败模式"沉淀, 而非单点 bug 复盘。
>
> 与 `retrospectives/` 的区别: `retrospectives/` 记录**单次事故** (时序 + 修复),
> `_families/` 抽象**多事故同源**的模式 + 跨时间复发跟踪 + 防再发 SOP。

---

## 什么是"家族失败模式"

家族失败模式 (Family Failure Mode) = 多个根因 + 多个症状 + 跨时间复发的一组相关问题。

**示例**:
- 个体 bug: `crud_create 返回 instance_scope 而非 object` (今天 9-16 看到的现象)
- 家族失败模式: **任何能让 server 加载老代码的因素** (symlink 错指 / loader 绕过 / 缓存 / lazy import)

家族 = 多个根因 + 多个症状 + 跨时间复发。

---

## 索引

| ID | 名称 | 状态 | 创建日期 |
|---|---|---|---|
| [F001](./families/F001-stale-loader.md) | Stale Loader — server 加载老代码 | ✅ 治本 (2026-09-16) | 2026-09-16 |

更多家族待发现。

---

## 库使用指南

### 何时查库

1. **事故复盘时**: 看当前 bug 属于哪个家族, 是否已有 SOP
2. **新人入职时**: 读 `README.md` (30分钟) + 浏览所有家族 (1小时)
3. **PR review 时**: 看"复发历史" + "防再发 SOP"
4. **新家族发现时**: 标准化入库 (见 `_families/template.md`)

### 如何报告新家族

1. 复制 `_families/template.md` 到 `families/FXXX-name.md`
2. 填症状 / 根因层 / 复发历史 / 防再发 / 相关工具
3. 在本 README 索引里加一行
4. commit

### 防"库腐烂"

- 每个家族必须有 **复发历史表格** (至少 1 行)
- 防再发 SOP 必须指向 **真实工具** (不能空泛)
- 每半年 review 一次, 删掉过时的家族

---

## 库与现有文档的关系

| 文档 | 视角 | 时效 |
|---|---|---|
| `retrospectives/<date>-*.md` | 单次事故 | 永久 (历史) |
| `_families/families/FXXX-*.md` | 跨事故抽象 | 滚动 (随家族演化) |
| `spec.md` | 业务规范 | 永久 (稳定) |
| `DEPLOY_HANDOVER_*.md` | 部署交接 | 单次 (用完即弃) |

---

## 库维护人

主理: dev agent (按事故复盘触发维护)
复核: PM (定期 review 防库腐烂)