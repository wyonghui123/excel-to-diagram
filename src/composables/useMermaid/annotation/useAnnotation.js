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

  const parseAnnotationsFromData = (data, diagramType, options = {}) => {
    // [V_NEW 2026-06-29] annotation category 过滤
    // 主线不受影响: filter 为空/undefined = 不过滤 (向后兼容)
    const { filter = [] } = options;
    const result = [];
    let number = 1;

    // [FIX 2026-06-29] 辅助函数 - 从 annotation 数组生成 annotation entries
    // 后端返回 annotationContents (数组) + annotationCategories (数组)
    // 每个 target 可能有多条 annotation, 每条生成一个 entry
    function pushAnnotation(targetType, targetId, targetName, contents, categories, extra = {}) {
      if (!Array.isArray(contents) || contents.length === 0) return
      contents.forEach((content, idx) => {
        if (!content) return  // 跳过空内容
        const category = (Array.isArray(categories) && categories[idx]) || DEFAULT_CATEGORY
        result.push({
          id: `ANN${String(number).padStart(3, '0')}`,
          number: number++,
          targetType,
          targetId,
          targetName,
          category,
          content,
          ...extra
        })
      })
    }

    if (diagramType === 'serviceModule' && data.containers) {
      const nodeMap = new Map();
      data.nodes?.forEach(node => nodeMap.set(node.id, node));

      data.containers.forEach(container => {
        pushAnnotation(
          'container',
          container.id,
          container.fullTitle || container.name || container.id,
          container.annotationContents,
          container.annotationCategories
        )
        if (container.nodes) {
          container.nodes.forEach(nodeItem => {
            const nodeId = typeof nodeItem === 'string' ? nodeItem : (nodeItem.id || nodeItem.code);
            const nodeData = nodeMap.get(nodeId);
            if (nodeData) {
              pushAnnotation(
                'node',
                nodeId,
                nodeData.name,
                nodeData.annotationContents,
                nodeData.annotationCategories
              )
            }
          });
        }
      });
    } else if (diagramType === 'businessObject' && data.nodes) {
      // 处理服务模块（容器）备注
      if (data.serviceModules) {
        data.serviceModules.forEach(sm => {
          pushAnnotation(
            'container',
            sm.code,
            sm.name,
            sm.annotationContents,
            sm.annotationCategories
          )
        });
      }

      // 处理业务对象（节点）备注
      data.nodes.forEach(node => {
        pushAnnotation(
          'node',
          node.code || node.id || node.name,
          node.name || node.originalName,
          node.annotationContents,
          node.annotationCategories
        )
      });
    }

    if (data.links) {
      data.links.forEach(link => {
        pushAnnotation(
          'relation',
          link.relationCode || `${link.source}-${link.target}`,
          `${link.label || link.relationDesc || ''}`,
          link.annotationContents,
          link.annotationCategories,
          {
            sourceBOName: link.sourceName || link.source || '',
            targetBOName: link.targetName || link.target || ''
          }
        )
      });
    }

    // [V_NEW 2026-06-29] 应用 category 过滤
    //   filter = [] => 不过滤 (向后兼容)
    //   filter 非空 => 只保留 category 在 filter 中的 annotation
    //   空 category 的 annotation 始终保留 (兼容无 category 数据)
    // 主线不受影响: 默认 [] = 不过滤
    const filteredResult = (Array.isArray(filter) && filter.length > 0)
      ? result.filter(ann => !ann.category || filter.includes(ann.category))
      : result;

    annotations.value = filteredResult;
    return filteredResult;
  };

  const buildNumberMap = (annotationList) => {
    const map = new Map();
    annotationList.forEach(ann => {
      const typeConfig = getTypeConfig(ann.targetType) || { bg: '#e7f3ff', border: '#0066cc', position: 'top-right' };
      // [FIX 2026-06-29 v4] categoryConfig 可能为 null (category 不在 CATEGORY_CONFIG 中)
      //   兜底为 DEFAULT_CATEGORY_CONFIG[DEFAULT_CATEGORY] (即 'info')
      //   主线不受影响: 之前 info 是有效的所以不会 null, 现在用户用自定义 enum (TEST) 触发 null
      const categoryConfig = getCategoryConfig(ann.category) || getCategoryConfig('info') || { label: ann.category || '信息', bg: '#e6f7ff', border: '#1677ff' };
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
