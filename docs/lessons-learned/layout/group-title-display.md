# 问题解决经验记录

## 2026-04-05：分组标题显示问题

### 问题描述

当父分组（如"供应链云"）被禁用时，子分组（如"供应链计划"）的容器标题应该显示父分组名称，格式为"子分组（父分组）"。

### 问题根因

1. **ID 不匹配**：
   - 用户配置 ID：`group_xxx`（UI 生成的临时 ID）
   - 架构数据 ID：`D_供应链云`（业务数据 ID）
   - 导致 `mergeUserGroup` 失败

2. **扁平化 vs 嵌套结构冲突**：
   - `GroupModel.toMermaidConfig()` 输出扁平化结构
   - 用户配置是嵌套结构（包含 children、directNodes）
   - 简单替换会导致服务模块图丢失节点分配信息

3. **filterGroupModelByScope 的副作用**：
   - `finalBoCodes` 是业务对象编码集合
   - 服务模块图的终端节点是服务模块，不是业务对象
   - 导致服务模块图的所有分组被错误地过滤掉

### 解决方案

1. 采用方案 D-2：将 `titleMap` 应用到 `effectiveLayoutControlConfig`
2. 跳过服务模块图的 `filterGroupModelByScope` 调用
3. 使用用户配置的嵌套结构作为 `layoutControlConfig`

### 关键经验

#### 1. 跨模块通信时 ID 对齐是常见陷阱
不同模块可能使用不同的 ID 生成策略，需要建立 ID 映射或使用共同的可识别字段（如 elementCode）。

#### 2. 轻量方案可能掩盖更深层问题
当简单修复无效时，问题可能不在表面，需要追踪完整数据流找到根本原因。

#### 3. 日志添加要有针对性
避免大量无目的的日志，关键节点：函数入口、出口、数据转换点。

#### 4. 注意数据的来源和类型
- 嵌套结构 vs 扁平结构
- ref vs 普通变量（容易忘记 .value）
- undefined vs null（检查逻辑可能不同）

#### 5. 过滤函数要有类型意识
filterGroupModelByScope 假设终端类型是 businessObject，但服务模块图的终端类型是 serviceModule，导致错误的过滤结果。

#### 6. 验证环境一致性
日志显示 empty array 可能是因为：
1. 真的为空
2. 不同调用/不同作用域混在一起
3. 缓存问题

### 技术债务

1. 清理所有调试日志
2. 重构 filterGroupModelByScope 支持不同图表类型
3. 考虑统一业务对象图和服务模块图的数据流
