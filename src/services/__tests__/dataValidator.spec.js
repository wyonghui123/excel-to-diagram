/**
 * dataValidator 单元测试
 * 目标覆盖率: 95%+
 */

import { describe, it, expect } from 'vitest'
import {
  validateData,
  validateDomainSubDomainNames,
  groupBySheet,
  groupByLevel,
  ValidationLevel,
  ValidationType
} from '../dataValidator.js'

describe('dataValidator', () => {
  describe('常量定义', () => {
    it('ValidationLevel 应该包含所有级别', () => {
      expect(ValidationLevel.ERROR).toBe('error')
      expect(ValidationLevel.WARNING).toBe('warning')
      expect(ValidationLevel.INFO).toBe('info')
    })

    it('ValidationType 应该包含所有类型', () => {
      expect(ValidationType.FOREIGN_KEY).toBe('foreign_key')
      expect(ValidationType.REQUIRED).toBe('required')
      expect(ValidationType.DUPLICATE).toBe('duplicate')
      expect(ValidationType.FORMAT).toBe('format')
      expect(ValidationType.AI_CHECK).toBe('ai_check')
    })
  })

  describe('validateData', () => {
    it('当 rawData 为空时应该返回空结果', () => {
      const result = validateData(null, {})
      expect(result.items).toEqual([])
      expect(result.summary).toEqual({ total: 0, errors: 0, warnings: 0, infos: 0 })
    })

    it('当 rawData 未定义时应该返回空结果', () => {
      const result = validateData(undefined, {})
      expect(result.items).toEqual([])
      expect(result.summary).toEqual({ total: 0, errors: 0, warnings: 0, infos: 0 })
    })

    it('应该检测业务对象外键错误（引用了不存在的服务模块）', () => {
      const rawData = {
        serviceComponentData: [
          { '服务模块编码': 'SM001', '服务模块名称': '采购管理', '领域': '供应链云', '子领域': '采购' }
        ],
        businessObjectData: [
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请', '服务模块编码': 'SM999' }
        ]
      }
      const previewData = {
        serviceModules: [{ code: 'SM001', name: '采购管理' }]
      }

      const result = validateData(rawData, previewData)
      const fkErrors = result.items.filter(i => i.type === ValidationType.FOREIGN_KEY && i.sheet === '业务对象')
      expect(fkErrors.length).toBeGreaterThan(0)
      expect(fkErrors[0].level).toBe(ValidationLevel.ERROR)
      expect(fkErrors[0].message).toContain('SM999')
    })

    it('应该检测关系数据外键错误（源业务对象不存在）', () => {
      const rawData = {
        businessObjectData: [
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请' }
        ],
        relationshipData: [
          { '源业务对象编码': 'BO999', '目标业务对象编码': 'BO001', '关系编码': 'R001' }
        ]
      }
      const previewData = {
        businessObjects: [{ code: 'BO001', name: '采购申请' }]
      }

      const result = validateData(rawData, previewData)
      const fkErrors = result.items.filter(i =>
        i.type === ValidationType.FOREIGN_KEY &&
        i.sheet === '业务对象关系' &&
        i.field === '源业务对象编码'
      )
      expect(fkErrors.length).toBe(1)
      expect(fkErrors[0].level).toBe(ValidationLevel.ERROR)
    })

    it('应该检测关系数据外键错误（目标业务对象不存在）', () => {
      const rawData = {
        businessObjectData: [
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请' }
        ],
        relationshipData: [
          { '源业务对象编码': 'BO001', '目标业务对象编码': 'BO999', '关系编码': 'R001' }
        ]
      }
      const previewData = {
        businessObjects: [{ code: 'BO001', name: '采购申请' }]
      }

      const result = validateData(rawData, previewData)
      const fkErrors = result.items.filter(i =>
        i.type === ValidationType.FOREIGN_KEY &&
        i.sheet === '业务对象关系' &&
        i.field === '目标业务对象编码'
      )
      expect(fkErrors.length).toBe(1)
    })

    it('应该检测关系自关联警告', () => {
      const rawData = {
        businessObjectData: [
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请' }
        ],
        relationshipData: [
          { '源业务对象编码': 'BO001', '目标业务对象编码': 'BO001', '关系编码': 'R001' }
        ]
      }
      const previewData = {
        businessObjects: [{ code: 'BO001', name: '采购申请' }]
      }

      const result = validateData(rawData, previewData)
      const selfRef = result.items.find(i =>
        i.type === ValidationType.FOREIGN_KEY &&
        i.message.includes('相同')
      )
      expect(selfRef).toBeDefined()
      expect(selfRef.level).toBe(ValidationLevel.WARNING)
    })

    it('应该检测业务对象必填项缺失', () => {
      // 源码逻辑：当 boCode/boName 全部为空时才报 REQUIRED 错误
      const rawData = {
        businessObjectData: [
          {}  // 所有必填字段都缺失
        ]
      }
      const result = validateData(rawData, {})
      const requiredErrors = result.items.filter(i =>
        i.type === ValidationType.REQUIRED && i.sheet === '业务对象'
      )
      expect(requiredErrors.length).toBeGreaterThan(0)
      expect(requiredErrors[0].level).toBe(ValidationLevel.ERROR)
    })

    it('应该检测服务模块必填项缺失', () => {
      // 源码逻辑：当 smCode/smName 全部为空时才报 REQUIRED 错误
      const rawData = {
        serviceComponentData: [
          {}  // 所有必填字段都缺失
        ]
      }
      const result = validateData(rawData, {})
      const requiredErrors = result.items.filter(i =>
        i.type === ValidationType.REQUIRED && i.sheet === '服务模块'
      )
      expect(requiredErrors.length).toBeGreaterThan(0)
    })

    it('应该检测关系必填项缺失（源业务对象编码为空）', () => {
      const rawData = {
        relationshipData: [
          { '目标业务对象编码': 'BO001', '关系编码': 'R001' }
        ]
      }
      const result = validateData(rawData, {})
      const requiredErrors = result.items.filter(i =>
        i.type === ValidationType.REQUIRED &&
        i.sheet === '业务对象关系' &&
        i.field === '源业务对象编码'
      )
      expect(requiredErrors.length).toBe(1)
    })

    it('应该检测关系必填项缺失（目标业务对象编码为空）', () => {
      const rawData = {
        relationshipData: [
          { '源业务对象编码': 'BO001', '关系编码': 'R001' }
        ]
      }
      const result = validateData(rawData, {})
      const requiredErrors = result.items.filter(i =>
        i.type === ValidationType.REQUIRED &&
        i.sheet === '业务对象关系' &&
        i.field === '目标业务对象编码'
      )
      expect(requiredErrors.length).toBe(1)
    })

    it('应该检测业务对象编码重复', () => {
      const rawData = {
        businessObjectData: [
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请' },
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请2' }
        ]
      }
      const result = validateData(rawData, {})
      const dupErrors = result.items.filter(i =>
        i.type === ValidationType.DUPLICATE && i.sheet === '业务对象'
      )
      expect(dupErrors.length).toBe(1)
      expect(dupErrors[0].level).toBe(ValidationLevel.WARNING)
      expect(dupErrors[0].message).toContain('BO001')
    })

    it('应该检测服务模块编码重复', () => {
      const rawData = {
        serviceComponentData: [
          { '服务模块编码': 'SM001', '服务模块名称': '采购管理' },
          { '服务模块编码': 'SM001', '服务模块名称': '采购管理2' }
        ]
      }
      const result = validateData(rawData, {})
      const dupErrors = result.items.filter(i =>
        i.type === ValidationType.DUPLICATE && i.sheet === '服务模块'
      )
      expect(dupErrors.length).toBe(1)
    })

    it('应该正确生成汇总统计', () => {
      const rawData = {
        businessObjectData: [
          { '业务对象编码': 'BO001', '业务对象名称': '采购申请' }
        ],
        relationshipData: [
          { '源业务对象编码': 'BO999', '目标业务对象编码': 'BO001', '关系编码': 'R001' }
        ]
      }
      const previewData = {
        businessObjects: [{ code: 'BO001', name: '采购申请' }]
      }

      const result = validateData(rawData, previewData)
      expect(result.summary.total).toBe(result.items.length)
      // 源码使用单数 error/warning/info
      expect(result.summary.error).toBeGreaterThan(0)
      expect(result.summary.warning).toBeGreaterThanOrEqual(0)
      expect(result.summary.info).toBeGreaterThanOrEqual(0)
    })

    it('应该支持英文字段名', () => {
      const rawData = {
        serviceComponentData: [
          { 'smCode': 'SM001', 'smName': 'Procurement', 'domain': 'SC', 'subDomain': 'Purchasing' }
        ],
        businessObjectData: [
          { 'boCode': 'BO001', 'boName': 'Purchase Request', 'smCode': 'SM999' }
        ]
      }
      const previewData = {
        serviceModules: [{ code: 'SM001', name: 'Procurement' }]
      }

      const result = validateData(rawData, previewData)
      const fkErrors = result.items.filter(i => i.sheet === '业务对象')
      expect(fkErrors.length).toBeGreaterThan(0)
    })
  })

  describe('validateDomainSubDomainNames', () => {
    it('当领域和子领域名称相同时应该返回警告', () => {
      const rawData = {
        serviceComponentData: [
          {
            '领域': '项目云',
            '子领域': '项目云',
            '服务模块编码': 'SM001',
            '服务模块名称': '项目管理'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBeGreaterThan(0)
      expect(result[0].level).toBe(ValidationLevel.WARNING)
      expect(result[0].type).toBe(ValidationType.FORMAT)
      expect(result[0].message).toContain('项目云')
    })

    it('当领域和子领域名称不同时不应该返回警告', () => {
      const rawData = {
        serviceComponentData: [
          {
            '领域': '项目云',
            '子领域': '项目管理',
            '服务模块编码': 'SM001',
            '服务模块名称': '项目管理'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBe(0)
    })

    it('当服务模块数据为空时不应该返回警告', () => {
      const result = validateDomainSubDomainNames({ serviceComponentData: [] }, {})
      expect(result.length).toBe(0)
    })

    it('当服务模块数据未定义时不应该返回警告', () => {
      const result = validateDomainSubDomainNames({}, {})
      expect(result.length).toBe(0)
    })

    it('当领域为空时不应该返回警告', () => {
      const rawData = {
        serviceComponentData: [
          {
            '领域': '',
            '子领域': '项目管理',
            '服务模块编码': 'SM001',
            '服务模块名称': '项目管理'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBe(0)
    })

    it('当子领域为空时不应该返回警告', () => {
      const rawData = {
        serviceComponentData: [
          {
            '领域': '项目云',
            '子领域': '',
            '服务模块编码': 'SM001',
            '服务模块名称': '项目管理'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBe(0)
    })

    it('应该支持英文字段名变体', () => {
      const rawData = {
        serviceComponentData: [
          {
            'Domain': '财务云',
            'SubDomain': '财务云',
            'smCode': 'SM001',
            'smName': '财务分析'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBeGreaterThan(0)
      expect(result[0].message).toContain('财务云')
    })

    it('应该合并相同领域-子领域对只返回一条警告', () => {
      const rawData = {
        serviceComponentData: [
          {
            '领域': '项目云',
            '子领域': '项目云',
            '服务模块编码': 'SM001',
            '服务模块名称': '项目管理'
          },
          {
            '领域': '项目云',
            '子领域': '项目云',
            '服务模块编码': 'SM002',
            '服务模块名称': '项目计划'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBe(1)
      expect(result[0].entityCode).toBe('SM001')
    })

    it('应该支持子领域字段名 subDomain（camelCase）', () => {
      // 源码仅支持 camelCase 形式的 'subDomain'，不支持全小写 'subdomain'
      const rawData = {
        serviceComponentData: [
          {
            'domain': '项目云',
            'subDomain': '项目云',
            'smCode': 'SM001',
            'smName': '项目管理'
          }
        ]
      }

      const result = validateDomainSubDomainNames(rawData, {})
      expect(result.length).toBeGreaterThan(0)
    })
  })

  describe('groupBySheet', () => {
    it('应该按 Sheet 名称分组', () => {
      const items = [
        { sheet: '业务对象', message: '错误1' },
        { sheet: '业务对象', message: '错误2' },
        { sheet: '服务模块', message: '错误3' }
      ]

      const result = groupBySheet(items)
      expect(Object.keys(result)).toContain('业务对象')
      expect(Object.keys(result)).toContain('服务模块')
      expect(result['业务对象'].length).toBe(2)
      expect(result['服务模块'].length).toBe(1)
    })

    it('空数组应该返回空对象', () => {
      const result = groupBySheet([])
      expect(result).toEqual({})
    })
  })

  describe('groupByLevel', () => {
    it('应该按级别分组', () => {
      const items = [
        { level: ValidationLevel.ERROR, message: '错误1' },
        { level: ValidationLevel.ERROR, message: '错误2' },
        { level: ValidationLevel.WARNING, message: '警告1' },
        { level: ValidationLevel.INFO, message: '信息1' }
      ]

      const result = groupByLevel(items)
      expect(result.error.length).toBe(2)
      expect(result.warning.length).toBe(1)
      expect(result.info.length).toBe(1)
    })

    it('空数组应该返回空分组', () => {
      const result = groupByLevel([])
      expect(result.error).toEqual([])
      expect(result.warning).toEqual([])
      expect(result.info).toEqual([])
    })
  })
})
