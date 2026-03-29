/**
 * 字段提取工具函数
 * 用于从Excel行数据中提取各类字段
 */

/**
 * 从对象中提取备注相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { annotationCategory, annotationContent }
 */
export function extractAnnotationFields(item) {
  const keys = Object.keys(item);
  console.log('extractAnnotationFields keys:', keys);
  console.log('extractAnnotationFields item:', item);
  let annotationCategory = '', annotationContent = '';

  const validCategories = ['important', 'warning', 'info', 'tip'];

  keys.forEach(key => {
    const lower = key.toLowerCase();
    console.log('Checking key:', key, 'lower:', lower);
    // 备注分类
    if ((key.includes('备注分类') || key.includes('annotationcategory') || 
         key.includes('annotation_category') || lower.includes('category')) && 
        key.includes('备注')) {
      const value = item[key];
      console.log('Found annotation category key:', key, 'value:', value);
      if (value && validCategories.includes(String(value).toLowerCase())) {
        annotationCategory = String(value).toLowerCase();
      }
    }
    // 备注内容
    else if ((key.includes('备注内容') || key.includes('annotationcontent') || 
              key.includes('annotation_content') || lower.includes('content')) && 
             key.includes('备注')) {
      const value = item[key];
      console.log('Found annotation content key:', key, 'value:', value);
      annotationContent = value;
    }
  });

  // 模糊匹配兜底
  if (!annotationCategory) {
    for (const key of keys) {
      if (key.includes('备注') && key.includes('分类')) {
        const value = item[key];
        if (value && validCategories.includes(String(value).toLowerCase())) {
          annotationCategory = String(value).toLowerCase();
          break;
        }
      }
    }
  }
  if (!annotationContent) {
    for (const key of keys) {
      if (key.includes('备注') && !key.includes('分类')) {
        annotationContent = item[key];
        break;
      }
    }
  }

  // 额外的模糊匹配：检查任何包含"备注"的列
  if (!annotationContent) {
    for (const key of keys) {
      if (key.includes('备注') || key.toLowerCase().includes('annotation') || key.toLowerCase().includes('note')) {
        const value = item[key];
        if (value && typeof value === 'string' && value.trim() && !key.includes('分类')) {
          annotationContent = value;
          console.log('Fallback: Found annotation content in key:', key, 'value:', value);
          break;
        }
      }
    }
  }

  console.log('extractAnnotationFields result:', { annotationCategory, annotationContent });
  return { annotationCategory, annotationContent };
}

/**
 * 从对象中提取服务模块相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { smCode, smName, domain, subDomain }
 */
export function extractServiceModuleFields(item) {
  const keys = Object.keys(item);
  let smCode = '', smName = '', domain = '', subDomain = '';

  keys.forEach(key => {
    const lower = key.toLowerCase();
    // 服务模块编码 - 优先匹配"服务模块编码"
    if ((key.includes('服务模块编码') || key.includes('servicemodulecode') || key.includes('sm_code')) && !key.includes('业务')) {
      smCode = item[key];
    }
    // 服务模块名称
    else if ((key.includes('服务模块名称') || key.includes('servicemodulename') || key.includes('sm_name')) && !key.includes('编码')) {
      smName = item[key];
    }
    // 领域
    else if ((key.includes('领域') || key.includes('domain')) && !key.includes('子')) {
      domain = item[key];
    }
    // 子领域
    else if (key.includes('子领域') || key.includes('subdomain') || key.includes('产品模块')) {
      subDomain = item[key];
    }
  });

  // 如果精确匹配失败，尝试模糊匹配
  if (!smCode) {
    for (const key of keys) {
      if (key.includes('编码') && key.includes('服务') && !key.includes('业务')) {
        smCode = item[key];
        break;
      }
    }
  }
  if (!smName) {
    for (const key of keys) {
      if ((key.includes('服务模块') || key.includes('名称')) && !key.includes('编码')) {
        smName = item[key];
        break;
      }
    }
  }
  if (!domain) {
    for (const key of keys) {
      if (key.includes('领域') && !key.includes('子')) {
        domain = item[key];
        break;
      }
    }
  }
  if (!subDomain) {
    for (const key of keys) {
      if (key.includes('子领域') || key.includes('模块')) {
        subDomain = item[key];
        break;
      }
    }
  }

  return { smCode, smName, domain, subDomain };
}

/**
 * 从对象中提取业务对象相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { boCode, boName, smCode }
 */
export function extractBusinessObjectFields(item) {
  const keys = Object.keys(item);
  let boCode = '', boName = '', smCode = '';

  keys.forEach(key => {
    const lower = key.toLowerCase();
    // 业务对象编码 - 优先匹配"业务对象编码"
    if ((key.includes('业务对象编码') || key.includes('businessobjectcode') || key.includes('bo_code')) && !key.includes('服务')) {
      boCode = item[key];
    }
    // 业务对象名称
    else if ((key.includes('业务对象名称') || key.includes('businessobjectname') || key.includes('boname')) && !key.includes('编码') && !key.includes('code')) {
      boName = item[key];
    }
    // 所属服务模块编码 - 优先匹配包含"服务模块"和"编码"的字段
    else if ((key.includes('所属服务模块编码') || key.includes('servicemodulecode') || key.includes('service_code') ||
              (key.includes('服务模块') && key.includes('编码')))) {
      smCode = item[key];
    }
  });

  // 如果精确匹配失败，尝试模糊匹配
  if (!boCode) {
    for (const key of keys) {
      if (key.includes('编码') && key.includes('业务') && !key.includes('服务')) {
        boCode = item[key];
        break;
      }
    }
  }
  if (!boName) {
    for (const key of keys) {
      if ((key.includes('业务对象') || key.includes('名称')) && !key.includes('编码')) {
        boName = item[key];
        break;
      }
    }
  }
  if (!smCode) {
    for (const key of keys) {
      if (key.includes('服务模块') || key.includes('所属')) {
        smCode = item[key];
        break;
      }
    }
  }

  return { boCode, boName, smCode };
}

/**
 * 从对象中提取关系相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { sourceCode, targetCode, relationCode, relationDesc }
 */
export function extractRelationshipFields(item) {
  const keys = Object.keys(item);
  let sourceCode = '', targetCode = '', relationCode = '', relationDesc = '';

  keys.forEach(key => {
    const lower = key.toLowerCase();
    // 源业务对象编码
    if ((key.includes('源') && key.includes('编码')) ||
        key.includes('sourcecode') ||
        key.includes('source_code')) {
      sourceCode = item[key];
    }
    // 目标业务对象编码
    else if ((key.includes('目标') && key.includes('编码')) ||
             key.includes('targetcode') ||
             key.includes('target_code')) {
      targetCode = item[key];
    }
    // 关系编码
    else if ((key.includes('关系') && key.includes('编码')) ||
             key.includes('relationcode') ||
             key.includes('relation_code')) {
      relationCode = item[key];
    }
    // 关系说明
    else if ((key.includes('关系') && key.includes('说明')) ||
             key.includes('relationdesc') ||
             key.includes('relation_desc')) {
      relationDesc = item[key];
    }
  });

  // 如果精确匹配失败，尝试模糊匹配
  if (!sourceCode) {
    for (const key of keys) {
      if (key.includes('源') && (key.includes('编码') || key.includes('code'))) {
        sourceCode = item[key];
        break;
      }
    }
  }
  if (!targetCode) {
    for (const key of keys) {
      if (key.includes('目标') && (key.includes('编码') || key.includes('code'))) {
        targetCode = item[key];
        break;
      }
    }
  }
  if (!relationCode) {
    for (const key of keys) {
      if (key.includes('关系') && (key.includes('编码') || key.includes('code'))) {
        relationCode = item[key];
        break;
      }
    }
  }
  if (!relationDesc) {
    for (const key of keys) {
      if (key.includes('说明') || key.includes('desc')) {
        relationDesc = item[key];
        break;
      }
    }
  }

  return { sourceCode, targetCode, relationCode, relationDesc };
}

/**
 * 从对象中提取服务模块关系相关字段
 * @param {Object} item - Excel行数据
 * @returns {Object} { sourceServiceModuleCode, targetServiceModuleCode, serviceRelationshipCode, businessObjectRelationshipCodes }
 */
export function extractServiceModuleRelationshipFields(item) {
  const keys = Object.keys(item);
  let sourceServiceModuleCode = '', targetServiceModuleCode = '', serviceRelationshipCode = '', businessObjectRelationshipCodes = '';

  keys.forEach(key => {
    const lower = key.toLowerCase();
    // 源服务模块编码
    if ((key.includes('源') && key.includes('服务模块') && key.includes('编码')) ||
        key.includes('sourceservicemodulecode') ||
        key.includes('source_service_module_code') ||
        key.includes('source_sm_code')) {
      sourceServiceModuleCode = item[key];
    }
    // 目标服务模块编码
    else if ((key.includes('目标') && key.includes('服务模块') && key.includes('编码')) ||
             key.includes('targetservicemodulecode') ||
             key.includes('target_service_module_code') ||
             key.includes('target_sm_code')) {
      targetServiceModuleCode = item[key];
    }
    // 服务关系编码
    else if ((key.includes('服务') && key.includes('关系') && key.includes('编码')) ||
             key.includes('servicerelationshipcode') ||
             key.includes('service_relationship_code') ||
             key.includes('service_relation_code')) {
      serviceRelationshipCode = item[key];
    }
    // 业务对象关系编码列表
    else if ((key.includes('业务对象') && key.includes('关系') && key.includes('编码')) ||
             key.includes('businessobjectrelationshipcodes') ||
             key.includes('bo_relationship_codes') ||
             key.includes('business_relation_codes')) {
      businessObjectRelationshipCodes = item[key];
    }
  });

  // 如果精确匹配失败，尝试模糊匹配
  if (!sourceServiceModuleCode) {
    for (const key of keys) {
      if (key.includes('源') && key.includes('服务') && key.includes('编码')) {
        sourceServiceModuleCode = item[key];
        break;
      }
    }
  }
  if (!targetServiceModuleCode) {
    for (const key of keys) {
      if (key.includes('目标') && key.includes('服务') && key.includes('编码')) {
        targetServiceModuleCode = item[key];
        break;
      }
    }
  }
  if (!serviceRelationshipCode) {
    for (const key of keys) {
      if (key.includes('服务') && key.includes('关系')) {
        serviceRelationshipCode = item[key];
        break;
      }
    }
  }
  if (!businessObjectRelationshipCodes) {
    for (const key of keys) {
      if (key.includes('业务') && key.includes('关系')) {
        businessObjectRelationshipCodes = item[key];
        break;
      }
    }
  }

  return { sourceServiceModuleCode, targetServiceModuleCode, serviceRelationshipCode, businessObjectRelationshipCodes };
}
