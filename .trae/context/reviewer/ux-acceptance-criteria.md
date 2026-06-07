# UE验收标准

## 通用UE验收

| 验收项 | 标准 |
|--------|------|
| 消息通知 | 使用 useMessage()，禁止 alert() |
| 操作反馈 | 所有CRUD操作有成功/失败反馈 |
| 加载状态 | 异步操作显示loading |
| 空状态 | 数据为空时有友好提示 |
| 错误状态 | 错误信息包含原因和解决方案 |

## UI规范验收（重要！）

| 验收项 | 标准 | 参考文档 |
|--------|------|---------|
| Tab导航 | 使用底部指示线，不使用填充背景 | [UI_COMPONENT_GUIDELINES.md](../../docs/UI_COMPONENT_GUIDELINES.md#21-tab-导航) |
| 侧边导航 | 使用左侧指示线，不使用背景填充 | [UI_COMPONENT_GUIDELINES.md](../../docs/UI_COMPONENT_GUIDELINES.md#22-侧边导航) |
| 文本颜色 | 主要内容用primary，次要内容用secondary，辅助内容用tertiary | [UI_COMPONENT_GUIDELINES.md](../../docs/UI_COMPONENT_GUIDELINES.md#23-文本颜色使用) |
| 滚动条 | 使用浏览器默认滚动条，禁止全局自定义 | [UI_COMPONENT_GUIDELINES.md](../../docs/UI_COMPONENT_GUIDELINES.md#24-滚动条) |
| 设计令牌 | 所有颜色、间距、字体使用CSS变量，禁止硬编码 | [variables.scss](../../src/styles/variables.scss) |
| 组件复用 | Tab用AppTabs，侧边导航用AppSideNav，日志用AuditLog | [index.js](../../src/components/common/index.js) |

## PM场景UE验收

| 验收项 | 标准 |
|--------|------|
| 范围选择 | PM能快速选择"我负责的领域" |
| 范围边界 | 清晰区分"范围内"和"范围外" |
| 关系展示 | 关系类型（依赖/调用/数据/流程）可区分 |
| 汇报友好 | 图表可导出为图片 |

## 交互设计5原则验收

1. **简洁明了**：操作步骤不超过5步
2. **权限透明**：用户能清晰看到自己的权限范围
3. **错误友好**：错误信息包含原因和解决方案
4. **操作可逆**：危险操作需二次确认
5. **响应式**：图表支持缩放和拖拽
