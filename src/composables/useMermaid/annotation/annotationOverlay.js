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
    console.log('overlayNumberMarkers called - no markers to render');
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
    console.log('calculateNumberPosition', { bbox, position });
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

  const overlayAnnotationPanel = (svg, annotations, options = {}) => {
    const {
      position = PANEL_POSITION.BOTTOM,
      showIcons = false
    } = options;

    const container = svg.closest('.mermaid-container');
    if (!container) return null;

    let existingPanel = container.querySelector('.annotation-dock-panel');
    if (existingPanel) {
      existingPanel.remove();
    }

    const panel = document.createElement('div');
    panel.className = 'annotation-dock-panel';
    panel.setAttribute('data-annotation-layer', 'panel');
    panel.style.cssText = `
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      max-height: 120px;
      background: rgba(248, 248, 248, 0.98);
      border-top: 1px solid #eee;
      padding: 4px 12px;
      box-sizing: border-box;
      overflow-y: auto;
      z-index: 100;
      font-family: Arial, sans-serif;
      display: flex;
      align-items: flex-start;
      gap: 8px;
    `;

    const header = document.createElement('div');
    header.className = 'annotation-header';
    header.textContent = '备注 ▼';
    header.style.cssText = `
      font-weight: bold;
      font-size: 11px;
      color: #999;
      white-space: nowrap;
      flex-shrink: 0;
      cursor: pointer;
      user-select: none;
    `;
    header.title = '点击隐藏/显示备注';
    panel.appendChild(header);

    const list = document.createElement('div');
    list.className = 'annotation-list';
    list.style.cssText = `
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      flex: 1;
    `;

    header.addEventListener('click', () => {
      if (list.style.display === 'none') {
        list.style.display = 'flex';
        header.textContent = '备注 ▼';
        panel.style.maxHeight = '120px';
        panel.style.padding = '4px 12px';
      } else {
        list.style.display = 'none';
        header.textContent = '备注 ▶';
        panel.style.maxHeight = '20px';
        panel.style.padding = '4px 12px 4px 12px';
      }
    });

    annotations.forEach(ann => {
      const categoryConfig = getCategoryConfig(ann.category);
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
      item.title = ann.content;

      const titleSpan = document.createElement('span');
      titleSpan.style.cssText = `
        font-weight: bold;
        font-size: 11px;
        color: #666;
        margin-right: 4px;
        white-space: nowrap;
      `;

      const nameText = ann.targetName;
      const codeText = ann.targetId;
      titleSpan.textContent = `${nameText} ${codeText}`;

      const separator = document.createElement('span');
      separator.textContent = ':';
      separator.style.cssText = `
        color: #bbb;
        margin-right: 4px;
      `;

      const contentSpan = document.createElement('span');
      contentSpan.className = 'annotation-content';
      contentSpan.style.cssText = `
        color: #888;
        font-size: 11px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 180px;
      `;

      if (showIcons && categoryConfig.icon) {
        contentSpan.textContent = `${categoryConfig.icon} ${ann.content}`;
      } else {
        contentSpan.textContent = ann.content;
      }

      item.appendChild(titleSpan);
      item.appendChild(separator);
      item.appendChild(contentSpan);
      list.appendChild(item);
    });

    panel.appendChild(list);
    container.appendChild(panel);

    return panel;
  };

  const bindAnnotationInteraction = (svg, annotations) => {
    const container = svg.closest('.mermaid-container');
    if (!container) return;

    const annotationMap = new Map();
    annotations.forEach(ann => {
      annotationMap.set(ann.targetId, ann);
    });

    container.querySelectorAll('.annotation-item').forEach(item => {
      item.addEventListener('click', () => {
        const targetId = item.getAttribute('data-target-id');
        const ann = annotationMap.get(targetId);
        const targetType = ann ? ann.targetType : null;
        if (targetId && targetType) {
          highlightTargetElement(svg, targetId, targetType);
          item.classList.add('annotation-item-selected');
          item.style.background = 'rgba(0, 0, 0, 0.05)';
        }
      });

      item.addEventListener('mouseenter', () => {
        const targetId = item.getAttribute('data-target-id');
        if (targetId) {
          hoverTargetElement(svg, targetId, true);
        }
      });

      item.addEventListener('mouseleave', () => {
        const targetId = item.getAttribute('data-target-id');
        if (targetId) {
          hoverTargetElement(svg, targetId, false);
        }
      });
    });

    svg.addEventListener('mousedown', () => {
      isDraggingState = false;
    });

    svg.addEventListener('mousemove', (e) => {
      if (e.buttons > 0) {
        isDraggingState = true;
      }
    });

    svg.addEventListener('mouseup', () => {
      setTimeout(() => {
        isDraggingState = false;
      }, 100);
    });

    svg.addEventListener('click', (e) => {
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
    });
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

  return {
    overlayNumberMarkers,
    overlayAnnotationPanel,
    bindAnnotationInteraction,
    highlightByNumber,
    clearHighlight,
    removeAnnotationLayers
  };
}
