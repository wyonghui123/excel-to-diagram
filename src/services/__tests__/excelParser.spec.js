/**
 * excelParser 单元测试
 * 目标覆盖率: 95%+
 * 适配 excelParser.js 的真实 API：parseExcelFile / parseServiceModules / parseBusinessObjects / parseRelationships / parseServiceModuleRelationships
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as XLSX from 'xlsx'
import {
  parseExcelFile,
  parseServiceModules,
  parseBusinessObjects,
  parseRelationships,
  parseServiceModuleRelationships
} from '../excelParser.js'

// Mock xlsx so parseExcelFile can run in happy-dom
vi.mock('xlsx', () => {
  return {
    read: vi.fn(),
    utils: {
      sheet_to_json: vi.fn()
    }
  }
})

// ---------------------------------------------------------------------------
// Helpers: build a fake workbook that the mocked xlsx.read / sheet_to_json
// can consume.
// ---------------------------------------------------------------------------
function buildWorkbook(sheetMap) {
  // sheetMap: { sheetName: [rowObj, ...] }
  const SheetNames = Object.keys(sheetMap)
  const Sheets = {}
  SheetNames.forEach(name => {
    Sheets[name] = { __rows: sheetMap[name] }
  })
  return { SheetNames, Sheets }
}

function setupXlsxMock(workbook, perSheetRowMap) {
  XLSX.read.mockReturnValue(workbook)
  XLSX.utils.sheet_to_json.mockImplementation(ws => ws?.__rows || [])
}

function makeMockFile(workbook) {
  return {
    name: 'test.xlsx',
    arrayBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8))
  }
}

// ---------------------------------------------------------------------------
// parseServiceModules
// ---------------------------------------------------------------------------
describe('parseServiceModules', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('构建 serviceModuleMap / moduleHierarchy / nameToCodeMap', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': '采购管理', '领域': '供应链云', '子领域': '采购' },
      { '服务模块编码': 'SM002', '服务模块名称': '库存管理', '领域': '供应链云', '子领域': '仓储' }
    ]
    const { serviceModuleMap, moduleHierarchy, nameToCodeMap } = parseServiceModules(scData)

    expect(serviceModuleMap.size).toBe(2)
    expect(serviceModuleMap.get('SM001').name).toBe('采购管理')
    expect(serviceModuleMap.get('SM001').domain).toBe('供应链云')
    expect(serviceModuleMap.get('SM001').subDomain).toBe('采购')
    expect(nameToCodeMap.get('采购管理')).toBe('SM001')
    expect(nameToCodeMap.get('库存管理')).toBe('SM002')

    expect(moduleHierarchy.size).toBe(1)
    const domainObj = moduleHierarchy.get('供应链云')
    expect(domainObj.name).toBe('供应链云')
    expect(domainObj.subDomains.size).toBe(2)
    expect(domainObj.subDomains.get('采购').serviceModules.length).toBe(1)
    expect(domainObj.subDomains.get('采购').serviceModules[0].code).toBe('SM001')
  })

  it('重复 smCode 只保留第一个', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': '采购A', '领域': 'X' },
      { '服务模块编码': 'SM001', '服务模块名称': '采购B', '领域': 'X' }
    ]
    const { serviceModuleMap, nameToCodeMap } = parseServiceModules(scData)
    expect(serviceModuleMap.size).toBe(1)
    // nameToCodeMap 也只设一次（第一个）
    expect(nameToCodeMap.get('采购A')).toBe('SM001')
    expect(nameToCodeMap.get('采购B')).toBeUndefined()
  })

  it('缺少 smCode 或 smName 的行被忽略', () => {
    const scData = [
      { '服务模块编码': 'SM001' /* no name */ },
      { '服务模块名称': '无名' /* no code */ },
      { '服务模块编码': 'SM002', '服务模块名称': '有名字的' }
    ]
    const { serviceModuleMap } = parseServiceModules(scData)
    expect(serviceModuleMap.size).toBe(1)
    expect(serviceModuleMap.get('SM002').name).toBe('有名字的')
  })

  it('空数组应该返回空的 map / hierarchy', () => {
    const { serviceModuleMap, moduleHierarchy, nameToCodeMap } = parseServiceModules([])
    expect(serviceModuleMap.size).toBe(0)
    expect(moduleHierarchy.size).toBe(0)
    expect(nameToCodeMap.size).toBe(0)
  })

  it('支持英文键名（sm_code / sm_name / domain）', () => {
    const scData = [
      { sm_code: 'SM100', sm_name: 'ModuleX', domain: 'CloudA' }
    ]
    const { serviceModuleMap } = parseServiceModules(scData)
    expect(serviceModuleMap.get('SM100').name).toBe('ModuleX')
    expect(serviceModuleMap.get('SM100').domain).toBe('CloudA')
  })

  it('支持中文键名（领域 / 子领域）', () => {
    const scData = [
      { '服务模块编码': 'SM200', '服务模块名称': '采购', '领域': '供应链云', '子领域': '采购' }
    ]
    const { serviceModuleMap, moduleHierarchy } = parseServiceModules(scData)
    expect(serviceModuleMap.get('SM200').name).toBe('采购')
    expect(serviceModuleMap.get('SM200').domain).toBe('供应链云')
    expect(serviceModuleMap.get('SM200').subDomain).toBe('采购')
    expect(moduleHierarchy.get('供应链云').subDomains.get('采购').serviceModules.length).toBe(1)
  })

  it('没有 domain 的行不进入 moduleHierarchy 但仍进入 serviceModuleMap', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': '孤儿', '领域': '' }
    ]
    const { serviceModuleMap, moduleHierarchy } = parseServiceModules(scData)
    expect(serviceModuleMap.size).toBe(1)
    expect(moduleHierarchy.size).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// parseBusinessObjects
// ---------------------------------------------------------------------------
describe('parseBusinessObjects', () => {
  beforeEach(() => vi.clearAllMocks())

  it('基于 serviceModule 编码关联并填充分组信息', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': '采购管理', '领域': '供应链云', '子领域': '采购' }
    ]
    const { serviceModuleMap, moduleHierarchy, nameToCodeMap } = parseServiceModules(scData)

    const boData = [
      { '业务对象编码': 'BO001', '业务对象名称': '采购申请', '服务模块': 'SM001' }
    ]
    const bos = parseBusinessObjects(boData, serviceModuleMap, moduleHierarchy, nameToCodeMap)

    expect(bos).toHaveLength(1)
    expect(bos[0]).toMatchObject({
      name: '采购申请',
      code: 'BO001',
      serviceModule: 'SM001',
      serviceModuleName: '采购管理',
      subDomain: '采购',
      domain: '供应链云'
    })
  })

  it('当 serviceModule 是名称而非编码时，通过 nameToCodeMap 解析', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': '采购管理', '领域': '供应链云', '子领域': '采购' }
    ]
    const { serviceModuleMap, moduleHierarchy, nameToCodeMap } = parseServiceModules(scData)

    const boData = [
      { '业务对象编码': 'BO001', '业务对象名称': '采购申请', '服务模块': '采购管理' }
    ]
    const bos = parseBusinessObjects(boData, serviceModuleMap, moduleHierarchy, nameToCodeMap)
    expect(bos[0].serviceModule).toBe('SM001')
    expect(bos[0].serviceModuleName).toBe('采购管理')
  })

  it('重复 boCode 只保留第一个', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': 'SM', '领域': 'D' }
    ]
    const { serviceModuleMap, moduleHierarchy, nameToCodeMap } = parseServiceModules(scData)

    const boData = [
      { '业务对象编码': 'BO001', '业务对象名称': 'A', '服务模块': 'SM001' },
      { '业务对象编码': 'BO001', '业务对象名称': 'B', '服务模块': 'SM001' }
    ]
    const bos = parseBusinessObjects(boData, serviceModuleMap, moduleHierarchy, nameToCodeMap)
    expect(bos).toHaveLength(1)
    expect(bos[0].name).toBe('A')
  })

  it('缺 boCode 或 boName 的行被忽略', () => {
    const bos = parseBusinessObjects(
      [{ '业务对象编码': 'BO001' /* no name */ }, { '业务对象名称': '无名' }],
      new Map(), new Map(), new Map()
    )
    expect(bos).toHaveLength(0)
  })

  it('空数据返回空数组', () => {
    expect(parseBusinessObjects([], new Map(), new Map(), new Map())).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// parseRelationships
// ---------------------------------------------------------------------------
describe('parseRelationships', () => {
  beforeEach(() => vi.clearAllMocks())

  it('基于 businessObjects 补全 sourceName/targetName', () => {
    const businessObjects = [
      { code: 'BO001', name: '采购申请' },
      { code: 'BO002', name: '采购订单' }
    ]
    const relData = [
      { '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002', '关系编码': 'R001', '描述': '关联' }
    ]
    const rels = parseRelationships(relData, businessObjects)

    expect(rels).toHaveLength(1)
    expect(rels[0]).toMatchObject({
      sourceCode: 'BO001',
      targetCode: 'BO002',
      sourceName: '采购申请',
      targetName: '采购订单',
      relationCode: 'R001',
      relationDesc: '关联'
    })
  })

  it('缺少 sourceCode 或 targetCode 的行被忽略', () => {
    const rels = parseRelationships(
      [
        { '源业务对象编码': 'BO001' },
        { '目标业务对象编码': 'BO002' },
        { '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002' }
      ],
      [{ code: 'BO001', name: 'A' }, { code: 'BO002', name: 'B' }]
    )
    expect(rels).toHaveLength(1)
  })

  it('未提供 relationCode 时自动生成 sourceCode-targetCode', () => {
    const rels = parseRelationships(
      [{ '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002' }],
      [{ code: 'BO001', name: 'A' }, { code: 'BO002', name: 'B' }]
    )
    expect(rels[0].relationCode).toBe('BO001-BO002')
  })

  it('空数据返回空数组', () => {
    expect(parseRelationships([], [])).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// parseServiceModuleRelationships
// ---------------------------------------------------------------------------
describe('parseServiceModuleRelationships', () => {
  beforeEach(() => vi.clearAllMocks())

  it('从业务对象关系推导服务模块关系', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': '采购', '领域': '供应链云' },
      { '服务模块编码': 'SM002', '服务模块名称': '订单', '领域': '供应链云' }
    ]
    const { serviceModuleMap } = parseServiceModules(scData)
    const businessObjects = [
      { code: 'BO001', name: '采购申请', serviceModule: 'SM001' },
      { code: 'BO002', name: '采购订单', serviceModule: 'SM002' }
    ]
    const relData = [
      { '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002', '关系编码': 'R1' }
    ]
    const smRels = parseServiceModuleRelationships(relData, serviceModuleMap, businessObjects)

    expect(smRels).toHaveLength(1)
    expect(smRels[0]).toMatchObject({
      sourceServiceModuleCode: 'SM001',
      targetServiceModuleCode: 'SM002',
      sourceServiceModuleName: '采购',
      targetServiceModuleName: '订单'
    })
    expect(smRels[0].businessObjectRelationshipCodes).toContain('R1')
  })

  it('同模块内的 BO 关系不产生服务模块关系', () => {
    const scData = [{ '服务模块编码': 'SM001', '服务模块名称': '采购', '领域': '供应链云' }]
    const { serviceModuleMap } = parseServiceModules(scData)
    const businessObjects = [
      { code: 'BO001', name: 'A', serviceModule: 'SM001' },
      { code: 'BO002', name: 'B', serviceModule: 'SM001' }
    ]
    const smRels = parseServiceModuleRelationships(
      [{ '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002' }],
      serviceModuleMap,
      businessObjects
    )
    expect(smRels).toEqual([])
  })

  it('BO 找不到所属服务模块时跳过该条关系', () => {
    const smRels = parseServiceModuleRelationships(
      [{ '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002' }],
      new Map(),
      []
    )
    expect(smRels).toEqual([])
  })

  it('多个 BO 关系合并到同一个服务模块关系 key', () => {
    const scData = [
      { '服务模块编码': 'SM001', '服务模块名称': 'A', '领域': 'X' },
      { '服务模块编码': 'SM002', '服务模块名称': 'B', '领域': 'X' }
    ]
    const { serviceModuleMap } = parseServiceModules(scData)
    const businessObjects = [
      { code: 'BO001', serviceModule: 'SM001' },
      { code: 'BO002', serviceModule: 'SM002' },
      { code: 'BO003', serviceModule: 'SM001' },
      { code: 'BO004', serviceModule: 'SM002' }
    ]
    const relData = [
      { '源业务对象编码': 'BO001', '目标业务对象编码': 'BO002', '关系编码': 'R1' },
      { '源业务对象编码': 'BO003', '目标业务对象编码': 'BO004', '关系编码': 'R2' }
    ]
    const smRels = parseServiceModuleRelationships(relData, serviceModuleMap, businessObjects)
    expect(smRels).toHaveLength(1)
    expect(smRels[0].businessObjectRelationshipCodes.sort()).toEqual(['R1', 'R2'])
  })
})

// ---------------------------------------------------------------------------
// parseExcelFile
// ---------------------------------------------------------------------------
describe('parseExcelFile', () => {
  beforeEach(() => vi.clearAllMocks())

  it('按 sheet 名分类：业务对象/服务/关系', async () => {
    const wb = buildWorkbook({
      '业务对象': [{ '业务对象编码': 'BO1', '业务对象名称': 'A' }],
      '服务模块': [{ '服务模块编码': 'SM1', '服务模块名称': 'S' }],
      // 避免使用 '业务对象关系'——会被 '业务对象' 分类优先匹配
      '关系': [{ '源业务对象编码': 'BO1', '目标业务对象编码': 'BO2' }]
    })
    setupXlsxMock(wb)
    const file = makeMockFile(wb)
    const result = await parseExcelFile(file)

    expect(result.businessObjectData).toHaveLength(1)
    expect(result.serviceComponentData).toHaveLength(1)
    expect(result.relationshipData).toHaveLength(1)
  })

  it('未知 sheet 名根据内容推断类型（source/target → 关系）', async () => {
    const wb = buildWorkbook({
      'random_sheet': [{ source_code: 'A', target_code: 'B' }]
    })
    setupXlsxMock(wb)
    const file = makeMockFile(wb)
    const result = await parseExcelFile(file)
    expect(result.relationshipData).toHaveLength(1)
    expect(result.businessObjectData).toHaveLength(0)
  })

  it('未知 sheet 含 service/domain 字段归类为服务', async () => {
    const wb = buildWorkbook({
      'misc': [{ service_code: 'SC1', service_name: 'svc' }]
    })
    setupXlsxMock(wb)
    const result = await parseExcelFile(makeMockFile(wb))
    expect(result.serviceComponentData).toHaveLength(1)
  })

  it('未知 sheet 默认归类为业务对象', async () => {
    const wb = buildWorkbook({
      'unknown_sheet': [{ foo: 1, bar: 2 }]
    })
    setupXlsxMock(wb)
    const result = await parseExcelFile(makeMockFile(wb))
    expect(result.businessObjectData).toHaveLength(1)
  })

  it('空 workbook 返回三个空数组', async () => {
    const wb = buildWorkbook({})
    setupXlsxMock(wb)
    const result = await parseExcelFile(makeMockFile(wb))
    expect(result).toEqual({
      businessObjectData: [],
      serviceComponentData: [],
      relationshipData: []
    })
  })

  it('空 sheet 数据不污染分类结果', async () => {
    const wb = buildWorkbook({
      '业务对象': [],
      '服务模块': [],
      '关系': []
    })
    setupXlsxMock(wb)
    const result = await parseExcelFile(makeMockFile(wb))
    expect(result.businessObjectData).toEqual([])
    expect(result.serviceComponentData).toEqual([])
    expect(result.relationshipData).toEqual([])
  })

  it('多 sheet 同类型会被合并到同一分类', async () => {
    const wb = buildWorkbook({
      '业务对象A': [{ '业务对象编码': 'B1' }],
      '业务对象B': [{ '业务对象编码': 'B2' }, { '业务对象编码': 'B3' }]
    })
    setupXlsxMock(wb)
    const result = await parseExcelFile(makeMockFile(wb))
    expect(result.businessObjectData).toHaveLength(3)
  })
})
