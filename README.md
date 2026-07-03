# Excel-to-Diagram 部署基础设施 (SOP)

> **目标**：一次建设，长期使用，部署/回滚/验证全流程自动化

---

## 5 分钟上手

### 1. 准备部署包（本地）

```bash
# 重建 _deploy_bundle/ (包含 zip + 所有脚本)
python tools/rebuild_bundle.py
# 输出: _deploy_bundle/ 目录 (~18.4 MB)
```

### 2. 上传到远端（一次性）

**MobaXterm SFTP**：拖 `_deploy_bundle/` → 远端 `/tmp/`

### 3. 一键部署（堡垒机终端）

```bash
bash /tmp/_deploy_bundle/deploy.sh --version v20260703_002 --port 5001
```

**自动完成**：
- precheck（7 项健康检查）
- 解压 zip
- 备份 + 复制 db
- 启 v004 backend（5001）
- 启 unified server（8081）
- smoke test（5 项真实功能）
- 切 current 链接

### 4. 出问题回滚

```bash
bash /tmp/_deploy_bundle/rollback.sh --to v20260630_003 --port 5000
```

---

## 工具清单

```
tools/
  ├── deploy.sh            # 通用部署 (任何版本可用)
  ├── rollback.sh          # 通用回滚
  ├── precheck.sh          # 部署前 7 项检查
  ├── smoke_test.sh        # 部署后 5 项真实测试
  ├── unified_server.py    # 静态文件 + API 代理 (单端口 serve)
  ├── lib/common.sh        # 共享库 (17 函数)
  ├── rebuild_bundle.py    # 自动生成 _deploy_bundle/
  │
  ├── e2e_sop_drill.py     # SOP 端到端演练
  ├── self_test.py         # 工具自检
  ├── test_deploy_generalized.py  # 通用性测试 (40 PASS)
  ├── test_precheck_smoke.py      # precheck+smoke 测试 (12 PASS)
  │
  ├── precheck_remote.sh   # 远端事实采集
  ├── diff_local_remote.py # 本地 vs 远端 diff
  ├── verify_deploy.py     # Playwright 端到端验证
  │
  └── repackage_zip.py     # 重新打包工具
```

---

## 部署 v005 流程（未来示例）

```bash
# 本地
python tools/rebuild_bundle.py --zip deploy-v20260801_001.zip

# SFTP 上传 _deploy_bundle/

# 远端
bash /tmp/_deploy_bundle/deploy.sh --version v20260801_001 --port 5002
```

**脚本自动适配**——不需改代码，只改参数。

---

## 测试覆盖

| 测试 | 工具 | PASS |
|------|------|------|
| 通用化 (无版本 hardcode) | test_deploy_generalized.py | 40/0 |
| precheck + smoke 逻辑 | test_precheck_smoke.py | 12/0 |
| SOP 端到端 | e2e_sop_drill.py | 18/0 |
| 工具自检 | self_test.py | 26/0 |

---

## 关键设计原则

1. **通用** - 一套脚本适用所有版本
2. **健壮** - 7 项 precheck + 5 项 smoke
3. **可逆** - 任何部署都能回滚
4. **可观察** - 统一日志入口 + 端口 + 状态
5. **低门槛** - 堡垒机一命令搞定

---

详细见 [DEPLOYMENT.md](DEPLOYMENT.md) 和 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
