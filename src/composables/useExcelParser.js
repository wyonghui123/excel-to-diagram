import { ref } from 'vue';
import {
  parseExcelFile,
  parseServiceModules,
  parseBusinessObjects,
  parseRelationships,
  parseServiceModuleRelationships
} from '../services/excelParser.js';
import {
  buildServiceModules,
  buildDomainProducts,
  buildPreviewData
} from '../services/dataTransformer.js';

/**
 * Excel解析组合式函数
 * 封装Excel文件解析和数据处理逻辑
 */
export function useExcelParser() {
  const loading = ref(false);
  const error = ref(null);
  const previewData = ref(null);
  const rawData = ref(null);

  /**
   * 处理文件上传
   * @param {File} file - Excel文件
   */
  async function handleFileUpload(file) {
    loading.value = true;
    error.value = null;

    try {
      // 1. 解析Excel文件
      const {
        businessObjectData,
        serviceComponentData,
        relationshipData
      } = await parseExcelFile(file);

      // 保存原始数据用于校验
      rawData.value = {
        businessObjectData,
        serviceComponentData,
        relationshipData
      };

      // 2. 解析服务模块数据
      const { serviceModuleMap, moduleHierarchy } = parseServiceModules(serviceComponentData);

      // 3. 解析业务对象数据
      const businessObjects = parseBusinessObjects(
        businessObjectData,
        serviceModuleMap,
        moduleHierarchy
      );

      // 4. 解析关系数据
      const relationships = parseRelationships(relationshipData, businessObjects);

      // 5. 解析服务模块关系数据（从业务对象关系推导）
      console.log('relationshipData:', relationshipData);
      const serviceModuleRelationships = parseServiceModuleRelationships(relationshipData, serviceModuleMap, businessObjects);
      console.log('解析后的 serviceModuleRelationships:', serviceModuleRelationships);

      // 6. 构建服务模块列表
      const serviceModules = buildServiceModules(serviceModuleMap);

      // 7. 构建领域产品层级结构
      const domainProducts = buildDomainProducts(moduleHierarchy);

      // 8. 构建预览数据
      previewData.value = buildPreviewData({
        businessObjects,
        serviceModules,
        relationships,
        serviceModuleRelationships,
        domainProducts
      });

      console.log('预览数据:', previewData.value);
      return true;
    } catch (err) {
      console.error('文件处理错误:', err);
      error.value = '文件处理失败: ' + err.message;
      return false;
    } finally {
      loading.value = false;
    }
  }

  /**
   * 清除数据
   */
  function clearData() {
    previewData.value = null;
    rawData.value = null;
    error.value = null;
  }

  return {
    loading,
    error,
    previewData,
    rawData,
    handleFileUpload,
    clearData
  };
}
