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

export function useAnnotationOverlay() {

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
    // [FIX 2026-06-29 v7] 用原生 addEventListener (避开 addListener 包装的 _cleanupFns 时序问题)
    header.addEventListener('click', onHeaderClick)
    _cleanupFns.push(() => header.removeEventListener('click', onHeaderClick))

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

  const bindAnnotationInteraction = (svg, annotations) => {
    // 先清理本实例上一次的监听器（panel header + svg 全局）
    cleanupListeners()

    const container = svg.closest('.mermaid-container');
    if (!container) return;

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
          highlightTargetElement(svg, targetId, targetType);
          item.classList.add('annotation-item-selected');
          item.style.background = 'rgba(0, 0, 0, 0.05)';
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
      // 排除拖拽操作触发的点击
      if (!isDraggingState) {
        if (e.target === svg || e.target.closest('.annotation-dock-panel') === null) {
          // 检查点击目标是否是备注相关元素
          const isAnnotationItem = e.target.closest('.annotation-item');
          const isHighlighted = e.target.closest('.annotation-highlighted');
          const isAnnotationOverlay = e.target.closest('.annotation-overlay');

          if (!isAnnotationItem && !isHighlighted && !isAnnotationOverlay) {
            clearAllHighlights(svg);
          }
        }
      }
    };
    addListener(svg, 'mousedown', onSvgMouseDown);
    addListener(svg, 'mousemove', onSvgMouseMove);
    addListener(svg, 'mouseup', onSvgMouseUp);
    addListener(svg, 'click', onSvgClick);
  };

  const highlightTargetElement = (svg, targetId, targetType) => {
    clearAllHighlights(svg);

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

      if (edgeEl) {
        highlightElement(svg, edgeEl, 'relation', targetId);
      }
    } else if (targetType === 'container') {
      // 容器备注：只选中容器
      let containerEl = svg.querySelector(`[data-container-code="${targetId}"]`);

      if (!containerEl) {
        const containers = svg.querySelectorAll('.subgraph, .cluster');
        containers.forEach(c => {
          if (containerEl) return;
          const label = c.querySelector('.cluster-label, text');
          if (label && label.textContent.includes(targetId)) {
            containerEl = c;
          }
        });
      }

      if (containerEl) {
        highlightElement(svg, containerEl, 'container');
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
      }
    }
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
      // 关系连线：先清除 useTooltip.js 的高亮，再触发点击
      // 清除之前的连线高亮样式
      svg.querySelectorAll('path').forEach(path => {
        path.style.removeProperty('filter');
        path.style.strokeWidth = '2px';
      });
      const edgeLabel = el.querySelector('.edgeLabel') || el;
      if (edgeLabel && typeof edgeLabel.click === 'function') {
        edgeLabel.click();
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

    const container = svg.closest('.mermaid-container');
    if (container) {
      container.querySelectorAll('.annotation-item-selected').forEach(item => {
        item.classList.remove('annotation-item-selected');
        item.style.background = 'transparent';
      });
    }
  };

  const highlightByNumber = (svg, number) => {
  };

  const clearHighlight = (svg) => {
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

  const overlayColorLegend = (svg, colorLegendData, options = {}) => {
    const {
      position = 'top-right'
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

    const title = document.createElement('div');
    title.style.cssText = `
      font-weight: bold;
      font-size: 11px;
      color: #666;
      margin-bottom: 6px;
      border-bottom: 1px solid #eee;
      padding-bottom: 4px;
    `;
    title.textContent = '图例';
    legend.appendChild(title);

    const legendList = document.createElement('div');
    legendList.style.cssText = `
      display: flex;
      flex-direction: column;
      gap: 4px;
    `;

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
    return legend;
  };

  return {
    overlayNumberMarkers,
    overlayAnnotationPanel,
    overlayColorLegend,
    bindAnnotationInteraction,
    highlightByNumber,
    clearHighlight,
    removeAnnotationLayers
  };
}
