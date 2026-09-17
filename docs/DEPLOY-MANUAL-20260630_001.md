# 部署操作手册 - v20260630_001

> **适用场景**：全新初始化部署（不保留旧数据）
> **重要提示**：`init_database.py --force` 会**删除现有数据库**，请确认备份已完成！
> **预计总耗时**：15 分钟（其中 Web SSH 部分约 10 分钟）

---

## 0. 准备工作（5 分钟）

### 0.1 待拷贝的固定信息

> ⚠️ 这些值在 Step 4 启动服务时需要使用，请**整段复制**保存

```
SERVER_IP=172.20.59.7
JWT_SECRET_KEY=j688XXn1fOFrIMFNqmRwmiuKq40KFBFOY0fw0GfoySM_0nbYPof6-5osHHR9Uwbx
ADMIN_PASSWORD=Admin@2026!Init
CORS_ORIGINS=http://172.20.59.7:8081,http://172.20.59.7:5001
```

### 0.2 需要确认的环境

| 项目 | 期望值 | 验证方法 |
|------|--------|---------|
| Python | 3.9.25 | `python -V` |
| OpenSSH | 10.3p1 | `ssh -V` |
| 服务器时间 | 与本地相差 ≤30 秒 | `date` |
| 端口 8081 空闲 | 未被占用 | `ss -tlnp \| grep 8081` |
| 端口 5001 空闲 | 未被占用 | `ss -tlnp \| grep 5001` |
| `/opt/app` 目录 | 存在且可写 | `ls -ld /opt/app` |

---

## 1. 阶段 A：通过堡垒机上传部署包（5 分钟）

> **这部分是你（运维）在堡垒机 web 控制台操作**

### Step A.1：登录堡垒机

1. 打开堡垒机 web 控制台
2. 用你的账号密码登录
3. 进入"文件传输"或"上传"功能
4. 选择目标服务器：`172.20.59.7`（按你公司的命名，可能是 "prod-app-01" 之类的）

### Step A.2：上传部署包

| 字段 | 值 |
|------|----|
| **本地文件** | `d:\filework\excel-to-diagram\deploy-v20260630_001.zip` |
| **远程路径** | `/tmp/` （先放到临时目录，下一步再到服务器上 mv） |
| **传输方式** | 二进制 / binary |

**预期输出**：
```
Upload completed: deploy-v20260630_001.zip (13.5 MB) / 100%
Elapsed: 45s
```

### Step A.3：确认上传成功

在堡垒机的 "文件管理" 中检查：
- `/tmp/deploy-v20260630_001.zip` 存在
- 大小 12.89 MB（zip 压缩）/ 解压后约 30 MB

✅ **完成上传后，继续执行 Step B（在服务器 Console）**

---

## 2. 阶段 B：通过 Web SSH 在服务器上操作（10 分钟）

> **这部分是你（运维）在 Web SSH 终端操作**
> **每一步都给出"复制粘贴"命令，直接回车即可**

### Step B.1：解压部署包

复制以下整段，粘贴到 Web SSH 终端，回车：

```bash
cd /opt/app && \
mkdir -p tmp_extract && \
mv /tmp/deploy-v20260630_001.zip tmp_extract/ 2>/dev/null; \
unzip -o tmp_extract/deploy-v20260630_001.zip -d tmp_extract/ && \
mkdir -p deployments/v20260630_001 && \
mv tmp_extract/frontend_dist_files tmp_extract/scripts tmp_extract/config tmp_extract/dependencies tmp_extract/backend tmp_extract/MANIFEST deployments/v20260630_001/ 2>/dev/null; \
rmdir tmp_extract/frontend_dist_files 2>/dev/null; \
ls -la deployments/v20260630_001/ | head -20 && \
echo "=== STEP B.1 OK: Unpack complete ==="
```

**预期输出**：
```
drwxr-xr-x  backend/
drwxr-xr-x  config/
drwxr-xr-x  dependencies/
drwxr-xr-x  frontend/
drwxr-xr-x  scripts/
-rw-r--r--  MANIFEST
=== STEP B.1 OK: Unpack complete ===
```

### Step B.2：建链接

```bash
cd /opt/app && \
ln -sfn /opt/app/deployments/v20260630_001 /opt/app/current_new && \
rm -f /opt/app/current && \
ln -sfn /opt/app/deployments/v20260630_001 /opt/app/current && \
ln -sfn /opt/app/shared/data /opt/app/current/data && \
ln -sfn /opt/app/shared/logs /opt/app/current/logs && \
mkdir -p /opt/app/shared/data /opt/app/shared/logs && \
ls -la /opt/app/current/ | head -10 && \
echo "=== STEP B.2 OK: Links created ==="
```

**预期输出**：
```
lrwxrwxrwx  current -> /opt/app/deployments/v20260630_001
=== STEP B.2 OK: Links created ===
```

### Step B.3：安装 Python 依赖（首次需要）

```bash
pip3 install -r /opt/app/current/meta/requirements.txt 2>&1 | tail -10
```

**预期输出**：
```
Successfully installed Flask-3.1.3 waitress-3.0.2 ...
```

> 如果提示 `pip3: command not found`，改用：
> ```bash
> /opt/miniconda3-py39/bin/pip install -r /opt/app/current/meta/requirements.txt
> ```

### Step B.4：备份旧库（如果存在）

```bash
if [ -f /opt/app/shared/data/architecture.db ]; then
    BACKUP_FILE="/opt/app/backups/architecture_$(date +%Y%m%d_%H%M%S).db.bak"
    cp /opt/app/shared/data/architecture.db "$BACKUP_FILE"
    echo "=== Backup saved to: $BACKUP_FILE ==="
else
    echo "=== No existing DB - first deploy, skipping backup ==="
fi
```

**预期输出**（首次部署）：
```
=== No existing DB - first deploy, skipping backup ===
```

### Step B.5：初始化数据库（删旧建新）

```bash
cd /opt/app/current/meta && \
python scripts/init_database.py --force 2>&1 | tail -10 && \
echo "=== STEP B.5 OK: DB schema created ==="
```

> ⚠️ 这一步**会删除旧库**，如有重要数据请先 B.4 备份！

**预期输出**：
```
Dropping old database...
Creating schema...
SQLite database created
=== STEP B.5 OK: DB schema created ===
```

### Step B.6：灌种子数据

```bash
cd /opt/app/current/meta && \
python scripts/init_and_seed.py --force 2>&1 | tail -15 && \
echo "=== STEP B.6 OK: Seed data loaded ==="
```

**预期输出**：
```
Created 4 domains
Created 8 sub-domains
Created 16 service modules
=== STEP B.6 OK: Seed data loaded ===
```

### Step B.7：初始化用户/角色/菜单（7 个脚本）

```bash
cd /opt/app/current/meta && \
python scripts/init_auth.py 2>&1 | tail -3 && \
echo "--- (1/7) init_auth OK ---" && \
python scripts/init_role_permissions.py 2>&1 | tail -3 && \
echo "--- (2/7) init_role_permissions OK ---" && \
python scripts/init_menu_permissions.py 2>&1 | tail -3 && \
echo "--- (3/7) init_menu_permissions OK ---" && \
python scripts/init_task_seed.py 2>&1 | tail -3 && \
echo "--- (4/7) init_task_seed OK ---" && \
python scripts/preload_hot_roles.py 2>&1 | tail -3 && \
echo "--- (5/7) preload_hot_roles OK ---" && \
echo "=== STEP B.7 OK: All init scripts done ==="
```

**预期输出**（最后一行）：
```
=== STEP B.7 OK: All init scripts done ===
```

### Step B.8：启动前端服务（端口 8081）

```bash
cd /opt/app/current && \
pkill -f "meta.server" 2>/dev/null; \
pkill -f "waitress-serve" 2>/dev/null; \
sleep 2 && \
PORT=8081 \
FLASK_DEBUG=false \
FLASK_ENV=production \
JWT_SECRET_KEY="j688XXn1fOFrIMFNqmRwmiuKq40KFBFOY0fw0GfoySM_0nbYPof6-5osHHR9Uwbx" \
CORS_ALLOWED_ORIGINS="http://172.20.59.7:8081,http://172.20.59.7:5001" \
ADMIN_PASSWORD="Admin@2026!Init" \
nohup python server.py > /opt/app/shared/logs/deploy.log 2>&1 & \
echo "Frontend started, PID=$!" && \
sleep 10 && \
curl -s http://localhost:8081/health && \
echo && \
echo "=== STEP B.8 OK: Frontend live on :8081 ==="
```

**预期输出**：
```
Frontend started, PID=12345
{"status":"ok"}      ← 这是 /health 响应
=== STEP B.8 OK: Frontend live on :8081 ===
```

### Step B.9：启动后端服务（端口 5001）

```bash
cd /opt/app/current/meta && \
PORT=5001 \
FLASK_DEBUG=false \
FLASK_ENV=production \
JWT_SECRET_KEY="j688XXn1fOFrIMFNqmRwmiuKq40KFBFOY0fw0GfoySM_0nbYPof6-5osHHR9Uwbx" \
CORS_ALLOWED_ORIGINS="http://172.20.59.7:8081,http://172.20.59.7:5001" \
ADMIN_PASSWORD="Admin@2026!Init" \
nohup python server.py > /opt/app/shared/logs/backend.log 2>&1 & \
echo "Backend started, PID=$!" && \
sleep 10 && \
curl -s http://localhost:5001/api/v1/health && \
echo && \
echo "=== STEP B.9 OK: Backend live on :5001 ==="
```

**预期输出**：
```
Backend started, PID=12346
{"status":"ok","db":"ok"}     ← /api/v1/health 响应
=== STEP B.9 OK: Backend live on :5001 ===
```

---

## 3. 阶段 C：验证（2 分钟）

### Step C.1：10 项检查清单

复制下面每行到终端执行，逐条对照：

```bash
echo "=== 部署验证清单 ===" && \
echo "[1] DB 文件存在：" && ls -la /opt/app/shared/data/architecture.db && \
echo "[2] DB 可读（admin 表）：" && sqlite3 /opt/app/shared/data/architecture.db "SELECT COUNT(*) FROM users;" && \
echo "[3] BO 模板已建：" && sqlite3 /opt/app/shared/data/architecture.db "SELECT COUNT(*) FROM business_objects;" && \
echo "[4] admin 用户存在：" && sqlite3 /opt/app/shared/data/architecture.db "SELECT username FROM users WHERE role='admin';" && \
echo "[5] 前端端口 8081：" && curl -s http://localhost:8081/health && \
echo && \
echo "[6] 后端端口 5001：" && curl -s http://localhost:5001/api/v1/health && \
echo && \
echo "[7] startup_checks 0 错误：" && grep -c "ERROR" /opt/app/shared/logs/backend.log || echo "0" && \
echo "[8] 进程都在跑：" && ps -ef | grep -E "server.py" | grep -v grep && \
echo "[9] 0 个端口冲突：" && ss -tlnp | grep -E "8081|5001" && \
echo "[10] CORS 检查通过：" && tail -5 /opt/app/shared/logs/deploy.log | grep -i "cors\|origins" && \
echo "=== 验证完成 ==="
```

**预期结果**：10 项全部输出

### Step C.2：浏览器验证

1. 打开浏览器（**建议用 Chrome 无痕模式**）
2. 访问：`http://172.20.59.7:8081/`
3. 预期看到登录页
4. 登录：
   - 用户名：`admin`
   - 密码：`Admin@2026!Init`
5. 进入后看到 4 个一级菜单

✅ **如果一切正常：部署成功！**

---

## 4. 回滚（如有问题）

如果部署后服务无法启动或验证失败：

```bash
/opt/app/scripts/rollback-enhanced.sh -a -f
```

这个脚本会：
1. 停止当前服务
2. 回退到上一个版本（**首次部署无历史版本，会失败**）
3. 恢复数据库备份（如有）

> ⚠️ **首次部署没有历史版本**，所以回滚只能解决"服务起不来"的问题，**数据库已删除则无法恢复**。所以 B.4 备份这一步很重要！

---

## 5. 快速对照表

| 阶段 | 步骤 | 耗时 | 你的角色 |
|------|------|------|---------|
| **0 准备** | 信息确认 | 5 min | 复制固定值 |
| **A 上传** | A.1 登录堡垒机 | 1 min | 手动 |
| | A.2 上传 zip | 1 min | 手动 |
| | A.3 确认文件 | 30s | 手动检查 |
| **B 服务器** | B.1 解压 | 30s | 粘贴+回车 |
| | B.2 建链接 | 10s | 粘贴+回车 |
| | B.3 安装依赖 | 2 min | 粘贴+回车 |
| | B.4 备份旧库 | 10s | 粘贴+回车 |
| | B.5 初始化 DB | 30s | 粘贴+回车 |
| | B.6 灌种子数据 | 30s | 粘贴+回车 |
| | B.7 权限/菜单 | 1 min | 粘贴+回车 |
| | B.8 启动前端 | 10s | 粘贴+回车 |
| | B.9 启动后端 | 10s | 粘贴+回车 |
| **C 验证** | C.1 检查清单 | 1 min | 粘贴+回车 |
| | C.2 浏览器 | 1 min | 手动 |
| **总计** | | **~13 min** | |

---

## 6. 常见问题

### Q1：粘贴命令后报 "Permission denied"

说明 `/opt/app/current/` 链接受损。重新执行 Step B.2。

### Q2：init_database.py 报 "no such table"

第一次跑 `init_and_seed.py` 时如果报"no such table products"，是 B.5 没跑成功。重新跑 B.5 + B.6。

### Q3：curl 健康检查返回 "Connection refused"

服务没起来。检查日志：
```bash
tail -50 /opt/app/shared/logs/deploy.log
tail -50 /opt/app/shared/logs/backend.log
```

### Q4：CORS 报错（浏览器报跨域）

确认 `CORS_ALLOWED_ORIGINS` 环境变量已设（Step B.8/B.9）。如果忘了，重启服务时加上即可。

### Q5：想看完整日志

```bash
tail -100 /opt/app/shared/logs/deploy.log /opt/app/shared/logs/backend.log
```

---

## 📞 卡住时把信息贴给我

把最后 50 行日志贴给我，我帮你定位：
```bash
tail -50 /opt/app/shared/logs/deploy.log /opt/app/shared/logs/backend.log
```

---

**文档版本**：v1.0 (2026-06-30)
**配套版本**：deploy-v20260630_001.zip
**配套 SOP**：[SOP-USER-DEPLOYMENT.md §十二](./SOP-USER-DEPLOYMENT.md)
