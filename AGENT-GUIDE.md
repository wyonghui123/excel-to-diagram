# AGENT-GUIDE.md

> 智能体快速理解项目的入口指引文档
> 版本: 1.0 | 更新日期: 2026-05-03

---

## 一、项目概述

**Excel to Diagram** 是一个将 Excel 数据转换为架构图的可视化工具。

| 属性 | 值 |
|------|-----|
| 类型 | 前后端分离 Web 应用 |
| 前端 | Vue 3 + Vite + Mermaid.js |
| 后端 | Python Flask + SQLite |
| 部署 | Vercel / Cloudflare Workers / 自托管 |

---

## 二、目录结构（精简版）

```
excel-to-diagram/
├── src/                    # 前端源码
│   ├── views/              # 页面组件
│   ├── components/         # 通用组件
│   ├── composables/        # 组合式函数
│   ├── services/           # 业务服务
│   └── stores/             # Pinia 状态管理
│
├── meta/                   # 后端源码
│   ├── api/                # API 端点
│   ├── services/           # 业务逻辑
│   ├── core/               # 核心模块
│   └── schemas/            # YAML Schema（元模型唯一定义源）
│
├── scripts/                # 运维脚本
├── config/                 # 配置文件
├── docs/                   # 项目文档
├── e2e/                    # E2E 测试
│
├── package.json            # 前端依赖
├── vite.config.js          # Vite 配置
├── pytest.ini              # 测试配置
└── README.md               # 项目说明
```

---

## 三、核心入口点

### 3.1 前端入口

| 文件 | 说明 |
|------|------|
| `src/main.js` | 应用入口 |
| `src/App.vue` | 根组件（路由逻辑） |
| `src/router/` | 路由配置 |
| `src/stores/` | 全局状态 |

### 3.2 后端入口

| 文件 | 说明 |
|------|------|
| `meta/server.py` | Flask 服务入口 |
| `meta/api/meta_api.py` | 元数据 API |
| `meta/api/manage_api.py` | 管理 API |
| `meta/schemas/business_object.yaml` | 业务对象 Schema |

### 3.3 配置入口

| 文件 | 说明 |
|------|------|
| `config/environment/server-prod.toml` | 服务器配置 |
| `.env.example` | 环境变量模板 |
| `package.json` | 前端依赖和脚本 |

---

## 四、核心模块说明

### 4.1 图表渲染模块

```
src/composables/useMermaid/
├── config/          # Mermaid 配置
├── core/            # 渲染核心
├── syntax/          # 语法生成
├── interaction/     # 交互（缩放/拖拽）
├── style/           # SVG 样式
├── color/           # 颜色方案
└── dataMap/         # 数据映射
```

### 4.2 数据导入模块

```
src/services/
├── excelParser.js   # Excel 解析
├── dataValidator.js # 数据验证
└── dataTransformer.js # 数据转换
```

### 4.3 后端 API 模块

```
meta/api/
├── meta_api.py      # 元数据查询
├── manage_api.py    # CRUD 操作
├── auth_api.py      # 认证授权
└── import_export_api.py # 导入导出
```

---

## 五、快速启动

```bash
# 安装依赖
npm install
pip install -r meta/requirements.txt

# 开发模式
npm run dev:full    # 前端 + 后端

# 测试
npm run test        # 前端单元测试
npm run test:e2e    # E2E 测试
pytest              # 后端测试

# 构建
npm run build
```

---

## 六、开发规范

### 6.1 UI规范（重要！）

**开发UI组件前必须查阅以下文档：**

| 文档 | 说明 |
|------|------|
| [UI_COMPONENT_GUIDELINES.md](docs/UI_COMPONENT_GUIDELINES.md) | UI组件开发规范（Tab、Nav、颜色等） |
| [YONYOU_DESIGN.md](src/styles/YONYOU_DESIGN.md) | yonDesign设计系统规范 |

**核心规范：**

| 规范项 | 要求 |
|--------|------|
| Tab导航 | 使用 `AppTabs` 组件或底部指示线样式 |
| 侧边导航 | 使用 `AppSideNav` 组件或左侧指示线样式 |
| 日志展示 | 使用 `AuditLog` 组件 |
| 消息通知 | 使用 `useMessage()`，禁止 `alert()` |
| 设计令牌 | 所有颜色、间距、字体使用CSS变量 |
| 滚动条 | 使用浏览器默认，禁止全局自定义 |

**可用UI组件：**

```javascript
import { AppTabs, AppSideNav, AuditLog } from '@/components/common'

// Tab导航示例
<AppTabs v-model="activeTab" :tabs="[
  { key: 'tab1', label: '标签1' },
  { key: 'tab2', label: '标签2', icon: 'settings' }
]" />

// 侧边导航示例
<AppSideNav v-model="currentMenu" :items="[
  { key: 'menu1', label: '菜单1', icon: 'home' },
  { key: 'menu2', label: '菜单2', icon: 'settings' }
]" />

// 日志展示示例
<AuditLog :logs="logs" :loading="loading" />
```

### 6.2 消息通知

```javascript
import { useMessage } from '@/composables/useMessage'
const message = useMessage()

message.success('操作成功')
message.error('操作失败')
```

### 6.3 API 响应格式

```json
{
  "success": true,
  "data": {},
  "message": "操作成功"
}
```

### 6.4 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 组件 | PascalCase | `TreeNode.vue` |
| 组合式函数 | camelCase + use | `useMermaid.js` |
| 服务 | camelCase + Service | `feishuService.js` |
| API 文件 | snake_case + _api | `meta_api.py` |

---

## 七、关键文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| UI组件规范 | `docs/UI_COMPONENT_GUIDELINES.md` | Tab、Nav、颜色等UI规范 |
| yonDesign规范 | `src/styles/YONYOU_DESIGN.md` | 设计系统规范 |
| 模块地图 | `.trae/context/module-map.md` | 文件-功能映射 |
| 项目规则 | `.trae/rules/project_rules.md` | 开发约定 |
| API 文档 | `docs/API接口文档.md` | API 说明 |
| 数据模型 | `docs/数据模型文档.md` | 数据结构 |
| 部署规范 | `docs/DEPLOYMENT_STANDARDS.md` | 部署流程 |
| 待办事项 | `docs/CONSOLIDATED-BACKLOG.md` | 任务清单 |

---

## 八、常见任务入口

| 任务 | 入口文件 |
|------|----------|
| 添加新 API | `meta/api/` + 注册到 `server.py` |
| 添加新组件 | `src/components/` |
| 添加新页面 | `src/views/` + 路由配置 |
| 修改 Schema | `meta/schemas/*.yaml` |
| 修改图表样式 | `src/composables/useMermaid/style/` |
| 修改颜色方案 | `src/composables/useMermaid/color/` |

---

## 九、归档目录说明

`archive/` 目录包含已归档的文件，不影响项目运行：

- `archive/debug/` - 调试脚本
- `archive/check/` - 检查脚本
- `archive/test/` - 临时测试
- `archive/deploy/` - 部署脚本变体
- `archive/docs/` - 历史文档
- `archive/objects-backup/` - 历史 Python 元模型定义（已由 YAML Schema 替代）

### ⚠️ 元模型架构说明

**YAML Schema 是元模型的唯一定义源**（`meta/schemas/*.yaml`）。

历史 Python 对象定义（`meta/objects/`）已归档至 `archive/objects-backup/`，原因：
- YAML 定义覆盖 24 个对象，Python 仅覆盖 8 个
- YAML 包含完整的 UI 配置、索引、校验、导入导出等元数据
- Python 对象已严重过时，缺少大量新增属性
- 双重定义导致智能体认知冲突

所有业务代码通过 `registry.get()` 访问元模型，从不直接引用 Python 对象常量。

---

*本文档由智能体优化分析生成，用于提升 AI Agent 理解项目的效率。*
