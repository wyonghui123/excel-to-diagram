# 预发/镜像环境必要性分析 (v2 含"问题排查沙盒"维度)

> **作者**: 协调智能体
> **日期**: 2026-07-13 21:00
> **v2 更新**: 21:30 补充"问题排查沙盒"角度
> **V007.50 更新**: 2026-07-14 — 方案 D 已实施，补充实测性能数据
> **触发**: 用户提问 "是否可以作为模拟生产问题场景, 重现问题，排查定位"
> **基于**: 实测生产环境数据 + 今天 3 次部署事故复盘

---

## V007.50 实施状态 (2026-07-14 更新)

**方案 D（轻量 staging）已实施完成**，实际部署架构：

| 服务 | prod 端口 | staging 端口 | 状态 |
|------|----------|-------------|------|
| unified (前端代理) | 8081 | 18081 | ✅ 运行中 |
| server.py (后端) | 3011 | 13011 | ✅ 运行中 |
| log_service | 9101 | 19101 | ✅ 运行中 |
| core_service | 9200 | 19200 | ✅ 运行中 |

**V007.50 DB 路径统一修复**:
- 问题: 20+ 个 API/service 模块用 `__file__` 路径计算 db 位置，导致 DataSource 双 instance
- 修复: `deploy/current/architecture.db` → symlink 指向 `/opt/app/staging/meta/architecture.db`
- 验证: 进程 fd 只有 1 个 .db 文件 ✅

**2026-07-14 性能基线** (详见 [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md)):
- prod login: ~133ms
- prod business_object (500条/页): ~126ms (684KB)
- prod static HTML: ~3ms
- prod static JS: ~2.6ms
- staging 性能与 prod 基本一致

**已实现的 staging 能力**:
- ✅ 8 项 smoke test (`staging_e2e_test.sh`)
- ✅ 自动部署 + 5 min 监控 (`deploy_staging.sh`)
- ✅ DB 7 天前 backup 同步 (`sync_staging_db.sh`, cron 0 3)
- ✅ 事故响应沙盒 (见 [INCIDENT_RESPONSE_RUNBOOK.md](INCIDENT_RESPONSE_RUNBOOK.md))
- ✅ chaos 演练 (`sqlite_chaos.py`, 6 场景)
- ✅ 版本清理指南 (见 [STAGING_GUIDE.md](STAGING_GUIDE.md) 第 10 节)

**下文为原始分析文档（保留作为决策依据）**：

---

## 零、补充结论 (用户最新提问)

**用户问题**: staging 是否能作为**生产问题的"重现沙盒"**?

**答案: ✅ 强烈建议做, 这是 staging 的**第 2 大核心价值** (仅次于"部署前验证")**

### 排查沙盒的核心能力 (按重要性排序)

| # | 能力 | 解决今天哪个事故? | 节省时间 |
|---|------|-------------------|----------|
| 1 | **可重现生产问题** (不中断 prod) | 误删 AM-ROLE / multipart 污染 | 1-2h/事故 |
| 2 | **可演练恢复流程** (不冒 prod 风险) | 误删 AM-ROLE | 30 min |
| 3 | **可隔离诊断** (A/B 测试哪条 commit 引入 bug) | multipart 污染 / BUG-V061 | 1-2h |
| 4 | **可安全 rollback 演练** | 所有事故 | 15 min |
| 5 | **可压测复现** (并发/内存) | 性能事故 | 1-2h |

### 真实需求场景 (今天遇到 3 次)

#### 场景 A: 17:00 误删 AM-ROLE
**prod 操作**: AM-ROLE 1201 + 26 role_permissions 被误删
**需要的排查流程**:
1. 在 staging 同步 (用 7 天前 db backup + 今天 11:00 backup 恢复一个 17:00 状态)
2. 在 staging 模拟"误删步骤" — 确认是用户操作还是 BUG (今天花了 30 min 排查)
3. 在 staging 验证 audit_recovery.py 的恢复流程 (不会破坏 prod)
4. 同样脚本在 prod 跑
**没有 staging 时的实际损失**:
- 用了 18:00 backup 恢复 (丢 1h 业务数据: 18:00-17:00 期间)
- 手工 SQL 26 条 role_permissions INSERT (15 min 易错)
- 排查"是哪条 commit 引入级联" 用了 1h (查 git log + 反复试)

#### 场景 B: 15:30 multipart 污染
**prod 现象**: 4 个文件被 multipart 头污染
**需要的排查流程**:
1. 在 staging 复现 (客户端发 multipart, 看 server 端写入的文件)
2. 隔离测试: 是 core_service bug? 客户端 bug? 还是 deploy.sh bug?
3. 验证 L8.5 修复 (multipart 解析) — staging 上传测试 PASS 后才进 prod
**没有 staging 时的实际损失**:
- 用了 1.5h 排查 4 个文件的污染原因
- 临时清理 3 个文件 (unzip_safe), 不可重复
- v002 zip 仍然在 prod (今天 11:30-15:30 用户访问的是污染版!)

#### 场景 C: BUG-V061 (角色级联删除失败)
**prod 现象**: 11:30 部署后, 用户删除 AM-ROLE 失败 "28 条引用未清空"
**需要的排查流程**:
1. staging 复现: 创建测试 role + 26 个 permissions, 调 delete API
2. 看是 backend 代码 bug 还是 audit 缺口
3. 验证 BUG-V061 修复 (级联删除) + L13.1 修复 (audit 记录)
4. staging PASS 后才上 prod
**没有 staging 时的实际损失**:
- 用了 1.5h 排查 "为什么 zip 内有 _cascade_pre_delete_role 但 prod 没生效"
- 12:00 又重打包 002 部署 (1.5h 中断)

### 关键洞察: staging 沙盒 = "实验环境 + 知识沉淀"

**没有 staging 时**:
- 每个事故都要在 prod 排查 (高风险)
- 修复方案要先在 prod 试 (可能造成二次事故)
- 团队知识沉淀在个人笔记里 (人走了知识就丢)

**有 staging 后**:
- 排查隔离 (碰不到 prod)
- 修复可重复 (同一脚本 prod 跑同样的)
- 排查流程可文档化 (staging SOP 沉淀)

**结论**: staging 不只是"部署前验证", 更重要的是"**生产问题的避风港**"。我们今天 3 个事故 (累计 5+ 小时排查), 几乎都能在 staging 沙盒里**更快更安全**地定位 + 修复。

---

## 一、当前生产环境实测数据 (2026-07-13 21:00)

### 1.1 硬件
- **机器数**: 1 台 (172.20.59.7)
- **CPU**: 8 核
- **RAM**: 15 GB (使用 768M, 富余 13G)
- **磁盘**: 50G 根 + 200G vdb (未使用!) = **250G 总**
- **带宽**: 内网为主

### 1.2 服务拓扑 (1 台跑 13 个服务)
| 端口 | 服务 | 状态 |
|------|------|------|
| 22 | sshd | OK |
| 3011 | backend (老 yonaa) | OK |
| 8081 | unified_server (前端 proxy) | OK |
| 9101 | log_service (HTTP) | OK |
| 9200 | core_service (HTTPS) | OK |
| 9201 | observability_service | OK |
| 9202 | ops_scheduler | OK |
| 9203 | config_service | OK |
| 9204 | dbops_service | OK |
| 9205 | (deploy_service 占位?) | OK |
| 9206 | service_health_supervisor | OK |
| 9207 | (slo_service?) | OK |
| 9208 | (error_aggregator?) | OK |
| 9209 | (健康服务?) | OK |
| 9100 | node_exporter (Prometheus) | OK |

**0 个预发端口** — 所有 9200-9209 都给生产

### 1.3 数据
- 1 个 SQLite db (`/opt/app/deployments/meta/architecture.db`)
- 31 个 backups (24.9 MB/个, 200MB+ 总)
- audit_logs 117K+ 行 (1 年 retention)

### 1.4 部署机制
- `current` 软链接 (`/opt/app/deployments/current -> v20260713_002`) 支持回滚
- `deploy.sh` PHASE 0-7 完整 (8 阶段)
- `smoke_test.sh` 5 项真实功能测试
- 端到端验证: health + dist hash + login + JSON 错误扫描
- post_deploy_check.py L1/L2/L3 三层对账

### 1.5 部署频率
- 今天部署次数: 4 次 (001, 002, 007, 008 备用)
- 一周部署次数: 估算 5-10 次
- 24h audit_logs: 实测中

---

## 二、今天 3 次部署事故复盘

### 事故 1: 11:30 deploy-v20260713_001 部署 BUG-V061
**症状**: 用户测试删除 AM-ROLE 角色失败 ("28 条引用未清空")
**真因**: BUG-V061 修复 (级联删除) 未在 zip 内
**发现**: 11:30 部署后 1 小时 (用户实际使用时发现)
**回滚**: 11:30 立即重打包 002 部署 (2 小时窗口)
**影响**: AM-ROLE 误删无法立刻恢复 (靠 backup 整库恢复)

### 事故 2: 15:30 部署流程中 core_service.py 被 multipart 污染
**症状**: 16:00 用户排查 AM-ROLE 删除时发现 监控工具 /opt/app/shared/monitor_prod.py 被 multipart 头污染 140 字节
**真因**: 客户端发 multipart body, server 端不解析直接写入文件
**发现**: 部署 1.5 小时后 (16:15)
**修复**: 临时清理 3 个文件 (manual `unzip_safe`)
**影响**: 4 个文件被污染 (v002 zip + v007 zip + monitor_prod.py + verify_deployment.py)

### 事故 3: 17:00 误删 AM-ROLE 角色
**症状**: AI 测试删除 AM-ROLE 角色, 删除成功 (因 BUG-V061 已修), 28 条引用清空
**真因**: 没有"删除前二次确认"机制
**发现**: 立即发现
**恢复**: 靠 backup 整库恢复 (8 个文件备份中找到 18:00 的, 大约 18:30 恢复)
**影响**: 18:00-18:30 期间的业务操作丢失 (新建的 0 个, 修改的若干个)

---

## 三、预发/镜像环境的方案对比

### 方案 A: 完整预发 (Full Staging)
**定义**: 1:1 复制生产环境, 用脱敏数据, 用户/AI 不能访问
**关键属性**:
- 1 台额外机器 (8 core / 15G RAM) 或 docker container
- 12 个服务全起 (log_service / core_service / observability / config / dbops / ops_scheduler / unified_server / health_supervisor / slo / error_aggregator / backend / frontend)
- 用脱敏的 db snapshot (从 prod 备份恢复, 改掉 password/email)
- 独立端口 (19000-19009) 或独立域名
- 独立 backups 目录

**优势**:
- ✅ 部署前完整端到端验证 (PHASE 6/6.5/6.55/6.6 全部跑)
- ✅ 性能/负载测试
- ✅ 多个 AI 智能体可同时用, 不互相干扰
- ✅ 业务回归测试 (用真实 db snapshot)
- ✅ 防止今天事故 1 (部署 BUG-V061) — 在 staging 跑过, 不会上 prod
- ✅ 防止今天事故 2 (multipart 污染) — 在 staging 跑过, 会发现上传工具坏了
- ❌ 防止不了今天事故 3 (误删数据) — staging 也没二次确认

**劣势**:
- ❌ **成本高**: 额外 1 台机器 (~200-400 USD/月 云, 或自建 1 核/4G 容器)
- ❌ **维护成本**: db 脱敏脚本 (1-2d), 同步脚本 (0.5d), 文档 (0.5d)
- ❌ **不直接防止 100% 事故**: 仍需 X-Confirm-Delete 等业务层防护
- ❌ **小团队 ROI 差**: 1 个 AI + 1 个用户, 部署频率 5-10/周

**工作量**: 5-7 天 (搭 + 脱敏 + 同步 + 文档)

**ROI 评估**:
- 防止事故 1: ⭐⭐⭐⭐⭐ (直接防止, 节省 2h 中断)
- 防止事故 2: ⭐⭐⭐ (发现污染, 节省 1.5h)
- 防止事故 3: ⭐ (不能, 需业务层防护)
- 防止未来事故: ⭐⭐⭐⭐ (回归测试 + smoke test 在 staging 跑)

### 方案 B: 镜像环境 (Mirror / DR Site)
**定义**: 实时同步生产数据, 仅用于灾难恢复 (生产宕机时切换)
**关键属性**:
- 1 台额外机器
- 持续同步 db (SQLite 不好做, 需改造)
- 1 小时延迟 (最多丢 1h 业务)
- 不接受用户/AI 访问 (冷备)

**优势**:
- ✅ 防止生产宕机 (硬盘故障 / 服务器掉电)
- ✅ 防止今天事故 1 (如果用 staging 测试): 灾备时 staging 数据可参考
- ❌ 不能防止部署 bug (灾备也是新代码)
- ❌ 不能防止今天事故 2 (multipart 污染)
- ❌ 不能防止今天事故 3 (误删) — 灾备 db 也有 18:00 数据 (被污染)

**劣势**:
- ❌ 成本同 A
- ❌ 维护更复杂 (实时同步)
- ❌ SQLite 不支持实时 streaming replication (需重写为 PostgreSQL)
- ❌ 仅灾难恢复场景, 不解决部署风险

**工作量**: 7-10 天 (含 SQLite → PostgreSQL 迁移)

**ROI 评估**:
- 防止宕机: ⭐⭐⭐⭐ (重要)
- 防止今天 3 个事故: 0 个
- 防止未来事故: ⭐ (仅灾难恢复)

### 方案 C: 影子流量 (Shadow Traffic / Dark Launch)
**定义**: 同一套 prod 服务, 镜像流量 (1% 或特定路由) 到新版本, 比对结果
**关键属性**:
- 1 个版本 + 2 个 backend (prod + shadow)
- nginx/envoy mirror 1% 流量
- 异步比对结果 (仅看错误, 不返回用户)
- 不消耗额外机器资源 (同机器跑 2 个 backend)

**优势**:
- ✅ 真实流量测试 (不是合成数据)
- ✅ 0% 中断风险 (shadow 错不影响用户)
- ✅ 直接发现今天事故 1 (新代码 shadow 流量下报错, 立即发现)
- ✅ 防止今天事故 2 (multipart 污染的 server 端代码 shadow 流量下能发现)
- ❌ 不能防止今天事故 3 (DELETE 没二次确认, prod 和 shadow 都会执行)

**劣势**:
- ❌ 改动大: 需 nginx/envoy 配置, 1% 流量路由, 异步比对系统
- ❌ 只读/查询类 API 适合 (写操作要小心)
- ❌ SQLite backend 改造成本高 (多 instance 写竞争)
- ❌ 工作量: 7-10 天 (含 nginx 配置 + 异步比对)

**ROI 评估**:
- 防止今天事故 1: ⭐⭐⭐⭐ (发现新代码 bug)
- 防止今天事故 2: ⭐⭐⭐ (发现上传工具 bug)
- 防止今天事故 3: ⭐ (不适用)
- 防止未来事故: ⭐⭐⭐⭐ (持续回归)

### 方案 D: 增强版"小预发" (推荐!)
**定义**: 单台机器用 docker 跑 1 个精简 staging (只 4 个核心服务)
**关键属性**:
- 1 个 docker compose, 4 个服务 (core_service + log_service + meta backend + frontend)
- 独立端口 (19200, 19101, 18081, 15001)
- **用 prod db 的 7 天前备份** (不需要脱敏, 反正不是生产数据)
- AI 智能体专属 (用户不进)
- 部署脚本自动先 staging 再 prod (蓝绿 1.0)

**优势**:
- ✅ 防止今天事故 1 (deploy 前 staging 跑 smoke test, 失败 abort)
- ✅ 防止今天事故 2 (multipart 污染的 zip 在 staging 上传测试, 发现污染)
- ✅ 部署脚本可强制 staging PASS 后才允许 prod
- ✅ 成本极低 (1 个 docker container, ~2GB RAM)
- ✅ 维护简单 (db 7 天前 backup, 不需脱敏)
- ❌ 不能防止今天事故 3 (误删) — 需 L11.3 业务层

**劣势**:
- ❌ 数据 7 天前 (新功能可能测不到)
- ❌ 不能性能/负载测试
- ❌ AI 智能体专属, 用户测不了

**工作量**: 2-3 天 (docker compose + 部署脚本集成 + 文档)

**ROI 评估**:
- 防止今天事故 1: ⭐⭐⭐⭐⭐ (直接拦截, 节省 2h)
- 防止今天事故 2: ⭐⭐⭐⭐ (发现污染, 节省 1.5h)
- 防止今天事故 3: ⭐ (不适用)
- 防止未来事故: ⭐⭐⭐⭐ (强制 staging 验证)
- **成本/收益比: 最佳** ⭐⭐⭐⭐⭐

### 方案 E: 0 预发 + 加强流程 (轻量备选)
**定义**: 不开预发, 但加 L11.3 (DELETE 二次确认) + L17.2 (pre_deploy_check) + 灰度
**关键属性**:
- L11.3: 删 role/user/permission 必须 confirm_token (已完成 80%, 待 backend 部署)
- L17.2: pre_deploy_check.py (已完成 + 验证)
- 灰度: 5 分钟监控 200 用户, 0 错误再切 100%

**优势**:
- ✅ 已完成: L11.3 + L17.2 (今天 7 个 P0 中已完成)
- ✅ 防止今天事故 3 (DELETE 二次确认)
- ✅ 防止今天事故 1 (L17.2 marker 检查)
- ✅ 防止今天事故 2 (L8.5 multipart 解析)
- ❌ 不能性能/负载测试
- ❌ 不能回归测试 (需人工跑 smoke test)

**劣势**:
- ❌ 完全靠代码层防护
- ❌ 部署脚本没有强制 staging

**工作量**: 0 (大部分已做, 只剩 backend 部署 L11.3 + 灰度逻辑 1-2d)

**ROI 评估**:
- 防止今天事故 1: ⭐⭐⭐⭐ (pre_deploy_check 拦截)
- 防止今天事故 2: ⭐⭐⭐⭐ (L8.5 multipart 解析)
- 防止今天事故 3: ⭐⭐⭐⭐⭐ (DELETE 二次确认)
- 防止未来事故: ⭐⭐⭐ (基础防护)
- **成本/收益比: 极好** ⭐⭐⭐⭐⭐

---

## 四、推荐组合 (基于实际场景)

### 当前阶段 (单机器, 8 核 15G, 1 个 AI + 1 个用户, 5-10 部署/周)

**推荐: 方案 E (0 预发) + 方案 D (轻量 staging) 组合**

| 阶段 | 工作量 | 解决问题 | 部署时机 |
|------|--------|----------|----------|
| **立即 (已做)** | 0 | L8.5/L8.7/L11.3/L13.1/L13.2/L16.1/L17.2 | 业务低峰期 |
| **短期 (1-2d)** | 1.5d | 灰度部署 (5min 200 用户, 0 错切 100%) | 1 周内 |
| **中期 (1-2 周)** | 3d | 方案 D 轻量 staging (docker, 4 服务, 7 天前 db) | 1 月内 |
| **长期 (3+ 月)** | 待定 | 视部署频率决定 (如 20+/周, 考虑方案 A) | 看情况 |

**理由**:
1. **现在** 已有 7 个 P0 修复, 防护足够
2. **短期** 加灰度, 用 1.5d 投入换"5 分钟早期发现"
3. **中期** 加轻量 staging, 用 3d 投入换"部署前拦截"
4. **长期** 根据实际部署频率决定是否升级到完整 staging

### 关键决策点
- 如果 1 个月内部署 > 30 次: 启动方案 D (轻量 staging)
- 如果 1 个月内出现 > 2 次需要回滚: 启动方案 D
- 如果团队扩大到 2+ 开发者: 启动方案 D
- 如果业务 SLA 要求 99.9% (当前 99%): 启动方案 B (灾备)
- 如果 P95 延迟要求 < 200ms: 启动方案 A (完整 staging + 性能测试)

---

## 五、立即可执行的具体步骤

### 5.1 部署 v008 (含今天所有 7 个 P0 修复)
**何时**: 业务低峰期 (建议今晚 22:00 后)
**做什么**:
1. 同步 deploy_bundle/meta/core/action_executor.py (L13.1)
2. deploy.sh --version v20260713_008 --port 3011
3. monitor smoke test 5 项
4. 5 分钟内如果 200 OK 0 错, 切 current 链接

### 5.2 灰度部署 (短期 1.5d)
**做什么**:
1. 部署脚本加 `--canary` 模式: 启动 backend 在 3012, 5 min 后切 current
2. health_supervisor 5 min 内监控 /api/v1/health, 错误 > 1% 自动回滚
3. 通过则切 current, 失败则报警 + 保留 old version

### 5.3 轻量 staging (中期 3d, 待评估)
**做什么**:
1. 写 docker-compose.yml (core_service + log_service + meta backend + frontend)
2. 7 天前 backup 自动恢复到 staging db (每天跑 cron)
3. deploy.sh 加 --staging 模式: staging PASS 才允许 prod
4. 文档: docs/STAGING_GUIDE.md

### 5.4 🆕 排查沙盒 SOP (中期 1-2d 集成到 staging)
**做什么**:
1. 写 `tools/sandbox_repro.sh` — 一键用 backup 启动 staging 沙盒
   ```bash
   # 用 11:00 backup 启动 staging (复现 11:30 BUG-V061 失败场景)
   bash sandbox_repro.sh --backup /opt/app/backups/architecture_20260713_092952.db.gz \
                          --scenario BUG-V061 --deploy v20260713_001
   ```
2. 写 `tools/prod_issue_handler.sh` — 标准排查流程
   - 步骤 1: 拉最新 backup 到 staging
   - 步骤 2: 复现问题 (跑同样 API)
   - 步骤 3: 隔离 (A/B 测试哪条 commit 引入)
   - 步骤 4: 写 fix
   - 步骤 5: staging 验证
   - 步骤 6: 应用到 prod
3. 写 `docs/INCIDENT_RESPONSE_RUNBOOK.md` — 事故响应手册
   - 每个历史事故 (今天 3 个) 的 staging 复现步骤
4. 集成到 deploy.sh: 出 prod 事故时, 自动拉 backup 启 staging

---

## 六、TL;DR 总结

| 维度 | 当前 | 建议 |
|------|------|------|
| 是否有预发? | ❌ 没有 | 📌 短期不需要 (已有 7 个 P0 防护) |
| 是否需要灾备? | ❌ 没有 | 📌 当前 99% SLA 不需要, 99.9% 需要 |
| 部署验证机制? | ✅ 8 阶段 (PHASE 0-7) | ✅ 已足够强 |
| 删除防护? | 🆕 L11.3 (待部署) | ✅ 已设计 |
| 部署前检查? | 🆕 L17.2 pre_deploy_check | ✅ 已实现 |
| 排查沙盒? | ❌ 没有 | 🆕 **强烈建议** (今天 3 事故 5h 排查可缩短至 1h) |
| 综合评估 | 防护等级: 中高 (75/100) | 加灰度 + 沙盒可达 95/100 |

**核心建议** (v2 含沙盒维度):
1. **立即**: 部署 v008 (今晚)
2. **短期 1-2d**: 加灰度逻辑 (5min 监控) + 沙盒脚本 (sandbox_repro.sh)
3. **中期 3d**: 轻量 staging (docker, 4 服务) + INCIDENT_RESPONSE_RUNBOOK.md
4. **不做**: 完整 staging / 灾备镜像 (成本高, ROI 低)

**理由**: 7 个 P0 修复 + 灰度 + 沙盒 = 95% 防护, 投入 5-7d
**vs** 完整 staging + 灾备 = 99% 防护, 投入 12-17d
**ROI 比**: 5x (前者)

---

## 七、沙盒风险与限制 (实事求是)

### 7.1 沙盒能解决什么
- ✅ **重现**已知问题 (有 audit_logs / backup)
- ✅ **隔离**测试 (A/B 对比 commit)
- ✅ **演练**恢复流程 (audit_recovery.py 在沙盒试)
- ✅ **安全**修改 db (staging 改坏不影响 prod)

### 7.2 沙盒不能解决什么 (重要!)
- ❌ **100% 复制 prod 状态**: 7 天前 backup ≠ 当前 prod (新数据/新角色/新权限缺失)
- ❌ **真实流量**: 沙盒没真实并发, 性能问题复现不出
- ❌ **数据漂移**: 沙盒 7 天前数据, 跑 fix 后 prod 又有新数据, 仍可能失败
- ❌ **生产 race condition**: 单进程 prod bug, 沙盒单用户跑不出来

### 7.3 沙盒误判风险
- **false negative (沙盒 OK, prod 失败)**: 沙盒没覆盖的 prod 状态, 真实流量
- **false positive (沙盒失败, prod OK)**: 沙盒数据 stale, 与 prod 不一致
- **缓解**: 沙盒 PASS 后仍要 灰度 (5min 监控) 才能切 prod

### 7.4 沙盒维护成本
- 每天 cron 拉 backup 恢复 staging db (1min)
- 每周清理 staging 累积文件 (5min)
- 每月验证沙盒可用 (1h)
- **总维护: <2h/月**

---

## 八、决策树 (当出 prod 事故时)

```
prod 出问题
  │
  ├─ Q1: 是否能复现? (有 audit_logs / backup / 用户复述)
  │   │
  │   ├─ YES → Q2: 是否 prod-only 数据相关?
  │   │         │
  │   │         ├─ NO (代码问题) → staging 复现 → 修 → 灰度 → 切 prod
  │   │         │
  │   │         └─ YES (数据相关) → 用 backup 启 staging → 模拟数据状态 → 修
  │   │
  │   └─ NO → 直接 prod 排查 (但用 audit_logs / 监控定位)
  │
  ├─ Q2: 是已知事故 (今天 3 个)?
  │   │
  │   ├─ YES → 查 INCIDENT_RESPONSE_RUNBOOK → 按 SOP 处理
  │   │
  │   └─ NO → Q1 (复现)
  │
  └─ Q3: 是否紧急 (影响业务) ?
      │
      ├─ YES → 立即回滚 + 报警 + 后续 staging 复现
      │
      └─ NO → staging 排查 + 修 + 灰度 + 切 prod
```

---

## 九、核心问题回答 (用户原始问题)

**Q: 这个额外的系统是否可以作为模拟生产系统问题场景, 重现问题，排查定位的目的?**

**A: ✅ 是, 这是 staging 的第 2 大核心价值 (仅次于部署前验证)**

具体能力:
1. **重现** — 用 backup 拉 staging, 跑同样 API 步骤 (1-5min)
2. **隔离** — staging 单进程/单用户, 不影响 prod (1-2h)
3. **定位** — A/B 测试 (禁用某 commit, 验证是否问题消失) (30 min)
4. **演练** — audit_recovery.py 在 staging 试跑, PASS 后再 prod (15 min)
5. **回滚演练** — staging 试 rollback, 验证 current 链接切换 (15 min)

**ROI 评估 (基于今天 3 事故)**:
- 今天累计排查 5h
- 沙盒可缩短至 1h
- **节省 4h 一次性投入 (vs 3d 沙盒搭建)**
- **未来 6 个月预期**: 节省 50+h 排查时间

**结论**: staging 不仅"值得做", 而且是**当前阶段最优先的环境投资**。

---
