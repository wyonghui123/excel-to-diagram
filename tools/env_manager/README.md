# env_manager - 环境管理工具包 (V007.50 2026-07-14)

> **目标**: 把"基础设施可复用"从口头承诺变成可执行工具
> **当前状态**: v1.0 设计完成, 等待验证

---

## 一、设计原则

### 1.1 staging 暂作 3 角色（不变）
- ✅ **prod 双胞胎** — 部署前验证
- ✅ **远程 e2e** — 远程端到端测试
- ✅ **问题复现沙盒** — 用户报事故时复现

> ⚠️ **暂不创建独立 test 环境**（避免过度工程化）。staging 已承担 e2e + 排查职责。

### 1.2 优化同时作用于 staging + prod
任何对 `lib/env_common.sh` 或 `templates/*.sh` 的改进，**跑 `env_manager.sh render --env=<env>` 即生成对应脚本**，同时作用于 staging 和 prod。

---

## 二、目录结构

```
tools/env_manager/
├── README.md                 # 本文件
├── env_manager.sh            # 入口 (render / list / validate / diff)
├── environments.yaml         # 环境注册表 (prod / staging, 未来加 test 不影响现有)
├── lib/
│   └── env_common.sh         # 公共函数库 (load_env_config, gen_token, check_4_ports 等)
├── templates/                # 脚本模板 (参数化, 通过 env var 渲染)
│   ├── start_env.sh          # 启动 4 服务
│   ├── stop_env.sh           # 停止 4 服务
│   ├── health_check.sh       # 7 项健康检查
│   ├── e2e_test.sh           # 8 项 e2e + staging 扩展 3 项
│   └── rollback_env.sh       # 回滚到指定版本
└── generated/                # 渲染输出 (按环境分目录)
    ├── staging/
    │   ├── start_env.sh
    │   ├── stop_env.sh
    │   ├── health_check.sh
    │   ├── e2e_test.sh
    │   └── rollback_env.sh
    └── prod/
        └── ...
```

---

## 三、快速开始

### 3.1 列出所有环境

```bash
bash tools/env_manager/env_manager.sh list
# 输出:
#   - staging
#   - prod
```

### 3.2 校验 environments.yaml

```bash
bash tools/env_manager/env_manager.sh validate
# 输出:
#   [OK] staging: root=/opt/app/staging backend=13011 unified=18081 log=19101 core=19200
#   [OK] prod: root=/opt/app backend=3011 unified=8081 log=9101 core=9200
```

### 3.3 生成 staging 的所有脚本

```bash
bash tools/env_manager/env_manager.sh render --env=staging
# 输出: generated/staging/{start,stop,health_check,e2e_test,rollback_env}.sh
```

### 3.4 上传到远端 staging 服务器

```bash
# 把生成的脚本上传到 staging
scp generated/staging/*.sh root@172.20.59.7:/opt/app/staging/scripts/

# 在远端执行
ssh root@172.20.59.7 "bash /opt/app/staging/scripts/health_check.sh --env=staging"
```

### 3.5 对比生成的脚本与现有脚本

```bash
bash tools/env_manager/env_manager.sh diff --env=staging
# 输出端口对比 + 路径对比 + 关键脚本存在性
```

---

## 四、environments.yaml Schema

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | ✅ | 环境标识（小写英文） | `staging` |
| `description` | ✅ | 环境用途 | `staging - prod 双胞胎 + 远程 e2e + 问题复现沙盒` |
| `host` | ✅ | 远程主机 | `172.20.59.7` |
| `root_path` | ✅ | 环境根目录 | `/opt/app/staging` |
| `db_path` | ✅ | 独立 db 路径 | `/opt/app/staging/meta/architecture.db` |
| `ports.backend` | ✅ | Flask 后端端口 | `13011` |
| `ports.unified` | ✅ | 前端代理端口 | `18081` |
| `ports.log_service` | ✅ | log_service 端口 | `19101` |
| `ports.core_service` | ✅ | core_service 端口 | `19200` |
| `secret` | ✅ | Token SECRET | `v007.35-infra-staging` |
| `shared_pkgs` | ✅ | 共享 Python 包列表 | `[telemetry, mcp, rls, schema, config, tools]` |
| `systemd_unit` | ✅ | systemd unit 前缀 | `staging` |
| `db_source` | ✅ | db 来源 | `sync_from_prod` |
| `ssl_cert` | ⚠️ | SSL 证书路径 | `/opt/app/shared/core_service.crt` |
| `log_dir` | ✅ | 日志目录 | `/opt/app/staging/logs` |
| `browser_url` | ✅ | 浏览器入口 | `http://172.20.59.7:18081` |

---

## 五、扩展用途（staging 临时承担）

### 5.1 远程 e2e

```bash
# 在本地跑 staging e2e
bash tools/env_manager/env_manager.sh render --env=staging
scp generated/staging/e2e_test.sh root@172.20.59.7:/opt/app/staging/scripts/
ssh root@172.20.59.7 "bash /opt/app/staging/scripts/e2e_test.sh --env=staging"

# 预期: 11 项全 PASS (8 通用 + 3 staging 扩展)
```

### 5.2 问题复现沙盒

```bash
# 用户报事故 → 在 staging 复现
# 1. 同步 staging db (7 天前 backup)
ssh root@172.20.59.7 "bash /opt/app/shared/sync_staging_db.sh"

# 2. 跑 staging e2e 确认 baseline OK
ssh root@172.20.59.7 "bash /opt/app/staging/scripts/e2e_test.sh --env=staging"

# 3. 在 staging 重现用户操作 (用 audit_recovery.py 或 API)
ssh root@172.20.59.7 "python3 /opt/app/shared/audit_recovery.py find 1201"

# 4. 在 staging 验证修复 (不影响 prod)
# ...

# 5. 修复 OK 后部署到 prod
```

### 5.3 远程 chaos 演练（V007.50 staging 专属）

```bash
# 6 场景 chaos (readonly / busy / extlock / corrupt / deleted / full)
ssh root@172.20.59.7 "CHAOS_DB_PATH=/opt/app/staging/meta/architecture.db \
  CHAOS_DB_BAK=/opt/app/staging/meta/architecture.db.chaos_bak \
  /opt/miniconda3-py39/bin/python3 /opt/app/staging/bin/sqlite_chaos.py all"
```

---

## 六、关键设计决策

### 6.1 为什么不直接重命名 staging 脚本？
- staging 脚本已运行良好 (`start_staging.sh` 等), 重命名风险大
- env_manager **生成的是新脚本** (`start_env.sh`), 与旧脚本并存
- 验证通过后**逐步迁移**到新脚本, 旧脚本保留 1 周作为 backup

### 6.2 为什么 env_common.sh 是 shell 而非 Python？
- 现有 ops/start/rollback 都是 shell 脚本
- shell 与 systemd / cron / logrotate 集成更自然
- Python 仅用于 db 操作 (sqlite3 / yaml 解析)

### 6.3 为什么 yaml 解析用 awk 而非 python？
- 避免依赖 pyyaml
- 现有 yaml 格式规范 (无嵌套引号), awk 够用
- 如未来 yaml 变复杂, 再换 python 解析

### 6.4 为什么 start_env.sh 同时支持 prod 和 staging？
- 配置文件 (environments.yaml) 区分 prod 和 staging
- 脚本逻辑完全相同, 仅 env var 不同 (端口/路径/secret)
- 同一套优化作用于所有环境, 无分叉

---

## 七、未来增强路线图

### 7.1 短期 (本月)
- [ ] 把生成的 staging 脚本部署到远端, 验证
- [ ] 把生成的 prod 脚本备份 (不立即用)
- [ ] 加 `env_manager.sh validate` 集成到 pre-commit hook

### 7.2 中期 (下月)
- [ ] 加 staging_watchdog.sh (cron 1min 检查 4 端口, 挂则重启)
- [ ] 加 staging_db_backup.sh (ops_scheduler 任务)
- [ ] 加 logrotate.d/staging 配置 (防止日志无限增长)
- [ ] 加 systemd unit (staging_core_service.service 等)

### 7.3 长期 (下季度)
- [ ] 加 environments.yaml 的远程多机支持 (host 字段)
- [ ] 加 env_manager deploy (一键部署到远端)
- [ ] 加环境对比工具 (diff staging vs prod 端口/路径)
- [ ] 加 CI/CD 集成 (PR merge → 自动部署 staging)

---

## 八、与现有工具的关系

| 现有工具 | 关系 |
|---------|------|
| `tools/start_staging.sh` | ✅ **保留**, 验证 env_manager 生成脚本可用后再迁移 |
| `tools/stop_staging.sh` | ✅ 同上 |
| `tools/staging_e2e_test.sh` | ✅ 同上 |
| `tools/staging_health_check.sh` | ✅ 同上 |
| `tools/deploy.sh` | ⚠️ **不动**, deploy.sh 是部署, env_manager 是环境管理, 职责不同 |
| `tools/rollback.sh` | ⚠️ **不动**, 同上 |

**迁移计划**:
1. 第 1 周: env_manager 生成 staging 脚本, **双轨运行** (旧 + 新)
2. 第 2 周: 验证新脚本全部通过, 改 1 个调用方用新脚本
3. 第 3 周: 全量切换, 旧脚本备份到 `tools/deprecated/`
4. 第 4 周: 删除旧脚本

---

## 九、CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-14 | v1.0 | 初始设计: 5 模板 + 1 注册表 + 1 公共库 + 1 入口 |

---

**协调智能体 v2026-07-14 V007.50 - 基础设施可复用 + 未来扩展无忧**