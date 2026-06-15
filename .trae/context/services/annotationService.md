# annotationService Context

> **目标文件**: `src/services/annotationService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

批注管理。在数据模型上添加/查询/回复批注,支持 @mention、附件、解决状态。

**架构位置**: P1 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `listAnnotations` | `(target) => Promise<Annotation[]>` | 列出批注 |
| `createAnnotation` | `(data) => Promise<Annotation>` | 创建 |
| `replyAnnotation` | `(parentId, data) => Promise<Annotation>` | 回复 |
| `resolveAnnotation` | `(id) => Promise<void>` | 标记已解决 |
| `deleteAnnotation` | `(id) => Promise<void>` | 删除 |

## 3. 调用方

预期:
- `src/components/common/ObjectPage/*`
- `src/components/ValidationPanel.vue`(问题批注)
- `src/components/MermaidComponent.vue`(图节点批注)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- @mention 用户解析
- 附件上传
- 嵌套回复层级
- 已解决批注的展示
- 批提及未读数

## 6. 易错点

- ⚠️ **实时性**: 批注通常需推送/WebSocket 更新
- ⚠️ **mention 通知**: 必须触发通知
- ⚠️ **删除权限**: 仅创建者或管理员可删

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |