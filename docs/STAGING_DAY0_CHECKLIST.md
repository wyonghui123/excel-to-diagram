# staging 启动检查表 (Day 0 准备 + 3 天实施计划)

> **作者**: 协调智能体
> **日期**: 2026-07-13 22:30
> **决策**: 产品经理确认"立即做, 本周内 3 天搭建"
> **目标**: 周一开始实施, 周三完成, 周四起所有部署走 staging

---

## 一、3 天实施计划 (用"练习厨房"比喻)

### Day 1 (周一): 搭"练习厨房"骨架
**类比**: 在餐厅旁边砌一间隔音小厨房, 装炉灶 + 通风

**目标**: 同一台机器起 4 个 staging 服务

**任务**:
1. **端口规划** (10min): 分配 staging 端口
   - core_service: 9200 → 19200
   - log_service: 9101 → 19101
   - backend: 3011 → 13011
   - frontend: 8081 → 18081
2. **服务配置** (2h): 复制 4 个 service 文件, 改端口/路径/db
3. **首次启动** (1h): 启 4 个 staging 服务, 跑通 hello world
4. **冒烟测试** (30min): 访问 `http://172.20.59.7:19101/api` 返回 OK
5. **隔离检查** (30min): staging 改了文件, prod 不受影响

**验证 (产品视角)**: 浏览器访问 `http://172.20.59.7:19101/api` 看到"staging v1"标识

---

### Day 2 (周二): 用 7 天前 db 备份 + 集成 staging 验证
**类比**: 给练习厨房装旧食材(7 天前的), 验证能正常做菜

**目标**: staging 用 7 天前 db 跑通完整功能

**任务**:
1. **db 同步脚本** (2h): `tools/sync_staging_db.sh`
   - 从 `/opt/app/backups/architecture_YYYYMMDD_HHMMSS.db.gz` 解压
   - 复制到 `/opt/app/staging/meta/architecture.db`
   - 改 owner 权限
2. **自动 cron** (1h): 每天凌晨 3 点拉最新 backup 到 staging
3. **集成核心服务** (2h): 让 backend 启动时读 staging db
4. **完整功能测试** (1h): 登录 + 创建角色 + 列表 + 详情
5. **回归测试工具集成** (30min): 跑 `regression_test_suite.py` 9 场景 (V007.55 取代 sqlite_chaos)

**验证 (产品视角)**: 在 staging 能看到上周的数据, 改东西不会影响真实系统

---

### Day 3 (周三): 集成到部署脚本 + 灰度切换
**类比**: 厨师改菜谱后, 自动先去练习厨房试做, OK 再上正式厨房

**目标**: 所有部署自动走 staging → prod 流程

**任务**:
1. **deploy.sh 加 staging 模式** (2h):
   - 改代码 → 先部署到 staging (1 min)
   - 跑 5 项 smoke test
   - PASS → 部署到生产 + 5 min 灰度监控
   - FAIL → abort + 报警
2. **回滚脚本** (1h): `tools/rollback.sh` 一键回退到上一版本
3. **staging 监控** (1h): `/api/staging/health` 端点 + 告警
4. **文档** (2h):
   - `docs/STAGING_GUIDE.md` - 怎么用
   - `docs/INCIDENT_RESPONSE_RUNBOOK.md` - 出事故时怎么用 staging
5. **演练** (1h): 故意改一个 bug, 验证 staging 拦得住

**验证 (产品视角)**: 明天开始, 每次改代码, 系统会先在 staging 试一遍, 没问题才上生产

---

## 二、今天 (Day 0) 准备 (业务低峰期 22:00-23:00)

我立即可以做的 (1 小时):

### 2.1 资源评估 ✅
- **磁盘**: 33GB 可用 (够 staging 用 5-10GB)
- **内存**: 13G 闲置 (staging 4 服务 2GB 足够)
- **CPU**: 8 核, 闲置率高 (4 staging 服务用 1-2 核)
- **结论**: 同机部署, 不需要额外机器 ✅

### 2.2 端口规划 ✅
| 服务 | 生产端口 | staging 端口 | 备注 |
|------|----------|--------------|------|
| core_service | 9200 | 19200 | HTTPS |
| log_service | 9101 | 19101 | HTTP |
| meta backend | 3011 | 13011 | HTTP |
| unified_server (前端) | 8081 | 18081 | HTTP |
| observability | 9201 | (用 prod) | 不隔离 |
| dbops | 9204 | (用 prod) | 不隔离 |
| ops_scheduler | 9202 | (用 prod) | 不隔离 |

**关键决策**: 只隔离 4 个核心服务, 其他 9 个共享 (避免过度)

### 2.3 备份策略 ✅
- 当前 31 个 backups (24.9MB/个, 7 天 retention)
- staging 用 7 天前 backup (周一早上 3 点同步)
- 每天凌晨 3 点自动拉最新

### 2.4 风险与缓解 ✅

| 风险 | 缓解 |
|------|------|
| staging 改了 prod db 误连 | 用不同 db path + 严格权限隔离 |
| staging 服务被 prod 客户端误访问 | 不同端口 + 不同 token |
| staging 资源占用影响 prod | limit memory 2GB, CPU 50% |
| 部署脚本兼容 staging/prod | 加 --target staging|prod 参数 |

### 2.5 立即可上传的工具 ✅
- [regression_test_suite.py](file:///d:/filework/worktrees/release-prep/tools/regression_test_suite.py) (V007.55, 9 场景, **取代 sqlite_chaos**)
- ~~[sqlite_chaos.py](file:///d:/filework/worktrees/release-prep/tools/sqlite_chaos.py)~~ (V007.55 **deprecated**, 用 `--redirect-to-regression` 软迁移)
- [audit_recovery.py](file:///d:/filework/worktrees/release-prep/tools/audit_recovery.py) (commit `79f9add`)
- [pre_deploy_check.py](file:///d:/filework/worktrees/release-prep/tools/pre_deploy_check.py) (commit `3455a90`)

---

## 三、产品经理视角的成功标准

### 3.1 客观指标 (3 天后必须达成)

| 指标 | 目标值 | 怎么验证 |
|------|--------|----------|
| staging 服务 UP | 4/4 | 浏览器访问 4 个端口 |
| staging 部署成功 | 1 次/天 | 改一行代码, 看 staging 自动部署 |
| 拦截 bug 率 | ≥ 70% | 故意埋 5 个 bug, 看 staging 拦住几个 |
| 部署到生产时间 | 仍 ≤ 10 min | 端到端计时 |
| 业务中断次数 | 0 | 上线后 1 周内 |

### 3.2 主观指标 (产品经理体感)

- ✅ "今天又出事故了" → **不再听到**
- ✅ "改个东西要大半夜" → **白天也能改**
- ✅ "删错了怎么办" → **先在 staging 演练**
- ✅ "新人怎么上手" → **看文档 + staging 试**

### 3.3 投资回报 (1 个月后看)

| 项 | 数值 |
|------|------|
| 投入时间 | 3 天 (一次性) + 2h/月 (维护) |
| 节省事故时间 | 8+ 小时/月 |
| 节省业务中断 | 70% |
| ROI | < 1 个月回本 |

---

## 四、决策点 (产品经理今晚要决定)

### 4.1 端口隔离 vs 路径隔离

**方案 A** (推荐, 简单): 端口隔离, 同机部署
- 优点: 简单, 1 天搭好
- 缺点: 共享资源 (CPU/内存)

**方案 B** (复杂): docker 容器隔离
- 优点: 完全隔离
- 缺点: 多 1 天配置 docker, 资源开销 2x

**建议**: 方案 A (单台机器, 流量小, 隔离够用)

### 4.2 staging 访问权限

**方案 1** (推荐): 内部访问, 加 IP 白名单
- 只允许运维 (172.20.x.x) 访问 staging 端口
- 用户/AI 不能进 (避免误操作)

**方案 2** (更宽松): 内网访问
- 同上, 但更宽松

**建议**: 方案 1 (更安全)

### 4.3 业务方能否访问 staging

**YES**: 给业务方演示新功能前, 先在 staging 跑
**NO**: 只技术用, 业务方不碰 (避免混淆)

**建议**: 业务低峰期 YES (新产品演示), 平时 NO

---

## 五、明早 (Day 1) 启动检查表

业务低峰期后, AI 立即开始:
- [ ] 创建 staging 目录 `/opt/app/staging/`
- [ ] 复制 4 个服务的 .py 文件 + 配置
- [ ] 改端口: 9200→19200, 9101→19101, 3011→13011, 8081→18081
- [ ] 启 4 个 staging 服务 (用 nohup, 不进 systemd)
- [ ] 浏览器访问 `http://172.20.59.7:19101/api` 验证
- [ ] 跑 `regression_test_suite.py --scenario R1` (readonly, 非破坏)
- [ ] 跑 `monitor_migrations.py --check-regression` 完整验证 9 场景
- [ ] 报告: Day 1 进度 + 风险

---

## 六、紧急回退方案

如果 staging 搭到一半发现严重问题 (比如占资源太多), 立即回退:
- pkill 所有 staging 进程
- 删 /opt/app/staging/ 目录
- 恢复 1 台机器全生产模式
- 决策: 继续或停 (不浪费更多时间)

---

**协调智能体准备就绪, 等业务低峰期 22:00 后开始 Day 1**

**Day 0 总结** (今天 22:30 提交):
- ✅ 资源够, 同机部署可行
- ✅ 端口规划完成
- ✅ 风险与缓解明确
- ✅ 成功标准清晰
- 🆘 决策点: 方案 A vs B (产品经理选)
- 🆘 决策点: 业务方能否访问 staging

详细技术: [STAGING_ENV_ANALYSIS.md v2](file:///d:/filework/worktrees/release-prep/docs/STAGING_ENV_ANALYSIS.md)
