# 编码规范

> 详细规范见 `.trae/rules/engineering-guidelines.md`，本文仅列出关键要点

## 前端

- Vue 3 Composition API（setup语法糖）
- 组件命名PascalCase，文件命名kebab-case或PascalCase
- 状态管理：Pinia stores
- 路由导航：router.push() 而非 emit 事件
- 消息通知：useMessage() 而非 alert()（详见 project_rules.md）

## 后端

- Flask蓝图组织
- API前缀：/api/v1/
- 响应格式：{ success: bool, data: any, error?: string }
- 元模型访问：registry.get()

## 通用

- 代码注释使用中文
- 提交信息格式：[模块] 简短描述
- 禁止提交密钥和敏感信息
