# 部署完整指南 (DEPLOYMENT.md)

> 完整的 Excel-to-Diagram 部署流程：准备 → 上传 → 部署 → 验证 → 回滚

---

## 1. 准备部署包（本地 Windows）

### 1.1 重建 `_deploy_bundle/`

```bash
cd D:\filework\release-prep-worktree
python tools/rebuild_bundle.py
```

**输出**：
```
_deploy_bundle/
├── deploy-v20260703_002.zip   (18.4 MB)
├── deploy.sh                  (13 KB)
├── precheck.sh                (6.8 KB)
├── smoke_test.sh              (6.3 KB)
├── rollback.sh                (4.8 KB)
├── unified_server.py          (5.5 KB)
├── lib/
│   └── common.sh              (6.6 KB)
└── README.txt                 (使用说明)
```

### 1.2 自检（推荐）

```bash
# 跑所有测试
python tools/test_deploy_generalized.py   # 通用化 (40 PASS)
python tools/test_precheck_smoke.py       # precheck+smoke (12 PASS)
python tools/e2e_sop_drill.py            # SOP 端到端 (18 PASS)
python tools/self_test.py                # 工具自检 (26 PASS)
```

**期望**：全 PASS

---

## 2. 上传到远端（堡垒机/MobaXterm）

### 2.1 打开堡垒机

浏览器 → `jumper.yyuap.com` → 登录 → 双因子 → 进 172.20.59.7

### 2.2 MobaXterm SFTP 拖文件

- MobaXterm → SFTP 标签
- 左侧本地：`D:\filework\release-prep-worktree\_deploy_bundle\`
- 右侧远端：`/tmp/`
- **拖整个 `_deploy_bundle/` 目录**（不是单个文件！）

### 2.3 验证上传

```bash
# 远端终端
ls -la /tmp/_deploy_bundle/
# 应该看到 7 个文件 + lib/ 目录
```

---

## 3. 部署 v004（堡垒机终端）

### 3.1 一键命令

```bash
bash /tmp/_deploy_bundle/deploy.sh --version v20260703_002 --port 5001
```

**脚本自动**（9 阶段）：
1. **PHASE 0: precheck**（7 项健康检查）
2. **PHASE 0.5: 解压 zip**
3. **PHASE 1: 停旧服务**
4. **PHASE 2: 备份 + 复制 db**
5. **PHASE 3: 写 systemd service**（如启用）
6. **PHASE 4: 启 backend（5001）**
7. **PHASE 5: 启 unified server（8081）**
8. **PHASE 6: curl 验证**
9. **PHASE 6.5: smoke test（5 项真实功能）**
10. **PHASE 7: 切 current 链接**

**总耗时**：~30 秒

### 3.2 完整参数

```bash
bash /tmp/_deploy_bundle/deploy.sh \
    --version v20260703_002 \           # 必填
    --port 5001 \                        # 必填
    --zip /opt/app/deploy-...zip \       # 可选, 默认自动找
    --frontend-port 8081 \               # 可选
    --db-source /path/to/old.db \        # 可选, 默认 current 版本
    --deploy-root /opt/app \             # 可选
    --unified /tmp/unified_server.py \   # 可选
    --skip-precheck \                    # 可选
    --skip-smoke \                       # 可选
    --no-systemd                         # 可选 (默认 no-systemd)
```

### 3.3 验证部署成功

DEPLOY SUMMARY 应该输出：
```
✓ 全部 PASS
浏览器访问: http://172.20.59.7:8081/
登录: admin / admin123
```

如果 FAIL：
- 看后端 log: `tail -f /opt/app/shared/logs/backend-v20260703_002.log`
- 看前端 log: `tail -f /opt/app/shared/logs/frontend-v20260703_002.log`

---

## 4. 浏览器验证

### 4.1 访问前端

浏览器：`http://172.20.59.7:8081/`

应该看到 v004 的登录页面。

### 4.2 登录

- 用户名：`admin`
- 密码：`admin123`

### 4.3 验证 enum mutability 修复

菜单 → enum 管理 → 检查是否有以下 mutability 值：
- ✅ `fullEditable`（v004 修复后的值）
- ✅ `extensible`
- ✅ `locked`
- ❌ `fully_editable`（**不应该出现**）

---

## 5. 出问题回滚

### 5.1 一键回滚

```bash
bash /tmp/_deploy_bundle/rollback.sh --to v20260630_003 --port 5000
```

**回滚**：
- 停 v004（5001）
- 启 v003（5000）
- 切 current 链接 → v003

### 5.2 完整回滚参数

```bash
bash /tmp/_deploy_bundle/rollback.sh \
    --to v20260630_003 \                 # 必填
    --port 5000 \                        # 必填
    --frontend-port 8081 \               # 可选
    --deploy-root /opt/app \             # 可选
    --no-systemd                         # 可选
```

### 5.3 验证回滚成功

```bash
# 远端
curl -s -o /dev/null -w "5000: HTTP %{http_code}\n" http://localhost:5000/api/v1/health
# 应该 200

curl -s -o /dev/null -w "8081: HTTP %{http_code}\n" http://localhost:8081/
# 应该 200
```

---

## 6. 部署新版本 (v005+)

### 6.1 准备新 zip

```bash
# 本地
python tools/rebuild_bundle.py --zip deploy-v20260801_001.zip
```

### 6.2 上传 + 部署

```bash
# MobaXterm SFTP 上传新 _deploy_bundle/

# 远端
bash /tmp/_deploy_bundle/deploy.sh --version v20260801_001 --port 5002
```

**关键**：**不改脚本**，只改 `--version --port` 参数。

---

## 7. 并行部署多版本

v003 (5000) + v004 (5001) + v005 (5002) 可同时跑：

```bash
# v003
bash /tmp/_deploy_bundle/deploy.sh --version v20260630_003 --port 5000

# v004
bash /tmp/_deploy_bundle/deploy.sh --version v20260703_002 --port 5001

# v005
bash /tmp/_deploy_bundle/deploy.sh --version v20260801_001 --port 5002
```

**注意**：8081 frontend 只能一个版本（切换需重启 unified）。

---

## 8. 文件位置速查

### 远端 (172.20.59.7)

| 路径 | 内容 |
|------|------|
| `/opt/app/current` | 符号链接，指向当前激活版本 |
| `/opt/app/deployments/v<version>/` | 版本目录 |
| `/opt/app/shared/logs/` | 所有日志 |
| `/opt/app/backups/` | db 备份 |
| `/tmp/_deploy_bundle/` | 部署包（你 SFTP 上传的）|
| `/etc/systemd/system/excel-backend.service` | systemd service |

### 本地 (D:\filework\release-prep-worktree)

| 路径 | 内容 |
|------|------|
| `tools/` | 所有脚本 |
| `_deploy_bundle/` | 一键部署包 |
| `build/verify/` | v004 解压后的代码 |
| `deploy-v20260703_002.zip` | v004 打包 |

---

## 9. 部署时间线示例（这次 v004 部署）

| 时间 | 事件 | 工具 |
|------|------|------|
| 08:00 | systemd 启旧 service 失败（旧 python 路径） | 远端 log |
| 08:30 | 改 service 用 miniconda3-py39 | sed |
| 09:00 | 写 SOP 工具套件 | tools/ |
| 10:00 | 通用化 deploy/rollback | refactor |
| 10:30 | 加 precheck + smoke | precheck.sh, smoke_test.sh |
| 10:45 | 重建 _deploy_bundle/ | rebuild_bundle.py |
| 11:00 | **真远端部署**（你执行）| deploy.sh |
