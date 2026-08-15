# -*- coding: utf-8 -*-
"""
[FOLD-OVERLAP 2026-08-12] 验证折叠/展开过渡阶段无 UI 元素重叠

背景: 折叠/展开渲染走 mermaid-fold-buffer 缓冲层 (跳过整屏 loading), 修复前:
  1. 新 SVG 在 mermaid.run() 布局完成前堆叠在中心且完全可见 (缺 is-fold-rendering 隐藏)
  2. 缓冲层克隆的旧图未复制 content 的 pan/zoom transform → 平移/缩放后位置错位重叠

修复:
  - captureFoldBuffer 复制 content.style.transform 到缓冲层
  - is-fold-rendering class 隐藏新 SVG (CSS opacity:0)

验证点:
  A. 折叠渲染期间 .mermaid-content 有 is-fold-rendering class
  B. 缓冲层 transform 与 content transform 一致
  C. 渲染完成后 is-fold-rendering 移除、缓冲层移除
"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
RESULTS = []

def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

with PlaywrightCLI() as cli:
    # ---- 登录 ----
    page = cli._ensure_browser()
    page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=15000)
    page.goto(f"{BASE}/system/archdata?preset=scp", wait_until="domcontentloaded", timeout=15000)
    page.wait_for_selector('.mermaid-content svg', timeout=60000)
    print(">>> 图表已渲染")

    # ---- 模拟用户平移/缩放 (设置 content transform) ----
    page.evaluate("""
        () => {
          const el = document.querySelector('.mermaid-content');
          if (el) el.style.transform = 'translate(120px, 80px) scale(1.4)';
        }
    """)
    time.sleep(0.5)
    before_t = page.evaluate("() => (document.querySelector('.mermaid-content')||{}).style?.transform || '(none)'")
    print(f">>> content transform = {before_t}")

    # ---- 折叠渲染期间精确检测 (MutationObserver 记录 class/缓冲层时间线) ----
    # [IMPROVE 2026-08-12] 轮询 100ms 间隔可能错过 is-fold-rendering 存在的短暂窗口
    #   (releaseFoldBuffer 有 300ms 淡出延迟 → 轮询可能抓到"缓冲层在但 class 已移除").
    #   改用 MutationObserver 在页面端记录 class 变化, 事后读取时间线, 不遗漏任何窗口.
    page.evaluate("""
        () => {
          const content = document.querySelector('.mermaid-content');
          const wrapper = document.querySelector('.mermaid-wrapper');
          if (!content || !wrapper) return false;
          window.__foldObs = { timeline: [], start: performance.now() };
          const record = () => {
            const buf = wrapper.querySelector('.mermaid-fold-buffer');
            const svg = content.querySelector('svg');
            window.__foldObs.timeline.push({
              dt: Math.round(performance.now() - window.__foldObs.start),
              cls: content.className,
              hasBuffer: !!buf,
              bufTransform: buf ? (buf.style.transform || '(none)') : null,
              svgLen: svg ? svg.outerHTML.length : 0,
              svgOpacity: svg ? getComputedStyle(svg).opacity : null
            });
          };
          const mo = new MutationObserver(() => record());
          mo.observe(content, { attributes: true, attributeFilter: ['class'], childList: true });
          // wrapper 子节点增删 (缓冲层出现/移除) 也记录
          mo.observe(wrapper, { childList: true });
          record();  // 初始状态
          window.__foldObs.mo = mo;
          // [B3] rAF 逐帧采样: MutationObserver 合并 microtask 中的 DOM 变更, 无法捕捉
          //   "新 SVG 已写入且 FOLD 仍在" 的精确帧. rAF 每帧执行, 记录所有可见帧的状态.
          window.__foldSamples = [];
          const sample = () => {
            const svg = content.querySelector('svg');
            window.__foldSamples.push({
              t: Math.round(performance.now() - window.__foldObs.start),
              fold: content.classList.contains('is-fold-rendering'),
              hasSvg: !!svg,
              svgLen: svg ? svg.outerHTML.length : 0,
              opacity: svg ? getComputedStyle(svg).opacity : null
            });
            const buf = wrapper.querySelector('.mermaid-fold-buffer');
            // 采样到缓冲层消失后再多采 0.5s (淡入) 即停, 避免无限采样
            if (buf || window.__foldSamples.length < 2000) {
              requestAnimationFrame(sample);
            }
          };
          requestAnimationFrame(sample);
          return true;
        }
    """)
    time.sleep(0.3)
    page.evaluate("""
        () => {
          // 记录 dblclick 前一刻的旧图长度 (排除旧图在折叠前的 processSvg 尺寸修改干扰)
          window.__foldObs.oldSvgLen = (document.querySelector('.mermaid-content svg') || {}).outerHTML?.length || 0;
          window.__foldObs.dblclickAt = performance.now() - window.__foldObs.start;
          window.__foldObs.timeline.push({ dt: Math.round(performance.now()-window.__foldObs.start), cls: document.querySelector('.mermaid-content').className, hasBuffer: !!document.querySelector('.mermaid-fold-buffer'), svgOpacity: getComputedStyle(document.querySelector('.mermaid-content svg')).opacity, marker: 'before-dblclick' });
        }
    """)

    # 触发折叠: 双击第一个 cluster (供应链云)
    page.evaluate("""
        () => {
          const clusters = document.querySelectorAll('.mermaid-content svg g.cluster');
          const target = clusters[0];
          if (!target) return false;
          const rect = target.getBoundingClientRect();
          const cx = rect.left + rect.width / 2;
          const cy = rect.top + rect.height / 2;
          target.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, detail: 2 }));
          return { cx: Math.round(cx), cy: Math.round(cy), nodes: clusters.length };
        }
    """)

    # 等待折叠渲染完成 (缓冲层出现又消失) 或超时
    try:
        page.wait_for_function(
            "() => !document.querySelector('.mermaid-fold-buffer') && window.__foldObs && window.__foldObs.timeline.some(t => t.hasBuffer)",
            timeout=12000
        )
    except Exception as e:
        print(f">>> 等待折叠渲染完成超时: {e}")
    # 缓冲层淡出完成后, 等 class 清除彻底落定
    time.sleep(0.6)
    page.evaluate("() => window.__foldObs.timeline.push({ dt: Math.round(performance.now()-window.__foldObs.start), cls: document.querySelector('.mermaid-content').className, hasBuffer: !!document.querySelector('.mermaid-fold-buffer'), svgOpacity: getComputedStyle(document.querySelector('.mermaid-content svg')).opacity, marker: 'after-settle' })")

    timeline = page.evaluate("() => window.__foldObs.timeline")
    # 输出时间线供分析
    print(">>> fold 时间线 (dt/class 摘要):")
    for t in timeline:
        flags = []
        if 'is-fold-rendering' in t['cls']: flags.append('FOLD')
        if 'is-rendering' in t['cls']: flags.append('REND')
        mark = t.get('marker', '')
        print(f"    +{t['dt']:>6}ms  buf={t['hasBuffer']}  opacity={t['svgOpacity']}  [{','.join(flags)}] {mark}")

    # 判定: 时间线中任一记录同时满足 缓冲层存在 + class 含 is-fold-rendering
    has_buffer_flag = any(t['hasBuffer'] for t in timeline)
    has_flag = any('is-fold-rendering' in t['cls'] for t in timeline)
    flag_during_buffer = any(t['hasBuffer'] and 'is-fold-rendering' in t['cls'] for t in timeline)
    # [B3] 基于 rAF 逐帧采样判定: 新 SVG 已写入 (svgLen 相比前帧突变) 且 FOLD 仍在 的帧中,
    #   SVG opacity 必须全部为 0 (被 is-fold-rendering CSS 隐藏). 排除旧 SVG 的 transition 尾巴帧
    #   (FOLD 加入瞬间旧图从 1 渐隐, opacity∈(0,1] 属正常过渡, 且 mermaid.run 随后清空旧图).
    samples = page.evaluate("() => window.__foldSamples || []")
    # 新 SVG 帧判定: FOLD 窗口内 svgLen != dblclick 前旧图长度 的帧即新图 (旧图在折叠前可能被
    #   processSvg 修改长度, 不能用首帧; 旧图 transition 渐隐帧 len 仍等于旧图, 天然排除).
    old_svg_len = page.evaluate("() => window.__foldObs?.oldSvgLen || 0")
    fold_new_svg = [s for s in samples if s.get('fold') and s.get('hasSvg') and s.get('svgLen') != old_svg_len]
    hidden_ok = bool(fold_new_svg) and all(s.get('opacity') == '0' for s in fold_new_svg)
    print(f">>> rAF 采样 {len(samples)} 帧, FOLD+新SVG共存 {len(fold_new_svg)} 帧, 全部隐藏={hidden_ok} (旧图len={old_svg_len})")
    if fold_new_svg:
        for s in fold_new_svg:
            print(f"    FOLD+SVG帧 +{s['t']}ms opacity={s['opacity']} svgLen={s['svgLen']}")
    # 缓冲层 transform 复制: 取缓冲层存在时记录的 bufTransform 与折叠前 content transform 对比
    buf_transforms = [t['bufTransform'] for t in timeline if t['hasBuffer'] and t.get('bufTransform')]

    record('A. 折叠期间存在缓冲层', has_buffer_flag)
    record('B. 折叠期间 content 有 is-fold-rendering', has_flag, f"timeline_entries={len(timeline)}")
    record('B2. is-fold-rendering 与缓冲层同窗共存', flag_during_buffer)
    record('B3. 折叠期间新 SVG 被隐藏 (opacity=0)', hidden_ok, f"fold_svg_frames={len(fold_new_svg)}")
    if buf_transforms:
        record('C. 缓冲层 transform 已复制', all(bt == before_t for bt in buf_transforms), f"buf={buf_transforms[0]} content={before_t}")
    else:
        record('C. 缓冲层 transform 已复制', False, '未捕获到缓冲层 transform')

    # ---- 终态检查: 无残留 ----
    time.sleep(1.0)
    final = page.evaluate("""
        () => {
          return {
            hasBuffer: !!document.querySelector('.mermaid-fold-buffer'),
            isFoldRendering: (document.querySelector('.mermaid-content')||{}).classList?.contains('is-fold-rendering') || false,
            contentOpacity: getComputedStyle(document.querySelector('.mermaid-content svg')).opacity
          };
        }
    """)
    record('D. 终态无缓冲层残留', not final.get('hasBuffer'))
    record('E. 终态无 is-fold-rendering', not final.get('isFoldRendering'))
    record('F. 终态 SVG 可见 (opacity=1)', final.get('contentOpacity') == '1', f"opacity={final.get('contentOpacity')}")

    # ---- 截图 ----
    cli.screenshot('verify_fold_overlap_final.png')

print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
passed = sum(1 for r in RESULTS if r['ok'])
print(f"\n结果: {passed}/{len(RESULTS)} PASS")
sys.exit(0 if passed == len(RESULTS) else 1)
