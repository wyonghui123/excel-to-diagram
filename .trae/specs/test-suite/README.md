# 测试套件

> **目标**: 为核心模块完备测试用例，确保产品质量
>
> **测试覆盖率目标**: 90%+

---

## 文档结构

```
test-suite/
├── README.md              # 测试套件总览
├── test-cases.md         # 测试用例规范
├── implementation-guide.md # 测试实现指南
└── test-checklist.md      # 测试用例清单
```

---

## 一、测试策略

### 1.1 测试金字塔

```
        ┌─────────────┐
        │   E2E测试   │   10个
        │  (用户视角)  │
        ├─────────────┤
        │  集成测试    │   20个
        │  (流程验证)  │
        ├─────────────┤
        │  组件测试    │   42个
        │  (交互验证)  │
        ├─────────────┤
        │   单元测试   │   102个
        │  (功能验证)  │
        └─────────────┘
```

### 1.2 测试原则

1. **快速反馈**: 单元测试优先，快速发现问题
2. **隔离性**: 每个测试独立，不依赖其他测试
3. **可重复**: 相同结果，CI/CD环境一致
4. **可维护**: 测试代码与业务代码同等重要
5. **覆盖率**: 核心模块90%+覆盖率

---

## 二、测试模块

### 2.1 单元测试 (Unit Tests)

**目标**: 验证每个函数/方法的独立功能

| 模块 | 文件位置 | 测试用例数 |
|------|---------|-----------|
| useMetaList | `tests/unit/composables/useMetaList.spec.js` | 70 |
| useImportExportApi | `tests/unit/composables/useImportExportApi.spec.js` | 32 |

**运行命令**:
```bash
npm run test:unit
```

### 2.2 组件测试 (Component Tests)

**目标**: 验证Vue组件的渲染和交互

| 组件 | 文件位置 | 测试用例数 |
|------|---------|-----------|
| ExportDialog | `tests/component/ExportDialog.spec.js` | 15 |
| ImportDialog | `tests/component/ImportDialog.spec.js` | 15 |
| TableHeaderFilter | `tests/component/TableHeaderFilter.spec.js` | 12 |

**运行命令**:
```bash
npm run test:component
```

### 2.3 集成测试 (Integration Tests)

**目标**: 验证多个组件/模块的协作

| 场景 | 文件位置 | 测试用例数 |
|------|---------|-----------|
| UserManagement | `tests/integration/UserManagement.spec.js` | 20 |

**运行命令**:
```bash
npm run test:integration
```

### 2.4 E2E测试 (End-to-End Tests)

**目标**: 验证完整的用户流程

| 场景 | 文件位置 | 测试用例数 |
|------|---------|-----------|
| 用户管理流程 | `tests/e2e/user-management.spec.js` | 10 |

**运行命令**:
```bash
npm run test:e2e
```

---

## 三、测试用例清单

详细测试用例请查看 [test-checklist.md](test-checklist.md)

### 3.1 useMetaList 测试用例 (70个)

#### 列表加载 (8个)
- ✅ 初始加载
- ✅ 加载成功/失败
- ✅ 加载状态
- ⬜ 空数据
- ⬜ 数据缓存
- ⬜ 手动/自动刷新

#### 分页功能 (12个)
- ✅ 跳转页面
- ✅ 改变pageSize
- ✅ 翻页重置
- ✅ 首页/末页/上一页/下一页
- ⬜ 快捷跳转
- ⬜ 每页条数选择

#### 过滤功能 (18个)
- ✅ 关键词搜索
- ✅ 表头过滤
- ✅ 日期范围
- ⬜ 多字段AND
- ⬜ 下拉过滤
- ⬜ 模糊/精确搜索
- ⬜ 保存/加载过滤

#### 排序功能 (10个)
- ✅ 升序/降序
- ✅ 切换方向/列
- ⬜ 默认排序
- ⬜ 多列排序
- ⬜ NULL排序

#### 批量选择 (14个)
- ✅ 选择/取消选择
- ✅ 全选当前页
- ✅ 翻页保留
- ⬜ 全选所有页
- ⬜ 反选
- ⬜ 范围选择

#### 工具栏操作 (8个)
- ✅ 新建/导出/导入/刷新
- ⬜ 自定义操作
- ⬜ 操作权限

### 3.2 useImportExportApi 测试用例 (32个)

#### 导出功能 (10个)
- ✅ Authorization头
- ✅ 导出参数
- ✅ 导出失败
- ⬜ 导出进度
- ⬜ 级联导出

#### 模板下载 (6个)
- ✅ 模板URL
- ✅ 认证token
- ⬜ 模板内容

#### 导入预览 (8个)
- ✅ 预览返回
- ✅ 校验错误
- ⬜ 必填/格式/重复校验

#### 执行导入 (8个)
- ✅ 执行导入
- ✅ Upsert/Skip/Replace策略
- ⬜ 导入进度

---

## 四、快速开始

### 4.1 安装依赖

```bash
npm install -D vitest @vue/test-utils happy-dom msw
```

### 4.2 运行所有测试

```bash
npm test
```

### 4.3 运行特定测试

```bash
# 单元测试
npm run test:unit

# 组件测试
npm run test:component

# 集成测试
npm run test:integration

# E2E测试
npm run test:e2e
```

### 4.4 生成覆盖率报告

```bash
npm run test:coverage
```

---

## 五、测试文件结构

```
tests/
├── setup.js                 # 测试环境设置
├── mocks/
│   ├── server.js           # MSW服务器
│   └── handlers.js        # API Mock处理
│
├── unit/
│   └── composables/
│       ├── useMetaList.spec.js
│       └── useImportExportApi.spec.js
│
├── component/
│   ├── ExportDialog.spec.js
│   ├── ImportDialog.spec.js
│   └── TableHeaderFilter.spec.js
│
├── integration/
│   └── UserManagement.spec.js
│
└── e2e/
    └── user-management.spec.js
```

---

## 六、编写测试指南

### 6.1 单元测试模板

```javascript
describe('模块名称', () => {
  describe('功能分组', () => {
    it('用例描述', () => {
      // Arrange - 准备测试数据
      const input = 'test'
      
      // Act - 执行被测试的函数
      const result = myFunction(input)
      
      // Assert - 验证结果
      expect(result).toBe('expected')
    })
  })
})
```

### 6.2 组件测试模板

```javascript
describe('组件名称', () => {
  it('用例描述', () => {
    // Arrange
    const wrapper = mount(Component, {
      props: {
        prop1: 'value1'
      }
    })
    
    // Act
    await wrapper.find('button').trigger('click')
    
    // Assert
    expect(wrapper.emitted('event')).toBeTruthy()
  })
})
```

### 6.3 Mock API示例

```javascript
import { rest } from 'msw'

export const handlers = [
  rest.get('/api/v2/bo/:entity', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        data: { items: [], total: 0 }
      })
    )
  })
]
```

---

## 七、持续集成

### 7.1 CI配置

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-node@v2
        with:
          node-version: '18'
      - run: npm ci
      - run: npm test
      - run: npm run test:coverage
```

### 7.2 覆盖率检查

- 核心模块覆盖率必须 ≥ 90%
- 新代码覆盖率必须 ≥ 80%
- 覆盖率下降必须修复

---

## 八、测试报告

### 8.1 本地报告

```bash
npm run test:coverage
# 生成 coverage/index.html
```

### 8.2 CI报告

- GitHub Actions 自动生成
- Codecov 覆盖率追踪
- Slack/邮件通知失败

---

## 九、常见问题

### Q1: 测试失败怎么办？

1. 查看测试输出确定失败原因
2. 检查是否代码改动导致
3. 更新测试用例或修复代码
4. 确保所有测试通过后再合并

### Q2: 如何调试测试？

```javascript
it('调试测试', () => {
  const wrapper = mount(Component)
  console.log(wrapper.html()) // 打印组件HTML
  debugger // 添加断点
})
```

### Q3: 如何跳过测试？

```javascript
it.skip('跳过的测试', () => {
  // 这个测试不会运行
})
```

---

## 十、联系方式

如有测试相关问题，请联系：
- 测试负责人: @test-team
- Slack: #test-support
