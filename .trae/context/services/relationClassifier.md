# relationClassifier Context

> **目标文件**: `src/services/relationClassifier.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关系分类器。基于规则或 ML 模型对关系进行分类(强/弱/依赖/继承等)。

**架构位置**: P2 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `classify` | `(source, target, context) => RelationType` | 分类 |
| `classifyBatch` | `(pairs) => RelationType[]` | 批量分类 |
| `getConfidence` | `(relation) => number` | 置信度 |
| `explain` | `(relation) => Explanation` | 可解释性 |

## 3. 调用方

预期:
- `src/components/AADiagramApp.vue`(自动分类)
- `src/components/MermaidComponent.vue`
- `src/services/archDataConverter.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 模糊关系
- 多类型混合
- 上下文不足
- 低置信度处理

## 6. 易错点

- ⚠️ **降级策略**: 低置信度需人工 review
- ⚠️ **模型更新**: ML 模型版本管理
- ⚠️ **可解释性**: 必须能解释分类依据

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |