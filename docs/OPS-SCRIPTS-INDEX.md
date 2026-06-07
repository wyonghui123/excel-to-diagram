# Excel to Diagram 运维脚本索引

## 📋 概述

本文档列出所有部署和运维相关的脚本，便于快速查找和使用。

---

## 🚀 部署脚本

### deploy-auto.sh
自动化部署脚本

```bash
/opt/app/excel-to-diagram/scripts/deploy-auto.sh
```

**功能:**
- 自动化部署应用程序
- 自动备份当前版本
- 健康检查验证

---

## 🔄 回滚脚本

### rollback-enhanced.sh
增强版回滚脚本

```bash
/opt/app/excel-to-diagram/scripts/rollback-enhanced.sh
```

**功能:**
- 快速回滚到上一个稳定版本
- 自动备份当前版本
- 健康检查验证

**使用示例:**
```bash
# 回滚到上一个版本
./rollback-enhanced.sh

# 回滚到指定版本
./rollback-enhanced.sh -v v20260427_001

# 列出可用版本
./rollback-enhanced.sh --list
```

---

## ✅ 健康检查脚本

### health-check.sh
健康检查脚本

```bash
/opt/app/excel-to-diagram/scripts/health-check.sh
```

**功能:**
- 服务端口检查
- API端点验证
- 数据库连接测试
- 依赖项检查

**使用示例:**
```bash
# 执行完整健康检查
./health-check.sh

# 详细输出
./health-check.sh -v

# 仅检查服务
./health-check.sh -s
```

---

## 📸 环境快照脚本

### snapshot-enhanced.sh
环境快照脚本

```bash
/opt/app/excel-to-diagram/scripts/snapshot-enhanced.sh
```

**功能:**
- 记录环境状态
- 变更检测
- 历史对比
- 自动告警

**使用示例:**
```bash
# 创建快照
./snapshot-enhanced.sh

# 对比历史
./snapshot-enhanced.sh --diff
```

---

## 🔍 部署后验证脚本

### post-deploy-verify.sh
部署后验证脚本

```bash
/opt/app/excel-to-diagram/scripts/post-deploy-verify.sh
```

**功能:**
- 自动执行健康检查
- 生成快照
- 发送通知

**使用示例:**
```bash
./post-deploy-verify.sh
```

---

## 🧪 CI/CD 测试脚本

### ci-cd-test.sh
自动化测试脚本

```bash
/opt/app/excel-to-diagram/scripts/ci-cd-test.sh
```

**功能:**
- 服务端口检查
- HTTP端点测试
- API功能测试
- 数据库检查
- 资源监控

**使用示例:**
```bash
# 执行完整测试
./ci-cd-test.sh

# 仅API测试
./ci-cd-test.sh -t api

# 配置文件位置
./ci-cd-test.sh --config /path/to/config.yaml
```

---

## 💾 备份脚本

### backup.sh
备份管理脚本

```bash
/opt/app/excel-to-diagram/scripts/backup.sh
```

**功能:**
- 数据库备份
- 应用数据备份
- 配置备份
- 过期备份清理
- 远程备份上传

**使用示例:**
```bash
# 全量备份
./backup.sh

# 仅备份数据库
./backup.sh -t db

# 备份并保留30天
./backup.sh -r 30

# 启用远程备份
./backup.sh --remote backup.server.com
```

### backup-scheduler.sh
定时备份调度脚本

```bash
/opt/app/excel-to-diagram/scripts/backup-scheduler.sh
```

**功能:**
- 安装定时备份任务
- 移除定时任务
- 查看备份状态

**使用示例:**
```bash
# 安装定时任务
./backup-scheduler.sh install

# 查看状态
./backup-scheduler.sh status

# 移除定时任务
./backup-scheduler.sh remove
```

---

## 📊 日志聚合脚本

### log-aggregator.sh
日志聚合服务

```bash
/opt/app/excel-to-diagram/scripts/log-aggregator.sh
```

**功能:**
- 日志解析
- 错误/警告提取
- 日志索引
- 归档管理

**使用示例:**
```bash
# 执行日志聚合
./log-aggregator.sh run

# 搜索日志
./log-aggregator.sh search "ERROR" "2026-04-28"

# 查看状态
./log-aggregator.sh status
```

---

## 🛠️ 配置目录

| 配置文件 | 路径 | 说明 |
|---------|------|------|
| 备份配置 | `/opt/app/excel-to-diagram/scripts/backup.conf` | 备份策略配置 |
| 日志轮转 | `/opt/app/excel-to-diagram/scripts/logrotate.conf` | 日志轮转规则 |
| Prometheus | `/opt/app/excel-to-diagram/config/monitoring/prometheus.yml` | 监控配置 |
| Prometheus告警 | `/opt/app/excel-to-diagram/config/monitoring/prometheus-alerts.yml` | 告警规则 |
| Grafana | `/opt/app/excel-to-diagram/config/monitoring/grafana-dashboard.json` | 仪表板配置 |

---

## 📁 目录结构

```
/opt/app/excel-to-diagram/
├── scripts/
│   ├── deploy-auto.sh              # 部署脚本
│   ├── rollback-enhanced.sh        # 回滚脚本
│   ├── health-check.sh             # 健康检查
│   ├── snapshot-enhanced.sh        # 环境快照
│   ├── post-deploy-verify.sh       # 部署验证
│   ├── ci-cd-test.sh              # CI/CD测试
│   ├── backup.sh                   # 备份管理
│   ├── backup-scheduler.sh         # 备份调度
│   ├── backup.conf                 # 备份配置
│   └── log-aggregator.sh           # 日志聚合
├── config/
│   └── monitoring/
│       ├── prometheus.yml          # Prometheus配置
│       ├── prometheus-alerts.yml   # 告警规则
│       └── grafana-dashboard.json  # Grafana仪表板
├── logs/                           # 日志目录
└── backups/                        # 备份存储
    ├── db/                         # 数据库备份
    ├── app/                        # 应用备份
    ├── config/                     # 配置备份
    └── metadata/                   # 备份元数据
```

---

## 🔄 常用操作流程

### 部署流程
```bash
# 1. 部署
./deploy-auto.sh /path/to/deploy-v20260428_001.zip

# 2. 验证
./post-deploy-verify.sh

# 3. 测试
./ci-cd-test.sh
```

### 回滚流程
```bash
# 回滚
./rollback-enhanced.sh

# 验证
./health-check.sh
```

### 备份流程
```bash
# 执行备份
./backup.sh

# 查看状态
./backup-scheduler.sh status
```

---

## 📝 注意事项

1. 所有脚本需要执行权限:
   ```bash
   chmod +x /opt/app/excel-to-diagram/scripts/*.sh
   ```

2. 定期检查备份空间:
   ```bash
   df -h /opt/app/backups
   ```

3. 监控日志聚合状态:
   ```bash
   ./log-aggregator.sh status
   ```
