# 技术栈决策

## 前端

| 技术 | 版本 | 选型理由 |
|------|------|---------|
| Vue 3 | 3.x | Composition API、响应式系统 |
| Pinia | - | 轻量级状态管理 |
| Vue Router | 4.x | SPA路由 |
| Mermaid.js | - | 图表渲染引擎 |
| SCSS | - | CSS预处理 |
| Vite | - | 构建工具 |

## 后端

| 技术 | 版本 | 选型理由 |
|------|------|---------|
| Python Flask | - | 轻量级Web框架 |
| SQLite | - | 嵌入式数据库，零配置 |
| YAML Schema | - | 元模型唯一定义源 |

## 关键架构决策

- 元模型驱动：YAML Schema是唯一定义源，不直接引用Python对象
- Feature-First：按功能组织代码，而非按文件类型
- Context分层：核心层→规范层→决策层→功能层→知识层
