## 目录

1. [一、项目现状分析](#一-项目现状分析)
2. [二、可测试模块分析](#二-可测试模块分析)
3. [三、测试用例设计](#三-测试用例设计)
4. [四、测试数据管理](#四-测试数据管理)
5. [五、实施计划](#五-实施计划)
6. [六、CI/CD 集成](#六-cicd-集成)
7. [七、测试最佳实践](#七-测试最佳实践)
8. [八、测试覆盖率目标](#八-测试覆盖率目标)
9. [九、针对本次 Bug 修复的测试建议](#九-针对本次-bug-修复的测试建议)
10. [十、总结与建议](#十-总结与建议)
11. [十一、重构对测试的影响与应对策略](#十一-重构对测试的影响与应对策略)

---
# 自动化测试策略与实施方案

> 创建日期：2026-04-16
> 状态：待评审

---

## 一、项目现状分析

### 1.1 现有测试基础设施

| 项目 | 现状 | 说明 |
|------|------|------|
| 测试框架 | ⚠️ 部分配置 | 测试文件中导入了 Vitest，但 **未配置** |
| 测试脚本 | ❌ 缺失 | `package.json` 中没有 `test` 脚本 |
| Vitest 配置 | ❌ 缺失 | 没有 `vitest.config.js` |
| 已有测试 | ✅ 1 个 | `GroupModel.test.js` (268 行，覆盖 9 个场景) |
| 测试工具 | ✅ Vitest | 已在 `GroupModel.test.js` 中使用 |

### 1.2 项目技术栈

```
Vue 3.5 + Composition API
Vite 6 (构建工具)
Pinia 3 (状态管理)
Vitest (测试框架 - 待配置)
SheetJS (Excel 解析)
Mermaid 11 (图表渲染)
ELK Layout (布局算法)
```

---

## 二、可测试模块分析

### 2.1 高价值测试模块（纯函数、无副作用）

| 模块 | 文件 | 测试价值 | 复杂度 | 依赖 |
|------|------|---------|--------|------|
| **GroupModel** | `services/groupModel/GroupModel.js` | ⭐⭐⭐⭐⭐ | 中 | 无外部依赖 |
| **ColorCalculator** | `services/groupModel/ColorCalculator.js` | ⭐⭐⭐⭐⭐ | 低 | 无外部依赖 |
| **dataValidator** | `services/dataValidator.js` | ⭐⭐⭐⭐⭐ | 中 | 无外部依赖 |
| **useMermaidColors** | `composables/useMermaid/color/useMermaidColors.js` | ⭐⭐⭐⭐ | 低 | 无外部依赖 |
| **safetyUtils** | `services/groupModel/safetyUtils.js` | ⭐⭐⭐⭐ | 低 | 无外部依赖 |
| **chartTypeConfig** | `services/groupModel/chartTypeConfig.js` | ⭐⭐⭐ | 低 | 无外部依赖 |
| **relationClassifier** | `services/relationClassifier.js` | ⭐⭐⭐ | 中 | 无外部依赖 |

### 2.2 中等价值测试模块（部分纯函数）

| 模块 | 文件 | 测试价值 | 说明 |
|------|------|---------|------|
| **excelParser** | `services/excelParser.js` | ⭐⭐⭐ | `parseServiceModules()`、`parseBusinessObjects()`、`parseRelationships()` 是纯函数，可测试 |
| **dataTransformer** | `services/dataTransformer.js` | ⭐⭐⭐ | 数据转换逻辑可测试 |
| **architectureProcessor** | `services/groupModel/architectureProcessor.js` | ⭐⭐⭐ | 分组构建逻辑可测试 |

### 2.3 需模拟依赖的模块

| 模块 | 文件 | 测试难度 | 说明 |
|------|------|---------|------|
| **useServiceModuleSyntax** | `composables/.../useServiceModuleSyntax.js` | 中 | 需模拟 `getColors()`、`useBlockDiagramStyle()` |
| **useBusinessObjectSyntax** | `composables/.../useBusinessObjectSyntax.js` | 中 | 需模拟颜色函数 |
| **UnifiedRenderer** | `services/groupModel/UnifiedRenderer.js` | 中 | 需模拟 GroupModel |
| **diagramDataBuilder** | `services/diagramDataBuilder.js` | 中 | 需模拟多个依赖 |
| **serviceModuleDiagramBuilder** | `services/serviceModuleDiagramBuilder.js` | 中 | 需模拟多个依赖 |

### 2.4 暂不推荐测试的模块

| 模块 | 说明 |
|------|------|
| **Vue 组件** | 需额外配置 Vue Test Utils，ROI 较低 |
| **Pinia Stores** | 需配置 Pinia Testing Library |
| **MermaidComponent** | 依赖浏览器环境和 Mermaid 库 |
| **useInteraction** | 依赖 DOM 操作和事件系统 |
| **useSvgProcessor** | 依赖 DOM 操作 |

---

## 三、测试用例设计

### 3.1 GroupModel 测试扩展（已有基础）

**当前覆盖**：✅ 9 个测试场景，268 行代码

**建议补充**：

```javascript
// 1. 边界条件测试
describe('边界条件', () => {
  it('空数组应该正常工作')
  it('单节点树应该正常工作')
  it('深层嵌套应该正常工作')
  it('循环引用应该被检测')
})

// 2. mergeUserGroup 扩展测试
describe('mergeUserGroup 扩展', () => {
  it('应该支持通过 title 匹配')
  it('应该支持通过 elementCode 匹配')
  it('嵌套 children 应该被递归合并')
  it('缺失字段不应该覆盖原有值')
})

// 3. 缓存机制测试（已有部分）
describe('缓存失效', () => {
  it('updateEnabled 应该清除缓存')
  it('updateDirection 应该清除缓存')
  it('更新 children 应该清除缓存')
})
```

### 3.2 ColorCalculator 测试

```javascript
// test file: src/services/groupModel/__tests__/ColorCalculator.test.js

describe('ColorCalculator.compute', () => {
  describe('基本功能', () => {
    it('应该为每个分组分配唯一颜色')
    it('相同分组应该使用相同颜色')
    it('应该尊重 colorScheme 配置')
  })

  describe('colorGroupBy 分组', () => {
    it('按 domain 分组应该正确')
    it('按 subDomain 分组应该正确')
    it('按 serviceModule 分组应该正确')
    it('未知分组键应该使用默认值')
  })

  describe('centerScopeHighlight', () => {
    it('启用时中心节点应该使用 centerScopeColor')
    it('禁用时中心节点应该使用普通颜色')
    it('非中心节点不受影响')
  })

  describe('customColors', () => {
    it('应该优先使用 customColors')
    it('未定义的分组应该回退到默认颜色')
  })

  describe('边界条件', () => {
    it('空 nodes 应该返回空结果')
    it('重复分组应该只分配一次颜色')
    it('超出配色数量应该循环')
  })
})
```

### 3.3 dataValidator 测试

```javascript
// test file: src/services/__tests__/dataValidator.test.js

describe('validateData', () => {
  describe('外键校验', () => {
    it('应该检测服务模块引用的无效领域')
    it('应该检测业务对象引用的无效服务模块')
    it('应该检测关系中的无效源业务对象')
    it('应该检测关系中的无效目标业务对象')
  })

  describe('必填项校验', () => {
    it('应该检测缺失的必填字段')
    it('应该正确识别空字符串和 null')
  })

  describe('重复校验', () => {
    it('应该检测重复的服务模块编码')
    it('应该检测重复的业务对象编码')
    it('应该检测重复的关系')
  })

  describe('汇总生成', () => {
    it('应该正确统计 error 数量')
    it('应该正确统计 warning 数量')
    it('应该正确统计 info 数量')
  })
})
```

### 3.4 useMermaidColors 测试

```javascript
// test file: src/composables/useMermaid/color/__tests__/useMermaidColors.test.js

describe('getColors', () => {
  it('应该返回正确的颜色数量')
  it('default 方案应该包含正确的颜色')
  it('vibrant 方案应该包含正确的颜色')
})

describe('assignColorsToGroups', () => {
  it('应该为每个分组分配颜色')
  it('相同分组应该使用相同颜色')
  it('应该尊重 groupOrder')
})

describe('getLinkColor', () => {
  it('两端都在中心范围应该使用源节点颜色')
  it('源在中心范围应该使用目标节点颜色')
  it('两端都不在中心范围应该使用默认颜色')
})
```

### 3.5 excelParser 测试

```javascript
// test file: src/services/__tests__/excelParser.test.js

describe('parseServiceModules', () => {
  it('应该正确提取服务模块信息')
  it('应该构建正确的 moduleHierarchy')
  it('应该处理重复的服务模块编码')
  it('应该处理缺失字段')
})

describe('parseBusinessObjects', () => {
  it('应该正确提取业务对象信息')
  it('应该正确关联服务模块')
  it('应该处理缺失的服务模块')
})

describe('parseRelationships', () => {
  it('应该正确提取关系信息')
  it('应该正确识别双向关系')
  it('应该处理自引用关系')
})

describe('Sheet 识别', () => {
  it('应该通过名称识别业务对象 Sheet')
  it('应该通过名称识别服务模块 Sheet')
  it('应该通过名称识别关系 Sheet')
  it('应该通过内容识别未命名 Sheet')
})
```

---

## 四、测试数据管理

### 4.1 测试数据文件结构

```
src/
├── services/
│   ├── groupModel/
│   │   └── __tests__/
│   │       ├── GroupModel.test.js
│   │       ├── ColorCalculator.test.js
│   │       └── fixtures/           # 测试数据
│   │           ├── simple-hierarchy.js
│   │           ├── multi-level-hierarchy.js
│   │           └── disabled-groups.js
│   └── __tests__/
│       ├── dataValidator.test.js
│       ├── excelParser.test.js
│       └── fixtures/               # 测试数据
│           ├── valid-excel-data.js
│           ├── invalid-excel-data.js
│           └── relationships-data.js
├── composables/
│   └── useMermaid/
│       ├── color/
│       │   └── __tests__/
│       │       └── useMermaidColors.test.js
│       └── syntax/
│           └── __tests__/
│               └── fixtures/
│                   ├── bo-syntax-input.js
│                   └── sm-syntax-input.js
└── __fixtures__/                   # 共享测试数据
    ├── domain-products.js
    ├── business-objects.js
    └── relationships.js
```

### 4.2 测试数据结构示例

```javascript
// src/__fixtures__/domain-products.js
export const validDomainProducts = {
  domains: [
    {
      name: '供应链云',
      modules: [
        {
          name: '采购供应',
          submodules: [
            { code: 'PR', name: '采购管理', businessObjects: [] },
            { code: 'SRM', name: '供应商管理', businessObjects: [] }
          ]
        }
      ]
    }
  ]
}

export const emptyDomainProducts = { domains: [] }
```

---

## 五、实施计划

### 5.1 第一阶段：配置测试基础设施（1天）

**目标**：让测试能够运行

**任务**：

1. 安装 Vitest 依赖
```bash
npm install -D vitest @vue/test-utils happy-dom
```

2. 创建 `vitest.config.js`
```javascript
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/services/**/*.js', 'src/composables/useMermaid/**/*.js']
    }
  }
})
```

3. 更新 `package.json` 脚本
```json
{
  "scripts": {
    "test": "vitest",
    "test:run": "vitest run",
    "test:coverage": "vitest run --coverage",
    "test:watch": "vitest --watch"
  }
}
```

4. 添加 Vitest 全局类型声明
```javascript
// src/vitest-setup.js
import { vi } from 'vitest'
```

**验收标准**：
- `npm run test:run` 能执行现有测试
- 测试覆盖率能正常生成

---

### 5.2 第二阶段：补充 GroupModel 测试（2天）

**目标**：提高核心模块的测试覆盖率

**任务**：

1. 补充边界条件测试（15个用例）
2. 补充 mergeUserGroup 测试（10个用例）
3. 补充缓存机制测试（5个用例）

**预期覆盖率**：从 60% → 85%

---

### 5.3 第三阶段：添加 ColorCalculator 测试（1天）

**目标**：验证颜色分配逻辑

**任务**：

1. 创建 `ColorCalculator.test.js`
2. 测试基本颜色分配
3. 测试 centerScopeHighlight 逻辑
4. 测试 customColors 覆盖
5. 测试边界条件

**预期覆盖率**：0% → 90%

---

### 5.4 第四阶段：添加 dataValidator 测试（1天）

**目标**：验证数据校验逻辑

**任务**：

1. 创建 `dataValidator.test.js`
2. 测试各类校验逻辑
3. 测试汇总生成

**预期覆盖率**：0% → 80%

---

### 5.5 第五阶段：添加 useMermaidColors 测试（0.5天）

**目标**：验证颜色工具函数

**任务**：

1. 创建 `useMermaidColors.test.js`
2. 测试颜色分配函数

---

### 5.6 第六阶段：添加 excelParser 测试（1天）

**目标**：验证 Excel 解析逻辑

**任务**：

1. 创建 `excelParser.test.js`
2. 测试数据提取函数
3. 测试 Sheet 识别逻辑

**预期覆盖率**：0% → 70%

---

### 5.7 时间估算

| 阶段 | 工作量 | 累计 |
|------|--------|------|
| 第一阶段：配置基础设施 | 1 人天 | 1 人天 |
| 第二阶段：GroupModel 测试 | 2 人天 | 3 人天 |
| 第三阶段：ColorCalculator 测试 | 1 人天 | 4 人天 |
| 第四阶段：dataValidator 测试 | 1 人天 | 5 人天 |
| 第五阶段：useMermaidColors 测试 | 0.5 人天 | 5.5 人天 |
| 第六阶段：excelParser 测试 | 1 人天 | 6.5 人天 |
| **总计** | **6.5 人天** | - |

---

## 六、CI/CD 集成

### 6.1 GitHub Actions 配置

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run tests
        run: npm run test:coverage
      
      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage/
      
      - name: Comment coverage
        uses: romeovs/lcov-reporter-action@v0.3.1
        with:
          lcov-file: coverage/lcov.info
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### 6.2 测试门禁规则

建议配置：

```yaml
# 最低测试覆盖率要求
coverage:
  global: 60%
  services: 70%
  composables: 50%
  
# 禁止合并的条件
- 任何新测试用例失败
- 测试覆盖率低于门槛
- 测试运行时间超过 5 分钟
```

---

## 七、测试最佳实践

### 7.1 命名规范

```javascript
// 测试文件
ModuleName.test.js

// 测试描述
describe('模块名', () => {
  describe('功能分组', () => {
    it('应该 [预期行为]', () => { ... })
  })
})
```

### 7.2 测试结构

```javascript
describe('模块', () => {
  // 1. Setup
  let calculator
  
  beforeEach(() => {
    calculator = new ColorCalculator()
  })
  
  // 2. Subject under test
  describe('核心功能', () => {
    it('应该...', () => { ... })
  })
  
  // 3. Edge cases
  describe('边界条件', () => {
    it('空输入应该...', () => { ... })
  })
  
  // 4. Error handling
  describe('错误处理', () => {
    it('无效输入应该抛出错误', () => { ... })
  })
})
```

### 7.3 Mock 使用

```javascript
import { vi } from 'vitest'

// Mock 外部依赖
vi.mock('../../../services/groupModel/ColorCalculator.js', () => ({
  ColorCalculator: {
    compute: vi.fn()
  }
}))

// Mock 控制台日志（保持输出清洁）
vi.spyOn(console, 'log').mockImplementation(() => {})
vi.spyOn(console, 'warn').mockImplementation(() => {})
```

### 7.4 测试数据管理

```javascript
// 使用工厂函数生成测试数据
function createMockGroup(overrides = {}) {
  return {
    id: 'test-group',
    title: '测试分组',
    layout: { enabled: true, direction: 'TB' },
    children: [],
    ...overrides
  }
}

// 使用 fixtures 共享数据
import { validDomainProducts } from '../__fixtures__/domain-products.js'
```

---

## 八、测试覆盖率目标

### 8.1 覆盖率指标

| 模块 | 当前覆盖率 | 目标覆盖率 | 关键文件 |
|------|----------|-----------|---------|
| **GroupModel** | ~60% | 85% | GroupModel.js |
| **ColorCalculator** | 0% | 90% | ColorCalculator.js |
| **dataValidator** | 0% | 80% | dataValidator.js |
| **useMermaidColors** | 0% | 80% | useMermaidColors.js |
| **safetyUtils** | 0% | 90% | safetyUtils.js |
| **excelParser** | 0% | 70% | excelParser.js |
| **架构层汇总** | **~15%** | **80%** | - |

### 8.2 覆盖率报告

建议使用 `vitest --coverage` 生成 HTML 覆盖率报告：

```
coverage/
├── index.html          # 概览页面
├── lcov.info          # LCOV 格式（CI 使用）
└── clover.xml         # Clover 格式
```

---

## 九、针对本次 Bug 修复的测试建议

### 9.1 已修复 Bug 的测试用例

```javascript
// Bug 1: 关系统计回退问题
describe('displayStats.objectRelations', () => {
  it('没有关系选择时应该为 0', () => {
    const stats = useDiagramData()
    stats.selectedRelationNodeIds.value = []
    expect(stats.displayStats.value.config.objectRelations).toBe(0)
  })
  
  it('有关系选择时应该显示选中数量', () => {
    const stats = useDiagramData()
    stats.selectedRelationNodeIds.value = ['rel1', 'rel2']
    expect(stats.displayStats.value.config.objectRelations).toBe(2)
  })
})

// Bug 2: Legend groupKey 计算
describe('buildColorLegendData', () => {
  it('serviceModule 分组应该使用 serviceModuleName', () => {
    const nodes = [{ code: 'BO1', serviceModuleName: '采购供应', serviceModule: 'CG' }]
    const legend = buildColorLegendData({ nodes, colorGroupBy: 'serviceModule' })
    expect(legend.items[0].name).toBe('采购供应') // 不是 'CG'
  })
})

// Bug 3: SM 图 nodeColorMappings
describe('useServiceModuleSyntax.generateMermaidCode', () => {
  it('应该返回 nodeColorMappings', () => {
    const result = generateMermaidCode(mockData)
    expect(result.nodeColorMappings).toBeDefined()
    expect(result.nodeColorMappings.length).toBeGreaterThan(0)
  })
})
```

### 9.2 回归测试策略

```javascript
// src/__tests__/regression/
describe('Regression: 2026-04-16', () => {
  describe('关系统计不显示零值', () => {
    it('未选关系时类型步骤应显示 0', () => { ... })
    it('未选关系时配置步骤应显示 0', () => { ... })
  })
  
  describe('Legend 显示正确分组', () => {
    it('BO 图按服务模块分组应显示名称', () => { ... })
    it('SM 图 Legend 应正常显示', () => { ... })
  })
})
```

---

## 十、总结与建议

### 10.1 实施优先级

| 优先级 | 任务 | ROI | 风险 |
|--------|------|-----|------|
| **P0** | 配置 Vitest 环境 | ⭐⭐⭐⭐⭐ | 低 |
| **P1** | GroupModel 测试补充 | ⭐⭐⭐⭐⭐ | 低 |
| **P1** | ColorCalculator 测试 | ⭐⭐⭐⭐ | 低 |
| **P2** | dataValidator 测试 | ⭐⭐⭐ | 低 |
| **P2** | useMermaidColors 测试 | ⭐⭐⭐ | 低 |
| **P3** | excelParser 测试 | ⭐⭐ | 中 |

### 10.2 关键成功因素

1. **领导支持**：确保测试工作纳入开发流程
2. **持续集成**：每次 PR 必须通过测试
3. **覆盖率门禁**：设置最低覆盖率门槛
4. **测试质量**：重视测试质量而非数量
5. **定期回顾**：每月回顾测试覆盖率和测试有效性

### 10.3 预期收益

1. **防止 Bug 复发**：今天的三个 Bug 通过测试验证
2. **提高重构信心**：重构 GroupModel 和 ColorCalculator 时有安全网
3. **文档价值**：测试是最好的接口文档
4. **开发效率**：快速发现回归问题，减少调试时间
5. **技术债务减少**：逐步提高代码质量

---

## 十一、重构对测试的影响与应对策略

### 11.1 重构计划概览

根据 `unified-model-refactor-plan.md` 和 `data-model-and-color-system-analysis.md`，有以下重构计划：

#### 重构路线图

| Phase | 重构内容 | 风险 | 影响范围 |
|-------|---------|------|---------|
| **Phase 1** | containers vs children 统一 | 低 | GroupModel, architectureProcessor |
| **Phase 2** | 统一 COLOR_SCHEMES | 低 | ColorCalculator, useMermaidColors, 所有使用颜色的地方 |
| **Phase 3** | 统一 groupKey 计算 | 低 | ColorCalculator, useSvgProcessor |
| **Phase 4** | 清理 UnifiedRenderer 死代码 | 中 | UnifiedRenderer, useDiagramData |
| **Phase 5** | 统一节点数据模型 | 高 | GroupModel, diagramDataBuilder, serviceModuleDiagramBuilder |
| **Phase 6** | UI 层统一 | 低 | CenterDomainSelect, ServiceModuleConfig |

### 11.2 各重构对测试的影响分析

#### Phase 1: containers vs children 统一（低风险）

**影响范围**：
- `GroupModel.buildIndex()`
- `GroupModel.mergeUserGroup()`
- `GroupItem.vue` 渲染逻辑

**测试影响**：
```
✅ 影响较小
- GroupModel 核心逻辑不变，只是数据位置改变
- 现有测试验证的是逻辑，不是数据结构
```

**需要更新的测试**：
- `GroupModel.test.js` 中涉及 containers 的测试用例可能需要调整断言
- 如果测试用例验证了 `group.containers` vs `group.children`，需要更新

**应对策略**：
1. 先更新测试，明确期望的数据结构
2. 重构后运行测试，确保逻辑行为不变

---

#### Phase 2: 统一 COLOR_SCHEMES（低风险）

**影响范围**：
- `ColorCalculator.js`
- `useMermaidColors.js`
- 所有配置文件

**测试影响**：
```
✅ 影响较小
- 测试验证的是分配逻辑，不是具体颜色值
- 只要颜色数量和分配顺序不变，测试仍然通过
```

**需要更新的测试**：
- 可能需要更新期望的颜色数量（从 8 色改为 30 色）
- 循环分配测试的断言需要调整

**应对策略**：
1. 将 COLOR_SCHEMES 提取到常量文件
2. 测试使用常量引用，而非硬编码期望值
3. 添加颜色数量验证测试

```javascript
// ✅ 好的测试方式
import { COLOR_SCHEMES } from '../../../constants/colorSchemes.js'

it('应该使用所有可用颜色', () => {
  expect(COLOR_SCHEMES.default.length).toBeGreaterThanOrEqual(groups.length)
})

// ❌ 脆弱的测试方式
it('应该有 8 种颜色', () => {
  expect(colors.length).toBe(8) // 重构后可能变成 30 色
})
```

---

#### Phase 3: 统一 groupKey 计算（低风险）

**影响范围**：
- `ColorCalculator.getGroupKey()`
- `useSvgProcessor.buildColorLegendData()`
- `useMermaidColors.assignColorsToGroups()`

**测试影响**：
```
✅ 影响较小
- 测试验证的是分组结果，不是实现方式
- 今天的 Bug 修复已经包含在 groupKey 逻辑中
```

**需要更新的测试**：
- 如果有直接测试 groupKey 函数的用例，需要更新
- 今天添加的回归测试应该保留

**应对策略**：
1. 将 `getGroupKey()` 提取为独立工具函数并测试
2. 回归测试确保 Bug 不再复发

---

#### Phase 4: 清理 UnifiedRenderer 死代码（中风险）

**影响范围**：
- `UnifiedRenderer.js`
- `useDiagramData.js` 中的 UnifiedRenderer 调用路径

**测试影响**：
```
⚠️ 影响中等
- 如果统一渲染路径被废弃，相关测试可能需要移除
- 如果保留，需要确保核心功能被覆盖
```

**需要决策**：
1. **方案 A**：保留 UnifiedRenderer，添加测试
2. **方案 B**：废弃 UnifiedRenderer，移除相关测试

**应对策略**：
1. 先评估 UnifiedRenderer 的使用情况
2. 如果废弃，标记相关代码为 `@deprecated`
3. 运行测试，找出实际使用的功能
4. 补充缺失功能的测试到主渲染路径

---

#### Phase 5: 统一节点数据模型（高风险）

**影响范围**：
- 节点 ID 策略（`bo.name` → `bo.code`）
- 节点 color 计算时机（语法层 → 构建层）
- `isCenter` 计算时机
- `nodeColorMappings` 结构

**测试影响**：
```
❌ 影响较大
- 多个模块的测试需要大量更新
- 涉及今天的三个 Bug 的测试用例
- 可能影响 30-40% 的测试用例
```

**需要更新的测试**：

```javascript
// 影响 1: 节点 ID 变化
// ❌ 旧测试
it('节点 ID 应该是名称', () => {
  expect(node.id).toBe(node.name)
})
// ✅ 新测试
it('节点 ID 应该是编码', () => {
  expect(node.id).toBe(node.code)
})

// 影响 2: color 字段存在性
// ❌ 旧测试
it('节点不应该有 color 字段', () => {
  expect(node.color).toBeUndefined()
})
// ✅ 新测试
it('节点应该有 color 字段', () => {
  expect(node.color).toBeDefined()
})

// 影响 3: isCenter 计算方式
// ❌ 旧测试
it('isCenter 应该从上游传入', () => {
  expect(node.isCenter).toBe(diagramData.isCenter)
})
// ✅ 新测试
it('isCenter 应该在构建层计算', () => {
  expect(node.isCenter).toBe(centerScopeHighlight && centerCodes.has(node.code))
})
```

**应对策略**：

1. **增量式重构**：
   - 先统一数据模型定义（不影响逻辑）
   - 分步骤修改各模块
   - 每步都运行测试

2. **测试先行（Test-First）**：
   ```javascript
   // 重构前：先写期望的测试
   describe('统一节点数据模型', () => {
     it('节点 ID 应该是编码', () => { ... })
     it('节点应该包含 color 字段', () => { ... })
     it('节点应该包含 isCenter 字段', () => { ... })
   })
   
   // 重构：让代码通过测试
   ```

3. **API 兼容性层**：
   ```javascript
   // 提供兼容层，避免一次性大规模修改
   function getNodeId(node) {
     return node.id || node.name // 兼容新旧两种格式
   }
   ```

---

#### Phase 6: UI 层统一（低风险）

**影响范围**：
- `CenterDomainSelect.vue`
- `ServiceModuleConfig.vue`

**测试影响**：
```
⚠️ 暂不推荐测试 Vue 组件
- 建议先提取共享逻辑到 composable
- 对 composable 进行单元测试
```

**应对策略**：
1. 提取共享逻辑到 `useColorConfig.js`
2. 对 composable 进行单元测试
3. 组件通过手动测试验证

---

### 11.3 测试保护策略

#### 11.3.1 测试分层策略

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E 测试（手工/少量）                        │
│  - 端到端场景验证                                            │
│  - 重构保护                                                  │
└─────────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────────────────────────────────────────┐
│                    集成测试                                    │
│  - GroupModel + ColorCalculator                              │
│  - 验证模块间协作                                            │
└─────────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────────────────────────────────────────┐
│                    单元测试（重点）                           │
│  - GroupModel (85%)                                          │
│  - ColorCalculator (90%)                                    │
│  - dataValidator (80%)                                      │
│  - 纯函数、无外部依赖                                         │
└─────────────────────────────────────────────────────────────┘
```

#### 11.3.2 重构前检查清单

在执行每个 Phase 前，执行以下检查：

```bash
# 1. 运行现有测试
npm run test:run

# 2. 生成覆盖率基准
npm run test:coverage -- --output lcov.info
cp coverage/lcov.info coverage/baseline.lcov.info

# 3. 执行重构

# 4. 运行测试并对比覆盖率
npm run test:coverage
diff coverage/lcov.info coverage/baseline.lcov.info

# 5. 检查是否有测试失败
npm run test:run
```

#### 11.3.3 测试与重构并行计划

```
时间线 ─────────────────────────────────────────────────────►

Phase 1-3 (容器/颜色/groupKey)
├─ 测试工作：补充 ColorCalculator + useMermaidColors 测试
├─ 重构工作：执行 Phase 1-3
└─ 状态：✅ 低风险，测试影响小

     Phase 4 (UnifiedRenderer)
     ├─ 测试工作：评估 UnifiedRenderer 使用情况
     ├─ 重构工作：清理死代码
     └─ 状态：⚠️ 中风险，需谨慎

          Phase 5 (节点数据模型) ★ 高风险
          ├─ 测试工作：重构前先写测试
          ├─ 重构工作：增量式修改
          └─ 状态：❌ 高风险，需充分测试
```

### 11.4 推荐的测试执行顺序

为了最大化测试对重构的保护作用，建议：

#### 1. 立即执行（不依赖重构）

```bash
# 配置 Vitest 环境
npm install -D vitest @vue/test-utils happy-dom

# 创建 vitest.config.js
# 更新 package.json scripts

# 验证现有测试能运行
npm run test:run
```

#### 2. Phase 1-3 期间执行

```bash
# 补充 ColorCalculator 测试
# 补充 useMermaidColors 测试
# 执行 Phase 1-3 重构
# 运行测试验证
```

#### 3. Phase 4 期间执行

```bash
# 评估 UnifiedRenderer 使用情况
# 决定保留或废弃
# 添加/移除相关测试
```

#### 4. Phase 5 期间执行（最重要）

```bash
# 1. 先写期望的测试（测试先行）
# 2. 执行重构让测试通过
# 3. 逐步添加边界条件测试
# 4. 对比覆盖率，确保没有退化
```

### 11.5 测试与重构的收益平衡

| 策略 | 优点 | 缺点 |
|------|------|------|
| **测试先行** | 重构安全性最高 | 开发时间增加 30-50% |
| **重构先行** | 开发速度快 | 后期测试维护成本高 |
| **混合策略** | 平衡速度和安全 | 需要经验判断优先级 |

**建议**：对 Phase 5（高风险）采用测试先行，其他 Phase 采用重构先行 + 测试验证。

---

### 11.6 总结：重构与测试的关系

```
┌─────────────────────────────────────────────────────────────┐
│                        测试是重构的安全网                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  重构前 ──► 写测试 ──► 重构 ──► 测试验证 ──► 通过 ──► 完成     │
│     │         │          │         │          │            │
│     └─────────┴──────────┴─────────┴──────────┘            │
│                    （失败则回滚）                              │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  关键原则：                                                   │
│  1. 测试验证行为，不验证实现                                   │
│  2. 优先测试稳定的核心逻辑                                     │
│  3. 高风险重构采用测试先行                                     │
│  4. 保持测试与代码同步更新                                     │
└─────────────────────────────────────────────────────────────┘
```

**核心结论**：

1. **Phase 1-3 影响小**：可以先重构，再补充测试
2. **Phase 4 需要决策**：先决定 UnifiedRenderer 的命运
3. **Phase 5 影响大**：必须测试先行，逐步执行
4. **测试保护投资**：今天投入的测试工作，会在 Phase 5 时得到回报

---

*文档更新时间：2026-04-16（第三版 - 增加重构影响分析）*
