/**
 * 数据校验服务
 * 负责校验导入数据的完整性和关联性
 */

// 校验级别
export const ValidationLevel = {
  ERROR: 'error',     // 严重错误，影响图表生成
  WARNING: 'warning', // 警告，可能影响展示效果
  INFO: 'info'        // 提示信息
};

// 校验类型
export const ValidationType = {
  FOREIGN_KEY: 'foreign_key',       // 外键关联
  REQUIRED: 'required',             // 必填项
  DUPLICATE: 'duplicate',           // 重复数据
  FORMAT: 'format',                 // 格式错误
  AI_CHECK: 'ai_check'              // AI检查
};

/**
 * 校验结果项
 * @typedef {Object} ValidationItem
 * @property {string} level - 校验级别 (error/warning/info)
 * @property {string} type - 校验类型
 * @property {string} sheet - 所在Sheet
 * @property {number} row - 行号
 * @property {string} field - 字段名
 * @property {string} value - 字段值
 * @property {string} message - 错误描述
 * @property {string} suggestion - 修复建议
 */

/**
 * 执行数据校验
 * @param {Object} rawData - 原始解析数据
 * @param {Object} previewData - 转换后的预览数据
 * @returns {Object} { items: ValidationItem[], summary: Object }
 */
export function validateData(rawData, previewData) {
  const items = [];

  // 1. 校验服务模块的外键关联（应用领域编码）
  items.push(...validateServiceModuleForeignKeys(rawData, previewData));

  // 2. 校验业务对象的外键关联
  items.push(...validateBusinessObjectForeignKeys(rawData, previewData));

  // 3. 校验关系数据的外键关联
  items.push(...validateRelationshipForeignKeys(rawData, previewData));

  // 4. 校验必填项
  items.push(...validateRequiredFields(rawData));

  // 5. 校验重复数据
  items.push(...validateDuplicates(rawData));

  // 生成汇总
  const summary = generateSummary(items);

  return { items, summary };
}

/**
 * 校验服务模块的外键关联
 * 检查服务模块引用的应用领域编码是否存在
 */
function validateServiceModuleForeignKeys(rawData, previewData) {
  const items = [];
  const validDomains = new Set();

  // 收集有效的领域编码（从服务模块数据中提取唯一的领域）
  rawData.serviceComponentData?.forEach(item => {
    const domain = item['领域'] || item['Domain'] || item['domain'];
    if (domain) {
      validDomains.add(domain);
    }
  });

  // 检查每个服务模块
  rawData.serviceComponentData?.forEach((item, index) => {
    const smCode = item['服务模块编码'] || item['SM编码'] || item['smCode'];
    const smName = item['服务模块名称'] || item['SM名称'] || item['smName'];
    const domain = item['领域'] || item['Domain'] || item['domain'];
    const subDomain = item['子领域'] || item['SubDomain'] || item['subDomain'];

    // 检查应用领域是否存在（如果填写了的话）
    if (domain && !validDomains.has(domain)) {
      items.push({
        level: ValidationLevel.WARNING,
        type: ValidationType.FOREIGN_KEY,
        sheet: '服务模块',
        row: index + 2,
        field: '领域',
        value: domain,
        entityCode: smCode,
        message: `服务模块"${smName || smCode}"引用了不存在的领域"${domain}"`,
        suggestion: '请检查领域名称是否正确'
      });
    }
  });

  return items;
}

/**
 * 校验业务对象的外键关联
 * 检查业务对象引用的服务模块是否存在
 */
function validateBusinessObjectForeignKeys(rawData, previewData) {
  const items = [];
  const validServiceModules = new Set();

  // 收集有效的服务模块编码
  previewData.serviceModules?.forEach(sm => {
    validServiceModules.add(sm.code);
  });

  // 检查每个业务对象
  rawData.businessObjectData?.forEach((item, index) => {
    const smCode = item['服务模块编码'] || item['SM编码'] || item['smCode'];
    const boCode = item['业务对象编码'] || item['BO编码'] || item['boCode'];
    const boName = item['业务对象名称'] || item['BO名称'] || item['boName'];

    if (smCode && !validServiceModules.has(smCode)) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.FOREIGN_KEY,
        sheet: '业务对象',
        row: index + 2, // Excel行号从1开始，第1行是标题
        field: '服务模块编码',
        value: smCode,
        entityCode: boCode,
        message: `业务对象"${boName || boCode}"引用了不存在的服务模块"${smCode}"`,
        suggestion: '请检查服务模块编码是否正确，或在服务模块Sheet中添加该模块'
      });
    }
  });

  return items;
}

/**
 * 校验关系数据的外键关联
 * 检查关系引用的源业务对象和目标业务对象是否存在
 */
function validateRelationshipForeignKeys(rawData, previewData) {
  const items = [];
  const validBusinessObjects = new Set();

  // 收集有效的业务对象编码
  previewData.businessObjects?.forEach(bo => {
    validBusinessObjects.add(bo.code);
  });

  // 检查每个关系
  rawData.relationshipData?.forEach((item, index) => {
    const sourceCode = item['源业务对象编码'] || item['Source编码'] || item['sourceCode'];
    const targetCode = item['目标业务对象编码'] || item['Target编码'] || item['targetCode'];
    const relationCode = item['关系编码'] || item['Relation编码'] || item['relationCode'];

    // 检查源业务对象
    if (sourceCode && !validBusinessObjects.has(sourceCode)) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.FOREIGN_KEY,
        sheet: '业务对象关系',
        row: index + 2,
        field: '源业务对象编码',
        value: sourceCode,
        entityCode: relationCode,
        message: `关系"${relationCode}"引用了不存在的源业务对象"${sourceCode}"`,
        suggestion: '请检查源业务对象编码是否正确，或在业务对象Sheet中添加该对象'
      });
    }

    // 检查目标业务对象
    if (targetCode && !validBusinessObjects.has(targetCode)) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.FOREIGN_KEY,
        sheet: '业务对象关系',
        row: index + 2,
        field: '目标业务对象编码',
        value: targetCode,
        entityCode: relationCode,
        message: `关系"${relationCode}"引用了不存在的目标业务对象"${targetCode}"`,
        suggestion: '请检查目标业务对象编码是否正确，或在业务对象Sheet中添加该对象'
      });
    }

    // 检查自关联
    if (sourceCode && targetCode && sourceCode === targetCode) {
      items.push({
        level: ValidationLevel.WARNING,
        type: ValidationType.FOREIGN_KEY,
        sheet: '业务对象关系',
        row: index + 2,
        field: '源/目标业务对象编码',
        value: sourceCode,
        entityCode: relationCode,
        message: `关系"${relationCode}"的源业务对象和目标业务对象相同`,
        suggestion: '请确认是否为自关联关系，如非预期请修改'
      });
    }
  });

  return items;
}

/**
 * 校验必填项
 */
function validateRequiredFields(rawData) {
  const items = [];

  // 业务对象必填项
  const boRequiredFields = ['业务对象编码', '业务对象名称', 'BO编码', 'BO名称', 'boCode', 'boName'];
  rawData.businessObjectData?.forEach((item, index) => {
    const boCode = item['业务对象编码'] || item['BO编码'] || item['boCode'];
    const boName = item['业务对象名称'] || item['BO名称'] || item['boName'];
    const hasCode = boRequiredFields.some(field => item[field]);
    if (!hasCode) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.REQUIRED,
        sheet: '业务对象',
        row: index + 2,
        field: '业务对象编码',
        value: '',
        entityCode: boCode,
        message: '业务对象编码不能为空',
        suggestion: '请填写业务对象编码'
      });
    }
  });

  // 服务模块必填项
  const smRequiredFields = ['服务模块编码', '服务模块名称', 'SM编码', 'SM名称', 'smCode', 'smName'];
  rawData.serviceComponentData?.forEach((item, index) => {
    const smCode = item['服务模块编码'] || item['SM编码'] || item['smCode'];
    const smName = item['服务模块名称'] || item['SM名称'] || item['smName'];
    const hasCode = smRequiredFields.some(field => item[field]);
    if (!hasCode) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.REQUIRED,
        sheet: '服务模块',
        row: index + 2,
        field: '服务模块编码',
        value: '',
        entityCode: smCode,
        message: '服务模块编码不能为空',
        suggestion: '请填写服务模块编码'
      });
    }
  });

  // 关系必填项
  rawData.relationshipData?.forEach((item, index) => {
    const sourceCode = item['源业务对象编码'] || item['Source编码'] || item['sourceCode'];
    const targetCode = item['目标业务对象编码'] || item['Target编码'] || item['targetCode'];
    const relationCode = item['关系编码'] || item['Relation编码'] || item['relationCode'];

    if (!sourceCode) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.REQUIRED,
        sheet: '业务对象关系',
        row: index + 2,
        field: '源业务对象编码',
        value: '',
        entityCode: relationCode,
        message: '源业务对象编码不能为空',
        suggestion: '请填写源业务对象编码'
      });
    }

    if (!targetCode) {
      items.push({
        level: ValidationLevel.ERROR,
        type: ValidationType.REQUIRED,
        sheet: '业务对象关系',
        row: index + 2,
        field: '目标业务对象编码',
        value: '',
        entityCode: relationCode,
        message: '目标业务对象编码不能为空',
        suggestion: '请填写目标业务对象编码'
      });
    }
  });

  return items;
}

/**
 * 校验重复数据
 */
function validateDuplicates(rawData) {
  const items = [];

  // 检查业务对象重复
  const boCodes = new Map();
  rawData.businessObjectData?.forEach((item, index) => {
    const code = item['业务对象编码'] || item['BO编码'] || item['boCode'];
    if (code) {
      if (boCodes.has(code)) {
        items.push({
          level: ValidationLevel.WARNING,
          type: ValidationType.DUPLICATE,
          sheet: '业务对象',
          row: index + 2,
          field: '业务对象编码',
          value: code,
          entityCode: code,
          message: `业务对象编码"${code}"重复`,
          suggestion: `该编码在第${boCodes.get(code)}行已存在，请检查是否为重复数据`
        });
      } else {
        boCodes.set(code, index + 2);
      }
    }
  });

  // 检查服务模块重复
  const smCodes = new Map();
  rawData.serviceComponentData?.forEach((item, index) => {
    const code = item['服务模块编码'] || item['SM编码'] || item['smCode'];
    if (code) {
      if (smCodes.has(code)) {
        items.push({
          level: ValidationLevel.WARNING,
          type: ValidationType.DUPLICATE,
          sheet: '服务模块',
          row: index + 2,
          field: '服务模块编码',
          value: code,
          entityCode: code,
          message: `服务模块编码"${code}"重复`,
          suggestion: `该编码在第${smCodes.get(code)}行已存在，请检查是否为重复数据`
        });
      } else {
        smCodes.set(code, index + 2);
      }
    }
  });

  return items;
}

/**
 * 生成校验汇总
 */
function generateSummary(items) {
  return {
    total: items.length,
    error: items.filter(i => i.level === ValidationLevel.ERROR).length,
    warning: items.filter(i => i.level === ValidationLevel.WARNING).length,
    info: items.filter(i => i.level === ValidationLevel.INFO).length
  };
}

/**
 * 按Sheet分组校验结果
 */
export function groupBySheet(items) {
  const groups = {};
  items.forEach(item => {
    if (!groups[item.sheet]) {
      groups[item.sheet] = [];
    }
    groups[item.sheet].push(item);
  });
  return groups;
}

/**
 * 按级别分组校验结果
 */
export function groupByLevel(items) {
  return {
    error: items.filter(i => i.level === ValidationLevel.ERROR),
    warning: items.filter(i => i.level === ValidationLevel.WARNING),
    info: items.filter(i => i.level === ValidationLevel.INFO)
  };
}
