---
title: 项目目录结构
version: 1.0.0
date: 2026-06-07
status: 活跃
audience: 开发者
---

# Excel to Diagram 目录结构规范

> 版本: v1.0  
> 更新日期: 2026-04-28

---

## 一、服务器目录结构

```
/opt/app/
│
├── config/                          # 配置目录
│   ├── deploy.conf                  # 部署配置
│   └── environment/                 # 环境配置
│       └── server-prod.toml        # 生产环境配置
│
├── deployments/                     # 版本部署目录
│   ├── v20260428_001/              # 版本1
│   │   ├── frontend/               # 前端静态文件
│   │   ├── backend/                # 后端代码
│   │   ├── meta/                   # 元数据服务
│   │   └── ...
│   ├── v20260428_002/              # 版本2
│   └── ...
│
├── current -> deployments/vXXX     # 当前版本符号链接
│
├── backups/                         # 备份目录
│   ├── v20260428_001-20260428/     # 版本备份
│   └── architecture.db-20260428   # 数据库备份
│
├── shared/                          # 共享数据目录
│   ├── data/                        # 数据文件
│   │   └── architecture.db         # 主数据库
│   └── logs/                        # 日志文件
│       ├── deploy-*.log            # 部署日志
│       ├── frontend.log            # 前端日志
│       ├── backend.log             # 后端日志
│       └── health-*.log            # 健康检查日志
│
├── state/                           # 状态目录
│   ├── current_version             # 当前版本号
│   ├── previous_version            # 上个版本号
│   ├── deployment_history.json     # 部署历史
│   ├── environment-snapshot.json   # 环境快照
│   ├── frontend.pid               # 前端进程PID
│   └── backend.pid                # 后端进程PID
│
├── scripts/                         # 运维脚本
│   ├── deploy.sh                   # 部署脚本
│   ├── rollback.sh                 # 回滚脚本
│   ├── preflight-check.sh          # 前置检查
│   ├── service-manager.sh          # 服务管理
│   ├── snapshot-environment.sh      # 环境快照
│   ├── health-check.sh             # 健康检查
│   └── migrate.sh                  # 数据库迁移
│
├── excel-to-diagram/               # 应用软链接 -> current
│   ├── dist/                      # 前端构建文件
│   ├── server.py                  # 前端服务器
│   └── ...
│
└── meta/                          # 元数据服务软链接 -> current/meta
    ├── api/
    ├── core/
    ├── services/
    └── ...
```

---

## 二、本地项目目录结构

```
d:\filework\excel-to-diagram\
│
├── config/                          # 配置目录
│   ├── deploy.conf                  # 部署配置
│   └── environment/                 # 环境配置
│       ├── server-prod.toml        # 生产环境
│       ├── server-staging.toml     # 预发环境
│       └── server-local.toml       # 本地环境
│
├── docs/                           # 文档目录
│   ├── DEPLOYMENT_STANDARDS.md    # 部署规范
│   ├── DIRECTORY_STRUCTURE.md     # 目录结构
│   └── ...
│
├── scripts/                        # 运维脚本
│   ├── build-deploy-package.sh     # 构建部署包
│   ├── server-preflight-check.sh   # 前置检查
│   ├── service-manager.sh          # 服务管理
│   ├── snapshot-environment.sh      # 环境快照
│   └── ...
│
├── excel-to-diagram/               # 前端项目
│   ├── src/
│   ├── dist/                      # 构建输出
│   ├── server.py                  # 带代理的服务器
│   ├── vite.config.js
│   └── package.json
│
├── meta/                           # 后端项目
│   ├── api/
│   ├── core/
│   ├── services/
│   ├── schemas/
│   ├── server.py
│   └── requirements.txt
│
├── migrations/                     # 数据库迁移
│   ├── 001_init_schema.sql
│   ├── 002_add_version.sql
│   └── ...
│
├── tests/                          # 测试目录
│   ├── post-deploy/
│   │   ├── smoke/
│   │   ├── integration/
│   │   └── e2e/
│   └── ...
│
├── build/                          # 构建临时目录
│   └── deploy-v{version}.zip
│
├── requirements.txt                 # Python 依赖
├── README.md
└── ...
```

---

## 三、路径配置映射

| 服务器路径 | 本地路径 | 说明 |
|-----------|---------|------|
| `/opt/app/config/` | `d:\...\config\` | 配置文件 |
| `/opt/app/deployments/` | `build/` | 部署包 |
| `/opt/app/shared/data/` | `meta/` | 数据库 |
| `/opt/app/shared/logs/` | 无 | 日志目录 |
| `/opt/app/scripts/` | `scripts/` | 运维脚本 |

---

## 四、符号链接关系

```
/opt/app/current
    ↓
/opt/app/deployments/v20260428_001

/opt/app/excel-to-diagram
    ↓
/opt/app/current/frontend

/opt/app/meta
    ↓
/opt/app/current/backend/meta
```

---

## 五、命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 版本目录 | `v{YYYYMMDD}_{NNN}` | `v20260428_001` |
| 部署包 | `deploy-v{YYYYMMDD}_{NNN}.zip` | `deploy-v20260428_001.zip` |
| 备份 | `{类型}-{版本}-{日期}` | `v20260428_001-20260428` |
| 日志 | `{类型}-{YYYYMMDD}.log` | `deploy-20260428.log` |
| PID文件 | `{服务名}.pid` | `frontend.pid` |

---

## 六、权限规范

| 目录/文件 | 权限 | 所有者 | 说明 |
|-----------|------|--------|------|
| `/opt/app/` | 755 | root | 根目录 |
| `/opt/app/shared/` | 755 | root | 共享数据 |
| `/opt/app/shared/data/` | 755 | root | 数据目录 |
| `/opt/app/shared/logs/` | 755 | root | 日志目录 |
| `/opt/app/deployments/` | 755 | root | 版本目录 |
| `/opt/app/scripts/*.sh` | 755 | root | 脚本可执行 |
| `/opt/app/state/` | 755 | root | 状态目录 |

---

## 七、磁盘空间规划

| 目录 | 预计大小 | 说明 |
|------|----------|------|
| `/opt/app/` | 10GB | 总空间 |
| `deployments/` | 5GB | 保留5个版本 |
| `backups/` | 2GB | 数据库和配置备份 |
| `shared/data/` | 500MB | 数据库文件 |
| `shared/logs/` | 500MB | 日志文件 |
| 预留空间 | 2GB | 临时文件和扩展 |
