/**
 * 备注功能配置
 */

export const CATEGORY_CONFIG = {
  important: { icon: '⚠️', label: '重要', bg: '#fff3cd', border: '#856404' },
  warning: { icon: '🚨', label: '警告', bg: '#f8d7da', border: '#721c24' },
  info: { icon: 'ℹ️', label: '信息', bg: '#e7f3ff', border: '#0066cc' },
  tip: { icon: '💡', label: '提示', bg: '#d4edda', border: '#155724' }
};

export const TYPE_CONFIG = {
  container: { bg: '#fff3cd', border: '#856404', position: 'top-left' },
  node: { bg: '#e7f3ff', border: '#0066cc', position: 'top-right' },
  relation: { bg: '#f8d7da', border: '#721c24', position: 'top-center' }
};

export const PANEL_POSITION = {
  BOTTOM: 'bottom',
  RIGHT: 'right',
  LEFT: 'left'
};

export const DEFAULT_CATEGORY = 'info';

export function getCategoryConfig(category) {
  return CATEGORY_CONFIG[category] || CATEGORY_CONFIG[DEFAULT_CATEGORY];
}

export function getTypeConfig(targetType) {
  return TYPE_CONFIG[targetType] || TYPE_CONFIG.node;
}

export function toCircleNumber(num) {
  const circles = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩',
                   '⑪','⑫','⑬','⑭','⑮','⑯','⑰','⑱','⑲','⑳'];
  return circles[num - 1] || `[${num}]`;
}
