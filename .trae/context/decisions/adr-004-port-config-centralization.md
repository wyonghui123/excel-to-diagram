# ADR-004: 端口配置中央化管理

## 状态
已接受

## 背景
项目中存在多个服务，每个服务都有独立的端口配置：
- Vite 前端开发服务器
- Node.js Mock API 服务器
- Python Flask 后端服务
- Playwright E2E 测试服务器

长期以来，这些端口配置分散在不同的文件中，导致：
1. 配置不一致，难以维护
2. 每次环境变更需要手动修改多个文件
3. 测试效率低下，经常因为端口配置错误导致失败
4. 新成员上手困难

## 决策

### 采用方案：环境变量 + 中央配置同步脚本

1. **创建 `.env.example`**：定义所有端口配置的默认值
2. **创建 `scripts/sync-ports.js`**：自动同步配置到所有相关文件
3. **创建 `PORT_CONFIG.md`**：文档化端口配置规则
4. **更新 npm scripts**：添加 `sync:ports` 等便捷命令

### 端口分配策略

| 端口范围 | 用途 |
|---------|------|
| 3000-3999 | 前端服务（Vite、Mock API、E2E） |
| 5000-5999 | 后端 API（Python Flask） |

### 配置优先级

```
系统环境变量 > .env.local > .env > 默认值
```

## 后果

### 正面
- 端口配置集中管理，易于维护
- 一键同步所有配置，避免手动修改
- 自动验证配置冲突
- 新成员更容易上手

### 负面
- 需要额外运行 `sync-ports.js` 脚本
- 需要理解环境变量机制

### 中性
- 需要确保 `.env.local` 不提交到 Git

## 实现

### 新增文件
- `.env.example` - 环境变量模板
- `scripts/sync-ports.js` - 配置同步脚本
- `PORT_CONFIG.md` - 端口配置文档

### 修改文件
- `package.json` - 添加新的 npm scripts
- `vite.config.js` - 使用环境变量
- `playwright.config.js` - 使用环境变量
- `meta/server.py` - 使用环境变量
- `server/server.js` - 使用环境变量

## 相关决策
- ADR-001: Mermaid 作为图表渲染方案
- ADR-003: Edge Label 背景色方案
