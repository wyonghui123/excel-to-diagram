/**
 * fieldExtractors 单元测试
 * 目标覆盖率: 95%+
 */

import { describe, it, expect } from 'vitest'
import {
  extractAnnotationFields,
  extractServiceModuleFields,
  extractBusinessObjectFields,
  extractRelationshipFields
} from '../fieldExtractors.js'

describe('fieldExtractors', () => {
  describe('extractAnnotationFields', () => {
    it('应该提取备注分类和内容', () => {
      const row = { '备注分类': 'important', '备注内容': '这是一个重要备注' }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('important')
      expect(result.annotationContent).toBe('这是一个重要备注')
    })

    it('应该支持英文备注字段名', () => {
      const row = { 'annotationCategory': 'warning', 'annotationContent': '警告内容' }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('warning')
      expect(result.annotationContent).toBe('警告内容')
    })

    it('应该支持下划线格式的备注字段名', () => {
      const row = { 'annotation_category': 'info', 'annotation_content': '信息内容' }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('info')
      expect(result.annotationContent).toBe('信息内容')
    })

    it('无效的分类值应该被忽略', () => {
      const row = { '备注分类': 'invalid', '备注内容': '内容' }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('')
      expect(result.annotationContent).toBe('内容')
    })

    it('空对象应该返回空值', () => {
      const result = extractAnnotationFields({})
      expect(result.annotationCategory).toBe('')
      expect(result.annotationContent).toBe('')
    })

    it('应该支持 tip 分类', () => {
      const row = { '备注分类': 'tip', '备注内容': '提示内容' }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('tip')
    })

    it('没有分类字段时应该尝试从包含备注和分类的字段中提取', () => {
      const row = { '备注_分类': 'important', '备注': '内容' }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('important')
      expect(result.annotationContent).toBe('内容')
    })

    it('应该支持 note 字段名', () => {
      const row = { 'note': '笔记内容' }
      const result = extractAnnotationFields(row)
      expect(result.annotationContent).toBe('笔记内容')
    })

    it('null 值应该被正确处理', () => {
      const row = { '备注分类': null, '备注内容': null }
      const result = extractAnnotationFields(row)
      expect(result.annotationCategory).toBe('')
      expect(result.annotationContent).toBe('')
    })
  })

  describe('extractServiceModuleFields', () => {
    it('应该提取服务模块字段', () => {
      const row = {
        '服务模块编码': 'SM001',
        '服务模块名称': '采购管理',
        '领域': '供应链云',
        '子领域': '采购'
      }
      const result = extractServiceModuleFields(row)
      expect(result.smCode).toBe('SM001')
      expect(result.smName).toBe('采购管理')
      expect(result.domain).toBe('供应链云')
      expect(result.subDomain).toBe('采购')
    })

    it('应该支持英文字段名', () => {
      const row = {
        'serviceModuleCode': 'SM002',
        'serviceModuleName': '销售管理',
        'domain': '营销云',
        'subDomain': '销售'
      }
      const result = extractServiceModuleFields(row)
      expect(result.smCode).toBe('SM002')
      expect(result.smName).toBe('销售管理')
      expect(result.domain).toBe('营销云')
      expect(result.subDomain).toBe('销售')
    })

    it('应该支持下划线字段名', () => {
      const row = {
        'sm_code': 'SM003',
        'sm_name': '库存管理',
        'domain': '供应链云',
        'subDomain': '库存'
      }
      const result = extractServiceModuleFields(row)
      expect(result.smCode).toBe('SM003')
      expect(result.smName).toBe('库存管理')
    })

    it('空对象应该返回空值', () => {
      const result = extractServiceModuleFields({})
      expect(result.smCode).toBe('')
      expect(result.smName).toBe('')
      expect(result.domain).toBe('')
      expect(result.subDomain).toBe('')
    })

    it('业务对象编码不应该被误提取为服务模块编码', () => {
      const row = {
        '业务对象编码': 'BO001',
        '服务模块编码': 'SM001'
      }
      const result = extractServiceModuleFields(row)
      expect(result.smCode).toBe('SM001')
    })

    it('服务模块编码字段不应该被误提取为名称', () => {
      const row = {
        '服务模块编码': 'SM001',
        '服务模块名称': '名称'
      }
      const result = extractServiceModuleFields(row)
      expect(result.smName).toBe('名称')
    })
  })

  describe('extractBusinessObjectFields', () => {
    it('应该提取业务对象字段', () => {
      const row = {
        '业务对象编码': 'BO001',
        '业务对象名称': '采购申请',
        '领域': '供应链云',
        '子领域': '采购',
        '服务模块': 'SM001'
      }
      const result = extractBusinessObjectFields(row)
      expect(result.boCode).toBe('BO001')
      expect(result.boName).toBe('采购申请')
      expect(result.domain).toBe('供应链云')
      expect(result.subDomain).toBe('采购')
      expect(result.serviceModule).toBe('SM001')
    })

    it('应该支持英文字段名', () => {
      const row = {
        'businessObjectCode': 'BO002',
        'businessObjectName': '销售订单',
        'domain': '营销云',
        'subDomain': '销售',
        'serviceModule': 'SM002'
      }
      const result = extractBusinessObjectFields(row)
      expect(result.boCode).toBe('BO002')
      expect(result.boName).toBe('销售订单')
      expect(result.serviceModule).toBe('SM002')
    })

    it('应该支持下划线字段名', () => {
      const row = {
        'bo_code': 'BO003',
        'bo_name': '库存查询',
        'domain': '供应链云',
        'subDomain': '库存',
        'sm': 'SM003'
      }
      const result = extractBusinessObjectFields(row)
      expect(result.boCode).toBe('BO003')
      expect(result.boName).toBe('库存查询')
      expect(result.serviceModule).toBe('SM003')
    })

    it('空对象应该返回空值', () => {
      const result = extractBusinessObjectFields({})
      expect(result.boCode).toBe('')
      expect(result.boName).toBe('')
      expect(result.domain).toBe('')
      expect(result.subDomain).toBe('')
      expect(result.serviceModule).toBe('')
    })
  })

  describe('extractRelationshipFields', () => {
    it('应该提取关系字段', () => {
      const row = {
        '源业务对象编码': 'BO001',
        '目标业务对象编码': 'BO002',
        '关系编码': 'REL001',
        '关系类型': '依赖',
        '描述': '描述信息'
      }
      const result = extractRelationshipFields(row)
      expect(result.sourceCode).toBe('BO001')
      expect(result.targetCode).toBe('BO002')
      expect(result.relationCode).toBe('REL001')
      expect(result.relationType).toBe('依赖')
      expect(result.description).toBe('描述信息')
    })

    it('应该支持英文字段名', () => {
      const row = {
        'sourceBusinessObjectCode': 'BO001',
        'targetBusinessObjectCode': 'BO002',
        'relationshipCode': 'REL001',
        'relationshipType': '关联',
        'description': '英文描述'
      }
      const result = extractRelationshipFields(row)
      expect(result.sourceCode).toBe('BO001')
      expect(result.targetCode).toBe('BO002')
      expect(result.relationCode).toBe('REL001')
      expect(result.relationType).toBe('关联')
      expect(result.description).toBe('英文描述')
    })

    it('应该支持下划线字段名', () => {
      const row = {
        'source': 'BO001',
        'target': 'BO002',
        'relation_code': 'REL001',
        'relation_type': '包含',
        'desc': '下划线描述'
      }
      const result = extractRelationshipFields(row)
      expect(result.sourceCode).toBe('BO001')
      expect(result.targetCode).toBe('BO002')
      expect(result.relationCode).toBe('REL001')
      expect(result.relationType).toBe('包含')
      expect(result.description).toBe('下划线描述')
    })

    it('空对象应该返回空值', () => {
      const result = extractRelationshipFields({})
      expect(result.sourceCode).toBe('')
      expect(result.targetCode).toBe('')
      expect(result.relationCode).toBe('')
      expect(result.relationType).toBe('')
      expect(result.description).toBe('')
    })

    it('应该支持说明字段', () => {
      const row = { '说明': '说明内容' }
      const result = extractRelationshipFields(row)
      expect(result.description).toBe('说明内容')
    })
  })
})
