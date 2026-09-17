# BUG-V048d: 对象范围 chip 双重计数 (141→282)

> 日期: 2026-07-09 | 修复者: AI Assistant | 状态: 已修复并验证

## 问题

在关系管理页面，勾选"供应链云" domain 时，对象范围 chip 显示 282 (=141×2) 而非 141。

## 根因

`RelationScopeTree.vue` 的 `hierarchyMap` computed 在遍历树构建 id→parent 映射时，service_module 条目会**始终覆盖**同 originalId 的 sub_domain 条目（代码注释写"SM/BO → 始终覆盖"）。

数据中存在 **51 个 SD/SM 共享 originalId** 的情况（如 SD 299 "供应链协同" 和 SM 299 "协同服务"），导致：

1. SD 299 (供应链云 2200) 的 `hmap[299] = {domainId: 2200, subDomainId: 299}` 先写入
2. SM 299 (协同云 2202) 的 `hmap[299] = {domainId: 2202, subDomainId: 326, serviceModuleId: 299}` 覆盖
3. SD loop 中 `selectedDomainSet.has(info.domainId)` 检查 domainId=2202 ≠ 2200 → 失败
4. SD 未被跳过 → domain 141 + SD 141 = 282

供应链云的 5 个 SD 全部被不同 domain 的 SM 覆盖：
- SD 297→hmap_domainId=2205, SD 299→2202, SD 302→2204, SD 339→2205, SD 343→2205

## 修复

新增两个**独立**的 computed，直接从 `treeData` 构建，不走 hierarchyMap：

1. `sdDomainMap`: SD originalId → domain originalId（只遍历 domain→SD 层级）
2. `smParentMap`: SM originalId → {domainId, subDomainId}（只遍历 domain→SD→SM 层级）

`selectedBoCount` 改用这两个新映射替代 `hierarchyMap`。

`hierarchyMap` 保留未删除，仍被 `effectiveDomainIds`/`effectiveSubDomainIds`/`effectiveServiceModuleIds` 使用。

## 诊断方法

1. Python 脚本 (`diag_282.py`) 从 3018 API 获取 domain/SD/SM 数据
2. 模拟 hierarchyMap 构建和 selectedBoCount 计算
3. 发现 51 个 ID 碰撞，供应链云 5 个 SD 全部被覆盖
4. 用 V048d 的 sdDomainMap/smParentMap 验证 → 所有 domain selectedBoCount 正确

## 验证

- Python 诊断脚本：供应链云 computed_total=141（不再 282）
- Playwright 浏览器测试：Badge 显示 `141 对象`（不再 `282 对象`）
- 所有 13 个 domain 的 selectedBoCount 均正确

## 教训

1. **ID 碰撞风险**：不同类型实体（SD/SM）共享 same ID 时，单 Map 方案必然碰撞
2. **"先到先得/始终覆盖"策略不够**：需要按使用场景分离映射，而非一个 Map 服务所有场景
3. **诊断优先**：用 API 数据 + 脚本模拟比在浏览器 console 挣扎高效得多
4. **V048→V048b→V048c→V048d 的迭代教训**：前三个修复都只处理了症状（normalizeId、去重），没有找到根因（hierarchyMap 碰撞）
