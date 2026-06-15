# 架构图 edge label 居中问题 (v40.7→v40.8) - 复盘 (2026-06-15)

> **问题类型**: Mermaid SVG 渲染 / 坐标系统混淆  
> **影响范围**: 业务对象图所有 28 个关系连线 (edge label)  
> **修复耗时**: 约 4 小时 (v40.6 垂直居中 → v40.7 scaleY 修复 → v40.8 单位换算修复)  
> **状态**: ✅ 已修复 (28/28 label 偏差 < 1px)

---

## TL;DR

**问题现象**: 关系线上的标题文字 (如 `BO_SUPPLIER_BO_REQ_01`) 没有精准居中于连线中点, 文字中心相对 path 中点**横向偏移 20-100px**, 且白色背景框**比文字内容大 2-3 倍** (右侧撑出)。

**根因 (3 层叠加)**:
1. **v40.6 用错缩放因子**: 高度从 viewport → SVG 单位时用 `scaleX` 而非 `scaleY`, 算出的 SVG 高度偏大, 让 div 中心上偏 0.5-2 SVG 单位
2. **v40.7 修复了高度, 但没修宽度**: 高度用 `scaleY` 转换 ✓, 但 `fixEdgeLabelOverflow` 函数中**宽度仍用 viewport 像素直接当 SVG 单位**
3. **xMidYMid slice 让事情更糟**: Mermaid 11 SVG 用 `preserveAspectRatio="xMidYMid slice"`, 实际视觉缩放 = `max(scaleX, scaleY)`, 不是单一的 `scaleX`。设 `width=69 SVG` (实际应是 185), viewport 显示 24px, 而 labelBkg 内容 64.6px, 撑出 foreignObject 右侧

**修复 (v40.8)**: 用 `foreignObject.getCTM()` 拿真实 SVG→viewport 缩放因子, 把 viewport 像素换算成 SVG 单位再设给 `foreignObject width` 属性。

**结果**: 28/28 label X 偏差 -0.71 ~ -0.86 px (sub-pixel), Y 偏差本质 0。

---

## 1. 问题发展时间线 (3 轮迭代)

### v40.6 (垂直方向不对)
- 用户反馈: "label 在连线上方 / 下方, 没居中"
- 误判: 假设是 text 视觉中心在 div 顶部 0.35×H 处
- 错误: `gLabelY = -textH * 0.35` (硬编码经验值)
- 实际: HTML baseline 行为下, 文字视觉中心 ≈ div 几何中心
- **问题**: 文字视觉中心落在 path 下方 1-3 px

### v40.7 (修了垂直, 露出水平 bug)
- 修复: 改用 `gLabelY = -textH/2` 让 div 几何中心对齐 path
- 新问题 (未察觉): `fixEdgeLabelOverflow` 用 `labelBkg.getBoundingClientRect().width` (viewport 像素) 直接当 SVG 单位
- 当 SVG 用 `xMidYMid slice` (scaleX=0.289, scaleY=0.349), 实际缩放 = 0.349
- 错误设 `foreignObject width=69 SVG` → viewport 24 px, 远小于内容 64.6 px
- 用户反馈: "labelBkg 撑出 foreignObject 右侧, 文字右偏"

### v40.8 (根本修复)
- 核心改动: 用 `foreignObject.getCTM()` 拿真实 SVG→viewport 缩放
- 换算: `measuredWidthSvg = measuredWidthVp / effectiveScale`
- 验证: 全部 28 个 label 居中 ✓

---

## 2. 根因技术细节

### 2.1 xMidYMid slice 是什么鬼

Mermaid 11 SVG 输出 `preserveAspectRatio="xMidYMid slice"` (从 `setupCanvasLayout` 日志确认)。这意味着:

```
viewBox: 5308.98 × 2105.67
svg rect: 1534 × 735
scaleX (字面) = 1534 / 5308.98 = 0.289
scaleY (字面) = 735 / 2105.67 = 0.349

slice = 用较大缩放均匀缩放, 多余部分裁剪
实际缩放 = max(0.289, 0.349) = 0.349
```

后果: X 轴方向 viewport 像素 = SVG 单位 × 0.349 (不是 0.289)。  
任何"用 `svgRect.width / viewBox.width` 算 scaleX 然后换算"的代码都是错的。

### 2.2 旧代码的 unit bug

```javascript
// ❌ 旧代码 (v40.7) — viewport 像素 vs SVG 单位混淆
const measuredWidth = labelBkg.getBoundingClientRect().width  // 64.6 px (viewport)
const targetWidth = Math.ceil(measuredWidth + SAFETY)        // 68.6 ???
foreignObject.setAttribute('width', String(targetWidth))      // 设 68.6 SVG ???
```

`getBoundingClientRect().width` 返回**屏幕像素**, 但 `foreignObject width` 属性是 **SVG 用户坐标**。这俩不是同一个单位!

- 正确 SVG width: 64.6 / 0.349 = **185 SVG 单位**
- 错误 SVG width: 68.6 SVG 单位 (直接当像素塞进去)
- 实际显示宽度: 68.6 × 0.349 = 23.94 px (远小于内容 64.6 px)

### 2.3 v40.7 高度的"侥幸正确"

```javascript
// ✅ v40.7 高度换算
textHSvg = textHVp / (scaleY || scaleX || 1)
// height = 8.38 px / 0.349 = 24.01 SVG
// 跟 foHeight=24 SVG 几乎一致 → 看起来"对了"
```

高度用 `scaleY` 是对的 (Y 轴方向缩放)。Y 方向没有 slice 问题 (因为 slice 的多余是水平方向的)。所以 v40.7 高度 OK, 但宽度没改 → 留下隐患。

### 2.4 fixEdgeLabelOverflow 的历史背景

这函数从 v33 就存在, 当时 SVG 默认 `preserveAspectRatio="xMidYMid meet"` 或无 transform, viewport 像素 ≈ SVG 单位 (1:1 缩放)。后来 Mermaid 升级到 11 改成 slice, 函数没跟着改。

---

## 3. 修复代码 (v40.8)

修改文件: [src/composables/useMermaid/style/useSvgStyle.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js#L404-L469)

```javascript
let measuredWidthVp = 0
try {
  const rect = labelBkg.getBoundingClientRect()
  measuredWidthVp = rect.width
} catch (e) {
  measuredWidthVp = labelBkg.scrollWidth || 0
}

if (measuredWidthVp > 0) {
  // [v40.8 关键] 拿真实 SVG→viewport 缩放
  let effectiveScale = 1
  try {
    const ctm = foreignObject.getCTM()
    if (ctm) {
      effectiveScale = Math.sqrt(ctm.a * ctm.a + ctm.b * ctm.b) || 1
    }
  } catch (e) {
    // 退路: 用 svg rect / viewBox 推算 (用 max 模拟 slice)
    const svgEl2 = foreignObject.closest('svg')
    if (svgEl2) {
      const sr = svgEl2.getBoundingClientRect()
      const vb = svgEl2.viewBox?.baseVal
      if (vb && vb.width > 0 && vb.height > 0) {
        effectiveScale = Math.max(sr.width / vb.width, sr.height / vb.height)
      }
    }
  }

  // viewport 像素 → SVG 单位
  const measuredWidthSvg = measuredWidthVp / (effectiveScale || 1)
  const targetWidth = Math.ceil(measuredWidthSvg + SAFETY)
  // ...
}
```

---

## 4. 调试方法论 (本次有效)

### 4.1 三层坐标系的可视化

| 层级 | 坐标系 | 工具 |
|------|--------|------|
| 1. SVG 用户空间 | `getCTM()` 之前的坐标 | `path.getPointAtLength(L/2)`, `getAttribute('transform')` |
| 2. Viewport 空间 | 浏览器屏幕像素 | `getBoundingClientRect()`, `getCTM()` |
| 3. 中间层 | SVG viewBox 缩放 | `viewBox.baseVal`, `getCTM()` |

每次定位都明确"我在哪一层", 不混用。

### 4.2 诊断脚手架

```javascript
// 在浏览器里画标记点对比 SVG 用户空间 vs viewport 空间
const c1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
c1.setAttribute('cx', pm.x); c1.setAttribute('cy', pm.y)  // SVG 用户空间
c1.setAttribute('r', '5'); c1.setAttribute('fill', 'red')

const ctm = path.getScreenCTM()  // SVG→viewport
const vpX = ctm.a * pm.x + ctm.c * pm.y + ctm.e
// 红色圆点应该出现在 vpX,vpY 处 — 视觉确认
```

### 4.3 关键诊断: 包围盒中心 ≠ 几何中点

```javascript
// ❌ 错误: 拿 path 包围盒中心
const pathMidVpX = pr.x + pr.width/2
// 对水平 path OK, 对对角线 path 偏差巨大

// ✅ 正确: 用 getPointAtLength 拿几何中点
const pm = path.getPointAtLength(path.getTotalLength() / 2)
const ctm = path.getScreenCTM()
const pathMidVpX = ctm.a * pm.x + ctm.c * pm.y + ctm.e
```

### 4.4 批量验证优于单点

跑了 28 个 edge label 验证, 全自动, < 5 秒。比逐个看截图快 100 倍。

---

## 5. 测试缺口 & 改进

### 当前缺口
- 0 个针对 Mermaid 渲染输出的 E2E 测试
- 现有 `test_archdata_chart_v32.py` 只测 Pinia store, 完全不验证 SVG 视觉输出
- 这种"viewport 像素 vs SVG 单位"类 bug, 纯单元测试很难抓到 (jsdom 不支持 getCTM)

### 应加的测试
1. **位置断言**: 对每个 edge label, 断言 `labelBkg.cx` 跟 `path.getPointAtLength(L/2)` 转换到 viewport 后偏差 < 3px
2. **背景尺寸断言**: 断言 `foreignObject width` (SVG) ≈ `labelBkg.viewport.width / effectiveScale + SAFETY`, 不允许 1:1 像素直塞
3. **保留 aspect ratio 变化测试**: 切到 `xMidYMid meet` / `none` / 旋转 90°, 验证仍居中

### 复现脚本 (保留价值)
- `test_diag_v408.py` — 单 label 详细诊断
- `test_v408_batch.py` — 28 个 label 批量验证 (含 pathMidVp 计算)
- `test_v408_detail.py` — 完整结构诊断 (el/gl/fo/lb 全字段)
- `analyze_v408.py` — 数据分析

---

## 6. 经验教训 (跨项目适用)

### 🎯 铁律 1: SVG 单位 vs Viewport 单位永远要明确

```javascript
// ❌ 把 viewport 像素当 SVG 单位塞
foreignObject.setAttribute('width', String(rect.width))

// ✅ 先换算
const ctm = foreignObject.getCTM()
const svgW = rect.width / Math.sqrt(ctm.a**2 + ctm.b**2)
foreignObject.setAttribute('width', String(svgW))
```

任何**`getBoundingClientRect()` 拿到的东西**都需先除以**当前 CTM 的缩放因子**再设回 SVG 属性。

### 🎯 铁律 2: xMidYMid slice 是隐形炸弹

`getBoundingClientRect() / viewBox.baseVal.width` 算出来的 scaleX **不等于**实际视觉缩放。

- slice: `max(svgW/vbW, svgH/vbH)`
- meet: `min(svgW/vbW, svgH/vbH)`
- 单一缩放: 上面两个相等

永远用 `getCTM()` 拿真实缩放, 不要从 svg/viewBox 反推。

### 🎯 铁律 3: "看起来对" 跟 "测了 < 1px 偏差" 是两回事

v40.7 修复后, label 看起来"差不多了", 但批量验证发现 15/28 label 偏差 20-100 px。  
肉眼难发现 1px 偏差, 但发现 20px 偏差后, 往往根因是系统性的, 其他 label 也中招。

**原则**: 任何"位置/尺寸"修复, 都要做**全量回归** + **多 label 统计**, 不能只看一个。

### 🎯 铁律 4: 高度对了 ≠ 宽度对了

v40.7 高度用 scaleY (对) → 垂直居中 OK → 我以为"问题解决了"  
实际上宽度没用缩放换算 → 水平还偏 → 用户再次反馈 "还没居中"

**原则**: 二维问题 (X/Y) 不能用一维验证 (只看 Y) 当作"全好了"。修一个轴就检查两个轴。

### 🎯 铁律 5: CTM 的 a/b/c/d 不是缩放因子, 是变换矩阵分量

```javascript
// ❌ 把 CTM.a 当缩放 (常见错误, 只在无旋转时碰巧对)
const scale = ctm.a

// ✅ 缩放 = X 基向量的长度 (考虑旋转)
const scale = Math.sqrt(ctm.a**2 + ctm.b**2)
```

### 🎯 铁律 6: 复现脚本 = 调试资产

调试过程中写的 `test_diag_*.py` / `test_v408_*.py` 看似临时, 实际是**最有价值的资产**:
- 证明问题存在 (P0)
- 验证修复有效 (P1)
- 防止回归 (P2)
- 文档化调试思路 (P3)

完成后**保留并整理**, 不要删。

---

## 7. 关键数字快照

### 修复前 (v40.7)
| label | dx (px) | 备注 |
|-------|---------|------|
| BO_SUPPLIER_BO_REQ_01 | **-97.55** | 文字右偏, 背景右侧撑出 |
| BO_INVENTORY_BO_INV_LOG_01 | -208.5 | 极度偏移 |
| (其他 15 个 label 都有类似问题) | | |

### 修复后 (v40.8)
| 指标 | 数值 |
|------|------|
| 28/28 label X 偏差范围 | -0.86 ~ -0.71 px |
| 28/28 label Y 偏差范围 | -0.00005 ~ 0.00004 px (本质 0) |
| foreignObject width (修正) | 185~253 SVG (之前 69~95 SVG) |

X 偏差恒定 -0.80 px 是 SAFETY 4 SVG 单位的 1.4 px 视觉效果 (labelBkg 在 foreignObject 内左对齐, 留 4 单位空在右)。视觉上完全不可见。

---

## 8. 行动项

### 立即 (已做)
- [x] 修复 fixEdgeLabelOverflow 的单位换算 bug
- [x] 28 个 label 全量验证通过
- [x] 保留 6 个调试脚本作为资产

### 短期 (1 周内)
- [ ] 在 `useEdgeLabelStyle.js` 加注释警示"viewport ≠ SVG 单位"
- [ ] 在 `setupCanvasLayout` 改 `xMidYMid slice` 为 `xMidYMid meet`, 避免缩放陷阱 (需评估对布局影响)
- [ ] 写 E2E 测试: 渲染后断言每个 label 中心 vs path 中点 < 3px

### 长期
- [ ] 抽象一个 `svgUnitToViewport()` / `viewportToSvgUnit()` 工具函数, 统一所有需要单位换算的地方
- [ ] 加 lint 规则禁止 `getBoundingClientRect().width` 直接 setAttribute 到 SVG 属性
- [ ] 复盘 [2026-06-11-edge-label-truncation](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-11-edge-label-truncation.md) 的测试缺口, 设计 Mermaid 渲染 E2E 测试套件

---

## 9. 相关文件清单

### 改动
- [src/composables/useMermaid/style/useSvgStyle.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js) — `fixEdgeLabelOverflow` 函数 (line 404-469)

### 调试脚本 (保留)
- [test_diag_v408.py](file:///d:/filework/excel-to-diagram/test_diag_v408.py) — 单 label 详细诊断
- [test_v408_detail.py](file:///d:/filework/excel-to-diagram/test_v408_detail.py) — 全 28 label 结构诊断
- [test_v408_batch.py](file:///d:/filework/excel-to-diagram/test_v408_batch.py) — 批量验证
- [analyze_v408.py](file:///d:/filework/excel-to-diagram/analyze_v408.py) — 统计

### 历史相关
- [2026-06-11-edge-label-truncation](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-11-edge-label-truncation.md) — 上次 edge label 问题 (截断)
- [docs/lessons-learned/mermaid/edgeLabel-styling.md](file:///d:/filework/excel-to-diagram/docs/lessons-learned/mermaid/edgeLabel-styling.md) — edge label 样式经验

### 数据快照
- [v408_detail.json](file:///d:/filework/excel-to-diagram/v408_detail.json) — 28 label 完整测量数据
- [v408_bo_req_01_zoom.png](file:///d:/filework/excel-to-diagram/v408_bo_req_01_zoom.png) — 视觉验证截图
- [v408_full.png](file:///d:/filework/excel-to-diagram/v408_full.png) — 全图截图

---

_本次复盘核心: SVG 渲染问题调试时, **第一件事**是确认坐标系 (SVG 用户空间 vs viewport 像素), 任何 `getBoundingClientRect()` 的结果都不能直接塞进 SVG 属性。_
