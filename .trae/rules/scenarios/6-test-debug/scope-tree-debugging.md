﻿﻿﻿﻿﻿﻿﻿# 领域树过滤调试经验

> 最后更新: 2026-06-30 | 来源: 领域过滤 Bug 排查

## 铁律: originalId 是 DB 主键，不同表会碰撞

RelationScopeTree 的 treeData 中，originalId 直接取自各实体表的 DB 主键:

| 节点类型 | originalId 来源 | 表 |
|----------|----------------|-----|
| domain | domain.id | domain 表 |
| sub_domain | subDomain.id | sub_domain 表 |
| service_module | module.id | service_module 表 |
| business_object | businessObject.id | business_object 表 |

这四张表独立自增，ID 值会碰撞。例如 originalId=347 既是 sub_domain"项目过程"，也是 service_module"现金流预测"。

## 高危函数: hierarchyMap 构建

RelationScopeTree.vue 的 hierarchyMap computed 用 originalId 作为 key。

### 错误: if (!map[oid]) 对所有类型先到先得

- sub_domain 先写入 -> 其 domainId 被记录
- 同 ID 的 service_module 后到达 -> 被跳过，无法写入正确 domainId
- 后果: SM->domain 推导出错，effectiveDomainIds 膨胀

### 正确策略

- domain: 先到先得
- sub_domain: 先到先得
- service_module: 始终覆盖 (可能与 sub_domain ID 碰撞)
- business_object: 始终覆盖 (同理)

```js
if (node.type === 'service_module') {
  map[oid] = { domainId, subDomainId, serviceModuleId: oid }  // ALWAYS overwrite
}
```

## 另一个高危点: buildHierarchyFilterParams

hierarchyService.js 中 effective 优先 (非 selected 优先):
effective = selected + SM推导(含跨域) -> 必须进入 API 过滤参数

```js
if (typeScope.effective.length > 0) {
  filters.id__in = typeScope.effective.join(',')
}
```

## 快速排查方法

1. console 检查 combinedFilters.id__in
2. 找到多出来的 domainId
3. 反查 hierarchyMap[smId].domainId
4. 检查该 SM 的 originalId 是否和某个 sub_domain 碰撞

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-30 | AI Assistant | 记录领域过滤排查经验 |