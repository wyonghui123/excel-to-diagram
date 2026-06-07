/**
 * 备注功能核心逻辑
 */
import { ref, computed } from 'vue';
import { 
  CATEGORY_CONFIG, 
  TYPE_CONFIG, 
  PANEL_POSITION, 
  DEFAULT_CATEGORY,
  getCategoryConfig,
  getTypeConfig,
  toCircleNumber 
} from './annotationConfig.js';

export function useAnnotation() {
  const annotations = ref([]);
  const annotationConfig = ref({
    panelPosition: PANEL_POSITION.BOTTOM,
    showIcons: false
  });

  const annotationCount = computed(() => {
    return annotations.value.length;
  });

  const shouldSuggestBottomPosition = computed(() => {
    return annotationCount.value >= 5;
  });

  const parseAnnotationsFromData = (data, diagramType) => {
    const result = [];
    let number = 1;

    if (diagramType === 'serviceModule' && data.containers) {
      const nodeMap = new Map();
      data.nodes?.forEach(node => nodeMap.set(node.id, node));

      data.containers.forEach(container => {
        if (container.annotationContent) {
          result.push({
            id: `ANN${String(number).padStart(3, '0')}`,
            number: number++,
            targetType: 'container',
            targetId: container.id,
            targetName: container.fullTitle || container.name || container.id,
            category: container.annotationCategory || DEFAULT_CATEGORY,
            content: container.annotationContent
          });
        }
        if (container.nodes) {
          container.nodes.forEach(nodeItem => {
            const nodeId = typeof nodeItem === 'string' ? nodeItem : (nodeItem.id || nodeItem.code);
            const nodeData = nodeMap.get(nodeId);
            if (nodeData?.annotationContent) {
              result.push({
                id: `ANN${String(number).padStart(3, '0')}`,
                number: number++,
                targetType: 'node',
                targetId: nodeId,
                targetName: nodeData.name,
                category: nodeData.annotationCategory || DEFAULT_CATEGORY,
                content: nodeData.annotationContent
              });
            }
          });
        }
      });
    } else if (diagramType === 'businessObject' && data.nodes) {
      // 处理服务模块（容器）备注
      if (data.serviceModules) {
        data.serviceModules.forEach(sm => {
          if (sm.annotationContent) {
            result.push({
              id: `ANN${String(number).padStart(3, '0')}`,
              number: number++,
              targetType: 'container',
              targetId: sm.code,
              targetName: sm.name,
              category: sm.annotationCategory || DEFAULT_CATEGORY,
              content: sm.annotationContent
            });
          }
        });
      }
      
      // 处理业务对象（节点）备注
      data.nodes.forEach(node => {
        if (node.annotationContent) {
          result.push({
            id: `ANN${String(number).padStart(3, '0')}`,
            number: number++,
            targetType: 'node',
            targetId: node.code || node.id || node.name,
            targetName: node.name || node.originalName,
            category: node.annotationCategory || DEFAULT_CATEGORY,
            content: node.annotationContent
          });
        }
      });
    }

    if (data.links) {
      data.links.forEach(link => {
        if (link.annotationContent) {
          result.push({
            id: `ANN${String(number).padStart(3, '0')}`,
            number: number++,
            targetType: 'relation',
            targetId: link.relationCode || `${link.source}-${link.target}`,
            targetName: `${link.label || link.relationDesc || ''}`,
            sourceBOName: link.sourceName || link.source || '',
            targetBOName: link.targetName || link.target || '',
            category: link.annotationCategory || DEFAULT_CATEGORY,
            content: link.annotationContent
          });
        }
      });
    }

    annotations.value = result;
    return result;
  };

  const buildNumberMap = (annotationList) => {
    const map = new Map();
    annotationList.forEach(ann => {
      const typeConfig = getTypeConfig(ann.targetType);
      const categoryConfig = getCategoryConfig(ann.category);
      const entry = {
        number: ann.number,
        displayNumber: toCircleNumber(ann.number),
        targetType: ann.targetType,
        targetId: ann.targetId,
        targetName: ann.targetName,
        bg: typeConfig.bg,
        border: typeConfig.border,
        position: typeConfig.position,
        categoryBg: categoryConfig.bg,
        categoryBorder: categoryConfig.border,
        label: categoryConfig.label
      };
      map.set(ann.id, entry);
    });
    return map;
  };

  const setConfig = (config) => {
    if (config.panelPosition) {
      annotationConfig.value.panelPosition = config.panelPosition;
    }
    if (typeof config.showIcons === 'boolean') {
      annotationConfig.value.showIcons = config.showIcons;
    }
  };

  return {
    annotations,
    annotationConfig,
    annotationCount,
    shouldSuggestBottomPosition,
    parseAnnotationsFromData,
    buildNumberMap,
    setConfig,
    getCategoryConfig,
    getTypeConfig,
    toCircleNumber
  };
}
