# Mermaid 图 AI Coding 自动化测试方法论 - 复盘 (2026-06-15)

> **问题类型**: 测试方法论沉淀 + 基础设施建设  
> **触发事件**: 修复 BO_SUPPLIER_BO_REQ_01 居中问题 (v40.6→v40.8) 过程中的 6 个验证脚本  
> **目标**: 为后续所有 Mermaid 图相关修改建立可复用的 AI 自动化测试基础设施与规范  
> **状态**: 📋 复盘完成 / 提案待评审

---

## TL;DR

**本次 (修复居中问题) 我用了什么方法**:
1. Playwright 启动浏览器 → 走完 5 步向导 → 渲染 Mermaid 图
2. `page.evaluate()` 在浏览器里直接调 DOM API, 用 `getBoundingClientRect()` / `getCTM()` / `getPointAtLength()` 三层坐标互转
3. 数据写 JSON 文件, 截图视觉确认
4. 6 个脚本分层 (单点诊断 → 全量结构 → 批量验证 → 数据分析)

**关键痛点**:
- 测试脚本被终端限制杀掉多次, 中断恢复成本高
- 28 个 label 手动跑断言, 无可复用库
- 路径几何中点 vs 包围盒中心混淆了一次 (自己的测试代码 bug)
- 复现脚本跟生产代码脱节, 没法在 CI 跑
- 没有任何 baseline 对比, 改动前/后纯靠肉眼

**核心提案**: 建一个 `meta/tests/mermaid/` 测试基础设施, 提供 4 个核心能力 (导航/测量/断言/快照), 让 AI Agent 写 Mermaid 测试像写单元测试一样简单。

---

## 1. 我做了什么 (时间线)

### 1.1 脚本演进

| 顺序 | 脚本 | 目的 | 验证强度 |
|------|------|------|----------|
| 1 | `test_v407_verify.py` | 单 label 诊断 (v40.7 修复后) | 1 个 label |
| 2 | `test_diag_v408.py` | 详细单 label 诊断 (含所有层坐标) | 1 个 label + 完整字段 |
| 3 | `test_v408_full_shot.py` | 全图截图视觉确认 | 全图 |
| 4 | `test_v408_zoom.py` | 单 label 局部放大 + 红蓝标记 | 1 个 label + 视觉 |
| 5 | `test_v408_detail.py` | 28 个 label 完整结构 (el/gl/fo/lb/transform) | 全量 + 完整字段 |
| 6 | `test_v408_batch.py` | 28 个 label 批量验证 (简化) | 全量 + 简化 |
| 7 | `analyze_v408.py` | 统计数据, 计算偏差分布 | 后处理 |

### 1.2 核心代码模式 (反复用到)

**模式 A: 走完向导到图表页**

```python
# 1. 登录
await pg.evaluate("async () => { await fetch('/api/v1/auth/dev-login?username=admin', {credentials:'include'}); }")

# 2. 拉 product/version (业务数据)
pv = await pg.evaluate("""async () => {
    const r = await fetch('/api/v2/bo/product/list', ...);
    const p = b.data.find(x => x.code==='SUPPLY_CHAIN') || b.data[0];
    ...
    return {pid: p.id, vid: b2.data[0].id};
}""")

# 3. 写 sessionStorage (跨页 state)
ad = {'versionId': pv['vid'], 'productId': pv['pid'], 'hierarchyFilter': {}}
await pg.evaluate(f"""() => {{
    sessionStorage.setItem('archDataForDiagram', JSON.stringify({json.dumps(ad)}));
    ...
}}""")

# 4. 跳到图表页 + 走向导
await pg.goto('http://localhost:3004/archdata-chart', ...)
await pg.evaluate("""() => {
    for (const x of document.querySelectorAll('.chart-type-card')) { 
        if ((x.innerText||'').includes('业务对象图')) x.click(); 
    }
}""")
for _ in range(2):
    await pg.evaluate("""() => {
        for (const b of document.querySelectorAll('button')) { 
            if (b.innerText.trim() === '下一步') b.click(); 
        }
    }""")
await pg.evaluate("""() => {
    for (const b of document.querySelectorAll('button')) { 
        if (b.innerText.trim().includes('生成')) b.click(); 
    }
}""")
```

**模式 B: 三层坐标互转**

```javascript
// 1. SVG 用户坐标 (path 几何中点)
const pm = pathEl.getPointAtLength(pathEl.getTotalLength() / 2)  // {x, y}

// 2. SVG 用户坐标 → Viewport 像素 (用 getScreenCTM)
const ctm = pathEl.getScreenCTM()  // {a, b, c, d, e, f}
const vpX = ctm.a * pm.x + ctm.c * pm.y + ctm.e
const vpY = ctm.b * pm.x + ctm.d * pm.y + ctm.f

// 3. Viewport 像素 (DOM 元素位置)
const lbr = labelBkg.getBoundingClientRect()  // {x, y, width, height}
const lbCenterVpX = lbr.x + lbr.width / 2
```

**模式 C: 视觉确认 (画标记点)**

```javascript
// 在 path 几何中点画红圆, 在 g.edgeLabel transform 点画蓝圆
const c1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
c1.setAttribute('cx', pm.x); c1.setAttribute('cy', pm.y)
c1.setAttribute('r', '5'); c1.setAttribute('fill', 'red')
bp.parentNode.appendChild(c1)

const c2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
c2.setAttribute('cx', lx); c2.setAttribute('cy', ly)
c2.setAttribute('r', '5'); c2.setAttribute('fill', 'blue')
ds.appendChild(c2)
```

---

## 2. 关键 Wins (做对的地方)

### ✅ 2.1 三层坐标互转 + 显式 CTM

不假设"viewport 像素 ≈ SVG 单位", 每次显式过 CTM。这帮我发现了 xMidYMid slice 陷阱。

### ✅ 2.2 单点 → 批量 → 统计 的递进式验证

- v40.7 修完后, 单点 (BO_SUPPLIER_BO_REQ_01) 看着"差不多", 但**批量跑 28 个 label**才发现**15 个还有 20-100px 偏差**
- 这是单点验证 + 肉眼绝对发现不了的

### ✅ 2.3 JSON 输出 + 后续 Python 脚本分析

测试运行时把所有数据 dump 到 JSON, 后面用 `analyze_v408.py` 单独分析。**测试代码 = 数据采集器, 跟分析逻辑解耦**。

### ✅ 2.4 视觉确认 (截图) 跟数据断言 (JSON) 配合

- 数据断言: 28 个 label 偏差 < 3px ✓
- 视觉确认: 1 张全图 + 1 张局部放大, 肉眼二次确认 "不是测量对了但看着不对"
- 两个独立证据互相印证

### ✅ 2.5 调试脚本保留为资产

每个 `test_*.py` 看似临时, 实际承载了:
- 问题复现 (P0)
- 修复验证 (P1)  
- 防回归 (P2)
- 调试思路文档化 (P3)

---

## 3. 关键痛点 (做错的地方)

### ❌ 3.1 终端限制 5 个, 测试多次被强杀

实际表现: `python test_diag_v408.py` 跑到一半被 kill, 输出半截, JSON 不完整。  
根因: 测试服务占了多个终端, 我自己写脚本时跟它们抢。  
浪费: 至少 30 分钟在重跑 + 等服务空闲。

**教训**: 写测试前要 `service_manager.ps1 status` 看空闲, 或分配独立 `AGENT_PORT` 启动专属服务实例。

### ❌ 3.2 28 个 label 手动跑断言, 无可复用库

每个测试脚本都要手写 `for (const p of paths) ... for (const l of labels) ...` 的配对逻辑。**配对逻辑写错了 2 次**:

- 第一次: 假设 edgeLabel[i] ↔ path[i] (按 document 顺序)
- 第二次: 用包围盒中心找最近 path (但包围盒中心 ≠ 几何中点, 对角线 path 错)

**教训**: 配对逻辑应该封装成库函数 `findNearestPath(label, paths)`, 一次写对, 永远复用。

### ❌ 3.3 测试代码 bug 跟生产代码 bug 混在一起

我自己测试用 `path.getBoundingClientRect()` 的中心当 pathMid, 但对角线 path 包围盒中心 ≠ 几何中点。第一次 batch verify 时发现 15 个 label 偏差 20-100 px, 以为修复没生效, 实际是**测试代码错了**。

**教训**: 测试代码本身要单独验证, 不能跟生产代码一起 "看输出对不对"。

### ❌ 3.4 复现脚本跟生产代码脱节, CI 没法跑

这 6 个脚本:
- 用的是 hardcoded `localhost:3004` (主 agent 端口)
- 没走 `python test.py` 统一入口
- 没接 `AGENT_PORT` 端口隔离
- 没用 `factory` 准备测试数据 (而是 hardcoded `SUPPLY_CHAIN`)
- 不能在 CI 跑 (没 pytest 适配, 没 `--all/--failed` 集成)

**教训**: 调试脚本跟正式测试应该是同一套代码的两个用法, 不是两套代码。

### ❌ 3.5 没有 baseline, "改动前/后" 纯靠肉眼

我没法说 "v40.6 时, BO_SUPPLIER_BO_REQ_01 的 labelBkg viewport width 是 64.6 px, v40.8 修完后是 64.6 px (没变), 但 foreignObject width 从 69 SVG 变成 190 SVG"。  
**有 baseline 才能证明 "没退化"**, 没有就只能证明 "新功能对"。

### ❌ 3.6 截图是 PNG, 没法 diff

`v408_full.png` / `v408_bo_req_01_zoom.png` 是给肉眼看的, 机器没法对比。  
一个像素级别的回归 (如某 label 偏了 0.5px) 只能靠新一轮肉眼发现。

---

## 4. 基础设施提案

### 4.1 目标

让 AI Agent 写 Mermaid 图相关测试, 像写 pytest 单元测试一样简单:

```python
# 期望的写法 (未来)
def test_edge_labels_are_centered_on_paths(mermaid_session):
    """所有 edge label 应居中于其关联 path 的几何中点"""
    labels = mermaid_session.get_edge_labels()
    for label in labels:
        path = mermaid_session.find_nearest_path(label)
        diff = mermaid_session.get_label_path_diff(label, path)
        assert abs(diff.dx) < 3, f"label {label.text} dx={diff.dx}"
        assert abs(diff.dy) < 3, f"label {label.text} dy={diff.dy}"
```

### 4.2 架构 (4 层)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: 断言库 (assertions)                                │
│  - assert_label_centered_on_path                            │
│  - assert_label_background_fits_text                        │
│  - assert_node_within_container                             │
│  - assert_no_overlapping_labels                            │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: 测量工具 (measurement)                             │
│  - get_label_center_in_viewport(label)                      │
│  - get_path_geometric_midpoint_in_viewport(path)            │
│  - get_svg_to_viewport_scale(element)                       │
│  - get_layered_position(element) → {svg, viewbox, viewport}  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: DOM 辅助 (dom_helpers)                            │
│  - find_edge_labels(svg)                                    │
│  - find_paths(svg)                                          │
│  - find_nearest_path(label, paths)                          │
│  - get_transform_translate(element)                          │
│  - get_label_bkg_metrics(label)                             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: 导航/会话 (session)                                │
│  - login_as_admin(page)                                     │
│  - open_business_object_chart(page, product_id, version_id) │
│  - wait_for_mermaid_render(page, timeout=30)                │
│  - take_label_zoom_screenshot(page, label, padding=200)     │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 文件结构 (提案)

```
meta/tests/mermaid/
├── __init__.py
├── conftest.py                    # mermaid_session fixture
├── session.py                     # Layer 1: 导航/会话
│   ├── MermaidSession class
│   ├── login_as_admin()
│   ├── open_business_object_chart()
│   ├── open_service_module_chart()
│   ├── wait_for_mermaid_render()
│   └── take_label_zoom_screenshot()
├── dom_helpers.py                 # Layer 2: DOM 辅助
│   ├── find_edge_labels()
│   ├── find_paths()
│   ├── find_nearest_path()
│   ├── get_transform_translate()
│   ├── get_label_bkg_metrics()
│   └── get_marker_circles()
├── measurement.py                 # Layer 3: 测量
│   ├── svg_to_viewport()
│   ├── get_svg_to_viewport_scale()
│   ├── get_label_center_viewport()
│   ├── get_path_midpoint_viewport()
│   ├── get_label_path_diff()
│   └── get_layered_position()
├── assertions.py                  # Layer 4: 断言
│   ├── assert_label_centered_on_path()
│   ├── assert_label_background_fits_text()
│   ├── assert_no_overlapping_labels()
│   ├── assert_node_in_cluster()
│   └── assert_arrow_markers_present()
├── snapshots/                     # 基线截图
│   ├── business_object_full_v40.8.png
│   ├── business_object_BO_SUPplier_BO_REQ_01_v40.8.png
│   └── ...
├── test_edge_label_centering.py   # 示例: 居中测试
├── test_label_background.py       # 示例: 背景尺寸测试
├── test_arrow_markers.py          # 示例: 箭头测试
├── test_node_layout.py            # 示例: 节点布局测试
└── README.md                      # 使用文档
```

### 4.4 关键 API 设计 (详细签名)

#### Layer 1: session.py

```python
class MermaidSession:
    """封装一个 Mermaid 图测试会话"""

    def __init__(self, page: Page, port: int = 3010):
        self.page = page
        self.port = port
        self.svg_handle = None  # Lazy 初始化

    async def login_as_admin(self) -> None:
        """通过 dev-login 走 cookie 认证"""
        await self.page.evaluate(
            f"async () => {{ await fetch('http://localhost:{self.port}/api/v1/auth/dev-login?username=admin', {{credentials:'include'}}); }}"
        )

    async def open_business_object_chart(
        self,
        product_code: str = "SUPPLY_CHAIN",
        version_search: str = "v1",
        hierarchy_filter: dict = None,
    ) -> None:
        """
        走完向导到业务对象图。
        等价于: 选类型 → 下一步 → 配置 → 下一步 → 生成 → 等渲染
        """
        # ... 内部实现
        pass

    async def wait_for_mermaid_render(self, timeout: float = 30.0) -> ElementHandle:
        """等到 .mermaid svg 出现 + 有 edgeLabel"""
        # 关键: 不能只看 svg 出现, 要等 edgeLabel 渲染 (Mermaid 异步)
        pass

    @property
    def svg(self) -> ElementHandle:
        """获取主 flowchart svg (handle)"""
        if self.svg_handle is None:
            self.svg_handle = self.page.evaluate_handle(
                """() => {
                    const all = Array.from(document.querySelectorAll('svg'));
                    return all.find(s =>
                        s.getAttribute('class')?.includes('flowchart') &&
                        s.getAttribute('class')?.includes('hide-tails')
                    );
                }"""
            )
        return self.svg_handle

    async def take_label_zoom_screenshot(
        self, label_text: str, padding: int = 200, output_path: str = None
    ) -> str:
        """找到指定 label 截图局部, 自动加红/蓝标记点"""
        # ... 内部实现
        pass
```

#### Layer 2: dom_helpers.py

```python
def find_edge_labels(svg) -> list[dict]:
    """返回所有 g.edgeLabel 的描述 (含 text, element)"""
    return svg.evaluate("""(svg) => {
        return Array.from(svg.querySelectorAll('g.edgeLabel')).map(el => ({
            text: el.textContent.trim(),
            element: el,
        }));
    }""")

def find_paths(svg) -> list[dict]:
    """返回所有 path.flowchart-link 的描述"""
    return svg.evaluate("""(svg) => {
        return Array.from(svg.querySelectorAll('path.flowchart-link')).map(el => ({
            d: el.getAttribute('d'),
            element: el,
        }));
    }""")

def find_nearest_path(label: dict, paths: list[dict]) -> dict:
    """基于 path 几何中点找 label 最近的 path (不是包围盒中心!)"""
    return label['element'].evaluate(
        """(labelEl, pathsData) => {
            const paths = pathsData.map(p => p.element);
            const tMatch = labelEl.getAttribute('transform').match(
                /translate\\(([-\\d.]+)[,\\s]+([-\\d.]+)\\)/
            );
            const lx = parseFloat(tMatch[1]);
            const ly = parseFloat(tMatch[2]);
            let best = null, bd = Infinity;
            for (const p of paths) {
                try {
                    const m = p.getPointAtLength(p.getTotalLength() / 2);
                    const d = Math.hypot(m.x - lx, m.y - ly);
                    if (d < bd) { bd = d; best = p; }
                } catch (e) {}
            }
            return {element: best, distance: bd};
        }""",
        paths,
    )
```

#### Layer 3: measurement.py

```python
def svg_to_viewport(point_svg: dict, element_with_ctm) -> dict:
    """SVG 用户坐标 → viewport 像素, 用 element.getScreenCTM()"""
    return element_with_ctm.evaluate(
        """(el, pt) => {
            const ctm = el.getScreenCTM();
            if (!ctm) return null;
            return {
                x: ctm.a * pt.x + ctm.c * pt.y + ctm.e,
                y: ctm.b * pt.x + ctm.d * pt.y + ctm.f,
            };
        }""",
        point_svg,
    )

def get_svg_to_viewport_scale(element) -> float:
    """返回 element 的 SVG→viewport 缩放因子 (考虑 preserveAspectRatio)"""
    return element.evaluate("""(el) => {
        const ctm = el.getScreenCTM();
        if (!ctm) return 1;
        return Math.sqrt(ctm.a * ctm.a + ctm.b * ctm.b);
    }""")

def get_label_center_viewport(label: dict) -> dict:
    """labelBkg 中心在 viewport 坐标"""
    return label['element'].evaluate("""(el) => {
        const lb = el.querySelector('foreignObject div.labelBkg');
        if (!lb) return null;
        const r = lb.getBoundingClientRect();
        return {x: r.x + r.width/2, y: r.y + r.height/2};
    }""")

def get_path_midpoint_viewport(path: dict) -> dict:
    """path 几何中点 (不是包围盒中心!) 在 viewport 坐标"""
    return path['element'].evaluate("""(el) => {
        const len = el.getTotalLength();
        if (!isFinite(len) || len === 0) return null;
        const pm = el.getPointAtLength(len / 2);
        const ctm = el.getScreenCTM();
        if (!ctm) return null;
        return {
            x: ctm.a * pm.x + ctm.c * pm.y + ctm.e,
            y: ctm.b * pm.x + ctm.d * pm.y + ctm.f,
            svg: {x: pm.x, y: pm.y},
        };
    }""")

def get_label_path_diff(label: dict, path: dict) -> dict:
    """label 中心 vs path 中点 偏差 (像素)"""
    lc = get_label_center_viewport(label)
    pm = get_path_midpoint_viewport(path)
    if not lc or not pm:
        return None
    return {
        dx: lc.x - pm.x,
        dy: lc.y - pm.y,
    }
```

#### Layer 4: assertions.py

```python
def assert_label_centered_on_path(
    label: dict, path: dict, tolerance_px: float = 3.0
) -> None:
    """断言 label 居中于 path (默认 3px 容差)"""
    diff = get_label_path_diff(label, path)
    assert diff is not None, f"无法计算 {label['text']} 的偏差"
    assert abs(diff['dx']) < tolerance_px, (
        f"Label {label['text']!r} X 偏差 {diff['dx']:.2f}px 超过 {tolerance_px}px"
    )
    assert abs(diff['dy']) < tolerance_px, (
        f"Label {label['text']!r} Y 偏差 {diff['dy']:.2f}px 超过 {tolerance_px}px"
    )

def assert_label_background_fits_text(
    label: dict, max_overshoot_px: float = 2.0
) -> None:
    """断言 label 背景框不超出文字 (默认 2px 容差)"""
    metrics = label['element'].evaluate("""(el) => {
        const fo = el.querySelector('foreignObject');
        const lb = el.querySelector('foreignObject div.labelBkg');
        const text = el.querySelector('foreignObject div.labelBkg p, foreignObject div.labelBkg span');
        if (!fo || !lb || !text) return null;
        const ctm = fo.getScreenCTM();
        const scale = ctm ? Math.sqrt(ctm.a**2 + ctm.b**2) : 1;
        const foW = parseFloat(fo.getAttribute('width'));
        const lbRect = lb.getBoundingClientRect();
        const textRect = text.getBoundingClientRect();
        return {
            foWidthSvg: foW,
            labelBkgWidthVp: lbRect.width,
            textWidthVp: textRect.width,
            labelBkgWidthSvg: lbRect.width / scale,
            // 背景不应比文字大太多
            bgOvershootSvg: (lbRect.width - textRect.width) / scale,
        };
    }""")
    assert metrics, "无法测量 label 背景"
    assert metrics['bgOvershootSvg'] < max_overshoot_px, (
        f"Label {label['text']!r} 背景超出文字 {metrics['bgOvershootSvg']:.1f} SVG 单位"
    )
```

### 4.5 pytest 集成 (conftest.py)

```python
# meta/tests/mermaid/conftest.py
import pytest
import os
from playwright.async_api import async_playwright
from meta.tests.mermaid.session import MermaidSession

@pytest.fixture(scope="session")
async def playwright_instance():
    async with async_playwright() as p:
        yield p

@pytest.fixture
async def mermaid_session(playwright_instance):
    """
    创建一个 Mermaid 测试会话。
    - 自动用 AGENT_PORT 环境变量
    - 自动启服务 (如果没起)
    - 自动登录
    - 自动渲染业务对象图
    """
    port = int(os.environ.get("AGENT_PORT", 3010))
    browser = await playwright_instance.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1600, "height": 1000})
    page = await context.new_page()

    session = MermaidSession(page, port=port)
    await session.login_as_admin()
    await session.open_business_object_chart(
        product_code="SUPPLY_CHAIN", version_search="v1"
    )
    await session.wait_for_mermaid_render(timeout=30)

    yield session

    await browser.close()
```

### 4.6 示例测试 (用上面的基础设施)

```python
# meta/tests/mermaid/test_edge_label_centering.py
import pytest
from meta.tests.mermaid.dom_helpers import find_edge_labels, find_paths, find_nearest_path
from meta.tests.mermaid.measurement import get_label_path_diff
from meta.tests.mermaid.assertions import assert_label_centered_on_path

# 关注的 label (本轮回归的)
CRITICAL_LABELS = [
    "BO_SUPPLIER_BO_REQ_01",
    "BO_AP_PAYMENT_BO_SUPPLIER_01",
    # ... 用户最近反馈过的
]

@pytest.mark.asyncio
async def test_all_edge_labels_centered(mermaid_session):
    """所有 edge label 应居中于其关联 path 的几何中点 (3px 容差)"""
    labels = await find_edge_labels(mermaid_session.svg)
    paths = await find_paths(mermaid_session.svg)

    failures = []
    for label in labels:
        path = await find_nearest_path(label, paths)
        diff = await get_label_path_diff(label, path)
        if abs(diff['dx']) >= 3 or abs(diff['dy']) >= 3:
            failures.append({
                "text": label['text'],
                "dx": diff['dx'],
                "dy": diff['dy'],
            })

    assert not failures, f"{len(failures)} 个 label 偏离 path 中点:\n" + \
        "\n".join(f"  {f['text']}: dx={f['dx']:.1f}, dy={f['dy']:.1f}" for f in failures)


@pytest.mark.asyncio
async def test_critical_labels_centered_strict(mermaid_session):
    """关键 label 居中 (1px 容差, 严格)"""
    labels = await find_edge_labels(mermaid_session.svg)
    label_texts = {l['text']: l for l in labels}

    for target in CRITICAL_LABELS:
        if target not in label_texts:
            pytest.skip(f"label {target} 不在当前图")
        label = label_texts[target]
        paths = await find_paths(mermaid_session.svg)
        path = await find_nearest_path(label, paths)
        # 1px 严格容差
        diff = await get_label_path_diff(label, path)
        assert abs(diff['dx']) < 1.0, f"{target} X 偏差 {diff['dx']:.2f}px"
        assert abs(diff['dy']) < 1.0, f"{target} Y 偏差 {diff['dy']:.2f}px"
```

### 4.7 集成到 test.py 入口

把 `meta/tests/mermaid/` 目录注册到 test.py 的发现范围, 让 AI Agent 可以这样跑:

```bash
# 单测快速反馈
python d:\filework\test.py --port 3011 --single meta/tests/mermaid/test_edge_label_centering.py::test_all_edge_labels_centered

# 跑整个 mermaid 测试目录
python d:\filework\test.py --port 3011 --file meta/tests/mermaid/

# 全量 (含 mermaid)
python d:\filework\test.py --port 3011 --all --force
```

### 4.8 baseline 截图对比 (可视化回归)

```python
# meta/tests/mermaid/test_visual_snapshots.py
import pytest
from pathlib import Path
from meta.tests.mermaid.assertions import assert_visual_snapshot

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"

@pytest.mark.asyncio
async def test_business_object_full_snapshot(mermaid_session, request):
    """业务对象图全图应匹配 baseline 截图"""
    actual_path = request.node.name + ".png"
    await mermaid_session.page.screenshot(path=actual_path, full_page=True)

    baseline = SNAPSHOTS_DIR / "business_object_full_v40.8.png"
    if not baseline.exists():
        baseline.parent.mkdir(parents=True, exist_ok=True)
        # 第一次跑, 存为 baseline
        Path(actual_path).rename(baseline)
        pytest.skip("首次跑, 已生成 baseline")

    # 用 pixelmatch 做像素级 diff
    diff = assert_visual_snapshot(baseline, actual_path, threshold=0.01)
    assert diff < 0.01, f"视觉回归: {diff*100:.2f}% 像素变化"
```

---

## 5. 规范提案 (Mermaid 图 AI 测试规范)

### 5.1 测试文件命名

- `test_<功能>_<条件>.py` (e.g., `test_edge_label_centering.py`)
- 文件放在 `meta/tests/mermaid/`
- 截图 baseline 放在 `meta/tests/mermaid/snapshots/<版本>/`

### 5.2 测试分层

| 层 | 类型 | 数量 | 频率 |
|----|------|------|------|
| L0 | 烟雾测试 (图能渲染) | 1-2 个 | 每次改动 |
| L1 | 单 label/节点位置 | 10-20 个 | 视觉相关改动 |
| L2 | 全图批量验证 | 3-5 个 | 每次改动 |
| L3 | 视觉快照 | 5-10 个 | 版本基线 |
| L4 | 性能 (渲染时间) | 1-2 个 | 性能相关改动 |

### 5.3 关键约束 (Hard Constraints)

| # | 约束 | 违规后果 |
|---|------|----------|
| 1 | 必须走 `python test.py` 入口 (不用 pytest) | conftest 硬阻断 |
| 2 | 必须设 `AGENT_PORT` env | 端口冲突 |
| 3 | 不能 hardcode `localhost:3004`, 用 fixture | 多 Agent 不可移植 |
| 4 | 测量必须用 `getScreenCTM()` 转换, 不能用包围盒中心代替几何中点 | 对角线 path 错 |
| 5 | viewport 像素不能直接当 SVG 单位塞 setAttribute | 单位混淆 bug |
| 6 | 断言失败必须带 label text / 节点名 / 截图路径 | AI Agent 难 debug |
| 7 | 测试用数据必须用 factory, 不能 hardcode id=1 | 跨次跑冲突 |
| 8 | 截图 baseline 必须 commit 到 git, 不能本地临时 | 不可复现 |

### 5.4 调试脚本 vs 测试代码 的关系

**原则**: 同一套代码, 两个用途

```
调试时:   ad-hoc 跑, 输出详细 JSON, 拿截图
回归时:   pytest 跑, 用 fixture, 拿断言结果
```

实现: 把调试脚本中的 evaluate 块拆成可复用函数, 加 pytest fixture, 一份代码两用。

### 5.5 失败排查标准流程

```
测试失败
  ↓
看断言信息 (label text / 偏差值)
  ↓
跑 session 截图脚本 (mermaid_session.take_label_zoom_screenshot)
  ↓
看截图, 判断是:
  - 位置错 (→ 调 fixEdgeLabelToMidpoint 类函数)
  - 尺寸错 (→ 调 fixEdgeLabelOverflow 类函数)
  - 样式错 (→ 改 CSS)
  - 数据错 (→ 查 archDataForDiagram)
  ↓
修代码, 重跑测试
  ↓
通过 → commit + 更新 baseline
```

---

## 6. 实施路线图

### Phase 1 (1-2 天): MVP
- 写 `meta/tests/mermaid/session.py` (Layer 1)
- 写 `meta/tests/mermaid/measurement.py` (Layer 3, 核心)
- 把 `test_diag_v408.py` 改写成 pytest 风格
- 在 CI 跑通 1 个测试 (居中验证)

### Phase 2 (3-5 天): 库化
- 写 Layer 2 (dom_helpers) + Layer 4 (assertions)
- 写 5-10 个核心测试 (覆盖 edge label 居中/背景/箭头)
- 写 baseline 截图 (3-5 个)
- 集成到 test.py --all

### Phase 3 (1 周): 完善
- 加 conftest fixture
- 加 视觉快照对比
- 写 README + 规范文档
- 培训其他 Agent 使用

### Phase 4 (持续): 演进
- 每次 Mermaid 相关改动都先加测试
- 失败案例沉淀到 assertions 库
- 跨项目复用 (其他用 Mermaid 的项目)

---

## 7. 相关文件清单

### 本次调试脚本 (待改写)
- [test_diag_v408.py](file:///d:/filework/excel-to-diagram/test_diag_v408.py) — 单 label 诊断
- [test_v408_detail.py](file:///d:/filework/excel-to-diagram/test_v408_detail.py) — 28 label 结构
- [test_v408_batch.py](file:///d:/filework/excel-to-diagram/test_v408_batch.py) — 批量验证
- [analyze_v408.py](file:///d:/filework/excel-to-diagram/analyze_v408.py) — 统计分析

### 现有相关测试 (待集成)
- `test_archdata_chart_v32.py` — Pinia store 测试, 不验证 SVG 视觉
- 缺: Mermaid 渲染视觉测试

### 现有经验沉淀
- [docs/retrospectives/2026-06-11-edge-label-truncation.md](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-11-edge-label-truncation.md) — 上次 edge label 截断问题
- [docs/lessons-learned/mermaid/edgeLabel-styling.md](file:///d:/filework/excel-to-diagram/docs/lessons-learned/mermaid/edgeLabel-styling.md) — edge label 样式
- [docs/research/mermaid-text-centering-debug.md](file:///d:/filework/excel-to-diagram/docs/research/mermaid-text-centering-debug.md) — 居中调试

### 相关 Skills / 规则
- `test-bootstrap` (已加载) — 跑测试前必读
- `e2e-testing` — Playwright E2E 测试工作流
- `mcp-frontend-testing` — MCP DevTools 浏览器验证
- `.trae/rules/e2e-simplification.md` — E2E 简化规范
- `.trae/rules/browser-test-verification.md` — 浏览器验证方法

---

## 8. 总结

### 核心洞察
**调试脚本 ≠ 测试代码, 但调试方法论 = 测试方法论**

我这次成功是因为:
1. 三层坐标互转 + CTM 显式 (帮发现 xMidYMid slice 陷阱)
2. 单点 → 批量 → 统计的递进 (单点看不出, 批量暴露 15/28 失败)
3. 数据 + 视觉双证据 (JSON 数字 + PNG 截图互相印证)

但流程上 "低效" 是因为:
1. 调试脚本 = 一次性, 不能复用
2. 复现脚本 ≠ CI 测试
3. 没有 baseline, 没法防回归

**基础设施化的本质**: 把"一次性调试经验"封装成"可复用测试资产", 让下一个 Agent 改 Mermaid 代码时, 不用从零写 evaluate 块, 直接调 `assert_label_centered_on_path()` 就行。

### 一句话建议
**别再 hardcode localhost:3004 写 evaluate 块了。** 把这次 6 个脚本里的可复用部分抽到 `meta/tests/mermaid/`, 让 AI Agent 写 Mermaid 测试像调 `mermaid_session.assert_label_centered(label)` 一样简单。

---

_本复盘聚焦 "测试方法论 + 基础设施", 跟 [2026-06-15-svg-edge-label-centering](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-15-svg-edge-label-centering.md) (聚焦 "bug 根因") 互补。_
