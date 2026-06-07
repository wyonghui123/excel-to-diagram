# 运维脚本使用指南

> **文档版本**: v1.0  
> **更新日期**: 2026-04-29  
> **适用范围**: 服务器运维

---

## 一、脚本概览

| 脚本名称 | 功能 | 优先级 | 状态 |
|---------|------|--------|------|
| `rollback-enhanced.sh` | 增强版回滚 | P0 | ✅ 已完成 |
| `health-check.sh` | 健康检查 | P0 | ✅ 已完成 |
| `snapshot-enhanced.sh` | 环境快照 | P0 | ✅ 已完成 |
| `post-deploy-verify.sh` | 部署后验证 | P1 | ✅ 已完成 |

---

## 二、快速开始

### 2.1 上传到服务器

```bash
# 在堡垒机执行
scp scripts/*.sh root@172.20.59.7:/opt/app/scripts/
ssh root@172.20.59.7 "chmod +x /opt/app/scripts/*.sh"
```

### 2.2 常用命令速查

```bash
# 健康检查
/opt/app/scripts/health-check.sh

# 生成环境快照
/opt/app/scripts/snapshot-enhanced.sh snapshot

# 查看快照历史
/opt/app/scripts/snapshot-enhanced.sh list

# 回滚到上一版本
/opt/app/scripts/rollback-enhanced.sh -a

# 部署后验证
/opt/app/scripts/post-deploy-verify.sh
```

---

## 三、详细使用说明

### 3.1 回滚脚本 (`rollback-enhanced.sh`)

**功能**: 支持自动备份、健康检查、快速回滚

**用法**:

```bash
# 交互式选择版本回滚
/opt/app/scripts/rollback-enhanced.sh

# 列出所有可用版本
/opt/app/scripts/rollback-enhanced.sh -l

# 自动回滚到上一版本
/opt/app/scripts/rollback-enhanced.sh -a

# 备份后回滚到指定版本
/opt/app/scripts/rollback-enhanced.sh -b v20250415_001

# 强制回滚（跳过确认）
/opt/app/scripts/rollback-enhanced.sh -f v20250415_001

# 仅执行健康检查
/opt/app/scripts/rollback-enhanced.sh -c

# 显示当前状态
/opt/app/scripts/rollback-enhanced.sh -s
```

**特性**:
- ✅ 自动备份当前版本和数据库
- ✅ 健康检查确保回滚成功
- ✅ 支持交互式和命令行模式
- ✅ 记录回滚历史

---

### 3.2 健康检查脚本 (`health-check.sh`)

**功能**: 自动化检查所有服务、数据库、依赖项的健康状态

**用法**:

```bash
# 执行完整健康检查
/opt/app/scripts/health-check.sh

# 静默模式
/opt/app/scripts/health-check.sh -q

# 只输出 JSON 报告
/opt/app/scripts/health-check.sh -j

# 遇到失败立即退出
/opt/app/scripts/health-check.sh -f

# 只检查服务
/opt/app/scripts/health-check.sh -c services

# 只检查数据库
/opt/app/scripts/health-check.sh -c database
```

**检查项**:
- 前端服务 (端口 8081)
- 后端服务 (端口 5001)
- Admin 服务 (端口 8080)
- 数据库文件和表
- Python 环境和依赖包
- 磁盘空间
- 内存使用
- 当前版本

**报告位置**: `/opt/app/state/health-report.json`

---

### 3.3 环境快照脚本 (`snapshot-enhanced.sh`)

**功能**: 记录环境状态，支持变更检测、历史对比、自动告警

**用法**:

```bash
# 生成当前环境快照
/opt/app/scripts/snapshot-enhanced.sh snapshot

# 查看最新快照
/opt/app/scripts/snapshot-enhanced.sh view

# 查看指定快照
/opt/app/scripts/snapshot-enhanced.sh view /opt/app/state/snapshots/snapshot_20240428_120000.json

# 列出所有快照
/opt/app/scripts/snapshot-enhanced.sh list

# 对比两个快照
/opt/app/scripts/snapshot-enhanced.sh diff snapshot_20240428_120000.json

# 对比两个指定快照
/opt/app/scripts/snapshot-enhanced.sh diff snapshot_20240428_120000.json snapshot_20240429_080000.json

# 清理旧快照（保留最近5个）
/opt/app/scripts/snapshot-enhanced.sh cleanup 5

# 设置定时快照
/opt/app/scripts/snapshot-enhanced.sh schedule
```

**快照内容**:
- 系统信息（OS、内核、运行时间）
- 版本信息（当前版本、上一版本）
- Python 环境（版本、路径、关键包）
- 服务状态（前端、后端、Admin）
- 目录信息（存在性、大小、修改时间）
- 数据库信息（表数、记录数、版本）
- 资源使用（磁盘、内存、CPU）
- 网络信息（IP 地址）

**告警阈值**:
- 磁盘使用率 >= 90%
- 服务未运行
- 数据库文件不存在

**快照位置**: `/opt/app/state/snapshots/`

---

### 3.4 部署后验证脚本 (`post-deploy-verify.sh`)

**功能**: 自动执行健康检查、生成快照、发送通知

**用法**:

```bash
# 完整验证流程
/opt/app/scripts/post-deploy-verify.sh

# 快速模式（跳过等待）
/opt/app/scripts/post-deploy-verify.sh -q

# 不生成快照
/opt/app/scripts/post-deploy-verify.sh -n

# 详细输出
/opt/app/scripts/post-deploy-verify.sh -v
```

**执行流程**:
1. 等待服务启动（最多60秒）
2. 执行健康检查
3. 生成环境快照
4. 生成部署报告

**报告位置**: `/opt/app/state/deploy-report-YYYYMMDD-HHMMSS.txt`

---

## 四、集成到部署流程

### 4.1 部署脚本集成

修改 `deploy-auto.sh`，在部署完成后自动执行验证：

```bash
# 在 deploy-auto.sh 末尾添加

# 部署后验证
if [[ -f "$APP_DIR/scripts/post-deploy-verify.sh" ]]; then
    echo ""
    echo "执行部署后验证..."
    bash "$APP_DIR/scripts/post-deploy-verify.sh"
fi
```

### 4.2 Crontab 定时任务

```bash
# 每小时执行健康检查
0 * * * * /opt/app/scripts/health-check.sh -q >> /opt/app/shared/logs/health-cron.log 2>&1

# 每天生成快照
0 2 * * * /opt/app/scripts/snapshot-enhanced.sh snapshot >> /opt/app/shared/logs/snapshot-cron.log 2>&1

# 每周清理旧快照
0 3 * * 0 /opt/app/scripts/snapshot-enhanced.sh cleanup 10 >> /opt/app/shared/logs/snapshot-cron.log 2>&1
```

---

## 五、故障排查

### 5.1 健康检查失败

```bash
# 查看详细报告
cat /opt/app/state/health-report.json | python3 -m json.tool

# 手动检查服务
curl -v http://localhost:8081/
curl -v http://localhost:5001/api/v1/health
curl -v http://localhost:8080/admin
```

### 5.2 回滚失败

```bash
# 查看回滚历史
cat /opt/app/state/rollback-history.log

# 手动检查版本
ls -la /opt/app/current
ls -la /opt/app/releases/

# 手动回滚
rm -f /opt/app/current
ln -s /opt/app/releases/v20250415_001 /opt/app/current
```

### 5.3 快照问题

```bash
# 检查快照目录
ls -la /opt/app/state/snapshots/

# 手动生成快照
/opt/app/scripts/snapshot-enhanced.sh snapshot

# 查看快照历史
cat /opt/app/state/snapshot-history.log
```

---

## 六、文件清单

```
/opt/app/scripts/
├── rollback-enhanced.sh      # 增强版回滚脚本
├── health-check.sh           # 健康检查脚本
├── snapshot-enhanced.sh      # 环境快照脚本
├── post-deploy-verify.sh     # 部署后验证脚本
├── service-manager.sh        # 服务管理脚本（已有）
├── server-preflight-check.sh # 部署前检查脚本（已有）
└── build-deploy-package.sh   # 打包脚本（已有）

/opt/app/state/
├── health-report.json        # 健康检查报告
├── environment-snapshot.json # 当前环境快照
├── snapshots/                # 历史快照目录
│   ├── snapshot_20240428_120000.json
│   └── ...
├── rollback-history.log      # 回滚历史记录
└── snapshot-history.log      # 快照历史记录
```

---

## 七、注意事项

1. **权限**: 所有脚本需要 root 权限运行
2. **依赖**: 依赖 `python3`、`curl`、`netstat` 等命令
3. **配置**: 自动读取 `/opt/app/config/environment/server-prod.toml`
4. **日志**: 所有操作日志保存在 `/opt/app/shared/logs/`

---

## 八、更新记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04-29 | 1.0 | 初始版本，包含4个核心脚本 |
