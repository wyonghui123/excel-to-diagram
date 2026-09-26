---
name: "devops-deploy-sop"
description: "DevOps 部署 SOP 智能助手。Invoke when user says '开始部署', 'deploy', '部署', '查看状态', '回滚', '帮助'."
---

# DevOps 部署 SOP 智能助手

## 核心原则

**用户只需要说 3 句话，其他全部自动化！**

## 用户傻瓜化流程

```
用户说 "开始部署" 
    ↓
我自动：打包 + 生成上传命令 + 生成部署命令
    ↓
用户复制上传命令 → 堡垒机执行
    ↓
用户粘贴结果给我
    ↓
我生成部署命令
    ↓
用户复制部署命令 → 服务器执行
    ↓
用户粘贴结果给我
    ↓
我给出完整部署报告
```

## 标准触发命令

| 用户输入 | 我的响应 |
|----------|----------|
| "开始部署" / "部署" / "deploy" | 启动完整部署流程 |
| "查看状态" | 显示服务状态 |
| "查看日志" | 显示最新日志 |
| "健康检查" | 执行健康检查 |
| "回滚" | 生成回滚命令 |
| "重启" | 生成重启命令 |
| "停止" | 停止所有服务 |
| "帮助" | 显示所有命令 |

## 服务器环境配置

路径: `d:\filework\excel-to-diagram\config\environment\server-prod.toml`

| 配置项 | 值 |
|--------|-----|
| 服务器IP | 172.20.59.7 |
| 前端端口 | 8081 |
| 后端端口 | 5001 |
| Python | /opt/miniconda3-py39/bin/python |
| 应用目录 | /opt/app |
| 数据库 | /opt/app/shared/data/architecture.db |

## 部署流程标准回复

### 1. 触发部署

当用户说 "开始部署"，我需要：

```
1. 自动执行打包脚本（build-deploy-package.sh）
2. 生成上传命令（scp）
3. 生成一键部署命令
4. 生成回滚命令（备用）
```

### 2. 上传命令模板

```
scp "d:\filework\excel-to-diagram\deploy-v{version}.zip" \
     root@172.20.59.7:/opt/app/
```

### 3. 部署命令模板

```bash
cd /opt/app && \
unzip -o deploy-v{version}.zip -d tmp && \
mkdir -p deployments/v{version} && \
mv tmp/deploy-v{version}/* deployments/v{version}/ && \
ln -sfn deployments/v{version} current && \
ln -sfn /opt/app/shared/data current/data && \
ln -sfn /opt/app/shared/logs current/logs && \
pkill -f "server.py" 2>/dev/null; \
sleep 2 && \
cd /opt/app/current && \
PORT=8081 nohup python server.py > /opt/app/shared/logs/deploy.log 2>&1 & \
sleep 3 && \
cd /opt/app/meta && \
PORT=5001 nohup python server.py > /opt/app/shared/logs/backend.log 2>&1 & \
sleep 5 && \
echo "=== 部署完成 ===" && \
echo "前端:" && curl -s http://localhost:8081/health && \
echo "后端:" && curl -s http://localhost:5001/health && \
echo "=== 检查完成 ==="
```

### 4. 部署报告模板

```
================================================================================
                    部署完成报告
================================================================================

📦 版本：{version}
⏱  耗时：{duration}
🌐 访问：http://172.20.59.7:8081/

✅ 服务状态：
   前端服务 (8081)：✅ 运行中
   后端服务 (5001)：✅ 运行中

✅ 健康检查：
   前端 /health：✅ 通过
   后端 /health：✅ 通过
   API代理：✅ 通过

📝 可用命令：
   "查看状态" - 查看当前服务状态
   "查看日志" - 查看最新日志
   "回滚" - 回滚到上一版本
   "重启" - 重启所有服务
================================================================================
```

### 5. 回滚命令模板

```bash
cd /opt/app && \
PREV=$(cat /opt/app/state/previous_version 2>/dev/null) && \
ln -sfn /opt/app/backups/$PREV /opt/app/current && \
pkill -f "server.py" 2>/dev/null; \
sleep 2 && \
cd /opt/app/current && \
python server.py &
```

## 健康检查命令

> 后端健康端点只有 `/health`；`/api/v1/health` 已被 v1 sunset 中间件接管，
> 恒定返回 **410**（实测 2026-09-25），不要再引用。

```bash
# 检查端口
netstat -tlnp | grep -E "8081|5001"

# 检查服务
curl -s http://localhost:8081/health
curl -s http://localhost:5001/health      # ✅ 唯一存活探活点（含 apps/apps_mode）

# 检查API
curl -s http://localhost:8081/api/v1/product?page_size=1
```

## 应用清单排查（"这台服务器部署了哪些 app"）

> 优先用一条命令完成三方对账（全只读）：
> ```bash
> python tools/staging_round.py app-status --target production   # 或 --target staging
> ```
> 它同时打印 **应然**（deploy_topology.yaml 的 `apps`）／**实时**（`/health`）／**事实**
> （`runtime_apps.json`）三层，并逐条列出差异。下面四步是等价的手工核对路径。

```bash
# 1) 应然开关: 该实例启动时启用了哪些应用
grep ENABLED_APPS /opt/app/deployments/.env.prod

# 2) 实时: /health 返回 apps_mode / enabled_apps / apps[]
curl -s http://localhost:5001/health

# 3) 事实副本: 最后一次启动实际加载的应用（平台库同目录）
cat /opt/app/deployments/meta/runtime_apps.json

# 4) 目录 + 日志: 应用包落盘位置 + 启动期注册日志
ls /opt/app/deployments/apps/ 2>/dev/null
journalctl -u meta-backend.service | grep AppRegistry | tail -20
```

- `apps_mode: legacy` = 该实例未启用任何应用（legacy 平台实例）
- `apps_mode: enabled` = 至少加载了一个应用，逐个核对 `apps[].id` / `version` / `dir`
- 注意应用包根目录与 `meta/` **平级**（`/opt/app/deployments/apps/`），不在 `meta/` 内
- `/health` 未上报 `apps_mode` → 该实例仍在跑旧代码（可见性改动未部署）

## app 维度部署

```bash
# 按 deploy_topology.yaml 的 production.apps 清单展开整个 app 包
APPROVED_DEPLOY=1 python tools/staging_round.py prod-deploy --apps warehouse
```

- 文件集 = `apps/<id>/**`，自动排除 `data/`（应用库属运行数据，覆盖即丢数据）与 `__pycache__`
- 远端落点 = `{apps_root}/<id>/X`，独立于 `deploy_root`
- `apps_root` / `apps` 是清单 SSOT，改清单即改"这台服务器该有哪些 app"
- **清单门禁**：未登记的 app 在路径解析阶段即 `[ABORT]`
- **前置门禁（只读）**：prod 平台库缺 `installed_apps`（v090）会 abort；
  工具**不会自动执行迁移**，需先显式跑 v090 再加 `--apps`

## 问题处理标准回复

### 部署失败

```
⚠️  部署遇到问题

❌ 失败阶段：{阶段}
📝 问题描述：{描述}

建议操作：
1️⃣  自动重试
2️⃣  回滚到上一版本
3️⃣  手动排查问题

请回复："1" / "2" / "3"
```

### 服务异常

```
🔴 检测到服务异常！

❌ 异常服务：{service}
📝 异常信息：{error}

建议操作：
1️⃣  自动重启服务
2️⃣  查看详细日志
3️⃣  回滚到上一版本

请回复："1" / "2" / "3"
```

## 规范文档位置

- 部署标准: `d:\filework\excel-to-diagram\docs\DEPLOYMENT_STANDARDS.md`
- 用户SOP: `d:\filework\excel-to-diagram\docs\SOP-USER-DEPLOYMENT.md`
- 目录结构: `d:\filework\excel-to-diagram\docs\DIRECTORY_STRUCTURE.md`
- 环境配置: `d:\filework\excel-to-diagram\config\environment\server-prod.toml`

## 运维脚本位置

- 前置检查: `d:\filework\excel-to-diagram\scripts\server-preflight-check.sh`
- 环境快照: `d:\filework\excel-to-diagram\scripts\snapshot-environment.sh`
- 服务管理: `d:\filework\excel-to-diagram\scripts\service-manager.sh`
- 打包脚本: `d:\filework\excel-to-diagram\scripts\build-deploy-package.sh`
