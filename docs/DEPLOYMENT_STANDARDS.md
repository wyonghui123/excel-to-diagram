---
title: 部署标准
version: 1.0.0
date: 2026-06-07
status: 活跃
audience: 运维、开发者
---

## 目录

1. [一、规范概述](#一-规范概述)
2. [二、部署架构](#二-部署架构)
3. [三、部署包规范](#三-部署包规范)
4. [四、部署流程规范](#四-部署流程规范)
5. [五、服务管理规范](#五-服务管理规范)
6. [六、数据库规范](#六-数据库规范)
7. [七、日志规范](#七-日志规范)
8. [八、版本管理规范](#八-版本管理规范)
9. [九、配置管理规范](#九-配置管理规范)
10. [十、回滚规范](#十-回滚规范)
11. [十一、测试规范](#十一-测试规范)
12. [十二、代码规范（重要）](#十二-代码规范（重要）)
13. [十三、变更记录](#十三-变更记录)
14. [附录](#附录)

---
# Excel to Diagram 部署规范标准

> 版本: v1.0  
> 更新日期: 2026-04-28  
> 状态: 草稿

---

## 一、规范概述

### 1.1 目的
建立统一的部署规范，确保：
- 部署过程可重复、可追溯
- 环境配置清晰、不易出错
- 问题可快速定位和修复

### 1.2 范围
适用于 `excel-to-diagram` 项目的所有部署场景

### 1.3 术语定义

| 术语 | 定义 |
|------|------|
| 部署包 | 包含所有部署文件的压缩包 |
| MANIFEST | 部署清单，记录版本、依赖、变更 |
| 前置检查 | 部署前对环境的全面验证 |
| 健康检查 | 部署后对服务状态的验证 |

---

## 二、部署架构

### 2.1 服务架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      用户浏览器                                   │
│                  http://172.20.59.7:18081/                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│      前端服务 unified_18081.py (18081端口)  [2026-09-02 更新]    │
│    - 静态文件服务: /opt/app/staging/deploy/current/dist        │
│    - API代理: /api/* → http://localhost:13011                  │
└─────────────────────────────────────────────────────────────────┘
                              │ 代理转发
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│      后端服务 server.py (13011端口)  [2026-09-02 更新]            │
│    - /api/v1/product, /api/v1/import 等                        │
│    - 数据库: /opt/app/staging/meta/architecture.db            │
└─────────────────────────────────────────────────────────────────┘

辅助服务（部署运维用）:
  - core_service (19200): exec/upload/audit (元能力, 4 端点架构冻结)
  - log_service (19101): log/alerts/deploy (10+ 端点, 已 systemd 守护)

守护机制:
  - staging_watchdog.sh (2026-09-02 v1.0): 30s 周期探测 4 服务, 自动重启
  - 详见 .trae/rules/staging-process-guardian.md
```

### 2.2 服务器环境要求

> **当前远程服务器实际版本**（2026-06-29 核实）：
> - Python 3.9.25（`python` / `python3` 已统一）
> - OpenSSH 10.3p1 / OpenSSL 1.1.1w（2026-06 升级，已应用）

| 项目 | 要求 | 备注 |
|------|------|------|
| 操作系统 | CentOS 7.x | 或兼容版本 |
| Python | 3.9.25 (Conda) | `/opt/miniconda3-py39/bin/python` (`python` / `python3` 均生效) |
| OpenSSH | 10.3p1 | 2026-06 已升级 |
| OpenSSL | 1.1.1w (11 Sep 2023) | 随 OpenSSH 升级 |
| 磁盘空间 | ≥2GB | 部署包 + 日志 + 备份 |
| 内存 | ≥2GB | 推荐4GB+ |
| 网络 | 内网可达 | 无需访问外网 |

#### 2.2.1 版本验证命令

远程升级后，执行以下命令验证版本一致性：

```bash
# Python（python 与 python3 输出版本必须一致）
ssh root@172.20.59.7 "python -V; python3 -V"
# 期望: Python 3.9.25 / Python 3.9.25

# SSH / OpenSSL
ssh -V
# 期望: OpenSSH_10.3p1, OpenSSL 1.1.1w 11 Sep 2023
```

> 注：`ssh -V` 在本地执行即可（显示客户端版本）；服务端版本用 `ssh root@172.20.59.7 "sshd -V"` 或 `cat /etc/redhat-release`。

---

## 三、部署包规范

### 3.1 目录结构

```
deploy-v{timestamp}.zip
├── MANIFEST                    # 部署清单（必需）
├── frontend/                   # 前端静态文件
│   ├── dist/
│   └── server.py              # 带代理的静态服务器
├── backend/                   # 后端代码
│   ├── meta/
│   └── requirements.txt       # Python依赖
├── migrations/                # 数据库迁移脚本
│   └── *.sql
├── dependencies/              # 离线依赖（可选）
│   └── python/packages/
├── scripts/                    # 部署脚本
│   └── *.sh
└── config/                     # 配置文件
    └── deploy.conf
```

### 3.2 MANIFEST 格式

```yaml
version: "v20260428_001"
released_at: "2026-04-28T16:00:00Z"

changes:
  - "新增导入导出功能"
  - "修复数据库路径问题"

requirements:
  python: ">=3.9,<3.14"           # 兼容 3.9.25 ~ 3.13.x；3.14.x 跳过（gevent socket 问题）
  python_tested: "3.9.25"         # 2026-06 实际验证版本
  disk_space: "500MB"

dependencies:
  python:
    added:
      - openpyxl==3.1.2
      - flask-cors==4.0.0

database:
  migrations:
    - "003_add_fields.sql"

services:
  frontend:
    port: 8081
  backend:
    port: 5001
```

---

## 四、部署流程规范

### 4.1 标准部署流程

```
┌────────────────────────────────────────────────────────────────────┐
│  阶段1: 前置检查 (preflight)                                        │
│  - 环境检测、配置验证、磁盘空间检查                                   │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段2: 备份 (backup)                                              │
│  - 备份当前版本、备份数据库                                         │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段3: 部署 (deploy)                                               │
│  - 解压文件、创建目录、符号链接共享数据                               │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段4: 依赖安装 (dependencies)                                     │
│  - 安装Python依赖、执行数据库迁移                                    │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段5: 启动服务 (start)                                            │
│  - 停止旧进程、启动新进程                                           │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段6: 健康检查 (health_check)                                      │
│  - 服务健康检查、端口监听检查                                        │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段7: 功能测试 (functional_test)                                  │
│  - API测试、代理测试                                               │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  阶段8: 更新状态 (update_state)                                     │
│  - 记录部署历史、清理旧版本                                         │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 各阶段检查点

| 阶段 | 检查点 | 失败处理 |
|------|--------|----------|
| 前置检查 | Python环境、磁盘空间、端口占用 | 终止部署 |
| 备份 | 数据库备份成功、旧版本备份 | 终止部署 |
| 部署 | 文件解压成功、目录创建成功 | 回滚 |
| 依赖安装 | pip安装成功、迁移执行成功 | 回滚 |
| 启动服务 | 进程启动、PID记录 | 回滚 |
| 健康检查 | HTTP 200响应 | 自动重试3次，失败则回滚 |
| 功能测试 | API返回正确 | 告警但不回滚 |

---

## 五、服务管理规范

### 5.1 服务定义

| 服务名 | 端口 | 进程名 | 健康检查端点 |
|--------|------|--------|-------------|
| frontend | 8081 | server.py | /health |
| backend | 5001 | server.py | /api/v1/health |

### 5.2 服务启停

```bash
# 启动所有服务
/opt/app/scripts/start-all.sh

# 停止所有服务
/opt/app/scripts/stop-all.sh

# 重启服务
/opt/app/scripts/restart.sh <service_name>
```

### 5.3 健康检查

```bash
# 检查所有服务
/opt/app/scripts/health-check.sh

# 检查单个服务
curl http://localhost:8081/health
curl http://localhost:5001/api/v1/health
```

---

## 六、数据库规范

### 6.1 数据库位置

| 环境 | 路径 |
|------|------|
| 生产 | `/opt/app/shared/data/architecture.db` |
| 本地 | `d:\filework\excel-to-diagram\meta\architecture.db` |

### 6.2 数据库迁移

```
migrations/
├── 001_init_schema.sql
├── 002_add_version.sql
├── 003_add_fields.sql
└── migrate.sh
```

### 6.3 迁移命名规范

```
{序号}_{简短描述}.sql
示例: 003_add_annotation_fields.sql
```

---

## 七、日志规范

### 7.1 日志目录

```
/opt/app/shared/logs/
├── deploy-YYYYMMDD_HHMMSS.log  # 部署日志
├── frontend.log                  # 前端服务日志
├── backend.log                  # 后端服务日志
└── health-YYYYMMDD.log          # 健康检查日志
```

### 7.2 日志格式

```
[时间戳] [级别] [来源] 消息
示例: [2026-04-28 14:00:00] [INFO] [deploy] 开始部署版本 v20260428_001
```

### 7.3 日志级别

| 级别 | 用途 |
|------|------|
| DEBUG | 调试信息 |
| INFO | 一般信息 |
| WARN | 警告信息 |
| ERROR | 错误信息 |

---

## 八、版本管理规范

### 8.1 版本号格式

```
v{YYYYMMDD}_{序号}
示例: v20260428_001
```

### 8.2 版本目录

```
/opt/app/deployments/
├── v20260428_001/
├── v20260428_002/
└── current -> v20260428_002 (符号链接)
```

### 8.3 保留策略

- 保留最近 **5** 个版本
- 保留所有备份
- 保留最近 **30** 天日志

---

## 九、配置管理规范

### 9.1 配置文件位置

**环境变量（实际生效的部署配置载体，优先看这里）**：

```
d:\filework\excel-to-diagram\
├── .env.production        # 生产环境变量模板（复制到服务器 .env 或 systemd EnvironmentFile）
├── .env.example           # 全部可用变量的说明模板
└── .env                   # 本地开发实际生效（已在 .gitignore，不提交）
```

**服务器 / 基础设施描述**：

```
d:\filework\excel-to-diagram\
├── config/
│   ├── environment/
│   │   └── server-prod.toml  # 生产服务器环境描述（路径 / 版本 / 依赖，非运行时配置）
│   └── monitoring/           # Prometheus / Grafana 配置
```

> `server-prod.toml` 是**环境描述**（部署拓扑、Python/Node 版本、依赖清单），**不是运行时配置载体** —— 运行时行为由环境变量决定（见 §9.2）。

### 9.2 部署级环境变量（`.env` / systemd `EnvironmentFile`）

以下开关是**实例（拓扑）属性**，不是应用属性 —— 由部署清单决定，**与装哪些 app 无关**（见 [platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §6.2.3](./platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md)）。

| 变量 | 默认 | 作用 | 生效范围 |
|---|---|---|---|
| `ENABLED_APPS` | 空（legacy） | 启用哪些应用包（白名单，逗号分隔） | 每次启动 |
| `APP_DB_ROUTING` | `0`（关） | **库形态**：0=合并（同库 + `table_prefix`）/ 1=各应用独立库 | 每次启动 |
| `PLATFORM_DISPLAY_NAME` | 空 | **实例展示名** —— 前端 4 个渲染点（详见 §9.2.1） | 每次启动 |
| `DISABLED_PLATFORM_MODULES` | 空（全开） | **平台模块**黑名单，逗号分隔 | 路由每次启动；菜单仅对未跑过种子的实例 |

> **`DISABLED_PLATFORM_MODULES` 当前可关闭：仅 `tasks`（任务体系）。**
> `rules`（规则体系）暂无可关闭入口 —— `meta/core/rule_*.py` 是平台核心库底层依赖，写了**不报错但无效果**，`/health` 的 `ineffective_platform_modules` 字段会如实报出，避免误判"已关闭"。

**验证开关是否真生效**（唯一存活的无鉴权探活点；`/api/v1/health` 已被 v1 sunset 接管返回 410，勿用）：

```bash
curl -s http://<host>:<port>/health | python -m json.tool
# 关注三个字段：
#   enabled_apps                    —— 已加载的应用
#   disabled_platform_modules       —— 已关闭的平台模块
#   ineffective_platform_modules    —— 写了但无效果的（应为空）
```

**已部署实例的存量清理**：模块开关**不回收存量菜单**。若实例已跑过菜单种子，关闭模块后侧栏菜单仍在，需一次性执行：

```sql
UPDATE menus SET show_in_sidebar=0 WHERE menu_code IN
('task-management','task-definitions','task-queues','task-executions','ai-async-tasks');
```

> 路由侧不受此影响 —— blueprint 已不注册，旧菜单点进去也是 404。

### 9.3 部署级环境变量的落点（`PLATFORM_DISPLAY_NAME` 展开）

**通用取值优先级**（后端裁定，`GET /api/v2/meta/instance`）：

```
PLATFORM_DISPLAY_NAME 有值  →  用它
         ↓ 无值
恰好启用 1 个 app          →  用该 app 的 app.yaml name
         ↓ 否则
默认名「BIP应用架构管理」
```

> 理由：左上角 / 标签页是**产品标识位**，不是导航位；app 之间的切换由侧栏菜单承担，多 app 时拼不出有意义的名称。

**前端 4 个渲染点**（全部经 [src/composables/useInstanceInfo.js](../../src/composables/useInstanceInfo.js) 单例取同一个值，请求失败静默回落默认名）：

| # | 位置 | 文件 | 说明 |
|---|---|---|---|
| 1 | 左上角 logo 文字 | [src/components/common/AppRootLayout.vue](../../src/components/common/AppRootLayout.vue) | 经 `AppLayout` → `TopNavHeader` 的 `logoText` prop |
| 2 | 登录页标题 `<h2>` | [src/components/LoginPage.vue](../../src/components/LoginPage.vue) | 登录前就要显示，故端点无鉴权 |
| 3 | **工作台页脚** `© 2026 <名>` | [src/components/ArchWorkspaceNew.vue](../../src/components/ArchWorkspaceNew.vue) | **常驻**（工作台底部一直显示） |
| 4 | **浏览器标签页标题** | [src/router/index.js](../../src/router/index.js) | `<页面名> - <实例名>`；路由守卫内首次导航时最多 await 一次 |

> 第3、4 处是**补漏**（2026-10-13）：首版只改了第 1、2 处，遗漏了工作台页脚与桌面标题栏（Electron）。桌面标题栏与页脚在同一个组件内、共用 `displayName`，已一并修复。

**已知的其余硬编码**（**刻意不改**，说明理由）：

| 位置 | 值 | 为何不改 |
|---|---|---|
| [TopNavHeader.vue](../../src/components/common/TopNavHeader/TopNavHeader.vue) `logoText` prop 默认值 | `BIP应用架构管理` | 组件级兜底值，实际总被 `AppRootLayout` 覆盖；已加注释指向真实来源 |
| [AppLayout.vue](../../src/components/common/AppLayout/AppLayout.vue) `logoText` prop 默认值 | `ArchWorkspace` | 同上兜底值，且**有单测断言**该默认值；改它属超出本次范围的无意义改动 |
| [zh-CN.json](../../src/i18n/locales/zh-CN.json) `app.title` | `BIP应用架构管理` | **死条目** —— 全项目无引用（Grep 确认） |
| `SystemSettings.vue` / `ConfigApp.vue` 关于页的"ArchWorkspace 是一款专业的架构设计工具…" | — | **产品名≠ 实例名**，是软件自身的描述，不应随部署改变 |

### 9.4 配置更新流程

1. 更新配置文件
2. 提交到版本控制
3. 记录变更日志
4. 下次部署时生效

---

## 十、回滚规范

### 10.1 自动回滚条件

- 前置检查失败
- 备份失败
- 部署文件解压失败
- 服务启动失败
- 健康检查连续失败

### 10.2 回滚流程

```
1. 停止当前服务
2. 恢复数据库备份
3. 恢复代码版本
4. 重启旧版本服务
5. 验证服务可用
```

### 10.3 回滚命令

```bash
# 回滚到上一版本
/opt/app/scripts/rollback.sh

# 回滚到指定版本
/opt/app/scripts/rollback.sh v20260428_001
```

---

## 十一、测试规范

### 11.1 测试类型

| 类型 | 执行时机 | 失败处理 |
|------|----------|----------|
| 冒烟测试 | 每次部署后 | 阻断部署 |
| 集成测试 | 每次部署后 | 告警 |
| E2E测试 | 重要版本 | 告警 |

### 11.2 测试命令

```bash
# 运行所有测试
/opt/app/tests/run_tests.sh all

# 只运行冒烟测试
/opt/app/tests/run_tests.sh smoke
```

---

## 十二、代码规范（重要）

### 12.1 API 数据库路径规范 ⚠️

**问题背景：**
相对路径 `meta/architecture.db` 在不同工作目录下解析结果不同，导致部署失败。

**正确写法：**
```python
import os
from meta.core.datasource import get_data_source

# ✅ 正确：基于 __file__ 计算绝对路径
db_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'architecture.db'
)
_data_source = get_data_source("sqlite", database=db_path)
```

**错误写法：**
```python
# ❌ 错误：使用相对路径
_data_source = get_data_source("sqlite", database="meta/architecture.db")

# ❌ 错误：使用相对路径
_data_source = get_data_source("sqlite", database="architecture.db")
```

### 12.2 新建 API 流程

1. **复制模板**：`meta/api/API_TEMPLATE.py`
2. **替换占位符**：
   - `{API名称}` → 你的API名称
   - `{api_name}` → 你的API名称小写
3. **注册蓝图**：在 `server.py` 中添加：
   ```python
   from meta.api.{api_name}_api import {api_name}_bp
   app.register_blueprint({api_name}_bp)
   ```

### 12.3 代码检查清单

创建新 API 后，请确认：

```
□ 数据库路径使用 os.path.join + __file__ 方式
□ 没有使用 "meta/architecture.db" 相对路径
□ 没有使用 "architecture.db" 相对路径
□ init_services 函数正确实现
□ 蓝图正确注册
```

---

## 十三、变更记录

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-04-28 | v1.0 | 初始版本 | DevOps |
| 2026-04-28 | v1.1 | 增加代码规范章节（API数据库路径规范） | DevOps |
| 2026-06-29 | v1.2 | 固化远程实际版本：Python 3.9.25、OpenSSH 10.3p1、OpenSSL 1.1.1w；新增 2.2.1 版本验证命令 | DevOps |
| 2026-06-29 | v1.3 | 新增 §2.2.2 Python 兼容性范围（AST 扫描结果：3.9.25 / 3.10~3.12 / 3.13 全兼容，3.14 不推荐）；MANIFEST §3.2 requirements 改为 `python: ">=3.9,<3.14"` + `python_tested: "3.9.25"` | DevOps |
| 2026-09-13 | v1.4 | 新增 §13.1 `tools/deploy_upload.py` 通用部署拓扑 CLI 行（详见 [retrospective 2026-09-13](retrospectives/2026-09-13-deploy-topology-generalization.md)）；取代 staging 特定硬编码脚本 | DevOps |
| 2026-10-13 | v1.5 | §9 重构：新增 **§9.2 部署级环境变量**（`ENABLED_APPS` / `APP_DB_ROUTING` / `PLATFORM_DISPLAY_NAME` / `DISABLED_PLATFORM_MODULES` 四条部署级开关 + `/health` 验证方法 + 存量菜单清理 SQL）；新增 **§9.3 `PLATFORM_DISPLAY_NAME` 落点**（前端 4 个渲染点 + 取值优先级 + 刻意不改的硬编码清单）；原"配置更新流程"顺延为 §9.4；修正 §9.1 遗漏 `.env` / `.env.production`（实际生效的部署配置载体） | AI Assistant |

---

## 附录

### A. 常用命令

```bash
# 查看服务状态
netstat -tlnp | grep -E "8081|5001"

# 查看日志
tail -f /opt/app/shared/logs/backend.log

# 查看部署历史
cat /opt/app/state/deployment_history.json

# 检查环境
/opt/app/scripts/preflight-check.sh
```

### B. 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 端口占用 | 旧进程未退出 | `fuser -k 8081/tcp` |
| 数据库连接失败 | 路径错误 | 检查配置文件 |
| API返回404 | 后端未启动 | 检查后端进程 |

---

## 十三、补遗: 新增能力 (2026-07-15)

> 本节记录 v1.3 之后新增的能力, 详见主文档 [DEPLOY_INFRASTRUCTURE.md](../../DEPLOY_INFRASTRUCTURE.md) 与 [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)。

### §13.1 远端操作 (agent 自动化)

**新增 5 个工具**, 替代原 SSH/SFTP 流程:

| 工具 | 用途 | 替代什么 |
|------|------|----------|
| `tools/yonaa_exec.py` | HTTP exec + upload (限流 + 跨小时 token + 错误分类 + bg 后台) | SSH 命令 |
| `tools/remote_capability_probe.py` | 30s 扫 7 端口 × 6 secret | 手工 `nc` / `curl` |
| `tools/staging_deploy_orchestrator.py` | 一键 staging 部署 (10 步自动) | SFTP + SSH 5 条命令 |
| `tools/deploy_upload.py` | **[2026-09-13]** 通用部署拓扑 CLI (resolve/upload/verify/healthcheck), 适配 staging/production/dev/preview 任意拓扑; 基于 DeployTarget + PathResolver + ResourceType 抽象 | staging 特定硬编码脚本 |
| ~~`tools/restart_log_service.py`~~ | **~~删除 V007.56~~** 旧手工 restart 工具 (deprecated V007.55) | 已删除 |
| `tools/install_log_service_systemd.py` | **V007.55** 一键装 systemd unit 守护 log_service | 旧 restart_log_service.py |
| `tools/setup_log_service_cron.py` | **V007.55** 装 cron `*/5 * * * *` 监控告警 | 手工写 crontab |
| `tools/find_log_service_killer.py` | **V007.56** 探查 SIGKILL 元凶 (journal + aegis + cgroup + auditd) | systemd 守护下还是被杀时 |
| `tools/deploy_log_service_systemd.py` | **V007.57** 上传 service + daemon-reload + restart (支持 nobody 用户) | 改 unit 文件后重发 |
| `tools/chown_log_service_dirs.py` + `chown_readable.py` + `fix_staging_chown.py` | **V007.57** nobody 用户下, chown DB/log/scripts 给 nobody 可写可读 | 改 nobody 后必跑一次 |
| `tools/monitor_hips.py` | **V007.57** 监控 nobody log_service 是否被 HIPS 杀 (2 分钟 12 次检查) | 验证 nobody 修复是否生效 | 
| `tools/alert_monitor.py` + `alert_monitor.bat` | **V007.58** agent 端 IM 告警 (5min 轮询 7 端口 + 飞书/钉钉/微信 webhook) | 服务器无公网, agent 主动轮询 | **agent 端** |
| `docs/INCIDENT_ALERT_SETUP.md` | **V007.58** IM 告警配置 5 分钟上手 (含网络拓扑/IM webhook 获取/Windows 任务计划) | 第一次配 IM | **运维** |
| `tools/rebuild_bundle.ps1` | 本地 rebuild (保留) | 保留 |

**新端口 (agent 入口, 7 个)**:
- 9200 (prod core_service), 19200 (staging core_service)
- 9201 (observability, 5 端点)
- **9101 (prod log_service, 10+ 端点, 本会话重启)**
- **19101 (staging log_service, 10+ 端点, 本会话重启)**
- 8081 (frontend), 3011 (backend)

**认证**: `SHA256(secret+hour)[:16]`, secret = `v007.52-core-write` (9200/19200) 或 `v007.35-infra` (9201/9101/19101)

### §13.2 Migration 升级 (P0/P1/P1.5)

| 工具 | 用途 |
|------|------|
| `meta/core/migration_runner.py` | 实际跑 schema migration (含 idempotent SQL) |
| `tools/backfill_schema_migrations.py` | 把已应用 schema 写到 schema_migrations 表 |
| `tools/migration_lint.py` + `migration_lint.legacy.yaml` | lint migration 文件 (5 规则) |
| `tools/monitor_migrations.py` | 监控 (WARN/CRIT/FAIL) + `--check-regression` 跑回归测试 |
| `tools/regression_test_suite.py` | **9 个 sqlite io error 场景 (R1-R9), 自动 restore + exit code** (V007.55) |

**关键变更**:
- ✅ migration_runner **idempotent**: `duplicate column` / `already exists` 自动跳过
- ✅ **executescript**: 处理 trigger `BEGIN/END` 块
- ✅ lint 升级: 26 个 V007.46 老文件**白名单豁免** (P1.5 legacy 机制)
- ✅ lint 退出码 0 (WARN 不阻塞 CI)
- ✅ test_utils 去除 pytest 硬依赖 (远端 system Python 也能跑)

**当前状态**:
- prod: 18 migration SUCCESS, **0 FAILED**
- staging: 18 migration SUCCESS, **0 FAILED**
- lint: **0 FAIL, 8 WARN, exit 0**

### §13.3 老 staging 架构下线 (2026-07-15)

| 旧端口 | 旧服务 | 新状态 |
|------|------|------|
| 13011 | meta_backend | ❌ dead (改用 core_service exec) |
| 18081 | unified | ❌ dead (agent 不通过 unified 调) |
| **19101** | **staging log_service** | ✅ **alive (本会话重启)** |
| **9101** | **prod log_service** | ✅ **alive (本会话重启)** |
| **19200** | **staging core_service** | ✅ alive |
| **9200** | **prod core_service** | ✅ alive |
| **9201** | **observability** | ✅ alive (5 端点) |

**新部署架构**: 2 服务 = `core_service.py` (exec + upload + audit) + `log_service.py` (10+ 端点), 通过 env var 切 port + db path。

**log_service 管理 (V007.55 systemd 守护)**:
```bash
# V007.55 推荐: 一键装 systemd unit
python tools/install_log_service_systemd.py
# 验证
python tools/remote_capability_probe.py --check-systemd
# 重启
python tools/restart_log_service.py --use-systemd
# 旧工具 (deprecated)
# python tools/restart_log_service.py --env prod
```

详见 [STAGING_GUIDE.md](STAGING_GUIDE.md)。

