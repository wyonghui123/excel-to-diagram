/**
 * 备注叠加层渲染
 */
import {
  getCategoryConfig,
  getTypeConfig,
  toCircleNumber,
  PANEL_POSITION
} from './annotationConfig.js';

let isDraggingState = false;

import { useDiagnostics } from '../core/useDiagnostics.js'

export function useAnnotationOverlay() {
  const diag = useDiagnostics()  // [FIX 2026-08-01] annotation 埋点

  const overlayNumberMarkers = (svg, numberMap, annotations) => {
    return null;
  };

  const getElementBBox = (el, targetType) => {
    // 对于容器，获取标题标签的位置而不是整个容器
    if ((targetType === 'container') && el.getBBox) {
      // 查找容器内的标签元素
      const label = el.querySelector('.cluster-label, text');
      if (label) {
        try {
          const labelBBox = label.getBBox();
          if (labelBBox) {
            console.log('Using container label bbox:', labelBBox);
            return labelBBox;
          }
        } catch (e) {
          console.log('Failed to get label bbox:', e);
        }
      }
    }
    
    if (el.getBBox) {
      try {
        return el.getBBox();
      } catch (e) {
        return null;
      }
    }
    const rect = el.getBoundingClientRect();
    const svg = el.closest('svg');
    if (!svg) return null;
    const svgRect = svg.getBoundingClientRect();
    return {
      x: rect.left - svgRect.left,
      y: rect.top - svgRect.top,
      width: rect.width,
      height: rect.height
    };
  };

  const calculateNumberPosition = (bbox, position) => {
    const offset = 14;
    switch (position) {
      case 'top-left':
        return { x: bbox.x - offset + 8, y: bbox.y - offset + 12 };
      case 'top-right':
        return { x: bbox.x + bbox.width - offset + 8, y: bbox.y - offset + 12 };
      case 'top-center':
        return { x: bbox.x + bbox.width / 2, y: bbox.y - offset + 12 };
      default:
        return { x: bbox.x + bbox.width - offset, y: bbox.y - offset + 12 };
    }
  };

  // 实例级状态：每个 useAnnotationOverlay() 调用都有自己的清理列表
  let _cleanupFns = []

  // 注册可清理的事件监听器
  const addListener = (element, event, handler, options) => {
    element.addEventListener(event, handler, options)
    _cleanupFns.push(() => element.removeEventListener(event, handler, options))
  }

  // 清理本实例注册的所有事件监听器（DOM 由 removeAnnotationLayers 处理）
  const cleanupListeners = () => {
    _cleanupFns.forEach(fn => fn())
    _cleanupFns = []
  }

  const overlayAnnotationPanel = (svg, annotations, options = {}) => {
    const {
      position = PANEL_POSITION.BOTTOM
    } = options;

    const container = svg.closest('.mermaid-container');
    if (!container) return null;

    let existingPanel = container.querySelector('.annotation-dock-panel');
    if (existingPanel) {
      existingPanel.remove();
    }

    // 状态：'collapsed'(收起), 'compact'(简洁), 'detail'(详情)
    const savedState = sessionStorage.getItem('annotationPanelState') || 'compact';
    let currentState = savedState;

    const panel = document.createElement('div');
    panel.className = 'annotation-dock-panel';
    panel.setAttribute('data-annotation-layer', 'panel');

    const updatePanel = () => {
      const maxHeight = currentState === 'collapsed' ? '20px' : (currentState === 'detail' ? '300px' : '120px');
      const overflowY = currentState === 'collapsed' ? 'hidden' : (currentState === 'detail' ? 'auto' : 'visible');

      panel.style.cssText = `
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        max-height: ${maxHeight};
        background: rgba(248, 248, 248, 0.98);
        border-top: 1px solid #eee;
        padding: ${currentState === 'collapsed' ? '4px 12px' : '4px 12px'};
        box-sizing: border-box;
        overflow-y: ${overflowY};
        z-index: 100;
        font-family: Arial, sans-serif;
        display: flex;
        flex-direction: column;
        max-width: 100%;
      `;
    };

    updatePanel();

    const header = document.createElement('div');
    header.className = 'annotation-header';
    header.style.cssText = `
      display: flex;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;
      cursor: pointer;
      user-select: none;
    `;
    header.title = '点击循环切换：收起 → 简洁模式 → 详情模式 → 收起';

    const titleSpan = document.createElement('span');
    titleSpan.style.cssText = `
      font-weight: bold;
      font-size: 11px;
      color: #999;
      white-space: nowrap;
    `;

    const getTitleText = () => {
      switch (currentState) {
        case 'collapsed': return '备注 ▶';
        case 'compact': return '备注（简）▼';
        case 'detail': return '备注（详）▼';
        default: return '备注 ▼';
      }
    };

    titleSpan.textContent = getTitleText();
    header.appendChild(titleSpan);
    panel.appendChild(header);

    const list = document.createElement('div');
    list.className = 'annotation-list';
    list.style.cssText = `
      display: ${currentState === 'collapsed' ? 'none' : 'flex'};
      flex-wrap: ${currentState === 'detail' ? 'none' : 'wrap'};
      gap: 4px;
      flex: 1;
      ${currentState === 'detail' ? 'flex-direction: column;' : ''}
    `;

    const updateContentStyles = () => {
      list.querySelectorAll('.annotation-content').forEach(contentEl => {
        if (currentState === 'detail') {
          contentEl.style.whiteSpace = 'normal';
          contentEl.style.maxWidth = 'none';
          contentEl.style.overflow = 'visible';
          contentEl.style.textOverflow = 'none';
        } else {
          contentEl.style.whiteSpace = 'nowrap';
          contentEl.style.maxWidth = '180px';
          contentEl.style.overflow = 'hidden';
          contentEl.style.textOverflow = 'ellipsis';
        }
      });
    };

    // 循环切换状态：collapsed -> compact -> detail -> collapsed
    const onHeaderClick = () => {
      console.log('[annotation-header-click]', { from: currentState, to: '?' })
      if (currentState === 'collapsed') {
        currentState = 'compact';
        list.style.display = 'flex';
        list.style.flexDirection = 'row';
        list.style.flexWrap = 'wrap';
      } else if (currentState === 'compact') {
        currentState = 'detail';
        list.style.display = 'flex';
        list.style.flexDirection = 'column';
        list.style.flexWrap = 'none';
      } else {
        currentState = 'collapsed';
        list.style.display = 'none';
      }
      sessionStorage.setItem('annotationPanelState', currentState);
      titleSpan.textContent = getTitleText();
      updatePanel();
      updateContentStyles();
    };
    // [FIX 2026-06-29 v9] onclick 属性 + addEventListener 双重保险
    //   之前只用 addEventListener, 但 addListener 包装有 _cleanupFns 时序问题
    //   改用 onclick 属性 (HTML 绑定, 不依赖 event system)
    //   + addEventListener 兜底
    header.onclick = onHeaderClick
    header.addEventListener('click', onHeaderClick)
    header.setAttribute('data-click-bound', 'true')
    console.log('[overlayAnnotationPanel] header click listener attached via onclick+addEventListener, header.outerHTML:', header.outerHTML.substring(0, 200))

    annotations.forEach(ann => {
      // [FIX 2026-06-29 v5] categoryConfig 可能 null (ann.category 不在 CATEGORY_CONFIG 中)
      //   兜底链: getCategoryConfig(ann.category) -> getCategoryConfig('info') -> inline default
      //   修复 'Cannot read properties of null (reading border)' 错误
      const categoryConfig = getCategoryConfig(ann.category) || getCategoryConfig('info') || { label: ann.category || '信息', bg: '#e6f7ff', border: '#1677ff' };
      const item = document.createElement('div');
      item.className = `annotation-item annotation-${ann.targetType}`;
      item.setAttribute('data-target-id', ann.targetId);
      item.style.cssText = `
        display: flex;
        align-items: baseline;
        padding: 2px 6px;
        background: transparent;
        border-left: 2px solid ${categoryConfig.border};
        border-radius: 2px;
        max-width: 100%;
        box-sizing: border-box;
      `;

      const isDetailMode = currentState === 'detail';
      if (isDetailMode && ann.targetType === 'relation' && (ann.sourceBOName || ann.targetBOName)) {
        item.title = `源业务对象: ${ann.sourceBOName}\n目标业务对象: ${ann.targetBOName}\n\n备注: ${ann.content}`;
      } else {
        item.title = ann.content;
      }

      const titleSpan = document.createElement('span');
      titleSpan.style.cssText = `
        font-weight: bold;
        font-size: 11px;
        color: #666;
        margin-right: 4px;
        white-space: nowrap;
      `;

      const nameText = ann.targetName;
      titleSpan.textContent = nameText;

      item.appendChild(titleSpan);

      if (isDetailMode && ann.targetType === 'relation' && (ann.sourceBOName || ann.targetBOName)) {
        const relationInfo = document.createElement('span');
        relationInfo.style.cssText = `
          color: #888;
          font-size: 10px;
          margin-right: 4px;
          white-space: nowrap;
        `;
        relationInfo.textContent = `(${ann.sourceBOName} → ${ann.targetBOName})`;
        item.appendChild(relationInfo);
      }

      const separator = document.createElement('span');
      separator.textContent = ':';
      separator.style.cssText = `
        color: #bbb;
        margin-right: 4px;
      `;
      item.appendChild(separator);

      const contentSpan = document.createElement('span');
      contentSpan.className = 'annotation-content';
      contentSpan.style.cssText = `
        color: #888;
        font-size: 11px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: ${isDetailMode ? 'normal' : 'nowrap'};
        max-width: ${isDetailMode ? 'none' : '180px'};
      `;

      contentSpan.textContent = ann.content;

      item.appendChild(contentSpan);
      list.appendChild(item);
    });

    panel.appendChild(list);
    container.appendChild(panel);
    return panel;
  };

  const bindAnnotationInteraction = (svg, annotations, options = {}) => {
    // 先清理本实例上一次的监听器（panel header + svg 全局）
    cleanupListeners()

    // [FIX 2026-08-01] 记录 annotation 监听器绑定 — 排查 "click annotation panel 没响应" 类问题
    diag.recordStepMeta('bindAnnotationInteraction', {
      svgId: svg.id || '',
      annotationCount: annotations?.length || 0
    })

    const container = svg.closest('.mermaid-container');
    if (!container) return;

    // [FIX 2026-07-31] 居中回调: 选中 annotation 后调用 (实现"点备注滚到对应节点"功能)
    const { onCenterElement } = options;

    const annotationMap = new Map();
    annotations.forEach(ann => {
      annotationMap.set(ann.targetId, ann);
    });

    container.querySelectorAll('.annotation-item').forEach(item => {
      const onItemClick = () => {
        const targetId = item.getAttribute('data-target-id');
        const ann = annotationMap.get(targetId);
        const targetType = ann ? ann.targetType : null;
        if (targetId && targetType) {
          // [FIX 2026-08-01 v4] highlightTargetElement 内部已经同步 panel selected + 高亮 chart.
          //   不再单独加 .annotation-item-selected / background — 否则会 "双击自己 item 时把 selected 重复加".
          const targetEl = highlightTargetElement(svg, targetId, targetType);
          // 调用居中回调 (MermaidComponent 注入)
          if (onCenterElement && targetEl) {
            try { onCenterElement(targetEl); } catch (e) { console.warn('[bindAnnotationInteraction] onCenterElement failed:', e) }
          }
        }
      };
      const onItemMouseEnter = () => {
        const targetId = item.getAttribute('data-target-id');
        if (targetId) {
          hoverTargetElement(svg, targetId, true);
        }
      };
      const onItemMouseLeave = () => {
        const targetId = item.getAttribute('data-target-id');
        if (targetId) {
          hoverTargetElement(svg, targetId, false);
        }
      };
      addListener(item, 'click', onItemClick);
      addListener(item, 'mouseenter', onItemMouseEnter);
      addListener(item, 'mouseleave', onItemMouseLeave);
    });

    const onSvgMouseDown = () => {
      isDraggingState = false;
    };
    const onSvgMouseMove = (e) => {
      if (e.buttons > 0) {
        isDraggingState = true;
      }
    };
    const onSvgMouseUp = () => {
      setTimeout(() => {
        isDraggingState = false;
      }, 100);
    };
    const onSvgClick = (e) => {
      // [FIX 2026-08-01 v3] 同一 click 事件只处理一次 (防止 svg/label/path 多 listener 重复触发).
      //   现状: bindAnnotationInteraction 在 svg、每个 edgeLabel、每个 flowchart-link path 上
      //   都绑了同一个 onSvgClick. 用户的真实 click 会触发 svg 上的 capture 阶段 listener (svg.click),
      //   然后冒泡阶段又触发 label.click → 同一个 handler 被调 2 次.
      //   如果 addLinkCodeAttributes 在不同生命周期多次 bindAnnotationInteraction (annotation 更新),
      //   cleanupListeners 清理 svg 的 listener 但 label/path 的 listener 因 _cleanupFns 闭包问题被残留,
      //   handler 会被调 3+ 次 → 每次都累加 transform, 导致过冲 (用户感知"偏的比较多").
      //   修复: 用 event.__annoHandled + e.timeStamp 双重标记.
      //   实测: e.__annoHandled 单独不够 — 因为 dispatchEvent 内部似乎为子元素 click 创建了不同的事件路径.
      //   改用 lastHandledTime 全局锁: 200ms 内同 svg 上的 click 只处理一次.
      const svgEl = svg
      if (svgEl && e) {
        const now = (e.timeStamp) || Date.now()
        if (svgEl.__lastAnnoClickTime && now - svgEl.__lastAnnoClickTime < 200) return
        svgEl.__lastAnnoClickTime = now
      }
      // 排除拖拽操作触发的点击
      if (!isDraggingState) {
        if (e.target === svg || e.target.closest('.annotation-dock-panel') === null) {
          // 检查点击目标是否是备注相关元素
          const isAnnotationItem = e.target.closest('.annotation-item');
          const isAnnotationOverlay = e.target.closest('.annotation-overlay');
          if (isAnnotationItem || isAnnotationOverlay) return;

          // [FIX 2026-07-31] 单击节点/容器/连线 → 高亮 + 居中
          //   设计意图: 用户期望单击图表元素时, 同步高亮(对齐备注面板) + 居中显示
          //     - 与 annotation 面板 item 点击行为完全对等
          //     - 支持 BO 图节点、BO 图容器 (serviceModule)、SM 图节点、SM 图容器、连线
          //   之前 onSvgClick 只清高亮, 不处理单击节点 → 用户误以为"必须双击"(实际双击触发 autoFit)
          const { nodeEl, containerEl, edgeEl, edgeLabelEl } = findTargetFromEvent(svg, e.target, e);
          let clickedTargetEl = null;
          let clickedTargetType = null;
          let clickedTargetId = null;

          if (nodeEl) {
            clickedTargetEl = nodeEl;
            clickedTargetType = 'node';
            // [FIX 2026-08-02] data-code/data-id 缺失时, 用 nodeLabel 文本兜底
            //   addNodeCodeAttributes 依赖 label 正则 `\(([^)]+)\)`, 部分节点匹配不上 → 无 data-code.
            //   之前 fallback 到 data-id 也为空 → 整段 if 跳过 → 当作"空白"清高亮 / 或误命中外层 cluster.
            //   现在用 label 文本作 targetId, highlightTargetElement 内部 text.includes 可命中.
            clickedTargetId = nodeEl.getAttribute('data-code')
              || nodeEl.getAttribute('data-id')
              || getNodeLabelText(nodeEl);
          } else if (containerEl) {
            clickedTargetEl = containerEl;
            clickedTargetType = 'container';
            // [FIX 2026-08-01] 优先 data-container-code (annotation 系统标识),
            //   缺失时用 cur.id 兜底 (mermaid 11 ELK 默认形如 "G_D_供应链云").
            //   否则 clickedTargetId 为 null 会导致整段 if (clickedTargetId) 跳过,
            //   用户点 cluster 后无任何响应 (不居中不高亮).
            clickedTargetId = containerEl.getAttribute('data-container-code') || containerEl.id;
          } else if (edgeLabelEl) {
            // edgeLabel 是 .edgeLabel > foreignObject (用户更常点中的是 label 文字)
            // 找最近的 edge 元素 + relationCode
            const labelG = edgeLabelEl.closest('g.edge') || edgeLabelEl.closest('g');
            clickedTargetEl = labelG;
            clickedTargetType = 'relation';
            // [FIX 2026-07-31 v2] 优先级: data-relation-code > data-id="L_..." > edgeLabel text
            //   addLinkCodeAttributes 在 link.code/relationCode/relationDesc 缺时无法匹配 ELK 自动 label
            //   → 兜底用 edgeLabel textContent 作为 relation key (高亮可以工作, 但不精确对应 link)
            clickedTargetId = findRelationCodeForLabel(svg, edgeLabelEl)
              || (edgeLabelEl.querySelector('.label') && edgeLabelEl.querySelector('.label').getAttribute('data-id'))
              || (edgeLabelEl.textContent || '').trim();
          } else if (edgeEl) {
            // 直接点 path, 找 path 上的 data-relation-code 或最近 edgeLabel
            const g = edgeEl.closest('g.edge') || edgeEl.closest('g');
            clickedTargetEl = g;
            clickedTargetType = 'relation';
            // [FIX 2026-07-31 v4] path 直接点击: 兜底用 closest('.edgeLabel') 的 textContent
            //   path 不在 .edgeLabel 子树下, closest g 也不是 g.edge
            //   真正的兜底: 用 path.getAttribute('d') 作为唯一 ID
            const nearestLabel = edgeEl.closest('.edgeLabel');
            clickedTargetId = edgeEl.getAttribute('data-relation-code')
              || findRelationCodeForLabel(svg, edgeEl)
              || (nearestLabel && (nearestLabel.textContent || '').trim())
              || ('path-' + edgeEl.getAttribute('d').substring(0, 50));  // 终极兜底: 用 d 前 50 字符作为 ID
          }

          if (clickedTargetEl && clickedTargetType && clickedTargetId) {
            // [FIX 2026-07-31 v3 v5] 给 highlightTargetElement 传 clickEdgeEl (label 或 path) 作为兜底
            //   当 addLinkCodeAttributes 没设 data-relation-code 时 (ELK 自动 label 不可匹配),
            //   highlightTargetElement 内部 text.includes(targetId) 找不到,
            //   但我们已经有 clickEdgeEl 直接拿 DOM, 直接高亮
            // [FIX 2026-08-01 v5] **不再居中** — 居中只在点 panel item 时触发.
            //   chart 上的元素被点击只是"我点了这里"的临时反馈 (高亮表示), 用户视觉位置不动.
            //   这样避免 "用户随手点 chart 任意位置 → 图表跳走" 的 UX 问题.
            //   设计意图与 VSCode 大纲/面包屑: 选中元素不强制滚动, 用户可自行决定是否需要居中.
            const clickEdgeEl = edgeLabelEl || edgeEl
            // [FIX 2026-08-01 v5] syncPanel='auto': 仅当 panel 有对应 item 时同步 panel
            //   - chart 元素被点击, 如果有对应 panel item → panel 切到该 item
            //   - chart 元素被点击, 但无对应 panel item → panel 保留原状 (用户已选的备注还在)
            highlightTargetElement(svg, clickedTargetId, clickedTargetType, clickEdgeEl, { syncPanel: 'auto' })
          } else {
            // 点击空白区域: 清高亮
            clearAllHighlights(svg)
          }
        }
      }
    };

    /**
     * [FIX 2026-07-31] 从事件 target 找节点/容器/连线
     *   - 节点: .node (data-code)
     *   - 容器: .subgraph / .cluster (data-container-code)
     *   - 连线 label: .edgeLabel (含 foreignObject, 用户最常点)
     *   - 连线 path: <path>
     *
     * [FIX 2026-08-02] 点 cluster 背景空白 ≠ 选中容器:
     *   仅当点击命中 cluster 的标题/标签 (title) 时才视为容器元素;
     *   否则 (点到大片空白背景) 继续上溯, 最终回落为空白 → 取消高亮。
     *   根因: ELK 渲染的 cluster 背景 rect 覆盖整个子域面积,
     *   用户点"画布空白"实际落到 cluster 背景 → 误选中容器 → 高亮一直不消失。
     */
    const findTargetFromEvent = (svg, target, ev = null) => {
      if (!target || target === svg) return {};
      let cur = target;
      // 上溯直到 svg 本身
      while (cur && cur !== svg) {
        if (cur.classList) {
          // 节点
          // [FIX 2026-08-02] 不再要求 data-code: 无 data-code 的节点 (label 正则匹配不上)
          //   之前会穿透到外层 cluster 造成"点节点高亮整个 cluster"的误判。
          //   现在直接识别为 node, 由 onSvgClick 用 label 文本兜底 targetId。
          if (cur.classList.contains('node')) {
            return { nodeEl: cur };
          }
          // 容器
          // [FIX 2026-08-01] 即使没有 data-container-code 也识别 cluster (mermaid 11 ELK 渲染时
          //   不是所有容器都带此 attribute, 比如无 annotation 数据时). 没 data-container-code 时
          //   用 cur.id 兜底 (id 形如 "G_D_供应链云").
          // [FIX 2026-08-01 v3] BUG FIX: 仅 <g class="cluster"> (单容器, 有 id, 用户视觉上可看到
          //   边框/标题/背景) 算 click 命中. 集合层 <g class="subgraphs"> 和 <g class="subgraph">
          // (复数和单数) 是 mermaid 11 ELK 的透明 wrapper, 不渲染, 但**bbox 覆盖整个图表**.
          //   用户在图表空白处点击时, e.target 落到这些 wrapper, findTargetFromEvent 上溯找到
          //   wrapper → 错误地触发 onCenterElement → 图表跳到第一个 cluster.
          //   修复: 只对真正的 cluster 触发, subgraphs/subgraph 视为空白 (clearHighlight 而非居中).
          // [FIX 2026-08-02 v2] 再收紧: cluster 必须命中标题/标签才算是容器 (见函数头注释).
          if (cur.classList.contains('cluster')) {
            if (isClusterLabelHit(cur, ev)) {
              return { containerEl: cur };
            }
            // 未命中标题 → 继续上溯 (嵌套场景可能命中外层容器标题, 否则最终回落为空白)
          }
          // 连线 label
          if (cur.classList.contains('edgeLabel')) {
            return { edgeLabelEl: cur };
          }
          // 连线 path
          if (cur.tagName && cur.tagName.toLowerCase() === 'path' && cur.parentElement) {
            // edgeLabel 内部有时也含 path, 跳过
            const pe = cur.parentElement
            if (!pe.classList.contains('edgeLabel')) {
              return { edgeEl: cur };
            }
          }
        }
        cur = cur.parentElement;
      }
      return {};
    };

    /**
     * [FIX 2026-08-02] 判断点击坐标是否命中 cluster 的标题/标签区域
     *   只有命中标题才认为用户"选中容器", 否则视为点空白 (背景 rect 不视为元素)。
     */
    const isClusterLabelHit = (cluster, ev) => {
      if (!ev || typeof ev.clientX !== 'number') return false
      const label = cluster.querySelector('.cluster-label, .cluster-title, text')
      if (!label) return false
      try {
        const r = label.getBoundingClientRect()
        if (!r || (r.width === 0 && r.height === 0)) return false
        const pad = 6  // 容差, 方便点击标题边缘
        return ev.clientX >= r.left - pad && ev.clientX <= r.right + pad &&
               ev.clientY >= r.top - pad && ev.clientY <= r.bottom + pad
      } catch (e) {
        return false
      }
    }

    /**
     * [FIX 2026-08-02] 取节点的显示文本 (nodeLabel), 作为无 data-code 时的 targetId 兜底
     */
    const getNodeLabelText = (nodeEl) => {
      if (!nodeEl) return ''
      const label = nodeEl.querySelector('.nodeLabel, text')
      return label ? (label.textContent || '').trim() : ''
    }

    /**
     * [FIX 2026-07-31] 从 edgeLabel DOM 找对应 relationCode
     *   mermaid 11 在 edgeLabel 内的 foreignObject > div 写入 label 文字, 但通常不含 code
     *   通过 addLinkCodeAttributes 设置的 data-relation-code 通常在 edgeLabel 同级的 edge 元素或 path 上
     */
    const findRelationCodeForLabel = (svg, labelOrPath) => {
      if (!labelOrPath) return null;
      // 直接找最近的 [data-relation-code]
      let cur = labelOrPath;
      while (cur && cur !== svg) {
        if (cur.hasAttribute && cur.hasAttribute('data-relation-code')) {
          return cur.getAttribute('data-relation-code');
        }
        cur = cur.parentElement;
      }
      // 退化: 找同 g.edge 下的 path
      const edge = labelOrPath.closest && labelOrPath.closest('g.edge');
      if (edge) {
        const path = edge.querySelector('path[data-relation-code], path.flowchart-link');
        if (path && path.hasAttribute('data-relation-code')) return path.getAttribute('data-relation-code');
      }
      return null;
    };
    addListener(svg, 'mousedown', onSvgMouseDown);
    addListener(svg, 'mousemove', onSvgMouseMove);
    addListener(svg, 'mouseup', onSvgMouseUp);
    // [FIX 2026-08-03] click 监听器从 svg 改为外层 .draggable-area 容器
    //   之前绑 svg 时, 点击 svg 外部 (背景可拖拽区域) 事件不冒泡到 svg, onSvgClick 不触发,
    //   点击空白背景无法 clearAllHighlights → 用户报告 "highlight 不取消".
    //   mousedown/mousemove/mouseup 仍绑 svg: isDraggingState 只关心 svg 内的拖动.
    //   容器链 fallback 兼容单测 (svg 无 .draggable-area 祖先时退回 svg 自身).
    const clickContainer = svg.closest('.draggable-area') || svg.closest('.mermaid-content') || svg;
    addListener(clickContainer, 'click', onSvgClick);

    // [FIX 2026-07-31 v4] edgeLabel 和 edge path 上 useTooltip 调用了 e.stopPropagation,
    //   阻止了 click 事件冒泡到 svg → onSvgClick 收不到
    //   解决: 直接在所有 edgeLabel 和 flowchart-link path 上绑 click listener
    //   内部调用同一份 onSvgClick 逻辑
    svg.querySelectorAll('.edgeLabel').forEach(label => {
      addListener(label, 'click', onSvgClick);
    });
    svg.querySelectorAll('path.flowchart-link').forEach(p => {
      addListener(p, 'click', onSvgClick);
    });
  };

  const highlightTargetElement = (svg, targetId, targetType, clickEdgeLabelEl = null, options = {}) => {
    // [FIX 2026-08-01 v4] 双向联动改造:
    //   之前这里调 clearAllHighlights(svg) 会清掉 panel 上所有 .annotation-item-selected,
    //   造成 "点 chart 上节点 → panel 选中消失" 的 UX bug (单向联动).
    //   改造: 不再 clear panel items; 仅清 SVG 高亮. panel 同步在末尾 setSelectedItems() 完成,
    //   这样能基于查找结果 panelMatched 做精准同步 (找不到时也能反映到 panel 清掉 selected).
    // [FIX 2026-08-01 v5] 加 options.syncPanel (默认 'forced'):
    //   - true / undefined → 'forced' 模式: 始终同步 panel (panel item 点击走这条)
    //   - 'auto' 模式: 仅当 panel 有对应 item 时同步, 否则保留原状 (chart 元素点击走这条)
    //   - false → 永远不同步 panel (极端 case, 保留接口)
    const syncPanel = options.syncPanel === undefined ? 'forced' : options.syncPanel
    clearSvgHighlightsOnly(svg);

    // [FIX 2026-08-01] 记录高亮查找 — 排查 "annotation 点了没反应" 类问题
    const tHL = diag.time('highlightTargetElement')

    let resultEl = null;

    if (targetType === 'relation') {
      // 关系连线：查找边组
      let edgeEl = svg.querySelector(`[data-relation-code="${targetId}"]`);

      if (!edgeEl) {
        svg.querySelectorAll('.edgeLabel').forEach(label => {
          if (edgeEl) return;
          const text = label.textContent || '';
          if (text.includes(targetId)) {
            edgeEl = label.closest('g');
          }
        });
      }

      // [FIX 2026-07-31 v3] 兜底: 如果 onSvgClick 传了 clickEdgeLabelEl, 直接高亮
      //   当 addLinkCodeAttributes 没设 data-relation-code 时 (ELK 自动 label 不可匹配),
      //   text.includes 失败, 但 clickEdgeLabelEl 是用户实际点击的元素, 直接用
      if (!edgeEl && clickEdgeLabelEl) {
        // [FIX v3.1] .edgeLabel 自身是 g, 直接用它. 它的 parent 才是真正的 edge g
        edgeEl = clickEdgeLabelEl.tagName && clickEdgeLabelEl.tagName.toLowerCase() === 'g'
          ? clickEdgeLabelEl
          : clickEdgeLabelEl.closest('g.edge') || clickEdgeLabelEl.closest('g');
      }

      if (edgeEl) {
        highlightElement(svg, edgeEl, 'relation', targetId);
        // [FIX 2026-07-31] 返回包含 path 和 label 的边组 (用于居中)
        resultEl = edgeEl.closest('g.edge') || edgeEl.closest('g[class*="edge"]') || edgeEl;
      }
    } else if (targetType === 'container') {
      // 容器备注：只选中容器
      let containerEl = svg.querySelector(`[data-container-code="${targetId}"]`);

      if (!containerEl) {
        const containers = svg.querySelectorAll('.subgraph, .cluster');
        containers.forEach(c => {
          if (containerEl) return;
          // [FIX 2026-08-01] 三级匹配:
          //   1) data-container-code 完全匹配 (走 querySelector 失败说明 attribute 缺失)
          //   2) c.id === targetId (mermaid 11 ELK 默认 ID 形如 G_D_供应链云, 我们已用 id 兜底)
          //   3) label textContent 包含 targetId (annotation 系统语义化名称)
          if (c.id === targetId) {
            containerEl = c;
            return;
          }
          const label = c.querySelector('.cluster-label, text');
          if (label && label.textContent.includes(targetId)) {
            containerEl = c;
          }
        });
      }

      if (containerEl) {
        highlightElement(svg, containerEl, 'container');
        resultEl = containerEl;
      }
    } else {
      // 节点备注：只选中节点
      let nodeEl = svg.querySelector(`[data-code="${targetId}"]`);

      if (!nodeEl) {
        const nodes = svg.querySelectorAll('.node');
        nodes.forEach(node => {
          if (nodeEl) return;
          const label = node.querySelector('.nodeLabel');
          if (label && label.textContent.includes(targetId)) {
            nodeEl = node;
          }
        });
      }

      if (nodeEl) {
        highlightElement(svg, nodeEl, 'node');
        resultEl = nodeEl;
      }
    }

    // [FOCUS 2026-08-06] 跨类型兜底: 布局树点击时调用方不知道目标渲染为 container 还是 node
    //   (领域/子领域/服务模块通常渲染为 subgraph=container, 但折叠/上提后会变单节点;
    //    服务模块图下服务模块也可能渲染为 g.node)。请求类型找不到时, 尝试另一类型的匹配,
    //   使"只有业务对象高亮、领域/子领域/服务模块无效"的问题得到兜底。
    if (!resultEl) {
      if (targetType === 'container') {
        let nodeEl = svg.querySelector(`[data-code="${targetId}"]`);
        if (!nodeEl) {
          svg.querySelectorAll('.node').forEach(node => {
            if (nodeEl) return;
            const label = node.querySelector('.nodeLabel');
            if (label && label.textContent.includes(targetId)) nodeEl = node;
          });
        }
        if (nodeEl) {
          highlightElement(svg, nodeEl, 'node');
          resultEl = nodeEl;
        }
      } else if (targetType === 'node') {
        let containerEl = svg.querySelector(`[data-container-code="${targetId}"]`);
        if (!containerEl) {
          svg.querySelectorAll('.subgraph, .cluster').forEach(c => {
            if (containerEl) return;
            if (c.id === targetId) { containerEl = c; return; }
            const label = c.querySelector('.cluster-label, text');
            if (label && label.textContent.includes(targetId)) containerEl = c;
          });
        }
        if (containerEl) {
          highlightElement(svg, containerEl, 'container');
          resultEl = containerEl;
        }
      }
    }
    // [FIX 2026-08-01 v4] 同时记录 panel sync 结果 (双向联动): 同步了多少 panel items
    // [FIX 2026-08-01 v5] syncPanel 决策:
    //   - 'forced' (默认): 始终同步 panel (panel item 点击走这条)
    //   - false: 始终不同步 (保留接口)
    //   - 'auto': 仅当 panel 有对应 item 时同步, 否则保留原状 (chart 元素点击走这条)
    let panelSync = { matched: 0, mode: 'skipped' }
    if (syncPanel === 'forced') {
      panelSync = setSelectedItems(svg, targetId, targetType)
      panelSync.mode = 'forced'
    } else if (syncPanel === 'auto') {
      if (hasPanelItemsFor(svg, targetId)) {
        panelSync = setSelectedItems(svg, targetId, targetType)
        panelSync.mode = 'auto-matched'
      } else {
        panelSync.mode = 'auto-preserved'  // 保留原 panel selected 不动
      }
    }
    diag.recordStepMeta('highlightTargetElement', {
      targetId, targetType,
      found: !!resultEl,
      resultTag: resultEl?.tagName || null,
      resultKlass: (resultEl && resultEl.getAttribute && resultEl.getAttribute('class')) || '',
      panelMatched: panelSync.matched,
      panelMode: panelSync.mode
    })
    diag.endStep('highlightTargetElement', tHL)
    return resultEl;
  };

  const highlightElement = (svg, el, targetType, targetId) => {
    el.classList.add('annotation-highlighted');

    if (targetType === 'node') {
      // 节点：使用 filter 高亮
      const rect = el.querySelector('rect, polygon');
      if (rect) {
        rect.style.filter = 'drop-shadow(0 0 12px rgba(255, 80, 80, 0.9))';
      }
      const label = el.querySelector('.nodeLabel, text');
      if (label) {
        label.style.fontWeight = 'bold';
        label.style.fontSize = '18px';
        label.style.fill = '#ff4444';
      }
    } else if (targetType === 'container') {
      // 容器：使用 filter 高亮
      const rect = el.querySelector('rect');
      if (rect) {
        rect.style.filter = 'drop-shadow(0 0 12px rgba(255, 80, 80, 0.9))';
      }
      const label = el.querySelector('.cluster-label, text');
      if (label) {
        label.style.fontWeight = 'bold';
        label.style.fontSize = '16px';
        label.style.fill = '#ff4444';
      }
    } else if (targetType === 'relation') {
      // [P0-C 2026-08-03] 消除 edgeLabel.click() 副作用 — 直接高亮 edge path
      //   之前: edgeLabel.click() 间接触发 useTooltip.setupLabelEvents.onClick 给 path 加
      //         strokeWidth=4px+filter, 但同时 (1) useTooltip 给 source/target node rect 加
      //         #FF6B6B stroke — annotationOverlay 无 relation.source/target 数据, 视觉混乱;
      //         (2) .click() 还会触发其他监听器 (e.g. annotationOverlay 自己的 onSvgClick 200ms 锁).
      //   现在: 直接给 edge group 内的 path 加 strokeWidth=4px+filter (与 useTooltip 视觉一致),
      //         放弃 source/target node 高亮 (用户直接点 edge 时 useTooltip.onClick 仍触发, 自己高亮).
      //   残留清理: clearSvgHighlightsOnly 不清 useTooltip 给 source/target node rect 设的 stroke
      //         (不在 .annotation-highlighted 子树), 这里手动清, 防止切换 highlight 时旧样式残留.
      svg.querySelectorAll('.node rect, .node polygon').forEach(r => {
        r.style.removeProperty('stroke');
        r.style.strokeWidth = '2px';
        r.style.removeProperty('filter');
      });
      // 找 edge group 内的 path: 优先 flowchart-link / [data-relation-code], 兜底任意 path.
      //   el 可能是 g.edge / g.edgeLabel / 任意 g, 多级 fallback 提高鲁棒性.
      let edgePath = el.querySelector('path.flowchart-link, path[data-relation-code]')
        || el.querySelector('path.edge-path')
        || el.querySelector('path');
      if (!edgePath) {
        // el 可能不是 g.edge (e.g. edgeLabel 的父 g), 找最近的 g.edge 内的 path
        const edgeGroup = el.closest('g.edge')
          || (el.parentElement && el.parentElement.closest('g.edge'));
        if (edgeGroup) {
          edgePath = edgeGroup.querySelector('path.flowchart-link, path[data-relation-code]')
            || edgeGroup.querySelector('path');
        }
      }
      if (edgePath) {
        edgePath.style.strokeWidth = '4px';
        edgePath.style.filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))';
        diag.recordStepMeta('annoOverlayHighlightRelation', {
          targetId, found: true, pathTag: edgePath.tagName,
          hasRelationCode: !!edgePath.getAttribute('data-relation-code')
        });
      } else {
        diag.recordStepMeta('annoOverlayHighlightRelation', {
          targetId, found: false, elTag: el.tagName,
          elClass: el.getAttribute('class') || ''
        });
      }
    } else {
      // 默认发光效果
      const rect = el.querySelector('rect');
      if (rect) {
        rect.style.filter = 'drop-shadow(0 0 8px rgba(0, 102, 204, 0.8))';
      }
      const path = el.querySelector('path');
      if (path) {
        path.style.filter = 'drop-shadow(0 0 6px rgba(0, 102, 204, 0.8))';
      }
    }
  };

  const hoverTargetElement = (svg, targetId, isHover) => {
    let targetEl = svg.querySelector(`[data-code="${targetId}"]`) ||
                   svg.querySelector(`[data-container-code="${targetId}"]`) ||
                   svg.querySelector(`[data-relation-code="${targetId}"]`);

    if (targetEl) {
      if (isHover) {
        targetEl.classList.add('annotation-hovered');
      } else {
        targetEl.classList.remove('annotation-hovered');
      }
    }
  };

  const clearAllHighlights = (svg) => {
    clearSvgHighlightsOnly(svg);

    const container = svg.closest('.mermaid-container');
    if (container) {
      // [FIX 2026-08-01 v4] 双向联动: 同时清 panel items. 仅在 "用户明确取消选中" 场景调用
      //   (点 svg 空白处 / hover 离开等). 高亮切换 (highlightTargetElement) 改用 setSelectedItems.
      container.querySelectorAll('.annotation-item-selected').forEach(item => {
        item.classList.remove('annotation-item-selected');
        item.style.background = 'transparent';
      });
    }
  };

  /**
   * [FIX 2026-08-01 v4] 只清 SVG 上的高亮 (filter / style / class), **不**动 panel items.
   * 用于 highlightTargetElement 内部 — 切到新目标时, 让旧目标先"取消高亮"但 panel 的选中视觉不动.
   */
  const clearSvgHighlightsOnly = (svg) => {
    svg.querySelectorAll('.annotation-highlighted').forEach(el => {
      el.classList.remove('annotation-highlighted');
      const rect = el.querySelector('rect, polygon');
      if (rect) {
        rect.style.removeProperty('filter');
      }
      el.querySelectorAll('path').forEach(path => {
        path.style.removeProperty('filter');
        path.style.strokeWidth = '2px';
      });
      const label = el.querySelector('.edgeLabel, .nodeLabel, .cluster-label, text');
      if (label) {
        label.style.removeProperty('filter');
        label.style.removeProperty('font-weight');
        label.style.removeProperty('font-size');
        label.style.removeProperty('fill');
      }
    });

    svg.querySelectorAll('.annotation-hovered').forEach(el => {
      el.classList.remove('annotation-hovered');
    });

    // 清除所有连线的 useTooltip.js 高亮样式
    svg.querySelectorAll('path').forEach(path => {
      path.style.removeProperty('filter');
      path.style.strokeWidth = '2px';
    });
  };

  /**
   * [FIX 2026-08-01 v4] 同步 panel 选中态到指定 target.
   * 行为: 清掉所有 .annotation-item-selected, 给 data-target-id 匹配的 items 加 selected (可多个,
   *   表示 "同一个 target 上有多条备注", 类似 VSCode 的 occurrences).
   *   - 找不到任何匹配 → 全部 selected 都被清掉 (行为同 clearAllHighlights, 表示 "没对应 item").
   *
   * @param {string|null} targetId - null = 全部清掉
   * @param {string} targetType - 保留参数便于未来按 type 过滤
   */
  const setSelectedItems = (svg, targetId, targetType) => {
    const container = svg.closest('.mermaid-container');
    if (!container) return { matched: 0 }
    // 先清所有 selected
    container.querySelectorAll('.annotation-item-selected').forEach(item => {
      item.classList.remove('annotation-item-selected')
      item.style.background = 'transparent'
    })
    // 再给匹配的加上
    if (!targetId) return { matched: 0 }
    const selector = `.annotation-item[data-target-id="${targetId}"]`
    const matched = container.querySelectorAll(selector)
    matched.forEach(item => {
      item.classList.add('annotation-item-selected')
      item.style.background = 'rgba(0, 0, 0, 0.05)'
    })
    return { matched: matched.length, targetId, targetType }
  };

  /**
   * [FIX 2026-08-01 v5] 仅查询 panel items 是否有匹配的 targetId — 不修改 DOM.
   * 用于 onSvgClick 中判断"chart 元素有无对应 panel item", 决定:
   *   - 有对应 → 调 setSelectedItems (panel 同步到该 item)
   *   - 无对应 → 保留 panel 原状 (用户已选的备注还在那里)
   */
  const hasPanelItemsFor = (svg, targetId) => {
    if (!targetId) return false
    const container = svg.closest('.mermaid-container')
    if (!container) return false
    return container.querySelectorAll(
      `.annotation-item[data-target-id="${targetId}"]`
    ).length > 0
  };

  const highlightByNumber = (svg, number) => {
  };

  const clearHighlight = (svg) => {
  };

  /**
   * [FOCUS 2026-08-05] 聚焦目标元素 (布局设置面板联动)
   * 复用 highlightTargetElement 的查找 + 高亮逻辑, 返回命中的 DOM 元素供调用方居中。
   * syncPanel 使用 'forced' 对齐"备注面板选中"行为 (与 annotation item 点击一致)。
   * @returns {Element|null} 命中的图表元素 (供 centerElement 使用)
   */
  const focusOnTarget = (svg, targetId, targetType) => {
    if (!svg || !targetId || !targetType) return null
    return highlightTargetElement(svg, targetId, targetType, null, { syncPanel: 'forced' })
  };

  const removeAnnotationLayers = (svg) => {
    // 关键：先清理事件监听器（panel header + svg 全局 + annotation-item）
    // 必须在删除 DOM 节点之前清理，否则 removeEventListener 无法匹配（节点引用变化）
    cleanupListeners()

    svg.querySelectorAll('[data-annotation-layer]').forEach(el => {
      el.remove();
    });
    const container = svg.closest('.mermaid-container');
    if (container) {
      const oldPanel = container.querySelector('.annotation-dock-panel');
      if (oldPanel) {
        oldPanel.remove();
      }
    }
  };

  // [LEGEND 2026-08-07] 图例点击隐藏的持久化状态（模块级，重渲染后仍保持用户选择）
  let legendDismissed = false;

  const overlayColorLegend = (svg, colorLegendData, options = {}) => {
    const {
      position = 'top-right',
      // [LEGEND 2026-08-07] 分组可见性切换回调 (由 MermaidComponent 注入):
      //   就地改 live 分组对象 visible + 以新引用替换 store 配置, 触发图表增量隐/显 + 配置树双向同步。
      //   缺省时 (如 HTML/PDF 导出, 无 store 上下文) 退化为直接就地改 visible (仅作用于当前图例引用)。
      onToggleGroupVisible = null
    } = options;

    const container = svg.closest('.mermaid-container');
    if (!container) return null;

    let existingLegend = container.querySelector('.color-legend-panel');
    if (existingLegend) {
      existingLegend.remove();
    }

    if (!colorLegendData || colorLegendData.length === 0) return null;

    const legend = document.createElement('div');
    legend.className = 'color-legend-panel';
    legend.setAttribute('data-annotation-layer', 'legend');

    const positionStyles = {
      'top-right': `
        position: absolute;
        top: 10px;
        right: 10px;
      `,
      'top-left': `
        position: absolute;
        top: 10px;
        left: 10px;
      `,
      'bottom-right': `
        position: absolute;
        bottom: 130px;
        right: 10px;
      `,
      'bottom-left': `
        position: absolute;
        bottom: 130px;
        left: 10px;
      `
    };

    legend.style.cssText = `
      ${positionStyles[position] || positionStyles['top-left']}
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 8px 12px;
      z-index: 99;
      font-family: Arial, sans-serif;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      max-width: 200px;
      /* 不限制高度，避免图例项多时出现滚动条 */
    `;

    // [LEGEND 2026-08-07] 图例支持点击隐藏：标题栏右侧提供关闭按钮(×)。
    //   关闭后隐藏面板并在原位显示一个"图例"小按钮，点击可重新唤出。
    const showToggleChip = () => {
      if (container.querySelector('.color-legend-toggle')) return;
      const chip = document.createElement('div');
      chip.className = 'color-legend-toggle';
      chip.setAttribute('data-annotation-layer', 'legend');
      chip.style.cssText = `
        ${positionStyles[position] || positionStyles['top-left']}
        background: rgba(255,255,255,0.95);
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 4px 10px;
        font-size: 11px;
        color: #666;
        cursor: pointer;
        z-index: 99;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      `;
      chip.textContent = '图例';
      chip.title = '显示图例';
      chip.addEventListener('click', () => {
        legendDismissed = false;
        legend.style.display = '';
        chip.remove();
      });
      container.appendChild(chip);
    };
    const hideLegend = () => {
      legendDismissed = true;
      legend.style.display = 'none';
      showToggleChip();
    };

    const title = document.createElement('div');
    title.style.cssText = `
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: bold;
      font-size: 11px;
      color: #666;
      margin-bottom: 6px;
      border-bottom: 1px solid #eee;
      padding-bottom: 4px;
    `;
    const titleText = document.createElement('span');
    titleText.textContent = '图例';
    title.appendChild(titleText);

    const closeBtn = document.createElement('span');
    closeBtn.textContent = '×';
    closeBtn.title = '隐藏图例';
    closeBtn.style.cssText = `
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
      padding: 0 2px;
      color: #999;
      user-select: none;
    `;
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      hideLegend();
    });
    title.appendChild(closeBtn);
    legend.appendChild(title);

    const legendList = document.createElement('div');
    legendList.style.cssText = `
      display: flex;
      flex-direction: column;
      gap: 4px;
    `;

    // [LEGEND 2026-08-07] 点击图例项(领域/子领域/服务模块等按颜色分组)切换对应分组的 visible,
    //   与图表配置树双向同步:
    //   - 分组对象引用来自 layoutControlConfig.groups (共享响应式对象)
    //   - 通过 onToggleGroupVisible 回调 (MermaidComponent 注入) 深克隆 store 配置 + 改 visible
    //     后以新引用替换, 触发 updateVisibilityOnly() 增量隐/显 (不重排布局); LayoutControlPanel 面板树同步高亮
    //   - 图例项自身维护 hidden 状态 (不依赖 store 对象身份, store 替换后原 group 引用会失效)
    const setGroupVisible = (g, hidden) => {
      // hidden=true 表示"隐藏", 故设置 visible = !hidden
      g.visible = !hidden;
      if (Array.isArray(g.children)) g.children.forEach(ch => setGroupVisible(ch, hidden));
      if (Array.isArray(g.containers)) g.containers.forEach(c => {
        if (c && typeof c === 'object') c.visible = !hidden;
      });
    };
    const setItemHiddenVisual = (el, span, hidden) => {
      el.style.opacity = hidden ? '0.4' : '';
      el.style.background = hidden ? 'rgba(0,0,0,0.04)' : '';
      span.style.textDecoration = hidden ? 'line-through' : '';
      span.title = hidden ? '点击显示该分组' : '点击隐藏该分组';
    };

    colorLegendData.forEach((item, index) => {
      const legendItem = document.createElement('div');
      legendItem.style.cssText = `
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 10px;
        color: #555;
        ${item.isCenter ? 'font-weight: bold; background: rgba(0,0,0,0.03); border-radius: 2px; padding: 2px 4px; margin: -2px -4px;' : ''}
      `;

      // 使用SVG确保打印时颜色正确显示
      const colorDot = document.createElement('span');
      colorDot.style.cssText = `
        width: 12px;
        height: 12px;
        flex-shrink: 0;
        display: inline-block;
      `;
      // [FIX 2026-08-02 v6] 中心范围图例项改为实心色块 (v5 起中心节点就是指定颜色 fill,
      //   不再有"分组色 + 虚线边框"方案, 图例保持纯色块与其他项一致)
      colorDot.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 12 12" xmlns="http://www.w3.org/2000/svg">
          <rect x="0" y="0" width="12" height="12" rx="2" fill="${item.color}" stroke="rgba(0,0,0,0.2)" stroke-width="0.5"/>
        </svg>
      `;

      const nameSpan = document.createElement('span');
      nameSpan.style.cssText = `
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      `;
      nameSpan.textContent = item.name;
      nameSpan.title = item.name;

      legendItem.appendChild(colorDot);
      legendItem.appendChild(nameSpan);
      legendList.appendChild(legendItem);

      // [LEGEND 2026-08-07] 可点击分组项: 匹配到分组引用的图例项可点击切换 visible
      const clickable = !item.isCenter && Array.isArray(item.groups) && item.groups.length > 0;
      if (clickable) {
        legendItem.style.cursor = 'pointer';
        // 图例项自身的 hidden 状态 (初始化时读取当前 group.visible, 兼容配置树侧已隐藏)
        let hidden = item.groups.some(g => g.visible === false);
        const applyVisual = () => setItemHiddenVisual(legendItem, nameSpan, hidden);
        legendItem.addEventListener('click', (e) => {
          e.stopPropagation();
          hidden = !hidden;
          if (typeof onToggleGroupVisible === 'function') {
            onToggleGroupVisible(item.name, hidden, item.groups);
          } else {
            // 无回调 (如 HTML/PDF 导出) 时直接就地改 visible
            item.groups.forEach(g => setGroupVisible(g, hidden));
          }
          applyVisual();
        });
        applyVisual();
      }

      // 在中心范围项后添加分隔线
      if (item.isCenter && index < colorLegendData.length - 1) {
        const separator = document.createElement('div');
        separator.style.cssText = `
          height: 1px;
          background: #eee;
          margin: 4px 0;
        `;
        legendList.appendChild(separator);
      }
    });

    legend.appendChild(legendList);
    container.appendChild(legend);
    // [LEGEND 2026-08-07] 若此前已点击隐藏，重渲染后保持隐藏并显示"图例"唤出按钮
    if (legendDismissed) {
      legend.style.display = 'none';
      showToggleChip();
    }
    return legend;
  };

  return {
    overlayNumberMarkers,
    overlayAnnotationPanel,
    overlayColorLegend,
    bindAnnotationInteraction,
    highlightByNumber,
    clearHighlight,
    clearSvgHighlightsOnly,
    focusOnTarget,
    removeAnnotationLayers
  };
}
