# MetaListV2 Component Context

> **目标文件**: `src/components/common/MetaListV2/MetaListV2.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据列表 v2。新一代列表页,采用更现代的虚拟滚动与响应式设计。

**架构位置**: MetaListPage 的下一代,渐进迁移

## 2. Props/Emit/Slot

(同 MetaListPage,但实现更新)

## 3. 调用方(依赖)

- `src/components/common/MetaTable.vue`(可能改用新表格)
- `src/components/common/FilterBar/`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 万级数据虚拟滚动
- 移动端适配

## 6. 易错点

- ⚠️ **共存**: 与 MetaListPage 共存,逐步迁移

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |