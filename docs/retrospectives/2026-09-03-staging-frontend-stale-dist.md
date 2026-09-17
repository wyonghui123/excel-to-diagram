# [INCIDENT 2026-09-03] staging 前端陈旧 dist — 修复"未送达"复盘

> 严重级别: P2 (功能不可见, 无数据损失)
> 现象: 用户在 staging `18081/detail/permission_set/1232` 看不到数据范围配置, 但 DB 数据完整
> 根因: staging dist 为 8/31 构建, 9/3 的前端修复只改了源码, 从未 rebuild + 部署
> 性质: **修复"未送达"** — 与同日 prod 8081 事故同构 (验证目标错位)
> 状态: 已修复 (15:40 rebuild + 原子部署 + chunk 验证 200)

---

## 1. 时间线还原 (证据驱动)

| 时间 | 事件 | 证据 |
|---|---|---|
| 8/31 20:24 | staging 前端最后一次构建部署 (`frontend_dist_files`, 同分钟还有 `frontend_dist_files_new`) | 服务器 dist mtime |
| 9/3 13:51 | 本地修改 `PermissionConfigPanel.vue` (loadScopeMatrix 合成 `__expression`/`__expression_display`) | 文件 mtime + git M 状态 |
| 9/3 13:57 | mx14 API 验证: 仅测 13011 后端 dimension-scopes 返回 (897/1/1195/1200), **未测前端渲染** | mx14 脚本内容 |
| 9/3 14:00 | 用户回复"现在看ok了" (验证环境未确认, 大概率是本地 dev 热更即时生效) | 会话记录 |
| 9/3 14:05–15:20 | 转向 prod 8081 故障 → systemd 优化 → status.sh 修复 → 文档审查 | 各 mx 脚本 |
| 9/3 15:30 | 用户在 staging 18081 查看 ps 1232 → 发现数据范围为空 | 用户报告 |
| 9/3 15:40 | 取证确认 dist 陈旧 → rebuild 2m15s → zipfile 打包上传 → 原子替换部署 → chunk 200 | mx55–mx58c |

## 2. 根因分析

### 直接原因
staging dist 自 8/31 后未重建。9/3 13:51 的修复只存在于: ①本地源码 (未 commit) ②本地 dev server (热更即时生效)。staging 是独立的静态产物, 不 rebuild 就永远停留在 8/31。

### 为什么会发生 (四个环节全部失守)

1. **验证目标错位** — 修复针对的是"前端渲染层不认旧语义数据", 但验证止步于 API 层 (mx14 只确认后端返回数据正确)。API 正确 ≠ 前端显示正确。**与上午 prod 8081 事故完全同构**: 那次是"静态页 200 ≠ 登录可用", 这次是"API 数据对 ≠ 页面显示对"。同一个错误模式一天内发生两次, 说明这是系统性盲区而非偶发失误。

2. **三环境 dist 漂移无台账** — 前端产物存在于三处: 本地 dev (实时) / staging dist (8/31) / prod dist (更早)。修改源码只自动作用于本地 dev, 其余环境都需要显式 rebuild + 部署。但整个流程中没有任何一步问过: "**这个修复需要送达哪些环境? 谁负责送达? 何时验证?**"

3. **会话收尾无环境交接声明** — 我在会话中声明"前端显示问题已修复", 但从未声明"该修复当前仅存在于本地 dev, staging/prod 需另行部署"。用户接续会话时 (本会话也是从压缩摘要恢复), 修复状态的环境边界信息丢失。

4. **用户确认被过度泛化** — 用户说"现在看ok了"被当作修复在全环境通过的依据。实际应追问/声明验证环境。用户验证的是本地 dev 的效果, 不是 staging。

### 系统性根因
- 缺少"前端修改 → 环境送达矩阵"的强制检查步骤 (改了 src 之后, 哪些环境的 dist 需要更新, 没有 checklist)
- staging/prod 的 dist 无版本台账 (哪个 commit 构建的、何时、包含哪些修改 — 无从查证)
- 部署动作未纳入修复类任务的完成定义 (DoD)

### 附带风险 (本次侥幸未爆)
- 刚才的 rebuild 部署发生在 **git 工作区未 commit** 状态下: 工作区含 3 个 M 文件 + 若干 untracked。本次 src 下恰好只有 PermissionConfigPanel.vue 一个修改, dist 产物只包含目标修复, 风险可控。但若工作区还有其他实验性前端改动, 会被一并打包上线。**部署前必须确认工作区范围**。

## 3. 改进措施 (已落地/待落地)

| # | 措施 | 状态 |
|---|---|---|
| 1 | **前端修复 DoD**: 修改 src 后, 完成定义 = rebuild + 部署到用户所指环境 + 在该环境端到端验证 (浏览器级) + 汇报时声明送达环境清单 | 已内化 (本文档 + 记忆) |
| 2 | **验证声明三要素**: 修复声明必须包含 (a) 验证了什么层 (API/渲染) (b) 在哪个环境验证 (c) 哪些环境尚未送达 | 已内化 |
| 3 | **部署前 git status 检查**: 确认工作区修改范围, 避免夹带未验证改动 | 待执行 (本次已人工确认仅 1 个前端文件) |
| 4 | **dist 版本台账**: 部署时记录构建时间 + git commit hash 到部署目录 (如 `DEPLOY_INFO.txt`) | 待做 (P2) |
| 5 | zipfile 打包替代 Compress-Archive (反斜杠路径坑), md5 双端校验 | 本次已用, 沉淀为标准做法 |
| 6 | **chunk 循环依赖构建门禁** (根治): 部署中暴露 jspdf 可选依赖 dompurify 激活导致 vendor-pdf↔vendor-mermaid 双向循环 → "Class extends value undefined"。历史靠打地鼠补 manualChunks 规则无法根治; 现已落地 `scripts/check_chunk_cycles.mjs` (DFS 检测 dist 静态 import 图, 有环硬失败), 接入 `npm run build` 链路, 坏产物无法离开构建机 | 已落地 + 三态自测通过 |

## 4. 二次复盘 (同日 16:40 补充) — 送达后仍"未配置": 渲染端第二层根因

第一次 rebuild + 部署 (mx80, chunk `PermissionConfigPanel-Bfc1kNYL`) 后浏览器验证 1228/1232 仍全部"未配置"。
取证发现**第二层根因与本次修复无关**, 即使 dist 新鲜也必然复现:

- `ResourceActionMatrix.cloneMatrixRows()` 无条件给每行注入 `row_scope: r.row_scope || null`
- 而 `rowScopeMode` 等 4 处行级判断的逻辑是 `hasOwnProperty('row_scope') ? 行级 : 回退 rt 级 scopeMatrixLocal`
- 注入导致 `hasOwnProperty` 恒 true → 永远读 `row.row_scope`(null) → rt 级 `scopeMatrix`(含 v83 平铺合成的 `__expression`) 成死代码
- **权限配置 tab 的迁移/存量维度配置必然全部显示"未配置"**, 与 dist 新旧无关

修复 (v84): `cloneMatrixRows` 仅在 `r.row_scope !== undefined` 时注入该字段。
融合视图 (org_service.py:934 真实携带 row_scope 拆行) 语义不受影响; 权限配置 tab 行回退 rt 级。

**教训**: "送达"只是 DoD 前半段; 送达后必须浏览器级验证真实数据路径。本次第一层根因 (dist 陈旧) 掩盖了第二层根因 (渲染端死代码) — 如果最初就在浏览器验证, 两层会一次暴露, 少走一轮 rebuild+部署。

最终验证 (v84, chunk `PermissionConfigPanel-DS4-P1Pi`, 备份 `frontend_dist_files_bak_20260903_mx84`):
- ps 1228 子领域: 查看(1 条) · 目标绩效 ✓
- ps 1232 子领域: 查看(1 条) · 时间管理 ✓
- 验证环境: staging 18081 (PlaywrightCLI 浏览器级); prod **未送达** (prod 下次部署必须用含门禁构建, 坏构建 vendor-pdf-BUFeYVXg 严禁上线)

## 5. 关联

- 同构事故: [2026-09-03-prod-8081-outage-self-inflicted.md](2026-09-03-prod-8081-outage-self-inflicted.md) — "单点探活 ≠ 端到端可用" vs "API 数据对 ≠ 页面显示对"
- 修复执行记录: mx55 (数据取证) → mx56-57 (dist 陈旧取证) → mx58a/b/c (rebuild + 部署, 规避 Compress-Archive 反斜杠坑 + 19200 黑名单)
- 本次部署备份: `/opt/app/staging/frontend_dist_files_bak_20260903_mx58c`
