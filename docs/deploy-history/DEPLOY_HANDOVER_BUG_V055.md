# DEPLOY_HANDOVER_BUG_V055 - V051/V052/V053/V054 实际未生效 (vite preview 模式不重新 build)

> **撰写**: 2026-07-06 21:10 (开发智能体)
> **优先级**: CRITICAL (PM 反馈四次都没看到效果)
> **状态**: READY FOR COORDINATOR REBUILD
> **SOP**: v3.2

---

## 0. TL;DR

| 维度 | 值 |
|------|-----|
| **BUG ID** | V055 (V051-V054 修复其实没生效) |
| **PM 报告次数** | 4 次 (V051 → V052 → V053 → V054) |
| **根因** | integration 3007 用 `vite preview` 启动, 不是 `vite dev` |
| **影响** | yon-ep.scss 修改没触发重新 build, PM 看到的还是 7/6 20:43 的旧 build 产物 |
| **修法** | 协调智能体重跑 `npm run build` 重生成 `frontend_dist_files/` |

---

## 1. PM 反馈链路

| 版本 | PM 反馈 | dev agent 改动 | 实际效果 |
|------|---------|---------------|---------|
| V051 | "领域详情 编辑/删除上方空白" | 改 `ObjectPageHeader.vue` | ✗ 改错组件 |
| V052 | "还是没效果" | 改 `ObjectDetailPage.odp-title-bar` | ✗ 改错组件 (standalone 模式, 不是 drawer) |
| V053 | "标题与编辑/删除按钮之间空白" | 改 `el-drawer__header` 全局样式 | ✗ build 没重跑, 浏览器看不到 |
| V054 | "3007 没解决" | 改 `el-drawer__body` 全局样式 | ✗ build 没重跑, 浏览器看不到 |
| **V055 (本 HANDOVER)** | "3007 测试并没有解决" | **诊断根因: vite preview 不重 build** | **修复方法: 重 build** |

---

## 2. 根因诊断（精确）

### 2.1 进程检查

```powershell
Get-WmiObject Win32_Process -Filter "ProcessId = 26136"
```

输出:
```
CommandLine : "C:\Users\Administrator\.trae-cn\binaries\node\versions\24.14.0\node.exe" 
              D:\filework\integration-worktree\node_modules\.bin\..\vite\bin\vite.js 
              preview --port 3007 --strictPort --host 0.0.0.0
```

**`vite preview`** - 不是 vite dev 模式！

### 2.2 Vite preview vs dev 区别

| 模式 | 命令 | 行为 |
|------|------|------|
| `vite dev` | `npm run dev` | 实时编译 scss/js, HMR 自动应用修改 |
| `vite preview` | `npm run preview` | **只服务 dist 静态文件**, 不编译, 不 HMR |

**integration 3007 跑的是 preview 模式**——所以 yon-ep.scss 修改不会自动重新编译。

### 2.3 实际编译结果验证

```python
# Python 验证 vite 编译的 index.css 不含 V053/V054 改动
import urllib.request
r = urllib.request.urlopen('http://localhost:3007/assets/index-DVXpzuQy.css', timeout=5)
raw = r.read().decode('utf-8')

print('Has .el-drawer__header:', '.el-drawer__header' in raw)  # False
print('Has .el-drawer__body:', '.el-drawer__body' in raw)      # False
print('Has V053/V054 comment:', 'V053' in raw or 'V054' in raw)  # False
```

**确认**: index.css 完全没有 V053/V054 改动！

### 2.4 build 时间戳

```
frontend_dist_files/index-k1qGmEN8.css - LastWriteTime: 7/6 20:43
build.out 7/6 20:43:11
build.err 7/6 20:43:12
```

**build 是 V053/V054 commit 之前跑的 (V053 cherry-pick 是 20:54)**——所以 PM 看到的是旧版。

---

## 3. 修复方案

### 3.1 协调智能体需要做的事（必做）

**选项 A（推荐）: 重 build**

```powershell
cd D:\filework\integration-worktree
npm run build
# 或: npx vite build
```

**选项 B: 改用 vite dev 模式**

```powershell
# 1. 停掉现有 preview 进程
Get-NetTCPConnection -LocalPort 3007 -State Listen | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force
}

# 2. 启动 dev 模式
cd D:\filework\integration-worktree
npm run dev
```

**推荐选项 B**——这样后续 scss 改动会自动 HMR。

### 3.2 验证步骤

```powershell
# 1. 重 build 后看 index.css
Get-Content D:\filework\integration-worktree\frontend_dist_files\assets\index-*.css -Raw | 
    Select-String -Pattern 'el-drawer__header|el-drawer__body'

# 期望输出: 找到 .el-drawer__header { padding: 8px 16px !important; ... }
#           找到 .el-drawer__body { padding: 12px 16px !important; }
```

### 3.3 PM 验证

PM 刷新 http://localhost:3007/system/archdata → 点击领域行打开侧边弹窗：
- 期望 1：`el-drawer__header` 高度约 22px (padding 8px + 内容) 而不是 52px
- 期望 2：`el-drawer__body` padding 12px 而不是 20px
- 期望 3：标题与编辑/删除按钮之间空白从 32px 减到 12px

---

## 4. 后续 commit 节点

| 项 | 值 |
|----|-----|
| V054 cherry-pick (integration) | `75b408c` |
| 当前 integration HEAD | `75b408c` |
| 已包含 V053 + V054 + V051 改动 | ✓ |
| 待办 | 协调智能体重 build |

---

## 5. CHANGELOG

| 日期 | 作者 | 内容 |
|------|------|------|
| 2026-07-06 18:30 | PM | 报告"侧边弹窗详情页面 编辑/删除按钮上方空白" |
| 2026-07-06 19:00 | dev agent (V051) | 改 ObjectPageHeader.vue, 实际无用 |
| 2026-07-06 19:30 | dev agent (V052) | 改 ObjectDetailPage.vue, 实际无用 |
| 2026-07-06 20:54 | dev agent (V053) | cherry-pick el-drawer__header 改动到 integration |
| 2026-07-06 21:02 | dev agent (V054) | cherry-pick el-drawer__body 改动到 integration |
| 2026-07-06 21:08 | PM | "3007 测试并没有解决" |
| 2026-07-06 21:10 | dev agent (V055) | 诊断根因: vite preview 不重 build |

---

## 6. 经验教训（写进 SOP）

> **铁律 16: 验证前端 dev server 模式**（2026-07-06 V055 教训）
>
> - 修改 .scss/.vue 后 PM 看不到效果时, 第一步确认 vite dev server 模式
> - `vite preview` 只服务 build 产物, **不会**因源码改动重新编译
> - 修复方法: 重 build **或** 改用 `vite dev` 模式
> - 检查命令: `Get-WmiObject Win32_Process -Filter "ProcessId = <pid>" | Select CommandLine`
> - 看到 `vite preview` → 不是 dev 模式 → 需要 build/dev 切换

---

## 7. 关联 BUG

| BUG | 状态 | 说明 |
|-----|------|------|
| V051 | 否决 | ObjectPageHeader.vue 改错组件 |
| V052 | 否决 | ObjectDetailPage.odp-title-bar 改错组件 |
| V053 | 待 build 验证 | el-drawer__header 改动正确 |
| V054 | 待 build 验证 | el-drawer__body 改动正确 |
| **V055** | **本 HANDOVER** | vite preview 不重 build 是真正根因 |

---

## 8. 一句话总结

> **PM 的反馈 4 次都对，但 dev agent 的修改只在源码层生效——vite preview 模式服务的是 build 产物，源码改了也不会重新编译。协调智能体需要 `npm run build` 重 build 或改用 `vite dev` 启动 3007。**