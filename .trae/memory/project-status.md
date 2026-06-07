# 项目状态快照
> 最后更新: 2026-05-23

## ⚠️ 重要提醒
**每次开始任务前，必须先查看此文件！**

---

## 1. 环境配置（权威来源）
- **配置文件**: `config/environment/server-prod.toml`
- **必须优先读取**，所有操作以此为准

## 2. 已完成的 SOP 工具
- `SOP_SIMPLE.md` - 傻瓜式3步SOP文档
- `deploy-auto.sh` - 智能一键部署脚本（**已存在**）
- `rollback.sh` - 快速回滚脚本（**已存在**）
- `deploy-centos7.sh` - CentOS7专用部署脚本

## 3. 当前服务器状态
| 项目 | 状态 |
|------|------|
| Python | 3.9.21 (已升级) |
| 前端端口 | 8081 |
| 后端端口 | 5000 |
| OpenSSH | 9.9p1 (已升级) |
| OpenSSL | 1.1.1u (已升级) |
| zlib | 1.3.1 (已升级) |

## 4. 关键路径
- 应用目录: `/opt/app/`
- 前端: `/opt/app/excel-to-diagram/dist/`
- 后端: `/opt/app/meta/`
- Python: `/opt/python3.9.21/`
- 启动脚本: `/usr/local/bin/python3.9.21-clean`

## 5. 常用命令
```bash
# 部署（需要先打包）
./deploy-auto.sh <版本号>.zip

# 回滚
./rollback.sh

# 查看版本
ls -la /opt/app/current
```

## 6. 不要重复造轮子
❌ **不要**重新创建已经存在的：
- deploy-auto.sh
- rollback.sh
- SOP_SIMPLE.md
- 其他 .sh 脚本

✅ **先检查**，再决定是否需要新建

---

## 7. DevOps 待办清单
- **文件**: `.trae/memory/devops-backlog.md`
- **Docker 化**: ⏸️ 暂缓（通过 SOP 观察）
- **CI/CD**: ⏸️ 暂缓
- **复审时间**: 2026-07-30

## 8. 每次任务前检查清单

- [ ] 读取 server-prod.toml
- [ ] 检查相关 .sh 脚本是否已存在
- [ ] 检查文档是否已存在
- [ ] 询问用户具体需求，而不是假设
- [ ] 查看 devops-backlog.md 是否有更新

## 9. E2E 测试体系（2026-05-23 重构）

### 当前状态
- **Spec**: `.trae/specs/e2e-test-system-spec.md`
- **规则（单一事实源）**: `.trae/rules/e2e-testing.md`（8条致命规则 + 经验表 + 模板）
- **规则（详细）**: `.trae/rules/project_rules.md`（规则 #10-#19）
- **会话提醒**: `.trae/rules/SESSION_REMINDER.md`（E2E 检查清单）
- **配置注释**: `playwright.config.js`（头部8条核心规则）
- **预检脚本**: `scripts/e2e-precheck.js`
- **辅助函数**: `e2e/helpers/auth.js`（含规则头部注释）
- **每个测试文件头部**: 均有 [E2E 规则速查] 注释

### 目录结构
```
e2e/
├── smoke/          # P0 冒烟测试（~3分钟）
│   ├── auth.smoke.spec.js
│   └── arch-data.smoke.spec.js
├── features/       # P1/P2 功能测试（~5分钟）
│   ├── arch-data-crud.spec.js
│   ├── arch-data-filter-scope.spec.js
│   ├── import-export.spec.js
│   ├── user-role.spec.js
│   ├── permission.spec.js
│   ├── enum-management.spec.js
│   ├── audit-log.spec.js
│   ├── diagram.spec.js
│   └── product-version.spec.js
├── shared/         # 共享组件操作层
│   └── components.js
└── helpers/        # 基础辅助函数
    ├── auth.js
    └── test-data.js
```

### 运行前必须检查
1. **环境预检**: `node scripts/e2e-precheck.js`
2. **终端分离**: 前端(终端A) / 后端(终端B) / 测试(终端C)
3. **禁止在 dev server 终端运行测试命令**
4. **报告查看**: `npx playwright show-report --port 9326`（不能用 python http.server）

### 核心经验（反复踩坑总结）
| # | 问题 | 根因 | 解决方案 | 影响程度 |
|---|------|------|---------|---------|
| 1 | 测试全部 ERR_CONNECTION_REFUSED | 服务未启动或被杀 | 预检脚本 + 终端分离 | 致命 |
| 2 | 测试永久卡死 | `networkidle` 在 SPA 中永不完成 | 用 `domcontentloaded` + 元素等待 | 致命 |
| 3 | 所有截图都是首页 | `screenshot: 'on'` 在测试结束后截图 | 用 `testInfo.attach()` 手动截图 | 严重 |
| 4 | 权限不生效 | 只改 localStorage 没改 Pinia | `setAdminPermissions()` 同步两者 | 严重 |
| 5 | 扫描旧测试文件 | project 没指定 testDir | 每个 project 指定独立 testDir | 中等 |
| 6 | 报告图片无法显示 | 用 python http.server 打开报告 | 用 `npx playwright show-report` | 中等 |
| 7 | Element Plus 下拉匹配隐藏 DOM | 没用 `:visible` 约束 | 下拉选项加 `:visible` | 中等 |
| 8 | API 请求返回 401 | page.request 不共享浏览器认证 | 手动带 Authorization header | 中等 |

### 经验固化机制（6层防护）
1. **playwright.config.js 头部注释**: 8条核心规则，编辑配置时第一眼可见
2. **helpers/auth.js 头部注释**: 10条核心规则，编辑辅助函数时可见
3. **每个测试文件头部**: [E2E 规则速查] 注释，编辑测试时可见
4. **.trae/rules/e2e-testing.md**: E2E 专用规则文件（单一事实源），8条致命规则 + 经验表 + 模板
5. **SESSION_REMINDER.md**: 会话开始时的 E2E 检查清单
6. **本文件**: 经验表格和里程碑进度

### 里程碑进度
- [x] 里程碑 1: 基础设施
- [x] 里程碑 2: 冒烟测试（5 passed）
- [x] 里程碑 3: 架构数据深度测试（S03 + S04 + S05）- CRUD 2 passed, 冒烟 5 passed
- [x] 里程碑 4: 用户权限与角色权限（S06 + S07）- 3 passed
- [x] 里程碑 5: 枚举管理（S08）- 3 passed
- [x] 里程碑 6: 审计日志与架构图（S09 + S10）- 5 passed
- [x] 里程碑 7: 产品版本管理（S11）- 3 passed
- [x] 里程碑 8: 清理旧文件 + 更新文档（19个旧文件已删除）

---

*此文件是项目记忆，每次任务前必须查看*
