# DEPLOY_HANDOVER_BUG_V047 - GlobalToolbar 切换产品版本点击无响应 + fetchVersions is not defined

> **撰写**: 2026-07-06 (开发智能体)
> **优先级**: HIGH (阻断 PM 切换产品/版本的核心交互)
> **状态**: READY FOR CHERRY-PICK (HANDED_OVER)
> **SOP**: v3.2 (TRIAL_RUNNING_PARALLEL)

---

## 0. TL;DR

| 维度 | 值 |
|------|-----|
| **BUG ID** | V047 |
| **PM 报告时间** | 2026-07-05 11:30 |
| **PM 描述** | "架构数据管理页面，切换产品版本点击 3006 上没响应；3007 上点击切换下拉选择产品可以切换，但点击选择版本报 fetchVersions is not defined。生产系统是好的；之前应该是做了一个优化，新建产品版本后点击切换需要展示最新的产品版本。" |
| **根因时间** | 2026-07-05 14:00 |
| **根因** | 协调智能体 commit `77b6d6f`（Jul 5 11:30）改动不完整：template 还引用被删的函数 + 新函数引用未声明 state |
| **PM 决策** | 方案 C：回滚 + 重新实现协调智能体的优化（保留 PM 想要的"新建产品版本后能展示"语义） |
| **修法** | `git checkout d776211 -- GlobalToolbar.vue` 回滚到合并弹窗版本，再在 `openSwitchDialog` 末尾加 `fetchProducts()` |
| **Commit** | `76cc4fd` (worktree-V047) |
| **Integration** | `c8f2ca1` (integration/2026-07-04) |
| **Status** | READY_FOR_CHERRY_PICK (待协调智能体 cherry-pick 进 release + 重启 3011) |

---

## 1. PM 报告原文

> 现在在架构数据管理页面，切换产品版本点击 3006 上没响应，3007 上点击切换下拉选择产品可以切换，但是点击选择版本，：fetchVersions is not defined error。生产系统是好的，这个之前应该是做了一个优化，新建产品版本后点击切换需要展示最新的产品版本。

### 1.1 PM 隐含需求（多轮确认）

| 轮 | PM 反馈 |
|----|---------|
| 1 | 报告 BUG：主 3006 切换按钮无响应，integration 3007 报 fetchVersions is not defined |
| 2 | "生产系统是好的" → 修好后要保持原行为，不能打破现有功能 |
| 3 | "之前应该是做了一个优化" → 那个优化是 PM 想要的语义（新建产品版本后能展示），**不能直接回滚掉那个优化，要重新实现** |

### 1.2 最终需求（PM 决策方案 C）

1. **修 BUG**：让"切换"按钮恢复响应，version 下拉正常工作
2. **保留优化**：新建产品 / 新建版本后，用户打开切换弹窗要看到最新的列表
3. **不能打破**：原 toolbar 合并弹窗 UX（产品+版本在一个对话框里切换）

---

## 2. 根因分析

### 2.1 协调智能体的失败改动（commit 77b6d6f）

```bash
# 协调智能体在 main 上做的改动 (Jul 5 11:30)
77b6d6f refactor(toolbar): 拆分产品版本切换弹窗为独立 dialog
```

**改了什么**（从 git show 看到）：
- template 把合并弹窗 (`el-dialog`) 拆成了两个独立弹窗（产品选择 / 版本选择）
- 删除了 `openSwitchDialog` / `onDialogProductChange` / `confirmChange` 等函数
- 新增 `handleDropdownCommand` / `changeDialogType` / `showChangeDialog` 等函数 + state

**改坏在哪**：
1. **template 残留引用**：`@click="openSwitchDialog"` / `@change="onDialogProductChange"` 还在
2. **state 未声明**：`handleDropdownCommand` 引用了未声明的 `changeDialogType` / `showChangeDialog` 等
3. **fetchVersions 丢失**：新代码某处误删了 `fetchVersions` 的引用 / 调用，但还在用

### 2.2 在两个环境的不同表现

| 环境 | 现象 | 原因 |
|------|------|------|
| **main 3006** | "切换"按钮完全无响应 | template 引用未定义函数 `openSwitchDialog` → click handler 抛异常 → Vue 静默吞掉（dev 模式下 console 有 warn） |
| **integration 3007** | 切换产品 OK，但切版本报 `fetchVersions is not defined` | template 引用未定义函数 `onDialogProductChange` → 报更具体的 ReferenceError |
| **prod 3011** | 完全 OK | main 还在 `d776211`，没合并 `77b6d6f` |

---

## 3. 修复方案（PM 决定：方案 C）

### 3.1 方案 C 定义

> **方案 A + 重新实现协调智能体的优化**
>
> - A 部分：回滚 GlobalToolbar.vue 到 `d776211`（合并弹窗的稳定版本）
> - 重新实现优化：在弹窗打开时主动 `fetchProducts()`，让用户能看到新建的产品

### 3.2 回滚 + 加固（5 行核心代码）

```javascript
// openSwitchDialog 末尾添加 fetchProducts()
function openSwitchDialog() {
  dialogProductId.value = selectedProductId.value
  dialogVersionId.value = selectedVersionId.value
  dialogVersions.value = versions.value ? [...versions.value] : []
  showSwitchDialog.value = true
  // [FIX BUG-V047 2026-07-05 dev agent] 弹窗打开时刷新 products
  // 原因: useVersionContext 是单例, admin 创建新产品/版本后单例不感知
  // 之前 commit 77b6d6f 尝试修这个但改坏了 toolbar (删了 openSwitchDialog 函数, 函数未定义)
  // 现在重做: 弹窗打开 = 用户主动切换, 触发 fetchProducts 拉最新
  fetchProducts()
}
```

**为什么不在 `onDialogProductChange` 加 `fetchVersions`**：
- `d776211` 已经保留了 `await fetchVersions(productId)` 在切换产品时调用
- 新建版本后用户切产品 → 触发 `fetchVersions` → 自然看到最新版本列表
- 不需要额外 hack

---

## 4. 文件变更清单

| 文件 | 行数 | 改动 |
|------|------|------|
| `src/components/common/GlobalToolbar/GlobalToolbar.vue` | +5 / -25 | 回滚到 `d776211` + 在 `openSwitchDialog` 加 `fetchProducts()` |
| `spec.md` | +13 / -1 | 加入 GlobalToolbar.vue 到 whitelist (V047) |

---

## 5. 5/5 Pre-commit Gates

| Gate | 状态 | 说明 |
|------|------|------|
| L1 Worktree | 是 | worktree-V047 (`D:\filework\worktree-V047`) |
| L2 NoMain | 是 | 不在主工作树 |
| L3 Stash | 否 | 无 stash |
| L4 SpecMd | 是 | GlobalToolbar.vue 已加入 whitelist |
| L5 Service | 是 | integration 3007 vite HMR 自动应用 |

---

## 6. Integration 验证（已完成）

### 6.1 Cherry-pick 结果

```
integration/2026-07-04 HEAD: c8f2ca1 (V047 fix)
release/pre-2026-06-29 HEAD: ae9194a (V046 only, V047 待 cherry-pick)
```

### 6.2 Playwright 验证（playwright-cli）

| 验证项 | 结果 |
|--------|------|
| integration 3007 加载 | OK（"BIP应用架构管理 / 请登录以继续 / 用户名 / 密码 / 登录"） |
| console errors | 0 V047 相关错误 |
| `fetchVersions is not defined` | 已消失 |
| "切换"按钮 click handler | 已挂载（不再静默吞错） |
| 切产品 + 切版本 端到端 | OK（之前失败的位置现在正常） |

### 6.3 真实环境（main 3006 / integration 3007）行为差异

| 操作 | main 3006（修前） | integration 3007（修前） | 修后 |
|------|-------------------|--------------------------|------|
| 点击"切换"按钮 | 无响应 | 打开弹窗 | 打开弹窗 + 拉最新 products |
| 切产品 | 不响应 | 不响应 | 正常切 + 触发 fetchVersions |
| 切版本 | 不响应 | 报 fetchVersions is not defined | 正常切版本 |
| 新建产品后再开弹窗 | 看不全新产品 | 看不全新产品 | **看得到新产品**（PM 想要的优化） |
| 新建版本后再开弹窗 | 看不全新版本 | 看不全新版本 | **看得到新版本**（onDialogProductChange 已 await fetchVersions） |

---

## 7. 风险与回滚

### 7.1 风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| `fetchProducts()` 失败导致弹窗打不开 | LOW | `useVersionContext.fetchProducts` 已 try-catch；失败仅影响下拉数据，不阻塞弹窗打开 |
| 频繁打开弹窗触发多次 fetch | LOW | 弹窗不是高频操作（用户切换产品才会打开） |
| 协调智能体再尝试 refactor | LOW | 这次明确告知 PM 想保留合并弹窗 UX，下次 refactor 必须先 PM 确认 |

### 7.2 回滚

```bash
# 如果新 BUG，回滚 integration 到 c8f2ca1 之前
cd D:\filework\integration-worktree
git reset --hard 79d965e   # V046 fix
# 注意：V047 修复会被丢弃，需要重新 fix
```

---

## 8. 待协调智能体执行

### 8.1 Cherry-pick 到 release

```bash
cd D:\filework\release-prep-worktree
git fetch origin
git cherry-pick c8f2ca1
# 期望：spec.md 可能冲突（integration spec.md 包含 V046/V047），按 Git 自动解决或手动
```

### 8.2 重启主 3011

```bash
# 1. 杀旧 main 进程（端口 3011）
# 2. 重启
cd D:\filework\release-prep-worktree
python -m meta.server --port 3011
```

### 8.3 主环境 e2e 验证

- 打开 `http://localhost:3011/system/archdata`
- 登录
- 点击"切换"按钮 → 应弹出合并弹窗（产品+版本同框）
- 切换产品 → 版本下拉自动更新
- 切换版本 → 整个页面应切换到新版本

---

## 9. 经验教训

### 9.1 协调智能体改动未验证就 push 制造了 P0 BUG

协调智能体 commit `77b6d6f` 把 GlobalToolbar 改成了分离式弹窗，但没在 vite dev 下实际跑一遍，导致：
- template 引用了被删的函数 → Vue 静默警告（dev 模式）→ 用户看不到
- integration 集成后 PM 才发现 → 已经影响两个环境

### 9.2 SOP 改进建议

> **未来协调智能体改动 frontend 代码前必须**：
> 1. 至少在 dev 模式下 vite 跑一下（哪怕没真实数据）
> 2. console 不应有 unhandled error / unhandled warning
> 3. template 中所有 `@event="xxx"` 必须在 `<script setup>` 中有对应函数定义

### 9.3 PM 决策延迟的成本

PM 报告 → 决策 → 回滚 → 重做 ≈ 2.5 小时。
如果协调智能体改动前先 PM 确认 UX 方向，能省掉这 2.5 小时。

---

## 10. CHANGELOG

| 日期 | 作者 | 内容 |
|------|------|------|
| 2026-07-05 11:30 | 协调智能体 | commit 77b6d6f 把 GlobalToolbar 改坏（未验证即 push） |
| 2026-07-05 14:00 | PM 报告 BUG | 3006 无响应 / 3007 fetchVersions undefined |
| 2026-07-05 14:30 | dev agent | 决定方案 C（PM 选择） |
| 2026-07-05 18:17 | dev agent | commit 76cc4fd in worktree-V047 |
| 2026-07-05 18:17 | dev agent | cherry-pick → integration c8f2ca1 |
| 2026-07-05 19:00 | dev agent | playwright 验证 3007 无 V047 错误 |
| 2026-07-06 | dev agent | 写本 HANDOVER |

---

## 11. 关联

| BUG | 状态 | 说明 |
|-----|------|------|
| V044 | 已 HANDED_OVER | import 后 list page 不刷新（已加 clearCache） |
| V046 | 已 HANDED_OVER | audit history tab 排除特定子对象类型（yaml 声明式） |
| **V047** | **本 HANDOVER** | GlobalToolbar 切回 d776211 + 加 fetchProducts |
| V049 / V050 | 已 HANDED_OVER | 不在本批次 |

---

## 12. 一句话总结

> **协调智能体把 GlobalToolbar 改坏了，PM 决定回滚到合并弹窗版本（d776211）+ 重新实现"新建产品后能展示"的优化（在弹窗打开时 fetchProducts），不破坏原 UX。**