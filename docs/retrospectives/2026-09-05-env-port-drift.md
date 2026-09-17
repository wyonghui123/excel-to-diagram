# [INCIDENT 2026-09-05] 环境端口漂移顽疾 — 单一真源改造复盘

> 严重级别: P1 (每次会话浪费 15-30 分钟排查, 曾致页面卡死/服务互踩)
> 现象: 后端起不来 (DB 锁被孤儿占用)、前端代理指向死掉的旧后端、测试 CLI 连错端口
> 根因: 端口配置散落 6 处且互相矛盾 + 孤儿进程无治理 + 会话引导缺失
> 性质: **系统性顽疾** — .env.development 自身记录了 3 轮修补史, 本次是第 4 轮
> 状态: 已根治 (P0-P3 全部落地, doctor 体检 HEALTHY + 双击验证闭环通过)

---

## 1. 时间线还原 (2026-09-05 本次会话实锤)

| 时间 | 事件 | 证据 |
|---|---|---|
| 会话开始 | 继续树状 search help 双击确认验证 | 上一会话摘要 |
| 初次验证 | dev-login 连 `localhost:3010` 被拒 (ERR_CONNECTION_REFUSED) | PlaywrightCLI 报错 |
| 排查① | 后端实际被 service_manager 启动在 3011, CLI 硬编码 3010 | browser_auth_cli.py L240/299 |
| 排查② | service_manager 启动后端失败: 孤儿 waitress (PID 28420, 端口 3010) 持有 `.architecture.lock` → `[P0 启动失败] DB 锁被占用, 退出` | waitress_server.py 启动日志 |
| 排查③ | 杀孤儿 + 删锁 + 重启后端 3011 成功 | service_manager 日志 |
| 排查④ | 3006 前端代理 500 → 该 vite 是上个会话裸 `npm run dev` 起的, 代理指向刚被杀的 3010 | `Invoke-WebRequest` 探测 |
| 排查⑤ | 以 `VITE_PORT=3006 + BACKEND_PORT=3011` 重启前端 → 代理 200 | npm 后台任务 |
| 验证通过 | 双击确认功能闭环 (dialogGone=true, echoed=系统管理员) | verify_dblclick_confirm.py |
| 复盘决议 | 用户批准 P0-P3 环境治理方案 | 本文档 |

## 2. 根因分析

### 根因 1: 端口有 6 个互相矛盾的"真相源" (治本对象)

| 来源 | 前端 | 后端 | 备注 |
|---|---|---|---|
| `.env.development` | 3005 | **3010** | 09-04 修的, 次日即过时 |
| `service_manager.py` | 3005 | 3011 | 与实际使用 (3006) 漂移 |
| `vite.config.js` 兜底 | — | **3010** | 漂移兜底值 |
| `sync-ports.js` (predev 每次运行) | **3004** | 5000 | 远古架构化石 (mock 3001/Flask 5000), 对 vite.config 的正则已静默失效 |
| `browser_auth_cli.py` | — | **3010** 硬编码 | 测试基建漂移 |
| 实际运行 | **3006** | **3011** | 真相, 但无人记录 |

每轮事故只修一个文件 → 打地鼠。`.env.development` 的注释自己记录了 v37 (08-27)、FIX (09-04) 两轮, 本次第三轮。

### 根因 2: 进程生命周期无人负责

- 会话结束时 detached 进程存活, 下个会话从零发现
- service_manager `start` 只看端口占用不看监听者归属 → **孤儿被误当 "already running" 采纳** (孤儿 vite 带着指向死后端的代理配置继续服务)
- 状态文件碎片化: 主 `.service_status.json` + 3 个 per-port 文件 + `.startup_state.json` + `.wt_service_status.json`, `status` 命令报 "FE 3005 RUNNING" 与现实 (3006 未受管) 矛盾

### 根因 3: 调试基建存在但没被用 + 有盲区

- SESSION_REMINDER 列了 `scripts/debug/env/diagnose.py` 等 7 大工具, 但实际排查时发现成本高于手写 `rg`/`netstat` → 无人调用
- diagnose.py 的 9 个检查项恰好**漏掉**所有复发点: 无端口配置一致性、无孤儿检测、无代理链路、无 DB 锁持有者
- 根目录 100+ 个 `check_*.py`/`verify_*.py` 一次性诊断尸体 = 每个会话都在重新发明一次性脚本

### 5 Whys 链条

```
验证失败 (dev-login 连 3010 被拒)
 ← CLI 硬编码 3010, 后端实际在 3011
 ← 3011 一开始起不来: 孤儿 waitress (3010) 持有 .architecture.lock
 ← 之前会话以非受管方式启动后端, 进程脱离管理存活
 ← 6 个端口真相源互相矛盾 + 无会话引导对账 + 工具盲区
```

## 3. 修复内容 (P0-P3)

### P0 — 端口单一真源 ✅
- 新建 [scripts/ports.json](file:///d:/filework/excel-to-diagram/scripts/ports.json): `FE=3006, BE=3011`, 带背景注释
- 消费方改造 (全部读真源, 进程环境变量仍可覆盖):
  - `vite.config.js`: backendPort + FE port
  - `waitress_server.py`: `_DEFAULT_PORT` (原 3010)
  - `service_manager.py`: SERVICES + env 注入
  - `test_helpers/browser_auth_cli.py`: `DEV_LOGIN_URL` (原硬编码 3010)
  - `playwright.config.js`: baseURL (原 3004)
  - `meta/server.py`: `__main__` 默认端口 (原 5000)
  - `package.json`: electron:dev (原 3004)
- `.env.development`: 删除 BACKEND_PORT/VITE_PORT, 留迁移说明
- 删除 `scripts/sync-ports.js` + `scripts/start-dev.sh` (化石), package.json 移除全部 sync-ports 引用 (predev/postinstall/pretest:e2e/dev:full/sync:ports/test:e2e:debug)

### P1 — service_manager 孤儿治理 ✅
- `_reconcile_orphans(svc_name)`: start 前对账, 端口监听者不受管 → taskkill + backend 家族清理 + 等待端口释放
- `_is_managed_listener`: 兼容 npm→cmd→node 多层包装 (status 记录的是包装进程 PID, 监听者是孙进程 → 进程树后代判断)
- `_db_lock_probe()`: 利用 msvcrt 字节锁语义 — **读文件被拒 = 锁活跃持有中; 可读 + 持有者已死 = 残留可删**
- `_cleanup_stale_db_lock()`: 只删可证安全的残留 (stale/empty), 绝不删活跃锁
- `--keep-orphans` 逃生口
- audit 增强: 输出 DB 锁持有者状态

### P2 — doctor 会话引导 ✅
- `python scripts/service_manager.py doctor`: 10 秒体检 5 项 (端口真源/服务归属/DB 锁/状态文件一致性/配置漂移坏值复活) + VERDICT + 修复路径
- `doctor --fix`: 清孤儿 + 残留锁
- `service_manager.ps1` 加 doctor 路由 (委派给 python 实现, 不重复造轮子)
- SESSION_REMINDER 铁律区新增: **会话第一步 = doctor; 端口真源 = ports.json; 严禁手写诊断脚本**

### P3 — 环境卫生 ✅
- 根目录 77 个一次性诊断脚本清理: 45 个已跟踪的 `git rm`, 32 个未跟踪的移入 `tools/_scratch/legacy-root-diagnostics/`
- 陈旧状态文件删除: `.service_status_3010.json`, `.service_status_3005.json`, `.wt_service_status.json`
- `diagnose.py`: 后端检查改读 ports.json + 新增 `check_port_consistency` 检查项

## 4. 验证证据 (闭环)

```
1. doctor (改造后首次): 准确识别 3 问题 (FE 孤儿/DB 锁残留/status 漂移) ✓
2. service_manager.py restart: 自动杀孤儿 vite (PID 19840) + 干净重启
   FE=3006/PID 10092, BE=3011/PID 29620, commit=2820da2d ✓
3. doctor (终检): VERDICT: HEALTHY ✓
4. verify_dblclick_confirm.py: dialogGone=true, echoed=系统管理员 (无环境变量, CLI 自动读真源) ✓
5. diagnose.py: 新增端口一致性检查项无漂移 ✓
```

## 5. 预防机制 (为什么这次不会再犯)

| 旧问题 | 新机制 |
|---|---|
| 端口配置打地鼠 | 单一真源 ports.json; doctor 第 5 项自动检测坏值复活 |
| 孤儿进程互踩 | start/restart 前强制对账清理; doctor 第 2 项可见 |
| DB 锁误删/误判 | 字节锁语义探针: 不可读=活跃, 可读+死=残留 |
| 状态文件与现实矛盾 | doctor 第 4 项对账 + per-port 陈旧文件已清 |
| 会话重复摸底 | SESSION_REMINDER 铁律: 第一步 doctor |
| 手写一次性诊断脚本 | 铁律明令禁止; 已有 doctor/diagnose 覆盖 |

## 6. 遗留与建议

- `.coord/ports.json` (worktree 级多 Agent 端口分配) 与 `scripts/ports.json` (仓级默认) 职责不同, 共存合理; worktree 场景仍用 `--port` 覆盖
- `restart_safe.py`/`_start_backend_3010.ps1` 等旧调试脚本未逐一审计, 若引用 3010 需跟进
- 未来新增消费方时: **只准读 ports.json, 禁止兜底字面量** (doctor 的漂移检测依赖这一点)
