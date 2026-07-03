# DEPLOY_SOP.md - Excel to Diagram 部署标准操作流程 (SOP v2.0)

> **核心原则**: 事实优先于推理, 验证先于执行, 单步可回滚。

---

## 🎯 设计哲学

| 反模式 (不要做) | 正模式 (要做) |
|----------------|--------------|
| ❌ 看 README 预测包结构 | ✅ 实际 ls 看包结构 |
| ❌ 假设 Python 在 PATH | ✅ which / ls /opt 找真实路径 |
| ❌ 假设 systemd 启的是 X | ✅ cat service 文件看 ExecStart |
| ❌ 假设端口是 X | ✅ curl 实际测 |
| ❌ 用户截图报"成功"就信 | ✅ 自己用 Playwright 验证 |
| ❌ 一次跑所有步骤 | ✅ 单步执行, 每步验证 |
| ❌ 出错时猜下一步 | ✅ 出错时看事实, 重新规划 |

---

## 📁 工具清单

| 工具 | 用途 | 何时用 |
|------|------|--------|
| `tools/precheck_remote.sh` | 远程事实采集 (PHASE 0) | 部署前必跑 |
| `tools/diff_local_remote.py` | 本地 vs 远端差异 | 打包后必跑 |
| `tools/deploy_step.sh` | 单步部署 + 验证 | 每个 step 必跑 |
| `tools/verify_deploy.py` | Playwright 端到端验证 | 部署后必跑 |
| `tools/rollback.sh` | 一键回滚 | 出问题必跑 |

---

## 🚀 部署流程 (5 个阶段)

### PHASE 0: 事实采集 (10 分钟)

**目标**: 输出"远端现状事实报告"

```bash
# 远端跑
bash tools/precheck_remote.sh > /tmp/precheck-$(date +%Y%m%d_%H%M%S).txt 2>&1
cat /tmp/precheck-*.txt
```

**必看项**:
- [ ] 当前 systemd service 配置 (`WorkingDirectory`, `ExecStart`)
- [ ] 当前 Python 解释器路径
- [ ] 当前进程 (PID, cwd, cmdline)
- [ ] 当前端口监听 (5000/5001/8080/8081)
- [ ] 当前 db 文件 (位置, 大小, 是否有 enum_types)
- [ ] 当前 server.py 的关键 import
- [ ] 三个端口 curl 实测结果

**绝不要**:
- 跳过这一步
- "我觉得" / "应该是" / "大概是"
- 基于旧截图下结论

---

### PHASE 1: 差异对比 (5 分钟)

**目标**: 确认本地包 vs 远端实际环境的差异

```bash
# 本地跑
python tools/diff_local_remote.py \
    --local build/verify \
    --remote-ssh root@172.20.59.7 \
    --remote-path /opt/app/deployments/v20260630_003/backend \
    --output diff-report.json
```

**必看项**:
- [ ] 本地包 vs 远端 v003 的文件差异
- [ ] 关键 Python import (是否所有依赖都打包)
- [ ] Checklist 中所有 FAIL 项 (尤其是 telemetry, requirements.txt, server.py, init_database.py)
- [ ] 缺失的依赖 (本地 import 但远端没装的)

**绝不要**:
- 不看差异就开始部署
- 假设远端环境 = 本地开发环境

---

### PHASE 2: 部署执行 (15 分钟, 单步)

**目标**: 单步执行, 每步必验证

```bash
# 在远端, 每个 step 独立跑
ssh root@172.20.59.7

# 0. 预检
bash tools/deploy_step.sh precheck

# 1. 停 v003 旧服务
bash tools/deploy_step.sh stop_v003

# 2. 复制 v003 db 到 v004 位置
bash tools/deploy_step.sh copy_db

# 3. 改 systemd service 启 v004
bash tools/deploy_step.sh setup_service

# 4. 启 v004 backend (systemd)
bash tools/deploy_step.sh start_backend

# 5. 启 v004 frontend (nohup)
bash tools/deploy_step.sh start_frontend
```

**每步必须**:
- 看到 `[OK]` 才进入下一步
- 看到 `[WARN]` 要二次确认
- 看到 `[ERR]` **立即停止**, 排查后再继续
- **不要** 用 `|| true` 跳过错误

**绝不要**:
- 一次跑完所有 step (`bash tools/deploy_step.sh all`)
- 跳过 step 0 precheck
- 看到错误还继续

---

### PHASE 3: 端到端验证 (5 分钟)

**目标**: 用 Playwright 实际访问远端, 截图, 验证业务功能

```bash
# 本地跑 (Playwright 实际访问远端)
python tools/verify_deploy.py \
    --host 172.20.59.7 \
    --frontend-port 8081 \
    --backend-port 5001 \
    --screenshots verify-screenshots
```

**必看项**:
- [ ] 登录页能打开 (200)
- [ ] admin/admin123 登录成功
- [ ] /api/v1/users/me 不再 500
- [ ] /api/v2/action/user.authenticate 不再 500
- [ ] /api/v1/enum-types 返回 fullEditable, extensible, locked (没有 fully_editable)
- [ ] 浏览器没有 console 错误
- [ ] 菜单能加载 (非空白)

**绝不要**:
- 只看 HTTP 200 就报"成功"
- 不看截图就下结论

---

### PHASE 4: 出错回滚 (5 分钟)

**如果 PHASE 2 或 PHASE 3 任何步骤失败**:

```bash
# 一键回滚 v003
ssh root@172.20.59.7
bash tools/rollback.sh
```

**回滚后**:
- [ ] 验证 v003 backend 在 5000 端口监听
- [ ] 验证浏览器能访问 172.20.59.7:8081
- [ ] 验证 v003 之前的功能正常

**绝不要**:
- 不回滚就继续
- 假设回滚一定能成功 (需要看事实)

---

## 🛠️ 常见错误及预防

| 错误 | 预防 |
|------|------|
| Python 路径错 | PHASE 0 precheck 看 `which python` |
| meta/ 路径错 | PHASE 1 diff 看包结构 |
| import telemetry 失败 | PHASE 1 diff checklist 检查 telemetry 模块 |
| 端口冲突 | PHASE 0 precheck 看当前端口 |
| systemd service 写死旧路径 | PHASE 0 precheck cat service 文件 |
| /opt/app/current 链接错 | PHASE 0 precheck ls -la current |
| 8081 实际死了但你以为是 200 | **自己用 Playwright 测** |
| 5000 跑空 db 但你以为是 v003 db | **PHASE 0 看 db size + 行数** |

---

## 📊 部署前必问 5 个问题

1. **service 启的是什么?**
   - 看 PHASE 0 的 `systemctl show`

2. **server.py 用什么路径?**
   - 看 PHASE 0 的 `ls -la /proc/$PID/cwd`

3. **db 实际在哪?**
   - 看 PHASE 0 的 `find /opt/app -name "*.db"`

4. **端口是谁在占?**
   - 看 PHASE 0 的 `ss -tlnp`

5. **真实 v003 db 有数据吗?**
   - 看 PHASE 0 的 `sqlite3 ... "SELECT COUNT(*) FROM enum_types"`

如果 5 个问题都能从 precheck 输出找到答案, **才能开始部署**。

---

## 🆘 求助模板

如果部署卡住, 按下面格式求助:

```
## 当前 step
(stop_v003 / copy_db / setup_service / start_backend / start_frontend / verify)

## PHASE 0 precheck 输出
(贴关键部分: service config, 端口, db 大小, server.py import)

## 当前错误
(贴完整 traceback 或 curl 输出)

## 已尝试
(已跑了什么命令, 结果)

## 我猜测的原因
(可空)
```

---

## 📝 SOP 演进日志

| 日期 | 改动 | 原因 |
|------|------|------|
| 2026-07-03 | 初始 v2.0 | 反思 v004 部署失败, 重写 SOP |

---

**最后提醒**: 永远**相信事实** (precheck 输出 + Playwright 截图), **不信预测** (我认为应该是 X)。
