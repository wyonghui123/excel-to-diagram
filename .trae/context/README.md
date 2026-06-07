# Excel转Diagram工具

## 项目定位

将 Excel/CSV 数据转换为可视化架构图（Mermaid），支持业务对象关系图的生成和管理。

**目标用户**: 业务分析师、系统架构师、产品经理

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Composition API |
| 状态管理 | Pinia |
| 路由 | Vue Router 4 |
| 图表渲染 | Mermaid.js（ELK/Dagre 布局引擎） |
| 样式 | SCSS |
| 后端框架 | Python Flask |
| 数据库 | SQLite |
| 元模型 | YAML Schema 驱动 |

## 前端路由结构

```
/                    → 工作台 (ArchWorkspaceNew)
/diagram             → AA图生成 (AADiagramApp)
/config              → 系统配置 (ConfigApp)
/data/:productId?/:versionId? → 架构数据管理 (ArchDataManageApp)
/product-version     → 产品版本管理 (ProductVersionApp)
/system              → 系统管理 (SystemManagement)
/test                → 组件测试 (ComponentTest)
```

## 元模型架构

**YAML Schema 是元模型的唯一定义源**（`meta/schemas/*.yaml`）

- 当前定义 24 个元模型对象
- 支持字段、关系、动作、校验、UI 配置等完整元数据
- 历史 Python 对象定义已归档至 `archive/objects-backup/`

## 关键约束

1. **元模型**: 所有元数据通过 `registry.get()` 访问，不直接引用 Python 对象
2. **路由导航**: 使用 `router.push()` 而非 emit 事件
3. **布局引擎**: ELK 和 Dagre 方向映射相反（见 ADR-002）
4. **颜色分组**: 通过 GroupModel 管理
5. **工程规范**: 遵循 `.trae/rules/engineering-guidelines.md`

## 目录结构

```
excel-to-diagram/
├── src/                    # 前端源码
│   ├── views/              # 页面组件
│   ├── components/         # 通用组件
│   ├── composables/        # 组合式函数
│   ├── services/           # 业务服务
│   ├── stores/             # Pinia 状态管理
│   └── router/             # 路由配置
│
├── meta/                   # 后端源码
│   ├── api/                # API 端点
│   ├── services/           # 业务逻辑
│   ├── core/               # 核心模块
│   └── schemas/            # YAML Schema（元模型唯一定义源）
│
├── archive/                # 归档文件
│   ├── objects-backup/     # 历史 Python 元模型定义
│   └── ...                 # 其他归档内容
│
├── scripts/                # 运维脚本
├── config/                 # 配置文件
├── docs/                   # 项目文档
└── e2e/                    # E2E 测试
```

## 快速导航

- [AGENT-GUIDE.md](../../AGENT-GUIDE.md) - 智能体入口指引
- [架构决策索引](./decisions/README.md) - 重要技术决策
- [工程规范](../rules/engineering-guidelines.md) - 编码规范
- [Context 使用规则](../rules/context-usage.md) - 何时查阅详细信息
- [功能规范](../specs/) - 各功能需求详情
- [文档中心](../../docs/README.md) - 完整文档导航

## 当前迭代

**2026-Q2 目标**
- ✅ 清理根目录，归档临时文件
- ✅ 解决元模型双重定义问题
- ✅ 移除 .env 中的密钥
- ✅ 引入 Vue Router
- 完善 Mermaid 图表渲染稳定性
- 优化颜色分组切换性能
