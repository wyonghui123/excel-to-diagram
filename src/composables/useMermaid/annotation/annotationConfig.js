/**
 * 备注功能配置
 */

const DEFAULT_CATEGORY_CONFIG = {
  important: { label: '重要', bg: '#fff1f0', border: '#ff4d4f' },
  warning: { label: '警告', bg: '#fff7e6', border: '#fa8c16' },
  info: { label: '信息', bg: '#e6f7ff', border: '#1677ff' },
  tip: { label: '提示', bg: '#f6ffed', border: '#52c41a' }
};

let _dynamicCategoryConfig = {};

export const CATEGORY_CONFIG = new Proxy(DEFAULT_CATEGORY_CONFIG, {
  get(target, prop) {
    if (prop in _dynamicCategoryConfig) {
      return _dynamicCategoryConfig[prop];
    }
    return target[prop];
  },
  has(target, prop) {
    return prop in _dynamicCategoryConfig || prop in target;
  }
});

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

/**
 * 注册动态分类配置
 * @param {string} code - 分类编码
 * @param {object} config - 配置对象 { label, bg, border }
 */
export function registerCategoryConfig(code, config) {
  _dynamicCategoryConfig[code] = config;
}

/**
 * 批量注册动态分类配置
 * @param {object} configs - 配置映射 { code: config }
 */
export function registerCategoryConfigs(configs) {
  Object.assign(_dynamicCategoryConfig, configs);
}

/**
 * 获取分类配置
 * @param {string} category - 分类编码
 * @returns {object} 配置对象 (永远不返回 null, 兜底为 info 或 inline default)
 *
 * [FIX 2026-06-29 v6] 永远不返回 null
 *   之前 _dynamicCategoryConfig[category] || DEFAULT_CATEGORY_CONFIG[category] || null
 *   如果 category 不在两个 config 中, 返回 null
 *   调用方要分别兜底 (line 147/217) 容易遗漏导致 null.bg / null.border 报错
 *   改为永远兜底为 DEFAULT_CATEGORY_CONFIG['info'], 还不存在则 inline 默认值
 */
export function getCategoryConfig(category) {
  return _dynamicCategoryConfig[category]
      || DEFAULT_CATEGORY_CONFIG[category]
      || DEFAULT_CATEGORY_CONFIG[DEFAULT_CATEGORY]
      || { label: category || DEFAULT_CATEGORY, bg: '#e6f7ff', border: '#1677ff' };
}

export function getTypeConfig(targetType) {
  return TYPE_CONFIG[targetType] || TYPE_CONFIG.node;
}

export function toCircleNumber(num) {
  const circles = ['(1)','(2)','(3)','(4)','(5)','(6)','(7)','(8)','(9)','(10)',
                   '(11)','(12)','(13)','(14)','(15)','(16)','(17)','(18)','(19)','(20)'];
  return circles[num - 1] || `[${num}]`;
}
