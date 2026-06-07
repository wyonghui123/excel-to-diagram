# Tasks

- [x] Task 1: 扩展 archDataStore 共享状态
  - [x] 在 archDataStore.js 中新增 selectedDomains、selectedSubDomains、relationScopeSelection 状态
  - [x] 添加 selectedDomains 的 getter 和 setter
  - [x] 添加 relationScopeSelection 的 getter 和 setter
  - [x] 确保 Tab 切换时状态不丢失

- [x] Task 2: 创建 useRelationScopeTree composable
  - [x] 实现关系范围树数据结构定义（RelationScopeNode）
  - [x] 实现 buildRelationScopeTree 算法：基于选中领域筛选关系
  - [x] 实现关系分类逻辑：中心范围/跨领域/同领域跨子域/同子域跨服务模块
  - [x] 实现逐级展开子树生成：领域对 → 子领域对 → 服务模块对
  - [x] 实现节点关系数量统计计算
  - [x] 实现选择状态管理：勾选/取消勾选节点

- [x] Task 3: 创建 RelationScopeTree 组件
  - [x] 实现树形渲染：支持展开/折叠
  - [x] 实现节点选择：checkbox 勾选
  - [x] 实现上下文提示：顶部显示"📌 基于选择: X、Y"
  - [x] 实现空状态引导：未选择领域时显示"⚠️ 请先在层级数据中选择领域"
  - [x] 实现默认展开策略：只展开第一层
  - [x] 实现节点右键菜单：查看源对象/查看目标对象

- [x] Task 4: 修改 TreeNavigator 组件
  - [x] 添加领域选择状态持久化（与 archDataStore.selectedDomains 同步）
  - [x] 添加底部"查看这些领域的关系"快捷按钮
  - [x] 按钮在有选择时启用，无选择时禁用

- [x] Task 5: 重构 index.vue 左侧面板
  - [x] 将 TreeNavigator 和 DynamicFilter 的 v-if 切换改为 v-show
  - [x] 替换 DynamicFilter 为 RelationScopeTree
  - [x] 确保左侧面板宽度可拖拽调整功能正常
  - [x] 确保 Tab 切换时两个组件都保持挂载状态

- [x] Task 6: 实现跨 Tab 联动交互
  - [x] 领域树选择变化时触发关系范围树重新生成
  - [x] "查看关系"按钮点击时切换到业务关系 Tab
  - [x] 关系范围树节点右键"查看源/目标对象"跳转到层级数据 Tab
  - [x] 关系范围树选择变化时更新右侧关系列表过滤

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 3, Task 4]
- [Task 6] depends on [Task 5]
