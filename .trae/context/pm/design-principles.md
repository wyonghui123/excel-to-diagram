# 交互设计原则

> 来源：docs/auth-user-interaction-design.md 中定义的5条原则

## 原则1：简洁明了

- 界面元素最小化，只展示当前任务需要的信息
- 操作步骤不超过5步
- 复杂操作提供分步引导

## 原则2：权限透明

- 用户能清晰看到自己的权限范围
- 无权限操作给出明确提示和引导
- 权限变更实时反映

## 原则3：错误友好

- 所有错误信息使用 message 服务（禁止 alert()）
- 错误信息包含原因和解决方案
- 操作可撤销的提供撤销入口

## 原则4：操作可逆

- 危险操作（删除等）需二次确认
- 提供撤销/回退机制
- 批量操作支持部分回滚

## 原则5：响应式

- 适配不同屏幕尺寸
- 关键操作在移动端可用
- 图表支持缩放和拖拽

## 消息通知规范

```javascript
import { useMessage } from '@/composables/useMessage'
const message = useMessage()

message.success('操作成功')
message.error('错误信息')
message.warning('警告信息')
message.info('提示信息')
```

## 导出功能规范

- 导出列名优先使用字段的 ui.title 配置
- 版本/产品线列通过 default_exclude_fields 排除
- 层级相关字段（父对象_name）不导出，通过 hierarchy_fields 排除
- Virtual字段如需导出，需设置 export_visible: true
