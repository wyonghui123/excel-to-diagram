# 折叠/展开长耗时渲染 - 升级整屏遮罩 (2026-08-17)

## 背景 / 问题

用户报告：在架构数据管理页，从领域层级点击展开到业务对象时，元素多的情况下有约 10 秒渲染开销，但看不到明显的"正在渲染"反馈。

根因：折叠/展开渲染走 `foldRenderPending` 路径（`MermaidComponent.vue`），该路径刻意跳过整屏遮罩（`rendering` 保持 false），只显示右上角"渲染中..."小指示器（延迟 500ms 出现，尺寸小）。对 10 秒级长渲染，用户感知不到反馈，误以为无反应。

## 方案：耗时升级整屏遮罩

### 核心逻辑
折叠/展开渲染开始时，在现有角落指示器基础上，**增加"升级计时器"**：渲染持续超过阈值 `FOLD_ESCALATE_MS`（2 秒）仍未完成 → 设置 `foldRenderingEscalated = true`，触发与全量渲染相同的整屏"图表渲染中"遮罩。

### 交互时序
```
折叠/展开渲染开始
  ├─ showFoldLoading()      → 500ms 后角落小指示器 (现有)
  └─ scheduleFoldEscalate() → 2000ms 后 → foldRenderingEscalated=true → 整屏遮罩
渲染结束 (setRendering(false))
  └─ hideFoldLoading()      → 清除角落指示器 + 重置 foldRenderingEscalated=false
```

### 行为变化
| 场景 | 之前 | 之后 |
|------|------|------|
| 快速折叠 (<2s) | 角落小指示器（可忽略） | 不变（不闪屏） |
| 长耗时展开 (>2s, 如 10s) | 无显著反馈 | 2s 后整屏"图表渲染中"遮罩 |
| 普通全量渲染 (reload/切图) | 整屏遮罩 | 不变 |

### 改动点
1. `MermaidComponent.vue`:
   - 新增常量 `FOLD_ESCALATE_MS = 2000`
   - 新增 `foldRenderingEscalated = ref(false)`
   - 新增 `scheduleFoldEscalate()` / `cancelFoldEscalate()`：定时器设置/清除，设置 `foldRenderingEscalated.value = true`
   - `hideFoldLoading()` 内追加 `cancelFoldEscalate()`（渲染结束统一清除）
2. 模板: 整屏遮罩 `v-if="rendering"` 改为 `v-if="rendering || foldRenderingEscalated"`
3. CSS: 无新增（复用 `.mermaid-rendering-overlay` / 转圈动画）

### 双缓冲保留
升级遮罩不破坏折叠双缓冲（旧图克隆层 z-index:2，遮罩 z-index:3 覆盖其上）。渲染完成 `releaseFoldBuffer` + 遮罩淡出 → 新图淡入，过渡不变。

### 风险
- 误升级：若展开仅需 2~3s，会短暂出现遮罩——可接受（用户确实在等待）
- 遮罩与缓冲层叠放：遮罩覆盖旧图克隆，属预期（用户看到"正在渲染"而非旧图静止）
