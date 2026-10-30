# B4 条件折扣：属性条件载体 + 客户组维度（T2.3 设计说明）

> 日期: 2026-10-30 · 范围: SO Wave3 · 对应迁移: `v153__pricing_customer_group_dimension.py`

## 结论

1. **属性条件的载体 = 键表因子扩展，不新增 `conditions` json 列。**
   一条属性条件折扣 = `key_schemas.key_fields` 里的一个因子（因子本身登记在
   `factor_catalogs`）。查找序列按槽位逐级匹配，属性条件因此天然复用了
   「槽位顺序 + 命中即停」的既有语义，不引入第二套匹配引擎。
   理由：v130（客户）、v152（组织）已用同一模式落地；再加一列会形成
   「键表 / conditions 双真源」，且 conditions 无法参与 `_matches` 的确定性排序与回放。
2. **首批只落 `customer_group_id`**（客户组，取自 `party_relations.group_id`）。
   物料组、客户地区等同类维度是**后续扩展点**：按同一模式追加
   `factor_catalogs` 因子 + `key_schemas` 键表 + 序列槽位即可，**不需要改本迁移**，
   也不需要改动定价算法。
3. **客户组只决定候选命中。** 组价记录落在 group 槽；折扣/附加费仍按
   `rate_type` 独立查表（W2-C），组维度不改变「同一 rate_type 一张表」的口径。
4. **数量段归阶梯。** 数量条件不塞进键表，仍由 `rate_record.scale`
   + `scale_semantic`（FR-009）在记录选定后定档。
5. **抬头折扣与附加费互斥沿用 v140 口径**，本批不触碰。

## 槽位口径

`LK_ITEM_CUST` 迁移后应为（org 槽来自 v152）：

```
seq1 KS_ORG_CUST_ITEM  (org_id, customer_account_id, item_id)
seq2 KS_GROUP_ITEM     (customer_group_id, item_id)      ← 本次新增
seq3 KS_ITEM_CUST      (customer_account_id, item_id)
seq4 KS_ITEM           (item_id)
```

- 任一因子在本行无值（如客户不属于任何组）⇒ 该槽位置 `None`，引擎跳过该槽，
  **顺序不变**，自然落回更粗的槽位（零回归）。
- 组槽位于客户槽**之前**，故「组价 > 客户价」；组织槽仍在最前，故
  「组织客户价 > 组价 > 客户价 > 物料价」，与 v152 的组织优先级一致。

## 服务注入

`pricing_determination_service._slot_keys` 的因子值表新增
`customer_group_id`：当 `customer_account_id` 非空时，
`customer_accounts JOIN party_relations` 取 `party_relations.group_id`；
查询失败、无关系、无组均返回 `None`（该槽跳过，不阻断取价）。

## 非目标（明确不做）

- 不改 `customer_account.yaml` / `party_relation.yaml`，不新增业务字段、不改表列；
- 不迁移 / 回填 / seed `rate_records` 业务数据；
- 不引入 `conditions` json 列；
- 不动前端。
