import * as XLSX from 'xlsx';
import {
  extractServiceModuleFields,
  extractBusinessObjectFields,
  extractRelationshipFields,
  extractAnnotationFields
} from '../utils/fieldExtractors.js';

/**
 * excelParser - Excel/CSV文件解析服务
 *
 * 所属模块：数据导入
 * 主要功能：
 *   - 解析Excel文件(.xlsx, .xls)
 *   - 解析CSV文件
 *   - 识别并分类Sheet数据（业务对象/服务模块/关系）
 *   - 处理不同编码格式(UTF-8, GBK)
 *
 * 核心接口：
 *   - parseExcelFile(): 解析Excel文件
 *   - parseCSVFile(): 解析CSV文件
 *
 * @see dataValidator.js - 数据验证
 * @see dataTransformer.js - 数据转换
 */

/**
 * 解析Excel文件
 * @param {File} file - Excel文件对象
 * @returns {Promise<Object>} { businessObjectData, serviceComponentData, relationshipData }
 */
export async function parseExcelFile(file) {
  const data = await file.arrayBuffer();
  const workbook = XLSX.read(data, { type: 'array' });

  // 初始化数据存储
  let businessObjectData = [];
  let serviceComponentData = [];
  let relationshipData = [];

  // 遍历所有Sheet
  workbook.SheetNames.forEach(sheetName => {
    const worksheet = workbook.Sheets[sheetName];
    const sheetData = XLSX.utils.sheet_to_json(worksheet);
    const lowerName = sheetName.toLowerCase();

    // 根据Sheet名称分类
    if (lowerName.includes('business') || lowerName.includes('业务对象')) {
      businessObjectData = businessObjectData.concat(sheetData);
    } else if (lowerName.includes('service') || lowerName.includes('component') || lowerName.includes('服务')) {
      serviceComponentData = serviceComponentData.concat(sheetData);
    } else if (lowerName.includes('relation') || lowerName.includes('关系')) {
      relationshipData = relationshipData.concat(sheetData);
    } else {
      // 根据内容判断
      if (sheetData.length > 0) {
        const keys = Object.keys(sheetData[0]).join(',').toLowerCase();
        if (keys.includes('source') || keys.includes('target') || keys.includes('源') || keys.includes('目标')) {
          relationshipData = relationshipData.concat(sheetData);
        } else if (keys.includes('service') || keys.includes('domain') || keys.includes('服务') || keys.includes('领域')) {
          serviceComponentData = serviceComponentData.concat(sheetData);
        } else {
          businessObjectData = businessObjectData.concat(sheetData);
        }
      }
    }
  });

  return {
    businessObjectData,
    serviceComponentData,
    relationshipData
  };
}

/**
 * 解析服务模块数据
 * @param {Array} scData - ServiceComponent Sheet数据
 * @returns {Object} { serviceModuleMap, moduleHierarchy }
 */
export function parseServiceModules(scData) {
  const serviceModuleMap = new Map();
  const moduleHierarchy = new Map();
  const nameToCodeMap = new Map();

  scData.forEach(item => {
    const { smCode, smName, domain, subDomain } = extractServiceModuleFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    if (smCode && smName) {
      if (serviceModuleMap.has(smCode)) {
        return;
      }

      serviceModuleMap.set(smCode, {
        code: smCode,
        name: smName,
        domain,
        subDomain,
        annotationCategory: annotationCategory || 'info',
        annotationContent: annotationContent || ''
      });

      if (!nameToCodeMap.has(smName)) {
        nameToCodeMap.set(smName, smCode);
      }

      if (domain) {
        if (!moduleHierarchy.has(domain)) {
          moduleHierarchy.set(domain, { name: domain, subDomains: new Map() });
        }
        if (subDomain) {
          const domainObj = moduleHierarchy.get(domain);
          if (!domainObj.subDomains.has(subDomain)) {
            domainObj.subDomains.set(subDomain, { name: subDomain, serviceModules: [] });
          }
          const subDomainObj = domainObj.subDomains.get(subDomain);
          const smExists = subDomainObj.serviceModules.some(sm => sm.code === smCode);
          if (!smExists) {
            subDomainObj.serviceModules.push({
              code: smCode,
              name: smName,
              businessObjects: [],
              annotationCategory: annotationCategory || 'info',
              annotationContent: annotationContent || ''
            });
          }
        }
      }
    }
  });

  return { serviceModuleMap, moduleHierarchy, nameToCodeMap };
}

/**
 * 解析业务对象数据
 * @param {Array} boData - BusinessObject Sheet数据
 * @param {Map} serviceModuleMap - 服务模块映射
 * @param {Map} moduleHierarchy - 模块层级结构
 * @param {Map} nameToCodeMap - 服务模块名称到编码的映射
 * @returns {Array} 业务对象数组
 */
export function parseBusinessObjects(boData, serviceModuleMap, moduleHierarchy, nameToCodeMap) {
  const businessObjects = [];
  const boCodeSet = new Set();

  boData.forEach((item, index) => {
    const { boCode, boName, serviceModule } = extractBusinessObjectFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    if (boName && boCode) {
      if (boCodeSet.has(boCode)) {
        return;
      }
      boCodeSet.add(boCode);

      let resolvedSmCode = serviceModule;
      if (!resolvedSmCode || !serviceModuleMap.has(resolvedSmCode)) {
        resolvedSmCode = nameToCodeMap.get(serviceModule);
      }

      const smInfo = serviceModuleMap.get(resolvedSmCode) || {};
      businessObjects.push({
        name: boName,
        code: boCode,
        serviceModule: resolvedSmCode || serviceModule || '',
        serviceModuleName: smInfo.name || '',
        subDomain: smInfo.subDomain || '',
        domain: smInfo.domain || '',
        annotationCategory: annotationCategory || 'info',
        annotationContent: annotationContent || ''
      });

      if (smInfo.domain && smInfo.subDomain) {
        const domainObj = moduleHierarchy.get(smInfo.domain);
        if (domainObj) {
          const subDomainObj = domainObj.subDomains.get(smInfo.subDomain);
          if (subDomainObj) {
            const sm = subDomainObj.serviceModules.find(m => m.code === resolvedSmCode);
            if (sm) {
              // 去重检查：只基于 code，不基于 name（因为不同业务对象可能有相同名称）
              const exists = sm.businessObjects.some(bo => bo.code === boCode);
              if (!exists) {
                sm.businessObjects.push({ name: boName, code: boCode });
              }
            }
          }
        }
      }
    }
  });

  return businessObjects;
}

/**
 * 解析关系数据
 * @param {Array} relData - Relationship Sheet数据
 * @param {Array} businessObjects - 业务对象数组
 * @returns {Array} 关系数组
 */
export function parseRelationships(relData, businessObjects) {
  const relationships = [];

  // 创建业务对象编码到名称的映射
  const boCodeToNameMap = new Map();
  businessObjects.forEach(bo => {
    if (bo.code) {
      boCodeToNameMap.set(bo.code, bo.name);
    }
  });

  relData.forEach(item => {
    const { sourceCode, targetCode, relationCode: extractedRelationCode, description: relationDesc } = extractRelationshipFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    if (sourceCode && targetCode) {
      // 通过编码获取业务对象名称
      const sourceName = boCodeToNameMap.get(sourceCode) || sourceCode;
      const targetName = boCodeToNameMap.get(targetCode) || targetCode;
      // 关系编码：优先使用Excel中的关系编码，如果没有则生成
      const relationCode = extractedRelationCode || `${sourceCode}-${targetCode}`;

      relationships.push({
        sourceCode,
        targetCode,
        sourceName,
        targetName,
        relationCode,
        relationDesc,
        annotationCategory: annotationCategory || 'info',
        annotationContent: annotationContent || ''
      });
    }
  });

  return relationships;
}

/**
 * 解析服务模块关系数据
 * 从业务对象关系中推导服务模块关系
 * @param {Array} relData - Relationship Sheet数据（业务对象关系）
 * @param {Map} serviceModuleMap - 服务模块映射
 * @param {Array} businessObjects - 业务对象数组，用于获取业务对象所属的服务模块
 * @returns {Array} 服务模块关系数组
 */
export function parseServiceModuleRelationships(relData, serviceModuleMap, businessObjects) {
  const serviceModuleRelationships = [];

  const boToServiceModuleMap = new Map();
  if (businessObjects) {
    businessObjects.forEach(bo => {
      const smCode = bo.smCode || bo.serviceModule;
      if (bo.code && smCode) {
        boToServiceModuleMap.set(bo.code, smCode);
      }
    });
  }

  const relationshipMap = new Map();

  relData.forEach((item) => {
    const {
      sourceCode,
      targetCode,
      relationCode
    } = extractRelationshipFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    const sourceSmCode = boToServiceModuleMap.get(sourceCode);
    const targetSmCode = boToServiceModuleMap.get(targetCode);

    if (sourceSmCode && targetSmCode && sourceSmCode !== targetSmCode) {
      const relationKey = `${sourceSmCode}-${targetSmCode}`;

      if (!relationshipMap.has(relationKey)) {
        relationshipMap.set(relationKey, {
          sourceServiceModuleCode: sourceSmCode,
          targetServiceModuleCode: targetSmCode,
          businessObjectRelationships: []
        });
      }

      const rel = relationshipMap.get(relationKey);
      rel.businessObjectRelationships.push({
        relationCode: relationCode || `${sourceCode}-${targetCode}`,
        annotationCategory: annotationCategory || 'info',
        annotationContent: annotationContent || ''
      });
    }
  });

  relationshipMap.forEach((rel) => {
    const sourceSm = serviceModuleMap.get(rel.sourceServiceModuleCode) || {};
    const targetSm = serviceModuleMap.get(rel.targetServiceModuleCode) || {};

    const boCodes = rel.businessObjectRelationships.map(boRel => boRel.relationCode);
    const boAnnotations = rel.businessObjectRelationships
      .filter(boRel => boRel.annotationContent)
      .map(boRel => boRel.annotationContent)
      .join('; ');

    serviceModuleRelationships.push({
      sourceServiceModuleCode: rel.sourceServiceModuleCode,
      targetServiceModuleCode: rel.targetServiceModuleCode,
      sourceServiceModuleName: sourceSm.name || rel.sourceServiceModuleCode,
      targetServiceModuleName: targetSm.name || rel.targetServiceModuleCode,
      serviceRelationshipCode: boCodes.join(', ') || `${rel.sourceServiceModuleCode}-${rel.targetServiceModuleCode}`,
      businessObjectRelationshipCodes: boCodes,
      annotationCategory: rel.businessObjectRelationships[0]?.annotationCategory || 'info',
      annotationContent: boAnnotations || ''
    });
  });

  return serviceModuleRelationships;
}
