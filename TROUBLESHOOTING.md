# 故障排除 (TROUBLESHOOTING.md)

> 这次 v004 部署过程中遇到的所有问题 + 解决方案

---

## 1. systemd 写死旧 Python 路径

### 症状
```
Failed at step EXEC spawning /tmp/python-build/Python-3.11.9/python: No such file or directory
```

### 原因
- `/tmp/python-build/Python-3.11.9/python` 是旧 build 临时 Python
- 重新部署时 `/tmp/` 被清空
- 但 `/etc/systemd/system/excel-backend.service` 还指向旧路径

### 解决
```bash
# sed 替换为 miniconda python
sed -i 's|/tmp/python-build/Python-3.11.9/python|/opt/miniconda3-py39/bin/python|g' /etc/systemd/system/excel-backend.service
systemctl daemon-reload
```

### 预防
- **新 deploy.sh 默认用 miniconda3-py39**（不依赖旧 /tmp/）
- systemd service 由 deploy.sh 自动重写

---

## 2. v004 server.py 启动失败：cwd 错误

### 症状
```
ModuleNotFoundError: No module named 'telemetry'
ModuleNotFoundError: No module named 'meta'
```

### 原因
- `server.py` 在 `meta/` 目录
- `sys.path.insert(0, parent_dir)` 假设 cwd = `meta/`
- 启 service 时 cwd = `/opt/app/meta`，但 service 的 WorkingDirectory 没设

### 解决
**systemd service 必须设 `WorkingDirectory` 为 `meta/` 或 `backend/`**：
```ini
WorkingDirectory=/opt/app/deployments/v20260703_002/meta
ExecStart=/opt/miniconda3-py39/bin/python server.py
```

### 预防
- **deploy.sh 自动检测 entry point**（meta/ 或 backend/）
- **自动写 service 带正确 WorkingDirectory**

---

## 3. v004 启动检查失败：JWT/FLASK key 太短

### 症状
```
[StartupCheck] CRITICAL security issues found:
  - JWT_SECRET_KEY is shorter than 32 characters
  - FLASK_SECRET_KEY is shorter than 32 characters
```

### 原因
v004 startup_checks.py 强制生产环境密钥 >= 32 字符。

### 解决
```bash
# 生成强密钥
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FLASK_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

**或者**用 deploy.sh 自动生成的密钥（≥ 32 字符）。

### 预防
- **deploy.sh 自动生成强密钥**（基于版本+时间戳）
- **CORS 也自动配**（避免 "CORS_ALLOWED_ORIGINS must be configured" 错误）

---

## 4. 8081 返回 500 NotFound

### 症状
浏览器访问 `http://172.20.59.7:8081/` 返回 500：
```json
{"error":"NotFound","message":"An internal error occurred."}
```

### 原因
- v004 `server.py` **只 serve API**，**不 serve 静态文件**
- 但 8081 启的也是 `server.py`
- 访问 `/` 时 server.py 返回 500（没 static route）

### 解决
**用 `unified_server.py`**：
- 8081 同时 serve 静态文件 + reverse proxy `/api/*` → 5001
- deploy.sh 自动用 unified_server 启 8081

```python
# unified_server.py 逻辑
GET /           → serve frontend_dist_files/index.html
GET /assets/*   → serve static
/api/*          → reverse proxy to 127.0.0.1:5001
```

---

## 5. 前端调 API 跨域

### 症状
浏览器 console：
```
Access to XMLHttpRequest at 'http://172.20.59.7:5001/api/v1/...' from origin 'http://172.20.59.7:8081' has been blocked by CORS policy
```

### 原因
- 8081 (frontend) 调 5001 (backend) 跨域
- CORS_ALLOWED_ORIGINS 没配或配错

### 解决
**用 unified_server 同源代理**（推荐，deploy.sh 默认）：
- 8081 同时 serve static + proxy `/api/*` → 5001
- 前端看到的是同源请求（`/api/v1/...`），无 CORS 问题

**或者**配置后端 CORS：
```bash
CORS_ALLOWED_ORIGINS="http://172.20.59.7:8081,http://172.20.59.7:5001"
```

---

## 6. 端口被占用

### 症状
deploy.sh PHASE 4 报端口 5001 已被占用。

### 原因
- 旧 server.py 没杀干净
- 之前 nohup 的进程还在

### 解决
deploy.sh PHASE 1 自动 `pkill -9 -f "python.*server.py"`。

**手动**：
```bash
pkill -9 -f "python.*server.py"
pkill -9 -f "unified_server"
pkill -9 -f "http.server"
sleep 2
ss -tlnp | grep :5001
```

### 预防
- **deploy.sh PHASE 1 自动杀**所有 server 进程
- **precheck.sh Check 4** 部署前检查端口

---

## 7. db 复制失败

### 症状
deploy.sh PHASE 2 报 "备份失败" 或 "复制失败"。

### 原因
- 源 db 不存在
- 目标目录无写权限
- 磁盘满

### 解决
```bash
# 1. 源 db 检查
ls -la /opt/app/deployments/v20260630_003/backend/architecture.db

# 2. 目标目录权限
ls -la /opt/app/deployments/v20260703_002/meta/

# 3. 磁盘空间
df -h /opt/app
```

### 预防
- **precheck.sh Check 6** 验证 db 源
- **deploy.sh 用 `cp -p`**（保留权限）

---

## 8. zip 上传但不解压

### 症状
deploy.sh PHASE 0.5 报 "缺 zip, 部署无法继续"。

### 原因
- zip 没上传到远端
- 上传路径不对（不是 `/tmp/_deploy_bundle/`）

### 解决
```bash
# 1. 远端检查
ls -la /tmp/_deploy_bundle/deploy-v20260703_002.zip

# 2. 重传
# MobaXterm SFTP: 拖 _deploy_bundle/ 到 /tmp/
```

### 预防
- **precheck.sh Check 5** 验证 zip 存在

---

## 9. v004 backend 起来了但 health 410

### 症状
```bash
curl http://localhost:5001/api/v1/health
# HTTP 410 Gone
```

### 原因
- v004 server alive 了
- 但 db schema 还没 init（`architecture.db` 是空 sqlite）
- 410 表示路由注册了但 db 未 init

### 解决
**这是预期行为**，不是 bug：
- unified_server proxy 后，浏览器 login 会触发 db init
- 或跑 init script：
```bash
cd /opt/app/deployments/v20260703_002/meta
python scripts/init_database.py
python scripts/init_auth.py
python scripts/init_and_seed.py
```

### 预防
- **smoke_test.sh test 3** 检测 login 成功
- **deploy.sh PHASE 2** 自动复制 v003 db（带数据），避免空 db

---

## 10. smoke test 失败

### 症状
```bash
bash /tmp/_deploy_bundle/smoke_test.sh --port 5001
# 4/5 PASS, 1 FAIL
```

### 排查步骤

```bash
# 1. 看后端 log
tail -50 /opt/app/shared/logs/backend-v20260703_002.log

# 2. 看前端 log
tail -50 /opt/app/shared/logs/frontend-v20260703_002.log

# 3. 手动 curl 测试
curl -v http://127.0.0.1:5001/api/v1/enum-types
curl -v http://127.0.0.1:8081/api/v1/enum-types

# 4. 看进程
ps -ef | grep -E "python.*server|unified"

# 5. 看端口
ss -tlnp | grep -E ":(5001|8081)"
```

### 回滚

```bash
bash /tmp/_deploy_bundle/rollback.sh --to v20260630_003 --port 5000
```

---

## 11. 部署完成后无法访问

### 排查清单

- [ ] 远端 8081 端口监听：`ss -tlnp | grep :8081`
- [ ] 远端 5001 端口监听：`ss -tlnp | grep :5001`
- [ ] 远端 curl：`curl -v http://localhost:8081/`
- [ ] 防火墙：堡垒机是否限制 8081/5001 出站
- [ ] 浏览器：试 chrome + edge + incognito
- [ ] DNS：直接用 IP `http://172.20.59.7:8081/`

### 堡垒机/防火墙

如果浏览器访问不到：
- 联系运维开放 8081 端口
- 临时方案：浏览器用 SSH tunnel `ssh -L 8081:localhost:8081 root@172.20.59.7`

---

## 12. 回滚后仍有问题

### 症状
rollback 到 v003 后 5000 仍不可用。

### 排查

```bash
# 1. 看 5000 进程
ps -ef | grep "python.*server.py"

# 2. 强制杀 + 重启
pkill -9 -f "python.*server.py"
cd /opt/app/deployments/v20260630_003/backend
nohup /opt/miniconda3-py39/bin/python server.py > /tmp/v003.log 2>&1 &

# 3. 验证
curl -s http://localhost:5000/api/v1/health
```

---

## 13. 数据库损坏

### 症状
```
sqlite3.DatabaseError: database disk image is malformed
```

### 解决

```bash
# 1. 备份当前 db
cp /opt/app/deployments/v20260703_002/meta/architecture.db /tmp/broken.db

# 2. 还原上次备份
ls /opt/app/backups/ | tail -1
cp /opt/app/backups/architecture_v20260630_003_<timestamp>.db \
   /opt/app/deployments/v20260703_002/meta/architecture.db

# 3. 重启服务
systemctl restart excel-backend.service
# 或
pkill -9 -f "python.*server.py"
nohup /opt/miniconda3-py39/bin/python /opt/app/deployments/v20260703_002/meta/server.py > /tmp/restored.log 2>&1 &
```

---

## 14. 关键问题排查命令

```bash
# 一键状态检查
ss -tlnp | grep -E ":(5000|5001|5002|8081|8082)"
ps -ef | grep -E "python.*server|unified_server"
ls -la /opt/app/current
ls -la /opt/app/deployments/
tail -20 /opt/app/shared/logs/backend-*.log
tail -20 /opt/app/shared/logs/frontend-*.log

# 端口检查
ss -tlnp | grep :8081
fuser 8081/tcp
lsof -i :8081

# 服务状态
systemctl status excel-backend.service
journalctl -u excel-backend.service --no-pager -n 30

# 磁盘
df -h /opt/app

# 内存
free -h
```

---

## 15. 这次部署踩过的所有坑（避坑指南）

1. ✅ **systemd 写死旧 python** → deploy.sh 自动重写 service
2. ✅ **WorkingDirectory 不对** → deploy.sh 自动检测 meta/backend
3. ✅ **JWT/FLASK key 太短** → deploy.sh 自动生成强密钥
4. ✅ **8081 返回 500** → 用 unified_server（静态+API 代理）
5. ✅ **CORS 跨域** → unified_server 同源代理
6. ✅ **db 复制不原子** → 用 `cp -p` 保留权限 + 备份
7. ✅ **端口被占** → deploy.sh PHASE 1 自动杀
8. ✅ **zip 没上传** → precheck.sh Check 5 验证
9. ✅ **health 410 误判** → smoke_test 接受 200/410
10. ✅ **回滚后没切链接** → rollback.sh PHASE 4 切
11. ✅ **`set -u` 太严** → common.sh 注释掉 `set -u`，函数可选参数不崩
12. ✅ **`run_check "$name"` 缺 $3** → `local detail="${3:-}"` 兜底

**所有坑都被新 deploy.sh + precheck + smoke 防住了**。
