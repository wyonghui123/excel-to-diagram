import * as XLSX from 'xlsx';
import {
  extractServiceModuleFields,
  extractBusinessObjectFields,
  extractRelationshipFields,
  extractServiceModuleRelationshipFields,
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

  scData.forEach(item => {
    const { smCode, smName, domain, subDomain } = extractServiceModuleFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    if (smCode && smName) {
      serviceModuleMap.set(smCode, { 
        code: smCode, 
        name: smName, 
        domain, 
        subDomain,
        annotationCategory: annotationCategory || 'info',
        annotationContent: annotationContent || ''
      });

      // 构建层级
      if (domain) {
        if (!moduleHierarchy.has(domain)) {
          moduleHierarchy.set(domain, { name: domain, subDomains: new Map() });
        }
        if (subDomain) {
          const domainObj = moduleHierarchy.get(domain);
          if (!domainObj.subDomains.has(subDomain)) {
            domainObj.subDomains.set(subDomain, { name: subDomain, serviceModules: [] });
          }
          domainObj.subDomains.get(subDomain).serviceModules.push({
            code: smCode,
            name: smName,
            businessObjects: [],
            annotationCategory: annotationCategory || 'info',
            annotationContent: annotationContent || ''
          });
        }
      }
    }
  });

  return { serviceModuleMap, moduleHierarchy };
}

/**
 * 解析业务对象数据
 * @param {Array} boData - BusinessObject Sheet数据
 * @param {Map} serviceModuleMap - 服务模块映射
 * @param {Map} moduleHierarchy - 模块层级结构
 * @returns {Array} 业务对象数组
 */
export function parseBusinessObjects(boData, serviceModuleMap, moduleHierarchy) {
  const businessObjects = [];

  boData.forEach(item => {
    const { boCode, boName, smCode } = extractBusinessObjectFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    if (boName) {
      const smInfo = serviceModuleMap.get(smCode) || {};
      businessObjects.push({
        name: boName,
        code: boCode,
        serviceModule: smCode || '',
        serviceModuleName: smInfo.name || '',
        subDomain: smInfo.subDomain || '',
        domain: smInfo.domain || '',
        annotationCategory: annotationCategory || 'info',
        annotationContent: annotationContent || ''
      });

      // 添加到层级结构 - 存储业务对象对象（包含code和name）
      if (smInfo.domain && smInfo.subDomain) {
        const domainObj = moduleHierarchy.get(smInfo.domain);
        if (domainObj) {
          const subDomainObj = domainObj.subDomains.get(smInfo.subDomain);
          if (subDomainObj) {
            const sm = subDomainObj.serviceModules.find(m => m.code === smCode);
            if (sm) {
              // 检查是否已存在（通过name或code）
              const exists = sm.businessObjects.some(bo => bo.name === boName || bo.code === boCode);
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
    const { sourceCode, targetCode, relationCode: extractedRelationCode, relationDesc } = extractRelationshipFields(item);
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
  console.log('parseServiceModuleRelationships 输入数据:', relData);
  console.log('businessObjects:', businessObjects);

  // 构建业务对象编码到服务模块编码的映射
  const boToServiceModuleMap = new Map();
  if (businessObjects) {
    console.log('businessObjects 数量:', businessObjects.length);
    console.log('第一个业务对象:', businessObjects[0]);
    businessObjects.forEach(bo => {
      // 业务对象中的服务模块字段可能是 smCode 或 serviceModule
      const smCode = bo.smCode || bo.serviceModule;
      console.log(`业务对象 ${bo.code} -> 服务模块 ${smCode}`);
      if (bo.code && smCode) {
        boToServiceModuleMap.set(bo.code, smCode);
      }
    });
  }
  console.log('业务对象到服务模块映射:', boToServiceModuleMap);
  console.log('映射大小:', boToServiceModuleMap.size);

  // 用于去重的集合
  const relationshipSet = new Set();

  relData.forEach((item, index) => {
    // 提取业务对象关系字段
    const {
      sourceBusinessObjectCode,
      targetBusinessObjectCode,
      relationshipCode
    } = extractRelationshipFields(item);
    const { annotationCategory, annotationContent } = extractAnnotationFields(item);

    console.log(`处理第${index}行业务对象关系:`, { sourceBusinessObjectCode, targetBusinessObjectCode, relationshipCode });

    // 根据业务对象编码查找对应的服务模块编码
    const sourceSmCode = boToServiceModuleMap.get(sourceBusinessObjectCode);
    const targetSmCode = boToServiceModuleMap.get(targetBusinessObjectCode);

    console.log('对应的服务模块:', { sourceSmCode, targetSmCode });

    // 如果找到了服务模块编码，且源和目标不同，则创建服务模块关系
    if (sourceSmCode && targetSmCode && sourceSmCode !== targetSmCode) {
      // 生成唯一的关系标识用于去重
      const relationKey = `${sourceSmCode}-${targetSmCode}`;

      if (!relationshipSet.has(relationKey)) {
        relationshipSet.add(relationKey);

        // 获取源和目标服务模块信息
        const sourceSm = serviceModuleMap.get(sourceSmCode) || {};
        const targetSm = serviceModuleMap.get(targetSmCode) || {};

        serviceModuleRelationships.push({
          sourceServiceModuleCode: sourceSmCode,
          targetServiceModuleCode: targetSmCode,
          sourceServiceModuleName: sourceSm.name || sourceSmCode,
          targetServiceModuleName: targetSm.name || targetSmCode,
          serviceRelationshipCode: relationshipCode || `${sourceSmCode}-${targetSmCode}`,
          businessObjectRelationshipCodes: [relationshipCode].filter(Boolean),
          annotationCategory: annotationCategory || 'info',
          annotationContent: annotationContent || ''
        });

        console.log('创建服务模块关系:', { sourceSmCode, targetSmCode });
      }
    }
  });

  console.log('最终服务模块关系:', serviceModuleRelationships);
  return serviceModuleRelationships;
}
